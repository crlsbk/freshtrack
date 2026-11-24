-- =============================================================================
-- 11_pruebas_carga.sql — Resultados de las pruebas de carga con Locust
--
-- Esquema propio (`pruebas`), separado de la operación. Idempotente; en caliente:
--   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
--     sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
--            -f /docker-entrypoint-initdb.d/11_pruebas_carga.sql'
-- Lo llena scripts/locust_importar.py a partir de docs/pruebas/locust/<run_id>/.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS pruebas;

CREATE TABLE IF NOT EXISTS pruebas.corrida (
    run_id               text PRIMARY KEY,
    escenario            text NOT NULL,
    host                 text NOT NULL,
    commit_git           text,
    locust_version       text,
    inicio               timestamptz,
    fin                  timestamptz,
    usuarios_max         integer,
    peticiones           bigint,
    rps_media            numeric(12,2),
    rps_pico             numeric(12,2),
    media_ms             numeric(12,1),
    p95_ms               numeric(12,1),
    p99_ms               numeric(12,1),
    pct_fallo            numeric(6,2),
    pct_limite           numeric(6,2),
    saturado             boolean,
    fase_saturacion      text,
    usuarios_saturacion  integer,
    recuperado           boolean,
    recuperacion_s       integer,
    config               jsonb NOT NULL DEFAULT '{}',
    prevuelo             jsonb NOT NULL DEFAULT '{}',
    resumen              jsonb NOT NULL DEFAULT '{}',
    negocio              jsonb NOT NULL DEFAULT '{}',
    desperdicio_antes    jsonb NOT NULL DEFAULT '{}',
    desperdicio_despues  jsonb NOT NULL DEFAULT '{}',
    reporte_md           text,
    importado_en         timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pruebas.fase (
    run_id        text NOT NULL REFERENCES pruebas.corrida(run_id) ON DELETE CASCADE,
    orden         integer NOT NULL,
    fase          text NOT NULL,
    usuarios      integer,
    segundos      integer,
    peticiones    bigint,
    rps           numeric(12,2),
    media_ms      numeric(12,1),
    p50_ms        numeric(12,1),
    p95_ms        numeric(12,1),
    p99_ms        numeric(12,1),
    max_ms        numeric(12,1),
    ok            bigint,
    negocio       bigint,
    limite        bigint,
    error_prueba  bigint,
    fallo         bigint,
    pct_fallo     numeric(6,2),
    PRIMARY KEY (run_id, fase)
);

-- fase = 'TOTAL' para el agregado de toda la corrida.
CREATE TABLE IF NOT EXISTS pruebas.endpoint_metrica (
    run_id        text NOT NULL REFERENCES pruebas.corrida(run_id) ON DELETE CASCADE,
    fase          text NOT NULL,
    metodo        text NOT NULL,
    endpoint      text NOT NULL,
    peticiones    bigint,
    media_ms      numeric(12,1),
    p50_ms        numeric(12,1),
    p95_ms        numeric(12,1),
    p99_ms        numeric(12,1),
    max_ms        numeric(12,1),
    ok            bigint,
    negocio       bigint,
    limite        bigint,
    error_prueba  bigint,
    fallo         bigint,
    pct_fallo     numeric(6,2),
    PRIMARY KEY (run_id, fase, metodo, endpoint)
);

CREATE TABLE IF NOT EXISTS pruebas.error (
    run_id     text NOT NULL REFERENCES pruebas.corrida(run_id) ON DELETE CASCADE,
    metodo     text NOT NULL,
    endpoint   text NOT NULL,
    status     integer,
    mensaje    text,
    conteo     bigint NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pruebas_error_run ON pruebas.error (run_id);

CREATE TABLE IF NOT EXISTS pruebas.serie_segundo (
    run_id        text NOT NULL REFERENCES pruebas.corrida(run_id) ON DELETE CASCADE,
    segundo       integer NOT NULL,
    fase          text,
    usuarios      integer,
    peticiones    integer,
    rps           numeric(12,2),
    media_ms      numeric(12,1),
    p95_ms        numeric(12,1),
    p99_ms        numeric(12,1),
    ok            integer,
    negocio       integer,
    limite        integer,
    error_prueba  integer,
    fallo         integer,
    PRIMARY KEY (run_id, segundo)
);

COMMENT ON SCHEMA pruebas IS 'Resultados de pruebas de carga (Locust): una fila por corrida y su detalle.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT USAGE ON SCHEMA pruebas TO app_backend;
        GRANT SELECT, INSERT, DELETE ON ALL TABLES IN SCHEMA pruebas TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT USAGE ON SCHEMA pruebas TO app_auditor;
        GRANT SELECT ON ALL TABLES IN SCHEMA pruebas TO app_auditor;
    END IF;
END
$$;
