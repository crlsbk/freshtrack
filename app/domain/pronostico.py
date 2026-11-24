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
import os
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, config_valor, escalar, one, query, transaccion
from app.events.dispatcher import publicar_evento
from app.services import cache_service
from app.services.doc_store import guardar_pronostico
from app.domain.cache_web import con_cache_web

METODOS_BASE = ("SUAVIZACION_EXPONENCIAL", "MEDIA_MOVIL_PONDERADA", "MEDIA_MOVIL")

METODOS = {
    "AUTO": {
        "etiqueta": "Automático por tienda",
        "descripcion": "Evalúa estrategias de demanda dentro de cada tienda y elige automáticamente la de menor error sin configuración manual.",
    },
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
        return {
            "mae": None,
            "rmse": None,
            "wmape": None,
            "wape": None,
            "sesgo": None,
            "demanda_intermitente": False,
            "n": 0,
            "suma_real": 0.0,
        }
    errores = [r - p for r, p in zip(reales, pronosticados)]
    mae = sum(abs(e) for e in errores) / len(errores)
    rmse = math.sqrt(sum(e * e for e in errores) / len(errores))
    # Sesgo (Bias): promedio de (pronosticado - real). >0 sobreestima, <0 subestima.
    sesgo = sum(p - r for r, p in zip(reales, pronosticados)) / len(errores)
    suma_real = sum(abs(r) for r in reales)
    wmape = (sum(abs(e) for e in errores) / suma_real * 100) if suma_real > 0 else None
    ceros = sum(1 for r in reales if abs(r) < 1e-9)
    intermitente = (ceros / len(reales)) >= 0.30
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "wmape": round(wmape, 4) if wmape is not None else None,
        "wape": round(wmape, 4) if wmape is not None else None,
        "sesgo": round(sesgo, 4),
        "demanda_intermitente": intermitente,
        "n": len(reales),
        "suma_real": round(suma_real, 4),
    }


