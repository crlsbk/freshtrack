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

from flask import Response, g, request

from app.db import a_float, one, query
from app.domain import compras as dom_compras
from app.domain import descuentos as dom_desc
from app.domain import pronostico as motor_pron
from app.domain import reabastecimiento as dom_reab
from app.domain import transferencias as dom_tr
from app.domain import triaje as dom_triaje
from app.events.dispatcher import publicar_evento
from app.services import cache_service, doc_store, mailer
from app.services.common.auth import requiere_auth, usuario_desde_token, validar_alcance_locacion
from app.services.common.response import (
    ErrorApi,
    decimal_pos,
    entero,
    error_response,
    leer_cuerpo,
    meta_paginacion,
    paginacion,
    render_response,
    requerir_campos,
    validar_uuid,
)
from app.services.common.servicio import crear_servicio, ejecutar
from app.services.common.swagger import documentar

app = crear_servicio(
    "svc-planning",
    "Demand Planning & Replenishment Service (FreshTrack)",
    "Pronóstico de demanda con linaje (PostgreSQL + MongoDB) y órdenes de reabastecimiento con aprobación humana.",
    dependencias=("postgres", "mongo", "redis", "bucket"),
)

ESTADOS_ORDEN = {"PENDIENTE", "APROBADA", "RECHAZADA", "EJECUTADA", "CANCELADA"}


@app.post("/api/v1/planning/forecast/run")
@documentar(
    "Ejecuta una corrida de pronóstico por tienda (AUTO por defecto)",
    cuerpo={"metodo": "AUTO", "horizonte": 7, "id_locacion": 3},
    raiz_xml="forecast_request",
    contrato_xsd="forecast_request",
    raiz_respuesta="forecast_run_result",
    errores=("400",),
)
@requiere_auth("planner")
def ejecutar_pronostico():
    """Calcula un modelo independiente por tienda; guarda la corrida relacional y la serie detallada."""
    datos = leer_cuerpo("forecast_request")
    metodo = str(datos.get("metodo") or "AUTO").upper()
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


# =============================================================================
# Optimizador Newsvendor y Backtesting vs. Naive
# =============================================================================
@app.post("/api/v1/planning/newsvendor/evaluate")
@documentar(
    "Calcula cantidad óptima Newsvendor vs política simple (SKU + tienda)",
    cuerpo={"id_sku": 1, "id_locacion": 3, "horizonte": 7},
    raiz_xml="newsvendor_request",
    respuesta={"cantidad_newsvendor": 42.0, "cantidad_politica_simple": 38.0, "fractil_critico": 0.65, "ahorro_esperado": 120.5},
    raiz_respuesta="newsvendor_evaluation",
    errores=("400", "404"),
    exito="200",
)
@requiere_auth("planner", "buyer", "store_manager")
def evaluar_newsvendor():
    """Evalúa un par SKU + tienda aplicando el modelo Newsvendor con costos de faltante/excedente y caducidad."""
    datos = leer_cuerpo(requerido=True)
    id_sku = entero(datos, "id_sku", minimo=1)
    id_locacion = g.contexto.get("location_id") or entero(datos, "id_locacion", minimo=1)
    if not id_sku or not id_locacion:
        raise ErrorApi(400, "campos_requeridos", "'id_sku' e 'id_locacion' son obligatorios.")
    horizonte = entero(datos, "horizonte", minimo=1, defecto=7) or 7
    try:
        analisis = dom_reab.analizar_sku_locacion(id_sku, id_locacion, horizonte)
    except ValueError as err:
        return error_response(404, "no_encontrado", str(err))
    return render_response(
        {
            "id_sku": id_sku,
            "producto": analisis["producto"]["nombre"],
            "id_locacion": id_locacion,
            "locacion": analisis["locacion"]["nombre"],
            "horizonte": horizonte,
            "demanda_horizonte": analisis["demanda_horizonte"],
            "inventario_util": analisis["inventario_util"],
            "inventario_riesgo": analisis["inventario_riesgo"],
            "cantidad_sugerida": analisis["cantidad_sugerida"],
            "newsvendor": analisis["newsvendor"],
            "advertencias": analisis["advertencias"],
        },
        status=200,
        root_tag="newsvendor_evaluation",
    )


