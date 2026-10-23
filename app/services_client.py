"""
Cliente HTTP de microservicios para la web (interfaz call_service / ServiceError).

Es una capa delgada sobre app/services/clientes.py: reenvía el JWT de la sesión y
un X-Correlation-Id, y convierte las respuestas de error del servicio en ServiceError.
No requiere dependencias externas (usa urllib a través de clientes.llamar).
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Callable

from app.services import clientes


class ServiceError(Exception):
    """Error devuelto por un microservicio."""

    def __init__(self, status_code: int, error_code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details


def call_service(
    service_name: str,
    method: str,
    path: str,
    *,
    json_data: Any = None,
    params: dict[str, Any] | None = None,
    timeout: float = 6.0,
    fallback_fn: Callable[[], Any] | None = None,
) -> Any:
    """
    Invoca un microservicio en nombre del usuario de la sesión. Si el servicio no
    responde y se da fallback_fn, se ejecuta (solo para consultas no críticas).
    """
    if service_name not in {s["clave"] for s in clientes.SERVICIOS}:
        raise ValueError(f"Microservicio desconocido: {service_name}")
    ruta = "/" + path.lstrip("/")
    if params:
        ruta += "?" + urllib.parse.urlencode(params)
    status, respuesta = clientes.como_usuario(service_name, method.upper(), ruta, json_data, timeout=timeout)
    if 200 <= status < 300:
        return respuesta if respuesta is not None else {}
    if status == 0:
        if fallback_fn is not None:
            return fallback_fn()
        raise ServiceError(503, "servicio_no_disponible", clientes.mensaje_error(service_name, 0, None))
    cuerpo = respuesta if isinstance(respuesta, dict) else {}
    raise ServiceError(status, cuerpo.get("error", f"http_{status}"),
                       clientes.mensaje_error(service_name, status, respuesta), cuerpo.get("detalles"))
