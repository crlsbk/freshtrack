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

import threading
import hashlib
import secrets
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
def _minutos_acceso() -> int:
    """Vida del access token. Corta: si se filtra, sirve poco tiempo."""
    try:
        valor = int(escalar("SELECT analitica.fn_config('jwt_minutos_acceso', :d)", d=str(Config.JWT_MINUTOS_ACCESO)))
    except Exception:
        valor = Config.JWT_MINUTOS_ACCESO
    return max(1, valor)


def _hash_refresh(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


SEGUNDOS_GRACIA_REFRESH = 30


def emitir_sesion(
    usuario: dict,
    ip: str | None = None,
    user_agent: str | None = None,
    *,
    familia: str | None = None,
    sesion_expira_en: datetime | None = None,
) -> dict:
    """
    Emite un access token JWT corto + un refresh token opaco y los persiste.

    - Access: `jwt_minutos_acceso` (15 min por defecto), nunca más allá del fin
      de la sesión.
    - Refresh: aleatorio de 256 bits; en PostgreSQL solo se guarda su SHA-256.
    - `familia` / `sesion_expira_en`: se heredan al rotar, así la sesión tiene un
      fin ABSOLUTO (`jwt_horas_vigencia` desde el login) que rotar no extiende.
    """
    jti = uuid.uuid4().hex
    emitido = _ahora()
    if sesion_expira_en is None:
        sesion_expira_en = emitido + timedelta(hours=_horas_vigencia())
    familia = familia or str(uuid.uuid4())
    expira = min(emitido + timedelta(minutes=_minutos_acceso()), sesion_expira_en)
    refresh_token = secrets.token_urlsafe(32)

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
                    (id_usuario, jti, emitido_en, expira_en, ip, user_agent,
                     refresh_hash, refresh_expira_en, familia)
                VALUES (CAST(:u AS uuid), :jti, :emitido, :expira,
                        CAST(:ip AS inet), :ua, :rh, :rexp, CAST(:fam AS uuid))
                """
            ),
            {
                "u": usuario["id_usuario"],
                "jti": jti,
                "emitido": emitido,
                "expira": expira,
                "ip": ip,
                "ua": (user_agent or "")[:300] or None,
                "rh": _hash_refresh(refresh_token),
                "rexp": sesion_expira_en,
                "fam": familia,
            },
        )

    ttl_acceso = max(1, int((expira - emitido).total_seconds()))
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
                "familia": familia,
                "ip": ip,
                "user_agent": user_agent,
                "login_en": emitido.isoformat(),
            },
            ttl_segundos=ttl_acceso,
        )
    except Exception:
        pass

    return {
        "token": token,
        "jti": jti,
        "refresh_token": refresh_token,
        "expira_en_segundos": ttl_acceso,
        "refresh_expira_en_segundos": max(0, int((sesion_expira_en - emitido).total_seconds())),
        "familia": familia,
    }


def crear_token(usuario: dict, ip: str | None = None, user_agent: str | None = None) -> tuple[str, str]:
    """Compatibilidad: emite una sesión nueva y devuelve solo (access token, jti)."""
    sesion = emitir_sesion(usuario, ip=ip, user_agent=user_agent)
    return sesion["token"], sesion["jti"]


def _usuario_vigente(id_usuario: str) -> dict | None:
    """Datos ACTUALES del usuario (rol, sucursal…) para firmar el token renovado."""
    return one(
        """
        SELECT u.id_usuario::text AS id_usuario, u.email, u.nombre_completo, u.id_locacion,
               u.estado_activo, r.clave AS rol_clave
        FROM operacion.usuario u JOIN operacion.rol r ON r.id_rol = u.id_rol
        WHERE u.id_usuario = CAST(:u AS uuid)
        """,
        u=id_usuario,
    )


def revocar_familia(familia: str, motivo: str = "") -> int:
    """Revoca todas las sesiones de una familia (PostgreSQL + Redis)."""
    with transaccion() as conn:
        filas = conn.execute(
            transaccion_texto(
                "UPDATE operacion.sesion_usuario SET revocado = true, revocado_en = now() "
                "WHERE familia = CAST(:f AS uuid) AND NOT revocado "
                "RETURNING jti, GREATEST(60, EXTRACT(EPOCH FROM expira_en - now())::int) AS ttl"
            ),
            {"f": familia},
        ).mappings().all()
    for fila in filas:
        try:
            revocar_jwt(fila["jti"], ttl_segundos=int(fila["ttl"]))
            eliminar_sesion_redis(fila["jti"])
        except Exception:
            pass
    return len(filas)


def renovar_sesion(
    *,
    refresh_token: str | None = None,
    jti_vigente: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> dict | None:
    """
    Rota la sesión: revoca la fila actual y emite access + refresh nuevos en la
    MISMA familia y con el MISMO fin absoluto. Devuelve None si no procede.

    - Con `refresh_token` (flujo normal, aunque el access ya haya expirado).
    - Con `jti_vigente` (compatibilidad: renovar con un access token válido).

    Reutilización: presentar un refresh que YA se rotó indica robo (lo usaron el
    dueño y el atacante). Se revoca la familia completa, salvo dentro de una
    gracia de 30 s en la que se devuelve el mismo par nuevo (dos pestañas o dos
    hilos que renuevan a la vez no deben cerrar la sesión).
    """
    from app.services.cache_service import get_json, set_json

    if refresh_token:
        hash_rt = _hash_refresh(refresh_token)
        condicion, valor = "s.refresh_hash = :v", hash_rt
    elif jti_vigente:
        hash_rt = None
        condicion, valor = "s.jti = :v", jti_vigente
    else:
        return None

    with transaccion() as conn:
        fila = conn.execute(
            transaccion_texto(
                f"""
                SELECT s.id_usuario::text AS id_usuario, s.jti, s.revocado, s.familia::text AS familia,
                       s.refresh_expira_en, s.expira_en
                FROM operacion.sesion_usuario s
                WHERE {condicion}
                FOR UPDATE
                """
            ),
            {"v": valor},
        ).mappings().first()
        if fila is None:
            return None

        reutilizado = bool(fila["revocado"])
        if not reutilizado:
            ahora = _ahora()
            fin = fila["refresh_expira_en"] or (ahora + timedelta(hours=_horas_vigencia()))
            if fin <= ahora:
                return None
            usuario = _usuario_vigente(fila["id_usuario"])
            if usuario is None or not usuario["estado_activo"]:
                return None
            conn.execute(
                transaccion_texto(
                    "UPDATE operacion.sesion_usuario SET revocado = true, revocado_en = now() WHERE jti = :j"
                ),
                {"j": fila["jti"]},
            )

    if reutilizado:
        if not hash_rt:
            return None  # un access token revocado simplemente no renueva
        previo = get_json(f"refresh:gracia:{hash_rt}")
        if previo and verificar_sesion_respaldo_bd(previo.get("jti", "")):
            return previo  # renovación concurrente legítima dentro de la gracia
        # Solo es robo si la familia seguía viva (alguien usa el sucesor). Tras un
        # logout o una revocación del admin no queda nada vivo: no hay alarma.
        revocados = revocar_familia(fila["familia"]) if fila["familia"] else 0
        if revocados:
            auditoria.registrar(
                "REFRESH_REUTILIZADO",
                tabla="sesion_usuario",
                id_registro=fila["id_usuario"],
                descripcion=f"Refresh token reutilizado tras rotar: se revocaron {revocados} sesión(es) de la familia",
                id_usuario=fila["id_usuario"],
                ip=ip,
                user_agent=user_agent,
            )
        return None

    ttl_viejo = max(60, int((fila["expira_en"] - _ahora()).total_seconds()))
    try:
        revocar_jwt(fila["jti"], ttl_segundos=ttl_viejo)
        eliminar_sesion_redis(fila["jti"])
    except Exception:
        pass

    nueva = emitir_sesion(
        usuario, ip=ip, user_agent=user_agent, familia=fila["familia"], sesion_expira_en=fin
    )
    nueva["usuario"] = usuario
    if hash_rt:
        try:
            set_json(f"refresh:gracia:{hash_rt}", nueva, ttl_segundos=SEGUNDOS_GRACIA_REFRESH)
        except Exception:
            pass
    return nueva


# Marca, por hilo, si la última verificación de sesión falló porque PostgreSQL no respondió.
_verificacion_local = threading.local()


def decodificar_token_con_motivo(token: str) -> tuple[dict | None, str]:
    """
    Valida el token y devuelve (payload, "ok"), (None, "invalido") o
    (None, "bd_no_disponible") cuando la firma es buena pero PostgreSQL no respondió.
    """
    try:
        payload = jwt.decode(
            token,
            Config.JWT_SECRET_KEY,
            algorithms=[Config.JWT_ALGORITHM],
            issuer="freshtrack",
            options={"require": ["exp", "iat", "jti", "sub", "iss"]},
            leeway=30,
        )
    except jwt.PyJWTError:
        return None, "invalido"
    jti = payload.get("jti")
    if not jti or esta_jwt_revocado(jti):
        return None, "invalido"
    _verificacion_local.fallo_bd = False
    if verificar_sesion_respaldo_bd(jti):
        return payload, "ok"
    return None, ("bd_no_disponible" if getattr(_verificacion_local, "fallo_bd", False) else "invalido")


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
        _verificacion_local.fallo_bd = True
        return False
    if vigente is None or vigente["revocado"] or not vigente["estado_activo"]:
        return False
    if vigente["expira_en"] <= _ahora():
        return False
    return True


def decodificar_token(token: str) -> dict | None:
    """Valida firma y expiración, y comprueba que la sesión siga vigente (Fail-Closed)."""
    return decodificar_token_con_motivo(token)[0]


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
    """
    Logout: revoca el token y TODA su familia (los access tokens y el refresh
    token nacidos del mismo login), en PostgreSQL y en Redis.
    """
    with transaccion() as conn:
        filas = conn.execute(
            transaccion_texto(
                """
                UPDATE operacion.sesion_usuario SET revocado = true, revocado_en = now()
                WHERE NOT revocado
                  AND (jti = :jti
                       OR familia = (SELECT familia FROM operacion.sesion_usuario WHERE jti = :jti))
                RETURNING jti
                """
            ),
            {"jti": jti},
        ).mappings().all()
    # Refleja la revocación en la denylist de Redis de inmediato y elimina la sesión.
    ttl = int(_horas_vigencia() * 3600)
    for j in {jti, *(f["jti"] for f in filas)}:
        revocar_jwt(j, ttl_segundos=ttl)
        eliminar_sesion_redis(j)


# ---------------------------------------------------------------------------
# Sesión web
# ---------------------------------------------------------------------------
def iniciar_sesion_web(usuario: dict, token: str, jti: str, refresh_token: str | None = None) -> None:
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
    # Cookie firmada y HttpOnly: JavaScript no puede leerla.
    session["refresh_token"] = refresh_token


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
def proveedor_de_sesion() -> int | None:
    """
    Para una sesión web con rol supplier, el id de SU proveedor (leído de la
    base en cada llamada, así una reasignación aplica de inmediato). Devuelve 0
    si el usuario no tiene proveedor asignado (no coincide con ninguno) y None
    para los demás roles (sin restricción).
    """
    if session.get("role") != "supplier":
        return None
    try:
        valor = escalar(
            "SELECT id_proveedor FROM operacion.usuario WHERE id_usuario = CAST(:u AS uuid)",
            u=session.get("user_id"),
        )
    except Exception:
        return 0
    return int(valor) if valor is not None else 0


def recurso_de_otro_proveedor(id_proveedor_recurso: int | None) -> bool:
    """True si la sesión es de un supplier y el recurso NO es de su proveedor."""
    propio = proveedor_de_sesion()
    if propio is None:
        return False
    return not propio or id_proveedor_recurso is None or int(id_proveedor_recurso) != propio


SEGUNDOS_MARGEN_RENOVACION = 60


def _segundos_restantes(token: str | None) -> float:
    """Segundos de vida que le quedan a un access token (lo firmamos nosotros)."""
    if not token:
        return 0.0
    try:
        exp = jwt.decode(token, options={"verify_signature": False}).get("exp", 0)
    except jwt.PyJWTError:
        return 0.0
    return float(exp) - _ahora().timestamp()


def _renovar_sesion_web() -> bool:
    """Rota access + refresh de la sesión web y actualiza la cookie. False si no se pudo."""
    nueva = renovar_sesion(
        refresh_token=session.get("refresh_token"),
        ip=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    if not nueva:
        return False
    u = nueva.get("usuario") or {}
    session["token"] = nueva["token"]
    session["jti"] = nueva["jti"]
    session["refresh_token"] = nueva["refresh_token"]
    # Datos frescos de la base (un cambio de rol ya revoca sesiones; esto es redundancia).
    if u:
        session["role"] = u.get("rol_clave", session.get("role"))
        session["id_locacion"] = u.get("id_locacion")
        session["user_email"] = u.get("email", session.get("user_email"))
    return True


def sesion_web_vigente() -> bool:
    """
    True si la cookie de sesión pertenece a una sesión viva y no revocada.

    Redis decide (denylist + session:{jti}); si Redis no responde, PostgreSQL
    decide (Fail-Closed). Una cookie sin jti no se acepta: todas las sesiones
    legítimas se abren con un JWT.

    El access token dura minutos: si está por vencer, ya venció o lo rotó otra
    petición simultánea de la misma sesión, se renueva con el refresh token de
    la cookie. Si la sesión fue revocada (logout, admin) o llegó a su fin
    absoluto, la renovación falla y la sesión termina.
    """
    if "user_id" not in session:
        return False
    jti = session.get("jti")
    if not jti:
        return False

    vigente = not esta_jwt_revocado(jti)
    if vigente:
        estado_redis = sesion_activa(jti)
        if estado_redis is False:
            vigente = False
        elif estado_redis is None and not verificar_sesion_respaldo_bd(jti):
            vigente = False
    if vigente and _segundos_restantes(session.get("token")) > SEGUNDOS_MARGEN_RENOVACION:
        return True
    if not session.get("refresh_token"):
        return vigente  # sesiones anteriores al refresh token: hasta su expiración
    return _renovar_sesion_web()


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
