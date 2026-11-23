"""Pruebas de las páginas de análisis: Tablero, Pronósticos y Newsvendor."""

from __future__ import annotations

import pytest
import requests
from lxml import etree
from PySide6.QtWidgets import QApplication

from conftest import muestra
from freshtrack_desktop.core.activity_log import ActivityLog
from freshtrack_desktop.core.api_client import ApiClient
from freshtrack_desktop.core.session import Session
from freshtrack_desktop.ui.context import AppContext
from freshtrack_desktop.ui.pages.newsvendor import NewsvendorPage, validar_parametros
from freshtrack_desktop.ui.pages.pronosticos import PronosticosPage
from freshtrack_desktop.ui.pages.tablero import TableroPage

WAIT = 5000

ALERTAS = b"""<?xml version="1.0" encoding="UTF-8"?>
<alertas_activas><total>2</total><alertas>
<item><_id>a1</_id><tipo>RIESGO_PRE_MERMA</tipo><criticidad>CRITICAL</criticidad><mensaje>Lote por vencer</mensaje>
<generada_en>2026-11-22T10:00:00</generada_en><id_sku>1</id_sku><id_locacion>3</id_locacion></item>
<item><_id>a2</_id><tipo>EXCESO_COBERTURA</tipo><criticidad>WARNING</criticidad><mensaje>Exceso</mensaje>
<generada_en>2026-11-22T09:00:00</generada_en><id_sku>2</id_sku><id_locacion>4</id_locacion></item>
</alertas></alertas_activas>"""


@pytest.fixture
def ctx(settings, qtbot):
    api = ApiClient(settings)
    log = ActivityLog(settings.data_dir / "actividad.log")
    c = AppContext(settings, api, log)
    c.api.session = Session(token="tok", jti="j", usuario={"rol": "planner", "email": "planner@freshtrack.mx"})
    yield c
    c.pool.waitForDone(WAIT)
    QApplication.processEvents()
    log.close()


def _esperar(ctx, qtbot):
    qtbot.waitUntil(lambda: ctx.pending == 0, timeout=WAIT)
    QApplication.processEvents()


def _catalogos(fake_http):
    fake_http.add("GET", "/api/v1/catalog/locations", body=muestra("locations"))
    fake_http.add("GET", "/api/v1/catalog/products", body=muestra("products"))


def _raiz(req) -> str:
    return etree.fromstring(req.body).tag


# --- Tablero ------------------------------------------------------------------
def _tablero_http(fake_http):
    fake_http.add("GET", "/api/v1/planning/forecast/analytics/kpis", body=muestra("kpis_planning"))
    fake_http.add("GET", "/api/v1/alerts/analytics/kpis", body=muestra("kpis_alerts"))
    fake_http.add("GET", "/api/v1/alerts/waste-measurement", body=muestra("waste"))
    fake_http.add("GET", "/api/v1/alerts/active", body=ALERTAS)


def test_tablero_refresh_muestra_kpis_y_alertas(ctx, qtbot, fake_http):
    _tablero_http(fake_http)
    page = TableroPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    _esperar(ctx, qtbot)
    assert page.kpi_modelos.value_label.text() == "60"
    assert page.kpi_mejor.value_label.text() == "Suavización exponencial"
    assert page.kpi_alertas.value_label.text() == "312"
    assert page.kpi_criticas.value_label.text() == "33"
    assert page.kpi_riesgo.value_label.text() == "$16,117.91"
    filas = page.table.rows()
    assert [f["criticidad"] for f in filas] == ["CRÍTICO", "ADVERTENCIA"]
    assert filas[0]["tipo"] == "Riesgo pre-merma"
    assert page.aviso.isHidden()


