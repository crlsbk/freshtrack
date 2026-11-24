#!/usr/bin/env bash
# Corre el escenario escalonado de Locust y muestrea CPU/memoria de los contenedores.
#
#   tests/carga/correr.sh [carpeta_salida] [escala_tiempo]
#
#   carpeta_salida  donde quedan los CSV, el HTML de Locust y docker_stats.csv
#                   (defecto: docs/pruebas/carga/<fecha>)
#   escala_tiempo   1 = escenario completo (~11 min); 0.1 = humo (~1 min)
#
# Después: .venv/bin/python tests/carga/analizar.py <carpeta_salida>
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SALIDA="${1:-$RAIZ/docs/pruebas/carga/$(date +%Y%m%d-%H%M)}"
ESCALA="${2:-1}"
LOCUST="${LOCUST:-$RAIZ/.venv/bin/locust}"
mkdir -p "$SALIDA"

# Muestreo de contenedores cada ~3 s (docker stats tarda ~2 s por llamada).
(
  echo "ts,contenedor,cpu_pct,mem_mb"
  while true; do
    ts=$(date +%s)
    docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' 2>/dev/null |
      awk -F, -v ts="$ts" '{
        gsub("%","",$2); split($3,m," ");
        v=m[1]; mb=v+0;
        if (v ~ /GiB/) mb=mb*1024; else if (v ~ /KiB/) mb=mb/1024;
        printf "%s,%s,%s,%.1f\n", ts, $1, $2, mb }'
    sleep 1
  done
) > "$SALIDA/docker_stats.csv" &
MUESTREO=$!
trap 'kill $MUESTREO 2>/dev/null || true' EXIT

CARGA_ESCALA_TIEMPO="$ESCALA" CARGA_MARCAS="$SALIDA/inicio.txt" \
  "$LOCUST" -f "$RAIZ/tests/carga/locustfile.py" --headless \
  --csv "$SALIDA/locust" --csv-full-history --html "$SALIDA/locust_reporte.html" \
  --only-summary 2>&1 | tail -n 60 > "$SALIDA/resumen_consola.txt" || true

echo "Resultados en $SALIDA"
