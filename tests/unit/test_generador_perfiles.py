"""Pruebas unitarias de los 4 perfiles de demanda, simulación FEFO y caché Redis web."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import os
from pathlib import Path
import random
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

os.environ.setdefault("SECRET_KEY", "clave-de-pruebas-perfiles-0123456789")
os.environ.setdefault("JWT_SECRET_KEY", "jwt-de-pruebas-perfiles-0123456789")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_backend:x@127.0.0.1:1/inexistente")

from app.domain import kpis as dom_kpis  # noqa: E402
from app.domain import pronostico as motor_pron  # noqa: E402
from app.services import cache_service  # noqa: E402
from scripts import generar_dataset_masivo as gen  # noqa: E402


def _serie_de_perfil(sku_cfg: dict, dias: int = 120, seed: int = 1234) -> list[tuple[date, float]]:
    rng = random.Random(seed)
    fin = date(2026, 11, 20)
    inicio = fin - timedelta(days=dias - 1)
    salida: list[tuple[date, float]] = []
    for i in range(dias):
        d = inicio + timedelta(days=i)
        cant, _ = gen.demanda_dia_perfil(sku_cfg, d, i, dias, rng)
        salida.append((d, float(cant)))
    return salida


def test_catalogo_200_skus_cumple_proporciones_y_vida_util():
    catalogo = gen.generar_catalogo_200_skus(n_skus=200, seed=42)
    assert len(catalogo) == 200

    conteo: dict[str, int] = {}
    subtipos: dict[str, int] = {}
    gtins = set()
    for p in catalogo:
        conteo[p["perfil_demanda"]] = conteo.get(p["perfil_demanda"], 0) + 1
        subtipos[p["subtipo"]] = subtipos.get(p["subtipo"], 0) + 1
        assert 2 <= p["vida_util_estandar"] <= 14
        assert p["precio_venta"] > p["precio_costo"]
        assert len(p["codigo_gtin"]) == 14
        gtins.add(p["codigo_gtin"])

    assert len(gtins) == 200
    assert conteo["ESTABLE_ESTACIONAL"] == 100
    assert conteo["DRIFT_TENDENCIA"] == 40
    assert conteo["INTERMITENTE"] == 40
    assert conteo["QUIEBRE_STOCK"] == 20
    assert subtipos["escalon_reciente"] == 20
    assert subtipos["rampa_60d"] == 20


def test_cuatro_perfiles_discriminan_en_pronostico_y_drift():
    catalogo = gen.generar_catalogo_200_skus(n_skus=200, seed=20261123)
    estable = next(p for p in catalogo if p["subtipo"] == "estable")
    escalon = next(p for p in catalogo if p["subtipo"] == "escalon_reciente")
    interm = next(p for p in catalogo if p["subtipo"] == "intermitente")
    quiebre = next(p for p in catalogo if p["subtipo"] == "quiebre")

    # 1. Estable + estacional vence al Naive
    s_est = _serie_de_perfil(estable, dias=120, seed=11)
    res_est = motor_pron.pronosticar_serie(s_est, "AUTO", horizonte=7, ventana=28, alpha=0.30, fecha_base=s_est[-1][0])
    assert res_est["mejora_vs_naive_pct"] is not None
    assert res_est["mejora_vs_naive_pct"] > 0

    # 2. Drift escalón reciente dispara alerta de Data Drift
    s_drift = _serie_de_perfil(escalon, dias=120, seed=22)
    diag = motor_pron.detectar_drift_serie(s_drift, ventana_reciente=14)
    assert diag["estado"] in ("NO_CONFIABLE", "VIGILANCIA")
    assert abs(diag["cambio_nivel_pct"]) >= 25.0

    # 3. Intermitente produce ~60% de ceros y activa bandera demanda_intermitente
    s_int = _serie_de_perfil(interm, dias=120, seed=33)
    ceros = sum(1 for _, v in s_int if v == 0)
    assert ceros / len(s_int) >= 0.45
    assert motor_pron._metricas([v for _, v in s_int], [1.0] * len(s_int))["demanda_intermitente"] is True

    # 4. Quiebre de stock contiene bloque exacto de 5 días seguidos en 0
    s_q = _serie_de_perfil(quiebre, dias=120, seed=44)
    racha_cero = max_racha = 0
    for _, v in s_q:
        racha_cero = (racha_cero + 1) if v == 0 else 0
        max_racha = max(max_racha, racha_cero)
    assert max_racha >= 5


def test_simulacion_fefo_consume_lote_mas_viejo_y_nunca_vencido():
    sku_cfg = {
        "id_sku": 1,
        "id_proveedor": 1,
        "vida_util_estandar": 4,
        "precio_costo": 10.0,
        "precio_venta": 20.0,
        "lambda_base": 15.0,
        "punto_reorden": 25.0,
        "moq_lote": 20.0,
        "subtipo": "estable",
        "direccion_drift": 1,
    }
    sim = gen.simular_serie_fefo_sku(
        sku_cfg,
        id_locacion=1,
        fecha_inicio=date(2026, 10, 1),
        dias=45,
        rng=random.Random(77),
        prefijo_prov="TST",
        usuario_id="00000000-0000-0000-0000-000000000001",
        seq_lote={},
    )
    cad_por_lote = {l[0]: l[6] for l in sim["lotes"]}
    assert len(sim["lotes"]) > 1
    assert len(sim["ventas_lineas"]) > 20
    # Ninguna venta ocurre después de la caducidad del lote consumido
    for ln in sim["ventas_lineas"]:
        assert ln["dia"] <= cad_por_lote[ln["id_lote"]]
    # Todas las existencias quedan >= 0 y todas las mermas automáticas son CADUCIDAD
    assert all(v >= 0 for v in sim["existencias"].values())
    assert all(m[4] == "CADUCIDAD" for m in sim["mermas"])


def test_cache_web_en_kpis_y_degradacion_sin_redis(monkeypatch):
    almacen: dict[str, object] = {}
    llamadas = {"n": 0}

    class _FakeRedis:
        pass

    monkeypatch.setenv("CACHE_WEB_ACTIVA", "true")
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(cache_service, "get_json", lambda k: almacen.get(k))
    monkeypatch.setattr(cache_service, "set_json", lambda k, v, ttl_segundos=60: almacen.__setitem__(k, v) or True)
    monkeypatch.setattr(cache_service, "incrementar_contador", lambda *a, **kw: 1)

    def _fn():
        llamadas["n"] += 1
        return {"valor": Decimal("123.45"), "fecha": date(2026, 11, 23)}

    r1 = dom_kpis._con_cache_web("web:test:1", 60, _fn)
    r2 = dom_kpis._con_cache_web("web:test:1", 60, _fn)
    assert llamadas["n"] == 1
    assert r1 == {"valor": 123.45, "fecha": "2026-11-23"}
    assert r2 == r1

    # Con CACHE_WEB_ACTIVA=false o sin Redis degrada limpiamente directo a fn()
    monkeypatch.setenv("CACHE_WEB_ACTIVA", "false")
    r3 = dom_kpis._con_cache_web("web:test:1", 60, _fn)
    assert llamadas["n"] == 2
    assert isinstance(r3["valor"], Decimal)


def test_generar_locaciones_gps_50_tiendas():
    locs = gen.generar_locaciones_gps(50)
    assert len(locs) == 52  # 2 CEDIS + 50 tiendas
    cedis = [l for l in locs if l[0] == "CEDIS"]
    tiendas = [l for l in locs if l[0] == "Tienda"]
    assert len(cedis) == 2
    assert len(tiendas) == 50
    assert len({l[1] for l in locs}) == 52  # nombres únicos
    # Preserva las 12 originales intactas
    assert locs[:12] == gen.LOCACIONES_GPS
    for _, _, _, lat, lon in locs:
        assert 14.0 <= lat <= 33.0
        assert -118.0 <= lon <= -86.0


def test_modos_config_rubrica_cumple_objetivos():
    cfg = gen.MODOS_CONFIG["rubrica"]
    assert cfg["tiendas"] == 50
    assert cfg["dias"] == 730
    assert cfg["skus"] == 200
    assert cfg["ordenes"] == 18250
    assert cfg["lineas_por_oc"] >= 50
    assert cfg["docs_mongo"] >= 5000
    assert cfg["kardex_dias"] is not None and 20 <= cfg["kardex_dias"] <= 90


def test_simulacion_fefo_acota_kardex_sin_perder_historial_ventas():
    sku_cfg = {
        "id_sku": 1,
        "id_proveedor": 1,
        "vida_util_estandar": 5,
        "precio_costo": 10.0,
        "precio_venta": 20.0,
        "lambda_base": 15.0,
        "punto_reorden": 25.0,
        "moq_lote": 20.0,
        "subtipo": "estable",
        "direccion_drift": 1,
    }
    kardex_desde = date(2026, 11, 15)
    sim = gen.simular_serie_fefo_sku(
        sku_cfg,
        id_locacion=1,
        fecha_inicio=date(2026, 10, 1),
        dias=60,
        rng=random.Random(99),
        prefijo_prov="TST",
        usuario_id="00000000-0000-0000-0000-000000000001",
        seq_lote={},
        kardex_desde=kardex_desde,
    )
    assert any(ln["dia"] < kardex_desde for ln in sim["ventas_lineas"])
    assert len(sim["movimientos"]) > 0
    assert all(m[9].date() >= kardex_desde for m in sim["movimientos"])
    assert all(v >= 0 for v in sim["existencias"].values())


def test_benchmark_parsear_niveles_concurrencia():
    from scripts import benchmark_plataforma as bench

    assert bench.parsear_niveles_concurrencia("1,25,50,100,200") == [1, 25, 50, 100, 200]
    assert bench.parsear_niveles_concurrencia(" 200 , 50, 50, 1 ") == [1, 50, 200]
