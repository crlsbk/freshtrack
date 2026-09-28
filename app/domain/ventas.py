"""
Dominio de ventas.

Aquí vive el **FEFO transaccional**: una venta no es un registro contable
suelto, es una operación que consume inventario real lote por lote, empezando
por el que vence antes.

Ejemplo exigido por la rúbrica:

    Venta: 30 unidades
      Lote A → vence mañana    → 12 disponibles
      Lote B → vence en 3 días → 25 disponibles
      Lote C → vence en 8 días → 50 disponibles

    El sistema consume:  A → 12,  B → 18
    Y deja:              A → 0,   B → 7,   C → 50

Todo queda persistido en PostgreSQL: la venta, sus líneas, la existencia
actualizada y el movimiento de kardex, dentro de una sola transacción.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text

from app import auditoria
from app.db import a_float, one, query, transaccion


# ---------------------------------------------------------------------------
# Núcleo FEFO
# ---------------------------------------------------------------------------
def _lotes_para_consumo(conn, id_sku: int, id_locacion: int, bloquear: bool = True) -> list[dict]:
    """
    Lotes con existencia del producto en la tienda, ordenados por caducidad
    ascendente. Con `bloquear=True` se toma un lock de fila para que dos ventas
    simultáneas no puedan vender el mismo inventario.
    """
    sql = """
        SELECT e.id_existencia::text AS id_existencia,
               e.id_lote::text      AS id_lote,
               l.codigo_lote_prov,
               e.cantidad_disponible,
               e.cantidad_reservada,
               l.fecha_caducidad,
               (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
               l.costo_unitario
        FROM operacion.existencia e
        JOIN operacion.lote l ON l.id_lote = e.id_lote
        WHERE l.id_sku = :id_sku
          AND e.id_locacion = :id_locacion
          AND (e.cantidad_disponible - e.cantidad_reservada) > 0
          AND l.fecha_caducidad >= CURRENT_DATE
        ORDER BY l.fecha_caducidad ASC, l.codigo_lote_prov ASC
    """
    if bloquear:
        sql += " FOR UPDATE OF e"
    filas = conn.execute(
        text(sql), {"id_sku": id_sku, "id_locacion": id_locacion}
    ).mappings().all()
    return [dict(f) for f in filas]


def repartir_fefo(lotes: list[dict], cantidad: float) -> list[dict]:
    """
    Reparte una cantidad entre lotes en orden FEFO (función pura, sin BD).
    Devuelve la lista de consumos con el desglose y el sobrante.
    """
    restante = float(cantidad)
    consumos = []
    for lote in lotes:
        if restante <= 1e-9:
            break
        disponible = a_float(lote["cantidad_disponible"]) - a_float(
            lote.get("cantidad_reservada") or 0
        )
        if disponible <= 0:
            continue
        toma = min(disponible, restante)
        restante -= toma
        consumos.append(
            {
                "id_lote": lote["id_lote"],
                "codigo_lote_prov": lote.get("codigo_lote_prov"),
                "fecha_caducidad": lote.get("fecha_caducidad"),
                "dias_restantes": lote.get("dias_restantes"),
                "costo_unitario": a_float(lote.get("costo_unitario")),
                "disponible_antes": round(disponible, 2),
                "consumido": round(toma, 2),
                "disponible_despues": round(disponible - toma, 2),
            }
        )
    return consumos


def previsualizar_fefo(id_sku: int, id_locacion: int, cantidad: float) -> dict:
    """
    Muestra qué lotes consumiría una venta, SIN tocar la base.
    Sirve para que el operador vea el reparto antes de confirmar.
    """
    lotes = query(
        """
        SELECT e.id_lote::text AS id_lote, l.codigo_lote_prov,
               e.cantidad_disponible, e.cantidad_reservada,
               l.fecha_caducidad,
               (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
               l.costo_unitario
        FROM operacion.existencia e
        JOIN operacion.lote l ON l.id_lote = e.id_lote
        WHERE l.id_sku = :id_sku
          AND e.id_locacion = :id_locacion
          AND (e.cantidad_disponible - e.cantidad_reservada) > 0
          AND l.fecha_caducidad >= CURRENT_DATE
        ORDER BY l.fecha_caducidad ASC, l.codigo_lote_prov ASC
        """,
        id_sku=id_sku,
        id_locacion=id_locacion,
    )
    consumos = repartir_fefo(lotes, cantidad)
    cubierto = sum(c["consumido"] for c in consumos)
    return {
        "consumos": consumos,
        "solicitado": round(float(cantidad), 2),
        "cubierto": round(cubierto, 2),
        "faltante": round(float(cantidad) - cubierto, 2),
        "suficiente": cubierto >= float(cantidad) - 1e-9,
    }


# ---------------------------------------------------------------------------
# Registro de ventas
# ---------------------------------------------------------------------------
def registrar_venta(
    *,
    id_locacion: int,
    lineas: list[dict],
    usuario: dict,
    canal: str = "TIENDA",
) -> dict:
    """
    Registra una venta completa.

    `lineas` es una lista de {"id_sku": int, "cantidad": float}.

    Hace, en una sola transacción:
      1. Bloquea las existencias de cada producto.
      2. Verifica que haya inventario suficiente (si no, no escribe nada).
      3. Reparte la cantidad entre lotes en orden FEFO.
      4. Inserta la cabecera, las líneas, actualiza existencias y kardex.
    """
    if not lineas:
        raise ValueError("La venta no tiene líneas.")

    lineas_limpias = []
    for linea in lineas:
        cantidad = a_float(linea.get("cantidad"))
        if cantidad <= 0:
            continue
        lineas_limpias.append({"id_sku": int(linea["id_sku"]), "cantidad": cantidad})
    if not lineas_limpias:
        raise ValueError("La venta no tiene líneas con cantidad mayor que cero.")

    id_venta = str(uuid.uuid4())
    asignaciones: list[dict] = []
    total_venta = 0.0

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        folio = conn.execute(
            text("SELECT operacion.fn_generar_folio_venta(:l)"), {"l": id_locacion}
        ).scalar()

        conn.execute(
            text(
                """
                INSERT INTO operacion.venta
                    (id_venta, folio, id_locacion, id_usuario, canal, total)
                VALUES (CAST(:id_venta AS uuid), :folio, :id_locacion,
                        CAST(:uid AS uuid), :canal, 0)
                """
            ),
            {
                "id_venta": id_venta,
                "folio": folio,
                "id_locacion": id_locacion,
                "uid": usuario["id_usuario"],
                "canal": canal,
            },
        )

        for linea in lineas_limpias:
            id_sku = linea["id_sku"]
            cantidad = linea["cantidad"]

            producto = conn.execute(
                text(
                    "SELECT nombre, precio_venta, unidad_medida FROM operacion.producto "
                    "WHERE id_sku = :s"
                ),
                {"s": id_sku},
            ).mappings().first()
            if producto is None:
                raise ValueError(f"El producto {id_sku} no existe.")
            precio = a_float(producto["precio_venta"])

            lotes = _lotes_para_consumo(conn, id_sku, id_locacion, bloquear=True)
            consumos = repartir_fefo(lotes, cantidad)
            cubierto = sum(c["consumido"] for c in consumos)

            if cubierto < cantidad - 1e-9:
                raise ValueError(
                    f"Inventario insuficiente de «{producto['nombre']}» en esta tienda: "
                    f"se pidieron {cantidad:g} y solo hay {cubierto:g} unidades "
                    f"no vencidas. La venta no se registró."
                )

            for consumo in consumos:
                subtotal = round(consumo["consumido"] * precio, 2)
                total_venta += subtotal

                conn.execute(
                    text(
                        """
                        INSERT INTO operacion.venta_detalle
                            (id_venta, id_sku, id_lote, id_locacion, cantidad,
                             precio_unitario, subtotal)
                        VALUES (CAST(:id_venta AS uuid), :id_sku,
                                CAST(:id_lote AS uuid), :id_locacion, :cantidad,
                                :precio, :subtotal)
                        """
                    ),
                    {
                        "id_venta": id_venta,
                        "id_sku": id_sku,
                        "id_lote": consumo["id_lote"],
                        "id_locacion": id_locacion,
                        "cantidad": consumo["consumido"],
                        "precio": precio,
                        "subtotal": subtotal,
                    },
                )

                resultante = conn.execute(
                    text(
                        """
                        UPDATE operacion.existencia
                           SET cantidad_disponible = cantidad_disponible - :cantidad,
                               actualizado_en = now()
                         WHERE id_lote = CAST(:id_lote AS uuid)
                           AND id_locacion = :id_locacion
                        RETURNING cantidad_disponible
                        """
                    ),
                    {
                        "cantidad": consumo["consumido"],
                        "id_lote": consumo["id_lote"],
                        "id_locacion": id_locacion,
                    },
                ).scalar()

                conn.execute(
                    text(
                        """
                        INSERT INTO operacion.movimiento_inventario
                            (id_lote, id_locacion, tipo, cantidad, cantidad_resultante,
                             costo_unitario, referencia_tipo, referencia_id, id_usuario)
                        VALUES (CAST(:id_lote AS uuid), :id_locacion, 'VENTA',
                                :cantidad, :resultante, :costo, 'VENTA',
                                CAST(:id_venta AS uuid), CAST(:uid AS uuid))
                        """
                    ),
                    {
                        "id_lote": consumo["id_lote"],
                        "id_locacion": id_locacion,
                        "cantidad": -consumo["consumido"],
                        "resultante": a_float(resultante),
                        "costo": consumo["costo_unitario"],
                        "id_venta": id_venta,
                        "uid": usuario["id_usuario"],
                    },
                )

                asignaciones.append(
                    {
                        **consumo,
                        "id_sku": id_sku,
                        "producto": producto["nombre"],
                        "unidad_medida": producto["unidad_medida"],
                        "precio_unitario": precio,
                        "subtotal": subtotal,
                    }
                )

        conn.execute(
            text("UPDATE operacion.venta SET total = :t WHERE id_venta = CAST(:i AS uuid)"),
            {"t": round(total_venta, 2), "i": id_venta},
        )

    auditoria.registrar(
        "REGISTER_SALE",
        tabla="venta",
        id_registro=id_venta,
        descripcion=(
            f"Venta {folio} por {round(total_venta, 2)} — "
            + ", ".join(
                f"{a['producto']}: {a['consumido']:g} del lote {a['codigo_lote_prov']}"
                for a in asignaciones
            )
        ),
        estado_nuevo={
            "folio": folio,
            "id_locacion": id_locacion,
            "total": round(total_venta, 2),
            "lineas": len(lineas_limpias),
        },
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    return {
        "id_venta": id_venta,
        "folio": folio,
        "total": round(total_venta, 2),
        "asignaciones": asignaciones,
        "lotes_tocados": len(asignaciones),
    }


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
def ventas_recientes(
    id_locacion: int | None = None,
    texto: str | None = None,
    limite: int = 200,
) -> list[dict]:
    condiciones = []
    params: dict = {"limite": limite}
    if id_locacion:
        condiciones.append("v.id_locacion = :id_locacion")
        params["id_locacion"] = id_locacion
    if texto:
        condiciones.append(
            "(v.folio ILIKE :texto OR p.nombre ILIKE :texto OR l.codigo_lote_prov ILIKE :texto)"
        )
        params["texto"] = f"%{texto}%"
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    return query(
        f"""
        SELECT v.folio,
               v.fecha_venta,
               v.total,
               v.canal,
               loc.nombre AS locacion,
               vd.id_locacion,
               p.nombre   AS producto,
               p.id_sku,
               l.codigo_lote_prov AS lote,
               vd.cantidad,
               vd.precio_unitario,
               vd.subtotal,
               (l.fecha_caducidad - vd.fecha_transaccion::date) AS dias_margen
        FROM operacion.venta_detalle vd
        JOIN operacion.venta    v   ON v.id_venta = vd.id_venta
        JOIN operacion.producto p   ON p.id_sku = vd.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = vd.id_locacion
        LEFT JOIN operacion.lote l  ON l.id_lote = vd.id_lote
        {where}
        ORDER BY vd.fecha_transaccion DESC
        LIMIT :limite
        """,
        **params,
    )


def resumen_ventas(id_locacion: int | None = None) -> dict:
    filtro = "WHERE vd.id_locacion = :id_locacion" if id_locacion else ""
    params = {"id_locacion": id_locacion} if id_locacion else {}
    fila = one(
        f"""
        SELECT COALESCE(SUM(vd.cantidad), 0)  AS unidades,
               COALESCE(SUM(vd.subtotal), 0)  AS ingreso,
               COUNT(DISTINCT vd.id_venta)    AS tickets,
               COUNT(*)                       AS lineas
        FROM operacion.venta_detalle vd
        {filtro}
        """,
        **params,
    ) or {}
    tickets = int(fila.get("tickets") or 0)
    fila["ticket_promedio"] = round(a_float(fila.get("ingreso")) / tickets, 2) if tickets else 0.0
    return fila


def serie_demanda(
    id_sku: int | None = None,
    id_locacion: int | None = None,
    dias: int = 90,
) -> list[dict]:
    """Serie diaria real de demanda (Venta → Tienda → Producto → Cantidad → Fecha)."""
    condiciones = [f"fecha >= CURRENT_DATE - {int(dias)}"]
    params: dict = {}
    if id_sku:
        condiciones.append("id_sku = :id_sku")
        params["id_sku"] = id_sku
    if id_locacion:
        condiciones.append("id_locacion = :id_locacion")
        params["id_locacion"] = id_locacion
    return query(
        f"""
        SELECT fecha, SUM(cantidad) AS cantidad
        FROM analitica.v_demanda_diaria
        WHERE {' AND '.join(condiciones)}
        GROUP BY fecha
        ORDER BY fecha
        """,
        **params,
    )


def pares_con_historia(min_dias: int = 14) -> list[dict]:
    """
    Pares (producto, tienda) con suficiente historia para pronosticar.
    Es la lista que alimenta el motor de pronóstico.
    """
    return query(
        """
        SELECT d.id_sku, d.id_locacion,
               p.nombre AS producto, p.categoria, p.unidad_medida,
               loc.nombre AS locacion,
               COUNT(*)      AS dias_con_venta,
               SUM(d.cantidad) AS demanda_total,
               MAX(d.fecha)  AS ultima_venta
        FROM analitica.v_demanda_diaria d
        JOIN operacion.producto p   ON p.id_sku = d.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = d.id_locacion
        GROUP BY d.id_sku, d.id_locacion, p.nombre, p.categoria, p.unidad_medida, loc.nombre
        HAVING COUNT(*) >= :min_dias
        ORDER BY p.nombre, loc.nombre
        """,
        min_dias=min_dias,
    )
