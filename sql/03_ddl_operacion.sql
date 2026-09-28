-- =============================================================================
-- 03_ddl_operacion.sql — Esquema transaccional de FreshTrack
--
-- Cubre lo que exige la rúbrica del Avance 2:
--   * catálogos con estado activo/inactivo (producto, proveedor, locación)
--   * proveedor con lead time y pedido mínimo (MOQ)
--   * producto con categoría, precios, unidad, stock de seguridad y punto de reorden
--   * reglas de clasificación de riesgo configurables por categoría o por SKU
--   * lote con fecha de producción, recepción, caducidad, cantidad recibida,
--     costo unitario y estado
--   * existencia por lote + locación (inventario real, no agregados)
--   * kardex de movimientos de inventario (trazabilidad completa)
--   * venta (cabecera) + venta_detalle (líneas con lote) → Venta/Tienda/Producto/
--     Cantidad/Fecha, insumo real del pronóstico
--   * merma con las 7 causas exigidas, valorizada
--   * usuario con correo, password_hash, rol y estado
--   * sesión de usuario (respalda el JWT y permite revocarlo en el logout)
--
-- Depende de 02_ddl_auditoria.sql (funciones de auditoría).
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS operacion;

-- -----------------------------------------------------------------------------
-- Roles del sistema
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.rol (
    id_rol       integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre_rol   varchar(50) NOT NULL UNIQUE,
    clave        varchar(30) NOT NULL UNIQUE,   -- admin | buyer | planner | ...
    descripcion  text
);

COMMENT ON COLUMN operacion.rol.clave IS
    'Identificador estable usado por la aplicación para resolver permisos.';

-- -----------------------------------------------------------------------------
-- Locaciones: tiendas y CEDIS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.locacion (
    id_locacion    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo_locacion  varchar(20)  NOT NULL,
    nombre         varchar(120) NOT NULL UNIQUE,
    ciudad         varchar(80),
    direccion      varchar(200),
    activo         boolean NOT NULL DEFAULT true,
    fecha_alta     timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_tipo_locacion CHECK (tipo_locacion IN ('Tienda', 'CEDIS'))
);

-- -----------------------------------------------------------------------------
-- Proveedores
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.proveedor (
    id_proveedor    integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rfc             varchar(13)  NOT NULL UNIQUE,
    razon_social    varchar(150) NOT NULL,
    lead_time_dias  integer      NOT NULL DEFAULT 3,
    moq             numeric(12,2) NOT NULL DEFAULT 1,   -- pedido mínimo
    contacto_email  varchar(150),
    telefono        varchar(30),
    activo          boolean      NOT NULL DEFAULT true,
    fecha_alta      timestamptz  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_lead_time CHECK (lead_time_dias >= 0),
    CONSTRAINT chk_moq       CHECK (moq > 0)
);

COMMENT ON COLUMN operacion.proveedor.lead_time_dias IS
    'Días de suministro. El motor de reabastecimiento cubre la demanda de ese periodo.';
COMMENT ON COLUMN operacion.proveedor.moq IS
    'Minimum Order Quantity: pedido mínimo que acepta el proveedor.';

-- -----------------------------------------------------------------------------
-- Productos (SKU)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.producto (
    id_sku               integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_gtin          varchar(14)  NOT NULL UNIQUE,
    nombre               varchar(150) NOT NULL,
    id_proveedor         integer      REFERENCES operacion.proveedor(id_proveedor),
    categoria            varchar(60)  NOT NULL DEFAULT 'Abarrotes',
    vida_util_estandar   integer      NOT NULL,
    unidad_medida        varchar(20)  NOT NULL DEFAULT 'Pieza',
    precio_costo         numeric(12,2) NOT NULL DEFAULT 0,
    precio_venta         numeric(12,2) NOT NULL DEFAULT 0,
    stock_seguridad      numeric(12,2) NOT NULL DEFAULT 0,
    punto_reorden        numeric(12,2) NOT NULL DEFAULT 0,
    perecedero           boolean      NOT NULL DEFAULT true,
    activo               boolean      NOT NULL DEFAULT true,
    fecha_alta           timestamptz  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_vida_util     CHECK (vida_util_estandar > 0),
    CONSTRAINT chk_precio_venta  CHECK (precio_venta >= 0),
    CONSTRAINT chk_precio_costo  CHECK (precio_costo >= 0)
);

