"""Pruebas unitarias para /health enriquecido de microservicios y el panel oculto /ops/status."""

from __future__ import annotations

import re

import importlib
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

os.environ.setdefault("SECRET_KEY", "clave-de-pruebas-monitoreo-0123456789")
os.environ.setdefault("JWT_SECRET_KEY", "jwt-de-pruebas-monitoreo-0123456789")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_backend:x@127.0.0.1:1/inexistente")
os.environ.setdefault("MONITOR_USER", "ops_test")
os.environ.setdefault("MONITOR_PASSWORD", "OpsClaveSegura2026!")

from app import create_app  # noqa: E402
from app.domain import monitoreo as dom_monitoreo  # noqa: E402
from app.services import cache_service, clientes  # noqa: E402
from app.services.common import servicio  # noqa: E402


SERVICIOS = ("auth", "catalog", "inventory", "commercial", "asn", "planning", "alerts", "audit")


def _parchear_dependencias(monkeypatch, *, postgres=True, mongo=True, redis=True, bucket=True):
    mapa = {"postgres": postgres, "mongo": mongo, "redis": redis, "bucket": bucket}
    monkeypatch.setattr(servicio, "_verificar_dependencia", lambda dep: mapa.get(dep, False))
    monkeypatch.setattr(cache_service, "incrementar_contador", lambda *a, **kw: 0)


def test_health_incluye_proceso_dependencias_latencia_y_version_json_y_xml(monkeypatch):
    _parchear_dependencias(monkeypatch)
    monkeypatch.setenv("APP_VERSION", "2.4.1")
    app = servicio.crear_servicio(
        "svc-test",
        "Test",
        "Prueba",
        dependencias=("postgres", "mongo", "redis", "bucket"),
    )
    c = app.test_client()

    r_json = c.get("/health")
    assert r_json.status_code == 200
    datos = r_json.get_json()
    assert datos["service"] == "svc-test"
    assert datos["status"] == "HEALTHY"
    assert datos["version"] == "2.4.1"
    assert isinstance(datos["response_time_ms"], (int, float))
    assert datos["checked_at"]
    assert datos["process"]["status"] == "UP"
    assert isinstance(datos["process"]["pid"], int)
    assert datos["process"]["uptime_seconds"] >= 0
    assert datos["process"]["started_at"]
    assert datos["dependencies"] == {"postgres": True, "mongo": True, "redis": True, "bucket": True}

    r_xml = c.get("/api/v1/test/health", headers={"Accept": "application/xml"})
    assert r_xml.status_code == 200
    raiz = ET.fromstring(r_xml.get_data(as_text=True))
    assert raiz.tag == "service_health"
    assert raiz.findtext("version") == "2.4.1"
    assert raiz.find("process/status").text == "UP"
    assert raiz.find("dependencies/postgres").text == "true"
    assert raiz.find("dependencies/mongo").text == "true"
    assert raiz.find("dependencies/redis").text == "true"
    assert raiz.find("dependencies/bucket").text == "true"


def test_health_degradado_si_falla_bucket_o_mongo(monkeypatch):
    _parchear_dependencias(monkeypatch, bucket=False, mongo=False)
    app = servicio.crear_servicio(
        "svc-deg",
        "Degradado",
        "Prueba",
        dependencias=("postgres", "mongo", "redis", "bucket"),
    )
    r = app.test_client().get("/health")
    assert r.status_code == 503
    datos = r.get_json()
    assert datos["status"] == "DEGRADED"
    assert datos["dependencies"] == {"postgres": True, "mongo": False, "redis": True, "bucket": False}


def test_todos_los_microservicios_declaran_las_cuatro_dependencias():
    for nombre in SERVICIOS:
        mod = importlib.import_module(f"app.services.{nombre}_service.app")
        ruta = Path(mod.__file__).read_text(encoding="utf-8")
        assert 'dependencias=("postgres", "mongo", "redis", "bucket")' in ruta, nombre


