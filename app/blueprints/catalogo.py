"""
Blueprint de catálogos y abastecimiento por proveedor.

    /productos                  gestión de productos (solo proveedor y admin)
    /proveedores                consolidado de proveedores + lotes inteligentes + OC PDF (comprador y admin)
    /compras/ordenes            registro y consulta de órdenes de compra (PDF + correo)
    /tiendas                    tiendas y CEDIS
"""

from __future__ import annotations

import os
from urllib.parse import quote

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from app.config import Config
from app.db import a_int, sql_error
from app.domain import compras as dom_compras
from app.repos import catalogo as repo
from app.security import login_required, requiere_rol, requiere_vista, usuario_actual
from app.services import clientes

CAMPOS_PRODUCTO = (
    "codigo_gtin", "nombre", "categoria", "unidad_medida", "vida_util_estandar",
    "precio_costo", "precio_venta", "id_proveedor", "stock_seguridad",
    "punto_reorden", "moq_lote",
)


def _producto_desde_formulario() -> dict:
    """Solo los campos capturados en el formulario (los vacíos no se envían)."""
    cuerpo = {c: request.form[c].strip() for c in CAMPOS_PRODUCTO if request.form.get(c, "").strip()}
    if "perecedero" in request.form:
        cuerpo["perecedero"] = request.form.get("perecedero") in ("1", "on", "true")
    return cuerpo


bp = Blueprint("catalogo", __name__)


