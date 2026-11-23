"""
Páginas de la ventana principal, en el orden de la barra lateral.

Las Tasks 5 a 7 reemplazan cada stub de `_stubs` importando aquí su clase real.
"""

from __future__ import annotations

from ._stubs import (
    DescuentosPage,
    ImportarVentasPage,
    MermasPage,
    NewsvendorPage,
    OrdenesCompraPage,
    PronosticosPage,
    ReabastecimientoPage,
    TableroPage,
    TransferenciasPage,
)
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
