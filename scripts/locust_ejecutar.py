#!/usr/bin/env python3
"""
Ejecuta una prueba de carga de FreshTrack con Locust y guarda TODO lo que la
prueba requiere y produce en docs/pruebas/locust/<run_id>/.

    export LOCUST_PASSWORD_POOL='...'     # contraseña de las cuentas op_*@freshtrack.mx
    export LOCUST_ADMIN_PASSWORD='...'    # cuenta admin (solo para el descubrimiento)
    .venv/bin/python scripts/locust_ejecutar.py --host https://34.x.x.x.nip.io --escenario rendimiento
    .venv/bin/python scripts/locust_ejecutar.py --host https://34.x.x.x.nip.io --escenario ventas

Pasos:
  1. Pre-vuelo: salud de la web y los 8 servicios, pool de cuentas por rol
     (se verifica la contraseña con un login por rol), tiendas, existencias por
     tienda, ASN y etiquetas, órdenes de compra, intervenciones vigentes y el
     desperdicio evitado ANTES de la corrida.
  2. Locust headless con la curva del escenario (tests/load/locustfile.py).
  3. Recalcula el desperdicio evitado y lo mide DESPUÉS.
  4. Analiza (saturación, recuperación, endpoints más lentos) y escribe
     resumen.json + REPORTE.md.
Después, para guardarlo en PostgreSQL:  scripts/locust_importar.py <carpeta>
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import urllib3

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from tests.load import analisis  # noqa: E402

ROLES_POOL = ("store_manager", "warehouse", "buyer", "planner", "auditor")
SERVICIOS = ("auth", "catalog", "inventory", "commercial", "asn", "planning", "alerts", "audit")
UA = "FreshTrack-Locust-Prevuelo"


class Cliente:
    def __init__(self, host: str, servicios: dict[str, str], verificar_tls: bool) -> None:
        self.host = host.rstrip("/")
        self.servicios = servicios
        self.s = requests.Session()
        self.s.verify = verificar_tls
        self.s.headers["User-Agent"] = UA
        self.token = ""

    def url(self, servicio: str | None, ruta: str) -> str:
        base = self.servicios.get(servicio) if servicio else None
        return f"{(base or self.host).rstrip('/')}{ruta}"

    def pedir(self, metodo: str, servicio: str | None, ruta: str, **kw) -> requests.Response:
        h = kw.pop("headers", {}) or {}
        if self.token:
            h.setdefault("Authorization", f"Bearer {self.token}")
        h.setdefault("Accept", "application/json")
        return self.s.request(metodo, self.url(servicio, ruta), headers=h, timeout=kw.pop("timeout", 60), **kw)

    def login(self, email: str, password: str) -> dict | None:
        r = self.s.post(self.url("auth", "/api/v1/auth/login"), json={"email": email, "password": password},
                        headers={"Accept": "application/json"}, timeout=30)
        return r.json() if r.status_code == 200 else None


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, text=True).strip()
    except Exception:  # noqa: BLE001
        return "sin-git"


def _servicios(texto: str | None) -> dict[str, str]:
    if not texto:
        return {}
    return dict(par.split("=", 1) for par in texto.split(",") if "=" in par)


# --- 1. Pre-vuelo -------------------------------------------------------------------
def prevuelo(c: Cliente, args) -> dict:
    print("[1/4] Pre-vuelo contra", c.host)
    salud = {"web": c.pedir("GET", None, "/health").status_code}
    for svc in SERVICIOS:
        try:
            salud[svc] = c.pedir("GET", svc, f"/api/v1/{svc}/health").status_code
        except requests.RequestException as exc:
            salud[svc] = f"error: {exc.__class__.__name__}"
    caidos = {k: v for k, v in salud.items() if v not in (200, 503)}
    if caidos:
        raise SystemExit(f"Servicios sin responder: {caidos}")

    admin = c.login(args.admin_email, args.admin_password)
    if not admin:
        raise SystemExit("No se pudo iniciar sesión con la cuenta admin (LOCUST_ADMIN_PASSWORD).")
    c.token = admin["token"]

    patron = re.compile(args.patron_pool)
    pool: dict[str, list[dict]] = {}
    for rol in ROLES_POOL:
        cuentas, pagina = [], 1
        while len(cuentas) < args.max_cuentas_rol:
            r = c.pedir("GET", "auth", f"/api/v1/auth/users?rol={rol}&activo=true&por_pagina=100&pagina={pagina}")
            filas = r.json().get("usuarios", []) if r.ok else []
            cuentas += [{"email": u["email"], "id_locacion": u.get("id_locacion")}
                        for u in filas if patron.search(u["email"])]
            if len(filas) < 100:
                break
            pagina += 1
        pool[rol] = cuentas[: args.max_cuentas_rol]
    verificacion = {}
    for rol, cuentas in pool.items():
        ok = bool(cuentas) and c.login(cuentas[0]["email"], args.password_pool) is not None
        verificacion[rol] = {"cuentas": len(cuentas), "login_ok": ok}
    faltan = [r for r, v in verificacion.items() if not v["login_ok"]]
    if faltan:
        raise SystemExit(
            f"El pool no sirve para los roles {faltan}: sin cuentas que coincidan con {args.patron_pool!r} "
            "o LOCUST_PASSWORD_POOL incorrecta. (El generador masivo crea op_*@freshtrack.mx con el hash "
            "de una cuenta semilla; usa esa contraseña.)"
        )

    locs = c.pedir("GET", "catalog", "/api/v1/catalog/locations?tipo=TIENDA").json().get("locaciones", [])
    tiendas = [int(l["id_locacion"]) for l in locs if str(l.get("activo", True)).lower() != "false"]
    stock: dict[str, list[dict]] = {}
    for loc in tiendas:
        r = c.pedir("GET", "inventory", f"/api/v1/inventory/stock?id_locacion={loc}&por_pagina=100")
        filas = r.json().get("existencias", []) if r.ok else []
        elegibles, vistos = [], set()
        for f in filas:
            if (f.get("estado_lote") == "DISPONIBLE" and (f.get("dias_restantes") or -1) >= 0
                    and float(f.get("disponible_neto") or 0) >= 2 and f["id_sku"] not in vistos):
                vistos.add(f["id_sku"])
                elegibles.append({"id_sku": f["id_sku"], "id_lote": f["id_lote"], "id_locacion": loc,
                                  "disponible": float(f["disponible_neto"])})
        stock[str(loc)] = elegibles[:60]

    asn, etiquetas = [], []
    r = c.pedir("GET", "asn", "/api/v1/asn?por_pagina=50")
    for d in (r.json().get("avisos_asn", []) if r.ok else []):
        asn.append(d["folio_asn"])
        etiquetas += [e["codigo_etiqueta"] for e in (d.get("etiquetas") or []) if e.get("codigo_etiqueta")]
    r = c.pedir("GET", "planning", "/api/v1/planning/purchase-orders?limite=30")
    ordenes = [o["id_oc"] for o in (r.json().get("ordenes", []) if r.ok else [])]

    intervenciones: dict[str, set] = {}
    for estado in ("APROBADO", "APLICADO"):
        r = c.pedir("GET", "planning", f"/api/v1/planning/discounts?estado={estado}&limite=300")
        for d in (r.json().get("descuentos", []) if r.ok else []):
            intervenciones.setdefault(str(d["id_locacion"]), set()).add(int(d["id_sku"]))
    r = c.pedir("GET", "planning", "/api/v1/planning/transfers?estado=EJECUTADA&limite=300")
    for t in (r.json().get("transferencias", []) if r.ok else []):
        intervenciones.setdefault(str(t["id_destino"]), set()).add(int(t["id_sku"]))

    desperdicio = c.pedir("GET", "alerts", "/api/v1/alerts/waste-measurement").json()
    print(f"      tiendas={len(tiendas)} · tiendas con stock={sum(1 for v in stock.values() if v)} · "
          f"ASN={len(asn)} · OC={len(ordenes)} · tiendas con intervención={len(intervenciones)}")
    return {
        "salud": salud,
        "verificacion_pool": verificacion,
        "contexto": {
            "servicios": c.servicios,
            "pool": pool,
            "tiendas": tiendas,
            "stock": stock,
            "asn": asn[:50],
            "etiquetas": etiquetas[:50],
            "ordenes_compra": ordenes,
            "intervenciones": {k: sorted(v) for k, v in intervenciones.items()},
        },
        "desperdicio_antes": desperdicio,
    }


# --- 3. Recálculo y medición posterior ---------------------------------------------------------
def recalcular_y_medir(c: Cliente, cuenta_planner: dict, password: str) -> dict:
    web = requests.Session()
    web.verify = c.s.verify
    web.headers["User-Agent"] = UA
    html = web.get(f"{c.host}/login", timeout=30).text
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if m:
        r = web.post(f"{c.host}/login", data={"email": cuenta_planner["email"], "password": password,
                                              "csrf_token": m.group(1)}, timeout=30)
        html = web.get(f"{c.host}/desperdicio-evitado", timeout=120).text
        m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
        if r.ok and m:
            web.post(f"{c.host}/desperdicio-evitado/recalcular", data={"csrf_token": m.group(1)}, timeout=300)
    return c.pedir("GET", "alerts", "/api/v1/alerts/waste-measurement").json()


# --- 4. Análisis y reporte -------------------------------------------------------------------------
def _leer_json(d: Path, nombre: str, defecto):
    p = d / nombre
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else defecto


def _leer_serie(d: Path) -> list[dict]:
    p = d / "serie_segundos.csv"
    if not p.is_file():
        return []
    with p.open(encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    for f in filas:
        for k, v in f.items():
            if k not in ("fase",):
                f[k] = float(v) if "." in v else int(v)
    return filas


def analizar(d: Path, fases_def: tuple[analisis.Fase, ...], escenario: str) -> dict:
    fases = _leer_json(d, "fases.json", [])
    serie = _leer_serie(d)
    endpoints = _leer_json(d, "endpoints.json", [])
    nombres_carga = [f.nombre for f in fases_def if f.nombre != "RECUPERACION"]
    fases_carga = [f for f in fases if f["fase"] in nombres_carga]
    resumen = {
        "global": _leer_json(d, "global.json", {}),
        "fases": fases,
        "saturacion": analisis.detectar_saturacion(fases_carga),
        "top_lentos": analisis.top_lentos(endpoints),
        "negocio": _leer_json(d, "negocio.json", {}),
    }
    if any(f.nombre == "RECUPERACION" for f in fases_def) and fases:
        resumen["recuperacion"] = analisis.medir_recuperacion(serie, "RECUPERACION", fases[0]["p95_ms"])
    else:
        resumen["recuperacion"] = {"recuperado": None, "motivo": f"el escenario {escenario} no tiene fase de recuperación"}
    return resumen


def _tabla(filas: list[dict], columnas: list[tuple[str, str]]) -> str:
    cab = "| " + " | ".join(t for t, _ in columnas) + " |\n|" + "---|" * len(columnas) + "\n"
    return cab + "".join("| " + " | ".join(str(f.get(k, "")) for _, k in columnas) + " |\n" for f in filas)


def _desperdicio(d: dict) -> dict:
    """Extrae los indicadores clave de /alerts/waste-measurement."""
    def g(*ruta):
        v = d
        for k in ruta:
            v = (v or {}).get(k) if isinstance(v, dict) else None
        return v
    return {
        "recuperado_unidades": g("producto_recuperado", "unidades"),
        "evitado_neto_unidades": g("desperdicio_evitado_estimado", "unidades"),
        "co2e_kg": g("co2e_evitado_estimado", "kg_co2e"),
    }


def escribir_reporte(d: Path, config: dict, resumen: dict, antes: dict, despues: dict) -> None:
    g = resumen["global"]
    sat, rec = resumen["saturacion"], resumen["recuperacion"]
    neg = resumen["negocio"]
    da, dd = _desperdicio(antes), _desperdicio(despues)
    col_fase = [("Fase", "fase"), ("VU", "usuarios"), ("Peticiones", "peticiones"), ("RPS", "rps"),
                ("Media ms", "media_ms"), ("p95 ms", "p95_ms"), ("p99 ms", "p99_ms"),
                ("Fallos reales", "fallo"), ("429", "limite"), ("Negocio 409/422", "negocio"), ("% fallo", "pct_fallo")]
    col_ep = [("Método", "metodo"), ("Endpoint", "endpoint"), ("Peticiones", "peticiones"), ("Media ms", "media_ms"),
              ("p95 ms", "p95_ms"), ("p99 ms", "p99_ms"), ("% fallo", "pct_fallo")]
    errores = _leer_json(d, "errores.json", [])[:15]
    texto = f"""# Prueba de carga FreshTrack — {config['run_id']}

