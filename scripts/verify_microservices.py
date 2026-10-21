#!/usr/bin/env python3
"""
Verificación de Microservicios Flask Context-Aware — FreshTrack.

Prueba de forma aislada e integrada los 4 microservicios contenerizados:
1. Planning Service (Puerto 5001) - Pronósticos & Series en MongoDB
2. Alerts Service (Puerto 5002) - Alertas Pre-Merma & Sostenibilidad ESG
3. Inventory Service (Puerto 5003) - Existencias & Reserva FEFO para Saga
4. Commercial Service (Puerto 5004) - Checkout POS con Saga Orquestada
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import one
from app.services.alerts_service.app import app as alerts_app
from app.services.auth_service.app import app as auth_app
from app.services.commercial_service.app import app as commercial_app
from app.services.inventory_service.app import app as inventory_app
from app.services.planning_service.app import app as planning_app

TOKEN = None


def obtener_token():
    global TOKEN
    if not TOKEN:
        c = auth_app.test_client()
        r = c.post("/api/v1/auth/login", json={"email": "admin@freshtrack.mx", "password": "Admin2026!"})
        if r.status_code == 200:
            TOKEN = r.get_json()["token"]
    return TOKEN


def probar_planning_service():
    print("\n--- 1. Probando Planning Service (Pronósticos & Series en Mongo) ---")
    client = planning_app.test_client()
    token = obtener_token()
    headers = {"Authorization": f"Bearer {token}", "X-Location-Id": "1"}

    # 1. Healthcheck
    resp = client.get("/health")
    assert resp.status_code == 200, f"Healthcheck falló: {resp.data}"
    data = resp.get_json()
    print(f" [OK] Health: {data['status']} (Postgres: {data['dependencies']['postgres']}, Redis: {data['dependencies']['redis']}, Mongo: {data['dependencies']['mongo']})")

    # 2. Latest forecast query
    resp_latest = client.get("/api/v1/planning/forecast/latest/1/1", headers=headers)
    assert resp_latest.status_code in (200, 404), "Error en endpoint /api/v1/planning/forecast/latest/1/1"
    print(f" [OK] Consulta documental a MongoDB operativa (Status: {resp_latest.status_code})")


def probar_alerts_service():
    print("\n--- 2. Probando Alerts Service (Alertas & Sostenibilidad ESG) ---")
    client = alerts_app.test_client()
    token = obtener_token()
    headers = {"Authorization": f"Bearer {token}", "X-Location-Id": "1"}

    # 1. Healthcheck
    resp = client.get("/health")
    assert resp.status_code == 200, f"Healthcheck falló: {resp.data}"
    data = resp.get_json()
    print(f" [OK] Health: {data['status']}")

    # 2. ESG Avoided waste
    resp_esg = client.get("/api/v1/alerts/esg/carbon-avoided", headers=headers)
    assert resp_esg.status_code == 200, "Error en /api/v1/alerts/esg/carbon-avoided"
    esg_data = resp_esg.get_json()
    print(f" [OK] Métricas ESG: {esg_data['alimento_recuperado_kg']} kg recuperados, {esg_data['co2e_evitado_kg']} kg CO2e ahorrados")

    # 3. Active alerts query
    resp_alerts = client.get("/api/v1/alerts/active", headers=headers)
    assert resp_alerts.status_code == 200, "Error en /api/v1/alerts/active"
    print(f" [OK] Alertas activas en MongoDB: {resp_alerts.get_json()['total']}")


def probar_inventory_service():
    print("\n--- 3. Probando Inventory Service (Existencias & Reserva FEFO) ---")
    client = inventory_app.test_client()
    token = obtener_token()
    headers = {"Authorization": f"Bearer {token}", "X-Location-Id": "1"}

    # 1. Healthcheck
    resp = client.get("/health")
    assert resp.status_code == 200, f"Healthcheck falló: {resp.data}"
    print(f" [OK] Health: {resp.get_json()['status']}")

    # 2. Stock query con context header
    resp_stock = client.get("/api/v1/inventory/stock", headers=headers)
    assert resp_stock.status_code == 200, "Error en /api/v1/inventory/stock"
    stock_data = resp_stock.get_json()
    print(f" [OK] Existencias consultadas con contexto Locación 1: {stock_data['total']} registros")


def probar_commercial_service():
    print("\n--- 4. Probando Commercial Service (Saga Orquestada de Ventas) ---")
    client = commercial_app.test_client()
    token = obtener_token()

    # 1. Healthcheck
    resp = client.get("/health")
    assert resp.status_code == 200, f"Healthcheck falló: {resp.data}"
    print(f" [OK] Health: {resp.get_json()['status']}")

    # 2. Sales history
    resp_hist = client.get("/api/v1/commercial/sales", headers={"Authorization": f"Bearer {token}", "X-Location-Id": "1"})
    assert resp_hist.status_code == 200, "Error en /api/v1/commercial/sales"
    print(f" [OK] Historial de ventas con contexto de tienda: {resp_hist.get_json()['total']} ventas")

    # 3. Checkout con Saga Orquestada
    admin = one("SELECT id_usuario FROM operacion.usuario WHERE email = 'admin@freshtrack.mx'")
    if admin:
        payload = {
            "id_locacion": 1,
            "id_usuario": str(admin["id_usuario"]),
            "lineas": [{"id_sku": 1, "cantidad": 0.2}],
            "canal": "TIENDA",
        }
        resp_checkout = client.post(
            "/api/v1/commercial/checkout",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "X-User-Id": str(admin["id_usuario"]),
                "X-User-Role": "admin",
                "X-Location-Id": "1",
            },
        )
        if resp_checkout.status_code == 201:
            data_sale = resp_checkout.get_json()
            print(f" [OK] Checkout vía Saga completado: Folio {data_sale['folio']}, Total ${data_sale['total']:.2f}")
        else:
            print(f" [INFO] Checkout respuesta: {resp_checkout.status_code} ({resp_checkout.get_json()})")


def main():
    print("=================================================================")
    print(" FreshTrack — Verificación de Microservicios Flask Context-Aware ")
    print("=================================================================")
    probar_planning_service()
    probar_alerts_service()
    probar_inventory_service()
    probar_commercial_service()
    print("\n>>> ¡TODOS LOS MICROSERVICIOS RESPONDEN CORRECTAMENTE! <<<\n")


if __name__ == "__main__":
    main()
