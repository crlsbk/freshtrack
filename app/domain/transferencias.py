"""
Motor de transferencias entre tiendas.

Detecta dos situaciones complementarias:

    Tienda A → exceso de inventario útil o riesgo de caducidad
    Tienda B → faltante contra la demanda esperada

y propone el traslado. Pero **no propone nada sin validarlo antes**:

    1. ¿La tienda de origen tiene inventario suficiente?
    2. ¿La tienda de destino realmente lo necesita?
    3. ¿El producto llegará antes de vencer?
    4. ¿La demanda prevista del destino permite consumirlo?

Cada transferencia queda en estado SUGERIDA hasta que una persona la aprueba.
Al ejecutarse mueve inventario real (existencia + kardex) entre las dos tiendas.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, config_valor, one, query, transaccion
from app.domain import inventario, pronostico

# Días que se asumen de traslado entre tiendas (no hay optimización logística
# todavía: es una constante explícita y documentada).
DIAS_TRANSITO = 1


def _json(valor) -> str:
    return json.dumps(valor, default=str, ensure_ascii=False)


def _situacion(id_sku: int, id_locacion: int, horizonte: int) -> dict:
    """Inventario útil, demanda esperada y exceso/faltante de un producto en una tienda."""
    lotes = query(
        """
        SELECT id_lote::text, codigo_lote_prov, cantidad_disponible,
               (fecha_caducidad - CURRENT_DATE) AS dias_restantes, clasificacion,
               costo_unitario
        FROM operacion.v_inventario_lote
        WHERE id_sku = :sku AND id_locacion = :loc AND cantidad_disponible > 0
        ORDER BY fecha_caducidad ASC
        """,
        sku=id_sku,
        loc=id_locacion,
    )
    promedio_diario = pronostico.demanda_diaria_promedio(id_sku, id_locacion, 28)
    dias_riesgo = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)

    fisico = 0.0
    en_riesgo = 0.0
    for lote in lotes:
        disponible = a_float(lote["cantidad_disponible"])
        fisico += disponible
        dias = a_int(lote["dias_restantes"], 0)
        demanda_antes = promedio_diario * min(max(dias, 0), dias_riesgo)
        en_riesgo += max(0.0, disponible - demanda_antes)

    util = round(fisico - en_riesgo, 2)
    demanda_horizonte = round(promedio_diario * horizonte, 2)
    return {
        "id_locacion": id_locacion,
        "lotes": lotes,
        "fisico": round(fisico, 2),
        "en_riesgo": round(en_riesgo, 2),
        "util": util,
        "demanda_diaria": round(promedio_diario, 2),
        "demanda_horizonte": demanda_horizonte,
        "exceso": round(max(0.0, util - demanda_horizonte), 2),
        "faltante": round(max(0.0, demanda_horizonte - util), 2),
    }


def detectar_oportunidades(
    *, usuario: dict, horizonte: int | None = None, minimo: float = 5.0
) -> dict:
    """
    Busca pares (origen con exceso → destino con faltante) para cada producto
    y registra las transferencias sugeridas que pasan las validaciones.
    """
    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)

    tiendas = inventario.locaciones_activas("Tienda")
    if len(tiendas) < 2:
        return {"sugeridas": [], "total": 0}

    productos = query(
        """
        SELECT DISTINCT d.id_sku, p.nombre AS producto, p.unidad_medida,
               p.vida_util_estandar, p.stock_seguridad
        FROM analitica.v_demanda_diaria d
        JOIN operacion.producto p ON p.id_sku = d.id_sku
        WHERE d.fecha >= CURRENT_DATE - 60 AND p.activo
        ORDER BY p.nombre
        """
    )

    sugeridas = []
    descartadas = 0

    for producto in productos:
        id_sku = producto["id_sku"]
        situaciones = {}
        for tienda in tiendas:
            s = _situacion(id_sku, tienda["id_locacion"], horizonte)
            s["nombre"] = tienda["nombre"]
            situaciones[tienda["id_locacion"]] = s

        origenes = [s for s in situaciones.values() if s["exceso"] > 0]
        destinos = [s for s in situaciones.values() if s["faltante"] > 0]
        if not origenes or not destinos:
            continue

        for destino in destinos:
            for origen in origenes:
                if origen["id_locacion"] == destino["id_locacion"]:
                    continue

                cantidad = round(min(origen["exceso"], destino["faltante"]), 2)
                if cantidad < minimo:
                    continue

                # --- Validaciones explícitas
                lote = next(
                    (l for l in origen["lotes"] if a_float(l["cantidad_disponible"]) >= cantidad),
                    origen["lotes"][0] if origen["lotes"] else None,
                )
                if lote is None:
                    descartadas += 1
                    continue

                disponible_lote = a_float(lote["cantidad_disponible"])
                dias_para_vencer = a_int(lote["dias_restantes"], 0)

                v1_origen = disponible_lote >= cantidad
                v2_destino = destino["faltante"] > 0
                v3_vigencia = dias_para_vencer > DIAS_TRANSITO
                demanda_util = destino["demanda_diaria"] * max(0, dias_para_vencer - DIAS_TRANSITO)
                v4_consumo = demanda_util >= cantidad

                validaciones = {
                    "origen_suficiente": {
                        "pasa": v1_origen,
                        "detalle": f"{origen['nombre']} tiene {disponible_lote:g} unidades del lote {lote['codigo_lote_prov']}",
                    },
                    "destino_necesita": {
                        "pasa": v2_destino,
                        "detalle": f"{destino['nombre']} tiene un faltante de {destino['faltante']:g} unidades",
                    },
                    "llega_antes_de_vencer": {
                        "pasa": v3_vigencia,
                        "detalle": (
                            f"El lote vence en {dias_para_vencer} días y el traslado toma "
                            f"{DIAS_TRANSITO} día(s)"
                        ),
                    },
                    "destino_puede_consumirlo": {
                        "pasa": v4_consumo,
                        "detalle": (
                            f"Con {destino['demanda_diaria']:g} unidades/día de demanda, "
                            f"{destino['nombre']} alcanzaría a vender {round(demanda_util, 2):g} "
                            f"antes de que el lote venza"
                        ),
                    },
                }

                if not all(v["pasa"] for v in validaciones.values()):
                    descartadas += 1
                    continue

                # ¿Ya existe una sugerencia pendiente igual?
                existente = one(
                    """
                    SELECT id_transferencia::text FROM analitica.transferencia
                    WHERE id_sku = :sku AND id_lote = CAST(:lote AS uuid)
                      AND id_locacion_destino = :destino AND estado IN ('SUGERIDA','APROBADA')
                    LIMIT 1
                    """,
                    sku=id_sku,
                    lote=lote["id_lote"],
                    destino=destino["id_locacion"],
                )
                if existente:
                    continue

                motivo = (
                    f"{origen['nombre']} tiene {origen['exceso']:g} unidades de exceso útil; "
                    f"{destino['nombre']} tiene un faltante de {destino['faltante']:g} unidades "
                    f"para los próximos {horizonte} días"
                )

                with transaccion(
                    id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
                ) as conn:
                    id_transferencia = conn.execute(
                        text(
                            """
                            INSERT INTO analitica.transferencia
                                (id_sku, id_lote, id_locacion_origen, id_locacion_destino,
                                 cantidad, motivo, exceso_origen, faltante_destino,
                                 dias_para_vencer, validaciones, estado, id_usuario_solicita)
                            VALUES
                                (:sku, CAST(:lote AS uuid), :origen, :destino, :cantidad,
                                 :motivo, :exceso, :faltante, :dias, CAST(:validaciones AS jsonb),
                                 'SUGERIDA', CAST(:uid AS uuid))
                            RETURNING id_transferencia::text
                            """
                        ),
                        {
                            "sku": id_sku,
                            "lote": lote["id_lote"],
                            "origen": origen["id_locacion"],
                            "destino": destino["id_locacion"],
                            "cantidad": cantidad,
                            "motivo": motivo,
                            "exceso": origen["exceso"],
                            "faltante": destino["faltante"],
                            "dias": dias_para_vencer,
                            "validaciones": _json(validaciones),
                            "uid": usuario["id_usuario"],
                        },
                    ).scalar()

                sugeridas.append(
                    {
                        "id_transferencia": id_transferencia,
                        "producto": producto["producto"],
                        "origen": origen["nombre"],
                        "destino": destino["nombre"],
                        "cantidad": cantidad,
                        "dias_para_vencer": dias_para_vencer,
                    }
                )

                auditoria.registrar(
                    "CREATE_TRANSFER",
                    tabla="transferencia",
                    id_registro=id_transferencia,
                    descripcion=(
                        f"Transferencia sugerida: {origen['nombre']} → {destino['nombre']} · "
                        f"{cantidad:g} {producto['unidad_medida']} de {producto['producto']} "
                        f"(lote {lote['codigo_lote_prov']}, vence en {dias_para_vencer} días)"
                    ),
                    estado_nuevo={
                        "id_sku": id_sku,
                        "id_lote": lote["id_lote"],
                        "cantidad": cantidad,
                        "origen": origen["id_locacion"],
                        "destino": destino["id_locacion"],
                    },
                    id_usuario=usuario["id_usuario"],
                    usuario_email=usuario["email"],
                )

    return {"sugeridas": sugeridas, "total": len(sugeridas), "descartadas": descartadas}


def listar_transferencias(estado: str | None = None, limite: int = 100) -> list[dict]:
    filtro = "WHERE t.estado = :estado" if estado else ""
    params = {"estado": estado, "limite": limite} if estado else {"limite": limite}
    return query(
        f"""
        SELECT t.id_transferencia::text, t.estado, t.cantidad, t.motivo,
               t.exceso_origen, t.faltante_destino, t.dias_para_vencer,
               t.validaciones, t.fecha_creacion, t.fecha_decision, t.fecha_ejecucion,
               p.nombre AS producto, p.id_sku, p.unidad_medida,
               l.codigo_lote_prov, l.fecha_caducidad,
               o.nombre AS origen, o.id_locacion AS id_origen,
               d.nombre AS destino, d.id_locacion AS id_destino,
               us.nombre_completo AS solicita,
               ua.nombre_completo AS aprueba
        FROM analitica.transferencia t
        JOIN operacion.producto  p ON p.id_sku = t.id_sku
        JOIN operacion.locacion  o ON o.id_locacion = t.id_locacion_origen
        JOIN operacion.locacion  d ON d.id_locacion = t.id_locacion_destino
        LEFT JOIN operacion.lote l ON l.id_lote = t.id_lote
        LEFT JOIN operacion.usuario us ON us.id_usuario = t.id_usuario_solicita
        LEFT JOIN operacion.usuario ua ON ua.id_usuario = t.id_usuario_aprueba
        {filtro}
        ORDER BY t.fecha_creacion DESC
        LIMIT :limite
        """,
        **params,
    )


def decidir_transferencia(
    id_transferencia: str, *, aprobar: bool, usuario: dict, cantidad: float | None = None
) -> dict:
    """Aprueba o rechaza una transferencia sugerida."""
    tr = one(
        """
        SELECT t.id_transferencia::text, t.estado, t.cantidad, t.id_sku, t.id_lote,
               p.nombre AS producto, o.nombre AS origen, d.nombre AS destino
        FROM analitica.transferencia t
        JOIN operacion.producto p ON p.id_sku = t.id_sku
        JOIN operacion.locacion o ON o.id_locacion = t.id_locacion_origen
        JOIN operacion.locacion d ON d.id_locacion = t.id_locacion_destino
        WHERE t.id_transferencia = CAST(:id AS uuid)
        """,
        id=id_transferencia,
    )
    if tr is None:
        raise ValueError("La transferencia no existe.")
    if tr["estado"] not in ("SUGERIDA", "APROBADA"):
        raise ValueError(f"La transferencia ya está en estado {tr['estado']}.")

    nueva = a_float(cantidad) if cantidad is not None else a_float(tr["cantidad"])
    estado = "APROBADA" if aprobar else "RECHAZADA"

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE analitica.transferencia
                   SET estado = :estado,
                       cantidad = CASE WHEN :aprobar THEN :cantidad ELSE cantidad END,
                       id_usuario_aprueba = CAST(:uid AS uuid),
                       fecha_decision = now()
                 WHERE id_transferencia = CAST(:id AS uuid)
                """
            ),
            {
                "estado": estado,
                "aprobar": aprobar,
                "cantidad": nueva,
                "uid": usuario["id_usuario"],
                "id": id_transferencia,
            },
        )

    auditoria.registrar(
        "APPROVE_TRANSFER" if aprobar else "REJECT_TRANSFER",
        tabla="transferencia",
        id_registro=id_transferencia,
        descripcion=(
            f"{'Aprobada' if aprobar else 'Rechazada'} la transferencia de "
            f"{tr['producto']}: {tr['origen']} → {tr['destino']}"
            + (f" por {nueva:g} unidades" if aprobar else "")
        ),
        estado_anterior={"estado": tr["estado"]},
        estado_nuevo={"estado": estado, "cantidad": nueva if aprobar else None},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_transferencia": id_transferencia, "estado": estado, "cantidad": nueva}


def ejecutar_transferencia(id_transferencia: str, *, usuario: dict) -> dict:
    """
    Mueve el inventario de verdad: descuenta en el origen, suma en el destino
    y deja los dos movimientos en el kardex.
    """
    tr = one(
        """
        SELECT t.id_transferencia::text, t.estado, t.cantidad, t.id_sku, t.id_lote,
               t.id_locacion_origen, t.id_locacion_destino, t.fecha_creacion,
               p.nombre AS producto, p.unidad_medida,
               l.codigo_lote_prov, l.costo_unitario, l.fecha_caducidad,
               (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
               o.nombre AS origen, d.nombre AS destino
        FROM analitica.transferencia t
        JOIN operacion.producto p ON p.id_sku = t.id_sku
        JOIN operacion.lote l     ON l.id_lote = t.id_lote
        JOIN operacion.locacion o ON o.id_locacion = t.id_locacion_origen
        JOIN operacion.locacion d ON d.id_locacion = t.id_locacion_destino
        WHERE t.id_transferencia = CAST(:id AS uuid)
        """,
        id=id_transferencia,
    )
    if tr is None:
        raise ValueError("La transferencia no existe.")
    if tr["estado"] != "APROBADA":
        raise ValueError(
            f"Solo se pueden ejecutar transferencias aprobadas (estado actual: {tr['estado']})."
        )

    cantidad = a_float(tr["cantidad"])
    costo = a_float(tr["costo_unitario"])

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        origen = conn.execute(
            text(
                """
                SELECT cantidad_disponible FROM operacion.existencia
                WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc
                FOR UPDATE
                """
            ),
            {"lote": tr["id_lote"], "loc": tr["id_locacion_origen"]},
        ).mappings().first()

        disponible = a_float(origen["cantidad_disponible"]) if origen else 0.0
        if disponible < cantidad - 1e-9:
            raise ValueError(
                f"El origen ya no tiene inventario suficiente: {disponible:g} disponibles "
                f"contra {cantidad:g} solicitadas."
            )

        resultante_origen = conn.execute(
            text(
                """
                UPDATE operacion.existencia
                   SET cantidad_disponible = cantidad_disponible - :cantidad,
                       actualizado_en = now()
                 WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc
                RETURNING cantidad_disponible
                """
            ),
            {"cantidad": cantidad, "lote": tr["id_lote"], "loc": tr["id_locacion_origen"]},
        ).scalar()

        resultante_destino = conn.execute(
            text(
                """
                INSERT INTO operacion.existencia
                    (id_lote, id_locacion, cantidad_disponible, cantidad_reservada)
                VALUES (CAST(:lote AS uuid), :loc, :cantidad, 0)
                ON CONFLICT (id_lote, id_locacion) DO UPDATE
                    SET cantidad_disponible =
                        operacion.existencia.cantidad_disponible + EXCLUDED.cantidad_disponible,
                        actualizado_en = now()
                RETURNING cantidad_disponible
                """
            ),
            {"lote": tr["id_lote"], "loc": tr["id_locacion_destino"], "cantidad": cantidad},
        ).scalar()

        for tipo, loc, signo, resultante in (
            ("TRANSFERENCIA_SALIDA", tr["id_locacion_origen"], -1, resultante_origen),
            ("TRANSFERENCIA_ENTRADA", tr["id_locacion_destino"], 1, resultante_destino),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO operacion.movimiento_inventario
                        (id_lote, id_locacion, tipo, cantidad, cantidad_resultante,
                         costo_unitario, referencia_tipo, referencia_id, id_usuario)
                    VALUES (CAST(:lote AS uuid), :loc, :tipo, :cantidad, :resultante,
                            :costo, 'TRANSFERENCIA', CAST(:id AS uuid), CAST(:uid AS uuid))
                    """
                ),
                {
                    "lote": tr["id_lote"],
                    "loc": loc,
                    "tipo": tipo,
                    "cantidad": signo * cantidad,
                    "resultante": a_float(resultante),
                    "costo": costo,
                    "id": id_transferencia,
                    "uid": usuario["id_usuario"],
                },
            )

        conn.execute(
            text(
                """
                UPDATE analitica.transferencia
                   SET estado = 'EJECUTADA', fecha_ejecucion = now()
                 WHERE id_transferencia = CAST(:id AS uuid)
                """
            ),
            {"id": id_transferencia},
        )

        # Registro del desperdicio evitado con su metodología
        conn.execute(
            text(
                """
                INSERT INTO analitica.desperdicio_evitado
                    (tipo_intervencion, id_transferencia, id_lote, id_locacion,
                     cantidad_en_riesgo, cantidad_intervenida, cantidad_recuperada,
                     cantidad_mermada, valor_recuperado, metodologia)
                VALUES
                    ('TRANSFERENCIA', CAST(:id AS uuid), CAST(:lote AS uuid), :origen,
                     :en_riesgo, :intervenida, 0, 0, 0, :metodologia)
                """
            ),
            {
                "id": id_transferencia,
                "lote": tr["id_lote"],
                "origen": tr["id_locacion_origen"],
                "en_riesgo": cantidad,
                "intervenida": cantidad,
                "metodologia": (
                    "Se registran las unidades que se movieron antes de vencer. La cantidad "
                    "recuperada se calcula después como las unidades de ese lote efectivamente "
                    "vendidas en la tienda destino entre la ejecución y la fecha de caducidad."
                ),
            },
        )

    auditoria.registrar(
        "EXECUTE_TRANSFER",
        tabla="transferencia",
        id_registro=id_transferencia,
        descripcion=(
            f"Transferencia ejecutada: {cantidad:g} {tr['unidad_medida']} de "
            f"{tr['producto']} (lote {tr['codigo_lote_prov']}) de {tr['origen']} "
            f"a {tr['destino']}"
        ),
        estado_anterior={"estado": "APROBADA"},
        estado_nuevo={"estado": "EJECUTADA", "cantidad": cantidad},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    return {
        "id_transferencia": id_transferencia,
        "cantidad": cantidad,
        "origen": tr["origen"],
        "destino": tr["destino"],
        "existencia_origen": a_float(resultante_origen),
        "existencia_destino": a_float(resultante_destino),
    }


def resumen_transferencias() -> dict:
    return one(
        """
        SELECT COUNT(*) FILTER (WHERE estado = 'SUGERIDA')  AS sugeridas,
               COUNT(*) FILTER (WHERE estado = 'APROBADA')  AS aprobadas,
               COUNT(*) FILTER (WHERE estado = 'EJECUTADA') AS ejecutadas,
               COUNT(*) FILTER (WHERE estado = 'RECHAZADA') AS rechazadas,
               COALESCE(SUM(CASE WHEN estado = 'EJECUTADA' THEN cantidad END), 0) AS unidades_movidas
        FROM analitica.transferencia
        """
    ) or {}
