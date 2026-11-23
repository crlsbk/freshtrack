"""
Widgets comunes: DataTable, KpiCard, Toolbar, botones con variante, íconos y diálogos cortos.

DataTable::

    t = DataTable(empty_text="Sin órdenes pendientes", title="Órdenes")
    t.set_columns([("id_orden", "Orden"), ("total", "Total", "money"), ("estado", "Estado", "status")])
    t.set_rows(lista_de_dicts)

Formatos de columna (tercer elemento opcional): "int" (1,234), "num" (1,234.50),
"money" ($1,234.50), "pct" (12.3 %), "status" (texto coloreado + ícono según STATUS_TONES)
o un callable `fn(valor) -> str`. Los valores numéricos (aunque lleguen como texto del XML)
se alinean a la derecha y se ordenan como número.
"""

from __future__ import annotations

import csv
import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QStandardItem, QStandardItemModel, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMenu, QMessageBox, QPushButton, QStackedWidget, QStyle, QTableView, QVBoxLayout, QWidget,
)

from . import theme

ROW_ROLE = Qt.ItemDataRole.UserRole + 1
SORT_ROLE = Qt.ItemDataRole.UserRole + 2
_RE_NUM = re.compile(r"^-?\d+(\.\d+)?([eE][-+]?\d+)?$")

# Texto de estado → tono del tema (success / warning / danger / info).
STATUS_TONES: dict[str, str] = {
    "OK": "success", "HEALTHY": "success", "APROBADO": "success", "APROBADA": "success",
    "EJECUTADA": "success", "EJECUTADO": "success", "IMPORTADO": "success", "ACTIVO": "success",
    "DEGRADADO": "warning", "DEGRADED": "warning", "VIGILANCIA": "warning", "PENDIENTE": "warning",
    "DUPLICADO": "warning", "ADVERTENCIA": "warning",
    "CAÍDO": "danger", "CRÍTICO": "danger", "CRITICO": "danger", "ERROR": "danger",
    "RECHAZADO": "danger", "RECHAZADA": "danger", "VENCIDO": "danger",
    "INFO": "info", "ENVIADA": "info", "ENVIADO": "info", "DESCONOCIDO": "warning",
    "SUGERIDA": "info", "SUGERIDO": "info", "ANUNCIADO": "info", "EN_TRANSITO": "info",
    "APLICADO": "success", "APLICADA": "success", "RECIBIDA": "success", "RECIBIDO": "success",
    "NO_CONFIABLE": "warning", "CANCELADA": "danger", "CANCELADO": "danger",
}
_TONE_ICON = {"success": "check-circle", "warning": "alert", "danger": "x-circle", "info": "info"}

Column = tuple  # (key, header) o (key, header, fmt)


# --------------------------------------------------------------------------- utilidades
def std_icon(name: str, color: str | None = None) -> QIcon:
    """Ícono de línea moderno (ui/icons.py). Acepta nombres propios ("refresh") o los
    antiguos de QStyle ("SP_BrowserReload"); si no hay equivalente, cae al de QStyle."""
    if not name:
        return QIcon()
    from . import icons

    if icons.has(name):
        return icons.icon(name, color)
    pix = getattr(QStyle.StandardPixmap, name, None)
    app = QApplication.instance()
    if pix is None or app is None:
        return QIcon()
    return app.style().standardIcon(pix)


