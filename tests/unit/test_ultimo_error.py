"""«Último error registrado» por microservicio (app/services/registro_errores.py y /ops/status)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app.domain import monitoreo as dom_monitoreo
from app.services import cache_service, clientes, registro_errores
from app.services.common import servicio
from app.services.common.response import error_response

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture()
def svc(redis_falso, monkeypatch):
    monkeypatch.setattr(servicio, "_verificar_dependencia", lambda dep: True)
    app = servicio.crear_servicio("svc-prueba", "Prueba", "Prueba", dependencias=("postgres", "redis"))

    @app.get("/api/v1/prueba/explota/<int:id_x>")
    def explota(id_x):
        raise RuntimeError("SELECT secreto FROM tabla_interna")  # no debe salir al panel

    @app.get("/api/v1/prueba/sin-mongo")
    def sin_mongo():
        return error_response(503, "mongo_no_disponible", "MongoDB no está disponible en este momento.")

    @app.get("/api/v1/prueba/negocio")
    def negocio():
        return error_response(409, "regla_negocio", "No aplica")

    return app


def test_error_no_controlado_queda_registrado_sin_detalles_internos(svc, redis_falso):
    r = svc.test_client().get("/api/v1/prueba/explota/42", headers={"X-Correlation-Id": "cid-123"})
    assert r.status_code == 500
    ultimo = registro_errores.ultimo_error("svc-prueba")
    assert ultimo["code"] == "error_interno" and ultimo["status"] == 500
    assert ultimo["endpoint"] == "GET /api/v1/prueba/explota/<int:id_x>"  # regla, sin el id real
    assert ultimo["correlation_id"] == r.get_json()["correlation_id"]
    assert "SELECT" not in json.dumps(ultimo)


def test_error_response_5xx_si_y_4xx_no(svc):
    c = svc.test_client()
    c.get("/api/v1/prueba/negocio")
    assert registro_errores.ultimo_error("svc-prueba") is None
    c.get("/api/v1/prueba/sin-mongo")
    assert registro_errores.ultimo_error("svc-prueba")["code"] == "mongo_no_disponible"


def test_lista_acotada_y_repeticiones(redis_falso):
    for i in range(registro_errores.MAXIMO + 5):
        registro_errores.registrar_error("svc-x", endpoint=f"GET /e{i}", codigo="c", mensaje="m", status=500)
    assert redis_falso.llen("monitor:errores:svc-x") == registro_errores.MAXIMO
    assert redis_falso.ttl("monitor:errores:svc-x") > 0
    assert registro_errores.ultimo_error("svc-x")["endpoint"] == f"GET /e{registro_errores.MAXIMO + 4}"
    registro_errores.registrar_error("svc-x", endpoint="GET /e24", codigo="c", mensaje="m", status=500)
    assert registro_errores.ultimo_error("svc-x")["repeticiones"] == 2
    assert redis_falso.llen("monitor:errores:svc-x") == registro_errores.MAXIMO


def test_sin_redis_sin_datos(monkeypatch):
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: None)
    assert registro_errores.registrar_error("svc-x", endpoint="e", codigo="c", mensaje="m") is False
    assert registro_errores.ultimos_errores("svc-x") is None


def test_health_expone_last_error_en_json_y_xml_valido(svc):
    c = svc.test_client()
    c.get("/api/v1/prueba/sin-mongo")
    datos = c.get("/health").get_json()
    assert datos["last_error"]["code"] == "mongo_no_disponible"
    xml = c.get("/health", headers={"Accept": "application/xml"}).get_data(as_text=True)
    assert ET.fromstring(xml).findtext("last_error/code") == "mongo_no_disponible"
    xmlschema = pytest.importorskip("xmlschema")
    assert xmlschema.XMLSchema(str(RAIZ / "contracts" / "xsd" / "service_health.xsd")).is_valid(xml)


def test_monitor_registra_health_fallido_y_lo_muestra(redis_falso, monkeypatch):
    dom_monitoreo._limpiar_historial()
    monkeypatch.setattr(cache_service, "obtener_contadores", lambda *a, **k: {})

    def llamar(clave, metodo, ruta, timeout=None):
        if clave == "asn":
            return 503, {"service": "svc-asn", "status": "DEGRADED", "dependencies": {"postgres": True, "mongo": False}}
        if clave == "audit":
            return 0, None
        return 200, {"service": f"svc-{clave}", "status": "HEALTHY", "dependencies": {"postgres": True}}

    monkeypatch.setattr(clientes, "llamar", llamar)
    snap = dom_monitoreo.verificar_plataforma(guardar_historial=False)
    por_nombre = {s["nombre"]: s for s in snap["servicios"]}
    asn = por_nombre["svc-asn"]["ultimo_error"]
    assert asn["code"] == "dependencia_caida" and "MongoDB" in asn["message"] and asn["correlation_id"]
    assert por_nombre["svc-audit"]["ultimo_error"]["code"] == "servicio_sin_respuesta"
    assert por_nombre["svc-auth"]["ultimo_error"] is None and por_nombre["svc-auth"]["ultimo_error_disponible"]
    # Un segundo refresco con la misma falla no desplaza otros errores: cuenta repeticiones.
    snap = dom_monitoreo.verificar_plataforma(guardar_historial=False)
    asn2 = {s["nombre"]: s for s in snap["servicios"]}["svc-asn"]
    assert asn2["ultimo_error"]["repeticiones"] == 2 and len(asn2["errores_recientes"]) == 1


def test_monitor_sin_redis_muestra_sin_datos(monkeypatch):
    dom_monitoreo._limpiar_historial()
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: None)
    monkeypatch.setattr(cache_service, "obtener_contadores", lambda *a, **k: {})
    monkeypatch.setattr(clientes, "llamar", lambda *a, **k: (0, None))
    snap = dom_monitoreo.verificar_plataforma(guardar_historial=False)
    assert all(s["ultimo_error"] is None and s["ultimo_error_disponible"] is False for s in snap["servicios"])
