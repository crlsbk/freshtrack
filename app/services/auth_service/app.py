"""
Microservicio 1: Auth & Identity Service (`svc-auth`) — FreshTrack (Flask).

Puerto: 5001
Responsabilidad:
- Autenticación segura mediante pgcrypto crypt() en PostgreSQL.
- Emisión y validación de tokens JWT (HS256) con claims RBAC.
- Revocación y verificación de ultra-baja latencia con Redis Denylist (< 0.8 ms).
- Administración de usuarios y estados de activación.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import Flask, g, request
from sqlalchemy import text

from app import auditoria
from app.config import Config
from app.db import one, query, transaccion
from app.security import autenticar, crear_token, decodificar_token, revocar_token
from app.services import cache_service
from app.services.common.auth import requiere_auth
from app.services.common.rate_limit import limite_tasa
from app.services.common.response import render_response
from app.services.common.swagger import registrar_openapi

app = Flask(__name__)
app.config.from_object(Config)


@app.get("/health")
def health():
    pg_ok = False
    try:
        res = one("SELECT 1 AS ok")
        pg_ok = bool(res and res["ok"] == 1)
    except Exception:
        pass

    redis_ok = False
    try:
        r = cache_service.get_redis_client()
        redis_ok = bool(r and r.ping())
    except Exception:
        pass

    estado = "HEALTHY" if (pg_ok and redis_ok) else "DEGRADED"
    return render_response({
        "service": "svc-auth",
        "status": estado,
        "dependencies": {"postgres": pg_ok, "redis": redis_ok},
    }, status=200 if estado == "HEALTHY" else 503, root_tag="service_health")


@app.post("/api/v1/auth/login")
@limite_tasa(limite=10, ventana_segundos=60)
def login():
    """Inicio de sesión con validación bcrypt en PostgreSQL y emisión de JWT."""
    datos = request.get_json(silent=True) or request.form
    email = (datos.get("email") or "").strip()
    password = datos.get("password") or ""

    if not email or not password:
        return render_response(
            {"error": "bad_request", "mensaje": "Correo y contraseña son obligatorios."},
            status=400,
            root_tag="auth_response",
        )

    ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")

    usuario, error = autenticar(email, password, ip=ip, user_agent=user_agent)
    if error:
        return render_response(
            {"error": "unauthorized", "mensaje": error},
            status=401,
            root_tag="auth_response",
        )

    token, jti = crear_token(usuario, ip=ip, user_agent=user_agent)
    return render_response({
        "token": token,
        "jti": jti,
        "token_type": "Bearer",
        "usuario": {
            "id_usuario": str(usuario["id_usuario"]),
            "email": usuario["email"],
            "nombre": usuario["nombre_completo"],
            "rol": usuario["rol_clave"],
            "id_locacion": usuario["id_locacion"],
        },
    }, status=200, root_tag="auth_response")


@app.post("/api/v1/auth/logout")
@requiere_auth()
def logout():
    """Revoca el token en PostgreSQL y en la denylist de Redis con TTL."""
    payload = g.usuario_actual
    jti = payload.get("jti")
    if jti:
        revocar_token(jti)
    return render_response({"status": "LOGOUT_EXITOSO", "jti": jti}, status=200, root_tag="auth_response")


@app.post("/api/v1/auth/verify")
def verificar():
    """Verificación de token de ultra-baja latencia para consumo perimetral o de otros microservicios."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.startswith("Bearer ") else request.args.get("token")
    if not token:
        return render_response({"valido": False, "motivo": "Falta token"}, status=400, root_tag="token_verification")

    payload = decodificar_token(token)
    if not payload:
        return render_response({"valido": False, "motivo": "Token inválido o expirado"}, status=401, root_tag="token_verification")

    jti = payload.get("jti")
    if jti and cache_service.esta_jwt_revocado(jti):
        return render_response({"valido": False, "motivo": "Token revocado en Redis"}, status=401, root_tag="token_verification")

    return render_response({
        "valido": True,
        "usuario": {
            "id_usuario": payload.get("sub"),
            "email": payload.get("email"),
            "rol": payload.get("rol"),
            "id_locacion": payload.get("id_locacion"),
        },
    }, status=200, root_tag="token_verification")


