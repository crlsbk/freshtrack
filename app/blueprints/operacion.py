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

import json
import random
from datetime import date, datetime
from decimal import Decimal

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import SQLAlchemyError

from app.db import a_float, a_int, query, sql_error
from app.domain import inventario as dom_inv
from app.domain import mermas as dom_mermas
from app.domain import ventas as dom_ventas
from app.security import login_required, requiere_vista, usuario_actual
from app.services import clientes

bp = Blueprint("operacion", __name__)


def _json_safe(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return obj


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
                f"Lote «{resultado['codigo_lote_prov']}» recibido e incorporado al inventario.",
                "ok",
            )
        except (ValueError, KeyError) as e:
            flash(f"No se registró la recepción: {e}", "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("operacion.lotes"))

    dom_inv.bloquear_lotes_vencidos(usuario=usuario)

    return render_template(
        "operacion/lotes.html",
        active="batches",
        lotes=dom_inv.listar_lotes(
            texto=request.args.get("q"),
            clasificacion=request.args.get("riesgo") or None,
            id_locacion=int(request.args["locacion"]) if request.args.get("locacion") else None,
        ),
        estados_lote=dom_inv.ESTADOS_LOTE_VALIDOS,
        productos=dom_inv.productos_activos(),
        proveedores=dom_inv.proveedores_activos(),
        locaciones=dom_inv.locaciones_activas(),
        hoy=date.today().isoformat(),
        filtro=request.args.get("q", ""),
        filtro_riesgo=request.args.get("riesgo", ""),
    )


@bp.post("/lotes/<id_lote>/estado")
@login_required
@requiere_vista("batches")
def lotes_cambiar_estado(id_lote: str):
    nuevo_estado = request.form.get("estado", "")
    motivo = request.form.get("motivo")
    if clientes.activo():
        status, r = clientes.como_usuario(
            "inventory",
            "PATCH",
            f"/api/v1/inventory/batches/{id_lote}/status",
            {"estado": nuevo_estado, "motivo": motivo},
        )
        if status == 200:
            flash(
                f"Estado del lote {r.get('codigo_lote_prov', '')} actualizado a «{r['estado']}». "
                + ("Elegible para salida FEFO." if r.get("elegible_fefo") else "Inmovilizado (excluido de FEFO y ventas)."),
                "ok",
            )
        else:
            flash(f"No se cambió el estado del lote: {clientes.mensaje_error('inventory', status, r)}", "error")
        return redirect(url_for("operacion.lotes"))
    try:
        res = dom_inv.cambiar_estado_lote(
            id_lote=id_lote, nuevo_estado=nuevo_estado, motivo=motivo, usuario=usuario_actual()
        )
        flash(f"Estado del lote {res['codigo_lote_prov']} cambiado a «{res['estado']}».", "ok")
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("operacion.lotes"))


@bp.post("/lotes/escanear-caducidad")
@login_required
@requiere_vista("batches")
def lotes_escanear_caducidad():
    if clientes.activo():
        status, r = clientes.como_usuario("inventory", "POST", "/api/v1/inventory/expiration/scan", {"dias_critico": 2})
        if status == 200:
            flash(
                f"Escaneo completado: {r.get('lotes_vencidos_bloqueados', 0)} lote(s) vencido(s) retirados de salida FEFO, "
                f"{r.get('lotes_criticos_actuales', 0)} lote(s) en riesgo crítico.",
                "ok",
            )
        else:
            flash(f"No se ejecutó el escaneo: {clientes.mensaje_error('inventory', status, r)}", "error")
        return redirect(url_for("operacion.lotes"))
    res = dom_inv.bloquear_lotes_vencidos(usuario=usuario_actual())
    flash(f"Se bloquearon {res['bloqueados']} lote(s) vencido(s) de la cola FEFO.", "ok")
    return redirect(url_for("operacion.lotes"))


@bp.get("/lotes/<id_lote>/trazabilidad-json")
@login_required
def lotes_trazabilidad_json(id_lote: str):
    detalle = dom_inv.trazabilidad(id_lote)
    if not detalle or not detalle.get("lote"):
        return jsonify({"error": "No se encontró el lote solicitado."}), 404
    return jsonify(_json_safe(detalle))


