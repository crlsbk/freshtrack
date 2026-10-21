"""
Microservicio 6: Planning, Forecasting & Replenishment Service (`svc-planning`) — FreshTrack (Flask).

Puerto: 5006
Responsabilidad:
- Ejecución de modelos de pronóstico de demanda (Media Móvil, MM Ponderada, Suavización Exponencial).
- Almacenamiento de proyecciones con percentiles en MongoDB ('pronosticos_demanda').
- Cálculo de sugerencias de reabastecimiento respetando Lead Time y MOQ del proveedor.
- Validación de transferencias inter-tienda en 4 pasos.
- Soporte dual JSON y XML.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import Flask, g, request
from sqlalchemy import text

from app.config import Config
from app.db import a_float, a_int, one, query, transaccion
from app.domain import pronostico as motor_pron
from app.domain import reabastecimiento as dom_reab
from app.events.dispatcher import publicar_evento
from app.services import cache_service, doc_store
from app.services.common.auth import requiere_auth
from app.services.common.response import render_response
from app.services.common.swagger import registrar_openapi

app = Flask(__name__)
app.config.from_object(Config)


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

    mongo_ok = False
    try:
        db = doc_store.get_mongo_db()
        mongo_ok = bool(db is not None)
    except Exception:
        pass

    estado = "HEALTHY" if (pg_ok and redis_ok and mongo_ok) else "DEGRADED"
    return render_response({
        "service": "svc-planning",
        "status": estado,
        "dependencies": {"postgres": pg_ok, "redis": redis_ok, "mongo": mongo_ok},
    }, status=200 if estado == "HEALTHY" else 503, root_tag="service_health")


@app.post("/api/v1/planning/forecast/run")
@requiere_auth("admin", "planner", "buyer")
def ejecutar_pronostico():
    """Ejecuta una corrida de pronóstico con linaje inmutable en PostgreSQL y MongoDB."""
    datos = request.get_json(silent=True) or request.form
    ctx = g.contexto

    usuario = {
        "id_usuario": ctx.get("user_id") or str(g.usuario_actual.get("sub")),
        "email": ctx.get("user_email") or g.usuario_actual.get("email"),
        "rol_clave": ctx.get("user_role") or g.usuario_actual.get("rol"),
    }

    try:
        resultado = motor_pron.ejecutar_pronostico(
            usuario=usuario,
            metodo=datos.get("metodo", "SUAVIZACION_EXPONENCIAL"),
            horizonte=a_int(datos.get("horizonte"), 7),
            ventana=a_int(datos.get("ventana"), 28),
            alpha=float(datos.get("alpha", 0.30) or 0.30),
            dias_historia=a_int(datos.get("dias_historia"), 120),
            id_locacion=a_int(ctx.get("location_id") or datos.get("id_locacion"), 0) or None,
        )
        return render_response(resultado, status=201, root_tag="forecast_run_result")
    except Exception as exc:
        return render_response({"error": "error_pronostico", "detalle": str(exc)}, status=400, root_tag="error_planning")


@app.get("/api/v1/planning/forecast/latest/<int:sku_id>/<int:locacion_id>")
@requiere_auth()
def obtener_ultimo_pronostico(sku_id: int, locacion_id: int):
    """Consulta la última serie de tiempo proyectada en MongoDB con soporte JSON y XML."""
    doc = doc_store.obtener_ultimo_pronostico(sku_id, locacion_id)
    if not doc:
        return render_response({"error": "not_found", "mensaje": "Sin corrida previa para este SKU y tienda en MongoDB."}, status=404, root_tag="forecast_latest")
    return render_response(doc, status=200, root_tag="forecast_latest")


@app.get("/api/v1/planning/replenishment/orders")
@requiere_auth("admin", "planner", "buyer", "store_manager")
def listar_ordenes():
    """Consulta órdenes de reabastecimiento calculadas."""
    ctx = g.contexto
    id_locacion = ctx.get("location_id") or a_int(request.args.get("id_locacion"), 0) or None
    filtro = "WHERE o.id_locacion = :loc" if id_locacion else ""
    params = {"loc": id_locacion} if id_locacion else {}

    sql = f"""
        SELECT o.id_orden::text AS id_orden, o.id_sku, p.nombre AS producto,
               o.id_locacion, o.id_proveedor, o.cantidad_sugerida, o.estado,
               o.explicacion, o.fecha_creacion
        FROM analitica.orden_reabastecimiento o
        JOIN operacion.producto p ON p.id_sku = o.id_sku
        {filtro}
        ORDER BY o.fecha_creacion DESC
        LIMIT 30
    """
    filas = query(sql, **params)
    items = []
    for f in filas:
        d = dict(f)
        d["cantidad_sugerida"] = a_float(d["cantidad_sugerida"])
        items.append(d)

    return render_response({"total": len(items), "ordenes": items}, status=200, root_tag="replenishment_orders")


@app.post("/api/v1/planning/replenishment/orders/<id_orden>/approve")
@requiere_auth("admin", "buyer")
def aprobar_orden(id_orden: str):
    """Aprobación humana de orden de compra respetando el flujo RACI."""
    with transaccion() as conn:
        conn.execute(
            text(
                """
                UPDATE analitica.orden_reabastecimiento
                SET estado = 'APROBADA', actualizado_en = now()
                WHERE id_orden = CAST(:id AS uuid)
                """
            ),
            {"id": id_orden},
        )
    publicar_evento("ORDEN_REABASTECIMIENTO_APROBADA", {"id_orden": id_orden})
    return render_response({"id_orden": id_orden, "estado": "APROBADA"}, status=200, root_tag="orden_aprobada")


@app.get("/api/v1/planning/forecast/analytics/kpis")
@requiere_auth()
def analitica_kpis_pronosticos():
    """Ejecuta pipeline de agregación en MongoDB ($group + $project + $sort) calculando métricas de modelos."""
    kpis = doc_store.analitica_kpis_pronosticos()
    return render_response({"total_modelos": len(kpis), "kpis_modelos": kpis}, status=200, root_tag="kpis_pronosticos")


@app.get("/api/v1/planning/sku/<int:sku_id>/full-context")
@requiere_auth()
def contexto_completo_sku(sku_id: int):
    """
    Recuperación híbrida: Consulta datos maestros de producto en PostgreSQL y los
    enriquece con el linaje de pronóstico y alertas operativas activas desde MongoDB.
    """
    ctx = g.contexto
    locacion_id = a_int(ctx.get("location_id") or request.args.get("id_locacion"), 1)

    # 1. PostgreSQL (fuente de verdad relacional)
    prod = one("SELECT id_sku, nombre, categoria, vida_util_dias, precio_unitario FROM operacion.producto WHERE id_sku = :sku", sku=sku_id)
    if not prod:
        return render_response({"error": "not_found", "mensaje": f"SKU {sku_id} no existe en PostgreSQL."}, status=404, root_tag="sku_context")

    # 2. MongoDB (almacén documental de contexto y analítica)
    doc_context = doc_store.obtener_contexto_documental_sku(sku_id, locacion_id)

    respuesta = {
        "producto_postgres": dict(prod),
        "contexto_mongo": doc_context,
    }
    return render_response(respuesta, status=200, root_tag="sku_full_context")


registrar_openapi(
    app,
    titulo="Planning, Forecasting & Replenishment Service (FreshTrack)",
    descripcion="Microservicio para modelos de demanda, percentiles en MongoDB y órdenes de reabastecimiento.",
    version="1.0.0",
    paths={
        "/health": {"get": {"summary": "Healthcheck del microservicio", "responses": {"200": {"description": "Estado saludable"}}}},
        "/api/v1/planning/forecast/run": {"post": {"summary": "Ejecución de pronósticos de demanda", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Pronóstico ejecutado"}}}},
        "/api/v1/planning/forecast/latest/{sku_id}/{locacion_id}": {"get": {"summary": "Última proyección en MongoDB", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Proyección obtenida"}}}},
        "/api/v1/planning/replenishment/orders": {"get": {"summary": "Órdenes de compra sugeridas", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Lista de órdenes"}}}},
        "/api/v1/planning/replenishment/orders/{id_orden}/approve": {"post": {"summary": "Aprobación de orden", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Orden aprobada"}}}},
    },
)

if __name__ == "__main__":
    port = int(os.getenv("PLANNING_SERVICE_PORT", "5006"))
    app.run(host="0.0.0.0", port=port, debug=False)