@app.get("/api/v1/planning/forecast/backtest")
@documentar(
    "Backtesting temporal cronológico comparando modelos contra Naive (MAE, WMAPE y Sesgo)",
    consulta=[("id_sku", "integer", "Producto opcional"), ("id_locacion", "integer", "Tienda opcional"), ("horizonte", "integer", "Días (defecto 7)")],
    raiz_respuesta="forecast_backtest",
)
@requiere_auth("planner", "buyer", "auditor")
def backtest_comparativo():
    """Evalúa todos los métodos frente a la línea base ingenua (Naive) midiendo sesgo y error temporal."""
    id_sku = entero(request.args, "id_sku", minimo=1)
    id_locacion = g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1)
    horizonte = entero(request.args, "horizonte", minimo=1, defecto=7) or 7
    res = motor_pron.evaluar_backtest_comparativo(
        id_sku=id_sku,
        id_locacion=id_locacion,
        horizonte=horizonte,
    )
    return render_response(res, status=200, root_tag="forecast_backtest")


@app.get("/api/v1/planning/forecast/drift")
@documentar(
    "Observabilidad de deriva de datos (data drift) y confiabilidad por tienda y producto",
    consulta=[("id_locacion", "integer", "Tienda opcional"), ("ventana_reciente", "integer", "Días recientes (defecto 14)")],
    raiz_respuesta="forecast_drift",
)
@requiere_auth("planner", "buyer", "store_manager", "auditor")
def salud_y_drift_modelos():
    """Evalúa deriva de ventas recientes, días atípicos y degradación de cada modelo por tienda."""
    id_locacion = g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1)
    ventana = entero(request.args, "ventana_reciente", minimo=7, defecto=14) or 14
    res = motor_pron.evaluar_salud_modelos(id_locacion=id_locacion, ventana_reciente=ventana)
    return render_response(res, status=200, root_tag="forecast_drift")


# =============================================================================
# Transferencias entre tiendas (REST JSON/XML)
# =============================================================================
ESTADOS_TRANSFER = {"SUGERIDA", "APROBADA", "RECHAZADA", "EJECUTADA", "CANCELADA"}
ESTADOS_DISCOUNT = {"SUGERIDO", "APROBADO", "RECHAZADO", "APLICADO"}


@app.get("/api/v1/planning/transfers")
@documentar(
    "Lista transferencias entre tiendas (filtros)",
    consulta=[("estado", "string", "SUGERIDA/APROBADA/EJECUTADA/RECHAZADA"), ("limite", "integer", "Máximo registros")],
    raiz_respuesta="transfers_list",
)
@requiere_auth("planner", "store_manager", "warehouse")
def listar_transferencias_api():
    """Lista las propuestas y ejecuciones de transferencia entre tiendas."""
    estado = (request.args.get("estado") or "").upper() or None
    if estado and estado not in ESTADOS_TRANSFER:
        raise ErrorApi(400, "parametro_invalido", f"Estado inválido. Valores: {sorted(ESTADOS_TRANSFER)}")
    limite = min(entero(request.args, "limite", minimo=1, defecto=100) or 100, 300)
    filas = dom_tr.listar_transferencias(estado=estado, limite=limite)
    for f in filas:
        f["cantidad"] = a_float(f["cantidad"])
    return render_response(
        {"total": len(filas), "resumen": dom_tr.resumen_transferencias(), "transferencias": filas},
        status=200,
        root_tag="transfers_list",
    )


@app.post("/api/v1/planning/transfers/detect")
@documentar(
    "Detecta oportunidades de transferencia entre tiendas",
    cuerpo={"horizonte": 7},
    raiz_xml="transfers_detect_request",
    raiz_respuesta="transfers_detected",
    errores=("400",),
    exito="201",
)
@requiere_auth("planner", "store_manager")
def detectar_transferencias_api():
    """Evalúa excesos vs faltantes y crea propuestas SUGERIDA válidas en PostgreSQL."""
    datos = leer_cuerpo()
    horizonte = entero(datos, "horizonte", minimo=1)
    res = dom_tr.detectar_oportunidades(usuario=usuario_desde_token(), horizonte=horizonte)
    publicar_evento("TRANSFERENCIAS_DETECTADAS", {"total": res["total"], "descartadas": res.get("descartadas", 0)})
    return render_response(res, status=201, root_tag="transfers_detected")