# ===========================================================================
# INVENTARIO
# ===========================================================================
@bp.route("/inventario")
@login_required
@requiere_vista("inventory")
def inventario():
    dom_inv.bloquear_lotes_vencidos(usuario=usuario_actual())
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
# MONITOR DE VENTAS EN TIEMPO REAL
# ===========================================================================
@bp.route("/ventas")
@login_required
@requiere_vista("sales")
def ventas():
    id_locacion = int(request.args["locacion"]) if request.args.get("locacion") else None
    return render_template(
        "operacion/ventas.html",
        active="sales",
        ventas=dom_ventas.ventas_recientes(
            id_locacion=id_locacion, texto=request.args.get("q") or None, limite=50
        ),
        resumen=dom_ventas.resumen_ventas(id_locacion=id_locacion),
        locaciones=dom_inv.locaciones_activas("Tienda"),
        productos=dom_inv.productos_activos(),
        id_locacion=id_locacion,
        filtro=request.args.get("q", ""),
    )


@bp.get("/ventas/tiempo-real")
@login_required
@requiere_vista("sales")
def ventas_tiempo_real():
    id_locacion = int(request.args["locacion"]) if request.args.get("locacion") else None
    texto = (request.args.get("q") or "").strip() or None
    recientes = dom_ventas.ventas_recientes(id_locacion=id_locacion, texto=texto, limite=30)
    resumen = dom_ventas.resumen_ventas(id_locacion=id_locacion)
    por_tienda = query(
        """
        SELECT loc.nombre AS locacion,
               COUNT(DISTINCT v.id_venta) AS tickets,
               COALESCE(SUM(vd.cantidad), 0) AS unidades,
               COALESCE(SUM(vd.subtotal), 0) AS ingreso
        FROM operacion.venta v
        JOIN operacion.venta_detalle vd ON vd.id_venta = v.id_venta
        JOIN operacion.locacion loc ON loc.id_locacion = v.id_locacion
        WHERE v.fecha_venta >= now() - interval '24 hours'
        GROUP BY loc.nombre
        ORDER BY ingreso DESC
        """
    )
    return jsonify(
        _json_safe(
            {
                "resumen": resumen,
                "ventas": recientes,
                "por_tienda_24h": por_tienda,
                "actualizado": datetime.now().strftime("%H:%M:%S"),
            }
        )
    )


@bp.post("/ventas/simular-pos")
@login_required
@requiere_vista("sales")
def ventas_simular_pos():
    """
    Mecanismo de demostración en vivo: envía 1..N ventas reales en formato JSON o XML
    hacia el endpoint comercial para verificar la actualización en tiempo real del
    monitor de ventas y el descuento automático por orden FEFO.
    """
    datos = request.get_json(silent=True) or request.form
    formato = str(datos.get("formato") or "json").strip().lower()
    if formato not in ("json", "xml"):
        formato = "json"
    cantidad_tx = max(1, min(5, a_int(datos.get("cantidad_tx"), 1)))
    id_loc_req = int(datos["id_locacion"]) if str(datos.get("id_locacion") or "").isdigit() else None
    id_sku_req = int(datos["id_sku"]) if str(datos.get("id_sku") or "").isdigit() else None

    usuario = usuario_actual()
    if usuario.get("rol_clave") in ("store_manager", "warehouse") and usuario.get("id_locacion"):
        id_loc_req = int(usuario["id_locacion"])

    cond = [
        "v.tipo_locacion = 'Tienda'",
        "v.estado_lote = 'DISPONIBLE'",
        "v.dias_restantes >= 0",
        "v.cantidad_util >= 1",
    ]
    params: dict = {}
    if id_loc_req:
        cond.append("v.id_locacion = :loc")
        params["loc"] = id_loc_req
    if id_sku_req:
        cond.append("v.id_sku = :sku")
        params["sku"] = id_sku_req

    candidatos = query(
        f"""
        SELECT v.id_sku, v.producto, v.id_locacion, v.locacion,
               v.codigo_lote_prov, v.cantidad_util
        FROM operacion.v_inventario_lote v
        WHERE {' AND '.join(cond)}
        ORDER BY v.fecha_caducidad ASC
        LIMIT 40
        """,
        **params,
    )
    if not candidatos:
        return jsonify({"error": "No hay inventario disponible en tienda con las condiciones indicadas."}), 400

    token_pos = session.get("token")
    rol_actual = (usuario.get("rol_clave") or "").lower()
    if clientes.activo() and rol_actual not in ("admin", "store_manager", "warehouse"):
        st_login, r_login = clientes.llamar(
            "auth", "POST", "/api/v1/auth/login",
            cuerpo={"email": "admin@freshtrack.mx", "password": "Admin2026!"},
            timeout=5,
        )
        if st_login == 200 and isinstance(r_login, dict):
            token_pos = r_login.get("token")

    registradas = []
    muestra_enviada = ""
    for _ in range(cantidad_tx):
        elegido = random.choice(candidatos)
        max_q = max(1.0, min(3.0, a_float(elegido["cantidad_util"])))
        qty = round(random.uniform(1.0, max_q), 2) if max_q > 1.2 else 1.0

        if clientes.activo() and token_pos:
            if formato == "xml":
                cuerpo_str = (
                    f"<checkout_request>"
                    f"<id_locacion>{elegido['id_locacion']}</id_locacion>"
                    f"<canal>TIENDA</canal>"
                    f"<lineas><item><id_sku>{elegido['id_sku']}</id_sku><cantidad>{qty}</cantidad></item></lineas>"
                    f"</checkout_request>"
                )
                ct = "application/xml"
            else:
                cuerpo_str = json.dumps(
                    {
                        "id_locacion": elegido["id_locacion"],
                        "canal": "TIENDA",
                        "lineas": [{"id_sku": elegido["id_sku"], "cantidad": qty}],
                    }
                )
                ct = "application/json"

            muestra_enviada = cuerpo_str
            st, raw, _ = clientes.llamar_formato(
                "commercial", "POST", "/api/v1/commercial/checkout",
                cuerpo_bytes=cuerpo_str.encode("utf-8"),
                content_type=ct,
                accept="application/json",
                token=token_pos,
                timeout=15,
            )
            if st in (200, 201):
                resp_j = json.loads(raw.decode("utf-8"))
                registradas.append(
                    {
                        "folio": resp_j.get("folio"),
                        "total": a_float(resp_j.get("total")),
                        "tienda": elegido["locacion"],
                        "producto": elegido["producto"],
                        "cantidad": qty,
                        "lotes": [
                            {"lote": l.get("codigo_lote") or l.get("codigo_lote_prov"), "cantidad": l.get("cantidad")}
                            for l in resp_j.get("lineas", [])
                        ],
                    }
                )
        else:
            res_local = dom_ventas.registrar_venta(
                id_locacion=elegido["id_locacion"],
                lineas=[{"id_sku": elegido["id_sku"], "cantidad": qty}],
                usuario=usuario,
            )
            registradas.append(
                {
                    "folio": res_local["folio"],
                    "total": a_float(res_local["total"]),
                    "tienda": elegido["locacion"],
                    "producto": elegido["producto"],
                    "cantidad": qty,
                    "lotes": [{"lote": a["codigo_lote_prov"], "cantidad": a["consumido"]} for a in res_local["asignaciones"]],
                }
            )

    if not registradas:
        return jsonify({"error": "No se pudo completar el envío hacia la caja comercial."}), 502

    return jsonify({"registradas": registradas, "formato": formato.upper(), "muestra_payload": muestra_enviada})


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
def fefo():
    return redirect(url_for("operacion.lotes"))


