-- =============================================================================
-- 04_ddl_analitica.sql — Esquema analítico
--
-- Pronóstico, reabastecimiento, transferencias, alertas, descuentos y la
-- medición de desperdicio evitado. Todo se calcula desde PostgreSQL;
-- ninguna de estas tablas se llena con datos simulados precalculados.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS analitica;

-- -----------------------------------------------------------------------------
-- Configuración del sistema (umbrales, parámetros de negocio)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.configuracion (
    clave       varchar(60) PRIMARY KEY,
    valor       text NOT NULL,
    tipo        varchar(20) NOT NULL DEFAULT 'texto',
    descripcion text,
    actualizado timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cfg_tipo CHECK (tipo IN ('texto', 'entero', 'decimal', 'booleano', 'json'))
);

-- -----------------------------------------------------------------------------
-- Corridas de pronóstico
--   Debe poder saberse: cuándo se ejecutó, quién, método, periodo histórico,
--   horizonte, producto, tienda y pronóstico. Esta tabla cubre lo primero.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.forecast_run (
    id_run           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    metodo           varchar(40) NOT NULL,
    parametros       jsonb NOT NULL DEFAULT '{}'::jsonb,
    periodo_inicio   date NOT NULL,
    periodo_fin      date NOT NULL,
    horizonte_dias   integer NOT NULL DEFAULT 7,
    id_usuario       uuid REFERENCES operacion.usuario(id_usuario),
    fecha_ejecucion  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duracion_ms      integer,
    n_series         integer NOT NULL DEFAULT 0,
    estado           varchar(20) NOT NULL DEFAULT 'COMPLETADO',
    mae              numeric(12,4),
    rmse             numeric(12,4),
    wmape            numeric(8,4),
    observaciones    text,
    CONSTRAINT chk_fc_metodo CHECK (metodo IN (
        'MEDIA_MOVIL', 'MEDIA_MOVIL_PONDERADA', 'SUAVIZACION_EXPONENCIAL'
    )),
    CONSTRAINT chk_fc_horizonte CHECK (horizonte_dias BETWEEN 1 AND 90),
    CONSTRAINT chk_fc_estado CHECK (estado IN ('COMPLETADO', 'ERROR', 'PARCIAL'))
);

CREATE INDEX IF NOT EXISTS idx_fcrun_fecha ON analitica.forecast_run (fecha_ejecucion DESC);

-- -----------------------------------------------------------------------------
-- Resultados del pronóstico: Producto + Tienda + Fecha → Demanda pronosticada
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.forecast_result (
    id_resultado          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_run                uuid    NOT NULL REFERENCES analitica.forecast_run(id_run) ON DELETE CASCADE,
    id_sku                integer NOT NULL REFERENCES operacion.producto(id_sku),
    id_locacion           integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    fecha_objetivo        date    NOT NULL,
    horizonte_dia         integer NOT NULL,
    demanda_pronosticada  numeric(12,2) NOT NULL,
    demanda_real          numeric(12,2),
    error_absoluto        numeric(12,2),
    CONSTRAINT uq_fc_resultado UNIQUE (id_run, id_sku, id_locacion, fecha_objetivo)
);

CREATE INDEX IF NOT EXISTS idx_fcres_serie ON analitica.forecast_result (id_sku, id_locacion, fecha_objetivo);
CREATE INDEX IF NOT EXISTS idx_fcres_run   ON analitica.forecast_result (id_run);

-- -----------------------------------------------------------------------------
-- Órdenes de reabastecimiento (recomendación + aprobación humana)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.orden_reabastecimiento (
    id_orden              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_sku                integer NOT NULL REFERENCES operacion.producto(id_sku),
    id_locacion           integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    id_proveedor          integer REFERENCES operacion.proveedor(id_proveedor),
    id_run                uuid REFERENCES analitica.forecast_run(id_run),
    demanda_pronosticada  numeric(12,2) NOT NULL DEFAULT 0,
    inventario_fisico     numeric(12,2) NOT NULL DEFAULT 0,
    inventario_riesgo     numeric(12,2) NOT NULL DEFAULT 0,
    inventario_util       numeric(12,2) NOT NULL DEFAULT 0,
    entradas_confirmadas  numeric(12,2) NOT NULL DEFAULT 0,
    stock_seguridad       numeric(12,2) NOT NULL DEFAULT 0,
    lead_time_dias        integer NOT NULL DEFAULT 0,
    moq                   numeric(12,2) NOT NULL DEFAULT 1,
    necesidad_neta        numeric(12,2) NOT NULL DEFAULT 0,
    cantidad_sugerida     numeric(12,2) NOT NULL DEFAULT 0,
    cantidad_aprobada     numeric(12,2),
    prioridad             varchar(10) NOT NULL DEFAULT 'MEDIA',
    estado                varchar(20) NOT NULL DEFAULT 'PENDIENTE',
    explicacion           text,
    advertencias          jsonb NOT NULL DEFAULT '[]'::jsonb,
    id_usuario_solicita   uuid REFERENCES operacion.usuario(id_usuario),
    id_usuario_aprueba    uuid REFERENCES operacion.usuario(id_usuario),
    fecha_creacion        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_decision        timestamptz,
    CONSTRAINT chk_or_estado CHECK (estado IN (
        'PENDIENTE', 'APROBADA', 'RECHAZADA', 'EJECUTADA', 'CANCELADA'
    )),
    CONSTRAINT chk_or_prioridad CHECK (prioridad IN ('ALTA', 'MEDIA', 'BAJA'))
);