def _decidir_transferencia_api(id_transferencia: str, aprobar: bool):
    id_transferencia = validar_uuid(id_transferencia, "id_transferencia")
    datos = leer_cuerpo()
    cantidad = decimal_pos(datos, "cantidad") if aprobar else None
    fila = one(
        "SELECT id_locacion_origen, id_locacion_destino FROM analitica.transferencia WHERE id_transferencia = CAST(:id AS uuid)",
        id=id_transferencia,
    )
    if not fila:
        return error_response(404, "no_encontrado", f"Transferencia {id_transferencia} no encontrada.")
    validar_alcance_locacion(fila["id_locacion_origen"])
    try:
        res = dom_tr.decidir_transferencia(
            id_transferencia, aprobar=aprobar, usuario=usuario_desde_token(), cantidad=cantidad
        )
    except ValueError as err:
        return error_response(409, "regla_negocio", str(err))
    publicar_evento("TRANSFERENCIA_" + ("APROBADA" if aprobar else "RECHAZADA"), res)
    return render_response(res, status=200, root_tag="transfer_decision")


@app.post("/api/v1/planning/transfers/<id_transferencia>/approve")
@documentar(
    "Aprueba una transferencia SUGERIDA",
    cuerpo={"cantidad": 10},
    raiz_xml="aprobacion_transferencia_request",
    raiz_respuesta="transfer_decision",
    errores=("400", "403", "404", "409"),
    exito="200",
)
@requiere_auth("store_manager", "planner")
def aprobar_transferencia_api(id_transferencia: str):
    """Aprueba humanamente la transferencia sugerida."""
    return _decidir_transferencia_api(id_transferencia, True)


@app.post("/api/v1/planning/transfers/<id_transferencia>/reject")
@documentar("Rechaza una transferencia SUGERIDA", raiz_respuesta="transfer_decision", errores=("400", "403", "404", "409"), exito="200")
@requiere_auth("store_manager", "planner")
def rechazar_transferencia_api(id_transferencia: str):
    """Rechaza la transferencia sugerida."""
    return _decidir_transferencia_api(id_transferencia, False)


@app.post("/api/v1/planning/transfers/<id_transferencia>/execute")
@documentar(
    "Ejecuta una transferencia APROBADA moviendo inventario entre tiendas",
    raiz_respuesta="transfer_executed",
    errores=("400", "403", "404", "409"),
    exito="200",
)
@requiere_auth("store_manager", "warehouse", "planner")
def ejecutar_transferencia_api(id_transferencia: str):
    """Descuenta stock en origen, suma en destino, escribe kardex y registra en desperdicio_evitado."""
    id_transferencia = validar_uuid(id_transferencia, "id_transferencia")
    fila = one(
        "SELECT id_locacion_origen FROM analitica.transferencia WHERE id_transferencia = CAST(:id AS uuid)",
        id=id_transferencia,
    )
    if not fila:
        return error_response(404, "no_encontrado", f"Transferencia {id_transferencia} no encontrada.")
    validar_alcance_locacion(fila["id_locacion_origen"])
    try:
        res = dom_tr.ejecutar_transferencia(id_transferencia, usuario=usuario_desde_token())
    except ValueError as err:
        return error_response(409, "regla_negocio", str(err))
    publicar_evento("TRANSFERENCIA_EJECUTADA", res)
    return render_response(res, status=200, root_tag="transfer_executed")


# =============================================================================
# Descuentos preventivos (REST JSON/XML)
# =============================================================================
@app.get("/api/v1/planning/discounts")
@documentar(
    "Lista descuentos preventivos por lote (filtros)",
    consulta=[("estado", "string", "SUGERIDO/APROBADO/RECHAZADO"), ("limite", "integer", "Máximo registros")],
    raiz_respuesta="discounts_list",
)
@requiere_auth("planner", "store_manager", "buyer")
def listar_descuentos_api():
    """Lista las sugerencias y aprobaciones de descuento preventivo."""
    estado = (request.args.get("estado") or "").upper() or None
    if estado and estado not in ESTADOS_DISCOUNT:
        raise ErrorApi(400, "parametro_invalido", f"Estado inválido. Valores: {sorted(ESTADOS_DISCOUNT)}")
    limite = min(entero(request.args, "limite", minimo=1, defecto=100) or 100, 300)
    filas = dom_desc.listar_descuentos(estado=estado, limite=limite)
    for f in filas:
        f["cantidad"] = a_float(f["cantidad"])
        f["descuento_pct"] = a_float(f["descuento_pct"])
        f["precio_normal"] = a_float(f["precio_normal"])
        f["precio_nuevo"] = a_float(f["precio_nuevo"])
        f["ingreso_potencial"] = a_float(f["ingreso_potencial"])
    return render_response(
        {"total": len(filas), "resumen": dom_desc.resumen_descuentos(), "descuentos": filas},
        status=200,
        root_tag="discounts_list",
    )


