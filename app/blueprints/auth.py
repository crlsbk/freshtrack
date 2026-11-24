"""
Blueprint de autenticación.

    GET  /login          formulario
    POST /login          valida contra PostgreSQL y abre sesión web + JWT
    GET  /logout         revoca el token y cierra la sesión
    POST /api/auth/token devuelve un JWT (para clientes de la API)
    GET  /api/auth/yo    datos del usuario del token
"""

from __future__ import annotations

from urllib.parse import urlsplit

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
    emitir_sesion,
    iniciar_sesion_web,
    token_requerido,
)

bp = Blueprint("auth", __name__)


def _ip() -> str | None:
    reenviada = request.headers.get("X-Forwarded-For", "")
    return (reenviada.split(",")[0].strip() or request.remote_addr) or None


def _destino_local_seguro(destino: str | None) -> bool:
    """
    Solo rutas internas del sitio. `startswith("/")` no bastaba: «//evil.com» y
    «/\\evil.com» empiezan con «/» y el navegador los trata como otro dominio.
    """
    if not destino or not destino.startswith("/") or destino.startswith(("//", "/\\")):
        return False
    if any(c in destino for c in ("\\", "\r", "\n", "\t")):
        return False
    partes = urlsplit(destino)
    return not partes.scheme and not partes.netloc


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
            return None, None, None, None, "El módulo de autenticación no está disponible en este momento."
        return None, None, None, None, (r or {}).get("mensaje") or "Correo o contraseña incorrectos."
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
    return usuario, r["token"], r["jti"], r.get("refresh_token"), None


_LIMITE_LOGIN = 10        # intentos por (IP, correo) por ventana
_LIMITE_LOGIN_IP = 30     # intentos por IP por ventana (frena probar 1 clave en muchas cuentas)
_VENTANA_LOGIN = 60


def _login_permitido(email: str) -> bool:
    """
    Rate limit del login (formulario web y /api/auth/token). El bloqueo de 5
    intentos por cuenta no frena probar una contraseña contra muchas cuentas;
    esto sí. Si Redis no responde se permite (el bloqueo por cuenta sigue).
    """
    from app.services.cache_service import incrementar_contador, verificar_rate_limit

    ip = _ip() or "?"
    ok_cuenta, _, _ = verificar_rate_limit(
        f"web_login:ip:{ip}:email:{(email or '-').lower()}", limite=_LIMITE_LOGIN, ventana_segundos=_VENTANA_LOGIN
    )
    ok_ip, _, _ = verificar_rate_limit(f"web_login:ip:{ip}", limite=_LIMITE_LOGIN_IP, ventana_segundos=_VENTANA_LOGIN)
    if not (ok_cuenta and ok_ip):
        incrementar_contador("web", "login_throttled")
        auditoria.registrar(
            "LOGIN_FALLIDO",
            tabla="usuario",
            descripcion=f"Intento bloqueado por exceso de intentos (límite de tasa) para {email or '-'}",
            usuario_email=email or None,
            ip=ip,
            user_agent=request.headers.get("User-Agent"),
        )
        return False
    return True


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for(ruta_inicial(session.get("role", ""))))

    error = None
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not _login_permitido(email):
            return render_template(
                "login.html", error="Demasiados intentos. Espera un minuto antes de volver a intentar.", email=email
            ), 429
        if clientes.activo():
            usuario, token, jti, refresh_token, error = _login_por_svc_auth(email, password)
        else:
            usuario, error = autenticar(
                email, password, ip=_ip(), user_agent=request.headers.get("User-Agent")
            )
            token = jti = refresh_token = None
            if usuario:
                sesion = emitir_sesion(usuario, ip=_ip(), user_agent=request.headers.get("User-Agent"))
                token, jti, refresh_token = sesion["token"], sesion["jti"], sesion["refresh_token"]

        if usuario:
            iniciar_sesion_web(usuario, token, jti, refresh_token)
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
            if _destino_local_seguro(destino):
                return redirect(destino)
            return redirect(url_for(ruta_inicial(usuario["rol_clave"])))

    return render_template("login.html", error=error, email=email)


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    # POST (botón «Salir», con token CSRF) es la vía normal. Un GET solo cierra
    # la sesión si viene de una página de este mismo sitio: así un <img> o un
    # enlace en otro sitio no puede cerrar sesiones ajenas.
    if request.method == "GET" and not (request.referrer or "").startswith(request.host_url):
        return redirect(url_for("publico.inicio"))
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
    if not _login_permitido(email):
        return jsonify({"error": "limite_excedido", "mensaje": "Demasiados intentos; espere un minuto."}), 429

    usuario, error = autenticar(
        email, password, ip=_ip(), user_agent=request.headers.get("User-Agent")
    )
    if usuario is None:
        return jsonify({"error": "credenciales_invalidas", "mensaje": error}), 401

    sesion = emitir_sesion(usuario, ip=_ip(), user_agent=request.headers.get("User-Agent"))
    token, jti = sesion["token"], sesion["jti"]
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
            "expira_en_segundos": sesion["expira_en_segundos"],
            "refresh_token": sesion["refresh_token"],
            "refresh_expira_en_segundos": sesion["refresh_expira_en_segundos"],
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
