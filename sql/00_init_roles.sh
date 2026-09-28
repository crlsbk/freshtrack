#!/usr/bin/env bash
# =============================================================================
# 00_init_roles.sh — Crea los roles transaccionales de FreshTrack.
#
# Las contraseñas NO están en el código: se leen del entorno (.env).
# Se ejecuta automáticamente en el primer arranque del contenedor de PostgreSQL
# (docker-entrypoint-initdb.d) y también desde scripts/bootstrap_db.py.
#
# Variables de entorno utilizadas:
#   POSTGRES_DB              nombre de la base (default: retail_perecederos)
#   POSTGRES_USER            superusuario (default: postgres)
#   APP_BACKEND_PASSWORD     contraseña del rol de la aplicación  (OBLIGATORIA)
#   APP_AUDITOR_PASSWORD     contraseña del rol de solo lectura   (OBLIGATORIA)
#
# Las dos contraseñas son obligatorias y no tienen valor por defecto: el script
# aborta si faltan. Así nunca se crean roles con una clave conocida.
# =============================================================================
set -euo pipefail

DB="${POSTGRES_DB:-retail_perecederos}"
SUPERUSER="${POSTGRES_USER:-postgres}"

# Sin valor por defecto: si la variable falta, el script falla en vez de crear
# roles con una contraseña conocida. Es la misma regla que aplica config.py con
# SECRET_KEY y DATABASE_URL.
exigir() {
    local nombre="$1"
    local valor="${!nombre:-}"
    if [ -z "$valor" ]; then
        echo "[init] ERROR: falta la variable de entorno ${nombre}." >&2
        echo "[init] Copia env.example a .env y define las claves antes de continuar:" >&2
        echo "[init]     cp env.example .env" >&2
        exit 1
    fi
    printf '%s' "$valor"
}

BACKEND_PASS="$(exigir APP_BACKEND_PASSWORD)"
AUDITOR_PASS="$(exigir APP_AUDITOR_PASSWORD)"

echo "[init] Creando roles transaccionales en la base ${DB}..."

psql -v ON_ERROR_STOP=1 --username "$SUPERUSER" --dbname "$DB" <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        CREATE ROLE app_backend LOGIN PASSWORD '${BACKEND_PASS}';
    ELSE
        ALTER ROLE app_backend WITH LOGIN PASSWORD '${BACKEND_PASS}';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        CREATE ROLE app_auditor LOGIN PASSWORD '${AUDITOR_PASS}';
    ELSE
        ALTER ROLE app_auditor WITH LOGIN PASSWORD '${AUDITOR_PASS}';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_etl') THEN
        CREATE ROLE app_etl LOGIN PASSWORD '${BACKEND_PASS}';
    ELSE
        ALTER ROLE app_etl WITH LOGIN PASSWORD '${BACKEND_PASS}';
    END IF;
END
\$\$;

GRANT CONNECT ON DATABASE ${DB} TO app_backend, app_auditor, app_etl;
SQL

echo "[init] Roles listos."
