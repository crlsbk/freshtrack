"""
Blueprint del panel, alertas, desperdicio evitado, usuarios, bitácora y ajustes.

    /panel                 tablero empresarial (todo desde PostgreSQL)
    /alertas               alertas generadas por reglas + regenerar
    /desperdicio-evitado   metodología del desperdicio evitado
    /sostenibilidad        indicadores de sostenibilidad
    /usuarios              CRUD de usuarios y roles
    /auditoria             consulta de auditoria.bitacora_eventos
    /configuracion         parámetros del sistema

Ninguna de estas pantallas lee datos simulados: todas consultan PostgreSQL.
"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import auditoria
from app.db import a_int, paginar, query, sql_error, transaccion
from app.domain import alertas as motor_alertas
from app.domain import inventario as dom_inv
from app.domain import kpis as motor_kpis
from app.domain import pronostico as motor_pron
from app.repos import catalogo as repo
from app.security import login_required, requiere_rol, requiere_vista, usuario_actual

bp = Blueprint("panel", __name__)


def _entero(nombre: str, default: int = 0) -> int:
    return a_int(request.args.get(nombre), default)


# ===========================================================================
# TABLERO
# ===========================================================================
@bp.route("/panel")
@login_required
@requiere_vista("dashboard")
def dashboard():
    return render_template(
        "panel/dashboard.html",
        active="dashboard",
        kpis=motor_kpis.panel_principal(),
        tasa=motor_kpis.tasa_merma(180),
        criticos=motor_kpis.lotes_criticos(8),
        serie=motor_kpis.serie_mensual(6),
        por_categoria=motor_kpis.merma_por_categoria(180),
        por_locacion=motor_kpis.inventario_por_locacion(),
        top_sku=motor_kpis.top_desperdicio_sku(6, 180),
        top_tienda=motor_kpis.top_desperdicio_tienda(6, 180),
        alertas=motor_alertas.resumen_alertas(),
        precision=motor_pron.precision_global(),
    )


# ===========================================================================
# ALERTAS
# ===========================================================================
@bp.route("/alertas")
@login_required
@requiere_vista("alerts")
def alertas():
    tipo = request.args.get("tipo") or None
    severidad = request.args.get("severidad") or None
    estado = request.args.get("estado") or "ABIERTA"
    return render_template(
        "panel/alertas.html",
        active="alerts",
        alertas=motor_alertas.listar_alertas(
            tipo=tipo, severidad=severidad, estado=estado
        ),
        resumen=motor_alertas.resumen_alertas(),
        tipos=motor_alertas.TIPOS,
        severidades=motor_alertas.SEVERIDADES,
        filtro_tipo=request.args.get("tipo", ""),
        filtro_severidad=request.args.get("severidad", ""),
        filtro_estado=estado,
    )


@bp.post("/alertas/regenerar")
@login_required
@requiere_vista("alerts")
def alertas_regenerar():
    try:
        resultado = motor_alertas.generar_alertas(usuario_actual())
        flash(
            f"Alertas recalculadas desde PostgreSQL: {resultado['generadas']} reglas "
            f"aplicadas, {resultado['cerradas']} cerradas por dejar de aplicar, "
            f"{resultado['abiertas']} abiertas en total.",
            "ok",
        )
    except (ValueError, SQLAlchemyError) as e:
        flash(sql_error(e) if isinstance(e, SQLAlchemyError) else str(e), "error")
    return redirect(url_for("panel.alertas"))


@bp.post("/alertas/<id_alerta>/cerrar")
@login_required
@requiere_vista("alerts")
def alertas_cerrar(id_alerta: str):
    try:
        motor_alertas.cerrar_alerta(id_alerta, usuario_actual())
        flash("Alerta marcada como atendida.", "ok")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("panel.alertas"))


# ===========================================================================
# DESPERDICIO EVITADO
# ===========================================================================
@bp.route("/desperdicio-evitado")
@login_required
@requiere_vista("savings")
def desperdicio_evitado():
    return render_template(
        "panel/desperdicio_evitado.html",
        active="savings",
        resumen=motor_kpis.resumen_desperdicio_evitado(),
        sostenibilidad=motor_kpis.kpis_sostenibilidad(180),
    )


@bp.post("/desperdicio-evitado/recalcular")
@login_required
@requiere_vista("savings")
def desperdicio_recalcular():
    try:
        resultado = motor_kpis.calcular_desperdicio_evitado()
        flash(
            f"Desperdicio evitado recalculado con las ventas reales: "
            f"{resultado['actualizados']} intervenciones actualizadas.",
            "ok",
        )
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("panel.desperdicio_evitado"))


# ===========================================================================
# SOSTENIBILIDAD
# ===========================================================================
@bp.route("/sostenibilidad")
@login_required
@requiere_vista("sustainability")
def sostenibilidad():
    return render_template(
        "panel/sostenibilidad.html",
        active="sustainability",
        indicadores=motor_kpis.kpis_sostenibilidad(180),
        tasa=motor_kpis.tasa_merma(180),
        por_categoria=motor_kpis.merma_por_categoria(180),
        serie=motor_kpis.serie_mensual(12),
    )


# ===========================================================================
# USUARIOS Y ROLES
# ===========================================================================
@bp.route("/usuarios", methods=["GET", "POST"])
@login_required
@requiere_vista("users")
def usuarios():
    if request.method == "POST":
        try:
            resultado = repo.crear_usuario(request.form, usuario_actual())
            flash(
                f"Usuario «{resultado['email']}» creado en PostgreSQL con su "
                f"contraseña cifrada con bcrypt.",
                "ok",
            )
        except ValueError as e:
            flash(str(e), "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("panel.usuarios"))

    return render_template(
        "panel/usuarios.html",
        active="users",
        usuarios=repo.listar_usuarios(texto=request.args.get("q")),
        roles=repo.roles(),
        locaciones=dom_inv.locaciones_activas(),
        filtro=request.args.get("q", ""),
    )


@bp.post("/usuarios/<id_usuario>/editar")
@login_required
@requiere_vista("users")
def usuarios_editar(id_usuario: str):
    try:
        repo.actualizar_usuario(id_usuario, request.form, usuario_actual())
        flash("Usuario actualizado.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("panel.usuarios"))


@bp.post("/usuarios/<id_usuario>/estado")
@login_required
@requiere_vista("users")
def usuarios_estado(id_usuario: str):
    activo = request.form.get("activo") == "1"
    try:
        repo.cambiar_estado_usuario(id_usuario, activo, usuario_actual())
        flash(
            f"Usuario {'activado' if activo else 'desactivado'}"
            + ("" if activo else " y sus sesiones revocadas."),
            "ok",
        )
    except ValueError as e:
        flash(str(e), "error")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("panel.usuarios"))


@bp.post("/usuarios/<id_usuario>/password")
@login_required
@requiere_vista("users")
def usuarios_password(id_usuario: str):
    try:
        repo.restablecer_password(id_usuario, request.form.get("password", ""), usuario_actual())
        flash("Contraseña restablecida y sesiones revocadas.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    except SQLAlchemyError as e:
        flash(sql_error(e), "error")
    return redirect(url_for("panel.usuarios"))


# ===========================================================================
# BITÁCORA DE AUDITORÍA
# ===========================================================================
@bp.route("/auditoria")
@login_required
@requiere_vista("audit")
def auditoria_bitacora():
    filtros = {
        "accion": request.args.get("accion") or None,
        "usuario": request.args.get("usuario") or None,
        "texto": request.args.get("q") or None,
        "desde": request.args.get("desde") or None,
        "hasta": request.args.get("hasta") or None,
    }
    condiciones = ["1 = 1"]
    params: dict = {}
    if filtros["accion"]:
        condiciones.append("b.accion = :accion")
        params["accion"] = filtros["accion"]
    if filtros["usuario"]:
        condiciones.append("b.id_usuario_app = CAST(:usuario AS uuid)")
        params["usuario"] = filtros["usuario"]
    if filtros["texto"]:
        condiciones.append(
            "(b.descripcion ILIKE :texto OR b.nombre_tabla ILIKE :texto "
            " OR b.accion ILIKE :texto)"
        )
        params["texto"] = f"%{filtros['texto']}%"
    if filtros["desde"]:
        condiciones.append("b.fecha_evento >= CAST(:desde AS date)")
        params["desde"] = filtros["desde"]
    if filtros["hasta"]:
        condiciones.append("b.fecha_evento < CAST(:hasta AS date) + 1")
        params["hasta"] = filtros["hasta"]

    where = " AND ".join(condiciones)
    total = query(
        f"SELECT COUNT(*) AS n FROM auditoria.bitacora_eventos b WHERE {where}", **params
    )[0]["n"]

    pagina = _entero("pagina", 1)
    por_pagina = 40
    eventos = query(
        f"""
        SELECT b.id_evento::text, b.fecha_evento, b.accion, b.tipo_operacion,
               b.nombre_tabla, b.id_registro, b.id_usuario_app::text,
               COALESCE(u.nombre_completo, b.usuario_email, 'Sistema') AS usuario,
               r.nombre_rol AS rol, b.descripcion, b.estado_anterior,
               b.estado_nuevo, b.ip
        FROM auditoria.bitacora_eventos b
        LEFT JOIN operacion.usuario u ON u.id_usuario = b.id_usuario_app
        LEFT JOIN operacion.rol     r ON r.id_rol     = u.id_rol
        WHERE {where}
        ORDER BY b.fecha_evento DESC
        LIMIT {por_pagina} OFFSET {(max(1, pagina) - 1) * por_pagina}
        """,
        **params,
    )

    acciones = query(
        "SELECT accion, COUNT(*) AS n FROM auditoria.bitacora_eventos "
        "GROUP BY accion ORDER BY n DESC"
    )

    return render_template(
        "panel/auditoria.html",
        active="audit",
        eventos=eventos,
        acciones=acciones,
        usuarios=repo.listar_usuarios(),
        paginacion={
            "pagina": max(1, pagina),
            "paginas": max(1, (total + por_pagina - 1) // por_pagina),
            "total": total,
            "por_pagina": por_pagina,
        },
        filtros={k: (v or "") for k, v in filtros.items()},
    )


# ===========================================================================
# CONFIGURACIÓN
# ===========================================================================
@bp.route("/configuracion", methods=["GET", "POST"])
@login_required
@requiere_vista("settings")
def configuracion():
    if request.method == "POST":
        try:
            _guardar_configuracion(request.form)
            flash("Parámetros guardados en analitica.configuracion.", "ok")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("panel.configuracion"))

    return render_template(
        "panel/configuracion.html",
        active="settings",
        parametros=query(
            "SELECT clave, valor, tipo, descripcion, actualizado "
            "FROM analitica.configuracion ORDER BY clave"
        ),
        reglas=query(
            """
            SELECT r.id_regla, r.id_sku, p.nombre AS producto, r.categoria,
                   r.dias_vigilancia, r.pct_vigilancia, r.dias_critico, r.pct_critico
            FROM operacion.regla_riesgo r
            LEFT JOIN operacion.producto p ON p.id_sku = r.id_sku
            ORDER BY r.id_regla
            """
        ),
    )


def _guardar_configuracion(form) -> None:
    """Actualiza los parámetros enviados. Deja registro en la bitácora."""
    usuario = usuario_actual()
    claves = [c for c in form.keys() if c.startswith("cfg_")]
    if not claves:
        return
    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        for campo in claves:
            clave = campo[4:]
            conn.execute(
                text(
                    """
                    UPDATE analitica.configuracion
                       SET valor = :v, actualizado = now()
                     WHERE clave = :c
                    """
                ),
                {"v": form.get(campo, ""), "c": clave},
            )
    auditoria.registrar(
        "UPDATE_USER",
        tabla="configuracion",
        id_registro=",".join(c[4:] for c in claves),
        descripcion=f"Se actualizaron {len(claves)} parámetros de configuración",
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
