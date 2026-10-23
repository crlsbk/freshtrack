"""
Blueprint de autenticación.

    GET  /login          formulario
    POST /login          valida contra PostgreSQL y abre sesión web + JWT
    GET  /logout         revoca el token y cierra la sesión
    POST /api/auth/token devuelve un JWT (para clientes de la API)
    GET  /api/auth/yo    datos del usuario del token
"""

from __future__ import annotations

from flask import (
    Blueprint,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app import auditoria
from app.navegacion import ruta_inicial
from app.security import (
    autenticar,
    cerrar_sesion_web,
    crear_token,
    iniciar_sesion_web,
    token_requerido,
)
from app.services_client import ServiceError, call_service

bp = Blueprint("auth", __name__)


def _ip() -> str | None:
    reenviada = request.headers.get("X-Forwarded-For", "")
    return (reenviada.split(",")[0].strip() or request.remote_addr) or None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for(ruta_inicial(session.get("role", ""))))

    error = None
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        try:
            # Delegación HTTP directa a svc-auth (5001)
            resp = call_service(
                "auth",
                "POST",
                "/api/v1/auth/login",
                json_data={"email": email, "password": password},
            )
            token = resp.get("token")
            jti = resp.get("jti")
            u_data = resp.get("usuario") or {}
            usuario = {
                "id_usuario": u_data.get("id_usuario"),
                "nombre_completo": u_data.get("nombre", ""),
                "email": u_data.get("email", email),
                "rol_clave": u_data.get("rol", ""),
                "id_locacion": u_data.get("id_locacion"),
                "nombre_rol": u_data.get("nombre_rol") or u_data.get("rol", "").capitalize(),
            }
            iniciar_sesion_web(usuario, token, jti)
            session["jwt_token"] = token
            session["jwt_jti"] = jti

            destino = request.args.get("next")
            if destino and destino.startswith("/"):
                return redirect(destino)
            return redirect(url_for(ruta_inicial(usuario["rol_clave"])))
        except ServiceError as serr:
            error = serr.message
        except Exception:
            # Fallback transparente si svc-auth está caído
            usuario, error = autenticar(
                email, password, ip=_ip(), user_agent=request.headers.get("User-Agent")
            )
            if usuario:
                token, jti = crear_token(
                    usuario, ip=_ip(), user_agent=request.headers.get("User-Agent")
                )
                iniciar_sesion_web(usuario, token, jti)
                session["jwt_token"] = token
                session["jwt_jti"] = jti
                auditoria.registrar(
                    "LOGIN",
                    tabla="usuario",
                    id_registro=usuario["id_usuario"],
                    descripcion=f"Inicio de sesión correcto como {usuario['nombre_rol']}",
                    id_usuario=usuario["id_usuario"],
                    usuario_email=usuario["email"],
                    ip=_ip(),
                    user_agent=request.headers.get("User-Agent"),
                )
                destino = request.args.get("next")
                if destino and destino.startswith("/"):
                    return redirect(destino)
                return redirect(url_for(ruta_inicial(usuario["rol_clave"])))

    return render_template("login.html", error=error, email=email)


@bp.route("/logout")
def logout():
    token = session.get("jwt_token")
    if token:
        try:
            call_service("auth", "POST", "/api/v1/auth/logout", timeout=2.0)
        except Exception:
            pass
    cerrar_sesion_web()
    return redirect(url_for("publico.inicio"))


# ---------------------------------------------------------------------------
# Endpoints JSON de autenticación
# ---------------------------------------------------------------------------
@bp.post("/api/auth/token")
def api_token():
    """Emite un JWT a partir de correo y contraseña (clientes externos)."""
    datos = request.get_json(silent=True) or request.form
    email = (datos.get("email") or "").strip()
    password = datos.get("password") or ""

    usuario, error = autenticar(
        email, password, ip=_ip(), user_agent=request.headers.get("User-Agent")
    )
    if usuario is None:
        return jsonify({"error": "credenciales_invalidas", "mensaje": error}), 401

    token, jti = crear_token(usuario, ip=_ip(), user_agent=request.headers.get("User-Agent"))
    auditoria.registrar(
        "LOGIN",
        tabla="usuario",
        id_registro=usuario["id_usuario"],
        descripcion="Inicio de sesión vía API (JWT)",
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
        ip=_ip(),
    )
    return jsonify(
        {
            "token": token,
            "jti": jti,
            "usuario": {
                "id": usuario["id_usuario"],
                "nombre": usuario["nombre_completo"],
                "email": usuario["email"],
                "rol": usuario["rol_clave"],
                "rol_nombre": usuario["nombre_rol"],
            },
        }
    )


@bp.get("/api/auth/yo")
@token_requerido
def api_yo():
    """Devuelve los datos del usuario dueño del token."""
    return jsonify({"usuario": g.jwt_payload})
