"""Pruebas del shell Qt: contexto, worker, login, ventana principal, inspector y páginas base."""

from __future__ import annotations

import csv
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import requests
from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from freshtrack_desktop.core.activity_log import ActivityLog
from freshtrack_desktop.core.api_client import ApiClient
from freshtrack_desktop.core.errors import ApiError, ServiceUnavailable, XmlContractError
from freshtrack_desktop.core.session import Session
from freshtrack_desktop.ui import theme
from freshtrack_desktop.ui.context import AppContext
from freshtrack_desktop.ui.widgets import DataTable, KpiCard, Toolbar

DESKTOP_DIR = Path(__file__).resolve().parents[1]
WAIT = 3000


# --- XML de ejemplo ----------------------------------------------------------------
def auth_xml(rol="planner", email="planner@freshtrack.mx", token="tok-1") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<auth_response><token>{token}</token><jti>jti-{token}</jti><token_type>Bearer</token_type>
<expira_en_segundos>28800</expira_en_segundos>
<usuario><id_usuario>7</id_usuario><email>{email}</email><nombre>Carlos Vega</nombre>
<rol>{rol}</rol><id_locacion>1</id_locacion></usuario></auth_response>""".encode()


def error_xml(status: int, codigo: str, mensaje: str = "Mensaje del servidor") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<error_response><error>{codigo}</error><mensaje>{mensaje}</mensaje><status>{status}</status>
<correlation_id>cid-servidor</correlation_id></error_response>""".encode()


