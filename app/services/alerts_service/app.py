"""
Microservicio 7: Pre-Shrinkage Alerts & ESG (`svc-alerts`) — FreshTrack (Flask).

Puerto: 5007
Responsabilidad:
- Escaneo de lotes próximos a caducar en PostgreSQL y emisión de alertas documentales en MongoDB
  (colección alertas_operativas, índice TTL de retención).
- Atención de alertas y consultas filtradas / agregadas (pipelines) por locación y criticidad.
- Reporte ESG de alimento rescatado y CO2e evitado.
- Eventos ALERTA_EMITIDA / ALERTA_ATENDIDA en Redis Streams.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import g, request

from app.db import a_float, one, query
from app.domain import kpis as motor_kpis
from app.events.dispatcher import publicar_evento
from app.services import cache_service, doc_store
from app.services.common.auth import requiere_auth
from app.services.common.response import ErrorApi, entero, error_response, render_response
from app.services.common.servicio import crear_servicio, ejecutar
from app.services.common.swagger import documentar

app = crear_servicio(
    "svc-alerts",
    "Pre-Shrinkage Alerts & ESG Service (FreshTrack)",
    "Alertas de riesgo de merma en MongoDB a partir de lotes en PostgreSQL, y métricas de sostenibilidad.",
    dependencias=("postgres", "mongo", "redis", "bucket"),
)

CRITICIDADES = {"INFO", "WARNING", "CRITICAL"}


def _mongo() -> None:
    if doc_store.get_mongo_db() is None:
        raise ErrorApi(503, "mongo_no_disponible", "MongoDB no está disponible en este momento.")


@app.post("/api/v1/alerts/scan")
@documentar(
    "Escanea lotes por vencer y emite alertas",
    consulta=[("id_locacion", "integer", "Limita el escaneo a una tienda"), ("dias", "integer", "Ventana de días (defecto 3, máx. 30)")],
    raiz_respuesta="alertas_scan_resultado",
    exito="200",
)
@requiere_auth("store_manager", "warehouse")
def escanear_alertas():
    """
    Busca existencias que vencen en ≤ N días. Usa un bloqueo distribuido en Redis para que
    dos escaneos simultáneos no dupliquen alertas.
    """
    _mongo()
    id_locacion = g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1)
    dias = min(entero(request.args, "dias", minimo=0, defecto=3), 30)

    with cache_service.bloqueo_distribuido(f"alerts:scan:{id_locacion or 'all'}", timeout_segundos=30) as token:
        if token is None and cache_service.get_redis_client() is not None:
            return error_response(409, "escaneo_en_curso", "Ya hay un escaneo en curso para esta locación.")
        filtro_loc = "AND e.id_locacion = :loc" if id_locacion else ""
        params = {"dias": dias, **({"loc": id_locacion} if id_locacion else {})}
        lotes = query(
            f"""
            SELECT l.id_lote::text AS id_lote, l.id_sku, p.nombre AS producto, e.id_locacion,
                   loc.nombre AS locacion, (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
                   e.cantidad_disponible
            FROM operacion.existencia e
            JOIN operacion.lote l ON l.id_lote = e.id_lote
            JOIN operacion.producto p ON p.id_sku = l.id_sku
            JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
            WHERE e.cantidad_disponible > 0
              AND (l.fecha_caducidad - CURRENT_DATE) BETWEEN 0 AND :dias
              {filtro_loc}
            ORDER BY dias_restantes ASC
            """,
            **params,
        )

        creadas = []
        for lote in lotes:
            dias_rest = lote["dias_restantes"]
            criticidad = "CRITICAL" if dias_rest <= 1 else "WARNING"
            cantidad = a_float(lote["cantidad_disponible"])
            mongo_id = doc_store.guardar_alerta_operativa(
                tipo="RIESGO_PRE_MERMA",
                criticidad=criticidad,
                mensaje=f"Lote de '{lote['producto']}' vence en {dias_rest} día(s). Stock: {cantidad:g} u.",
                id_sku=lote["id_sku"],
                id_locacion=lote["id_locacion"],
                contexto={"dias_restantes": dias_rest, "producto": lote["producto"], "id_lote": lote["id_lote"], "cantidad": cantidad},
            )
            publicar_evento(
                "ALERTA_EMITIDA",
                {"mongo_id": mongo_id, "criticidad": criticidad, "id_sku": lote["id_sku"], "dias_restantes": dias_rest},
                contexto={"location_id": lote["id_locacion"]},
            )
            creadas.append({"id_mongo": mongo_id, "id_lote": lote["id_lote"], "criticidad": criticidad})

    cache_service.incrementar_contador("alerts", "scan_executed")
    return render_response(
        {"status": "COMPLETADO", "ventana_dias": dias, "total_escaneados": len(lotes), "alertas_emitidas": len(creadas), "detalle": creadas},
        status=200,
        root_tag="alertas_scan_resultado",
    )


@app.get("/api/v1/alerts/active")
@documentar(
    "Alertas abiertas (MongoDB)",
    consulta=[("id_locacion", "integer", "Tienda"), ("criticidad", "string", "INFO/WARNING/CRITICAL"), ("limite", "integer", "Máximo (defecto 50, máx. 200)")],
    raiz_respuesta="alertas_activas",
)
@requiere_auth()
def listar_alertas_activas():
    """Consulta alertas no atendidas filtrando por locación y criticidad."""
    _mongo()
    criticidad = (request.args.get("criticidad") or "").upper() or None
    if criticidad and criticidad not in CRITICIDADES:
        raise ErrorApi(400, "parametro_invalido", f"Criticidad inválida. Valores: {sorted(CRITICIDADES)}")
    alertas = doc_store.listar_alertas_operativas(
        id_locacion=g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1),
        atendida=False,
        criticidad=criticidad,
        limite=min(entero(request.args, "limite", minimo=1, defecto=50), 200),
    )
    return render_response({"total": len(alertas), "alertas": alertas}, status=200, root_tag="alertas_activas")


@app.patch("/api/v1/alerts/<id_mongo>/resolve")
@documentar("Marca una alerta como atendida", respuesta={"id_mongo": "6716…", "status": "ATENDIDA"}, raiz_respuesta="alerta_resuelta")
@requiere_auth("store_manager", "warehouse")
def atender_alerta(id_mongo: str):
    """$set atendida=true y atendida_en; a partir de ahí corre su retención TTL."""
    _mongo()
    if len(id_mongo) != 24 or any(c not in "0123456789abcdef" for c in id_mongo.lower()):
        raise ErrorApi(400, "parametro_invalido", "'id_mongo' debe ser un ObjectId de 24 caracteres hexadecimales.")
    if not doc_store.marcar_alerta_atendida(id_mongo):
        return error_response(404, "no_encontrado", "Alerta no encontrada o ya atendida.")
    publicar_evento("ALERTA_ATENDIDA", {"id_mongo": id_mongo}, contexto={"user_id": g.usuario_actual.get("sub")})
    return render_response({"id_mongo": id_mongo, "status": "ATENDIDA"}, status=200, root_tag="alerta_resuelta")


@app.get("/api/v1/alerts/esg/carbon-avoided")
@documentar("Reporte ESG: alimento rescatado, desperdicio evitado neto y CO2e evitado", raiz_respuesta="reporte_esg_sostenibilidad")
@requiere_auth()
def calcular_esg():
    """Suma recuperado bruto, estimado neto contrafactual y CO2e evitado (cacheado 5 min en Redis)."""
    clave = "alerts:esg:resumen"
    cache = cache_service.get_json(clave)
    if cache:
        return render_response({**cache, "fuente": "redis_cache"}, status=200, root_tag="reporte_esg_sostenibilidad")
    comp = motor_kpis.indicadores_desperdicio_completo(30)
    cuerpo = {
        "alimento_recuperado_kg": comp["producto_recuperado"]["unidades"],
        "desperdicio_evitado_neto_kg": comp["desperdicio_evitado_estimado"]["unidades"],
        "contrafactual_organico_kg": comp["desperdicio_evitado_estimado"]["contrafactual_organico"],
        "ahorro_financiero_mxn": comp["producto_recuperado"]["valor"],
        "co2e_evitado_kg": comp["co2e_evitado_estimado"]["kg_co2e"],
        "co2e_evitado_toneladas": comp["co2e_evitado_estimado"]["toneladas_co2e"],
        "factor_conversion": comp["co2e_evitado_estimado"]["factor"],
        "indicadores_6": comp,
    }
    cache_service.set_json(clave, cuerpo, ttl_segundos=300)
    return render_response({**cuerpo, "fuente": "postgres"}, status=200, root_tag="reporte_esg_sostenibilidad")


@app.get("/api/v1/alerts/waste-measurement")
@documentar(
    "Medición causal y contrafactual del desperdicio (6 indicadores)",
    consulta=[("dias", "integer", "Ventana para reducción observada de merma (defecto 30)")],
    raiz_respuesta="medicion_desperdicio",
)
@requiere_auth()
def medicion_desperdicio():
    """Distingue riesgo, proyección, recuperación bruta, neto contrafactual, merma observada y CO2e."""
    dias = min(entero(request.args, "dias", minimo=7, defecto=30) or 30, 365)
    comp = motor_kpis.indicadores_desperdicio_completo(dias)
    return render_response(comp, status=200, root_tag="medicion_desperdicio")


@app.get("/api/v1/alerts/analytics/kpis")
@documentar("Alertas por locación y criticidad (pipeline de agregación)", raiz_respuesta="kpis_alertas")
@requiere_auth()
def analitica_kpis_alertas():
    """Pipeline $match + $group + $project sobre alertas_operativas."""
    _mongo()
    kpis = doc_store.analitica_alertas_por_locacion()
    return render_response({"total_grupos": len(kpis), "kpis_alertas": kpis}, status=200, root_tag="kpis_alertas")


if __name__ == "__main__":
    ejecutar(app, "ALERTS_SERVICE_PORT", 5007)
