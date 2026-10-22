"""Cada microservicio expone /health, Swagger y una especificación OpenAPI completa y versionada."""

from __future__ import annotations

import importlib

import pytest

SERVICIOS = ["auth", "catalog", "inventory", "commercial", "asn", "planning", "alerts", "audit"]


@pytest.fixture(scope="module", params=SERVICIOS)
def spec(request):
    modulo = importlib.import_module(f"app.services.{request.param}_service.app")
    cliente = modulo.app.test_client()
    resp = cliente.get("/api/v1/openapi.json")
    assert resp.status_code == 200
    assert cliente.get("/api/v1/docs").status_code == 200
    return request.param, resp.get_json()


def test_rutas_versionadas_y_health(spec):
    _, s = spec
    assert "/health" in s["paths"]
    negocio = [p for p in s["paths"] if p not in ("/health",) and "contracts" not in p]
    assert negocio and all(p.startswith("/api/v1/") for p in negocio)


def test_endpoints_protegidos_declaran_jwt_y_errores(spec):
    _, s = spec
    for ruta, ops in s["paths"].items():
        for metodo, op in ops.items():
            assert op["summary"], f"{metodo} {ruta} sin resumen"
            assert "500" in op["responses"]
            if "security" in op:
                assert "401" in op["responses"], f"{metodo} {ruta}"


def test_cuerpos_con_ejemplo_json_y_xml(spec):
    _, s = spec
    for ruta, ops in s["paths"].items():
        for metodo, op in ops.items():
            if "requestBody" in op:
                contenido = op["requestBody"]["content"]
                assert contenido["application/json"]["example"], f"{metodo} {ruta}"
                assert contenido["application/xml"]["example"].startswith("<?xml"), f"{metodo} {ruta}"


def test_respuestas_en_json_y_xml(spec):
    _, s = spec
    for ops in s["paths"].values():
        for op in ops.values():
            for r in op["responses"].values():
                assert {"application/json", "application/xml"} <= set(r["content"])


def test_usa_metodos_http_variados():
    metodos = set()
    for nombre in SERVICIOS:
        modulo = importlib.import_module(f"app.services.{nombre}_service.app")
        for regla in modulo.app.url_map.iter_rules():
            metodos |= regla.methods
    assert {"GET", "POST", "PUT", "PATCH", "DELETE"} <= metodos