@app.post("/api/v1/planning/discounts/generate")
@documentar(
    "Genera sugerencias de descuentos preventivos respetando margen y caducidad",
    cuerpo={"dias_hasta": 5},
    raiz_xml="discounts_generate_request",
    raiz_respuesta="discounts_generated",
    errores=("400",),
    exito="201",
)
@requiere_auth("planner", "store_manager")
def generar_descuentos_api():
    """Calcula descuentos preventivos respetando costo piso y lotes elegibles."""
    datos = leer_cuerpo()
    dias = entero(datos, "dias_hasta", minimo=0)
    res = dom_desc.sugerir_descuentos(usuario=usuario_desde_token(), dias_hasta=dias)
    publicar_evento("DESCUENTOS_SUGERIDOS", {"total": res["total"]})
    return render_response(res, status=201, root_tag="discounts_generated")


def _decidir_descuento_api(id_descuento: str, aprobar: bool):
    id_descuento = validar_uuid(id_descuento, "id_descuento")
    fila = one(
        "SELECT id_locacion FROM analitica.descuento WHERE id_descuento = CAST(:id AS uuid)",
        id=id_descuento,
    )
    if not fila:
        return error_response(404, "no_encontrado", f"Descuento {id_descuento} no encontrado.")
    validar_alcance_locacion(fila["id_locacion"])
    try:
        res = dom_desc.decidir_descuento(id_descuento, aprobar=aprobar, usuario=usuario_desde_token())
    except ValueError as err:
        return error_response(409, "regla_negocio", str(err))
    publicar_evento("DESCUENTO_" + ("APROBADO" if aprobar else "RECHAZADO"), res)
    return render_response(res, status=200, root_tag="discount_decision")


@app.post("/api/v1/planning/discounts/<id_descuento>/approve")
@documentar("Aprueba un descuento preventivo", raiz_respuesta="discount_decision", errores=("400", "403", "404", "409"), exito="200")
@requiere_auth("store_manager", "planner")
def aprobar_descuento_api(id_descuento: str):
    """Aprueba el descuento preventivo y da de alta su seguimiento en desperdicio_evitado."""
    return _decidir_descuento_api(id_descuento, True)


@app.post("/api/v1/planning/discounts/<id_descuento>/reject")
@documentar("Rechaza un descuento preventivo", raiz_respuesta="discount_decision", errores=("400", "403", "404", "409"), exito="200")
@requiere_auth("store_manager", "planner")
def rechazar_descuento_api(id_descuento: str):
    """Rechaza la propuesta de descuento."""
    return _decidir_descuento_api(id_descuento, False)


# =============================================================================
# Motor de Triaje Automático: Descuento ↔ Traslado ↔ Merma
# =============================================================================
@app.get("/api/v1/planning/triage")
@documentar(
    "Evalúa en vivo la decisión óptima por lote (Descuento ↔ Traslado ↔ Merma)",
    consulta=[("id_locacion", "integer", "Tienda opcional"), ("horizonte", "integer", "Días (defecto 7)")],
    raiz_respuesta="triage_evaluation",
)
@requiere_auth("planner", "store_manager", "buyer")
def evaluar_triaje_api():
    """Calcula sin escribir en BD qué ruta económica recupera más valor para cada lote en riesgo."""
    id_locacion = g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1)
    horizonte = entero(request.args, "horizonte", minimo=1, defecto=7)
    res = dom_triaje.evaluar_triaje_lotes(id_locacion=id_locacion, horizonte=horizonte)
    return render_response(res, status=200, root_tag="triage_evaluation")


@app.post("/api/v1/planning/triage/run")
@documentar(
    "Ejecuta el motor de triaje automático (Descuento ↔ Traslado ↔ Merma) y materializa decisiones",
    cuerpo={"horizonte": 7},
    raiz_xml="triage_run_request",
    raiz_respuesta="triage_run_result",
    errores=("400", "403"),
    exito="201",
)
@requiere_auth("planner", "store_manager")
def ejecutar_triaje_api():
    """Evalúa lotes en riesgo, resuelve la mejor acción económica y crea traslados, descuentos o bloqueos."""
    datos = leer_cuerpo()
    id_locacion = g.contexto.get("location_id") or entero(datos, "id_locacion", minimo=1)
    validar_alcance_locacion(id_locacion)
    horizonte = entero(datos, "horizonte", minimo=1, defecto=7)
    res = dom_triaje.ejecutar_triaje_automatico(
        usuario=usuario_desde_token(),
        id_locacion=id_locacion,
        horizonte=horizonte,
    )
    publicar_evento("TRIAJE_PREVENTIVO_EJECUTADO", res["aplicados"])
    return render_response(res, status=201, root_tag="triage_run_result")


