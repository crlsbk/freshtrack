"""Mecanismo común de autenticación/autorización (@requiere_auth) y rate limiting con Redis."""

from __future__ import annotations

import jwt
import pytest
from flask import Flask, g

from app.config import Config
from app.services import cache_service
from app.services.common import auth as auth_mod
from app.services.common.auth import requiere_auth
from app.services.common.rate_limit import limite_tasa
from app.services.common.servicio import crear_servicio


def _token(rol="store_manager", jti="jti-1"):
    return jwt.encode({"sub": "u-1", "rol": rol, "email": "x@freshtrack.mx", "jti": jti}, Config.JWT_SECRET_KEY, algorithm="HS256")


@pytest.fixture()
def cliente(redis_falso, monkeypatch):
    # Sustituye la verificación contra PostgreSQL: solo se valida la firma.
    def decodificar(token):
        try:
            return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None

    monkeypatch.setattr(auth_mod, "decodificar_token", decodificar)
    app = crear_servicio("svc-prueba", "Prueba", "Servicio de prueba", dependencias=("redis",))

    @app.get("/libre")
    @requiere_auth()
    def libre():
        return {"usuario": g.usuario_actual["email"]}

    @app.get("/solo-auditor")
    @requiere_auth("auditor")
    def solo_auditor():
        return {"ok": True}

    @app.get("/limitado")
    @limite_tasa(limite=2, ventana_segundos=60)
    def limitado():
        return {"ok": True}

    cache_service.crear_sesion_redis("jti-1", {"id_usuario": "u-1"})
    return app.test_client()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_sin_token_401(cliente):
    r = cliente.get("/libre")
    assert r.status_code == 401
    assert r.get_json()["error"] == "token_requerido"


def test_token_manipulado_401(cliente):
    token = _token()[:-3] + "abc"
    r = cliente.get("/libre", headers=_auth(token))
    assert r.status_code == 401 and r.get_json()["error"] == "token_invalido"


def test_token_expirado_401(cliente):
    token = jwt.encode({"sub": "u", "rol": "admin", "jti": "jti-1", "exp": 1}, Config.JWT_SECRET_KEY, algorithm="HS256")
    assert cliente.get("/libre", headers=_auth(token)).status_code == 401


def test_token_valido_200(cliente):
    r = cliente.get("/libre", headers=_auth(_token()))
    assert r.status_code == 200 and r.get_json()["usuario"] == "x@freshtrack.mx"
    assert r.headers["X-Correlation-Id"]


def test_token_revocado_en_denylist_401(cliente):
    cache_service.revocar_jwt("jti-1")
    r = cliente.get("/libre", headers=_auth(_token()))
    assert r.status_code == 401 and r.get_json()["error"] == "token_revocado"


def test_sesion_inexistente_en_redis_401(cliente):
    r = cliente.get("/libre", headers=_auth(_token(jti="sin-sesion")))
    assert r.status_code == 401 and r.get_json()["error"] == "sesion_inexistente"


def test_cerrar_sesiones_usuario_invalida_tokens(cliente):
    assert cache_service.cerrar_sesiones_usuario("u-1") == 1
    assert cache_service.esta_jwt_revocado("jti-1")
    assert cliente.get("/libre", headers=_auth(_token())).status_code == 401


def test_rol_no_permitido_403(cliente):
    r = cliente.get("/solo-auditor", headers=_auth(_token(rol="store_manager")))
    assert r.status_code == 403
    assert "auditor" in r.get_json()["detalles"]["roles_permitidos"]


@pytest.mark.parametrize("rol", ["auditor", "admin"])
def test_rol_permitido_y_admin_200(cliente, rol):
    assert cliente.get("/solo-auditor", headers=_auth(_token(rol=rol))).status_code == 200


def test_rate_limit_429_con_cabeceras(cliente):
    assert cliente.get("/limitado").status_code == 200
    r2 = cliente.get("/limitado")
    assert r2.headers["X-RateLimit-Remaining"] == "0"
    r3 = cliente.get("/limitado")
    assert r3.status_code == 429
    assert int(r3.headers["Retry-After"]) > 0
    assert r3.get_json()["error"] == "limite_excedido"


def test_errores_http_estandarizados(cliente):
    r = cliente.get("/no-existe", headers={"Accept": "application/xml"})
    assert r.status_code == 404 and b"<error_response>" in r.data
    assert cliente.post("/libre").status_code == 405


def test_error_no_controlado_no_expone_traza(redis_falso):
    app = crear_servicio("svc-x", "X", "X", dependencias=())

    @app.get("/falla")
    def falla():
        raise RuntimeError("detalle interno secreto")

    r = app.test_client().get("/falla")
    assert r.status_code == 500
    assert "secreto" not in r.get_data(as_text=True)
    assert r.get_json()["error"] == "error_interno"


def test_health_reporta_dependencias(redis_falso):
    app = crear_servicio("svc-h", "H", "H", dependencias=("redis",))
    r = app.test_client().get("/health")
    assert r.status_code == 200
    assert r.get_json()["dependencies"] == {"redis": True}
