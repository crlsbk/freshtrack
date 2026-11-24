#!/usr/bin/env python3
"""
Pruebas de sistema (extremo a extremo) contra el stack LOCAL de docker compose.

Recorre los flujos de negocio por las APIs HTTP reales (y la web cuando aplica) y deja:
  docs/pruebas/sistema/salida_pruebas_sistema.txt   bitácora con cada petición/respuesta (tokens ocultos)
  docs/pruebas/sistema/resultados_pruebas_sistema.json  un registro por caso (PASA/FALLA)

Uso:  .venv/bin/python docs/pruebas/scripts/pruebas_sistema.py
"""

from __future__ import annotations

import io
import json
import sys
import time
import traceback
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun as c  # noqa: E402

LOG = c.Bitacora("salida_pruebas_sistema", c.DIR_SISTEMA)
CASOS: list[dict] = []
CTX: dict = {}
TIENDA, DESTINO = 3, 4


def jpeg(n_bytes: int) -> bytes:
    """Bytes con cabecera JPEG real (magic bytes FF D8 FF) y relleno hasta n_bytes."""
    cab = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return cab + b"\x00" * max(0, n_bytes - len(cab) - 2) + b"\xff\xd9"


def caso(cid: str, flujo: str, pre: str, pasos: str, esperado: str):
    def deco(fn):
        def run():
            LOG.paso(f"{cid} · {flujo}")
            t0 = time.perf_counter()
            reg = {"id": cid, "flujo": flujo, "precondiciones": pre, "pasos": pasos, "esperado": esperado}
            try:
                ok, obtenido = fn()
            except Exception as exc:  # noqa: BLE001
                LOG("  EXCEPCIÓN: " + "".join(traceback.format_exception_only(type(exc), exc)).strip())
                ok, obtenido = False, f"Excepción en la prueba: {type(exc).__name__}: {exc}"
            reg.update(obtenido=obtenido, estado="PASA" if ok else "FALLA", segundos=round(time.perf_counter() - t0, 2))
            LOG(f"  => {reg['estado']}: {obtenido}")
            CASOS.append(reg)
        CASOS_FN.append(run)
        return fn
    return deco


CASOS_FN: list = []
tok = {}


def T(rol: str) -> str:
    if rol not in tok:
        tok[rol] = c.login(rol)["token"]
    return tok[rol]


# =============================================================================
@caso("PS-01", "Salud de la plataforma", "docker compose arriba", "GET /health en web y 8 servicios",
      "9 × HTTP 200 HEALTHY con postgres/mongo/redis/bucket en true")
def _():
    h = c.health_todos()
    LOG(c.tabla_health(h))
    sanos = [s for s, r in h.items() if r.status == 200 and r["json"].get("status") == "HEALTHY"]
    return len(sanos) == 9, f"{len(sanos)}/9 componentes HEALTHY"


@caso("PS-02", "Login por rol (svc-auth)", "Cuentas demo del seed", "POST /api/v1/auth/login para los 7 roles",
      "200 con JWT y rol correcto en cada cuenta")
def _():
    oks = []
    for rol in c.cuentas():
        email, pwd = c.cuentas()[rol]
        r = LOG.http(rol, c.pedir("POST", c.url("auth", "/api/v1/auth/login"), json={"email": email, "password": pwd}), 250)
        if r.status == 200 and r["json"]["usuario"]["rol"] == rol:
            oks.append(rol)
            tok[rol] = r["json"]["token"]
    return len(oks) == len(c.cuentas()), f"{len(oks)}/{len(c.cuentas())} roles con login 200 y rol correcto"


@caso("PS-03", "Login inválido y RBAC entre servicios", "Tokens de PS-02",
      "Login con contraseña errónea; buyer → GET /audit/events; auditor → GET /audit/events; sin token → inventory",
      "401 credenciales; 403 acceso_denegado (buyer); 200 (auditor); 401 token_requerido")
def _():
    r1 = LOG.http("pwd errónea", c.pedir("POST", c.url("auth", "/api/v1/auth/login"), json={"email": "buyer@freshtrack.mx", "password": "incorrecta"}), 300)
    r2 = LOG.http("buyer→audit", c.pedir("GET", c.url("audit", "/api/v1/audit/events?por_pagina=1"), token=T("buyer")), 300)
    r3 = LOG.http("auditor→audit", c.pedir("GET", c.url("audit", "/api/v1/audit/events?por_pagina=1"), token=T("auditor")), 200)
    r4 = LOG.http("sin token", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock")), 300)
    ok = r1.status == 401 and r2.status == 403 and r3.status == 200 and r4.status == 401
    return ok, f"login malo={r1.status}, buyer→audit={r2.status} {r2['json'].get('error') if r2.get('json') else ''}, auditor→audit={r3.status}, sin token={r4.status}"


@caso("PS-04", "Revocación: logout invalida el token en todos los servicios", "Sesión nueva del planner",
      "Login → usar token en inventory/planning → POST /auth/logout → reusar token en inventory, planning y audit",
      "Antes 200; después 401 token_revocado en los 3 servicios")
def _():
    t = c.login("planner")["token"]
    a = LOG.http("antes inventory", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=t), 150)
    b = LOG.http("antes planning", c.pedir("GET", c.url("planning", "/api/v1/planning/replenishment/orders?por_pagina=1"), token=t), 150)
    lo = LOG.http("logout", c.pedir("POST", c.url("auth", "/api/v1/auth/logout"), token=t), 200)
    despues = [LOG.http(f"después {s}", c.pedir("GET", c.url(s, ruta), token=t), 250) for s, ruta in
               [("inventory", "/api/v1/inventory/stock"), ("planning", "/api/v1/planning/replenishment/orders"), ("audit", "/api/v1/audit/events")]]
    ok = a.status == 200 and b.status == 200 and lo.status == 200 and all(
        d.status == 401 and d["json"].get("error") == "token_revocado" for d in despues)
    return ok, f"antes {a.status}/{b.status}; logout {lo.status}; después " + ", ".join(f"{d.status} {d['json'].get('error')}" for d in despues)


