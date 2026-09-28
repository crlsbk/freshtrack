"""
Blueprint de operación diaria.

    /lotes           recepción de lotes y consulta de caducidades
    /inventario      inventario real por producto → tienda → lote → caducidad
    /ventas          registro de ventas con FEFO transaccional
    /fefo            cola FEFO
    /mermas          registro y análisis de mermas
    /trazabilidad    ciclo de vida completo de un lote
"""

from __future__ import annotations

from datetime import date, datetime

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy.exc import SQLAlchemyError

from app.db import sql_error
from app.domain import inventario as dom_inv
from app.domain import mermas as dom_mermas
from app.domain import ventas as dom_ventas
from app.security import login_required, requiere_vista, usuario_actual

bp = Blueprint("operacion", __name__)


def _fecha(valor, default=None):
    if not valor:
        return default
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return default


# ===========================================================================
# LOTES Y RECEPCIÓN
# ===========================================================================
@bp.route("/lotes", methods=["GET", "POST"])
@login_required
@requiere_vista("batches")
def lotes():
    usuario = usuario_actual()

    if request.method == "POST":
        try:
            resultado = dom_inv.registrar_recepcion(
                id_sku=int(request.form["id_sku"]),
                id_proveedor=int(request.form["id_proveedor"]),
                id_locacion=int(request.form["id_locacion"]),
                codigo_lote_prov=request.form.get("codigo_lote_prov", ""),
                fecha_produccion=_fecha(request.form.get("fecha_produccion")),
                fecha_recepcion=_fecha(request.form.get("fecha_recepcion"), date.today()),
                fecha_caducidad=_fecha(request.form.get("fecha_caducidad")),
                cantidad=float(request.form.get("cantidad", 0) or 0),
                costo_unitario=float(request.form.get("costo_unitario", 0) or 0),
                observaciones=request.form.get("observaciones"),
                usuario=usuario,
            )
            flash(
                f"Lote «{resultado['codigo_lote_prov']}» recibido. Inventario actualizado "
                f"en PostgreSQL.",
                "ok",
            )
        except (ValueError, KeyError) as e:
            flash(f"No se registró la recepción: {e}", "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("operacion.lotes"))

    return render_template(
        "operacion/lotes.html",
        active="batches",
        lotes=dom_inv.listar_lotes(
            texto=request.args.get("q"),
            clasificacion=request.args.get("riesgo") or None,
            id_locacion=int(request.args["locacion"]) if request.args.get("locacion") else None,
        ),
        productos=dom_inv.productos_activos(),
        proveedores=dom_inv.proveedores_activos(),
        locaciones=dom_inv.locaciones_activas(),
        hoy=date.today().isoformat(),
        filtro=request.args.get("q", ""),
        filtro_riesgo=request.args.get("riesgo", ""),
    )


# ===========================================================================
# INVENTARIO
# ===========================================================================
@bp.route("/inventario")
@login_required
@requiere_vista("inventory")
def inventario():
    id_locacion = int(request.args["locacion"]) if request.args.get("locacion") else None
    texto = request.args.get("q") or None
    return render_template(
        "operacion/inventario.html",
        active="inventory",
        grupos=dom_inv.inventario_agrupado(id_locacion=id_locacion, texto=texto),
        resumen=dom_inv.resumen_inventario(),
        locaciones=dom_inv.locaciones_activas(),
        id_locacion=id_locacion,
        filtro=request.args.get("q", ""),
    )


# ===========================================================================
# VENTAS (FEFO transaccional)
# ===========================================================================
@bp.route("/ventas", methods=["GET", "POST"])
@login_required
@requiere_vista("sales")
def ventas():
    usuario = usuario_actual()

    if request.method == "POST":
        try:
            id_locacion = int(request.form["id_locacion"])
            id_sku = int(request.form["id_sku"])
            cantidad = float(request.form["cantidad"])

            resultado = dom_ventas.registrar_venta(
                id_locacion=id_locacion,
                lineas=[{"id_sku": id_sku, "cantidad": cantidad}],
                usuario=usuario,
            )
            reparto = " · ".join(
                f"{a['consumido']:g} del lote {a['codigo_lote_prov']}"
                for a in resultado["asignaciones"]
            )
            flash(
                f"Venta {resultado['folio']} registrada por {resultado['total']:,.2f}. "
                f"FEFO consumió: {reparto}.",
                "ok",
            )
        except (ValueError, KeyError) as e:
            flash(f"La venta no se registró: {e}", "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("operacion.ventas"))

    id_locacion = int(request.args["locacion"]) if request.args.get("locacion") else None
    return render_template(
        "operacion/ventas.html",
        active="sales",
        ventas=dom_ventas.ventas_recientes(
            id_locacion=id_locacion, texto=request.args.get("q") or None
        ),
        resumen=dom_ventas.resumen_ventas(id_locacion=id_locacion),
        locaciones=dom_inv.locaciones_activas("Tienda"),
        productos=dom_inv.productos_activos(),
        id_locacion=id_locacion,
        filtro=request.args.get("q", ""),
    )


@bp.post("/ventas/previsualizar")
@login_required
@requiere_vista("sales")
def ventas_previsualizar():
    """Devuelve, sin tocar la base, cómo repartiría FEFO una venta."""
    datos = request.get_json(silent=True) or request.form
    try:
        id_sku = int(datos.get("id_sku"))
        id_locacion = int(datos.get("id_locacion"))
        cantidad = float(datos.get("cantidad") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Parámetros inválidos."}), 400

    if cantidad <= 0:
        return jsonify({"error": "La cantidad debe ser mayor que cero."}), 400

    resultado = dom_ventas.previsualizar_fefo(id_sku, id_locacion, cantidad)
    return jsonify(
        {
            "consumos": [
                {
                    "lote": c["codigo_lote_prov"],
                    "fecha_caducidad": str(c["fecha_caducidad"]),
                    "dias_restantes": c["dias_restantes"],
                    "disponible_antes": c["disponible_antes"],
                    "consumido": c["consumido"],
                    "disponible_despues": c["disponible_despues"],
                }
                for c in resultado["consumos"]
            ],
            "solicitado": resultado["solicitado"],
            "cubierto": resultado["cubierto"],
            "faltante": resultado["faltante"],
            "suficiente": resultado["suficiente"],
        }
    )


# ===========================================================================
# FEFO
# ===========================================================================
@bp.route("/fefo")
@login_required
@requiere_vista("fefo")
def fefo():
    id_locacion = int(request.args["locacion"]) if request.args.get("locacion") else None
    return render_template(
        "operacion/fefo.html",
        active="fefo",
        cola=dom_inv.cola_fefo(id_locacion=id_locacion),
        locaciones=dom_inv.locaciones_activas(),
        id_locacion=id_locacion,
    )


# ===========================================================================
# MERMAS
# ===========================================================================
@bp.route("/mermas", methods=["GET", "POST"])
@login_required
@requiere_vista("shrinkage")
def mermas():
    usuario = usuario_actual()

    if request.method == "POST":
        try:
            resultado = dom_mermas.registrar_merma(
                id_lote=request.form["id_lote"],
                id_locacion=int(request.form["id_locacion"]),
                cantidad=float(request.form["cantidad"]),
                causa=request.form["causa_merma"],
                observacion=request.form.get("observacion"),
                usuario=usuario,
            )
            flash(
                f"Merma registrada en PostgreSQL: {resultado['cantidad']:g} "
                f"{resultado['unidad_medida']} de {resultado['producto']} "
                f"(lote {resultado['codigo_lote_prov']}) por {resultado['causa_etiqueta']}. "
                f"Valor {resultado['valor_merma']:,.2f}. Inventario descontado: quedan "
                f"{resultado['existencia_restante']:g}.",
                "ok",
            )
        except (ValueError, KeyError) as e:
            flash(f"La merma NO se registró: {e}", "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("operacion.mermas"))

    return render_template(
        "operacion/mermas.html",
        active="shrinkage",
        mermas=dom_mermas.mermas_recientes(
            id_locacion=int(request.args["locacion"]) if request.args.get("locacion") else None,
            causa=request.args.get("causa") or None,
        ),
        resumen=dom_mermas.resumen_mermas(dias=180),
        causas=dom_mermas.CAUSAS,
        lotes=dom_mermas.lotes_para_merma(),
        locaciones=dom_inv.locaciones_activas(),
        filtro_causa=request.args.get("causa", ""),
    )


# ===========================================================================
# TRAZABILIDAD
# ===========================================================================
@bp.route("/trazabilidad")
@login_required
@requiere_vista("traceability")
def trazabilidad():
    id_lote = request.args.get("lote")
    detalle = dom_inv.trazabilidad(id_lote) if id_lote else None
    return render_template(
        "operacion/trazabilidad.html",
        active="traceability",
        detalle=detalle or {},
        id_lote=id_lote,
        lotes=dom_inv.listar_lotes(limite=200),
    )
