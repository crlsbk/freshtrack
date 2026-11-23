"""
Página base de la ventana principal.

Contrato para las páginas (Tasks 5 a 7):
- Atributos de clase `title`, `subtitle` (una línea), `icon` (nombre de QStyle.StandardPixmap)
  y `roles` (vacío = todos los roles; admin siempre entra).
- `__init__(ctx)` arma los widgets SIN tocar la red. La red va en `refresh()` vía `ctx.run`.
- `on_show()` se llama al activar la página (por defecto `refresh()`); `on_hide()` al dejarla.
- Encabezado: `self.actions` (Toolbar a la derecha del título) y `self.body` (QVBoxLayout).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..widgets import Toolbar, secondary_label

if TYPE_CHECKING:
    from ..context import AppContext


class BasePage(QWidget):
    title: str = ""
    subtitle: str = ""
    icon: str = ""
    roles: tuple[str, ...] = ()

    def __init__(self, ctx: "AppContext", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = secondary_label(self.subtitle)
        self.subtitle_label.setVisible(bool(self.subtitle))
        textos.addWidget(self.title_label)
        textos.addWidget(self.subtitle_label)
        header.addLayout(textos, 1)
        self.actions = Toolbar()
        header.addLayout(self.actions)
        outer.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        outer.addLayout(self.body, 1)

    @classmethod
    def allowed_for(cls, session: Any) -> bool:
        if not cls.roles:
            return True
        return session is not None and session.can(*cls.roles)

    def on_show(self) -> None:
        self.refresh()

    def on_hide(self) -> None:
        pass

    def refresh(self) -> None:
        pass