HEALTH_OK = (Path(__file__).resolve().parents[2] / ".superpowers/sdd/2026-11-22-app-escritorio/samples/health_planning.xml")
HEALTH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<service_health><service>svc-x</service><status>HEALTHY</status><version>1.0.0</version>
<dependencies><postgres>true</postgres><mongo>true</mongo><redis>true</redis></dependencies></service_health>"""
HEALTH_DEGRADED = b"""<?xml version="1.0" encoding="UTF-8"?>
<service_health><service>svc-alerts</service><status>DEGRADED</status><version>1.0.0</version>
<dependencies><postgres>true</postgres><redis>false</redis></dependencies></service_health>"""
PRODUCTOS = b"""<?xml version="1.0" encoding="UTF-8"?>
<productos><total>1</total><productos><item><id_sku>1</id_sku></item></productos></productos>"""


# --- fixtures ------------------------------------------------------------------------
@pytest.fixture
def ctx(settings, qtbot):
    api = ApiClient(settings)
    log = ActivityLog(settings.data_dir / "actividad.log")
    c = AppContext(settings, api, log)
    yield c
    c.pool.waitForDone(WAIT)
    QApplication.processEvents()
    log.close()


@pytest.fixture
def controller(ctx, qtbot):
    from freshtrack_desktop.app import AppController

    ctrl = AppController(ctx, quit_fn=lambda: None)
    yield ctrl
    if ctrl.window is not None:
        ctrl.window.detach()
        ctrl.window.deleteLater()
    if ctrl.login_dialog is not None:
        ctrl.login_dialog.deleteLater()


def _login(controller, qtbot, fake_http, rol="planner", email="planner@freshtrack.mx"):
    fake_http.add("POST", "/api/v1/auth/login", body=auth_xml(rol=rol, email=email))
    controller.show_login()
    dlg = controller.login_dialog
    dlg.email.setText(email)
    dlg.password.setText("Secreta2026!")
    qtbot.mouseClick(dlg.btn_entrar, Qt.LeftButton)
    return dlg


def _con_sesion(ctx, rol="planner"):
    ctx.api.session = Session(token="tok", jti="j", usuario={"rol": rol, "email": f"{rol}@freshtrack.mx"})
    return ctx


# --- AppContext / worker -----------------------------------------------------------
def test_run_entrega_resultado_en_hilo_de_ui(ctx, qtbot):
    hilos = {}

    def trabajo(a, b):
        hilos["trabajo"] = QThread.currentThread()
        return a + b

    resultado = []

    def ok(valor):
        hilos["callback"] = QThread.currentThread()
        resultado.append(valor)

    ctx.run(trabajo, 2, 3, on_ok=ok)
    qtbot.waitUntil(lambda: resultado == [5], timeout=WAIT)
    app_thread = QApplication.instance().thread()
    assert hilos["callback"] is app_thread
    assert hilos["trabajo"] is not app_thread
    qtbot.waitUntil(lambda: ctx.pending == 0, timeout=WAIT)


def test_run_entrega_excepcion_y_deshabilita_busy(ctx, qtbot):
    boton = QPushButton("Cargar")
    qtbot.addWidget(boton)
    liberar = threading.Event()
    errores = []

    def falla():
        liberar.wait(2)
        raise ServiceUnavailable("planning")

    ctx.run(falla, on_error=errores.append, busy=boton)
    assert not boton.isEnabled()
    liberar.set()
    qtbot.waitUntil(lambda: len(errores) == 1, timeout=WAIT)
    assert isinstance(errores[0], ServiceUnavailable)
    qtbot.waitUntil(lambda: boton.isEnabled(), timeout=WAIT)


def test_run_no_explota_si_el_widget_destino_ya_no_existe(ctx, qtbot):
    import shiboken6

    etiqueta = QLabel()
    liberar = threading.Event()

    def lento():
        liberar.wait(2)
        return "hola"

    ctx.run(lento, on_ok=etiqueta.setText, busy=etiqueta)
    shiboken6.delete(etiqueta)
    liberar.set()
    qtbot.waitUntil(lambda: ctx.pending == 0, timeout=WAIT)


def test_error_message_por_tipo():
    from freshtrack_desktop.ui.context import error_message

    assert error_message(ServiceUnavailable("planning")) == "El servicio planning no está disponible"
    assert error_message(ApiError(403, "acceso_denegado", "x")) == "No tienes permiso para esta acción"
    assert error_message(XmlContractError("mal")) == "La respuesta no cumple el contrato XML"
    assert error_message(ApiError(409, "conflicto", "Ya existe")) == "Ya existe"


def test_show_error_muestra_correlation_id_y_lo_registra(ctx, qtbot):
    exc = ApiError(403, "acceso_denegado", "Sin permiso", correlation_id="cid-123")
    dlg = ctx.show_error(exc, None)
    try:
        assert dlg.text() == "No tienes permiso para esta acción"
        assert "cid-123" in dlg.informativeText()
        assert "403" in dlg.informativeText()
        info = dlg.findChild(QLabel, "qt_msgbox_informativelabel")
        assert info is None or info.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    finally:
        dlg.close()
    ultima = ctx.log.tail()[-1]
    assert ultima["ok"] is False and "cid-123" in ultima["detalle"]


def test_service_for_url(ctx):
    assert ctx.service_for_url("http://localhost:5006/api/v1/planning/x") == "planning"
    ctx.settings.set_servers(gateway_url="https://gw.example.com")
    assert ctx.service_for_url("https://gw.example.com/api/v1/alerts/active") == "alerts"


# --- widgets -------------------------------------------------------------------------
def test_datatable_filtra_ordena_selecciona_y_exporta(qtbot, tmp_path):
    t = DataTable(empty_text="Sin órdenes")
    qtbot.addWidget(t)
    t.set_columns([("id", "ID"), ("nombre", "Nombre"), ("monto", "Monto", "money")])
    assert t.is_empty()
    filas = [{"id": "2", "nombre": "Manzana", "monto": "1234.5"},
             {"id": "10", "nombre": "Pera", "monto": "20"}]
    t.set_rows(filas)
    assert not t.is_empty()
    assert t.rows() == filas
    assert t.model.item(0, 2).text() == "$1,234.50"
    # orden numérico (10 > 2), no alfabético
    t.view.sortByColumn(0, Qt.DescendingOrder)
    assert [r["id"] for r in t.visible_rows()] == ["10", "2"]
    t.filter_edit.setText("manz")
    assert [r["nombre"] for r in t.visible_rows()] == ["Manzana"]
    t.view.selectRow(0)
    assert t.selected_row() == filas[0]
    destino = tmp_path / "out.csv"
    t.filter_edit.clear()
    assert t.export_csv(destino) == 2
    with open(destino, encoding="utf-8-sig", newline="") as fh:
        filas_csv = list(csv.reader(fh))
    assert filas_csv[0] == ["ID", "Nombre", "Monto"]
    assert len(filas_csv) == 3
    assert "<table" in t.to_html("Reporte") and "Manzana" in t.to_html("Reporte")


def test_kpi_card_y_toolbar(qtbot):
    k = KpiCard("Servicios OK")
    qtbot.addWidget(k)
    k.set_value("7/8", "1 caído")
    assert k.value_label.text() == "7/8" and k.sub_label.text() == "1 caído"
    bar = Toolbar()
    llamado = []
    b = bar.add_button("Actualizar", lambda: llamado.append(1), variant="primary")
    b.click()
    assert llamado == [1] and b.property("variant") == "primary"


def test_theme_apply_define_paleta(qtbot):
    app = QApplication.instance()
    theme.apply(app)
    assert theme.base_style().lower() == "fusion"
    t = theme.tokens()
    assert t["primary"] in (theme.LIGHT["primary"], theme.DARK["primary"])
    assert set(theme.LIGHT) == set(theme.DARK)


# --- páginas -------------------------------------------------------------------------
def test_all_pages_orden_y_roles():
    from freshtrack_desktop.ui.pages import ALL_PAGES
    from freshtrack_desktop.ui.pages.base import BasePage

    titulos = [p.title for p in ALL_PAGES]
    assert titulos == ["Tablero", "Pronósticos", "Newsvendor", "Reabastecimiento", "Transferencias",
                       "Descuentos", "Mermas y desperdicio", "Órdenes de compra", "Importar ventas",
                       "Estado de servicios", "Actividad"]
    roles = {p.title: set(p.roles) for p in ALL_PAGES}
    assert roles["Órdenes de compra"] == {"buyer"}
    assert roles["Transferencias"] == {"planner"} and roles["Descuentos"] == {"planner"}
    assert roles["Pronósticos"] == {"planner", "buyer"}
    assert roles["Importar ventas"] == {"buyer", "planner"}
    assert roles["Tablero"] == set() and roles["Actividad"] == set()
    assert all(issubclass(p, BasePage) for p in ALL_PAGES)


def test_estado_page_marca_servicio_caido_y_degradado(ctx, qtbot, fake_http):
    from freshtrack_desktop.ui.pages.estado import EstadoPage

    fake_http.add("GET", "/health", body=HEALTH_OK.read_bytes())
    fake_http.add_error("GET", "localhost:5003/health", requests.ConnectionError("apagado"))
    fake_http.add("GET", "localhost:5007/health", status=503, body=HEALTH_DEGRADED)
    page = EstadoPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    qtbot.waitUntil(lambda: len(page.table.rows()) == 8, timeout=WAIT)
    estados = {r["servicio"]: r["estado"] for r in page.table.rows()}
    assert estados["inventory"] == "CAÍDO"
    assert estados["alerts"] == "DEGRADADO"
    assert estados["planning"] == "OK"
    assert list(estados) == ["auth", "catalog", "inventory", "commercial", "asn", "planning", "alerts", "audit"]
    alerts = next(r for r in page.table.rows() if r["servicio"] == "alerts")
    assert "redis" in alerts["dependencias"] and alerts["version"] == "1.0.0"
    assert page.kpi_caidos.value_label.text() == "1"


def test_estado_page_autorefresh_solo_mientras_esta_activa(ctx, qtbot, fake_http):
    from freshtrack_desktop.ui.pages.estado import EstadoPage

    fake_http.add("GET", "/health", body=HEALTH_XML)
    page = EstadoPage(ctx)
    qtbot.addWidget(page)
    page.on_show()
    assert page.timer.isActive() and page.timer.interval() == 30_000
    qtbot.waitUntil(lambda: len(page.table.rows()) == 8, timeout=WAIT)
    page.on_hide()
    assert not page.timer.isActive()


def test_actividad_page_muestra_tail_y_sincroniza(ctx, qtbot, fake_http):
    from freshtrack_desktop.ui.pages.actividad import ActividadPage

    _con_sesion(ctx)
    ctx.log.record("LOGIN", "entrada")
    ctx.log.record("APROBAR_ORDEN", "orden 5", ok=False)
    fake_http.add("POST", "/api/v1/audit/log", status=201,
                  body=b"<audit_log_response><ok>true</ok></audit_log_response>")
    page = ActividadPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    acciones = [r["accion"] for r in page.table.rows()]
    assert acciones == ["APROBAR_ORDEN", "LOGIN"]  # más reciente primero
    qtbot.mouseClick(page.btn_sync, Qt.LeftButton)
    qtbot.waitUntil(lambda: len(fake_http.calls_to("POST", "/api/v1/audit/log")) == 2, timeout=WAIT)
    qtbot.waitUntil(lambda: ctx.pending == 0, timeout=WAIT)


# --- inspector XML -------------------------------------------------------------------
def test_inspector_recibe_exchange_tras_una_llamada(ctx, qtbot, fake_http):
    from freshtrack_desktop.ui.xml_inspector import XmlInspector

    fake_http.add("GET", "/api/v1/catalog/products", body=PRODUCTOS)
    insp = XmlInspector(ctx)
    qtbot.addWidget(insp)
    ctx.run(ctx.api.call, "catalog", "GET", "/api/v1/catalog/products", on_ok=lambda _: None)
    qtbot.waitUntil(lambda: len(insp.exchanges) == 1, timeout=WAIT)
    ex = insp.exchanges[0]
    assert ex.status == 200 and ex.url.endswith("/api/v1/catalog/products")
    assert "<productos>" in insp.response_view.toPlainText()
    assert "\n  <total>1</total>" in insp.response_view.toPlainText()  # con indentación
    insp.detach()
    assert insp._listener not in ctx.api.listeners


def test_inspector_guarda_solo_50(ctx, qtbot):
    from freshtrack_desktop.core.api_client import Exchange
    from freshtrack_desktop.ui.xml_inspector import XmlInspector

    insp = XmlInspector(ctx)
    qtbot.addWidget(insp)
    for i in range(60):
        insp.add_exchange(Exchange("GET", f"http://h/{i}", 200, "", "<a/>", f"c{i}", 1.0))
    assert len(insp.exchanges) == 50
    assert insp.exchanges[0].correlation_id == "c59"  # más reciente primero
    insp.detach()


# --- login y ventana principal ------------------------------------------------------
def test_login_planner_abre_ventana_con_paginas_permitidas(controller, qtbot, fake_http, ctx):
    _login(controller, qtbot, fake_http, rol="planner")
    qtbot.waitUntil(lambda: controller.window is not None and controller.window.isVisible(), timeout=WAIT)
    titulos = controller.window.page_titles()
    assert "Órdenes de compra" not in titulos
    assert "Transferencias" in titulos and "Estado de servicios" in titulos and "Actividad" in titulos
    assert "planner" in controller.window.user_label.text().lower() or "planeador" in controller.window.user_label.text().lower()
    assert ctx.log.tail()[-1]["accion"] == "LOGIN"
    assert ctx.window is controller.window


def test_login_buyer_ve_ordenes_y_no_transferencias(controller, qtbot, fake_http):
    _login(controller, qtbot, fake_http, rol="buyer", email="buyer@freshtrack.mx")
    qtbot.waitUntil(lambda: controller.window is not None, timeout=WAIT)
    titulos = controller.window.page_titles()
    assert "Órdenes de compra" in titulos
    assert "Transferencias" not in titulos and "Descuentos" not in titulos


def test_login_warehouse_muestra_error_y_no_abre(controller, qtbot, fake_http, ctx):
    fake_http.add("POST", "/api/v1/auth/logout", status=200, body=b"")
    dlg = _login(controller, qtbot, fake_http, rol="warehouse", email="almacen@freshtrack.mx")
    qtbot.waitUntil(lambda: len(fake_http.calls_to("POST", "/api/v1/auth/logout")) == 1, timeout=WAIT)
    qtbot.waitUntil(lambda: ctx.pending == 0, timeout=WAIT)
    assert controller.window is None
    assert dlg.isVisible()
    assert dlg.message.text().splitlines()[0] == "Esta aplicación es para compradores y planeadores"
    assert "warehouse" in dlg.message.text() and dlg.message.isVisible()
    assert ctx.api.session is None


def test_login_credenciales_invalidas_muestra_mensaje(controller, qtbot, fake_http, ctx):
    fake_http.add("POST", "/api/v1/auth/login", status=401,
                  body=error_xml(401, "credenciales_invalidas", "Credenciales inválidas"))
    controller.show_login()
    dlg = controller.login_dialog
    dlg.email.setText("planner@freshtrack.mx")
    dlg.password.setText("mala")
    qtbot.mouseClick(dlg.btn_entrar, Qt.LeftButton)
    qtbot.waitUntil(lambda: "Credenciales inválidas" in dlg.message.text(), timeout=WAIT)
    assert controller.window is None and dlg.btn_entrar.isEnabled()


def test_login_auth_caido_muestra_servicio_no_disponible(controller, qtbot, fake_http):
    fake_http.add_error("POST", "/api/v1/auth/login", requests.ConnectionError("rechazada"))
    controller.show_login()
    dlg = controller.login_dialog
    dlg.email.setText("planner@freshtrack.mx")
    dlg.password.setText("x")
    qtbot.mouseClick(dlg.btn_entrar, Qt.LeftButton)
    qtbot.waitUntil(lambda: "El servicio auth no está disponible" in dlg.message.text(), timeout=WAIT)


def test_login_cuentas_demo_llenan_campos(controller, qtbot):
    controller.show_login()
    dlg = controller.login_dialog
    dlg.btn_demo_buyer.click()
    assert dlg.email.text() == "buyer@freshtrack.mx" and dlg.password.text()
    dlg.btn_demo_planner.click()
    assert dlg.email.text() == "planner@freshtrack.mx"


def test_dialogo_servidores_guarda_settings(settings, qtbot):
    from freshtrack_desktop.ui.login_dialog import ServersDialog

    dlg = ServersDialog(settings)
    qtbot.addWidget(dlg)
    dlg.host.setText("10.0.0.5")
    dlg.gateway.setText("")
    dlg.accept()
    assert settings.base_urls["auth"] == "http://10.0.0.5:5001"
    assert settings.config_path.exists()


def test_on_unauthorized_regresa_al_login(controller, qtbot, fake_http, ctx):
    _login(controller, qtbot, fake_http, rol="planner")
    qtbot.waitUntil(lambda: controller.window is not None and controller.window.isVisible(), timeout=WAIT)
    ventana = controller.window
    fake_http.add("GET", "/api/v1/planning/transfers", status=401, body=error_xml(401, "token_revocado"))
    fake_http.add("POST", "/api/v1/auth/refresh", status=401, body=error_xml(401, "token_revocado"))
    errores = []
    ctx.run(ctx.api.call, "planning", "GET", "/api/v1/planning/transfers", on_error=errores.append)
    qtbot.waitUntil(lambda: controller.window is None and controller.login_dialog.isVisible(), timeout=WAIT)
    import shiboken6

    assert not shiboken6.isValid(ventana) or not ventana.isVisible()  # WA_DeleteOnClose
    assert "Tu sesión terminó o fue revocada" in controller.login_dialog.message.text()
    assert ctx.api.session is None


def test_cerrar_sesion_vuelve_al_login(controller, qtbot, fake_http, ctx):
    fake_http.add("POST", "/api/v1/auth/logout", status=200, body=b"")
    _login(controller, qtbot, fake_http, rol="planner")
    qtbot.waitUntil(lambda: controller.window is not None, timeout=WAIT)
    controller.window.logout()
    qtbot.waitUntil(lambda: controller.window is None and controller.login_dialog.isVisible(), timeout=WAIT)
    assert len(fake_http.calls_to("POST", "/api/v1/auth/logout")) == 1
    assert ctx.api.session is None


def test_ventana_muestra_servicio_de_ultima_llamada(controller, qtbot, fake_http, ctx):
    _login(controller, qtbot, fake_http, rol="planner")
    qtbot.waitUntil(lambda: controller.window is not None, timeout=WAIT)
    fake_http.add("GET", "/api/v1/catalog/products", body=PRODUCTOS)
    ctx.run(ctx.api.call, "catalog", "GET", "/api/v1/catalog/products", on_ok=lambda _: None)
    qtbot.waitUntil(lambda: "catalog" in controller.window.service_label.text(), timeout=WAIT)
    controller.window.show_page("Estado de servicios")
    assert controller.window.current_page().title == "Estado de servicios"


# --- arranque ------------------------------------------------------------------------
def _entorno(tmp_path):
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", HOME=str(tmp_path))
    env.pop("FRESHTRACK_GATEWAY_URL", None)
    env.pop("FRESHTRACK_HOST", None)
    return env


def test_smoke_modulo(tmp_path):
    r = subprocess.run([sys.executable, "-m", "freshtrack_desktop", "--smoke"], cwd=DESKTOP_DIR,
                       env=_entorno(tmp_path), capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode(errors="replace")


def test_smoke_lanzador_desde_la_raiz(tmp_path):
    raiz = DESKTOP_DIR.parent
    r = subprocess.run([sys.executable, "desktop/run_desktop.py", "--smoke"], cwd=raiz,
                       env=_entorno(tmp_path), capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode(errors="replace")


def test_format_value_fecha_iso_en_hora_local():
    from freshtrack_desktop.ui.widgets import format_value
    assert format_value("2026-11-23T05:44:38.234314+00:00").count(":") == 1
    assert len(format_value("2026-11-23T05:44:38.234314+00:00")) == 16
    assert format_value("2026-11-23") == "2026-11-23"
    assert format_value("no es fecha") == "no es fecha"
