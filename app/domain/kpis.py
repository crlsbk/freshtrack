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


def metricas_por_locacion(dias: int = 30) -> list[dict]:
    """
    Indicadores de cada tienda y CEDIS activos para el mapa: ubicación,
    inventario y riesgo actuales, ventas y merma de los últimos `dias`, alertas
    abiertas, órdenes pendientes y los lotes en riesgo de mayor valor.
    """
    locaciones = query(
        """
        SELECT id_locacion, nombre, tipo_locacion, ciudad, direccion,
               latitud::float AS latitud, longitud::float AS longitud
        FROM operacion.locacion
        WHERE activo
        ORDER BY tipo_locacion, nombre
        """
    )

    def por_id(filas: list[dict]) -> dict[int, dict]:
        return {f["id_locacion"]: f for f in filas}

    inventario = por_id(query(
        """
        SELECT id_locacion,
               SUM(cantidad_disponible)  AS unidades,
               SUM(valor_inventario)     AS valor,
               COUNT(DISTINCT id_lote)   AS lotes,
               COUNT(DISTINCT id_sku)    AS skus,
               COUNT(*) FILTER (WHERE clasificacion = 'VIGILANCIA') AS lotes_vigilancia,
               COUNT(*) FILTER (WHERE clasificacion = 'CRITICO')    AS lotes_criticos,
               COUNT(*) FILTER (WHERE clasificacion = 'VENCIDO')    AS lotes_vencidos,
               COALESCE(SUM(valor_inventario) FILTER (
                   WHERE clasificacion IN ('CRITICO', 'VENCIDO')), 0) AS valor_en_riesgo
        FROM operacion.v_inventario_lote
        WHERE cantidad_disponible > 0
        GROUP BY id_locacion
        """
    ))
    ventas = por_id(query(
        """
        SELECT id_locacion,
               SUM(subtotal)            AS ingreso,
               SUM(cantidad)            AS unidades,
               COUNT(DISTINCT id_venta) AS tickets
        FROM operacion.venta_detalle
        WHERE fecha_transaccion >= CURRENT_DATE - :dias
        GROUP BY id_locacion
        """,
        dias=dias,
    ))
    merma = por_id(query(
        """
        SELECT id_locacion, SUM(cantidad) AS unidades, SUM(valor_merma) AS valor
        FROM operacion.merma
        WHERE fecha_registro >= CURRENT_DATE - :dias
        GROUP BY id_locacion
        """,
        dias=dias,
    ))
    recibido = por_id(query(
        """
        SELECT id_locacion_recepcion AS id_locacion, SUM(cantidad_recibida) AS unidades
        FROM operacion.lote
        WHERE fecha_recepcion >= CURRENT_DATE - :dias
        GROUP BY id_locacion_recepcion
        """,
        dias=dias,
    ))
    alertas = por_id(query(
        """
        SELECT id_locacion,
               COUNT(*) AS abiertas,
               COUNT(*) FILTER (WHERE severidad IN ('CRITICA', 'ALTA')) AS urgentes
        FROM analitica.alerta
        WHERE estado = 'ABIERTA' AND id_locacion IS NOT NULL
        GROUP BY id_locacion
        """
    ))
    ordenes = por_id(query(
        """
        SELECT id_locacion, COUNT(*) AS pendientes
        FROM analitica.orden_reabastecimiento
        WHERE estado = 'PENDIENTE'
        GROUP BY id_locacion
        """
    ))
    en_riesgo: dict[int, list[dict]] = {}
    for f in query(
        """
        SELECT id_locacion, producto, codigo_lote_prov, clasificacion, dias_restantes,
               cantidad_disponible, unidad_medida, valor_inventario
        FROM (
            SELECT v.*, ROW_NUMBER() OVER (
                       PARTITION BY id_locacion ORDER BY valor_inventario DESC) AS n
            FROM operacion.v_inventario_lote v
            WHERE cantidad_disponible > 0 AND clasificacion IN ('CRITICO', 'VENCIDO')
        ) t
        WHERE n <= 3
        ORDER BY id_locacion, n
        """
    ):
        en_riesgo.setdefault(f["id_locacion"], []).append({
            "producto": f["producto"],
            "lote": f["codigo_lote_prov"],
            "clasificacion": f["clasificacion"],
            "dias_restantes": a_int(f["dias_restantes"]),
            "cantidad": a_float(f["cantidad_disponible"]),
            "unidad": f["unidad_medida"],
            "valor": a_float(f["valor_inventario"]),
        })

    resultado = []
    for loc in locaciones:
        i = loc["id_locacion"]
        inv, ven, mer = inventario.get(i, {}), ventas.get(i, {}), merma.get(i, {})
        rec = a_float(recibido.get(i, {}).get("unidades"))
        merma_unidades = a_float(mer.get("unidades"))
        resultado.append({
            **loc,
            "inventario": {
                "unidades": a_float(inv.get("unidades")),
                "valor": a_float(inv.get("valor")),
                "lotes": a_int(inv.get("lotes")),
                "skus": a_int(inv.get("skus")),
                "lotes_vigilancia": a_int(inv.get("lotes_vigilancia")),
                "lotes_criticos": a_int(inv.get("lotes_criticos")),
                "lotes_vencidos": a_int(inv.get("lotes_vencidos")),
                "valor_en_riesgo": a_float(inv.get("valor_en_riesgo")),
            },
            "ventas": {
                "ingreso": a_float(ven.get("ingreso")),
                "unidades": a_float(ven.get("unidades")),
                "tickets": a_int(ven.get("tickets")),
            },
            "merma": {
                "unidades": merma_unidades,
                "valor": a_float(mer.get("valor")),
                "recibido": rec,
                "tasa_pct": round(100 * merma_unidades / rec, 2) if rec else None,
            },
            "alertas": {
                "abiertas": a_int(alertas.get(i, {}).get("abiertas")),
                "urgentes": a_int(alertas.get(i, {}).get("urgentes")),
            },
            "ordenes_pendientes": a_int(ordenes.get(i, {}).get("pendientes")),
            "lotes_en_riesgo": en_riesgo.get(i, []),
        })
    return resultado


