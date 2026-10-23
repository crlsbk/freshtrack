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
from app.db import one
from app.navegacion import ruta_inicial
from app.services import clientes
from app.security import (
    autenticar,
    cerrar_sesion_web,
    crear_token,
    iniciar_sesion_web,
    token_requerido,
)

bp = Blueprint("auth", __name__)


def _ip() -> str | None:
    reenviada = request.headers.get("X-Forwarded-For", "")
    return (reenviada.split(",")[0].strip() or request.remote_addr) or None


def _login_por_svc_auth(email: str, password: str):
    """
    El login de la web lo resuelve svc-auth: valida la contraseña, emite el JWT y
    crea la sesión en Redis. La web solo guarda ese token en su cookie de sesión y
    lo reenvía en cada operación que delega a los demás microservicios.
    """
    status, r = clientes.como_usuario(
        "auth", "POST", "/api/v1/auth/login", {"email": email, "password": password}
    )
    if status != 200:
        if status == 0:
            return None, None, None, "El servicio de autenticación (svc-auth) no está disponible."
        return None, None, None, (r or {}).get("mensaje") or "Correo o contraseña incorrectos."
    u = r["usuario"]
    rol = one("SELECT nombre_rol FROM operacion.rol WHERE clave = :c", c=u["rol"]) or {}
    usuario = {
        "id_usuario": u["id_usuario"],
        "email": u["email"],
        "nombre_completo": u["nombre"],
        "rol_clave": u["rol"],
        "nombre_rol": rol.get("nombre_rol", u["rol"]),
        "id_locacion": u["id_locacion"],
    }
    return usuario, r["token"], r["jti"], None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for(ruta_inicial(session.get("role", ""))))

    error = None
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if clientes.activo():
            usuario, token, jti, error = _login_por_svc_auth(email, password)
        else:
            usuario, error = autenticar(
                email, password, ip=_ip(), user_agent=request.headers.get("User-Agent")
            )
            token = jti = None
            if usuario:
                token, jti = crear_token(
                    usuario, ip=_ip(), user_agent=request.headers.get("User-Agent")
                )

        if usuario:
            iniciar_sesion_web(usuario, token, jti)
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
    if clientes.activo() and session.get("token"):
        # svc-auth revoca el JWT (PostgreSQL + denylist de Redis) y borra la sesión.
        clientes.como_usuario("auth", "POST", "/api/v1/auth/logout")
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
