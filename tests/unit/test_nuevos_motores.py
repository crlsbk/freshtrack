"""Pruebas unitarias de los motores nuevos y seguridad Fail-Closed."""

from __future__ import annotations

from datetime import date, timedelta

from app import security
from app.domain import pronostico as p
from app.domain.reabastecimiento import optimizar_newsvendor
from app.domain.triaje import decidir_ruta_lote
from app.domain.ventas import repartir_fefo
from app.services import cache_service


def test_fefo_excluye_lotes_bloqueados_cuarentena_y_caducados():
    lotes = [
        {"id_lote": "bloqueado", "cantidad_disponible": 20, "cantidad_reservada": 0, "costo_unitario": 10, "estado": "BLOQUEADO", "dias_restantes": 2},
        {"id_lote": "cuarentena", "cantidad_disponible": 20, "cantidad_reservada": 0, "costo_unitario": 10, "estado": "CUARENTENA", "dias_restantes": 2},
        {"id_lote": "vencido", "cantidad_disponible": 20, "cantidad_reservada": 0, "costo_unitario": 10, "estado": "DISPONIBLE", "dias_restantes": -1},
        {"id_lote": "elegible", "cantidad_disponible": 15, "cantidad_reservada": 5, "costo_unitario": 10, "estado": "DISPONIBLE", "dias_restantes": 3},
    ]
    consumos = repartir_fefo(lotes, 10)
    assert [(c["id_lote"], c["consumido"]) for c in consumos] == [("elegible", 10)]


def test_newsvendor_optimiza_costo_y_respeta_caducidad():
    nv = optimizar_newsvendor(
        precio_venta=50.0,
        precio_costo=20.0,
        demanda_media=100.0,
        desviacion_estandar=20.0,
        vida_util_dias=7,
        demanda_diaria=15.0,
        stock_util=20.0,
        entradas=0.0,
        stock_seguridad_simple=10.0,
    )
    assert nv["costo_faltante"] == 30.0
    assert nv["costo_excedente"] > 0
    assert 0.5 < nv["fractil_critico"] < 1.0
    # Vida útil 7 días * 15/día = 105 max stock objetivo -> 105 - 20 = 85 max pedido
    assert nv["stock_objetivo_newsvendor"] <= 105.0
    assert nv["costo_esperado_newsvendor"] <= nv["costo_esperado_simple"] + 1e-6


def test_triaje_elige_traslado_descuento_y_merma():
    # 1. Caducado -> MERMA
    m = decidir_ruta_lote(
        estado_lote="DISPONIBLE",
        dias_restantes=-1,
        cantidad_disponible=10,
        demanda_diaria_origen=2,
        precio_venta=50,
        precio_costo=30,
    )
    assert m["accion"] == "MERMA"

    # 2. Exceso con tienda destino deficitaria y tiempo suficiente -> TRASLADO
    t = decidir_ruta_lote(
        estado_lote="DISPONIBLE",
        dias_restantes=4,
        cantidad_disponible=40,
        demanda_diaria_origen=2,
        precio_venta=60,
        precio_costo=30,
        mejor_destino={"id_locacion": 4, "nombre": "Tienda Cumbres", "faltante": 30, "demanda_diaria": 10},
    )
    assert t["accion"] == "TRASLADO"
    assert t["valor_traslado_neto"] >= t["valor_descuento_neto"]

    # 3. Riesgo urgente (vence en 1 día, no llega traslado) -> DESCUENTO local
    d = decidir_ruta_lote(
        estado_lote="DISPONIBLE",
        dias_restantes=1,
        cantidad_disponible=20,
        demanda_diaria_origen=4,
        precio_venta=60,
        precio_costo=30,
        mejor_destino={"id_locacion": 4, "nombre": "Tienda Cumbres", "faltante": 30, "demanda_diaria": 10},
    )
    assert d["accion"] == "DESCUENTO"
    assert d["valor_descuento_neto"] > 0


def test_pronostico_calcula_sesgo_y_naive():
    m = p._metricas([10, 0, 20, 0], [12, 2, 22, 2])
    assert m["sesgo"] == 2.0  # sobreestima por +2
    assert m["demanda_intermitente"] is True

    base = date(2026, 10, 1)
    serie = [(base + timedelta(days=i), float(10 + (i % 7))) for i in range(60)]
    res = p.pronosticar_serie(serie, "SUAVIZACION_EXPONENCIAL", horizonte=7, ventana=28, alpha=0.3, fecha_base=serie[-1][0])
    assert "metricas_naive" in res
    assert res["metricas"]["sesgo"] is not None


def test_seguridad_fail_closed_sin_redis_ni_postgres(monkeypatch):
    monkeypatch.setattr(cache_service, "_client", None)
    monkeypatch.setattr(cache_service, "_ultimo_fallo", 10**12)  # evita intentar conectar

    def _bd_caida(*args, **kwargs):
        raise RuntimeError("PostgreSQL unreachable")

    monkeypatch.setattr(security, "one", _bd_caida)
    assert security.verificar_sesion_respaldo_bd("jti-cualquiera") is False
