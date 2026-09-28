"""
Motor de pronóstico.

Modelo simple y verificable — todavía sin LSTM, como pide la rúbrica:

  * MEDIA_MOVIL                → promedio de los últimos N días
  * MEDIA_MOVIL_PONDERADA      → promedio con pesos lineales crecientes
  * SUAVIZACION_EXPONENCIAL    → suavización exponencial simple (SES)

Sobre esos métodos se aplica un **índice de estacionalidad semanal** calculado
de la propia historia (la demanda de perecederos sube los fines de semana).
El cálculo es:

    1. Se desestacionaliza la serie:      y_adj[t] = y[t] / factor[día_semana(t)]
    2. Se aplica el método elegido a y_adj → nivel
    3. Pronóstico para la fecha objetivo: nivel * factor[día_semana(objetivo)]

La salida es siempre **por Producto + Tienda**, nunca un único pronóstico
global. Y la calidad se mide: MAE, RMSE y WMAPE sobre una ventana de backtest
tomada del final de la historia. El sistema no dice que un pronóstico es bueno
sin haberlo medido.

Cada corrida queda persistida en analitica.forecast_run y sus resultados en
analitica.forecast_result (producto, tienda, fecha, demanda pronosticada).
"""

from __future__ import annotations

import math
import time
from datetime import date, timedelta

from sqlalchemy import text

from app import auditoria
from app.db import a_float, escalar, one, query, transaccion

METODOS = {
    "MEDIA_MOVIL": {
        "etiqueta": "Media móvil",
        "descripcion": "Promedio simple de los últimos N días de venta.",
    },
    "MEDIA_MOVIL_PONDERADA": {
        "etiqueta": "Media móvil ponderada",
        "descripcion": "Promedio con pesos crecientes: los días recientes pesan más.",
    },
    "SUAVIZACION_EXPONENCIAL": {
        "etiqueta": "Suavización exponencial",
        "descripcion": "Suavización exponencial simple (SES) con factor alfa.",
    },
}


# ---------------------------------------------------------------------------
# Construcción de la serie
# ---------------------------------------------------------------------------
def _serie_completa(filas: list[dict], fecha_inicio: date, fecha_fin: date) -> list[tuple[date, float]]:
    """Rellena con ceros los días sin venta: una serie diaria debe ser continua."""
    por_fecha = {f["fecha"]: a_float(f["cantidad"]) for f in filas}
    serie = []
    dia = fecha_inicio
    while dia <= fecha_fin:
        serie.append((dia, por_fecha.get(dia, 0.0)))
        dia += timedelta(days=1)
    return serie


def _factores_semana(serie: list[tuple[date, float]]) -> dict[int, float]:
    """
    Índice de estacionalidad por día de la semana (lunes=0 … domingo=6).
    Se acota a [0.5, 2.0] para que un día atípico no distorsione todo.
    """
    acumulado: dict[int, list[float]] = {i: [] for i in range(7)}
    for fecha, valor in serie:
        acumulado[fecha.weekday()].append(valor)

    media_global = sum(v for _, v in serie) / len(serie) if serie else 0.0
    if media_global <= 0:
        return {i: 1.0 for i in range(7)}

    factores = {}
    for dow, valores in acumulado.items():
        if not valores:
            factores[dow] = 1.0
            continue
        media_dow = sum(valores) / len(valores)
        factores[dow] = min(2.0, max(0.5, media_dow / media_global))
    return factores


# ---------------------------------------------------------------------------
# Métodos de pronóstico (sobre la serie ya desestacionalizada)
# ---------------------------------------------------------------------------
def _media_movil(valores: list[float], ventana: int) -> float:
    muestra = valores[-ventana:] if ventana > 0 else valores
    return sum(muestra) / len(muestra) if muestra else 0.0


def _media_movil_ponderada(valores: list[float], ventana: int) -> float:
    muestra = valores[-ventana:] if ventana > 0 else valores
    if not muestra:
        return 0.0
    pesos = list(range(1, len(muestra) + 1))  # el más reciente pesa más
    total_pesos = sum(pesos)
    return sum(v * p for v, p in zip(muestra, pesos)) / total_pesos


def _suavizacion_exponencial(valores: list[float], alpha: float) -> float:
    if not valores:
        return 0.0
    alpha = min(0.99, max(0.01, alpha))
    nivel = valores[0]
    for valor in valores[1:]:
        nivel = alpha * valor + (1 - alpha) * nivel
    return nivel


