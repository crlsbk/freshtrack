"""
Últimos errores registrados por microservicio (para el panel /ops/status).

Se alimenta desde tres lugares:
  * error_response() con status >= 500 (incluye el manejador de errores no
    controlados de crear_servicio, que responde con error_response(500, ...)).
  * El monitor (app/domain/monitoreo.py) cuando el /health de un servicio
    responde DEGRADED o no responde.

Cada servicio tiene una lista acotada en Redis:
    monitor:errores:<servicio>  →  LPUSH + LTRIM (los 20 más recientes), TTL 7 días

Solo se guardan datos seguros para mostrar: hora, origen, endpoint (la regla de
la ruta, sin ids ni parámetros), código, mensaje público (el mismo que recibe
el cliente) y correlation_id para buscar el detalle en el log. Nunca trazas ni
SQL. Si Redis no responde, registrar no hace nada y consultar devuelve None
(«sin datos»).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.services import cache_service

logger = logging.getLogger("freshtrack.registro_errores")

PREFIJO = "monitor:errores:"
MAXIMO = 20
TTL_SEGUNDOS = 7 * 24 * 3600
_LARGO_MENSAJE = 200


def _clave(servicio: str) -> str:
    return PREFIJO + (servicio or "desconocido")


def registrar_error(
    servicio: str,
    *,
    endpoint: str,
    codigo: str,
    mensaje: str,
    status: int | None = None,
    correlation_id: str | None = None,
    origen: str = "http",
) -> bool:
    """
    Agrega un error a la lista del servicio. Si el error más reciente es idéntico
    (mismo origen, endpoint, código y mensaje; p. ej. el monitor viendo la misma
    dependencia caída en cada refresco) solo actualiza su hora y cuenta la
    repetición, para no desplazar errores distintos.
    """
    r = cache_service.get_redis_client()
    if r is None:
        return False
    entrada: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": origen,
        "endpoint": (endpoint or "-")[:120],
        "status": status,
        "code": (codigo or "error")[:60],
        "message": (mensaje or "")[:_LARGO_MENSAJE],
        "correlation_id": (correlation_id or "")[:64],
        "repeticiones": 1,
    }
    clave = _clave(servicio)
    try:
        previo_crudo = r.lindex(clave, 0)
        if previo_crudo:
            try:
                previo = json.loads(previo_crudo)
            except (TypeError, ValueError):
                previo = {}
            if all(previo.get(k) == entrada[k] for k in ("source", "endpoint", "code", "message")):
                entrada["repeticiones"] = int(previo.get("repeticiones") or 1) + 1
                r.lset(clave, 0, json.dumps(entrada))
                r.expire(clave, TTL_SEGUNDOS)
                return True
        pipe = r.pipeline()
        pipe.lpush(clave, json.dumps(entrada))
        pipe.ltrim(clave, 0, MAXIMO - 1)
        pipe.expire(clave, TTL_SEGUNDOS)
        pipe.execute()
        return True
    except Exception as exc:  # noqa: BLE001 — registrar un error nunca debe provocar otro
        logger.warning("No se pudo registrar el último error de %s: %s", servicio, exc)
        return False


def ultimos_errores(servicio: str, limite: int = 5) -> list[dict] | None:
    """Errores más recientes primero; None si Redis no está disponible (sin datos)."""
    r = cache_service.get_redis_client()
    if r is None:
        return None
    try:
        crudos = r.lrange(_clave(servicio), 0, max(0, limite - 1))
    except Exception:  # noqa: BLE001
        return None
    errores = []
    for crudo in crudos:
        try:
            errores.append(json.loads(crudo))
        except (TypeError, ValueError):
            continue
    return errores


def ultimo_error(servicio: str) -> dict | None:
    errores = ultimos_errores(servicio, limite=1)
    return errores[0] if errores else None


def registrar_desde_respuesta(status: int, codigo: str, mensaje: str, correlation_id: str | None) -> None:
    """Gancho de error_response(): registra los 5xx del microservicio que responde."""
    if status < 500:
        return
    try:
        from flask import current_app, has_request_context, request

        if not has_request_context():
            return
        servicio = current_app.name
        if not servicio.startswith("svc-"):
            return  # la web tiene su propio manejo de errores
        regla = request.url_rule.rule if request.url_rule is not None else request.path
        registrar_error(
            servicio,
            endpoint=f"{request.method} {regla}",
            codigo=codigo,
            mensaje=mensaje,
            status=status,
            correlation_id=correlation_id,
        )
    except Exception:  # noqa: BLE001
        pass
