"""
Dominio de mermas.

Flujo obligatorio (el que exige la rúbrica):

    tienda → producto → lote → cantidad → causa → validar existencia
          → registrar merma → descontar inventario → auditar

El mensaje de éxito solo se produce si el INSERT realmente ocurrió. Si la
existencia no alcanza, se levanta un error y **no se escribe nada**: no hay
forma de ver «Merma registrada correctamente» sin registro en PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy import text

from app import auditoria
from app.db import a_float, one, query, transaccion

# Las 7 causas mínimas exigidas, con su etiqueta para la interfaz
CAUSAS: list[dict] = [
    {"codigo": "CADUCIDAD", "etiqueta": "Caducidad", "color": "#f87171"},
    {"codigo": "DANO", "etiqueta": "Daño", "color": "#fb923c"},
    {"codigo": "CALIDAD", "etiqueta": "Calidad", "color": "#facc15"},
    {"codigo": "CADENA_DE_FRIO", "etiqueta": "Cadena de frío", "color": "#38bdf8"},
    {"codigo": "MANIPULACION", "etiqueta": "Manipulación", "color": "#a78bfa"},
    {"codigo": "DEVOLUCION", "etiqueta": "Devolución", "color": "#f472b6"},
    {"codigo": "OTRA", "etiqueta": "Otra", "color": "#94a3b8"},
]
CAUSAS_CODIGOS = [c["codigo"] for c in CAUSAS]
ETIQUETA_CAUSA = {c["codigo"]: c["etiqueta"] for c in CAUSAS}


def registrar_merma(
    *,
    id_lote: str,
    id_locacion: int,
    cantidad: float,
    causa: str,
    observacion: str | None,
    usuario: dict,
) -> dict:
    """
    Registra una merma real y descuenta el inventario.

    Todo ocurre dentro de una transacción: si la validación de existencia
    falla, no se inserta nada.
    """
    cantidad = a_float(cantidad)
    if cantidad <= 0:
        raise ValueError("La cantidad de merma debe ser mayor que cero.")
    if causa not in CAUSAS_CODIGOS:
        raise ValueError(
            f"Causa de merma no válida: {causa}. "
            f"Opciones: {', '.join(CAUSAS_CODIGOS)}"
        )

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        # --- Validar existencia (con lock para evitar carreras)
        existencia = conn.execute(
            text(
                """
                SELECT e.cantidad_disponible, l.costo_unitario, l.codigo_lote_prov,
                       l.fecha_caducidad, p.nombre AS producto, p.unidad_medida
                FROM operacion.existencia e
                JOIN operacion.lote l     ON l.id_lote = e.id_lote
                JOIN operacion.producto p ON p.id_sku = l.id_sku
                WHERE e.id_lote = CAST(:id_lote AS uuid)
                  AND e.id_locacion = :id_locacion
                FOR UPDATE OF e
                """
            ),
            {"id_lote": id_lote, "id_locacion": id_locacion},
        ).mappings().first()

        if existencia is None:
            raise ValueError(
                "Ese lote no tiene existencia registrada en la tienda seleccionada."
            )

        disponible = a_float(existencia["cantidad_disponible"])
        if disponible < cantidad - 1e-9:
            raise ValueError(
                f"No se puede registrar la merma: el lote "
                f"{existencia['codigo_lote_prov']} solo tiene {disponible:g} "
                f"{existencia['unidad_medida']} disponibles y se intentaron dar de baja "
                f"{cantidad:g}. No se guardó nada."
            )

        costo = a_float(existencia["costo_unitario"])
        restante = disponible - cantidad

        # --- Insertar la merma
        fila = conn.execute(
            text(
                """
                INSERT INTO operacion.merma
                    (id_lote, id_locacion, id_usuario, cantidad, causa_merma,
                     costo_unitario, observacion)
                VALUES (CAST(:id_lote AS uuid), :id_locacion, CAST(:uid AS uuid),
                        :cantidad, :causa, :costo, :observacion)
                RETURNING id_merma::text AS id_merma, valor_merma, fecha_registro
                """
            ),
            {
                "id_lote": id_lote,
                "id_locacion": id_locacion,
                "uid": usuario["id_usuario"],
                "cantidad": cantidad,
                "causa": causa,
                "costo": costo,
                "observacion": observacion,
            },
        ).mappings().first()

        # --- Descontar inventario
        conn.execute(
            text(
                """
                UPDATE operacion.existencia
                   SET cantidad_disponible = cantidad_disponible - :cantidad,
                       actualizado_en = now()
                 WHERE id_lote = CAST(:id_lote AS uuid)
                   AND id_locacion = :id_locacion
                """
            ),
            {"cantidad": cantidad, "id_lote": id_lote, "id_locacion": id_locacion},
        )

        # --- Kardex
        conn.execute(
            text(
                """
                INSERT INTO operacion.movimiento_inventario
                    (id_lote, id_locacion, tipo, cantidad, cantidad_resultante,
                     costo_unitario, referencia_tipo, referencia_id, id_usuario)
                VALUES (CAST(:id_lote AS uuid), :id_locacion, 'MERMA', :cantidad,
                        :resultante, :costo, 'MERMA', CAST(:id_merma AS uuid),
                        CAST(:uid AS uuid))
                """
            ),
            {
                "id_lote": id_lote,
                "id_locacion": id_locacion,
                "cantidad": -cantidad,
                "resultante": restante,
                "costo": costo,
                "id_merma": fila["id_merma"],
                "uid": usuario["id_usuario"],
            },
        )

        # --- Estado del lote
        if restante <= 1e-9:
            conn.execute(
                text(
                    """
                    UPDATE operacion.lote
                       SET estado = CASE
                             WHEN fecha_caducidad < CURRENT_DATE THEN 'VENCIDO'
                             WHEN :causa = 'CADUCIDAD'          THEN 'MERMA'
                             ELSE estado
                           END
                     WHERE id_lote = CAST(:id_lote AS uuid)
                    """
                ),
                {"id_lote": id_lote, "causa": causa},
            )

    auditoria.registrar(
        "REGISTER_SHRINKAGE",
        tabla="merma",
        id_registro=fila["id_merma"],
        descripcion=(
            f"Merma de {cantidad:g} {existencia['unidad_medida']} de "
            f"{existencia['producto']} (lote {existencia['codigo_lote_prov']}) "
            f"por {ETIQUETA_CAUSA[causa]}. Valor: {a_float(fila['valor_merma']):.2f}"
        ),
        estado_nuevo={
            "id_merma": fila["id_merma"],
            "cantidad": cantidad,
            "causa": causa,
            "costo_unitario": costo,
            "valor_merma": a_float(fila["valor_merma"]),
            "existencia_restante": round(restante, 2),
        },
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    return {
        "id_merma": fila["id_merma"],
        "cantidad": cantidad,
        "causa": causa,
        "causa_etiqueta": ETIQUETA_CAUSA[causa],
        "valor_merma": a_float(fila["valor_merma"]),
        "producto": existencia["producto"],
        "codigo_lote_prov": existencia["codigo_lote_prov"],
        "existencia_restante": round(restante, 2),
        "unidad_medida": existencia["unidad_medida"],
    }


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
def mermas_recientes(
    id_locacion: int | None = None,
    causa: str | None = None,
    id_sku: int | None = None,
    texto: str | None = None,
    limite: int = 200,
) -> list[dict]:
    condiciones = []
    params: dict = {"limite": limite}
    if id_locacion:
        condiciones.append("m.id_locacion = :id_locacion")
        params["id_locacion"] = id_locacion
    if causa:
        condiciones.append("m.causa_merma = :causa")
        params["causa"] = causa
    if id_sku:
        condiciones.append("l.id_sku = :id_sku")
        params["id_sku"] = id_sku
    if texto:
        condiciones.append(
            "(p.nombre ILIKE :texto OR l.codigo_lote_prov ILIKE :texto)"
        )
        params["texto"] = f"%{texto}%"
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    return query(
        f"""
        SELECT m.id_merma::text, m.fecha_registro, m.cantidad, m.causa_merma,
               m.costo_unitario, m.valor_merma, m.observacion,
               loc.nombre AS locacion, m.id_locacion,
               l.codigo_lote_prov, l.fecha_caducidad, l.id_sku,
               p.nombre AS producto, p.categoria, p.unidad_medida,
               u.nombre_completo AS responsable,
               (l.fecha_caducidad - m.fecha_registro::date) AS dias_vs_caducidad
        FROM operacion.merma m
        JOIN operacion.lote      l   ON l.id_lote = m.id_lote
        JOIN operacion.producto  p   ON p.id_sku = l.id_sku
        JOIN operacion.locacion  loc ON loc.id_locacion = m.id_locacion
        JOIN operacion.usuario   u   ON u.id_usuario = m.id_usuario
        {where}
        ORDER BY m.fecha_registro DESC
        LIMIT :limite
        """,
        **params,
    )


def resumen_mermas(dias: int = 90) -> dict:
    """Merma total, valorizada, por tienda, por SKU, por causa y por caducidad."""
    base = f"m.fecha_registro >= CURRENT_DATE - {int(dias)}"

    totales = one(
        f"""
        SELECT COALESCE(SUM(m.cantidad), 0)   AS unidades,
               COALESCE(SUM(m.valor_merma), 0) AS valor,
               COUNT(*)                        AS eventos
        FROM operacion.merma m
        WHERE {base}
        """
    ) or {}

    por_causa = query(
        f"""
        SELECT m.causa_merma AS causa,
               SUM(m.cantidad)    AS unidades,
               SUM(m.valor_merma) AS valor,
               COUNT(*)           AS eventos
        FROM operacion.merma m
        WHERE {base}
        GROUP BY m.causa_merma
        ORDER BY valor DESC
        """
    )

    por_tienda = query(
        f"""
        SELECT loc.nombre AS locacion, m.id_locacion,
               SUM(m.cantidad)    AS unidades,
               SUM(m.valor_merma) AS valor
        FROM operacion.merma m
        JOIN operacion.locacion loc ON loc.id_locacion = m.id_locacion
        WHERE {base}
        GROUP BY loc.nombre, m.id_locacion
        ORDER BY valor DESC
        """
    )

    por_sku = query(
        f"""
        SELECT p.nombre AS producto, p.id_sku, p.categoria,
               SUM(m.cantidad)    AS unidades,
               SUM(m.valor_merma) AS valor
        FROM operacion.merma m
        JOIN operacion.lote     l ON l.id_lote = m.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        WHERE {base}
        GROUP BY p.nombre, p.id_sku, p.categoria
        ORDER BY valor DESC
        LIMIT 10
        """
    )

    por_caducidad = one(
        f"""
        SELECT COALESCE(SUM(CASE WHEN m.causa_merma = 'CADUCIDAD'
                                 THEN m.cantidad END), 0)      AS unidades_caducidad,
               COALESCE(SUM(CASE WHEN m.causa_merma = 'CADUCIDAD'
                                 THEN m.valor_merma END), 0)   AS valor_caducidad,
               COALESCE(SUM(CASE WHEN m.causa_merma <> 'CADUCIDAD'
                                 THEN m.cantidad END), 0)      AS unidades_otras,
               COALESCE(SUM(CASE WHEN m.causa_merma <> 'CADUCIDAD'
                                 THEN m.valor_merma END), 0)   AS valor_otras
        FROM operacion.merma m
        WHERE {base}
        """
    ) or {}

    total_valor = a_float(totales.get("valor")) or 1.0
    for fila in por_causa:
        fila["etiqueta"] = ETIQUETA_CAUSA.get(fila["causa"], fila["causa"])
        fila["porcentaje"] = round(100 * a_float(fila["valor"]) / total_valor, 1)

    return {
        "totales": totales,
        "por_causa": por_causa,
        "por_tienda": por_tienda,
        "por_sku": por_sku,
        "por_caducidad": por_caducidad,
    }


def lotes_para_merma(id_locacion: int | None = None, id_sku: int | None = None) -> list[dict]:
    """Lotes con existencia para el formulario de merma."""
    condiciones = ["e.cantidad_disponible > 0"]
    params: dict = {}
    if id_locacion:
        condiciones.append("e.id_locacion = :id_locacion")
        params["id_locacion"] = id_locacion
    if id_sku:
        condiciones.append("l.id_sku = :id_sku")
        params["id_sku"] = id_sku
    return query(
        f"""
        SELECT e.id_lote::text AS id_lote, l.codigo_lote_prov,
               p.nombre AS producto, p.id_sku, p.unidad_medida,
               loc.nombre AS locacion, e.id_locacion,
               e.cantidad_disponible, l.fecha_caducidad,
               (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
               operacion.fn_clasificar_riesgo(
                   p.id_sku, p.categoria,
                   (l.fecha_caducidad - CURRENT_DATE)::numeric,
                   operacion.fn_vida_util_pct(
                       (l.fecha_caducidad - CURRENT_DATE)::numeric,
                       CASE WHEN l.fecha_produccion IS NOT NULL
                            THEN (l.fecha_caducidad - l.fecha_produccion)::numeric
                            ELSE p.vida_util_estandar::numeric END
                   )
               ) AS clasificacion
        FROM operacion.existencia e
        JOIN operacion.lote     l   ON l.id_lote = e.id_lote
        JOIN operacion.producto p   ON p.id_sku = l.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
        WHERE {' AND '.join(condiciones)}
        ORDER BY l.fecha_caducidad ASC
        """,
        **params,
    )