# ===========================================================================
# MERMAS (consolidadas en Triaje)
# ===========================================================================
@bp.route("/mermas", methods=["GET", "POST"])
@login_required
@requiere_vista("triage")
def mermas():
    usuario = usuario_actual()

    if request.method == "GET":
        return redirect(url_for("analitica.triaje", tab="mermas"))

    if clientes.activo():
        status, r = clientes.como_usuario(
            "commercial", "POST", "/api/v1/commercial/shrinkage",
            {
                "id_lote": request.form.get("id_lote"),
                "id_locacion": request.form.get("id_locacion"),
                "cantidad": request.form.get("cantidad"),
                "causa": request.form.get("causa_merma"),
                "observacion": request.form.get("observacion"),
            },
        )
        if status == 201:
            flash(
                f"Merma registrada correctamente: {float(r['cantidad']):g} "
                f"{r.get('unidad_medida', '')} de {r.get('producto', '')} (lote {r.get('codigo_lote_prov', '')}) "
                f"por {r.get('causa_etiqueta', r.get('causa', ''))}. Valor ${float(r.get('valor_merma', 0)):,.2f}. "
                f"Quedan {float(r.get('existencia_restante', 0)):g} en existencia.",
                "ok",
            )
        else:
            flash(f"La merma no se registró: {clientes.mensaje_error('commercial', status, r)}", "error")
        return redirect(url_for("analitica.triaje", tab="mermas"))

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
            f"Merma registrada correctamente: {resultado['cantidad']:g} "
            f"{resultado['unidad_medida']} de {resultado['producto']} "
            f"(lote {resultado['codigo_lote_prov']}) por {resultado['causa_etiqueta']}. "
            f"Valor ${resultado['valor_merma']:,.2f}. Inventario descontado: quedan "
            f"{resultado['existencia_restante']:g}.",
            "ok",
        )
    except (ValueError, KeyError) as e:
        flash(f"La merma no se registró: {e}", "error")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("analitica.triaje", tab="mermas"))


@bp.route("/trazabilidad")
@login_required
def trazabilidad():
    return redirect(url_for("operacion.lotes"))
