-- =============================================================================
-- 02_ddl_auditoria.sql — Esquema de auditoría
--
-- La bitácora es INMUTABLE: un trigger bloquea cualquier UPDATE o DELETE.
-- Se llena por dos vías:
--   1) Triggers a nivel de fila sobre las tablas de operación (genéricos).
--   2) Eventos de aplicación (LOGIN, RUN_FORECAST, APPROVE_TRANSFER, ...)
--      mediante auditoria.fn_registrar_accion(...).
--
-- El usuario responsable se obtiene de la variable de sesión
-- `app.current_user_id`, que la aplicación fija en cada transacción
-- (ver app/db.py → sesion_bd()).
-- =============================================================================

CREATE TABLE IF NOT EXISTS auditoria.bitacora_eventos (
    id_evento        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fecha_evento     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accion           varchar(60) NOT NULL,
    tipo_operacion   varchar(10) NOT NULL,
    nombre_tabla     varchar(100) NOT NULL,
    id_registro      text,
    id_usuario_app   uuid,
    usuario_email    varchar(255),
    descripcion      text,
    estado_anterior  jsonb,
    estado_nuevo     jsonb,
    ip               inet,
    user_agent       text,
    CONSTRAINT chk_tipo_operacion CHECK (
        tipo_operacion IN ('INSERT', 'UPDATE', 'DELETE', 'ACCION', 'LOGIN', 'LOGOUT')
    )
);

CREATE INDEX IF NOT EXISTS idx_bitacora_fecha
    ON auditoria.bitacora_eventos (fecha_evento DESC);
CREATE INDEX IF NOT EXISTS idx_bitacora_usuario
    ON auditoria.bitacora_eventos (id_usuario_app, fecha_evento DESC);
CREATE INDEX IF NOT EXISTS idx_bitacora_accion
    ON auditoria.bitacora_eventos (accion, fecha_evento DESC);
CREATE INDEX IF NOT EXISTS idx_bitacora_tabla
    ON auditoria.bitacora_eventos (nombre_tabla, fecha_evento DESC);

COMMENT ON TABLE auditoria.bitacora_eventos IS
    'Bitácora inmutable. Cubre las acciones exigidas: LOGIN, LOGOUT, CREATE_PRODUCT, UPDATE_PRODUCT, CREATE_BATCH, RECEIVE_INVENTORY, REGISTER_SALE, REGISTER_SHRINKAGE, RUN_FORECAST, CREATE_REPLENISHMENT, APPROVE_REPLENISHMENT, CREATE_TRANSFER, APPROVE_TRANSFER.';

-- -----------------------------------------------------------------------------
-- Bloqueo de alteración de la bitácora
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auditoria.fn_bloquear_modificacion_auditoria()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Violación de seguridad: la bitácora de auditoría es inmutable (operación % bloqueada).',
        TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_proteger_bitacora ON auditoria.bitacora_eventos;
CREATE TRIGGER trg_proteger_bitacora
    BEFORE UPDATE OR DELETE ON auditoria.bitacora_eventos
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_bloquear_modificacion_auditoria();

-- -----------------------------------------------------------------------------
-- Trigger genérico de fila
--   Se engancha a cada tabla de operación con:
--     CREATE TRIGGER trg_aud_<tabla> AFTER INSERT OR UPDATE OR DELETE
--     ON operacion.<tabla> FOR EACH ROW
--     EXECUTE FUNCTION auditoria.fn_registrar_auditoria('<ACCION_BASE>');
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auditoria.fn_registrar_auditoria()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = auditoria, operacion, pg_catalog
AS $$
DECLARE
    v_user_id  uuid;
    v_email    varchar(255);
    v_accion   varchar(60);
    v_id_reg   text;
    v_ant      jsonb;
    v_nuevo    jsonb;
    v_base     varchar(60);