CREATE INDEX IF NOT EXISTS idx_or_estado ON analitica.orden_reabastecimiento (estado, fecha_creacion DESC);
CREATE INDEX IF NOT EXISTS idx_or_sku    ON analitica.orden_reabastecimiento (id_sku, id_locacion);

-- -----------------------------------------------------------------------------
-- Transferencias entre locaciones
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.transferencia (
    id_transferencia      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_sku                integer NOT NULL REFERENCES operacion.producto(id_sku),
    id_lote               uuid REFERENCES operacion.lote(id_lote),
    id_locacion_origen    integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    id_locacion_destino   integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    cantidad              numeric(12,2) NOT NULL,
    motivo                text,
    exceso_origen         numeric(12,2),
    faltante_destino      numeric(12,2),
    dias_para_vencer      integer,
    validaciones          jsonb NOT NULL DEFAULT '{}'::jsonb,
    estado                varchar(20) NOT NULL DEFAULT 'SUGERIDA',
    id_usuario_solicita   uuid REFERENCES operacion.usuario(id_usuario),
    id_usuario_aprueba    uuid REFERENCES operacion.usuario(id_usuario),
    fecha_creacion        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_decision        timestamptz,
    fecha_ejecucion       timestamptz,
    CONSTRAINT chk_tr_estado CHECK (estado IN (
        'SUGERIDA', 'APROBADA', 'RECHAZADA', 'EJECUTADA', 'CANCELADA'
    )),
    CONSTRAINT chk_tr_cantidad CHECK (cantidad > 0),
    CONSTRAINT chk_tr_distintas CHECK (id_locacion_origen <> id_locacion_destino)
);

CREATE INDEX IF NOT EXISTS idx_tr_estado ON analitica.transferencia (estado, fecha_creacion DESC);

-- -----------------------------------------------------------------------------
-- Alertas generadas automáticamente por reglas sobre PostgreSQL
--   La columna `huella` evita duplicar la misma alerta mientras siga abierta.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.alerta (
    id_alerta        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo             varchar(40) NOT NULL,
    severidad        varchar(10) NOT NULL DEFAULT 'MEDIA',
    id_sku           integer REFERENCES operacion.producto(id_sku),
    id_lote          uuid REFERENCES operacion.lote(id_lote),
    id_locacion      integer REFERENCES operacion.locacion(id_locacion),
    mensaje          text NOT NULL,
    detalle          jsonb NOT NULL DEFAULT '{}'::jsonb,
    estado           varchar(20) NOT NULL DEFAULT 'ABIERTA',
    referencia_tipo  varchar(30),
    referencia_id    uuid,
    huella           varchar(120) NOT NULL,
    fecha_generacion timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre     timestamptz,
    CONSTRAINT chk_al_tipo CHECK (tipo IN (
        'LOTE_POR_VENCER', 'LOTE_VENCIDO', 'RIESGO_DE_MERMA', 'SOBREINVENTARIO',
        'RIESGO_DE_FALTANTE', 'REABASTECIMIENTO_REQUERIDO', 'TRANSFERENCIA_SUGERIDA'
    )),
    CONSTRAINT chk_al_severidad CHECK (severidad IN ('CRITICA', 'ALTA', 'MEDIA', 'BAJA')),
    CONSTRAINT chk_al_estado CHECK (estado IN ('ABIERTA', 'ATENDIDA', 'DESCARTADA'))
);

CREATE INDEX IF NOT EXISTS idx_al_estado ON analitica.alerta (estado, severidad, fecha_generacion DESC);
CREATE INDEX IF NOT EXISTS idx_al_tipo   ON analitica.alerta (tipo);
CREATE UNIQUE INDEX IF NOT EXISTS uq_alerta_abierta
    ON analitica.alerta (huella) WHERE estado = 'ABIERTA';

