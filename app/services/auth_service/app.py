"""
Microservicio 1: Auth & Identity Service (`svc-auth`) — FreshTrack (Flask).

Puerto: 5001
Responsabilidad:
- Autenticación segura mediante pgcrypto crypt() en PostgreSQL.
- Emisión y validación de tokens JWT (HS256) con claims RBAC.
- Sesiones en Redis (session:{jti}) y revocación con denylist (jwt:denylist:{jti}).
- Administración de usuarios, estados de activación y sesiones activas.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import g, request
from sqlalchemy import text

from app.db import one, query, transaccion
from app.security import autenticar, crear_token, decodificar_token, revocar_token
from app.services import cache_service
from app.services.common.auth import requiere_auth
from app.services.common.rate_limit import limite_tasa
from app.services.common.response import (
    ErrorApi,
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
    "svc-auth",
    "Auth & Identity Service (FreshTrack)",
    "Autenticación contra PostgreSQL (pgcrypto), emisión de JWT con RBAC, sesiones y denylist en Redis.",
    dependencias=("postgres", "redis"),
)

_USUARIO_EJEMPLO = {
    "id_usuario": "6b1d0c2e-2f0e-4a8e-9b3a-1f2e3d4c5b6a",
    "email": "admin@freshtrack.mx",
    "nombre": "Jorge Almanza",
    "rol": "admin",
    "id_locacion": 1,
}


def _clave_rate_login() -> str:
    """Rate limit por IP + correo: frena fuerza bruta sobre una cuenta sin bloquear a toda la oficina."""
    try:
        email = str(leer_cuerpo().get("email") or "").strip().lower()
    except ErrorApi:
        email = ""
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "?")
    return f"login:ip:{ip}:email:{email or '-'}"


@app.post("/api/v1/auth/login")
@documentar(
    "Inicio de sesión y emisión de JWT",
    cuerpo={"email": "admin@freshtrack.mx", "password": "Admin2026!"},
    raiz_xml="login_request",
    contrato_xsd="login_request",
    respuesta={"token": "eyJhbGciOiJIUzI1NiIs...", "jti": "a1b2c3", "token_type": "Bearer", "expira_en_segundos": 28800, "usuario": _USUARIO_EJEMPLO},
    raiz_respuesta="auth_response",
    errores=("400", "401", "429"),
    exito="200",
)
@limite_tasa(limite=10, ventana_segundos=60, clave_func=lambda: _clave_rate_login())
def login():
    """Valida credenciales en PostgreSQL (crypt/bcrypt), crea la sesión en Redis y entrega el JWT."""
    datos = leer_cuerpo("login_request", requerido=True)
    requerir_campos(datos, "email", "password")
    email = str(datos["email"]).strip()
    password = str(datos["password"])

    ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")

    usuario, error = autenticar(email, password, ip=ip, user_agent=user_agent)
    if error:
        cache_service.incrementar_contador("auth", "login_failed")
        return error_response(401, "credenciales_invalidas", error)

    token, jti = crear_token(usuario, ip=ip, user_agent=user_agent)
    cache_service.incrementar_contador("auth", "login_success")
    return render_response({
        "token": token,
        "jti": jti,
        "token_type": "Bearer",
        "expira_en_segundos": cache_service.obtener_ttl(f"session:{jti}"),
        "usuario": {
            "id_usuario": str(usuario["id_usuario"]),
            "email": usuario["email"],
            "nombre": usuario["nombre_completo"],
            "rol": usuario["rol_clave"],
            "id_locacion": usuario["id_locacion"],
        },
    }, status=200, root_tag="auth_response")


@app.post("/api/v1/auth/logout")
@documentar("Cierre de sesión y revocación del token", respuesta={"status": "LOGOUT_EXITOSO", "jti": "a1b2c3"}, raiz_respuesta="auth_response")
@requiere_auth()
def logout():
    """Revoca el token en PostgreSQL, lo agrega a la denylist de Redis y elimina la sesión."""
    jti = g.usuario_actual.get("jti")
    revocar_token(jti)
    return render_response({"status": "LOGOUT_EXITOSO", "jti": jti}, status=200, root_tag="auth_response")


@app.post("/api/v1/auth/verify")
@documentar(
    "Verificación de token para otros componentes",
    respuesta={"valido": True, "usuario": _USUARIO_EJEMPLO, "sesion_ttl_segundos": 28750},
    raiz_respuesta="token_verification",
    errores=("400", "401"),
    exito="200",
)
def verificar():
    """Valida firma, vigencia, sesión en Redis y denylist. Lo usan la web y otros servicios."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else request.args.get("token")
    if not token:
        return error_response(400, "token_requerido", "Envíe el token en Authorization: Bearer o ?token=")

    payload = decodificar_token(token)
    if not payload:
        return error_response(401, "token_invalido", "Token inválido, expirado o revocado.")
    jti = payload.get("jti")
    if cache_service.sesion_activa(jti) is False:
        return error_response(401, "sesion_inexistente", "La sesión no existe en Redis.")

    return render_response({
        "valido": True,
        "usuario": {
            "id_usuario": payload.get("sub"),
            "email": payload.get("email"),
            "nombre": payload.get("nombre"),
            "rol": payload.get("rol"),
            "id_locacion": payload.get("id_locacion"),
        },
        "sesion_ttl_segundos": cache_service.obtener_ttl(f"session:{jti}"),
    }, status=200, root_tag="token_verification")


