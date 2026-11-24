-- =============================================================================
-- 12_app_movil.sql — Tablas que usa la app Android (FreshTrack Mobile)
--
--   operacion.evidencia      fotos subidas desde el teléfono (bucket privado; solo
--                            se guardan metadatos y SHA-256; se ven con URL firmada)
--   operacion.conteo_ciclico conteos físicos por tienda con su exactitud; la
--                            Idempotency-Key evita duplicar ajustes al reintentar
--   operacion.merma.id_evidencia  liga la merma con su foto
--
-- Idempotente. En caliente:
--   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
--     sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
--            -f /docker-entrypoint-initdb.d/12_app_movil.sql'
-- =============================================================================

CREATE TABLE IF NOT EXISTS operacion.evidencia (
    id_evidencia     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo             varchar(20) NOT NULL DEFAULT 'OTRO',
    referencia_tipo  varchar(20),
    referencia_id    varchar(80),
    id_locacion      integer REFERENCES operacion.locacion(id_locacion),
    content_type     varchar(40) NOT NULL,
    tamano_bytes     integer NOT NULL,
    sha256           char(64) NOT NULL,
    storage_provider varchar(20) NOT NULL,
    bucket           varchar(120) NOT NULL,
    object_key       varchar(300) NOT NULL,
    descripcion      text,
    id_usuario       uuid REFERENCES operacion.usuario(id_usuario),
    creado_en        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_evidencia_tipo CHECK (tipo IN ('ANAQUEL', 'MERMA', 'RECEPCION', 'TEMPERATURA', 'OTRO')),
    CONSTRAINT chk_evidencia_tamano CHECK (tamano_bytes > 0)
);
CREATE INDEX IF NOT EXISTS idx_evidencia_loc_fecha ON operacion.evidencia (id_locacion, creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_evidencia_ref ON operacion.evidencia (referencia_tipo, referencia_id);

CREATE TABLE IF NOT EXISTS operacion.conteo_ciclico (
    id_conteo             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_locacion           integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    id_sku                integer REFERENCES operacion.producto(id_sku),
    idempotency_key       varchar(80) UNIQUE,
    lineas_contadas       integer NOT NULL,
    lineas_con_diferencia integer NOT NULL,
    exactitud_pct         numeric(5,2) NOT NULL,
    ajustes               jsonb NOT NULL DEFAULT '[]'::jsonb,
    observacion           text,
    id_usuario            uuid REFERENCES operacion.usuario(id_usuario),
    creado_en             timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conteo_loc_fecha ON operacion.conteo_ciclico (id_locacion, creado_en DESC);

ALTER TABLE operacion.merma ADD COLUMN IF NOT EXISTS id_evidencia uuid REFERENCES operacion.evidencia(id_evidencia);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT SELECT, INSERT, UPDATE ON operacion.evidencia, operacion.conteo_ciclico TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT SELECT ON operacion.evidencia, operacion.conteo_ciclico TO app_auditor;
    END IF;
END $$;