- **Escenario:** {config['escenario']} · **Host:** {config['host']} · **Commit:** {config['commit']}
- **Inicio:** {config['inicio']} · **Fin:** {config.get('fin', '')} · **Locust:** {config.get('locust_version', '')}
- **Fases:** {', '.join(f"{f['nombre']} {f['usuarios']} VU × {f['segundos']} s" for f in config['fases'])}
- **Perfiles (rúbrica → FreshTrack):** consultas de tienda, caja POS (ventas reales en todas las tiendas),
  app móvil de almacén, app de escritorio (XML), sensores de temperatura en recepción, paneles web,
  procesos programados y ciclo de rescate. *Conductores actualizando ubicación* no existe en
  FreshTrack y no se simuló.
- La carga sale de **una sola IP**: los límites por IP (catálogo público 120/min, login web 30/min)
  se alcanzan antes que con tráfico real distribuido; sus 429 se reportan aparte como contrapresión.

## 1. Usuarios concurrentes
Máximo alcanzado: **{g.get('usuarios_max', 0)} usuarios virtuales**. Serie por segundo en `serie_segundos.csv`.

## 2–5. Peticiones por segundo, tiempo medio, p95 y p99
Global: **{g.get('peticiones', 0)} peticiones**, **{g.get('rps', 0)} RPS** de media (pico {g.get('rps_pico', 0)} RPS),
media **{g.get('media_ms', 0)} ms**, p95 **{g.get('p95_ms', 0)} ms**, p99 **{g.get('p99_ms', 0)} ms**.

