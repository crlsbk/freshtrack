"""
Microservicio 6: Demand Planning & Replenishment (`svc-planning`) — FreshTrack (Flask).

Puerto: 5006
Responsabilidad:
- Corridas de pronóstico de demanda (media móvil, ponderada, suavización exponencial)
  con linaje en PostgreSQL (analitica.forecast_run) y serie detallada en MongoDB.
- Generación de órdenes de reabastecimiento y su aprobación/rechazo humano (RACI).
- Contexto híbrido por SKU: datos maestros (PostgreSQL) + pronóstico y alertas (MongoDB).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import g, request

from app.db import a_float, one, query
from app.domain import pronostico as motor_pron
from app.domain import reabastecimiento as dom_reab
from app.events.dispatcher import publicar_evento
from app.services import cache_service, doc_store
from app.services.common.auth import requiere_auth, usuario_desde_token
from app.services.common.response import (
    ErrorApi,
    decimal_pos,
    entero,
    error_response,
    leer_cuerpo,
    meta_paginacion,
    paginacion,
    render_response,
    validar_uuid,
)
from app.services.common.servicio import crear_servicio, ejecutar
from app.services.common.swagger import documentar

app = crear_servicio(
    "svc-planning",
    "Demand Planning & Replenishment Service (FreshTrack)",
    "Pronóstico de demanda con linaje (PostgreSQL + MongoDB) y órdenes de reabastecimiento con aprobación humana.",
    dependencias=("postgres", "mongo", "redis"),
)

ESTADOS_ORDEN = {"PENDIENTE", "APROBADA", "RECHAZADA", "EJECUTADA", "CANCELADA"}


@app.post("/api/v1/planning/forecast/run")
@documentar(
    "Ejecuta una corrida de pronóstico",
    cuerpo={"metodo": "SUAVIZACION_EXPONENCIAL", "horizonte": 7, "ventana": 28, "alpha": 0.3, "dias_historia": 120, "id_locacion": 2},
    raiz_xml="forecast_request",
    contrato_xsd="forecast_request",
    raiz_respuesta="forecast_run_result",
    errores=("400",),
)
@requiere_auth("planner", "buyer")
def ejecutar_pronostico():
    """Calcula el pronóstico por SKU y tienda; guarda la corrida en PostgreSQL y la serie en MongoDB."""
    datos = leer_cuerpo("forecast_request")
    metodo = str(datos.get("metodo") or "SUAVIZACION_EXPONENCIAL").upper()
    if metodo not in motor_pron.METODOS:
        raise ErrorApi(400, "parametro_invalido", f"Método no soportado. Valores: {sorted(motor_pron.METODOS)}")
    alpha = decimal_pos(datos, "alpha", defecto=0.30)
    if not 0 < alpha <= 1:
        raise ErrorApi(400, "parametro_invalido", "'alpha' debe estar en (0, 1].")
    try:
        resultado = motor_pron.ejecutar_pronostico(
            usuario=usuario_desde_token(),
            metodo=metodo,
            horizonte=entero(datos, "horizonte", minimo=1, defecto=7),
            ventana=entero(datos, "ventana", minimo=2, defecto=28),
            alpha=alpha,
            dias_historia=entero(datos, "dias_historia", minimo=14, defecto=120),
            id_locacion=g.contexto.get("location_id") or entero(datos, "id_locacion", minimo=1),
            id_sku=entero(datos, "id_sku", minimo=1),
        )
    except ValueError as err:
        return error_response(400, "regla_negocio", str(err))
    cache_service.incrementar_contador("planning", "forecast_run")
    return render_response(resultado, status=201, root_tag="forecast_run_result")


@app.get("/api/v1/planning/forecast/latest/<int:sku_id>/<int:locacion_id>")
@documentar("Última serie pronosticada (MongoDB) para un SKU y tienda", raiz_respuesta="forecast_latest")
@requiere_auth()
def obtener_ultimo_pronostico(sku_id: int, locacion_id: int):
    """Recupera de MongoDB el documento más reciente, enlazado por id_sku e id_locacion de PostgreSQL."""
    if doc_store.get_mongo_db() is None:
        return error_response(503, "mongo_no_disponible", "MongoDB no está disponible.")
    doc = doc_store.obtener_ultimo_pronostico(sku_id, locacion_id)
    if not doc:
        return error_response(404, "no_encontrado", "Sin corrida previa para este SKU y tienda.")
    return render_response(doc, status=200, root_tag="forecast_latest")


@app.post("/api/v1/planning/replenishment/generate")
@documentar(
    "Genera órdenes de reabastecimiento sugeridas",
    cuerpo={"horizonte": 7},
    raiz_xml="replenishment_request",
    raiz_respuesta="replenishment_generated",
    errores=("400",),
)
@requiere_auth("planner", "buyer")
def generar_ordenes():
    """Analiza inventario útil, riesgo de caducidad y demanda proyectada; crea órdenes PENDIENTE."""
    datos = leer_cuerpo()
    try:
        res = dom_reab.generar_recomendaciones(usuario=usuario_desde_token(), horizonte=entero(datos, "horizonte", minimo=1))
    except ValueError as err:
        return error_response(400, "regla_negocio", str(err))
    publicar_evento("ORDENES_REABASTECIMIENTO_GENERADAS", {k: v for k, v in res.items() if not isinstance(v, list)})
    return render_response(res, status=201, root_tag="replenishment_generated")


@app.get("/api/v1/planning/replenishment/orders")
@documentar(
    "Órdenes de reabastecimiento (filtros y paginación)",
    consulta=[("estado", "string", "PENDIENTE/APROBADA/RECHAZADA/EJECUTADA/CANCELADA"), ("id_locacion", "integer", "Tienda"),
              ("id_sku", "integer", "Producto"), ("pagina", "integer", "Página"), ("por_pagina", "integer", "Tamaño")],
    raiz_respuesta="replenishment_orders",
)
@requiere_auth("planner", "buyer", "store_manager")
def listar_ordenes():
    """Consulta de órdenes calculadas con explicación y prioridad."""
    pagina, por_pagina, offset = paginacion()
    condiciones, params = [], {"lim": por_pagina, "off": offset}
    estado = (request.args.get("estado") or "").upper()
    if estado:
        if estado not in ESTADOS_ORDEN:
            raise ErrorApi(400, "parametro_invalido", f"Estado inválido. Valores: {sorted(ESTADOS_ORDEN)}")
        condiciones.append("o.estado = :estado")
        params["estado"] = estado
    id_locacion = g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1)
    if id_locacion:
        condiciones.append("o.id_locacion = :loc")
        params["loc"] = id_locacion
    id_sku = entero(request.args, "id_sku", minimo=1)
    if id_sku:
        condiciones.append("o.id_sku = :sku")
        params["sku"] = id_sku
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = query(
        f"""
        SELECT o.id_orden::text AS id_orden, o.id_sku, p.nombre AS producto, o.id_locacion,
               loc.nombre AS locacion, o.id_proveedor, o.cantidad_sugerida, o.cantidad_aprobada,
               o.prioridad, o.estado, o.explicacion, o.fecha_creacion, o.fecha_decision,
               COUNT(*) OVER () AS _total
        FROM analitica.orden_reabastecimiento o
        JOIN operacion.producto p ON p.id_sku = o.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = o.id_locacion
        {where}
        ORDER BY o.fecha_creacion DESC
        LIMIT :lim OFFSET :off
        """,
        **params,
    )
    total = filas[0]["_total"] if filas else 0
    for d in filas:
        d.pop("_total", None)
        d["cantidad_sugerida"] = a_float(d["cantidad_sugerida"])
        d["cantidad_aprobada"] = a_float(d["cantidad_aprobada"]) if d["cantidad_aprobada"] is not None else None
    return render_response(
        {"paginacion": meta_paginacion(pagina, por_pagina, total), "ordenes": filas},
        status=200,
        root_tag="replenishment_orders",
    )


def _decidir(id_orden: str, aprobar: bool):
    id_orden = validar_uuid(id_orden, "id_orden")
    datos = leer_cuerpo()
    cantidad = decimal_pos(datos, "cantidad") if aprobar else None
    if not one("SELECT 1 AS x FROM analitica.orden_reabastecimiento WHERE id_orden = CAST(:id AS uuid)", id=id_orden):
        return error_response(404, "no_encontrado", f"Orden {id_orden} no encontrada.")
    try:
        res = dom_reab.decidir_orden(id_orden, aprobar=aprobar, usuario=usuario_desde_token(), cantidad=cantidad)
    except ValueError as err:
        return error_response(409, "regla_negocio", str(err))
    publicar_evento("ORDEN_REABASTECIMIENTO_" + ("APROBADA" if aprobar else "RECHAZADA"), res)
    return render_response(res, status=200, root_tag="orden_decision")


@app.post("/api/v1/planning/replenishment/orders/<id_orden>/approve")
@documentar(
    "Aprueba una orden PENDIENTE (cantidad opcional)",
    cuerpo={"cantidad": 48},
    raiz_xml="aprobacion_request",
    respuesta={"id_orden": "…", "estado": "APROBADA", "cantidad": 48.0},
    raiz_respuesta="orden_decision",
    errores=("400", "409"),
    exito="200",
)
@requiere_auth("buyer", "store_manager", "planner")
def aprobar_orden(id_orden: str):
    """Aprobación humana: solo órdenes PENDIENTE; registra quién y cuándo decidió."""
    return _decidir(id_orden, aprobar=True)


@app.post("/api/v1/planning/replenishment/orders/<id_orden>/reject")
@documentar("Rechaza una orden PENDIENTE", raiz_respuesta="orden_decision", errores=("409",), exito="200")
@requiere_auth("buyer", "store_manager", "planner")
def rechazar_orden(id_orden: str):
    """Rechazo humano de la orden sugerida."""
    return _decidir(id_orden, aprobar=False)


@app.get("/api/v1/planning/forecast/analytics/kpis")
@documentar("Métricas de precisión por modelo (pipeline de agregación)", raiz_respuesta="kpis_pronosticos")
@requiere_auth()
def analitica_kpis_pronosticos():
    """Pipeline $group + $project + $sort sobre pronosticos_demanda en MongoDB."""
    if doc_store.get_mongo_db() is None:
        return error_response(503, "mongo_no_disponible", "MongoDB no está disponible.")
    kpis = doc_store.analitica_kpis_pronosticos()
    return render_response({"total_modelos": len(kpis), "kpis_modelos": kpis}, status=200, root_tag="kpis_pronosticos")


@app.get("/api/v1/planning/sku/<int:sku_id>/full-context")
@documentar("Contexto híbrido PostgreSQL + MongoDB de un SKU", consulta=[("id_locacion", "integer", "Tienda (por omisión 1)")], raiz_respuesta="sku_full_context")
@requiere_auth()
def contexto_completo_sku(sku_id: int):
    """Datos maestros del producto (PostgreSQL) enriquecidos con pronóstico y alertas activas (MongoDB)."""
    locacion_id = g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1, defecto=1)
    prod = one(
        """
        SELECT id_sku, codigo_gtin, nombre, categoria, vida_util_estandar, precio_venta, precio_costo, activo
        FROM operacion.producto WHERE id_sku = :sku
        """,
        sku=sku_id,
    )
    if not prod:
        return error_response(404, "no_encontrado", f"SKU {sku_id} no existe.")
    prod["precio_venta"] = a_float(prod["precio_venta"])
    prod["precio_costo"] = a_float(prod["precio_costo"])
    return render_response(
        {"producto_postgres": prod, "contexto_mongo": doc_store.obtener_contexto_documental_sku(sku_id, locacion_id)},
        status=200,
        root_tag="sku_full_context",
    )


if __name__ == "__main__":
    ejecutar(app, "PLANNING_SERVICE_PORT", 5006)
