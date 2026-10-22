"""
Servicio de Caché, Bloqueos Distribuidos, Sesiones, Rate Limiting y Denylist con Redis.

Proporciona soporte de persistencia en memoria y concurrencia para:
1. Gestión de sesiones web y API con sliding TTL y mapeo por usuario.
2. Denylist de tokens JWT revocados (logout instantáneo con TTL < 0.8ms).
3. Caché de lectura context-aware (Cache-Aside con invalidación por patrón).
4. Contadores atómicos de operaciones (INCR, HINCRBY por servicio/fecha).
5. Rate limiting distribuido por ventana fija atómica con cabeceras estándar.
6. Almacenamiento temporal (ephemeral state para carritos POS y tickets).
7. Inspección y gobernanza de TTL.
8. Bloqueos distribuidos atómicos (SET NX EX + Lua script release + context manager).

PostgreSQL se mantiene como la única fuente de verdad transaccional.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timezone
import json
import logging
import uuid
from typing import Any, Generator

import redis
from app.config import Config

logger = logging.getLogger("freshtrack.cache")

_pool: redis.ConnectionPool | None = None
_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis | None:
    """Devuelve un cliente de Redis reutilizando el pool de conexiones."""
    global _pool, _client
    if _client is not None:
        return _client

    try:
        if Config.REDIS_PASSWORD:
            _pool = redis.ConnectionPool(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                password=Config.REDIS_PASSWORD,
                db=Config.REDIS_DB,
                socket_connect_timeout=2.0,
                decode_responses=True,
            )
        else:
            _pool = redis.ConnectionPool(
                host=Config.REDIS_HOST,
                port=Config.REDIS_PORT,
                db=Config.REDIS_DB,
                socket_connect_timeout=2.0,
                decode_responses=True,
            )
        _client = redis.Redis(connection_pool=_pool)
        _client.ping()
        return _client
    except Exception as exc:
        logger.warning("No se pudo conectar a Redis en %s:%s: %s", Config.REDIS_HOST, Config.REDIS_PORT, exc)
        return None


# =============================================================================
# 1. Gestión de Sesiones Distribuidas
# =============================================================================
def crear_sesion_redis(session_id: str, datos: dict[str, Any], ttl_segundos: int = 28800) -> bool:
    """
    Registra una sesión de usuario en Redis con TTL y vincula al conjunto de sesiones del usuario.
    Clave: session:{session_id} -> JSON
    Índice: user:sessions:{id_usuario} -> Set de session_ids
    """
    r = get_redis_client()
    if r is None or not session_id:
        return False
    try:
        clave_sesion = f"session:{session_id}"
        serializado = json.dumps(datos, default=str)
        pipeline = r.pipeline()
        pipeline.setex(clave_sesion, ttl_segundos, serializado)

        id_usuario = datos.get("id_usuario") or datos.get("sub")
        if id_usuario:
            clave_usuario = f"user:sessions:{id_usuario}"
            pipeline.sadd(clave_usuario, session_id)
            pipeline.expire(clave_usuario, ttl_segundos + 3600)

        pipeline.execute()
        return True
    except Exception as exc:
        logger.error("Error al crear sesión %s en Redis: %s", session_id, exc)
        return False


def obtener_sesion_redis(session_id: str, refrescar_ttl: bool = True, ttl_segundos: int = 28800) -> dict[str, Any] | None:
    """Recupera la información de sesión y renueva su TTL si refrescar_ttl es True (sliding window)."""
    r = get_redis_client()
    if r is None or not session_id:
        return None
    try:
        clave_sesion = f"session:{session_id}"
        val = r.get(clave_sesion)
        if val is None:
            return None
        if refrescar_ttl:
            r.expire(clave_sesion, ttl_segundos)
        return json.loads(val)
    except Exception as exc:
        logger.warning("Error al leer sesión %s de Redis: %s", session_id, exc)
        return None


def eliminar_sesion_redis(session_id: str) -> bool:
    """Elimina la sesión y la desvincula del conjunto de sesiones de su usuario."""
    r = get_redis_client()
    if r is None or not session_id:
        return False
    try:
        clave_sesion = f"session:{session_id}"
        val = r.get(clave_sesion)
        id_usuario = None
        if val:
            try:
                datos = json.loads(val)
                id_usuario = datos.get("id_usuario") or datos.get("sub")
            except Exception:
                pass

        pipeline = r.pipeline()
        pipeline.delete(clave_sesion)
        if id_usuario:
            pipeline.srem(f"user:sessions:{id_usuario}", session_id)
        pipeline.execute()
        return True
    except Exception as exc:
        logger.warning("Error al eliminar sesión %s de Redis: %s", session_id, exc)
        return False


def listar_sesiones_usuario(id_usuario: str) -> list[str]:
    """Obtiene los IDs de sesiones activas asociadas a un usuario."""
    r = get_redis_client()
    if r is None or not id_usuario:
        return []
    try:
        clave = f"user:sessions:{id_usuario}"
        sesiones = list(r.smembers(clave))
        # Limpiar referencias a sesiones que ya expiraron
        vivas = []
        for sid in sesiones:
            if r.exists(f"session:{sid}"):
                vivas.append(sid)
            else:
                r.srem(clave, sid)
        return vivas
    except Exception as exc:
        logger.warning("Error al listar sesiones de usuario %s en Redis: %s", id_usuario, exc)
        return []


def cerrar_sesiones_usuario(id_usuario: str) -> int:
    """Cierra y purga todas las sesiones activas de un usuario (ej. ante cambio de clave o bloqueo)."""
    r = get_redis_client()
    if r is None or not id_usuario:
        return 0
    try:
        sesiones = listar_sesiones_usuario(id_usuario)
        if not sesiones:
            return 0
        pipeline = r.pipeline()
        for sid in sesiones:
            pipeline.delete(f"session:{sid}")
        pipeline.delete(f"user:sessions:{id_usuario}")
        pipeline.execute()
        return len(sesiones)
    except Exception as exc:
        logger.error("Error al cerrar todas las sesiones del usuario %s: %s", id_usuario, exc)
        return 0


# =============================================================================
# 2. Denylist de JWT (Tokens Revocados)
# =============================================================================
def revocar_jwt(jti: str, ttl_segundos: int = 28800) -> bool:
    """Registra un JTI en la denylist de Redis con TTL para rechazo inmediato (<0.8ms)."""
    r = get_redis_client()
    if r is None or not jti:
        return False
    try:
        clave = f"jwt:denylist:{jti}"
        r.setex(clave, max(60, ttl_segundos), "1")
        return True
    except Exception as exc:
        logger.error("Error al revocar JWT %s en Redis: %s", jti, exc)
        return False


def esta_jwt_revocado(jti: str) -> bool:
    """Consulta si un token ha sido revocado en la denylist de Redis."""
    r = get_redis_client()
    if r is None or not jti:
        return False
    try:
        clave = f"jwt:denylist:{jti}"
        return bool(r.exists(clave))
    except Exception as exc:
        logger.warning("Error al consultar denylist de JWT en Redis: %s", exc)
        return False


def contar_tokens_revocados() -> int:
    """Devuelve la cantidad de tokens actualmente en la denylist."""
    r = get_redis_client()
    if r is None:
        return 0
    try:
        return sum(1 for _ in r.scan_iter(match="jwt:denylist:*", count=100))
    except Exception as exc:
        logger.warning("Error al contar tokens revocados: %s", exc)
        return 0


# =============================================================================
# 3. Caché Context-Aware de Consultas (Cache-Aside)
# =============================================================================
def get_json(clave: str) -> Any | None:
    """Recupera un objeto JSON cacheado."""
    r = get_redis_client()
    if r is None:
        return None
    try:
        val = r.get(clave)
        if val is None:
            return None
        return json.loads(val)
    except Exception as exc:
        logger.warning("Error al leer clave %s de Redis: %s", clave, exc)
        return None


def set_json(clave: str, valor: Any, ttl_segundos: int = 300) -> bool:
    """Guarda un objeto serializable en JSON con expiración."""
    r = get_redis_client()
    if r is None:
        return False
    try:
        serializado = json.dumps(valor, default=str)
        r.setex(clave, ttl_segundos, serializado)
        return True
    except Exception as exc:
        logger.warning("Error al escribir clave %s en Redis: %s", clave, exc)
        return False


def borrar_clave(clave: str) -> bool:
    """Elimina una clave de la caché."""
    r = get_redis_client()
    if r is None:
        return False
    try:
        r.delete(clave)
        return True
    except Exception as exc:
        logger.warning("Error al borrar clave %s de Redis: %s", clave, exc)
        return False


def invalidar_patron(patron: str) -> int:
    """
    Elimina todas las claves que coincidan con el patrón usando SCAN (no bloquea el servidor).
    Ejemplo: invalidar_patron('catalog:*')
    """
    r = get_redis_client()
    if r is None:
        return 0
    try:
        eliminadas = 0
        pipeline = r.pipeline()
        for clave in r.scan_iter(match=patron, count=100):
            pipeline.delete(clave)
            eliminadas += 1
            if eliminadas % 500 == 0:
                pipeline.execute()
                pipeline = r.pipeline()
        if eliminadas % 500 != 0:
            pipeline.execute()
        return eliminadas
    except Exception as exc:
        logger.warning("Error al invalidar patrón %s en Redis: %s", patron, exc)
        return 0


# =============================================================================
# 4. Contadores de Operaciones
# =============================================================================
def incrementar_contador(servicio: str, operacion: str, delta: int = 1, ttl_segundos: int = 604800) -> int:
    """
    Incrementa atómicamente un contador de operaciones operacionales.
    Clave: counter:ops:{servicio}:{operacion}:{YYYYMMDD} (TTL 7 días)
    """
    r = get_redis_client()
    if r is None:
        return 0
    try:
        fecha_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        clave = f"counter:ops:{servicio}:{operacion}:{fecha_str}"
        pipeline = r.pipeline()
        pipeline.incrby(clave, delta)
        pipeline.expire(clave, ttl_segundos)
        res = pipeline.execute()
        return int(res[0])
    except Exception as exc:
        logger.warning("Error al incrementar contador %s:%s en Redis: %s", servicio, operacion, exc)
        return 0


def obtener_contadores(servicio: str | None = None, fecha_str: str | None = None) -> dict[str, int]:
    """Obtiene el estado de los contadores operacionales."""
    r = get_redis_client()
    if r is None:
        return {}
    try:
        if not fecha_str:
            fecha_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        patron = f"counter:ops:{servicio or '*'}:*:{fecha_str}"
        resultado = {}
        for clave in r.scan_iter(match=patron, count=100):
            val = r.get(clave)
            if val is not None:
                resultado[clave] = int(val)
        return resultado
    except Exception as exc:
        logger.warning("Error al leer contadores de Redis: %s", exc)
        return {}


# =============================================================================
# 5. Rate Limiting Distribuido (Ventana Fija / Deslizante Atómica)
# =============================================================================
_LUA_RATE_LIMIT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""

def verificar_rate_limit(identificador: str, limite: int = 60, ventana_segundos: int = 60) -> tuple[bool, int, int]:
    """
    Aplica rate limiting distribuido usando un script Lua atómico (INCR + EXPIRE + TTL).
    Devuelve (permitido, restantes, segundos_para_reset).
    """
    r = get_redis_client()
    if r is None:
        # Fallback abierto en caso de no disponibilidad de Redis
        return True, limite - 1, ventana_segundos

    clave = f"ratelimit:{identificador}"
    try:
        res = r.eval(_LUA_RATE_LIMIT, 1, clave, ventana_segundos)
        conteo, ttl = int(res[0]), max(0, int(res[1]))
        restante = max(0, limite - conteo)
        permitido = conteo <= limite
        return permitido, restante, ttl
    except Exception as exc:
        logger.warning("Error al evaluar rate limit en Redis para %s: %s", identificador, exc)
        return True, limite, ventana_segundos


# =============================================================================
# 6. Almacenamiento Temporal (Ephemeral State / Carritos / OTP)
# =============================================================================
def guardar_temporal(categoria: str, clave_id: str, datos: Any, ttl_segundos: int = 900) -> bool:
    """Guarda un estado temporal (ej. carrito pre-venta POS o ticket efímero) con TTL (def. 15 min)."""
    clave = f"temp:{categoria}:{clave_id}"
    return set_json(clave, datos, ttl_segundos=ttl_segundos)


def obtener_temporal(categoria: str, clave_id: str) -> Any | None:
    """Recupera un estado temporal sin eliminarlo."""
    clave = f"temp:{categoria}:{clave_id}"
    return get_json(clave)


_LUA_CONSUMIR_TEMPORAL = """
local val = redis.call('GET', KEYS[1])
if val then
    redis.call('DEL', KEYS[1])
