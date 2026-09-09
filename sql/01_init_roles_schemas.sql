-- 01_init_roles_schemas.sql
-- Inicialización de extensiones, esquemas y roles transaccionales

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SCHEMA IF NOT EXISTS operacion;
CREATE SCHEMA IF NOT EXISTS auditoria;

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_backend') THEN
      CREATE ROLE app_backend WITH LOGIN PASSWORD 'backend_secure_pass';
   END IF;
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_auditor') THEN
      CREATE ROLE app_auditor WITH LOGIN PASSWORD 'auditor_secure_pass';
   END IF;
END
$$;

GRANT CONNECT ON DATABASE retail_perecederos TO app_backend, app_auditor;
GRANT USAGE ON SCHEMA operacion, auditoria TO app_backend, app_auditor;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA operacion TO app_backend;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA operacion TO app_backend;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA auditoria TO app_backend;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA auditoria TO app_backend;
GRANT SELECT ON ALL TABLES IN SCHEMA operacion, auditoria TO app_auditor;
ALTER DEFAULT PRIVILEGES IN SCHEMA operacion GRANT ALL ON TABLES TO app_backend;
ALTER DEFAULT PRIVILEGES IN SCHEMA auditoria GRANT SELECT, INSERT ON TABLES TO app_backend;
ALTER DEFAULT PRIVILEGES IN SCHEMA operacion, auditoria GRANT SELECT ON TABLES TO app_auditor;
