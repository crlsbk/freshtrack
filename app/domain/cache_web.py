"""
Cache-Aside en Redis para las lecturas pesadas de la plataforma web.

  * `CACHE_WEB_ACTIVA=false` lo desactiva (benchmark "con vs. sin Redis").
  * Si Redis no está disponible, se consulta PostgreSQL directo.
  * Los valores se normalizan (Decimal → float, fechas → ISO) para JSON; los
    filtros de plantilla (`fecha_hora`, `cantidad`, …) aceptan ambos tipos.
  * `con_lock=True` evita la "estampida": si el valor no está y otro worker ya
    lo está calculando, se espera brevemente a que lo publique en lugar de
    lanzar la misma consulta pesada en paralelo (2 vCPU se saturan rápido).
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from app.services import cache_service


def normalizar_cache(obj: Any) -> Any:
    """Convierte Decimal y fechas para serializar limpio a Redis sin cambiar tipos numéricos."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: normalizar_cache(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalizar_cache(v) for v in obj]
    return obj


def cache_activa() -> bool:
    return os.getenv("CACHE_WEB_ACTIVA", "true").strip().lower() not in ("0", "false", "no")


def con_cache_web(
    clave: str,
    ttl: int,
    fn: Callable[[], Any],
    *,
    con_lock: bool = False,
    espera_max_seg: float = 8.0,
) -> Any:
    """Devuelve `fn()` cacheado en Redis bajo `clave` durante `ttl` segundos."""
    if not cache_activa() or cache_service.get_redis_client() is None:
        return fn()

    cached = cache_service.get_json(clave)
    if cached is not None:
        cache_service.incrementar_contador("web", "cache_hit")
        return cached
    cache_service.incrementar_contador("web", "cache_miss")

    if not con_lock:
        datos = normalizar_cache(fn())
        cache_service.set_json(clave, datos, ttl_segundos=ttl)
        return datos

    token = cache_service.adquirir_bloqueo(f"calc:{clave}", timeout_segundos=max(30, int(espera_max_seg * 4)))
    if token is None:
        # Otro worker lo está calculando: esperar a que lo publique.
        limite = time.monotonic() + espera_max_seg
        while time.monotonic() < limite:
            time.sleep(0.25)
            cached = cache_service.get_json(clave)
            if cached is not None:
                cache_service.incrementar_contador("web", "cache_hit_espera")
                return cached
        # Se agotó la espera: calcular de todos modos (mejor lento que vacío).
        return normalizar_cache(fn())
    try:
        datos = normalizar_cache(fn())
        cache_service.set_json(clave, datos, ttl_segundos=ttl)
        return datos
    finally:
        cache_service.liberar_bloqueo(f"calc:{clave}", token)


def invalidar(*patrones: str) -> None:
    """Invalida patrones de llaves sin propagar fallos de Redis."""
    for patron in patrones:
        try:
            cache_service.invalidar_patron(patron)
        except Exception:  # noqa: BLE001
            pass


def invalida(*patrones: str):
    """
    Decorador para funciones de escritura: al terminar sin error invalida los
    patrones dados (p. ej. ``@invalida("web:triaje:*")``).
    """
    import functools

    def deco(fn):
        @functools.wraps(fn)
        def envoltura(*args, **kwargs):
            resultado = fn(*args, **kwargs)
            invalidar(*patrones)
            return resultado

        return envoltura

    return deco


def contar_cacheado(sql_desde: str, params: dict, ttl: int = 60) -> int:
    """
    `SELECT COUNT(*) <sql_desde>` cacheado por (SQL, filtros).

    Sustituye a `COUNT(*) OVER ()` en los listados paginados de los
    microservicios: esa ventana obliga a leer TODAS las filas filtradas antes
    del LIMIT en cada página. El total para la paginación tolera ~1 min de
    desfase. `lim`/`off` se ignoran (no cambian el total).
    """
    import hashlib

    from app.db import escalar

    filtros = {k: v for k, v in params.items() if k not in ("lim", "off", "limite", "offset")}
    huella = hashlib.sha1(
        (" ".join(sql_desde.split()) + repr(sorted(filtros.items(), key=lambda kv: kv[0]))).encode("utf-8")
    ).hexdigest()
    return int(
        con_cache_web(f"web:count:{huella}", ttl, lambda: escalar(f"SELECT COUNT(*) {sql_desde}", **filtros) or 0)
    )
