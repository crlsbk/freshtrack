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
    id_locacion      integer REFERENCES operacion.locacion(id_locacion),
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
    sesgo            numeric(12,4),
    naive_mae        numeric(12,4),
    naive_wmape      numeric(8,4),
    observaciones    text,
    CONSTRAINT chk_fc_metodo CHECK (metodo IN (
        'AUTO', 'ETS_HOLT_WINTERS', 'MEDIA_MOVIL', 'MEDIA_MOVIL_PONDERADA', 'SUAVIZACION_EXPONENCIAL'
    )),
    CONSTRAINT chk_fc_horizonte CHECK (horizonte_dias BETWEEN 1 AND 90),
    CONSTRAINT chk_fc_estado CHECK (estado IN ('COMPLETADO', 'ERROR', 'PARCIAL'))
);

ALTER TABLE analitica.forecast_run
    ADD COLUMN IF NOT EXISTS id_locacion    integer REFERENCES operacion.locacion(id_locacion),
    ADD COLUMN IF NOT EXISTS sesgo          numeric(12,4),
    ADD COLUMN IF NOT EXISTS naive_mae      numeric(12,4),
    ADD COLUMN IF NOT EXISTS naive_wmape    numeric(8,4),
    ADD COLUMN IF NOT EXISTS proposito      varchar(20) NOT NULL DEFAULT 'PRODUCCION',
    ADD COLUMN IF NOT EXISTS id_experimento uuid;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_fc_metodo') THEN
        ALTER TABLE analitica.forecast_run DROP CONSTRAINT chk_fc_metodo;
    END IF;
    ALTER TABLE analitica.forecast_run
        ADD CONSTRAINT chk_fc_metodo CHECK (metodo IN (
            'AUTO', 'ETS_HOLT_WINTERS', 'MEDIA_MOVIL', 'MEDIA_MOVIL_PONDERADA', 'SUAVIZACION_EXPONENCIAL'
        ));
END
$$;

CREATE INDEX IF NOT EXISTS idx_fcrun_fecha ON analitica.forecast_run (fecha_ejecucion DESC);
CREATE INDEX IF NOT EXISTS idx_fcrun_loc_fecha ON analitica.forecast_run (id_locacion, fecha_ejecucion DESC);

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
    desviacion_std        numeric(12,4),
    modelo_aplicado       varchar(40),
    id_experimento        uuid,
    grupo_ab              varchar(20),
    demanda_real          numeric(12,2),
    error_absoluto        numeric(12,2),
    CONSTRAINT uq_fc_resultado UNIQUE (id_run, id_sku, id_locacion, fecha_objetivo)
);

ALTER TABLE analitica.forecast_result
    ADD COLUMN IF NOT EXISTS desviacion_std  numeric(12,4),
    ADD COLUMN IF NOT EXISTS modelo_aplicado varchar(40),
    ADD COLUMN IF NOT EXISTS id_experimento  uuid,
    ADD COLUMN IF NOT EXISTS grupo_ab        varchar(20);

CREATE INDEX IF NOT EXISTS idx_fcres_serie ON analitica.forecast_result (id_sku, id_locacion, fecha_objetivo);
CREATE INDEX IF NOT EXISTS idx_fcres_run   ON analitica.forecast_result (id_run);

-- -----------------------------------------------------------------------------
-- Gobernanza de modelos: Campeón en producción y Retador de laboratorio
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.modelo_produccion (
    id_config        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_locacion      integer REFERENCES operacion.locacion(id_locacion),
    categoria        varchar(80),
    rol_modelo       varchar(20) NOT NULL,
    metodo           varchar(40) NOT NULL,
    parametros       jsonb NOT NULL DEFAULT '{}'::jsonb,
    metricas_lab     jsonb NOT NULL DEFAULT '{}'::jsonb,
    activo           boolean NOT NULL DEFAULT true,
    promovido_por    uuid REFERENCES operacion.usuario(id_usuario),
    fecha_promocion  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_mp_rol CHECK (rol_modelo IN ('CAMPEON', 'RETADOR'))
);

CREATE INDEX IF NOT EXISTS idx_mp_activo
    ON analitica.modelo_produccion (rol_modelo, activo, fecha_promocion DESC);

INSERT INTO analitica.modelo_produccion (id_locacion, categoria, rol_modelo, metodo, parametros, metricas_lab, activo)
SELECT NULL, NULL, 'CAMPEON', 'AUTO', '{"horizonte": 7, "ventana": 28, "alpha": 0.30}'::jsonb, '{}'::jsonb, true
WHERE NOT EXISTS (
    SELECT 1 FROM analitica.modelo_produccion
    WHERE rol_modelo = 'CAMPEON' AND id_locacion IS NULL AND categoria IS NULL AND activo = true
);

-- -----------------------------------------------------------------------------
-- Experimentos A/B (Control vs. Tratamiento con bitácora diaria auditable)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.experimento_ab (
    id_experimento       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre               varchar(140) NOT NULL,
    estado               varchar(20) NOT NULL DEFAULT 'ACTIVO',
    categoria            varchar(80),
    horizonte_dias       integer NOT NULL DEFAULT 7,
    modelo_campeon       varchar(40) NOT NULL,
    parametros_campeon   jsonb NOT NULL DEFAULT '{}'::jsonb,
    modelo_retador       varchar(40) NOT NULL,
    parametros_retador   jsonb NOT NULL DEFAULT '{}'::jsonb,
    fecha_inicio         date NOT NULL DEFAULT CURRENT_DATE,
    duracion_dias        integer NOT NULL DEFAULT 21,
    fecha_fin_estimada   date NOT NULL,
    fecha_cierre         timestamptz,
    decision_final       varchar(20),
    notas_decision       text,
    id_usuario_crea      uuid REFERENCES operacion.usuario(id_usuario),
    id_usuario_decide    uuid REFERENCES operacion.usuario(id_usuario),
    creado_en            timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_ab_estado CHECK (estado IN ('ACTIVO', 'PROMOVIDO', 'DESCARTADO')),
    CONSTRAINT chk_ab_duracion CHECK (duracion_dias BETWEEN 3 AND 90)
);

