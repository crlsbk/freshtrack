"""Mapa de tiendas: validación de coordenadas y permisos de la vista."""

from __future__ import annotations

import pytest

from app.navegacion import VISTAS_POR_ROL, endpoint_de
from app.repos.catalogo import _coordenadas


def test_coordenadas_vacias_son_opcionales():
    assert _coordenadas({}) == (None, None)
    assert _coordenadas({"latitud": " ", "longitud": ""}) == (None, None)


def test_coordenadas_validas_se_convierten_a_numero():
    assert _coordenadas({"latitud": "25.6575", "longitud": "-100.402"}) == (25.6575, -100.402)


@pytest.mark.parametrize(
    "datos, mensaje",
    [
        ({"latitud": "25.6"}, "juntas"),
        ({"longitud": "-100.4"}, "juntas"),
        ({"latitud": "norte", "longitud": "-100.4"}, "números"),
        ({"latitud": "95", "longitud": "-100.4"}, "fuera de rango"),
        ({"latitud": "25.6", "longitud": "-181"}, "fuera de rango"),
    ],
)
def test_coordenadas_invalidas_se_rechazan(datos, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        _coordenadas(datos)


def test_vista_del_mapa_registrada_y_sin_acceso_para_proveedor():
    assert endpoint_de("map") == "panel.mapa"
    assert "map" not in VISTAS_POR_ROL["supplier"]
    for rol in ("admin", "buyer", "planner", "store_manager", "warehouse", "auditor"):
        assert "map" in VISTAS_POR_ROL[rol], rol
