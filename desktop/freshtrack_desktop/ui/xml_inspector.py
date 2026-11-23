"""
Inspector XML: los últimos 50 intercambios HTTP (petición y respuesta) con indentación.

Se suscribe a `api.listeners`. Esos listeners corren en el hilo de la petición, así que
solo emiten una señal; la conexión encolada lleva el Exchange al hilo de UI.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

from lxml import etree
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QSplitter,
    QTabWidget, QVBoxLayout, QWidget,
)

from ..core.api_client import Exchange
from .widgets import button, secondary_label

MAX_EXCHANGES = 50


def pretty_xml(texto: str) -> str:
    """Indenta XML sin resolver entidades ni ir a la red; si no es XML lo deja igual."""
    if not texto or not texto.lstrip().startswith("<"):
        return texto or ""
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=True,
                                 load_dtd=False)
        raiz = etree.fromstring(texto.encode("utf-8"), parser)
        return etree.tostring(raiz, pretty_print=True, encoding="unicode").rstrip()
    except (etree.XMLSyntaxError, ValueError):
        return texto


class XmlInspector(QDockWidget):
    exchange_received = Signal(object)

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__("Inspector XML", parent)
        self.setObjectName("XmlInspector")
        self.ctx = ctx
        self._exchanges: deque[Exchange] = deque(maxlen=MAX_EXCHANGES)

        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.list = QListWidget()
        self.list.setFont(mono)
        self.list.currentRowChanged.connect(self._mostrar)
        self.header_label = secondary_label("Sin intercambios todavía")
        self.header_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.request_view = QPlainTextEdit(readOnly=True)
        self.response_view = QPlainTextEdit(readOnly=True)
        for v in (self.request_view, self.response_view):
            v.setFont(mono)
            v.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.response_view, "Respuesta")
        self.tabs.addTab(self.request_view, "Petición")

        detalle = QWidget()
        dl = QVBoxLayout(detalle)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self.header_label)
        dl.addWidget(self.tabs, 1)
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.list)
        split.addWidget(detalle)
        split.setSizes([160, 400])

        barra = QHBoxLayout()
        barra.addWidget(QLabel(f"Últimos {MAX_EXCHANGES} intercambios"))
        barra.addStretch(1)
        barra.addWidget(button("Copiar", self._copiar, icon="SP_FileDialogContentsView"))
        barra.addWidget(button("Limpiar", self.clear, icon="SP_DialogResetButton"))

        cont = QWidget()
        lay = QVBoxLayout(cont)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addLayout(barra)
        lay.addWidget(split, 1)
        self.setWidget(cont)
        self.setMinimumWidth(380)

        self.exchange_received.connect(self.add_exchange, Qt.ConnectionType.QueuedConnection)
        self._listener = self.exchange_received.emit  # se llama en hilos de trabajo
        ctx.api.listeners.append(self._listener)

    @property
    def exchanges(self) -> list[Exchange]:
        """Intercambios guardados, el más reciente primero."""
        return list(reversed(self._exchanges))

    def detach(self) -> None:
        try:
            self.ctx.api.listeners.remove(self._listener)
        except ValueError:
            pass

    def add_exchange(self, ex: Exchange) -> None:
        seguir_ultimo = self.list.currentRow() <= 0
        self._exchanges.append(ex)
        ruta = ex.url.split("://", 1)[-1]
        ruta = ruta[ruta.find("/"):] if "/" in ruta else ruta
        estado = ex.status if ex.status else "---"
        item = QListWidgetItem(f"{datetime.now():%H:%M:%S}  {ex.method:<6} {estado}  {ruta}  ({ex.elapsed_ms:.0f} ms)")
        item.setToolTip(f"{ex.url}\ncorrelation_id: {ex.correlation_id}")
        self.list.insertItem(0, item)
        while self.list.count() > MAX_EXCHANGES:
            self.list.takeItem(self.list.count() - 1)
        if seguir_ultimo:
            self.list.setCurrentRow(0)

    def _mostrar(self, fila: int) -> None:
        exs = self.exchanges
        if fila < 0 or fila >= len(exs):
            self.header_label.setText("Sin intercambios todavía")
            self.request_view.clear()
            self.response_view.clear()
            return
        ex = exs[fila]
        estado = f"HTTP {ex.status}" if ex.status else "sin respuesta (servicio no disponible)"
        self.header_label.setText(f"{ex.method} {ex.url}\n{estado} · {ex.elapsed_ms:.0f} ms · "
                                  f"correlation_id: {ex.correlation_id}")
        self.request_view.setPlainText(pretty_xml(ex.request_xml) or "(sin cuerpo)")
        self.response_view.setPlainText(pretty_xml(ex.response_text) or "(sin cuerpo)")

    def clear(self) -> None:
        self._exchanges.clear()
        self.list.clear()
        self._mostrar(-1)

    def _copiar(self) -> None:
        vista = self.tabs.currentWidget()
        if isinstance(vista, QPlainTextEdit):
            QApplication.clipboard().setText(vista.toPlainText())