def tasa_merma(dias: int | None = 180) -> dict:
    """Merma como porcentaje de lo recibido: el indicador honesto."""
    if dias is not None:
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
    else:
        fila = one(
            """
            SELECT
                (SELECT COALESCE(SUM(cantidad_recibida), 0) FROM operacion.lote) AS recibido,
                (SELECT COALESCE(SUM(cantidad), 0) FROM operacion.merma) AS mermado,
                (SELECT COALESCE(SUM(cantidad), 0) FROM operacion.venta_detalle) AS vendido
            """
        ) or {}
    recibido = a_float(fila.get("recibido"))
    fila["tasa_pct"] = round(100 * a_float(fila.get("mermado")) / recibido, 2) if recibido else 0.0
    fila["tasa_venta_pct"] = (
        round(100 * a_float(fila.get("vendido")) / recibido, 2) if recibido else 0.0
    )
    return fila


def metricas_periodo(dias: int | None = 30) -> dict:
    """
    Calcula dinámicamente en tiempo real contra PostgreSQL las métricas de ventas,
    merma y tasa porcentual para cualquier ventana de días especificada (o histórico completo).
    """
    if dias is not None:
        filtro_v = "WHERE fecha_transaccion >= CURRENT_DATE - :dias"
        filtro_m = "WHERE fecha_registro >= CURRENT_DATE - :dias"
        params = {"dias": dias}
        if dias == 30:
            etiqueta = "Último mes (30 días)"
        elif dias == 90:
            etiqueta = "Últimos 3 meses (90 días)"
        elif dias == 180:
            etiqueta = "Últimos 6 meses (180 días)"
        else:
            etiqueta = f"Últimos {dias} días"
    else:
        filtro_v = ""
        filtro_m = ""
        params = {}
        etiqueta = "Histórico completo"

    ventas = one(
        f"""
        SELECT COALESCE(SUM(cantidad), 0) AS unidades,
               COALESCE(SUM(subtotal), 0) AS ingreso,
               COUNT(DISTINCT id_venta)   AS tickets
        FROM operacion.venta_detalle
        {filtro_v}
        """,
        **params,
    ) or {"unidades": 0, "ingreso": 0, "tickets": 0}

    merma = one(
        f"""
        SELECT COALESCE(SUM(cantidad), 0)    AS unidades,
               COALESCE(SUM(valor_merma), 0) AS valor,
               COUNT(*)                      AS eventos
        FROM operacion.merma
        {filtro_m}
        """,
        **params,
    ) or {"unidades": 0, "valor": 0, "eventos": 0}

    tasa = tasa_merma(dias)

    v_ingreso = a_float(ventas.get("ingreso"))
    v_unidades = a_float(ventas.get("unidades"))
    v_tickets = a_int(ventas.get("tickets"))

    m_valor = a_float(merma.get("valor"))
    m_unidades = a_float(merma.get("unidades"))
    m_eventos = a_int(merma.get("eventos"))

    d_v = 0 if (v_ingreso >= 100000 or v_ingreso <= -100000) else 2
    d_m = 0 if (m_valor >= 100000 or m_valor <= -100000) else 2

    return {
        "dias": dias,
        "etiqueta_periodo": etiqueta,
        "ventas": {
            "unidades": v_unidades,
            "ingreso": v_ingreso,
            "tickets": v_tickets,
            "unidades_formato": f"{v_unidades:,.0f}" if abs(v_unidades - round(v_unidades)) < 0.005 else f"{v_unidades:,.2f}",
            "ingreso_formato": f"${v_ingreso:,.{d_v}f}",
            "tickets_formato": f"{v_tickets:,}",
        },
        "merma": {
            "unidades": m_unidades,
            "valor": m_valor,
            "eventos": m_eventos,
            "unidades_formato": f"{m_unidades:,.0f}" if abs(m_unidades - round(m_unidades)) < 0.005 else f"{m_unidades:,.2f}",
            "valor_formato": f"${m_valor:,.{d_m}f}",
            "eventos_formato": f"{m_eventos:,}",
        },
        "tasa": {
            "tasa_pct": tasa.get("tasa_pct", 0.0),
            "tasa_venta_pct": tasa.get("tasa_venta_pct", 0.0),
            "mermado": a_float(tasa.get("mermado")),
            "recibido": a_float(tasa.get("recibido")),
            "mermado_formato": f"{a_float(tasa.get('mermado')):,.0f}",
            "recibido_formato": f"{a_float(tasa.get('recibido')):,.0f}",
        },
    }


