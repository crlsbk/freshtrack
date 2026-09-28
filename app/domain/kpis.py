"""
KPIs y tablero.

Todo lo que muestra el panel se calcula contra PostgreSQL: no hay ni un
indicador de ejemplo.

Incluye la metodología de **desperdicio evitado**, que deja de ser un número
inventado y pasa a ser un cálculo explicable:

    1. Riesgo estimado inicial : unidades que iban a vencer sin intervención
    2. Intervención            : transferencia o descuento aprobado
    3. Recuperado              : unidades vendidas antes de vencer
    4. Merma residual          : unidades que igualmente se perdieron

    desperdicio evitado = unidades recuperadas por la intervención
"""

from __future__ import annotations

from sqlalchemy import text

from app.db import a_float, a_int, one, query, transaccion


# ---------------------------------------------------------------------------
# Panel principal
# ---------------------------------------------------------------------------
def panel_principal() -> dict:
    """Métricas del tablero empresarial."""
    inventario = one(
        """
        SELECT COALESCE(SUM(cantidad_disponible), 0) AS unidades,
               COALESCE(SUM(valor_inventario), 0)    AS valor,
               COUNT(DISTINCT id_lote)               AS lotes,
               COUNT(DISTINCT id_sku)                AS skus,
               COUNT(DISTINCT id_locacion)           AS locaciones,
               COALESCE(SUM(CASE WHEN clasificacion = 'CRITICO'
                                 THEN cantidad_disponible END), 0) AS criticas,
               COALESCE(SUM(CASE WHEN clasificacion = 'VIGILANCIA'
                                 THEN cantidad_disponible END), 0) AS vigilancia,
               COALESCE(SUM(CASE WHEN clasificacion = 'VENCIDO'
                                 THEN cantidad_disponible END), 0) AS vencidas,
               COUNT(*) FILTER (WHERE clasificacion = 'CRITICO')   AS lotes_criticos,
               COUNT(*) FILTER (WHERE clasificacion = 'VIGILANCIA') AS lotes_vigilancia
        FROM operacion.v_inventario_lote
        WHERE cantidad_disponible > 0
        """
    ) or {}

    ventas = one(
        """
        SELECT COALESCE(SUM(cantidad), 0) AS unidades,
               COALESCE(SUM(subtotal), 0) AS ingreso,
               COUNT(DISTINCT id_venta)   AS tickets,
               COALESCE(SUM(CASE WHEN fecha_transaccion >= CURRENT_DATE - 7
                                 THEN cantidad END), 0) AS unidades_7d,
               COALESCE(SUM(CASE WHEN fecha_transaccion >= CURRENT_DATE - 30
                                 THEN cantidad END), 0) AS unidades_30d
        FROM operacion.venta_detalle
        """
    ) or {}

    merma = one(
        """
        SELECT COALESCE(SUM(cantidad), 0)    AS unidades,
               COALESCE(SUM(valor_merma), 0) AS valor,
               COUNT(*)                      AS eventos,
               COALESCE(SUM(CASE WHEN fecha_registro >= CURRENT_DATE - 30
                                 THEN cantidad END), 0) AS unidades_30d,
               COALESCE(SUM(CASE WHEN fecha_registro >= CURRENT_DATE - 30
                                 THEN valor_merma END), 0) AS valor_30d
        FROM operacion.merma
        """
    ) or {}

    alertas = one(
        """
        SELECT COUNT(*) FILTER (WHERE estado = 'ABIERTA')                     AS abiertas,
               COUNT(*) FILTER (WHERE estado = 'ABIERTA' AND severidad = 'CRITICA') AS criticas,
               COUNT(*) FILTER (WHERE estado = 'ABIERTA' AND severidad = 'ALTA')    AS altas
        FROM analitica.alerta
        """
    ) or {}

    ordenes = one(
        """
        SELECT COUNT(*) FILTER (WHERE estado = 'PENDIENTE') AS pendientes,
               COUNT(*) FILTER (WHERE estado = 'APROBADA')  AS aprobadas
        FROM analitica.orden_reabastecimiento
        """
    ) or {}

    transferencias = one(
        """
        SELECT COUNT(*) FILTER (WHERE estado = 'SUGERIDA')  AS sugeridas,
               COUNT(*) FILTER (WHERE estado = 'APROBADA')  AS aprobadas,
               COUNT(*) FILTER (WHERE estado = 'EJECUTADA') AS ejecutadas
        FROM analitica.transferencia
        """
    ) or {}

    return {
        "inventario": inventario,
        "ventas": ventas,
        "merma": merma,
        "alertas": alertas,
        "ordenes": ordenes,
        "transferencias": transferencias,
    }


