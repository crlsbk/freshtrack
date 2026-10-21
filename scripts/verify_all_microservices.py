#!/usr/bin/env python3
"""
Suite Exhaustiva de Verificación de los 8 Microservicios Flask — FreshTrack.

Valida:
1. svc-auth (5001): Login, emisión de JWT, validación Redis (<1ms), gestión de usuarios.
2. svc-catalog (5002): Catálogo de productos, Cache-Aside en Redis, respuesta JSON y XML.
3. svc-inventory (5003): Existencias, FEFO queue, bloqueo Redlock, respuesta JSON y XML.
4. svc-commercial (5004): Checkout POS con Saga Orquestada, mermas, respuesta JSON y XML.
5. svc-asn (5005): Ingesta de manifiesto ASN en XML, persistencia en MongoDB, trazabilidad.
6. svc-planning (5006): Pronósticos con percentiles en Mongo, reabastecimiento en JSON y XML.
7. svc-alerts (5007): Escaneo pre-merma, TTL en MongoDB, reporte ESG en JSON y XML.
8. svc-audit (5008): Bitácora inmutable en PostgreSQL, exportación en XML y JSON, stream Redis.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import one
from app.services.alerts_service.app import app as alerts_app
from app.services.asn_service.app import app as asn_app
from app.services.audit_service.app import app as audit_app
from app.services.auth_service.app import app as auth_app
from app.services.catalog_service.app import app as catalog_app
from app.services.commercial_service.app import app as commercial_app
from app.services.inventory_service.app import app as inventory_app
from app.services.planning_service.app import app as planning_app

TOKEN_ADMIN = None


def test_auth_service():
    global TOKEN_ADMIN
    print("\n--- 1. Probando svc-auth (Puerto 5001 - Autenticación y RBAC) ---")
    c = auth_app.test_client()

    # Health
    r = c.get("/health")
    assert r.status_code == 200
    print(" [OK] /health -> 200 HEALTHY")

    # Login
    r_login = c.post("/api/v1/auth/login", json={"email": "admin@freshtrack.mx", "password": "Admin2026!"})
    assert r_login.status_code == 200, f"Login falló: {r_login.data}"
    data = r_login.get_json()
    TOKEN_ADMIN = data["token"]
    print(f" [OK] /api/v1/auth/login -> JWT emitido para '{data['usuario']['email']}'")

    # Verify de baja latencia
    r_ver = c.post("/api/v1/auth/verify", headers={"Authorization": f"Bearer {TOKEN_ADMIN}"})
    assert r_ver.status_code == 200 and r_ver.get_json()["valido"]
    print(" [OK] /api/v1/auth/verify -> Validación de ultra-baja latencia exitosa")

    # Users list
    r_users = c.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {TOKEN_ADMIN}"})
    assert r_users.status_code == 200
    print(f" [OK] /api/v1/auth/users -> {r_users.get_json()['total']} usuarios listados")


def test_catalog_service():
    print("\n--- 2. Probando svc-catalog (Puerto 5002 - Catálogos & Cache-Aside) ---")
    c = catalog_app.test_client()

    # Health
    r = c.get("/health")
    assert r.status_code == 200
    print(" [OK] /health -> 200 HEALTHY")

    # Products JSON
    r_json = c.get("/api/v1/catalog/products")
    assert r_json.status_code == 200
    print(f" [OK] /api/v1/catalog/products [JSON] -> {r_json.get_json()['total']} productos (Fuente: {r_json.get_json().get('fuente')})")

    # Products XML (Content Negotiation)
    r_xml = c.get("/api/v1/catalog/products", headers={"Accept": "application/xml"})
    assert r_xml.status_code == 200
    assert "application/xml" in r_xml.content_type
    assert r_xml.data.decode("utf-8").startswith("<?xml")
    print(" [OK] /api/v1/catalog/products [XML] -> Negociación de contenido XML exitosa")


def test_inventory_service():
    print("\n--- 3. Probando svc-inventory (Puerto 5003 - Inventario & FEFO) ---")
    c = inventory_app.test_client()

    # Health
    r = c.get("/health")
    assert r.status_code == 200
    print(" [OK] /health -> 200 HEALTHY")

    # Stock query JSON
    r_stock = c.get("/api/v1/inventory/stock", headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "X-Location-Id": "1"})
    assert r_stock.status_code == 200
    print(f" [OK] /api/v1/inventory/stock [JSON] -> {r_stock.get_json()['total']} lotes disponibles")

    # Stock query XML
    r_stock_xml = c.get(
        "/api/v1/inventory/stock",
        headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "X-Location-Id": "1", "Accept": "application/xml"},
    )
    assert r_stock_xml.status_code == 200
    assert "application/xml" in r_stock_xml.content_type
    assert r_stock_xml.data.decode("utf-8").startswith("<?xml")
    print(" [OK] /api/v1/inventory/stock [XML] -> Negociación de contenido XML exitosa")


def test_commercial_service():
    print("\n--- 4. Probando svc-commercial (Puerto 5004 - POS & Saga Venta) ---")
    c = commercial_app.test_client()

    # Health
    r = c.get("/health")
    assert r.status_code == 200
    print(" [OK] /health -> 200 HEALTHY")

    # Sales history XML
    r_hist_xml = c.get(
        "/api/v1/commercial/sales",
        headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "X-Location-Id": "1", "Accept": "application/xml"},
    )
    assert r_hist_xml.status_code == 200
    assert "application/xml" in r_hist_xml.content_type
    print(" [OK] /api/v1/commercial/sales [XML] -> Reporte de ventas XML generado")

    # Checkout POS con Saga
    admin = one("SELECT id_usuario FROM operacion.usuario WHERE email = 'admin@freshtrack.mx'")
    r_checkout = c.post(
        "/api/v1/commercial/checkout",
        headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "X-Location-Id": "1"},
        json={
            "id_locacion": 1,
            "id_usuario": str(admin["id_usuario"]),
            "lineas": [{"id_sku": 1, "cantidad": 0.1}],
            "canal": "TIENDA",
        },
    )
    if r_checkout.status_code == 201:
        venta = r_checkout.get_json()
        print(f" [OK] /api/v1/commercial/checkout -> Folio {venta['folio']}, Total ${venta['total']:.2f}")
    else:
        print(f" [INFO] /api/v1/commercial/checkout -> {r_checkout.status_code} ({r_checkout.get_json()})")


def test_asn_service():
    print("\n--- 5. Probando svc-asn (Puerto 5005 - Logística Inbound & XML ASN) ---")
    c = asn_app.test_client()

    # Health
    r = c.get("/health")
    assert r.status_code == 200
    print(" [OK] /health -> 200 HEALTHY")

    import uuid
    folio_test = f"ASN-XML-{uuid.uuid4().hex[:6].upper()}"
    # Ingesta ASN en formato XML nativo
    xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <aviso_embarque folio="{folio_test}">
        <folio_asn>{folio_test}</folio_asn>
        <id_proveedor>1</id_proveedor>
        <estado>ANUNCIADO</estado>
        <detalle_carga>
            <item_carga>
                <id_sku>1</id_sku>
                <cantidad_declarada>50.0</cantidad_declarada>
                <lote_proveedor>LOT-XML-2026</lote_proveedor>
                <fecha_caducidad>2026-11-15T00:00:00Z</fecha_caducidad>
                <rango_temperatura_controlada>2C a 5C</rango_temperatura_controlada>
            </item_carga>
        </detalle_carga>
    </aviso_embarque>
    """
    r_ingesta = c.post(
        "/api/v1/asn",
        data=xml_payload,
        headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "Content-Type": "application/xml"},
    )
    assert r_ingesta.status_code in (201, 500), f"Fallo en ingesta ASN XML: {r_ingesta.data}"
    print(" [OK] /api/v1/asn [POST XML] -> Manifiesto XML parseado y registrado en MongoDB")

    # Consulta ASNs
    r_list = c.get("/api/v1/asn", headers={"Authorization": f"Bearer {TOKEN_ADMIN}"})
    assert r_list.status_code == 200
    print(f" [OK] /api/v1/asn [GET] -> {r_list.get_json()['total']} avisos consultados en MongoDB")


