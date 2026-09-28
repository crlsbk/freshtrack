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
from app.domain import pronostico as motor_pron
from app.domain import reabastecimiento as motor_reab
from app.domain import transferencias as motor_tr
from app.security import login_required, requiere_vista, usuario_actual

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

    return render_template(
        "analitica/pronostico.html",
        active="forecast",
        corrida=corrida,
        corridas=motor_pron.corridas(10),
        series=series,
        precision=precision,
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
@bp.route("/reabastecimiento")
@login_required
@requiere_vista("replenishment")
def reabastecimiento():
    estado = request.args.get("estado") or "PENDIENTE"
    return render_template(
        "analitica/reabastecimiento.html",
        active="replenishment",
        ordenes=motor_reab.listar_ordenes(estado=estado if estado != "TODAS" else None),
        resumen=motor_reab.resumen_ordenes(),
        sobreinventario=motor_reab.sobreinventario(),
        estado_filtro=estado,
    )


@bp.post("/reabastecimiento/generar")
@login_required
@requiere_vista("replenishment")
def reabastecimiento_generar():
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
    try:
        resultado = motor_reab.decidir_orden(
            id_orden,
            aprobar=aprobar,
            usuario=usuario_actual(),
            cantidad=float(cantidad) if cantidad else None,
        )
        flash(
            f"Orden {resultado['estado'].lower()}"
            + (f" por {resultado['cantidad']:g} unidades." if aprobar else "."),
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.reabastecimiento"))


# ===========================================================================
# TRANSFERENCIAS
# ===========================================================================
@bp.route("/transferencias")
@login_required
@requiere_vista("transfers")
def transferencias():
    estado = request.args.get("estado") or "SUGERIDA"
    return render_template(
        "analitica/transferencias.html",
        active="transfers",
        transferencias=motor_tr.listar_transferencias(
            estado=estado if estado != "TODAS" else None
        ),
        resumen=motor_tr.resumen_transferencias(),
        estado_filtro=estado,
    )


@bp.post("/transferencias/detectar")
@login_required
@requiere_vista("transfers")
def transferencias_detectar():
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
    return redirect(url_for("analitica.transferencias"))


@bp.post("/transferencias/<id_transferencia>/decidir")
@login_required
@requiere_vista("transfers")
def transferencias_decidir(id_transferencia: str):
    aprobar = request.form.get("decision") == "aprobar"
    cantidad = request.form.get("cantidad")
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
    return redirect(url_for("analitica.transferencias"))


@bp.post("/transferencias/<id_transferencia>/ejecutar")
@login_required
@requiere_vista("transfers")
def transferencias_ejecutar(id_transferencia: str):
    try:
        resultado = motor_tr.ejecutar_transferencia(
            id_transferencia, usuario=usuario_actual()
        )
        flash(
            f"Transferencia ejecutada: {resultado['cantidad']:g} unidades de "
            f"{resultado['origen']} a {resultado['destino']}. Inventario movido en "
            f"PostgreSQL (origen queda con {resultado['existencia_origen']:g}, "
            f"destino con {resultado['existencia_destino']:g}).",
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.transferencias"))


# ===========================================================================
# DESCUENTOS
# ===========================================================================
@bp.route("/descuentos")
@login_required
@requiere_vista("discounts")
def descuentos():
    estado = request.args.get("estado") or "SUGERIDO"
    return render_template(
        "analitica/descuentos.html",
        active="discounts",
        descuentos=dom_desc.listar_descuentos(
            estado=estado if estado != "TODAS" else None
        ),
        resumen=dom_desc.resumen_descuentos(),
        estado_filtro=estado,
    )


@bp.post("/descuentos/generar")
@login_required
@requiere_vista("discounts")
def descuentos_generar():
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
    return redirect(url_for("analitica.descuentos"))


@bp.post("/descuentos/<id_descuento>/decidir")
@login_required
@requiere_vista("discounts")
def descuentos_decidir(id_descuento: str):
    aprobar = request.form.get("decision") == "aprobar"
    try:
        resultado = dom_desc.decidir_descuento(
            id_descuento, aprobar=aprobar, usuario=usuario_actual()
        )
        flash(f"Descuento {resultado['estado'].lower()}.", "ok")
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("analitica.descuentos"))
