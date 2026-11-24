-- =============================================================================
-- 13_dispositivos_idempotencia.sql — Registro seguro de dispositivos móviles y
-- merma idempotente (sincronización posterior de la app Android)
--
--   operacion.dispositivo_movil   teléfonos registrados por usuario (UUID generado
--                                 una vez en el teléfono, modelo, versión de
--                                 Android y de la app); el administrador puede
--                                 revocarlos y un dispositivo revocado ya no
--                                 puede volver a registrarse.
--   operacion.merma.idempotency_key  la app reenvía la merma capturada sin
--                                 conexión con la misma llave: el índice UNIQUE
--                                 impide descontar inventario dos veces.
--
-- Idempotente. En caliente:
--   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
--     sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
--            -f /docker-entrypoint-initdb.d/13_dispositivos_idempotencia.sql'
-- =============================================================================

CREATE TABLE IF NOT EXISTS operacion.dispositivo_movil (
    id_registro      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_dispositivo   uuid NOT NULL,
    id_usuario       uuid NOT NULL REFERENCES operacion.usuario(id_usuario),
    plataforma       varchar(20) NOT NULL DEFAULT 'ANDROID',
    modelo           varchar(120),
    version_so       varchar(40),
    version_app      varchar(40),
    ultima_ip        varchar(45),
    registrado_en    timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultimo_registro  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revocado         boolean NOT NULL DEFAULT false,
    revocado_en      timestamptz,
    revocado_por     uuid REFERENCES operacion.usuario(id_usuario),
    CONSTRAINT uq_dispositivo_usuario UNIQUE (id_dispositivo, id_usuario)
);
CREATE INDEX IF NOT EXISTS idx_dispositivo_usuario ON operacion.dispositivo_movil (id_usuario, ultimo_registro DESC);

ALTER TABLE operacion.merma ADD COLUMN IF NOT EXISTS idempotency_key varchar(80);
CREATE UNIQUE INDEX IF NOT EXISTS uq_merma_idempotency_key
    ON operacion.merma (idempotency_key) WHERE idempotency_key IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT SELECT, INSERT, UPDATE ON operacion.dispositivo_movil TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT SELECT ON operacion.dispositivo_movil TO app_auditor;
    END IF;
END $$;
