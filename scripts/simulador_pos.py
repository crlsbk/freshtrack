#!/usr/bin/env python3
"""
Simulador de tráfico de cajas POS externas para demostración en tiempo real.

Envía ventas reales en formato JSON o XML hacia svc-commercial
(POST /api/v1/commercial/checkout) para demostrar cómo el inventario descuenta
lotes en orden FEFO y el Monitor de Ventas (/ventas) se actualiza en vivo.

Uso:
    .venv/bin/python scripts/simulador_pos.py --cantidad 5 --intervalo 1.5 --formato mixto
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request


def pedir(
    url: str,
    metodo: str = "GET",
    cuerpo: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Emulador externo de ventas POS (JSON/XML)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--email", default="admin@freshtrack.mx")
    ap.add_argument("--password", default="Admin2026!")
    ap.add_argument("--cantidad", type=int, default=5, help="Número de tickets POS a emitir")
    ap.add_argument("--intervalo", type=float, default=1.5, help="Segundos entre tickets")
    ap.add_argument("--formato", choices=("json", "xml", "mixto"), default="mixto")
    ap.add_argument("--locacion", type=int, default=None, help="Filtrar a una tienda específica")
    args = ap.parse_args()

    # 1. Autenticación contra el servicio de identidad
    st, raw = pedir(
        f"http://{args.host}:5001/api/v1/auth/login",
        "POST",
        json.dumps({"email": args.email, "password": args.password}).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    if st != 200:
        print(f"[ERR] No se pudo autenticar ({st}): {raw}")
        return 1
    token = json.loads(raw)["token"]
    auth_h = {"Authorization": f"Bearer {token}"}

    # 2. Consultar existencias vigentes elegibles en tiendas
    st, raw = pedir(f"http://{args.host}:5003/api/v1/inventory/stock?por_pagina=200", headers=auth_h)
    if st != 200:
        print(f"[ERR] No se pudo consultar stock ({st}): {raw}")
        return 1
    existencias = [
        x
        for x in json.loads(raw).get("existencias", [])
        if x.get("estado_lote") == "DISPONIBLE"
        and (x.get("dias_restantes") or -1) >= 0
        and float(x.get("disponible_neto") or 0) >= 1.5
        and "Tienda" in str(x.get("locacion") or "")
        and (args.locacion is None or x.get("id_locacion") == args.locacion)
    ]
    if not existencias:
        print("[ERR] No se encontró inventario elegible en tiendas para simular ventas.")
        return 1

    print(f"Emitiendo {args.cantidad} ventas POS (formato={args.formato}) hacia http://{args.host}:5004 ...")
    ok_count = 0
    for i in range(1, args.cantidad + 1):
        elegido = random.choice(existencias)
        id_loc = elegido["id_locacion"]
        id_sku = elegido["id_sku"]
        qty = round(random.uniform(1.0, min(3.0, float(elegido["disponible_neto"]))), 2)

        fmt = ("xml" if i % 2 == 0 else "json") if args.formato == "mixto" else args.formato
        if fmt == "xml":
            body = (
                f"<checkout_request>"
                f"<id_locacion>{id_loc}</id_locacion>"
                f"<canal>TIENDA</canal>"
                f"<lineas><item><id_sku>{id_sku}</id_sku><cantidad>{qty}</cantidad></item></lineas>"
                f"</checkout_request>"
            ).encode("utf-8")
            ct = "application/xml"
        else:
            body = json.dumps(
                {
                    "id_locacion": id_loc,
                    "canal": "TIENDA",
                    "lineas": [{"id_sku": id_sku, "cantidad": qty}],
                }
            ).encode("utf-8")
            ct = "application/json"

        st_v, raw_v = pedir(
            f"http://{args.host}:5004/api/v1/commercial/checkout",
            "POST",
            body,
            {**auth_h, "Content-Type": ct, "Accept": "application/json"},
        )
        if st_v in (200, 201):
            ok_count += 1
            resp = json.loads(raw_v)
            lotes = ", ".join(
                f"{l.get('codigo_lote') or l.get('codigo_lote_prov')} ({l.get('cantidad')} u.)"
                for l in resp.get("lineas", [])
            )
            print(
                f"  [{i}/{args.cantidad}] [{fmt.upper()}] Folio={resp.get('folio')} | "
                f"{elegido['locacion']} | {elegido['producto']} x {qty} -> ${resp.get('total'):,.2f} | FEFO: {lotes}"
            )
        else:
            print(f"  [{i}/{args.cantidad}] [{fmt.upper()}] RECHAZADO ({st_v}): {raw_v[:160]}")

        if i < args.cantidad and args.intervalo > 0:
            time.sleep(args.intervalo)

    print(f"\nCompletado: {ok_count}/{args.cantidad} ventas transmitidas.")
    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