def as_number(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if _RE_NUM.match(s):
            try:
                return float(s)
            except ValueError:
                return None
    return None


def format_value(v: Any, fmt: str | Callable[[Any], str] | None = None) -> str:
    if callable(fmt):
        try:
            return str(fmt(v))
        except Exception:  # noqa: BLE001 - un formateador roto no debe tumbar la tabla
            return "" if v is None else str(v)
    if v is None:
        return ""
    n = as_number(v)
    if n is not None and fmt in ("int", "num", "money", "pct"):
        if fmt == "int":
            return f"{n:,.0f}"
        if fmt == "num":
            return f"{n:,.2f}"
        if fmt == "money":
            return f"-${abs(n):,.2f}" if n < 0 else f"${n:,.2f}"
        return f"{n:.1f} %"
    if isinstance(v, bool):
        return "Sí" if v else "No"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    if isinstance(v, str) and _RE_ISO_DT.match(v):
        return format_datetime(v)
    return str(v)


_RE_ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")


def format_datetime(v: str) -> str:
    """'2026-11-23T05:44:38.23+00:00' → '2026-11-22 23:44' en la hora local del equipo."""
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return v
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


def button(text: str, slot: Callable | None = None, *, variant: str = "", icon: str = "",
           tooltip: str = "", shortcut: str | None = None) -> QPushButton:
    """QPushButton con variante de estilo: "primary", "danger", "link" o "" (normal)."""
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if icon:
        on_color = theme.tokens()["on_primary"] if variant == "primary" else (
            theme.tokens()["on_danger"] if variant == "danger" else None)
        b.setIcon(std_icon(icon, on_color))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        b.setToolTip(tooltip)
    if shortcut:
        b.setShortcut(QKeySequence(shortcut))
    if slot is not None:
        b.clicked.connect(lambda _checked=False: slot())
    return b


def secondary_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "secondary")
    lbl.setWordWrap(True)
    return lbl


def set_tone(label: QLabel, tone: str | None) -> None:
    label.setProperty("tone", tone or "")
    theme.repolish(label)