@caso("PS-05", "Revocación administrativa y logout web", "admin y planner con sesión",
      "admin DELETE /auth/sessions/{planner}; token del planner en planning. Web: login gerente → gateway /svc/inventory → logout → reintento",
      "401 tras cierre forzado; en la web el gateway deja de responder datos tras logout (redirige a /login)")
def _():
    p = c.login("planner")
    r0 = LOG.http("planner antes", c.pedir("GET", c.url("planning", "/api/v1/planning/transfers?por_pagina=1"), token=p["token"]), 120)
    rd = LOG.http("admin cierra sesiones", c.pedir("DELETE", c.url("auth", f"/api/v1/auth/sessions/{p['usuario']['id_usuario']}"), token=T("admin")), 250)
    r1 = LOG.http("planner después", c.pedir("GET", c.url("planning", "/api/v1/planning/transfers?por_pagina=1"), token=p["token"]), 250)
    tok.pop("planner", None)
    s, rl = c.sesion_web("store_manager")
    LOG.http("login web", rl, 150)
    g1 = LOG.http("gateway antes", c.pedir("GET", c.url("web", "/svc/inventory/api/v1/inventory/stock?por_pagina=1"), sesion=s, allow_redirects=False), 150)
    csrf = c.csrf_de(s, "/inventario")
    lo = LOG.http("logout web", c.pedir("POST", c.url("web", "/logout"), sesion=s, data={"csrf_token": csrf}, allow_redirects=False), 120)
    g2 = LOG.http("gateway después", c.pedir("GET", c.url("web", "/svc/inventory/api/v1/inventory/stock?por_pagina=1"), sesion=s, allow_redirects=False), 150)
    ok = r0.status == 200 and rd.status == 200 and r1.status == 401 and g1.status == 200 and g2.status in (302, 401)
    return ok, (f"API: antes {r0.status}, cierre {rd.status}, después {r1.status} {r1['json'].get('error')}; "
                f"web: gateway antes {g1.status}, logout {lo.status}, gateway después {g2.status} → {g2.get('headers', {}).get('Location', '')}")


@caso("PS-06", "Orden de compra con PDF en el bucket", "buyer; proveedor 1 con SKU 9",
      "POST /planning/purchase-orders (1 lote SKU 9 → tienda 3); GET .../pdf",
      "201 con folio OC y documento_pdf en S3; PDF descargable (application/pdf)")
def _():
    r = LOG.http("crear OC", c.pedir("POST", c.url("planning", "/api/v1/planning/purchase-orders"), token=T("buyer"),
                                      json={"id_proveedor": 1, "lineas": [{"id_sku": 9, "id_locacion_destino": TIENDA, "cantidad_lotes": 1}],
                                            "observaciones": "Prueba de sistema PS-06"}), 500)
    if r.status != 201:
        return False, f"crear OC → {r.status}"
    CTX["oc"] = r["json"]
    pdf = LOG.http("PDF OC", c.pedir("GET", c.url("planning", f"/api/v1/planning/purchase-orders/{r['json']['id_oc']}/pdf"), token=T("buyer")), 150)
    ok = pdf.status == 200 and "pdf" in pdf["content_type"]
    return ok, f"OC {r['json']['folio']} 201, PDF en bucket {r['json']['documento_pdf']['object_key']}; descarga {pdf.status} {pdf['content_type']} {pdf['bytes']} bytes"


@caso("PS-07", "ASN desde la OC con etiquetas QR firmadas", "OC de PS-06",
      "POST /asn/from-purchase-order; GET /asn/labels?codigo=<payload QR>; GET /asn/{folio}/labels-pdf",
      "201 EN_TRANSITO con etiqueta FTL; firma_valida=true; PDF de etiquetas descargable")
