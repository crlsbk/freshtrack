"""Pruebas de las páginas de decisión: Reabastecimiento, Transferencias y Descuentos."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from freshtrack_desktop.core.session import Session
from freshtrack_desktop.ui.pages import descuentos, reabastecimiento, transferencias
from freshtrack_desktop.ui.pages.descuentos import DescuentosPage
from freshtrack_desktop.ui.pages.reabastecimiento import ReabastecimientoPage
from freshtrack_desktop.ui.pages.transferencias import TransferenciasPage

from test_shell import WAIT, ctx, error_xml  # noqa: F401 - fixture ctx

SAMPLES = Path(__file__).resolve().parents[2] / ".superpowers/sdd/2026-11-22-app-escritorio/samples"
ORDENES = (SAMPLES / "repl_orders.xml").read_bytes()
TRANSFERS = (SAMPLES / "transfers.xml").read_bytes()
DISCOUNTS = (SAMPLES / "discounts.xml").read_bytes()
LOCS = (SAMPLES / "locations.xml").read_bytes()
SKU = (SAMPLES / "sku_context.xml").read_bytes()
CYCLE = (SAMPLES / "cycle_run.xml").read_bytes()
VACIO_ORD = (b"<replenishment_orders><paginacion><pagina>1</pagina><por_pagina>100</por_pagina><total>0</total>"
             b"<total_paginas>0</total_paginas></paginacion><ordenes /></replenishment_orders>")
OK_DECISION = b"<orden_decision><id_orden>x</id_orden><estado>APROBADA</estado></orden_decision>"
L = "/api/v1/planning"


def con_sesion(ctx, rol="planner"):
    ctx.api.session = Session(token="tok", jti="j", usuario={"rol": rol, "email": f"{rol}@freshtrack.mx"})
    return ctx


def cargada(qtbot, cls, ctx, n):
    page = cls(ctx)
    qtbot.addWidget(page)
    page.on_show()
    qtbot.waitUntil(lambda: len(page.table.rows()) == n and ctx.pending == 0, timeout=WAIT)
    return page


def seleccionar_todo(page):
    page.table.view.selectAll()
    QApplication.processEvents()


def acciones(ctx):
    return [e["accion"] for e in ctx.log.tail(50)]


@pytest.fixture
def api(fake_http):
    fake_http.add("GET", f"{L}/replenishment/orders", body=ORDENES)
    fake_http.add("GET", "/api/v1/catalog/locations", body=LOCS)
    fake_http.add("GET", f"{L}/transfers", body=TRANSFERS)
    fake_http.add("GET", f"{L}/discounts", body=DISCOUNTS)
    return fake_http


# --- Reabastecimiento -----------------------------------------------------------------
def test_reabastecimiento_lista_filtros_y_detalle(ctx, qtbot, api):
    con_sesion(ctx)
    page = cargada(qtbot, ReabastecimientoPage, ctx, 5)
    assert (ReabastecimientoPage.title, ReabastecimientoPage.roles) == ("Reabastecimiento", ("planner", "buyer"))
    peticion = api.calls_to("GET", f"{L}/replenishment/orders")[0]
    assert peticion.params["estado"] == "PENDIENTE" and "id_locacion" not in peticion.params
    qtbot.waitUntil(lambda: page.cmb_tienda.count() == 6, timeout=WAIT)  # Todas + 5 tiendas
    page.table.view.selectRow(0)
    assert "Zanahoria" in page.detail.toPlainText() and "Newsvendor" in page.detail.toPlainText()
    page.cmb_tienda.setCurrentIndex(page.cmb_tienda.findText("Tienda Sur"))
    qtbot.waitUntil(lambda: any(c.params.get("id_locacion") == "7"
                                for c in api.calls_to("GET", f"{L}/replenishment/orders")), timeout=WAIT)


def test_reabastecimiento_aprobar_usa_post_y_registra(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    api.add("POST", f"{L}/replenishment/orders/9a34ffda-47f6-46e3-b9ea-30384f1b7d2c/approve", body=OK_DECISION)
    page = cargada(qtbot, ReabastecimientoPage, ctx, 5)
    page.table.view.selectRow(0)
    monkeypatch.setattr(reabastecimiento, "confirm", lambda *a, **k: True)
    n_antes = len(api.calls_to("GET", f"{L}/replenishment/orders"))
    page.btn_aprobar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and len(api.calls_to("GET", f"{L}/replenishment/orders")) > n_antes,
                    timeout=WAIT)
    posts = [c for c in api.calls if c.method == "POST"]
    assert len(posts) == 1 and posts[0].url.endswith("/9a34ffda-47f6-46e3-b9ea-30384f1b7d2c/approve")
    assert posts[0].headers["Accept"] == "application/xml"
    assert "APROBAR_ORDEN" in acciones(ctx)


def test_reabastecimiento_lote_reporta_exitos_y_errores(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    api.add("POST", f"{L}/replenishment/orders/612b4b36-06a3-4e3c-b900-23e82b7fcc6e/approve", status=409,
            body=error_xml(409, "regla_negocio", "La orden ya fue decidida"))
    api.add("POST", "/approve", body=OK_DECISION)
    page = cargada(qtbot, ReabastecimientoPage, ctx, 5)
    seleccionar_todo(page)
    resumenes = []
    monkeypatch.setattr(reabastecimiento, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(ReabastecimientoPage, "_resumen", lambda self, v, ok, err: resumenes.append((ok, len(err))))
    page.btn_aprobar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and len(resumenes) == 1, timeout=WAIT)
    assert resumenes == [(4, 1)]
    assert len([c for c in api.calls if c.method == "POST"]) == 5
    registros = [e for e in ctx.log.tail(50) if e["accion"] == "APROBAR_ORDEN"]
    assert sum(e["ok"] for e in registros) == 4 and sum(not e["ok"] for e in registros) == 1


def test_reabastecimiento_rechazar_pide_motivo(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    api.add("POST", "/reject", body=OK_DECISION)
    page = cargada(qtbot, ReabastecimientoPage, ctx, 5)
    page.table.view.selectRow(1)
    monkeypatch.setattr(reabastecimiento, "ask_text", lambda *a, **k: None)
    page.btn_rechazar.click()
    QApplication.processEvents()
    assert not [c for c in api.calls if c.method == "POST"]  # sin motivo no se rechaza
    monkeypatch.setattr(reabastecimiento, "ask_text", lambda *a, **k: "Sobrestock")
    page.btn_rechazar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "RECHAZAR_ORDEN" in acciones(ctx), timeout=WAIT)
    post = [c for c in api.calls if c.method == "POST"][0]
    assert post.url.endswith("/612b4b36-06a3-4e3c-b900-23e82b7fcc6e/reject") and "Sobrestock" in post.text
    detalle = next(e["detalle"] for e in ctx.log.tail(50) if e["accion"] == "RECHAZAR_ORDEN")
    assert "Sobrestock" in detalle


def test_reabastecimiento_403_muestra_error_sin_romper(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    api.add("POST", "/approve", status=403, body=error_xml(403, "prohibido", "Rol sin permiso"))
    page = cargada(qtbot, ReabastecimientoPage, ctx, 5)
    page.table.view.selectRow(0)
    errores = []
    monkeypatch.setattr(ctx, "show_error", lambda exc, parent=None: errores.append(exc))
    page.btn_aprobar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and len(errores) == 1, timeout=WAIT)
    assert errores[0].status == 403
    assert page.table.rows() and page.btn_actualizar.isEnabled()
    assert any(not e["ok"] for e in ctx.log.tail(50) if e["accion"] == "APROBAR_ORDEN")


def test_reabastecimiento_lista_vacia_muestra_cero_filas(ctx, qtbot, fake_http):
    con_sesion(ctx)
    fake_http.add("GET", f"{L}/replenishment/orders", body=VACIO_ORD)
    fake_http.add("GET", "/api/v1/catalog/locations", body=LOCS)
    page = cargada(qtbot, ReabastecimientoPage, ctx, 0)
    assert page.table.is_empty() and "0 de 0" in page.status_label.text()


def test_reabastecimiento_generar_envia_horizonte(ctx, qtbot, api):
    con_sesion(ctx)
    api.add("POST", f"{L}/replenishment/generate", status=201,
            body=b"<replenishment_generated><total>3</total><ordenes /></replenishment_generated>")
    page = cargada(qtbot, ReabastecimientoPage, ctx, 5)
    page.spin_horizonte.setValue(14)
    page.btn_generar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "GENERAR_ORDENES" in acciones(ctx), timeout=WAIT)
    post = api.calls_to("POST", f"{L}/replenishment/generate")[0]
    assert "<horizonte>14</horizonte>" in post.text and "replenishment_request" in post.text


def test_contexto_del_sku(ctx, qtbot, api):
    con_sesion(ctx)
    api.add("GET", f"{L}/sku/10/full-context", body=SKU)
    page = cargada(qtbot, ReabastecimientoPage, ctx, 5)
    page.table.view.selectRow(0)
    page.btn_contexto.click()
    qtbot.waitUntil(lambda: "Contexto del SKU" in page.detail.toPlainText(), timeout=WAIT)
    assert api.calls_to("GET", f"{L}/sku/10/full-context")[0].params == {"id_locacion": "5"}
    assert "Leche Entera" in page.detail.toPlainText()


def test_ciclo_planeacion_actualiza_las_tres_listas(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    api.add("POST", f"{L}/cycle/run", status=201, body=CYCLE)
    monkeypatch.setattr(reabastecimiento, "confirm", lambda *a, **k: True)
    raiz = QWidget()
    qtbot.addWidget(raiz)
    reab, trans, desc = ReabastecimientoPage(ctx, raiz), TransferenciasPage(ctx, raiz), DescuentosPage(ctx, raiz)
    qtbot.waitUntil(lambda: ctx.pending == 0, timeout=WAIT)
    reab.btn_ciclo.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "EJECUTAR_CICLO" in acciones(ctx)
                    and len(trans.table.rows()) == 22 and len(desc.table.rows()) == 12
                    and len(reab.table.rows()) == 5, timeout=WAIT)
    post = api.calls_to("POST", f"{L}/cycle/run")[0]
    assert "planning_cycle_request" in post.text and "<horizonte>7</horizonte>" in post.text
    detalle = next(e["detalle"] for e in ctx.log.tail(50) if e["accion"] == "EJECUTAR_CICLO")
    assert "5 tienda(s) recalibrada(s)" in detalle and "22 traslado(s)" in detalle


def test_ciclo_deshabilitado_si_no_es_planner(ctx, qtbot, api):
    con_sesion(ctx, "buyer")
    page = cargada(qtbot, ReabastecimientoPage, ctx, 5)
    assert not page.btn_ciclo.isEnabled() and page.btn_generar.isEnabled()
    con_sesion(ctx, "planner")
    page.on_show()
    assert page.btn_ciclo.isEnabled()


# --- Transferencias -------------------------------------------------------------------
def test_transferencias_lista_y_detalle(ctx, qtbot, api):
    con_sesion(ctx)
    page = cargada(qtbot, TransferenciasPage, ctx, 22)
    assert (TransferenciasPage.title, TransferenciasPage.roles) == ("Transferencias", ("planner",))
    page.table.view.selectRow(0)
    txt = page.detail.toPlainText()
    assert "[OK] El destino lo necesita" in txt and "Tienda" in txt
    assert not page.btn_ejecutar.isEnabled() and page.btn_aprobar.isEnabled()


def test_transferencias_aprobar_rechazar_ejecutar(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    for accion in ("approve", "reject", "execute"):
        api.add("POST", f"/{accion}", body=b"<transfer_decision><estado>OK</estado></transfer_decision>")
    monkeypatch.setattr(transferencias, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(transferencias, "ask_text", lambda *a, **k: "No hay camión")
    page = cargada(qtbot, TransferenciasPage, ctx, 22)
    page.table.view.selectRow(0)
    id0 = page.table.selected_row()["id_transferencia"]
    page.btn_aprobar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "APROBAR_TRANSFERENCIA" in acciones(ctx), timeout=WAIT)
    assert api.calls_to("POST", f"{L}/transfers/{id0}/approve")
    page.table.view.selectRow(1)
    page.btn_rechazar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "RECHAZAR_TRANSFERENCIA" in acciones(ctx), timeout=WAIT)
    assert any(c.url.endswith("/reject") and "No hay camión" in c.text for c in api.calls)
    # Ejecutar solo aplica a APROBADA: simula una fila aprobada.
    fila = dict(page.table.rows()[0], estado="APROBADA")
    page.table.set_rows([fila])
    page.table.view.selectRow(0)
    page.btn_ejecutar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "EJECUTAR_TRANSFERENCIA" in acciones(ctx), timeout=WAIT)
    assert api.calls_to("POST", f"{L}/transfers/{id0}/execute")


def test_transferencias_detectar_y_lista_vacia(ctx, qtbot, fake_http):
    con_sesion(ctx)
    fake_http.add("GET", f"{L}/transfers", body=b"<transfers_list><total>0</total><resumen><sugeridas>0</sugeridas>"
                  b"</resumen><transferencias /></transfers_list>")
    fake_http.add("POST", f"{L}/transfers/detect", status=201,
                  body=b"<transfers_detected><total>4</total><descartadas>1</descartadas></transfers_detected>")
    page = cargada(qtbot, TransferenciasPage, ctx, 0)
    assert page.table.is_empty()
    page.btn_detectar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "DETECTAR_TRANSFERENCIAS" in acciones(ctx), timeout=WAIT)
    assert "transfers_detect_request" in fake_http.calls_to("POST", f"{L}/transfers/detect")[0].text
    assert "4 nueva(s)" in next(e["detalle"] for e in ctx.log.tail(10) if e["accion"] == "DETECTAR_TRANSFERENCIAS")


def test_transferencias_403_en_aprobar(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    api.add("POST", "/approve", status=403, body=error_xml(403, "prohibido"))
    errores = []
    monkeypatch.setattr(ctx, "show_error", lambda exc, parent=None: errores.append(exc))
    page = cargada(qtbot, TransferenciasPage, ctx, 22)
    page.table.view.selectRow(0)
    page.btn_aprobar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and bool(errores), timeout=WAIT)
    assert errores[0].status == 403 and len(page.table.rows()) == 22


# --- Descuentos -----------------------------------------------------------------------
def test_descuentos_muestra_precio_margen_y_vigencia(ctx, qtbot, api):
    con_sesion(ctx)
    page = cargada(qtbot, DescuentosPage, ctx, 12)
    assert (DescuentosPage.title, DescuentosPage.roles) == ("Descuentos", ("planner",))
    fila = next(r for r in page.table.rows() if r["id_descuento"] == "1fd4e983-0a75-4aec-aa41-602d725c1320")
    assert fila["margen"] == pytest.approx((76.42 - 55.0) / 76.42 * 100)
    assert fila["vigencia"] == "4 d (vence 2026-11-27)"
    page.table.view.selectRow(0)
    assert "Margen con descuento" in page.detail.toPlainText()


def test_descuentos_aprobar_y_generar(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    api.add("POST", "/approve", body=b"<discount_decision><estado>APROBADO</estado></discount_decision>")
    api.add("POST", f"{L}/discounts/generate", status=201,
            body=b"<discounts_generated><total>2</total></discounts_generated>")
    page = cargada(qtbot, DescuentosPage, ctx, 12)
    page.table.view.selectRow(0)
    id0 = page.table.selected_row()["id_descuento"]
    page.btn_aprobar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "APROBAR_DESCUENTO" in acciones(ctx), timeout=WAIT)
    assert api.calls_to("POST", f"{L}/discounts/{id0}/approve")
    page.spin_dias.setValue(3)
    page.btn_generar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and "GENERAR_DESCUENTOS" in acciones(ctx), timeout=WAIT)
    assert "<dias_hasta>3</dias_hasta>" in api.calls_to("POST", f"{L}/discounts/generate")[0].text


def test_descuentos_rechazar_403_y_vacio(ctx, qtbot, api, monkeypatch):
    con_sesion(ctx)
    api.add("POST", "/reject", status=403, body=error_xml(403, "prohibido"))
    monkeypatch.setattr(descuentos, "ask_text", lambda *a, **k: "Margen bajo")
    errores = []
    monkeypatch.setattr(ctx, "show_error", lambda exc, parent=None: errores.append(exc))
    page = cargada(qtbot, DescuentosPage, ctx, 12)
    page.table.view.selectRow(0)
    page.btn_rechazar.click()
    qtbot.waitUntil(lambda: ctx.pending == 0 and bool(errores), timeout=WAIT)
    assert errores[0].status == 403
    page.table.set_rows([])
    assert page.table.is_empty()


def test_exportar_csv_de_cada_pagina(ctx, qtbot, api, tmp_path):
    con_sesion(ctx)
    for cls, n in ((ReabastecimientoPage, 5), (TransferenciasPage, 22), (DescuentosPage, 12)):
        page = cargada(qtbot, cls, ctx, n)
        assert page.table.export_csv(tmp_path / f"{cls.__name__}.csv") == n
        assert page.btn_csv is not None and page.btn_imprimir is not None


# --- Ronda 1 ---------------------------------------------------------------------------
def test_refresh_concurrente_gana_el_ultimo_filtro(ctx, qtbot, fake_http):
    import time

    con_sesion(ctx)
    fake_http.add("GET", "/api/v1/catalog/locations", body=LOCS)

    def ordenes(req):
        if req.params.get("estado") == "PENDIENTE":
            time.sleep(0.4)  # la respuesta vieja llega después de la nueva
            return 200, ORDENES, {}
        return 200, VACIO_ORD, {}

    fake_http.add("GET", f"{L}/replenishment/orders", body=ordenes)
    page = ReabastecimientoPage(ctx)
    qtbot.addWidget(page)
    page.refresh()  # estado PENDIENTE (lento, 5 filas)
    page.cmb_estado.setCurrentIndex(page.cmb_estado.findData("RECHAZADA"))  # dispara el segundo refresh (0 filas)
    qtbot.waitUntil(lambda: ctx.pending == 0, timeout=WAIT)
    QApplication.processEvents()
    assert page.table.rows() == [] and "0 de 0" in page.status_label.text()


def test_barra_de_botones_no_trunca_texto(ctx, qtbot, api):
    con_sesion(ctx)
    page = ReabastecimientoPage(ctx)
    qtbot.addWidget(page)
    for b in (page.btn_ciclo, page.btn_generar, page.btn_aprobar, page.btn_rechazar, page.btn_contexto):
        assert b.minimumWidth() >= b.sizeHint().width()
    assert page.detail.maximumHeight() <= 120


def test_descuentos_estado_y_lote_junto_a_producto(ctx, qtbot, api):
    page = DescuentosPage(ctx)
    qtbot.addWidget(page)
    cabeceras = [page.table.model.horizontalHeaderItem(i).text() for i in range(4)]
    assert cabeceras == ["Producto", "Tienda", "Estado", "Lote"]
