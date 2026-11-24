"""
Blueprint del panel, alertas, desperdicio evitado, usuarios, bitácora y ajustes.

    /panel                 tablero empresarial (todo desde PostgreSQL)
    /alertas               alertas generadas por reglas + regenerar
    /notificaciones        centro de notificaciones del usuario (campana)
    /desperdicio-evitado   metodología del desperdicio evitado
    /sostenibilidad        indicadores de sostenibilidad
    /usuarios              CRUD de usuarios y roles
    /auditoria             consulta de auditoria.bitacora_eventos
    /configuracion         parámetros del sistema

Ninguna de estas pantallas lee datos simulados: todas consultan PostgreSQL.
"""

from __future__ import annotations

import hashlib
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import auditoria
from app.db import a_int, limpiar_cache_config, paginar, query, sql_error, transaccion
from app.domain import alertas as motor_alertas
from app.domain import inventario as dom_inv
from app.domain import kpis as motor_kpis
from app.domain import pronostico as motor_pron
from app.repos import catalogo as repo
from app.services import clientes, doc_store
from app.security import login_required, requiere_rol, requiere_vista, usuario_actual

_RE_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

bp = Blueprint("panel", __name__)


def _entero(nombre: str, default: int = 0) -> int:
    return a_int(request.args.get(nombre), default)


# ===========================================================================
# TABLERO
# ===========================================================================
@bp.route("/mapa")
@login_required
@requiere_vista("map")
def mapa():
    """Mapa de tiendas y CEDIS: al pulsar un punto se ven sus indicadores."""
    ventana_param = request.args.get("ventana", "30")
    dias = int(ventana_param) if ventana_param in ("7", "30", "90", "180") else 30
    return render_template(
        "panel/mapa.html",
        active="map",
        ventana=dias,
        locaciones=motor_kpis.metricas_por_locacion(dias),
    )


