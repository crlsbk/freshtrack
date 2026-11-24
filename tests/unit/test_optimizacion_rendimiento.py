"""Pruebas unitarias de optimización de consultas SQL, caché Redis y anti-deadlock."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
import os
from pathlib import Path
import random
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

os.environ.setdefault("SECRET_KEY", "clave-de-pruebas-optimizacion-0123456789")
os.environ.setdefault("JWT_SECRET_KEY", "jwt-de-pruebas-optimizacion-0123456789")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_backend:x@127.0.0.1:1/inexistente")

from app.domain import alertas as dom_alertas  # noqa: E402
from app.domain import inventario as dom_inv  # noqa: E402
from app.domain import pronostico as dom_pron  # noqa: E402
from app.domain import ventas as dom_ventas  # noqa: E402
from app.repos import catalogo as repo_cat  # noqa: E402
from app.services import cache_service  # noqa: E402
from scripts import generar_dataset_masivo as gen  # noqa: E402


def test_vistas_sql_no_invocan_fn_clasificar_riesgo_por_fila():
    sql = (RAIZ / "sql" / "06_views.sql").read_text(encoding="utf-8")
    bloque_inv = sql.split("CREATE OR REPLACE VIEW operacion.v_inventario_lote AS")[1].split(
        "CREATE OR REPLACE VIEW analitica.v_demanda_diaria AS"
    )[0]
    assert "operacion.fn_clasificar_riesgo(" not in bloque_inv
    assert bloque_inv.count("LEFT JOIN operacion.regla_riesgo") >= 6


def test_bloquear_lotes_vencidos_usa_throttle_redis_y_skip_locked(monkeypatch):
    almacen: dict[str, object] = {"web:inv:expire_scan_reciente": {"ts": True}}
    sql_capturado: list[str] = []

    class _FakeRedis:
        pass

    class _FakeResult:
        def mappings(self):
            return self

        def all(self):
            return []

    class _FakeConn:
        def execute(self, stmt, *args, **kwargs):
            sql_capturado.append(str(stmt))
            return _FakeResult()

    @contextmanager
    def _fake_tx(**kwargs):
        yield _FakeConn()

    monkeypatch.setenv("CACHE_WEB_ACTIVA", "true")
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(cache_service, "get_json", lambda k: almacen.get(k))
    monkeypatch.setattr(cache_service, "set_json", lambda k, v, ttl_segundos=300: almacen.__setitem__(k, v) or True)
    monkeypatch.setattr(cache_service, "invalidar_patron", lambda p: 0)
    monkeypatch.setattr(dom_inv, "transaccion", _fake_tx)

    # Con throttle vigente y forzar=False no toca PostgreSQL
    res_skip = dom_inv.bloquear_lotes_vencidos(forzar=False)
    assert res_skip == {"bloqueados": 0, "lotes": []}
    assert sql_capturado == []

    # Con forzar=True ejecuta UPDATE con FOR UPDATE SKIP LOCKED
    res_forzado = dom_inv.bloquear_lotes_vencidos(forzar=True)
    assert res_forzado == {"bloqueados": 0, "lotes": []}
    assert len(sql_capturado) == 1
    assert "FOR UPDATE SKIP LOCKED" in sql_capturado[0]


def test_cache_aside_en_pronostico_alertas_y_ventas(monkeypatch):
    almacen: dict[str, object] = {}

    class _FakeRedis:
        pass

    monkeypatch.setenv("CACHE_WEB_ACTIVA", "true")
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(cache_service, "get_json", lambda k: almacen.get(k))
    monkeypatch.setattr(cache_service, "set_json", lambda k, v, ttl_segundos=60: almacen.__setitem__(k, v) or True)
    monkeypatch.setattr(cache_service, "incrementar_contador", lambda *a, **kw: 1)

    # 1. evaluar_salud_modelos
    conteo_pron = {"n": 0}
    monkeypatch.setattr(dom_pron, "modelos_activos_por_tienda", lambda id_locacion=None: [])
    monkeypatch.setattr(dom_pron, "escalar", lambda sql, **kw: date(2026, 11, 20))

    def _fake_pron_q(sql, **kw):
        conteo_pron["n"] += 1
        return []

    monkeypatch.setattr(dom_pron, "query", _fake_pron_q)
    s1 = dom_pron.evaluar_salud_modelos()
    s2 = dom_pron.evaluar_salud_modelos()
    assert conteo_pron["n"] == 1
    assert s1 == s2

    # 2. resumen_alertas
    conteo_al = {"n": 0}

    def _fake_al_q(sql, **kw):
        conteo_al["n"] += 1
        return [{"tipo": "LOTE_POR_VENCER", "severidad": "ALTA", "n": 3}]

    monkeypatch.setattr(dom_alertas, "query", _fake_al_q)
    a1 = dom_alertas.resumen_alertas()
    a2 = dom_alertas.resumen_alertas()
    assert conteo_al["n"] == 1
    assert a1["total"] == 3 and a1 == a2

    # 3. resumen_ventas
    conteo_ven = {"n": 0}

    def _fake_ven_one(sql, **kw):
        conteo_ven["n"] += 1
        if "FROM operacion.venta_detalle" not in sql:
            return {"tickets": 10, "ingreso": Decimal("1250.50")}
        return {"unidades": Decimal("40"), "lineas": 12}

    monkeypatch.setattr(dom_ventas, "one", _fake_ven_one)
    v1 = dom_ventas.resumen_ventas()
    v2 = dom_ventas.resumen_ventas()
    assert conteo_ven["n"] == 2  # solo 1 corrida (2 consultas cab+det), la segunda viene de Redis
    assert v1["tickets"] == 10
    assert v1 == v2


def test_listar_usuarios_aplica_limit_por_defecto(monkeypatch):
    llamadas: list[tuple[str, dict]] = []

    def _fake_q(sql, **params):
        llamadas.append((sql, params))
        return []

    monkeypatch.setattr(repo_cat, "query", _fake_q)
    repo_cat.listar_usuarios()
    assert len(llamadas) == 1
    sql, params = llamadas[0]
    assert "LIMIT :limite" in sql
    assert params["limite"] == 150


def test_simulacion_fefo_marca_lotes_agotados_en_memoria():
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
    fecha_ini = date(2026, 10, 1)
    dias = 45
    fecha_fin = fecha_ini + timedelta(days=dias)
    sim = gen.simular_serie_fefo_sku(
        sku_cfg,
        id_locacion=1,
        fecha_inicio=fecha_ini,
        dias=dias,
        rng=random.Random(77),
        prefijo_prov="TST",
        usuario_id="00000000-0000-0000-0000-000000000001",
        seq_lote={},
    )
    estados_cero = {
        lt[10]
        for lt in sim["lotes"]
        if sim["existencias"].get((lt[0], 1), 0.0) <= 0.0
    }
    assert len(estados_cero) >= 1
    assert estados_cero.issubset({"AGOTADO", "MERMA"})

    for lt in sim["lotes"]:
        saldo = sim["existencias"].get((lt[0], 1), 0.0)
        if lt[10] == "DISPONIBLE":
            assert saldo > 0.0
            assert lt[6] >= fecha_fin
