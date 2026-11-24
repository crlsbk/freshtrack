"""
Fábrica común de microservicios FreshTrack.

Cada servicio se crea con `crear_servicio(...)`, que le da el mismo esqueleto:

- /health con el estado real de sus dependencias (PostgreSQL, MongoDB, Redis)
  y el último error 5xx registrado (last_error, si hay).
- Manejo estandarizado de errores HTTP (400/401/403/404/405/409/415/429/500)
  en JSON o XML, sin exponer trazas internas.
- Registro de actividad: cada petición se escribe en el log con método, ruta,
  estado, duración, usuario y X-Correlation-Id; además incrementa contadores
  por servicio en Redis.
- Publicación de los contratos XSD en /api/v1/contracts/<nombre>.xsd.
- Documentación OpenAPI/Swagger en /api/v1/openapi.json y /api/v1/docs.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
import logging
import os
import time
from typing import Iterable

from flask import Flask, Response, g, request, send_from_directory
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

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


def _verificar_dependencia(dep: str) -> bool:
    try:
        if dep == "postgres":
            from app.db import escalar

            return escalar("SELECT 1") == 1
        if dep == "redis":
            r = cache_service.get_redis_client()
            return bool(r and r.ping())
        if dep == "mongo":
            db = doc_store.get_mongo_db()
            return db is not None and bool(db.client.admin.command("ping").get("ok"))
        if dep == "bucket":
            from app.services import object_storage

            return bool(object_storage.verificar_salud())
    except Exception:
        return False
    return False


def _estado_dependencias(dependencias: Iterable[str]) -> dict[str, bool]:
    deps_list = list(dependencias)
    if not deps_list:
        return {}
    if len(deps_list) == 1:
        return {deps_list[0]: _verificar_dependencia(deps_list[0])}
    with ThreadPoolExecutor(max_workers=min(len(deps_list), 4)) as pool:
        futuros = {dep: pool.submit(_verificar_dependencia, dep) for dep in deps_list}
        # Reconstruye en el orden exacto recibido para respetar <xs:sequence> en XML.
        return {dep: bool(futuros[dep].result()) for dep in deps_list}


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


_PARAMS_SECRETOS = {"token", "access_token", "refresh_token", "password", "jwt", "key", "secret"}


def _ruta_sin_secretos() -> str:
    """Ruta + query para el log, con los valores de parámetros sensibles ocultos."""
    if not request.query_string:
        return request.path
    from urllib.parse import parse_qsl, urlencode

    pares = [
        (k, "***" if k.lower() in _PARAMS_SECRETOS else v)
        for k, v in parse_qsl(request.query_string.decode("utf-8", "replace"), keep_blank_values=True)
    ]
    return f"{request.path}?{urlencode(pares)}"


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
    if os.getenv("TRUST_PROXY", str(Config.TRUST_PROXY)).lower() == "true":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    app.config["JSON_SORT_KEYS"] = False
    app.json = JsonContrato(app)
    log = logging.getLogger(f"freshtrack.{nombre}")
    inicio_mono = time.monotonic()
    iniciado_en = datetime.now(timezone.utc).isoformat()
    version_desplegada = os.getenv("APP_VERSION", "").strip() or version

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
        if not request.path.endswith("/health"):
            log.info(
                "%s %s %s %.1fms user=%s cid=%s",
                request.method, _ruta_sin_secretos(), resp.status_code, dur_ms, usuario, correlation_id(),
            )
            cache_service.incrementar_contador(nombre, f"http_{resp.status_code}")
            if resp.status_code >= 500:
                cache_service.incrementar_contador(nombre, "errores_5xx")
        return resp

    # --- Errores estandarizados ------------------------------------------------
    @app.errorhandler(ErrorApi)
    def _error_api(exc: ErrorApi):
        return error_response(exc.status, exc.codigo, exc.mensaje, exc.detalles)

    @app.errorhandler(HTTPException)
    def _error_http(exc: HTTPException):
        codigo = exc.code or 500
        if codigo == 413:
            tope = (app.config.get("MAX_CONTENT_LENGTH") or 0) / (1024 * 1024)
            return error_response(413, "cuerpo_demasiado_grande",
                                  f"La petición excede el tamaño máximo permitido ({tope:g} MB).")
        return error_response(codigo, _CODIGOS_HTTP.get(codigo, "error_http"), exc.description or exc.name)

    @app.errorhandler(Exception)
    def _error_interno(exc: Exception):
        log.exception("Error no controlado en %s %s (cid=%s)", request.method, request.path, correlation_id())
        cache_service.incrementar_contador(nombre, "errores_internos")
        return error_response(500, "error_interno", "Ocurrió un error inesperado. Consulte el log con el correlation_id.")

    # --- Infraestructura -------------------------------------------------------
    @app.get("/health")
    def health():
        """Estado del microservicio, proceso, latencia, versión y dependencias."""
        t0 = time.perf_counter()
        deps = _estado_dependencias(dependencias)
        response_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        sano = all(deps.values())
        cuerpo_extra = {}
        from app.services.registro_errores import ultimo_error

        ultimo = ultimo_error(nombre)
        if ultimo:
            cuerpo_extra["last_error"] = {
                k: ultimo.get(k) for k in ("timestamp", "source", "endpoint", "status", "code", "message", "correlation_id")
            }
        return render_response(
            {
                "service": nombre,
                "status": "HEALTHY" if sano else "DEGRADED",
                "version": version_desplegada,
                "process": {
                    "status": "UP",
                    "pid": os.getpid(),
                    "uptime_seconds": round(time.monotonic() - inicio_mono, 1),
                    "started_at": iniciado_en,
                },
                "response_time_ms": response_time_ms,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "dependencies": deps,
                **cuerpo_extra,
            },
            status=200 if sano else 503,
            root_tag="service_health",
        )

    # Alias detrás del gateway (Caddy enruta /api/v1/<servicio>*): svc-auth → /api/v1/auth/health.
    prefijo = nombre.split("-", 1)[1] if nombre.startswith("svc-") else nombre
    app.add_url_rule(f"/api/v1/{prefijo}/health", "health_gateway", health, methods=["GET"])

    @app.get("/api/v1/contracts/<nombre_xsd>.xsd")
    def contrato_xsd(nombre_xsd: str):
        """Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request)."""
        if not (DIR_XSD / f"{nombre_xsd}.xsd").is_file():
            return error_response(404, "no_encontrado", f"No existe el contrato '{nombre_xsd}.xsd'.")
        return send_from_directory(DIR_XSD, f"{nombre_xsd}.xsd", mimetype="application/xml")

    registrar_openapi(app, titulo=titulo, descripcion=descripcion, version=version_desplegada)
    return app


def ejecutar(app: Flask, variable_puerto: str, puerto_defecto: int) -> None:
    puerto = int(os.getenv(variable_puerto, str(puerto_defecto)))
    app.run(host="0.0.0.0", port=puerto, debug=False)
