"""Mapa de tiendas: métricas por locación calculadas contra PostgreSQL."""

from __future__ import annotations

from app.db import a_float, one
from app.domain import kpis

from .conftest import TIENDA


def test_metricas_por_locacion_traen_coordenadas_y_cuadran_con_postgres():
    locaciones = {l["id_locacion"]: l for l in kpis.metricas_por_locacion(30)}
    tienda = locaciones[TIENDA]

    # El seed le da coordenadas a todas las locaciones base.
    assert tienda["latitud"] is not None and tienda["longitud"] is not None
    assert -90 <= tienda["latitud"] <= 90 and -180 <= tienda["longitud"] <= 180

    esperado = one(
        """
        SELECT COALESCE(SUM(valor_inventario), 0) AS valor,
               COUNT(DISTINCT id_lote)            AS lotes
        FROM operacion.v_inventario_lote
        WHERE id_locacion = :loc AND cantidad_disponible > 0
        """,
        loc=TIENDA,
    )
    assert abs(tienda["inventario"]["valor"] - a_float(esperado["valor"])) < 0.01
    assert tienda["inventario"]["lotes"] == esperado["lotes"]
    assert tienda["inventario"]["valor_en_riesgo"] <= tienda["inventario"]["valor"]
    assert len(tienda["lotes_en_riesgo"]) <= 3


def test_metricas_por_locacion_solo_incluye_activas():
    activas = one("SELECT count(*) AS n FROM operacion.locacion WHERE activo")["n"]
    assert len(kpis.metricas_por_locacion(7)) == activas