class Toolbar(QHBoxLayout):
    """Fila de acciones (QHBoxLayout) con atajos para agregar botones."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(8)

    def add_button(self, text: str, slot: Callable | None = None, *, variant: str = "", icon: str = "",
                   tooltip: str = "", shortcut: str | None = None) -> QPushButton:
        b = button(text, slot, variant=variant, icon=icon, tooltip=tooltip, shortcut=shortcut)
        self.addWidget(b)
        return b

    def add_widget(self, w: QWidget, stretch: int = 0) -> QWidget:
        self.addWidget(w, stretch)
        return w

    def add_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        self.addWidget(lbl)
        return lbl

    def add_stretch(self) -> None:
        self.addStretch(1)


# --------------------------------------------------------------------------- KpiCard
class KpiCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("KpiCard")
        self.setMinimumWidth(150)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)
        self.title_label = secondary_label(title)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("KpiValue")
        self.value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.sub_label = secondary_label("")
        self.sub_label.hide()
        lay.addWidget(self.title_label)
        lay.addWidget(self.value_label)
        lay.addWidget(self.sub_label)
        lay.addStretch(1)

    def set_value(self, text: str, sub: str = "", tone: str | None = None) -> None:
        self.value_label.setText(str(text))
        set_tone(self.value_label, tone)
        self.sub_label.setText(sub)
        self.sub_label.setVisible(bool(sub))


# --------------------------------------------------------------------------- DataTable
class _Proxy(QSortFilterProxyModel):
    def lessThan(self, left, right) -> bool:  # números antes que texto, cada uno en su orden
        a, b = left.data(SORT_ROLE), right.data(SORT_ROLE)
        na, nb = isinstance(a, float), isinstance(b, float)
        if na and nb:
            return a < b
        if na != nb:
            return na
        return str(a or "") < str(b or "")


class DataTable(QWidget):
    selection_changed = Signal()
    activated = Signal(dict)  # doble clic / Enter sobre una fila

    def __init__(self, parent: QWidget | None = None, *, empty_text: str = "Sin datos",
                 title: str = "", filterable: bool = True, multi: bool = True) -> None:
        super().__init__(parent)
        self.title = title
        self._columns: list[tuple[str, str, Any]] = []
        self._rows: list[dict] = []

        self.model = QStandardItemModel(0, 0, self)
        self.proxy = _Proxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setSortRole(SORT_ROLE)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filtrar…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.proxy.setFilterFixedString)
        self.filter_edit.setVisible(filterable)

        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if multi
                                   else QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(34)
        self.view.setShowGrid(False)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setHighlightSections(False)
        self.view.setWordWrap(False)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        self.view.doubleClicked.connect(self._doble_clic)
        self.view.selectionModel().selectionChanged.connect(lambda *_: self.selection_changed.emit())

        self.empty_label = QLabel(empty_text)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setProperty("role", "secondary")

        self._stack = QStackedWidget()
        self._stack.addWidget(self.view)
        self._stack.addWidget(self.empty_label)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self.filter_edit)
        lay.addWidget(self._stack, 1)

        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut
        self.act_copy = self._accion("Copiar", QKeySequence.StandardKey.Copy, self.copy_selection, ctx, "")
        self.act_export = self._accion("Exportar CSV…", "Ctrl+E", self.export_csv_dialog, ctx,
                                       "SP_DialogSaveButton")
        self.act_print = self._accion("Imprimir…", "Ctrl+P", lambda: self.print_table(self.title, self), ctx,
                                      "printer")
        self._actualizar_vacio()

    def _accion(self, texto, atajo, slot, ctx, icono) -> QAction:
        a = QAction(texto, self)
        a.setShortcut(QKeySequence(atajo))
        a.setShortcutContext(ctx)
        if icono:
            a.setIcon(std_icon(icono))
        a.triggered.connect(lambda _c=False: slot())
        self.addAction(a)
        return a

    # ---- datos
    def set_columns(self, columns: Iterable[Column]) -> None:
        self._columns = [(c[0], c[1], c[2] if len(c) > 2 else None) for c in columns]
        self.model.setColumnCount(len(self._columns))
        self.model.setHorizontalHeaderLabels([c[1] for c in self._columns])
        self.set_rows(self._rows)

    def set_empty_text(self, text: str) -> None:
        self.empty_label.setText(text)

    def set_rows(self, rows: Iterable[dict]) -> None:
        self._rows = [r if isinstance(r, dict) else {"valor": r} for r in (rows or [])]
        self.view.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        for i, fila in enumerate(self._rows):
            self.model.appendRow([self._item(fila.get(key), fmt, i) for key, _h, fmt in self._columns])
        self.view.setSortingEnabled(True)
        self._actualizar_vacio()
        if self._rows:
            self.view.resizeColumnsToContents()
            for c in range(len(self._columns)):
                if self.view.columnWidth(c) > 360:
                    self.view.setColumnWidth(c, 360)

    def _item(self, valor: Any, fmt: Any, idx: int) -> QStandardItem:
        it = QStandardItem(format_value(valor, None if fmt == "status" else fmt))
        it.setData(idx, ROW_ROLE)
        n = as_number(valor)
        it.setData(n if n is not None else str(valor or "").lower(), SORT_ROLE)
        if n is not None and fmt != "status":
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if fmt == "status":
            tono = STATUS_TONES.get(str(valor or "").strip().upper())
            if tono:
                it.setForeground(theme.color(tono))
                it.setIcon(std_icon(_TONE_ICON[tono], theme.tokens()[tono]))
                f = theme.font(theme.BASE_PT, bold=True)
                it.setFont(f)
        return it

    def _actualizar_vacio(self) -> None:
        self._stack.setCurrentWidget(self.empty_label if not self._rows else self.view)

    def is_empty(self) -> bool:
        return not self._rows

    def rows(self) -> list[dict]:
        """Todas las filas, en el orden en que se cargaron."""
        return list(self._rows)

    def _fila_de_proxy(self, proxy_row: int) -> dict:
        idx = self.proxy.mapToSource(self.proxy.index(proxy_row, 0))
        return self._rows[self.model.item(idx.row(), 0).data(ROW_ROLE)]

    def visible_rows(self) -> list[dict]:
        """Filas que pasan el filtro, en el orden mostrado."""
        if not self._columns:
            return []
        return [self._fila_de_proxy(r) for r in range(self.proxy.rowCount())]

    def selected_rows(self) -> list[dict]:
        filas = sorted({i.row() for i in self.view.selectionModel().selectedRows()})
        return [self._fila_de_proxy(r) for r in filas] if self._columns else []

    def selected_row(self) -> dict | None:
        sel = self.selected_rows()
        return sel[0] if sel else None

    def _doble_clic(self, index) -> None:
        if index.isValid():
            self.activated.emit(self._fila_de_proxy(index.row()))

    # ---- exportar / copiar / imprimir
    def _matriz(self) -> tuple[list[str], list[list[str]]]:
        headers = [c[1] for c in self._columns]
        datos = [[self.proxy.index(r, c).data() or "" for c in range(len(self._columns))]
                 for r in range(self.proxy.rowCount())]
        return headers, datos

    def export_csv(self, path: str | Path) -> int:
        """Escribe las filas visibles (con filtro y orden) en CSV UTF-8 con BOM. Devuelve cuántas."""
        headers, datos = self._matriz()
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(headers)
            w.writerows(datos)
        return len(datos)

    def export_csv_dialog(self) -> str | None:
        nombre = re.sub(r"[^\w-]+", "_", self.title or "tabla").strip("_").lower() or "tabla"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar CSV", f"{nombre}.csv", "CSV (*.csv)")
        if not path:
            return None
        n = self.export_csv(path)
        QMessageBox.information(self, "Exportar CSV", f"Se exportaron {n} filas a:\n{path}")
        return path

    def copy_selection(self) -> None:
        sel = sorted({i.row() for i in self.view.selectionModel().selectedRows()})
        lineas = ["\t".join(self.proxy.index(r, c).data() or "" for c in range(len(self._columns)))
                  for r in sel]
        if lineas:
            QApplication.clipboard().setText("\n".join(lineas))

    def to_html(self, title: str = "") -> str:
        headers, datos = self._matriz()
        th = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        filas = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in fila) + "</tr>"
                        for fila in datos)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        return (
            "<html><head><style>"
            "body{font-family:sans-serif;font-size:9pt} h2{margin:0 0 4px 0}"
            "table{border-collapse:collapse;width:100%} th{background:#E2E8F0;text-align:left}"
            "th,td{border:1px solid #CBD5E1;padding:3px 5px}"
            "</style></head><body>"
            f"<h2>{html.escape(title or self.title or 'FreshTrack')}</h2>"
            f"<p>FreshTrack Desktop · {fecha} · {len(datos)} filas</p>"
            f"<table cellspacing='0' cellpadding='3'><thead><tr>{th}</tr></thead><tbody>{filas}</tbody></table>"
            "</body></html>"
        )

    def print_table(self, title: str = "", parent: QWidget | None = None) -> bool:
        """Abre el diálogo de impresión y renderiza la tabla como HTML. True si se imprimió."""
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, parent or self)
        dlg.setWindowTitle("Imprimir")
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            return False
        doc = QTextDocument()
        doc.setHtml(self.to_html(title))
        doc.print_(printer)
        return True

    def _menu(self, pos) -> None:
        m = QMenu(self)
        m.addAction(self.act_copy)
        m.addSeparator()
        m.addAction(self.act_export)
        m.addAction(self.act_print)
        m.exec(self.view.viewport().mapToGlobal(pos))


# --------------------------------------------------------------------------- diálogos
def confirm(parent: QWidget | None, text: str, title: str = "Confirmar") -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    si = box.addButton("Sí", QMessageBox.ButtonRole.YesRole)
    no = box.addButton("No", QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is si


def ask_text(parent: QWidget | None, title: str, label: str) -> str | None:
    """Pide un texto; None si se cancela o queda vacío."""
    texto, ok = QInputDialog.getText(parent, title, label)
    texto = (texto or "").strip()
    return texto if ok and texto else None
