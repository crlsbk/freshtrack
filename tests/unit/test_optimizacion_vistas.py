"""Pruebas de la segunda ronda de optimización: MV de demanda, caché web, paginación."""

from __future__ import annotations

import os
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

os.environ.setdefault("SECRET_KEY", "clave-de-pruebas-optimizacion-0123456789")
os.environ.setdefault("JWT_SECRET_KEY", "jwt-de-pruebas-optimizacion-0123456789")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_backend:x@127.0.0.1:1/inexistente")

from app.domain import cache_web  # noqa: E402
from app.domain import pronostico as dom_pron  # noqa: E402
from app.domain import transferencias as dom_tr  # noqa: E402
from app.services import cache_service  # noqa: E402

SQL_08 = (RAIZ / "sql" / "08_optimizacion.sql").read_text(encoding="utf-8")


def test_08_conserva_columnas_y_usa_historico_materializado():
    vista = SQL_08.split("CREATE OR REPLACE VIEW analitica.v_demanda_diaria AS")[1].split(";")[0]
    assert "analitica.mv_demanda_diaria_hist" in vista
    assert "UNION ALL" in vista
    for col in ("id_sku", "id_locacion", "fecha", "cantidad", "ingreso"):
        assert col in vista
    # Nunca datos incompletos: si el histórico está sucio se agrega todo en vivo.
    assert "sucio" in vista and "-infinity" in vista


def test_08_indices_y_refresco():
    for idx in ("idx_vd_venta", "idx_lote_disp_caducidad", "idx_lote_proveedor", "idx_tr_lote",
                "idx_dc_lote_loc_estado", "idx_bitacora_desc_trgm", "uq_mv_demanda_serie"):
        assert idx in SQL_08
    assert "REFRESH MATERIALIZED VIEW CONCURRENTLY" in SQL_08
    assert "SECURITY DEFINER" in SQL_08
    assert "REFERENCING NEW TABLE" in SQL_08


def test_06_no_pisa_la_vista_materializada():
    sql06 = (RAIZ / "sql" / "06_views.sql").read_text(encoding="utf-8")
    bloque = sql06.split("CREATE OR REPLACE VIEW analitica.v_demanda_diaria AS")[0][-1200:]
    assert "mv_demanda_diaria_hist" in bloque and "IF NOT EXISTS" in bloque


def test_con_cache_web_hit_miss_y_desactivable(redis_falso, monkeypatch):
    llamadas = []

    def _fn():
        llamadas.append(1)
        return {"n": 1}

    assert cache_web.con_cache_web("web:test:x", 60, _fn) == {"n": 1}
    assert cache_web.con_cache_web("web:test:x", 60, _fn) == {"n": 1}
    assert len(llamadas) == 1
    cache_web.invalidar("web:test:*")
    cache_web.con_cache_web("web:test:x", 60, _fn, con_lock=True)
    assert len(llamadas) == 2
    monkeypatch.setenv("CACHE_WEB_ACTIVA", "false")
    cache_web.con_cache_web("web:test:x", 60, _fn)
    assert len(llamadas) == 3


def test_con_lock_espera_al_otro_worker(redis_falso, monkeypatch):
    # Otro worker tiene el lock y publica el valor: no se recalcula.
    redis_falso.set("lock:calc:web:test:lock", "otro", ex=30)
    publicado = {"hecho": False}

    def _get_json(clave):
        if not publicado["hecho"]:
            publicado["hecho"] = True
            return None
        return {"listo": True}

    monkeypatch.setattr(cache_service, "get_json", _get_json)
    monkeypatch.setattr("app.domain.cache_web.time.sleep", lambda s: None)
    r = cache_web.con_cache_web("web:test:lock", 60, lambda: (_ for _ in ()).throw(AssertionError("no debía calcular")), con_lock=True)
    assert r == {"listo": True}


def test_decorador_invalida(redis_falso):
    redis_falso.set("web:triaje:eval:all:7", "{}")

    @cache_web.invalida("web:triaje:*")
    def _escribe():
        return 42

    assert _escribe() == 42
    assert redis_falso.get("web:triaje:eval:all:7") is None


def test_contar_cacheado_ignora_paginacion(redis_falso, monkeypatch):
    vistas = []
    monkeypatch.setattr("app.db.escalar", lambda sql, **p: vistas.append((sql, p)) or 7)
    assert cache_web.contar_cacheado("FROM t WHERE a = :a", {"a": 1, "lim": 20, "off": 0}) == 7
    assert cache_web.contar_cacheado("FROM t WHERE a = :a", {"a": 1, "lim": 20, "off": 40}) == 7
    assert len(vistas) == 1 and vistas[0][1] == {"a": 1}


def test_demandas_en_lote_cae_al_promedio(monkeypatch):
    consultas = []

    def _query(sql, **p):
        consultas.append(sql)
        if "forecast_result" in sql:
            return [{"id_sku": 1, "id_locacion": 10, "total": 70, "dias": 7}]
        return [{"id_sku": 2, "id_locacion": 10, "promedio": 3.5}]

    monkeypatch.setattr(dom_pron, "query", _query)
    r = dom_pron.demandas_diarias_vigentes([(1, 10), (2, 10), (3, 10), (1, 10)])
    assert r == {(1, 10): 10.0, (2, 10): 3.5, (3, 10): 0.0}
    assert len(consultas) == 2


def test_situaciones_en_lote_equivale_a_calculo_por_par(monkeypatch):
    lotes = [
        {"id_sku": 1, "id_locacion": 10, "id_lote": "a", "codigo_lote_prov": "A", "cantidad_disponible": 30,
         "dias_restantes": 2, "clasificacion": "CRITICO", "costo_unitario": 1},
        {"id_sku": 1, "id_locacion": 10, "id_lote": "b", "codigo_lote_prov": "B", "cantidad_disponible": 50,
         "dias_restantes": 9, "clasificacion": "NORMAL", "costo_unitario": 1},
    ]
    monkeypatch.setattr(dom_tr, "query", lambda sql, **p: [dict(x) for x in lotes])
    monkeypatch.setattr(dom_tr, "config_valor", lambda c, d=None: "5")
    monkeypatch.setattr(dom_tr.pronostico, "demandas_diarias_vigentes", lambda pares: {p: 4.0 for p in pares})
    r = dom_tr.situaciones_en_lote([1], [10, 11], 7)
    esperado = dom_tr._calcular_situacion(10, [{k: v for k, v in x.items() if k not in ("id_sku", "id_locacion")} for x in lotes], 4.0, 5, 7)
    assert {k: v for k, v in r[(1, 10)].items() if k != "lotes"} == {k: v for k, v in esperado.items() if k != "lotes"}
    assert r[(1, 11)]["fisico"] == 0 and r[(1, 11)]["faltante"] == 28.0
