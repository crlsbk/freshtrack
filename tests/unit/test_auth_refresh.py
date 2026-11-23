"""POST /api/v1/auth/refresh: renueva el JWT y revoca el jti anterior."""

from __future__ import annotations

import jwt
import pytest

from app.config import Config
from app.services import cache_service
from app.services.auth_service import app as auth_app
from app.services.common import auth as auth_mod


def _token(jti="jti-viejo"):
    return jwt.encode(
        {"sub": "u-1", "rol": "buyer", "email": "b@freshtrack.mx", "nombre": "Ana Compradora",
         "id_locacion": 3, "jti": jti},
        Config.JWT_SECRET_KEY, algorithm="HS256",
    )


@pytest.fixture()
def ctx(redis_falso, monkeypatch):
    def decodificar(token):
        try:
            return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None

    revocados, emitidos = [], []

    def crear_token(usuario, ip=None, user_agent=None):
        emitidos.append(usuario)
        cache_service.crear_sesion_redis("jti-nuevo", {"id_usuario": usuario["id_usuario"]})
        return "token-nuevo", "jti-nuevo"

    monkeypatch.setattr(auth_mod, "decodificar_token", decodificar)
    monkeypatch.setattr(auth_app, "crear_token", crear_token)
    monkeypatch.setattr(auth_app, "revocar_token", lambda jti: revocados.append(jti))
    cache_service.crear_sesion_redis("jti-viejo", {"id_usuario": "u-1"})
    return auth_app.app.test_client(), revocados, emitidos


def test_refresh_devuelve_token_nuevo_y_revoca_el_anterior(ctx):
    cliente, revocados, emitidos = ctx
    r = cliente.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200
    datos = r.get_json()
    assert datos["token"] == "token-nuevo" and datos["jti"] == "jti-nuevo"
    assert datos["token_type"] == "Bearer"
    assert datos["expira_en_segundos"] > 0
    assert datos["usuario"] == {"id_usuario": "u-1", "email": "b@freshtrack.mx", "nombre": "Ana Compradora",
                                "rol": "buyer", "id_locacion": 3}
    assert revocados == ["jti-viejo"]
    assert emitidos[0]["rol_clave"] == "buyer"


def test_refresh_sin_token_401(ctx):
    cliente, revocados, _ = ctx
    r = cliente.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.get_json()["error"] == "token_requerido"
    assert revocados == []


def test_refresh_xml_raiz_auth_response(ctx):
    cliente, _, _ = ctx
    r = cliente.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {_token()}", "Accept": "application/xml"})
    assert r.status_code == 200
    assert r.get_data(as_text=True).lstrip().split("<auth_response", 1)[0].count("<") <= 1
    assert "<auth_response" in r.get_data(as_text=True)