def _():
    oc = CTX["oc"]
    cad = (date.today() + timedelta(days=4)).isoformat()
    r = LOG.http("ASN", c.pedir("POST", c.url("asn", "/api/v1/asn/from-purchase-order"), token=T("buyer"), json={
        "id_oc": oc["id_oc"], "transporte": {"chofer": "Prueba Sistema", "placas": "NL-0000-A", "temperatura_salida_c": 3.5},
        "partidas": [{"id_sku": 9, "id_locacion_destino": TIENDA, "cantidad_declarada": 50, "lote_proveedor": f"LP-PS07-{uuid.uuid4().hex[:4].upper()}", "fecha_caducidad": cad}]}), 500)
    if r.status != 201:
        return False, f"ASN → {r.status}"
    CTX["asn"] = r["json"]
    etq = r["json"]["etiquetas"][0]
    lab = LOG.http("consulta etiqueta (payload QR)", c.pedir("GET", c.url("asn", "/api/v1/asn/labels"), token=T("warehouse"),
                                                           params={"codigo": etq["qr_payload"]}), 300)
    pdf = LOG.http("PDF etiquetas", c.pedir("GET", c.url("asn", f"/api/v1/asn/{r['json']['folio_asn']}/labels-pdf"), token=T("buyer")), 150)
    ok = lab.status == 200 and lab["json"].get("firma_valida") is True and pdf.status == 200 and "pdf" in pdf["content_type"]
    return ok, f"ASN {r['json']['folio_asn']} 201; etiqueta {etq['codigo_etiqueta']} firma_valida={lab.get('json', {}).get('firma_valida')}; PDF {pdf.status} {pdf['bytes']} bytes"


@caso("PS-08", "Recepción por escaneo QR → lote en cola FEFO (idempotente)", "Etiqueta de PS-07; warehouse de la tienda 3",
      "POST /inventory/receive-scan con Idempotency-Key; repetir con la misma clave; repetir sin clave; GET /fefo-queue/9/3",
      "201 lote creado; repetición con la misma clave devuelve el mismo lote (idempotente=true); sin clave 409; lote visible en FEFO")
def _():
    etq = CTX["asn"]["etiquetas"][0]
    cuerpo = {"codigo_etiqueta": etq["qr_payload"], "id_locacion_recepcion": TIENDA, "cantidad_recibida": 50,
              "temperatura_registrada_c": 4.1, "resultado_inspeccion": "CONFORME", "accion_calidad": "ACEPTAR_DISPONIBLE", "medio_lectura": "QR"}
    clave = f"ps08-{uuid.uuid4().hex[:8]}"
    r1 = LOG.http("recepción", c.pedir("POST", c.url("inventory", "/api/v1/inventory/receive-scan"), token=T("warehouse"), headers={"Idempotency-Key": clave}, json=cuerpo), 500)
    r2 = LOG.http("reintento misma clave", c.pedir("POST", c.url("inventory", "/api/v1/inventory/receive-scan"), token=T("warehouse"), headers={"Idempotency-Key": clave}, json=cuerpo), 300)
    r3 = LOG.http("doble escaneo sin clave", c.pedir("POST", c.url("inventory", "/api/v1/inventory/receive-scan"), token=T("warehouse"), json=cuerpo), 300)
    fefo = LOG.http("cola FEFO", c.pedir("GET", c.url("inventory", f"/api/v1/inventory/fefo-queue/9/{TIENDA}"), token=T("warehouse")), 900)
    if r1.status != 201:
        return False, f"recepción {r1.status}"
    CTX["lote_recibido"] = r1["json"]["id_lote"]
    en_fefo = any(l["id_lote"] == r1["json"]["id_lote"] for l in fefo["json"]["lotes_fefo"])
    ok = r2.status in (200, 201) and r2["json"].get("id_lote") == r1["json"]["id_lote"] and r2["json"].get("idempotente") is True \
        and r3.status == 409 and en_fefo
    return ok, (f"recepción {r1.status} lote {r1['json']['id_lote'][:8]}…; misma clave {r2.status} idempotente={r2['json'].get('idempotente')}; "
                f"sin clave {r3.status} {r3['json'].get('error')}; en FEFO={en_fefo} ({fefo['json']['total_lotes']} lotes)")


@caso("PS-09", "Venta POS (Saga de checkout) con asignación FEFO", "Existencias SKU 9 en tienda 3",
      "GET cola FEFO; POST /commercial/checkout (2 pzas SKU 9); GET cola FEFO",
      "201 saga COMPLETADA; se descuenta el lote que caduca primero")
def _():
    antes = c.pedir("GET", c.url("inventory", f"/api/v1/inventory/fefo-queue/9/{TIENDA}"), token=T("store_manager"))["json"]["lotes_fefo"]
    primero = antes[0]
    LOG(f"  - primer lote FEFO antes: {primero['codigo_lote_prov']} cad {primero['fecha_caducidad']} disp {primero['cantidad_disponible']}")
    r = LOG.http("checkout", c.pedir("POST", c.url("commercial", "/api/v1/commercial/checkout"), token=T("store_manager"),
                                     json={"id_locacion": TIENDA, "canal": "TIENDA", "lineas": [{"id_sku": 9, "cantidad": 2}]}), 700)
    despues = {l["id_lote"]: l for l in c.pedir("GET", c.url("inventory", f"/api/v1/inventory/fefo-queue/9/{TIENDA}"), token=T("store_manager"))["json"]["lotes_fefo"]}
    nuevo = despues.get(primero["id_lote"], {"cantidad_disponible": 0})["cantidad_disponible"]
    LOG(f"  - mismo lote después: disp {nuevo}")
    ok = r.status == 201 and r["json"].get("estado") == "COMPLETADA" and round(primero["cantidad_disponible"] - nuevo, 2) == 2
    return ok, f"checkout {r.status} {r['json'].get('estado')} folio {r['json'].get('folio')}; lote FEFO {primero['codigo_lote_prov']} {primero['cantidad_disponible']} → {nuevo}"


