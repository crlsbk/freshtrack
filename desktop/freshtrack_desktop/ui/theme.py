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
    from . import icons

    abajo = icons.svg_file("chevron-down", t["text2"])
    arriba = icons.svg_file("chevron-up", t["text2"])
    return f"""
QMainWindow, QDialog {{ background: {t['window']}; }}
QToolTip {{ background: {t['text']}; color: {t['surface']}; border: none; padding: 6px 8px; border-radius: 6px; }}

/* ---------- barra lateral ---------- */
QFrame#SidebarPanel {{ background: {t['surface']}; border: none; border-right: 1px solid {t['border']}; }}
QLabel#BrandName {{ font-size: 12.5pt; font-weight: 700; color: {t['text']}; }}
QLabel#BrandSub {{ font-size: {SMALL_PT}pt; color: {t['text2']}; }}
QLabel#SidebarSection {{ font-size: 8pt; font-weight: 700; color: {t['text2']}; padding-left: 10px; letter-spacing: 1px; }}
QListWidget#Sidebar {{ background: transparent; border: none; outline: 0; }}
QListWidget#Sidebar::item {{
    border-radius: 8px; padding-left: 10px; margin: 1px 0; color: {t['text2']}; font-weight: 500;
}}
QListWidget#Sidebar::item:hover {{ background: {t['alt_row']}; color: {t['text']}; }}
QListWidget#Sidebar::item:selected {{ background: {t['selection_bg']}; color: {t['primary']}; font-weight: 600; }}
QFrame#UserCard {{ background: {t['window']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QFrame#UserCard QLabel {{ background: transparent; border: none; }}
QFrame#UserCard QLabel#Avatar {{ background: {t['primary']}; color: {t['on_primary']}; border-radius: 16px; font-weight: 700; }}
QLabel#UserName {{ font-weight: 600; color: {t['text']}; }}
QLabel#UserRole {{ font-size: {SMALL_PT}pt; color: {t['text2']}; }}
QToolButton#LogoutButton {{ border: none; border-radius: 6px; padding: 4px; background: transparent; }}
QToolButton#LogoutButton:hover {{ background: {t['alt_row']}; }}

/* ---------- textos ---------- */
QLabel#PageTitle {{ font-size: {TITLE_PT + 2}pt; font-weight: 700; }}
QLabel[role="secondary"] {{ color: {t['text2']}; font-size: {SMALL_PT}pt; }}
QLabel[tone="success"] {{ color: {t['success']}; }}
QLabel[tone="warning"] {{ color: {t['warning']}; }}
QLabel[tone="danger"] {{ color: {t['danger']}; }}
QLabel[tone="info"] {{ color: {t['info']}; }}

/* ---------- tarjetas KPI ---------- */
QFrame#KpiCard {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 12px; }}
QFrame#KpiCard QLabel {{ background: transparent; border: none; }}
QLabel#KpiValue {{ font-size: {KPI_PT + 2}pt; font-weight: 700; }}

/* ---------- botones ---------- */
QPushButton {{
    background: {t['surface']}; color: {t['text']}; border: 1px solid {t['border']}; border-radius: 8px;
    padding: 7px 14px; font-weight: 500;
}}
QPushButton:hover {{ background: {t['alt_row']}; }}
QPushButton:pressed {{ background: {t['border']}; }}
QPushButton:disabled {{ color: {t['text2']}; background: {t['window']}; }}
QPushButton[variant="primary"] {{
    background: {t['primary']}; color: {t['on_primary']}; border: 1px solid {t['primary']}; font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: {t['primary_hover']}; border-color: {t['primary_hover']}; }}
QPushButton[variant="danger"] {{
    background: {t['surface']}; color: {t['danger']}; border: 1px solid {t['danger']}; font-weight: 600;
}}
QPushButton[variant="danger"]:hover {{ background: {t['danger']}; color: {t['on_danger']}; }}
QPushButton[variant="primary"]:disabled, QPushButton[variant="danger"]:disabled {{
    background: {t['window']}; color: {t['text2']}; border-color: {t['border']};
}}
QPushButton[variant="link"] {{ border: none; background: transparent; color: {t['info']}; text-align: left; padding: 2px 0; }}
QPushButton:focus {{ border: 1px solid {t['primary']}; }}

/* ---------- campos ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {t['selection_bg']}; selection-color: {t['text']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus,
QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {t['primary']}; }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{abajo}"); width: 14px; height: 14px; }}
QAbstractSpinBox {{ padding-right: 22px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none; background: transparent;
}}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; margin: 3px 3px 0 0; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 3px 3px 0; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {t['alt_row']}; border-radius: 4px; }}
QAbstractSpinBox::up-arrow {{ image: url("{arriba}"); width: 11px; height: 11px; }}
QAbstractSpinBox::down-arrow {{ image: url("{abajo}"); width: 11px; height: 11px; }}
QComboBox QAbstractItemView {{ border: 1px solid {t['border']}; border-radius: 8px; padding: 4px;
    selection-background-color: {t['selection_bg']}; selection-color: {t['text']}; outline: 0; }}

/* ---------- tablas ---------- */
QTableView {{
    background: {t['surface']}; alternate-background-color: {t['window']};
    border: 1px solid {t['border']}; border-radius: 10px; gridline-color: transparent;
    selection-background-color: {t['selection_bg']}; selection-color: {t['text']};
}}
QTableView::item {{ padding: 0 8px; border-bottom: 1px solid {t['border']}; }}
QHeaderView::section {{
    background: {t['surface']}; color: {t['text2']}; font-weight: 600; font-size: {SMALL_PT}pt;
    padding: 8px; border: none; border-bottom: 1px solid {t['border']};
}}
QTableCornerButton::section {{ background: {t['surface']}; border: none; }}

/* ---------- pestañas ---------- */
QTabWidget::pane {{ border: none; border-top: 1px solid {t['border']}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {t['text2']}; padding: 8px 14px; border: none;
    border-bottom: 2px solid transparent; font-weight: 500;
}}
QTabBar::tab:hover {{ color: {t['text']}; }}
QTabBar::tab:selected {{ color: {t['primary']}; border-bottom: 2px solid {t['primary']}; font-weight: 600; }}

/* ---------- barras de scroll delgadas ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {t['text2']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['border']}; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- otros ---------- */
QGroupBox {{ border: 1px solid {t['border']}; border-radius: 10px; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {t['text2']}; font-weight: 600; }}
QMenuBar {{ background: {t['surface']}; border-bottom: 1px solid {t['border']}; }}
QMenuBar::item {{ padding: 6px 10px; background: transparent; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {t['alt_row']}; }}
QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['selection_bg']}; color: {t['text']}; }}
QDockWidget::title {{ padding: 6px 10px; background: {t['surface']}; }}
QStatusBar {{ color: {t['text2']}; background: {t['surface']}; border-top: 1px solid {t['border']}; }}
QStatusBar QLabel {{ padding: 0 8px; }}
QProgressBar {{ border: none; background: {t['border']}; border-radius: 3px; height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {t['primary']}; border-radius: 3px; }}
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
    try:
        from . import icons

        icons.clear_cache()
    except ImportError:
        pass
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
