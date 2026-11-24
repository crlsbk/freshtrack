-- =============================================================================
-- 10_refresh_token.sql — Refresh tokens con rotación y detección de reutilización
--
-- Cambio mínimo: tres columnas opcionales en operacion.sesion_usuario (una fila
-- por access token emitido, como hasta ahora). Idempotente; en caliente:
--
--   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
--     sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
--            -f /docker-entrypoint-initdb.d/10_refresh_token.sql'
--
--   refresh_hash       SHA-256 del refresh token (el token en claro nunca se guarda)
--   refresh_expira_en  fin ABSOLUTO de la sesión: rotar no lo extiende
--   familia            todas las filas nacidas del mismo login; si un refresh ya
--                      rotado se reutiliza (robo), se revoca la familia completa
-- =============================================================================

ALTER TABLE operacion.sesion_usuario ADD COLUMN IF NOT EXISTS refresh_hash      text;
ALTER TABLE operacion.sesion_usuario ADD COLUMN IF NOT EXISTS refresh_expira_en timestamptz;
ALTER TABLE operacion.sesion_usuario ADD COLUMN IF NOT EXISTS familia           uuid;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sesion_refresh_hash
    ON operacion.sesion_usuario (refresh_hash) WHERE refresh_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sesion_familia
    ON operacion.sesion_usuario (familia) WHERE familia IS NOT NULL;

-- Vida del access token (minutos). La sesión completa sigue en jwt_horas_vigencia.
INSERT INTO analitica.configuracion (clave, valor, tipo, descripcion)
VALUES ('jwt_minutos_acceso', '15', 'entero',
        'Minutos de vida del access token JWT; se renueva con el refresh token hasta jwt_horas_vigencia.')
ON CONFLICT (clave) DO NOTHING;