CREATE INDEX IF NOT EXISTS idx_producto_activo    ON operacion.producto (activo);
CREATE INDEX IF NOT EXISTS idx_producto_categoria ON operacion.producto (categoria);

-- -----------------------------------------------------------------------------
-- Reglas de clasificación de riesgo de vencimiento
--
-- Umbrales DOCUMENTADOS y CONFIGURABLES por categoría o por SKU concreto.
-- La resolución es: regla del SKU → regla de la categoría → regla por defecto.
--
-- Clasificación resultante (ver 06_views.sql → operacion.fn_clasificar_riesgo):
--   VENCIDO    : días restantes < 0
--   CRÍTICO    : días restantes <= dias_critico  OR  vida residual % <= pct_critico
--   VIGILANCIA : días restantes <= dias_vigilancia OR vida residual % <= pct_vigilancia
--   NORMAL     : en cualquier otro caso
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.regla_riesgo (
    id_regla          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_sku            integer REFERENCES operacion.producto(id_sku) ON DELETE CASCADE,
    categoria         varchar(60),
    dias_vigilancia   integer NOT NULL DEFAULT 5,
    dias_critico      integer NOT NULL DEFAULT 2,
    pct_vigilancia    numeric(5,2) NOT NULL DEFAULT 30.00,
    pct_critico       numeric(5,2) NOT NULL DEFAULT 10.00,
    es_default        boolean NOT NULL DEFAULT false,
    descripcion       text,
    CONSTRAINT chk_regla_alcance CHECK (id_sku IS NOT NULL OR categoria IS NOT NULL OR es_default),
    CONSTRAINT chk_regla_orden   CHECK (dias_critico <= dias_vigilancia)
);

-- Una sola regla por alcance. Sin estos índices, volver a ejecutar la carga
-- base duplicaba las reglas (y «ganaba» la última insertada, que no es
-- necesariamente la que el administrador configuró).
CREATE UNIQUE INDEX IF NOT EXISTS uq_regla_categoria
    ON operacion.regla_riesgo (categoria) WHERE categoria IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_regla_sku
    ON operacion.regla_riesgo (id_sku) WHERE id_sku IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_regla_default
    ON operacion.regla_riesgo (es_default) WHERE es_default;

-- -----------------------------------------------------------------------------
-- Usuarios
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.usuario (
    id_usuario          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_rol              integer NOT NULL REFERENCES operacion.rol(id_rol),
    id_locacion         integer REFERENCES operacion.locacion(id_locacion),
    nombre_completo     varchar(150) NOT NULL,
    email               varchar(255) NOT NULL UNIQUE,
    password_hash       text NOT NULL,
    estado_activo       boolean NOT NULL DEFAULT true,
    intentos_fallidos   integer NOT NULL DEFAULT 0,
    bloqueado_hasta     timestamptz,
    ultimo_acceso       timestamptz,
    fecha_alta          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_email_formato CHECK (email LIKE '%_@_%._%')
);

CREATE INDEX IF NOT EXISTS idx_usuario_email ON operacion.usuario (lower(email));

COMMENT ON COLUMN operacion.usuario.password_hash IS
    'Hash bcrypt generado con pgcrypto (crypt + gen_salt(''bf'')). Nunca texto plano.';

-- -----------------------------------------------------------------------------
-- Sesiones (respalda el JWT y permite revocarlo en el logout)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.sesion_usuario (
    id_sesion    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_usuario   uuid NOT NULL REFERENCES operacion.usuario(id_usuario) ON DELETE CASCADE,
    jti          varchar(64) NOT NULL UNIQUE,
    emitido_en   timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_en    timestamptz NOT NULL,
    revocado     boolean NOT NULL DEFAULT false,
    revocado_en  timestamptz,
    ip           inet,
    user_agent   text
);