@caso("PS-10", "Merma con foto de evidencia", "gerente tienda 3; lote recibido en PS-08",
      "POST /commercial/evidence (JPEG); POST /commercial/shrinkage con id_evidencia; GET /evidence/{id}/url; GET a la URL firmada",
      "201 evidencia; 201 merma ligada; URL firmada que descarga la imagen (200) sin JWT")
def _():
    files = {"archivo": ("merma.jpg", io.BytesIO(jpeg(40_000)), "image/jpeg")}
    ev = LOG.http("evidencia", c.pedir("POST", c.url("commercial", "/api/v1/commercial/evidence"), token=T("store_manager"), files=files,
                                       data={"tipo": "MERMA", "descripcion": "Prueba sistema PS-10", "id_locacion": str(TIENDA)}), 500)
    if ev.status != 201:
        return False, f"evidencia {ev.status}"
    id_ev = ev["json"]["id_evidencia"]
    m = LOG.http("merma", c.pedir("POST", c.url("commercial", "/api/v1/commercial/shrinkage"), token=T("store_manager"), json={
        "id_lote": CTX["lote_recibido"], "id_locacion": TIENDA, "cantidad": 1, "causa": "DANO", "observacion": "Empaque roto (PS-10)", "id_evidencia": id_ev}), 500)
    u = LOG.http("URL firmada", c.pedir("GET", c.url("commercial", f"/api/v1/commercial/evidence/{id_ev}/url"), token=T("store_manager")), 300)
    url_f = (u.get("json") or {}).get("url") or (u.get("json") or {}).get("url_firmada")
    CTX["url_firmada"] = url_f
    # La URL se firma con el host interno (minio:9000). Para validar la FIRMA desde el host se manda
    # la petición a localhost:9000 conservando la cabecera Host firmada; PS-10b prueba la URL tal cual.
    from urllib.parse import urlparse
    pu = urlparse(url_f or "")
    img = LOG.http("descarga con URL firmada (Host firmado, vía localhost:9000)",
                   c.pedir("GET", f"http://localhost:{pu.port or 80}{pu.path}?{pu.query}", headers={"Host": pu.netloc}), 120) if url_f else None
    sin_firma = LOG.http("misma ruta sin firma", c.pedir("GET", f"http://localhost:{pu.port or 80}{pu.path}", headers={"Host": pu.netloc}), 200) if url_f else None
    ok = (m.status == 201 and m["json"].get("id_evidencia") == id_ev and u.status == 200 and img is not None and img.status == 200
          and "image" in img["content_type"] and sin_firma.status == 403)
    return ok, (f"evidencia 201 ({ev['json'].get('tamano_bytes')} B); merma {m.status} ligada={m['json'].get('id_evidencia') == id_ev}; URL {u.status}; "
                f"descarga firmada {img.status if img else 'sin url'} {img['content_type'] if img else ''}; sin firma {sin_firma.status if sin_firma else '-'}")


@caso("PS-10b", "URL firmada de evidencia usable por un cliente externo (app/escritorio)", "URL de PS-10; stack local sin OBJECT_STORAGE_PUBLIC_ENDPOINT",
      "GET a la URL firmada exactamente como la devuelve la API, desde el host (fuera de la red Docker)",
      "200 con la imagen (el host de la URL debe ser alcanzable por el cliente)")
def _():
    url_f = CTX.get("url_firmada")
    if not url_f:
        return False, "no hay URL de PS-10"
    r = LOG.http("URL tal cual", c.pedir("GET", url_f, timeout=10), 200)
    return r.status == 200, f"host de la URL = {url_f.split('/')[2]}; resultado {r.status or 'sin respuesta'} {r.get('error', '')[:60]}"


@caso("PS-11", "Conteo cíclico con reintento idempotente", "Lote de PS-08 en tienda 3",
      "POST /inventory/counts con Idempotency-Key (contado = disponible − 1); repetir igual; consultar existencia",
      "201 con ajuste −1; el reintento devuelve el mismo id_conteo y no ajusta otra vez")