@app.post("/api/v1/planning/cycle/run")
@documentar(
    "Ejecuta el ciclo integrado: Auto-Pronóstico por tienda → Triaje → Reabastecimiento Neto",
    cuerpo={"horizonte": 7},
    raiz_xml="planning_cycle_request",
    raiz_respuesta="planning_cycle_result",
    errores=("400", "403"),
    exito="201",
)
@requiere_auth("planner", "store_manager")
def ejecutar_ciclo_planeacion_api():
    """Actualiza modelos por tienda si vencieron, ejecuta triaje preventivo y genera compras netas."""
    datos = leer_cuerpo()
    id_locacion = g.contexto.get("location_id") or entero(datos, "id_locacion", minimo=1)
    validar_alcance_locacion(id_locacion)
    horizonte = entero(datos, "horizonte", minimo=1)
    try:
        res = dom_triaje.ejecutar_ciclo_planeacion(
            usuario=usuario_desde_token(),
            id_locacion=id_locacion,
            horizonte=horizonte,
        )
    except ValueError as err:
        return error_response(400, "regla_negocio", str(err))
    publicar_evento(
        "CICLO_PLANEACION_EJECUTADO",
        {
            "horizonte": res["horizonte"],
            "id_locacion": id_locacion,
            "modelos_recalibrados": res["pronostico"]["total_recalibradas"],
            "ordenes": res["reabastecimiento"]["total"],
        },
    )
    return render_response(res, status=201, root_tag="planning_cycle_result")


# =============================================================================
# Abastecimiento por Proveedor y Órdenes de Compra por Lotes (PDF + Object Storage + Correo)
# =============================================================================
@app.get("/api/v1/planning/procurement/suppliers")
@documentar(
    "Lista proveedores activos con resumen de necesidad de reposición",
    raiz_respuesta="procurement_suppliers",
)
@requiere_auth("buyer")
def listar_proveedores_compra_api():
    resumen = dom_compras.resumen_necesidad_por_proveedor()
    provs = query(
        """
        SELECT id_proveedor, rfc, razon_social, lead_time_dias, moq,
               contacto_email, telefono
        FROM operacion.proveedor
        WHERE activo = true
        ORDER BY razon_social ASC
        """
    )
    salida = []
    for p in provs:
        r = resumen.get(p["id_proveedor"], {})
        salida.append(
            {
                **p,
                "moq": a_float(p["moq"]),
                "productos_activos": r.get("productos_activos", 0),
                "ordenes_pendientes": r.get("ordenes_pendientes", 0),
                "urgentes": r.get("urgentes", 0),
                "unidades_sugeridas": r.get("unidades_sugeridas", 0.0),
            }
        )
    return render_response({"total": len(salida), "proveedores": salida}, status=200, root_tag="procurement_suppliers")


@app.get("/api/v1/planning/procurement/suppliers/<int:id_proveedor>/catalog")
@documentar(
    "Catálogo de compra del proveedor con MOQ por producto y sugerencia Newsvendor por tienda",
    consulta=[("horizonte", "integer", "Horizonte de días opcional")],
    raiz_respuesta="supplier_procurement_catalog",
    errores=("404",),
)
@requiere_auth("buyer")
def catalogo_compra_proveedor_api(id_proveedor: int):
    horizonte = entero(request.args, "horizonte", minimo=1)
    try:
        res = dom_compras.catalogo_compra_proveedor(id_proveedor, horizonte=horizonte)
    except ValueError as err:
        return error_response(404, "no_encontrado", str(err))
    return render_response(res, status=200, root_tag="supplier_procurement_catalog")


