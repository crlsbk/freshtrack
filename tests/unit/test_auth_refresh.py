"""POST /api/v1/auth/refresh: rota access + refresh token (refresh en el cuerpo o Bearer vigente)."""

from __future__ import annotations

import pytest

from app.services.auth_service import app as auth_app

USUARIO = {"id_usuario": "u-1", "email": "b@freshtrack.mx", "nombre_completo": "Ana Compradora",
           "rol_clave": "buyer", "id_locacion": 3, "estado_activo": True}
NUEVA = {"token": "token-nuevo", "jti": "jti-nuevo", "refresh_token": "rt-nuevo-" + "x" * 30,
         "expira_en_segundos": 900, "refresh_expira_en_segundos": 27000, "familia": "f-1", "usuario": USUARIO}
RT_VIEJO = "rt-viejo-" + "a" * 30


@pytest.fixture()
def ctx(redis_falso, monkeypatch):
    llamadas = []

    def renovar(**kw):
        llamadas.append(kw)
        if kw.get("refresh_token") == RT_VIEJO or kw.get("jti_vigente") == "jti-viejo":
            return dict(NUEVA)
        return None

    monkeypatch.setattr(auth_app, "renovar_sesion", renovar)
    monkeypatch.setattr(auth_app, "decodificar_token",
                        lambda t: {"jti": "jti-viejo", "sub": "u-1"} if t == "access-vigente" else None)
    return auth_app.app.test_client(), llamadas


def test_refresh_con_refresh_token_en_el_cuerpo(ctx):
    cliente, llamadas = ctx
    r = cliente.post("/api/v1/auth/refresh", json={"refresh_token": RT_VIEJO})
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["token"] == "token-nuevo" and datos["refresh_token"] == NUEVA["refresh_token"]
    assert datos["token_type"] == "Bearer" and datos["expira_en_segundos"] == 900
    assert datos["refresh_expira_en_segundos"] == 27000
    assert datos["usuario"] == {"id_usuario": "u-1", "email": "b@freshtrack.mx", "nombre": "Ana Compradora",
                                "rol": "buyer", "id_locacion": 3}
    assert llamadas[0]["refresh_token"] == RT_VIEJO and llamadas[0]["jti_vigente"] is None


def test_refresh_en_xml_valida_contrato(ctx):
    cliente, _ = ctx
    cuerpo = f"<refresh_request><refresh_token>{RT_VIEJO}</refresh_token></refresh_request>"
    r = cliente.post("/api/v1/auth/refresh", data=cuerpo,
                     headers={"Content-Type": "application/xml", "Accept": "application/xml"})
    assert r.status_code == 200 and "<auth_response" in r.get_data(as_text=True)
    malo = "<refresh_request><refresh_token>a b</refresh_token></refresh_request>"
    r = cliente.post("/api/v1/auth/refresh", data=malo, headers={"Content-Type": "application/xml"})
    assert r.status_code == 400


def test_refresh_compatible_con_bearer_vigente(ctx):
    cliente, llamadas = ctx
    r = cliente.post("/api/v1/auth/refresh", headers={"Authorization": "Bearer access-vigente"})
    assert r.status_code == 200 and r.get_json()["jti"] == "jti-nuevo"
    assert llamadas[0]["jti_vigente"] == "jti-viejo"


def test_refresh_sin_credenciales_o_rechazado_401(ctx):
    cliente, llamadas = ctx
    r = cliente.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.get_json()["error"] == "refresh_invalido"
    assert llamadas == []
    r = cliente.post("/api/v1/auth/refresh", json={"refresh_token": "otro-" + "z" * 30})
    assert r.status_code == 401 and r.get_json()["error"] == "refresh_invalido"
