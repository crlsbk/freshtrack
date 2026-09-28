-- =============================================================================
-- 05_funciones_negocio.sql — Reglas de negocio ejecutadas en la base
--
-- Aquí vive la lógica que NO debe venir precalculada desde ningún mock:
--   * vida útil residual (%) de cada lote
--   * clasificación automática de riesgo: NORMAL / VIGILANCIA / CRÍTICO / VENCIDO
--   * resolución de umbrales configurables por SKU → categoría → default
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Resuelve la regla de riesgo aplicable.
-- Precedencia: regla específica del SKU → regla de la categoría → regla default.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION operacion.fn_resolver_regla_riesgo(
    p_id_sku    integer,
    p_categoria varchar
) RETURNS TABLE (
    dias_vigilancia integer,
    dias_critico    integer,
    pct_vigilancia  numeric,
    pct_critico     numeric,
    origen          text
)
LANGUAGE sql
STABLE
AS $$
    WITH candidatas AS (
        SELECT r.dias_vigilancia, r.dias_critico, r.pct_vigilancia, r.pct_critico,
               CASE
                   WHEN r.id_sku IS NOT NULL        THEN 1
                   WHEN r.categoria IS NOT NULL     THEN 2
                   ELSE 3
               END AS prioridad,
               CASE
                   WHEN r.id_sku IS NOT NULL        THEN 'SKU'
                   WHEN r.categoria IS NOT NULL     THEN 'CATEGORIA'
                   ELSE 'DEFAULT'
               END AS origen_txt
        FROM operacion.regla_riesgo r
        WHERE (r.id_sku IS NOT NULL AND r.id_sku = p_id_sku)
           OR (r.categoria IS NOT NULL AND lower(r.categoria) = lower(COALESCE(p_categoria, '')))
           OR (r.es_default)
    )
    SELECT c.dias_vigilancia, c.dias_critico, c.pct_vigilancia, c.pct_critico, c.origen_txt
    FROM candidatas c
    ORDER BY c.prioridad
    LIMIT 1;
$$;

COMMENT ON FUNCTION operacion.fn_resolver_regla_riesgo IS
    'Devuelve los umbrales de riesgo aplicables. Precedencia: SKU > categoría > default.';

-- -----------------------------------------------------------------------------
-- Vida útil residual (%) = días restantes / vida total del lote
--   La vida total se toma de (fecha_caducidad − fecha_produccion) cuando existe;
--   si no, se usa la vida útil estándar del producto.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION operacion.fn_vida_util_pct(
    p_dias_restantes numeric,
    p_vida_total     numeric
) RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_vida_total IS NULL OR p_vida_total <= 0 THEN 0::numeric
        WHEN p_dias_restantes IS NULL                  THEN 0::numeric
        ELSE round(
            GREATEST(0::numeric, LEAST(100::numeric, (p_dias_restantes / p_vida_total) * 100))
        , 2)
    END;
$$;

-- -----------------------------------------------------------------------------
-- Clasificación automática de riesgo
--   VENCIDO    : días restantes < 0
--   CRÍTICO    : días restantes <= dias_critico    OR vida residual % <= pct_critico
--   VIGILANCIA : días restantes <= dias_vigilancia OR vida residual % <= pct_vigilancia
--   NORMAL     : resto
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION operacion.fn_clasificar_riesgo(
    p_id_sku          integer,
    p_categoria       varchar,
    p_dias_restantes  numeric,
    p_vida_util_pct   numeric
) RETURNS varchar
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    r record;
BEGIN
    IF p_dias_restantes IS NULL THEN
        RETURN 'SIN_DATO';
    END IF;

    IF p_dias_restantes < 0 THEN
        RETURN 'VENCIDO';
    END IF;

    SELECT * INTO r FROM operacion.fn_resolver_regla_riesgo(p_id_sku, p_categoria);

    IF r IS NULL THEN
        -- Fallback si no hay ninguna regla cargada
        r.dias_vigilancia := 5;
        r.dias_critico    := 2;
        r.pct_vigilancia  := 30;
        r.pct_critico     := 10;
    END IF;

    IF p_dias_restantes <= r.dias_critico
       OR (p_vida_util_pct IS NOT NULL AND p_vida_util_pct <= r.pct_critico) THEN
        RETURN 'CRITICO';
    END IF;

    IF p_dias_restantes <= r.dias_vigilancia
       OR (p_vida_util_pct IS NOT NULL AND p_vida_util_pct <= r.pct_vigilancia) THEN
        RETURN 'VIGILANCIA';
    END IF;

    RETURN 'NORMAL';
END;
$$;

COMMENT ON FUNCTION operacion.fn_clasificar_riesgo IS
    'NORMAL / VIGILANCIA / CRITICO / VENCIDO. Los umbrales salen de operacion.regla_riesgo (configurables por SKU o categoría).';

-- -----------------------------------------------------------------------------
-- Etiqueta legible para la interfaz
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION operacion.fn_etiqueta_riesgo(p_clasificacion varchar)
RETURNS varchar
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE upper(COALESCE(p_clasificacion, ''))
        WHEN 'VENCIDO'    THEN 'Vencido'
        WHEN 'CRITICO'    THEN 'Crítico'
        WHEN 'VIGILANCIA' THEN 'Vigilancia'
        WHEN 'NORMAL'     THEN 'Normal'
        ELSE 'Sin dato'
    END;
$$;

-- -----------------------------------------------------------------------------
-- Folio de venta: VT-<locacion>-<yyyymmdd>-<secuencia>
-- La secuencia garantiza unicidad incluso con ventas concurrentes.
-- -----------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS operacion.seq_folio_venta;

CREATE OR REPLACE FUNCTION operacion.fn_generar_folio_venta(p_id_locacion integer)
RETURNS varchar
LANGUAGE sql
AS $$
    SELECT format(
        'VT-%s-%s-%s',
        p_id_locacion,
        to_char(CURRENT_DATE, 'YYYYMMDD'),
        lpad(nextval('operacion.seq_folio_venta')::text, 6, '0')
    );
$$;

-- -----------------------------------------------------------------------------
-- Configuración tipada
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION analitica.fn_config(p_clave varchar, p_default text DEFAULT NULL)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE((SELECT valor FROM analitica.configuracion WHERE clave = p_clave), p_default);
$$;
