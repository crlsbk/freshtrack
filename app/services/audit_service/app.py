"""
Microservicio 8: Immutable Audit & Compliance Service (`svc-audit`) — FreshTrack (Flask).

Puerto: 5008
Responsabilidad:
- Bitácora inmutable de eventos operacionales en PostgreSQL ('auditoria.bitacora_eventos').
- Consumo asíncrono de eventos desde Redis Streams ('freshtrack:events').
- Reconstrucción de trazabilidad integral por lote perecedero (Recepción -> Existencia -> FEFO -> Merma/Venta).
- Soporte dual JSON y XML (formatos regulatorios sanitarios y fiscales).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import Flask, request

from app import auditoria
from app.config import Config
from app.db import a_int, one, query
from app.events.dispatcher import asegurar_consumer_group, leer_ultimos_eventos
from app.services import cache_service
from app.services.common.auth import requiere_auth
from app.services.common.response import render_response
from app.services.common.swagger import registrar_openapi

app = Flask(__name__)
app.config.from_object(Config)

STREAM_AUDIT_GROUP = "audit_workers"


@app.get("/health")
def health():
    pg_ok = False
    try:
        res = one("SELECT 1 AS ok")
        pg_ok = bool(res and res["ok"] == 1)
    except Exception:
        pass

    redis_ok = False
    try:
        r = cache_service.get_redis_client()
        redis_ok = bool(r and r.ping())
    except Exception:
        pass

    estado = "HEALTHY" if (pg_ok and redis_ok) else "DEGRADED"
    return render_response({
        "service": "svc-audit",
        "status": estado,
        "dependencies": {"postgres": pg_ok, "redis": redis_ok},
    }, status=200 if estado == "HEALTHY" else 503, root_tag="service_health")


@app.get("/api/v1/audit/events")
@requiere_auth("admin", "auditor")
def listar_eventos():
    """Consulta de bitácora inmutable con soporte de exportación JSON y XML."""
    tabla = request.args.get("tabla")
    accion = request.args.get("accion")
    limite = a_int(request.args.get("limite"), 50)

    condiciones = []
    params = {"lim": limite}
    if tabla:
        condiciones.append("nombre_tabla = :tab")
        params["tab"] = tabla
    if accion:
        condiciones.append("accion = :acc")
        params["acc"] = accion

    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    sql = f"""
        SELECT id_evento::text AS id_evento, fecha_evento, accion, nombre_tabla,
               id_registro, descripcion, usuario_email, ip
        FROM auditoria.bitacora_eventos
        {where}
        ORDER BY fecha_evento DESC
        LIMIT :lim
    """
    filas = query(sql, **params)
    items = [dict(f) for f in filas]
    return render_response({"total": len(items), "bitacora": items}, status=200, root_tag="bitacora_auditoria")


@app.get("/api/v1/audit/traceability/<id_lote>")
@requiere_auth("admin", "auditor", "warehouse")
def trazabilidad_lote(id_lote: str):
    """Reconstrucción del ciclo de vida y trazabilidad completa de un lote en JSON / XML."""
    lote = one(
        """
        SELECT l.id_lote::text AS id_lote, l.codigo_lote_prov, l.fecha_recepcion,
               l.fecha_caducidad, p.id_sku, p.nombre AS producto, pr.razon_social AS proveedor
        FROM operacion.lote l
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        JOIN operacion.proveedor pr ON pr.id_proveedor = l.id_proveedor
        WHERE l.id_lote = CAST(:id AS uuid)
        """,
        id=id_lote,
    )
    if not lote:
        return render_response({"error": "not_found", "mensaje": f"Lote {id_lote} no encontrado."}, status=404, root_tag="trazabilidad")

    movimientos = query(
        """
        SELECT id_movimiento, tipo, cantidad, cantidad_resultante, fecha, referencia_tipo
        FROM operacion.movimiento_inventario
        WHERE id_lote = CAST(:id AS uuid)
        ORDER BY fecha ASC
        """,
        id=id_lote,
    )
    movs = [dict(m) for m in movimientos]

    return render_response({
        "lote": dict(lote),
        "movimientos_kardex": movs,
        "total_movimientos": len(movs),
    }, status=200, root_tag="trazabilidad_lote")


@app.post("/api/v1/audit/log")
@requiere_auth()
def registrar_log_explicit():
    """Registro explícito de acción de seguridad o cumplimiento en la bitácora."""
    datos = request.get_json(silent=True) or request.form
    accion = datos.get("accion", "AUDIT_CHECK")
    descripcion = datos.get("descripcion", "Verificación de cumplimiento")
    tabla = datos.get("tabla", "sistema")

    evento_id = auditoria.registrar(
        accion=accion,
        tabla=tabla,
        descripcion=descripcion,
        id_usuario=request.headers.get("X-User-Id"),
        usuario_email=request.headers.get("X-User-Email"),
        ip=request.remote_addr,
    )
    return render_response({"id_evento": evento_id, "status": "REGISTRADO"}, status=201, root_tag="log_creado")


@app.get("/api/v1/audit/stream/recent")
@requiere_auth("admin", "auditor")
def ver_stream_eventos():
    """Consulta los eventos en tránsito en Redis Streams."""
    eventos = leer_ultimos_eventos(cantidad=a_int(request.args.get("n"), 25))
    return render_response({"total": len(eventos), "stream_eventos": eventos}, status=200, root_tag="redis_stream")


registrar_openapi(
    app,
    titulo="Immutable Audit & Compliance Service (FreshTrack)",
    descripcion="Microservicio para bitácora inmutable de eventos, trazabilidad sanitaria de lotes y monitoreo de Redis Streams.",
    version="1.0.0",
    paths={
        "/health": {"get": {"summary": "Healthcheck del microservicio", "responses": {"200": {"description": "Estado saludable"}}}},
        "/api/v1/audit/events": {"get": {"summary": "Consulta de bitácora inmutable (JSON / XML)", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Lista de eventos de auditoría"}}}},
        "/api/v1/audit/traceability/{id_lote}": {"get": {"summary": "Trazabilidad de ciclo de vida del lote (JSON / XML)", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Trazabilidad completa"}}}},
        "/api/v1/audit/log": {"post": {"summary": "Registro explícito de evento", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Evento persistido"}}}},
        "/api/v1/audit/stream/recent": {"get": {"summary": "Eventos recientes en Redis Streams", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Stream de eventos"}}}},
    },
)

if __name__ == "__main__":
    port = int(os.getenv("AUDIT_SERVICE_PORT", "5008"))
    app.run(host="0.0.0.0", port=port, debug=False)
