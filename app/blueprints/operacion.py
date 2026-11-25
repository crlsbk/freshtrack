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
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import (
    Blueprint,
    Response,
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
from app.domain.cache_web import con_cache_web
from app.domain import compras as dom_compras
from app.domain import etiquetas_qr
from app.domain import inventario as dom_inv
from app.domain import mermas as dom_mermas
from app.domain import por_recibir as dom_por_recibir
from app.domain import recepcion as dom_recepcion
from app.domain import ventas as dom_ventas
from app.security import (
    login_required,
    proveedor_de_sesion,
    recurso_de_otro_proveedor,
    requiere_vista,
    usuario_actual,
)
from app.services import clientes

bp = Blueprint("operacion", __name__)

# Tamaño de página de los listados operativos (lotes, inventario, ventas, mermas).
POR_PAGINA = 50


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
        if usuario["rol_clave"] not in ("admin", "warehouse"):
            flash("Solo el personal de almacén o el administrador puede registrar recepciones de mercancía.", "error")
            return redirect(url_for("operacion.lotes"))
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

    filtros_lotes = {
        "texto": request.args.get("q") or None,
        "clasificacion": request.args.get("riesgo") or None,
        "id_locacion": int(request.args["locacion"]) if request.args.get("locacion") else None,
    }
    total = dom_inv.contar_lotes(**filtros_lotes)
    paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    pagina = min(max(1, a_int(request.args.get("pagina"), 1)), paginas)

    return render_template(
        "operacion/lotes.html",
        active="batches",
        lotes=dom_inv.listar_lotes(**filtros_lotes, limite=POR_PAGINA, offset=(pagina - 1) * POR_PAGINA),
        paginacion={"pagina": pagina, "paginas": paginas, "total": total, "por_pagina": POR_PAGINA},
        filtros_pag={k: v for k, v in (
            ("q", request.args.get("q")), ("riesgo", request.args.get("riesgo")),
            ("locacion", request.args.get("locacion")),
        ) if v},
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
    if usuario_actual()["rol_clave"] not in ("admin", "warehouse", "store_manager", "planner"):
        flash("Tu rol es de solo consulta sobre lotes y prioridad FEFO.", "error")
        return redirect(url_for("operacion.lotes"))
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
    if usuario_actual()["rol_clave"] not in ("admin", "warehouse", "store_manager", "planner"):
        flash("Tu rol es de solo consulta sobre lotes y prioridad FEFO.", "error")
        return redirect(url_for("operacion.lotes"))
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
    res = dom_inv.bloquear_lotes_vencidos(usuario=usuario_actual(), forzar=True)
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
    res = dom_inv.inventario_agrupado_paginado(
        id_locacion=id_locacion, texto=texto, pagina=a_int(request.args.get("pagina"), 1), por_pagina=25
    )
    return render_template(
        "operacion/inventario.html",
        active="inventory",
        grupos=res["grupos"],
        paginacion=res["paginacion"],
        filtros_pag={k: v for k, v in (("q", texto), ("locacion", id_locacion)) if v},
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
    por_tienda = con_cache_web("web:ventas:por_tienda_24h", 10, lambda: query(
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
    ))
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


# ===========================================================================
# DESPACHOS DE PROVEEDOR (ASN + HOJA QR) Y RECEPCIÓN POR ESCANEO
# ===========================================================================
def _oc_de_otro_proveedor(id_oc: str) -> bool:
    if not id_oc or proveedor_de_sesion() is None:
        return False
    try:
        prov = query("SELECT id_proveedor FROM operacion.orden_compra WHERE id_oc = CAST(:i AS uuid)", i=id_oc)
    except Exception:
        return True
    return recurso_de_otro_proveedor(prov[0]["id_proveedor"] if prov else None)


def _asn_de_otro_proveedor(folio_asn: str) -> bool:
    if proveedor_de_sesion() is None:
        return False
    from app.services.doc_store import get_mongo_db

    db = get_mongo_db()
    doc = db.avisos_asn.find_one({"folio_asn": folio_asn}, {"id_proveedor": 1}) if db is not None else None
    return recurso_de_otro_proveedor(doc.get("id_proveedor") if doc else None)


@bp.get("/por-recibir")
@login_required
@requiere_vista("incoming")
def por_recibir():
    """Mercancía en camino a la tienda: fecha estimada, embarque y avance de recepción."""
    usuario = usuario_actual()
    propia = usuario.get("rol_clave") in ("store_manager", "warehouse") and usuario.get("id_locacion")
    if propia:
        id_loc = int(usuario["id_locacion"])
        tiendas = []
    else:
        tienda = request.args.get("tienda", "")
        id_loc = int(tienda) if tienda.isdigit() else None
        tiendas = query(
            "SELECT id_locacion, nombre FROM operacion.locacion "
            "WHERE activo = true ORDER BY tipo_locacion DESC, nombre"
        )
    try:
        datos = dom_por_recibir.listar_por_recibir(id_locacion=id_loc)
    except SQLAlchemyError as exc:
        flash(f"No se pudo consultar la mercancía por recibir: {sql_error(exc)}", "error")
        datos = {"envios": [], "conteo": {}, "proxima_llegada": None, "hoy": date.today()}
    return render_template(
        "operacion/por_recibir.html",
        datos=datos,
        tiendas=tiendas,
        id_loc=id_loc,
        tienda_propia=bool(propia),
        hoy=datos["hoy"],
    )


@bp.route("/despachos", methods=["GET", "POST"])
@login_required
@requiere_vista("dispatches")
def despachos():
    usuario = usuario_actual()

    if request.method == "POST":
        if usuario["rol_clave"] not in ("admin", "supplier"):
            flash("Solo el proveedor o el administrador puede generar despachos y etiquetas QR.", "error")
            return redirect(url_for("operacion.despachos"))

        id_oc = (request.form.get("id_oc") or "").strip()
        if _oc_de_otro_proveedor(id_oc):
            flash("Solo puedes despachar órdenes de compra dirigidas a tu proveedor.", "error")
            return redirect(url_for("operacion.despachos"))
        transporte = {
            "chofer": (request.form.get("chofer") or "").strip() or None,
            "placas": (request.form.get("placas") or "").strip() or None,
            "temperatura_salida_c": request.form.get("temperatura_salida_c") or None,
        }
        indices = sorted(
            {
                int(k.split("_", 1)[1])
                for k in request.form
                if k.startswith("sku_") and k.split("_", 1)[1].isdigit()
            }
        )
        partidas: list[dict] = []
        for idx in indices:
            cant = a_float(request.form.get(f"cant_{idx}"))
            if cant <= 0:
                continue
            partidas.append(
                {
                    "id_detalle_oc": (request.form.get(f"det_{idx}") or "").strip() or None,
                    "id_sku": a_int(request.form.get(f"sku_{idx}"), 0),
                    "id_locacion_destino": a_int(request.form.get(f"loc_{idx}"), 0),
                    "cantidad_declarada": cant,
                    "lote_proveedor": (request.form.get(f"lote_{idx}") or "").strip(),
                    "fecha_produccion": (request.form.get(f"fprod_{idx}") or "").strip() or None,
                    "fecha_caducidad": (request.form.get(f"fcad_{idx}") or "").strip(),
                    "rango_temperatura_controlada": (request.form.get(f"temp_{idx}") or "2C a 6C").strip(),
                    "codigo_rfid_epc": (request.form.get(f"rfid_{idx}") or "").strip() or None,
                }
            )

        if not id_oc or not partidas:
            flash("Captura al menos una partida con cantidad mayor a cero para generar el despacho.", "error")
            return redirect(url_for("operacion.despachos", tab="despachar"))

        if clientes.activo():
            st, r = clientes.como_usuario(
                "asn",
                "POST",
                "/api/v1/asn/from-purchase-order",
                {"id_oc": id_oc, "partidas": partidas, "transporte": transporte},
                timeout=25,
            )
            if st == 201 and isinstance(r, dict) and r.get("folio_asn"):
                flash(
                    f"Despacho {r['folio_asn']} registrado con {len(r.get('etiquetas') or [])} etiqueta(s) QR listas para imprimir.",
                    "ok",
                )
                return redirect(url_for("operacion.despachos", folio=r["folio_asn"], tab="despachar"))
            flash(f"No se pudo generar el despacho: {clientes.mensaje_error('asn', st, r)}", "error")
            return redirect(url_for("operacion.despachos", id_oc=id_oc, tab="despachar"))

        try:
            r = dom_recepcion.crear_despacho_desde_oc(
                id_oc=id_oc,
                partidas=partidas,
                usuario=usuario,
                transporte=transporte,
            )
            flash(
                f"Despacho {r['folio_asn']} registrado con {len(r.get('etiquetas') or [])} etiqueta(s) QR listas para imprimir.",
                "ok",
            )
            return redirect(url_for("operacion.despachos", folio=r["folio_asn"], tab="despachar"))
        except (ValueError, SQLAlchemyError) as e:
            flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
            return redirect(url_for("operacion.despachos", id_oc=id_oc, tab="despachar"))

    # Un proveedor solo ve SUS órdenes por despachar y SUS avisos ASN
    # (0 = supplier sin proveedor asignado: no ve ninguno).
    prov_sesion = proveedor_de_sesion()
    ordenes_pendientes = (
        dom_recepcion.listar_ordenes_para_despacho()
        if prov_sesion is None
        else (dom_recepcion.listar_ordenes_para_despacho(id_proveedor=prov_sesion) if prov_sesion else [])
    )
    id_oc_sel = (request.args.get("id_oc") or "").strip() or (
        ordenes_pendientes[0]["id_oc"] if ordenes_pendientes else ""
    )
    if id_oc_sel and _oc_de_otro_proveedor(id_oc_sel):
        id_oc_sel = ""
    oc_sel = dom_compras.obtener_orden_compra(id_oc_sel) if id_oc_sel else None
    despachos_lista = dom_recepcion.listar_despachos_recientes(limite=40, id_proveedor=prov_sesion)

    folio_sel = (request.args.get("folio") or "").strip()
    asn_sel = next((d for d in despachos_lista if d.get("folio_asn") == folio_sel), None) if folio_sel else None
    if asn_sel:
        asn_sel = {
            **asn_sel,
            "etiquetas_svg": [
                {
                    **e,
                    "svg_qr": etiquetas_qr.generar_svg_qr(
                        e.get("qr_payload")
                        or etiquetas_qr.construir_payload_qr(
                            e["codigo_etiqueta"],
                            asn_sel.get("folio_oc"),
                            int(e["id_locacion_destino"]),
                            int(e["id_sku"]),
                        ),
                        escala=3,
                    ),
                }
                for e in (asn_sel.get("etiquetas") or [])
            ],
        }

    tab_defecto = "despachar" if usuario["rol_clave"] in ("admin", "supplier") else "historial"
    tab_activa = request.args.get("tab") or tab_defecto
    if tab_activa not in ("despachar", "historial"):
        tab_activa = tab_defecto
    if tab_activa == "despachar" and usuario["rol_clave"] not in ("admin", "supplier"):
        tab_activa = "historial"

    return render_template(
        "operacion/despachos.html",
        active="dispatches",
        ordenes_pendientes=ordenes_pendientes,
        oc_sel=oc_sel,
        asn_sel=asn_sel,
        despachos=despachos_lista,
        tab_activa=tab_activa,
        hoy=date.today().isoformat(),
        cad_defecto=(date.today() + timedelta(days=7)).isoformat(),
    )


@bp.get("/despachos/<folio_asn>/pdf")
@login_required
@requiere_vista("dispatches")
def despacho_pdf(folio_asn: str):
    if _asn_de_otro_proveedor(folio_asn):
        flash("El despacho solicitado no existe.", "error")
        return redirect(url_for("operacion.despachos"))
    descargar = request.args.get("descargar") == "1"
    if clientes.activo():
        ruta = f"/api/v1/asn/{folio_asn}/labels-pdf" + ("?download=1" if descargar else "")
        st, pdf_bytes, hdrs = clientes.como_usuario_binario("asn", "GET", ruta, timeout=20)
        if st == 200 and pdf_bytes:
            disp = hdrs.get("content-disposition") or f'{"attachment" if descargar else "inline"}; filename="{folio_asn}_etiquetas.pdf"'
            return Response(pdf_bytes, status=200, mimetype="application/pdf", headers={"Content-Disposition": disp, "Cache-Control": "no-store"})

    try:
        pdf_bytes, _ = dom_recepcion.obtener_pdf_hoja_asn(folio_asn, usuario=usuario_actual())
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("operacion.despachos"))

    disp = "attachment" if descargar else "inline"
    return Response(
        pdf_bytes,
        status=200,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{folio_asn}_etiquetas.pdf"', "Cache-Control": "no-store"},
    )



@bp.post("/despachos/<folio_asn>/enviar-correo")
@login_required
@requiere_vista("dispatches")
def despacho_enviar_correo(folio_asn: str):
    if _asn_de_otro_proveedor(folio_asn):
        flash("El despacho solicitado no existe.", "error")
        return redirect(url_for("operacion.despachos"))
    """Envía la Hoja QR (PDF) por correo: vía svc-asn si está activo; si no, con el dominio local."""
    correo = (request.form.get("correo") or "").strip()
    mensaje = (request.form.get("mensaje") or "").strip()
    volver = url_for("operacion.despachos", folio=folio_asn)

    if clientes.activo():
        st, r = clientes.como_usuario(
            "asn", "POST", f"/api/v1/asn/{folio_asn}/send-email",
            {"correo": correo, "mensaje": mensaje}, timeout=30,
        )
        if st == 200 and isinstance(r, dict):
            _flash_envio_hoja(r)
        else:
            flash(f"No se pudo enviar el correo: {clientes.mensaje_error('asn', st, r)}", "error")
        return redirect(volver)

    try:
        _flash_envio_hoja(dom_recepcion.enviar_hoja_asn_correo(folio_asn, correo, usuario_actual(), mensaje))
    except ValueError as e:
        flash(str(e), "error")
    return redirect(volver)


def _flash_envio_hoja(r: dict) -> None:
    if r.get("enviado_real") in (True, "true"):
        flash(f"Hoja QR {r.get('folio_asn')} enviada con su PDF adjunto a {r.get('correo_envio')}.", "ok")
    else:
        flash(
            f"Envío registrado para {r.get('correo_envio')}, pero no hay servidor de correo configurado "
            "(SMTP_HOST vacío). Descarga el PDF o configura el SMTP.",
            "ok",
        )


@bp.get("/lotes/qr-consultar")
@login_required
@requiere_vista("batches")
def lotes_qr_consultar():
    usuario = usuario_actual()
    if usuario["rol_clave"] not in ("admin", "warehouse", "store_manager"):
        return jsonify({"error": "No tienes permisos para validar etiquetas de recepción."}), 403

    codigo = (request.args.get("codigo") or "").strip()
    id_loc = a_int(request.args.get("id_locacion"), 0) or None
    if clientes.activo():
        from urllib.parse import urlencode
        qs = urlencode({k: v for k, v in {"codigo": codigo, "id_locacion": id_loc}.items() if v is not None})
        st, r = clientes.como_usuario("asn", "GET", f"/api/v1/asn/labels?{qs}", timeout=8)
        if st:
            if st == 200:
                return jsonify(r), 200
            return jsonify({"error": clientes.mensaje_error("asn", st, r)}), st

    try:
        info = dom_recepcion.consultar_etiqueta_para_recepcion(codigo, id_locacion_usuario=id_loc)
        return jsonify(info), 200
    except dom_recepcion.ErrorRecepcion as err:
        return jsonify({"error": str(err)}), err.http_status


@bp.post("/lotes/recibir-qr")
@login_required
@requiere_vista("batches")
def lotes_recibir_qr():
    usuario = usuario_actual()
    if usuario["rol_clave"] not in ("admin", "warehouse"):
        flash("Solo el personal de almacén o el administrador puede confirmar recepciones por QR.", "error")
        return redirect(url_for("operacion.lotes"))

    codigo = (request.form.get("codigo_qr_crudo") or "").strip()
    id_loc = a_int(request.form.get("id_locacion_recepcion"), 0)
    cant = a_float(request.form.get("cantidad_recibida"))
    temp_raw = (request.form.get("temperatura_registrada_c") or "").strip()
    temp = float(temp_raw) if temp_raw else None
    idem = (request.form.get("idempotency_key") or "").strip() or None
    payload = {
        "codigo_qr_crudo": codigo,
        "id_locacion_recepcion": id_loc,
        "cantidad_recibida": cant,
        "fecha_caducidad_verificada": (request.form.get("fecha_caducidad_verificada") or "").strip() or None,
        "temperatura_registrada_c": temp,
        "resultado_inspeccion": request.form.get("resultado_inspeccion") or "CONFORME",
        "accion_calidad": request.form.get("accion_calidad") or "ACEPTAR_DISPONIBLE",
        "medio_lectura": "QR",
        "observaciones": (request.form.get("observaciones") or "").strip() or None,
        "idempotency_key": idem,
    }

    if clientes.activo():
        st, r = clientes.como_usuario("inventory", "POST", "/api/v1/inventory/receive-scan", payload, timeout=15)
        if st in (200, 201) and isinstance(r, dict):
            flash(
                f"Recepción QR confirmada ({r.get('codigo_etiqueta', '')}): "
                f"{r.get('producto', '')} · {float(r.get('cantidad_recibida', 0)):g} "
                f"{r.get('unidad_medida', '')} ({r.get('accion_calidad', '')}).",
                "ok",
            )
        else:
            flash(f"No se registró la recepción QR: {clientes.mensaje_error('inventory', st, r)}", "error")
        return redirect(url_for("operacion.lotes"))

    try:
        r = dom_recepcion.procesar_recepcion_escaneo(
            codigo_o_qr=codigo,
            id_locacion_recepcion=id_loc,
            cantidad_recibida=cant,
            usuario=usuario,
            fecha_caducidad_verificada=payload["fecha_caducidad_verificada"],
            temperatura_registrada_c=temp,
            resultado_inspeccion=payload["resultado_inspeccion"],
            accion_calidad=payload["accion_calidad"],
            medio_lectura="QR",
            observaciones=payload["observaciones"],
            idempotency_key=idem,
        )
        flash(
            f"Recepción QR confirmada ({r['codigo_etiqueta']}): {r['producto']} · "
            f"{r['cantidad_recibida']:g} {r['unidad_medida']} ({r['accion_calidad']}).",
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("operacion.lotes"))
