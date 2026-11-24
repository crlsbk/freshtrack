"""
Autenticación y control de acceso.

Flujo completo exigido por la rúbrica:

    Login → validación en PostgreSQL → verificación del password_hash (bcrypt)
          → emisión de sesión web + JWT → resolución de rol y permisos
          → menú correspondiente

Además: logout, usuarios activos/inactivos, protección de rutas, bloqueo por
intentos fallidos y revocación de tokens.

La verificación del hash se hace **dentro de PostgreSQL** con `crypt()`
(pgcrypto), de modo que la contraseña en claro nunca se compara en Python.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import jsonify, redirect, request, session, url_for

from app import auditoria
from app.config import Config
from app.db import escalar, one, transaccion
from app.navegacion import puede_ver, ruta_inicial
from app.services.cache_service import (
    crear_sesion_redis,
    eliminar_sesion_redis,
    esta_jwt_revocado,
    obtener_sesion_redis,
    revocar_jwt,
    sesion_activa,
)

MAX_INTENTOS_DEFECTO = 5
MINUTOS_BLOQUEO = 15


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _max_intentos() -> int:
    try:
        return int(escalar("SELECT analitica.fn_config('max_intentos_login', '5')") or 5)
    except Exception:
        return MAX_INTENTOS_DEFECTO


def _horas_vigencia() -> int:
    try:
        return int(escalar("SELECT analitica.fn_config('jwt_horas_vigencia', '8')") or 8)
    except Exception:
        return Config.JWT_HORAS_VIGENCIA


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
def autenticar(email: str, password: str, ip: str | None = None, user_agent: str | None = None):
    """
    Valida las credenciales contra PostgreSQL.

    Devuelve (usuario, error). `usuario` es None si algo falla.
    El mensaje de error es genérico a propósito: no se revela si el correo
    existe o no.
    """
    email = (email or "").strip()
    if not email or not password:
        return None, "Captura tu correo y tu contraseña."

    usuario = one(
        """
        SELECT u.id_usuario::text AS id_usuario,
               u.id_rol,
               u.id_locacion,
               u.nombre_completo,
               u.email,
               u.estado_activo,
               u.intentos_fallidos,
               u.bloqueado_hasta,
               r.clave       AS rol_clave,
               r.nombre_rol,
               (public.crypt(:password, u.password_hash) = u.password_hash) AS password_ok
        FROM operacion.usuario u
        JOIN operacion.rol r ON r.id_rol = u.id_rol
        WHERE lower(u.email) = lower(:email)
        """,
        email=email,
        password=password,
    )

    if usuario is None:
        auditoria.registrar(
            "LOGIN_FALLIDO",
            tabla="usuario",
            descripcion=f"Intento de acceso con un correo no registrado: {email}",
            usuario_email=email,
            ip=ip,
            user_agent=user_agent,
        )
        return None, "Correo o contraseña incorrectos."

    if usuario["bloqueado_hasta"] and usuario["bloqueado_hasta"] > _ahora():
        restante = int((usuario["bloqueado_hasta"] - _ahora()).total_seconds() // 60) + 1
        return None, f"La cuenta está bloqueada temporalmente. Intenta en {restante} minuto(s)."

    if not usuario["password_ok"]:
        intentos = (usuario["intentos_fallidos"] or 0) + 1
        maximo = _max_intentos()
        with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
            if intentos >= maximo:
                conn.execute(
                    transaccion_texto(
                        "UPDATE operacion.usuario SET intentos_fallidos = :i, "
                        "bloqueado_hasta = now() + (:m || ' minutes')::interval "
                        "WHERE id_usuario = CAST(:u AS uuid)"
                    ),
                    {"i": intentos, "m": str(MINUTOS_BLOQUEO), "u": usuario["id_usuario"]},
                )
            else:
                conn.execute(
                    transaccion_texto(
                        "UPDATE operacion.usuario SET intentos_fallidos = :i "
                        "WHERE id_usuario = CAST(:u AS uuid)"
                    ),
                    {"i": intentos, "u": usuario["id_usuario"]},
                )
        auditoria.registrar(
            "LOGIN_FALLIDO",
            tabla="usuario",
            id_registro=usuario["id_usuario"],
            descripcion=f"Contraseña incorrecta ({intentos}/{maximo})",
            id_usuario=usuario["id_usuario"],
            usuario_email=usuario["email"],
            ip=ip,
            user_agent=user_agent,
        )
        return None, "Correo o contraseña incorrectos."

    if not usuario["estado_activo"]:
        auditoria.registrar(
            "LOGIN_FALLIDO",
            tabla="usuario",
            id_registro=usuario["id_usuario"],
            descripcion="Intento de acceso con una cuenta desactivada",
            id_usuario=usuario["id_usuario"],
            usuario_email=usuario["email"],
            ip=ip,
            user_agent=user_agent,
        )
        return None, "Esta cuenta está desactivada. Contacta al administrador."

    # Credenciales correctas: se limpian los intentos y se registra el acceso
    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        conn.execute(
            transaccion_texto(
                "UPDATE operacion.usuario SET intentos_fallidos = 0, "
                "bloqueado_hasta = NULL, ultimo_acceso = now() "
                "WHERE id_usuario = CAST(:u AS uuid)"
            ),
            {"u": usuario["id_usuario"]},
        )

    return usuario, None


def transaccion_texto(sql: str):
    """Pequeño ayudante para no importar `text` en cada módulo."""
    from sqlalchemy import text

    return text(sql)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def crear_token(usuario: dict, ip: str | None = None, user_agent: str | None = None) -> tuple[str, str]:
    """Emite un JWT y lo persiste en operacion.sesion_usuario para poder revocarlo."""
    jti = uuid.uuid4().hex
    horas = _horas_vigencia()
    emitido = _ahora()
    expira = emitido + timedelta(hours=horas)

    payload = {
        "sub": usuario["id_usuario"],
        "email": usuario["email"],
        "nombre": usuario["nombre_completo"],
        "rol": usuario["rol_clave"],
        "id_locacion": usuario["id_locacion"],
        "jti": jti,
        "iat": int(emitido.timestamp()),
        "exp": int(expira.timestamp()),
        "iss": "freshtrack",
    }
    token = jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)

    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        conn.execute(
            transaccion_texto(
                """
                INSERT INTO operacion.sesion_usuario
                    (id_usuario, jti, emitido_en, expira_en, ip, user_agent)
                VALUES (CAST(:u AS uuid), :jti, :emitido, :expira,
                        CAST(:ip AS inet), :ua)
                """
            ),
            {
                "u": usuario["id_usuario"],
                "jti": jti,
                "emitido": emitido,
                "expira": expira,
                "ip": ip,
                "ua": (user_agent or "")[:300] or None,
            },
        )

    # Registrar sesión activa en Redis con sliding TTL
    try:
        crear_sesion_redis(
            jti,
            {
                "id_usuario": usuario["id_usuario"],
                "email": usuario["email"],
                "nombre": usuario["nombre_completo"],
                "rol": usuario["rol_clave"],
                "id_locacion": usuario["id_locacion"],
                "jti": jti,
                "ip": ip,
                "user_agent": user_agent,
                "login_en": emitido.isoformat(),
            },
            ttl_segundos=int(horas * 3600),
        )
    except Exception:
        pass

    return token, jti


def verificar_sesion_respaldo_bd(jti: str) -> bool:
    """
    Verificación Fail-Closed en PostgreSQL cuando Redis no está disponible.
    Devuelve True únicamente si la sesión existe, no está revocada, no expiró
    y la cuenta del usuario sigue activa. Ante cualquier fallo devuelve False.
    """
    if not jti:
        return False
    try:
        vigente = one(
            """
            SELECT s.revocado, s.expira_en, u.estado_activo
            FROM operacion.sesion_usuario s
            JOIN operacion.usuario u ON u.id_usuario = s.id_usuario
            WHERE s.jti = :jti
            """,
            jti=jti,
        )
    except Exception:
        return False
    if vigente is None or vigente["revocado"] or not vigente["estado_activo"]:
        return False
    if vigente["expira_en"] <= _ahora():
        return False
    return True


def decodificar_token(token: str) -> dict | None:
    """Valida firma y expiración, y comprueba que la sesión siga vigente (Fail-Closed)."""
    try:
        payload = jwt.decode(
            token,
            Config.JWT_SECRET_KEY,
            algorithms=[Config.JWT_ALGORITHM],
            issuer="freshtrack",
            # Sin `require`, PyJWT acepta un token SIN exp como si no caducara.
            options={"require": ["exp", "iat", "jti", "sub", "iss"]},
            leeway=30,
        )
    except jwt.PyJWTError:
        return None

    jti = payload.get("jti")
    if not jti:
        return None

    # Verificación ultra-rápida en la denylist de Redis
    if esta_jwt_revocado(jti):
        return None

    if not verificar_sesion_respaldo_bd(jti):
        return None
    return payload


def revocar_sesiones_usuario(id_usuario: str) -> int:
    """
    Revoca TODAS las sesiones vigentes de un usuario en PostgreSQL y en Redis.

    Se usa al desactivar la cuenta, restablecer la contraseña o cambiar rol,
    sucursal o correo (datos que viajan dentro del JWT). Revocar solo en
    PostgreSQL no basta: `login_required` consulta Redis primero y la sesión
    seguía viva hasta su expiración. Los jti salen de PostgreSQL (no del índice
    user:sessions de Redis) para cubrir también sesiones creadas mientras Redis
    estaba caído. Devuelve cuántas sesiones se revocaron.
    """
    from app.services import cache_service

    with transaccion() as conn:
        filas = conn.execute(
            transaccion_texto(
                "UPDATE operacion.sesion_usuario SET revocado = true, revocado_en = now() "
                "WHERE id_usuario = CAST(:u AS uuid) AND NOT revocado AND expira_en > now() "
                "RETURNING jti, GREATEST(60, EXTRACT(EPOCH FROM expira_en - now())::int) AS ttl"
            ),
            {"u": id_usuario},
        ).mappings().all()
    for fila in filas:
        try:
            revocar_jwt(fila["jti"], ttl_segundos=int(fila["ttl"]))
            eliminar_sesion_redis(fila["jti"])
        except Exception:
            pass
    # Sesiones que solo existieran en Redis (p. ej. ya revocadas en PG pero vivas allá).
    try:
        cache_service.cerrar_sesiones_usuario(id_usuario)
    except Exception:
        pass
    return len(filas)


def revocar_token(jti: str) -> None:
    """Marca una sesión como revocada (logout)."""
    with transaccion() as conn:
        conn.execute(
            transaccion_texto(
                "UPDATE operacion.sesion_usuario SET revocado = true, revocado_en = now() "
                "WHERE jti = :jti"
            ),
            {"jti": jti},
        )
    # Refleja la revocación en la denylist de Redis de inmediato y elimina la sesión
    horas = _horas_vigencia()
    revocar_jwt(jti, ttl_segundos=int(horas * 3600))
    eliminar_sesion_redis(jti)


# ---------------------------------------------------------------------------
# Sesión web
# ---------------------------------------------------------------------------
def iniciar_sesion_web(usuario: dict, token: str, jti: str) -> None:
    session.clear()
    session.permanent = True
    session["user_id"] = usuario["id_usuario"]
    session["user_name"] = usuario["nombre_completo"]
    session["user_email"] = usuario["email"]
    session["role"] = usuario["rol_clave"]
    session["role_label"] = usuario["nombre_rol"]
    session["id_locacion"] = usuario["id_locacion"]
    session["jti"] = jti
    session["token"] = token


def cerrar_sesion_web() -> None:
    jti = session.get("jti")
    usuario = usuario_actual()
    if jti:
        revocar_token(jti)
    if usuario:
        auditoria.registrar(
            "LOGOUT",
            tabla="usuario",
            id_registro=usuario["id_usuario"],
            descripcion="Cierre de sesión",
            id_usuario=usuario["id_usuario"],
            usuario_email=usuario["email"],
        )
    session.clear()


def usuario_actual() -> dict | None:
    """Datos del usuario de la sesión actual (o del token Bearer si es API)."""
    if "user_id" not in session:
        return None
    return {
        "id_usuario": session["user_id"],
        "nombre_completo": session.get("user_name", ""),
        "email": session.get("user_email", ""),
        "rol_clave": session.get("role", ""),
        "nombre_rol": session.get("role_label", ""),
        "id_locacion": session.get("id_locacion"),
        "jti": session.get("jti"),
        "token": session.get("token"),
    }


# ---------------------------------------------------------------------------
# Decoradores de protección de rutas
# ---------------------------------------------------------------------------
def sesion_web_vigente() -> bool:
    """
    True si la cookie de sesión pertenece a una sesión viva y no revocada.

    Redis decide (denylist + session:{jti}); si Redis no responde, PostgreSQL
    decide (Fail-Closed). Una cookie sin jti no se acepta: todas las sesiones
    legítimas se abren con un JWT.
    """
    if "user_id" not in session:
        return False
    jti = session.get("jti")
    if not jti:
        return False
    if esta_jwt_revocado(jti):
        return False
    estado_redis = sesion_activa(jti)
    if estado_redis is False:
        return False
    if estado_redis is None and not verificar_sesion_respaldo_bd(jti):
        return False
    return True


def login_required(f):
    """Cualquier ruta que no sea pública exige sesión iniciada."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "no_autenticado"}), 401
            return redirect(url_for("auth.login", next=request.path))

        if not sesion_web_vigente():
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify({"error": "sesion_revocada"}), 401
            return redirect(url_for("auth.login", next=request.path))

        return f(*args, **kwargs)

    return wrapper


