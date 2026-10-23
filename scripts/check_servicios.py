#!/usr/bin/env python3
"""
scripts/check_servicios.py — Barrido de los 8 microservicios por HTTP real.

Complementa a check_planeador.py (mismo estilo y mismos helpers) pero recorre
toda la arquitectura con el usuario administrador:

  1. /health de la web y de los 8 microservicios, con sus dependencias.
  2. Endpoints de consulta de cada servicio, pidiendo JSON y luego XML.
  3. Saga de venta en svc-commercial (JSON y XML) sobre un lote con existencia,
     y rechazo 400 de un XML que no cumple checkout_request.xsd.
  4. Escaneo de alertas pre-merma en svc-alerts.
  5. Trazabilidad: todas las peticiones llevan el mismo X-Correlation-Id y se
     comprueba que aparece en `docker logs` de cada contenedor.

Ojo: el paso 3 registra ventas reales (1 unidad cada una) en la base local.

Uso:
  python scripts/check_servicios.py               # resumen
  python scripts/check_servicios.py -v            # imprime los cuerpos JSON/XML
  python scripts/check_servicios.py --sin-ventas  # omite la saga de venta
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_planeador as cp  # noqa: E402  (helpers compartidos)
from check_planeador import check, es_json_valido, es_xml_valido, mostrar, seccion  # noqa: E402

ADMIN = ("admin@freshtrack.mx", "Admin2026!")

SERVICIOS = {
    "web": 5000, "svc_auth": 5001, "svc_catalog": 5002, "svc_inventory": 5003, "svc_commercial": 5004,
    "svc_asn": 5005, "svc_planning": 5006, "svc_alerts": 5007, "svc_audit": 5008,
}

CONSULTAS = [
    ("svc_auth", "/api/v1/auth/users?por_pagina=2"),
    ("svc_catalog", "/api/v1/catalog/products?por_pagina=2"),
    ("svc_catalog", "/api/v1/catalog/locations"),
    ("svc_catalog", "/api/v1/catalog/suppliers"),
    ("svc_inventory", "/api/v1/inventory/stock?por_pagina=2"),
    ("svc_inventory", "/api/v1/inventory/fefo-queue/1/2"),
    ("svc_commercial", "/api/v1/commercial/sales?por_pagina=2"),
    ("svc_asn", "/api/v1/asn?por_pagina=2"),
    ("svc_asn", "/api/v1/asn/analytics/summary"),
    ("svc_planning", "/api/v1/planning/replenishment/orders?por_pagina=2"),
    ("svc_planning", "/api/v1/planning/forecast/analytics/kpis"),
    ("svc_alerts", "/api/v1/alerts/active?por_pagina=2"),
    ("svc_alerts", "/api/v1/alerts/analytics/kpis"),
    ("svc_alerts", "/api/v1/alerts/esg/carbon-avoided"),
    ("svc_audit", "/api/v1/audit/events?por_pagina=2"),
    ("svc_audit", "/api/v1/audit/stream/recent"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="Host donde están publicados los puertos 5000-5008")
    ap.add_argument("-v", "--verbose", action="store_true", help="Imprime los cuerpos JSON y XML")
    ap.add_argument("--sin-ventas", action="store_true", help="No ejecuta la saga de venta (no escribe en la base)")
    args = ap.parse_args()
    cp.VERBOSO = args.verbose

    cid = f"check-servicios-{int(time.time())}"
    url = {k: f"http://{args.host}:{p}" for k, p in SERVICIOS.items()}

    def http(metodo: str, destino: str, **kw) -> tuple[int, str, str]:
        # Todas las peticiones con el mismo correlation id, para rastrearlas en los logs.
        kw.setdefault("accept", "application/json")
        return cp.http(metodo, destino, cid=cid, **kw)

    seccion("1. Salud de la web y los 8 microservicios")
    for nombre, base in url.items():
        st, _, body = http("GET", f"{base}/health")
        deps = json.loads(body).get("dependencies", {}) if es_json_valido(body) else {}
        check(f"{nombre} /health", st == 200 and deps and all(deps.values()),
              " ".join(f"{k}={'ok' if v else 'CAIDO'}" for k, v in deps.items()) or f"HTTP {st}")
    if not any(ok for _, ok in cp.resultados):
        print(f"\n  {cp.ROJO}Ningún servicio responde. Levanta todo con: docker compose up -d --build{cp.FIN}")
        return 1

    seccion("2. Login del administrador")
    st, _, body = http("POST", f"{url['svc_auth']}/api/v1/auth/login",
                       cuerpo=json.dumps({"email": ADMIN[0], "password": ADMIN[1]}))
    token = json.loads(body).get("token") if es_json_valido(body) else None
    if not check("POST /auth/login (admin)", st == 200 and bool(token), f"HTTP {st}"):
        return 1

    seccion("3. Consultas de cada servicio (JSON vs XML)")
    for servicio, ruta in CONSULTAS:
        sj, cj, bj = http("GET", url[servicio] + ruta, token=token)
        sx, cx, bx = http("GET", url[servicio] + ruta, token=token, accept="application/xml")
        check(f"{servicio:<15} GET {ruta}",
              sj == 200 and "json" in cj and es_json_valido(bj) and sx == 200 and "xml" in cx and es_xml_valido(bx),
              f"json={sj} xml={sx}")
        mostrar(bj, es_xml=False)
        mostrar(bx, es_xml=True)

    seccion("4. Saga de venta en svc-commercial")
    if args.sin_ventas:
        print(f"  {cp.AMARILLO}[--]{cp.FIN} Omitida (--sin-ventas)")
    else:
        # Un lote vigente con existencia; si no hay, la saga respondería 409 por regla de negocio.
        _, _, body = http("GET", f"{url['svc_inventory']}/api/v1/inventory/stock?por_pagina=200", token=token)
        existencias = json.loads(body).get("existencias", []) if es_json_valido(body) else []
        candidato = next((e for e in existencias if e.get("disponible_neto", 0) >= 2 and e.get("dias_restantes", -1) >= 0), None)
        if not check("Hay un lote vigente con existencia", candidato is not None):
            print("      Carga datos con: make etl")
        else:
            loc, sku = candidato["id_locacion"], candidato["id_sku"]
            print(f"  usando {candidato['producto']} (sku {sku}) en {candidato['locacion']} (locación {loc})")
            venta = {"id_locacion": loc, "canal": "TIENDA", "lineas": [{"id_sku": sku, "cantidad": 1}]}
            st, ct, body = http("POST", f"{url['svc_commercial']}/api/v1/commercial/checkout", token=token,
                                cuerpo=json.dumps(venta))
            check("POST /commercial/checkout [JSON] -> saga COMPLETADA", st == 201 and '"COMPLETADA"' in body, f"HTTP {st}")
            mostrar(body, es_xml=False)

            xml_venta = (f"<checkout_request><id_locacion>{loc}</id_locacion><canal>TIENDA</canal><lineas>"
                         f"<item><id_sku>{sku}</id_sku><cantidad>1</cantidad></item></lineas></checkout_request>")
            st, ct, body = http("POST", f"{url['svc_commercial']}/api/v1/commercial/checkout", token=token,
                                cuerpo=xml_venta, content_type="application/xml", accept="application/xml")
            check("POST /commercial/checkout [XML] -> saga COMPLETADA", st == 201 and "COMPLETADA" in body and "xml" in ct,
                  f"HTTP {st}")
            mostrar(body, es_xml=True)

            invalido = xml_venta.replace("<item>", "<linea>").replace("</item>", "</linea>")
            st, ct, body = http("POST", f"{url['svc_commercial']}/api/v1/commercial/checkout", token=token,
                                cuerpo=invalido, content_type="application/xml", accept="application/xml")
            check("XML fuera de contrato (checkout_request.xsd) -> 400", st == 400 and "xml_no_cumple_contrato" in body,
                  f"HTTP {st}")
            mostrar(body, es_xml=True)

    seccion("5. Alertas pre-merma")
    st, _, body = http("POST", f"{url['svc_alerts']}/api/v1/alerts/scan?dias=3", token=token)
    datos = json.loads(body) if es_json_valido(body) else {}
    check("POST /alerts/scan", st == 200, f"escaneados={datos.get('total_escaneados')} emitidas={datos.get('alertas_emitidas')}")

    seccion(f"6. Trazabilidad en docker logs (cid={cid})")
    if shutil.which("docker") and subprocess.run(["docker", "ps"], capture_output=True).returncode == 0:
        time.sleep(1)  # dar tiempo a que el último registro llegue al log del contenedor
        for nombre in SERVICIOS:
            if nombre == "web":
                continue
            r = subprocess.run(["docker", "logs", "--since", "10m", f"freshtrack_{nombre}"], capture_output=True, text=True)
            lineas = [l for l in (r.stdout + r.stderr).splitlines() if f"cid={cid}" in l]
            check(f"freshtrack_{nombre} registró las peticiones", bool(lineas), f"{len(lineas)} líneas")
        print(f"\n  Para verlas tú: docker compose logs | grep 'cid={cid}'")
    else:
        print(f"  {cp.AMARILLO}[--]{cp.FIN} Sin acceso a docker; se omite la revisión de logs")

    fallas = [n for n, ok in cp.resultados if not ok]
    seccion(f"RESUMEN: {len(cp.resultados) - len(fallas)}/{len(cp.resultados)} comprobaciones OK")
    for n in fallas:
        print(f"  {cp.ROJO}- {n}{cp.FIN}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
