"""Correo saliente (app/services/mailer.py) y envío de la Hoja QR del ASN por svc-asn."""

from __future__ import annotations

import smtplib

import jwt
import pytest

from app.config import Config
from app.services import cache_service, mailer
from app.services.common import auth as auth_mod


class SMTPFalso:
    """Sustituye smtplib.SMTP: guarda lo que se enviaría."""

    enviados: list = []
    falla: Exception | None = None

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.tls = False
        self.login_con = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, pwd):
        self.login_con = (user, pwd)

    def send_message(self, msg):
        if SMTPFalso.falla:
            raise SMTPFalso.falla
        SMTPFalso.enviados.append((self, msg))


@pytest.fixture()
def smtp_falso(monkeypatch):
    SMTPFalso.enviados = []
    SMTPFalso.falla = None
    monkeypatch.setattr(smtplib, "SMTP", SMTPFalso)
    return SMTPFalso


def _cfg(**kw):
    base = dict(host="mail", port=1025, user="", password="", remitente="FreshTrack <no-reply@freshtrack.mx>", tls=False)
    base.update(kw)
    return mailer.ConfigSMTP(**base)


def test_sin_smtp_host_solo_registra(smtp_falso):
    assert mailer.enviar_correo("a@b.mx", "Asunto", "Hola", config=_cfg(host="")) == mailer.SIN_SMTP
    assert smtp_falso.enviados == []


def test_envia_pdf_adjunto_a_mailpit_sin_tls(smtp_falso):
    estado = mailer.enviar_correo("prov@ejemplo.com", "Hoja QR", "Cuerpo",
                                  [(b"%PDF-1.4 x", "ASN-1_etiquetas.pdf", "application/pdf")], config=_cfg())
    assert estado == mailer.ENVIADO
    srv, msg = smtp_falso.enviados[0]
    assert (srv.host, srv.port, srv.tls, srv.login_con) == ("mail", 1025, False, None)
    assert msg["To"] == "prov@ejemplo.com" and msg["Subject"] == "Hoja QR"
    adj = list(msg.iter_attachments())
    assert len(adj) == 1 and adj[0].get_filename() == "ASN-1_etiquetas.pdf"
    assert adj[0].get_content_type() == "application/pdf" and adj[0].get_content() == b"%PDF-1.4 x"


def test_smtp_externo_usa_starttls_y_login(smtp_falso):
    mailer.enviar_correo("a@b.mx", "x", "y", config=_cfg(host="smtp.gmail.com", port=587, user="u@gmail.com",
                                                          password="clave", tls=True))
    srv, _ = smtp_falso.enviados[0]
    assert srv.tls is True and srv.login_con == ("u@gmail.com", "clave")


def test_correo_invalido_lanza_valueerror(smtp_falso):
    with pytest.raises(ValueError):
        mailer.enviar_correo("no-es-correo", "x", "y", config=_cfg())


def test_fallo_del_servidor_lanza_errorcorreo(smtp_falso):
    smtp_falso.falla = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    with pytest.raises(mailer.ErrorCorreo):
        mailer.enviar_correo("a@b.mx", "x", "y", config=_cfg())


# --- svc-asn POST /api/v1/asn/<folio>/send-email ------------------------------------
@pytest.fixture()
def cliente_asn(redis_falso, monkeypatch):
    def decodificar(token):
        try:
            return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None

    monkeypatch.setattr(auth_mod, "decodificar_token", decodificar)
    from app.services.asn_service import app as asn_mod

    cache_service.crear_sesion_redis("jti-asn", {"id_usuario": "u-1"})
    return asn_mod, asn_mod.app.test_client()


def _auth(rol):
    tok = jwt.encode({"sub": "u-1", "rol": rol, "email": "x@freshtrack.mx", "jti": "jti-asn"},
                     Config.JWT_SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def test_endpoint_envia_hoja_qr_en_xml(cliente_asn, monkeypatch):
    asn_mod, c = cliente_asn
    llamadas = []

    def falso(folio, correo, usuario, mensaje_extra=None):
        llamadas.append((folio, correo, mensaje_extra))
        return {"folio_asn": folio, "folio_oc": "OC-1", "correo_envio": correo,
                "estado_envio_correo": mailer.ENVIADO, "enviado_real": True}

    monkeypatch.setattr(asn_mod.dom_recepcion, "enviar_hoja_asn_correo", falso)
    r = c.post("/api/v1/asn/ASN-2026-000001/send-email",
               data=b"<send_email_request><correo>prov@ejemplo.com</correo><mensaje>Hola</mensaje></send_email_request>",
               headers={**_auth("supplier"), "Content-Type": "application/xml", "Accept": "application/xml"})
    assert r.status_code == 200, r.data
    assert b"<send_email_result>" in r.data and b"ENVIADO_SMTP" in r.data
    assert llamadas == [("ASN-2026-000001", "prov@ejemplo.com", "Hola")]


def test_endpoint_rechaza_correo_invalido_por_xsd(cliente_asn):
    _, c = cliente_asn
    r = c.post("/api/v1/asn/ASN-1/send-email", data=b"<send_email_request><correo>nope</correo></send_email_request>",
               headers={**_auth("buyer"), "Content-Type": "application/xml"})
    assert r.status_code == 400 and r.get_json()["error"] == "xml_no_cumple_contrato"


def test_endpoint_smtp_caido_responde_502(cliente_asn, monkeypatch):
    asn_mod, c = cliente_asn

    def falla(*a, **k):
        raise asn_mod.dom_recepcion.ErrorRecepcion("El servidor de correo no aceptó el envío.",
                                                   codigo="correo_no_enviado", http_status=502)

    monkeypatch.setattr(asn_mod.dom_recepcion, "enviar_hoja_asn_correo", falla)
    r = c.post("/api/v1/asn/ASN-1/send-email", json={"correo": "a@b.mx"}, headers=_auth("warehouse"))
    assert r.status_code == 502 and r.get_json()["error"] == "correo_no_enviado"


def test_endpoint_rol_sin_permiso_403(cliente_asn):
    _, c = cliente_asn
    r = c.post("/api/v1/asn/ASN-1/send-email", json={"correo": "a@b.mx"}, headers=_auth("auditor"))
    assert r.status_code == 403


def test_puerto_587_siempre_usa_starttls_aunque_smtp_tls_sea_false(monkeypatch, smtp_falso):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_TLS", "false")
    monkeypatch.setenv("SMTP_USER", "u@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "clave")
    cfg = mailer.config_smtp()
    assert cfg.tls is True
    mailer.enviar_correo("a@b.mx", "x", "y", config=cfg)
    srv, _ = smtp_falso.enviados[0]
    assert srv.tls is True and srv.login_con == ("u@gmail.com", "clave")


def test_mailpit_1025_sin_tls(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setenv("SMTP_TLS", "false")
    assert mailer.config_smtp().tls is False
