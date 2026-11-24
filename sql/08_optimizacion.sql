-- =============================================================================
-- 08_optimizacion.sql — Rendimiento sobre el dataset masivo (idempotente)
--
-- Se ejecuta en el primer arranque (docker-entrypoint-initdb.d, después de
-- 06_views.sql) y también EN CALIENTE sobre una base ya cargada, sin borrar
-- datos:
--
--   docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
--     sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
--            -f /docker-entrypoint-initdb.d/08_optimizacion.sql'
--
-- Contenido:
--   1. Índices que faltaban para los patrones de consulta reales.
--   2. Demanda diaria histórica materializada (analitica.mv_demanda_diaria_hist)
--      y v_demanda_diaria redefinida como  histórico materializado ∪ hoy en vivo.
--      Mismo nombre y mismas columnas: ningún consumidor cambia.
--   3. fn_refrescar_agregados(): refresco CONCURRENTLY invocable por app_backend.
--   4. ANALYZE.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Índices
-- -----------------------------------------------------------------------------

-- FK venta_detalle → venta (ON DELETE CASCADE) sin índice: cada JOIN por id_venta
-- (ventas en tiempo real, detalle de ticket, trazabilidad) recorría 500k filas.
CREATE INDEX IF NOT EXISTS idx_vd_venta ON operacion.venta_detalle (id_venta);

-- Barrido de caducidad (bloquear_lotes_vencidos) y colas de riesgo.
CREATE INDEX IF NOT EXISTS idx_lote_disp_caducidad
    ON operacion.lote (fecha_caducidad) WHERE estado = 'DISPONIBLE';

-- Conteos por proveedor (/proveedores, /productos) y métricas por fecha de recepción (/mapa).
CREATE INDEX IF NOT EXISTS idx_lote_proveedor ON operacion.lote (id_proveedor);
CREATE INDEX IF NOT EXISTS idx_lote_recepcion ON operacion.lote (fecha_recepcion);

-- Detalle de lote / trazabilidad y búsquedas de descuentos vigentes por lote.
CREATE INDEX IF NOT EXISTS idx_tr_lote ON analitica.transferencia (id_lote);
CREATE INDEX IF NOT EXISTS idx_dc_lote_loc_estado ON analitica.descuento (id_lote, id_locacion, estado);
CREATE INDEX IF NOT EXISTS idx_dc_estado_fecha    ON analitica.descuento (estado, fecha_creacion DESC);

-- Búsqueda libre (?q=) de /auditoria: ILIKE '%texto%' con trigramas.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_bitacora_desc_trgm
    ON auditoria.bitacora_eventos USING gin (descripcion gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_bitacora_email_trgm
    ON auditoria.bitacora_eventos USING gin (usuario_email gin_trgm_ops);
-- El filtro ?q= es  descripcion ILIKE x OR nombre_tabla ILIKE x OR accion ILIKE x:
-- un BitmapOr solo es posible si las TRES columnas tienen índice trigram.
CREATE INDEX IF NOT EXISTS idx_bitacora_tabla_trgm
    ON auditoria.bitacora_eventos USING gin (nombre_tabla gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_bitacora_accion_trgm
    ON auditoria.bitacora_eventos USING gin (accion gin_trgm_ops);

-- Redundantes: duplican un índice único con la misma columna líder y solo
-- encarecen las escrituras masivas.
--   idx_existencia_lote  ⊂ uq (id_lote, id_locacion)
--   idx_fcres_run        ⊂ uq (id_run, id_sku, id_locacion, fecha_objetivo)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'operacion' AND tablename = 'existencia'
          AND indexdef ILIKE 'CREATE UNIQUE INDEX%(id_lote, id_locacion)%'
    ) THEN
        DROP INDEX IF EXISTS operacion.idx_existencia_lote;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'analitica' AND tablename = 'forecast_result'
          AND indexdef ILIKE 'CREATE UNIQUE INDEX%(id_run, id_sku, id_locacion, fecha_objetivo)%'
    ) THEN
        DROP INDEX IF EXISTS analitica.idx_fcres_run;
    END IF;
END
$$;