def _():
    fefo = c.pedir("GET", c.url("inventory", f"/api/v1/inventory/fefo-queue/9/{TIENDA}"), token=T("warehouse"))["json"]["lotes_fefo"]
    lote = next(l for l in fefo if l["id_lote"] == CTX["lote_recibido"])
    contado = round(lote["cantidad_disponible"] - 1, 2)
    clave = f"ps11-{uuid.uuid4().hex[:8]}"
    cuerpo = {"id_locacion": TIENDA, "id_sku": 9, "lineas": [{"id_lote": lote["id_lote"], "cantidad_contada": contado}], "observacion": "PS-11"}
    r1 = LOG.http("conteo", c.pedir("POST", c.url("inventory", "/api/v1/inventory/counts"), token=T("warehouse"), headers={"Idempotency-Key": clave}, json=cuerpo), 500)
    r2 = LOG.http("reintento", c.pedir("POST", c.url("inventory", "/api/v1/inventory/counts"), token=T("warehouse"), headers={"Idempotency-Key": clave}, json=cuerpo), 500)
    fefo2 = c.pedir("GET", c.url("inventory", f"/api/v1/inventory/fefo-queue/9/{TIENDA}"), token=T("warehouse"))["json"]["lotes_fefo"]
    final = next(l for l in fefo2 if l["id_lote"] == lote["id_lote"])["cantidad_disponible"]
    LOG(f"  - disponible: {lote['cantidad_disponible']} → contado {contado} → final {final}")
    ok = r1.status == 201 and r2.status in (200, 201) and r1["json"].get("id_conteo") == r2["json"].get("id_conteo") and final == contado
    return ok, f"conteo {r1.status}, reintento {r2.status} mismo id={r1['json'].get('id_conteo') == r2['json'].get('id_conteo')}; existencia {lote['cantidad_disponible']} → {final} (un solo ajuste)"


def _medicion():
    return c.pedir("GET", c.url("alerts", "/api/v1/alerts/waste-measurement"), token=T("admin"))["json"]["producto_recuperado"]


@caso("PS-12", "Transferencia solicitada → aprobada → ejecutada → desperdicio evitado", "Lote recibido en tienda 3 sin stock previo en tienda 4 con caducidad menor",
      "gerente POST /planning/transfers (3→4, 5 pzas); planner approve; warehouse execute; admin vende 2 pzas en tienda 4; GET /alerts/waste-measurement",
      "201 SUGERIDA → APROBADA → EJECUTADA; inventario movido; producto_recuperado sube con lo vendido del lote trasladado")
def _():
    # Lote de la tienda 3 cuya caducidad sea la más próxima del SKU en la tienda 4 (así FEFO lo vende primero allá).
    stock3 = c.pedir("GET", c.url("inventory", f"/api/v1/inventory/stock?id_locacion={TIENDA}&por_pagina=100"), token=T("admin"))["json"]["existencias"]
    stock4 = c.pedir("GET", c.url("inventory", f"/api/v1/inventory/stock?id_locacion={DESTINO}&por_pagina=100"), token=T("admin"))["json"]["existencias"]
    min4: dict[int, str] = {}
    for e in stock4:
        if e["disponible_neto"] > 0 and e["dias_restantes"] >= 0:
            min4[e["id_sku"]] = min(min4.get(e["id_sku"], "9999"), e["fecha_caducidad"])
    cand = [e for e in stock3 if e["estado_lote"] == "DISPONIBLE" and e["dias_restantes"] >= 2 and e["disponible_neto"] >= 6
            and e["fecha_caducidad"] <= min4.get(e["id_sku"], "9999")]
    if not cand:
        return False, "No hay lote candidato para la transferencia"
    lote = sorted(cand, key=lambda e: e["fecha_caducidad"])[0]
    LOG(f"  - lote elegido: {lote['producto']} {lote['codigo_lote_prov']} cad {lote['fecha_caducidad']} disp {lote['disponible_neto']}")
    antes = _medicion()
    t = LOG.http("solicitud", c.pedir("POST", c.url("planning", "/api/v1/planning/transfers"), token=T("store_manager"), json={
        "id_lote": lote["id_lote"], "id_locacion_origen": TIENDA, "id_locacion_destino": DESTINO, "cantidad": 5, "motivo": "PS-12 exceso que vence pronto"}), 500)
    if t.status != 201:
        return False, f"solicitud {t.status}"
    idt = t["json"].get("id_transferencia")
    a = LOG.http("aprobar", c.pedir("POST", c.url("planning", f"/api/v1/planning/transfers/{idt}/approve"), token=T("planner"), json={}), 400)
    e = LOG.http("ejecutar", c.pedir("POST", c.url("planning", f"/api/v1/planning/transfers/{idt}/execute"), token=T("warehouse"), json={}), 500)
    fefo4 = c.pedir("GET", c.url("inventory", f"/api/v1/inventory/fefo-queue/{lote['id_sku']}/{DESTINO}"), token=T("admin"))["json"]["lotes_fefo"]
    LOG(f"  - cola FEFO tienda {DESTINO}: " + ", ".join(f"{l['codigo_lote_prov']}({l['cantidad_disponible']}, {l['fecha_caducidad']})" for l in fefo4[:4]))
    previo = 0.0
    for l in fefo4:
        if l["id_lote"] == lote["id_lote"]:
            break
        previo += l["cantidad_disponible"]
    cant = round(previo + 2, 2)
    LOG(f"  - unidades por delante en FEFO destino: {previo}; se venden {cant}")
    v = LOG.http("venta en destino", c.pedir("POST", c.url("commercial", "/api/v1/commercial/checkout"), token=T("admin"),
                                             json={"id_locacion": DESTINO, "canal": "TIENDA", "lineas": [{"id_sku": lote["id_sku"], "cantidad": cant}]}), 500)
    despues = _medicion()
    t_esp = c.esperar(lambda: _medicion()["unidades"] >= antes["unidades"] + 2 - 0.001, limite=150, paso=10)
    despues = _medicion()
    LOG(f"  - tiempo hasta reflejarse (caché 60 s anidada): {t_esp} s")
    LOG(f"  - producto_recuperado: {antes['unidades']} u / ${antes['valor']} → {despues['unidades']} u / ${despues['valor']}")
    estados = [t["json"].get("estado"), a.get("json", {}).get("estado"), "EJECUTADA" if e.status == 200 else e.status]
    ok = a.status == 200 and e.status == 200 and v.status == 201 and despues["unidades"] >= antes["unidades"] + 2 - 0.001
    return ok, f"estados {estados} ({t.status}/{a.status}/{e.status}); inventario origen→destino {e.get('json', {}).get('existencia_origen')}/{e.get('json', {}).get('existencia_destino')}; venta destino {v.status}; recuperado {antes['unidades']} → {despues['unidades']} u (se reflejó en {t_esp} s)"


