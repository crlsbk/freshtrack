"""
Blueprint de analítica.

    /pronostico        corridas de pronóstico y su precisión
    /reabastecimiento  recomendaciones con aprobación humana
    /transferencias    sugerencias entre tiendas con validaciones
    /descuentos        sugerencias de descuento para lotes por vencer
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from app.db import a_int, config_valor, sql_error
from app.domain import alertas as motor_alertas
from app.domain import descuentos as dom_desc
from app.domain import inventario as dom_inv
from app.domain import mermas as dom_mermas
from app.domain import pronostico as motor_pron
from app.domain import reabastecimiento as motor_reab
from app.domain import transferencias as motor_tr
from app.domain import triaje as dom_triaje
from app.security import login_required, requiere_vista, usuario_actual
from app.services import clientes

bp = Blueprint("analitica", __name__)


# ===========================================================================
# PRONÓSTICO
# ===========================================================================
@bp.route("/pronostico")
@login_required
@requiere_vista("forecast")
def pronostico():
    corrida = motor_pron.ultima_corrida()
    id_run = request.args.get("run") or (corrida["id_run"] if corrida else None)

    series = motor_pron.pronostico_por_serie(id_run) if id_run else []
    precision = motor_pron.precision_global()
    backtest = None
    try:
        if clientes.activo():
            st, resp = clientes.como_usuario("planning", "GET", "/api/v1/planning/forecast/backtest", timeout=5)
            if st == 200 and isinstance(resp, dict):
                backtest = resp
        if backtest is None:
            backtest = motor_pron.evaluar_backtest_comparativo(horizonte=7)
    except Exception:
        backtest = None

    return render_template(
        "analitica/pronostico.html",
        active="forecast",
        corrida=corrida,
        corridas=motor_pron.corridas(10),
        series=series,
        precision=precision,
        backtest=backtest,
        id_run=id_run,
        metodos=motor_pron.METODOS,
        horizonte_defecto=a_int(config_valor("horizonte_pronostico_dias", "7"), 7),
        ventana_defecto=a_int(config_valor("ventana_media_movil", "28"), 28),
        alpha_defecto=config_valor("alpha_suavizacion", "0.30"),
        locaciones=dom_inv.locaciones_activas(),
    )


@bp.post("/pronostico/ejecutar")
@login_required
@requiere_vista("forecast")
def pronostico_ejecutar():
    if clientes.activo():
        # El cálculo lo hace svc-planning: guarda la corrida en PostgreSQL y la serie en MongoDB.
        cuerpo = {
            "metodo": request.form.get("metodo", "SUAVIZACION_EXPONENCIAL"),
            "horizonte": request.form.get("horizonte") or 7,
            "ventana": request.form.get("ventana") or 28,
            "alpha": request.form.get("alpha") or 0.30,
            "dias_historia": request.form.get("dias_historia") or 120,
        }
        if request.form.get("id_locacion"):
            cuerpo["id_locacion"] = request.form["id_locacion"]
        status, r = clientes.como_usuario("planning", "POST", "/api/v1/planning/forecast/run", cuerpo, timeout=120)
        if status == 201 and r.get("series", 0) == 0:
            flash("No hay series con historia suficiente para pronosticar. Carga datos con el ETL o registra ventas primero.", "error")
        elif status == 201:
            flash(
                f"Pronóstico ejecutado ({r.get('metodo_etiqueta', r.get('metodo'))}): "
                f"{r['series']} series de producto y tienda, horizonte {r['horizonte']} días. "
                f"Error medido — MAE {r['mae']}, RMSE {r['rmse']}, WMAPE {r['wmape']}%.",
                "ok",
            )
        else:
            flash(f"El pronóstico no se ejecutó: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.pronostico"))
    try:
        resultado = motor_pron.ejecutar_pronostico(
            usuario=usuario_actual(),
            metodo=request.form.get("metodo", "SUAVIZACION_EXPONENCIAL"),
            horizonte=a_int(request.form.get("horizonte"), 7),
            ventana=a_int(request.form.get("ventana"), 28),
            alpha=float(request.form.get("alpha", 0.30) or 0.30),
            dias_historia=a_int(request.form.get("dias_historia"), 120),
            id_locacion=int(request.form["id_locacion"]) if request.form.get("id_locacion") else None,
        )
        if resultado["series"] == 0:
            flash(
                "No hay series con historia suficiente para pronosticar. "
                "Carga datos con el ETL o registra ventas primero.",
                "error",
            )
        else:
            flash(
                f"Pronóstico ejecutado ({resultado['metodo_etiqueta']}): "
                f"{resultado['series']} series de producto + tienda, horizonte "
                f"{resultado['horizonte']} días. Error medido — "
                f"MAE {resultado['mae']}, RMSE {resultado['rmse']}, "
                f"WMAPE {resultado['wmape']}%. Corrida guardada con su trazabilidad.",
                "ok",
            )
    except (ValueError, SQLAlchemyError) as e:
        flash(
            sql_error(e) if isinstance(e, SQLAlchemyError) else str(e),
            "error",
        )
    return redirect(url_for("analitica.pronostico"))


# ===========================================================================
# REABASTECIMIENTO
# ===========================================================================
# Estados posibles de una orden: los mismos que valida el CHECK chk_or_estado
# de analitica.orden_reabastecimiento. El desplegable «Estado» se genera desde
# aquí para que no se desincronice del filtro del listado.
ESTADOS_ORDEN = ("PENDIENTE", "APROBADA", "RECHAZADA", "EJECUTADA", "CANCELADA")


def _filtro_ordenes(estado: str | None) -> str:
    """Normaliza el filtro del listado; cualquier valor desconocido cae en PENDIENTE."""
    if estado == "TODAS" or estado in ESTADOS_ORDEN:
        return estado
    return "PENDIENTE"


@bp.route("/reabastecimiento")
@login_required
@requiere_vista("replenishment")
def reabastecimiento():
    estado = _filtro_ordenes(request.args.get("estado"))
    return render_template(
        "analitica/reabastecimiento.html",
        active="replenishment",
        ordenes=motor_reab.listar_ordenes(estado=estado if estado != "TODAS" else None),
        resumen=motor_reab.resumen_ordenes(),
        sobreinventario=motor_reab.sobreinventario(),
        estado_filtro=estado,
        estados=ESTADOS_ORDEN,
    )


@bp.post("/reabastecimiento/generar")
@login_required
@requiere_vista("replenishment")
def reabastecimiento_generar():
    if clientes.activo():
        cuerpo = {"horizonte": request.form.get("horizonte")} if request.form.get("horizonte") else {}
        status, r = clientes.como_usuario("planning", "POST", "/api/v1/planning/replenishment/generate", cuerpo, timeout=120)
        if status == 201:
            flash(
                f"Se revisaron {r.get('revisadas', 0)} combinaciones de producto y tienda y se generaron "
                f"{r.get('total', 0)} recomendaciones nuevas (pendientes de aprobación).",
                "ok",
            )
            motor_alertas.generar_alertas(usuario_actual())
        else:
            flash(f"No se generaron recomendaciones: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.reabastecimiento"))
    try:
        resultado = motor_reab.generar_recomendaciones(
            usuario=usuario_actual(),
            horizonte=a_int(request.form.get("horizonte"), 0) or None,
        )
        if resultado["total"] == 0:
            flash(
                f"Se revisaron {resultado['revisadas']} combinaciones de producto y tienda: "
                f"ninguna necesita reabastecimiento en este momento "
                f"(o ya hay una orden pendiente para las que sí lo necesitan).",
                "ok",
            )
        else:
            flash(
                f"Se generaron {resultado['total']} recomendaciones de reabastecimiento "
                f"a partir de {resultado['revisadas']} combinaciones evaluadas. "
                f"Cada una incluye su explicación y queda pendiente de aprobación.",
                "ok",
            )
        motor_alertas.generar_alertas(usuario_actual())
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.reabastecimiento"))


@bp.post("/reabastecimiento/<id_orden>/decidir")
@login_required
@requiere_vista("replenishment")
def reabastecimiento_decidir(id_orden: str):
    aprobar = request.form.get("decision") == "aprobar"
    cantidad = request.form.get("cantidad")
    # El formulario viaja con el filtro activo: al decidir, el usuario vuelve a
    # la misma lista desde la que actuó (si venía de «Pendiente» no pierde la
    # cola) y el aviso le dice con qué filtro encontrar la orden ya decidida.
    filtro = _filtro_ordenes(request.form.get("filtro"))
    if clientes.activo():
        accion = "approve" if aprobar else "reject"
        cuerpo = {"cantidad": cantidad} if (aprobar and cantidad) else {}
        status, r = clientes.como_usuario(
            "planning", "POST", f"/api/v1/planning/replenishment/orders/{id_orden}/{accion}", cuerpo
        )
        if status == 200:
            flash(
                f"Orden {r['estado'].lower()}"
                + (f" por {float(r['cantidad']):g} unidades." if aprobar and r.get("cantidad") is not None else ".")
                + f" La encuentras con el filtro «{r['estado']}».",
                "ok",
            )
        else:
            flash(f"La orden no cambió: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.reabastecimiento", estado=filtro))
    try:
        resultado = motor_reab.decidir_orden(
            id_orden,
            aprobar=aprobar,
            usuario=usuario_actual(),
            cantidad=float(cantidad) if cantidad else None,
        )
        flash(
            f"Orden {resultado['estado'].lower()}"
            + (f" por {resultado['cantidad']:g} unidades." if aprobar else ".")
            + f" La encuentras con el filtro «{resultado['estado']}».",
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.reabastecimiento", estado=filtro))


# ===========================================================================
# TRANSFERENCIAS (consolidadas en Triaje)
# ===========================================================================
@bp.route("/transferencias")
@login_required
def transferencias():
    return redirect(url_for("analitica.triaje", tab="traslados"))


@bp.post("/transferencias/detectar")
@login_required
@requiere_vista("triage")
def transferencias_detectar():
    if clientes.activo():
        status, r = clientes.como_usuario("planning", "POST", "/api/v1/planning/transfers/detect", {})
        if status == 201:
            if r.get("total", 0) == 0:
                flash(
                    f"No se encontraron transferencias que pasaran las cuatro validaciones "
                    f"({r.get('descartadas', 0)} candidatas descartadas).",
                    "ok",
                )
            else:
                flash(
                    f"Se sugirieron {r['total']} transferencias entre tiendas. "
                    f"Cada una pasó origen suficiente, destino con necesidad, llegada antes de vencer y consumo.",
                    "ok",
                )
            motor_alertas.generar_alertas(usuario_actual())
        else:
            flash(f"No se detectaron transferencias: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.triaje", tab="traslados"))
    try:
        resultado = motor_tr.detectar_oportunidades(usuario=usuario_actual())
        if resultado["total"] == 0:
            flash(
                f"No se encontraron transferencias que pasaran las cuatro validaciones "
                f"({resultado['descartadas']} candidatas descartadas por no cumplirlas).",
                "ok",
            )
        else:
            flash(
                f"Se sugirieron {resultado['total']} transferencias entre tiendas. "
                f"Cada una pasó las validaciones de origen suficiente, destino con "
                f"necesidad, llegada antes de vencer y capacidad de consumo.",
                "ok",
            )
        motor_alertas.generar_alertas(usuario_actual())
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.triaje", tab="traslados"))


@bp.post("/transferencias/<id_transferencia>/decidir")
@login_required
@requiere_vista("triage")
def transferencias_decidir(id_transferencia: str):
    aprobar = request.form.get("decision") == "aprobar"
    cantidad = request.form.get("cantidad")
    if clientes.activo():
        accion = "approve" if aprobar else "reject"
        cuerpo = {"cantidad": cantidad} if (aprobar and cantidad) else {}
        status, r = clientes.como_usuario(
            "planning", "POST", f"/api/v1/planning/transfers/{id_transferencia}/{accion}", cuerpo
        )
        if status == 200:
            flash(
                f"Transferencia {r['estado'].lower()}"
                + (f" por {float(r['cantidad']):g} unidades." if aprobar and r.get("cantidad") is not None else "."),
                "ok",
            )
        else:
            flash(f"La transferencia no cambió: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.triaje", tab="traslados"))
    try:
        resultado = motor_tr.decidir_transferencia(
            id_transferencia,
            aprobar=aprobar,
            usuario=usuario_actual(),
            cantidad=float(cantidad) if cantidad else None,
        )
        flash(
            f"Transferencia {resultado['estado'].lower()}"
            + (f" por {resultado['cantidad']:g} unidades." if aprobar else "."),
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.triaje", tab="traslados"))


@bp.post("/transferencias/<id_transferencia>/ejecutar")
@login_required
@requiere_vista("triage")
def transferencias_ejecutar(id_transferencia: str):
    if clientes.activo():
        status, r = clientes.como_usuario(
            "planning", "POST", f"/api/v1/planning/transfers/{id_transferencia}/execute", {}
        )
        if status == 200:
            flash(
                f"Transferencia ejecutada: {float(r['cantidad']):g} unidades de "
                f"{r['origen']} a {r['destino']} (origen: {float(r['existencia_origen']):g}, "
                f"destino: {float(r['existencia_destino']):g}).",
                "ok",
            )
        else:
            flash(f"No se ejecutó la transferencia: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.triaje", tab="traslados"))
    try:
        resultado = motor_tr.ejecutar_transferencia(
            id_transferencia, usuario=usuario_actual()
        )
        flash(
            f"Transferencia ejecutada: {resultado['cantidad']:g} unidades de "
            f"{resultado['origen']} a {resultado['destino']}. Inventario actualizado "
            f"(origen queda con {resultado['existencia_origen']:g}, "
            f"destino con {resultado['existencia_destino']:g}).",
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.triaje", tab="traslados"))


# ===========================================================================
# DESCUENTOS (consolidados en Triaje)
# ===========================================================================
@bp.route("/descuentos")
@login_required
def descuentos():
    return redirect(url_for("analitica.triaje", tab="descuentos"))


@bp.post("/descuentos/generar")
@login_required
@requiere_vista("triage")
def descuentos_generar():
    if clientes.activo():
        status, r = clientes.como_usuario("planning", "POST", "/api/v1/planning/discounts/generate", {})
        if status == 201:
            flash(
                f"Se generaron {r['total']} sugerencias de descuento respetando margen y caducidad."
                if r.get("total")
                else "No se detectaron lotes en vigilancia o crítico elegibles para descuento.",
                "ok",
            )
        else:
            flash(f"No se generaron descuentos: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.triaje", tab="descuentos"))
    try:
        resultado = dom_desc.sugerir_descuentos(usuario=usuario_actual())
        flash(
            f"Se generaron {resultado['total']} sugerencias de descuento para lotes "
            f"próximos a vencer."
            if resultado["total"]
            else "No hay lotes en vigilancia o crítico que necesiten descuento.",
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.triaje", tab="descuentos"))


@bp.post("/descuentos/<id_descuento>/decidir")
@login_required
@requiere_vista("triage")
def descuentos_decidir(id_descuento: str):
    aprobar = request.form.get("decision") == "aprobar"
    if clientes.activo():
        accion = "approve" if aprobar else "reject"
        status, r = clientes.como_usuario(
            "planning", "POST", f"/api/v1/planning/discounts/{id_descuento}/{accion}", {}
        )
        if status == 200:
            flash(f"Descuento {r['estado'].lower()} correctamente.", "ok")
        else:
            flash(f"El descuento no cambió: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.triaje", tab="descuentos"))
    try:
        resultado = dom_desc.decidir_descuento(
            id_descuento, aprobar=aprobar, usuario=usuario_actual()
        )
        flash(f"Descuento {resultado['estado'].lower()}.", "ok")
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.triaje", tab="descuentos"))


# ===========================================================================
# CENTRO ÚNICO DE TRIAJE PREVENTIVO (DESCUENTO ↔ TRASLADO ↔ MERMA)
# ===========================================================================
@bp.route("/triaje")
@login_required
@requiere_vista("triage")
def triaje():
    id_loc = int(request.args["locacion"]) if request.args.get("locacion") else None
    filtro_accion = (request.args.get("accion") or "").upper()
    estado_tr = request.args.get("estado_tr") or "SUGERIDA"
    estado_desc = request.args.get("estado_desc") or "SUGERIDO"
    filtro_causa = request.args.get("causa") or ""
    tab_activa = request.args.get("tab") or "triaje"
    if tab_activa not in ("triaje", "traslados", "descuentos", "mermas"):
        tab_activa = "triaje"

    evaluacion = None
    if clientes.activo():
        ruta = "/api/v1/planning/triage" + (f"?id_locacion={id_loc}" if id_loc else "")
        status, r = clientes.como_usuario("planning", "GET", ruta, timeout=10)
        if status == 200 and isinstance(r, dict):
            evaluacion = r
    if evaluacion is None or any("transferencia_activa" not in d for d in evaluacion.get("decisiones", [])):
        evaluacion = dom_triaje.evaluar_triaje_lotes(id_locacion=id_loc)

    decisiones = evaluacion.get("decisiones", [])
    if filtro_accion in ("TRASLADO", "DESCUENTO", "MERMA", "NORMAL"):
        decisiones = [d for d in decisiones if d["accion"] == filtro_accion]

    return render_template(
        "analitica/triaje.html",
        active="triage",
        evaluacion=evaluacion,
        decisiones=decisiones,
        locaciones=dom_inv.locaciones_activas("Tienda"),
        locaciones_todas=dom_inv.locaciones_activas(),
        id_locacion=id_loc,
        filtro_accion=filtro_accion,
        tab_activa=tab_activa,
        transferencias=motor_tr.listar_transferencias(estado=estado_tr if estado_tr != "TODAS" else None),
        resumen_tr=motor_tr.resumen_transferencias(),
        estado_tr=estado_tr,
        descuentos=dom_desc.listar_descuentos(estado=estado_desc if estado_desc != "TODAS" else None),
        resumen_desc=dom_desc.resumen_descuentos(),
        estado_desc=estado_desc,
        mermas=dom_mermas.mermas_recientes(id_locacion=id_loc, causa=filtro_causa or None),
        resumen_mermas=dom_mermas.resumen_mermas(dias=180),
        causas_merma=dom_mermas.CAUSAS,
        lotes_merma=dom_mermas.lotes_para_merma(id_locacion=id_loc),
        filtro_causa=filtro_causa,
    )


@bp.post("/triaje/ejecutar")
@login_required
@requiere_vista("triage")
def triaje_ejecutar():
    cuerpo = {}
    if request.form.get("id_locacion"):
        cuerpo["id_locacion"] = int(request.form["id_locacion"])
    if clientes.activo():
        status, r = clientes.como_usuario("planning", "POST", "/api/v1/planning/triage/run", cuerpo, timeout=30)
        if status == 201:
            ap = r.get("aplicados", {})
            flash(
                f"Triaje automático ejecutado: {r.get('total_evaluados', 0)} lotes evaluados → "
                f"{ap.get('traslados_creados', 0)} traslados sugeridos, "
                f"{ap.get('descuentos_creados', 0)} descuentos propuestos, "
                f"{ap.get('lotes_vencidos_bloqueados', 0)} lotes vencidos bloqueados.",
                "ok",
            )
            motor_alertas.generar_alertas(usuario_actual())
        else:
            flash(f"No se pudo ejecutar el triaje: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("analitica.triaje"))

    try:
        res = dom_triaje.ejecutar_triaje_automatico(
            usuario=usuario_actual(), id_locacion=cuerpo.get("id_locacion")
        )
        ap = res["aplicados"]
        flash(
            f"Triaje automático ejecutado: {ap['traslados_creados']} traslados, "
            f"{ap['descuentos_creados']} descuentos, {ap['lotes_vencidos_bloqueados']} lotes vencidos bloqueados.",
            "ok",
        )
        motor_alertas.generar_alertas(usuario_actual())
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.triaje"))


@bp.post("/triaje/accion-lote")
@login_required
@requiere_vista("triage")
def triaje_accion_lote():
    id_lote = request.form.get("id_lote", "").strip()
    tipo_accion = request.form.get("tipo_accion", "").strip().upper()
    tab_origen = request.form.get("tab_origen") or "triaje"
    try:
        id_loc = int(request.form["id_locacion"])
        id_dest = int(request.form["id_locacion_destino"]) if request.form.get("id_locacion_destino") else None
        cantidad = float(request.form["cantidad"]) if request.form.get("cantidad") else None
        desc_pct = float(request.form["descuento_pct"]) if request.form.get("descuento_pct") else None
        ejecutar_fisico = request.form.get("ejecutar_fisico") == "1"
        res = dom_triaje.ejecutar_accion_directa_lote(
            id_lote=id_lote,
            id_locacion=id_loc,
            tipo_accion=tipo_accion,
            usuario=usuario_actual(),
            id_locacion_destino=id_dest,
            cantidad=cantidad,
            descuento_pct=desc_pct,
            causa_merma=request.form.get("causa_merma") or "CADUCIDAD",
            observacion=request.form.get("observacion"),
            ejecutar_fisico=ejecutar_fisico,
        )
        flash(res.get("mensaje") or "Acción ejecutada correctamente.", "ok")
        motor_alertas.generar_alertas(usuario_actual())
    except (ValueError, KeyError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.triaje", tab=tab_origen))
