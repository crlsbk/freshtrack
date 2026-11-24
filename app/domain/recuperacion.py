"""
Recuperación de contraseña por correo (web).

Flujo:
  1. El usuario captura su correo en /recuperar. La respuesta es SIEMPRE la
     misma, exista o no la cuenta (no se revela qué correos están registrados).
  2. Si la cuenta existe y está activa se genera un token aleatorio de un solo
     uso (secrets.token_urlsafe). En Redis se guarda solo su SHA-256:
         pwdreset:<sha256(token)> → id_usuario   (TTL 30 min)
     Quien lea Redis no obtiene un enlace utilizable.
  3. Se envía por correo el enlace /restablecer/<token>.
  4. Al restablecer se valida la política de contraseñas, se actualiza el hash
     (crypt/bcrypt en PostgreSQL), se consume el token (GET+DEL atómico: un solo
     uso), se revocan todas las sesiones del usuario y se audita.

Si Redis no está disponible la función falla cerrada (RecuperacionNoDisponible):
sin Redis no hay dónde guardar el token ni cómo limitar los intentos.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Callable

logger = logging.getLogger("freshtrack.recuperacion")

PREFIJO = "pwdreset:"
TTL_SEGUNDOS = 30 * 60
LIMITE_POR_CORREO = 3      # solicitudes por correo por ventana
LIMITE_POR_IP = 10         # solicitudes por IP por ventana
VENTANA_SEGUNDOS = 15 * 60

MENSAJE_NEUTRO = (
    "Si el correo corresponde a una cuenta activa, en unos minutos recibirás un enlace "
    "para restablecer tu contraseña. El enlace vence en 30 minutos y solo funciona una vez."
)
MENSAJE_NO_DISPONIBLE = (
    "La recuperación de contraseña no está disponible en este momento. "
    "Intenta más tarde o pide al administrador que restablezca tu contraseña."
)
MENSAJE_TOKEN_INVALIDO = (
    "El enlace para restablecer la contraseña no es válido, ya se usó o venció. "
    "Solicita uno nuevo."
)


class RecuperacionNoDisponible(RuntimeError):
    """Redis no responde: no se puede emitir ni validar el token."""


class TokenInvalido(ValueError):
    """Token inexistente, vencido o ya utilizado."""


class LimiteExcedido(RuntimeError):
    """Demasiadas solicitudes para el mismo correo o IP."""


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _redis():
    from app.services import cache_service

    r = cache_service.get_redis_client()
    if r is None:
        raise RecuperacionNoDisponible(MENSAJE_NO_DISPONIBLE)
    try:
        r.ping()
    except Exception as exc:  # noqa: BLE001
        raise RecuperacionNoDisponible(MENSAJE_NO_DISPONIBLE) from exc
    return r


def _usuario_activo_por_email(email: str) -> dict | None:
    from app.db import one

    return one(
        "SELECT id_usuario::text AS id_usuario, email, nombre_completo "
        "FROM operacion.usuario WHERE lower(email) = lower(:e) AND estado_activo",
        e=email,
    )


def _usuario_por_id(id_usuario: str) -> dict | None:
    from app.db import one

    return one(
        "SELECT id_usuario::text AS id_usuario, email, nombre_completo, estado_activo "
        "FROM operacion.usuario WHERE id_usuario = CAST(:u AS uuid)",
        u=id_usuario,
    )


def _enviar(destino: str, nombre: str, enlace: str) -> str:
    from app.services import mailer

    cuerpo = (
        f"Hola {nombre or ''},\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta de FreshTrack.\n"
        f"Abre este enlace para elegir una nueva (vence en {TTL_SEGUNDOS // 60} minutos y solo sirve una vez):\n\n"
        f"{enlace}\n\n"
        "Si no fuiste tú, ignora este correo: tu contraseña actual sigue funcionando.\n\n"
        "— FreshTrack"
    )
    return mailer.enviar_correo(destino, "FreshTrack — Restablecer contraseña", cuerpo)


def _auditar(accion: str, **kwargs) -> None:
    try:
        from app import auditoria

        auditoria.registrar(accion, tabla="usuario", **kwargs)
    except Exception as exc:  # noqa: BLE001 — la bitácora no debe romper el flujo
        logger.warning("No se pudo auditar %s: %s", accion, exc)


def _limite_permitido(r, identificador: str, limite: int) -> bool:
    clave = f"ratelimit:pwdreset:{identificador}"
    conteo = r.incr(clave)
    if conteo == 1:
        r.expire(clave, VENTANA_SEGUNDOS)
    return conteo <= limite


def solicitar(email: str, construir_enlace: Callable[[str], str], ip: str | None = None) -> str:
    """
    Procesa una solicitud de recuperación. Devuelve un estado interno
    ("ENVIADO", "SIN_CUENTA", "ERROR_CORREO") que la vista NO muestra: al usuario
    siempre se le responde MENSAJE_NEUTRO.

    Lanza RecuperacionNoDisponible si Redis no responde y LimiteExcedido si se
    superó el límite por correo o por IP.
    """
    email = (email or "").strip().lower()
    r = _redis()
    if not _limite_permitido(r, f"ip:{ip or '?'}", LIMITE_POR_IP) or not _limite_permitido(
        r, f"email:{hash_token(email)}", LIMITE_POR_CORREO
    ):
        raise LimiteExcedido("Demasiadas solicitudes. Espera unos minutos.")

    usuario = _usuario_activo_por_email(email) if email else None
    if not usuario:
        return "SIN_CUENTA"

    token = secrets.token_urlsafe(32)
    r.set(PREFIJO + hash_token(token), usuario["id_usuario"], ex=TTL_SEGUNDOS)
    try:
        _enviar(usuario["email"], usuario.get("nombre_completo") or "", construir_enlace(token))
    except Exception as exc:  # noqa: BLE001 — ErrorCorreo u otro: no se revela al usuario
        logger.warning("No se pudo enviar el correo de recuperación: %s", exc)
        r.delete(PREFIJO + hash_token(token))
        return "ERROR_CORREO"
    _auditar(
        "REQUEST_PASSWORD_RESET",
        id_registro=usuario["id_usuario"],
        descripcion="Solicitud de recuperación de contraseña por correo",
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
        ip=ip,
    )
    return "ENVIADO"


# GET + DEL atómico (equivale a GETDEL, que no existe en Redis < 6.2).
_LUA_CONSUMIR = """
local v = redis.call('GET', KEYS[1])
if v then redis.call('DEL', KEYS[1]) end
return v
"""


def token_vigente(token: str) -> bool:
    """True si el token existe y no ha vencido (para mostrar o no el formulario)."""
    if not token or len(token) > 200:
        return False
    return bool(_redis().get(PREFIJO + hash_token(token)))


def restablecer(token: str, nueva: str, confirmacion: str, ip: str | None = None) -> dict:
    """
    Cambia la contraseña con un token válido. Valida primero (política y
    confirmación) para no gastar el token por un error de captura; luego lo
    consume de forma atómica (GET+DEL en Lua) para que dos envíos simultáneos no lo usen
    dos veces. Devuelve el usuario.
    """
    from app.repos.catalogo import restablecer_password, validar_politica_password

    r = _redis()
    clave = PREFIJO + hash_token(token)
    if not token or len(token) > 200 or not r.exists(clave):
        raise TokenInvalido(MENSAJE_TOKEN_INVALIDO)
    validar_politica_password(nueva)
    if nueva != confirmacion:
        raise ValueError("La confirmación no coincide con la nueva contraseña.")

    id_usuario = r.eval(_LUA_CONSUMIR, 1, clave)
    if not id_usuario:
        raise TokenInvalido(MENSAJE_TOKEN_INVALIDO)
    usuario = _usuario_por_id(id_usuario)
    if not usuario or not usuario.get("estado_activo"):
        raise TokenInvalido(MENSAJE_TOKEN_INVALIDO)

    # Actualiza el hash con crypt(gen_salt('bf')), limpia intentos/bloqueo y
    # revoca TODAS las sesiones (PostgreSQL + denylist y sesiones de Redis).
    restablecer_password(
        usuario["id_usuario"],
        nueva,
        {"id_usuario": usuario["id_usuario"], "email": usuario["email"]},
        descripcion="Contraseña restablecida con enlace de recuperación por correo",
    )
    _auditar(
        "RESET_PASSWORD",
        id_registro=usuario["id_usuario"],
        descripcion="Recuperación de contraseña completada; sesiones anteriores revocadas",
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
        ip=ip,
    )
    return usuario
