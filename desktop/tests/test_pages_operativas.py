"""Pruebas de las páginas operativas: Mermas y desperdicio, Órdenes de compra e Importar ventas."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from freshtrack_desktop.core.activity_log import ActivityLog
from freshtrack_desktop.core.api_client import ApiClient
from freshtrack_desktop.core.session import Session
from freshtrack_desktop.core.xml_codec import parse_xml, validate
from freshtrack_desktop.ui.context import AppContext

WAIT = 3000
SAMPLES = Path(__file__).resolve().parent / "fixtures" / "xml"


def muestra(nombre: str) -> bytes:
    return (SAMPLES / f"{nombre}.xml").read_bytes()


def _ctx(settings, rol):
    api = ApiClient(settings)
    api.session = Session(token="tok", jti="j", usuario={"rol": rol, "email": f"{rol}@freshtrack.mx"})
    log = ActivityLog(settings.data_dir / "actividad.log")
    return AppContext(settings, api, log)


@pytest.fixture
def ctx(settings, qtbot):
    c = _ctx(settings, "buyer")
    yield c
    c.pool.waitForDone(WAIT)
    QApplication.processEvents()
    c.log.close()


def acciones(ctx) -> list[str]:
    return [e["accion"] for e in ctx.log.tail(50)]


# --------------------------------------------------------------------------- roles y títulos
def test_clases_conservan_titulo_y_roles():
    from freshtrack_desktop.ui.pages._stubs import ImportarVentasPage as S3, MermasPage as S1, OrdenesCompraPage as S2
    from freshtrack_desktop.ui.pages.importar_ventas import ImportarVentasPage
    from freshtrack_desktop.ui.pages.mermas import MermasPage
    from freshtrack_desktop.ui.pages.ordenes_compra import OrdenesCompraPage

    for real, stub in ((MermasPage, S1), (OrdenesCompraPage, S2), (ImportarVentasPage, S3)):
        assert (real.title, real.roles, real.icon) == (stub.title, stub.roles, stub.icon)
    planner = Session(token="t", jti="j", usuario={"rol": "planner"})
    assert not OrdenesCompraPage.allowed_for(planner)
    assert ImportarVentasPage.allowed_for(planner) and MermasPage.allowed_for(planner)


# --------------------------------------------------------------------------- Mermas
def test_mermas_muestra_indicadores_carbono_y_triage(ctx, qtbot, fake_http, monkeypatch):
    from freshtrack_desktop.ui.pages import mermas
    from freshtrack_desktop.ui.pages.mermas import MermasPage

    fake_http.add("GET", "/api/v1/alerts/waste-measurement", body=muestra("waste"))
    fake_http.add("GET", "/api/v1/alerts/esg/carbon-avoided", body=muestra("carbon"))
    fake_http.add("GET", "/api/v1/planning/triage", body=muestra("triage"))
    page = MermasPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    qtbot.waitUntil(lambda: not page.table_triage.is_empty(), timeout=WAIT)
    nombres = [r["indicador"] for r in page.table_indicadores.rows()]
    assert len(nombres) == 6
    assert page.kpi_riesgo.value_label.text() == "688.39"
    assert page.kpi_proyectado.value_label.text() == "86.39"
    assert page.kpi_co2e.value_label.text().startswith("0")
    assert "1.37" in page.kpi_reduccion.value_label.text()
    assert len(page.table_triage.rows()) == 37
    serie = page.chart_view.chart().series()[0]
    assert serie.barSets()[0].count() == 4
    assert page.chart_view.chart().series()[0].barSets()[0].at(0) == pytest.approx(688.39)

    # exportar e imprimir quedan en la bitácora
    destino = ctx.settings.data_dir / "mermas.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    page.exportar()
    assert destino.exists() and "Producto en riesgo" in destino.read_text(encoding="utf-8-sig")
    monkeypatch.setattr(type(page.table_indicadores), "print_table", lambda self, *a, **k: True)
    page.imprimir()
    assert "EXPORTAR_REPORTE_MERMAS" in acciones(ctx) and "IMPRIMIR_REPORTE_MERMAS" in acciones(ctx)


# --------------------------------------------------------------------------- Importar ventas
CSV_MIXTO = (
    "folio_externo,id_locacion,id_sku,cantidad,canal\n"
    "A-1,3,1,2,TIENDA\n"
    "A-1,3,2,1.5,\n"
    ",3,1,1,\n"            # sin folio
    "A-2,3,x,1,\n"         # sku inválido
    "A-3,3,1,0,\n"         # cantidad 0
    "A-4,3,1,1,PERSONAL\n"  # canal inválido
    "A-5,0,1,1,\n"         # locación inválida
    "A-6,4,5,3,ONLINE\n"
)


def test_parseo_csv_reporta_errores_por_fila_y_no_los_incluye(tmp_path):
    from freshtrack_desktop.ui.pages.importar_ventas import parsear_csv

    p = tmp_path / "v.csv"
    p.write_text(CSV_MIXTO, encoding="utf-8")
    filas, tickets = parsear_csv(p)
    assert len(filas) == 8
    estados = [f["estado"] for f in filas]
    assert estados == ["OK", "OK", "ERROR", "ERROR", "ERROR", "ERROR", "ERROR", "OK"]
    assert "folio" in filas[2]["mensaje"].lower()
    assert [t["folio_externo"] for t in tickets] == ["A-1", "A-6"]
    assert len(tickets[0]["lineas"]) == 2 and tickets[0]["canal"] == "TIENDA"
    assert tickets[1]["id_locacion"] == 4 and tickets[1]["canal"] == "ONLINE"


def test_parseo_csv_exige_columnas(tmp_path):
    from freshtrack_desktop.ui.pages.importar_ventas import parsear_csv

    p = tmp_path / "v.csv"
    p.write_text("folio,sku\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="columnas"):
        parsear_csv(p)


def test_xml_de_importacion_valida_contra_el_xsd():
    from freshtrack_desktop.ui.pages.importar_ventas import construir_xml

    xml = construir_xml(3, [
        {"folio_externo": "A-1", "canal": "ONLINE", "lineas": [{"id_sku": 1, "cantidad": "2"}, {"id_sku": 2, "cantidad": "1.5"}]},
        {"folio_externo": "A-2", "canal": "", "lineas": [{"id_sku": 1, "cantidad": "1"}]},
    ])
    validate(xml, "sales_import_request")
    raiz, datos = parse_xml(xml)
    assert raiz == "sales_import_request" and datos["id_locacion"] == "3"
    assert "<canal>" not in xml.decode().split("A-2")[1].split("</ticket>")[0]


def _resultado(*items, imp=0, dup=0, err=0) -> bytes:
    cuerpo = "".join(items)
    return (f"<?xml version='1.0'?><sales_import_result><importados>{imp}</importados><duplicados>{dup}</duplicados>"
            f"<errores>{err}</errores><resultados>{cuerpo}</resultados></sales_import_result>").encode()


def test_importar_envia_xml_y_muestra_duplicado(ctx, qtbot, fake_http, tmp_path, monkeypatch):
    from freshtrack_desktop.ui.pages import importar_ventas
    from freshtrack_desktop.ui.pages.importar_ventas import ImportarVentasPage

    monkeypatch.setattr(importar_ventas, "confirm", lambda *a, **k: True)
    fake_http.add("POST", "/api/v1/commercial/sales/import", body=_resultado(
        "<item><folio_externo>A-1</folio_externo><estado>IMPORTADO</estado><id_venta>10</id_venta><folio>V-0010</folio></item>",
        "<item><folio_externo>A-6</folio_externo><estado>DUPLICADO</estado></item>", imp=1, dup=1))
    p = tmp_path / "v.csv"
    p.write_text(CSV_MIXTO, encoding="utf-8")
    page = ImportarVentasPage(ctx)
    qtbot.addWidget(page)
    page.cargar_csv(p)
    assert len(page.table_vista.rows()) == 8
    assert page.btn_importar.isEnabled()
    page.importar()
    qtbot.waitUntil(lambda: not page.table_resultados.is_empty(), timeout=WAIT)
    estados = {r["folio_externo"]: r["estado"] for r in page.table_resultados.rows()}
    assert estados == {"A-1": "IMPORTADO", "A-6": "DUPLICADO"}
    # una petición por tienda (3 y 4); las filas con error no viajan
    posts = fake_http.calls_to("POST", "/api/v1/commercial/sales/import")
    assert len(posts) == 2
    assert all(c.headers["Content-Type"].startswith("application/xml") for c in posts)
    cuerpos = "".join(c.text for c in posts)
    assert "A-2" not in cuerpos and "A-5" not in cuerpos and "A-1" in cuerpos and "A-6" in cuerpos
    for c in posts:
        validate(c.body, "sales_import_request")
    assert "IMPORTAR_VENTAS" in acciones(ctx)


def test_importar_divide_en_bloques_de_500(ctx, qtbot, fake_http, tmp_path, monkeypatch):
    from freshtrack_desktop.ui.pages import importar_ventas
    from freshtrack_desktop.ui.pages.importar_ventas import ImportarVentasPage

    monkeypatch.setattr(importar_ventas, "confirm", lambda *a, **k: True)
    fake_http.add("POST", "/api/v1/commercial/sales/import", body=_resultado(imp=0))
    p = tmp_path / "v.csv"
    p.write_text("folio_externo,id_locacion,id_sku,cantidad\n" + "".join(f"F-{i},3,1,1\n" for i in range(1001)),
                 encoding="utf-8")
    page = ImportarVentasPage(ctx)
    qtbot.addWidget(page)
    page.cargar_csv(p)
    page.importar()
    qtbot.waitUntil(lambda: len(fake_http.calls_to("POST", "/api/v1/commercial/sales/import")) == 3, timeout=WAIT)
    tamanos = [c.text.count("<ticket>") for c in fake_http.calls_to("POST", "/api/v1/commercial/sales/import")]
    assert tamanos == [500, 500, 1]


def test_plantilla_csv_se_guarda(ctx, qtbot, tmp_path, monkeypatch):
    from freshtrack_desktop.ui.pages import importar_ventas
    from freshtrack_desktop.ui.pages.importar_ventas import ImportarVentasPage, parsear_csv

    destino = tmp_path / "plantilla.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
    monkeypatch.setattr(importar_ventas.QMessageBox, "information", lambda *a, **k: None)
    page = ImportarVentasPage(ctx)
    qtbot.addWidget(page)
    page.descargar_plantilla()
    filas, tickets = parsear_csv(destino)
    assert filas and all(f["estado"] == "OK" for f in filas) and tickets


# --------------------------------------------------------------------------- Órdenes de compra
OC_ID = "11111111-2222-3333-4444-555555555555"
OC_LIST = f"""<?xml version="1.0"?><purchase_orders_list><total>1</total><ordenes><item>
<id_oc>{OC_ID}</id_oc><folio>OC-20261122-0001</folio><id_proveedor>1</id_proveedor>
<proveedor>Lácteos del Norte</proveedor><contacto_email>ventas@lacteosdelnorte.mx</contacto_email>
<estado>EMITIDA</estado><total_lotes>3</total_lotes><total_unidades>150.0</total_unidades><total>3900.0</total>
<fecha_entrega_estimada>2026-11-25</fecha_entrega_estimada><correo_envio /><estado_envio_correo />
<fecha_creacion>2026-11-22T10:00:00</fecha_creacion><comprador>Carlos Vega</comprador><n_tiendas>2</n_tiendas>
</item></ordenes></purchase_orders_list>""".encode()
OC_DETALLE = f"""<?xml version="1.0"?><purchase_order><id_oc>{OC_ID}</id_oc><folio>OC-20261122-0001</folio>
<id_proveedor>1</id_proveedor><proveedor>Lácteos del Norte</proveedor><estado>EMITIDA</estado><total>3900.0</total>
<contacto_email>ventas@lacteosdelnorte.mx</contacto_email><fecha_creacion>2026-11-22T10:00:00</fecha_creacion>
<lineas><item><id_sku>9</id_sku><producto>Crema Ácida 450g</producto><id_locacion_destino>6</id_locacion_destino>
<locacion_destino>Tienda Centro</locacion_destino><cantidad_lotes>1</cantidad_lotes><unidades_por_lote>50.0</unidades_por_lote>
<cantidad_unidades>50.0</cantidad_unidades><precio_unitario>26.0</precio_unitario><subtotal>1300.0</subtotal></item>
<item><id_sku>9</id_sku><producto>Crema Ácida 450g</producto><id_locacion_destino>4</id_locacion_destino>
<locacion_destino>Tienda Cumbres</locacion_destino><cantidad_lotes>2</cantidad_lotes><unidades_por_lote>50.0</unidades_por_lote>
<cantidad_unidades>100.0</cantidad_unidades><precio_unitario>26.0</precio_unitario><subtotal>2600.0</subtotal></item></lineas>
</purchase_order>""".encode()


def _pagina_oc(ctx, qtbot, fake_http):
    from freshtrack_desktop.ui.pages.ordenes_compra import OrdenesCompraPage

    fake_http.add("GET", "/api/v1/planning/purchase-orders", body=OC_LIST)
    fake_http.add("GET", f"/api/v1/planning/purchase-orders/{OC_ID}", body=OC_DETALLE)
    page = OrdenesCompraPage(ctx)
    qtbot.addWidget(page)
    page.refresh()
    qtbot.waitUntil(lambda: not page.table.is_empty(), timeout=WAIT)
    return page


def test_oc_lista_y_detalle_al_seleccionar(ctx, qtbot, fake_http):
    page = _pagina_oc(ctx, qtbot, fake_http)
    assert page.table.rows()[0]["folio"] == "OC-20261122-0001"
    page.table.view.selectRow(0)
    qtbot.waitUntil(lambda: len(page.table_lineas.rows()) == 2, timeout=WAIT)
    assert page.table_lineas.rows()[0]["producto"] == "Crema Ácida 450g"


def test_oc_descargar_pdf_guarda_archivo(ctx, qtbot, fake_http, tmp_path, monkeypatch):
    from freshtrack_desktop.ui.pages import ordenes_compra

    page = _pagina_oc(ctx, qtbot, fake_http)
    fake_http.add("GET", f"/api/v1/planning/purchase-orders/{OC_ID}/pdf", body=b"%PDF-1.4 demo",
                  headers={"Content-Type": "application/pdf"})
    destino = tmp_path / "oc.pdf"
    pedidos = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (pedidos.append(a) or str(destino), ""))
    monkeypatch.setattr(ordenes_compra.QMessageBox, "information", lambda *a, **k: None)
    page.table.view.selectRow(0)
    page.descargar_pdf()
    qtbot.waitUntil(lambda: destino.exists(), timeout=WAIT)
    assert destino.read_bytes() == b"%PDF-1.4 demo"
    pdf = fake_http.calls_to("GET", f"/api/v1/planning/purchase-orders/{OC_ID}/pdf")[0]
    assert pdf.headers["Accept"] == "application/pdf"
    assert "DESCARGAR_PDF_OC" in acciones(ctx)


def test_oc_imprimir_pdf_sin_qpdf_abre_con_el_sistema(ctx, qtbot, fake_http, monkeypatch):
    from freshtrack_desktop.ui.pages import ordenes_compra

    page = _pagina_oc(ctx, qtbot, fake_http)
    fake_http.add("GET", f"/api/v1/planning/purchase-orders/{OC_ID}/pdf", body=b"%PDF-1.4 demo",
                  headers={"Content-Type": "application/pdf"})
    abiertos = []
    monkeypatch.setattr(ordenes_compra, "QPDF_DISPONIBLE", False)
    monkeypatch.setattr(ordenes_compra.QDesktopServices, "openUrl", lambda url: abiertos.append(url.toLocalFile()) or True)
    page.table.view.selectRow(0)
    page.imprimir_pdf()
    qtbot.waitUntil(lambda: bool(abiertos), timeout=WAIT)
    assert abiertos[0].endswith(".pdf") and Path(abiertos[0]).read_bytes() == b"%PDF-1.4 demo"
    assert "IMPRIMIR_PDF_OC" in acciones(ctx)


def test_oc_exportar_csv_con_lineas(ctx, qtbot, fake_http, tmp_path, monkeypatch):
    from freshtrack_desktop.ui.pages import ordenes_compra

    page = _pagina_oc(ctx, qtbot, fake_http)
    destino = tmp_path / "ordenes.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
    monkeypatch.setattr(ordenes_compra.QMessageBox, "information", lambda *a, **k: None)
    page.table.view.selectRow(0)
    page.exportar_csv()
    qtbot.waitUntil(lambda: destino.exists(), timeout=WAIT)
    with open(destino, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.DictReader(fh))
    assert len(filas) == 2
    assert filas[0]["Folio"] == "OC-20261122-0001" and filas[0]["Producto"] == "Crema Ácida 450g"
    assert filas[1]["Cantidad (lotes)"] == "2" and filas[1]["Tienda destino"] == "Tienda Cumbres"
    assert "EXPORTAR_CSV_OC" in acciones(ctx)


def test_oc_enviar_correo_pide_confirmacion(ctx, qtbot, fake_http, monkeypatch):
    from freshtrack_desktop.ui.pages import ordenes_compra

    page = _pagina_oc(ctx, qtbot, fake_http)
    fake_http.add("POST", f"/api/v1/planning/purchase-orders/{OC_ID}/send-email", body=(
        f"<send_email_result><id_oc>{OC_ID}</id_oc><folio>OC-20261122-0001</folio><correo_envio>a@b.mx</correo_envio>"
        "<estado_envio_correo>ENVIADO_DEMO</estado_envio_correo><enviado_real>false</enviado_real></send_email_result>"))
    page.table.view.selectRow(0)
    monkeypatch.setattr(ordenes_compra, "ask_text", lambda *a, **k: "a@b.mx")
    monkeypatch.setattr(ordenes_compra, "confirm", lambda *a, **k: False)
    page.enviar_correo()
    QApplication.processEvents()
    assert not fake_http.calls_to("POST", f"/api/v1/planning/purchase-orders/{OC_ID}/send-email")
    monkeypatch.setattr(ordenes_compra, "confirm", lambda *a, **k: True)
    page.enviar_correo()
    qtbot.waitUntil(lambda: bool(fake_http.calls_to("POST", f"/api/v1/planning/purchase-orders/{OC_ID}/send-email")),
                    timeout=WAIT)
    envio = fake_http.calls_to("POST", f"/api/v1/planning/purchase-orders/{OC_ID}/send-email")[0]
    _, datos = parse_xml(envio.body)
    assert datos["correo"] == "a@b.mx"
    qtbot.waitUntil(lambda: "ENVIAR_CORREO_OC" in acciones(ctx), timeout=WAIT)


def test_oc_correo_invalido_no_envia(ctx, qtbot, fake_http, monkeypatch):
    from freshtrack_desktop.ui.pages import ordenes_compra

    page = _pagina_oc(ctx, qtbot, fake_http)
    page.table.view.selectRow(0)
    avisos = []
    monkeypatch.setattr(ordenes_compra, "ask_text", lambda *a, **k: "no-es-correo")
    monkeypatch.setattr(ordenes_compra, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(ordenes_compra.QMessageBox, "warning", lambda *a, **k: avisos.append(a))
    page.enviar_correo()
    assert avisos and not fake_http.calls_to("POST", f"/api/v1/planning/purchase-orders/{OC_ID}/send-email")


def test_oc_nueva_orden_arma_el_xml(ctx, qtbot, fake_http):
    from freshtrack_desktop.ui.pages.ordenes_compra import NuevaOCDialog

    fake_http.add("GET", "/api/v1/planning/procurement/suppliers", body=muestra("suppliers_proc"))
    fake_http.add("GET", "/api/v1/planning/procurement/suppliers/1/catalog", body=muestra("sup_catalog"))
    fake_http.add("POST", "/api/v1/planning/purchase-orders", status=201, body=OC_DETALLE)
    page = _pagina_oc(ctx, qtbot, fake_http)
    page.nueva_oc()
    qtbot.waitUntil(lambda: page._dialogo is not None, timeout=WAIT)
    dlg: NuevaOCDialog = page._dialogo
    qtbot.addWidget(dlg)
    qtbot.waitUntil(lambda: dlg.combo_proveedor.count() > 0, timeout=WAIT)
    idx = dlg.combo_proveedor.findData(1)
    dlg.combo_proveedor.setCurrentIndex(idx)
    qtbot.waitUntil(lambda: dlg.tabla.rowCount() > 0, timeout=WAIT)
    dlg.spin_en(0).setValue(2)
    dlg.spin_en(1).setValue(1)
    assert dlg.lineas() and sum(l["cantidad_lotes"] for l in dlg.lineas()) == 3
    dlg.observaciones.setText("Entrega matutina")
    dlg.accept()
    qtbot.waitUntil(lambda: bool(fake_http.calls_to("POST", "/api/v1/planning/purchase-orders")), timeout=WAIT)
    post = fake_http.calls_to("POST", "/api/v1/planning/purchase-orders")[0]
    raiz, datos = parse_xml(post.body)
    assert raiz == "purchase_order_request" and datos["id_proveedor"] == "1"
    assert len(datos["lineas"]) == 2 and datos["observaciones"] == "Entrega matutina"
    assert {"id_sku", "id_locacion_destino", "cantidad_lotes"} <= set(datos["lineas"][0])
    qtbot.waitUntil(lambda: "CREAR_OC" in acciones(ctx), timeout=WAIT)


def test_oc_nueva_orden_sin_lotes_no_envia(ctx, qtbot, fake_http, monkeypatch):
    from freshtrack_desktop.ui.pages import ordenes_compra

    fake_http.add("GET", "/api/v1/planning/procurement/suppliers", body=muestra("suppliers_proc"))
    fake_http.add("GET", "/api/v1/planning/procurement/suppliers/1/catalog", body=muestra("sup_catalog"))
    page = _pagina_oc(ctx, qtbot, fake_http)
    avisos = []
    monkeypatch.setattr(ordenes_compra.QMessageBox, "warning", lambda *a, **k: avisos.append(a))
    page.nueva_oc()
    qtbot.waitUntil(lambda: page._dialogo is not None, timeout=WAIT)
    dlg = page._dialogo
    qtbot.addWidget(dlg)
    qtbot.waitUntil(lambda: dlg.combo_proveedor.count() > 0, timeout=WAIT)
    dlg.combo_proveedor.setCurrentIndex(dlg.combo_proveedor.findData(1))
    qtbot.waitUntil(lambda: dlg.tabla.rowCount() > 0, timeout=WAIT)
    dlg.accept()
    assert avisos and not fake_http.calls_to("POST", "/api/v1/planning/purchase-orders")


def test_ticket_con_una_fila_invalida_se_excluye_completo(ctx, qtbot, fake_http, tmp_path, monkeypatch):
    from freshtrack_desktop.ui.pages import importar_ventas
    from freshtrack_desktop.ui.pages.importar_ventas import ImportarVentasPage, parsear_csv

    p = tmp_path / "v.csv"
    p.write_text("folio_externo,id_locacion,id_sku,cantidad\nA-1,3,1,2\nA-1,3,x,1\nA-2,3,1,1\n", encoding="utf-8")
    filas, tickets = parsear_csv(p)
    assert [t["folio_externo"] for t in tickets] == ["A-2"]
    assert filas[0]["estado"] == "ERROR" and "ticket excluido: la fila 3 tiene errores" in filas[0]["mensaje"]
    monkeypatch.setattr(importar_ventas, "confirm", lambda *a, **k: True)
    fake_http.add("POST", "/api/v1/commercial/sales/import", body=_resultado(
        "<item><folio_externo>A-2</folio_externo><estado>IMPORTADO</estado></item>", imp=1))
    page = ImportarVentasPage(ctx)
    qtbot.addWidget(page)
    page.cargar_csv(p)
    page.importar()
    qtbot.waitUntil(lambda: not page.table_resultados.is_empty(), timeout=WAIT)
    cuerpo = fake_http.calls_to("POST", "/api/v1/commercial/sales/import")[0].text
    assert "A-2" in cuerpo and "A-1" not in cuerpo


def test_error_429_detiene_el_envio_y_marca_no_enviado(ctx, qtbot, fake_http, tmp_path, monkeypatch):
    from freshtrack_desktop.ui.pages import importar_ventas
    from freshtrack_desktop.ui.pages.importar_ventas import ImportarVentasPage

    monkeypatch.setattr(importar_ventas, "confirm", lambda *a, **k: True)
    errores = []
    monkeypatch.setattr(ctx, "show_error", lambda exc, parent=None: errores.append(exc))
    fake_http.add("POST", "/api/v1/commercial/sales/import", status=429, body=(
        "<error_response><error>limite</error><mensaje>Demasiadas</mensaje><status>429</status></error_response>"))
    p = tmp_path / "v.csv"
    p.write_text("folio_externo,id_locacion,id_sku,cantidad\nA-1,3,1,1\nB-1,4,1,1\n", encoding="utf-8")
    page = ImportarVentasPage(ctx)
    qtbot.addWidget(page)
    page.cargar_csv(p)
    page.importar()
    qtbot.waitUntil(lambda: not page.table_resultados.is_empty(), timeout=WAIT)
    assert {r["estado"] for r in page.table_resultados.rows()} == {"NO ENVIADO"}
    assert len(fake_http.calls_to("POST", "/api/v1/commercial/sales/import")) == 1
    assert len(errores) == 1
