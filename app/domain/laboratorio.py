"""
Etapa 2: Laboratorio Offline (Entrenamiento, Backtest y Simulación Newsvendor).

Mantiene el desacoplamiento:
  - `pronostico.py` entrega únicamente la distribución esperada (media y sigma)
    durante el backtest walk-forward.
  - `laboratorio.py` toma esa salida pura y la evalúa económicamente contra
    costos de merma/faltante (Newsvendor) y valor agregado sobre Naive (FVA).
"""

from __future__ import annotations

import json
import math
from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import auditoria
from app.db import a_float, a_int, escalar, one, query, transaccion
from app.domain import pronostico

MODELOS_LABORATORIO: tuple[str, ...] = (
    "AUTO",
    "ETS_HOLT_WINTERS",
    "SUAVIZACION_EXPONENCIAL",
    "MEDIA_MOVIL_PONDERADA",
    "MEDIA_MOVIL",
)


def _json(valor: Any) -> str:
    return json.dumps(valor, default=str, ensure_ascii=False)


def categorias_con_historia() -> list[str]:
    """Lista las categorías activas con ventas históricas disponibles para el laboratorio."""
    try:
        filas = query(
            """
            SELECT DISTINCT p.categoria
            FROM operacion.producto p
            JOIN analitica.v_demanda_diaria v ON v.id_sku = p.id_sku
            WHERE p.activo = true AND p.categoria IS NOT NULL AND p.categoria <> ''
            ORDER BY p.categoria
            """
        )
        return [f["categoria"] for f in filas if f.get("categoria")]
    except SQLAlchemyError:
        return []


def asegurar_campeon_global() -> dict[str, Any]:
    """
    Garantiza que exista un Campeón Global activo en `analitica.modelo_produccion`.
    Si aún no hay ninguno, establece `AUTO` por defecto de forma idempotente.
    """
    defecto = {
        "id_config": None,
        "id_locacion": None,
        "categoria": None,
        "rol_modelo": "CAMPEON",
        "metodo": "AUTO",
        "etiqueta": pronostico.METODOS["AUTO"]["etiqueta"],
        "parametros": {"horizonte": 7, "ventana": 28, "alpha": 0.30},
        "metricas_lab": {},
        "fecha_promocion": None,
    }
    try:
        existente = one(
            """
            SELECT id_config::text, id_locacion, categoria, rol_modelo, metodo,
                   parametros, metricas_lab, fecha_promocion
            FROM analitica.modelo_produccion
            WHERE rol_modelo = 'CAMPEON'
              AND id_locacion IS NULL
              AND categoria IS NULL
              AND activo = true
            ORDER BY fecha_promocion DESC
            LIMIT 1
            """
        )
        if existente:
            existente["etiqueta"] = pronostico.METODOS.get(
                existente["metodo"], {}
            ).get("etiqueta", existente["metodo"])
            return existente

        with transaccion() as conn:
            id_cfg = conn.execute(
                text(
                    """
                    INSERT INTO analitica.modelo_produccion
                        (id_locacion, categoria, rol_modelo, metodo, parametros, metricas_lab, activo)
                    VALUES (NULL, NULL, 'CAMPEON', 'AUTO',
                            CAST(:params AS jsonb), '{}'::jsonb, true)
                    RETURNING id_config::text
                    """
                ),
                {"params": _json(defecto["parametros"])},
            ).scalar()
        defecto["id_config"] = id_cfg
        return defecto
    except SQLAlchemyError:
        return defecto


