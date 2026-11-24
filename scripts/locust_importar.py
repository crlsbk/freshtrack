#!/usr/bin/env python3
"""
Importa a PostgreSQL (esquema `pruebas`, sql/11_pruebas_carga.sql) una corrida
de Locust generada por scripts/locust_ejecutar.py.

    python scripts/locust_importar.py docs/pruebas/locust/<run_id>

Idempotente: reimportar la misma corrida reemplaza sus filas. En producción el
puerto de PostgreSQL está cerrado, así que se ejecuta dentro de la VM:
    scp -r docs/pruebas/locust/<run_id> vm:~/iac-proyecto/docs/pruebas/locust/
    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec app \\
        python scripts/locust_importar.py docs/pruebas/locust/<run_id>
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.db import transaccion  # noqa: E402

COLS_METRICA = ("peticiones", "media_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms",
                "ok", "negocio", "limite", "error_prueba", "fallo", "pct_fallo")


def _json(d: Path, nombre: str, defecto):
    p = d / nombre
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else defecto


def leer_corrida(d: Path) -> dict:
    """Lee la carpeta y arma las filas a insertar (sin tocar la base: testeable)."""
    config = _json(d, "config.json", None)
    if not config:
        raise SystemExit(f"{d} no tiene config.json: no es una carpeta de corrida.")
    resumen = _json(d, "resumen.json", {})
    g = resumen.get("global", {})
    sat = resumen.get("saturacion", {})
    rec = resumen.get("recuperacion", {})
    serie = []
    p = d / "serie_segundos.csv"
    if p.is_file():
        with p.open(encoding="utf-8") as fh:
            serie = list(csv.DictReader(fh))
    return {
        "corrida": {
            "run_id": config["run_id"], "escenario": config["escenario"], "host": config["host"],
            "commit_git": config.get("commit"), "locust_version": config.get("locust_version"),
            "inicio": config.get("inicio"), "fin": config.get("fin"),
            "usuarios_max": g.get("usuarios_max"), "peticiones": g.get("peticiones"),
            "rps_media": g.get("rps"), "rps_pico": g.get("rps_pico"), "media_ms": g.get("media_ms"),
            "p95_ms": g.get("p95_ms"), "p99_ms": g.get("p99_ms"), "pct_fallo": g.get("pct_fallo"),
            "pct_limite": g.get("pct_limite"), "saturado": sat.get("saturado"),
            "fase_saturacion": sat.get("fase"), "usuarios_saturacion": sat.get("usuarios"),
            "recuperado": rec.get("recuperado"), "recuperacion_s": rec.get("segundos"),
            "config": json.dumps(config), "prevuelo": json.dumps(_json(d, "prevuelo.json", {})),
            "resumen": json.dumps(resumen, default=str), "negocio": json.dumps(_json(d, "negocio.json", {})),
            "desperdicio_antes": json.dumps(_json(d, "desperdicio_antes.json", {})),
            "desperdicio_despues": json.dumps(_json(d, "desperdicio_despues.json", {})),
            "reporte_md": (d / "REPORTE.md").read_text(encoding="utf-8") if (d / "REPORTE.md").is_file() else None,
        },
        "fases": [{"orden": i, **f} for i, f in enumerate(_json(d, "fases.json", []))],
        "endpoints": [{"fase": "TOTAL", **e} for e in _json(d, "endpoints.json", [])] + _json(d, "fase_endpoints.json", []),
        "errores": _json(d, "errores.json", []),
        "serie": serie,
    }


def importar(d: Path) -> dict:
    datos = leer_corrida(d)
    c = datos["corrida"]
    with transaccion() as conn:
        conn.execute(text("DELETE FROM pruebas.corrida WHERE run_id = :r"), {"r": c["run_id"]})
        cols = list(c)
        conn.execute(
            text(f"INSERT INTO pruebas.corrida ({', '.join(cols)}) VALUES ("
                 + ", ".join(f"CAST(:{k} AS jsonb)" if k in ("config", "prevuelo", "resumen", "negocio",
                                                              "desperdicio_antes", "desperdicio_despues") else f":{k}"
                             for k in cols) + ")"),
            c,
        )
        if datos["fases"]:
            conn.execute(
                text("INSERT INTO pruebas.fase (run_id, orden, fase, usuarios, segundos, rps, "
                     + ", ".join(COLS_METRICA) + ") VALUES (:run_id, :orden, :fase, :usuarios, :segundos, :rps, "
                     + ", ".join(f":{k}" for k in COLS_METRICA) + ")"),
                [{"run_id": c["run_id"], "rps": f.get("rps"), **{k: f.get(k) for k in ("orden", "fase", "usuarios", "segundos", *COLS_METRICA)}}
                 for f in datos["fases"]],
            )
        if datos["endpoints"]:
            conn.execute(
                text("INSERT INTO pruebas.endpoint_metrica (run_id, fase, metodo, endpoint, " + ", ".join(COLS_METRICA)
                     + ") VALUES (:run_id, :fase, :metodo, :endpoint, " + ", ".join(f":{k}" for k in COLS_METRICA) + ")"),
                [{"run_id": c["run_id"], **{k: e.get(k) for k in ("fase", "metodo", "endpoint", *COLS_METRICA)}}
                 for e in datos["endpoints"]],
            )
        if datos["errores"]:
            conn.execute(
                text("INSERT INTO pruebas.error (run_id, metodo, endpoint, status, mensaje, conteo) "
                     "VALUES (:run_id, :metodo, :endpoint, :status, :mensaje, :conteo)"),
                [{"run_id": c["run_id"], **e} for e in datos["errores"]],
            )
        if datos["serie"]:
            cols_s = ("segundo", "fase", "usuarios", "peticiones", "rps", "media_ms", "p95_ms", "p99_ms",
                      "ok", "negocio", "limite", "error_prueba", "fallo")
            conn.execute(
                text(f"INSERT INTO pruebas.serie_segundo (run_id, {', '.join(cols_s)}) VALUES (:run_id, "
                     + ", ".join(f":{k}" for k in cols_s) + ")"),
                [{"run_id": c["run_id"], **{k: s.get(k) for k in cols_s}} for s in datos["serie"]],
            )
    return {"run_id": c["run_id"], "fases": len(datos["fases"]), "endpoints": len(datos["endpoints"]),
            "errores": len(datos["errores"]), "segundos": len(datos["serie"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("carpeta", type=Path)
    r = importar(ap.parse_args().carpeta)
    print(f"Importada {r['run_id']}: {r['fases']} fases, {r['endpoints']} filas de endpoint, "
          f"{r['errores']} tipos de error, {r['segundos']} segundos de serie.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