# ---------------------------------------------------------------------------
# Desperdicio evitado
# ---------------------------------------------------------------------------
def calcular_desperdicio_evitado() -> dict:
    """
    Recalcula el desperdicio evitado a partir de las intervenciones reales
    (transferencias ejecutadas y descuentos aprobados), descontando la línea
    base contrafactual (demanda orgánica sin intervención).
    """
    with transaccion() as conn:
        act_tr = conn.execute(
            text(
                """
                WITH intervenciones AS (
                    SELECT de.id_registro::text, de.id_lote, de.id_locacion,
                           de.cantidad_intervenida, de.demanda_base_contrafactual,
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
                       desperdicio_proyectado = GREATEST(de.cantidad_en_riesgo, de.cantidad_intervenida - de.demanda_base_contrafactual),
                       desperdicio_evitado_neto = LEAST(
                           de.cantidad_intervenida,
                           GREATEST(0, LEAST(v.recuperado, de.cantidad_intervenida) - de.demanda_base_contrafactual)
                       ),
                       metodologia = 'Unidades del lote vendidas en tienda destino entre la ejecución '
                                     'y la caducidad, descontando cualquier demanda base contrafactual.'
                  FROM vendido v, mermado m
                 WHERE de.id_registro = CAST(v.id_registro AS uuid)
                   AND de.id_registro = CAST(m.id_registro AS uuid)
                   AND de.tipo_intervencion = 'TRANSFERENCIA'
                """
            )
        ).rowcount or 0

        act_desc = conn.execute(
            text(
                """
                WITH intervenciones AS (
                    SELECT de.id_registro::text, de.id_lote, de.id_locacion,
                           de.cantidad_intervenida, de.demanda_base_contrafactual,
                           COALESCE(d.fecha_decision, d.fecha_creacion) AS desde,
                           l.fecha_caducidad
                    FROM analitica.desperdicio_evitado de
                    JOIN analitica.descuento d ON d.id_descuento = de.id_descuento
                    JOIN operacion.lote l ON l.id_lote = de.id_lote
                    WHERE de.tipo_intervencion = 'DESCUENTO'
                ),
                vendido AS (
                    SELECT i.id_registro,
                           COALESCE(SUM(vd.cantidad), 0) AS recuperado,
                           COALESCE(SUM(vd.subtotal), 0) AS valor
                    FROM intervenciones i
                    LEFT JOIN operacion.venta_detalle vd
                           ON vd.id_lote = i.id_lote
                          AND vd.id_locacion = i.id_locacion
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
                          AND m.id_locacion = i.id_locacion
                          AND m.fecha_registro >= i.desde
                          AND m.fecha_registro::date <= i.fecha_caducidad
                    GROUP BY i.id_registro
                )
                UPDATE analitica.desperdicio_evitado de
                   SET cantidad_recuperada = LEAST(v.recuperado, de.cantidad_intervenida),
                       cantidad_mermada    = m.perdido,
                       valor_recuperado    = v.valor,
                       desperdicio_proyectado = GREATEST(de.cantidad_en_riesgo, de.cantidad_intervenida - de.demanda_base_contrafactual),
                       desperdicio_evitado_neto = LEAST(
                           de.cantidad_intervenida,
                           GREATEST(0, LEAST(v.recuperado, de.cantidad_intervenida) - de.demanda_base_contrafactual)
                       ),
                       metodologia = 'Descuento preventivo: las unidades vendidas tras el descuento '
                                     'se contrastan contra la línea base contrafactual orgánica para '
                                     'estimar el desperdicio neto evitado.'
                  FROM vendido v, mermado m
                 WHERE de.id_registro = CAST(v.id_registro AS uuid)
                   AND de.id_registro = CAST(m.id_registro AS uuid)
                   AND de.tipo_intervencion = 'DESCUENTO'
                """
            )
        ).rowcount or 0

    return {"actualizados": act_tr + act_desc, "transferencias": act_tr, "descuentos": act_desc}


