"""
Motor de Triaje Preventivo Automático: Descuento ↔ Traslado ↔ Merma.

Unifica en un único flujo de decisión por lote las tres posibles salidas
preventivas para inventario perecedero:

1. MERMA (o inmovilización): si el lote ya caducó o está bloqueado / dañado /
   en cuarentena, se retira inmediatamente de la cola FEFO.
2. TRASLADO ENTRE TIENDAS: si otra tienda tiene déficit proyectado, el lote
   alcanza a llegar con vida útil (d > DIAS_TRANSITO + 1) y el valor neto
   después de costo logístico supera la alternativa local.
3. DESCUENTO PREVENTIVO: si el traslado no es viable o deja menor valor neto,
   se propone rebaja comercial respetando margen/costo piso.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, config_valor, one, query, transaccion
from app.domain import inventario, pronostico, transferencias

DIAS_TRANSITO = transferencias.DIAS_TRANSITO


def _json(valor) -> str:
    return json.dumps(valor, default=str, ensure_ascii=False)


def decidir_ruta_lote(
    *,
    estado_lote: str,
    dias_restantes: int,
    cantidad_disponible: float,
    demanda_diaria_origen: float,
    precio_venta: float,
    precio_costo: float,
    dias_ventana_riesgo: int = 5,
    mejor_destino: dict | None = None,
    pct_descuento_critico: float = 30.0,
    pct_descuento_vigilancia: float = 15.0,
    costo_logistico_pct: float = 0.10,
) -> dict:
    """
    Función pura de decisión económica para un lote individual.
    Evalúa en orden: Inmovilización/Merma → Valor Traslado vs. Valor Descuento.
    """
    estado = (estado_lote or "DISPONIBLE").upper()
    disp = max(0.0, float(cantidad_disponible))
    dias = int(dias_restantes)
    p_venta = max(0.0, float(precio_venta))
    p_costo = max(0.0, float(precio_costo))

    # 1. Criterio estricto de calidad y caducidad
    if dias < 0 or estado in ("VENCIDO", "BLOQUEADO", "CUARENTENA", "DAÑADO", "RETIRADO", "MERMA"):
        motivo = (
            f"Lote caducado hace {abs(dias)} día(s)."
            if dias < 0
            else f"Lote en estado operativo '{estado}' (no elegible para venta)."
        )
        return {
            "accion": "MERMA",
            "unidades_en_riesgo": round(disp, 2),
            "valor_traslado_neto": 0.0,
            "valor_descuento_neto": 0.0,
            "costo_merma_potencial": round(disp * p_costo, 2),
            "cantidad_propuesta": round(disp, 2),
            "detalle": {"motivo": motivo, "requiere_bloqueo": estado == "DISPONIBLE" and dias < 0},
            "explicacion": f"MERMA / BLOQUEO OBLIGATORIO: {motivo} Pérdida en costo: ${disp * p_costo:,.2f}.",
        }

    # 2. Estimación de unidades que NO se venderán antes de vencer o salir de ventana
    dias_consumo = min(max(dias, 0), max(1, dias_ventana_riesgo))
    demanda_esperada_local = max(0.0, float(demanda_diaria_origen)) * dias_consumo
    unidades_en_riesgo = round(max(0.0, disp - demanda_esperada_local), 2)

    if unidades_en_riesgo < 1.0 and dias > dias_ventana_riesgo:
        return {
            "accion": "NORMAL",
            "unidades_en_riesgo": 0.0,
            "valor_traslado_neto": 0.0,
            "valor_descuento_neto": 0.0,
            "costo_merma_potencial": 0.0,
            "cantidad_propuesta": 0.0,
            "detalle": {},
            "explicacion": "Stock saludable: la demanda local proyectada absorbe el lote dentro de su vida útil (FEFO estándar).",
        }

    if dias > dias_ventana_riesgo and unidades_en_riesgo < 1.0:
        return {
            "accion": "NORMAL",
            "unidades_en_riesgo": 0.0,
            "valor_traslado_neto": 0.0,
            "valor_descuento_neto": 0.0,
            "costo_merma_potencial": 0.0,
            "cantidad_propuesta": 0.0,
            "detalle": {},
            "explicacion": "Sin excedente riesgoso.",
        }

    cant_objetivo = unidades_en_riesgo if unidades_en_riesgo >= 1.0 else disp
    costo_merma = round(cant_objetivo * p_costo, 2)

    # 3. Evaluar Opción A: TRASLADO a tienda con déficit
    v_traslado = 0.0
    detalle_traslado: dict | None = None
    if mejor_destino and dias > DIAS_TRANSITO:
        faltante_dest = max(0.0, float(mejor_destino.get("faltante", 0)))
        dem_dest = max(0.0, float(mejor_destino.get("demanda_diaria", 0)))
        cant_tr = round(min(cant_objetivo, disp, faltante_dest), 2)
        cap_dest = dem_dest * max(0, dias - DIAS_TRANSITO)
        if cant_tr >= 1.0 and cap_dest >= cant_tr:
            costo_log_unit = max(1.5, round(p_costo * costo_logistico_pct, 2))
            margen_traslado_unit = p_venta - p_costo - costo_log_unit
            # Valor recuperado neto descontando logística vs perder el costo
            v_traslado = round((p_venta - costo_log_unit) * cant_tr, 2)
            if p_venta > costo_log_unit and (p_venta - costo_log_unit) > 0:
                detalle_traslado = {
                    "id_locacion_destino": mejor_destino["id_locacion"],
                    "destino": mejor_destino["nombre"],
                    "cantidad": cant_tr,
                    "faltante_destino": round(faltante_dest, 2),
                    "demanda_diaria_destino": round(dem_dest, 2),
                    "costo_logistico_total": round(costo_log_unit * cant_tr, 2),
                    "margen_neto_estimado": round(margen_traslado_unit * cant_tr, 2),
                }
            else:
                v_traslado = 0.0

    # 4. Evaluar Opción B: DESCUENTO PREVENTIVO local (respetando margen / costo piso)
    v_descuento = 0.0
    detalle_descuento: dict | None = None
    if 0 <= dias <= dias_ventana_riesgo and p_venta > 0:
        pct = pct_descuento_critico if dias <= 2 else pct_descuento_vigilancia
        precio_nuevo = round(p_venta * (1.0 - pct / 100.0), 2)
        # Regla comercial: respetar piso de costo salvo urgencia de liquidación (>= 85% costo)
        piso = p_costo * (0.85 if dias <= 1 else 1.0)
        if precio_nuevo < piso and p_venta > piso:
            pct = round((1.0 - piso / p_venta) * 100.0, 2)
            precio_nuevo = round(piso, 2)

        if precio_nuevo >= piso and pct >= 5.0:
            # Elasticidad estimada por descuento: acelera la velocidad de salida local
            factor_aceleracion = 2.2 if pct >= 25 else 1.6
            dem_acelerada = max(0.5, float(demanda_diaria_origen) * factor_aceleracion) * max(1, dias)
            cant_recuperable = round(min(cant_objetivo, disp, dem_acelerada), 2)
            if cant_recuperable >= 1.0:
                v_descuento = round(precio_nuevo * cant_recuperable, 2)
                detalle_descuento = {
                    "descuento_pct": pct,
                    "precio_normal": p_venta,
                    "precio_nuevo": precio_nuevo,
                    "cantidad": cant_recuperable,
                    "ingreso_potencial": v_descuento,
                }

    # 5. Selección excluyente por mayor recuperación neta
    if detalle_traslado and v_traslado >= v_descuento and v_traslado > 0:
        return {
            "accion": "TRASLADO",
            "unidades_en_riesgo": cant_objetivo,
            "valor_traslado_neto": v_traslado,
            "valor_descuento_neto": v_descuento,
            "costo_merma_potencial": costo_merma,
            "cantidad_propuesta": detalle_traslado["cantidad"],
            "detalle": detalle_traslado,
            "explicacion": (
                f"TRASLADO a {detalle_traslado['destino']}: recupera ${v_traslado:,.2f} a precio completo "
                f"(descontando logística) frente a ${v_descuento:,.2f} por descuento local o pérdida de ${costo_merma:,.2f} en merma."
            ),
        }

    if detalle_descuento and v_descuento > 0:
        return {
            "accion": "DESCUENTO",
            "unidades_en_riesgo": cant_objetivo,
            "valor_traslado_neto": v_traslado,
            "valor_descuento_neto": v_descuento,
            "costo_merma_potencial": costo_merma,
            "cantidad_propuesta": detalle_descuento["cantidad"],
            "detalle": detalle_descuento,
            "explicacion": (
                f"DESCUENTO {detalle_descuento['descuento_pct']:g}% (${detalle_descuento['precio_normal']:,.2f} → "
                f"${detalle_descuento['precio_nuevo']:,.2f}): recupera ${v_descuento:,.2f} en tienda antes de caducar "
                f"(traslado: ${v_traslado:,.2f}; riesgo merma: ${costo_merma:,.2f})."
            ),
        }

    return {
        "accion": "MERMA",
        "unidades_en_riesgo": cant_objetivo,
        "valor_traslado_neto": v_traslado,
        "valor_descuento_neto": v_descuento,
        "costo_merma_potencial": costo_merma,
        "cantidad_propuesta": cant_objetivo,
        "detalle": {"motivo": "Sin demanda suficiente ni tienda destino apta antes de caducidad."},
        "explicacion": (
            f"ALERTA DE MERMA PREVENTIVA: caduca en {dias} día(s) sin viabilidad de traslado (${v_traslado:,.2f}) "
            f"ni liquidación con margen piso. Preparar retiro/donación."
        ),
    }


def evaluar_triaje_lotes(
    *, id_locacion: int | None = None, horizonte: int | None = None
) -> dict:
    """Evalúa lotes vigentes/vencidos con existencia y decide la ruta óptima por lote."""
    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)
    dias_ventana = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)
    pct_crit = a_float(config_valor("descuento_pct_critico", "30")) or 30.0
    pct_vig = a_float(config_valor("descuento_pct_vigilancia", "15")) or 15.0

    filtro_loc = "AND v.id_locacion = :loc" if id_locacion else ""
    params = {"ventana": dias_ventana, **({"loc": id_locacion} if id_locacion else {})}

    lotes = query(
        f"""
        SELECT v.id_lote::text, v.codigo_lote_prov, v.estado_lote,
               v.id_sku, v.producto, v.unidad_medida,
               v.id_locacion, v.locacion, v.tipo_locacion,
               v.cantidad_disponible, v.cantidad_util,
               v.fecha_caducidad, v.dias_restantes, v.clasificacion,
               v.costo_unitario, p.precio_venta, p.precio_costo
        FROM operacion.v_inventario_lote v
        JOIN operacion.producto p ON p.id_sku = v.id_sku
        WHERE v.cantidad_disponible > 0
          AND (v.dias_restantes <= :ventana OR v.estado_lote <> 'DISPONIBLE' OR v.clasificacion IN ('CRITICO', 'VIGILANCIA', 'VENCIDO'))
          {filtro_loc}
        ORDER BY v.dias_restantes ASC, v.cantidad_disponible DESC
        """,
        **params,
    )

    tiendas = inventario.locaciones_activas("Tienda")
    situaciones_cache: dict[tuple[int, int], dict] = {}

    def _sit(sku: int, loc: int) -> dict:
        if (sku, loc) not in situaciones_cache:
            s = transferencias._situacion(sku, loc, horizonte)
            situaciones_cache[(sku, loc)] = s
        return situaciones_cache[(sku, loc)]

    decisiones = []
    resumen = {"TRASLADO": 0, "DESCUENTO": 0, "MERMA": 0, "NORMAL": 0}
    valor_rescatable = 0.0

    for l in lotes:
        sku = l["id_sku"]
        loc_orig = l["id_locacion"]
        dem_orig = pronostico.demanda_diaria_promedio(sku, loc_orig, 28)

        mejor_dest = None
        if l["estado_lote"] == "DISPONIBLE" and a_int(l["dias_restantes"], 0) > DIAS_TRANSITO:
            candidatos_dest = []
            for t in tiendas:
                if t["id_locacion"] == loc_orig:
                    continue
                sit = _sit(sku, t["id_locacion"])
                if sit["faltante"] > 0 and sit["demanda_diaria"] > 0:
                    candidatos_dest.append({
                        "id_locacion": t["id_locacion"],
                        "nombre": t["nombre"],
                        "faltante": sit["faltante"],
                        "demanda_diaria": sit["demanda_diaria"],
                    })
            if candidatos_dest:
                mejor_dest = max(candidatos_dest, key=lambda x: min(x["faltante"], a_float(l["cantidad_disponible"])))

        dec = decidir_ruta_lote(
            estado_lote=l["estado_lote"],
            dias_restantes=a_int(l["dias_restantes"], 0),
            cantidad_disponible=a_float(l["cantidad_disponible"]),
            demanda_diaria_origen=dem_orig,
            precio_venta=a_float(l["precio_venta"]),
            precio_costo=a_float(l["precio_costo"] or l["costo_unitario"]),
            dias_ventana_riesgo=dias_ventana,
            mejor_destino=mejor_dest,
            pct_descuento_critico=pct_crit,
            pct_descuento_vigilancia=pct_vig,
        )
        resumen[dec["accion"]] = resumen.get(dec["accion"], 0) + 1
        if dec["accion"] in ("TRASLADO", "DESCUENTO"):
            valor_rescatable += max(dec["valor_traslado_neto"], dec["valor_descuento_neto"])

        decisiones.append({
            "id_lote": l["id_lote"],
            "codigo_lote_prov": l["codigo_lote_prov"],
            "estado_lote": l["estado_lote"],
            "id_sku": sku,
            "producto": l["producto"],
            "unidad_medida": l["unidad_medida"],
            "id_locacion": loc_orig,
            "locacion": l["locacion"],
            "cantidad_disponible": a_float(l["cantidad_disponible"]),
            "fecha_caducidad": str(l["fecha_caducidad"]),
            "dias_restantes": a_int(l["dias_restantes"], 0),
            "clasificacion": l["clasificacion"],
            **dec,
        })

    return {
        "total_evaluados": len(decisiones),
        "resumen": resumen,
        "valor_rescatable_estimado": round(valor_rescatable, 2),
        "decisiones": decisiones,
    }


def ejecutar_triaje_automatico(
    *, usuario: dict, id_locacion: int | None = None, horizonte: int | None = None
) -> dict:
    """
    Ejecuta el motor de triaje Descuento ↔ Traslado ↔ Merma y materializa
    las propuestas ganadoras sin duplicar ni contradecir acciones vigentes.
    """
    evaluacion = evaluar_triaje_lotes(id_locacion=id_locacion, horizonte=horizonte)
    traslados_creados = 0
    descuentos_creados = 0
    lotes_bloqueados = 0

    for d in evaluacion["decisiones"]:
        accion = d["accion"]

        if accion == "TRASLADO":
            det = d["detalle"]
            id_dest = det["id_locacion_destino"]
            ya_tr = one(
                """
                SELECT id_transferencia::text FROM analitica.transferencia
                WHERE id_lote = CAST(:lote AS uuid) AND id_locacion_origen = :orig
                  AND estado IN ('SUGERIDA', 'APROBADA')
                LIMIT 1
                """,
                lote=d["id_lote"],
                orig=d["id_locacion"],
            )
            if not ya_tr:
                validaciones = {
                    "origen_suficiente": {"pasa": True, "detalle": f"{d['locacion']} tiene {d['cantidad_disponible']:g} u. disponibles"},
                    "destino_necesita": {"pasa": True, "detalle": f"{det['destino']} requiere {det['faltante_destino']:g} u."},
                    "llega_antes_de_vencer": {"pasa": True, "detalle": f"Vence en {d['dias_restantes']} d; tránsito {DIAS_TRANSITO} d"},
                    "destino_puede_consumirlo": {"pasa": True, "detalle": f"Demanda en destino {det['demanda_diaria_destino']:g} u/día absorbe el lote"},
                }
                with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
                    # Evitar contradicción: cancelar descuentos pendientes no aprobados para el mismo lote
                    conn.execute(
                        text(
                            """
                            UPDATE analitica.descuento
                               SET estado = 'RECHAZADO', fecha_decision = now()
                             WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :orig AND estado = 'SUGERIDO'
                            """
                        ),
                        {"lote": d["id_lote"], "orig": d["id_locacion"]},
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO analitica.transferencia
                                (id_sku, id_lote, id_locacion_origen, id_locacion_destino,
                                 cantidad, motivo, exceso_origen, faltante_destino,
                                 dias_para_vencer, validaciones, estado, id_usuario_solicita)
                            VALUES
                                (:sku, CAST(:lote AS uuid), :orig, :dest, :cant, :motivo,
                                 :exc, :falt, :dias, CAST(:val AS jsonb), 'SUGERIDA', CAST(:uid AS uuid))
                            """
                        ),
                        {
                            "sku": d["id_sku"],
                            "lote": d["id_lote"],
                            "orig": d["id_locacion"],
                            "dest": id_dest,
                            "cant": det["cantidad"],
                            "motivo": d["explicacion"],
                            "exc": d["unidades_en_riesgo"],
                            "falt": det["faltante_destino"],
                            "dias": d["dias_restantes"],
                            "val": _json(validaciones),
                            "uid": usuario["id_usuario"],
                        },
                    )
                traslados_creados += 1

        elif accion == "DESCUENTO":
            det = d["detalle"]
            ya_desc = one(
                """
                SELECT id_descuento::text FROM analitica.descuento
                WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc
                  AND estado IN ('SUGERIDO', 'APROBADO')
                LIMIT 1
                """,
                lote=d["id_lote"],
                loc=d["id_locacion"],
            )
            ya_tr = one(
                """
                SELECT id_transferencia::text FROM analitica.transferencia
                WHERE id_lote = CAST(:lote AS uuid) AND id_locacion_origen = :loc
                  AND estado IN ('SUGERIDA', 'APROBADA')
                LIMIT 1
                """,
                lote=d["id_lote"],
                loc=d["id_locacion"],
            )
            if not ya_desc and not ya_tr:
                with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO analitica.descuento
                                (id_lote, id_locacion, descuento_pct, precio_normal, precio_nuevo,
                                 cantidad, dias_restantes, ingreso_potencial, estado, id_usuario_solicita)
                            VALUES
                                (CAST(:lote AS uuid), :loc, :pct, :normal, :nuevo,
                                 :cant, :dias, :ingreso, 'SUGERIDO', CAST(:uid AS uuid))
                            """
                        ),
                        {
                            "lote": d["id_lote"],
                            "loc": d["id_locacion"],
                            "pct": det["descuento_pct"],
                            "normal": det["precio_normal"],
                            "nuevo": det["precio_nuevo"],
                            "cant": det["cantidad"],
                            "dias": d["dias_restantes"],
                            "ingreso": det["ingreso_potencial"],
                            "uid": usuario["id_usuario"],
                        },
                    )
                descuentos_creados += 1

        elif accion == "MERMA" and d["detalle"].get("requiere_bloqueo"):
            with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
                conn.execute(
                    text("UPDATE operacion.lote SET estado = 'VENCIDO' WHERE id_lote = CAST(:l AS uuid) AND estado = 'DISPONIBLE'"),
                    {"l": d["id_lote"]},
                )
            lotes_bloqueados += 1

    auditoria.registrar(
        "RUN_PREVENTIVE_TRIAGE",
        tabla="lote",
        descripcion=(
            f"Triaje automático ejecutado: {evaluacion['total_evaluados']} lotes evaluados · "
            f"{traslados_creados} traslados, {descuentos_creados} descuentos, {lotes_bloqueados} lotes bloqueados."
        ),
        estado_nuevo={
            "traslados_creados": traslados_creados,
            "descuentos_creados": descuentos_creados,
            "lotes_bloqueados": lotes_bloqueados,
        },
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    return {
        **evaluacion,
        "aplicados": {
            "traslados_creados": traslados_creados,
            "descuentos_creados": descuentos_creados,
            "lotes_vencidos_bloqueados": lotes_bloqueados,
        },
    }
