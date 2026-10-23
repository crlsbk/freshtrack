"""
Cliente HTTP unificado de Microservicios para FreshTrack Web.

Permite a la aplicación web (puerto 5000) actuar como API Gateway / Frontend BFF,
consumiendo los microservicios en puertos 5001-5008 vía HTTP REST/JSON con
propagación de JWT, identidad del usuario y correlación distribuida.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Callable

from flask import g, has_request_context, request, session
import requests

log = logging.getLogger("freshtrack.services_client")

# Mapeo de microservicios y URLs base
SERVICIOS_URL = {
    "auth": os.getenv("SVC_AUTH_URL", "http://127.0.0.1:5001"),
    "catalog": os.getenv("SVC_CATALOG_URL", "http://127.0.0.1:5002"),
    "inventory": os.getenv("SVC_INVENTORY_URL", "http://127.0.0.1:5003"),
    "commercial": os.getenv("SVC_COMMERCIAL_URL", "http://127.0.0.1:5004"),
    "asn": os.getenv("SVC_ASN_URL", "http://127.0.0.1:5005"),
    "planning": os.getenv("SVC_PLANNING_URL", "http://127.0.0.1:5006"),
    "alerts": os.getenv("SVC_ALERTS_URL", "http://127.0.0.1:5007"),
    "audit": os.getenv("SVC_AUDIT_URL", "http://127.0.0.1:5008"),
}


def _obtener_correlation_id() -> str:
    """Recupera o genera un correlation_id para la trazabilidad distribuida."""
    if has_request_context():
        cid = getattr(g, "correlation_id", None) or request.headers.get("X-Correlation-Id")
        if not cid:
            cid = uuid.uuid4().hex
            g.correlation_id = cid
        return str(cid)
    return uuid.uuid4().hex


def _cabeceras_contexto() -> dict[str, str]:
    """Construye las cabeceras HTTP con token Bearer y contexto distribuido."""
    cabeceras = {
        "X-Correlation-Id": _obtener_correlation_id(),
        "Accept": "application/json",
    }
    if has_request_context():
        # Inyectar Bearer token si la sesión web lo tiene
        token = session.get("jwt_token") or getattr(g, "jwt_token", None)
        if token:
            cabeceras["Authorization"] = f"Bearer {token}"

        user_id = session.get("user_id") or getattr(g, "usuario_actual", {}).get("id_usuario")
        if user_id:
            cabeceras["X-User-Id"] = str(user_id)

        role = session.get("role") or getattr(g, "usuario_actual", {}).get("rol_clave")
        if role:
            cabeceras["X-User-Role"] = str(role)

        loc_id = session.get("location_id") or getattr(g, "usuario_actual", {}).get("id_locacion")
        if loc_id:
            cabeceras["X-Location-Id"] = str(loc_id)

    return cabeceras


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
    headers: dict[str, str] | None = None,
    timeout: float = 6.0,
    fallback_fn: Callable[[], Any] | None = None,
) -> Any:
    """
    Invoca un microservicio vía HTTP con propagación de contexto.
    Si el microservicio no está disponible y se provee fallback_fn, ejecuta el fallback.
    """
    base_url = SERVICIOS_URL.get(service_name)
    if not base_url:
        raise ValueError(f"Microservicio desconocido: {service_name}")

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    req_headers = _cabeceras_contexto()
    if headers:
        req_headers.update(headers)

    cid = req_headers.get("X-Correlation-Id", "-")

    try:
        resp = requests.request(
            method=method.upper(),
            url=url,
            json=json_data,
            params=params,
            headers=req_headers,
            timeout=timeout,
        )

        log.info(
            "HTTP %s %s -> %s (cid=%s)",
            method.upper(),
            url,
            resp.status_code,
            cid,
        )

        # Si el servicio responde con éxito (2xx)
        if 200 <= resp.status_code < 300:
            if resp.status_code == 204 or not resp.content:
                return {}
            try:
                return resp.json()
            except Exception:
                return resp.text

        # Si el servicio devuelve error controlado (4xx o 5xx)
        try:
            err_json = resp.json()
            err_code = err_json.get("error", "error_servicio")
            err_msg = err_json.get("mensaje", err_json.get("message", resp.text))
            err_det = err_json.get("detalles")
        except Exception:
            err_code = f"http_{resp.status_code}"
            err_msg = resp.text
            err_det = None

        log.warning("Microservicio %s devolvió error %s: %s", service_name, resp.status_code, err_msg)
        raise ServiceError(resp.status_code, err_code, err_msg, err_det)

    except requests.exceptions.RequestException as exc:
        log.warning(
            "Fallo de conexión HTTP al microservicio %s (%s): %s (cid=%s)",
            service_name,
            url,
            exc,
            cid,
        )
        if fallback_fn is not None:
            log.info("Ejecutando fallback de dominio para %s", service_name)
            return fallback_fn()
        raise ServiceError(503, "servicio_no_disponible", f"Microservicio {service_name} no disponible: {exc}")