@app.get("/api/v1/auth/me")
@documentar("Perfil del usuario autenticado", respuesta=_USUARIO_EJEMPLO, raiz_respuesta="usuario")
@requiere_auth()
def perfil():
    """Devuelve los datos del usuario dueño del token."""
    p = g.usuario_actual
    return render_response({
        "id_usuario": p.get("sub"),
        "email": p.get("email"),
        "nombre": p.get("nombre"),
        "rol": p.get("rol"),
        "id_locacion": p.get("id_locacion"),
    }, root_tag="usuario")


@app.get("/api/v1/auth/users")
@documentar(
    "Listado paginado de usuarios",
    consulta=[("rol", "string", "Filtra por clave de rol"), ("activo", "boolean", "true/false"), ("q", "string", "Busca en nombre o correo"),
              ("pagina", "integer", "Página (1..n)"), ("por_pagina", "integer", "Tamaño de página (máx. 100)")],
    raiz_respuesta="users_list",
)
@requiere_auth("admin")
def listar_usuarios():
    """Lista usuarios con su rol y locación, con filtros y paginación."""
    pagina, por_pagina, offset = paginacion()
    condiciones, params = [], {"lim": por_pagina, "off": offset}
    if request.args.get("rol"):
        condiciones.append("r.clave = :rol")
        params["rol"] = request.args["rol"]
    if request.args.get("activo") in ("true", "false"):
        condiciones.append("u.estado_activo = :act")
        params["act"] = request.args["activo"] == "true"
    if request.args.get("q"):
        condiciones.append("(u.nombre_completo ILIKE :q OR u.email ILIKE :q)")
        params["q"] = f"%{request.args['q']}%"
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = query(
        f"""
        SELECT u.id_usuario::text AS id_usuario, u.email, u.nombre_completo,
               r.clave AS rol, u.id_locacion, u.estado_activo, u.fecha_alta,
               COUNT(*) OVER () AS _total
        FROM operacion.usuario u
        JOIN operacion.rol r ON r.id_rol = u.id_rol
        {where}
        ORDER BY u.nombre_completo ASC
        LIMIT :lim OFFSET :off
        """,
        **params,
    )
    total = filas[0]["_total"] if filas else 0
    for f in filas:
        f.pop("_total", None)
    return render_response(
        {"paginacion": meta_paginacion(pagina, por_pagina, total), "usuarios": filas},
        status=200,
        root_tag="users_list",
    )


def _revocar_sesiones_pg(id_usuario: str) -> int:
    with transaccion() as conn:
        res = conn.execute(
            text(
                "UPDATE operacion.sesion_usuario SET revocado = true, revocado_en = now() "
                "WHERE id_usuario = CAST(:u AS uuid) AND NOT revocado AND expira_en > now()"
            ),
            {"u": id_usuario},
        )
        return res.rowcount or 0