-- -----------------------------------------------------------------------------
-- 2. Demanda diaria: histórico materializado + día en curso en vivo
--
-- Antes, v_demanda_diaria agrupaba TODO venta_detalle por fecha_transaccion::date;
-- el cast no es indexable, así que cualquier filtro "fecha >= CURRENT_DATE - 28"
-- era un Seq Scan + HashAggregate de ~500k filas (3 veces por generar_alertas).
--
-- Ahora:
--   * mv_demanda_diaria_hist guarda los días cerrados (< CURRENT_DATE) con
--     índice único (id_sku, id_locacion, fecha) e índice por fecha.
--   * v_demanda_diaria = hist  UNION ALL  agregado de las filas con
--     fecha_transaccion >= marca de corte (lo no materializado, típicamente
--     solo hoy; usa idx_vd_fecha).
--
-- La marca de corte se guarda en analitica.agregado_refresco, así que si el
-- refresco nocturno no corre, las filas posteriores siguen apareciendo en vivo.
-- Si alguien inserta/actualiza/borra ventas con fecha ANTERIOR al corte (POS
-- con fecha retroactiva, correcciones), un trigger marca el agregado como
-- "sucio" y la vista vuelve a agregar todo en vivo (correcto, más lento) hasta
-- el siguiente refresco: la vista NUNCA devuelve datos incompletos.
--
-- OJO: ETL.py y generar_dataset_masivo.py usan session_replication_role=replica
-- (no disparan triggers); por eso llaman a fn_refrescar_agregados() al terminar.
-- Cualquier otra carga masiva debe hacer lo mismo.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analitica.agregado_refresco (
    nombre           varchar(60) PRIMARY KEY,
    corte            timestamptz NOT NULL,
    fecha_refresco   timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duracion_ms      integer,
    sucio            boolean NOT NULL DEFAULT false
);
ALTER TABLE analitica.agregado_refresco ADD COLUMN IF NOT EXISTS sucio boolean NOT NULL DEFAULT false;

COMMENT ON TABLE analitica.agregado_refresco IS
    'Marca de corte de cada agregado materializado: lo anterior a "corte" está en la MV; lo posterior se agrega en vivo.';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_matviews
        WHERE schemaname = 'analitica' AND matviewname = 'mv_demanda_diaria_hist'
    ) THEN
        -- La vista actual depende de nada; se reemplaza más abajo.
        EXECUTE $mv$
            CREATE MATERIALIZED VIEW analitica.mv_demanda_diaria_hist AS
            SELECT
                vd.id_sku,
                vd.id_locacion,
                vd.fecha_transaccion::date AS fecha,
                SUM(vd.cantidad)           AS cantidad,
                SUM(vd.subtotal)           AS ingreso
            FROM operacion.venta_detalle vd
            WHERE vd.fecha_transaccion < CURRENT_DATE::timestamptz
            GROUP BY vd.id_sku, vd.id_locacion, vd.fecha_transaccion::date
            WITH DATA
        $mv$;
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mv_demanda_serie
    ON analitica.mv_demanda_diaria_hist (id_sku, id_locacion, fecha);
CREATE INDEX IF NOT EXISTS idx_mv_demanda_fecha
    ON analitica.mv_demanda_diaria_hist (fecha);
CREATE INDEX IF NOT EXISTS idx_mv_demanda_loc_fecha
    ON analitica.mv_demanda_diaria_hist (id_locacion, fecha);

-- Corte inicial = inicio del día en que se creó/refrescó la MV.
INSERT INTO analitica.agregado_refresco (nombre, corte)
VALUES ('mv_demanda_diaria_hist', CURRENT_DATE::timestamptz)
ON CONFLICT (nombre) DO NOTHING;

CREATE OR REPLACE VIEW analitica.v_demanda_diaria AS
WITH r AS (
    SELECT corte, sucio FROM analitica.agregado_refresco
    WHERE nombre = 'mv_demanda_diaria_hist'
)
SELECT h.id_sku, h.id_locacion, h.fecha, h.cantidad, h.ingreso
FROM analitica.mv_demanda_diaria_hist h
WHERE NOT COALESCE((SELECT sucio FROM r), true)
UNION ALL
SELECT
    vd.id_sku,
    vd.id_locacion,
    vd.fecha_transaccion::date AS fecha,
    SUM(vd.cantidad)           AS cantidad,
    SUM(vd.subtotal)           AS ingreso
FROM operacion.venta_detalle vd
WHERE vd.fecha_transaccion >= COALESCE(
    (SELECT CASE WHEN sucio THEN '-infinity'::timestamptz ELSE corte END FROM r),
    '-infinity'::timestamptz
)
GROUP BY vd.id_sku, vd.id_locacion, vd.fecha_transaccion::date;

COMMENT ON VIEW analitica.v_demanda_diaria IS
    'Serie histórica real usada por el motor de pronóstico (agregada por día). '
    'Días cerrados desde mv_demanda_diaria_hist + ventas posteriores al corte en vivo.';

-- Trigger de "suciedad": una escritura de ventas con fecha anterior al corte
-- invalida el histórico materializado hasta el próximo refresco.
CREATE OR REPLACE FUNCTION analitica.fn_marcar_demanda_sucia()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = analitica, operacion, pg_temp
AS $$
DECLARE
    v_corte timestamptz;
    v_hay   boolean := false;