CREATE INDEX IF NOT EXISTS idx_sesion_usuario ON operacion.sesion_usuario (id_usuario, revocado);

-- -----------------------------------------------------------------------------
-- Lotes — núcleo de FreshTrack
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.lote (
    id_lote              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_sku               integer NOT NULL REFERENCES operacion.producto(id_sku),
    id_proveedor         integer NOT NULL REFERENCES operacion.proveedor(id_proveedor),
    codigo_lote_prov     varchar(50) NOT NULL,
    fecha_produccion     date,
    fecha_recepcion      date NOT NULL DEFAULT CURRENT_DATE,
    fecha_caducidad      date NOT NULL,
    cantidad_recibida    numeric(12,2) NOT NULL DEFAULT 0,
    costo_unitario       numeric(12,2) NOT NULL DEFAULT 0,
    id_locacion_recepcion integer REFERENCES operacion.locacion(id_locacion),
    estado               varchar(20) NOT NULL DEFAULT 'DISPONIBLE',
    observaciones        text,
    creado_en            timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_lote_fechas CHECK (fecha_caducidad > fecha_recepcion),
    CONSTRAINT chk_lote_prod   CHECK (fecha_produccion IS NULL OR fecha_produccion <= fecha_recepcion),
    CONSTRAINT chk_lote_cant   CHECK (cantidad_recibida >= 0),
    CONSTRAINT chk_lote_estado CHECK (
        estado IN ('DISPONIBLE', 'AGOTADO', 'VENCIDO', 'MERMA', 'BLOQUEADO')
    ),
    CONSTRAINT uq_lote_proveedor UNIQUE (id_proveedor, codigo_lote_prov)
);

CREATE INDEX IF NOT EXISTS idx_lote_caducidad ON operacion.lote (fecha_caducidad);
CREATE INDEX IF NOT EXISTS idx_lote_sku       ON operacion.lote (id_sku, fecha_caducidad);
CREATE INDEX IF NOT EXISTS idx_lote_estado    ON operacion.lote (estado);

COMMENT ON TABLE operacion.lote IS
    'Un lote es la unidad de trazabilidad. La vida útil residual y el riesgo de vencimiento se calculan a partir de fecha_caducidad y fecha_produccion, nunca se almacenan precalculados.';

-- -----------------------------------------------------------------------------
-- Existencias — inventario real por lote y locación
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.existencia (
    id_existencia       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_lote             uuid    NOT NULL REFERENCES operacion.lote(id_lote) ON DELETE RESTRICT,
    id_locacion         integer NOT NULL REFERENCES operacion.locacion(id_locacion) ON DELETE RESTRICT,
    cantidad_disponible numeric(12,2) NOT NULL DEFAULT 0,
    cantidad_reservada  numeric(12,2) NOT NULL DEFAULT 0,
    actualizado_en      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cantidad_disponible CHECK (cantidad_disponible >= 0),
    CONSTRAINT chk_cantidad_reservada  CHECK (cantidad_reservada >= 0),
    CONSTRAINT uq_existencia_lote_loc  UNIQUE (id_lote, id_locacion)
);

CREATE INDEX IF NOT EXISTS idx_existencia_lote      ON operacion.existencia (id_lote);
CREATE INDEX IF NOT EXISTS idx_existencia_locacion  ON operacion.existencia (id_locacion);
CREATE INDEX IF NOT EXISTS idx_existencia_disponible ON operacion.existencia (id_locacion, cantidad_disponible)
    WHERE cantidad_disponible > 0;

