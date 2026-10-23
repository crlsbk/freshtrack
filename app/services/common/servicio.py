"""
Fábrica común de microservicios FreshTrack.

Cada servicio se crea con `crear_servicio(...)`, que le da el mismo esqueleto:

- /health con el estado real de sus dependencias (PostgreSQL, MongoDB, Redis).
- Manejo estandarizado de errores HTTP (400/401/403/404/405/409/415/429/500)
  en JSON o XML, sin exponer trazas internas.
- Registro de actividad: cada petición se escribe en el log con método, ruta,
  estado, duración, usuario y X-Correlation-Id; además incrementa contadores
  por servicio en Redis.
- Publicación de los contratos XSD en /api/v1/contracts/<nombre>.xsd.
- Documentación OpenAPI/Swagger en /api/v1/openapi.json y /api/v1/docs.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterable

from datetime import date, datetime
from decimal import Decimal

from flask import Flask, Response, g, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException

from app.config import Config
from app.services import cache_service, doc_store
from app.services.common.response import DIR_XSD, ErrorApi, correlation_id, error_response, render_response
from app.services.common.swagger import registrar_openapi

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_CODIGOS_HTTP = {
    400: "solicitud_invalida",
    401: "no_autenticado",
    403: "acceso_denegado",
    404: "no_encontrado",
    405: "metodo_no_permitido",
    409: "conflicto",
    413: "cuerpo_demasiado_grande",
    415: "tipo_no_soportado",
    422: "entidad_no_procesable",
    429: "limite_excedido",
}


def _estado_dependencias(dependencias: Iterable[str]) -> dict[str, bool]:
    estado: dict[str, bool] = {}
    for dep in dependencias:
        ok = False
        try:
            if dep == "postgres":
                from app.db import escalar

                ok = escalar("SELECT 1") == 1
            elif dep == "redis":
                r = cache_service.get_redis_client()
                ok = bool(r and r.ping())
            elif dep == "mongo":
                db = doc_store.get_mongo_db()
                ok = db is not None and bool(db.client.admin.command("ping").get("ok"))
        except Exception:
            ok = False
        estado[dep] = ok
    return estado


class JsonContrato(DefaultJSONProvider):
    """JSON del contrato: fechas ISO 8601, decimales como número, UTF-8 sin escapar y orden original."""

    sort_keys = False
    ensure_ascii = False

    @staticmethod
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return DefaultJSONProvider.default(o)


def crear_servicio(
    nombre: str,
    titulo: str,
    descripcion: str,
    dependencias: tuple[str, ...] = ("postgres", "redis"),
    version: str = "1.0.0",
) -> Flask:
    """Crea la aplicación Flask de un microservicio con el comportamiento común."""
    app = Flask(nombre)
    app.config.from_object(Config)
    app.config["JSON_SORT_KEYS"] = False
    app.json = JsonContrato(app)
    log = logging.getLogger(f"freshtrack.{nombre}")

    @app.before_request
    def _inicio() -> None:
        g.t0 = time.perf_counter()
        correlation_id()

    @app.after_request
    def _registro(resp: Response) -> Response:
        dur_ms = (time.perf_counter() - getattr(g, "t0", time.perf_counter())) * 1000
        resp.headers["X-Correlation-Id"] = correlation_id()
        resp.headers["X-Service"] = nombre
        usuario = (getattr(g, "usuario_actual", None) or {}).get("email", "-")
        if request.path != "/health":
            log.info(
                "%s %s %s %.1fms user=%s cid=%s",
                request.method, request.full_path.rstrip("?"), resp.status_code, dur_ms, usuario, correlation_id(),
            )
            cache_service.incrementar_contador(nombre, f"http_{resp.status_code}")
        return resp

    # --- Errores estandarizados ------------------------------------------------
    @app.errorhandler(ErrorApi)
    def _error_api(exc: ErrorApi):
        return error_response(exc.status, exc.codigo, exc.mensaje, exc.detalles)

    @app.errorhandler(HTTPException)
    def _error_http(exc: HTTPException):
        codigo = exc.code or 500
        return error_response(codigo, _CODIGOS_HTTP.get(codigo, "error_http"), exc.description or exc.name)

    @app.errorhandler(Exception)
    def _error_interno(exc: Exception):
        log.exception("Error no controlado en %s %s (cid=%s)", request.method, request.path, correlation_id())
        cache_service.incrementar_contador(nombre, "errores_internos")
        return error_response(500, "error_interno", "Ocurrió un error inesperado. Consulte el log con el correlation_id.")

    # --- Infraestructura -------------------------------------------------------
    @app.get("/health")
    def health():
        """Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis)."""
        deps = _estado_dependencias(dependencias)
        sano = all(deps.values())
        return render_response(
            {
                "service": nombre,
                "status": "HEALTHY" if sano else "DEGRADED",
                "version": version,
                "dependencies": deps,
            },
            status=200 if sano else 503,
            root_tag="service_health",
        )

    @app.get("/api/v1/contracts/<nombre_xsd>.xsd")
    def contrato_xsd(nombre_xsd: str):
        """Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request)."""
        if not (DIR_XSD / f"{nombre_xsd}.xsd").is_file():
            return error_response(404, "no_encontrado", f"No existe el contrato '{nombre_xsd}.xsd'.")
        return send_from_directory(DIR_XSD, f"{nombre_xsd}.xsd", mimetype="application/xml")

    registrar_openapi(app, titulo=titulo, descripcion=descripcion, version=version)
    return app


def ejecutar(app: Flask, variable_puerto: str, puerto_defecto: int) -> None:
    puerto = int(os.getenv(variable_puerto, str(puerto_defecto)))
    app.run(host="0.0.0.0", port=puerto, debug=False)