def obtener_campeon_y_retador(
    id_locacion: int | None = None,
    categoria: str | None = None,
) -> dict[str, Any]:
    """Devuelve el modelo Campeón vigente (prioriza específico → global) y el Retador activo."""
    campeon_global = asegurar_campeon_global()
    campeon = campeon_global
    retador = None
    try:
        filas = query(
            """
            SELECT id_config::text, id_locacion, categoria, rol_modelo, metodo,
                   parametros, metricas_lab, fecha_promocion
            FROM analitica.modelo_produccion
            WHERE activo = true
            ORDER BY
                (CASE WHEN id_locacion = :loc THEN 0 ELSE 1 END),
                (CASE WHEN categoria = :cat THEN 0 ELSE 1 END),
                fecha_promocion DESC
            """,
            loc=id_locacion,
            cat=categoria,
        )
        for f in filas:
            f["etiqueta"] = pronostico.METODOS.get(f["metodo"], {}).get("etiqueta", f["metodo"])
            if f["rol_modelo"] == "CAMPEON" and campeon is campeon_global:
                if (f["id_locacion"] in (id_locacion, None)) and (f["categoria"] in (categoria, None)):
                    campeon = f
            elif f["rol_modelo"] == "RETADOR" and retador is None:
                if (f["id_locacion"] in (id_locacion, None)) and (f["categoria"] in (categoria, None)):
                    retador = f
    except SQLAlchemyError:
        pass
    return {"campeon": campeon, "retador": retador}


def simular_newsvendor_backtest(
    puntos: list[dict[str, Any]],
    *,
    precio_venta: float,
    precio_costo: float,
    vida_util_dias: int,
    sigma_diaria: float,
) -> dict[str, float]:
    """
    Simula la política Newsvendor día a día sobre los resultados del backtest walk-forward:
      - Calcula el cuantil objetivo Q*(F*) usando la predicción (media) y sigma del modelo.
      - Contrastado con la demanda real del día, mide merma simulada y venta perdida.
    """
    p_venta = max(0.0, a_float(precio_venta))
    p_costo = max(0.01, a_float(precio_costo))
    vida = max(1, a_int(vida_util_dias, 7))
    v_salv = round(p_costo * 0.25, 2) if vida > 3 else 0.0
    c_u = max(0.01, p_venta - p_costo)
    c_o = max(0.01, p_costo - v_salv)
    fractil = c_u / (c_u + c_o)
    factor_caducidad = min(1.0, 1.0 / vida)

    merma_u = 0.0
    merma_val = 0.0
    faltante_u = 0.0
    faltante_val = 0.0

    for pt in puntos:
        real = max(0.0, a_float(pt.get("real")))
        pred = max(0.0, a_float(pt.get("pred")))
        sigma = max(0.0, a_float(sigma_diaria))
        q_opt = pronostico.cuantil_normal(pred, sigma, fractil)
        exceso = max(0.0, q_opt - real)
        faltante = max(0.0, real - q_opt)

        m_u = exceso * factor_caducidad
        merma_u += m_u
        merma_val += m_u * c_o
        faltante_u += faltante
        faltante_val += faltante * c_u

    return {
        "merma_simulada_unidades": round(merma_u, 2),
        "merma_simulada_valor": round(merma_val, 2),
        "venta_perdida_unidades": round(faltante_u, 2),
        "venta_perdida_valor": round(faltante_val, 2),
        "costo_total_simulado": round(merma_val + faltante_val, 2),
    }