@app.get("/api/v1/auth/users")
@requiere_auth("admin")
def listar_usuarios():
    """Lista usuarios con su rol y locación."""
    sql = """
        SELECT u.id_usuario::text AS id_usuario, u.email, u.nombre_completo,
               r.clave AS rol, u.id_locacion, u.estado_activo, u.fecha_alta
        FROM operacion.usuario u
        JOIN operacion.rol r ON r.id_rol = u.id_rol
        ORDER BY u.nombre_completo ASC
    """
    usuarios = query(sql)
    return render_response({"total": len(usuarios), "usuarios": usuarios}, status=200, root_tag="users_list")


@app.patch("/api/v1/auth/users/<id_usuario>/status")
@requiere_auth("admin")
def cambiar_estado_usuario(id_usuario: str):
    """Activa o desactiva un usuario."""
    datos = request.get_json(silent=True) or {}
    activo = bool(datos.get("estado_activo", True))
    
    with transaccion() as conn:
        conn.execute(
            text("UPDATE operacion.usuario SET estado_activo = :act WHERE id_usuario = CAST(:uid AS uuid)"),
            {"act": activo, "uid": id_usuario},
        )
    # Si se desactiva al usuario, se cierran todas sus sesiones en Redis de inmediato
    if not activo:
        cache_service.cerrar_sesiones_usuario(id_usuario)

    return render_response({"id_usuario": id_usuario, "estado_activo": activo}, status=200, root_tag="user_status")


@app.get("/api/v1/auth/sessions/<id_usuario>")
@requiere_auth("admin")
def consultar_sesiones_usuario(id_usuario: str):
    """Consulta las sesiones activas en Redis de un usuario específico."""
    sesiones_ids = cache_service.listar_sesiones_usuario(id_usuario)
    detalles = []
    for sid in sesiones_ids:
        s_data = cache_service.obtener_sesion_redis(sid, refrescar_ttl=False)
        ttl = cache_service.obtener_ttl(f"session:{sid}")
        if s_data:
            s_data["ttl_restante_segundos"] = ttl
            detalles.append(s_data)

    return render_response(
        {"id_usuario": id_usuario, "total_activas": len(detalles), "sesiones": detalles},
        status=200,
        root_tag="user_sessions",
    )


@app.delete("/api/v1/auth/sessions/<id_usuario>")
@requiere_auth("admin")
def revocar_todas_sesiones_usuario(id_usuario: str):
    """Cierra y revoca forzosamente todas las sesiones activas en Redis de un usuario."""
    cerradas = cache_service.cerrar_sesiones_usuario(id_usuario)
    return render_response(
        {"id_usuario": id_usuario, "sesiones_cerradas": cerradas, "mensaje": "Sesiones activas revocadas en Redis"},
        status=200,
        root_tag="sessions_revoked",
    )


@app.get("/api/v1/auth/counters")
@requiere_auth("admin")
def ver_contadores_operacion():
    """Consulta los contadores operacionales en tiempo real registrados en Redis."""
    contadores = cache_service.obtener_contadores()
    return render_response(
        {"total_metricas": len(contadores), "contadores": contadores},
        status=200,
        root_tag="operational_counters",
    )


# Registro de Documentación OpenAPI / Swagger
registrar_openapi(
    app,
    titulo="Auth & Identity Service (FreshTrack)",
    descripcion="Microservicio para autenticación con PostgreSQL crypt(), gestión de RBAC y denylist Redis.",
    version="1.0.0",
    paths={
        "/health": {"get": {"summary": "Healthcheck del microservicio", "responses": {"200": {"description": "Estado saludable"}}}},
        "/api/v1/auth/login": {"post": {"summary": "Inicio de sesión y entrega de JWT", "responses": {"200": {"description": "Autenticación exitosa"}}}},
        "/api/v1/auth/logout": {"post": {"summary": "Cierre de sesión y revocación en Redis", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Revocación confirmada"}}}},
        "/api/v1/auth/verify": {"post": {"summary": "Validación de token de baja latencia", "responses": {"200": {"description": "Token válido"}}}},
        "/api/v1/auth/users": {"get": {"summary": "Listado de usuarios del sistema", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Lista de usuarios"}}}},
    },
)

if __name__ == "__main__":
    port = int(os.getenv("AUTH_SERVICE_PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=False)
