#!/usr/bin/env bash
# =============================================================================
# Respaldo diario de PostgreSQL y MongoDB (y subida opcional a GCS).
#
# Uso manual o por cron:
#   /ruta/del/repo/deploy/backup_db.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/var/backups/freshtrack}"
RETENCION_DIAS="${RETENCION_DIAS:-7}"
TS="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"

PG_FILE="${BACKUP_DIR}/pg_${POSTGRES_DB:-retail_perecederos}_${TS}.dump"
MG_FILE="${BACKUP_DIR}/mongo_${MONGO_DB:-retail_perecederos}_${TS}.archive.gz"

echo "[backup] Respaldando PostgreSQL -> ${PG_FILE}"
docker exec freshtrack_db pg_dump \
  -U "${POSTGRES_USER:-postgres}" \
  -d "${POSTGRES_DB:-retail_perecederos}" \
  -Fc > "${PG_FILE}"

echo "[backup] Respaldando MongoDB -> ${MG_FILE}"
docker exec freshtrack_mongo mongodump \
  --username "${MONGO_USER:-freshtrack_mongo}" \
  --password "${MONGO_PASSWORD}" \
  --authenticationDatabase admin \
  --archive --gzip > "${MG_FILE}"

echo "[backup] Purgando respaldos locales con más de ${RETENCION_DIAS} días..."
find "$BACKUP_DIR" -maxdepth 1 -type f -mtime +"$RETENCION_DIAS" -delete

if [ -n "${GCS_BACKUP_BUCKET:-}" ]; then
  DEST="gs://${GCS_BACKUP_BUCKET}/backups/${TS}/"
  if command -v gcloud >/dev/null 2>&1; then
    echo "[backup] Subiendo respaldos a ${DEST} vía gcloud storage..."
    gcloud storage cp "$PG_FILE" "$MG_FILE" "$DEST"
  elif command -v gsutil >/dev/null 2>&1; then
    echo "[backup] Subiendo respaldos a ${DEST} vía gsutil..."
    gsutil cp "$PG_FILE" "$MG_FILE" "$DEST"
  else
    echo "[backup] ADVERTENCIA: GCS_BACKUP_BUCKET definido pero ni gcloud ni gsutil están instalados en la VM." >&2
  fi
fi

echo "[backup] Completado: ${PG_FILE}, ${MG_FILE}"