def evaluar_modelos_laboratorio(
    *,
    id_locacion: int | None = None,
    categoria: str | None = None,
    horizonte: int = 7,
    ventana: int = 28,
    alpha: float = 0.30,
    dias_historia: int = 120,
    min_dias_historia: int = 14,
) -> dict[str, Any]:
    """
    Etapa 2: evalúa todos los modelos en walk-forward y ejecuta la simulación Newsvendor.
    Devuelve tabla comparativa con WMAPE, Bias, FVA vs. Naive y Merma Simulada.
    """
    from datetime import date

    fecha_fin = escalar("SELECT max(fecha) FROM analitica.v_demanda_diaria") or date.today()
    fecha_inicio = fecha_fin - timedelta(days=dias_historia)

    condiciones = ["v.fecha >= :inicio", "loc.activo = true", "p.activo = true"]
    params: dict[str, Any] = {"inicio": fecha_inicio}
    if id_locacion:
        condiciones.append("v.id_locacion = :id_locacion")
        params["id_locacion"] = id_locacion
    if categoria:
        condiciones.append("p.categoria = :categoria")
        params["categoria"] = categoria

    filas = query(
        f"""
        SELECT v.id_sku, v.id_locacion, v.fecha, v.cantidad,
               p.nombre AS producto, p.categoria, p.precio_venta, p.precio_costo,
               p.vida_util_estandar, loc.nombre AS locacion
        FROM analitica.v_demanda_diaria v
        JOIN operacion.producto p   ON p.id_sku = v.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = v.id_locacion
        WHERE {' AND '.join(condiciones)}
        ORDER BY v.id_sku, v.id_locacion, v.fecha
        """,
        **params,
    )

    grupos: dict[tuple[int, int], list[dict]] = {}
    meta_serie: dict[tuple[int, int], dict[str, Any]] = {}
    for f in filas:
        key = (f["id_sku"], f["id_locacion"])
        grupos.setdefault(key, []).append(f)
        if key not in meta_serie:
            meta_serie[key] = {
                "producto": f["producto"],
                "locacion": f["locacion"],
                "categoria": f["categoria"],
                "precio_venta": a_float(f["precio_venta"], 20.0),
                "precio_costo": a_float(f["precio_costo"], 10.0),
                "vida_util_dias": a_int(f["vida_util_estandar"], 7),
            }

    modelos_eval = (*MODELOS_LABORATORIO, "NAIVE")
    acum: dict[str, dict[str, Any]] = {
        m: {
            "abs": 0.0,
            "cuad": 0.0,
            "sesgo": 0.0,
            "real": 0.0,
            "n": 0,
            "merma_u": 0.0,
            "merma_val": 0.0,
            "perdida_u": 0.0,
            "perdida_val": 0.0,
            "costo_total": 0.0,
        }
        for m in modelos_eval
    }

    series_evaluadas = 0
    for key, filas_serie in grupos.items():
        serie = pronostico._serie_completa(filas_serie, fecha_inicio, fecha_fin)
        if sum(1 for _, v in serie if v > 0) < min_dias_historia:
            continue
        series_evaluadas += 1
        info = meta_serie[key]

        naive_capturado = False
        for modelo in MODELOS_LABORATORIO:
            sal = pronostico.pronosticar_serie(serie, modelo, horizonte, ventana, alpha, fecha_fin)
            m = sal["metricas"]
            puntos = sal.get("backtest_puntos") or []
            sim = simular_newsvendor_backtest(
                puntos,
                precio_venta=info["precio_venta"],
                precio_costo=info["precio_costo"],
                vida_util_dias=info["vida_util_dias"],
                sigma_diaria=a_float(sal.get("sigma_diaria"), 0.0),
            )
            a = acum[modelo]
            if m["n"]:
                a["abs"] += (m["mae"] or 0.0) * m["n"]
                a["cuad"] += ((m["rmse"] or 0.0) ** 2) * m["n"]
                a["sesgo"] += (m.get("sesgo") or 0.0) * m["n"]
                a["real"] += m.get("suma_real") or 0.0
                a["n"] += m["n"]
            a["merma_u"] += sim["merma_simulada_unidades"]
            a["merma_val"] += sim["merma_simulada_valor"]
            a["perdida_u"] += sim["venta_perdida_unidades"]
            a["perdida_val"] += sim["venta_perdida_valor"]
            a["costo_total"] += sim["costo_total_simulado"]

            if not naive_capturado:
                mn = sal["metricas_naive"]
                puntos_naive = [{"real": pt["real"], "pred": pt["naive"]} for pt in puntos]
                reales_n = [pt["real"] for pt in puntos]
                preds_n = [pt["naive"] for pt in puntos]
                sigma_n = (
                    math.sqrt(sum((r - p) ** 2 for r, p in zip(reales_n, preds_n)) / len(reales_n))
                    if reales_n
                    else 0.0
                )
                sim_n = simular_newsvendor_backtest(
                    puntos_naive,
                    precio_venta=info["precio_venta"],
                    precio_costo=info["precio_costo"],
                    vida_util_dias=info["vida_util_dias"],
                    sigma_diaria=sigma_n,
                )
                an = acum["NAIVE"]
                if mn["n"]:
                    an["abs"] += (mn["mae"] or 0.0) * mn["n"]
                    an["cuad"] += ((mn["rmse"] or 0.0) ** 2) * mn["n"]
                    an["sesgo"] += (mn.get("sesgo") or 0.0) * mn["n"]
                    an["real"] += mn.get("suma_real") or 0.0
                    an["n"] += mn["n"]
                an["merma_u"] += sim_n["merma_simulada_unidades"]
                an["merma_val"] += sim_n["merma_simulada_valor"]
                an["perdida_u"] += sim_n["venta_perdida_unidades"]
                an["perdida_val"] += sim_n["venta_perdida_valor"]
                an["costo_total"] += sim_n["costo_total_simulado"]
                naive_capturado = True

    an = acum["NAIVE"]
    wmape_naive = (an["abs"] / an["real"] * 100.0) if an["real"] > 0 else None
    costo_naive = an["costo_total"]

    gobernanza = obtener_campeon_y_retador(id_locacion=id_locacion, categoria=categoria)
    metodo_campeon = gobernanza["campeon"]["metodo"]
    metodo_retador = gobernanza["retador"]["metodo"] if gobernanza["retador"] else None

    tabla: list[dict[str, Any]] = []
    for modelo in modelos_eval:
        a = acum[modelo]
        n = a["n"]
        wmape = round(a["abs"] / a["real"] * 100.0, 2) if a["real"] > 0 else None
        mae = round(a["abs"] / n, 2) if n else None
        rmse = round(math.sqrt(a["cuad"] / n), 2) if n else None
        sesgo = round(a["sesgo"] / n, 2) if n else None
        fva_pp = (
            round(wmape_naive - wmape, 2)
            if (wmape_naive is not None and wmape is not None and modelo != "NAIVE")
            else (0.0 if modelo == "NAIVE" else None)
        )
        etiqueta = (
            "Referencia semanal (Naive)"
            if modelo == "NAIVE"
            else pronostico.METODOS[modelo]["etiqueta"]
        )
        tabla.append(
            {
                "modelo": modelo,
                "etiqueta": etiqueta,
                "es_naive": modelo == "NAIVE",
                "es_campeon": modelo == metodo_campeon,
                "es_retador": modelo == metodo_retador,
                "recomendado": False,
                "wmape": wmape,
                "mae": mae,
                "rmse": rmse,
                "sesgo": sesgo,
                "fva_pp": fva_pp,
                "merma_simulada_unidades": round(a["merma_u"], 2),
                "merma_simulada_valor": round(a["merma_val"], 2),
                "venta_perdida_unidades": round(a["perdida_u"], 2),
                "venta_perdida_valor": round(a["perdida_val"], 2),
                "costo_total_simulado": round(a["costo_total"], 2),
                "ahorro_vs_naive_valor": round(costo_naive - a["costo_total"], 2),
                "puntos_evaluados": n,
            }
        )

    candidatos_reales = [r for r in tabla if not r["es_naive"] and r["wmape"] is not None]
    if candidatos_reales:
        ganador = min(
            candidatos_reales,
            key=lambda r: (r["costo_total_simulado"], r["wmape"]),
        )
        ganador["recomendado"] = True

    tabla.sort(
        key=lambda r: (
            1 if r["es_naive"] else 0,
            r["costo_total_simulado"],
            r["wmape"] if r["wmape"] is not None else 9999.0,
        )
    )

    return {
        "alcance": {
            "id_locacion": id_locacion,
            "categoria": categoria or "Todas",
            "horizonte": horizonte,
            "series_evaluadas": series_evaluadas,
            "periodo_inicio": fecha_inicio.isoformat(),
            "periodo_fin": fecha_fin.isoformat(),
        },
        "modelos": tabla,
        "campeon": gobernanza["campeon"],
        "retador": gobernanza["retador"],
    }