# ===========================================================================
# PRODUCTOS (responsabilidad del Proveedor y Administrador; Comprador redirige)
# ===========================================================================
@bp.route("/productos", methods=["GET", "POST"])
@login_required
def productos():
    usuario = usuario_actual()
    if usuario["rol_clave"] == "buyer":
        return redirect(url_for("catalogo.proveedores"))

    if request.method == "POST":
        if usuario["rol_clave"] not in ("admin", "supplier"):
            flash("Solo el proveedor o el administrador puede registrar productos en el catálogo.", "error")
            return redirect(url_for("catalogo.productos"))
        if clientes.activo():
            status, r = clientes.como_usuario("catalog", "POST", "/api/v1/catalog/products", _producto_desde_formulario())
            if status == 201:
                flash(f"Producto «{r['nombre']}» registrado correctamente (SKU {r['id_sku']}).", "ok")
            else:
                flash(f"El producto no se registró: {clientes.mensaje_error('catalog', status, r)}", "error")
            return redirect(url_for("catalogo.productos"))
        try:
            resultado = repo.crear_producto(request.form, usuario)
            flash(f"Producto «{resultado['nombre']}» registrado correctamente.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("catalogo.productos"))

    return render_template(
        "catalogo/productos.html",
        active="products",
        productos=repo.listar_productos(
            texto=request.args.get("q"), categoria=request.args.get("categoria")
        ),
        proveedores=repo.listar_proveedores(solo_activos=True),
        categorias=repo.categorias(),
        filtro=request.args.get("q", ""),
        filtro_categoria=request.args.get("categoria", ""),
    )


@bp.post("/productos/<int:id_sku>/editar")
@login_required
@requiere_vista("products")
def editar_producto(id_sku: int):
    if usuario_actual()["rol_clave"] not in ("admin", "supplier"):
        flash("Solo el proveedor o el administrador puede modificar productos.", "error")
        return redirect(url_for("catalogo.proveedores" if usuario_actual()["rol_clave"] == "buyer" else "catalogo.productos"))
    if clientes.activo():
        status, r = clientes.como_usuario("catalog", "PATCH", f"/api/v1/catalog/products/{id_sku}", _producto_desde_formulario())
        if status == 200:
            flash(f"Producto SKU {id_sku} actualizado correctamente.", "ok")
        else:
            flash(f"El producto no cambió: {clientes.mensaje_error('catalog', status, r)}", "error")
        return redirect(url_for("catalogo.productos"))
    try:
        repo.actualizar_producto(id_sku, request.form, usuario_actual())
        flash(f"Producto SKU {id_sku} actualizado.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("catalogo.productos"))


@bp.post("/productos/<int:id_sku>/estado")
@login_required
@requiere_vista("products")
def estado_producto(id_sku: int):
    if usuario_actual()["rol_clave"] not in ("admin", "supplier"):
        flash("Solo el proveedor o el administrador puede activar o desactivar productos.", "error")
        return redirect(url_for("catalogo.proveedores" if usuario_actual()["rol_clave"] == "buyer" else "catalogo.productos"))
    activo = request.form.get("activo") == "1"
    if clientes.activo():
        status, r = clientes.como_usuario("catalog", "PATCH", f"/api/v1/catalog/products/{id_sku}", {"activo": activo})
        if status == 200:
            flash(f"Producto SKU {id_sku} {'activado' if activo else 'desactivado'} correctamente.", "ok")
        else:
            flash(f"El producto no cambió: {clientes.mensaje_error('catalog', status, r)}", "error")
        return redirect(url_for("catalogo.productos"))
    try:
        repo.cambiar_estado_producto(id_sku, activo, usuario_actual())
        flash(
            f"Producto SKU {id_sku} {'activado' if activo else 'desactivado'}.",
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("catalogo.productos"))


# ===========================================================================
# PROVEEDORES Y COMPRAS CONSOLIDADAS POR LOTES
# ===========================================================================
@bp.route("/proveedores", methods=["GET", "POST"])
@login_required
@requiere_vista("suppliers")
def proveedores():
    usuario = usuario_actual()

    if request.method == "POST":
        if usuario["rol_clave"] != "admin":
            flash("Solo el administrador puede dar de alta proveedores.", "error")
            return redirect(url_for("catalogo.proveedores"))
        if clientes.activo():
            cuerpo = {
                "razon_social": request.form.get("razon_social"),
                "rfc": request.form.get("rfc"),
                "lead_time_dias": request.form.get("lead_time_dias") or 3,
                "moq": request.form.get("moq") or 1,
                "contacto_email": request.form.get("contacto_email"),
                "telefono": request.form.get("telefono"),
            }
            status, r = clientes.como_usuario("catalog", "POST", "/api/v1/catalog/suppliers", cuerpo)
            if status == 201:
                flash(f"Proveedor «{r['razon_social']}» registrado correctamente.", "ok")
            else:
                flash(f"No se registró el proveedor: {clientes.mensaje_error('catalog', status, r)}", "error")
            return redirect(url_for("catalogo.proveedores", tab="directorio"))
        try:
            resultado = repo.crear_proveedor(request.form, usuario)
            flash(
                f"Proveedor «{resultado['razon_social']}» registrado correctamente.",
                "ok",
            )
        except ValueError as e:
            flash(str(e), "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("catalogo.proveedores", tab="directorio"))

    filtro = request.args.get("q", "")
    proveedores_lista = repo.listar_proveedores(texto=filtro or None)
    resumen_necesidad = dom_compras.resumen_necesidad_por_proveedor()
    for pr in proveedores_lista:
        r_nec = resumen_necesidad.get(pr["id_proveedor"], {})
        pr["ordenes_pendientes"] = r_nec.get("ordenes_pendientes", 0)
        pr["urgentes"] = r_nec.get("urgentes", 0)
        pr["unidades_sugeridas"] = r_nec.get("unidades_sugeridas", 0.0)

    activos = [p for p in proveedores_lista if p["activo"]]
    id_prov_sel = a_int(request.args.get("proveedor"), 0)
    if not id_prov_sel and activos:
        con_necesidad = next((p for p in activos if p.get("ordenes_pendientes", 0) > 0), None)
        id_prov_sel = (con_necesidad or activos[0])["id_proveedor"]

    horizonte = a_int(request.args.get("horizonte"), 0) or None
    catalogo_prov = None
    if id_prov_sel:
        if clientes.activo():
            ruta_cat = f"/api/v1/planning/procurement/suppliers/{id_prov_sel}/catalog"
            if horizonte:
                ruta_cat += f"?horizonte={horizonte}"
            st_c, resp_c = clientes.como_usuario("planning", "GET", ruta_cat, timeout=20)
            if st_c == 200 and isinstance(resp_c, dict) and "productos" in resp_c:
                catalogo_prov = resp_c
        if catalogo_prov is None:
            try:
                catalogo_prov = dom_compras.catalogo_compra_proveedor(id_prov_sel, horizonte=horizonte)
            except ValueError:
                catalogo_prov = None

    ordenes_compra = []
    if clientes.activo():
        st_oc, resp_oc = clientes.como_usuario("planning", "GET", "/api/v1/planning/purchase-orders?limite=50", timeout=10)
        if st_oc == 200 and isinstance(resp_oc, dict):
            ordenes_compra = resp_oc.get("ordenes", [])
    if not ordenes_compra:
        ordenes_compra = dom_compras.listar_ordenes_compra(limite=50)

    tab_activa = request.args.get("tab") or "pedir"
    if tab_activa not in ("pedir", "ordenes", "directorio"):
        tab_activa = "pedir"
    if tab_activa == "directorio" and usuario["rol_clave"] != "admin":
        tab_activa = "pedir"

    return render_template(
        "catalogo/proveedores.html",
        active="suppliers",
        proveedores=proveedores_lista,
        proveedores_activos=activos,
        id_prov_sel=id_prov_sel,
        catalogo_prov=catalogo_prov,
        ordenes_compra=ordenes_compra,
        horizonte_sel=horizonte or (catalogo_prov["horizonte"] if catalogo_prov else 7),
        tab_activa=tab_activa,
        filtro=filtro,
    )


@bp.post("/proveedores/<int:id_proveedor>/editar")
@login_required
@requiere_vista("suppliers")
def editar_proveedor(id_proveedor: int):
    if usuario_actual()["rol_clave"] != "admin":
        flash("Solo el administrador puede editar proveedores.", "error")
        return redirect(url_for("catalogo.proveedores"))
    if clientes.activo():
        cuerpo = {
            "razon_social": request.form.get("razon_social"),
            "rfc": request.form.get("rfc"),
            "lead_time_dias": request.form.get("lead_time_dias"),
            "moq": request.form.get("moq"),
            "contacto_email": request.form.get("contacto_email"),
            "telefono": request.form.get("telefono"),
        }
        status, r = clientes.como_usuario("catalog", "PATCH", f"/api/v1/catalog/suppliers/{id_proveedor}", cuerpo)
        if status == 200:
            flash(f"Proveedor {id_proveedor} actualizado correctamente.", "ok")
        else:
            flash(f"El proveedor no cambió: {clientes.mensaje_error('catalog', status, r)}", "error")
        return redirect(url_for("catalogo.proveedores", tab="directorio"))
    try:
        repo.actualizar_proveedor(id_proveedor, request.form, usuario_actual())
        flash(f"Proveedor {id_proveedor} actualizado.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("catalogo.proveedores", tab="directorio"))


@bp.post("/proveedores/<int:id_proveedor>/estado")
@login_required
@requiere_vista("suppliers")
def estado_proveedor(id_proveedor: int):
    if usuario_actual()["rol_clave"] != "admin":
        flash("Solo el administrador puede activar o desactivar proveedores.", "error")
        return redirect(url_for("catalogo.proveedores"))
    activo = request.form.get("activo") == "1"
    if clientes.activo():
        status, r = clientes.como_usuario("catalog", "PATCH", f"/api/v1/catalog/suppliers/{id_proveedor}", {"activo": activo})
        if status == 200:
            flash(f"Proveedor {id_proveedor} {'activado' if activo else 'desactivado'} correctamente.", "ok")
        else:
            flash(f"El proveedor no cambió: {clientes.mensaje_error('catalog', status, r)}", "error")
        return redirect(url_for("catalogo.proveedores", tab="directorio"))
    try:
        repo.cambiar_estado_proveedor(id_proveedor, activo, usuario_actual())
        flash(
            f"Proveedor {id_proveedor} {'activado' if activo else 'desactivado'}.", "ok"
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("catalogo.proveedores", tab="directorio"))


# ===========================================================================
# ÓRDENES DE COMPRA POR LOTES (PDF + VISOR + ENVÍO POR CORREO)
# ===========================================================================
@bp.post("/compras/ordenes")
@login_required
@requiere_rol("admin", "buyer")
def crear_orden_compra():
    id_proveedor = a_int(request.form.get("id_proveedor"), 0)
    observaciones = (request.form.get("observaciones") or "").strip() or None

    lineas: list[dict] = []
    for campo, valor in request.form.items():
        if not campo.startswith("lotes_"):
            continue
        partes = campo.split("_")
        if len(partes) != 3:
            continue
        try:
            sku = int(partes[1])
            loc = int(partes[2])
            cant_lotes = int(float(valor or 0))
        except ValueError:
            continue
        if cant_lotes > 0:
            lineas.append(
                {
                    "id_sku": sku,
                    "id_locacion_destino": loc,
                    "cantidad_lotes": cant_lotes,
                }
            )

    if not lineas:
        flash("Selecciona al menos 1 lote en alguna tienda destino antes de emitir la orden.", "error")
        return redirect(url_for("catalogo.proveedores", proveedor=id_proveedor or None))

    if clientes.activo():
        status, r = clientes.como_usuario(
            "planning",
            "POST",
            "/api/v1/planning/purchase-orders",
            {"id_proveedor": id_proveedor, "lineas": lineas, "observaciones": observaciones},
            timeout=30,
        )
        if status == 201 and isinstance(r, dict) and r.get("id_oc"):
            flash(
                f"Orden de compra {r['folio']} emitida por {r['total_lotes']} lote(s) "
                f"y documento PDF generado.",
                "ok",
            )
            return redirect(url_for("catalogo.orden_compra_detalle", id_oc=r["id_oc"]))
        flash(f"No se registró la orden de compra: {clientes.mensaje_error('planning', status, r)}", "error")
        return redirect(url_for("catalogo.proveedores", proveedor=id_proveedor or None))

    try:
        orden = dom_compras.registrar_orden_compra(
            id_proveedor=id_proveedor,
            lineas=lineas,
            usuario=usuario_actual(),
            observaciones=observaciones,
        )
        flash(
            f"Orden de compra {orden['folio']} emitida por {orden['total_lotes']} lote(s) "
            f"y documento PDF generado.",
            "ok",
        )
        return redirect(url_for("catalogo.orden_compra_detalle", id_oc=orden["id_oc"]))
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
        return redirect(url_for("catalogo.proveedores", proveedor=id_proveedor or None))


@bp.get("/compras/ordenes/<id_oc>")
@login_required
@requiere_rol("admin", "buyer", "supplier", "warehouse", "auditor")
def orden_compra_detalle(id_oc: str):
    orden = None
    if clientes.activo():
        st, resp = clientes.como_usuario("planning", "GET", f"/api/v1/planning/purchase-orders/{id_oc}", timeout=10)
        if st == 200 and isinstance(resp, dict) and resp.get("id_oc"):
            orden = resp
    if orden is None:
        try:
            orden = dom_compras.obtener_orden_compra(id_oc)
        except Exception:
            orden = None

    if orden is None:
        flash("La orden de compra solicitada no existe.", "error")
        return redirect(url_for("catalogo.proveedores"))

    asunto_mailto = quote(f"Orden de Compra {orden['folio']} - FreshTrack")
    cuerpo_mailto = quote(
        f"Estimado equipo de {orden['proveedor']},\n\n"
        f"Compartimos la Orden de Compra {orden['folio']} por {orden['total_lotes']} lote(s) "
        f"({orden['total_unidades']:g} unidades) con importe total de ${orden['total']:,.2f}.\n"
        f"Fecha estimada de entrega: {orden.get('fecha_entrega_estimada') or '-'}.\n\nSaludos."
    )
    mailto_href = f"mailto:{orden.get('contacto_email') or ''}?subject={asunto_mailto}&body={cuerpo_mailto}"
    correo_configurado = bool(os.getenv("SMTP_HOST", Config.SMTP_HOST).strip())

    return render_template(
        "catalogo/orden_compra_detalle.html",
        active="suppliers",
        orden=orden,
        mailto_href=mailto_href,
        correo_configurado=correo_configurado,
    )


@bp.get("/compras/ordenes/<id_oc>/pdf")
@login_required
@requiere_rol("admin", "buyer", "supplier", "warehouse", "auditor")
def orden_compra_pdf(id_oc: str):
    descargar = request.args.get("descargar") == "1"
    if clientes.activo():
        ruta = f"/api/v1/planning/purchase-orders/{id_oc}/pdf" + ("?download=1" if descargar else "")
        st, pdf_bytes, hdrs = clientes.como_usuario_binario("planning", "GET", ruta, timeout=20)
        if st == 200 and pdf_bytes:
            disp = hdrs.get("content-disposition") or f'{"attachment" if descargar else "inline"}; filename="orden_compra.pdf"'
            return Response(
                pdf_bytes,
                status=200,
                mimetype="application/pdf",
                headers={"Content-Disposition": disp, "Cache-Control": "no-store"},
            )

    try:
        pdf_bytes, orden = dom_compras.obtener_pdf_orden_compra(id_oc, usuario=usuario_actual())
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("catalogo.proveedores"))

    disp = "attachment" if descargar else "inline"
    return Response(
        pdf_bytes,
        status=200,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'{disp}; filename="{orden["folio"]}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@bp.post("/compras/ordenes/<id_oc>/enviar-correo")
@login_required
@requiere_rol("admin", "buyer")
def orden_compra_enviar_correo(id_oc: str):
    correo = (request.form.get("correo") or "").strip()
    mensaje = (request.form.get("mensaje") or "").strip() or None

    if clientes.activo():
        st, r = clientes.como_usuario(
            "planning",
            "POST",
            f"/api/v1/planning/purchase-orders/{id_oc}/send-email",
            {"correo": correo, "mensaje": mensaje},
            timeout=25,
        )
        if st == 200 and isinstance(r, dict):
            if r.get("enviado_real"):
                flash(f"Orden {r['folio']} enviada con su PDF adjunto a {r['correo_envio']}.", "ok")
            else:
                flash(
                    f"Envío registrado para {r['correo_envio']}: la orden cambió a «ENVIADA». "
                    f"El servidor de correo saliente externo aún no está habilitado en este entorno; "
                    f"puedes descargar el PDF o enviarlo desde tu cliente de correo.",
                    "ok",
                )
        else:
            flash(f"No se pudo enviar el correo: {clientes.mensaje_error('planning', st, r)}", "error")
        return redirect(url_for("catalogo.orden_compra_detalle", id_oc=id_oc))

    try:
        r = dom_compras.enviar_orden_compra_correo(
            id_oc=id_oc, correo_destino=correo, usuario=usuario_actual(), mensaje_extra=mensaje
        )
        if r.get("enviado_real"):
            flash(f"Orden {r['folio']} enviada con su PDF adjunto a {r['correo_envio']}.", "ok")
        else:
            flash(
                f"Envío registrado para {r['correo_envio']}: puedes descargar el PDF o usar tu cliente de correo.",
                "ok",
            )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("catalogo.orden_compra_detalle", id_oc=id_oc))


# ===========================================================================
# TIENDAS Y CEDIS
# ===========================================================================
@bp.route("/tiendas", methods=["GET", "POST"])
@login_required
@requiere_vista("stores")
def locaciones():
    usuario = usuario_actual()

    if request.method == "POST":
        try:
            resultado = repo.crear_locacion(request.form, usuario)
            flash(f"«{resultado['nombre']}» registrada correctamente.", "ok")
        except ValueError as e:
            flash(str(e), "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("catalogo.locaciones"))

    return render_template(
        "catalogo/tiendas.html",
        active="stores",
        locaciones=repo.listar_locaciones(),
    )


@bp.post("/tiendas/<int:id_locacion>/editar")
@login_required
@requiere_vista("stores")
def editar_locacion(id_locacion: int):
    try:
        repo.actualizar_locacion(id_locacion, request.form, usuario_actual())
        flash(f"Locación {id_locacion} actualizada.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("catalogo.locaciones"))


@bp.post("/tiendas/<int:id_locacion>/estado")
@login_required
@requiere_vista("stores")
def estado_locacion(id_locacion: int):
    activo = request.form.get("activo") == "1"
    try:
        repo.cambiar_estado_locacion(id_locacion, activo, usuario_actual())
        flash(f"Locación {id_locacion} {'activada' if activo else 'desactivada'}.", "ok")
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("catalogo.locaciones"))
