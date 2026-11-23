"""Órdenes de compra (solo buyer): lista, detalle, nueva OC, PDF, CSV y envío por correo."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ...core.xml_codec import as_list, num
from ..widgets import DataTable, button, confirm, ask_text, secondary_label
from .base import BasePage

try:  # QtPdf puede no estar instalado: sin él se abre el PDF con la aplicación del sistema
    from PySide6.QtPdf import QPdfDocument
    QPDF_DISPONIBLE = True
except ImportError:  # pragma: no cover
    QPdfDocument = None
    QPDF_DISPONIBLE = False

_RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RUTA_OC = "/api/v1/planning/purchase-orders"
CSV_COLUMNAS = ["Folio", "Proveedor", "Estado", "Fecha de creación", "Entrega estimada", "Total OC", "SKU", "Producto",
                "Tienda destino", "Cantidad (lotes)", "Unidades por lote", "Cantidad (unidades)",
                "Precio unitario", "Subtotal"]


def filas_csv_orden(orden: dict) -> list[list]:
    """Una fila por línea de la orden (o una sola con las columnas de línea vacías)."""
    cab = [orden.get("folio", ""), orden.get("proveedor", ""), orden.get("estado", ""),
           orden.get("fecha_creacion", ""), orden.get("fecha_entrega_estimada", ""), orden.get("total", "")]
    lineas = [l for l in as_list(orden.get("lineas")) if isinstance(l, dict)]
    if not lineas:
        return [cab + [""] * 8]
    return [cab + [l.get("id_sku", ""), l.get("producto", ""), l.get("locacion_destino", ""),
                   l.get("cantidad_lotes", ""), l.get("unidades_por_lote", ""), l.get("cantidad_unidades", ""),
                   l.get("precio_unitario", ""), l.get("subtotal", "")] for l in lineas]


# --------------------------------------------------------------------------- Nueva OC
class NuevaOCDialog(QDialog):
    """Elige proveedor, carga su catálogo (producto × tienda) y captura los lotes a pedir."""

    def __init__(self, ctx, proveedores: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Nueva orden de compra")
        self.resize(900, 520)
        self._filas: list[dict] = []
        self._proveedor_actual: int | None = None

        self.combo_proveedor = QComboBox()
        self.combo_proveedor.addItem("Selecciona un proveedor…", None)
        for p in proveedores:
            texto = f"{p.get('razon_social', '')} (lead time {p.get('lead_time_dias', '?')} d, MOQ {num(p.get('moq')):,.0f})"
            self.combo_proveedor.addItem(texto, int(num(p.get("id_proveedor"))))
        self.combo_proveedor.currentIndexChanged.connect(self._proveedor_cambio)
        self.observaciones = QLineEdit()
        self.observaciones.setPlaceholderText("Observaciones (opcional)")
        form = QFormLayout()
        form.addRow("Proveedor", self.combo_proveedor)
        form.addRow("Observaciones", self.observaciones)

        self.tabla = QTableWidget(0, 7)
        self.tabla.setHorizontalHeaderLabels(["Producto", "Tienda destino", "Necesidad neta", "Sugerido (lotes)",
                                              "Lotes a pedir", "Unidades/lote", "Subtotal"])
        self.tabla.verticalHeader().hide()
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.horizontalHeader().setStretchLastSection(True)
        self.estado_label = secondary_label("Elige un proveedor para ver su catálogo.")
        self.total_label = QLabel("Total estimado: $0.00")
        self.btn_sugerencias = button("Usar sugerencias", self.usar_sugerencias,
                                      tooltip="Rellena los lotes con la sugerencia del Newsvendor")
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Crear orden")
        botones.button(QDialogButtonBox.StandardButton.Ok).setProperty("variant", "primary")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        pie = QHBoxLayout()
        pie.addWidget(self.btn_sugerencias)
        pie.addWidget(self.total_label)
        pie.addStretch(1)
        pie.addWidget(botones)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.estado_label)
        lay.addWidget(self.tabla, 1)
        lay.addLayout(pie)

    # ---- catálogo
    def _proveedor_cambio(self, _i: int) -> None:
        id_prov = self.combo_proveedor.currentData()
        self._proveedor_actual = id_prov
        self._limpiar()
        if id_prov is None:
            self.estado_label.setText("Elige un proveedor para ver su catálogo.")
            return
        self.estado_label.setText("Cargando catálogo…")
        self.ctx.run(self._pedir_catalogo, id_prov, on_ok=self._catalogo, on_error=self._error)

    def _pedir_catalogo(self, id_prov: int) -> tuple[int, dict]:
        datos = self.ctx.api.call("planning", "GET", f"/api/v1/planning/procurement/suppliers/{id_prov}/catalog",
                                  expect_root="supplier_procurement_catalog")
        return id_prov, datos

    def _error(self, exc: BaseException) -> None:
        self.estado_label.setText("No se pudo cargar el catálogo.")
        self.ctx.show_error(exc, self)

    def _limpiar(self) -> None:
        self._filas = []
        self.tabla.setRowCount(0)
        self._recalcular()

    def _catalogo(self, resultado: tuple[int, dict]) -> None:
        id_prov, datos = resultado
        if id_prov != self._proveedor_actual:  # respuesta de un proveedor ya descartado
            return
        self._limpiar()
        for prod in as_list(_dict(datos).get("productos")):
            prod = _dict(prod)
            for t in as_list(prod.get("tiendas")):
                t = _dict(t)
                self._agregar_fila(prod, t)
        self.estado_label.setText(f"{len(self._filas)} combinaciones producto-tienda. "
                                  "Captura los lotes a pedir (0 = no pedir).")
        self._recalcular()

    def _agregar_fila(self, prod: dict, tienda: dict) -> None:
        costo_lote = num(prod.get("costo_por_lote"))
        info = {"id_sku": int(num(prod.get("id_sku"))), "id_locacion_destino": int(num(tienda.get("id_locacion"))),
                "costo_lote": costo_lote, "sugeridos": int(num(tienda.get("lotes_sugeridos")))}
        self._filas.append(info)
        r = self.tabla.rowCount()
        self.tabla.insertRow(r)
        textos = [prod.get("nombre", ""), tienda.get("locacion", ""), f"{num(tienda.get('necesidad_neta')):,.2f}",
                  str(info["sugeridos"]), None, f"{num(prod.get('moq_lote')):,.0f}", "$0.00"]
        for c, t in enumerate(textos):
            if t is not None:
                it = QTableWidgetItem(t)
                if c >= 2:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 0 and tienda.get("advertencias"):
                    it.setToolTip("\n".join(str(a) for a in as_list(tienda.get("advertencias"))))
                self.tabla.setItem(r, c, it)
        spin = QSpinBox()
        spin.setRange(0, 9999)
        spin.valueChanged.connect(lambda _v: self._recalcular())
        self.tabla.setCellWidget(r, 4, spin)

    def spin_en(self, fila: int) -> QSpinBox:
        return self.tabla.cellWidget(fila, 4)

    def usar_sugerencias(self) -> None:
        for i, f in enumerate(self._filas):
            self.spin_en(i).setValue(f["sugeridos"])

    def _recalcular(self) -> None:
        total = 0.0
        for i, f in enumerate(self._filas):
            sub = self.spin_en(i).value() * f["costo_lote"]
            total += sub
            item = self.tabla.item(i, 6)
            if item is not None:
                item.setText(f"${sub:,.2f}")
        self.total_label.setText(f"Total estimado: ${total:,.2f}")

    # ---- resultado
    def lineas(self) -> list[dict]:
        salida = []
        for i, f in enumerate(self._filas):
            lotes = self.spin_en(i).value()
            if lotes > 0:
                salida.append({"id_sku": f["id_sku"], "id_locacion_destino": f["id_locacion_destino"],
                               "cantidad_lotes": lotes})
        return salida

    def cuerpo(self) -> dict:
        cuerpo: dict = {"id_proveedor": self._proveedor_actual, "lineas": self.lineas()}
        if self.observaciones.text().strip():
            cuerpo["observaciones"] = self.observaciones.text().strip()
        return cuerpo

    def accept(self) -> None:
        if self._proveedor_actual is None:
            QMessageBox.warning(self, "Nueva orden de compra", "Selecciona un proveedor.")
            return
        if not self.lineas():
            QMessageBox.warning(self, "Nueva orden de compra", "Asigna al menos 1 lote en alguna tienda.")
            return
        super().accept()


def _dict(v) -> dict:
    return v if isinstance(v, dict) else {}


# --------------------------------------------------------------------------- Página
class OrdenesCompraPage(BasePage):
    title = "Órdenes de compra"
    subtitle = "Órdenes emitidas a proveedores: crea, descarga o imprime el PDF, exporta y envía por correo"
    icon = "SP_FileIcon"
    roles = ("buyer",)

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self._dialogo: NuevaOCDialog | None = None
        self._detalle_id = ""
        self.btn_actualizar = self.actions.add_button("Actualizar", self.refresh, icon="SP_BrowserReload")
        self.btn_nueva = self.actions.add_button("Nueva OC…", self.nueva_oc, variant="primary", icon="SP_FileDialogNewFolder")
        self.btn_pdf = self.actions.add_button("Descargar PDF", self.descargar_pdf, icon="SP_ArrowDown")
        self.btn_imprimir = self.actions.add_button("Imprimir PDF", self.imprimir_pdf, icon="SP_FileDialogDetailedView")
        self.btn_csv = self.actions.add_button("Exportar CSV", self.exportar_csv, icon="SP_DialogSaveButton")
        self.btn_correo = self.actions.add_button("Enviar por correo", self.enviar_correo, icon="SP_DialogYesButton")

        self.table = DataTable(empty_text="Sin órdenes de compra. Crea una con «Nueva OC…».",
                               title="Órdenes de compra")
        self.table.set_columns([
            ("folio", "Folio"), ("proveedor", "Proveedor"), ("estado", "Estado", "status"),
            ("total_lotes", "Lotes", "int"), ("total_unidades", "Unidades", "num"), ("total", "Total", "money"),
            ("n_tiendas", "Tiendas", "int"), ("fecha_entrega_estimada", "Entrega estimada"),
            ("estado_envio_correo", "Correo"), ("comprador", "Comprador"), ("fecha_creacion", "Creada"),
        ])
        self.table.selection_changed.connect(self._seleccion)
        self.table.activated.connect(lambda _fila: self._seleccion())
        self.detalle_label = secondary_label("Selecciona una orden para ver sus líneas.")
        self.table_lineas = DataTable(empty_text="Sin líneas que mostrar.", title="Líneas de la orden", filterable=False)
        self.table_lineas.set_columns([
            ("producto", "Producto"), ("locacion_destino", "Tienda destino"), ("cantidad_lotes", "Lotes", "int"),
            ("unidades_por_lote", "Unid./lote", "num"), ("cantidad_unidades", "Unidades", "num"),
            ("cantidad_recibida", "Recibido", "num"), ("precio_unitario", "Precio", "money"),
            ("subtotal", "Subtotal", "money"),
        ])
        self.body.addWidget(self.table, 3)
        self.body.addWidget(self.detalle_label)
        self.body.addWidget(self.table_lineas, 2)
        self._actualizar_botones()

    # ---- lista y detalle
    def refresh(self) -> None:
        self.ctx.run(self._listar, on_ok=self._mostrar_lista, busy=self.btn_actualizar)

    def _listar(self) -> dict:
        return self.ctx.api.call("planning", "GET", RUTA_OC, expect_root="purchase_orders_list")

    def _mostrar_lista(self, datos) -> None:
        ordenes = [o for o in as_list(_dict(datos).get("ordenes")) if isinstance(o, dict)]
        self.table.set_rows(ordenes)
        self._detalle_id = ""
        self.table_lineas.set_rows([])
        self.detalle_label.setText("Selecciona una orden para ver sus líneas.")
        self._actualizar_botones()

    def _actualizar_botones(self) -> None:
        n = len(self.table.selected_rows())
        for b in (self.btn_pdf, self.btn_imprimir, self.btn_correo):
            b.setEnabled(n == 1)
        self.btn_csv.setEnabled(n >= 1)

    def _seleccion(self) -> None:
        self._actualizar_botones()
        fila = self.table.selected_row()
        if fila is None or len(self.table.selected_rows()) != 1:
            return
        id_oc = str(fila.get("id_oc", ""))
        self._detalle_id = id_oc
        self.ctx.run(self._detalle, id_oc, on_ok=self._mostrar_detalle)

    def _detalle(self, id_oc: str) -> dict:
        return self.ctx.api.call("planning", "GET", f"{RUTA_OC}/{id_oc}", expect_root="purchase_order")

    def _mostrar_detalle(self, orden) -> None:
        orden = _dict(orden)
        if str(orden.get("id_oc", "")) != self._detalle_id:
            return
        self.table_lineas.set_rows([l for l in as_list(orden.get("lineas")) if isinstance(l, dict)])
        self.detalle_label.setText(
            f"{orden.get('folio', '')} · {orden.get('proveedor', '')} · {orden.get('estado', '')} · "
            f"total ${num(orden.get('total')):,.2f} · contacto {orden.get('contacto_email', '') or 'sin correo'}")

    def _una(self) -> dict | None:
        filas = self.table.selected_rows()
        if len(filas) != 1:
            self.ctx.notify("Selecciona una sola orden.")
            return None
        return filas[0]

    # ---- nueva OC
    def nueva_oc(self) -> None:
        self.ctx.run(self._proveedores, on_ok=self._abrir_dialogo, busy=self.btn_nueva)

    def _proveedores(self) -> dict:
        return self.ctx.api.call("planning", "GET", "/api/v1/planning/procurement/suppliers",
                                 expect_root="procurement_suppliers")

    def _abrir_dialogo(self, datos) -> None:
        provs = [p for p in as_list(_dict(datos).get("proveedores")) if isinstance(p, dict)]
        dlg = NuevaOCDialog(self.ctx, provs, self)
        dlg.accepted.connect(lambda: self._crear(dlg.cuerpo()))
        dlg.finished.connect(lambda _r: setattr(self, "_dialogo", None))
        self._dialogo = dlg
        dlg.open()

    def _crear(self, cuerpo: dict) -> None:
        self.ctx.run(self._post_crear, cuerpo, on_ok=self._creada)

    def _post_crear(self, cuerpo: dict) -> dict:
        return self.ctx.api.call("planning", "POST", RUTA_OC, body=cuerpo, body_root="purchase_order_request",
                                 expect_root="purchase_order")

    def _creada(self, orden) -> None:
        orden = _dict(orden)
        folio = orden.get("folio", "")
        self.ctx.log.record("CREAR_OC", f"Orden de compra {folio} creada (proveedor {orden.get('proveedor', '')}, "
                                        f"total ${num(orden.get('total')):,.2f})")
        self.ctx.notify(f"Orden {folio} creada")
        self.refresh()

    # ---- PDF
    def descargar_pdf(self) -> None:
        fila = self._una()
        if fila:
            self.ctx.run(self._pdf, fila, {"download": "1"}, on_ok=self._guardar_pdf)

    def imprimir_pdf(self) -> None:
        fila = self._una()
        if fila:
            self.ctx.run(self._pdf, fila, None, on_ok=self._imprimir)

    def _pdf(self, fila: dict, params) -> tuple[str, str, bytes]:
        datos = self.ctx.api.get_bytes("planning", f"{RUTA_OC}/{fila['id_oc']}/pdf", params)
        return str(fila.get("folio", "orden")), str(fila.get("id_oc", "")), datos

    def _guardar_pdf(self, resultado: tuple[str, str, bytes]) -> None:
        folio, _id, datos = resultado
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar PDF de la orden", f"{folio}.pdf", "PDF (*.pdf)")
        if not ruta:
            return
        try:
            Path(ruta).write_bytes(datos)
        except OSError as exc:
            QMessageBox.warning(self, "Descargar PDF", f"No se pudo guardar el archivo:\n{exc}")
            return
        self.ctx.log.record("DESCARGAR_PDF_OC", f"PDF de la orden {folio} guardado en {ruta}")
        QMessageBox.information(self, "Descargar PDF", f"PDF guardado en:\n{ruta}")

    def _imprimir(self, resultado: tuple[str, str, bytes]) -> None:
        folio, _id, datos = resultado
        carpeta = self.ctx.settings.data_dir / "tmp"
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = carpeta / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', folio)}.pdf"
        ruta.write_bytes(datos)
        if QPDF_DISPONIBLE:
            if not self._imprimir_con_qpdf(ruta):
                return
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(ruta)))
        self.ctx.log.record("IMPRIMIR_PDF_OC", f"PDF de la orden {folio} enviado a impresión")

    def _imprimir_con_qpdf(self, ruta: Path) -> bool:
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("Imprimir orden de compra")
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return False
        doc = QPdfDocument(self)
        doc.load(str(ruta))
        painter = QPainter(printer)
        try:
            for i in range(doc.pageCount()):
                if i:
                    printer.newPage()
                area, punto = painter.viewport(), doc.pagePointSize(i)
                escala = min(area.width() / punto.width(), area.height() / punto.height())
                painter.drawImage(0, 0, doc.render(i, QSize(int(punto.width() * escala), int(punto.height() * escala))))
        finally:
            painter.end()
        return True

    # ---- CSV
    def exportar_csv(self) -> None:
        filas = self.table.selected_rows()
        if not filas:
            self.ctx.notify("Selecciona una o más órdenes para exportar.")
            return
        self.ctx.run(self._detalles, filas, on_ok=self._guardar_csv)

    def _detalles(self, filas: list[dict]) -> list[dict]:
        return [self.ctx.api.call("planning", "GET", f"{RUTA_OC}/{f['id_oc']}", expect_root="purchase_order")
                for f in filas]

    def _guardar_csv(self, ordenes: list[dict]) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar órdenes a CSV", "ordenes_compra.csv", "CSV (*.csv)")
        if not ruta:
            return
        try:
            with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(CSV_COLUMNAS)
                for o in ordenes:
                    w.writerows(filas_csv_orden(_dict(o)))
        except OSError as exc:
            QMessageBox.warning(self, "Exportar CSV", f"No se pudo guardar el archivo:\n{exc}")
            return
        self.ctx.log.record("EXPORTAR_CSV_OC", f"{len(ordenes)} orden(es) exportadas a {ruta}")
        QMessageBox.information(self, "Exportar CSV", f"Se exportaron {len(ordenes)} orden(es) a:\n{ruta}")

    # ---- correo
    def enviar_correo(self) -> None:
        fila = self._una()
        if not fila:
            return
        folio, sugerido = fila.get("folio", ""), fila.get("contacto_email") or ""
        etiqueta = f"Correo del destinatario para la orden {folio}" + (f" (contacto del proveedor: {sugerido})" if sugerido else "")
        correo = ask_text(self, "Enviar por correo", etiqueta)
        if not correo:
            return
        if not _RE_CORREO.match(correo):
            QMessageBox.warning(self, "Enviar por correo", "Ingresa un correo electrónico válido.")
            return
        if not confirm(self, f"¿Enviar la orden {folio} con su PDF a {correo}?", "Enviar por correo"):
            return
        self.ctx.run(self._post_correo, fila["id_oc"], correo, on_ok=self._enviada)

    def _post_correo(self, id_oc: str, correo: str) -> dict:
        return self.ctx.api.call("planning", "POST", f"{RUTA_OC}/{id_oc}/send-email", body={"correo": correo},
                                 body_root="send_email_request", expect_root="send_email_result")

    def _enviada(self, res) -> None:
        res = _dict(res)
        self.ctx.log.record("ENVIAR_CORREO_OC", f"Orden {res.get('folio', '')} enviada a {res.get('correo_envio', '')} "
                                                f"({res.get('estado_envio_correo', '')})")
        self.ctx.notify(f"Orden {res.get('folio', '')}: {res.get('estado_envio_correo', 'enviada')}")
        self.refresh()