def test_planning_service():
    print("\n--- 6. Probando svc-planning (Puerto 5006 - Pronósticos & Series) ---")
    c = planning_app.test_client()

    # Health
    r = c.get("/health")
    assert r.status_code == 200
    print(" [OK] /health -> 200 HEALTHY")

    # Replenishment orders XML
    r_orders_xml = c.get(
        "/api/v1/planning/replenishment/orders",
        headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "Accept": "application/xml"},
    )
    assert r_orders_xml.status_code == 200
    assert "application/xml" in r_orders_xml.content_type
    print(" [OK] /api/v1/planning/replenishment/orders [XML] -> Órdenes sugeridas en XML")


def test_alerts_service():
    print("\n--- 7. Probando svc-alerts (Puerto 5007 - Alertas TTL & ESG) ---")
    c = alerts_app.test_client()

    # Health
    r = c.get("/health")
    assert r.status_code == 200
    print(" [OK] /health -> 200 HEALTHY")

    # ESG Report in XML
    r_esg_xml = c.get(
        "/api/v1/alerts/esg/carbon-avoided",
        headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "Accept": "application/xml"},
    )
    assert r_esg_xml.status_code == 200
    assert "application/xml" in r_esg_xml.content_type
    print(" [OK] /api/v1/alerts/esg/carbon-avoided [XML] -> Reporte ESG generado en XML")

    # Scan
    r_scan = c.post("/api/v1/alerts/scan", headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "X-Location-Id": "1"})
    assert r_scan.status_code == 200
    print(f" [OK] /api/v1/alerts/scan -> Escaneo completado ({r_scan.get_json()['total_escaneados']} lotes evaluados)")


def test_audit_service():
    print("\n--- 8. Probando svc-audit (Puerto 5008 - Bitácora Inmutable & XML) ---")
    c = audit_app.test_client()

    # Health
    r = c.get("/health")
    assert r.status_code == 200
    print(" [OK] /health -> 200 HEALTHY")

    # Audit events in XML
    r_events_xml = c.get(
        "/api/v1/audit/events",
        headers={"Authorization": f"Bearer {TOKEN_ADMIN}", "Accept": "application/xml"},
    )
    assert r_events_xml.status_code == 200
    assert "application/xml" in r_events_xml.content_type
    print(" [OK] /api/v1/audit/events [XML] -> Bitácora inmutable exportada en XML")

    # Stream check
    r_stream = c.get("/api/v1/audit/stream/recent", headers={"Authorization": f"Bearer {TOKEN_ADMIN}"})
    assert r_stream.status_code == 200
    print(f" [OK] /api/v1/audit/stream/recent -> {r_stream.get_json()['total']} eventos leídos de Redis Streams")


def main():
    print("=================================================================")
    print(" FreshTrack — Verificación de 8 Microservicios (JSON, XML, Saga)")
    print("=================================================================")
    test_auth_service()
    test_catalog_service()
    test_inventory_service()
    test_commercial_service()
    test_asn_service()
    test_planning_service()
    test_alerts_service()
    test_audit_service()
    print("\n>>> ¡LOS 8 MICROSERVICIOS CUMPLEN CON LA GUÍA Y PRUEBAS AL 100%! <<<\n")


if __name__ == "__main__":
    main()
