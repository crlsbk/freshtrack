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
--
-- Endurecimiento: ni la base ni el esquema public conservan los privilegios que
-- PostgreSQL concede a PUBLIC por omisión. Es seguro porque en public no vive
-- nada nuestro: las únicas tablas y vistas del sistema están en operacion,
-- analitica y auditoria.
--
-- La excepción son las EXTENSIONES. pgcrypto y unaccent se instalaron en public
-- (CREATE EXTENSION sin esquema), así que crypt(), gen_salt() y los diccionarios
-- de unaccent son objetos public.*. Para resolver un nombre calificado hay que
-- tener USAGE sobre su esquema: sin este grant, el login falla con
-- «permission denied for schema public» aunque el rol sí tenga EXECUTE sobre la
-- función (EXECUTE por sí solo no basta). Por eso va el USAGE explícito abajo.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    -- Quita los privilegios por omisión de PUBLIC (idempotente). Los roles de
    -- aplicación no los necesitan: reciben CONNECT de forma explícita.
    EXECUTE format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database());
    REVOKE ALL ON SCHEMA public FROM PUBLIC;

    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT USAGE ON SCHEMA operacion, analitica, auditoria TO app_backend;
        -- Necesario para public.crypt() y public.gen_salt() en la verificación
        -- de contraseñas (ver app/security.py). Solo USAGE: sin CREATE.
        GRANT USAGE ON SCHEMA public TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_etl') THEN
        GRANT USAGE ON SCHEMA operacion, analitica TO app_etl;
        GRANT USAGE ON SCHEMA public TO app_etl;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT USAGE ON SCHEMA operacion, analitica, auditoria TO app_auditor;
    END IF;
END
$$;