def test_tablero_con_alerts_caido_sigue_mostrando_planning(ctx, qtbot, fake_http):
    fake_http.add("GET", "/api/v1/planning/forecast/analytics/kpis", body=muestra("kpis_planning"))
    for ruta in ("/api/v1/alerts/analytics/kpis", "/api/v1/alerts/waste-measurement", "/api/v1/alerts/active"):
        fake_http.add_error("GET", ruta, requests.ConnectionError("apagado"))
    page = TableroPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    _esperar(ctx, qtbot)
    assert page.kpi_modelos.value_label.text() == "60"
    assert page.kpi_alertas.sub_label.text() == "No disponible"
    assert page.kpi_merma.sub_label.text() == "No disponible"
    assert not page.aviso.isHidden()
    assert "alerts" in page.aviso.text()
    assert page.table.is_empty()


def test_tablero_alertas_vacias(ctx, qtbot, fake_http):
    fake_http.add("GET", "/api/v1/planning/forecast/analytics/kpis", body=muestra("kpis_planning"))
    fake_http.add("GET", "/api/v1/alerts/analytics/kpis", body=muestra("kpis_alerts"))
    fake_http.add("GET", "/api/v1/alerts/waste-measurement", body=muestra("waste"))
    fake_http.add("GET", "/api/v1/alerts/active", body=muestra("alerts_active"))
    page = TableroPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    _esperar(ctx, qtbot)
    assert page.table.is_empty()


# --- Pronósticos -------------------------------------------------------------------
def test_pronosticos_refresh_llena_catalogos(ctx, qtbot, fake_http):
    _catalogos(fake_http)
    page = PronosticosPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    _esperar(ctx, qtbot)
    assert page.cmb_tienda.count() == 8  # todas + 7 locaciones
    assert page.cmb_sku.count() == 6
    assert page.cmb_tienda.itemData(1) == 1


def test_pronosticos_generar_envia_xml_forecast_request(ctx, qtbot, fake_http):
    _catalogos(fake_http)
    fake_http.add("POST", "/api/v1/planning/forecast/run", status=201, body=muestra("forecast_run"))
    page = PronosticosPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    _esperar(ctx, qtbot)
    page.cmb_tienda.setCurrentIndex(page.cmb_tienda.findData(3))
    page.cmb_sku.setCurrentIndex(page.cmb_sku.findData(1))
    page.cmb_metodo.setCurrentIndex(page.cmb_metodo.findData("MEDIA_MOVIL"))
    page.generar()
    _esperar(ctx, qtbot)
    llamadas = fake_http.calls_to("POST", "/api/v1/planning/forecast/run")
    assert len(llamadas) == 1
    req = llamadas[0]
    assert _raiz(req) == "forecast_request"
    assert req.headers["Accept"] == "application/xml"
    assert req.headers["Content-Type"].startswith("application/xml")
    cuerpo = etree.fromstring(req.body)
    assert cuerpo.findtext("metodo") == "MEDIA_MOVIL"
    assert cuerpo.findtext("id_sku") == "1" and cuerpo.findtext("id_locacion") == "3"
    assert cuerpo.findtext("alpha") == "0.3"
    assert ctx.log.tail()[-1]["accion"] == "PRONOSTICO"