-- -----------------------------------------------------------------------------
-- Kardex: todo movimiento de inventario queda registrado
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.movimiento_inventario (
    id_movimiento        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_lote              uuid    NOT NULL REFERENCES operacion.lote(id_lote) ON DELETE RESTRICT,
    id_locacion          integer NOT NULL REFERENCES operacion.locacion(id_locacion) ON DELETE RESTRICT,
    tipo                 varchar(30) NOT NULL,
    cantidad             numeric(12,2) NOT NULL,   -- + entrada / − salida
    cantidad_resultante  numeric(12,2) NOT NULL,
    costo_unitario       numeric(12,2) NOT NULL DEFAULT 0,
    referencia_tipo      varchar(30),
    referencia_id        uuid,
    id_usuario           uuid REFERENCES operacion.usuario(id_usuario),
    fecha                timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_mov_tipo CHECK (tipo IN (
        'RECEPCION', 'VENTA', 'MERMA', 'TRANSFERENCIA_SALIDA',
        'TRANSFERENCIA_ENTRADA', 'AJUSTE', 'VENCIMIENTO'
    ))
);

CREATE INDEX IF NOT EXISTS idx_mov_lote    ON operacion.movimiento_inventario (id_lote, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_mov_fecha   ON operacion.movimiento_inventario (fecha DESC);
CREATE INDEX IF NOT EXISTS idx_mov_tipo    ON operacion.movimiento_inventario (tipo, fecha DESC);

-- -----------------------------------------------------------------------------
-- Ventas
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.venta (
    id_venta    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    folio       varchar(30) NOT NULL UNIQUE,
    id_locacion integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    id_usuario  uuid REFERENCES operacion.usuario(id_usuario),
    canal       varchar(20) NOT NULL DEFAULT 'TIENDA',
    total       numeric(14,2) NOT NULL DEFAULT 0,
    fecha_venta timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_canal CHECK (canal IN ('TIENDA', 'ONLINE', 'MAYOREO'))
);

CREATE INDEX IF NOT EXISTS idx_venta_fecha    ON operacion.venta (fecha_venta DESC);
CREATE INDEX IF NOT EXISTS idx_venta_locacion ON operacion.venta (id_locacion, fecha_venta DESC);

CREATE TABLE IF NOT EXISTS operacion.venta_detalle (
    id_detalle        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_venta          uuid    NOT NULL REFERENCES operacion.venta(id_venta) ON DELETE CASCADE,
    id_sku            integer NOT NULL REFERENCES operacion.producto(id_sku),
    id_lote           uuid REFERENCES operacion.lote(id_lote),
    id_locacion       integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    cantidad          numeric(12,2) NOT NULL,
    precio_unitario   numeric(12,2) NOT NULL DEFAULT 0,
    subtotal          numeric(14,2) NOT NULL DEFAULT 0,
    fecha_transaccion timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cantidad_venta CHECK (cantidad > 0)
);

-- Índice clave para el pronóstico: serie Venta → Tienda → Producto → Fecha
CREATE INDEX IF NOT EXISTS idx_vd_serie ON operacion.venta_detalle (id_sku, id_locacion, fecha_transaccion);
CREATE INDEX IF NOT EXISTS idx_vd_fecha ON operacion.venta_detalle (fecha_transaccion DESC);
CREATE INDEX IF NOT EXISTS idx_vd_lote  ON operacion.venta_detalle (id_lote);

-- -----------------------------------------------------------------------------
-- Mermas
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operacion.merma (
    id_merma        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_lote         uuid    NOT NULL REFERENCES operacion.lote(id_lote) ON DELETE RESTRICT,
    id_locacion     integer NOT NULL REFERENCES operacion.locacion(id_locacion),
    id_usuario      uuid    NOT NULL REFERENCES operacion.usuario(id_usuario),
    cantidad        numeric(12,2) NOT NULL,
    causa_merma     varchar(30) NOT NULL,
    costo_unitario  numeric(12,2) NOT NULL DEFAULT 0,
    valor_merma     numeric(14,2) GENERATED ALWAYS AS (cantidad * costo_unitario) STORED,
    observacion     text,
    fecha_registro  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cantidad_merma CHECK (cantidad > 0),
    CONSTRAINT chk_causa_merma CHECK (causa_merma IN (
        'CADUCIDAD', 'DANO', 'CALIDAD', 'CADENA_DE_FRIO',
        'MANIPULACION', 'DEVOLUCION', 'OTRA'
    ))
);

CREATE INDEX IF NOT EXISTS idx_merma_fecha   ON operacion.merma (fecha_registro DESC);
CREATE INDEX IF NOT EXISTS idx_merma_causa   ON operacion.merma (causa_merma);
CREATE INDEX IF NOT EXISTS idx_merma_lote    ON operacion.merma (id_lote);
CREATE INDEX IF NOT EXISTS idx_merma_locacion ON operacion.merma (id_locacion);

-- =============================================================================
-- TRIGGERS DE AUDITORÍA
-- El argumento del trigger define el nombre de la acción:
--   CREATE_PRODUCT, UPDATE_PRODUCT, CREATE_BATCH, CREATE_SALE,
--   CREATE_SHRINKAGE, CREATE_USER, ...
-- =============================================================================
DROP TRIGGER IF EXISTS trg_aud_producto   ON operacion.producto;
DROP TRIGGER IF EXISTS trg_aud_proveedor  ON operacion.proveedor;
DROP TRIGGER IF EXISTS trg_aud_locacion   ON operacion.locacion;
DROP TRIGGER IF EXISTS trg_aud_lote       ON operacion.lote;
DROP TRIGGER IF EXISTS trg_aud_existencia ON operacion.existencia;
DROP TRIGGER IF EXISTS trg_aud_venta      ON operacion.venta;
DROP TRIGGER IF EXISTS trg_aud_venta_det  ON operacion.venta_detalle;
DROP TRIGGER IF EXISTS trg_aud_merma      ON operacion.merma;
DROP TRIGGER IF EXISTS trg_aud_usuario    ON operacion.usuario;

CREATE TRIGGER trg_aud_producto   AFTER INSERT OR UPDATE OR DELETE ON operacion.producto
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('PRODUCT');
CREATE TRIGGER trg_aud_proveedor  AFTER INSERT OR UPDATE OR DELETE ON operacion.proveedor
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('SUPPLIER');
CREATE TRIGGER trg_aud_locacion   AFTER INSERT OR UPDATE OR DELETE ON operacion.locacion
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('LOCATION');
CREATE TRIGGER trg_aud_lote       AFTER INSERT OR UPDATE OR DELETE ON operacion.lote
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('BATCH');
CREATE TRIGGER trg_aud_existencia AFTER INSERT OR UPDATE OR DELETE ON operacion.existencia
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('INVENTORY');
CREATE TRIGGER trg_aud_venta      AFTER INSERT OR UPDATE OR DELETE ON operacion.venta
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('SALE');
CREATE TRIGGER trg_aud_venta_det  AFTER INSERT OR UPDATE OR DELETE ON operacion.venta_detalle
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('SALE_LINE');
CREATE TRIGGER trg_aud_merma      AFTER INSERT OR UPDATE OR DELETE ON operacion.merma
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('SHRINKAGE');
CREATE TRIGGER trg_aud_usuario    AFTER INSERT OR UPDATE OR DELETE ON operacion.usuario
    FOR EACH ROW EXECUTE FUNCTION auditoria.fn_registrar_auditoria('USER');

-- =============================================================================
-- PERMISOS
-- =============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA operacion TO app_backend;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA operacion TO app_backend;
        ALTER DEFAULT PRIVILEGES IN SCHEMA operacion
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_backend;
        ALTER DEFAULT PRIVILEGES IN SCHEMA operacion
            GRANT USAGE, SELECT ON SEQUENCES TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_etl') THEN
        GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA operacion TO app_etl;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA operacion TO app_etl;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT SELECT ON ALL TABLES IN SCHEMA operacion TO app_auditor;
    END IF;
END
$$;