CREATE INDEX IF NOT EXISTS idx_ab_estado
    ON analitica.experimento_ab (estado, creado_en DESC);

CREATE TABLE IF NOT EXISTS analitica.experimento_ab_asignacion (
    id_experimento  uuid    NOT NULL REFERENCES analitica.experimento_ab(id_experimento) ON DELETE CASCADE,
    id_locacion     integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    grupo           varchar(20) NOT NULL,
    modelo_asignado varchar(40) NOT NULL,
    PRIMARY KEY (id_experimento, id_locacion),
    CONSTRAINT chk_aba_grupo CHECK (grupo IN ('CONTROL', 'TRATAMIENTO'))
);

CREATE TABLE IF NOT EXISTS analitica.experimento_ab_bitacora (
    id_registro          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_experimento       uuid    NOT NULL REFERENCES analitica.experimento_ab(id_experimento) ON DELETE CASCADE,
    fecha                date    NOT NULL,
    id_locacion          integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    id_sku               integer NOT NULL REFERENCES operacion.producto(id_sku),
    grupo                varchar(20) NOT NULL,
    id_run               uuid REFERENCES analitica.forecast_run(id_run) ON DELETE SET NULL,
    modelo_usado         varchar(40) NOT NULL,
    demanda_media        numeric(12,2) NOT NULL DEFAULT 0,
    desviacion_std       numeric(12,4) NOT NULL DEFAULT 0,
    demanda_real         numeric(12,2),
    error_absoluto       numeric(12,2),
    ventas_reales_valor  numeric(14,2) NOT NULL DEFAULT 0,
    merma_real_unidades  numeric(12,2) NOT NULL DEFAULT 0,
    merma_real_valor     numeric(14,2) NOT NULL DEFAULT 0,
    CONSTRAINT uq_ab_bitacora UNIQUE (id_experimento, fecha, id_locacion, id_sku)
);

CREATE INDEX IF NOT EXISTS idx_ab_bit_exp_fecha
    ON analitica.experimento_ab_bitacora (id_experimento, fecha, grupo);

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
    entradas_traslados    numeric(12,2) NOT NULL DEFAULT 0,
    stock_seguridad       numeric(12,2) NOT NULL DEFAULT 0,
    lead_time_dias        integer NOT NULL DEFAULT 0,
    moq                   numeric(12,2) NOT NULL DEFAULT 1,
    necesidad_neta        numeric(12,2) NOT NULL DEFAULT 0,
    cantidad_sugerida     numeric(12,2) NOT NULL DEFAULT 0,
    cantidad_aprobada     numeric(12,2),
    costo_faltante        numeric(12,2),
    costo_excedente       numeric(12,2),
    fractil_critico       numeric(6,4),
    cantidad_newsvendor   numeric(12,2),
    cantidad_politica_simple numeric(12,2),
    ahorro_esperado       numeric(12,2),
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

ALTER TABLE analitica.orden_reabastecimiento
    ADD COLUMN IF NOT EXISTS entradas_traslados numeric(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS costo_faltante numeric(12,2),
    ADD COLUMN IF NOT EXISTS costo_excedente numeric(12,2),
    ADD COLUMN IF NOT EXISTS fractil_critico numeric(6,4),
    ADD COLUMN IF NOT EXISTS cantidad_newsvendor numeric(12,2),
    ADD COLUMN IF NOT EXISTS cantidad_politica_simple numeric(12,2),
    ADD COLUMN IF NOT EXISTS ahorro_esperado numeric(12,2);

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
        'RIESGO_DE_FALTANTE', 'REABASTECIMIENTO_REQUERIDO', 'TRANSFERENCIA_SUGERIDA',
        'DERIVA_DEMANDA'
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
    demanda_base_contrafactual numeric(12,2) NOT NULL DEFAULT 0,
    desperdicio_proyectado     numeric(12,2) NOT NULL DEFAULT 0,
    desperdicio_evitado_neto   numeric(12,2) NOT NULL DEFAULT 0,
    metodologia           text NOT NULL,
    fecha_registro        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_de_tipo CHECK (tipo_intervencion IN ('TRANSFERENCIA', 'DESCUENTO'))
);

ALTER TABLE analitica.desperdicio_evitado
    ADD COLUMN IF NOT EXISTS demanda_base_contrafactual numeric(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS desperdicio_proyectado     numeric(12,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS desperdicio_evitado_neto   numeric(12,2) NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_de_fecha ON analitica.desperdicio_evitado (fecha_registro DESC);

-- Referencia cruzada desde operacion.orden_compra_detalle hacia analitica.orden_reabastecimiento
-- (se agrega aquí porque 03_ddl_operacion.sql corre antes de crear el esquema analitica).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_ocd_orden_reabastecimiento'
    ) THEN
        ALTER TABLE operacion.orden_compra_detalle
            ADD CONSTRAINT fk_ocd_orden_reabastecimiento
            FOREIGN KEY (id_orden_reabastecimiento)
            REFERENCES analitica.orden_reabastecimiento(id_orden)
            ON DELETE SET NULL;
    END IF;
END
$$;

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
