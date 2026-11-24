"""Pruebas unitarias del flujo guiado de Pronósticos en 4 etapas y su desacoplamiento."""

from __future__ import annotations

import ast
from datetime import date, timedelta
import os
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

os.environ.setdefault("SECRET_KEY", "clave-de-pruebas-pronostico-0123456789")
os.environ.setdefault("JWT_SECRET_KEY", "jwt-de-pruebas-pronostico-0123456789")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_backend:x@127.0.0.1:1/inexistente")

from app import create_app  # noqa: E402
from app import navegacion  # noqa: E402
from app.domain import experimentos_ab as dom_ab  # noqa: E402
from app.domain import inventario as dom_inv  # noqa: E402
from app.domain import laboratorio as dom_lab  # noqa: E402
from app.domain import pronostico as motor_pron  # noqa: E402
from app.domain import reabastecimiento as motor_reab  # noqa: E402
from app.services import clientes  # noqa: E402


def test_pronostico_esta_desacoplado_de_fefo_y_newsvendor():
    fuente = (RAIZ / "app" / "domain" / "pronostico.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    modulos_importados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                modulos_importados.add(alias.name)
        elif isinstance(nodo, ast.ImportFrom):
            mod = nodo.module or ""
            modulos_importados.add(mod)
            for alias in nodo.names:
                modulos_importados.add(f"{mod}.{alias.name}")

    for prohibido in ("reabastecimiento", "inventario", "mermas", "descuentos", "triaje"):
        assert not any(prohibido in m for m in modulos_importados), (
            f"pronostico.py no debe importar {prohibido}: {modulos_importados}"
        )


def test_ets_y_desviacion_std_y_cuantil_normal():
    assert "ETS_HOLT_WINTERS" in motor_pron.METODOS
    hoy = date(2026, 11, 20)
    serie = [(hoy - timedelta(days=39 - i), 20.0 + (i % 7) * 1.5 + i * 0.2) for i in range(40)]

    sal_ets = motor_pron.pronosticar_serie(serie, "ETS_HOLT_WINTERS", horizonte=7, ventana=28, alpha=0.30, fecha_base=hoy)
    assert len(sal_ets["pronostico"]) == 7
    assert sal_ets["sigma_diaria"] > 0
    assert all("desviacion_std" in p and p["desviacion_std"] > 0 for p in sal_ets["pronostico"])
    assert len(sal_ets["backtest_puntos"]) == sal_ets["dias_backtest"]

    sal_auto = motor_pron.pronosticar_serie(serie, "AUTO", horizonte=7, ventana=28, alpha=0.30, fecha_base=hoy)
    assert sal_auto["metodo_ganador"] in motor_pron.METODOS_BASE

    q50 = motor_pron.cuantil_normal(100.0, 10.0, 0.50)
    q90 = motor_pron.cuantil_normal(100.0, 10.0, 0.90)
    assert q50 == 100.0
    assert q90 > q50


def test_laboratorio_calcula_fva_y_simulacion_newsvendor():
    puntos = [
        {"real": 20.0, "pred": 25.0},
        {"real": 30.0, "pred": 28.0},
        {"real": 18.0, "pred": 24.0},
    ]
    sim = dom_lab.simular_newsvendor_backtest(
        puntos,
        precio_venta=50.0,
        precio_costo=20.0,
        vida_util_dias=5,
        sigma_diaria=4.0,
    )
    assert sim["merma_simulada_unidades"] >= 0
    assert sim["merma_simulada_valor"] >= 0
    assert sim["venta_perdida_valor"] >= 0
    assert sim["costo_total_simulado"] == round(sim["merma_simulada_valor"] + sim["venta_perdida_valor"], 2)


def test_ab_test_asignacion_balanceada_y_comparativa():
    tiendas = [
        {"id_locacion": 1, "locacion": "Centro", "volumen_30d": 1000},
        {"id_locacion": 2, "locacion": "Norte", "volumen_30d": 900},
        {"id_locacion": 3, "locacion": "Sur", "volumen_30d": 500},
        {"id_locacion": 4, "locacion": "Oeste", "volumen_30d": 400},
    ]
    asig = dom_ab.asignar_serpiente_por_volumen(tiendas)
    ctrl = [t for t in asig if t["grupo"] == "CONTROL"]
    trat = [t for t in asig if t["grupo"] == "TRATAMIENTO"]
    assert len(ctrl) == 2 and len(trat) == 2
    # Serpiente: 1000+400=1400 vs 900+500=1400
    assert sum(t["volumen_30d"] for t in ctrl) == sum(t["volumen_30d"] for t in trat)

    comp = dom_ab.calcular_comparativa_ab(
        grupos_agg={
            "CONTROL": {
                "registros": 10, "tiendas": 2, "dias": 5,
                "real_total": 100.0, "pred_total": 110.0, "error_total": 20.0,
                "ventas_valor": 1000.0, "merma_unidades": 10.0, "merma_valor": 100.0,
            },
            "TRATAMIENTO": {
                "registros": 10, "tiendas": 2, "dias": 5,
                "real_total": 100.0, "pred_total": 102.0, "error_total": 10.0,
                "ventas_valor": 1100.0, "merma_unidades": 5.0, "merma_valor": 50.0,
            },
        },
        dia_actual=14,
        duracion_dias=21,
    )
    assert comp["dia_actual"] == 14
    assert comp["avance_pct"] == 67
    assert comp["control"]["wmape_real"] == 20.0
    assert comp["tratamiento"]["wmape_real"] == 10.0
    assert comp["deltas"]["wmape_pp"] == -10.0
    assert comp["deltas"]["tasa_merma_pp"] < 0
    assert comp["veredicto"] == "PROMOVER_RETADOR"


def test_riesgo_fefo_secuencial_no_duplica_demanda(monkeypatch):
    # Demanda diaria = 10 u/d. Lote 1 vence en 1 dia (10 u.), Lote 2 vence en 2 dias (15 u.).
    # Consumo secuencial: dia 1 consume las 10 u. del Lote 1 -> dia 2 solo quedan 10 u. de demanda para Lote 2 -> 5 en riesgo.
    monkeypatch.setattr(motor_pron, "demanda_diaria_vigente", lambda sku, loc: 10.0)
    monkeypatch.setattr(
        motor_reab,
        "query",
        lambda sql, **kw: [
            {"id_lote": "l1", "codigo_lote_prov": "L1", "cantidad_disponible": 10.0, "fecha_caducidad": date.today() + timedelta(days=1), "dias_restantes": 1, "clasificacion": "CRITICO", "vida_util_pct": 20.0, "costo_unitario": 5.0, "unidad_medida": "kg"},
            {"id_lote": "l2", "codigo_lote_prov": "L2", "cantidad_disponible": 15.0, "fecha_caducidad": date.today() + timedelta(days=2), "dias_restantes": 2, "clasificacion": "VIGILANCIA", "vida_util_pct": 40.0, "costo_unitario": 5.0, "unidad_medida": "kg"},
        ],
    )
    lotes = motor_reab.riesgo_por_lote(1, 1, dias_ventana=5)
    assert lotes[0]["unidades_en_riesgo"] == 0.0
    assert lotes[1]["demanda_antes_caducidad"] == 10.0
    assert lotes[1]["unidades_en_riesgo"] == 5.0


def test_cuatro_etapas_en_pronostico_sin_nuevas_ventanas_sidebar(monkeypatch):
    # Verificar que el sidebar mantiene una sola entrada bajo Analitica para Pronosticos
    analitica_sec = next(s for s in navegacion.SECCIONES if s["label"] == "Analítica")
    ids_analitica = [i["id"] for i in analitica_sec["items"]]
    assert ids_analitica == ["forecast", "triage", "replenishment"]

    monkeypatch.setattr(clientes, "activo", lambda: False)
    monkeypatch.setattr("app.blueprints.analitica.config_valor", lambda c, d=None: d)
    monkeypatch.setattr(dom_inv, "locaciones_activas", lambda tipo=None: [{"id_locacion": 1, "nombre": "Sucursal Centro"}])
    monkeypatch.setattr(
        dom_lab,
        "obtener_campeon_y_retador",
        lambda **kw: {
            "campeon": {"metodo": "AUTO", "etiqueta": "Automático por tienda"},
            "retador": {"metodo": "ETS_HOLT_WINTERS", "etiqueta": "ETS (Tendencia + Estacionalidad)"},
        },
    )
    monkeypatch.setattr(dom_lab, "categorias_con_historia", lambda: ["Lácteos"])
    monkeypatch.setattr(
        dom_lab,
        "evaluar_modelos_laboratorio",
        lambda **kw: {
            "alcance": {"id_locacion": None, "categoria": "Todas", "horizonte": 7, "series_evaluadas": 4, "periodo_inicio": "2026-08-01", "periodo_fin": "2026-11-23"},
            "modelos": [
                {"modelo": "ETS_HOLT_WINTERS", "etiqueta": "ETS", "es_naive": False, "es_campeon": False, "es_retador": True, "recomendado": True, "wmape": 11.5, "mae": 2.1, "rmse": 2.9, "sesgo": 0.2, "fva_pp": 5.5, "merma_simulada_unidades": 3.0, "merma_simulada_valor": 45.0, "venta_perdida_valor": 20.0, "costo_total_simulado": 65.0, "ahorro_vs_naive_valor": 35.0},
            ],
            "campeon": {"metodo": "AUTO"},
            "retador": {"metodo": "ETS_HOLT_WINTERS"},
        },
    )
    monkeypatch.setattr(
        motor_pron,
        "evaluar_salud_datos",
        lambda **kw: {
            "resumen": {"total_tiendas": 1, "confiables": 1, "vigilancia": 0, "no_confiables": 0, "sin_datos": 0, "total_anomalias_sku": 0},
            "salud_datos": {"semaforo_global": "VERDE", "ultima_fecha_ventas": "2026-11-23", "dias_rezago_ventas": 0, "tiendas_verdes": 1, "tiendas_ambar": 0, "tiendas_rojas": 0},
            "tiendas": [{"id_locacion": 1, "locacion": "Sucursal Centro", "semaforo": "VERDE", "estado": "CONFIABLE", "cambio_nivel_pct": 1.2, "psi": 0.04, "ratio_volatilidad": 1.0, "delta_ceros_pp": 0.0, "dias_atipicos": 0, "aviso_pre_entrenamiento": "Estable", "motivos": [], "productos_con_anomalia": 0}],
            "anomalias_sku": [],
        },
    )
    monkeypatch.setattr(dom_ab, "inicializar_experimento_si_vacio", lambda usr: None)
    monkeypatch.setattr(dom_ab, "fecha_inicio_sugerida_real", lambda d=14: date(2026, 11, 10))
    monkeypatch.setattr(dom_ab, "obtener_experimento_activo", lambda: None)
    monkeypatch.setattr(dom_ab, "sugerir_asignacion_balanceada", lambda **kw: [{"id_locacion": 1, "locacion": "Centro", "volumen_30d": 100, "grupo": "CONTROL"}])
    monkeypatch.setattr(dom_ab, "listar_experimentos_ab", lambda limite=10: [])
    monkeypatch.setattr(
        motor_reab,
        "pipeline_produccion_newsvendor_fefo",
        lambda **kw: {
            "horizonte": 7,
            "resumen": {"total_series": 1, "con_orden_sugerida": 1, "unidades_sugeridas": 20.0, "inventario_en_riesgo": 2.0, "ahorro_esperado": 50.0},
            "filas": [{"id_sku": 1, "producto": "Leche", "categoria": "Lácteos", "unidad_medida": "litro", "id_locacion": 1, "locacion": "Centro", "desde": "2026-11-24", "hasta": "2026-11-30", "modelo_aplicado": "AUTO", "grupo_ab": None, "media": 70.0, "media_diaria": 10.0, "desviacion_std": 8.0, "fractil_critico": 0.6, "cuantil_optimo": 72.0, "caduca_hoy": 2.0, "caduca_manana": 5.0, "caduca_2_dias": 8.0, "caduca_3_5_dias": 10.0, "caduca_mas_5_dias": 20.0, "stock_fisico": 45.0, "inventario_riesgo": 2.0, "inventario_util": 43.0, "entradas_confirmadas": 0.0, "orden_sugerida": 29.0, "prioridad": "MEDIA", "ahorro_esperado": 50.0}],
        },
    )
    monkeypatch.setattr(motor_pron, "corridas", lambda *a, **kw: [])
    monkeypatch.setattr("app.domain.alertas.resumen_alertas", lambda: {"total": 0})

    web = create_app()
    c = web.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = "00000000-0000-0000-0000-000000000001"
        sess["role"] = "planner"
        sess["role_label"] = "Planeador"
        sess["user_name"] = "Planeador Demo"
        sess["user_email"] = "planner@freshtrack.mx"

    for etapa, texto in (
        ("salud", "Semáforo de Salud de Datos"),
        ("laboratorio", "Evaluar Modelos"),
        ("abtest", "Configurar A/B Test"),
        ("produccion", "Pipeline Integrado: Pronóstico"),
    ):
        r = c.get(f"/pronostico?etapa={etapa}")
        assert r.status_code == 200, etapa
        assert texto in r.get_data(as_text=True), etapa
