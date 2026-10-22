"""Reglas de negocio puras: reparto FEFO y modelos de pronóstico."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain import pronostico as p
from app.domain.ventas import repartir_fefo


def _lote(id_, disp, res=0, costo=10):
    return {"id_lote": id_, "cantidad_disponible": disp, "cantidad_reservada": res, "costo_unitario": costo}


def test_fefo_consume_primero_el_lote_mas_proximo_a_caducar():
    lotes = [_lote("vence-hoy", 3), _lote("vence-manana", 10)]
    consumos = repartir_fefo(lotes, 5)
    assert [(c["id_lote"], c["consumido"]) for c in consumos] == [("vence-hoy", 3), ("vence-manana", 2)]


def test_fefo_respeta_lo_ya_reservado():
    consumos = repartir_fefo([_lote("a", 5, res=4), _lote("b", 5)], 3)
    assert [(c["id_lote"], c["consumido"]) for c in consumos] == [("a", 1), ("b", 2)]


def test_fefo_stock_insuficiente_cubre_lo_posible():
    consumos = repartir_fefo([_lote("a", 2)], 5)
    assert sum(c["consumido"] for c in consumos) == 2


def test_fefo_omite_lotes_sin_disponible():
    assert repartir_fefo([_lote("a", 1, res=1), _lote("b", 0)], 1) == []


def test_medias_moviles():
    assert p._media_movil([1, 2, 3, 4], 2) == 3.5
    # Pesos 1,2,3 sobre [2,4,6] → (2+8+18)/6
    assert p._media_movil_ponderada([2, 4, 6], 3) == pytest.approx(28 / 6)


def test_suavizacion_exponencial_converge_al_ultimo_valor_con_alpha_alto():
    assert p._suavizacion_exponencial([10, 10, 10, 50], 0.99) == pytest.approx(49.6, rel=1e-2)
    assert p._suavizacion_exponencial([], 0.3) == 0.0


def test_metodo_desconocido_lanza_error():
    with pytest.raises(ValueError):
        p._nivel([1, 2], "MAGIA", 7, 0.3)


def test_metricas_de_error():
    m = p._metricas([10, 20], [12, 18])
    assert m["mae"] == 2 and m["n"] == 2 and m["wmape"] == pytest.approx(13.3333, rel=1e-3)


def test_pronosticar_serie_horizonte_y_no_negativo():
    base = date(2026, 10, 1)
    serie = [(base + timedelta(days=i), float(10 + (i % 7))) for i in range(60)]
    res = p.pronosticar_serie(serie, "SUAVIZACION_EXPONENCIAL", horizonte=7, ventana=28, alpha=0.3, fecha_base=serie[-1][0])
    assert len(res["pronostico"]) == 7
    assert all(x["valor"] >= 0 for x in res["pronostico"])
    assert res["metricas"]["n"] == res["dias_backtest"]