def test_xsd_service_health_valido_y_compatible():
    xsd_path = RAIZ / "contracts" / "xsd" / "service_health.xsd"
    tree = ET.parse(xsd_path)
    elementos = [
        elem.attrib.get("name")
        for elem in tree.iter("{http://www.w3.org/2001/XMLSchema}element")
        if "name" in elem.attrib
    ]
    for requerido in ("service_health", "process", "response_time_ms", "checked_at", "postgres", "mongo", "redis", "bucket"):
        assert requerido in elementos

    try:
        import xmlschema
    except ImportError:
        return
    esquema = xmlschema.XMLSchema(str(xsd_path))
    xml_nuevo = (
        "<service_health><service>svc-auth</service><status>HEALTHY</status><version>1.0.0</version>"
        "<process><status>UP</status><pid>10</pid><uptime_seconds>5.2</uptime_seconds>"
        "<started_at>2026-11-24T00:00:00+00:00</started_at></process>"
        "<response_time_ms>3.1</response_time_ms><checked_at>2026-11-24T00:00:05+00:00</checked_at>"
        "<dependencies><postgres>true</postgres><mongo>true</mongo><redis>true</redis><bucket>true</bucket></dependencies>"
        "</service_health>"
    )
    xml_legacy = (
        "<service_health><service>svc-auth</service><status>HEALTHY</status><version>1.0.0</version>"
        "<dependencies><postgres>true</postgres><redis>true</redis></dependencies></service_health>"
    )
    assert esquema.is_valid(xml_nuevo)
    assert esquema.is_valid(xml_legacy)


def test_verificar_plataforma_consolida_degradados_caidas_errores_e_historial(monkeypatch):
    dom_monitoreo._limpiar_historial()
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: None)
    monkeypatch.setattr(
        cache_service,
        "obtener_contadores",
        lambda: {
            "counter:ops:svc-catalog:http_500:20261124": 2,
            "counter:ops:svc-catalog:errores_internos:20261124": 2,
            "counter:ops:svc-catalog:http_404:20261124": 1,
            "counter:ops:svc-asn:http_503:20261124": 3,
        },
    )

    respuestas_ronda_1 = {
        "auth": (200, {"service": "svc-auth", "status": "HEALTHY", "version": "1.2.0", "response_time_ms": 4.5, "process": {"status": "UP", "pid": 101, "uptime_seconds": 30.0}, "dependencies": {"postgres": True, "mongo": True, "redis": True, "bucket": True}}),
        "catalog": (503, {"service": "svc-catalog", "status": "DEGRADED", "version": "1.2.0", "response_time_ms": 12.0, "process": {"status": "UP", "pid": 102, "uptime_seconds": 30.0}, "dependencies": {"postgres": True, "mongo": False, "redis": True, "bucket": True}}),
        "inventory": (200, {"service": "svc-inventory", "status": "HEALTHY", "version": "1.2.0", "response_time_ms": 5.0, "process": {"status": "UP", "pid": 103, "uptime_seconds": 30.0}, "dependencies": {"postgres": True, "mongo": True, "redis": True, "bucket": True}}),
        "commercial": (200, {"service": "svc-commercial", "status": "HEALTHY", "version": "1.2.0", "response_time_ms": 6.0, "process": {"status": "UP", "pid": 104, "uptime_seconds": 30.0}, "dependencies": {"postgres": True, "mongo": True, "redis": True, "bucket": True}}),
        "asn": (0, None),
        "planning": (503, {"service": "svc-planning", "status": "DEGRADED", "version": "1.2.0", "response_time_ms": 9.5, "process": {"status": "UP", "pid": 106, "uptime_seconds": 30.0}, "dependencies": {"postgres": True, "mongo": True, "redis": True, "bucket": False}}),
        "alerts": (200, {"service": "svc-alerts", "status": "HEALTHY", "version": "1.2.0", "response_time_ms": 7.0, "process": {"status": "UP", "pid": 107, "uptime_seconds": 30.0}, "dependencies": {"postgres": True, "mongo": True, "redis": True, "bucket": True}}),
        "audit": (200, {"service": "svc-audit", "status": "HEALTHY", "version": "1.2.0", "response_time_ms": 4.0, "process": {"status": "UP", "pid": 108, "uptime_seconds": 30.0}, "dependencies": {"postgres": True, "mongo": True, "redis": True, "bucket": True}}),
    }

    monkeypatch.setattr(clientes, "llamar", lambda clave, metodo, ruta, **kw: respuestas_ronda_1[clave])
    snap1 = dom_monitoreo.verificar_plataforma(guardar_historial=True)

    assert snap1["estado_global"] == "DEGRADED" or snap1["estado_global"] == "DEGRADADO"
    assert snap1["resumen"]["sanos"] == 5
    assert snap1["resumen"]["degradados"] == 2
    assert snap1["resumen"]["caidos"] == 1
    assert snap1["resumen"]["disponibilidad_actual_pct"] == 62.5
    assert snap1["resumen"]["verificaciones_registradas"] == 1

    nombres_deg = {s["nombre"] for s in snap1["servicios_degradados"]}
    assert nombres_deg == {"svc-catalog", "svc-asn", "svc-planning"}

    caidas = {d["clave"]: d for d in snap1["dependencias_caidas"]}
    assert set(caidas) == {"mongo", "bucket"}
    assert caidas["mongo"]["servicios_afectados"] == ["svc-catalog"]
    assert caidas["bucket"]["servicios_afectados"] == ["svc-planning"]

    cat = next(s for s in snap1["servicios"] if s["clave"] == "catalog")
    # 1 fallo de verificacion + 2 http_500 (sin duplicar errores_internos) + 1 http_404 = 4
    assert cat["errores"] == 4
    assert cat["disponibilidad_pct"] == 0.0

    # Segunda ronda todo sano -> disponibilidad acumulada pasa a 50% en catalog/planning/asn
    respuestas_sanas = {
        s["clave"]: (
            200,
            {
                "service": s["nombre"],
                "status": "HEALTHY",
                "version": "1.2.0",
                "response_time_ms": 3.0,
                "process": {"status": "UP", "pid": 200, "uptime_seconds": 45.0},
                "dependencies": {"postgres": True, "mongo": True, "redis": True, "bucket": True},
            },
        )
        for s in clientes.SERVICIOS
    }
    monkeypatch.setattr(clientes, "llamar", lambda clave, metodo, ruta, **kw: respuestas_sanas[clave])
    snap2 = dom_monitoreo.verificar_plataforma(guardar_historial=True)

    assert snap2["estado_global"] == "OPERATIVO"
    assert snap2["resumen"]["verificaciones_registradas"] == 2
    cat2 = next(s for s in snap2["servicios"] if s["clave"] == "catalog")
    assert cat2["disponibilidad_pct"] == 50.0


