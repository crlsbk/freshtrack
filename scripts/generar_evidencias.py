#!/usr/bin/env python3
"""
Genera docs/evidencias/EVIDENCIAS_REQUEST_RESPONSE.md ejecutando peticiones HTTP REALES
contra los microservicios desplegados (docker compose o servidor en la nube).

Por cada operación se registra: URL completa, método, headers (token abreviado),
cuerpo JSON/XML, código HTTP, respuesta completa (recortada si es muy larga) y el
objetivo del caso. Se cubren casos correctos, parámetros inválidos, registros
inexistentes, acceso sin token, rol sin permiso, token revocado y errores de negocio.

Uso:
    docker compose up -d --build --wait
    python scripts/generar_evidencias.py                 # contra localhost
    python scripts/generar_evidencias.py --host 1.2.3.4  # contra el servidor
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PUERTOS = {"auth": 5001, "catalog": 5002, "inventory": 5003, "commercial": 5004,
           "asn": 5005, "planning": 5006, "alerts": 5007, "audit": 5008}
NOMBRES = {k: f"svc-{k}" for k in PUERTOS}
CREDENCIALES = {
    "admin": ("admin@freshtrack.mx", "Admin2026!"),
    "buyer": ("buyer@freshtrack.mx", "Compras2026!"),
    "store_manager": ("gerente@freshtrack.mx", "Tienda2026!"),
    "warehouse": ("almacen@freshtrack.mx", "Almacen2026!"),
    "auditor": ("auditor@freshtrack.mx", "Auditor2026!"),
    "planner": ("planner@freshtrack.mx", "Plan2026!"),
}
MAX_RESPUESTA = 2500


class Evidencias:
    def __init__(self, host: str):
        self.host = host
        self.casos: list[dict] = []
        self.tokens: dict[str, str] = {}

    def url(self, svc: str, ruta: str) -> str:
        return f"http://{self.host}:{PUERTOS[svc]}{ruta}"

    def pedir(self, svc, metodo, ruta, *, objetivo, rol=None, token=None, json_body=None, xml_body=None,
              accept=None, esperado=None, registrar=True):
        headers = {}
        if rol and not token:
            token = self.tokens[rol]
        if token:
            headers["Authorization"] = f"Bearer {token}"
        datos = None
        if json_body is not None:
            datos = json.dumps(json_body, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        elif xml_body is not None:
            datos = xml_body.encode()
            headers["Content-Type"] = "application/xml"
        if accept:
            headers["Accept"] = accept
        headers["X-Correlation-Id"] = uuid.uuid4().hex[:16]
        req = urllib.request.Request(self.url(svc, ruta), data=datos, method=metodo, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                status, cuerpo, ctype = r.status, r.read().decode(), r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            status, cuerpo, ctype = e.code, e.read().decode(), e.headers.get("Content-Type", "")
        except Exception as e:
            status, cuerpo, ctype = 0, f"(sin respuesta: {e})", ""
        if registrar:
            self.casos.append({
                "svc": svc, "metodo": metodo, "url": self.url(svc, ruta), "objetivo": objetivo,
                "headers": {k: (v[:27] + "…" if k == "Authorization" else v) for k, v in headers.items()},
                "cuerpo": json.dumps(json_body, ensure_ascii=False, indent=2) if json_body is not None else xml_body,
                "formato_cuerpo": "json" if json_body is not None else ("xml" if xml_body else None),
                "status": status, "ctype": ctype, "respuesta": cuerpo, "esperado": esperado,
            })
        try:
            return status, json.loads(cuerpo)
        except ValueError:
            return status, cuerpo

    def login(self, rol, guardar=True):
        email, pwd = CREDENCIALES[rol]
        import time

        for _ in range(3):
            st, cuerpo = self.pedir("auth", "POST", "/api/v1/auth/login", objetivo="", json_body={"email": email, "password": pwd}, registrar=False)
            if st != 429:
                break
            espera = int((cuerpo.get("detalles") or {}).get("retry_after", 30)) + 1
            print(f"Rate limit de login para {rol}: esperando {espera}s…")
            time.sleep(espera)
        if st != 200:
            raise SystemExit(f"No se pudo iniciar sesión como {rol}: {st} {cuerpo}")
        if guardar:
            self.tokens[rol] = cuerpo["token"]
        return cuerpo


def ejecutar(ev: Evidencias) -> None:
    for rol in CREDENCIALES:
        ev.login(rol)
    tienda = 3
    hoy = date.today()

    # ---------------- svc-auth ----------------
    ev.pedir("auth", "POST", "/api/v1/auth/login", objetivo="Inicio de sesión correcto (JSON): emite JWT y crea session:{jti} en Redis",
             json_body={"email": "gerente@freshtrack.mx", "password": "Tienda2026!"}, esperado=200)
    ev.pedir("auth", "POST", "/api/v1/auth/login", objetivo="Inicio de sesión con cuerpo XML y respuesta XML",
             xml_body="<login_request><email>auditor@freshtrack.mx</email><password>Auditor2026!</password></login_request>",
             accept="application/xml", esperado=200)
    ev.pedir("auth", "POST", "/api/v1/auth/login", objetivo="Credenciales incorrectas (no revela si el correo existe)",
             json_body={"email": "admin@freshtrack.mx", "password": "equivocada"}, esperado=401)
    ev.pedir("auth", "POST", "/api/v1/auth/login", objetivo="XML que no cumple login_request.xsd",
             xml_body="<login_request><email>no-es-correo</email></login_request>", esperado=400)
    ev.pedir("auth", "POST", "/api/v1/auth/login", objetivo="Cuenta desactivada",
             json_body={"email": "inactivo@freshtrack.mx", "password": "Inactivo2026!"}, esperado=401)
    ev.pedir("auth", "POST", "/api/v1/auth/verify", rol="warehouse", objetivo="Verificación de token (firma, vigencia, sesión Redis, denylist)", esperado=200)
    ev.pedir("auth", "GET", "/api/v1/auth/me", rol="buyer", objetivo="Perfil del usuario del token", esperado=200)
    ev.pedir("auth", "GET", "/api/v1/auth/users?rol=store_manager&pagina=1&por_pagina=5", rol="admin", objetivo="Usuarios filtrados y paginados (admin)", esperado=200)
    ev.pedir("auth", "GET", "/api/v1/auth/users", rol="auditor", objetivo="Rol sin permiso intenta listar usuarios", esperado=403)
    ev.pedir("auth", "GET", "/api/v1/auth/users", objetivo="Petición sin token", esperado=401)
    ev.pedir("auth", "GET", "/api/v1/auth/sessions/no-es-uuid", rol="admin", objetivo="Parámetro de ruta inválido", esperado=400)
    ev.pedir("auth", "GET", f"/api/v1/auth/sessions/{uuid.uuid4()}", rol="admin", objetivo="Usuario inexistente", esperado=404)
    planner = ev.login("planner", guardar=False)
    ev.pedir("auth", "GET", f"/api/v1/auth/sessions/{planner['usuario']['id_usuario']}", rol="admin", objetivo="Sesiones activas en Redis con TTL restante", esperado=200)
    ev.pedir("auth", "DELETE", f"/api/v1/auth/sessions/{planner['usuario']['id_usuario']}", rol="admin", objetivo="Cierre forzado de todas las sesiones de un usuario", esperado=200)
    ev.pedir("planning", "GET", "/api/v1/planning/replenishment/orders", token=planner["token"], objetivo="El token del usuario cuyas sesiones se cerraron ya no sirve en otro servicio", esperado=401)
    ev.login("planner")  # el cierre forzado revocó todas sus sesiones; se abre una nueva
    ev.pedir("auth", "GET", "/api/v1/auth/counters?servicio=auth", rol="admin", objetivo="Contadores de operación en Redis", esperado=200)
    temporal = ev.login("store_manager", guardar=False)["token"]
    ev.pedir("auth", "POST", "/api/v1/auth/logout", token=temporal, objetivo="Logout: revoca en PostgreSQL y agrega jti a la denylist de Redis", esperado=200)
    ev.pedir("inventory", "GET", "/api/v1/inventory/stock", token=temporal, objetivo="Token revocado usado en OTRO microservicio", esperado=401)
    ev.pedir("inventory", "GET", "/api/v1/inventory/stock", token=temporal[:-4] + "AAAA", objetivo="Token con firma alterada", esperado=401)

    # ---------------- svc-catalog ----------------
    nombre = f"Fresa evidencia {uuid.uuid4().hex[:5]}"
    ev.pedir("catalog", "GET", "/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3", objetivo="Productos filtrados y paginados (Cache-Aside: 1.ª vez PostgreSQL)", esperado=200)
    ev.pedir("catalog", "GET", "/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3", objetivo="Misma consulta servida desde caché Redis (campo fuente y TTL)", esperado=200)
    ev.pedir("catalog", "GET", "/api/v1/catalog/products?por_pagina=2", accept="application/xml", objetivo="Respuesta en XML", esperado=200)
    ev.pedir("catalog", "GET", "/api/v1/catalog/products?pagina=0", objetivo="Parámetro de paginación inválido", esperado=400)
    st, _ = ev.pedir("catalog", "POST", "/api/v1/catalog/products", rol="buyer", objetivo="Alta de producto con XML validado contra producto_request.xsd",
                     xml_body=f"<producto_request><nombre>{nombre}</nombre><categoria>Frutas</categoria><precio_costo>20</precio_costo>"
                              "<precio_venta>35.5</precio_venta><vida_util_estandar>5</vida_util_estandar></producto_request>",
                     accept="application/xml", esperado=201)
    _, lista = ev.pedir("catalog", "GET", f"/api/v1/catalog/products?q={nombre.replace(' ', '%20')}", objetivo="", registrar=False)
    id_sku = lista["productos"][0]["id_sku"] if isinstance(lista, dict) and lista.get("productos") else 1
    ev.pedir("catalog", "GET", f"/api/v1/catalog/products/{id_sku}", objetivo="Detalle por SKU", esperado=200)
    ev.pedir("catalog", "PATCH", f"/api/v1/catalog/products/{id_sku}", rol="buyer", json_body={"precio_venta": 39.9}, objetivo="Actualización parcial (PATCH)", esperado=200)
    ev.pedir("catalog", "PUT", f"/api/v1/catalog/products/{id_sku}", rol="buyer",
             json_body={"nombre": nombre, "categoria": "Frutas", "precio_costo": 21, "precio_venta": 40, "vida_util_estandar": 6, "unidad_medida": "Pieza"},
             objetivo="Reemplazo completo (PUT)", esperado=200)
    ev.pedir("catalog", "PATCH", f"/api/v1/catalog/products/{id_sku}", rol="buyer", json_body={"precio_venta": 5}, objetivo="Regla de negocio: precio de venta menor al costo", esperado=409)
    ev.pedir("catalog", "POST", "/api/v1/catalog/products", rol="buyer", json_body={"nombre": "Sin precio"}, objetivo="Campos obligatorios faltantes", esperado=400)
    ev.pedir("catalog", "DELETE", f"/api/v1/catalog/products/{id_sku}", rol="buyer", objetivo="Baja reservada a admin", esperado=403)
    ev.pedir("catalog", "DELETE", f"/api/v1/catalog/products/{id_sku}", rol="admin", objetivo="Baja lógica (activo=false)", esperado=200)
    ev.pedir("catalog", "GET", "/api/v1/catalog/products/99999999", objetivo="SKU inexistente", esperado=404)
    ev.pedir("catalog", "GET", "/api/v1/catalog/locations?tipo=Tienda", objetivo="Tiendas (Cache-Aside)", esperado=200)

    # ---------------- svc-inventory ----------------
    ev.pedir("inventory", "GET", f"/api/v1/inventory/stock?id_locacion={tienda}&dias_max=7&por_pagina=5", rol="store_manager", objetivo="Existencias por vencer en ≤7 días (paginado, orden FEFO)", esperado=200)
    ev.pedir("inventory", "GET", f"/api/v1/inventory/fefo-queue/1/{tienda}", rol="warehouse", accept="application/xml", objetivo="Cola FEFO en XML", esperado=200)
    ev.pedir("inventory", "GET", f"/api/v1/inventory/fefo-queue/99999999/{tienda}", rol="warehouse", objetivo="SKU inexistente en la cola FEFO", esperado=404)
    saga = f"evidencia-{uuid.uuid4().hex[:8]}"
    ev.pedir("inventory", "POST", "/api/v1/inventory/reserve-fefo", rol="warehouse",
             xml_body=f"<reserva_request><id_locacion>{tienda}</id_locacion><saga_id>{saga}</saga_id><lineas><item><id_sku>1</id_sku><cantidad>1</cantidad></item></lineas></reserva_request>",
             objetivo="Reserva FEFO con lock distribuido en Redis (XML)", esperado=200)
    ev.pedir("inventory", "POST", "/api/v1/inventory/cancel-reservation", rol="warehouse", json_body={"saga_id": saga}, objetivo="Compensación: libera la reserva guardada en Redis", esperado=200)
    ev.pedir("inventory", "POST", "/api/v1/inventory/reserve-fefo", rol="warehouse",
             json_body={"id_locacion": tienda, "lineas": [{"id_sku": 1, "cantidad": 99999999}]}, objetivo="Stock insuficiente (rollback)", esperado=409)
    ev.pedir("inventory", "POST", "/api/v1/inventory/reserve-fefo", rol="warehouse",
             json_body={"id_locacion": tienda, "lineas": [{"id_sku": "abc", "cantidad": 1}]}, objetivo="Tipo de dato inválido", esperado=400)
    ev.pedir("inventory", "POST", "/api/v1/inventory/reserve-fefo", rol="auditor",
             json_body={"id_locacion": tienda, "lineas": [{"id_sku": 1, "cantidad": 1}]}, objetivo="Auditor no puede reservar", esperado=403)

    # ---------------- svc-commercial ----------------
    ev.pedir("commercial", "POST", "/api/v1/commercial/checkout", rol="store_manager",
             json_body={"id_locacion": tienda, "canal": "TIENDA", "lineas": [{"id_sku": 1, "cantidad": 1}]},
             objetivo="Venta POS por Saga: reserva FEFO → venta → descuento de existencias", esperado=201)
    ev.pedir("commercial", "POST", "/api/v1/commercial/checkout", rol="store_manager",
             xml_body=f"<checkout_request><id_locacion>{tienda}</id_locacion><lineas><item><id_sku>1</id_sku><cantidad>99999999</cantidad></item></lineas></checkout_request>",
             accept="application/xml", objetivo="Venta rechazada por stock (compensación de la saga, respuesta XML)", esperado=409)
    ev.pedir("commercial", "POST", "/api/v1/commercial/checkout", rol="store_manager",
             xml_body="<checkout_request><canal>OTRO</canal><lineas/></checkout_request>", objetivo="XML que no cumple checkout_request.xsd", esperado=400)
    carrito = f"caja1-{uuid.uuid4().hex[:4]}"
    ev.pedir("commercial", "PUT", f"/api/v1/commercial/cart/{carrito}", rol="store_manager", json_body={"lineas": [{"id_sku": 1, "cantidad": 2}]}, objetivo="Carrito temporal en Redis (TTL 15 min)", esperado=200)
    ev.pedir("commercial", "GET", f"/api/v1/commercial/cart/{carrito}", rol="store_manager", objetivo="Consulta del carrito con TTL restante", esperado=200)
    ev.pedir("commercial", "DELETE", f"/api/v1/commercial/cart/{carrito}", rol="store_manager", objetivo="Consumo atómico (GET+DEL en Lua)", esperado=200)
    ev.pedir("commercial", "GET", f"/api/v1/commercial/cart/{carrito}", rol="store_manager", objetivo="Carrito ya consumido", esperado=404)
    ev.pedir("commercial", "POST", "/api/v1/commercial/shrinkage", rol="warehouse",
             json_body={"id_lote": str(uuid.uuid4()), "id_locacion": tienda, "cantidad": 1, "causa": "DANO"}, objetivo="Merma sobre un lote que no existe", esperado=409)
    ev.pedir("commercial", "POST", "/api/v1/commercial/shrinkage", rol="warehouse",
             json_body={"id_lote": str(uuid.uuid4()), "id_locacion": tienda, "cantidad": 1, "causa": "INVENTADA"}, objetivo="Causa de merma inválida", esperado=400)
    ev.pedir("commercial", "GET", f"/api/v1/commercial/sales?id_locacion={tienda}&desde={hoy - timedelta(days=30)}&por_pagina=3", rol="store_manager", objetivo="Historial de ventas por rango de fechas", esperado=200)

    # ---------------- svc-asn ----------------
    folio = f"ASN-EV-{uuid.uuid4().hex[:6].upper()}"
    cad = (hoy + timedelta(days=20)).isoformat()
    xml_asn = (f"<asn_request><folio_asn>{folio}</folio_asn><id_proveedor>1</id_proveedor><detalle_carga>"
               f"<item_carga><id_sku>1</id_sku><cantidad_declarada>120</cantidad_declarada><lote_proveedor>LP-7781</lote_proveedor>"
               f"<fecha_caducidad>{cad}</fecha_caducidad><rango_temperatura_controlada>2C a 6C</rango_temperatura_controlada></item_carga>"
               f"<item_carga><id_sku>2</id_sku><cantidad_declarada>40</cantidad_declarada><fecha_caducidad>{cad}</fecha_caducidad></item_carga>"
               "</detalle_carga></asn_request>")
    ev.pedir("asn", "POST", "/api/v1/asn", rol="warehouse", xml_body=xml_asn, objetivo="Ingesta de ASN en XML (validado con asn_request.xsd) → documento en MongoDB", esperado=201)
    ev.pedir("asn", "POST", "/api/v1/asn", rol="warehouse", xml_body=xml_asn, objetivo="Folio duplicado (índice único en MongoDB)", esperado=409)
    ev.pedir("asn", "POST", "/api/v1/asn", rol="buyer",
             json_body={"folio_asn": f"ASN-X-{uuid.uuid4().hex[:4]}", "id_proveedor": 1, "detalle_carga": [{"id_sku": 99999999, "cantidad_declarada": 1, "fecha_caducidad": cad}]},
             objetivo="SKU inexistente en PostgreSQL (integración PG↔Mongo)", esperado=409)
    ev.pedir("asn", "GET", f"/api/v1/asn/{folio}", rol="warehouse", objetivo="Recuperación por folio", esperado=200)
    ev.pedir("asn", "PATCH", f"/api/v1/asn/{folio}/status", rol="warehouse", json_body={"estado": "RECIBIDO"}, objetivo="Transición de estado inválida", esperado=409)
    ev.pedir("asn", "PATCH", f"/api/v1/asn/{folio}/status", rol="warehouse", json_body={"estado": "EN_TRANSITO"}, objetivo="Actualización de documento ($set)", esperado=200)
    ev.pedir("asn", "POST", f"/api/v1/asn/{folio}/inspection", rol="warehouse", json_body={"resultado": "CONFORME", "temperatura_registrada": 4.2, "observaciones": "Sellos íntegros"}, objetivo="Inspección agregada con $push", esperado=201)
    ev.pedir("asn", "GET", "/api/v1/asn?id_sku=2&estado=EN_TRANSITO&por_pagina=5", rol="buyer", objetivo="Filtrado por campo anidado y estado", esperado=200)
    ev.pedir("asn", "GET", "/api/v1/asn/analytics/summary", rol="buyer", objetivo="Pipeline de agregación ($unwind/$group/$sort)", esperado=200)
    ev.pedir("asn", "GET", "/api/v1/asn/NO-EXISTE", rol="buyer", objetivo="Folio inexistente", esperado=404)

    # ---------------- svc-planning ----------------
    ev.pedir("planning", "POST", "/api/v1/planning/forecast/run", rol="planner",
             json_body={"metodo": "SUAVIZACION_EXPONENCIAL", "horizonte": 7, "alpha": 0.3, "id_locacion": tienda, "id_sku": 1},
             objetivo="Corrida de pronóstico (linaje en PostgreSQL, serie en MongoDB)", esperado=201)
    ev.pedir("planning", "POST", "/api/v1/planning/forecast/run", rol="planner", json_body={"metodo": "MAGIA"}, objetivo="Método no soportado", esperado=400)
    ev.pedir("planning", "GET", f"/api/v1/planning/forecast/latest/1/{tienda}", rol="planner", objetivo="Última serie pronosticada (MongoDB)", esperado=200)
    ev.pedir("planning", "GET", "/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=3", rol="buyer", objetivo="Órdenes pendientes paginadas", esperado=200)
    ev.pedir("planning", "POST", f"/api/v1/planning/replenishment/orders/{uuid.uuid4()}/approve", rol="buyer", json_body={}, objetivo="Aprobar orden inexistente", esperado=404)
    ev.pedir("planning", "GET", f"/api/v1/planning/sku/1/full-context?id_locacion={tienda}", rol="planner", objetivo="Contexto híbrido PostgreSQL + MongoDB", esperado=200)
    ev.pedir("planning", "GET", "/api/v1/planning/forecast/analytics/kpis", rol="planner", objetivo="Métricas por modelo (agregación)", esperado=200)

    # ---------------- svc-alerts ----------------
    ev.pedir("alerts", "POST", f"/api/v1/alerts/scan?id_locacion={tienda}&dias=5", rol="store_manager", objetivo="Escaneo con lock distribuido → alertas en MongoDB + eventos en Redis Streams", esperado=200)
    _, activas = ev.pedir("alerts", "GET", f"/api/v1/alerts/active?id_locacion={tienda}&limite=3", rol="store_manager", objetivo="Alertas abiertas filtradas", esperado=200)
    if isinstance(activas, dict) and activas.get("alertas"):
        id_alerta = activas["alertas"][0].get("_id") or activas["alertas"][0].get("id")
        ev.pedir("alerts", "PATCH", f"/api/v1/alerts/{id_alerta}/resolve", rol="store_manager", objetivo="Atender alerta (inicia retención TTL)", esperado=200)
    ev.pedir("alerts", "PATCH", "/api/v1/alerts/zzz/resolve", rol="store_manager", objetivo="ObjectId inválido", esperado=400)
    ev.pedir("alerts", "GET", "/api/v1/alerts/esg/carbon-avoided", rol="auditor", accept="application/xml", objetivo="Reporte ESG en XML", esperado=200)
    ev.pedir("alerts", "GET", "/api/v1/alerts/analytics/kpis", rol="admin", objetivo="Alertas por locación y criticidad (agregación)", esperado=200)

    # ---------------- svc-audit ----------------
    ev.pedir("audit", "POST", "/api/v1/audit/log", rol="auditor",
             xml_body="<audit_log_request><accion>REVISION_CUMPLIMIENTO</accion><descripcion>Revisión de mermas de octubre</descripcion></audit_log_request>",
             objetivo="Registro explícito de cumplimiento (identidad tomada del JWT)", esperado=201)
    ev.pedir("audit", "GET", "/api/v1/audit/events?accion=REVISION_CUMPLIMIENTO&por_pagina=3", rol="auditor", objetivo="Bitácora filtrada y paginada", esperado=200)
    ev.pedir("audit", "GET", "/api/v1/audit/events?desde=2026-13-01", rol="auditor", objetivo="Fecha inválida", esperado=400)
    ev.pedir("audit", "GET", "/api/v1/audit/events", rol="store_manager", objetivo="Gerente sin permiso sobre la bitácora", esperado=403)
    ev.pedir("audit", "GET", "/api/v1/audit/traceability/no-es-uuid", rol="auditor", objetivo="Identificador de lote inválido", esperado=400)
    ev.pedir("audit", "GET", "/api/v1/audit/stream/recent?n=5", rol="auditor", objetivo="Eventos de dominio en Redis Streams", esperado=200)

    for svc in PUERTOS:
        ev.pedir(svc, "GET", "/health", accept="application/xml" if svc == "auth" else None, objetivo="Endpoint de salud con estado de dependencias", esperado=200)


def a_markdown(ev: Evidencias) -> str:
    ok = sum(1 for c in ev.casos if c["status"] == c["esperado"])
    lineas = [
        "# Evidencias de petición y respuesta — Microservicios FreshTrack",
        "",
        f"Generado el {datetime.now():%Y-%m-%d %H:%M} con `python scripts/generar_evidencias.py --host {ev.host}` "
        "mediante peticiones HTTP reales contra los contenedores. Los tokens se muestran abreviados.",
        "",
        f"**{ok} de {len(ev.casos)} casos** respondieron con el código esperado.",
        "",
        "| # | Servicio | Método | Ruta | Objetivo | Esperado | Obtenido |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, c in enumerate(ev.casos, 1):
        ruta = c["url"].split(str(PUERTOS[c["svc"]]), 1)[1]
        marca = "✅" if c["status"] == c["esperado"] else "⚠️"
        lineas.append(f"| [{i}](#caso-{i}) | {NOMBRES[c['svc']]} | {c['metodo']} | `{ruta}` | {c['objetivo']} | {c['esperado']} | {marca} {c['status']} |")
    for i, c in enumerate(ev.casos, 1):
        resp = c["respuesta"]
        formato = "xml" if "xml" in c["ctype"] else "json"
        if formato == "json":
            try:
                resp = json.dumps(json.loads(resp), ensure_ascii=False, indent=2)
            except ValueError:
                pass
        if len(resp) > MAX_RESPUESTA:
            resp = resp[:MAX_RESPUESTA] + "\n… (respuesta recortada)"
        lineas += [
            "",
            f'<a id="caso-{i}"></a>',
            f"## {i}. {NOMBRES[c['svc']]} — {c['metodo']} {c['url'].split(str(PUERTOS[c['svc']]), 1)[1].split('?')[0]}",
            "",
            f"- **Objetivo:** {c['objetivo']}",
            f"- **URL:** `{c['metodo']} {c['url']}`",
            f"- **Código HTTP:** `{c['status']}` (esperado `{c['esperado']}`)",
            "- **Headers:**",
            "",
            "```http",
            *[f"{k}: {v}" for k, v in c["headers"].items()],
            "```",
        ]
        if c["cuerpo"]:
            lineas += ["", "**Cuerpo de la petición:**", "", f"```{c['formato_cuerpo']}", c["cuerpo"], "```"]
        lineas += ["", f"**Respuesta ({c['ctype'] or 'sin contenido'}):**", "", f"```{formato}", resp, "```"]
    return "\n".join(lineas) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--salida", default=str(RAIZ / "docs" / "evidencias" / "EVIDENCIAS_REQUEST_RESPONSE.md"))
    args = ap.parse_args()
    ev = Evidencias(args.host)
    ejecutar(ev)
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(a_markdown(ev), encoding="utf-8")
    distintos = [c for c in ev.casos if c["status"] != c["esperado"]]
    print(f"{len(ev.casos)} casos → {salida}")
    for c in distintos:
        print(f"  ⚠ {c['metodo']} {c['url']} esperado {c['esperado']} obtenido {c['status']}: {c['respuesta'][:150]}")
    return 1 if distintos else 0


if __name__ == "__main__":
    sys.exit(main())
