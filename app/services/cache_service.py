"""
Servicio de Caché, Bloqueos Distribuidos y Denylist de JWT con Redis.

Proporciona soporte de persistencia en memoria y concurrencia para:
- Denylist de tokens JWT revocados (logout instantáneo con TTL).
- Caché de lectura context-aware (por tienda / SKU / catálogo).
- Bloqueos distribuidos atómicos para concurrencia en reserva de lotes y ventas.

PostgreSQL se mantiene como la única fuente de verdad transaccional.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

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


# -----------------------------------------------------------------------------
# Denylist de JWT (Tokens Revocados)
# -----------------------------------------------------------------------------
def revocar_jwt(jti: str, ttl_segundos: int = 28800) -> bool:
    """Registra un JTI en la denylist de Redis con TTL para rechazo inmediato."""
    r = get_redis_client()
    if r is None:
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
    if r is None:
        return False
    try:
        clave = f"jwt:denylist:{jti}"
        return bool(r.exists(clave))
    except Exception as exc:
        logger.warning("Error al consultar denylist de JWT en Redis: %s", exc)
        return False


# -----------------------------------------------------------------------------
# Caché Context-Aware de Consultas
# -----------------------------------------------------------------------------
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
    """Elimina una clave o patrón de clave de la caché."""
    r = get_redis_client()
    if r is None:
        return False
    try:
        r.delete(clave)
        return True
    except Exception as exc:
        logger.warning("Error al borrar clave %s de Redis: %s", clave, exc)
        return False


# -----------------------------------------------------------------------------
# Bloqueos Distribuidos Atómicos (Atomic Locks)
# -----------------------------------------------------------------------------
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