-- -----------------------------------------------------------------------------
-- Descuentos sugeridos para lotes próximos a vencer (requieren aprobación)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.descuento (
    id_descuento        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_lote             uuid    NOT NULL REFERENCES operacion.lote(id_lote),
    id_locacion         integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    descuento_pct       numeric(5,2) NOT NULL,
    precio_normal       numeric(12,2) NOT NULL,
    precio_nuevo        numeric(12,2) NOT NULL,
    cantidad            numeric(12,2) NOT NULL,
    dias_restantes      integer,
    ingreso_potencial   numeric(14,2),
    estado              varchar(20) NOT NULL DEFAULT 'SUGERIDO',
    id_usuario_solicita uuid REFERENCES operacion.usuario(id_usuario),
    id_usuario_aprueba  uuid REFERENCES operacion.usuario(id_usuario),
    fecha_creacion      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_decision      timestamptz,
    CONSTRAINT chk_dc_estado CHECK (estado IN (
        'SUGERIDO', 'APROBADO', 'RECHAZADO', 'APLICADO'
    )),
    CONSTRAINT chk_dc_pct CHECK (descuento_pct > 0 AND descuento_pct < 100)
);

-- -----------------------------------------------------------------------------
-- Desperdicio evitado — metodología explícita y auditable
--
--   1. Riesgo estimado inicial      : unidades que iban a vencer sin intervención
--   2. Intervención                 : transferencia o descuento aprobado
--   3. Recuperado                    : unidades vendidas antes de vencer
--   4. Merma residual                : unidades que igualmente se perdieron
--
--   desperdicio_evitado = cantidad_recuperada
--   tasa_recuperacion   = cantidad_recuperada / cantidad_en_riesgo
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.desperdicio_evitado (
    id_registro           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tipo_intervencion     varchar(20) NOT NULL,
    id_transferencia      uuid REFERENCES analitica.transferencia(id_transferencia),
    id_descuento          uuid REFERENCES analitica.descuento(id_descuento),
    id_lote               uuid NOT NULL REFERENCES operacion.lote(id_lote),
    id_locacion           integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    cantidad_en_riesgo    numeric(12,2) NOT NULL DEFAULT 0,
    cantidad_intervenida  numeric(12,2) NOT NULL DEFAULT 0,
    cantidad_recuperada   numeric(12,2) NOT NULL DEFAULT 0,
    cantidad_mermada      numeric(12,2) NOT NULL DEFAULT 0,
    valor_recuperado      numeric(14,2) NOT NULL DEFAULT 0,
    metodologia           text NOT NULL,
    fecha_registro        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_de_tipo CHECK (tipo_intervencion IN ('TRANSFERENCIA', 'DESCUENTO'))
);

CREATE INDEX IF NOT EXISTS idx_de_fecha ON analitica.desperdicio_evitado (fecha_registro DESC);

-- =============================================================================
-- TRIGGERS DE AUDITORÍA sobre el esquema analítico
-- =============================================================================
DROP TRIGGER IF EXISTS trg_aud_orden     ON analitica.orden_reabastecimiento;
DROP TRIGGER IF EXISTS trg_aud_transf    ON analitica.transferencia;
DROP TRIGGER IF EXISTS trg_aud_alerta    ON analitica.alerta;
DROP TRIGGER IF EXISTS trg_aud_descuento ON analitica.descuento;

CREATE TRIGGER trg_aud_orden AFTER INSERT OR UPDATE OR DELETE
    ON analitica.orden_reabastecimiento FOR EACH ROW
    EXECUTE FUNCTION auditoria.fn_registrar_auditoria('REPLENISHMENT');
CREATE TRIGGER trg_aud_transf AFTER INSERT OR UPDATE OR DELETE
    ON analitica.transferencia FOR EACH ROW
    EXECUTE FUNCTION auditoria.fn_registrar_auditoria('TRANSFER');
CREATE TRIGGER trg_aud_alerta AFTER INSERT OR UPDATE OR DELETE
    ON analitica.alerta FOR EACH ROW
    EXECUTE FUNCTION auditoria.fn_registrar_auditoria('ALERT');
CREATE TRIGGER trg_aud_descuento AFTER INSERT OR UPDATE OR DELETE
    ON analitica.descuento FOR EACH ROW
    EXECUTE FUNCTION auditoria.fn_registrar_auditoria('DISCOUNT');

-- =============================================================================
-- PERMISOS
-- =============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA analitica TO app_backend;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analitica TO app_backend;
        ALTER DEFAULT PRIVILEGES IN SCHEMA analitica
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_etl') THEN
        GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA analitica TO app_etl;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT SELECT ON ALL TABLES IN SCHEMA analitica TO app_auditor;
    END IF;
END
$$;
