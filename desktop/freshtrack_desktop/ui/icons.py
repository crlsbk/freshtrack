"""
Íconos de línea (estilo Lucide, 24×24, trazo redondeado) dibujados con QtSvg.

Sustituyen a los QStyle.StandardPixmap de Fusion, que se ven de principios de los 2000.
Trazos tomados de Lucide (https://lucide.dev, licencia ISC). Cada ícono se pinta con el
color del tema activo, así que funciona igual en claro y oscuro.

    icon("refresh")                      → QIcon con el color de texto secundario
    icon("check", color="#FFFFFF")       → para botones primarios
    icon("SP_BrowserReload")             → alias de compatibilidad (páginas existentes)
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS: dict[str, str] = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                 '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "chart": '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="m19 9-5 5-4-4-3 3"/>',
    "target": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    "package": '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4'
               'A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 8.7 5 8.7-5"/>'
               '<path d="m7.5 4.27 9 5.15"/>',
    "transfer": '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    "tag": '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.7 8.7a2.43 2.43 0 0 0 3.42 0'
           'l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor"/>',
    "leaf": '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/>'
            '<path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>',
    "clipboard": '<rect width="8" height="4" x="8" y="2" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6'
                 'a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/>'
                 '<path d="M8 16h.01"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "activity": '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0'
                'l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
               '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "play": '<path d="M6 3.5v17a.5.5 0 0 0 .77.42l13.2-8.5a.5.5 0 0 0 0-.84L6.77 3.08A.5.5 0 0 0 6 3.5z"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
            '<path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
    "printer": '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
               '<path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/><rect x="6" y="14" width="12" height="8" rx="1"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "server": '<rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/>'
              '<path d="M6 6h.01"/><path d="M6 18h.01"/>',
    "send": '<path d="M14.54 21.69a.5.5 0 0 0 .94-.03l6.5-19a.5.5 0 0 0-.64-.64l-19 6.5a.5.5 0 0 0-.03.94l7.93 3.18'
            'a2 2 0 0 1 1.11 1.11z"/><path d="m21.85 2.15-10.94 10.94"/>',
    "mail": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/>'
             '<path d="M12 17h.01"/>',
    "x-circle": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "settings": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73'
                'l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38'
                'a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18'
                'a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08'
                'a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08'
                'a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "code": '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-up": '<path d="m18 15-6-6-6 6"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
}

# Compatibilidad: nombres de QStyle.StandardPixmap que ya usan las páginas.
_ALIAS: dict[str, str] = {
    "SP_BrowserReload": "refresh", "SP_DialogApplyButton": "check", "SP_DialogYesButton": "check",
    "SP_FileDialogDetailedView": "dashboard", "SP_FileDialogContentsView": "chart",
    "SP_DialogSaveButton": "download", "SP_ArrowDown": "download", "SP_MediaPlay": "play",
    "SP_FileDialogNewFolder": "plus", "SP_FileDialogInfoView": "info", "SP_DialogResetButton": "tag",
    "SP_DialogOpenButton": "upload", "SP_DialogCancelButton": "x", "SP_DialogCloseButton": "logout",
    "SP_TrashIcon": "trash", "SP_FileIcon": "file", "SP_DriveNetIcon": "server", "SP_DirLinkIcon": "transfer",
    "SP_ArrowUp": "send", "SP_MessageBoxWarning": "alert", "SP_MessageBoxInformation": "info",
    "SP_MessageBoxCritical": "x-circle",
}

# Ícono propio de cada página en la barra lateral (por título).
PAGE_ICONS: dict[str, str] = {
    "Tablero": "dashboard", "Pronósticos": "chart", "Newsvendor": "target", "Reabastecimiento": "package",
    "Transferencias": "transfer", "Descuentos": "tag", "Mermas y desperdicio": "leaf",
    "Órdenes de compra": "clipboard", "Importar ventas": "upload", "Estado de servicios": "activity",
    "Actividad": "history",
}


def resolve(name: str) -> str:
    return _ALIAS.get(name, name)


def has(name: str) -> bool:
    return resolve(name) in _PATHS


def svg(name: str, color: str, stroke: float = 1.8) -> bytes:
    body = _PATHS[resolve(name)].replace("currentColor", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).encode()


def pixmap(name: str, color: str, size: int = 18, dpr: float = 2.0) -> QPixmap:
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.GlobalColor.transparent)
    r = QSvgRenderer(QByteArray(svg(name, color)))
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


@lru_cache(maxsize=512)
def _icon_cache(name: str, normal: str, active: str, disabled: str) -> QIcon:
    ic = QIcon()
    for s in (16, 18, 20, 24, 32):
        ic.addPixmap(pixmap(name, normal, s), QIcon.Mode.Normal)
        ic.addPixmap(pixmap(name, active, s), QIcon.Mode.Selected)
        ic.addPixmap(pixmap(name, active, s), QIcon.Mode.Active)
        ic.addPixmap(pixmap(name, disabled, s), QIcon.Mode.Disabled)
    return ic


def icon(name: str, color: str | None = None, active: str | None = None) -> QIcon:
    """QIcon teñido con el tema actual. Nombre desconocido → QIcon vacío."""
    if not name or not has(name):
        return QIcon()
    from . import theme

    t = theme.tokens()
    normal = color or t["text2"]
    return _icon_cache(resolve(name), normal, active or color or t["primary"], t["border"] if not theme.is_dark() else "#334155")


def app_logo(size: int = 64) -> QPixmap:
    """Logo de la app: hoja blanca sobre un cuadro verde redondeado."""
    from . import theme

    dpr = 2.0
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#15803D"))
    s = size * dpr
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.24, s * 0.24)
    r = QSvgRenderer(QByteArray(svg("leaf", "#FFFFFF", 2.0)))
    m = s * 0.2
    r.render(p, QRectF(m, m, s - 2 * m, s - 2 * m))
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


def svg_file(name: str, color: str, stroke: float = 2.0) -> str:
    """Escribe el SVG en la caché del usuario y devuelve la ruta (para `image: url(...)` en QSS)."""
    import tempfile
    from pathlib import Path

    carpeta = Path(tempfile.gettempdir()) / "freshtrack_desktop_icons"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{resolve(name)}_{color.lstrip('#')}.svg"
    if not ruta.exists():
        ruta.write_bytes(svg(name, color, stroke))
    return ruta.as_posix()


def clear_cache() -> None:
    """Llamar al cambiar de tema claro↔oscuro."""
    _icon_cache.cache_clear()


__all__ = ["icon", "pixmap", "app_logo", "PAGE_ICONS", "has", "resolve", "clear_cache", "QSize"]
