#!/usr/bin/env python3
"""
Convierte una corrida de tests/carga/correr.sh en un reporte Markdown con gráfica SVG.

    .venv/bin/python tests/carga/analizar.py docs/pruebas/carga/escalonada

Lee locust_stats.csv, locust_stats_history.csv, locust_failures.csv, docker_stats.csv e
inicio.txt, y escribe REPORTE.md + grafica.svg en la misma carpeta con:

  * usuarios concurrentes, peticiones/s, tiempo medio, p95, p99 y errores por escalón
  * saturación: punto donde el throughput deja de crecer y la latencia/CPU se disparan
  * recuperación: segundos que tarda el sistema en volver a la latencia base tras el pico
  * endpoints más lentos y errores agrupados
  * CPU y memoria por contenedor
"""

from __future__ import annotations

import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from locustfile import ESCALONES  # noqa: E402

CPUS_HOST = None  # se llena en main() con os.cpu_count()


def num(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def mediana(vals: list[float]) -> float:
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else 0.0


def leer_inicio(carpeta: Path, primer_ts: float) -> tuple[float, float]:
    f = carpeta / "inicio.txt"
    if not f.exists():
        return primer_ts, 1.0
    lineas = f.read_text().split()
    return float(lineas[0]), float(lineas[1]) if len(lineas) > 1 else 1.0


def escalon_de(rel: float, escala: float) -> str | None:
    for fin, _u, _t, etiqueta in ESCALONES:
        if rel < fin * escala:
            return etiqueta
    return None


def ms(v: float) -> str:
    return f"{v:,.0f} ms" if v < 10_000 else f"{v / 1000:,.1f} s"


# ---------------------------------------------------------------------------
# Gráfica SVG sin dependencias: usuarios, RPS, p95 y errores/s en el tiempo
# ---------------------------------------------------------------------------
def grafica_svg(serie: list[dict], escala: float) -> str:
    W, H, ML, MR = 900, 640, 70, 20
    paneles = [
        ("Usuarios concurrentes", "usuarios", "#2563eb", ""),
        ("Peticiones por segundo", "rps", "#16a34a", ""),
        ("Percentil 95 (ventana móvil)", "p95", "#d97706", " ms"),
        ("Errores por segundo", "fps", "#dc2626", ""),
    ]
    alto = (H - 40) / len(paneles)
    t_max = max((p["rel"] for p in serie), default=1) or 1
    x = lambda t: ML + (W - ML - MR) * t / t_max  # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="system-ui,sans-serif" font-size="11">',
           f'<rect width="{W}" height="{H}" fill="#fff"/>']
    # Bandas de escalones
    ini = 0.0
    for i, (fin, _u, _t, etiqueta) in enumerate(ESCALONES):
        x0, x1 = x(min(ini, t_max)), x(min(fin * escala, t_max))
        if x1 > x0:
            out.append(f'<rect x="{x0:.1f}" y="10" width="{x1 - x0:.1f}" height="{H - 30}" '
                       f'fill="{"#f1f5f9" if i % 2 else "#fff"}"/>')
            out.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{H - 6}" text-anchor="middle" fill="#64748b">{etiqueta}</text>')
        ini = fin * escala
    for i, (titulo, clave, color, unidad) in enumerate(paneles):
        y0 = 14 + i * alto
        vals = [p[clave] for p in serie if p[clave] is not None]
        vmax = max(vals, default=1) or 1
        y = lambda v: y0 + alto - 22 - (alto - 36) * v / vmax  # noqa: E731,B023
        out.append(f'<text x="{ML}" y="{y0 + 8}" font-weight="600" fill="#0f172a">{titulo}</text>')
        out.append(f'<text x="{ML - 6}" y="{y(vmax) + 4:.1f}" text-anchor="end" fill="#64748b">{vmax:,.0f}{unidad}</text>')
        out.append(f'<text x="{ML - 6}" y="{y(0) + 4:.1f}" text-anchor="end" fill="#64748b">0</text>')
        out.append(f'<line x1="{ML}" x2="{W - MR}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="#cbd5e1"/>')
        pts = " ".join(f"{x(p['rel']):.1f},{y(p[clave]):.1f}" for p in serie if p[clave] is not None)
        out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6"/>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    import os

    global CPUS_HOST
    CPUS_HOST = os.cpu_count() or 1
    carpeta = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

    # --- Serie de tiempo agregada -----------------------------------------
    hist = [r for r in csv.DictReader(open(carpeta / "locust_stats_history.csv")) if r["Name"] == "Aggregated"]
    t0, escala = leer_inicio(carpeta, float(hist[0]["Timestamp"]))
    serie = []
    for r in hist:
        rel = float(r["Timestamp"]) - t0
        serie.append({
            "rel": rel,
            "escalon": escalon_de(rel, escala),
            "usuarios": int(r["User Count"]),
            "rps": num(r["Requests/s"]) or 0.0,
            "fps": num(r["Failures/s"]) or 0.0,
            "p50": num(r["50%"]),
            "p95": num(r["95%"]),
            "p99": num(r["99%"]),
        })

    # --- CPU / memoria por contenedor ------------------------------------
    docker = defaultdict(lambda: defaultdict(list))  # escalon -> contenedor -> [(cpu, mem)]
    ruta_docker = carpeta / "docker_stats.csv"
    if ruta_docker.exists():
        for r in csv.DictReader(open(ruta_docker)):
            esc = escalon_de(float(r["ts"]) - t0, escala)
            if esc and num(r["cpu_pct"]) is not None:
                docker[esc][r["contenedor"].replace("freshtrack_", "")].append((num(r["cpu_pct"]), num(r["mem_mb"]) or 0))

    # --- Por escalón -------------------------------------------------------
    filas = []
    for _fin, usuarios_obj, _tasa, etiqueta in ESCALONES:
        pts = [p for p in serie if p["escalon"] == etiqueta]
        if not pts:
            continue
        # Se descartan los primeros 15 s de cada escalón (rampa) para medir el estado estable.
        inicio = pts[0]["rel"]
        estables = [p for p in pts if p["rel"] - inicio >= 15 * escala] or pts
        rps = statistics.mean(p["rps"] for p in estables)
        fps = statistics.mean(p["fps"] for p in estables)
        cont = docker.get(etiqueta, {})
        cpu_total = 0.0
        if cont:
            # CPU total = suma de los promedios de cada contenedor (100% = 1 núcleo)
            cpu_total = sum(statistics.mean(c for c, _m in v) for v in cont.values())
        filas.append({
            "etiqueta": etiqueta, "usuarios": round(statistics.median(p["usuarios"] for p in estables)), "objetivo": usuarios_obj,
            "rps": rps, "fps": fps, "err_pct": 100 * fps / rps if rps else 0.0,
            "p50": mediana([p["p50"] for p in estables]), "p95": mediana([p["p95"] for p in estables]),
            "p99": mediana([p["p99"] for p in estables]), "cpu_total": cpu_total, "pts": pts,
        })

    base = next((f for f in filas if f["etiqueta"].startswith("2-")), filas[0])

    # --- Saturación ----------------------------------------------------------
    saturacion = None
    for prev, f in zip(filas, filas[1:]):
        if f["etiqueta"].startswith("6-"):
            break
        crecimiento_usuarios = f["usuarios"] / max(prev["usuarios"], 1)
        crecimiento_rps = f["rps"] / max(prev["rps"], 0.01)
        motivos = []
        if crecimiento_usuarios > 1.2 and crecimiento_rps < 1 + (crecimiento_usuarios - 1) * 0.5:
            motivos.append(f"el throughput creció solo ×{crecimiento_rps:.2f} con ×{crecimiento_usuarios:.2f} usuarios")
        if f["p95"] > 3 * max(base["p95"], 1):
            motivos.append(f"p95 {ms(f['p95'])} (> 3× la base de {ms(base['p95'])})")
        if f["err_pct"] > 5:
            motivos.append(f"{f['err_pct']:.1f}% de errores")
        if f["cpu_total"] > 0.9 * CPUS_HOST * 100:
            motivos.append(f"CPU total {f['cpu_total']:.0f}% de {CPUS_HOST * 100}% disponibles")
        if motivos:
            saturacion = (f, motivos)
            break

    # --- Recuperación ----------------------------------------------------------
    recuperacion = None
    rec = next((f for f in filas if f["etiqueta"].startswith("6-")), None)
    if rec:
        umbral = max(1.5 * base["p95"], base["p95"] + 100)
        pts = rec["pts"]
        t_ini = pts[0]["rel"]
        racha = 0
        for p in pts:
            ok = p["p95"] is not None and p["p95"] <= umbral and p["fps"] == 0
            racha = racha + 1 if ok else 0
            if racha >= 5:
                recuperacion = (p["rel"] - t_ini - 4, umbral)
                break
        if recuperacion is None:
            recuperacion = (None, umbral)

    # --- Totales y endpoints ----------------------------------------------------
    stats = list(csv.DictReader(open(carpeta / "locust_stats.csv")))
    total = next(r for r in stats if r["Name"] == "Aggregated")
    endpoints = [r for r in stats if r["Name"] != "Aggregated" and int(r["Request Count"]) > 0]
    duracion = max(p["rel"] for p in serie) or 1
    lentos = sorted(endpoints, key=lambda r: num(r["95%"]) or 0, reverse=True)[:12]

    fallas = list(csv.DictReader(open(carpeta / "locust_failures.csv")))
    por_tipo: dict[str, int] = defaultdict(int)
    for f in fallas:
        err = f["Error"]
        m = re.search(r"\b([45]\d\d)\b", err)
        if "sesión perdida" in err:
            clave = "Sesión web perdida (redirección a /login)"
        elif "login web" in err:
            clave = "Login web rechazado/fallido"
        elif m:
            clave = f"HTTP {m.group(1)}"
        elif "Timeout" in err or "timed out" in err:
            clave = "Timeout del cliente"
        elif "Connection" in err:
            clave = "Conexión rechazada/cortada"
        else:
            clave = err[:60]
        por_tipo[clave] += int(f["Occurrences"])

    # --- Markdown ---------------------------------------------------------------
    L: list[str] = []
    w = L.append
    n_total, n_fail = int(total["Request Count"]), int(total["Failure Count"])
    w(f"# Resultados — corrida `{carpeta.name}`\n")
    w(f"Duración: **{duracion / 60:.1f} min** · Escala de tiempo: {escala} · "
      f"Host con {CPUS_HOST} núcleos (Locust corre en el mismo host que los contenedores).\n")
    w("## Resumen global\n")
    w("| Métrica | Valor |\n|---|---|")
    w(f"| Usuarios concurrentes (máx.) | {max(p['usuarios'] for p in serie)} |")
    w(f"| Peticiones totales | {n_total:,} |")
    w(f"| Peticiones por segundo (promedio de la corrida) | {n_total / duracion:.1f} |")
    w(f"| Peticiones por segundo (máximo sostenido, por escalón) | {max(f['rps'] for f in filas):.1f} |")
    w(f"| Tiempo medio de respuesta | {ms(num(total['Average Response Time']))} |")
    w(f"| Mediana | {ms(num(total['50%']))} |")
    w(f"| Percentil 95 | {ms(num(total['95%']))} |")
    w(f"| Percentil 99 | {ms(num(total['99%']))} |")
    w(f"| Errores | {n_fail:,} ({100 * n_fail / max(n_total, 1):.2f}%) |")
    w("")
    w("![Usuarios, RPS, p95 y errores en el tiempo](grafica.svg)\n")

    w("## Por escalón de carga\n")
    w("Valores en estado estable (se descartan los primeros 15 s de rampa de cada escalón). "
      "p50/p95/p99 son la mediana de la ventana móvil de Locust.\n")
    w("| Escalón | Usuarios | RPS | Errores | p50 | p95 | p99 | CPU total contenedores |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    for f in filas:
        w(f"| {f['etiqueta']} | {f['usuarios']} | {f['rps']:.1f} | {f['err_pct']:.1f}% | {ms(f['p50'])} | "
          f"{ms(f['p95'])} | {ms(f['p99'])} | {f['cpu_total']:.0f}% / {CPUS_HOST * 100}% |")
    w("")

    w("## Saturación\n")
    if base["p95"] > 2000 or base["cpu_total"] > 0.8 * CPUS_HOST * 100:
        w(f"**La carga normal ({base['usuarios']} usuarios) ya opera saturada:** p95 de {ms(base['p95'])} y "
          f"{base['cpu_total']:.0f}% de CPU de contenedores sobre {CPUS_HOST * 100}% disponibles. "
          "Los criterios relativos de abajo comparan contra esa base, así que subestiman la saturación.\n")
    if saturacion:
        f, motivos = saturacion
        w(f"El sistema se satura en el escalón **{f['etiqueta']}** (~{f['usuarios']} usuarios concurrentes):\n")
        for m in motivos:
            w(f"- {m}")
    else:
        w("No se detectó saturación con los criterios usados (throughput, p95 > 3× base, errores > 5 %, CPU > 90 %).")
    w("")

    w("## Recuperación\n")
    if recuperacion:
        seg, umbral = recuperacion
        if seg is not None:
            w(f"Tras bajar del pico a {rec['usuarios']} usuarios, el sistema volvió a p95 ≤ {ms(umbral)} sin errores "
              f"(5 s seguidos) en **{max(seg, 0):.0f} s**.")
        else:
            w(f"Tras bajar del pico, el p95 **no** volvió a ≤ {ms(umbral)} sin errores durante el escalón de "
              f"recuperación ({rec['pts'][-1]['rel'] - rec['pts'][0]['rel']:.0f} s).")
    w("")

    w("## Endpoints más lentos (por p95)\n")
    w("| Endpoint | Peticiones | Fallas | Media | p95 | p99 | Máx. |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for r in lentos:
        w(f"| `{r['Type']} {r['Name']}` | {int(r['Request Count']):,} | {int(r['Failure Count']):,} | "
          f"{ms(num(r['Average Response Time']))} | {ms(num(r['95%']))} | {ms(num(r['99%']))} | "
          f"{ms(num(r['Max Response Time']))} |")
    w("")

    w("## Errores\n")
    if por_tipo:
        w("| Tipo | Ocurrencias |\n|---|---:|")
        for k, v in sorted(por_tipo.items(), key=lambda kv: -kv[1]):
            w(f"| {k} | {v:,} |")
        w("\nDetalle (top 10):\n")
        w("| Endpoint | Error | Ocurrencias |\n|---|---|---:|")
        for f in sorted(fallas, key=lambda f: -int(f["Occurrences"]))[:10]:
            err = f["Error"].replace("|", "/").replace("\n", " ")[:140]
            w(f"| `{f['Name']}` | {err} | {int(f['Occurrences']):,} |")
    else:
        w("Sin errores.")
    w("")

    if docker:
        w("## Consumo por contenedor (CPU promedio / máx. · memoria máx.)\n")
        etiquetas = [f["etiqueta"] for f in filas]
        conts = sorted({c for e in docker.values() for c in e},
                       key=lambda c: -max((statistics.mean(x for x, _ in docker[e][c]) for e in docker if c in docker[e]),
                                          default=0))
        w("| Contenedor | " + " | ".join(etiquetas) + " |")
        w("|---|" + "---:|" * len(etiquetas))
        for c in conts:
            celdas = []
            for e in etiquetas:
                v = docker.get(e, {}).get(c)
                celdas.append(f"{statistics.mean(x for x, _ in v):.0f}% / {max(x for x, _ in v):.0f}% · "
                              f"{max(m for _, m in v):.0f} MB" if v else "—")
            w(f"| {c} | " + " | ".join(celdas) + " |")
        w("")

    (carpeta / "REPORTE.md").write_text("\n".join(L))
    (carpeta / "grafica.svg").write_text(grafica_svg(serie, escala))
    print(f"Escrito {carpeta / 'REPORTE.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
