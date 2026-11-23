"""
Tema visual: Fusion + paleta FreshTrack (claro/oscuro según el sistema) + un QSS corto.

Los tokens salen de la guía visual (ui-guidelines.md). Las páginas usan `tokens()`,
`color(nombre)` y las propiedades dinámicas de los widgets (`variant`, `tone`, `role`)
en lugar de colores fijos, para que el modo oscuro funcione en todos lados.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

LIGHT: dict[str, str] = {
    "window": "#F8FAFC",
    "surface": "#FFFFFF",
    "alt_row": "#F1F5F9",
    "text": "#0F172A",
    "text2": "#475569",
    "border": "#E2E8F0",
    "primary": "#15803D",
    "primary_hover": "#166534",
    "on_primary": "#FFFFFF",
    "selection_bg": "#DCFCE7",
    "success": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
    "on_danger": "#FFFFFF",
    "info": "#0369A1",
}

DARK: dict[str, str] = {
    "window": "#0B1220",
    "surface": "#111A2B",
    "alt_row": "#152036",
    "text": "#E2E8F0",
    "text2": "#94A3B8",
    "border": "#1F2A3D",
    "primary": "#22C55E",
    "primary_hover": "#4ADE80",
    "on_primary": "#052E16",
    "selection_bg": "#14532D",
    "success": "#4ADE80",
    "warning": "#FBBF24",
    "danger": "#F87171",
    "on_danger": "#1F0606",
    "info": "#38BDF8",
}

BASE_PT = 10
TITLE_PT = 15
KPI_PT = 20
SMALL_PT = 9

_actual: dict[str, str] = LIGHT
_conectado = False
_estilo_base = ""


def base_style() -> str:
    """Nombre del QStyle base aplicado por `apply()` ("fusion")."""
    return _estilo_base


def is_dark() -> bool:
    return _actual is DARK


def tokens() -> dict[str, str]:
    """Tokens del tema activo (copia)."""
    return dict(_actual)


def color(nombre: str) -> QColor:
    return QColor(_actual.get(nombre, _actual["text"]))


def font(pt: float = BASE_PT, bold: bool = False) -> QFont:
    f = QFont(QGuiApplication.font())
    f.setPointSizeF(pt)
    if bold:
        f.setWeight(QFont.Weight.DemiBold)
    return f


def system_prefers_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return False


def _paleta(t: dict[str, str]) -> QPalette:
    p = QPalette()
    c = {k: QColor(v) for k, v in t.items()}
    roles = {
        QPalette.ColorRole.Window: c["window"],
        QPalette.ColorRole.WindowText: c["text"],
        QPalette.ColorRole.Base: c["surface"],
        QPalette.ColorRole.AlternateBase: c["alt_row"],
        QPalette.ColorRole.Text: c["text"],
        QPalette.ColorRole.Button: c["surface"],
        QPalette.ColorRole.ButtonText: c["text"],
        QPalette.ColorRole.ToolTipBase: c["surface"],
        QPalette.ColorRole.ToolTipText: c["text"],
        QPalette.ColorRole.PlaceholderText: c["text2"],
        QPalette.ColorRole.Highlight: c["primary"],
        QPalette.ColorRole.HighlightedText: c["on_primary"],
        QPalette.ColorRole.Link: c["info"],
        QPalette.ColorRole.Mid: c["border"],
        QPalette.ColorRole.Midlight: c["border"],
    }
    for rol, col in roles.items():
        p.setColor(rol, col)
    for rol in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, rol, c["text2"])
    return p


def stylesheet(t: dict[str, str]) -> str:
    return f"""
QMainWindow, QDialog {{ background: {t['window']}; }}
QListWidget#Sidebar {{
    background: {t['surface']}; border: none; border-right: 1px solid {t['border']};
    outline: 0; padding-top: 8px;
}}
QListWidget#Sidebar::item {{
    height: 36px; padding-left: 9px; border-left: 3px solid transparent; color: {t['text']};
}}
QListWidget#Sidebar::item:hover {{ background: {t['alt_row']}; }}
QListWidget#Sidebar::item:selected {{
    background: {t['selection_bg']}; color: {t['text']}; border-left: 3px solid {t['primary']};
}}
QLabel#PageTitle {{ font-size: {TITLE_PT}pt; font-weight: 600; }}
QLabel[role="secondary"] {{ color: {t['text2']}; font-size: {SMALL_PT}pt; }}
QLabel[tone="success"] {{ color: {t['success']}; }}
QLabel[tone="warning"] {{ color: {t['warning']}; }}
QLabel[tone="danger"] {{ color: {t['danger']}; }}
QLabel[tone="info"] {{ color: {t['info']}; }}
QFrame#KpiCard {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QFrame#KpiCard QLabel {{ background: transparent; border: none; }}
QLabel#KpiValue {{ font-size: {KPI_PT}pt; font-weight: 600; }}
QPushButton {{ padding: 5px 12px; }}
QPushButton[variant="primary"] {{
    background: {t['primary']}; color: {t['on_primary']}; border: none; border-radius: 6px;
    padding: 6px 14px; font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: {t['primary_hover']}; }}
QPushButton[variant="danger"] {{
    background: {t['danger']}; color: {t['on_danger']}; border: none; border-radius: 6px;
    padding: 6px 14px; font-weight: 600;
}}
QPushButton[variant="primary"]:disabled, QPushButton[variant="danger"]:disabled {{
    background: {t['border']}; color: {t['text2']};
}}
QPushButton[variant="link"] {{ border: none; color: {t['info']}; text-align: left; padding: 2px 0; }}
QPushButton:focus, QLineEdit:focus {{ outline: none; border: 1px solid {t['primary']}; }}
QTableView {{
    background: {t['surface']}; alternate-background-color: {t['alt_row']};
    gridline-color: {t['border']}; border: 1px solid {t['border']};
    selection-background-color: {t['selection_bg']}; selection-color: {t['text']};
}}
QHeaderView::section {{
    background: {t['window']}; color: {t['text']}; font-weight: 600; padding: 4px 6px;
    border: none; border-bottom: 1px solid {t['border']}; border-right: 1px solid {t['border']};
}}
QDockWidget::title {{ padding: 4px 8px; background: {t['window']}; }}
QStatusBar {{ color: {t['text2']}; }}
"""


def apply(app: QApplication | None = None, dark: bool | None = None) -> None:
    """Aplica Fusion, la paleta y el QSS. `dark=None` sigue al sistema."""
    global _actual, _conectado, _estilo_base
    app = app or QApplication.instance()
    if app is None:
        return
    app.setStyle("Fusion")
    _estilo_base = app.style().name()  # con QSS, app.style() pasa a ser un QStyleSheetStyle sin nombre
    _actual = DARK if (system_prefers_dark() if dark is None else dark) else LIGHT
    f = QFont(app.font())
    f.setPointSizeF(BASE_PT)
    app.setFont(f)
    app.setPalette(_paleta(_actual))
    app.setStyleSheet(stylesheet(_actual))
    if dark is None and not _conectado:
        try:
            app.styleHints().colorSchemeChanged.connect(lambda *_: apply(app))
            _conectado = True
        except AttributeError:
            pass


def repolish(widget) -> None:
    """Vuelve a aplicar el QSS tras cambiar una propiedad dinámica (variant/tone)."""
    st = widget.style()
    st.unpolish(widget)
    st.polish(widget)
    widget.update()
