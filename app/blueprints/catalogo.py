"""
Blueprint de catálogos.

CRUD completo (crear, consultar, editar, activar/desactivar) de:

    /productos    /proveedores    /tiendas

Todo se escribe en PostgreSQL. Ninguna pantalla lee datos simulados.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import sql_error
from app.repos import catalogo as repo
from app.security import login_required, requiere_vista
from app.security import usuario_actual
from sqlalchemy.exc import SQLAlchemyError

bp = Blueprint("catalogo", __name__)


# ===========================================================================
# PRODUCTOS
# ===========================================================================
@bp.route("/productos", methods=["GET", "POST"])
@login_required
@requiere_vista("products")
def productos():
    usuario = usuario_actual()

    if request.method == "POST":
        try:
            resultado = repo.crear_producto(request.form, usuario)
            flash(f"Producto «{resultado['nombre']}» registrado en PostgreSQL.", "ok")
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
    activo = request.form.get("activo") == "1"
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
# PROVEEDORES
# ===========================================================================
@bp.route("/proveedores", methods=["GET", "POST"])
@login_required
@requiere_vista("suppliers")
def proveedores():
    usuario = usuario_actual()

    if request.method == "POST":
        try:
            resultado = repo.crear_proveedor(request.form, usuario)
            flash(
                f"Proveedor «{resultado['razon_social']}» registrado en PostgreSQL.",
                "ok",
            )
        except ValueError as e:
            flash(str(e), "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("catalogo.proveedores"))

    return render_template(
        "catalogo/proveedores.html",
        active="suppliers",
        proveedores=repo.listar_proveedores(texto=request.args.get("q")),
        filtro=request.args.get("q", ""),
    )


@bp.post("/proveedores/<int:id_proveedor>/editar")
@login_required
@requiere_vista("suppliers")
def editar_proveedor(id_proveedor: int):
    try:
        repo.actualizar_proveedor(id_proveedor, request.form, usuario_actual())
        flash(f"Proveedor {id_proveedor} actualizado.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("catalogo.proveedores"))


@bp.post("/proveedores/<int:id_proveedor>/estado")
@login_required
@requiere_vista("suppliers")
def estado_proveedor(id_proveedor: int):
    activo = request.form.get("activo") == "1"
    try:
        repo.cambiar_estado_proveedor(id_proveedor, activo, usuario_actual())
        flash(
            f"Proveedor {id_proveedor} {'activado' if activo else 'desactivado'}.", "ok"
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("catalogo.proveedores"))


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
            flash(f"«{resultado['nombre']}» registrada en PostgreSQL.", "ok")
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
