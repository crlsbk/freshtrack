#!/usr/bin/env python3
"""
Simulacros de fallas y recuperación contra el stack LOCAL de docker compose.

Cada escenario detiene (docker stop) o congela (docker pause) UNA dependencia, registra lo que
responden la web, los microservicios y el panel de monitoreo, y SIEMPRE la restaura en un
bloque finally (docker start / docker unpause), midiendo el tiempo de recuperación.

Uso:
    .venv/bin/python docs/pruebas/scripts/simulacro_fallas.py microservicio
    .venv/bin/python docs/pruebas/scripts/simulacro_fallas.py redis|mongo|postgres|minio|timeout|archivos
    .venv/bin/python docs/pruebas/scripts/simulacro_fallas.py todos

Salida: docs/pruebas/fallas/<escenario>.txt (bitácora) y <escenario>.json (datos clave).
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun as c  # noqa: E402

FUGAS = re.compile(r"Traceback|psycopg|sqlalchemy|OperationalError|File \"/app|pymongo\.errors|redis\.exceptions", re.I)


def jpeg(n: int) -> bytes:
    cab = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return cab + b"\x00" * max(0, n - len(cab) - 2) + b"\xff\xd9"


def html(r: c.Resp) -> str:
    """Resumen de una respuesta HTML de la web: estado, título, mensajes visibles y fugas."""
    if r.status == 0:
        return f"SIN RESPUESTA en {r['ms']} ms ({r.get('error')})"
    t = r.get("texto") or ""
    titulo = re.search(r"<title>(.*?)</title>", t, re.S)
    msgs = re.findall(r'(?:class="[^"]*(?:flash|alert|error|mensaje|toast)[^"]*"[^>]*>)\s*([^<]{8,220})', t)
    fuga = FUGAS.search(t)
    loc = r.get("headers", {}).get("Location")
    return (f"HTTP {r.status} en {r['ms']} ms" + (f" → {loc}" if loc else "") +
            f" | título: {titulo.group(1).strip()[:70] if titulo else '-'}" +
            (f" | mensajes: {[m.strip() for m in msgs[:3]]}" if msgs else "") +
            f" | fuga de detalles internos: {'SÍ (' + fuga.group(0) + ')' if fuga else 'no'}")


def fuga_json(r: c.Resp) -> bool:
    return bool(FUGAS.search(json.dumps(r.get("json") or r.get("texto") or "", ensure_ascii=False, default=str)))


def snapshot_monitor(log: c.Bitacora, etiqueta: str = "panel /ops/status") -> dict:
    u, p = c.credenciales_monitor()
    r = c.pedir("GET", c.url("web", "/ops/status/api/snapshot?solo_lectura=1"), auth=(u, p), timeout=40)
    j = r.get("json") or {}
    serv = {s["nombre"]: f"{s['estado']}({s.get('http')})" for s in j.get("servicios", [])}
    log(f"  - {etiqueta}: HTTP {r.status} en {r['ms']} ms estado_global={j.get('estado_global')} "
        f"resumen={ {k: (j.get('resumen') or {}).get(k) for k in ('sanos', 'degradados', 'caidos', 'disponibilidad_actual_pct')} } "
        f"deps_caidas={[d.get('nombre') for d in j.get('dependencias_caidas', [])]}")
    log(f"      servicios: {serv}")
    return j


def health(log: c.Bitacora, titulo: str) -> dict:
    h = c.health_todos(timeout=15)
    log(f"  - /health de los 9 componentes ({titulo}):", c.tabla_health(h))
    return {s: r.status for s, r in h.items()}


def recuperacion(log: c.Bitacora, negocio, contenedor: str, svc_health: list[str] | None = None, limite: float = 240, paso: float = 1.0) -> dict:
    """Mide: health 200 (todos o los indicados), primera operación de negocio OK y contenedores healthy."""
    t0 = time.monotonic()
    objetivo = svc_health or list(c.PUERTOS)

    def health_ok():
        h = c.health_todos(timeout=5)
        return all(h[s].status == 200 for s in objetivo)

    t_health = c.esperar(health_ok, limite=limite, paso=0.5)
    t_negocio_rel = c.esperar(negocio, limite=limite, paso=paso)
    t_negocio = round(time.monotonic() - t0, 1) if t_negocio_rel is not None else None
    t_docker_rel = c.esperar(c.contenedores_sanos, limite=limite, paso=2)
    t_docker = round(time.monotonic() - t0, 1) if t_docker_rel is not None else None
    log(f"  - Recuperación tras iniciar {contenedor}: /health 200 en {t_health} s; primera operación de negocio OK a los {t_negocio} s; "
        f"todos los contenedores (healthy) a los {t_docker} s")
    log(c.estado_contenedores())
    return {"health_s": t_health, "negocio_s": t_negocio, "docker_healthy_s": t_docker}


# =============================================================================
def esc_microservicio(log: c.Bitacora) -> dict:
    out: dict = {}
    s_web, _ = c.sesion_web("planner")
    tp = c.login("planner")["token"]
    log.paso("Estado inicial")
    health(log, "antes")
    log.paso("docker stop freshtrack_svc_planning")
    log(c.docker("stop", "freshtrack_svc_planning"))
    t_stop = time.monotonic()
    try:
        log.paso("Lo que ve cada cliente con svc-planning detenido")
        out["directo"] = log.http("cliente directo (escritorio/Android en modo local) → :5006", c.pedir("GET", c.url("planning", "/api/v1/planning/transfers"), token=tp, timeout=20)).status
        g = log.http("gateway web /svc/planning/... (lo usa el navegador)", c.pedir("GET", c.url("web", "/svc/planning/api/v1/planning/transfers"), sesion=s_web, timeout=40))
        out["gateway"] = g.status
        r = c.pedir("GET", c.url("web", "/reabastecimiento"), sesion=s_web, timeout=60)
        log(f"  - web GET /reabastecimiento: {html(r)}")
        out["web_reabastecimiento"] = r.status
        r = c.pedir("GET", c.url("web", "/pronostico"), sesion=s_web, timeout=60)
        log(f"  - web GET /pronostico: {html(r)}")
        out["web_pronostico"] = r.status
        csrf = c.csrf_de(s_web, "/reabastecimiento")
        r = c.pedir("POST", c.url("web", "/reabastecimiento/generar"), sesion=s_web, data={"csrf_token": csrf, "horizonte": "7"}, allow_redirects=False, timeout=150)
        log(f"  - web POST /reabastecimiento/generar (botón «Generar»): {html(r)}")
        r2 = c.pedir("GET", c.url("web", "/reabastecimiento"), sesion=s_web, timeout=60)
        m = re.search(r"No se generaron recomendaciones:[^<]*", r2.get("texto") or "")
        log(f"      mensaje flash mostrado al usuario: «{m.group(0).strip() if m else 'no encontrado'}»")
        out["flash"] = m.group(0).strip() if m else None
        log.paso("Los demás servicios siguen operando")
        tg = c.login("store_manager")["token"]
        out["inventory"] = log.http("svc-inventory stock", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tg), 200).status
        out["checkout"] = log.http("svc-commercial checkout (venta 1 pza SKU 9)", c.pedir("POST", c.url("commercial", "/api/v1/commercial/checkout"), token=tg,
                                   json={"id_locacion": 3, "canal": "TIENDA", "lineas": [{"id_sku": 9, "cantidad": 1}]}), 250).status
        out["alerts"] = log.http("svc-alerts activas", c.pedir("GET", c.url("alerts", "/api/v1/alerts/active?por_pagina=1"), token=tg), 200).status
        log.paso("Monitoreo")
        out["health"] = health(log, "con planning detenido")
        out["monitor"] = snapshot_monitor(log).get("estado_global")
    finally:
        log.paso("docker start freshtrack_svc_planning (restauración)")
        log(c.docker("start", "freshtrack_svc_planning"))
        out["caida_s"] = round(time.monotonic() - t_stop, 1)
    out["recuperacion"] = recuperacion(
        log, lambda: c.pedir("GET", c.url("planning", "/api/v1/planning/transfers?por_pagina=1"), token=c.login("planner")["token"], timeout=5).status == 200,
        "freshtrack_svc_planning", ["planning"])
    out["monitor_despues"] = snapshot_monitor(log, "panel tras recuperación").get("estado_global")
    return out


# =============================================================================
def esc_redis(log: c.Bitacora) -> dict:
    out: dict = {}
    log.paso("Preparación: sesiones abiertas ANTES de la caída")
    tok_a = c.login("planner")["token"]
    tok_logout = c.login("buyer")["token"]
    tok_g = c.login("store_manager")["token"]
    s_web, rl = c.sesion_web("store_manager")
    log(f"  - token A (planner) emitido; token L (buyer) emitido; sesión web gerente {rl.status}")
    health(log, "antes")
    log.paso("docker stop freshtrack_redis")
    log(c.docker("stop", "freshtrack_redis"))
    t_stop = time.monotonic()
    tok_b = None
    try:
        log.paso("Autenticación con Redis caído")
        r = log.http("token A (emitido antes) en svc-inventory", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tok_a), 250)
        out["token_previo"] = r.status
        r = log.http("token A en svc-planning", c.pedir("GET", c.url("planning", "/api/v1/planning/transfers?por_pagina=1"), token=tok_a), 250)
        email, pwd = c.cuentas()["warehouse"]
        r = log.http("login nuevo (warehouse) en svc-auth", c.pedir("POST", c.url("auth", "/api/v1/auth/login"), json={"email": email, "password": pwd}), 300)
        out["login_nuevo"] = r.status
        if r.status == 200:
            tok_b = r["json"]["token"]
            out["token_nuevo"] = log.http("token B (emitido durante la caída) en svc-inventory",
                                          c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tok_b), 250).status
        out["logout"] = log.http("logout del token L durante la caída", c.pedir("POST", c.url("auth", "/api/v1/auth/logout"), token=tok_logout), 250).status
        r = log.http("reuso del token L tras su logout", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tok_logout), 300)
        out["token_revocado"] = f"{r.status} {(r.get('json') or {}).get('error')}"
        log.paso("Rate limiting (login API limitado a 10/min por IP con Redis)")
        estados = []
        for _ in range(12):
            rr = c.pedir("POST", c.url("auth", "/api/v1/auth/login"), json={"email": "noexiste@freshtrack.mx", "password": "x"})
            estados.append(rr.status)
        log(f"  - 12 logins fallidos seguidos → {estados}; cabeceras del último: {rr.get('headers')}")
        out["rate_limit"] = estados
        log.paso("Caché, carrito, importación de ventas y saga")
        out["catalogo"] = log.http("catálogo (Cache-Aside)", c.pedir("GET", c.url("catalog", "/api/v1/catalog/products?por_pagina=1"), token=tok_a), 300).status
        tbuyer = c.login("buyer")["token"] if out.get("login_nuevo") == 200 else tok_a
        out["import"] = log.http("importación de ventas (idempotencia en Redis)", c.pedir("POST", c.url("commercial", "/api/v1/commercial/sales/import"), token=tbuyer,
                                 json={"id_locacion": 3, "tickets": [{"folio_externo": f"REDIS-{uuid.uuid4().hex[:6]}", "lineas": [{"id_sku": 9, "cantidad": 1}]}]}), 300).status
        tg = c.login("store_manager")["token"] if out.get("login_nuevo") == 200 else None
        if tg:
            out["carrito"] = log.http("carrito POS temporal (Redis)", c.pedir("PUT", c.url("commercial", "/api/v1/commercial/cart/caja-redis"), token=tg,
                                      json={"lineas": [{"id_sku": 9, "cantidad": 1}]}), 300).status
            out["checkout"] = log.http("checkout (reserva FEFO con lock Redis)", c.pedir("POST", c.url("commercial", "/api/v1/commercial/checkout"), token=tg,
                                       json={"id_locacion": 3, "canal": "TIENDA", "lineas": [{"id_sku": 9, "cantidad": 1}]}), 300).status
            out["alerts_scan"] = log.http("escaneo de alertas (lock Redis)", c.pedir("POST", c.url("alerts", "/api/v1/alerts/scan"), token=tg, params={"id_locacion": 3, "dias": 3}), 300).status
        log.paso("Web")
        r = c.pedir("GET", c.url("web", "/inventario"), sesion=s_web, timeout=60)
        log(f"  - sesión web abierta antes → GET /inventario: {html(r)}")
        out["web_sesion_previa"] = r.status
        s2, r2 = c.sesion_web("planner")
        log(f"  - login web nuevo (planner): {html(r2)}")
        out["web_login"] = r2.status
        log.paso("Monitoreo")
        out["health"] = health(log, "con Redis detenido")
        out["monitor"] = snapshot_monitor(log).get("estado_global")
    finally:
        log.paso("docker start freshtrack_redis (restauración)")
        log(c.docker("start", "freshtrack_redis"))
        out["caida_s"] = round(time.monotonic() - t_stop, 1)
    # Operación de negocio que NECESITA Redis: guardar un carrito POS (token emitido antes de la caída).
    out["recuperacion"] = recuperacion(log, lambda: c.pedir("PUT", c.url("commercial", "/api/v1/commercial/cart/caja-recuperacion"), token=tok_g,
                                       json={"lineas": [{"id_sku": 9, "cantidad": 1}]}, timeout=5).status == 200, "freshtrack_redis")
    log.paso("Después de la recuperación: ¿siguen sirviendo los tokens?")
    out["token_previo_despues"] = log.http("token A (emitido antes de la caída)", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tok_a), 250).status
    if tok_b:
        r = log.http("token B (emitido DURANTE la caída)", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tok_b), 300)
        out["token_nuevo_despues"] = f"{r.status} {(r.get('json') or {}).get('error') or ''}".strip()
    r = log.http("token L (logout durante la caída)", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tok_logout), 300)
    out["token_revocado_despues"] = f"{r.status} {(r.get('json') or {}).get('error') or ''}".strip()
    return out


# =============================================================================
def esc_mongo(log: c.Bitacora) -> dict:
    out: dict = {}
    ta = c.login("admin")["token"]
    tg = c.login("store_manager")["token"]
    s_web, _ = c.sesion_web("admin")
    health(log, "antes")
    log.paso("docker stop freshtrack_mongo")
    log(c.docker("stop", "freshtrack_mongo"))
    t_stop = time.monotonic()
    try:
        log.paso("Endpoints que dependen de MongoDB")
        for clave, svc, ruta in [("alerts_active", "alerts", "/api/v1/alerts/active"), ("alerts_kpis", "alerts", "/api/v1/alerts/analytics/kpis"),
                                 ("asn_list", "asn", "/api/v1/asn?por_pagina=1"), ("forecast_latest", "planning", "/api/v1/planning/forecast/latest/9/3"),
                                 ("audit_events", "audit", "/api/v1/audit/events?por_pagina=1")]:
            r = log.http(f"{svc} {ruta}", c.pedir("GET", c.url(svc, ruta), token=ta), 300)
            out[clave] = r.status
            if fuga_json(r):
                log("      ⚠ la respuesta contiene detalles internos")
        log.paso("Lo que sigue funcionando (PostgreSQL)")
        out["stock"] = log.http("inventario", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tg), 200).status
        out["fefo"] = log.http("cola FEFO", c.pedir("GET", c.url("inventory", "/api/v1/inventory/fefo-queue/9/3"), token=tg), 200).status
        out["checkout"] = log.http("checkout POS", c.pedir("POST", c.url("commercial", "/api/v1/commercial/checkout"), token=tg,
                                                             json={"id_locacion": 3, "canal": "TIENDA", "lineas": [{"id_sku": 9, "cantidad": 1}]}), 250).status
        out["login"] = log.http("login", c.pedir("POST", c.url("auth", "/api/v1/auth/login"), json=dict(zip(("email", "password"), c.cuentas()["auditor"]))), 150).status
        out["forecast_run"] = log.http("pronóstico (serie se guarda en Mongo)", c.pedir("POST", c.url("planning", "/api/v1/planning/forecast/run"), token=c.login("planner")["token"],
                                       json={"metodo": "AUTO", "horizonte": 7, "id_locacion": 3}, timeout=120), 300).status
        log.paso("Web")
        for ruta in ("/alertas", "/panel", "/inventario", "/despachos"):
            r = c.pedir("GET", c.url("web", ruta), sesion=s_web, timeout=90)
            log(f"  - web GET {ruta}: {html(r)}")
            out[f"web{ruta}"] = r.status
        out["health"] = health(log, "con MongoDB detenido")
        out["monitor"] = snapshot_monitor(log).get("estado_global")
    finally:
        log.paso("docker start freshtrack_mongo (restauración)")
        log(c.docker("start", "freshtrack_mongo"))
        out["caida_s"] = round(time.monotonic() - t_stop, 1)
    out["recuperacion"] = recuperacion(log, lambda: c.pedir("GET", c.url("alerts", "/api/v1/alerts/active?por_pagina=1"), token=ta, timeout=8).status == 200,
                                       "freshtrack_mongo")
    return out


# =============================================================================
def esc_postgres(log: c.Bitacora) -> dict:
    out: dict = {}
    ta = c.login("admin")["token"]
    tg = c.login("store_manager")["token"]
    s_web, _ = c.sesion_web("store_manager")
    health(log, "antes")
    log.paso("docker stop freshtrack_db")
    log(c.docker("stop", "freshtrack_db"))
    t_stop = time.monotonic()
    try:
        log.paso("Health de todos los componentes")
        out["health"] = health(log, "con PostgreSQL detenido")
        log.paso("API con PostgreSQL caído")
        email, pwd = c.cuentas()["buyer"]
        pruebas = [("login", "POST", "auth", "/api/v1/auth/login", None, {"email": email, "password": pwd}),
                   ("stock", "GET", "inventory", "/api/v1/inventory/stock?por_pagina=1", tg, None),
                   ("productos", "GET", "catalog", "/api/v1/catalog/products?por_pagina=1", tg, None),
                   ("checkout", "POST", "commercial", "/api/v1/commercial/checkout", tg, {"id_locacion": 3, "canal": "TIENDA", "lineas": [{"id_sku": 9, "cantidad": 1}]}),
                   ("alertas_mongo", "GET", "alerts", "/api/v1/alerts/active?por_pagina=1", ta, None),
                   ("asn_mongo", "GET", "asn", "/api/v1/asn?por_pagina=1", ta, None),
                   ("auditoria", "GET", "audit", "/api/v1/audit/events?por_pagina=1", ta, None),
                   ("sin_token", "GET", "inventory", "/api/v1/inventory/stock", None, None)]
        for clave, met, svc, ruta, tok, cuerpo in pruebas:
            r = log.http(f"{clave}: {svc}", c.pedir(met, c.url(svc, ruta), token=tok, json=cuerpo, timeout=40), 350)
            out[clave] = f"{r.status} {(r.get('json') or {}).get('error') or ''}".strip()
            out[f"{clave}_cid"] = bool(r.get("correlation_id")) and bool((r.get("json") or {}).get("correlation_id", True))
            if fuga_json(r):
                log("      ⚠ la respuesta contiene detalles internos")
                out[f"{clave}_fuga"] = True
        log.paso("Web")
        for ruta in ("/login", "/inventario", "/ventas"):
            r = c.pedir("GET", c.url("web", ruta), sesion=s_web, timeout=60, allow_redirects=False)
            log(f"  - web GET {ruta}: {html(r)}")
            out[f"web{ruta}"] = r.status
        _, r = c.sesion_web("planner")
        log(f"  - web POST /login (planner): {html(r)}")
        out["web_login"] = r.status
        out["monitor"] = snapshot_monitor(log).get("estado_global")
    finally:
        log.paso("docker start freshtrack_db (restauración, SIN reiniciar los servicios)")
        log(c.docker("start", "freshtrack_db"))
        out["caida_s"] = round(time.monotonic() - t_stop, 1)
    t_pg = c.esperar(lambda: "accepting" in c.docker("exec", "freshtrack_db", "pg_isready"), limite=120, paso=0.5)
    log(f"  - pg_isready acepta conexiones a los {t_pg} s")
    out["pg_ready_s"] = t_pg
    out["recuperacion"] = recuperacion(log, lambda: c.pedir("GET", c.url("inventory", "/api/v1/inventory/fefo-queue/9/3"), token=tg, timeout=8).status == 200,
                                       "freshtrack_db", paso=0.5)
    log.paso("Tras la recuperación: token y sesión web emitidos antes de la caída")
    out["token_previo_despues"] = log.http("token del gerente emitido antes", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tg), 200).status
    r = c.pedir("GET", c.url("web", "/inventario"), sesion=s_web, timeout=60)
    log(f"  - sesión web previa → /inventario: {html(r)}")
    out["web_despues"] = r.status
    return out


# =============================================================================
def _oc_y_asn(ta: str) -> tuple[str | None, str | None]:
    oc = c.pedir("GET", c.url("planning", "/api/v1/planning/purchase-orders?por_pagina=1"), token=ta)
    asn = c.pedir("GET", c.url("asn", "/api/v1/asn?por_pagina=50"), token=ta)
    id_oc = ((oc.get("json") or {}).get("ordenes") or [{}])[0].get("id_oc")
    folio = next((a["folio_asn"] for a in (asn.get("json") or {}).get("avisos_asn", []) if a.get("folio_oc")), None)
    return id_oc, folio


def esc_minio(log: c.Bitacora) -> dict:
    out: dict = {}
    ta = c.login("admin")["token"]
    tb = c.login("buyer")["token"]
    tg = c.login("store_manager")["token"]
    id_oc, folio = _oc_y_asn(ta)
    log(f"  - OC de referencia {id_oc}; ASN de referencia {folio}")
    s_web, _ = c.sesion_web("admin")
    health(log, "antes")
    log.paso("docker stop freshtrack_minio")
    log(c.docker("stop", "freshtrack_minio"))
    t_stop = time.monotonic()
    try:
        log.paso("Documentos PDF")
        out["oc_pdf"] = log.http("PDF de OC existente (svc-planning)", c.pedir("GET", c.url("planning", f"/api/v1/planning/purchase-orders/{id_oc}/pdf"), token=ta, timeout=40), 300).status
        out["asn_pdf"] = log.http("PDF de etiquetas ASN existente (svc-asn)", c.pedir("GET", c.url("asn", f"/api/v1/asn/{folio}/labels-pdf"), token=ta, timeout=40), 300).status
        r = c.pedir("GET", c.url("web", f"/compras/ordenes/{id_oc}/pdf"), sesion=s_web, timeout=60, allow_redirects=False)
        log(f"  - web GET /compras/ordenes/<id>/pdf: HTTP {r.status} {r.get('content_type')} {r.get('bytes')} bytes en {r['ms']} ms")
        out["web_oc_pdf"] = r.status
        r = log.http("OC nueva (genera PDF)", c.pedir("POST", c.url("planning", "/api/v1/planning/purchase-orders"), token=tb, timeout=60,
                                                   json={"id_proveedor": 1, "lineas": [{"id_sku": 9, "id_locacion_destino": 3, "cantidad_lotes": 1}], "observaciones": "Simulacro bucket caído"}), 700)
        out["oc_nueva"] = r.status
        if r.status == 201:
            out["oc_nueva_pdf"] = log.http("PDF de la OC creada durante la caída", c.pedir("GET", c.url("planning", f"/api/v1/planning/purchase-orders/{r['json']['id_oc']}/pdf"), token=tb, timeout=40), 200).status
            out["oc_nueva_id"] = r["json"]["id_oc"]
        log.paso("Evidencia fotográfica (app móvil)")
        r = log.http("POST /commercial/evidence (JPEG 50 KB)", c.pedir("POST", c.url("commercial", "/api/v1/commercial/evidence"), token=tg, timeout=40,
                                                                    files={"archivo": ("f.jpg", io.BytesIO(jpeg(50_000)), "image/jpeg")}, data={"tipo": "MERMA", "id_locacion": "3"}), 300)
        out["evidencia"] = f"{r.status} {(r.get('json') or {}).get('error') or ''}".strip()
        fefo = c.pedir("GET", c.url("inventory", "/api/v1/inventory/fefo-queue/9/3"), token=tg)["json"]["lotes_fefo"]
        out["merma_sin_foto"] = log.http("merma sin foto (lo que sugiere el mensaje)", c.pedir("POST", c.url("commercial", "/api/v1/commercial/shrinkage"), token=tg,
                                         json={"id_lote": fefo[-1]["id_lote"], "id_locacion": 3, "cantidad": 1, "causa": "DANO", "observacion": "Simulacro bucket caído"}), 250).status
        log.paso("Health y monitoreo")
        out["health"] = health(log, "con el bucket detenido")
        out["monitor"] = snapshot_monitor(log).get("estado_global")
        log.paso("¿Qué hace Docker con los healthchecks? (interval 15 s × 5 reintentos)")
        t_unh = c.esperar(lambda: "unhealthy" in c.docker("ps", "--filter", "name=freshtrack_svc_auth", "--format", "{{.Status}}"), limite=110, paso=5)
        log(f"  - freshtrack_svc_auth pasó a (unhealthy) a los {t_unh} s de espera adicional")
        log(c.estado_contenedores())
        out["docker_unhealthy_tras_s"] = t_unh
    finally:
        log.paso("docker start freshtrack_minio (restauración)")
        log(c.docker("start", "freshtrack_minio"))
        out["caida_s"] = round(time.monotonic() - t_stop, 1)
    out["recuperacion"] = recuperacion(log, lambda: c.pedir("POST", c.url("commercial", "/api/v1/commercial/evidence"), token=tg, timeout=10,
                                       files={"archivo": ("f.jpg", io.BytesIO(jpeg(2000)), "image/jpeg")}, data={"tipo": "OTRO", "id_locacion": "3"}).status == 201,
                                       "freshtrack_minio", paso=3.5)
    if out.get("oc_nueva_id"):
        out["oc_nueva_pdf_despues"] = log.http("PDF de la OC creada durante la caída (ya con bucket)", c.pedir("GET", c.url("planning", f"/api/v1/planning/purchase-orders/{out['oc_nueva_id']}/pdf"), token=tb), 200).status
    return out


# =============================================================================
def esc_timeout(log: c.Bitacora) -> dict:
    out: dict = {}
    s_web, _ = c.sesion_web("planner")
    tp = c.login("planner")["token"]
    tg = c.login("store_manager")["token"]
    health(log, "antes")

    # --- A: servicio congelado -------------------------------------------------
    log.paso("A) docker pause freshtrack_svc_planning (el proceso existe pero no responde)")
    log(c.docker("pause", "freshtrack_svc_planning"))
    t0 = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            f_dir = pool.submit(c.pedir, "GET", c.url("planning", "/api/v1/planning/transfers"), token=tp, timeout=20)
            f_gw = pool.submit(c.pedir, "GET", c.url("web", "/svc/planning/api/v1/planning/transfers"), sesion=s_web, timeout=60)
            f_pron = pool.submit(c.pedir, "GET", c.url("web", "/pronostico"), sesion=c.sesion_web("planner")[0], timeout=60)
            f_mon = pool.submit(snapshot_monitor, log, "panel /ops/status con planning congelado")
            f_inv = pool.submit(c.pedir, "GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tg, timeout=20)
            r = log.http("cliente con timeout de 20 s (como Android/escritorio) → :5006", f_dir.result(), 200)
            out["A_cliente_20s"] = f"{r.status} {r['ms']} ms"
            r = log.http("gateway web /svc/planning (timeout interno 30 s)", f_gw.result(), 300)
            out["A_gateway"] = f"{r.status} {r['ms']} ms"
            r = f_pron.result()
            log(f"  - web /pronostico (llamada a drift con timeout 10 s y respaldo local): {html(r)}")
            out["A_web_pronostico"] = f"{r.status} {r['ms']} ms"
            out["A_monitor"] = f_mon.result().get("estado_global")
            r = log.http("otro servicio (inventory) mientras tanto", f_inv.result(), 150)
            out["A_inventory"] = f"{r.status} {r['ms']} ms"
    finally:
        log(c.docker("unpause", "freshtrack_svc_planning"))
    out["A_recuperacion_s"] = c.esperar(lambda: c.pedir("GET", c.url("planning", "/health"), timeout=3).status == 200, limite=60)
    log(f"  - planning vuelve a responder /health a los {out['A_recuperacion_s']} s del unpause (pausa total {round(time.monotonic() - t0, 1)} s)")

    # --- B: Redis congelado --------------------------------------------------------
    log.paso("B) docker pause freshtrack_redis (sockets abiertos sin respuesta; socket_timeout=2 s)")
    log(c.docker("pause", "freshtrack_redis"))
    try:
        for i in range(3):
            r = log.http(f"inventario con token válido (intento {i + 1})", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tg, timeout=60), 150)
            out[f"B_inventory_{i + 1}"] = f"{r.status} {r['ms']} ms"
        r = log.http("health de svc-auth", c.pedir("GET", c.url("auth", "/health"), timeout=30), 250)
        out["B_health"] = f"{r.status} {r['ms']} ms"
    finally:
        log(c.docker("unpause", "freshtrack_redis"))
    out["B_recuperacion_s"] = c.esperar(c.todo_sano, limite=60)
    log(f"  - todo /health 200 a los {out['B_recuperacion_s']} s del unpause")

    # --- C: PostgreSQL congelado ---------------------------------------------------
    log.paso("C) docker pause freshtrack_db (conexiones del pool abiertas sin respuesta)")
    log(c.docker("pause", "freshtrack_db"))
    t0 = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            f1 = pool.submit(c.pedir, "GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tg, timeout=45)
            f2 = pool.submit(c.pedir, "GET", c.url("inventory", "/health"), timeout=45)
            f3 = pool.submit(c.pedir, "GET", c.url("web", "/health"), timeout=45)
            for clave, f in (("C_stock", f1), ("C_health_inventory", f2), ("C_health_web", f3)):
                r = log.http(clave, f.result(), 250)
                out[clave] = f"{r.status} {r['ms']} ms"
    finally:
        log(c.docker("unpause", "freshtrack_db"))
    log(f"  - pausa de PostgreSQL: {round(time.monotonic() - t0, 1)} s")
    out["C_recuperacion_s"] = c.esperar(c.todo_sano, limite=120)
    log(f"  - todo /health 200 a los {out['C_recuperacion_s']} s del unpause")
    r = log.http("primera operación tras el unpause", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=tg, timeout=30), 120)
    out["C_despues"] = f"{r.status} {r['ms']} ms"
    log(c.estado_contenedores())
    return out


# =============================================================================
def esc_archivos(log: c.Bitacora) -> dict:
    out: dict = {}
    tg = c.login("store_manager")["token"]
    casos = [("1 KB JPEG", jpeg(1024), "f.jpg", "image/jpeg"),
             ("3.9 MB JPEG", jpeg(int(3.9 * 1024 * 1024)), "f.jpg", "image/jpeg"),
             ("4.1 MB JPEG", jpeg(int(4.1 * 1024 * 1024)), "f.jpg", "image/jpeg"),
             ("7.9 MB JPEG (justo debajo de 8 MB)", jpeg(int(7.9 * 1024 * 1024)), "f.jpg", "image/jpeg"),
             ("8.1 MB JPEG (justo arriba de 8 MB)", jpeg(int(8.1 * 1024 * 1024)), "f.jpg", "image/jpeg"),
             ("PDF renombrado a .jpg (no es imagen)", b"%PDF-1.4\n" + b"0" * 50_000, "f.jpg", "image/jpeg"),
             ("texto plano", b"hola " * 2000, "f.txt", "text/plain"),
             ("archivo vacío", b"", "f.jpg", "image/jpeg")]
    for etiqueta, datos, nombre, ct in casos:
        r = log.http(f"evidencia {etiqueta}", c.pedir("POST", c.url("commercial", "/api/v1/commercial/evidence"), token=tg, timeout=60,
                                                      files={"archivo": (nombre, io.BytesIO(datos), ct)}, data={"tipo": "OTRO", "id_locacion": "3"}), 300)
        out[etiqueta] = f"{r.status} {(r.get('json') or {}).get('error') or ''}".strip()
    log.paso("Otros límites de tamaño")
    grande = "<?xml version=\"1.0\"?><sales_import_request><id_locacion>3</id_locacion><tickets>" + \
             "".join(f"<ticket><folio_externo>BIG-{i}</folio_externo><lineas><linea><id_sku>9</id_sku><cantidad>1</cantidad></linea></lineas></ticket>" for i in range(45_000)) + \
             "</tickets></sales_import_request>"
    log(f"  - XML de importación de {len(grande) / 1024 / 1024:.1f} MB")
    r = log.http("importación XML > 4 MB", c.pedir("POST", c.url("commercial", "/api/v1/commercial/sales/import"), token=c.login("buyer")["token"],
                                                   data=grande.encode(), headers={"Content-Type": "application/xml"}, timeout=60), 300)
    out["import_xml_grande"] = f"{r.status} {(r.get('json') or {}).get('error') or ''}".strip()
    s_web, _ = c.sesion_web("store_manager")
    r = c.pedir("POST", c.url("web", "/svc/commercial/api/v1/commercial/evidence"), sesion=s_web, timeout=60,
                files={"archivo": ("f.jpg", io.BytesIO(jpeg(int(5 * 1024 * 1024))), "image/jpeg")}, data={"tipo": "OTRO", "id_locacion": "3"},
                headers={"X-CSRF-Token": c.csrf_de(s_web, "/inventario") or ""})
    log(f"  - gateway web con imagen de 5 MB: HTTP {r.status} {r['ms']} ms {(r.get('json') or {}).get('error') or (r.get('texto') or '')[:120]}")
    out["gateway_web_5MB"] = r.status
    return out


ESCENARIOS = {"microservicio": esc_microservicio, "redis": esc_redis, "mongo": esc_mongo, "postgres": esc_postgres,
              "minio": esc_minio, "timeout": esc_timeout, "archivos": esc_archivos}


def correr(nombre: str) -> dict:
    log = c.Bitacora(nombre)
    log(f"Simulacro «{nombre}» — inicio {c.ahora()}")
    log(c.estado_contenedores())
    try:
        datos = ESCENARIOS[nombre](log)
    finally:
        # Red de seguridad: nada queda detenido ni congelado.
        for cont in c.CONTENEDORES_INFRA + c.CONTENEDORES_APP:
            est = c.docker("inspect", "-f", "{{.State.Status}}", cont)
            if est == "paused":
                log(f"  ! {cont} seguía en pausa → unpause: {c.docker('unpause', cont)}")
            elif est in ("exited", "created"):
                log(f"  ! {cont} seguía detenido → start: {c.docker('start', cont)}")
    log(f"\nFin {c.ahora()}")
    (c.DIR_FALLAS / f"{nombre}.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log.cerrar()
    return datos


if __name__ == "__main__":
    pedidos = sys.argv[1:] or ["todos"]
    if pedidos == ["todos"]:
        pedidos = list(ESCENARIOS)
    for n in pedidos:
        print(json.dumps(correr(n), ensure_ascii=False, indent=1, default=str))
