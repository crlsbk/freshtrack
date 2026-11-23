"""
Correo saliente de FreshTrack (un solo lugar para todo envío SMTP).

Lo usan el envío de Órdenes de Compra (svc-planning) y el de la Hoja de Empaque
con etiquetas QR del ASN (svc-asn). La configuración sale del entorno:

    SMTP_HOST      servidor SMTP. En Docker es `mailpit` (ver docker-compose.yml);
                   vacío = modo demostración (no se envía nada, solo se registra).
    SMTP_PORT      587 (STARTTLS), 465 (SSL directo) o 1025 (Mailpit, sin cifrar).
    SMTP_USER      usuario para autenticarse (vacío = sin autenticación).
    SMTP_PASSWORD  contraseña / contraseña de aplicación.
    SMTP_FROM      remitente, p. ej. "FreshTrack Compras <compras@tuempresa.mx>".
    SMTP_TLS       true/false: STARTTLS en puertos distintos de 465.

Con la configuración de Docker la app entrega siempre a Mailpit, que guarda una
copia visible en http://localhost:8025 y, si se le dan credenciales MAIL_RELAY_*,
reenvía el correo al destinatario real (Gmail, Outlook, etc.).
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

logger = logging.getLogger("freshtrack.mailer")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

ENVIADO = "ENVIADO_SMTP"
SIN_SMTP = "REGISTRADO_SIN_SMTP"


class ErrorCorreo(ValueError):
    """El servidor SMTP rechazó el envío o no respondió."""


@dataclass(frozen=True)
class ConfigSMTP:
    host: str
    port: int
    user: str
    password: str
    remitente: str
    tls: bool

    @property
    def habilitado(self) -> bool:
        return bool(self.host)


def config_smtp() -> ConfigSMTP:
    """Lee la configuración en cada llamada (permite cambiar .env sin reconstruir imágenes)."""
    from app.config import Config

    try:
        port = int(os.getenv("SMTP_PORT", str(Config.SMTP_PORT)) or 587)
    except ValueError:
        port = 587
    return ConfigSMTP(
        host=os.getenv("SMTP_HOST", Config.SMTP_HOST).strip(),
        port=port,
        user=os.getenv("SMTP_USER", Config.SMTP_USER).strip(),
        password=os.getenv("SMTP_PASSWORD", Config.SMTP_PASSWORD),
        remitente=(os.getenv("SMTP_FROM", Config.SMTP_FROM) or "").strip() or "FreshTrack <no-reply@freshtrack.mx>",
        tls=os.getenv("SMTP_TLS", str(Config.SMTP_TLS)).lower() not in ("0", "false", "no"),
    )


def correo_valido(correo: str | None) -> bool:
    return bool(correo) and bool(EMAIL_RE.match(correo.strip())) and len(correo.strip()) <= 254


def enviar_correo(
    destino: str,
    asunto: str,
    cuerpo: str,
    adjuntos: list[tuple[bytes, str, str]] | None = None,
    *,
    config: ConfigSMTP | None = None,
) -> str:
    """
    Envía un correo con adjuntos `(bytes, nombre_archivo, mime)`.

    Devuelve ENVIADO_SMTP si el servidor lo aceptó o REGISTRADO_SIN_SMTP si no hay
    SMTP_HOST (modo demostración). Lanza ValueError si el destino no es válido y
    ErrorCorreo si el servidor falla (para que el llamador no marque "enviado").
    """
    destino = (destino or "").strip()
    if not correo_valido(destino):
        raise ValueError("Ingresa un correo electrónico válido.")
    cfg = config or config_smtp()
    if not cfg.habilitado:
        logger.info("SMTP no configurado: envío a %s registrado sin enviar (%s)", destino, asunto)
        return SIN_SMTP

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = cfg.remitente
    msg["To"] = destino
    msg["Message-ID"] = make_msgid(domain="freshtrack.mx")
    msg.set_content(cuerpo)
    for datos, nombre, mime in adjuntos or []:
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(datos, maintype=maintype, subtype=subtype or "octet-stream", filename=nombre)

    try:
        if cfg.port == 465:
            with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=15) as srv:
                if cfg.user and cfg.password:
                    srv.login(cfg.user, cfg.password)
                srv.send_message(msg)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as srv:
                if cfg.tls:
                    srv.starttls()
                if cfg.user and cfg.password:
                    srv.login(cfg.user, cfg.password)
                srv.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Fallo SMTP enviando a %s vía %s:%s: %s", destino, cfg.host, cfg.port, exc)
        raise ErrorCorreo(f"El servidor de correo no aceptó el envío ({type(exc).__name__}).") from exc
    logger.info("Correo enviado a %s vía %s:%s (%s)", destino, cfg.host, cfg.port, asunto)
    return ENVIADO
