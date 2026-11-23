"""
Páginas de la ventana principal, en el orden de la barra lateral.

Cada página vive en su módulo; `_stubs` conserva las definiciones originales de título y roles
(las pruebas comparan contra ellas).
"""

from __future__ import annotations

from .descuentos import DescuentosPage
from .importar_ventas import ImportarVentasPage
from .mermas import MermasPage
from .newsvendor import NewsvendorPage
from .ordenes_compra import OrdenesCompraPage
from .pronosticos import PronosticosPage
from .reabastecimiento import ReabastecimientoPage
from .tablero import TableroPage
from .transferencias import TransferenciasPage
from .actividad import ActividadPage
from .base import BasePage
from .estado import EstadoPage

ALL_PAGES: list[type[BasePage]] = [
    TableroPage,
    PronosticosPage,
    NewsvendorPage,
    ReabastecimientoPage,
    TransferenciasPage,
    DescuentosPage,
    MermasPage,
    OrdenesCompraPage,
    ImportarVentasPage,
    EstadoPage,
    ActividadPage,
]

__all__ = ["ALL_PAGES", "BasePage", "EstadoPage", "ActividadPage"]