def resumen_desperdicio_evitado() -> dict:
    totales = one(
        """
        SELECT COALESCE(SUM(cantidad_en_riesgo), 0)         AS en_riesgo,
               COALESCE(SUM(cantidad_intervenida), 0)       AS intervenido,
               COALESCE(SUM(cantidad_recuperada), 0)        AS recuperado,
               COALESCE(SUM(cantidad_mermada), 0)           AS mermado,
               COALESCE(SUM(valor_recuperado), 0)           AS valor,
               COALESCE(SUM(demanda_base_contrafactual), 0) AS contrafactual,
               COALESCE(SUM(desperdicio_evitado_neto), 0)   AS evitado_neto,
               COUNT(*)                                     AS intervenciones
        FROM analitica.desperdicio_evitado
        """
    ) or {}

    en_riesgo = a_float(totales.get("en_riesgo"))
    recuperado = a_float(totales.get("recuperado"))
    evitado_neto = a_float(totales.get("evitado_neto"))
    # Si todavía no se ha recalculado neto (registros legacy), usar recuperado - contrafactual
    if evitado_neto == 0 and recuperado > 0 and a_float(totales.get("contrafactual")) == 0:
        evitado_neto = recuperado
        totales["evitado_neto"] = evitado_neto

    totales["tasa_recuperacion"] = (
        round(100 * recuperado / en_riesgo, 1) if en_riesgo else 0.0
    )

    detalle = query(
        """
        SELECT de.id_registro::text, de.tipo_intervencion, de.cantidad_en_riesgo,
               de.cantidad_intervenida, de.cantidad_recuperada, de.cantidad_mermada,
               de.valor_recuperado, de.demanda_base_contrafactual,
               de.desperdicio_evitado_neto, de.fecha_registro, de.metodologia,
               p.nombre AS producto, p.unidad_medida,
               o.nombre AS origen, d.nombre AS destino,
               loc.nombre AS locacion_desc,
               l.codigo_lote_prov, l.fecha_caducidad
        FROM analitica.desperdicio_evitado de
        JOIN operacion.lote l ON l.id_lote = de.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        LEFT JOIN analitica.transferencia t ON t.id_transferencia = de.id_transferencia
        LEFT JOIN operacion.locacion o ON o.id_locacion = t.id_locacion_origen
        LEFT JOIN operacion.locacion d ON d.id_locacion = t.id_locacion_destino
        LEFT JOIN operacion.locacion loc ON loc.id_locacion = de.id_locacion
        ORDER BY de.fecha_registro DESC
        LIMIT 50
        """
    )

    return {"totales": totales, "detalle": detalle}


