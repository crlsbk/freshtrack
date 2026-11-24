"""
Crea en el servidor una Orden de Compra + ASN con etiquetas QR firmadas hacia una tienda, para
probar el flujo «Recibir» de la app móvil. Usa el flujo real de negocio:

  comprador → POST /planning/purchase-orders  (OC por lotes, PDF en bucket)
  comprador → POST /asn/from-purchase-order   (ASN EN_TRANSITO + etiquetas FT1 firmadas con HMAC)

Uso:
    python android-app/tools/crear_asn_prueba.py [--tienda 3] [--productos 3] [--base https://34.51.41.80.nip.io/]
Después vuelve a correr generar_datos_prueba.py para que las etiquetas salgan en la hoja.
"""

from __future__ import annotations

import argparse
import collections
import json
import urllib.request
from datetime import date, timedelta


def api(base, path, tok=None, method="GET", body=None):
    req = urllib.request.Request(base + "api/v1/" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://34.51.41.80.nip.io/")
    ap.add_argument("--tienda", type=int, default=3)
    ap.add_argument("--productos", type=int, default=3)
    a = ap.parse_args()
    base = a.base if a.base.endswith("/") else a.base + "/"

    st, d = api(base, "auth/login", method="POST", body={"email": "buyer@freshtrack.mx", "password": "Compras2026!"})
    assert st == 200, d
    tok = d["token"]

    # Catálogo completo: productos activos perecederos con GTIN, agrupados por proveedor
    prods, pag = [], 1
    while True:
        _, d = api(base, f"catalog/products?por_pagina=100&pagina={pag}")
        prods += d.get("productos", [])
        if pag >= (d.get("paginacion") or {}).get("total_paginas", 1):
            break
        pag += 1
    por_prov = collections.defaultdict(list)
    for p in prods:
        if p.get("activo") and p.get("codigo_gtin") and p.get("id_proveedor") and p.get("perecedero", True):
            por_prov[p["id_proveedor"]].append(p)
    # Proveedor con más productos con GTIN; se priorizan vidas útiles cortas (lo interesante para FEFO)
    prov, lista = max(por_prov.items(), key=lambda kv: len(kv[1]))
    lista = sorted(lista, key=lambda p: (p.get("vida_util_estandar") or 99))[: a.productos]

    st, oc = api(base, "planning/purchase-orders", tok, "POST", {
        "id_proveedor": prov,
        "lineas": [{"id_sku": p["id_sku"], "id_locacion_destino": a.tienda, "cantidad_lotes": 1} for p in lista],
        "observaciones": "OC de prueba para la app móvil (flujo Recibir)",
    })
    print("OC", st, json.dumps({k: oc.get(k) for k in ("folio", "id_oc", "estado", "total", "total_unidades", "error", "mensaje")}, ensure_ascii=False))
    if st != 201:
        raise SystemExit(1)
    lineas = oc.get("lineas") or oc.get("detalle") or []
    if not lineas or "id_detalle" not in lineas[0]:
        _, det = api(base, f"planning/purchase-orders/{oc['id_oc']}", tok)
        lineas = det.get("lineas") or det.get("detalle") or []

    hoy = date.today()
    partidas = []
    for i, l in enumerate(lineas, start=1):
        prod = next(p for p in lista if p["id_sku"] == l["id_sku"])
        vida = int(prod.get("vida_util_estandar") or 7)
        partidas.append({
            "id_detalle_oc": l["id_detalle"],
            "id_sku": l["id_sku"],
            "id_locacion_destino": l.get("id_locacion_destino", a.tienda),
            "cantidad_declarada": float(l.get("cantidad_total") or l.get("cantidad") or l.get("cantidad_unidades") or 10),
            "lote_proveedor": f"LP-APP-{hoy:%y%m%d}-{i:02d}",
            "fecha_produccion": hoy.isoformat(),
            "fecha_caducidad": (hoy + timedelta(days=max(2, vida))).isoformat(),
        })
    st, asn = api(base, "asn/from-purchase-order", tok, "POST", {
        "id_oc": oc["id_oc"],
        "transporte": {"chofer": "Prueba App Móvil", "placas": "NL-TEST-01", "temperatura_salida_c": 3.5},
        "partidas": partidas,
    })
    print("ASN", st, json.dumps({k: asn.get(k) for k in ("folio_asn", "estado", "folio_oc", "error", "mensaje")}, ensure_ascii=False))
    for e in asn.get("etiquetas", []):
        print("  etiqueta", e.get("codigo_etiqueta"), e.get("producto") or e.get("id_sku"), e.get("cantidad_declarada"), e.get("fecha_caducidad"))
    if st != 201:
        print(json.dumps(asn, ensure_ascii=False)[:800])
        raise SystemExit(1)
    # Se guarda el folio para que generar_datos_prueba.py lo encuentre aunque haya miles de ASN.
    from pathlib import Path
    reg = Path(__file__).resolve().parents[1] / "datos_prueba" / "asn_prueba.json"
    reg.parent.mkdir(exist_ok=True)
    folios = json.loads(reg.read_text(encoding="utf-8")) if reg.exists() else []
    folios = [f for f in folios if f != asn["folio_asn"]] + [asn["folio_asn"]]
    reg.write_text(json.dumps(folios[-10:], indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
