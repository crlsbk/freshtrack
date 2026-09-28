"""
Dominio de inventario: lotes, recepción, existencias y vida útil.

Nada de lo que devuelven estas funciones viene precalculado: los días
restantes, el porcentaje de vida útil residual y la clasificación de riesgo
(NORMAL / VIGILANCIA / CRÍTICO / VENCIDO) los calcula PostgreSQL en el momento
de la consulta, a partir de operacion.regla_riesgo.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, one, query, transaccion

# ---------------------------------------------------------------------------
# Consultas de catálogo auxiliar
# ---------------------------------------------------------------------------
def productos_activos() -> list[dict]:
    return query(
        """
        SELECT p.id_sku, p.codigo_gtin, p.nombre, p.categoria, p.unidad_medida,
               p.vida_util_estandar, p.precio_costo, p.precio_venta,
               p.stock_seguridad, p.punto_reorden, p.id_proveedor,
               pr.razon_social AS proveedor, pr.lead_time_dias, pr.moq
        FROM operacion.producto p
        LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        WHERE p.activo
        ORDER BY p.nombre
        """
    )


def locaciones_activas(tipo: str | None = None) -> list[dict]:
    if tipo:
        return query(
            "SELECT id_locacion, nombre, tipo_locacion, ciudad "
            "FROM operacion.locacion WHERE activo AND tipo_locacion = :t "
            "ORDER BY tipo_locacion, nombre",
            t=tipo,
        )
    return query(
        "SELECT id_locacion, nombre, tipo_locacion, ciudad "
        "FROM operacion.locacion WHERE activo "
        "ORDER BY tipo_locacion, nombre"
    )


def proveedores_activos() -> list[dict]:
    return query(
        """
        SELECT id_proveedor, rfc, razon_social, lead_time_dias, moq,
               contacto_email, telefono
        FROM operacion.proveedor WHERE activo ORDER BY razon_social
        """
    )


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------
def inventario_por_lote(
    id_locacion: int | None = None,
    id_sku: int | None = None,
    clasificacion: str | None = None,
    solo_con_existencia: bool = True,
    texto: str | None = None,
    limite: int = 500,
) -> list[dict]:
    """
    Inventario real por lote: Producto → Tienda → Lote → Caducidad,
    con días restantes, vida útil residual y clasificación de riesgo.
    """
    condiciones = []
    params: dict = {"limite": limite}
    if solo_con_existencia:
        condiciones.append("cantidad_disponible > 0")
    if id_locacion:
        condiciones.append("id_locacion = :id_locacion")
        params["id_locacion"] = id_locacion
    if id_sku:
        condiciones.append("id_sku = :id_sku")
        params["id_sku"] = id_sku
    if clasificacion:
        condiciones.append("clasificacion = :clasificacion")
        params["clasificacion"] = clasificacion
    if texto:
        condiciones.append("(producto ILIKE :texto OR codigo_lote_prov ILIKE :texto)")
        params["texto"] = f"%{texto}%"

    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    return query(
        f"""
        SELECT id_existencia::text, id_lote::text, codigo_lote_prov, estado_lote,
               id_sku, producto, categoria, unidad_medida, vida_util_estandar,
               id_locacion, locacion, tipo_locacion,
               cantidad_disponible, cantidad_reservada, cantidad_util,
               fecha_produccion, fecha_recepcion, fecha_caducidad,
               costo_unitario, valor_inventario, dias_restantes,
               vida_util_total_dias, vida_util_pct, clasificacion,
               id_proveedor, proveedor, lead_time_dias
        FROM operacion.v_inventario_lote
        {where}
        ORDER BY clasificacion DESC, fecha_caducidad ASC, producto
        LIMIT :limite
        """,
        **params,
    )


def inventario_agrupado(
    id_locacion: int | None = None, texto: str | None = None
) -> list[dict]:
    """
    Inventario agrupado: producto → tienda → lote → caducidad.

    Devuelve la estructura que exige la rúbrica:

        MANZANA / TIENDA SAN PEDRO
          Lote A01  200 kg  vence 14 Sep
          Lote A02  350 kg  vence 17 Sep
          ------------------------------------
          Total     550 kg

    El total se calcula, no se almacena.
    """
    filas = inventario_por_lote(
        id_locacion=id_locacion, solo_con_existencia=True, texto=texto, limite=2000
    )

    grupos: dict[tuple, dict] = {}
    for f in filas:
        clave = (f["id_sku"], f["id_locacion"])
        grupo = grupos.setdefault(
            clave,
            {
                "id_sku": f["id_sku"],
                "producto": f["producto"],
                "categoria": f["categoria"],
                "unidad_medida": f["unidad_medida"],
                "id_locacion": f["id_locacion"],
                "locacion": f["locacion"],
                "tipo_locacion": f["tipo_locacion"],
                "lotes": [],
                "total": 0.0,
                "valor": 0.0,
                "en_riesgo": 0.0,
                "criticos": 0,
            },
        )
        grupo["lotes"].append(f)
        grupo["total"] += a_float(f["cantidad_disponible"])
        grupo["valor"] += a_float(f["valor_inventario"])
        if f["clasificacion"] in ("CRITICO", "VENCIDO"):
            grupo["en_riesgo"] += a_float(f["cantidad_disponible"])
            grupo["criticos"] += 1

    for grupo in grupos.values():
        grupo["lotes"].sort(key=lambda l: (l["fecha_caducidad"], l["codigo_lote_prov"]))
        grupo["total"] = round(grupo["total"], 2)
        grupo["valor"] = round(grupo["valor"], 2)
        grupo["en_riesgo"] = round(grupo["en_riesgo"], 2)
        grupo["n_lotes"] = len(grupo["lotes"])

    return sorted(grupos.values(), key=lambda g: (g["producto"], g["locacion"]))


def cola_fefo(id_locacion: int | None = None, limite: int = 200) -> list[dict]:
    """
    Cola FEFO: lotes con existencia ordenados por fecha de caducidad ascendente.
    Es el orden en el que el sistema debe consumir el inventario.
    """
    condicion = "AND id_locacion = :id_locacion" if id_locacion else ""
    params = {"id_locacion": id_locacion, "limite": limite} if id_locacion else {"limite": limite}
    return query(
        f"""
        SELECT id_lote::text, codigo_lote_prov, producto, id_sku, categoria,
               locacion, id_locacion, cantidad_disponible, unidad_medida,
               fecha_caducidad, dias_restantes, vida_util_pct, clasificacion,
               costo_unitario, proveedor
        FROM operacion.v_inventario_lote
        WHERE cantidad_disponible > 0
          AND dias_restantes >= 0
          {condicion}
        ORDER BY fecha_caducidad ASC, codigo_lote_prov
        LIMIT :limite
        """,
        **params,
    )


def lotes_fefo_disponibles(id_sku: int, id_locacion: int) -> list[dict]:
    """Lotes con existencia de un producto en una tienda, ordenados por FEFO."""
    return query(
        """
        SELECT id_lote::text, codigo_lote_prov, cantidad_disponible,
               fecha_caducidad, dias_restantes, clasificacion, costo_unitario
        FROM operacion.v_inventario_lote
        WHERE id_sku = :id_sku
          AND id_locacion = :id_locacion
          AND cantidad_disponible > 0
        ORDER BY fecha_caducidad ASC
        """,
        id_sku=id_sku,
        id_locacion=id_locacion,
    )


def stock_por_locacion(id_sku: int) -> list[dict]:
    """Existencia de un producto en todas las locaciones (para transferencias)."""
    return query(
        """
        SELECT id_locacion, locacion, tipo_locacion,
               SUM(cantidad_disponible) AS cantidad
        FROM operacion.v_inventario_lote
        WHERE id_sku = :id_sku AND cantidad_disponible > 0
        GROUP BY id_locacion, locacion, tipo_locacion
        ORDER BY cantidad DESC
        """,
        id_sku=id_sku,
    )


# ---------------------------------------------------------------------------
# Lotes
# ---------------------------------------------------------------------------
def listar_lotes(
    texto: str | None = None,
    clasificacion: str | None = None,
    id_locacion: int | None = None,
    solo_vigentes: bool = True,
    limite: int = 400,
) -> list[dict]:
    condiciones = []
    params: dict = {"limite": limite}
    if solo_vigentes:
        condiciones.append("dias_restantes >= -30")
    if clasificacion:
        condiciones.append("clasificacion = :clasificacion")
        params["clasificacion"] = clasificacion
    if texto:
        condiciones.append(
            "(producto ILIKE :texto OR codigo_lote_prov ILIKE :texto "
            "OR proveedor ILIKE :texto)"
        )
        params["texto"] = f"%{texto}%"

    filtro_loc = ""
    if id_locacion:
        filtro_loc = """
          AND EXISTS (
              SELECT 1 FROM operacion.existencia e
              WHERE e.id_lote = v.id_lote AND e.id_locacion = :id_locacion
          )
        """
        params["id_locacion"] = id_locacion

    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    return query(
        f"""
        SELECT v.id_lote::text, v.codigo_lote_prov, v.producto, v.id_sku, v.categoria,
               v.proveedor, v.fecha_produccion, v.fecha_recepcion, v.fecha_caducidad,
               v.cantidad_recibida, v.costo_unitario, v.dias_restantes,
               v.vida_util_pct, v.clasificacion, v.estado, v.existencia_total
        FROM operacion.v_lote_riesgo v
        {where}
        {filtro_loc}
        ORDER BY v.fecha_caducidad ASC
        LIMIT :limite
        """,
        **params,
    )


def obtener_lote(id_lote: str) -> dict | None:
    return one(
        """
        SELECT v.*, p.unidad_medida, p.precio_venta, p.vida_util_estandar,
               pr.moq, pr.lead_time_dias, pr.rfc
        FROM operacion.v_lote_riesgo v
        JOIN operacion.producto  p  ON p.id_sku = v.id_sku
        JOIN operacion.proveedor pr ON pr.id_proveedor = v.id_proveedor
        WHERE v.id_lote = CAST(:id_lote AS uuid)
        """,
        id_lote=id_lote,
    )


def registrar_recepcion(
    *,
    id_sku: int,
    id_proveedor: int,
    id_locacion: int,
    codigo_lote_prov: str,
    fecha_produccion: date | None,
    fecha_recepcion: date,
    fecha_caducidad: date,
    cantidad: float,
    costo_unitario: float,
    observaciones: str | None,
    usuario: dict,
) -> dict:
    """
    Da de alta un lote y su existencia inicial.

    Escribe en una sola transacción: lote + existencia + movimiento de kardex.
    Los triggers de auditoría registran CREATE_BATCH y CREATE_INVENTORY, y
    además se anota explícitamente RECEIVE_INVENTORY.
    """
    if cantidad <= 0:
        raise ValueError("La cantidad recibida debe ser mayor que cero.")
    if fecha_caducidad <= fecha_recepcion:
        raise ValueError("La fecha de caducidad debe ser posterior a la de recepción.")
    if fecha_produccion and fecha_produccion > fecha_recepcion:
        raise ValueError("La fecha de producción no puede ser posterior a la de recepción.")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        fila = conn.execute(
            text(
                """
                INSERT INTO operacion.lote
                    (id_sku, id_proveedor, codigo_lote_prov, fecha_produccion,
                     fecha_recepcion, fecha_caducidad, cantidad_recibida,
                     costo_unitario, id_locacion_recepcion, estado, observaciones)
                VALUES
                    (:id_sku, :id_proveedor, :codigo, :f_prod, :f_recep, :f_cad,
                     :cantidad, :costo, :id_locacion, 'DISPONIBLE', :obs)
                RETURNING id_lote::text AS id_lote
                """
            ),
            {
                "id_sku": id_sku,
                "id_proveedor": id_proveedor,
                "codigo": codigo_lote_prov.strip(),
                "f_prod": fecha_produccion,
                "f_recep": fecha_recepcion,
                "f_cad": fecha_caducidad,
                "cantidad": cantidad,
                "costo": costo_unitario,
                "id_locacion": id_locacion,
                "obs": observaciones,
            },
        ).mappings().first()
        id_lote = fila["id_lote"]

        conn.execute(
            text(
                """
                INSERT INTO operacion.existencia
                    (id_lote, id_locacion, cantidad_disponible, cantidad_reservada)
                VALUES (CAST(:id_lote AS uuid), :id_locacion, :cantidad, 0)
                ON CONFLICT (id_lote, id_locacion) DO UPDATE
                    SET cantidad_disponible =
                        operacion.existencia.cantidad_disponible + EXCLUDED.cantidad_disponible,
                        actualizado_en = now()
                """
            ),
            {"id_lote": id_lote, "id_locacion": id_locacion, "cantidad": cantidad},
        )

        conn.execute(
            text(
                """
                INSERT INTO operacion.movimiento_inventario
                    (id_lote, id_locacion, tipo, cantidad, cantidad_resultante,
                     costo_unitario, referencia_tipo, referencia_id, id_usuario)
                VALUES (CAST(:id_lote AS uuid), :id_locacion, 'RECEPCION',
                        :cantidad, :cantidad, :costo, 'LOTE',
                        CAST(:id_lote AS uuid), CAST(:uid AS uuid))
                """
            ),
            {
                "id_lote": id_lote,
                "id_locacion": id_locacion,
                "cantidad": cantidad,
                "costo": costo_unitario,
                "uid": usuario["id_usuario"],
            },
        )

    auditoria.registrar(
        "RECEIVE_INVENTORY",
        tabla="lote",
        id_registro=id_lote,
        descripcion=(
            f"Recepción de {cantidad:g} unidades del lote {codigo_lote_prov} "
            f"(SKU {id_sku}) en la locación {id_locacion}"
        ),
        estado_nuevo={
            "id_lote": id_lote,
            "id_sku": id_sku,
            "cantidad": cantidad,
            "fecha_caducidad": str(fecha_caducidad),
        },
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_lote": id_lote, "codigo_lote_prov": codigo_lote_prov}


# ---------------------------------------------------------------------------
# Trazabilidad
# ---------------------------------------------------------------------------
def trazabilidad(id_lote: str) -> dict:
    """Ciclo de vida completo de un lote: proveedor, recepción, ventas, mermas, transferencias."""
    lote = one(
        """
        SELECT l.id_lote::text, l.codigo_lote_prov, l.fecha_produccion,
               l.fecha_recepcion, l.fecha_caducidad, l.cantidad_recibida,
               l.costo_unitario, l.estado, l.observaciones,
               p.nombre AS producto, p.categoria, p.unidad_medida, p.id_sku,
               pr.razon_social AS proveedor, pr.rfc, pr.lead_time_dias,
               loc.nombre AS locacion_recepcion,
               v.dias_restantes, v.vida_util_pct, v.clasificacion, v.existencia_total
        FROM operacion.lote l
        JOIN operacion.producto  p  ON p.id_sku = l.id_sku
        JOIN operacion.proveedor pr ON pr.id_proveedor = l.id_proveedor
        LEFT JOIN operacion.locacion loc ON loc.id_locacion = l.id_locacion_recepcion
        LEFT JOIN operacion.v_lote_riesgo v ON v.id_lote = l.id_lote
        WHERE l.id_lote = CAST(:id_lote AS uuid)
        """,
        id_lote=id_lote,
    )
    if lote is None:
        return {}

    lotes_ = {"lote": lote}
    lotes_["existencias"] = query(
        """
        SELECT e.id_locacion, loc.nombre AS locacion, loc.tipo_locacion,
               e.cantidad_disponible, e.cantidad_reservada
        FROM operacion.existencia e
        JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
        WHERE e.id_lote = CAST(:id_lote AS uuid)
        ORDER BY e.cantidad_disponible DESC
        """,
        id_lote=id_lote,
    )
    lotes_["ventas"] = query(
        """
        SELECT v.folio, vd.fecha_transaccion, vd.cantidad, vd.precio_unitario,
               vd.subtotal, loc.nombre AS locacion
        FROM operacion.venta_detalle vd
        JOIN operacion.venta v ON v.id_venta = vd.id_venta
        JOIN operacion.locacion loc ON loc.id_locacion = vd.id_locacion
        WHERE vd.id_lote = CAST(:id_lote AS uuid)
        ORDER BY vd.fecha_transaccion DESC
        """,
        id_lote=id_lote,
    )
    lotes_["mermas"] = query(
        """
        SELECT m.fecha_registro, m.cantidad, m.causa_merma, m.valor_merma,
               loc.nombre AS locacion, u.nombre_completo AS responsable,
               m.observacion
        FROM operacion.merma m
        JOIN operacion.locacion loc ON loc.id_locacion = m.id_locacion
        JOIN operacion.usuario  u   ON u.id_usuario   = m.id_usuario
        WHERE m.id_lote = CAST(:id_lote AS uuid)
        ORDER BY m.fecha_registro DESC
        """,
        id_lote=id_lote,
    )
    lotes_["transferencias"] = query(
        """
        SELECT t.id_transferencia::text, t.estado, t.cantidad, t.motivo,
               t.fecha_creacion, t.fecha_decision, t.fecha_ejecucion,
               o.nombre AS origen, d.nombre AS destino
        FROM analitica.transferencia t
        JOIN operacion.locacion o ON o.id_locacion = t.id_locacion_origen
        JOIN operacion.locacion d ON d.id_locacion = t.id_locacion_destino
        WHERE t.id_lote = CAST(:id_lote AS uuid)
        ORDER BY t.fecha_creacion DESC
        """,
        id_lote=id_lote,
    )
    lotes_["movimientos"] = query(
        """
        SELECT mi.fecha, mi.tipo, mi.cantidad, mi.cantidad_resultante,
               loc.nombre AS locacion, u.nombre_completo AS usuario
        FROM operacion.movimiento_inventario mi
        JOIN operacion.locacion loc ON loc.id_locacion = mi.id_locacion
        LEFT JOIN operacion.usuario u ON u.id_usuario = mi.id_usuario
        WHERE mi.id_lote = CAST(:id_lote AS uuid)
        ORDER BY mi.fecha ASC, mi.id_movimiento ASC
        """,
        id_lote=id_lote,
    )

    vendido = sum(a_float(v["cantidad"]) for v in lotes_["ventas"])
    mermado = sum(a_float(m["cantidad"]) for m in lotes_["mermas"])
    recibido = a_float(lote["cantidad_recibida"])
    lotes_["resumen"] = {
        "recibido": round(recibido, 2),
        "vendido": round(vendido, 2),
        "mermado": round(mermado, 2),
        "existencia": round(a_float(lote["existencia_total"]), 2),
        "porcentaje_venta": round(100 * vendido / recibido, 1) if recibido else 0.0,
        "porcentaje_merma": round(100 * mermado / recibido, 1) if recibido else 0.0,
    }
    return lotes_


# ---------------------------------------------------------------------------
# Resúmenes
# ---------------------------------------------------------------------------
def resumen_inventario() -> dict:
    fila = one(
        """
        SELECT COALESCE(SUM(cantidad_disponible), 0)                    AS unidades,
               COALESCE(SUM(valor_inventario), 0)                       AS valor,
               COALESCE(SUM(CASE WHEN clasificacion = 'CRITICO'
                                 THEN cantidad_disponible END), 0)      AS criticas,
               COALESCE(SUM(CASE WHEN clasificacion = 'VIGILANCIA'
                                 THEN cantidad_disponible END), 0)      AS vigilancia,
               COALESCE(SUM(CASE WHEN clasificacion = 'VENCIDO'
                                 THEN cantidad_disponible END), 0)      AS vencidas,
               COUNT(DISTINCT id_lote)                                  AS lotes,
               COUNT(DISTINCT id_sku)                                   AS skus,
               COUNT(DISTINCT id_locacion)                              AS locaciones
        FROM operacion.v_inventario_lote
        WHERE cantidad_disponible > 0
        """
    ) or {}
    return fila