@caso("PS-13", "Descuento preventivo: sugerir → aprobar", "Lotes próximos a caducar",
      "planner POST /planning/discounts/generate {dias_hasta: 5}; GET /discounts?estado=SUGERIDO; POST .../approve",
      "201/200 con sugerencias; aprobación 200 estado APROBADO")
def _():
    g = LOG.http("generar", c.pedir("POST", c.url("planning", "/api/v1/planning/discounts/generate"), token=T("planner"), json={"dias_hasta": 5}), 500)
    lst = LOG.http("listar sugeridos", c.pedir("GET", c.url("planning", "/api/v1/planning/discounts"), token=T("planner"), params={"estado": "SUGERIDO"}), 500)
    items = (lst.get("json") or {}).get("descuentos") or (lst.get("json") or {}).get("items") or []
    if not items:
        return g.status in (200, 201) and False, f"generar {g.status}; sin sugerencias para aprobar"
    idd = items[0].get("id_descuento")
    ap = LOG.http("aprobar", c.pedir("POST", c.url("planning", f"/api/v1/planning/discounts/{idd}/approve"), token=T("planner"), json={}), 400)
    ok = g.status in (200, 201) and ap.status == 200
    return ok, f"generar {g.status}; {len(items)} sugeridos; aprobar {ap.status} estado {ap.get('json', {}).get('estado')}"


@caso("PS-14", "Pronóstico + recomendación de reabastecimiento", "Historial de ventas de la tienda 3",
      "planner POST /planning/forecast/run (AUTO, 7 días, tienda 3); GET /forecast/latest/9/3; POST /replenishment/generate; GET /replenishment/orders",
      "201 corrida con serie en MongoDB; 200 serie; 201 recomendaciones (PENDIENTE)")
def _():
    f = LOG.http("pronóstico", c.pedir("POST", c.url("planning", "/api/v1/planning/forecast/run"), token=T("planner"),
                                        json={"metodo": "AUTO", "horizonte": 7, "id_locacion": TIENDA}, timeout=180), 500)
    s = LOG.http("serie", c.pedir("GET", c.url("planning", f"/api/v1/planning/forecast/latest/9/{TIENDA}"), token=T("planner")), 400)
    rg = LOG.http("reabastecimiento", c.pedir("POST", c.url("planning", "/api/v1/planning/replenishment/generate"), token=T("planner"),
                                               json={"horizonte": 7}, timeout=180), 500)
    o = LOG.http("órdenes", c.pedir("GET", c.url("planning", "/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=3"), token=T("buyer")), 400)
    ok = f.status == 201 and s.status == 200 and rg.status == 201 and o.status == 200
    return ok, f"pronóstico {f.status} ({f['ms']} ms); serie {s.status}; reabastecimiento {rg.status} total={rg.get('json', {}).get('total')}; órdenes {o.status}"


@caso("PS-15", "Escaneo de alertas pre-merma", "Lotes por vencer en tienda 3",
      "gerente POST /alerts/scan?id_locacion=3&dias=5; GET /alerts/active",
      "200/201 con alertas emitidas o ya existentes; listado 200 desde MongoDB")
def _():
    s = LOG.http("scan", c.pedir("POST", c.url("alerts", "/api/v1/alerts/scan"), token=T("store_manager"), params={"id_locacion": TIENDA, "dias": 5}), 500)
    a = LOG.http("activas", c.pedir("GET", c.url("alerts", "/api/v1/alerts/active"), token=T("store_manager"), params={"id_locacion": TIENDA}), 400)
    ok = s.status in (200, 201) and a.status == 200
    return ok, f"scan {s.status}; activas {a.status}"


def _xml_import(folios: list[str]) -> str:
    t = "".join(f"<ticket><folio_externo>{f}</folio_externo><canal>TIENDA</canal><lineas><linea><id_sku>9</id_sku><cantidad>1</cantidad></linea></lineas></ticket>"
                for f in folios)
    return f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><sales_import_request><id_locacion>{TIENDA}</id_locacion><tickets>{t}</tickets></sales_import_request>"