def requiere_vista(vista: str):
    """Exige que el rol tenga permiso sobre una pantalla concreta."""

    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            if not puede_ver(session.get("role", ""), vista):
                return redirect(url_for(ruta_inicial(session.get("role", ""))))
            return f(*args, **kwargs)

        return wrapper

    return decorador


def requiere_rol(*claves: str):
    """Exige que el usuario tenga uno de los roles indicados."""

    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("auth.login"))
            if session.get("role") not in claves:
                return redirect(url_for(ruta_inicial(session.get("role", ""))))
            return f(*args, **kwargs)

        return wrapper

    return decorador


def token_requerido(f):
    """
    Protege los endpoints JSON: exige `Authorization: Bearer <token>`.
    Deja la identidad del usuario en flask.g.
    """
    from flask import g

    @wraps(f)
    def wrapper(*args, **kwargs):
        cabecera = request.headers.get("Authorization", "")
        if not cabecera.startswith("Bearer "):
            return jsonify({"error": "falta_token"}), 401
        payload = decodificar_token(cabecera[7:].strip())
        if payload is None:
            return jsonify({"error": "token_invalido"}), 401
        g.jwt_payload = payload
        g.id_usuario = payload["sub"]
        g.rol = payload["rol"]
        return f(*args, **kwargs)

    return wrapper


def rol_en_token(*claves: str):
    """Restringe un endpoint JSON a ciertos roles."""

    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import g

            if getattr(g, "rol", None) not in claves:
                return jsonify({"error": "permiso_denegado"}), 403
            return f(*args, **kwargs)

        return wrapper

    return decorador
