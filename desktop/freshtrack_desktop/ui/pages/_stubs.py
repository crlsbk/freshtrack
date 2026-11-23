"""Páginas provisionales ("En construcción") hasta que las Tasks 5 a 7 las reemplacen."""

from __future__ import annotations

from PySide6.QtCore import Qt

from ..widgets import secondary_label
from .base import BasePage


class EnConstruccionPage(BasePage):
    subtitle = "En construcción"

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        aviso = secondary_label(f"La página «{self.title}» está en construcción.")
        aviso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.addWidget(aviso, 1)


class TableroPage(EnConstruccionPage):
    title, icon, roles = "Tablero", "SP_FileDialogDetailedView", ()


class PronosticosPage(EnConstruccionPage):
    title, icon, roles = "Pronósticos", "SP_FileDialogContentsView", ("planner", "buyer")


class NewsvendorPage(EnConstruccionPage):
    title, icon, roles = "Newsvendor", "SP_DialogApplyButton", ("planner", "buyer")


class ReabastecimientoPage(EnConstruccionPage):
    title, icon, roles = "Reabastecimiento", "SP_BrowserReload", ("planner", "buyer")


class TransferenciasPage(EnConstruccionPage):
    title, icon, roles = "Transferencias", "SP_DirLinkIcon", ("planner",)


class DescuentosPage(EnConstruccionPage):
    title, icon, roles = "Descuentos", "SP_DialogResetButton", ("planner",)


class MermasPage(EnConstruccionPage):
    title, icon, roles = "Mermas y desperdicio", "SP_TrashIcon", ()


class OrdenesCompraPage(EnConstruccionPage):
    title, icon, roles = "Órdenes de compra", "SP_FileIcon", ("buyer",)


class ImportarVentasPage(EnConstruccionPage):
    title, icon, roles = "Importar ventas", "SP_DialogOpenButton", ("buyer", "planner")
