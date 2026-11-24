"""Usuarios con rol supplier: solo operan sobre recursos de su propio proveedor."""

from __future__ import annotations

import pytest

from app.services import cache_service
from app.services.common import auth as auth_mod

SUPPLIER = {"sub": "u-prov", "rol": "supplier", "jti": "j-prov", "email": "p@x.mx"}
BUYER = {"sub": "u-buy", "rol": "buyer", "jti": "j-buy", "email": "b@x.mx"}
H = {"Authorization": "Bearer x"}


@pytest.fixture()
def catalogo(redis_falso, monkeypatch):
    from app.services.catalog_service import app as mod

    cache_service.crear_sesion_redis("j-prov", {"id_usuario": "u-prov"})
    cache_service.crear_sesion_redis("j-buy", {"id_usuario": "u-buy"})
    return mod, mod.app.test_client()


def _como(monkeypatch, payload, proveedor):
    monkeypatch.setattr(auth_mod, "decodificar_token", lambda t: dict(payload))
    monkeypatch.setattr(auth_mod, "proveedor_del_usuario", lambda u: proveedor)


@pytest.mark.parametrize("metodo", ["patch", "delete"])
def test_supplier_no_modifica_producto_ajeno(catalogo, monkeypatch, metodo):
    mod, c = catalogo
    _como(monkeypatch, SUPPLIER, 3)
    monkeypatch.setattr(mod, "one", lambda *a, **k: {"precio_venta": 10, "precio_costo": 5, "id_proveedor": 7})
    r = getattr(c, metodo)("/api/v1/catalog/products/1", json={"precio_venta": 12}, headers=H)
    assert r.status_code == 403 and r.get_json()["error"] == "proveedor_no_autorizado"


def test_supplier_sin_proveedor_asignado_no_opera(catalogo, monkeypatch):
    mod, c = catalogo
    _como(monkeypatch, SUPPLIER, None)
    monkeypatch.setattr(mod, "one", lambda *a, **k: {"precio_venta": 10, "precio_costo": 5, "id_proveedor": 3})
    r = c.patch("/api/v1/catalog/products/1", json={"precio_venta": 12}, headers=H)
    assert r.status_code == 403 and r.get_json()["error"] == "proveedor_no_asignado"


def test_supplier_no_regala_su_producto_a_otro_proveedor(catalogo, monkeypatch):
    mod, c = catalogo
    _como(monkeypatch, SUPPLIER, 3)
    monkeypatch.setattr(mod, "one", lambda *a, **k: {"precio_venta": 10, "precio_costo": 5, "id_proveedor": 3, "x": 1})
    r = c.patch("/api/v1/catalog/products/1", json={"id_proveedor": 7}, headers=H)
    assert r.status_code == 403


def test_listado_de_supplier_filtra_por_su_proveedor(catalogo, monkeypatch):
    mod, c = catalogo
    _como(monkeypatch, SUPPLIER, 3)
    monkeypatch.setattr(mod, "decodificar_token", lambda t: dict(SUPPLIER))
    vistas = []
    monkeypatch.setattr(mod, "query", lambda sql, **p: vistas.append((sql, p)) or [])
    assert c.get("/api/v1/catalog/products", headers=H).status_code == 200
    assert vistas and vistas[0][1].get("prov") == 3
    # Sin token (catálogo público) no se filtra.
    vistas.clear()
    assert c.get("/api/v1/catalog/products?q=zz").status_code == 200
    assert "prov" not in vistas[0][1]


def test_otros_roles_no_se_restringen_por_proveedor(redis_falso, monkeypatch):
    from flask import Flask, g

    app = Flask(__name__)
    with app.test_request_context():
        g.usuario_actual = dict(BUYER)
        auth_mod.validar_alcance_proveedor(99)  # no lanza
        assert auth_mod.proveedor_forzado() is None


def test_usuario_supplier_requiere_proveedor(monkeypatch):
    from app.repos import catalogo as repo

    respuestas = iter(["supplier"])
    monkeypatch.setattr(repo, "escalar", lambda *a, **k: next(respuestas))
    with pytest.raises(ValueError):
        repo._proveedor_para_rol(6, {"id_proveedor": ""})
    monkeypatch.setattr(repo, "escalar", lambda *a, **k: "planner")
    assert repo._proveedor_para_rol(3, {"id_proveedor": "4"}) is None  # otros roles: siempre NULL