@caso("PS-16", "Importación de ventas (XML, JSON y CSV de escritorio) idempotente", "buyer; SKU 9 con existencia en tienda 3",
      "POST /commercial/sales/import en XML con 2 folios; repetir; JSON con 1 folio; CSV → XML con el parser de la app de escritorio",
      "1.ª vez importados=2; repetición duplicados=2 importados=0; JSON 1 importado; CSV importado")
def _():
    base = f"PS16-{uuid.uuid4().hex[:6]}"
    xml = _xml_import([f"{base}-1", f"{base}-2"])
    h = {"Content-Type": "application/xml", "Accept": "application/json"}
    r1 = LOG.http("XML 1.ª vez", c.pedir("POST", c.url("commercial", "/api/v1/commercial/sales/import"), token=T("buyer"), data=xml.encode(), headers=h), 500)
    r2 = LOG.http("XML repetido", c.pedir("POST", c.url("commercial", "/api/v1/commercial/sales/import"), token=T("buyer"), data=xml.encode(), headers=h), 500)
    rj = LOG.http("JSON", c.pedir("POST", c.url("commercial", "/api/v1/commercial/sales/import"), token=T("buyer"),
                                  json={"id_locacion": TIENDA, "tickets": [{"folio_externo": f"{base}-J", "canal": "TIENDA", "lineas": [{"id_sku": 9, "cantidad": 1}]}]}), 400)
    csv_txt = f"folio_externo,id_locacion,id_sku,cantidad,canal\n{base}-C,{TIENDA},9,1,TIENDA\n{base}-MALO,{TIENDA},abc,-1,TIENDA\n"
    rc_txt = "parser de escritorio no disponible"
    try:
        sys.path.insert(0, str(c.RAIZ / "desktop"))
        from freshtrack_desktop.ui.pages.importar_ventas import construir_xml, parsear_csv
        ruta = c.DIR_SISTEMA / "ventas_ps16.csv"
        ruta.write_text(csv_txt, encoding="utf-8")
        filas, tickets = parsear_csv(ruta)
        LOG("  - vista previa CSV: " + "; ".join(f"fila {f['fila']} {f['estado']} {f['mensaje']}" for f in filas))
        rc = LOG.http("CSV→XML", c.pedir("POST", c.url("commercial", "/api/v1/commercial/sales/import"), token=T("buyer"),
                                         data=construir_xml(TIENDA, tickets), headers=h), 400)
        csv_ok = rc.status == 200 and rc["json"]["importados"] == 1 and sum(f["estado"] == "ERROR" for f in filas) == 1
        rc_txt = f"CSV: 1 fila válida importada, 1 fila rechazada en la vista previa ({rc.status})"
    except Exception as exc:  # noqa: BLE001
        csv_ok = False
        rc_txt = f"CSV: {type(exc).__name__}: {exc}"
    ok = (r1.status == 200 and r1["json"]["importados"] == 2 and r2.status == 200 and r2["json"]["duplicados"] == 2
          and r2["json"]["importados"] == 0 and rj.status == 200 and rj["json"]["importados"] == 1 and csv_ok)
    return ok, (f"XML {r1.status} importados={r1['json'].get('importados')}; repetido duplicados={r2['json'].get('duplicados')} importados={r2['json'].get('importados')}; "
                f"JSON importados={rj['json'].get('importados')}; {rc_txt}")


@caso("PS-17", "Negociación de contenido XML y rechazo por XSD", "Tokens válidos",
      "GET /inventory/stock con Accept: application/xml; POST /commercial/sales/import con XML que viola el XSD; POST /checkout XML inválido en XML",
      "200 application/xml; 400 xml_no_cumple_contrato con motivos; error también en XML")
def _():
    x = LOG.http("stock XML", c.pedir("GET", c.url("inventory", "/api/v1/inventory/stock?por_pagina=1"), token=T("warehouse"), headers={"Accept": "application/xml"}), 300)
    bad = "<sales_import_request><id_locacion>tres</id_locacion><tickets/></sales_import_request>"
    b = LOG.http("XML inválido", c.pedir("POST", c.url("commercial", "/api/v1/commercial/sales/import"), token=T("buyer"), data=bad.encode(),
                                         headers={"Content-Type": "application/xml"}), 600)
    bx = LOG.http("XML inválido (respuesta XML)", c.pedir("POST", c.url("commercial", "/api/v1/commercial/checkout"), token=T("store_manager"),
                                                      data=b"<checkout_request><canal>OTRO</canal><lineas/></checkout_request>",
                                                      headers={"Content-Type": "application/xml", "Accept": "application/xml"}), 600)
    ok = (x.status == 200 and "xml" in x["content_type"] and str(x["texto"]).startswith("<?xml") and b.status == 400
          and b["json"].get("error") == "xml_no_cumple_contrato" and bx.status == 400 and "xml" in bx["content_type"])
    return ok, f"stock {x.status} {x['content_type']}; XSD inválido {b.status} {b['json'].get('error')}; checkout XML {bx.status} {bx['content_type']}"


