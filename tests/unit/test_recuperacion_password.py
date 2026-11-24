"""Recuperación de contraseña por correo (app/domain/recuperacion.py y /recuperar, /restablecer)."""

from __future__ import annotations

import re

import pytest

from app.domain import recuperacion
from app.services import cache_service

USUARIO = {"id_usuario": "11111111-1111-1111-1111-111111111111", "email": "gerente@freshtrack.mx",
           "nombre_completo": "Gerente Demo"}


@pytest.fixture()
def entorno(redis_falso, monkeypatch):
    """Sin PostgreSQL ni SMTP: usuario en memoria, correos capturados, cambios registrados."""
    correos, cambios, revocadas, auditados = [], [], [], []

    monkeypatch.setattr(
        recuperacion, "_usuario_activo_por_email",
        lambda email: dict(USUARIO) if email == USUARIO["email"] else None,
    )
    monkeypatch.setattr(
        recuperacion, "_usuario_por_id",
        lambda i: dict(USUARIO, estado_activo=True) if i == USUARIO["id_usuario"] else None,
    )
    monkeypatch.setattr(recuperacion, "_enviar", lambda destino, nombre, enlace: correos.append((destino, enlace)))
    monkeypatch.setattr(recuperacion, "_auditar", lambda accion, **kw: auditados.append(accion))

    from app.repos import catalogo

    def restablecer_password(id_usuario, nueva, usuario, descripcion=""):
        catalogo.validar_politica_password(nueva)
        cambios.append((id_usuario, nueva))
        revocadas.append(id_usuario)  # la función real llama a revocar_sesiones_usuario

    monkeypatch.setattr(catalogo, "restablecer_password", restablecer_password)
    return {"redis": redis_falso, "correos": correos, "cambios": cambios, "revocadas": revocadas,
            "auditados": auditados}


def _enlace(t):
    return f"http://localhost/restablecer/{t}"


def _token_de(entorno):
    return entorno["correos"][-1][1].rsplit("/", 1)[1]


def test_correo_desconocido_no_genera_token_ni_correo(entorno):
    assert recuperacion.solicitar("nadie@ejemplo.com", _enlace, ip="1.1.1.1") == "SIN_CUENTA"
    assert entorno["correos"] == []
    assert entorno["redis"].keys("pwdreset:*") == []


def test_token_se_guarda_hasheado_con_ttl(entorno):
    assert recuperacion.solicitar("Gerente@FreshTrack.mx", _enlace, ip="1.1.1.1") == "ENVIADO"
    token = _token_de(entorno)
    claves = entorno["redis"].keys("pwdreset:*")
    assert claves == [f"pwdreset:{recuperacion.hash_token(token)}"]
    assert token not in claves[0]
    assert entorno["redis"].get(claves[0]) == USUARIO["id_usuario"]
    assert 0 < entorno["redis"].ttl(claves[0]) <= 30 * 60
    assert "REQUEST_PASSWORD_RESET" in entorno["auditados"]


def test_restablecer_es_de_un_solo_uso_y_revoca_sesiones(entorno):
    recuperacion.solicitar(USUARIO["email"], _enlace)
    token = _token_de(entorno)
    assert recuperacion.token_vigente(token)
    recuperacion.restablecer(token, "NuevaClave2026", "NuevaClave2026", ip="1.1.1.1")
    assert entorno["cambios"] == [(USUARIO["id_usuario"], "NuevaClave2026")]
    assert entorno["revocadas"] == [USUARIO["id_usuario"]]
    assert "RESET_PASSWORD" in entorno["auditados"]
    assert not recuperacion.token_vigente(token)
    with pytest.raises(recuperacion.TokenInvalido):
        recuperacion.restablecer(token, "OtraClave2026", "OtraClave2026")


def test_politica_y_confirmacion_no_gastan_el_token(entorno):
    recuperacion.solicitar(USUARIO["email"], _enlace)
    token = _token_de(entorno)
    with pytest.raises(ValueError, match="8 caracteres"):
        recuperacion.restablecer(token, "corta", "corta")
    with pytest.raises(ValueError, match="confirmación"):
        recuperacion.restablecer(token, "NuevaClave2026", "Distinta2026")
    assert entorno["cambios"] == []
    assert recuperacion.token_vigente(token)


def test_token_inventado_o_vencido(entorno):
    with pytest.raises(recuperacion.TokenInvalido):
        recuperacion.restablecer("inventado", "NuevaClave2026", "NuevaClave2026")
    recuperacion.solicitar(USUARIO["email"], _enlace)
    token = _token_de(entorno)
    entorno["redis"].delete(f"pwdreset:{recuperacion.hash_token(token)}")  # TTL cumplido
    assert not recuperacion.token_vigente(token)


def test_limite_por_correo(entorno):
    for _ in range(recuperacion.LIMITE_POR_CORREO):
        recuperacion.solicitar(USUARIO["email"], _enlace, ip="2.2.2.2")
    with pytest.raises(recuperacion.LimiteExcedido):
        recuperacion.solicitar(USUARIO["email"], _enlace, ip="2.2.2.2")


def test_sin_redis_falla_cerrado(monkeypatch):
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: None)
    with pytest.raises(recuperacion.RecuperacionNoDisponible):
        recuperacion.solicitar(USUARIO["email"], _enlace)
    with pytest.raises(recuperacion.RecuperacionNoDisponible):
        recuperacion.restablecer("x", "NuevaClave2026", "NuevaClave2026")


# --- Vistas web ---------------------------------------------------------------
@pytest.fixture()
def cliente(entorno, monkeypatch):
    monkeypatch.setenv("AGREGADOS_AUTO_REFRESCO", "false")
    from app import create_app

    app = create_app()
    return app.test_client()


def _csrf(c, ruta):
    html = c.get(ruta).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def test_login_muestra_enlace_de_recuperacion(cliente):
    assert "¿Olvidaste tu contraseña?" in cliente.get("/login").get_data(as_text=True)


def test_vista_responde_igual_exista_o_no_la_cuenta(cliente, entorno):
    t = _csrf(cliente, "/recuperar")
    r1 = cliente.post("/recuperar", data={"email": "nadie@ejemplo.com", "csrf_token": t})
    r2 = cliente.post("/recuperar", data={"email": USUARIO["email"], "csrf_token": t})
    assert r1.status_code == r2.status_code == 200
    assert recuperacion.MENSAJE_NEUTRO in r1.get_data(as_text=True)
    assert recuperacion.MENSAJE_NEUTRO in r2.get_data(as_text=True)
    assert len(entorno["correos"]) == 1


def test_vista_exige_csrf(cliente):
    cliente.get("/recuperar")
    assert cliente.post("/recuperar", data={"email": USUARIO["email"]}).status_code == 400


def test_vista_restablecer_flujo_completo(cliente, entorno):
    recuperacion.solicitar(USUARIO["email"], _enlace)
    token = _token_de(entorno)
    ruta = f"/restablecer/{token}"
    t = _csrf(cliente, ruta)
    r = cliente.post(ruta, data={"password": "NuevaClave2026", "confirmacion": "NuevaClave2026", "csrf_token": t})
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    r2 = cliente.get(ruta)
    assert r2.status_code == 400 and "ya se usó o venció" in r2.get_data(as_text=True)


def test_vista_sin_redis_mensaje_amable(cliente, monkeypatch):
    t = _csrf(cliente, "/recuperar")
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: None)
    r = cliente.post("/recuperar", data={"email": USUARIO["email"], "csrf_token": t})
    assert r.status_code == 503 and "no está disponible" in r.get_data(as_text=True)