def indicadores_desperdicio_completo(dias: int = 30) -> dict:
    """
    Devuelve los 6 indicadores diferenciados requeridos en instructions.md:
      1. Producto en riesgo
      2. Desperdicio proyectado
      3. Producto recuperado
      4. Desperdicio evitado estimado (contra línea base contrafactual)
      5. Reducción observada de merma
      6. CO2e evitado estimado (con factor y supuestos documentados)
    """
    riesgo_actual = one(
        """
        WITH dem AS (
            SELECT id_sku, id_locacion, AVG(cantidad) AS diaria
            FROM analitica.v_demanda_diaria
            WHERE fecha >= CURRENT_DATE - 28
            GROUP BY id_sku, id_locacion
        )
        SELECT COALESCE(SUM(v.cantidad_disponible), 0) AS unidades_riesgo,
               COALESCE(SUM(v.valor_inventario), 0) AS valor_riesgo,
               COUNT(DISTINCT v.id_lote) AS lotes_riesgo,
               COALESCE(SUM(GREATEST(0, v.cantidad_disponible - COALESCE(d.diaria, 0) * GREATEST(0, v.dias_restantes))), 0) AS proy_unidades,
               COALESCE(SUM(GREATEST(0, v.cantidad_disponible - COALESCE(d.diaria, 0) * GREATEST(0, v.dias_restantes)) * v.costo_unitario), 0) AS proy_valor
        FROM operacion.v_inventario_lote v
        LEFT JOIN dem d ON d.id_sku = v.id_sku AND d.id_locacion = v.id_locacion
        WHERE v.cantidad_disponible > 0
          AND v.estado_lote = 'DISPONIBLE'
          AND v.clasificacion IN ('CRITICO', 'VIGILANCIA')
        """
    ) or {}

    evitado = resumen_desperdicio_evitado()["totales"]
    recuperado = a_float(evitado.get("recuperado"))
    contrafactual = a_float(evitado.get("contrafactual"))
    evitado_neto = a_float(evitado.get("evitado_neto"))
    valor_rec = a_float(evitado.get("valor"))

    tasa_reciente = tasa_merma(dias)
    tasa_historica = tasa_merma(180)
    tasa_rec_pct = a_float(tasa_reciente.get("tasa_pct"))
    tasa_hist_pct = a_float(tasa_historica.get("tasa_pct"))
    reduccion_pts = round(tasa_hist_pct - tasa_rec_pct, 2)

    factor_co2 = 2.5
    co2_evitado = round(evitado_neto * factor_co2, 2)

    return {
        "producto_en_riesgo": {
            "unidades": round(a_float(riesgo_actual.get("unidades_riesgo")), 2),
            "valor": round(a_float(riesgo_actual.get("valor_riesgo")), 2),
            "lotes": a_int(riesgo_actual.get("lotes_riesgo")),
            "definicion": "Existencia vigente en clasificación VIGILANCIA o CRÍTICO con probabilidad de caducar.",
        },
        "desperdicio_proyectado": {
            "unidades": round(a_float(riesgo_actual.get("proy_unidades")), 2),
            "valor": round(a_float(riesgo_actual.get("proy_valor")), 2),
            "definicion": "Cantidad estimada que se perdería si no se ejecuta ninguna intervención antes del vencimiento.",
        },
        "producto_recuperado": {
            "unidades": round(recuperado, 2),
            "valor": round(valor_rec, 2),
            "definicion": "Unidades efectivamente vendidas pertenecientes a lotes con transferencia ejecutada o descuento aprobado.",
        },
        "desperdicio_evitado_estimado": {
            "unidades": round(evitado_neto, 2),
            "contrafactual_organico": round(contrafactual, 2),
            "porcentaje_causal": round(100 * evitado_neto / recuperado, 1) if recuperado > 0 else 0.0,
            "definicion": "Diferencia neta frente a la línea base contrafactual sin intervención (excluye ventas orgánicas que habrían ocurrido a precio normal).",
        },
        "reduccion_observada_merma": {
            "tasa_reciente_pct": tasa_rec_pct,
            "tasa_base_historica_pct": tasa_hist_pct,
            "cambio_puntos_pct": reduccion_pts,
            "merma_reciente_unidades": a_float(tasa_reciente.get("mermado")),
            "ventana_dias": dias,
            "definicion": "Cambio empírico comprobado en las mermas registradas en PostgreSQL frente al histórico base.",
        },
        "co2e_evitado_estimado": {
            "kg_co2e": co2_evitado,
            "toneladas_co2e": round(co2_evitado / 1000.0, 4),
            "factor": "2.5 kg CO2e / kg alimento perecedero (referencia FAO)",
            "definicion": "Conversión ambiental calculada únicamente sobre el desperdicio evitado estimado neto (contrafactual).",
        },
    }


def kpis_sostenibilidad(dias: int = 180) -> dict:
    """Indicadores de sostenibilidad: separa recuperación bruta, neto contrafactual y merma observada."""
    completo = indicadores_desperdicio_completo(min(dias, 30))
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
    evitado_neto = a_float(evitado.get("evitado_neto"))
    mermado = a_float(merma.get("unidades"))
    total = recuperado + mermado

    return {
        "unidades_recuperadas": recuperado,
        "desperdicio_evitado_neto": evitado_neto,
        "unidades_mermadas": mermado,
        "valor_recuperado": a_float(evitado.get("valor")),
        "tasa_aprovechamiento": round(100 * recuperado / total, 1) if total else 0.0,
        "co2e_evitado_kg": completo["co2e_evitado_estimado"]["kg_co2e"],
        "completo": completo,
        "metodologia": completo["desperdicio_evitado_estimado"]["definicion"] + " " + completo["co2e_evitado_estimado"]["factor"],
    }
