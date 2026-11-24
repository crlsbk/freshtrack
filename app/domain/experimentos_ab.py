"""
Etapa 3: Gestor de A/B Test (Control vs. Tratamiento).

Asigna el modelo Campeón al Grupo A (Control) y el Retador al Grupo B (Tratamiento),
guarda diariamente qué predicción se utilizó por tienda/SKU en PostgreSQL y consolida
las ventas y mermas reales para decidir si se promueve el Retador a Producción.
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import auditoria
from app.db import a_float, a_int, escalar, one, query, transaccion
from app.domain import laboratorio as dom_lab
from app.domain import pronostico


def _json(valor: Any) -> str:
    return json.dumps(valor, default=str, ensure_ascii=False)


def fecha_maxima_ventas() -> date:
    """Última fecha con demanda registrada en PostgreSQL (fallback: hoy)."""
    try:
        f = escalar("SELECT max(fecha) FROM analitica.v_demanda_diaria")
        if isinstance(f, date):
            return f
    except SQLAlchemyError:
        pass
    return date.today()


def fecha_inicio_sugerida_real(dias_ventana: int = 14) -> date:
    """Fecha de inicio sugerida sobre las ventas y mermas reales disponibles."""
    return fecha_maxima_ventas() - timedelta(days=max(1, dias_ventana - 1))


def asignar_serpiente_por_volumen(tiendas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Algoritmo puro de reparto balanceado en serpiente (A, B, B, A, ...)
    ordenando por volumen de ventas descendente para equilibrar ambos grupos.
    """
    ordenadas = sorted(
        tiendas,
        key=lambda t: (-a_float(t.get("volumen_30d")), a_int(t.get("id_locacion"))),
    )
    patron = ("CONTROL", "TRATAMIENTO", "TRATAMIENTO", "CONTROL")
    salida: list[dict[str, Any]] = []
    for idx, t in enumerate(ordenadas):
        grupo = patron[idx % 4]
        salida.append({**t, "grupo": grupo})
    return salida


def sugerir_asignacion_balanceada(categoria: str | None = None) -> list[dict[str, Any]]:
    """Consulta tiendas activas con su volumen de ventas reales y sugiere Grupo A/B."""
    filtro_cat = "AND p.categoria = :cat" if categoria else ""
    params: dict[str, Any] = {"cat": categoria} if categoria else {}
    try:
        filas = query(
            f"""
            SELECT loc.id_locacion, loc.nombre AS locacion,
                   COALESCE(SUM(vd.cantidad), 0) AS volumen_30d,
                   COALESCE(SUM(vd.subtotal), 0) AS ventas_valor_30d
            FROM operacion.locacion loc
            LEFT JOIN operacion.venta_detalle vd
                   ON vd.id_locacion = loc.id_locacion
                  AND vd.fecha_transaccion >= CURRENT_TIMESTAMP - interval '30 days'
            LEFT JOIN operacion.producto p ON p.id_sku = vd.id_sku
            WHERE loc.activo = true
              AND loc.tipo_locacion = 'Tienda'
              {filtro_cat}
            GROUP BY loc.id_locacion, loc.nombre
            ORDER BY volumen_30d DESC, loc.nombre ASC
            """,
            **params,
        )
    except SQLAlchemyError:
        return []
    return asignar_serpiente_por_volumen(filas)


def modelo_activo_para_tienda(id_locacion: int) -> dict[str, Any]:
    """
    Devuelve qué modelo debe usar `id_locacion` en producción:
    si participa en un A/B Test ACTIVO usa el asignado (CONTROL/TRATAMIENTO);
    de lo contrario usa el Campeón vigente.
    """
    try:
        ab = one(
            """
            SELECT e.id_experimento::text, e.modelo_campeon, e.modelo_retador,
                   e.horizonte_dias, a.grupo, a.modelo_asignado
            FROM analitica.experimento_ab e
            JOIN analitica.experimento_ab_asignacion a
              ON a.id_experimento = e.id_experimento
            WHERE e.estado = 'ACTIVO'
              AND a.id_locacion = :loc
            ORDER BY e.creado_en DESC
            LIMIT 1
            """,
            loc=id_locacion,
        )
        if ab:
            return {
                "metodo": ab["modelo_asignado"],
                "id_experimento": ab["id_experimento"],
                "grupo_ab": ab["grupo"],
                "proposito": "AB_CONTROL" if ab["grupo"] == "CONTROL" else "AB_TRATAMIENTO",
            }
    except SQLAlchemyError:
        pass

    campeon = dom_lab.obtener_campeon_y_retador(id_locacion=id_locacion)["campeon"]
    return {
        "metodo": campeon["metodo"],
        "id_experimento": None,
        "grupo_ab": None,
        "proposito": "PRODUCCION",
    }