@bp.route("/panel")
@login_required
@requiere_vista("dashboard")
def dashboard():
    ventana_param = request.args.get("ventana", "30")
    if ventana_param in ("todo", "all", "historico", "none") or not ventana_param.isdigit():
        dias_ventana = None
    else:
        dias_ventana = int(ventana_param)

    periodo = motor_kpis.metricas_periodo(dias_ventana)
    dias_tasa = dias_ventana if dias_ventana is not None else 180

    return render_template(
        "panel/dashboard.html",
        active="dashboard",
        kpis=motor_kpis.panel_principal(),
        periodo=periodo,
        ventana=dias_ventana,
        tasa=periodo["tasa"],
        criticos=motor_kpis.lotes_criticos(8),
        serie=motor_kpis.serie_mensual(6),
        por_categoria=motor_kpis.merma_por_categoria(dias_tasa),
        por_locacion=motor_kpis.inventario_por_locacion(),
        top_sku=motor_kpis.top_desperdicio_sku(6, dias_tasa),
        top_tienda=motor_kpis.top_desperdicio_tienda(6, dias_tasa),
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


# ===========================================================================
# NOTIFICACIONES (app/domain/notificaciones.py)
# ===========================================================================
@bp.route("/notificaciones")
@login_required
def notificaciones():
    from app.domain import notificaciones as dom_notif

    datos = dom_notif.listar(usuario_actual())
    return render_template(
        "panel/notificaciones.html",
        active="notifications",
        notificaciones=datos["items"],
        no_leidas=datos["no_leidas"],
        fuentes=datos["fuentes"],
    )


@bp.post("/notificaciones/leer")
@login_required
def notificaciones_leer():
    """Marca una (campo «id») o todas (sin «id») como leídas."""
    from app.domain import notificaciones as dom_notif

    usuario = usuario_actual()
    id_notif = (request.form.get("id") or "").strip()
    ok = dom_notif.marcar_leidas(usuario, [id_notif]) if id_notif else dom_notif.marcar_todas(usuario)
    if not ok:
        flash("No se pudo guardar el estado de lectura en este momento. Intenta más tarde.", "error")
    return redirect(url_for("panel.notificaciones"))


@bp.post("/alertas/regenerar")
@login_required
@requiere_vista("alerts")
def alertas_regenerar():
    try:
        resultado = motor_alertas.generar_alertas(usuario_actual())
        flash(
            f"Alertas actualizadas: {resultado['generadas']} reglas "
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
    # Consulta complementaria al microservicio svc-alerts (5007)
    esg_api = None
    indicadores_6 = None
    if clientes.activo():
        st, resp = clientes.como_usuario("alerts", "GET", "/api/v1/alerts/esg/carbon-avoided", timeout=3)
        if st == 200 and isinstance(resp, dict):
            esg_api = resp
            indicadores_6 = resp.get("indicadores_6")
    if indicadores_6 is None:
        indicadores_6 = motor_kpis.indicadores_desperdicio_completo(30)

    return render_template(
        "panel/desperdicio_evitado.html",
        active="savings",
        resumen=motor_kpis.resumen_desperdicio_evitado(),
        sostenibilidad=motor_kpis.kpis_sostenibilidad(180),
        indicadores_6=indicadores_6,
        esg_api=esg_api,
        tasa=motor_kpis.tasa_merma(180),
        por_categoria=motor_kpis.merma_por_categoria(180),
        serie=motor_kpis.serie_mensual(12),
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
def sostenibilidad():
    return redirect(url_for("panel.desperdicio_evitado"))


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
                f"Usuario «{resultado['email']}» creado correctamente.",
                "ok",
            )
        except ValueError as e:
            flash(str(e), "error")
        except SQLAlchemyError as e:
            flash(sql_error(e), "error")
        return redirect(url_for("panel.usuarios"))

    texto = request.args.get("q") or None
    por_pagina = 50  # cada fila lleva su modal de edición con roles y locaciones
    total = repo.contar_usuarios(texto)
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = min(max(1, _entero("pagina", 1)), paginas)
    return render_template(
        "panel/usuarios.html",
        active="users",
        usuarios=repo.listar_usuarios(texto=texto, limite=por_pagina, offset=(pagina - 1) * por_pagina),
        paginacion={"pagina": pagina, "paginas": paginas, "total": total, "por_pagina": por_pagina},
        filtros_pag={"q": texto} if texto else {},
        roles=repo.roles(),
        locaciones=dom_inv.locaciones_activas(),
        proveedores=repo.listar_proveedores(solo_activos=True),
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
        # Antes era un <select> con los primeros 150 de ~2000 usuarios (filtro
        # incompleto y DOM pesado). Ahora se escribe el correo (o parte) y se
        # busca con el índice trigram de usuario_email; un UUID sigue sirviendo.
        if _RE_UUID.match(filtros["usuario"]):
            condiciones.append("b.id_usuario_app = CAST(:usuario AS uuid)")
            params["usuario"] = filtros["usuario"]
        else:
            condiciones.append("b.usuario_email ILIKE :usuario")
            params["usuario"] = f"%{filtros['usuario']}%"
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
    if where == "1 = 1":
        est = query(
            "SELECT GREATEST(0, reltuples::bigint) AS n FROM pg_class WHERE oid = 'auditoria.bitacora_eventos'::regclass"
        )
        total = int(est[0]["n"]) if est and int(est[0]["n"]) > 0 else query(
            "SELECT COUNT(*) AS n FROM auditoria.bitacora_eventos"
        )[0]["n"]
    else:
        clave_total = "web:auditoria:total:" + hashlib.sha1(
            repr(sorted(filtros.items())).encode("utf-8")
        ).hexdigest()
        total = int(motor_kpis._con_cache_web(
            clave_total,
            60,
            lambda: query(
                f"SELECT COUNT(*) AS n FROM auditoria.bitacora_eventos b WHERE {where}", **params
            )[0]["n"],
        ))

    por_pagina = 40
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = min(max(1, _entero("pagina", 1)), paginas)
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

    acciones = motor_kpis._con_cache_web(
        "web:auditoria:acciones",
        60,
        lambda: query(
            "SELECT accion, COUNT(*) AS n FROM auditoria.bitacora_eventos "
            "GROUP BY accion ORDER BY n DESC"
        ),
    )

    return render_template(
        "panel/auditoria.html",
        active="audit",
        eventos=eventos,
        acciones=acciones,
        paginacion={
            "pagina": pagina,
            "paginas": paginas,
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
            flash("Parámetros de configuración guardados correctamente.", "ok")
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
    limpiar_cache_config()
    auditoria.registrar(
        "UPDATE_USER",
        tabla="configuracion",
        id_registro=",".join(c[4:] for c in claves),
        descripcion=f"Se actualizaron {len(claves)} parámetros de configuración",
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


@bp.route("/mongo")
@login_required
def mongo_explorer():
    return redirect(url_for("panel.dashboard"))


@bp.route("/microservicios")
@login_required
def microservicios():
    return redirect(url_for("panel.dashboard"))


@bp.route("/svc/<clave>/<path:ruta>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@login_required
def gateway_microservicios(clave: str, ruta: str):
    """
    Gateway de la web hacia los microservicios: el navegador llama a /svc/<servicio>/api/v1/...
    y la web reenvía la petición con el JWT de la sesión. Así el frontend consume los
    servicios por HTTP sin exponer el token en JavaScript ni depender de CORS.
    """
    from flask import Response, session

    from app.services import clientes

    if clave not in {s["clave"] for s in clientes.SERVICIOS}:
        return {"error": "no_encontrado", "mensaje": f"No existe el servicio '{clave}'."}, 404
    status, cuerpo, tipo, cid = clientes.reenviar(
        clave, request.method, "/" + ruta, request.query_string.decode(),
        request.get_data() or None, request.headers.get("Content-Type"),
        request.headers.get("Accept"), session.get("token"),
    )
    resp = Response(cuerpo, status=status, content_type=tipo)
    resp.headers["X-Servicio"] = clientes.nombre(clave)
    if cid:
        resp.headers["X-Correlation-Id"] = cid
    return resp