def test_pronosticos_resultado_con_series(ctx, qtbot, fake_http):
    run = b"""<forecast_run_result><id_run>r1</id_run><id_locacion>3</id_locacion><locacion>Tienda San Pedro</locacion>
<metodo>MEDIA_MOVIL</metodo><metodo_etiqueta>Media m\xc3\xb3vil</metodo_etiqueta><horizonte>2</horizonte><series>1</series>
<mae>5.0</mae><wmape>10.8</wmape><sesgo>1.6</sesgo><duracion_ms>15</duracion_ms>
<resultados><item><id_sku>1</id_sku><id_locacion>3</id_locacion><metodo_ganador>MEDIA_MOVIL</metodo_ganador>
<metricas><mae>5.0</mae><wmape>10.8</wmape><sesgo>1.6</sesgo></metricas><mejora_vs_naive_pct>45.2</mejora_vs_naive_pct>
<pronostico><item><fecha>2026-11-23</fecha><valor>41.9</valor></item><item><fecha>2026-11-24</fecha><valor>43.0</valor></item></pronostico>
</item></resultados></forecast_run_result>"""
    fake_http.add("POST", "/api/v1/planning/forecast/run", status=201, body=run)
    page = PronosticosPage(ctx)
    qtbot.addWidget(page)
    page.generar()
    _esperar(ctx, qtbot)
    assert len(page.tabla.rows()) == 2
    assert page.tabla_series.rows()[0]["metodo"] == "Media móvil"
    assert page.kpi_mae.value_label.text() == "5.00"
    assert len(page.grafico.chart().series()) == 1
    # con "todas" no se mandan id_sku/id_locacion
    cuerpo = etree.fromstring(fake_http.calls_to("POST", "/api/v1/planning/forecast/run")[0].body)
    assert cuerpo.find("id_sku") is None and cuerpo.find("id_locacion") is None


def test_pronosticos_buyer_no_puede_generar(ctx, qtbot, fake_http):
    ctx.api.session = Session(token="t", jti="j", usuario={"rol": "buyer", "email": "b@freshtrack.mx"})
    page = PronosticosPage(ctx)
    qtbot.addWidget(page)
    assert not page.btn_correr.isEnabled()


def test_pronosticos_ultimo_404_es_sin_pronostico(ctx, qtbot, fake_http, monkeypatch):
    _catalogos(fake_http)
    fake_http.add("GET", "/api/v1/planning/forecast/latest/1/3", status=404, body=muestra("fc_latest"))
    page = PronosticosPage(ctx)
    qtbot.addWidget(page)
    monkeypatch.setattr(ctx, "show_error", lambda *a, **k: pytest.fail("no debe mostrar error"))
    page.refresh()
    _esperar(ctx, qtbot)
    page.cmb_tienda.setCurrentIndex(page.cmb_tienda.findData(3))
    page.cmb_sku.setCurrentIndex(page.cmb_sku.findData(1))
    page.ver_ultimo()
    _esperar(ctx, qtbot)
    assert "Sin pronóstico guardado" in page.lbl_estado.text()
    assert page.tabla.is_empty()


def test_pronosticos_ultimo_guardado(ctx, qtbot, fake_http):
    latest = b"""<forecast_latest><id_sku>1</id_sku><id_locacion>3</id_locacion><fecha_calculo>2026-11-23T05:57:41</fecha_calculo>
<modelo>MEDIA_MOVIL</modelo><metricas><mae>5.0</mae><wmape>10.8</wmape><sesgo>1.6</sesgo></metricas>
<puntos><item><fecha>2026-11-23T00:00:00</fecha><demanda_pronosticada>41.96</demanda_pronosticada>
<intervalo_inferior>35.6</intervalo_inferior><intervalo_superior>48.2</intervalo_superior></item>
<item><fecha>2026-11-24T00:00:00</fecha><demanda_pronosticada>43.0</demanda_pronosticada>
<intervalo_inferior>36.5</intervalo_inferior><intervalo_superior>49.4</intervalo_superior></item></puntos></forecast_latest>"""
    _catalogos(fake_http)
    fake_http.add("GET", "/api/v1/planning/forecast/latest/1/3", body=latest)
    page = PronosticosPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    _esperar(ctx, qtbot)
    page.cmb_tienda.setCurrentIndex(page.cmb_tienda.findData(3))
    page.cmb_sku.setCurrentIndex(page.cmb_sku.findData(1))
    page.ver_ultimo()
    _esperar(ctx, qtbot)
    assert len(page.tabla.rows()) == 2
    assert len(page.grafico.chart().series()) == 3
    assert page.kpi_metodo.value_label.text() == "Media móvil"