BEGIN
    -- Usuario responsable: lo fija la aplicación al abrir la transacción.
    BEGIN
        v_user_id := NULLIF(current_setting('app.current_user_id', true), '')::uuid;
        v_email   := NULLIF(current_setting('app.current_user_email', true), '');
    EXCEPTION WHEN OTHERS THEN
        v_user_id := NULL;
        v_email   := NULL;
    END;

    -- Acción base pasada como argumento del trigger (p. ej. 'PRODUCTO').
    v_base := COALESCE(TG_ARGV[0], upper(TG_TABLE_NAME));

    v_accion := CASE TG_OP
        WHEN 'INSERT' THEN 'CREATE_' || v_base
        WHEN 'UPDATE' THEN 'UPDATE_' || v_base
        WHEN 'DELETE' THEN 'DELETE_' || v_base
        ELSE 'ACCION_' || v_base
    END;

    IF TG_OP = 'DELETE' THEN
        v_ant   := to_jsonb(OLD);
        v_nuevo := NULL;
        v_id_reg := COALESCE(v_ant ->> 'id_lote', v_ant ->> 'id_sku',
                             v_ant ->> 'id_usuario', v_ant ->> 'id_locacion',
                             v_ant ->> 'id_proveedor', v_ant ->> 'id_venta',
                             v_ant ->> 'id_merma');
    ELSIF TG_OP = 'UPDATE' THEN
        -- Solo registramos si de verdad hubo cambios.
        IF OLD IS NOT DISTINCT FROM NEW THEN
            RETURN NEW;
        END IF;
        v_ant   := to_jsonb(OLD);
        v_nuevo := to_jsonb(NEW);
        v_id_reg := COALESCE(v_nuevo ->> 'id_lote', v_nuevo ->> 'id_sku',
                             v_nuevo ->> 'id_usuario', v_nuevo ->> 'id_locacion',
                             v_nuevo ->> 'id_proveedor', v_nuevo ->> 'id_venta',
                             v_nuevo ->> 'id_merma');
    ELSE
        v_ant   := NULL;
        v_nuevo := to_jsonb(NEW);
        v_id_reg := COALESCE(v_nuevo ->> 'id_lote', v_nuevo ->> 'id_sku',
                             v_nuevo ->> 'id_usuario', v_nuevo ->> 'id_locacion',
                             v_nuevo ->> 'id_proveedor', v_nuevo ->> 'id_venta',
                             v_nuevo ->> 'id_merma');
    END IF;

    INSERT INTO auditoria.bitacora_eventos (
        accion, tipo_operacion, nombre_tabla, id_registro,
        id_usuario_app, usuario_email, descripcion,
        estado_anterior, estado_nuevo
    ) VALUES (
        v_accion, TG_OP, TG_TABLE_NAME, v_id_reg,
        v_user_id, v_email,
        format('%s sobre %s.%s', TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME),
        v_ant, v_nuevo
    );

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

-- -----------------------------------------------------------------------------
-- Registro de acciones de aplicación (no ligadas a una fila concreta)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auditoria.fn_registrar_accion(
    p_accion          varchar,
    p_tabla           varchar,
    p_id_registro     text        DEFAULT NULL,
    p_descripcion     text        DEFAULT NULL,
    p_estado_anterior jsonb       DEFAULT NULL,
    p_estado_nuevo    jsonb       DEFAULT NULL,
    p_id_usuario      uuid        DEFAULT NULL,
    p_usuario_email   varchar     DEFAULT NULL,
    p_ip              text        DEFAULT NULL,
    p_user_agent      text        DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = auditoria, pg_catalog
AS $$
DECLARE
    v_id      uuid;
    v_user    uuid;
    v_email   varchar(255);
    v_tipo    varchar(10);
BEGIN
    -- Si no se pasa usuario explícito, se toma de la variable de sesión.
    IF p_id_usuario IS NULL THEN
        BEGIN
            v_user := NULLIF(current_setting('app.current_user_id', true), '')::uuid;
            v_email := NULLIF(current_setting('app.current_user_email', true), '');
        EXCEPTION WHEN OTHERS THEN
            v_user := NULL; v_email := NULL;
        END;
    ELSE
        v_user := p_id_usuario;
        v_email := p_usuario_email;
    END IF;

    v_tipo := CASE
        WHEN p_accion = 'LOGIN'  THEN 'LOGIN'
        WHEN p_accion = 'LOGOUT' THEN 'LOGOUT'
        WHEN p_accion LIKE 'CREATE_%' OR p_accion LIKE 'REGISTER_%' OR p_accion LIKE 'RUN_%' THEN 'INSERT'
        WHEN p_accion LIKE 'UPDATE_%' OR p_accion LIKE 'APPROVE_%' OR p_accion LIKE 'REJECT_%'
          OR p_accion LIKE 'ACTIVATE_%' OR p_accion LIKE 'DEACTIVATE_%' THEN 'UPDATE'
        WHEN p_accion LIKE 'DELETE_%' THEN 'DELETE'
        ELSE 'ACCION'
    END;

    INSERT INTO auditoria.bitacora_eventos (
        accion, tipo_operacion, nombre_tabla, id_registro,
        id_usuario_app, usuario_email, descripcion,
        estado_anterior, estado_nuevo, ip, user_agent
    ) VALUES (
        upper(p_accion), v_tipo, COALESCE(p_tabla, '-'), p_id_registro,
        v_user, v_email, p_descripcion,
        p_estado_anterior, p_estado_nuevo,
        NULLIF(p_ip, '')::inet, p_user_agent
    )
    RETURNING id_evento INTO v_id;

    RETURN v_id;
END;
$$;

-- NOTA: la vista auditoria.v_bitacora se crea en 06_views.sql, porque
-- depende de operacion.usuario y operacion.rol (definidas en 03).

-- -----------------------------------------------------------------------------
-- Permisos
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT SELECT, INSERT ON auditoria.bitacora_eventos TO app_backend;
        GRANT EXECUTE ON FUNCTION auditoria.fn_registrar_accion(
            varchar, varchar, text, text, jsonb, jsonb, uuid, varchar, text, text
        ) TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT SELECT ON auditoria.bitacora_eventos TO app_auditor;
    END IF;
END
$$;
