-- =============================================================================
-- 01_init_schemas.sql — Extensiones y esquemas de FreshTrack
--
-- Se ejecuta después de 00_init_roles.sh y antes del DDL.
-- Idempotente: puede correrse varias veces sin efectos secundarios.
-- =============================================================================

-- gen_random_uuid(), crypt(), gen_salt() para los hashes de contraseña
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Normalización de acentos para generar correos a partir de nombres
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Esquema transaccional: catálogos, inventario y operación diaria
CREATE SCHEMA IF NOT EXISTS operacion;

-- Esquema analítico: pronóstico, reabastecimiento, transferencias y alertas
CREATE SCHEMA IF NOT EXISTS analitica;

-- Esquema de auditoría: bitácora inmutable de eventos
CREATE SCHEMA IF NOT EXISTS auditoria;

-- -----------------------------------------------------------------------------
-- Permisos por rol
--   app_backend  → la aplicación Flask (lectura/escritura de operación)
--   app_etl      → proceso de carga histórica
--   app_auditor  → solo lectura (rol de auditoría, no puede alterar nada)
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT USAGE ON SCHEMA operacion, analitica, auditoria TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_etl') THEN
        GRANT USAGE ON SCHEMA operacion, analitica TO app_etl;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT USAGE ON SCHEMA operacion, analitica, auditoria TO app_auditor;
    END IF;
END
$$;