{_tabla(resumen['fases'], col_fase)}
## 6. Errores
Fallos reales (5xx, timeouts): **{g.get('fallo', 0)}** ({g.get('pct_fallo', 0)} %) · contrapresión 429:
**{g.get('limite', 0)}** ({g.get('pct_limite', 0)} %) · reglas de negocio esperadas (409/422): **{g.get('negocio', 0)}** ·
errores de la prueba (otros 4xx): **{g.get('error_prueba', 0)}**.

{_tabla(errores, [("Método", "metodo"), ("Endpoint", "endpoint"), ("Status", "status"), ("Mensaje", "mensaje"), ("Conteo", "conteo")]) if errores else "Sin errores."}
## 7. Saturación
{"**Saturó** en la fase **" + str(sat.get('fase')) + f"** con **{sat.get('usuarios')} VU**: " + "; ".join(sat.get('motivos', [])) + "." if sat.get('saturado') else "No se detectó saturación: " + str(sat.get('motivo', ''))}

Criterios: ΔRPS/ΔVU < 15 % de la línea base, p95 > 1,500 ms, fallos reales > 1 % o 429 > 5 %.

## 8. Recuperación
{("Se recuperó en **" + str(rec.get('segundos')) + " s** tras bajar del pico (objetivo p95 ≤ " + str(rec.get('objetivo_p95_ms')) + " ms y 0 fallos en 10 s).") if rec.get('recuperado') else ("No aplica: " + str(rec.get('motivo')) if rec.get('recuperado') is None else "**No se recuperó** dentro de la fase: p95 final " + str(rec.get('p95_final_ms')) + " ms (objetivo " + str(rec.get('objetivo_p95_ms')) + " ms), fallos " + str(rec.get('fallos_finales')) + ".")}