@app.patch("/api/v1/auth/users/<id_usuario>/status")
@documentar(
    "Activa o desactiva un usuario",
    cuerpo={"estado_activo": False},
    raiz_xml="user_status_request",
    respuesta={"id_usuario": "6b1d0c2e-...", "estado_activo": False, "sesiones_revocadas": 1},
    raiz_respuesta="user_status",
    errores=("400", "404", "409"),
)
@requiere_auth("admin")
def cambiar_estado_usuario(id_usuario: str):
    """Activa/desactiva un usuario. Al desactivarlo se revocan sus sesiones en Redis y PostgreSQL."""
    id_usuario = validar_uuid(id_usuario, "id_usuario")
    datos = leer_cuerpo(requerido=True)
    if "estado_activo" not in datos:
        raise ErrorApi(400, "campos_requeridos", "Falta 'estado_activo'.", {"faltantes": ["estado_activo"]})
    valor = datos["estado_activo"]
    activo = valor if isinstance(valor, bool) else str(valor).strip().lower() in ("true", "1", "si", "sí")
    if id_usuario == g.usuario_actual.get("sub") and not activo:
        return error_response(409, "regla_negocio", "Un administrador no puede desactivarse a sí mismo.")

    with transaccion() as conn:
        res = conn.execute(
            text("UPDATE operacion.usuario SET estado_activo = :act WHERE id_usuario = CAST(:uid AS uuid)"),
            {"act": activo, "uid": id_usuario},
        )
        if res.rowcount == 0:
            return error_response(404, "no_encontrado", f"Usuario {id_usuario} no encontrado.")

    revocadas = 0
    if not activo:
        revocadas = max(cache_service.cerrar_sesiones_usuario(id_usuario), _revocar_sesiones_pg(id_usuario))

    return render_response(
        {"id_usuario": id_usuario, "estado_activo": activo, "sesiones_revocadas": revocadas},
        status=200,
        root_tag="user_status",
    )


@app.get("/api/v1/auth/sessions/<id_usuario>")
@documentar("Sesiones activas de un usuario (Redis)", raiz_respuesta="user_sessions")
@requiere_auth("admin")
def consultar_sesiones_usuario(id_usuario: str):
    """Consulta las sesiones activas en Redis de un usuario y su TTL restante."""
    id_usuario = validar_uuid(id_usuario, "id_usuario")
    if not one("SELECT 1 AS x FROM operacion.usuario WHERE id_usuario = CAST(:u AS uuid)", u=id_usuario):
        return error_response(404, "no_encontrado", f"Usuario {id_usuario} no encontrado.")
    detalles = []
    for sid in cache_service.listar_sesiones_usuario(id_usuario):
        s_data = cache_service.obtener_sesion_redis(sid, refrescar_ttl=False)
        if s_data:
            s_data["ttl_restante_segundos"] = cache_service.obtener_ttl(f"session:{sid}")
            detalles.append(s_data)

    return render_response(
        {"id_usuario": id_usuario, "total_activas": len(detalles), "sesiones": detalles},
        status=200,
        root_tag="user_sessions",
    )


@app.delete("/api/v1/auth/sessions/<id_usuario>")
@documentar("Cierra todas las sesiones de un usuario", raiz_respuesta="sessions_revoked")
@requiere_auth("admin")
def revocar_todas_sesiones_usuario(id_usuario: str):
    """Revoca forzosamente todas las sesiones del usuario (denylist en Redis + PostgreSQL)."""
    id_usuario = validar_uuid(id_usuario, "id_usuario")
    cerradas_redis = cache_service.cerrar_sesiones_usuario(id_usuario)
    cerradas_pg = _revocar_sesiones_pg(id_usuario)
    return render_response(
        {"id_usuario": id_usuario, "sesiones_cerradas": max(cerradas_redis, cerradas_pg), "mensaje": "Sesiones revocadas"},
        status=200,
        root_tag="sessions_revoked",
    )


@app.get("/api/v1/auth/counters")
@documentar("Contadores operativos en Redis", consulta=[("servicio", "string", "Filtra por servicio, p. ej. auth")], raiz_respuesta="operational_counters")
@requiere_auth("admin")
def ver_contadores_operacion():
    """Consulta los contadores de operaciones (HINCRBY por servicio y día) registrados en Redis."""
    contadores = cache_service.obtener_contadores(request.args.get("servicio"))
    return render_response(
        {"total_metricas": len(contadores), "contadores": contadores},
        status=200,
        root_tag="operational_counters",
    )


if __name__ == "__main__":
    ejecutar(app, "AUTH_SERVICE_PORT", 5001)