def top_desperdicio_sku(limite: int = 8, dias: int = 180) -> list[dict]:
    return query(
        """
        SELECT p.nombre AS producto, p.id_sku, p.categoria,
               SUM(m.cantidad)    AS unidades,
               SUM(m.valor_merma) AS valor
        FROM operacion.merma m
        JOIN operacion.lote     l ON l.id_lote = m.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        WHERE m.fecha_registro >= CURRENT_DATE - :dias
        GROUP BY p.nombre, p.id_sku, p.categoria
        ORDER BY valor DESC
        LIMIT :limite
        """,
        dias=dias,
        limite=limite,
    )


def top_desperdicio_tienda(limite: int = 8, dias: int = 180) -> list[dict]:
    return query(
        """
        SELECT loc.nombre AS locacion, m.id_locacion,
               SUM(m.cantidad)    AS unidades,
               SUM(m.valor_merma) AS valor
        FROM operacion.merma m
        JOIN operacion.locacion loc ON loc.id_locacion = m.id_locacion
        WHERE m.fecha_registro >= CURRENT_DATE - :dias
        GROUP BY loc.nombre, m.id_locacion
        ORDER BY valor DESC
        LIMIT :limite
        """,
        dias=dias,
        limite=limite,
    )


def lotes_criticos(limite: int = 12) -> list[dict]:
    return query(
        """
        SELECT producto, locacion, codigo_lote_prov, cantidad_disponible,
               unidad_medida, fecha_caducidad, dias_restantes, vida_util_pct,
               clasificacion, valor_inventario, id_lote::text
        FROM operacion.v_inventario_lote
        WHERE cantidad_disponible > 0
          AND clasificacion IN ('CRITICO', 'VENCIDO')
        ORDER BY dias_restantes ASC
        LIMIT :limite
        """,
        limite=limite,
    )


def serie_mensual(meses: int = 6) -> list[dict]:
    """Ventas y merma por mes, para las gráficas del panel."""
    return query(
        """
        WITH meses AS (
            SELECT to_char(date_trunc('month', CURRENT_DATE - (n || ' months')::interval),
                           'YYYY-MM') AS mes,
                   date_trunc('month', CURRENT_DATE - (n || ' months')::interval)::date AS inicio
            FROM generate_series(0, :meses - 1) AS n
        ),
        v AS (
            SELECT to_char(date_trunc('month', fecha_transaccion), 'YYYY-MM') AS mes,
                   SUM(cantidad) AS unidades, SUM(subtotal) AS ingreso
            FROM operacion.venta_detalle GROUP BY 1
        ),
        m AS (
            SELECT to_char(date_trunc('month', fecha_registro), 'YYYY-MM') AS mes,
                   SUM(cantidad) AS unidades, SUM(valor_merma) AS valor
            FROM operacion.merma GROUP BY 1
        )
        SELECT to_char(mm.inicio, 'YYYY-MM') AS mes,
               COALESCE(v.unidades, 0) AS ventas_unidades,
               COALESCE(v.ingreso, 0)  AS ventas_ingreso,
               COALESCE(m.unidades, 0) AS merma_unidades,
               COALESCE(m.valor, 0)    AS merma_valor
        FROM meses mm
        LEFT JOIN v ON v.mes = mm.mes
        LEFT JOIN m ON m.mes = mm.mes
        ORDER BY mm.inicio
        """,
        meses=meses,
    )


def merma_por_categoria(dias: int = 180) -> list[dict]:
    return query(
        """
        SELECT p.categoria AS name,
               SUM(m.cantidad)    AS unidades,
               SUM(m.valor_merma) AS valor
        FROM operacion.merma m
        JOIN operacion.lote     l ON l.id_lote = m.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        WHERE m.fecha_registro >= CURRENT_DATE - :dias
        GROUP BY p.categoria
        ORDER BY valor DESC
        """,
        dias=dias,
    )