def test_pronosticos_backtest_y_drift(ctx, qtbot, fake_http):
    fake_http.add("GET", "/api/v1/planning/forecast/backtest", body=muestra("backtest"))
    fake_http.add("GET", "/api/v1/planning/forecast/drift", body=muestra("drift"))
    page = PronosticosPage(ctx)
    qtbot.addWidget(page)
    page.cargar_backtest()
    page.cargar_drift()
    _esperar(ctx, qtbot)
    filas = {f["modelo"]: f for f in page.tabla_bt.rows()}
    assert len(filas) == 5
    assert set(filas) == {"Automático", "Media móvil", "Media móvil ponderada", "Suavización exponencial", "Ingenuo"}
    assert filas["Automático"]["mejora"] == pytest.approx((10.0229 - 6.355) / 10.0229 * 100)
    assert filas["Ingenuo"]["mejora"] is None
    assert len(page.grafico_bt.chart().series()) == 1  # una serie de barras con 2 conjuntos
    assert page.kpi_no_conf.value_label.text() == "5"
    drift = page.tabla_drift.rows()
    assert drift and drift[0]["estado"] == "CRÍTICO"
    assert fake_http.calls_to("GET", "/api/v1/planning/forecast/backtest")[0].params["horizonte"] == 7


# --- Newsvendor ----------------------------------------------------------------------
def test_newsvendor_validacion_local():
    assert validar_parametros(1, 1, 7) == []
    assert len(validar_parametros(None, None, 0)) == 3
    assert validar_parametros(1, 3, 366)


def test_newsvendor_evaluar_envia_xml_y_muestra_resultado(ctx, qtbot, fake_http):
    _catalogos(fake_http)
    fake_http.add("POST", "/api/v1/planning/newsvendor/evaluate", body=muestra("newsvendor"))
    page = NewsvendorPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    _esperar(ctx, qtbot)
    page.cmb_sku.setCurrentIndex(page.cmb_sku.findData(1))
    page.cmb_tienda.setCurrentIndex(page.cmb_tienda.findData(1))
    page.evaluar()
    _esperar(ctx, qtbot)
    req = fake_http.calls_to("POST", "/api/v1/planning/newsvendor/evaluate")[0]
    assert _raiz(req) == "newsvendor_request"
    assert req.headers["Accept"] == "application/xml"
    assert etree.fromstring(req.body).findtext("id_sku") == "1"
    assert page.kpi_sugerida.value_label.text() == "120"
    assert page.kpi_fractil.value_label.text() == "0.316"
    assert [f["politica"] for f in page.tabla_comp.rows()] == ["Newsvendor", "Política simple"]
    assert page.tabla_comp.rows()[1]["costo_esperado"] == "1665.6"
    assert ctx.log.tail()[-1]["accion"] == "NEWSVENDOR"


def test_newsvendor_sin_seleccion_no_envia(ctx, qtbot, fake_http):
    page = NewsvendorPage(ctx)
    qtbot.addWidget(page)
    page.evaluar()
    assert "Elige un SKU" in page.lbl_estado.text()
    assert not fake_http.calls


def test_etiqueta_metodo_legible():
    from freshtrack_desktop.ui.pages.pronosticos import etiqueta_metodo

    assert etiqueta_metodo("SUAVIZACION_EXPONENCIAL") == "Suavización exponencial"
    assert etiqueta_metodo("MEDIA_MOVIL_PONDERADA") == "Media móvil ponderada"
    assert etiqueta_metodo("NAIVE") == "Ingenuo"
    assert etiqueta_metodo("CROSTON_SBA") == "Croston sba"  # desconocido: legible igual
    assert etiqueta_metodo("") == "" and etiqueta_metodo(None) == ""


def test_pronosticos_grafica_inicial_dice_el_siguiente_paso(ctx, qtbot):
    page = PronosticosPage(ctx)
    qtbot.addWidget(page)
    assert page.grafico.chart().title() == "Elige tienda y SKU y pulsa «Generar pronóstico»."