end
return val
"""

def consumir_temporal(categoria: str, clave_id: str) -> Any | None:
    """Recupera y elimina atómicamente el estado temporal en una sola operación (ej. canjear ticket o carrito)."""
    r = get_redis_client()
    if r is None:
        return None
    clave = f"temp:{categoria}:{clave_id}"
    try:
        val = r.eval(_LUA_CONSUMIR_TEMPORAL, 1, clave)
        if not val:
            return None
        return json.loads(val)
    except Exception as exc:
        logger.warning("Error al consumir temporal %s de Redis: %s", clave, exc)
        return None


# =============================================================================
# 7. Manejo y Consulta de TTL
# =============================================================================
def obtener_ttl(clave: str) -> int:
    """Devuelve los segundos restantes de vida de una clave (-2 si no existe, -1 si es persistente)."""
    r = get_redis_client()
    if r is None:
        return -2
    try:
        return int(r.ttl(clave))
    except Exception as exc:
        logger.warning("Error al consultar TTL de %s: %s", clave, exc)
        return -2


# =============================================================================
# 8. Bloqueos Distribuidos Atómicos (Atomic Redlock-style)
# =============================================================================
_LUA_RELEASE_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

def adquirir_bloqueo(nombre_recurso: str, timeout_segundos: int = 10) -> str | None:
    """
    Intenta adquirir un bloqueo distribuido atómico (SET NX EX).
    Devuelve un token único (UUID) si fue exitoso, o None si el recurso está bloqueado.
    """
    r = get_redis_client()
    if r is None:
        return None
    token = uuid.uuid4().hex
    clave = f"lock:{nombre_recurso}"
    try:
        adquirido = r.set(clave, token, nx=True, ex=timeout_segundos)
        return token if adquirido else None
    except Exception as exc:
        logger.warning("Error al adquirir bloqueo %s: %s", nombre_recurso, exc)
        return None


def liberar_bloqueo(nombre_recurso: str, token: str) -> bool:
    """Libera el bloqueo atómicamente solo si el token coincide con el poseedor actual."""
    r = get_redis_client()
    if r is None or not token:
        return False
    clave = f"lock:{nombre_recurso}"
    try:
        resultado = r.eval(_LUA_RELEASE_LOCK, 1, clave, token)
        return bool(resultado)
    except Exception as exc:
        logger.warning("Error al liberar bloqueo %s: %s", nombre_recurso, exc)
        return False


@contextlib.contextmanager
def bloqueo_distribuido(nombre_recurso: str, timeout_segundos: int = 10) -> Generator[str | None, None, None]:
    """Context manager para asegurar adquisición y liberación segura de bloqueos distribuidos."""
    token = adquirir_bloqueo(nombre_recurso, timeout_segundos=timeout_segundos)
    try:
        yield token
    finally:
        if token:
            liberar_bloqueo(nombre_recurso, token)