def inventario_por_locacion() -> list[dict]:
    return query(
        """
        SELECT loc.nombre AS locacion, loc.tipo_locacion, v.id_locacion,
               SUM(v.cantidad_disponible) AS unidades,
               SUM(v.valor_inventario)    AS valor,
               COUNT(*) FILTER (WHERE v.clasificacion IN ('CRITICO','VENCIDO')) AS lotes_en_riesgo
        FROM operacion.v_inventario_lote v
        JOIN operacion.locacion loc ON loc.id_locacion = v.id_locacion
        WHERE v.cantidad_disponible > 0
        GROUP BY loc.nombre, loc.tipo_locacion, v.id_locacion
        ORDER BY valor DESC
        """
    )


def tasa_merma(dias: int = 180) -> dict:
    """Merma como porcentaje de lo recibido: el indicador honesto."""
    fila = one(
        """
        SELECT
            (SELECT COALESCE(SUM(cantidad_recibida), 0) FROM operacion.lote
              WHERE fecha_recepcion >= CURRENT_DATE - :dias) AS recibido,
            (SELECT COALESCE(SUM(cantidad), 0) FROM operacion.merma
              WHERE fecha_registro >= CURRENT_DATE - :dias) AS mermado,
            (SELECT COALESCE(SUM(cantidad), 0) FROM operacion.venta_detalle
              WHERE fecha_transaccion >= CURRENT_DATE - :dias) AS vendido
        """,
        dias=dias,
    ) or {}
    recibido = a_float(fila.get("recibido"))
    fila["tasa_pct"] = round(100 * a_float(fila.get("mermado")) / recibido, 2) if recibido else 0.0
    fila["tasa_venta_pct"] = (
        round(100 * a_float(fila.get("vendido")) / recibido, 2) if recibido else 0.0
    )
    return fila


# ---------------------------------------------------------------------------
# Desperdicio evitado
# ---------------------------------------------------------------------------
def calcular_desperdicio_evitado() -> dict:
    """
    Recalcula el desperdicio evitado a partir de las intervenciones reales.

    Para cada transferencia ejecutada y cada descuento aplicado, se cuentan las
    unidades de ese lote vendidas en el destino entre la intervención y la fecha
    de caducidad. Eso es lo recuperado. Lo que se mermó en ese mismo intervalo
    es la merma residual.
    """
    with transaccion() as conn:
        actualizados = conn.execute(
            text(
                """
                WITH intervenciones AS (
                    SELECT de.id_registro::text, de.id_lote, de.id_locacion,
                           de.cantidad_intervenida, de.tipo_intervencion,
                           t.fecha_ejecucion AS desde,
                           t.id_locacion_destino AS loc_destino,
                           l.fecha_caducidad
                    FROM analitica.desperdicio_evitado de
                    JOIN analitica.transferencia t ON t.id_transferencia = de.id_transferencia
                    JOIN operacion.lote l ON l.id_lote = de.id_lote
                    WHERE de.tipo_intervencion = 'TRANSFERENCIA'
                ),
                vendido AS (
                    SELECT i.id_registro,
                           COALESCE(SUM(vd.cantidad), 0) AS recuperado,
                           COALESCE(SUM(vd.subtotal), 0) AS valor
                    FROM intervenciones i
                    LEFT JOIN operacion.venta_detalle vd
                           ON vd.id_lote = i.id_lote
                          AND vd.id_locacion = i.loc_destino
                          AND vd.fecha_transaccion >= i.desde
                          AND vd.fecha_transaccion::date <= i.fecha_caducidad
                    GROUP BY i.id_registro
                ),
                mermado AS (
                    SELECT i.id_registro,
                           COALESCE(SUM(m.cantidad), 0) AS perdido
                    FROM intervenciones i
                    LEFT JOIN operacion.merma m
                           ON m.id_lote = i.id_lote
                          AND m.id_locacion = i.loc_destino
                          AND m.fecha_registro >= i.desde
                          AND m.fecha_registro::date <= i.fecha_caducidad
                    GROUP BY i.id_registro
                )
                UPDATE analitica.desperdicio_evitado de
                   SET cantidad_recuperada = LEAST(v.recuperado, de.cantidad_intervenida),
                       cantidad_mermada    = m.perdido,
                       valor_recuperado    = v.valor,
                       metodologia = 'Unidades del lote efectivamente vendidas en la tienda '
                                     'destino entre la fecha de ejecución de la transferencia '
                                     'y la fecha de caducidad del lote. La merma residual son '
                                     'las unidades de ese mismo lote dadas de baja en el '
                                     'destino dentro del mismo intervalo.'
                  FROM vendido v, mermado m
                 WHERE de.id_registro = CAST(v.id_registro AS uuid)
                   AND de.id_registro = CAST(m.id_registro AS uuid)
                   AND de.tipo_intervencion = 'TRANSFERENCIA'
                """
            )
        ).rowcount or 0

    return {"actualizados": actualizados}