## 9. Endpoints más lentos (top 10 por p95)
{_tabla(resumen['top_lentos'], col_ep)}
## 10. Operaciones de negocio y desperdicio evitado
| Indicador | Valor |
|---|---|
| Ventas registradas | {int(neg.get('ventas_registradas', 0))} |
| Unidades vendidas | {round(neg.get('unidades_vendidas', 0), 2)} |
| Tickets con SKU intervenido (rescate) | {int(neg.get('tickets_con_sku_intervenido', 0))} |
| Mermas registradas | {int(neg.get('mermas_registradas', 0))} |
| Descuentos aprobados / traslados ejecutados | {int(neg.get('descuentos_aprobados', 0))} / {int(neg.get('traslados_ejecutados', 0))} |
| Lecturas de sensores | {int(neg.get('lecturas_sensor', 0))} |
| Recálculos de desperdicio evitado | {int(neg.get('recalculos_desperdicio', 0))} |

| Desperdicio evitado | Antes | Después |
|---|---|---|
| Unidades recuperadas | {da['recuperado_unidades']} | {dd['recuperado_unidades']} |
| Desperdicio evitado neto (unidades) | {da['evitado_neto_unidades']} | {dd['evitado_neto_unidades']} |
| CO2e evitado (kg) | {da['co2e_kg']} | {dd['co2e_kg']} |