@app.post("/api/v1/planning/purchase-orders")
@documentar(
    "Registra una Orden de Compra multi-tienda por lotes y genera su PDF en Cloud Object Storage",
    cuerpo={"id_proveedor": 1, "lineas": [{"id_sku": 1, "id_locacion_destino": 3, "cantidad_lotes": 2}], "observaciones": "Entrega matutina"},
    raiz_xml="purchase_order_request",
    raiz_respuesta="purchase_order",
    errores=("400", "403", "409"),
    exito="201",
)
@requiere_auth("buyer")
def crear_orden_compra_api():
    datos = leer_cuerpo(requerido=True)
    requerir_campos(datos, "id_proveedor", "lineas")
    id_proveedor = entero(datos, "id_proveedor", minimo=1)
    lineas = datos.get("lineas")
    if isinstance(lineas, dict):
        lineas = list(lineas.values())
    if not isinstance(lineas, list) or not lineas:
        raise ErrorApi(400, "parametro_invalido", "'lineas' debe contener al menos una partida de compra.")
    try:
        orden = dom_compras.registrar_orden_compra(
            id_proveedor=id_proveedor,
            lineas=lineas,
            usuario=usuario_desde_token(),
            observaciones=datos.get("observaciones"),
        )
    except ValueError as err:
        return error_response(400, "regla_negocio", str(err))
    return render_response(orden, status=201, root_tag="purchase_order")


@app.get("/api/v1/planning/purchase-orders")
@documentar(
    "Lista órdenes de compra emitidas con metadatos de su PDF en Cloud Object Storage",
    consulta=[("id_proveedor", "integer", "Filtro por proveedor"), ("estado", "string", "Estado OC"), ("limite", "integer", "Máximo")],
    raiz_respuesta="purchase_orders_list",
)
@requiere_auth("buyer", "supplier", "warehouse", "auditor")
def listar_ordenes_compra_api():
    id_prov = entero(request.args, "id_proveedor", minimo=1)
    estado = (request.args.get("estado") or "").upper() or None
    limite = min(entero(request.args, "limite", minimo=1, defecto=50) or 50, 200)
    ordenes = dom_compras.listar_ordenes_compra(id_proveedor=id_prov, estado=estado, limite=limite)
    return render_response({"total": len(ordenes), "ordenes": ordenes}, status=200, root_tag="purchase_orders_list")


@app.get("/api/v1/planning/purchase-orders/<id_oc>")
@documentar("Detalle completo de una Orden de Compra", raiz_respuesta="purchase_order", errores=("400", "404"))
@requiere_auth("buyer", "supplier", "warehouse", "auditor")
def detalle_orden_compra_api(id_oc: str):
    id_oc = validar_uuid(id_oc, "id_oc")
    orden = dom_compras.obtener_orden_compra(id_oc)
    if orden is None:
        return error_response(404, "no_encontrado", f"Orden de compra {id_oc} no encontrada.")
    return render_response(orden, status=200, root_tag="purchase_order")


@app.get("/api/v1/planning/purchase-orders/<id_oc>/pdf")
@documentar(
    "Descarga o visualiza el PDF de la Orden de Compra desde Cloud Object Storage",
    consulta=[("download", "integer", "1 para forzar descarga como adjunto")],
    errores=("400", "404"),
)
@requiere_auth("buyer", "supplier", "warehouse", "auditor")
def pdf_orden_compra_api(id_oc: str):
    id_oc = validar_uuid(id_oc, "id_oc")
    try:
        pdf_bytes, orden = dom_compras.obtener_pdf_orden_compra(id_oc, usuario=usuario_desde_token())
    except ValueError as err:
        return error_response(404, "no_encontrado", str(err))
    disp = "attachment" if request.args.get("download") == "1" else "inline"
    return Response(
        pdf_bytes,
        status=200,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'{disp}; filename="{orden["folio"]}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/v1/planning/purchase-orders/<id_oc>/send-email")
@documentar(
    "Envía la Orden de Compra (con PDF adjunto desde Cloud Object Storage) por correo electrónico",
    cuerpo={"correo": "ventas@proveedor.mx", "mensaje": "Favor confirmar recepción"},
    raiz_xml="send_email_request",
    raiz_respuesta="send_email_result",
    errores=("400", "404"),
)
@requiere_auth("buyer")
def enviar_orden_compra_correo_api(id_oc: str):
    id_oc = validar_uuid(id_oc, "id_oc")
    datos = leer_cuerpo(requerido=True)
    requerir_campos(datos, "correo")
    try:
        res = dom_compras.enviar_orden_compra_correo(
            id_oc=id_oc,
            correo_destino=str(datos["correo"]),
            usuario=usuario_desde_token(),
            mensaje_extra=datos.get("mensaje"),
        )
    except mailer.ErrorCorreo as err:
        return error_response(502, "correo_no_enviado", str(err))
    except ValueError as err:
        msg = str(err)
        codigo = 404 if "no existe" in msg.lower() else 400
        return error_response(codigo, "regla_negocio", msg)
    return render_response(res, status=200, root_tag="send_email_result")


if __name__ == "__main__":
    ejecutar(app, "PLANNING_SERVICE_PORT", 5006)
