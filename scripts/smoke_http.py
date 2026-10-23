#!/usr/bin/env python3
"""
Prueba de humo por HTTP contra la arquitectura desplegada (docker compose o nube).

Comprueba que los 9 contenedores de aplicación responden /health y ejecuta el flujo
distribuido de seguridad entre servicios reales:

    login (XML) en svc-auth → consulta en svc-inventory (XML) → 403 por rol en svc-audit
    → logout en svc-auth → el mismo token es rechazado (401) en svc-inventory

Uso:
    python scripts/smoke_http.py                       # contra localhost
    python scripts/smoke_http.py --host 203.0.113.10   # contra el servidor desplegado
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

PUERTOS = {"web": 5000, "svc-auth": 5001, "svc-catalog": 5002, "svc-inventory": 5003, "svc-commercial": 5004,
           "svc-asn": 5005, "svc-planning": 5006, "svc-alerts": 5007, "svc-audit": 5008}


def pedir(url: str, metodo: str = "GET", cuerpo: str | None = None, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=cuerpo.encode() if cuerpo else None, method=metodo, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:  # conexión rechazada, timeout...
        return 0, str(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--esperar", type=int, default=120, help="Segundos máximos esperando a que todo esté sano")
    args = ap.parse_args()
    base = lambda nombre: f"http://{args.host}:{PUERTOS[nombre]}"  # noqa: E731

    fallos = 0
    limite = time.time() + args.esperar
    for nombre in PUERTOS:
        while True:
            status, cuerpo = pedir(base(nombre) + "/health")
            if status == 200 or time.time() > limite:
                break
            time.sleep(3)
        print(f"[{'OK ' if status == 200 else 'ERR'}] {nombre:15s} /health -> {status} {cuerpo[:120]}")
        fallos += status != 200

    def paso(desc: str, ok: bool, detalle: str = "") -> None:
        nonlocal fallos
        print(f"[{'OK ' if ok else 'ERR'}] {desc} {detalle[:160]}")
        fallos += not ok

    xml = "<login_request><email>gerente@freshtrack.mx</email><password>Tienda2026!</password></login_request>"
    st, cuerpo = pedir(base("svc-auth") + "/api/v1/auth/login", "POST", xml, {"Content-Type": "application/xml"})
    paso("login XML en svc-auth", st == 200, str(st))
    if st != 200:
        return 1
    token = json.loads(cuerpo)["token"]
    auth = {"Authorization": f"Bearer {token}"}

    st, cuerpo = pedir(base("svc-inventory") + "/api/v1/inventory/stock?por_pagina=1", headers={**auth, "Accept": "application/xml"})
    paso("svc-inventory responde XML con el token de svc-auth", st == 200 and cuerpo.startswith("<?xml"), str(st))
    st, _ = pedir(base("svc-audit") + "/api/v1/audit/events", headers=auth)
    paso("svc-audit niega acceso al gerente (403)", st == 403, str(st))
    st, _ = pedir(base("svc-auth") + "/api/v1/auth/logout", "POST", headers=auth)
    paso("logout en svc-auth", st == 200, str(st))
    st, cuerpo = pedir(base("svc-inventory") + "/api/v1/inventory/stock", headers=auth)
    paso("token revocado rechazado en svc-inventory (401)", st == 401 and "token_revocado" in cuerpo, str(st))

    # --- La web como frontend: login por formulario (svc-auth) y gateway /svc/... ---
    import http.cookiejar
    import urllib.parse

    jar = http.cookiejar.CookieJar()
    navegador = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    datos = urllib.parse.urlencode({"email": "admin@freshtrack.mx", "password": "Admin2026!"}).encode()
    try:
        r = navegador.open(base("web") + "/login", data=datos, timeout=15)
        paso("login en la web (delegado a svc-auth)", r.status == 200 and "/login" not in r.geturl(), r.geturl())
        r = navegador.open(urllib.request.Request(base("web") + "/svc/inventory/api/v1/inventory/stock?por_pagina=1",
                                                  headers={"Accept": "application/xml"}), timeout=15)
        cuerpo = r.read().decode()
        paso("gateway web /svc/inventory → svc-inventory (XML)",
             r.status == 200 and r.headers.get("X-Servicio") == "svc-inventory" and cuerpo.startswith("<?xml"), str(r.status))
    except Exception as e:  # noqa: BLE001
        paso("flujo web → microservicios", False, str(e))

    print(f"\n{'TODO CORRECTO' if not fallos else f'{fallos} FALLO(S)'}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