@caso("PS-18", "Swagger/OpenAPI de los 8 servicios", "Servicios arriba", "GET /api/v1/docs y /api/v1/openapi.json en 5001..5008",
      "200 en los 16 recursos; OpenAPI 3 con rutas")
def _():
    oks = 0
    for s in c.PUERTOS:
        if s == "web":
            continue
        d = c.pedir("GET", c.url(s, "/api/v1/docs"))
        o = c.pedir("GET", c.url(s, "/api/v1/openapi.json"))
        n = len((o.get("json") or {}).get("paths", {}))
        LOG(f"  - {s}: docs {d.status}, openapi {o.status} ({(o.get('json') or {}).get('openapi')}, {n} rutas)")
        oks += d.status == 200 and o.status == 200 and n > 0
    return oks == 8, f"{oks}/8 servicios con Swagger UI y OpenAPI"


@caso("PS-19", "Panel de monitoreo oculto /ops/status", "Credenciales MONITOR_* del contenedor web",
      "GET /ops/status sin sesión; GET /ops/status/api/snapshot sin y con Basic Auth",
      "302 a /ops/status/login; 401 sin credenciales; 200 OPERATIVO con 8/8 sanos")
def _():
    u, p = c.credenciales_monitor()
    a = LOG.http("panel sin sesión", c.pedir("GET", c.url("web", "/ops/status"), allow_redirects=False), 150)
    b = LOG.http("snapshot sin auth", c.pedir("GET", c.url("web", "/ops/status/api/snapshot?solo_lectura=1")), 200)
    s = c.pedir("GET", c.url("web", "/ops/status/api/snapshot?solo_lectura=1"), auth=(u, p))
    j = s.get("json") or {}
    res = j.get("resumen") or {}
    LOG(f"  - snapshot con auth: HTTP {s.status} estado_global={j.get('estado_global')} resumen={res}")
    ok = a.status == 302 and b.status == 401 and s.status == 200 and j.get("estado_global") == "OPERATIVO" and res.get("sanos") == 8
    return ok, f"sin sesión {a.status}; sin auth {b.status}; con auth {s.status} {j.get('estado_global')} sanos={res.get('sanos')}/8 disponibilidad {res.get('disponibilidad_actual_pct')}%"


@caso("PS-20", "Pantallas de la web por rol (navegador real por HTTP)", "Cuentas demo",
      "Login por formulario con CSRF para 7 roles y GET a su pantalla inicial", "302 al destino del rol y 200 en esa pantalla")
def _():
    oks = 0
    for rol in c.cuentas():
        s, r = c.sesion_web(rol)
        dest = r.get("headers", {}).get("Location", "")
        g = c.pedir("GET", c.url("web", dest), sesion=s) if dest else None
        LOG(f"  - {rol}: login {r.status} → {dest} → {g.status if g else '-'}")
        oks += r.status == 302 and g is not None and g.status == 200
    return oks == len(c.cuentas()), f"{oks}/{len(c.cuentas())} roles entran y ven su pantalla inicial"


@caso("PS-21", "Todas las pantallas del menú por rol (equivalente a smoke_rutas.py con CSRF)", "Cuentas demo; web en :5000",
      "Para cada rol: login por formulario con CSRF y GET a cada vista de VISTAS_POR_ROL contra la web real",
      "HTTP 200 en todas las pantallas permitidas")
def _():
    import os
    os.chdir(c.RAIZ)
    sys.path.insert(0, str(c.RAIZ))
    from dotenv import load_dotenv
    load_dotenv(c.RAIZ / ".env")
    from app import create_app
    from app.navegacion import VISTAS_POR_ROL, endpoint_de
    app = create_app()
    mapa = app.url_map.bind("localhost")
    total, fallos = 0, []
    for rol in c.cuentas():
        s, r = c.sesion_web(rol)
        for vista in sorted(VISTAS_POR_ROL.get(rol, [])):
            ep = endpoint_de(vista)
            if not ep:
                continue
            ruta = mapa.build(ep)
            g = c.pedir("GET", c.url("web", ruta), sesion=s, allow_redirects=False, timeout=60)
            total += 1
            LOG(f"  - {rol:<13} {ruta:<28} {g.status} {g['ms']} ms")
            if g.status != 200:
                fallos.append(f"{rol} {ruta} {g.status}")
    return not fallos, f"{total - len(fallos)}/{total} pantallas con 200" + (f"; fallos: {fallos}" if fallos else "")


if __name__ == "__main__":
    LOG(f"Pruebas de sistema FreshTrack — inicio {c.ahora()}")
    LOG(c.estado_contenedores())
    for fn in CASOS_FN:
        fn()
    (c.DIR_SISTEMA / "resultados_pruebas_sistema.json").write_text(json.dumps(CASOS, ensure_ascii=False, indent=2), encoding="utf-8")
    pasa = sum(1 for x in CASOS if x["estado"] == "PASA")
    LOG(f"\nResumen: {pasa}/{len(CASOS)} casos PASA — fin {c.ahora()}")
    LOG.cerrar()
