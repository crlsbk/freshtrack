-- =============================================================================
-- 06_views.sql — Vistas de lectura
--
-- Toda la interfaz consume estas vistas: no hay una sola pantalla que lea
-- datos simulados. La vida útil y el riesgo se calculan al vuelo con las
-- funciones de 05_funciones_negocio.sql.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Inventario real por lote
--   Producto → Tienda → Lote → Caducidad, con días restantes, vida útil
--   residual y clasificación de riesgo ya calculadas.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW operacion.v_inventario_lote AS
SELECT
    e.id_existencia,
    e.id_lote,
    l.codigo_lote_prov,
    l.estado                AS estado_lote,
    p.id_sku,
    p.nombre                AS producto,
    p.categoria,
    p.unidad_medida,
    p.vida_util_estandar,
    loc.id_locacion,
    loc.nombre              AS locacion,
    loc.tipo_locacion,
    e.cantidad_disponible,
    e.cantidad_reservada,
    (e.cantidad_disponible - e.cantidad_reservada) AS cantidad_util,
    l.fecha_produccion,
    l.fecha_recepcion,
    l.fecha_caducidad,
    l.costo_unitario,
    (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
    CASE
        WHEN l.fecha_produccion IS NOT NULL
            THEN (l.fecha_caducidad - l.fecha_produccion)
        ELSE p.vida_util_estandar
    END AS vida_util_total_dias,
    operacion.fn_vida_util_pct(
        (l.fecha_caducidad - CURRENT_DATE)::numeric,
        CASE
            WHEN l.fecha_produccion IS NOT NULL
                THEN (l.fecha_caducidad - l.fecha_produccion)::numeric
            ELSE p.vida_util_estandar::numeric
        END
    ) AS vida_util_pct,
    operacion.fn_clasificar_riesgo(
        p.id_sku,
        p.categoria,
        (l.fecha_caducidad - CURRENT_DATE)::numeric,
        operacion.fn_vida_util_pct(
            (l.fecha_caducidad - CURRENT_DATE)::numeric,
            CASE
                WHEN l.fecha_produccion IS NOT NULL
                    THEN (l.fecha_caducidad - l.fecha_produccion)::numeric
                ELSE p.vida_util_estandar::numeric
            END
        )
    ) AS clasificacion,
    (e.cantidad_disponible * l.costo_unitario) AS valor_inventario,
    pr.id_proveedor,
    pr.razon_social         AS proveedor,
    pr.lead_time_dias
FROM operacion.existencia e
JOIN operacion.lote      l   ON l.id_lote      = e.id_lote
JOIN operacion.producto  p   ON p.id_sku       = l.id_sku
JOIN operacion.locacion  loc ON loc.id_locacion = e.id_locacion
JOIN operacion.proveedor pr  ON pr.id_proveedor = l.id_proveedor;

COMMENT ON VIEW operacion.v_inventario_lote IS
    'Inventario por lote con vida útil residual y clasificación de riesgo calculadas en el momento de la consulta.';

-- -----------------------------------------------------------------------------
-- Lotes con su nivel de riesgo (incluye lotes ya sin existencia)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW operacion.v_lote_riesgo AS
SELECT
    l.id_lote,
    l.codigo_lote_prov,
    l.estado,
    p.id_sku,
    p.nombre        AS producto,
    p.categoria,
    pr.id_proveedor,
    pr.razon_social AS proveedor,
    l.fecha_produccion,
    l.fecha_recepcion,
    l.fecha_caducidad,
    l.cantidad_recibida,
    l.costo_unitario,
    (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
    operacion.fn_vida_util_pct(
        (l.fecha_caducidad - CURRENT_DATE)::numeric,
        CASE WHEN l.fecha_produccion IS NOT NULL
             THEN (l.fecha_caducidad - l.fecha_produccion)::numeric
             ELSE p.vida_util_estandar::numeric END
    ) AS vida_util_pct,
    operacion.fn_clasificar_riesgo(
        p.id_sku, p.categoria,
        (l.fecha_caducidad - CURRENT_DATE)::numeric,
        operacion.fn_vida_util_pct(
            (l.fecha_caducidad - CURRENT_DATE)::numeric,
            CASE WHEN l.fecha_produccion IS NOT NULL
                 THEN (l.fecha_caducidad - l.fecha_produccion)::numeric
                 ELSE p.vida_util_estandar::numeric END
        )
    ) AS clasificacion,
    COALESCE((
        SELECT SUM(e.cantidad_disponible)
        FROM operacion.existencia e
        WHERE e.id_lote = l.id_lote
    ), 0) AS existencia_total
FROM operacion.lote l
JOIN operacion.producto  p  ON p.id_sku = l.id_sku
JOIN operacion.proveedor pr ON pr.id_proveedor = l.id_proveedor;

-- -----------------------------------------------------------------------------
-- Serie de demanda diaria: Venta → Tienda → Producto → Cantidad → Fecha
-- Es el insumo del pronóstico. Nada aquí está simulado.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analitica.v_demanda_diaria AS
SELECT
    vd.id_sku,
    vd.id_locacion,
    vd.fecha_transaccion::date AS fecha,
    SUM(vd.cantidad)           AS cantidad,
    SUM(vd.subtotal)           AS ingreso
FROM operacion.venta_detalle vd
GROUP BY vd.id_sku, vd.id_locacion, vd.fecha_transaccion::date;

COMMENT ON VIEW analitica.v_demanda_diaria IS
    'Serie histórica real usada por el motor de pronóstico (agregada por día).';

-- -----------------------------------------------------------------------------
-- Bitácora de auditoría con nombres legibles
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW auditoria.v_bitacora AS
SELECT
    b.id_evento,
    b.fecha_evento,
    b.accion,
    b.tipo_operacion,
    b.nombre_tabla,
    b.id_registro,
    b.id_usuario_app,
    COALESCE(u.nombre_completo, b.usuario_email, 'Sistema') AS usuario,
    r.nombre_rol AS rol,
    b.descripcion,
    b.estado_anterior,
    b.estado_nuevo,
    b.ip
FROM auditoria.bitacora_eventos b
LEFT JOIN operacion.usuario u ON u.id_usuario = b.id_usuario_app
LEFT JOIN operacion.rol     r ON r.id_rol     = u.id_rol;

-- -----------------------------------------------------------------------------
-- Merma agregada por producto, tienda y causa
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analitica.v_merma_agregada AS
SELECT
    m.id_locacion,
    loc.nombre  AS locacion,
    l.id_sku,
    p.nombre    AS producto,
    p.categoria,
    m.causa_merma,
    date_trunc('month', m.fecha_registro)::date AS mes,
    SUM(m.cantidad)    AS unidades,
    SUM(m.valor_merma) AS valor
FROM operacion.merma m
JOIN operacion.lote     l   ON l.id_lote = m.id_lote
JOIN operacion.producto p   ON p.id_sku  = l.id_sku
JOIN operacion.locacion loc ON loc.id_locacion = m.id_locacion
GROUP BY m.id_locacion, loc.nombre, l.id_sku, p.nombre, p.categoria,
         m.causa_merma, date_trunc('month', m.fecha_registro)::date;

-- -----------------------------------------------------------------------------
-- Alertas abiertas
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analitica.v_alerta_abierta AS
SELECT a.id_alerta, a.tipo, a.severidad, a.mensaje, a.detalle, a.estado,
       a.id_sku, p.nombre AS producto,
       a.id_lote, l.codigo_lote_prov,
       a.id_locacion, loc.nombre AS locacion,
       a.referencia_tipo, a.referencia_id,
       a.fecha_generacion
FROM analitica.alerta a
LEFT JOIN operacion.producto p   ON p.id_sku = a.id_sku
LEFT JOIN operacion.lote     l   ON l.id_lote = a.id_lote
LEFT JOIN operacion.locacion loc ON loc.id_locacion = a.id_locacion
WHERE a.estado = 'ABIERTA';

-- -----------------------------------------------------------------------------
-- Trazabilidad de lote: una fila por evento del ciclo de vida
--   Proveedor → Recepción → Tienda/CEDIS → Existencia → Ventas FEFO →
--   Transferencias → Merma → Estado final
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW analitica.v_trazabilidad_lote AS
SELECT
    l.id_lote,
    l.codigo_lote_prov,
    p.nombre  AS producto,
    pr.razon_social AS proveedor,
    l.fecha_recepcion,
    l.fecha_caducidad,
    l.cantidad_recibida,
    l.estado  AS estado_final,
    'RECEPCION' AS etapa,
    l.fecha_recepcion::timestamptz AS fecha_etapa,
    l.cantidad_recibida AS cantidad,
    COALESCE(loc.nombre, '—') AS locacion,
    NULL::text AS referencia
FROM operacion.lote l
JOIN operacion.producto  p  ON p.id_sku = l.id_sku
JOIN operacion.proveedor pr ON pr.id_proveedor = l.id_proveedor
LEFT JOIN operacion.locacion loc ON loc.id_locacion = l.id_locacion_recepcion

UNION ALL
SELECT
    l.id_lote, l.codigo_lote_prov, p.nombre, pr.razon_social,
    l.fecha_recepcion, l.fecha_caducidad, l.cantidad_recibida, l.estado,
    'VENTA', vd.fecha_transaccion, vd.cantidad, loc.nombre,
    v.folio
FROM operacion.venta_detalle vd
JOIN operacion.venta     v   ON v.id_venta = vd.id_venta
JOIN operacion.lote      l   ON l.id_lote = vd.id_lote
JOIN operacion.producto  p   ON p.id_sku = l.id_sku
JOIN operacion.proveedor pr  ON pr.id_proveedor = l.id_proveedor
JOIN operacion.locacion  loc ON loc.id_locacion = vd.id_locacion

UNION ALL
SELECT
    l.id_lote, l.codigo_lote_prov, p.nombre, pr.razon_social,
    l.fecha_recepcion, l.fecha_caducidad, l.cantidad_recibida, l.estado,
    'MERMA', m.fecha_registro, m.cantidad, loc.nombre, m.causa_merma
FROM operacion.merma m
JOIN operacion.lote      l   ON l.id_lote = m.id_lote
JOIN operacion.producto  p   ON p.id_sku = l.id_sku
JOIN operacion.proveedor pr  ON pr.id_proveedor = l.id_proveedor
JOIN operacion.locacion  loc ON loc.id_locacion = m.id_locacion

UNION ALL
SELECT
    l.id_lote, l.codigo_lote_prov, p.nombre, pr.razon_social,
    l.fecha_recepcion, l.fecha_caducidad, l.cantidad_recibida, l.estado,
    'TRANSFERENCIA', COALESCE(t.fecha_ejecucion, t.fecha_creacion), t.cantidad,
    o.nombre || ' → ' || d.nombre, t.estado
FROM analitica.transferencia t
JOIN operacion.lote      l  ON l.id_lote = t.id_lote
JOIN operacion.producto  p  ON p.id_sku = l.id_sku
JOIN operacion.proveedor pr ON pr.id_proveedor = l.id_proveedor
JOIN operacion.locacion  o  ON o.id_locacion = t.id_locacion_origen
JOIN operacion.locacion  d  ON d.id_locacion = t.id_locacion_destino;

-- =============================================================================
-- Permisos
-- =============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        GRANT SELECT ON operacion.v_inventario_lote, operacion.v_lote_riesgo TO app_backend;
        GRANT SELECT ON analitica.v_demanda_diaria, analitica.v_merma_agregada,
                        analitica.v_alerta_abierta, analitica.v_trazabilidad_lote TO app_backend;
        GRANT SELECT ON auditoria.v_bitacora TO app_backend;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_auditor') THEN
        GRANT SELECT ON operacion.v_inventario_lote, operacion.v_lote_riesgo TO app_auditor;
        GRANT SELECT ON analitica.v_demanda_diaria, analitica.v_merma_agregada,
                        analitica.v_alerta_abierta, analitica.v_trazabilidad_lote TO app_auditor;
        GRANT SELECT ON auditoria.v_bitacora TO app_auditor;
    END IF;
END
$$;