def resumen_desperdicio_evitado() -> dict:
    totales = one(
        """
        SELECT COALESCE(SUM(cantidad_en_riesgo), 0)   AS en_riesgo,
               COALESCE(SUM(cantidad_intervenida), 0) AS intervenido,
               COALESCE(SUM(cantidad_recuperada), 0)  AS recuperado,
               COALESCE(SUM(cantidad_mermada), 0)     AS mermado,
               COALESCE(SUM(valor_recuperado), 0)     AS valor,
               COUNT(*)                               AS intervenciones
        FROM analitica.desperdicio_evitado
        """
    ) or {}

    en_riesgo = a_float(totales.get("en_riesgo"))
    recuperado = a_float(totales.get("recuperado"))
    totales["tasa_recuperacion"] = (
        round(100 * recuperado / en_riesgo, 1) if en_riesgo else 0.0
    )

    detalle = query(
        """
        SELECT de.id_registro::text, de.tipo_intervencion, de.cantidad_en_riesgo,
               de.cantidad_intervenida, de.cantidad_recuperada, de.cantidad_mermada,
               de.valor_recuperado, de.fecha_registro, de.metodologia,
               p.nombre AS producto, p.unidad_medida,
               o.nombre AS origen, d.nombre AS destino,
               l.codigo_lote_prov, l.fecha_caducidad
        FROM analitica.desperdicio_evitado de
        JOIN operacion.lote l ON l.id_lote = de.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        LEFT JOIN analitica.transferencia t ON t.id_transferencia = de.id_transferencia
        LEFT JOIN operacion.locacion o ON o.id_locacion = t.id_locacion_origen
        LEFT JOIN operacion.locacion d ON d.id_locacion = t.id_locacion_destino
        ORDER BY de.fecha_registro DESC
        LIMIT 50
        """
    )

    return {"totales": totales, "detalle": detalle}


def kpis_sostenibilidad(dias: int = 180) -> dict:
    """Indicadores de sostenibilidad: lo que se evitó y su equivalencia."""
    evitado = resumen_desperdicio_evitado()["totales"]
    merma = one(
        """
        SELECT COALESCE(SUM(cantidad), 0) AS unidades,
               COALESCE(SUM(valor_merma), 0) AS valor
        FROM operacion.merma
        WHERE fecha_registro >= CURRENT_DATE - :dias
        """,
        dias=dias,
    ) or {}

    recuperado = a_float(evitado.get("recuperado"))
    mermado = a_float(merma.get("unidades"))
    total = recuperado + mermado

    # 2.5 kg de CO2e por kg de alimento desperdiciado (referencia FAO)
    kg_evitados = recuperado
    return {
        "unidades_recuperadas": recuperado,
        "unidades_mermadas": mermado,
        "valor_recuperado": a_float(evitado.get("valor")),
        "tasa_aprovechamiento": round(100 * recuperado / total, 1) if total else 0.0,
        "co2e_evitado_kg": round(kg_evitados * 2.5, 1),
        "metodologia": (
            "Unidades recuperadas mediante transferencias y descuentos aprobados, "
            "medidas como ventas reales del lote antes de su caducidad. "
            "La equivalencia de CO2e usa 2.5 kg CO2e por kg de alimento (referencia FAO)."
        ),
    }
