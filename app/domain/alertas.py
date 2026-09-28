"""
Motor de alertas.

Las alertas NO son una tabla de ejemplo: se derivan de PostgreSQL aplicando
reglas sobre el inventario, el pronóstico y las órdenes pendientes. Se
recalculan cada vez que alguien entra a la pantalla o pulsa «Regenerar».

Tipos cubiertos (los 7 que exige la rúbrica):

    LOTE_POR_VENCER          RIESGO_DE_FALTANTE
    LOTE_VENCIDO             REABASTECIMIENTO_REQUERIDO
    RIESGO_DE_MERMA          TRANSFERENCIA_SUGERIDA
    SOBREINVENTARIO

Cada alerta lleva una `huella` que impide duplicarla mientras siga abierta.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, config_valor, query, transaccion

TIPOS = {
    "LOTE_POR_VENCER": {"etiqueta": "Lote por vencer", "icono": "clock"},
    "LOTE_VENCIDO": {"etiqueta": "Lote vencido", "icono": "alert"},
    "RIESGO_DE_MERMA": {"etiqueta": "Riesgo de merma", "icono": "trash"},
    "SOBREINVENTARIO": {"etiqueta": "Sobreinventario", "icono": "box"},
    "RIESGO_DE_FALTANTE": {"etiqueta": "Riesgo de faltante", "icono": "down"},
    "REABASTECIMIENTO_REQUERIDO": {"etiqueta": "Reabastecimiento requerido", "icono": "truck"},
    "TRANSFERENCIA_SUGERIDA": {"etiqueta": "Transferencia sugerida", "icono": "transfer"},
}

SEVERIDADES = {
    "CRITICA": {"etiqueta": "Crítica", "color": "#f87171"},
    "ALTA": {"etiqueta": "Alta", "color": "#fb923c"},
    "MEDIA": {"etiqueta": "Media", "color": "#facc15"},
    "BAJA": {"etiqueta": "Baja", "color": "#60a5fa"},
}


def _json(valor) -> str:
    return json.dumps(valor, default=str, ensure_ascii=False)


def _insertar(conn, *, tipo, severidad, mensaje, huella, id_sku=None, id_lote=None,
              id_locacion=None, detalle=None, referencia_tipo=None, referencia_id=None):
    conn.execute(
        text(
            """
            INSERT INTO analitica.alerta
                (tipo, severidad, id_sku, id_lote, id_locacion, mensaje, detalle,
                 huella, referencia_tipo, referencia_id)
            VALUES
                (:tipo, :sev, :sku, CAST(:lote AS uuid), :loc, :mensaje,
                 CAST(:detalle AS jsonb), :huella, :ref_tipo, CAST(:ref_id AS uuid))
            ON CONFLICT (huella) WHERE estado = 'ABIERTA' DO NOTHING
            """
        ),
        {
            "tipo": tipo,
            "sev": severidad,
            "sku": id_sku,
            "lote": id_lote,
            "loc": id_locacion,
            "mensaje": mensaje,
            "detalle": _json(detalle or {}),
            "huella": huella[:120],
            "ref_tipo": referencia_tipo,
            "ref_id": referencia_id,
        },
    )


def generar_alertas(usuario: dict | None = None) -> dict:
    """
    Recalcula todas las alertas desde la base de datos.

    Devuelve cuántas se generaron, cuántas se cerraron porque su causa ya
    desapareció, cuántas quedan abiertas y el desglose por tipo.
    """
    horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)
    dias_ventana = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)
    umbral_sobre = a_int(config_valor("umbral_sobreinventario_dias", "21"), 21)

    conteos: dict[str, int] = {t: 0 for t in TIPOS}
    uid = usuario["id_usuario"] if usuario else None
    email = usuario["email"] if usuario else None

    with transaccion(id_usuario=uid, usuario_email=email) as conn:
        # --- 1. Lotes por vencer y vencidos ---------------------------------
        lotes = conn.execute(
            text(
                """
                SELECT id_lote::text, codigo_lote_prov, id_sku, producto, id_locacion,
                       locacion, cantidad_disponible, unidad_medida, fecha_caducidad,
                       dias_restantes, vida_util_pct, clasificacion, valor_inventario
                FROM operacion.v_inventario_lote
                WHERE cantidad_disponible > 0
                  AND dias_restantes <= :ventana
                ORDER BY dias_restantes ASC
                """
            ),
            {"ventana": dias_ventana},
        ).mappings().all()

        for lote in lotes:
            dias = a_int(lote["dias_restantes"], 0)
            if dias < 0:
                _insertar(
                    conn,
                    tipo="LOTE_VENCIDO",
                    severidad="CRITICA",
                    id_sku=lote["id_sku"],
                    id_lote=lote["id_lote"],
                    id_locacion=lote["id_locacion"],
                    mensaje=(
                        f"El lote {lote['codigo_lote_prov']} de {lote['producto']} venció "
                        f"hace {abs(dias)} día(s) y aún tiene {a_float(lote['cantidad_disponible']):g} "
                        f"{lote['unidad_medida']} en {lote['locacion']}. Debe darse de baja."
                    ),
                    detalle={
                        "cantidad": a_float(lote["cantidad_disponible"]),
                        "valor": a_float(lote["valor_inventario"]),
                        "dias_restantes": dias,
                    },
                    huella=f"LOTE_VENCIDO:{lote['id_lote']}",
                )
                conteos["LOTE_VENCIDO"] += 1
            elif lote["clasificacion"] in ("CRITICO", "VIGILANCIA"):
                _insertar(
                    conn,
                    tipo="LOTE_POR_VENCER",
                    severidad="ALTA" if lote["clasificacion"] == "CRITICO" else "MEDIA",
                    id_sku=lote["id_sku"],
                    id_lote=lote["id_lote"],
                    id_locacion=lote["id_locacion"],
                    mensaje=(
                        f"El lote {lote['codigo_lote_prov']} de {lote['producto']} vence en "
                        f"{dias} día(s) ({a_float(lote['vida_util_pct']):g}% de vida útil) con "
                        f"{a_float(lote['cantidad_disponible']):g} {lote['unidad_medida']} "
                        f"en {lote['locacion']}."
                    ),
                    detalle={
                        "cantidad": a_float(lote["cantidad_disponible"]),
                        "dias_restantes": dias,
                        "vida_util_pct": a_float(lote["vida_util_pct"]),
                        "clasificacion": lote["clasificacion"],
                    },
                    huella=f"LOTE_POR_VENCER:{lote['id_lote']}",
                )
                conteos["LOTE_POR_VENCER"] += 1

        # --- 2. Riesgo de merma por lote ------------------------------------
        riesgos = conn.execute(
            text(
                """
                WITH demanda AS (
                    SELECT id_sku, id_locacion, AVG(cantidad) AS diaria
                    FROM analitica.v_demanda_diaria
                    WHERE fecha >= CURRENT_DATE - 28
                    GROUP BY id_sku, id_locacion
                )
                SELECT v.id_lote::text, v.codigo_lote_prov, v.id_sku, v.producto,
                       v.id_locacion, v.locacion, v.unidad_medida,
                       v.cantidad_disponible, v.dias_restantes, v.costo_unitario,
                       COALESCE(d.diaria, 0) AS demanda_diaria
                FROM operacion.v_inventario_lote v
                LEFT JOIN demanda d
                       ON d.id_sku = v.id_sku AND d.id_locacion = v.id_locacion
                WHERE v.cantidad_disponible > 0
                  AND v.dias_restantes BETWEEN 0 AND :ventana
                """
            ),
            {"ventana": dias_ventana},
        ).mappings().all()

        for r in riesgos:
            disponible = a_float(r["cantidad_disponible"])
            dias = min(a_int(r["dias_restantes"], 0), dias_ventana)
            demanda_antes = a_float(r["demanda_diaria"]) * dias
            en_riesgo = max(0.0, disponible - demanda_antes)
            if en_riesgo < 1:
                continue
            valor = round(en_riesgo * a_float(r["costo_unitario"]), 2)
            _insertar(
                conn,
                tipo="RIESGO_DE_MERMA",
                severidad="ALTA" if en_riesgo > 20 else "MEDIA",
                id_sku=r["id_sku"],
                id_lote=r["id_lote"],
                id_locacion=r["id_locacion"],
                mensaje=(
                    f"El lote {r['codigo_lote_prov']} de {r['producto']} vence en "
                    f"{r['dias_restantes']} día(s): de {disponible:g} unidades, solo se "
                    f"esperan vender {round(demanda_antes, 2):g} antes de que caduque. "
                    f"Hay {round(en_riesgo, 2):g} en riesgo ({valor:,.2f} de valor)."
                ),
                detalle={
                    "existencia": disponible,
                    "demanda_antes_caducidad": round(demanda_antes, 2),
                    "unidades_en_riesgo": round(en_riesgo, 2),
                    "valor_en_riesgo": valor,
                    "dias_restantes": a_int(r["dias_restantes"], 0),
                },
                huella=f"RIESGO_DE_MERMA:{r['id_lote']}",
            )
            conteos["RIESGO_DE_MERMA"] += 1

        # --- 3. Sobreinventario --------------------------------------------
        sobre = conn.execute(
            text(
                """
                WITH inventario AS (
                    SELECT id_sku, id_locacion,
                           SUM(cantidad_disponible) AS fisico,
                           SUM(CASE WHEN clasificacion IN ('CRITICO','VENCIDO')
                                    THEN cantidad_disponible ELSE 0 END) AS en_riesgo
                    FROM operacion.v_inventario_lote
                    WHERE cantidad_disponible > 0
                    GROUP BY id_sku, id_locacion
                ),
                demanda AS (
                    SELECT id_sku, id_locacion, AVG(cantidad) AS diaria
                    FROM analitica.v_demanda_diaria
                    WHERE fecha >= CURRENT_DATE - 28
                    GROUP BY id_sku, id_locacion
                )
                SELECT i.id_sku, i.id_locacion, i.fisico, i.en_riesgo, d.diaria,
                       p.nombre AS producto, p.unidad_medida, p.vida_util_estandar,
                       loc.nombre AS locacion
                FROM inventario i
                JOIN operacion.producto p   ON p.id_sku = i.id_sku
                JOIN operacion.locacion loc ON loc.id_locacion = i.id_locacion
                JOIN demanda d ON d.id_sku = i.id_sku AND d.id_locacion = i.id_locacion
                WHERE d.diaria > 0
                  AND (i.fisico - i.en_riesgo) / d.diaria > :umbral
                """
            ),
            {"umbral": umbral_sobre},
        ).mappings().all()

        for s in sobre:
            util = a_float(s["fisico"]) - a_float(s["en_riesgo"])
            cobertura = round(util / a_float(s["diaria"]), 1)
            _insertar(
                conn,
                tipo="SOBREINVENTARIO",
                severidad="MEDIA",
                id_sku=s["id_sku"],
                id_locacion=s["id_locacion"],
                mensaje=(
                    f"{s['producto']} en {s['locacion']}: {util:g} unidades útiles cubren "
                    f"{cobertura:g} días de demanda (umbral {umbral_sobre} días). "
                    f"El producto dura {s['vida_util_estandar']} días: hay riesgo de que "
                    f"parte se venza."
                ),
                detalle={
                    "inventario_util": util,
                    "demanda_diaria": a_float(s["diaria"]),
                    "dias_cobertura": cobertura,
                },
                huella=f"SOBREINVENTARIO:{s['id_sku']}:{s['id_locacion']}",
            )
            conteos["SOBREINVENTARIO"] += 1

        # --- 4. Riesgo de faltante -----------------------------------------
        faltantes = conn.execute(
            text(
                """
                WITH inventario AS (
                    SELECT id_sku, id_locacion,
                           SUM(cantidad_disponible) AS fisico,
                           SUM(CASE WHEN clasificacion IN ('CRITICO','VENCIDO')
                                    THEN cantidad_disponible ELSE 0 END) AS en_riesgo
                    FROM operacion.v_inventario_lote
                    WHERE cantidad_disponible > 0
                    GROUP BY id_sku, id_locacion
                ),
                demanda AS (
                    SELECT id_sku, id_locacion, AVG(cantidad) AS diaria
                    FROM analitica.v_demanda_diaria
                    WHERE fecha >= CURRENT_DATE - 28
                    GROUP BY id_sku, id_locacion
                )
                SELECT i.id_sku, i.id_locacion, i.fisico, i.en_riesgo, d.diaria,
                       p.nombre AS producto, p.unidad_medida,
                       COALESCE(pr.lead_time_dias, 3) AS lead_time_dias,
                       loc.nombre AS locacion
                FROM inventario i
                JOIN operacion.producto p   ON p.id_sku = i.id_sku
                JOIN operacion.locacion loc ON loc.id_locacion = i.id_locacion
                JOIN demanda d ON d.id_sku = i.id_sku AND d.id_locacion = i.id_locacion
                LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
                WHERE d.diaria > 0
                  AND (i.fisico - i.en_riesgo) / d.diaria < COALESCE(pr.lead_time_dias, 3)
                """
            )
        ).mappings().all()

        for f in faltantes:
            util = a_float(f["fisico"]) - a_float(f["en_riesgo"])
            cobertura = round(util / a_float(f["diaria"]), 1) if a_float(f["diaria"]) else 0
            _insertar(
                conn,
                tipo="RIESGO_DE_FALTANTE",
                severidad="ALTA",
                id_sku=f["id_sku"],
                id_locacion=f["id_locacion"],
                mensaje=(
                    f"{f['producto']} en {f['locacion']}: el inventario útil cubre "
                    f"{cobertura:g} días, pero el proveedor tarda {f['lead_time_dias']} días "
                    f"en surtir. Riesgo de quedarse sin producto."
                ),
                detalle={
                    "inventario_util": util,
                    "dias_cobertura": cobertura,
                    "lead_time_dias": a_int(f["lead_time_dias"], 3),
                },
                huella=f"RIESGO_DE_FALTANTE:{f['id_sku']}:{f['id_locacion']}",
            )
            conteos["RIESGO_DE_FALTANTE"] += 1

        # --- 5. Reabastecimiento requerido ---------------------------------
        ordenes = conn.execute(
            text(
                """
                SELECT o.id_orden::text, o.cantidad_sugerida, o.prioridad,
                       o.necesidad_neta, p.nombre AS producto, p.unidad_medida,
                       loc.nombre AS locacion, o.id_sku, o.id_locacion
                FROM analitica.orden_reabastecimiento o
                JOIN operacion.producto p   ON p.id_sku = o.id_sku
                JOIN operacion.locacion loc ON loc.id_locacion = o.id_locacion
                WHERE o.estado = 'PENDIENTE'
                """
            )
        ).mappings().all()

        for o in ordenes:
            _insertar(
                conn,
                tipo="REABASTECIMIENTO_REQUERIDO",
                severidad="ALTA" if o["prioridad"] == "ALTA" else "MEDIA",
                id_sku=o["id_sku"],
                id_locacion=o["id_locacion"],
                mensaje=(
                    f"Hay una orden pendiente de aprobar: {a_float(o['cantidad_sugerida']):g} "
                    f"{o['unidad_medida']} de {o['producto']} para {o['locacion']} "
                    f"(prioridad {o['prioridad']})."
                ),
                detalle={
                    "id_orden": o["id_orden"],
                    "cantidad_sugerida": a_float(o["cantidad_sugerida"]),
                    "necesidad_neta": a_float(o["necesidad_neta"]),
                    "prioridad": o["prioridad"],
                },
                referencia_tipo="ORDEN",
                referencia_id=o["id_orden"],
                huella=f"REABASTECIMIENTO_REQUERIDO:{o['id_orden']}",
            )
            conteos["REABASTECIMIENTO_REQUERIDO"] += 1

        # --- 6. Transferencias sugeridas -----------------------------------
        transferencias = conn.execute(
            text(
                """
                SELECT t.id_transferencia::text, t.cantidad, t.dias_para_vencer,
                       p.nombre AS producto, p.unidad_medida, t.id_sku,
                       o.nombre AS origen, d.nombre AS destino,
                       l.codigo_lote_prov, t.id_lote::text AS id_lote
                FROM analitica.transferencia t
                JOIN operacion.producto p ON p.id_sku = t.id_sku
                JOIN operacion.locacion o ON o.id_locacion = t.id_locacion_origen
                JOIN operacion.locacion d ON d.id_locacion = t.id_locacion_destino
                LEFT JOIN operacion.lote l ON l.id_lote = t.id_lote
                WHERE t.estado = 'SUGERIDA'
                """
            )
        ).mappings().all()

        for t in transferencias:
            _insertar(
                conn,
                tipo="TRANSFERENCIA_SUGERIDA",
                severidad="MEDIA",
                id_sku=t["id_sku"],
                id_lote=t["id_lote"],
                mensaje=(
                    f"Transferencia sugerida: {t['origen']} → {t['destino']} · "
                    f"{a_float(t['cantidad']):g} {t['unidad_medida']} de {t['producto']} "
                    f"(lote {t['codigo_lote_prov']}, vence en {t['dias_para_vencer']} días)."
                ),
                detalle={
                    "id_transferencia": t["id_transferencia"],
                    "cantidad": a_float(t["cantidad"]),
                    "dias_para_vencer": a_int(t["dias_para_vencer"], 0),
                    "origen": t["origen"],
                    "destino": t["destino"],
                },
                referencia_tipo="TRANSFERENCIA",
                referencia_id=t["id_transferencia"],
                huella=f"TRANSFERENCIA_SUGERIDA:{t['id_transferencia']}",
            )
            conteos["TRANSFERENCIA_SUGERIDA"] += 1

        # --- 7. Cerrar alertas cuya causa ya desapareció --------------------
        cerradas = conn.execute(
            text(
                """
                UPDATE analitica.alerta a
                   SET estado = 'ATENDIDA', fecha_cierre = now()
                 WHERE a.estado = 'ABIERTA'
                   AND a.id_lote IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM operacion.existencia e
                       WHERE e.id_lote = a.id_lote AND e.cantidad_disponible > 0
                   )
                   AND a.tipo IN ('LOTE_POR_VENCER', 'RIESGO_DE_MERMA')
                """
            )
        ).rowcount or 0

    if usuario:
        auditoria.registrar(
            "RUN_ALERTS",
            tabla="alerta",
            descripcion=(
                "Motor de alertas ejecutado: "
                + ", ".join(f"{k}={v}" for k, v in conteos.items() if v)
            ),
            estado_nuevo=conteos,
            id_usuario=usuario["id_usuario"],
            usuario_email=usuario["email"],
        )

    return {
        "generadas": sum(conteos.values()),
        "cerradas": cerradas,
        "abiertas": resumen_alertas()["total"],
        "por_tipo": conteos,
    }


def listar_alertas(
    tipo: str | None = None,
    severidad: str | None = None,
    estado: str = "ABIERTA",
    limite: int = 200,
) -> list[dict]:
    condiciones = ["a.estado = :estado"]
    params: dict = {"estado": estado, "limite": limite}
    if tipo:
        condiciones.append("a.tipo = :tipo")
        params["tipo"] = tipo
    if severidad:
        condiciones.append("a.severidad = :sev")
        params["sev"] = severidad
    return query(
        f"""
        SELECT a.id_alerta::text, a.tipo, a.severidad, a.mensaje, a.detalle,
               a.estado, a.fecha_generacion, a.referencia_tipo, a.referencia_id::text,
               a.id_sku, a.id_lote::text, a.id_locacion,
               p.nombre AS producto, p.unidad_medida,
               l.codigo_lote_prov, loc.nombre AS locacion
        FROM analitica.alerta a
        LEFT JOIN operacion.producto p   ON p.id_sku = a.id_sku
        LEFT JOIN operacion.lote     l   ON l.id_lote = a.id_lote
        LEFT JOIN operacion.locacion loc ON loc.id_locacion = a.id_locacion
        WHERE {' AND '.join(condiciones)}
        ORDER BY CASE a.severidad WHEN 'CRITICA' THEN 1 WHEN 'ALTA' THEN 2
                                  WHEN 'MEDIA' THEN 3 ELSE 4 END,
                 a.fecha_generacion DESC
        LIMIT :limite
        """,
        **params,
    )


def resumen_alertas() -> dict:
    fila = query(
        """
        SELECT tipo, severidad, COUNT(*) AS n
        FROM analitica.alerta
        WHERE estado = 'ABIERTA'
        GROUP BY tipo, severidad
        """
    )
    por_tipo: dict[str, int] = {}
    por_severidad: dict[str, int] = {}
    for f in fila:
        por_tipo[f["tipo"]] = por_tipo.get(f["tipo"], 0) + int(f["n"])
        por_severidad[f["severidad"]] = por_severidad.get(f["severidad"], 0) + int(f["n"])
    return {
        "por_tipo": por_tipo,
        "por_severidad": por_severidad,
        "total": sum(por_tipo.values()),
    }


def cerrar_alerta(id_alerta: str, usuario: dict, estado: str = "ATENDIDA") -> None:
    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE analitica.alerta
                   SET estado = :estado, fecha_cierre = now()
                 WHERE id_alerta = CAST(:id AS uuid)
                """
            ),
            {"estado": estado, "id": id_alerta},
        )