BEGIN
    SELECT corte INTO v_corte FROM analitica.agregado_refresco
    WHERE nombre = 'mv_demanda_diaria_hist' AND NOT sucio;
    IF v_corte IS NULL THEN
        RETURN NULL;  -- ya está sucio (o no existe): nada que hacer
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT EXISTS (SELECT 1 FROM filas_nuevas WHERE fecha_transaccion < v_corte) INTO v_hay;
    END IF;
    IF NOT v_hay AND TG_OP IN ('DELETE', 'UPDATE') THEN
        SELECT EXISTS (SELECT 1 FROM filas_viejas WHERE fecha_transaccion < v_corte) INTO v_hay;
    END IF;
    IF v_hay THEN
        UPDATE analitica.agregado_refresco SET sucio = true
        WHERE nombre = 'mv_demanda_diaria_hist' AND NOT sucio;
    END IF;
    RETURN NULL;
END
$$;

DROP TRIGGER IF EXISTS trg_vd_demanda_sucia_ins ON operacion.venta_detalle;
DROP TRIGGER IF EXISTS trg_vd_demanda_sucia_upd ON operacion.venta_detalle;
DROP TRIGGER IF EXISTS trg_vd_demanda_sucia_del ON operacion.venta_detalle;
CREATE TRIGGER trg_vd_demanda_sucia_ins AFTER INSERT ON operacion.venta_detalle
    REFERENCING NEW TABLE AS filas_nuevas
    FOR EACH STATEMENT EXECUTE FUNCTION analitica.fn_marcar_demanda_sucia();
CREATE TRIGGER trg_vd_demanda_sucia_upd AFTER UPDATE ON operacion.venta_detalle
    REFERENCING OLD TABLE AS filas_viejas NEW TABLE AS filas_nuevas
    FOR EACH STATEMENT EXECUTE FUNCTION analitica.fn_marcar_demanda_sucia();
CREATE TRIGGER trg_vd_demanda_sucia_del AFTER DELETE ON operacion.venta_detalle
    REFERENCING OLD TABLE AS filas_viejas
    FOR EACH STATEMENT EXECUTE FUNCTION analitica.fn_marcar_demanda_sucia();

-- -----------------------------------------------------------------------------
-- 3. Refresco (SECURITY DEFINER: app_backend no es dueño de la MV)
--
-- Nota: si una venta se registra con fecha_transaccion ANTERIOR al corte
-- (cargas históricas/ETL), no aparecerá hasta el siguiente refresco. Por eso
-- ETL.py y generar_dataset_masivo.py refrescan al terminar.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION analitica.fn_refrescar_agregados()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = analitica, operacion, pg_temp
AS $$
DECLARE
    v_inicio timestamptz := clock_timestamp();
    v_corte  timestamptz := CURRENT_DATE::timestamptz;
    v_ms     integer;
BEGIN
    -- Un solo refresco a la vez (los demás esperan y salen rápido).
    PERFORM pg_advisory_xact_lock(hashtext('analitica.fn_refrescar_agregados'));

    -- La definición de la MV usa CURRENT_DATE, así que el refresco recalcula
    -- exactamente "todo lo anterior a hoy" — coherente con v_corte.
    REFRESH MATERIALIZED VIEW CONCURRENTLY analitica.mv_demanda_diaria_hist;

    v_ms := (extract(epoch FROM clock_timestamp() - v_inicio) * 1000)::integer;
    INSERT INTO analitica.agregado_refresco (nombre, corte, fecha_refresco, duracion_ms)
    VALUES ('mv_demanda_diaria_hist', v_corte, CURRENT_TIMESTAMP, v_ms)
    ON CONFLICT (nombre) DO UPDATE
        SET corte = EXCLUDED.corte,
            fecha_refresco = EXCLUDED.fecha_refresco,
            duracion_ms = EXCLUDED.duracion_ms,
            sucio = false;
    RETURN v_ms;
END
$$;

COMMENT ON FUNCTION analitica.fn_refrescar_agregados() IS
    'Refresca CONCURRENTLY los agregados materializados y mueve la marca de corte. Devuelve la duración en ms.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT SELECT ON analitica.mv_demanda_diaria_hist TO app_backend;
        GRANT SELECT ON analitica.agregado_refresco TO app_backend;
        GRANT EXECUTE ON FUNCTION analitica.fn_refrescar_agregados() TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_etl') THEN
        GRANT SELECT ON analitica.mv_demanda_diaria_hist TO app_etl;
        GRANT EXECUTE ON FUNCTION analitica.fn_refrescar_agregados() TO app_etl;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT SELECT ON analitica.mv_demanda_diaria_hist TO app_auditor;
        GRANT SELECT ON analitica.agregado_refresco TO app_auditor;
    END IF;
END
$$;

-- Aplicado en caliente sobre una base con datos: dejar la MV al día.
SELECT analitica.fn_refrescar_agregados();

-- -----------------------------------------------------------------------------
-- 4. Estadísticas del optimizador
-- -----------------------------------------------------------------------------
ANALYZE operacion.venta_detalle;
ANALYZE operacion.lote;
ANALYZE operacion.existencia;
ANALYZE analitica.mv_demanda_diaria_hist;
ANALYZE analitica.descuento;
ANALYZE analitica.transferencia;
ANALYZE auditoria.bitacora_eventos;