def _nivel(valores: list[float], metodo: str, ventana: int, alpha: float) -> float:
    if not valores:
        return 0.0
    if metodo == "MEDIA_MOVIL":
        return _media_movil(valores, ventana)
    if metodo == "MEDIA_MOVIL_PONDERADA":
        return _media_movil_ponderada(valores, ventana)
    if metodo == "SUAVIZACION_EXPONENCIAL":
        return _suavizacion_exponencial(valores, alpha)
    raise ValueError(f"Método de pronóstico desconocido: {metodo}")


def _pronosticar_fecha(
    serie: list[tuple[date, float]],
    objetivo: date,
    metodo: str,
    ventana: int,
    alpha: float,
    factores: dict[int, float],
) -> float:
    """Pronóstico para una fecha concreta usando solo los datos anteriores."""
    ajustados = [v / factores[f.weekday()] for f, v in serie]
    nivel = _nivel(ajustados, metodo, ventana, alpha)
    return max(0.0, nivel * factores[objetivo.weekday()])


def _metricas(reales: list[float], pronosticados: list[float]) -> dict:
    if not reales:
        return {"mae": None, "rmse": None, "wmape": None, "n": 0}
    errores = [r - p for r, p in zip(reales, pronosticados)]
    mae = sum(abs(e) for e in errores) / len(errores)
    rmse = math.sqrt(sum(e * e for e in errores) / len(errores))
    suma_real = sum(abs(r) for r in reales)
    wmape = (sum(abs(e) for e in errores) / suma_real * 100) if suma_real > 0 else None
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wmape": round(wmape, 4) if wmape is not None else None,
        "n": len(reales),
    }


