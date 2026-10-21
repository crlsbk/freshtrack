"""
Microservicio 7: Context-Aware Alerts & ESG Sustainability Service (`svc-alerts`) — FreshTrack (Flask).

Puerto: 5007
Responsabilidad:
- Detección proactiva de riesgos pre-merma mediante semáforo de vida útil restante.
- Persistencia de alertas operativas con política TTL (180 días) en MongoDB ('alertas_operativas').
- Sugerencia de descuentos dinámicos escalonados para remate antes de caducidad.
- Cuantificación de impacto ambiental ESG: emisiones evitadas de CO2e y mermas prevenidas.
- Soporte dual JSON y XML.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import Flask, g, request

from app.config import Config
from app.db import a_float, a_int, one, query
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
        "service": "svc-alerts",
        "status": estado,
        "dependencies": {"postgres": pg_ok, "redis": redis_ok, "mongo": mongo_ok},
    }, status=200 if estado == "HEALTHY" else 503, root_tag="service_health")


@app.post("/api/v1/alerts/scan")
@requiere_auth("admin", "store_manager", "warehouse")
def escanear_alertas():
    """Escanea lotes en PostgreSQL y emite alertas documentales en MongoDB y eventos en Redis Streams."""
    ctx = g.contexto
    id_locacion = a_int(ctx.get("location_id") or request.args.get("id_locacion"), 0) or None

    filtro_loc = "AND e.id_locacion = :loc" if id_locacion else ""
    sql = f"""
        SELECT l.id_lote::text AS id_lote,
               l.id_sku,
               p.nombre AS producto,
               e.id_locacion,
               loc.nombre AS locacion,
               (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
               e.cantidad_disponible
        FROM operacion.existencia e
        JOIN operacion.lote l ON l.id_lote = e.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
        WHERE e.cantidad_disponible > 0
          AND (l.fecha_caducidad - CURRENT_DATE) BETWEEN 0 AND 3
          {filtro_loc}
        ORDER BY dias_restantes ASC
    """
    params = {"loc": id_locacion} if id_locacion else {}
    lotes_criticos = query(sql, **params)

    alertas_creadas = []
    for lote in lotes_criticos:
        dias = lote["dias_restantes"]
        criticidad = "CRITICAL" if dias <= 1 else "WARNING"
        mensaje = f"Lote crítico de '{lote['producto']}' vence en {dias} día(s). Stock: {lote['cantidad_disponible']} u."

        mongo_id = doc_store.guardar_alerta_operativa(
            tipo="RIESGO_PRE_MERMA",
            criticidad=criticidad,
            mensaje=mensaje,
            id_sku=lote["id_sku"],
            id_locacion=lote["id_locacion"],
            contexto={"dias_restantes": dias, "producto": lote["producto"], "id_lote": lote["id_lote"]},
        )

        publicar_evento(
            "ALERTA_EMITIDA",
            {
                "mongo_id": mongo_id,
                "tipo": "RIESGO_PRE_MERMA",
                "criticidad": criticidad,
                "id_sku": lote["id_sku"],
                "producto": lote["producto"],
                "dias_restantes": dias,
            },
            contexto={"location_id": lote["id_locacion"]},
        )
        alertas_creadas.append({"id_mongo": mongo_id, "lote": lote["id_lote"], "criticidad": criticidad})

    return render_response({
        "status": "COMPLETADO",
        "total_escaneados": len(lotes_criticos),
        "alertas_emitidas": len(alertas_creadas),
        "detalle": alertas_creadas,
    }, status=200, root_tag="alertas_scan_resultado")


@app.get("/api/v1/alerts/active")
@requiere_auth()
def listar_alertas_activas():
    """Consulta alertas abiertas en MongoDB con soporte JSON y XML."""
    ctx = g.contexto
    id_locacion = a_int(ctx.get("location_id") or request.args.get("id_locacion"), 0) or None
    criticidad = request.args.get("criticidad")
    limite = a_int(request.args.get("limite"), 50)

    alertas = doc_store.listar_alertas_operativas(
        id_locacion=id_locacion,
        atendida=False,
        criticidad=criticidad,
        limite=limite,
    )
    return render_response({"total": len(alertas), "alertas": alertas}, status=200, root_tag="alertas_activas")


@app.patch("/api/v1/alerts/<id_mongo>/resolve")
@requiere_auth("admin", "store_manager", "warehouse")
def atender_alerta(id_mongo: str):
    """Marca una alerta como atendida en MongoDB (iniciando su ciclo de expiración TTL)."""
    ok = doc_store.marcar_alerta_atendida(id_mongo)
    if not ok:
        return render_response({"error": "not_found", "mensaje": "Alerta no encontrada en MongoDB."}, status=404, root_tag="alerta_resuelta")

    publicar_evento("ALERTA_ATENDIDA", {"id_mongo": id_mongo}, contexto={"user_id": g.usuario_actual.get("sub")})
    return render_response({"id_mongo": id_mongo, "status": "ATENDIDA"}, status=200, root_tag="alerta_resuelta")


@app.get("/api/v1/alerts/esg/carbon-avoided")
@requiere_auth()
def calcular_esg():
    """Reporte ESG de alimentos rescatados y CO2e evitado con soporte JSON y XML."""
    fila = one(
        """
        SELECT COALESCE(SUM(cantidad_recuperada), 0) AS total_kg_evitados,
               COALESCE(SUM(valor_recuperado), 0)     AS total_mxn_recuperado
        FROM analitica.desperdicio_evitado
        """
    )
    kg = a_float(fila.get("total_kg_evitados", 0.0))
    mxn = a_float(fila.get("total_mxn_recuperado", 0.0))
    co2e_kg = round(kg * 2.5, 2)

    return render_response({
        "alimento_recuperado_kg": round(kg, 2),
        "ahorro_financiero_mxn": round(mxn, 2),
        "co2e_evitado_kg": co2e_kg,
        "co2e_evitado_toneladas": round(co2e_kg / 1000.0, 3),
        "factor_conversion": "2.5 kg CO2e / kg perecedero",
    }, status=200, root_tag="reporte_esg_sostenibilidad")


@app.get("/api/v1/alerts/analytics/kpis")
@requiere_auth()
def analitica_kpis_alertas():
    """Ejecuta pipeline de agregación en MongoDB ($match + $group + $project) agrupando alertas por locación y criticidad."""
    kpis = doc_store.analitica_alertas_por_locacion()
    return render_response({"total_grupos": len(kpis), "kpis_alertas": kpis}, status=200, root_tag="kpis_alertas")


registrar_openapi(
    app,
    titulo="Context-Aware Alerts & ESG Sustainability Service (FreshTrack)",
    descripcion="Microservicio para alertas operativas pre-merma con TTL en MongoDB y cálculo de CO2e evitado.",
    version="1.0.0",
    paths={
        "/health": {"get": {"summary": "Healthcheck del microservicio", "responses": {"200": {"description": "Estado saludable"}}}},
        "/api/v1/alerts/scan": {"post": {"summary": "Escaneo pre-merma de lotes", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Escaneo finalizado"}}}},
        "/api/v1/alerts/active": {"get": {"summary": "Alertas abiertas en MongoDB (JSON / XML)", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Lista de alertas"}}}},
        "/api/v1/alerts/{id_mongo}/resolve": {"patch": {"summary": "Atender alerta", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Alerta atendida"}}}},
        "/api/v1/alerts/esg/carbon-avoided": {"get": {"summary": "Reporte de CO2e evitado (JSON / XML)", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Métricas ESG"}}}},
    },
)

if __name__ == "__main__":
    port = int(os.getenv("ALERTS_SERVICE_PORT", "5007"))
    app.run(host="0.0.0.0", port=port, debug=False)
