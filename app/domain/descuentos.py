"""
Dominio de descuentos.

Para los lotes que se acercan a su caducidad y que no alcanzarán a venderse a
precio completo, el sistema propone un descuento. Igual que el reabastecimiento
y las transferencias, la propuesta requiere aprobación humana antes de
considerarse una decisión comercial.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, config_valor, one, query, transaccion


def _json(valor) -> str:
    return json.dumps(valor, default=str, ensure_ascii=False)


def sugerir_descuentos(*, usuario: dict, dias_hasta: int | None = None) -> dict:
    """
    Genera sugerencias de descuento para los lotes próximos a vencer que
    tienen existencia y riesgo de no venderse.
    """
    if dias_hasta is None:
        dias_hasta = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)

    pct_critico = a_float(config_valor("descuento_pct_critico", "30")) or 30.0
    pct_vigilancia = a_float(config_valor("descuento_pct_vigilancia", "15")) or 15.0

    candidatos = query(
        """
        SELECT v.id_lote::text, v.codigo_lote_prov, v.producto, v.id_sku,
               v.id_locacion, v.locacion, v.cantidad_disponible, v.unidad_medida,
               v.fecha_caducidad, v.dias_restantes, v.clasificacion, v.vida_util_pct,
               p.precio_venta, p.precio_costo
        FROM operacion.v_inventario_lote v
        JOIN operacion.producto p ON p.id_sku = v.id_sku
        WHERE v.cantidad_disponible > 0
          AND v.dias_restantes BETWEEN 0 AND :dias
          AND v.clasificacion IN ('VIGILANCIA', 'CRITICO')
        ORDER BY v.fecha_caducidad ASC
        """,
        dias=dias_hasta,
    )

    generados = []
    for c in candidatos:
        existente = one(
            """
            SELECT id_descuento::text FROM analitica.descuento
            WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc
              AND estado IN ('SUGERIDO', 'APROBADO')
            LIMIT 1
            """,
            lote=c["id_lote"],
            loc=c["id_locacion"],
        )
        if existente:
            continue

        pct = pct_critico if c["clasificacion"] == "CRITICO" else pct_vigilancia
        precio_normal = a_float(c["precio_venta"])
        precio_nuevo = round(precio_normal * (1 - pct / 100), 2)
        cantidad = a_float(c["cantidad_disponible"])
        ingreso = round(cantidad * precio_nuevo, 2)

        with transaccion(
            id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
        ) as conn:
            id_descuento = conn.execute(
                text(
                    """
                    INSERT INTO analitica.descuento
                        (id_lote, id_locacion, descuento_pct, precio_normal, precio_nuevo,
                         cantidad, dias_restantes, ingreso_potencial, estado,
                         id_usuario_solicita)
                    VALUES
                        (CAST(:lote AS uuid), :loc, :pct, :normal, :nuevo, :cantidad,
                         :dias, :ingreso, 'SUGERIDO', CAST(:uid AS uuid))
                    RETURNING id_descuento::text
                    """
                ),
                {
                    "lote": c["id_lote"],
                    "loc": c["id_locacion"],
                    "pct": pct,
                    "normal": precio_normal,
                    "nuevo": precio_nuevo,
                    "cantidad": cantidad,
                    "dias": a_int(c["dias_restantes"], 0),
                    "ingreso": ingreso,
                    "uid": usuario["id_usuario"],
                },
            ).scalar()

        generados.append(
            {
                "id_descuento": id_descuento,
                "producto": c["producto"],
                "locacion": c["locacion"],
                "descuento_pct": pct,
                "cantidad": cantidad,
            }
        )

        auditoria.registrar(
            "CREATE_DISCOUNT",
            tabla="descuento",
            id_registro=id_descuento,
            descripcion=(
                f"Descuento sugerido del {pct:g}% para el lote {c['codigo_lote_prov']} "
                f"de {c['producto']} en {c['locacion']} "
                f"({cantidad:g} {c['unidad_medida']}, vence en {c['dias_restantes']} días)"
            ),
            estado_nuevo={
                "id_lote": c["id_lote"],
                "descuento_pct": pct,
                "cantidad": cantidad,
                "precio_nuevo": precio_nuevo,
            },
            id_usuario=usuario["id_usuario"],
            usuario_email=usuario["email"],
        )

    return {"generados": generados, "total": len(generados)}


def listar_descuentos(estado: str | None = None, limite: int = 100) -> list[dict]:
    filtro = "WHERE d.estado = :estado" if estado else ""
    params = {"estado": estado, "limite": limite} if estado else {"limite": limite}
    return query(
        f"""
        SELECT d.id_descuento::text, d.estado, d.descuento_pct, d.precio_normal,
               d.precio_nuevo, d.cantidad, d.dias_restantes, d.ingreso_potencial,
               d.fecha_creacion, d.fecha_decision,
               p.nombre AS producto, p.id_sku, p.unidad_medida, p.precio_costo,
               l.codigo_lote_prov, l.fecha_caducidad,
               loc.nombre AS locacion, loc.id_locacion,
               us.nombre_completo AS solicita, ua.nombre_completo AS aprueba
        FROM analitica.descuento d
        JOIN operacion.lote     l   ON l.id_lote = d.id_lote
        JOIN operacion.producto p   ON p.id_sku = l.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = d.id_locacion
        LEFT JOIN operacion.usuario us ON us.id_usuario = d.id_usuario_solicita
        LEFT JOIN operacion.usuario ua ON ua.id_usuario = d.id_usuario_aprueba
        {filtro}
        ORDER BY d.fecha_creacion DESC
        LIMIT :limite
        """,
        **params,
    )


def decidir_descuento(id_descuento: str, *, aprobar: bool, usuario: dict) -> dict:
    d = one(
        """
        SELECT d.id_descuento::text, d.estado, d.descuento_pct, d.cantidad,
               p.nombre AS producto, loc.nombre AS locacion
        FROM analitica.descuento d
        JOIN operacion.lote l       ON l.id_lote = d.id_lote
        JOIN operacion.producto p   ON p.id_sku = l.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = d.id_locacion
        WHERE d.id_descuento = CAST(:id AS uuid)
        """,
        id=id_descuento,
    )
    if d is None:
        raise ValueError("El descuento no existe.")
    if d["estado"] not in ("SUGERIDO", "APROBADO"):
        raise ValueError(f"El descuento ya está en estado {d['estado']}.")

    estado = "APROBADO" if aprobar else "RECHAZADO"
    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE analitica.descuento
                   SET estado = :estado, id_usuario_aprueba = CAST(:uid AS uuid),
                       fecha_decision = now()
                 WHERE id_descuento = CAST(:id AS uuid)
                """
            ),
            {"estado": estado, "uid": usuario["id_usuario"], "id": id_descuento},
        )

    auditoria.registrar(
        "APPROVE_DISCOUNT" if aprobar else "REJECT_DISCOUNT",
        tabla="descuento",
        id_registro=id_descuento,
        descripcion=(
            f"{'Aprobado' if aprobar else 'Rechazado'} el descuento del "
            f"{a_float(d['descuento_pct']):g}% para {d['producto']} en {d['locacion']}"
        ),
        estado_anterior={"estado": d["estado"]},
        estado_nuevo={"estado": estado},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_descuento": id_descuento, "estado": estado}


def resumen_descuentos() -> dict:
    return one(
        """
        SELECT COUNT(*) FILTER (WHERE estado = 'SUGERIDO') AS sugeridos,
               COUNT(*) FILTER (WHERE estado = 'APROBADO') AS aprobados,
               COUNT(*) FILTER (WHERE estado = 'RECHAZADO') AS rechazados,
               COALESCE(SUM(CASE WHEN estado = 'SUGERIDO'
                                 THEN ingreso_potencial END), 0) AS ingreso_potencial,
               COALESCE(SUM(CASE WHEN estado = 'SUGERIDO'
                                 THEN cantidad END), 0) AS unidades
        FROM analitica.descuento
        """
    ) or {}