def _pronosticar_serie_base(
    serie: list[tuple[date, float]],
    metodo: str,
    horizonte: int,
    ventana: int,
    alpha: float,
    fecha_base: date,
) -> dict:
    """
    Pronostica una serie (producto + tienda) con un algoritmo concreto y mide su error con backtest.

    El backtest es walk-forward sobre los últimos `horizonte` días de historia:
    para cada día se pronostica usando únicamente la información previa, y se
    compara además contra una predicción ingenua (Naive estacional semanal).
    """
    factores = _factores_semana(serie)
    dias_backtest = min(horizonte, max(1, len(serie) // 5))

    reales, pronosticados, naive_pronosticados = [], [], []
    if len(serie) > dias_backtest:
        for i in range(len(serie) - dias_backtest, len(serie)):
            entrenamiento = serie[:i]
            fecha, real = serie[i]
            pronosticados.append(
                _pronosticar_fecha(entrenamiento, fecha, metodo, ventana, alpha, factores)
            )
            # Predicción ingenua (Naive): mismo día de la semana anterior o último día observado
            naive_val = entrenamiento[-7][1] if len(entrenamiento) >= 7 else (entrenamiento[-1][1] if entrenamiento else 0.0)
            naive_pronosticados.append(naive_val)
            reales.append(real)

    metricas = _metricas(reales, pronosticados)
    metricas_naive = _metricas(reales, naive_pronosticados)
    mejora_vs_naive = None
    if metricas["mae"] is not None and metricas_naive["mae"] and metricas_naive["mae"] > 0:
        mejora_vs_naive = round((metricas_naive["mae"] - metricas["mae"]) / metricas_naive["mae"] * 100, 2)

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
        "metricas": metricas,
        "metricas_naive": metricas_naive,
        "mejora_vs_naive_pct": mejora_vs_naive,
        "factores_semana": factores,
        "dias_backtest": dias_backtest,
        "metodo_ganador": metodo,
        "alpha_ganador": alpha,
        "ventana_ganador": ventana,
        "estrategia_etiqueta": METODOS[metodo]["etiqueta"],
        "nivel_ajustado": round(
            _nivel(
                [v / factores[f.weekday()] for f, v in serie], metodo, ventana, alpha
            ),
            2,
        ),
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
    Pronostica una serie (producto + tienda). En modo AUTO evalúa internamente
    varios candidatos ligeros por backtest y selecciona el de menor error sin
    configuración manual.
    """
    if metodo != "AUTO":
        return _pronosticar_serie_base(serie, metodo, horizonte, ventana, alpha, fecha_base)

    candidatos = (
        ("SUAVIZACION_EXPONENCIAL", 28, 0.25),
        ("SUAVIZACION_EXPONENCIAL", 28, 0.45),
        ("MEDIA_MOVIL_PONDERADA", 21, 0.30),
        ("MEDIA_MOVIL", 28, 0.30),
    )
    mejor_res: dict | None = None
    mejor_score: tuple[float, float] = (1e12, 1e12)
    for m_cand, v_cand, a_cand in candidatos:
        res_cand = _pronosticar_serie_base(serie, m_cand, horizonte, v_cand, a_cand, fecha_base)
        met = res_cand["metricas"]
        score = (
            float(met["wmape"]) if met["wmape"] is not None else 1e9,
            float(met["mae"]) if met["mae"] is not None else 1e9,
        )
        if mejor_res is None or score < mejor_score:
            mejor_res = res_cand
            mejor_score = score
    assert mejor_res is not None
    return mejor_res


# ---------------------------------------------------------------------------
# Observabilidad de deriva de datos (Data Drift) y anomalías
# ---------------------------------------------------------------------------
def _asignar_bin_psi(valor: float, cortes: list[float]) -> int:
    """Ubica un valor diario en uno de los 4 intervalos construidos sobre la línea base."""
    if valor <= cortes[0]:
        return 0
    if valor <= cortes[1]:
        return 1
    if valor <= cortes[2]:
        return 2
    return 3


def detectar_drift_serie(
    serie: list[tuple[date, float]],
    *,
    metricas_modelo: dict | None = None,
    metricas_naive: dict | None = None,
    ventana_reciente: int = 14,
) -> dict:
    """
    Detecta cambios en la distribución de ventas recientes (data drift),
    días atípicos y pérdida de desempeño del modelo frente a la línea base.
    """
    wmape = (metricas_modelo or {}).get("wmape")
    mae = (metricas_modelo or {}).get("mae")
    sesgo = (metricas_modelo or {}).get("sesgo")
    naive_mae = (metricas_naive or {}).get("mae")
    mejora_vs_naive_pct = None
    if mae is not None and naive_mae is not None and naive_mae > 0:
        mejora_vs_naive_pct = round((naive_mae - mae) / naive_mae * 100.0, 1)

    if len(serie) < ventana_reciente + 14:
        return {
            "estado": "SIN_DATOS",
            "confiabilidad": "Referencia",
            "requiere_reemplazo": False,
            "psi": 0.0,
            "z_nivel": 0.0,
            "cambio_nivel_pct": 0.0,
            "ratio_volatilidad": 1.0,
            "delta_ceros_pp": 0.0,
            "dias_atipicos": 0,
            "media_base": 0.0,
            "media_reciente": 0.0,
            "wmape": wmape,
            "mae": mae,
            "sesgo": sesgo,
            "mejora_vs_naive_pct": mejora_vs_naive_pct,
            "motivos": ["Historia insuficiente para evaluar deriva de datos."],
            "recomendacion": "Mantener seguimiento conforme se acumulen más días de venta.",
        }

    base = [float(v) for _, v in serie[:-ventana_reciente]]
    reciente = [float(v) for _, v in serie[-ventana_reciente:]]

    media_base = sum(base) / len(base)
    media_rec = sum(reciente) / len(reciente)
    std_base = math.sqrt(sum((x - media_base) ** 2 for x in base) / len(base))
    std_rec = math.sqrt(sum((x - media_rec) ** 2 for x in reciente) / len(reciente))
    denom_std = max(std_base, 0.5)

    z_nivel = round((media_rec - media_base) / denom_std, 2)
    if media_base > 0.01:
        cambio_nivel_pct = round((media_rec - media_base) / media_base * 100.0, 1)
    else:
        cambio_nivel_pct = 100.0 if media_rec > 0.01 else 0.0

    ratio_volatilidad = round(std_rec / denom_std, 2)
    tasa_ceros_base = sum(1 for x in base if abs(x) < 1e-9) / len(base)
    tasa_ceros_rec = sum(1 for x in reciente if abs(x) < 1e-9) / len(reciente)
    delta_ceros_pp = round((tasa_ceros_rec - tasa_ceros_base) * 100.0, 1)

    umbral_atipico = max(2.8 * std_base, media_base * 0.85, 3.0)
    dias_atipicos = sum(1 for x in reciente if abs(x - media_base) > umbral_atipico)

    # Population Stability Index (PSI) con cuartiles de la historia base
    base_ord = sorted(base)
    n_b = len(base_ord)
    cortes = [
        base_ord[int(0.25 * (n_b - 1))],
        base_ord[int(0.50 * (n_b - 1))],
        base_ord[int(0.75 * (n_b - 1))],
    ]
    if len(set(cortes)) < 3:
        if media_base > 0:
            cortes = [media_base * 0.5, media_base, media_base * 1.5]
        else:
            cortes = [0.5, 1.5, 3.0]

    conteos_base = [0, 0, 0, 0]
    for x in base:
        conteos_base[_asignar_bin_psi(x, cortes)] += 1
    conteos_rec = [0, 0, 0, 0]
    for x in reciente:
        conteos_rec[_asignar_bin_psi(x, cortes)] += 1

    p_raw = [(c + 1.0) / (len(base) + 4.0) for c in conteos_base]
    q_raw = [(c + 1.0) / (len(reciente) + 4.0) for c in conteos_rec]
    psi = round(
        sum((q - p) * math.log(q / p) for p, q in zip(p_raw, q_raw)),
        4,
    )

    sesgo_relativo = (
        abs(sesgo) / max(mae, 0.1)
        if (sesgo is not None and mae is not None)
        else 0.0
    )

    criticos: list[str] = []
    vigilancia: list[str] = []

    if psi >= 0.25:
        criticos.append("Cambio fuerte en el patrón reciente de demanda (deriva alta).")
    elif psi >= 0.15:
        vigilancia.append("Desviación moderada en el comportamiento reciente de ventas.")

    if abs(z_nivel) >= 2.8:
        direccion = "subió" if z_nivel > 0 else "cayó"
        criticos.append(f"El volumen reciente {direccion} {abs(cambio_nivel_pct):g}% frente al historial base.")
    elif abs(z_nivel) >= 1.8:
        vigilancia.append(f"Variación notable en demanda reciente ({cambio_nivel_pct:+g}% vs. base).")

    if delta_ceros_pp >= 35.0:
        criticos.append(f"Aumento severo de días sin venta (+{delta_ceros_pp:g} pp), posible quiebre o caída de rotación.")
    elif delta_ceros_pp >= 20.0:
        vigilancia.append(f"Incremento de días sin venta (+{delta_ceros_pp:g} pp) en las últimas dos semanas.")

    if wmape is not None and wmape > 45.0:
        criticos.append(f"Error de proyección elevado ({wmape:.1f}% sobre el volumen real).")
    elif wmape is not None and wmape > 30.0:
        vigilancia.append(f"Error de proyección en zona de seguimiento ({wmape:.1f}%).")

    if mejora_vs_naive_pct is not None and mejora_vs_naive_pct < -10.0:
        criticos.append("El modelo actual rinde por debajo de la referencia semanal básica; requiere reemplazo.")

    if ratio_volatilidad >= 2.0:
        vigilancia.append(f"Mayor volatilidad en ventas recientes ({ratio_volatilidad:g}× la dispersión habitual).")
    if dias_atipicos >= 2:
        vigilancia.append(f"Se detectaron {dias_atipicos} día(s) con demanda atípica en las últimas dos semanas.")
    if sesgo_relativo > 0.65 and (mae or 0.0) >= 1.0:
        sentido = "sobreestima" if (sesgo or 0.0) > 0 else "subestima"
        vigilancia.append(f"Sesgo sostenido detectado: el modelo {sentido} la demanda de forma consistente.")

    if criticos:
        estado = "NO_CONFIABLE"
        confiabilidad = "Baja"
        requiere_reemplazo = True
        recomendacion = "Recalibrar el modelo de la tienda y revisar quiebres, promociones o cambios de demanda."
    elif vigilancia:
        estado = "VIGILANCIA"
        confiabilidad = "Media"
        requiere_reemplazo = False
        recomendacion = "Monitorear los próximos días y recalibrar la tienda si la variación persiste."
    else:
        estado = "CONFIABLE"
        confiabilidad = "Alta"
        requiere_reemplazo = False
        recomendacion = "Modelo vigente y confiable para decisiones de triaje y compra."

    motivos = criticos + vigilancia
    if not motivos:
        motivos = ["Comportamiento estable frente al historial de ventas."]

    return {
        "estado": estado,
        "confiabilidad": confiabilidad,
        "requiere_reemplazo": requiere_reemplazo,
        "psi": psi,
        "z_nivel": z_nivel,
        "cambio_nivel_pct": cambio_nivel_pct,
        "ratio_volatilidad": ratio_volatilidad,
        "delta_ceros_pp": delta_ceros_pp,
        "dias_atipicos": dias_atipicos,
        "media_base": round(media_base, 2),
        "media_reciente": round(media_rec, 2),
        "wmape": wmape,
        "mae": mae,
        "sesgo": sesgo,
        "mejora_vs_naive_pct": mejora_vs_naive_pct,
        "motivos": motivos,
        "recomendacion": recomendacion,
    }


# ---------------------------------------------------------------------------
# Ejecución y persistencia (un modelo independiente por cada tienda)
# ---------------------------------------------------------------------------
def _acumular_metricas_globales(resultados: list[dict]) -> dict:
    """Agrega MAE, RMSE, WMAPE, Sesgo y referencia Naive sobre una lista de series."""
    suma_abs, suma_cuad, suma_real, suma_sesgo, n_total = 0.0, 0.0, 0.0, 0.0, 0
    suma_naive_abs, suma_naive_real, n_naive = 0.0, 0.0, 0
    for res in resultados:
        m = res.get("metricas") or {}
        if m.get("n"):
            suma_abs += (m["mae"] or 0.0) * m["n"]
            suma_cuad += ((m["rmse"] or 0.0) ** 2) * m["n"]
            suma_sesgo += (m.get("sesgo") or 0.0) * m["n"]
            suma_real += m.get("suma_real") or 0.0
            n_total += m["n"]
        mn = res.get("metricas_naive") or {}
        if mn.get("n") and mn.get("mae") is not None:
            suma_naive_abs += mn["mae"] * mn["n"]
            suma_naive_real += mn.get("suma_real") or 0.0
            n_naive += mn["n"]

    return {
        "mae": round(suma_abs / n_total, 4) if n_total else None,
        "rmse": round(math.sqrt(suma_cuad / n_total), 4) if n_total else None,
        "wmape": round(suma_abs / suma_real * 100, 4) if suma_real > 0 else None,
        "sesgo": round(suma_sesgo / n_total, 4) if n_total else None,
        "naive_mae": round(suma_naive_abs / n_naive, 4) if n_naive else None,
        "naive_wmape": round(suma_naive_abs / suma_naive_real * 100, 4) if suma_naive_real > 0 else None,
    }


def _ejecutar_pronostico_tienda(
    *,
    usuario: dict,
    id_locacion: int,
    metodo: str = "AUTO",
    horizonte: int = 7,
    ventana: int = 28,
    alpha: float = 0.30,
    dias_historia: int = 120,
    min_dias_historia: int = 14,
    id_sku: int | None = None,
) -> dict:
    """Entrena/calibra y persiste un modelo de pronóstico independiente para una tienda."""
    loc_row = one(
        "SELECT id_locacion, nombre FROM operacion.locacion WHERE id_locacion = :loc",
        loc=id_locacion,
    )
    if loc_row is None:
        raise ValueError(f"La tienda {id_locacion} no existe.")
    loc_nombre = loc_row["nombre"]

    fecha_fin = escalar("SELECT MAX(fecha_transaccion)::date FROM operacion.venta_detalle") or date.today()
    fecha_inicio = fecha_fin - timedelta(days=dias_historia)

    condiciones = ["vd.fecha_transaccion >= :inicio", "vd.id_locacion = :id_locacion"]
    params: dict = {"inicio": fecha_inicio, "id_locacion": id_locacion}
    if id_sku:
        condiciones.append("vd.id_sku = :id_sku")
        params["id_sku"] = id_sku

    filas = query(
        f"""
        SELECT vd.id_sku, vd.id_locacion,
               vd.fecha_transaccion::date AS fecha,
               SUM(vd.cantidad) AS cantidad
        FROM operacion.venta_detalle vd
        WHERE {' AND '.join(condiciones)}
        GROUP BY vd.id_sku, vd.id_locacion, vd.fecha_transaccion::date
        ORDER BY vd.id_sku, vd.fecha_transaccion::date
        """,
        **params,
    )

    grupos: dict[int, list[dict]] = {}
    totales_diarios: dict[date, float] = {}
    for fila in filas:
        grupos.setdefault(fila["id_sku"], []).append(fila)
        totales_diarios[fila["fecha"]] = totales_diarios.get(fila["fecha"], 0.0) + a_float(fila["cantidad"])

    series_validas: list[tuple[int, list[tuple[date, float]]]] = []
    for sku, filas_serie in grupos.items():
        serie = _serie_completa(filas_serie, fecha_inicio, fecha_fin)
        if sum(1 for _, v in serie if v > 0) >= min_dias_historia:
            series_validas.append((sku, serie))

    inicio_reloj = time.time()
    if not series_validas:
        return {
            "id_run": None,
            "id_locacion": id_locacion,
            "locacion": loc_nombre,
            "metodo": metodo,
            "metodo_etiqueta": METODOS[metodo]["etiqueta"],
            "horizonte": horizonte,
            "series": 0,
            "mae": None,
            "rmse": None,
            "wmape": None,
            "sesgo": None,
            "naive_mae": None,
            "naive_wmape": None,
            "estrategia_dominante": None,
            "distribucion_estrategias": {},
            "salud_modelo": None,
            "resultados": [],
            "duracion_ms": int((time.time() - inicio_reloj) * 1000),
        }

    resultados: list[dict] = []
    distribucion_estrategias: dict[str, int] = {}
    for sku, serie in series_validas:
        salida = pronosticar_serie(serie, metodo, horizonte, ventana, alpha, fecha_fin)
        ganador = salida.get("metodo_ganador", metodo)
        distribucion_estrategias[ganador] = distribucion_estrategias.get(ganador, 0) + 1
        resultados.append(
            {
                "id_sku": sku,
                "id_locacion": id_locacion,
                "metodo_ganador": ganador,
                "metricas": salida["metricas"],
                "metricas_naive": salida["metricas_naive"],
                "mejora_vs_naive_pct": salida["mejora_vs_naive_pct"],
                "pronostico": salida["pronostico"],
            }
        )

    globales = _acumular_metricas_globales(resultados)
    estrategia_dominante = (
        max(distribucion_estrategias, key=lambda k: distribucion_estrategias[k])
        if distribucion_estrategias
        else metodo
    )
    serie_tienda = _serie_completa(
        [{"fecha": f, "cantidad": c} for f, c in totales_diarios.items()],
        fecha_inicio,
        fecha_fin,
    )
    salud_modelo = detectar_drift_serie(
        serie_tienda,
        metricas_modelo={
            "mae": globales["mae"],
            "wmape": globales["wmape"],
            "sesgo": globales["sesgo"],
        },
        metricas_naive={"mae": globales["naive_mae"]},
    )

    parametros_run = {
        "id_locacion": id_locacion,
        "locacion": loc_nombre,
        "estrategia_dominante": estrategia_dominante,
        "distribucion_estrategias": distribucion_estrategias,
        "salud_modelo": salud_modelo,
        "ventana": ventana,
        "alpha": alpha,
        "dias_historia": dias_historia,
    }

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        id_run = conn.execute(
            text(
                """
                INSERT INTO analitica.forecast_run
                    (id_locacion, metodo, parametros, periodo_inicio, periodo_fin,
                     horizonte_dias, id_usuario, estado, n_series)
                VALUES (:loc, :metodo, CAST(:params AS jsonb), :inicio, :fin, :horizonte,
                        CAST(:uid AS uuid), 'PARCIAL', 0)
                RETURNING id_run::text
                """
            ),
            {
                "loc": id_locacion,
                "metodo": metodo,
                "params": _json(parametros_run),
                "inicio": fecha_inicio,
                "fin": fecha_fin,
                "horizonte": horizonte,
                "uid": usuario["id_usuario"],
            },
        ).scalar()

        for res in resultados:
            for punto in res["pronostico"]:
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
                        "sku": res["id_sku"],
                        "loc": id_locacion,
                        "fecha": punto["fecha"],
                        "h": punto["horizonte_dia"],
                        "valor": punto["valor"],
                    },
                )

        duracion = int((time.time() - inicio_reloj) * 1000)
        conn.execute(
            text(
                """
                UPDATE analitica.forecast_run
                   SET estado = 'COMPLETADO', n_series = :n, mae = :mae,
                       rmse = :rmse, wmape = :wmape, sesgo = :sesgo,
                       naive_mae = :n_mae, naive_wmape = :n_wmape,
                       duracion_ms = :ms, parametros = CAST(:params AS jsonb)
                 WHERE id_run = CAST(:id AS uuid)
                """
            ),
            {
                "n": len(resultados),
                "mae": globales["mae"],
                "rmse": globales["rmse"],
                "wmape": globales["wmape"],
                "sesgo": globales["sesgo"],
                "n_mae": globales["naive_mae"],
                "n_wmape": globales["naive_wmape"],
                "ms": duracion,
                "params": _json(parametros_run),
                "id": id_run,
            },
        )

    auditoria.registrar(
        "RUN_FORECAST",
        tabla="forecast_run",
        id_registro=id_run,
        descripcion=(
            f"Modelo de tienda {loc_nombre} ({METODOS[metodo]['etiqueta']}) · "
            f"horizonte {horizonte} días · {len(resultados)} productos · MAE {globales['mae']}"
        ),
        estado_nuevo={
            "id_locacion": id_locacion,
            "locacion": loc_nombre,
            "metodo": metodo,
            "estrategia_dominante": estrategia_dominante,
            "horizonte": horizonte,
            "series": len(resultados),
            "mae": globales["mae"],
            "rmse": globales["rmse"],
            "wmape": globales["wmape"],
        },
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    try:
        for res in resultados:
            puntos_mongo = [
                {
                    "fecha": datetime.combine(p["fecha"], datetime.min.time(), tzinfo=timezone.utc),
                    "demanda_pronosticada": float(p["valor"]),
                    "intervalo_inferior": round(float(p["valor"]) * 0.85, 2),
                    "intervalo_superior": round(float(p["valor"]) * 1.15, 2),
                    "percentil": 50,
                }
                for p in res.get("pronostico", [])
            ]
            if puntos_mongo:
                guardar_pronostico(
                    id_sku=res["id_sku"],
                    id_locacion=res["id_locacion"],
                    modelo=res.get("metodo_ganador", metodo),
                    puntos=puntos_mongo,
                    fecha_inicio=puntos_mongo[0]["fecha"],
                    fecha_fin=puntos_mongo[-1]["fecha"],
                    dias_horizonte=max(7, horizonte),
                    version_modelo="1.0",
                    linaje={"id_run": id_run, "id_locacion": id_locacion, "generado_por": usuario.get("email")},
                    metricas=res.get("metricas"),
                )
    except Exception:
        pass

    publicar_evento(
        "PRONOSTICO_CALCULADO",
        {
            "id_run": id_run,
            "id_locacion": id_locacion,
            "locacion": loc_nombre,
            "metodo": metodo,
            "estrategia_dominante": estrategia_dominante,
            "horizonte": horizonte,
            "series_count": len(resultados),
            "mae": globales["mae"],
            "rmse": globales["rmse"],
            "wmape": globales["wmape"],
        },
        contexto={
            "location_id": id_locacion,
            "user_id": usuario.get("id_usuario"),
            "user_role": usuario.get("rol_clave"),
            "correlation_id": id_run,
        },
    )
    try:
        cache_service.invalidar_patron("web:forecast:*")
    except Exception:
        pass

    return {
        "id_run": id_run,
        "id_locacion": id_locacion,
        "locacion": loc_nombre,
        "metodo": metodo,
        "metodo_etiqueta": METODOS[metodo]["etiqueta"],
        "estrategia_dominante": estrategia_dominante,
        "distribucion_estrategias": distribucion_estrategias,
        "salud_modelo": salud_modelo,
        "horizonte": horizonte,
        "series": len(resultados),
        "mae": globales["mae"],
        "rmse": globales["rmse"],
        "wmape": globales["wmape"],
        "sesgo": globales["sesgo"],
        "naive_mae": globales["naive_mae"],
        "naive_wmape": globales["naive_wmape"],
        "resultados": resultados,
        "duracion_ms": duracion,
    }


def ejecutar_pronostico(
    *,
    usuario: dict,
    metodo: str = "AUTO",
    horizonte: int = 7,
    ventana: int = 28,
    alpha: float = 0.30,
    dias_historia: int = 120,
    min_dias_historia: int = 14,
    id_locacion: int | None = None,
    id_sku: int | None = None,
) -> dict:
    """
    Crea y persiste SIEMPRE un modelo independiente por cada tienda activa.
    Si se especifica `id_locacion`, recalibra únicamente esa tienda.
    """
    metodo = (metodo or "AUTO").upper()
    if metodo not in METODOS:
        raise ValueError(f"Método no soportado: {metodo}")
    if not 1 <= horizonte <= 90:
        raise ValueError("El horizonte debe estar entre 1 y 90 días.")

    if id_locacion:
        res = _ejecutar_pronostico_tienda(
            usuario=usuario,
            id_locacion=id_locacion,
            metodo=metodo,
            horizonte=horizonte,
            ventana=ventana,
            alpha=alpha,
            dias_historia=dias_historia,
            min_dias_historia=min_dias_historia,
            id_sku=id_sku,
        )
        res["tiendas_procesadas"] = 1 if res["series"] > 0 else 0
        res["modelos_por_tienda"] = [
            {
                "id_locacion": res["id_locacion"],
                "locacion": res["locacion"],
                "id_run": res["id_run"],
                "series": res["series"],
                "mae": res["mae"],
                "wmape": res["wmape"],
                "estrategia_dominante": res["estrategia_dominante"],
            }
        ] if res["id_run"] else []
        return res

    tiendas = query(
        """
        SELECT DISTINCT v.id_locacion
        FROM analitica.v_demanda_diaria v
        JOIN operacion.locacion l ON l.id_locacion = v.id_locacion
        WHERE l.activo = true
        ORDER BY v.id_locacion
        """
    )

    inicio_reloj = time.time()
    modelos_por_tienda: list[dict] = []
    resultados_totales: list[dict] = []
    ultimo_id_run = None

    for t in tiendas:
        res_t = _ejecutar_pronostico_tienda(
            usuario=usuario,
            id_locacion=t["id_locacion"],
            metodo=metodo,
            horizonte=horizonte,
            ventana=ventana,
            alpha=alpha,
            dias_historia=dias_historia,
            min_dias_historia=min_dias_historia,
            id_sku=id_sku,
        )
        if res_t["id_run"]:
            ultimo_id_run = res_t["id_run"]
            modelos_por_tienda.append(
                {
                    "id_locacion": res_t["id_locacion"],
                    "locacion": res_t["locacion"],
                    "id_run": res_t["id_run"],
                    "series": res_t["series"],
                    "mae": res_t["mae"],
                    "wmape": res_t["wmape"],
                    "estrategia_dominante": res_t["estrategia_dominante"],
                }
            )
            resultados_totales.extend(res_t["resultados"])

    globales = _acumular_metricas_globales(resultados_totales)
    return {
        "id_run": ultimo_id_run,
        "metodo": metodo,
        "metodo_etiqueta": METODOS[metodo]["etiqueta"],
        "horizonte": horizonte,
        "tiendas_procesadas": len(modelos_por_tienda),
        "modelos_por_tienda": modelos_por_tienda,
        "series": len(resultados_totales),
        "mae": globales["mae"],
        "rmse": globales["rmse"],
        "wmape": globales["wmape"],
        "sesgo": globales["sesgo"],
        "naive_mae": globales["naive_mae"],
        "naive_wmape": globales["naive_wmape"],
        "resultados": resultados_totales,
        "duracion_ms": int((time.time() - inicio_reloj) * 1000),
    }


def _json(valor) -> str:
    import json

    return json.dumps(valor, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Backtesting comparativo (modelos vs. Naive por SKU y tienda)
# ---------------------------------------------------------------------------
def evaluar_backtest_comparativo(
    *,
    id_sku: int | None = None,
    id_locacion: int | None = None,
    horizonte: int = 7,
    ventana: int = 28,
    alpha: float = 0.30,
    dias_historia: int = 120,
    min_dias_historia: int = 14,
) -> dict:
    """
    Evalúa en validación temporal cronológica (walk-forward) los tres métodos
    frente a la predicción ingenua (Naive) por producto y tienda, reportando
    MAE, RMSE, WMAPE, Sesgo y demanda intermitente.
    """
    fecha_fin = escalar("SELECT max(fecha) FROM analitica.v_demanda_diaria") or date.today()
    fecha_inicio = fecha_fin - timedelta(days=dias_historia)
    condiciones = ["v.fecha >= :inicio"]
    params: dict = {"inicio": fecha_inicio}
    if id_locacion:
        condiciones.append("v.id_locacion = :id_locacion")
        params["id_locacion"] = id_locacion
    if id_sku:
        condiciones.append("v.id_sku = :id_sku")
        params["id_sku"] = id_sku

    filas = query(
        f"""
        SELECT v.id_sku, v.id_locacion, v.fecha, v.cantidad,
               p.nombre AS producto, loc.nombre AS locacion
        FROM analitica.v_demanda_diaria v
        JOIN operacion.producto p ON p.id_sku = v.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = v.id_locacion
        WHERE {' AND '.join(condiciones)}
        ORDER BY v.id_sku, v.id_locacion, v.fecha
        """,
        **params,
    )

    grupos: dict[tuple[int, int], list[dict]] = {}
    nombres: dict[tuple[int, int], tuple[str, str]] = {}
    for fila in filas:
        key = (fila["id_sku"], fila["id_locacion"])
        grupos.setdefault(key, []).append(fila)
        nombres[key] = (fila["producto"], fila["locacion"])

    resumen_modelos: dict[str, dict] = {
        m: {"abs": 0.0, "real": 0.0, "sesgo": 0.0, "cuad": 0.0, "n": 0}
        for m in (*METODOS.keys(), "NAIVE")
    }
    detalle_series: list[dict] = []

    for (sku, loc), filas_serie in grupos.items():
        serie = _serie_completa(filas_serie, fecha_inicio, fecha_fin)
        if sum(1 for _, v in serie if v > 0) < min_dias_historia:
            continue

        comparativa_serie: dict[str, dict] = {}
        naive_capturado = False
        for metodo in METODOS:
            sal = pronosticar_serie(serie, metodo, horizonte, ventana, alpha, fecha_fin)
            m = sal["metricas"]
            comparativa_serie[metodo] = {
                "mae": m["mae"],
                "wmape": m["wmape"],
                "sesgo": m["sesgo"],
                "demanda_intermitente": m["demanda_intermitente"],
            }
            if m["n"]:
                resumen_modelos[metodo]["abs"] += m["mae"] * m["n"]
                resumen_modelos[metodo]["cuad"] += (m["rmse"] ** 2) * m["n"]
                resumen_modelos[metodo]["sesgo"] += (m["sesgo"] or 0.0) * m["n"]
                resumen_modelos[metodo]["real"] += m["suma_real"]
                resumen_modelos[metodo]["n"] += m["n"]
            if not naive_capturado:
                mn = sal["metricas_naive"]
                comparativa_serie["NAIVE"] = {
                    "mae": mn["mae"],
                    "wmape": mn["wmape"],
                    "sesgo": mn["sesgo"],
                }
                if mn["n"]:
                    resumen_modelos["NAIVE"]["abs"] += mn["mae"] * mn["n"]
                    resumen_modelos["NAIVE"]["cuad"] += (mn["rmse"] ** 2) * mn["n"]
                    resumen_modelos["NAIVE"]["sesgo"] += (mn["sesgo"] or 0.0) * mn["n"]
                    resumen_modelos["NAIVE"]["real"] += mn["suma_real"]
                    resumen_modelos["NAIVE"]["n"] += mn["n"]
                naive_capturado = True

        mejor = min(
            METODOS.keys(),
            key=lambda m: 1e9 if comparativa_serie[m]["mae"] is None else comparativa_serie[m]["mae"],
        )
        prod_nom, loc_nom = nombres[(sku, loc)]
        detalle_series.append(
            {
                "id_sku": sku,
                "producto": prod_nom,
                "id_locacion": loc,
                "locacion": loc_nom,
                "mejor_modelo": mejor,
                "modelos": comparativa_serie,
            }
        )

    global_modelos = {}
    for nombre, acc in resumen_modelos.items():
        n = acc["n"]
        global_modelos[nombre] = {
            "mae": round(acc["abs"] / n, 4) if n else None,
            "rmse": round(math.sqrt(acc["cuad"] / n), 4) if n else None,
            "wmape": round(acc["abs"] / acc["real"] * 100, 4) if acc["real"] > 0 else None,
            "sesgo": round(acc["sesgo"] / n, 4) if n else None,
            "puntos": n,
        }

    return {
        "horizonte": horizonte,
        "total_series": len(detalle_series),
        "resumen_global": global_modelos,
        "series": detalle_series[:100],
    }


# ---------------------------------------------------------------------------
# Consultas por tienda y vigilancia de deriva
# ---------------------------------------------------------------------------
def ultima_corrida(id_locacion: int | None = None) -> dict | None:
    """Última corrida completada (cacheada 90 s; se invalida al ejecutar un pronóstico)."""
    return con_cache_web(
        f"web:forecast:ultima:{id_locacion or 'all'}", 90, lambda: _ultima_corrida_db(id_locacion)
    )


def _ultima_corrida_db(id_locacion: int | None = None) -> dict | None:
    filtro_loc = "AND r.id_locacion = :loc" if id_locacion else ""
    params = {"loc": id_locacion} if id_locacion else {}
    return one(
        f"""
        SELECT r.id_run::text, r.id_locacion, loc.nombre AS locacion,
               r.metodo, r.parametros, r.periodo_inicio, r.periodo_fin,
               r.horizonte_dias, r.fecha_ejecucion, r.n_series, r.estado,
               r.mae, r.rmse, r.wmape, r.sesgo, r.naive_mae, r.naive_wmape, r.duracion_ms,
               u.nombre_completo AS ejecutado_por
        FROM analitica.forecast_run r
        LEFT JOIN operacion.locacion loc ON loc.id_locacion = r.id_locacion
        LEFT JOIN operacion.usuario u ON u.id_usuario = r.id_usuario
        WHERE r.estado = 'COMPLETADO'
          {filtro_loc}
        ORDER BY r.fecha_ejecucion DESC
        LIMIT 1
        """,
        **params,
    )


def corridas(limite: int = 20, id_locacion: int | None = None) -> list[dict]:
    """Historial de corridas (cacheado 90 s; se invalida al ejecutar un pronóstico)."""
    return con_cache_web(
        f"web:forecast:corridas:{int(limite)}:{id_locacion or 'all'}",
        90,
        lambda: _corridas_db(limite, id_locacion),
    )


def _corridas_db(limite: int = 20, id_locacion: int | None = None) -> list[dict]:
    filtro_loc = "WHERE r.id_locacion = :loc" if id_locacion else ""
    params: dict = {"limite": limite, **({"loc": id_locacion} if id_locacion else {})}
    return query(
        f"""
        SELECT r.id_run::text, r.id_locacion, loc.nombre AS locacion,
               r.metodo, r.parametros, r.horizonte_dias, r.fecha_ejecucion,
               r.n_series, r.mae, r.rmse, r.wmape, r.sesgo, r.naive_mae, r.naive_wmape,
               r.duracion_ms, r.estado, r.periodo_inicio, r.periodo_fin,
               u.nombre_completo AS ejecutado_por
        FROM analitica.forecast_run r
        LEFT JOIN operacion.locacion loc ON loc.id_locacion = r.id_locacion
        LEFT JOIN operacion.usuario u ON u.id_usuario = r.id_usuario
        {filtro_loc}
        ORDER BY r.fecha_ejecucion DESC
        LIMIT :limite
        """,
        **params,
    )


def pronostico_por_serie(id_run: str, limite: int = 300) -> list[dict]:
    """
    Pronóstico agregado por Producto + Tienda: próximo día y próximos N días.
    Es el formato que exige la rúbrica. Una corrida es inmutable una vez
    completada, así que se cachea 5 min.
    """
    return con_cache_web(
        f"web:forecast:serie:{id_run}:{int(limite)}", 300, lambda: _pronostico_por_serie_db(id_run, limite)
    )


def _pronostico_por_serie_db(id_run: str, limite: int = 300) -> list[dict]:
    return query(
        """
        SELECT p.nombre AS producto, p.id_sku, p.unidad_medida,
               loc.nombre AS locacion, loc.id_locacion,
               r.id_run::text, r.metodo,
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
        GROUP BY p.nombre, p.id_sku, p.unidad_medida, loc.nombre, loc.id_locacion, r.id_run, r.metodo
        ORDER BY loc.nombre, p.nombre
        LIMIT :limite
        """,
        id_run=id_run,
        limite=limite,
    )


def pronostico_vigente_por_tienda(
    id_locacion: int | None = None, limite: int = 300
) -> list[dict]:
    """Proyecciones vigentes del último modelo de cada tienda (cacheadas 90 s)."""
    return con_cache_web(
        f"web:forecast:vigente:{id_locacion or 'all'}:{int(limite)}",
        90,
        lambda: _pronostico_vigente_por_tienda_db(id_locacion, limite),
        con_lock=True,
    )


def _pronostico_vigente_por_tienda_db(
    id_locacion: int | None = None, limite: int = 300
) -> list[dict]:
    filtro_loc = "WHERE ut.id_locacion = :loc" if id_locacion else ""
    params: dict = {"limite": limite, **({"loc": id_locacion} if id_locacion else {})}
    filas = query(
        f"""
        WITH ultimas_tiendas AS (
            SELECT DISTINCT ON (id_locacion) id_run, id_locacion, metodo, horizonte_dias
            FROM analitica.forecast_run
            WHERE estado = 'COMPLETADO' AND id_locacion IS NOT NULL
            ORDER BY id_locacion, fecha_ejecucion DESC
        )
        SELECT p.nombre AS producto, p.id_sku, p.unidad_medida,
               loc.nombre AS locacion, loc.id_locacion,
               ut.id_run::text, ut.metodo,
               COALESCE(SUM(CASE WHEN fr.horizonte_dia = 1
                                 THEN fr.demanda_pronosticada END), 0) AS proximo_dia,
               COALESCE(SUM(fr.demanda_pronosticada), 0)                 AS total_horizonte,
               MAX(ut.horizonte_dias)                                    AS horizonte_dias,
               MIN(fr.fecha_objetivo)                                    AS desde,
               MAX(fr.fecha_objetivo)                                    AS hasta
        FROM ultimas_tiendas ut
        JOIN analitica.forecast_result fr ON fr.id_run = ut.id_run
        JOIN operacion.producto p         ON p.id_sku = fr.id_sku
        JOIN operacion.locacion loc       ON loc.id_locacion = fr.id_locacion
        {filtro_loc}
        GROUP BY p.nombre, p.id_sku, p.unidad_medida, loc.nombre, loc.id_locacion, ut.id_run, ut.metodo
        ORDER BY loc.nombre, p.nombre
        LIMIT :limite
        """,
        **params,
    )
    if filas:
        return filas
    corrida = ultima_corrida()
    if not corrida:
        return []
    series = pronostico_por_serie(corrida["id_run"], limite=limite)
    if id_locacion:
        return [s for s in series if s["id_locacion"] == id_locacion]
    return series


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
    """Pronóstico vigente (priorizando el modelo propio de la tienda) para un SKU y tienda."""
    return one(
        """
        SELECT fr.id_run::text, SUM(fr.demanda_pronosticada) AS total,
               SUM(CASE WHEN fr.horizonte_dia = 1 THEN fr.demanda_pronosticada END) AS proximo_dia,
               COUNT(*) AS dias, MIN(fr.fecha_objetivo) AS desde, MAX(fr.fecha_objetivo) AS hasta
        FROM analitica.forecast_result fr
        WHERE fr.id_sku = :sku AND fr.id_locacion = :loc
          AND fr.id_run = (
              SELECT r.id_run
              FROM analitica.forecast_run r
              WHERE r.estado = 'COMPLETADO'
                AND (r.id_locacion = :loc OR r.id_locacion IS NULL)
                AND EXISTS (
                    SELECT 1 FROM analitica.forecast_result fr2
                    WHERE fr2.id_run = r.id_run AND fr2.id_sku = :sku AND fr2.id_locacion = :loc
                )
              ORDER BY (CASE WHEN r.id_locacion = :loc THEN 0 ELSE 1 END),
                       r.fecha_ejecucion DESC
              LIMIT 1
          )
        GROUP BY fr.id_run
        """,
        sku=id_sku,
        loc=id_locacion,
    )


def demanda_diaria_promedio(id_sku: int, id_locacion: int, dias: int = 28) -> float:
    """Demanda promedio diaria reciente (usada como respaldo cuando no hay modelo)."""
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


def demanda_diaria_vigente(id_sku: int, id_locacion: int) -> float:
    """Demanda diaria según el modelo vigente de la tienda; cae a promedio 28d si no existe."""
    vigente = pronostico_actual_por_sku_loc(id_sku, id_locacion)
    if vigente and vigente.get("dias"):
        total = a_float(vigente.get("total"))
        dias = a_int(vigente.get("dias"), 0)
        if dias > 0 and total > 0:
            return round(total / dias, 4)
    return demanda_diaria_promedio(id_sku, id_locacion, 28)


def demandas_diarias_vigentes(pares) -> dict[tuple[int, int], float]:
    """
    Versión en lote de `demanda_diaria_vigente` para muchos pares (sku, tienda).

    Misma regla, en 2 consultas en vez de 2-3 por par:
      1. Modelo vigente: la corrida COMPLETADA más reciente con resultados para
         el par, priorizando la corrida propia de la tienda sobre la global.
         Demanda diaria = total pronosticado / días del horizonte.
      2. Respaldo: promedio de los últimos 28 días con venta.
    """
    pares = sorted({(int(s), int(l)) for s, l in pares})
    if not pares:
        return {}
    skus = [s for s, _ in pares]
    locs = [l for _, l in pares]
    resultado: dict[tuple[int, int], float] = {}

    for f in query(
        """
        WITH pares AS (
            SELECT * FROM unnest(CAST(:skus AS integer[]), CAST(:locs AS integer[])) AS t(id_sku, id_locacion)
        ),
        elegido AS (
            SELECT DISTINCT ON (pa.id_sku, pa.id_locacion)
                   pa.id_sku, pa.id_locacion, r.id_run
            FROM pares pa
            JOIN analitica.forecast_result fr
              ON fr.id_sku = pa.id_sku AND fr.id_locacion = pa.id_locacion
            JOIN analitica.forecast_run r
              ON r.id_run = fr.id_run
             AND r.estado = 'COMPLETADO'
             AND (r.id_locacion = pa.id_locacion OR r.id_locacion IS NULL)
            ORDER BY pa.id_sku, pa.id_locacion,
                     (CASE WHEN r.id_locacion = pa.id_locacion THEN 0 ELSE 1 END),
                     r.fecha_ejecucion DESC
        )
        SELECT e.id_sku, e.id_locacion,
               SUM(fr.demanda_pronosticada) AS total, COUNT(*) AS dias
        FROM elegido e
        JOIN analitica.forecast_result fr
          ON fr.id_run = e.id_run AND fr.id_sku = e.id_sku AND fr.id_locacion = e.id_locacion
        GROUP BY e.id_sku, e.id_locacion
        """,
        skus=skus,
        locs=locs,
    ):
        total = a_float(f["total"])
        dias = a_int(f["dias"], 0)
        if dias > 0 and total > 0:
            resultado[(f["id_sku"], f["id_locacion"])] = round(total / dias, 4)

    faltan = [p for p in pares if p not in resultado]
    if faltan:
        promedios = {
            (f["id_sku"], f["id_locacion"]): a_float(f["promedio"])
            for f in query(
                """
                WITH pares AS (
                    SELECT * FROM unnest(CAST(:skus AS integer[]), CAST(:locs AS integer[])) AS t(id_sku, id_locacion)
                )
                SELECT s.id_sku, s.id_locacion, AVG(s.cantidad) AS promedio
                FROM (
                    SELECT d.id_sku, d.id_locacion, d.fecha, SUM(d.cantidad) AS cantidad
                    FROM analitica.v_demanda_diaria d
                    JOIN pares pa ON pa.id_sku = d.id_sku AND pa.id_locacion = d.id_locacion
                    WHERE d.fecha >= CURRENT_DATE - 28
                    GROUP BY d.id_sku, d.id_locacion, d.fecha
                ) s
                GROUP BY s.id_sku, s.id_locacion
                """,
                skus=[s for s, _ in faltan],
                locs=[l for _, l in faltan],
            )
        }
        for par in faltan:
            resultado[par] = promedios.get(par, 0.0)
    return resultado


def modelos_activos_por_tienda(id_locacion: int | None = None) -> list[dict]:
    """Devuelve todas las tiendas activas junto con su último modelo propio generado."""
    filtro_loc = "AND loc.id_locacion = :loc" if id_locacion else ""
    params = {"loc": id_locacion} if id_locacion else {}
    filas = query(
        f"""
        WITH ultimos AS (
            SELECT DISTINCT ON (r.id_locacion)
                   r.id_locacion,
                   r.id_run::text AS id_run,
                   r.metodo,
                   r.parametros,
                   r.horizonte_dias,
                   r.fecha_ejecucion,
                   r.n_series,
                   r.mae,
                   r.rmse,
                   r.wmape,
                   r.sesgo,
                   r.naive_mae,
                   r.naive_wmape,
                   u.nombre_completo AS ejecutado_por,
                   EXTRACT(EPOCH FROM (now() - r.fecha_ejecucion)) / 3600.0 AS edad_horas
            FROM analitica.forecast_run r
            LEFT JOIN operacion.usuario u ON u.id_usuario = r.id_usuario
            WHERE r.estado = 'COMPLETADO'
              AND r.id_locacion IS NOT NULL
            ORDER BY r.id_locacion, r.fecha_ejecucion DESC
        )
        SELECT loc.id_locacion, loc.nombre AS locacion, loc.tipo_locacion,
               ul.id_run, ul.metodo, ul.parametros, ul.horizonte_dias,
               ul.fecha_ejecucion, ul.n_series, ul.mae, ul.rmse,
               ul.wmape, ul.sesgo, ul.naive_mae, ul.naive_wmape,
               ul.ejecutado_por, ul.edad_horas
        FROM operacion.locacion loc
        LEFT JOIN ultimos ul ON ul.id_locacion = loc.id_locacion
        WHERE loc.activo = true
          AND loc.tipo_locacion = 'Tienda'
          {filtro_loc}
        ORDER BY loc.nombre
        """,
        **params,
    )
    for f in filas:
        for campo in ("mae", "rmse", "wmape", "sesgo", "naive_mae", "naive_wmape", "edad_horas"):
            if f.get(campo) is not None:
                f[campo] = round(a_float(f[campo]), 2)
    return filas


def evaluar_salud_modelos(
    id_locacion: int | None = None,
    dias_historia: int = 120,
    ventana_reciente: int = 14,
) -> dict:
    """
    Evalúa la salud de cada modelo por tienda y detecta deriva de datos (data drift)
    y anomalías tanto a nivel tienda como por producto dentro de cada tienda.
    """
    activa = os.getenv("CACHE_WEB_ACTIVA", "true").strip().lower() not in ("0", "false", "no")
    clave_cache = f"web:forecast:salud:{id_locacion or 'all'}:{int(dias_historia)}:{int(ventana_reciente)}"
    if activa and cache_service.get_redis_client() is not None:
        cached = cache_service.get_json(clave_cache)
        if isinstance(cached, dict) and "tiendas" in cached:
            cache_service.incrementar_contador("web", "cache_hit")
            return cached
        cache_service.incrementar_contador("web", "cache_miss")

    tiendas_modelo = modelos_activos_por_tienda(id_locacion=id_locacion)
    fecha_fin = escalar("SELECT MAX(fecha_transaccion)::date FROM operacion.venta_detalle") or date.today()
    fecha_inicio = fecha_fin - timedelta(days=dias_historia)

    condiciones = ["vd.fecha_transaccion >= :inicio"]
    params: dict = {"inicio": fecha_inicio}
    if id_locacion:
        condiciones.append("vd.id_locacion = :loc")
        params["loc"] = id_locacion

    filas = query(
        f"""
        SELECT vd.id_sku, vd.id_locacion,
               vd.fecha_transaccion::date AS fecha,
               SUM(vd.cantidad) AS cantidad,
               p.nombre AS producto, p.unidad_medida, p.perfil_demanda, loc.nombre AS locacion
        FROM operacion.venta_detalle vd
        JOIN operacion.producto p ON p.id_sku = vd.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = vd.id_locacion
        WHERE {' AND '.join(condiciones)}
        GROUP BY vd.id_sku, vd.id_locacion, vd.fecha_transaccion::date,
                 p.nombre, p.unidad_medida, p.perfil_demanda, loc.nombre
        ORDER BY vd.id_locacion, vd.id_sku, vd.fecha_transaccion::date
        """,
        **params,
    )

    por_tienda_diario: dict[int, dict[date, float]] = {}
    por_tienda_sku: dict[int, dict[int, list[dict]]] = {}
    productos_info: dict[int, tuple[str, str, str | None]] = {}
    for f in filas:
        loc_id = f["id_locacion"]
        sku_id = f["id_sku"]
        productos_info[sku_id] = (f["producto"], f["unidad_medida"], f.get("perfil_demanda"))
        por_tienda_diario.setdefault(loc_id, {})
        por_tienda_diario[loc_id][f["fecha"]] = (
            por_tienda_diario[loc_id].get(f["fecha"], 0.0) + a_float(f["cantidad"])
        )
        por_tienda_sku.setdefault(loc_id, {}).setdefault(sku_id, []).append(f)

    resultados_tiendas: list[dict] = []
    anomalias_sku: list[dict] = []

    for mod in tiendas_modelo:
        loc_id = mod["id_locacion"]
        diario_map = por_tienda_diario.get(loc_id, {})
        if diario_map:
            serie_tienda = _serie_completa(
                [{"fecha": fecha, "cantidad": val} for fecha, val in diario_map.items()],
                fecha_inicio,
                fecha_fin,
            )
        else:
            serie_tienda = []

        metricas_mod = (
            {"mae": mod["mae"], "wmape": mod["wmape"], "sesgo": mod["sesgo"]}
            if mod["id_run"]
            else None
        )
        metricas_nv = {"mae": mod["naive_mae"]} if mod["naive_mae"] is not None else None
        diag = detectar_drift_serie(
            serie_tienda,
            metricas_modelo=metricas_mod,
            metricas_naive=metricas_nv,
            ventana_reciente=ventana_reciente,
        )

        # Evaluar anomalías por producto dentro de esta tienda
        skus_loc = por_tienda_sku.get(loc_id, {})
        anomalias_tienda = 0
        for sku_id, rows_sku in skus_loc.items():
            serie_sku = _serie_completa(rows_sku, fecha_inicio, fecha_fin)
            if sum(1 for _, v in serie_sku if v > 0) < 14:
                continue
            diag_sku = detectar_drift_serie(serie_sku, ventana_reciente=ventana_reciente)
            if diag_sku["estado"] in ("NO_CONFIABLE", "VIGILANCIA"):
                anomalias_tienda += 1
                prod_nom, u_med, perfil_dem = productos_info[sku_id]
                anomalias_sku.append(
                    {
                        "id_sku": sku_id,
                        "producto": prod_nom,
                        "unidad_medida": u_med,
                        "perfil_demanda": perfil_dem,
                        "id_locacion": loc_id,
                        "locacion": mod["locacion"],
                        **diag_sku,
                    }
                )

        motivos = list(diag["motivos"])
        estado = diag["estado"]
        confiabilidad = diag["confiabilidad"]
        requiere_reemplazo = diag["requiere_reemplazo"]
        recomendacion = diag["recomendacion"]

        if mod["id_run"] is None:
            estado = "NO_CONFIABLE"
            confiabilidad = "Baja"
            requiere_reemplazo = True
            motivos = ["Esta tienda aún no cuenta con un modelo propio generado."] + [
                m for m in motivos if m != "Comportamiento estable frente al historial de ventas."
            ]
            recomendacion = "Generar ahora el modelo automático de esta tienda."
        elif mod["edad_horas"] is not None and mod["edad_horas"] > 72.0:
            motivo_edad = "El modelo lleva más de 72 horas sin actualizarse con ventas recientes."
            if motivo_edad not in motivos:
                motivos = [m for m in motivos if m != "Comportamiento estable frente al historial de ventas."]
                motivos.append(motivo_edad)
            if estado == "CONFIABLE":
                estado = "VIGILANCIA"
                confiabilidad = "Media"
                recomendacion = "Actualizar el modelo de la tienda para incorporar las últimas ventas."

        parametros_run = mod.get("parametros") or {}
        estrategia = parametros_run.get("estrategia_dominante") or mod.get("metodo") or "AUTO"
        estrategia_etiqueta = METODOS.get(estrategia, {}).get("etiqueta", estrategia)

        resultados_tiendas.append(
            {
                "id_locacion": loc_id,
                "locacion": mod["locacion"],
                "id_run": mod["id_run"],
                "metodo": mod["metodo"],
                "estrategia_dominante": estrategia,
                "estrategia_etiqueta": estrategia_etiqueta,
                "horizonte_dias": mod["horizonte_dias"],
                "n_series": mod["n_series"] or 0,
                "fecha_ejecucion": mod["fecha_ejecucion"].isoformat() if mod["fecha_ejecucion"] else None,
                "edad_horas": mod["edad_horas"],
                "mae": mod["mae"],
                "rmse": mod["rmse"],
                "wmape": mod["wmape"],
                "sesgo": mod["sesgo"],
                "naive_mae": mod["naive_mae"],
                "estado": estado,
                "confiabilidad": confiabilidad,
                "requiere_reemplazo": requiere_reemplazo,
                "psi": diag["psi"],
                "z_nivel": diag["z_nivel"],
                "cambio_nivel_pct": diag["cambio_nivel_pct"],
                "ratio_volatilidad": diag["ratio_volatilidad"],
                "delta_ceros_pp": diag["delta_ceros_pp"],
                "dias_atipicos": diag["dias_atipicos"],
                "media_base": diag["media_base"],
                "media_reciente": diag["media_reciente"],
                "mejora_vs_naive_pct": diag["mejora_vs_naive_pct"],
                "productos_con_anomalia": anomalias_tienda,
                "motivos": motivos,
                "recomendacion": recomendacion,
            }
        )

    prioridad_estado = {"NO_CONFIABLE": 0, "VIGILANCIA": 1, "SIN_DATOS": 2, "CONFIABLE": 3}
    resultados_tiendas.sort(key=lambda t: (prioridad_estado.get(t["estado"], 9), t["locacion"]))
    anomalias_sku.sort(key=lambda a: (prioridad_estado.get(a["estado"], 9), -a["psi"], -abs(a["z_nivel"])))

    resumen = {
        "total_tiendas": len(resultados_tiendas),
        "confiables": sum(1 for t in resultados_tiendas if t["estado"] == "CONFIABLE"),
        "vigilancia": sum(1 for t in resultados_tiendas if t["estado"] == "VIGILANCIA"),
        "no_confiables": sum(1 for t in resultados_tiendas if t["estado"] == "NO_CONFIABLE"),
        "sin_datos": sum(1 for t in resultados_tiendas if t["estado"] == "SIN_DATOS"),
        "total_anomalias_sku": len(anomalias_sku),
    }
    salida_salud = {
        "resumen": resumen,
        "tiendas": resultados_tiendas,
        "anomalias_sku": anomalias_sku[:40],
    }
    if activa and cache_service.get_redis_client() is not None:
        try:
            cache_service.set_json(clave_cache, salida_salud, ttl_segundos=90)
        except Exception:
            pass
    return salida_salud


def asegurar_pronostico_vigente(
    *,
    usuario: dict,
    id_locacion: int | None = None,
    max_edad_horas: int = 24,
    horizonte: int | None = None,
) -> dict:
    """
    Garantiza en silencio que cada tienda activa tenga su modelo propio vigente.
    Solo recalibra las tiendas sin modelo, vencidas (> max_edad_horas) o en estado
    NO_CONFIABLE (si llevan más de 1 hora desde la última corrida).
    """
    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)

    salud = evaluar_salud_modelos(id_locacion=id_locacion)
    recalibradas: list[dict] = []
    reutilizadas: list[dict] = []

    for tienda in salud["tiendas"]:
        edad = tienda["edad_horas"]
        necesita = (
            tienda["id_run"] is None
            or (edad is not None and edad > max_edad_horas)
            or (tienda["estado"] == "NO_CONFIABLE" and (edad is None or edad > 1.0))
        )
        if necesita:
            res = _ejecutar_pronostico_tienda(
                usuario=usuario,
                id_locacion=tienda["id_locacion"],
                metodo="AUTO",
                horizonte=horizonte,
            )
            if res["id_run"]:
                recalibradas.append(
                    {
                        "id_locacion": res["id_locacion"],
                        "locacion": res["locacion"],
                        "id_run": res["id_run"],
                        "series": res["series"],
                        "wmape": res["wmape"],
                    }
                )
        else:
            reutilizadas.append(
                {
                    "id_locacion": tienda["id_locacion"],
                    "locacion": tienda["locacion"],
                    "id_run": tienda["id_run"],
                    "edad_horas": edad,
                    "estado": tienda["estado"],
                }
            )

    return {
        "horizonte": horizonte,
        "tiendas_recalibradas": recalibradas,
        "tiendas_reutilizadas": reutilizadas,
        "total_recalibradas": len(recalibradas),
        "total_reutilizadas": len(reutilizadas),
    }


def precision_global() -> dict:
    """Precisión del último pronóstico, ya contrastada contra la demanda real (con Cache-Aside)."""
    activa = os.getenv("CACHE_WEB_ACTIVA", "true").strip().lower() not in ("0", "false", "no")
    clave_cache = "web:forecast:precision_global"
    if activa and cache_service.get_redis_client() is not None:
        cached = cache_service.get_json(clave_cache)
        if cached is not None:
            cache_service.incrementar_contador("web", "cache_hit")
            return cached
        cache_service.incrementar_contador("web", "cache_miss")

    fila = one(
        """
        SELECT r.id_run::text, r.id_locacion, loc.nombre AS locacion,
               r.metodo, r.mae, r.rmse, r.wmape, r.fecha_ejecucion,
               r.horizonte_dias,
               COUNT(fr.id_resultado)                                          AS puntos,
               COUNT(fr.demanda_real)                                          AS puntos_evaluados,
               COALESCE(SUM(ABS(fr.error_absoluto)), 0)                        AS error_total,
               COALESCE(SUM(fr.demanda_real), 0)                               AS demanda_real_total
        FROM analitica.forecast_run r
        LEFT JOIN operacion.locacion loc ON loc.id_locacion = r.id_locacion
        LEFT JOIN analitica.forecast_result fr ON fr.id_run = r.id_run
        WHERE r.estado = 'COMPLETADO'
          AND r.id_run = (
              SELECT id_run FROM analitica.forecast_run
              WHERE estado = 'COMPLETADO' ORDER BY fecha_ejecucion DESC LIMIT 1
          )
        GROUP BY r.id_run, r.id_locacion, loc.nombre, r.metodo, r.mae, r.rmse, r.wmape, r.fecha_ejecucion, r.horizonte_dias
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
    if activa and cache_service.get_redis_client() is not None:
        norm = {
            k: (float(v) if isinstance(v, Decimal) else (v.isoformat() if isinstance(v, (date, datetime)) else v))
            for k, v in fila.items()
        }
        cache_service.set_json(clave_cache, norm, ttl_segundos=60)
        return norm
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