## Archivos de esta corrida
`config.json`, `contexto.json`, `prevuelo.json`, `locust.html`, `locust_*.csv`, `locust.log`,
`serie_segundos.csv`, `fases.json`, `fase_endpoints.json`, `endpoints.json`, `errores.json`,
`global.json`, `negocio.json`, `desperdicio_antes.json`, `desperdicio_despues.json`, `resumen.json`.
Importar a PostgreSQL: `python scripts/locust_importar.py {d.as_posix()}`
"""
    (d / "REPORTE.md").write_text(texto, encoding="utf-8")


# --- main -----------------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Prueba de carga FreshTrack con Locust")
    ap.add_argument("--host", required=True, help="URL del sitio (gateway), p. ej. https://34.x.x.x.nip.io")
    ap.add_argument("--escenario", choices=("rendimiento", "ventas"), default="rendimiento")
    ap.add_argument("--fases", help="Sobrescribe la curva: 'NOMBRE:segundos:usuarios,...'")
    ap.add_argument("--servicios", help="Solo local sin gateway: 'auth=http://localhost:5001,catalog=...'")
    ap.add_argument("--admin-email", default=os.getenv("LOCUST_ADMIN_EMAIL", "admin@freshtrack.mx"))
    ap.add_argument("--admin-password", default=os.getenv("LOCUST_ADMIN_PASSWORD"))
    ap.add_argument("--password-pool", default=os.getenv("LOCUST_PASSWORD_POOL"))
    ap.add_argument("--patron-pool", default=r"^op_\d+@freshtrack\.mx$")
    ap.add_argument("--max-cuentas-rol", type=int, default=300)
    ap.add_argument("--salida", default="docs/pruebas/locust")
    ap.add_argument("--inseguro", action="store_true", help="No verificar el certificado TLS")
    args = ap.parse_args()
    if not args.admin_password or not args.password_pool:
        ap.error("Define LOCUST_ADMIN_PASSWORD y LOCUST_PASSWORD_POOL (o --admin-password / --password-pool).")
    if args.inseguro:
        urllib3.disable_warnings()

    fases = analisis.parsear_fases(args.fases) if args.fases else (
        analisis.FASES_VENTAS if args.escenario == "ventas" else analisis.FASES_RENDIMIENTO)
    commit = _git_commit()
    run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{args.escenario}-{commit}"
    d = RAIZ / args.salida / run_id
    d.mkdir(parents=True, exist_ok=True)

    c = Cliente(args.host, _servicios(args.servicios), verificar_tls=not args.inseguro)
    pv = prevuelo(c, args)
    (d / "contexto.json").write_text(json.dumps(pv["contexto"], ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "prevuelo.json").write_text(json.dumps({"salud": pv["salud"], "pool": pv["verificacion_pool"]},
                                                ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "desperdicio_antes.json").write_text(json.dumps(pv["desperdicio_antes"], ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        version = subprocess.check_output([sys.executable, "-m", "locust", "--version"], text=True).split()[1]
    except Exception:  # noqa: BLE001
        version = "?"
    config = {
        "run_id": run_id, "escenario": args.escenario, "host": args.host, "commit": commit,
        "locust_version": version, "inicio": datetime.now(timezone.utc).isoformat(),
        "fases": [f.__dict__ for f in fases], "servicios": c.servicios,
        "cuentas_por_rol": {r: len(v) for r, v in pv["contexto"]["pool"].items()},
        "tiendas": len(pv["contexto"]["tiendas"]),
    }

    print(f"[2/4] Locust: {args.escenario}, {analisis.duracion_total(fases)} s, pico {max(f.usuarios for f in fases)} VU")
    env = {**os.environ,
           "LOCUST_CONTEXTO": str(d / "contexto.json"), "LOCUST_ESCENARIO": args.escenario,
           "LOCUST_FASES": ",".join(f"{f.nombre}:{f.segundos}:{f.usuarios}" for f in fases),
           "LOCUST_SALIDA": str(d), "LOCUST_RUN_ID": run_id, "LOCUST_MODO": "curva",
           "LOCUST_PASSWORD_POOL": args.password_pool}
    cmd = [sys.executable, "-m", "locust", "-f", str(RAIZ / "tests/load/locustfile.py"), "--headless",
           "--host", args.host.rstrip("/"), "--csv", str(d / "locust"), "--csv-full-history",
           "--html", str(d / "locust.html"), "--only-summary", "--stop-timeout", "30"]
    if args.inseguro:
        env["LOCUST_INSEGURO"] = "1"  # el locustfile desactiva la verificación TLS en sus clientes
    with (d / "locust.log").open("w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, env=env, cwd=RAIZ, stdout=log, stderr=subprocess.STDOUT,
                              timeout=analisis.duracion_total(fases) + 600)
    config["fin"] = datetime.now(timezone.utc).isoformat()
    config["locust_exit_code"] = proc.returncode
    (d / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[3/4] Recalculando y midiendo el desperdicio evitado")
    planner = (pv["contexto"]["pool"].get("planner") or [{}])[0]
    despues = recalcular_y_medir(c, planner, args.password_pool) if planner else {}
    (d / "desperdicio_despues.json").write_text(json.dumps(despues, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[4/4] Analizando y escribiendo el reporte")
    resumen = analizar(d, fases, args.escenario)
    resumen["desperdicio"] = {"antes": _desperdicio(pv["desperdicio_antes"]), "despues": _desperdicio(despues)}
    (d / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    escribir_reporte(d, config, resumen, pv["desperdicio_antes"], despues)
    print(f"Listo: {d}/REPORTE.md (código de salida de Locust {proc.returncode})")
    return 0 if (d / "fases.json").is_file() else 1


if __name__ == "__main__":
    sys.exit(main())