def test_panel_oculto_protegido_y_sin_enlaces_en_sitio(monkeypatch):
    dom_monitoreo._limpiar_historial()
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: None)
    monkeypatch.setattr(cache_service, "obtener_contadores", lambda: {})
    monkeypatch.setattr(
        clientes,
        "llamar",
        lambda clave, metodo, ruta, **kw: (
            200,
            {
                "service": f"svc-{clave}",
                "status": "HEALTHY",
                "version": "1.0.0",
                "response_time_ms": 2.5,
                "process": {"status": "UP", "pid": 99, "uptime_seconds": 12.0},
                "dependencies": {"postgres": True, "mongo": True, "redis": True, "bucket": True},
            },
        ),
    )

    web = create_app()
    client = web.test_client()

    # Sin sesion: redirige a login y API responde 401
    r_anon = client.get("/ops/status")
    assert r_anon.status_code == 302
    assert "/ops/status/login" in r_anon.headers["Location"]
    assert r_anon.headers["X-Robots-Tag"] == "noindex, nofollow"

    r_api_anon = client.get("/ops/status/api/snapshot")
    assert r_api_anon.status_code == 401

    # Sin token CSRF el formulario se rechaza; el token se lee del propio formulario.
    assert client.post("/ops/status/login", data={"username": "ops_test", "password": "x"}).status_code == 400
    pagina_login = client.get("/ops/status/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', pagina_login).group(1)

    # Credenciales incorrectas
    r_bad = client.post("/ops/status/login", data={"username": "ops_test", "password": "incorrecta", "csrf_token": tok})
    assert r_bad.status_code == 200
    assert "incorrectos" in r_bad.get_data(as_text=True).lower()

    # Login valido
    r_ok = client.post(
        "/ops/status/login",
        data={"username": "ops_test", "password": "OpsClaveSegura2026!", "csrf_token": tok},
        follow_redirects=True,
    )
    assert r_ok.status_code == 200
    html = r_ok.get_data(as_text=True)
    assert "Monitor Central" in html
    assert "PostgreSQL" in html
    assert "Bucket" in html

    r_snap = client.get("/ops/status/api/snapshot")
    assert r_snap.status_code == 200
    assert r_snap.get_json()["estado_global"] == "OPERATIVO"

    # Logout revoca acceso
    r_out = client.post("/ops/status/logout", data={"csrf_token": tok})
    assert r_out.status_code == 302
    assert client.get("/ops/status/api/snapshot").status_code == 401

    # No debe aparecer ningun enlace en la navegacion ni plantillas publicas/login
    for rel in (
        "app/navegacion.py",
        "app/templates/base.html",
        "app/templates/landing.html",
        "app/templates/login.html",
    ):
        assert "/ops/status" not in (RAIZ / rel).read_text(encoding="utf-8"), rel