def obtener_experimento_activo() -> dict[str, Any] | None:
    try:
        return one(
            """
            SELECT id_experimento::text, nombre, estado, categoria, horizonte_dias,
                   modelo_campeon, parametros_campeon, modelo_retador, parametros_retador,
                   fecha_inicio, duracion_dias, fecha_fin_estimada, fecha_cierre,
                   decision_final, notas_decision, creado_en
            FROM analitica.experimento_ab
            WHERE estado = 'ACTIVO'
            ORDER BY creado_en DESC
            LIMIT 1
            """
        )
    except SQLAlchemyError:
        return None


def listar_experimentos_ab(limite: int = 10) -> list[dict[str, Any]]:
    try:
        return query(
            """
            SELECT id_experimento::text, nombre, estado, categoria, horizonte_dias,
                   modelo_campeon, modelo_retador, fecha_inicio, duracion_dias,
                   fecha_fin_estimada, fecha_cierre, decision_final, creado_en
            FROM analitica.experimento_ab
            ORDER BY creado_en DESC
            LIMIT :limite
            """,
            limite=limite,
        )
    except SQLAlchemyError:
        return []


def consolidar_experimento_ab(id_experimento: str, *, usuario: dict | None = None) -> dict[str, Any]:
    """
    Calcula y registra día por día (en `analitica.experimento_ab_bitacora`) las predicciones
    causales del grupo Control (Campeón) vs. Tratamiento (Retador) y las cruza con las
    ventas reales y mermas reales registradas en PostgreSQL.
    """
    exp = one(
        """
        SELECT id_experimento::text, nombre, estado, categoria, horizonte_dias,
               modelo_campeon, modelo_retador, fecha_inicio, duracion_dias, fecha_fin_estimada
        FROM analitica.experimento_ab
        WHERE id_experimento = CAST(:id AS uuid)
        """,
        id=id_experimento,
    )
    if exp is None:
        raise ValueError("El experimento A/B no existe.")

    asignaciones = query(
        """
        SELECT id_locacion, grupo, modelo_asignado
        FROM analitica.experimento_ab_asignacion
        WHERE id_experimento = CAST(:id AS uuid)
        """,
        id=id_experimento,
    )
    if not asignaciones:
        raise ValueError("El experimento no tiene tiendas asignadas.")

    mapa_loc = {a["id_locacion"]: a for a in asignaciones}
    loc_ids = list(mapa_loc.keys())
    fecha_inicio: date = exp["fecha_inicio"]
    fecha_max_datos = fecha_maxima_ventas()
    fecha_corte = min(exp["fecha_fin_estimada"], fecha_max_datos)
    if fecha_corte < fecha_inicio:
        fecha_corte = fecha_inicio

    fecha_hist_inicio = fecha_inicio - timedelta(days=90)
    cat = exp.get("categoria")
    filtro_cat = "AND p.categoria = :cat" if cat else ""
    params_q: dict[str, Any] = {
        "h_ini": fecha_hist_inicio,
        "f_corte": fecha_corte,
        "f_ini": fecha_inicio,
        "locs": loc_ids,
    }
    if cat:
        params_q["cat"] = cat

    demanda_rows = query(
        f"""
        SELECT v.id_locacion, v.id_sku, v.fecha, v.cantidad
        FROM analitica.v_demanda_diaria v
        JOIN operacion.producto p ON p.id_sku = v.id_sku
        WHERE v.id_locacion = ANY(:locs)
          AND v.fecha BETWEEN :h_ini AND :f_corte
          {filtro_cat}
        ORDER BY v.id_locacion, v.id_sku, v.fecha
        """,
        **params_q,
    )

    ventas_valor_rows = query(
        f"""
        SELECT vd.id_locacion, vd.id_sku, DATE(vd.fecha_transaccion) AS fecha,
               SUM(vd.cantidad) AS unidades, SUM(vd.subtotal) AS valor
        FROM operacion.venta_detalle vd
        JOIN operacion.producto p ON p.id_sku = vd.id_sku
        WHERE vd.id_locacion = ANY(:locs)
          AND DATE(vd.fecha_transaccion) BETWEEN :f_ini AND :f_corte
          {filtro_cat}
        GROUP BY vd.id_locacion, vd.id_sku, DATE(vd.fecha_transaccion)
        """,
        **params_q,
    )

    mermas_rows = query(
        f"""
        SELECT m.id_locacion, l.id_sku, DATE(m.fecha_registro) AS fecha,
               SUM(m.cantidad) AS unidades, SUM(m.valor_merma) AS valor
        FROM operacion.merma m
        JOIN operacion.lote l     ON l.id_lote = m.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        WHERE m.id_locacion = ANY(:locs)
          AND DATE(m.fecha_registro) BETWEEN :f_ini AND :f_corte
          {filtro_cat}
        GROUP BY m.id_locacion, l.id_sku, DATE(m.fecha_registro)
        """,
        **params_q,
    )

    ventas_map = {
        (r["id_locacion"], r["id_sku"], r["fecha"]): (
            a_float(r["unidades"]),
            a_float(r["valor"]),
        )
        for r in ventas_valor_rows
    }
    mermas_map = {
        (r["id_locacion"], r["id_sku"], r["fecha"]): (
            a_float(r["unidades"]),
            a_float(r["valor"]),
        )
        for r in mermas_rows
    }

    series_raw: dict[tuple[int, int], list[dict]] = {}
    for r in demanda_rows:
        series_raw.setdefault((r["id_locacion"], r["id_sku"]), []).append(r)

    registros_upsert: list[dict[str, Any]] = []
    for (loc_id, sku_id), filas_serie in series_raw.items():
        asig = mapa_loc.get(loc_id)
        if not asig:
            continue
        serie = pronostico._serie_completa(filas_serie, fecha_hist_inicio, fecha_corte)
        # Requerir un mínimo razonable de historia previa para evaluar el SKU
        idx_inicio = (fecha_inicio - fecha_hist_inicio).days
        if sum(1 for _, v in serie[: max(1, idx_inicio)] if v > 0) < 5:
            continue

        factores = pronostico._factores_semana(serie[: max(7, idx_inicio)])
        modelo_grupo = asig["modelo_asignado"]
        metodo_eval = "SUAVIZACION_EXPONENCIAL" if modelo_grupo == "AUTO" else modelo_grupo

        for idx in range(idx_inicio, len(serie)):
            dia_obj, real = serie[idx]
            entreno = serie[:idx]
            if not entreno:
                continue
            pred = pronostico._pronosticar_fecha(
                entreno, dia_obj, metodo_eval, 28, 0.30, factores
            )
            ventana_rec = [v for _, v in entreno[-14:]]
            media_rec = sum(ventana_rec) / len(ventana_rec) if ventana_rec else 0.0
            sigma_est = math.sqrt(
                sum((v - media_rec) ** 2 for v in ventana_rec) / len(ventana_rec)
            ) if ventana_rec else 0.0

            _, venta_val = ventas_map.get((loc_id, sku_id, dia_obj), (real, 0.0))
            merma_u, merma_val = mermas_map.get((loc_id, sku_id, dia_obj), (0.0, 0.0))
            err_abs = abs(pred - real)

            registros_upsert.append(
                {
                    "id_exp": id_experimento,
                    "fecha": dia_obj,
                    "loc": loc_id,
                    "sku": sku_id,
                    "grupo": asig["grupo"],
                    "modelo": modelo_grupo,
                    "media": round(pred, 2),
                    "sigma": round(max(sigma_est, pred * 0.08), 4),
                    "real": round(real, 2),
                    "err": round(err_abs, 2),
                    "venta_val": round(venta_val, 2),
                    "merma_u": round(merma_u, 2),
                    "merma_val": round(merma_val, 2),
                }
            )

    if registros_upsert:
        uid = usuario.get("id_usuario") if usuario else None
        uemail = usuario.get("email") if usuario else None
        with transaccion(id_usuario=uid, usuario_email=uemail) as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO analitica.experimento_ab_bitacora
                        (id_experimento, fecha, id_locacion, id_sku, grupo, modelo_usado,
                         demanda_media, desviacion_std, demanda_real, error_absoluto,
                         ventas_reales_valor, merma_real_unidades, merma_real_valor)
                    VALUES
                        (CAST(:id_exp AS uuid), :fecha, :loc, :sku, :grupo, :modelo,
                         :media, :sigma, :real, :err, :venta_val, :merma_u, :merma_val)
                    ON CONFLICT (id_experimento, fecha, id_locacion, id_sku)
                    DO UPDATE SET
                        modelo_usado = EXCLUDED.modelo_usado,
                        demanda_media = EXCLUDED.demanda_media,
                        desviacion_std = EXCLUDED.desviacion_std,
                        demanda_real = EXCLUDED.demanda_real,
                        error_absoluto = EXCLUDED.error_absoluto,
                        ventas_reales_valor = EXCLUDED.ventas_reales_valor,
                        merma_real_unidades = EXCLUDED.merma_real_unidades,
                        merma_real_valor = EXCLUDED.merma_real_valor
                    """
                ),
                registros_upsert,
            )

    return resumen_experimento_ab(id_experimento)


def crear_experimento_ab(
    *,
    nombre: str,
    modelo_campeon: str,
    modelo_retador: str,
    tiendas_control: list[int],
    tiendas_tratamiento: list[int],
    usuario: dict,
    duracion_dias: int = 21,
    horizonte_dias: int = 7,
    categoria: str | None = None,
    fecha_inicio: date | None = None,
    parametros_campeon: dict | None = None,
    parametros_retador: dict | None = None,
) -> dict[str, Any]:
    """Crea un A/B Test Control vs. Tratamiento y lo consolida sobre datos reales."""
    modelo_campeon = (modelo_campeon or "AUTO").upper()
    modelo_retador = (modelo_retador or "ETS_HOLT_WINTERS").upper()
    if modelo_campeon not in pronostico.METODOS or modelo_retador not in pronostico.METODOS:
        raise ValueError("El modelo Campeón o Retador no es válido.")

    ctrl = sorted({int(x) for x in tiendas_control})
    trat = sorted({int(x) for x in tiendas_tratamiento})
    if not ctrl or not trat:
        raise ValueError("Debes asignar al menos 1 tienda en Control (A) y 1 en Tratamiento (B).")
    if set(ctrl) & set(trat):
        raise ValueError("Una misma tienda no puede estar simultáneamente en Control y Tratamiento.")

    if not 3 <= int(duracion_dias) <= 90:
        raise ValueError("La duración del experimento debe estar entre 3 y 90 días.")

    if obtener_experimento_activo() is not None:
        raise ValueError("Ya existe un experimento A/B activo. Decídelo o descártalo antes de iniciar otro.")

    f_ini = fecha_inicio or fecha_inicio_sugerida_real(min(14, duracion_dias))
    f_fin = f_ini + timedelta(days=int(duracion_dias) - 1)
    cat = categoria.strip() if isinstance(categoria, str) and categoria.strip() else None

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        id_exp = conn.execute(
            text(
                """
                INSERT INTO analitica.experimento_ab
                    (nombre, estado, categoria, horizonte_dias,
                     modelo_campeon, parametros_campeon, modelo_retador, parametros_retador,
                     fecha_inicio, duracion_dias, fecha_fin_estimada, id_usuario_crea)
                VALUES
                    (:nombre, 'ACTIVO', :cat, :horizonte,
                     :m_camp, CAST(:p_camp AS jsonb), :m_ret, CAST(:p_ret AS jsonb),
                     :f_ini, :dur, :f_fin, CAST(:uid AS uuid))
                RETURNING id_experimento::text
                """
            ),
            {
                "nombre": nombre.strip() or f"{modelo_campeon} vs {modelo_retador}",
                "cat": cat,
                "horizonte": int(horizonte_dias),
                "m_camp": modelo_campeon,
                "p_camp": _json(parametros_campeon or {}),
                "m_ret": modelo_retador,
                "p_ret": _json(parametros_retador or {}),
                "f_ini": f_ini,
                "dur": int(duracion_dias),
                "f_fin": f_fin,
                "uid": usuario["id_usuario"],
            },
        ).scalar()

        asig_rows = [
            {"id_exp": id_exp, "loc": loc, "grupo": "CONTROL", "mod": modelo_campeon}
            for loc in ctrl
        ] + [
            {"id_exp": id_exp, "loc": loc, "grupo": "TRATAMIENTO", "mod": modelo_retador}
            for loc in trat
        ]
        conn.execute(
            text(
                """
                INSERT INTO analitica.experimento_ab_asignacion
                    (id_experimento, id_locacion, grupo, modelo_asignado)
                VALUES (CAST(:id_exp AS uuid), :loc, :grupo, :mod)
                """
            ),
            asig_rows,
        )

    auditoria.registrar(
        "RUN_FORECAST",
        tabla="experimento_ab",
        id_registro=id_exp,
        descripcion=f"Experimento A/B iniciado: {modelo_campeon} (Control: {len(ctrl)}) vs {modelo_retador} (Tratamiento: {len(trat)})",
        estado_nuevo={"modelo_campeon": modelo_campeon, "modelo_retador": modelo_retador, "fecha_inicio": f_ini.isoformat()},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return consolidar_experimento_ab(id_exp, usuario=usuario)


def calcular_comparativa_ab(
    *,
    grupos_agg: dict[str, dict[str, float]],
    dia_actual: int,
    duracion_dias: int,
) -> dict[str, Any]:
    """Calcula métricas de comparación Control vs. Tratamiento y veredicto sugerido."""
    ctrl = grupos_agg.get("CONTROL", {})
    trat = grupos_agg.get("TRATAMIENTO", {})

    def _m(g: dict[str, float]) -> dict[str, Any]:
        real_tot = a_float(g.get("real_total"))
        err_tot = a_float(g.get("error_total"))
        pred_tot = a_float(g.get("pred_total"))
        n = a_int(g.get("registros"), 0)
        ventas_val = a_float(g.get("ventas_valor"))
        merma_u = a_float(g.get("merma_unidades"))
        merma_val = a_float(g.get("merma_valor"))
        wmape = round(err_tot / real_tot * 100.0, 2) if real_tot > 0 else None
        bias = round((pred_tot - real_tot) / n, 2) if n > 0 else None
        tasa_merma = round(merma_val / ventas_val * 100.0, 2) if ventas_val > 0 else 0.0
        return {
            "registros": n,
            "tiendas": a_int(g.get("tiendas"), 0),
            "dias": a_int(g.get("dias"), 0),
            "demanda_real": round(real_tot, 2),
            "ventas_valor": round(ventas_val, 2),
            "merma_unidades": round(merma_u, 2),
            "merma_valor": round(merma_val, 2),
            "tasa_merma_pct": tasa_merma,
            "wmape_real": wmape,
            "bias_real": bias,
        }

    m_ctrl = _m(ctrl)
    m_trat = _m(trat)

    delta_merma_val = round(m_trat["merma_valor"] - m_ctrl["merma_valor"], 2)
    delta_tasa_merma_pp = round(m_trat["tasa_merma_pct"] - m_ctrl["tasa_merma_pct"], 2)
    delta_ventas_pct = (
        round((m_trat["ventas_valor"] - m_ctrl["ventas_valor"]) / m_ctrl["ventas_valor"] * 100.0, 2)
        if m_ctrl["ventas_valor"] > 0
        else 0.0
    )
    delta_wmape_pp = (
        round(m_trat["wmape_real"] - m_ctrl["wmape_real"], 2)
        if (m_ctrl["wmape_real"] is not None and m_trat["wmape_real"] is not None)
        else None
    )

    avance_pct = min(100, max(0, round(dia_actual / max(1, duracion_dias) * 100)))
    if m_trat["registros"] == 0 or m_ctrl["registros"] == 0:
        veredicto = "CONTINUAR_PRUEBA"
        texto_veredicto = "Aún se están acumulando observaciones comparables entre Control y Tratamiento."
    elif (delta_tasa_merma_pp <= 0 and (delta_wmape_pp is None or delta_wmape_pp <= 1.0)) or (
        delta_wmape_pp is not None and delta_wmape_pp < -1.0 and delta_merma_val <= 0
    ):
        veredicto = "PROMOVER_RETADOR"
        texto_veredicto = "El Retador muestra menor tasa de merma y/o mejor precisión real frente al Campeón."
    elif dia_actual >= duracion_dias and delta_tasa_merma_pp > 1.0:
        veredicto = "MANTENER_CAMPEON"
        texto_veredicto = "El Campeón mantiene mejor desempeño de merma; conviene descartar el Retador."
    else:
        veredicto = "CONTINUAR_PRUEBA"
        texto_veredicto = "Diferencia aún moderada; observa la evolución diaria antes de decidir."

    return {
        "dia_actual": dia_actual,
        "duracion_dias": duracion_dias,
        "avance_pct": avance_pct,
        "control": m_ctrl,
        "tratamiento": m_trat,
        "deltas": {
            "merma_valor": delta_merma_val,
            "tasa_merma_pp": delta_tasa_merma_pp,
            "ventas_pct": delta_ventas_pct,
            "wmape_pp": delta_wmape_pp,
        },
        "veredicto": veredicto,
        "texto_veredicto": texto_veredicto,
    }


def resumen_experimento_ab(id_experimento: str) -> dict[str, Any]:
    exp = one(
        """
        SELECT id_experimento::text, nombre, estado, categoria, horizonte_dias,
               modelo_campeon, parametros_campeon, modelo_retador, parametros_retador,
               fecha_inicio, duracion_dias, fecha_fin_estimada, fecha_cierre,
               decision_final, notas_decision, creado_en
        FROM analitica.experimento_ab
        WHERE id_experimento = CAST(:id AS uuid)
        """,
        id=id_experimento,
    )
    if exp is None:
        raise ValueError("El experimento A/B no existe.")

    asignaciones = query(
        """
        SELECT a.id_locacion, loc.nombre AS locacion, a.grupo, a.modelo_asignado
        FROM analitica.experimento_ab_asignacion a
        JOIN operacion.locacion loc ON loc.id_locacion = a.id_locacion
        WHERE a.id_experimento = CAST(:id AS uuid)
        ORDER BY a.grupo, loc.nombre
        """,
        id=id_experimento,
    )

    agg_rows = query(
        """
        SELECT grupo,
               COUNT(*) AS registros,
               COUNT(DISTINCT id_locacion) AS tiendas,
               COUNT(DISTINCT fecha) AS dias,
               COALESCE(SUM(demanda_real), 0) AS real_total,
               COALESCE(SUM(demanda_media), 0) AS pred_total,
               COALESCE(SUM(error_absoluto), 0) AS error_total,
               COALESCE(SUM(ventas_reales_valor), 0) AS ventas_valor,
               COALESCE(SUM(merma_real_unidades), 0) AS merma_unidades,
               COALESCE(SUM(merma_real_valor), 0) AS merma_valor
        FROM analitica.experimento_ab_bitacora
        WHERE id_experimento = CAST(:id AS uuid)
        GROUP BY grupo
        """,
        id=id_experimento,
    )
    grupos_agg = {r["grupo"]: r for r in agg_rows}

    fecha_ref = min(exp["fecha_fin_estimada"], max(fecha_maxima_ventas(), exp["fecha_inicio"]))
    dia_actual = max(1, min(exp["duracion_dias"], (fecha_ref - exp["fecha_inicio"]).days + 1))

    comp = calcular_comparativa_ab(
        grupos_agg=grupos_agg,
        dia_actual=dia_actual,
        duracion_dias=exp["duracion_dias"],
    )

    diario = query(
        """
        SELECT fecha,
               COALESCE(SUM(CASE WHEN grupo = 'CONTROL' THEN ventas_reales_valor END), 0) AS ventas_control,
               COALESCE(SUM(CASE WHEN grupo = 'TRATAMIENTO' THEN ventas_reales_valor END), 0) AS ventas_tratamiento,
               COALESCE(SUM(CASE WHEN grupo = 'CONTROL' THEN merma_real_valor END), 0) AS merma_control,
               COALESCE(SUM(CASE WHEN grupo = 'TRATAMIENTO' THEN merma_real_valor END), 0) AS merma_tratamiento,
               COALESCE(SUM(CASE WHEN grupo = 'CONTROL' THEN error_absoluto END), 0) AS err_control,
               COALESCE(SUM(CASE WHEN grupo = 'CONTROL' THEN demanda_real END), 0) AS real_control,
               COALESCE(SUM(CASE WHEN grupo = 'TRATAMIENTO' THEN error_absoluto END), 0) AS err_tratamiento,
               COALESCE(SUM(CASE WHEN grupo = 'TRATAMIENTO' THEN demanda_real END), 0) AS real_tratamiento
        FROM analitica.experimento_ab_bitacora
        WHERE id_experimento = CAST(:id AS uuid)
        GROUP BY fecha
        ORDER BY fecha DESC
        LIMIT 21
        """,
        id=id_experimento,
    )

    return {
        "experimento": {
            **exp,
            "etiqueta_campeon": pronostico.METODOS.get(exp["modelo_campeon"], {}).get("etiqueta", exp["modelo_campeon"]),
            "etiqueta_retador": pronostico.METODOS.get(exp["modelo_retador"], {}).get("etiqueta", exp["modelo_retador"]),
        },
        "asignaciones": {
            "CONTROL": [a for a in asignaciones if a["grupo"] == "CONTROL"],
            "TRATAMIENTO": [a for a in asignaciones if a["grupo"] == "TRATAMIENTO"],
        },
        "serie_diaria": diario,
        **comp,
    }


def decidir_experimento_ab(
    id_experimento: str,
    *,
    decision: str,
    usuario: dict,
    notas: str = "",
) -> dict[str, Any]:
    """Cierra el experimento A/B promoviendo el Retador a Producción o descartándolo."""
    dec = (decision or "").upper()
    if dec not in ("PROMOVIDO", "DESCARTADO"):
        raise ValueError("La decisión del experimento debe ser PROMOVIDO o DESCARTADO.")

    res = resumen_experimento_ab(id_experimento)
    exp = res["experimento"]
    if exp["estado"] != "ACTIVO":
        raise ValueError(f"El experimento ya fue cerrado con estado {exp['estado']}.")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE analitica.experimento_ab
                   SET estado = :dec,
                       decision_final = :dec,
                       notas_decision = :notas,
                       fecha_cierre = now(),
                       id_usuario_decide = CAST(:uid AS uuid)
                 WHERE id_experimento = CAST(:id AS uuid)
                """
            ),
            {"dec": dec, "notas": notas, "uid": usuario["id_usuario"], "id": id_experimento},
        )

    campeon_actualizado = None
    if dec == "PROMOVIDO":
        campeon_actualizado = dom_lab.promover_a_campeon(
            metodo=exp["modelo_retador"],
            usuario=usuario,
            id_locacion=None,
            categoria=exp.get("categoria"),
            parametros=exp.get("parametros_retador") or {},
            metricas_lab=res["tratamiento"],
        )

    auditoria.registrar(
        "RUN_FORECAST",
        tabla="experimento_ab",
        id_registro=id_experimento,
        descripcion=f"Experimento A/B {dec}: {exp['modelo_retador']} frente a {exp['modelo_campeon']}",
        estado_anterior={"estado": "ACTIVO"},
        estado_nuevo={"estado": dec, "campeon": campeon_actualizado},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_experimento": id_experimento, "decision": dec, "campeon": campeon_actualizado}


def inicializar_experimento_si_vacio(usuario: dict) -> dict[str, Any] | None:
    """
    Si no existe ningún experimento A/B registrado todavía en la plataforma,
    inicializa automáticamente uno entre el Campeón Global y ETS_HOLT_WINTERS
    usando el reparto balanceado y los últimos 14 días reales de ventas y mermas.
    """
    try:
        if obtener_experimento_activo() is not None or listar_experimentos_ab(1):
            return None
        asignacion = sugerir_asignacion_balanceada()
        ctrl = [t["id_locacion"] for t in asignacion if t["grupo"] == "CONTROL"]
        trat = [t["id_locacion"] for t in asignacion if t["grupo"] == "TRATAMIENTO"]
        if not ctrl or not trat:
            return None
        gobernanza = dom_lab.obtener_campeon_y_retador()
        campeon = gobernanza["campeon"]["metodo"]
        retador = (gobernanza["retador"] or {}).get("metodo") or (
            "ETS_HOLT_WINTERS" if campeon != "ETS_HOLT_WINTERS" else "SUAVIZACION_EXPONENCIAL"
        )
        return crear_experimento_ab(
            nombre=f"{campeon} vs {retador} (Red en vivo)",
            modelo_campeon=campeon,
            modelo_retador=retador,
            tiendas_control=ctrl,
            tiendas_tratamiento=trat,
            usuario=usuario,
            duracion_dias=21,
            horizonte_dias=7,
            fecha_inicio=fecha_inicio_sugerida_real(14),
        )
    except Exception:
        return None