def _promover_rol_modelo(
    *,
    rol_modelo: str,
    metodo: str,
    usuario: dict,
    id_locacion: int | None = None,
    categoria: str | None = None,
    parametros: dict | None = None,
    metricas_lab: dict | None = None,
) -> dict[str, Any]:
    metodo = (metodo or "").upper()
    if metodo not in pronostico.METODOS:
        raise ValueError(f"Modelo '{metodo}' no válido para producción/laboratorio.")
    rol = rol_modelo.upper()
    if rol not in ("CAMPEON", "RETADOR"):
        raise ValueError("rol_modelo debe ser CAMPEON o RETADOR.")

    cat = categoria.strip() if isinstance(categoria, str) and categoria.strip() else None
    params_norm = parametros or {"horizonte": 7, "ventana": 28, "alpha": 0.30}
    metricas_norm = metricas_lab or {}

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE analitica.modelo_produccion
                   SET activo = false
                 WHERE rol_modelo = :rol
                   AND activo = true
                   AND ((id_locacion IS NULL AND :loc IS NULL) OR id_locacion = :loc)
                   AND ((categoria IS NULL AND :cat IS NULL) OR categoria = :cat)
                """
            ),
            {"rol": rol, "loc": id_locacion, "cat": cat},
        )
        id_cfg = conn.execute(
            text(
                """
                INSERT INTO analitica.modelo_produccion
                    (id_locacion, categoria, rol_modelo, metodo, parametros, metricas_lab, activo, promovido_por)
                VALUES
                    (:loc, :cat, :rol, :metodo, CAST(:params AS jsonb), CAST(:met AS jsonb), true, CAST(:uid AS uuid))
                RETURNING id_config::text
                """
            ),
            {
                "loc": id_locacion,
                "cat": cat,
                "rol": rol,
                "metodo": metodo,
                "params": _json(params_norm),
                "met": _json(metricas_norm),
                "uid": usuario["id_usuario"],
            },
        ).scalar()

    etiqueta = pronostico.METODOS[metodo]["etiqueta"]
    auditoria.registrar(
        "RUN_FORECAST",
        tabla="modelo_produccion",
        id_registro=id_cfg,
        descripcion=f"Modelo promovido a {rol}: {etiqueta} (locación={id_locacion or 'Global'}, categoría={cat or 'Todas'})",
        estado_nuevo={"rol_modelo": rol, "metodo": metodo, "id_locacion": id_locacion, "categoria": cat},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {
        "id_config": id_cfg,
        "rol_modelo": rol,
        "metodo": metodo,
        "etiqueta": etiqueta,
        "id_locacion": id_locacion,
        "categoria": cat,
    }


def promover_a_retador(
    *,
    metodo: str,
    usuario: dict,
    id_locacion: int | None = None,
    categoria: str | None = None,
    parametros: dict | None = None,
    metricas_lab: dict | None = None,
) -> dict[str, Any]:
    return _promover_rol_modelo(
        rol_modelo="RETADOR",
        metodo=metodo,
        usuario=usuario,
        id_locacion=id_locacion,
        categoria=categoria,
        parametros=parametros,
        metricas_lab=metricas_lab,
    )


def promover_a_campeon(
    *,
    metodo: str,
    usuario: dict,
    id_locacion: int | None = None,
    categoria: str | None = None,
    parametros: dict | None = None,
    metricas_lab: dict | None = None,
) -> dict[str, Any]:
    return _promover_rol_modelo(
        rol_modelo="CAMPEON",
        metodo=metodo,
        usuario=usuario,
        id_locacion=id_locacion,
        categoria=categoria,
        parametros=parametros,
        metricas_lab=metricas_lab,
    )