def pronosticar_serie(
    serie: list[tuple[date, float]],
    metodo: str,
    horizonte: int,
    ventana: int,
    alpha: float,
    fecha_base: date,
) -> dict:
    """
    Pronostica una serie (producto + tienda) y mide su error con backtest.

    El backtest es walk-forward sobre los últimos `horizonte` días de historia:
    para cada día se pronostica usando únicamente la información previa.
    """
    factores = _factores_semana(serie)
    dias_backtest = min(horizonte, max(1, len(serie) // 5))

    reales, pronosticados = [], []
    if len(serie) > dias_backtest:
        for i in range(len(serie) - dias_backtest, len(serie)):
            entrenamiento = serie[:i]
            fecha, real = serie[i]
            pronosticados.append(
                _pronosticar_fecha(entrenamiento, fecha, metodo, ventana, alpha, factores)
            )
            reales.append(real)

    pronostico = []
    for h in range(1, horizonte + 1):
        objetivo = fecha_base + timedelta(days=h)
        pronostico.append(
            {
                "fecha": objetivo,
                "horizonte_dia": h,
                "valor": round(
                    _pronosticar_fecha(serie, objetivo, metodo, ventana, alpha, factores),
                    2,
                ),
            }
        )

    return {
        "pronostico": pronostico,
        "metricas": _metricas(reales, pronosticados),
        "factores_semana": factores,
        "dias_backtest": dias_backtest,
        "nivel_ajustado": round(
            _nivel(
                [v / factores[f.weekday()] for f, v in serie], metodo, ventana, alpha
            ),
            2,
        ),
    }


# ---------------------------------------------------------------------------
# Ejecución y persistencia
# ---------------------------------------------------------------------------
def ejecutar_pronostico(
    *,
    usuario: dict,
    metodo: str = "SUAVIZACION_EXPONENCIAL",
    horizonte: int = 7,
    ventana: int = 28,
    alpha: float = 0.30,
    dias_historia: int = 120,
    min_dias_historia: int = 14,
    id_locacion: int | None = None,
    id_sku: int | None = None,
) -> dict:
    """
    Corre el pronóstico para todos los pares producto+tienda con historia
    suficiente y lo persiste. Devuelve el resumen de la corrida.
    """
    if metodo not in METODOS:
        raise ValueError(f"Método no soportado: {metodo}")
    if not 1 <= horizonte <= 90:
        raise ValueError("El horizonte debe estar entre 1 y 90 días.")

    fecha_fin = escalar("SELECT max(fecha) FROM analitica.v_demanda_diaria") or date.today()
    fecha_inicio = fecha_fin - timedelta(days=dias_historia)

    condiciones = ["fecha >= :inicio"]
    params: dict = {"inicio": fecha_inicio}
    if id_locacion:
        condiciones.append("id_locacion = :id_locacion")
        params["id_locacion"] = id_locacion
    if id_sku:
        condiciones.append("id_sku = :id_sku")
        params["id_sku"] = id_sku

    filas = query(
        f"""
        SELECT id_sku, id_locacion, fecha, cantidad
        FROM analitica.v_demanda_diaria
        WHERE {' AND '.join(condiciones)}
        ORDER BY id_sku, id_locacion, fecha
        """,
        **params,
    )

    # Agrupar por (sku, tienda)
    grupos: dict[tuple[int, int], list[dict]] = {}
    for fila in filas:
        grupos.setdefault((fila["id_sku"], fila["id_locacion"]), []).append(fila)

    inicio_reloj = time.time()
    id_run = None
    series_procesadas = 0
    resultados: list[dict] = []
    suma_abs, suma_cuad, suma_real, n_total = 0.0, 0.0, 0.0, 0

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        id_run = conn.execute(
            text(
                """
                INSERT INTO analitica.forecast_run
                    (metodo, parametros, periodo_inicio, periodo_fin, horizonte_dias,
                     id_usuario, estado, n_series)
                VALUES (:metodo, CAST(:params AS jsonb), :inicio, :fin, :horizonte,
                        CAST(:uid AS uuid), 'PARCIAL', 0)
                RETURNING id_run::text
                """
            ),
            {
                "metodo": metodo,
                "params": _json(
                    {"ventana": ventana, "alpha": alpha, "dias_historia": dias_historia}
                ),
                "inicio": fecha_inicio,
                "fin": fecha_fin,
                "horizonte": horizonte,
                "uid": usuario["id_usuario"],
            },
        ).scalar()

        for (sku, loc), filas_serie in grupos.items():
            serie = _serie_completa(filas_serie, fecha_inicio, fecha_fin)
            if sum(1 for _, v in serie if v > 0) < min_dias_historia:
                continue

            salida = pronosticar_serie(
                serie, metodo, horizonte, ventana, alpha, fecha_fin
            )
            metricas = salida["metricas"]
            series_procesadas += 1

            for punto in salida["pronostico"]:
                conn.execute(
                    text(
                        """
                        INSERT INTO analitica.forecast_result
                            (id_run, id_sku, id_locacion, fecha_objetivo,
                             horizonte_dia, demanda_pronosticada)
                        VALUES (CAST(:id_run AS uuid), :sku, :loc, :fecha, :h, :valor)
                        ON CONFLICT (id_run, id_sku, id_locacion, fecha_objetivo)
                        DO UPDATE SET demanda_pronosticada = EXCLUDED.demanda_pronosticada
                        """
                    ),
                    {
                        "id_run": id_run,
                        "sku": sku,
                        "loc": loc,
                        "fecha": punto["fecha"],
                        "h": punto["horizonte_dia"],
                        "valor": punto["valor"],
                    },
                )

            resultados.append(
                {
                    "id_sku": sku,
                    "id_locacion": loc,
                    "metricas": metricas,
                    "pronostico": salida["pronostico"],
                }
            )
            if metricas["n"]:
                suma_abs += metricas["mae"] * metricas["n"]
                suma_cuad += (metricas["rmse"] ** 2) * metricas["n"]
                n_total += metricas["n"]

        mae_global = round(suma_abs / n_total, 4) if n_total else None
        rmse_global = round(math.sqrt(suma_cuad / n_total), 4) if n_total else None
        wmape_global = None
        if n_total:
            suma_real_total = escalar(
                """
                SELECT COALESCE(SUM(cantidad), 0) FROM analitica.v_demanda_diaria
                WHERE fecha >= CURRENT_DATE - :h
                """,
                h=horizonte,
            )
            suma_real_total = a_float(suma_real_total)
            if suma_real_total > 0:
                wmape_global = round(suma_abs / suma_real_total * 100, 4)

        duracion = int((time.time() - inicio_reloj) * 1000)
        conn.execute(
            text(
                """
                UPDATE analitica.forecast_run
                   SET estado = 'COMPLETADO', n_series = :n, mae = :mae,
                       rmse = :rmse, wmape = :wmape, duracion_ms = :ms
                 WHERE id_run = CAST(:id AS uuid)
                """
            ),
            {
                "n": series_procesadas,
                "mae": mae_global,
                "rmse": rmse_global,
                "wmape": wmape_global,
                "ms": duracion,
                "id": id_run,
            },
        )

    auditoria.registrar(
        "RUN_FORECAST",
        tabla="forecast_run",
        id_registro=id_run,
        descripcion=(
            f"Pronóstico {METODOS[metodo]['etiqueta']} · horizonte {horizonte} días · "
            f"{series_procesadas} series · MAE {mae_global}"
        ),
        estado_nuevo={
            "metodo": metodo,
            "horizonte": horizonte,
            "ventana": ventana,
            "alpha": alpha,
            "series": series_procesadas,
            "mae": mae_global,
            "rmse": rmse_global,
            "wmape": wmape_global,
        },
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    return {
        "id_run": id_run,
        "metodo": metodo,
        "metodo_etiqueta": METODOS[metodo]["etiqueta"],
        "horizonte": horizonte,
        "series": series_procesadas,
        "mae": mae_global,
        "rmse": rmse_global,
        "wmape": wmape_global,
        "resultados": resultados,
        "duracion_ms": duracion,
    }


def _json(valor) -> str:
    import json

    return json.dumps(valor, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
def ultima_corrida() -> dict | None:
    return one(
        """
        SELECT r.id_run::text, r.metodo, r.parametros, r.periodo_inicio, r.periodo_fin,
               r.horizonte_dias, r.fecha_ejecucion, r.n_series, r.estado,
               r.mae, r.rmse, r.wmape, r.duracion_ms,
               u.nombre_completo AS ejecutado_por
        FROM analitica.forecast_run r
        LEFT JOIN operacion.usuario u ON u.id_usuario = r.id_usuario
        WHERE r.estado = 'COMPLETADO'
        ORDER BY r.fecha_ejecucion DESC
        LIMIT 1
        """
    )


def corridas(limite: int = 20) -> list[dict]:
    return query(
        """
        SELECT r.id_run::text, r.metodo, r.horizonte_dias, r.fecha_ejecucion,
               r.n_series, r.mae, r.rmse, r.wmape, r.duracion_ms, r.estado,
               r.periodo_inicio, r.periodo_fin,
               u.nombre_completo AS ejecutado_por
        FROM analitica.forecast_run r
        LEFT JOIN operacion.usuario u ON u.id_usuario = r.id_usuario
        ORDER BY r.fecha_ejecucion DESC
        LIMIT :limite
        """,
        limite=limite,
    )


def pronostico_por_serie(id_run: str, limite: int = 300) -> list[dict]:
    """
    Pronóstico agregado por Producto + Tienda: próximo día y próximos N días.
    Es el formato que exige la rúbrica.
    """
    return query(
        """
        SELECT p.nombre AS producto, p.id_sku, p.unidad_medida,
               loc.nombre AS locacion, loc.id_locacion,
               COALESCE(SUM(CASE WHEN fr.horizonte_dia = 1
                                 THEN fr.demanda_pronosticada END), 0) AS proximo_dia,
               COALESCE(SUM(fr.demanda_pronosticada), 0)                 AS total_horizonte,
               MAX(r.horizonte_dias)                                     AS horizonte_dias,
               MIN(fr.fecha_objetivo)                                    AS desde,
               MAX(fr.fecha_objetivo)                                    AS hasta
        FROM analitica.forecast_result fr
        JOIN analitica.forecast_run r ON r.id_run = fr.id_run
        JOIN operacion.producto p     ON p.id_sku = fr.id_sku
        JOIN operacion.locacion loc   ON loc.id_locacion = fr.id_locacion
        WHERE fr.id_run = CAST(:id_run AS uuid)
        GROUP BY p.nombre, p.id_sku, p.unidad_medida, loc.nombre, loc.id_locacion
        ORDER BY p.nombre, loc.nombre
        LIMIT :limite
        """,
        id_run=id_run,
        limite=limite,
    )


def detalle_serie(id_run: str, id_sku: int, id_locacion: int) -> list[dict]:
    return query(
        """
        SELECT fecha_objetivo, horizonte_dia, demanda_pronosticada,
               demanda_real, error_absoluto
        FROM analitica.forecast_result
        WHERE id_run = CAST(:id_run AS uuid) AND id_sku = :sku AND id_locacion = :loc
        ORDER BY fecha_objetivo
        """,
        id_run=id_run,
        sku=id_sku,
        loc=id_locacion,
    )


def historico_vs_pronostico(id_sku: int, id_locacion: int, dias: int = 60) -> list[dict]:
    """Historia real reciente, para graficar junto al pronóstico."""
    return query(
        """
        SELECT fecha, SUM(cantidad) AS cantidad
        FROM analitica.v_demanda_diaria
        WHERE id_sku = :sku AND id_locacion = :loc
          AND fecha >= CURRENT_DATE - :dias
        GROUP BY fecha ORDER BY fecha
        """,
        sku=id_sku,
        loc=id_locacion,
        dias=dias,
    )


def pronostico_actual_por_sku_loc(id_sku: int, id_locacion: int) -> dict | None:
    """Pronóstico vigente (última corrida) para un producto y tienda."""
    return one(
        """
        SELECT fr.id_run::text, SUM(fr.demanda_pronosticada) AS total,
               SUM(CASE WHEN fr.horizonte_dia = 1 THEN fr.demanda_pronosticada END) AS proximo_dia,
               COUNT(*) AS dias, MIN(fr.fecha_objetivo) AS desde, MAX(fr.fecha_objetivo) AS hasta
        FROM analitica.forecast_result fr
        WHERE fr.id_sku = :sku AND fr.id_locacion = :loc
          AND fr.id_run = (
              SELECT id_run FROM analitica.forecast_run
              WHERE estado = 'COMPLETADO' ORDER BY fecha_ejecucion DESC LIMIT 1
          )
        GROUP BY fr.id_run
        """,
        sku=id_sku,
        loc=id_locacion,
    )


def demanda_diaria_promedio(id_sku: int, id_locacion: int, dias: int = 28) -> float:
    """Demanda promedio diaria reciente (usada por el motor de reabastecimiento)."""
    valor = escalar(
        """
        SELECT COALESCE(AVG(cantidad), 0) FROM (
            SELECT fecha, SUM(cantidad) AS cantidad
            FROM analitica.v_demanda_diaria
            WHERE id_sku = :sku AND id_locacion = :loc
              AND fecha >= CURRENT_DATE - :dias
            GROUP BY fecha
        ) s
        """,
        sku=id_sku,
        loc=id_locacion,
        dias=dias,
    )
    return a_float(valor)


def precision_global() -> dict:
    """Precisión del último pronóstico, ya contrastada contra la demanda real."""
    fila = one(
        """
        SELECT r.id_run::text, r.metodo, r.mae, r.rmse, r.wmape, r.fecha_ejecucion,
               r.horizonte_dias,
               COUNT(fr.id_resultado)                                          AS puntos,
               COUNT(fr.demanda_real)                                          AS puntos_evaluados,
               COALESCE(SUM(ABS(fr.error_absoluto)), 0)                        AS error_total,
               COALESCE(SUM(fr.demanda_real), 0)                               AS demanda_real_total
        FROM analitica.forecast_run r
        LEFT JOIN analitica.forecast_result fr ON fr.id_run = r.id_run
        WHERE r.estado = 'COMPLETADO'
          AND r.id_run = (
              SELECT id_run FROM analitica.forecast_run
              WHERE estado = 'COMPLETADO' ORDER BY fecha_ejecucion DESC LIMIT 1
          )
        GROUP BY r.id_run, r.metodo, r.mae, r.rmse, r.wmape, r.fecha_ejecucion, r.horizonte_dias
        """
    ) or {}
    if fila:
        real = a_float(fila.get("demanda_real_total"))
        fila["mae_observado"] = (
            round(a_float(fila["error_total"]) / fila["puntos_evaluados"], 2)
            if fila.get("puntos_evaluados")
            else None
        )
        fila["wmape_observado"] = (
            round(a_float(fila["error_total"]) / real * 100, 2) if real else None
        )
    return fila


def consolidar_demanda_real() -> int:
    """
    Rellena demanda_real y error_absoluto de los pronósticos cuya fecha ya
    pasó. Permite medir la precisión de forma acumulada, no solo en backtest.
    """
    with transaccion() as conn:
        res = conn.execute(
            text(
                """
                UPDATE analitica.forecast_result fr
                   SET demanda_real = d.cantidad,
                       error_absoluto = ABS(fr.demanda_pronosticada - d.cantidad)
                  FROM (
                      SELECT id_sku, id_locacion, fecha, SUM(cantidad) AS cantidad
                      FROM analitica.v_demanda_diaria
                      GROUP BY id_sku, id_locacion, fecha
                  ) d
                 WHERE fr.id_sku = d.id_sku
                   AND fr.id_locacion = d.id_locacion
                   AND fr.fecha_objetivo = d.fecha
                   AND fr.demanda_real IS NULL
                """
            )
        )
        return res.rowcount or 0
