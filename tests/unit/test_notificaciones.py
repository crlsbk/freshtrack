"""Centro de notificaciones de la web (app/domain/notificaciones.py y /notificaciones)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.domain import notificaciones as dom
from app.events.dispatcher import publicar_evento
from app.services import cache_service, doc_store

GERENTE_1 = {"id_usuario": "g1", "rol_clave": "store_manager", "id_locacion": 1}
GERENTE_2 = {"id_usuario": "g2", "rol_clave": "store_manager", "id_locacion": 2}
PLANEADOR = {"id_usuario": "p1", "rol_clave": "planner", "id_locacion": None}
COMPRADOR = {"id_usuario": "b1", "rol_clave": "buyer", "id_locacion": None}
PROVEEDOR = {"id_usuario": "s1", "rol_clave": "supplier", "id_locacion": None, "id_proveedor": 7}
AUDITOR = {"id_usuario": "a1", "rol_clave": "auditor", "id_locacion": None}

ALERTA_MONGO = {"_id": "a" * 24, "tipo": "RIESGO_PRE_MERMA", "criticidad": "CRITICAL",
                "mensaje": "Lote de 'Leche' vence en 1 día(s).",
                "generada_en": datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc), "id_locacion": 1}


@pytest.fixture()
def fuentes(redis_falso, monkeypatch):
    """Redis falso con eventos reales del dispatcher; Mongo y PostgreSQL simulados."""
    llamadas_mongo = []
    monkeypatch.setattr(doc_store, "get_mongo_db", lambda: object())

    def listar_mongo(**kw):
        llamadas_mongo.append(kw)
        return [dict(ALERTA_MONGO)] if kw.get("id_locacion") in (None, 1) else []

    monkeypatch.setattr(doc_store, "listar_alertas_operativas", listar_mongo)
    monkeypatch.setattr(dom, "query", lambda sql, **p: [])
    publicar_evento("TRANSFERENCIA_SOLICITADA", {"id_transferencia": "t1", "cantidad": 5},
                    contexto={"user_id": "otro", "location_id": 1})
    publicar_evento("DESCUENTO_APROBADO", {"id_descuento": "d1", "estado": "APROBADO"},
                    contexto={"user_id": "p1", "location_id": 2})
    publicar_evento("ORDEN_COMPRA_EMITIDA", {"folio": "OC-1", "id_proveedor": 7, "total": 100},
                    contexto={"user_id": "b1"})
    publicar_evento("ORDEN_COMPRA_EMITIDA", {"folio": "OC-2", "id_proveedor": 9, "total": 50},
                    contexto={"user_id": "b1"})
    publicar_evento("VENTA_REGISTRADA", {"x": 1}, contexto={"user_id": "otro"})  # no notificable
    return {"redis": redis_falso, "mongo": llamadas_mongo}


def _tipos(res):
    return [n["tipo"] for n in res["items"]]


def test_filtra_por_rol_y_tienda(fuentes):
    g1 = _tipos(dom.listar(dict(GERENTE_1)))
    assert "TRANSFERENCIA_SOLICITADA" in g1 and "RIESGO_PRE_MERMA" in g1
    assert "DESCUENTO_APROBADO" not in g1  # fue en la tienda 2
    assert "ORDEN_COMPRA_EMITIDA" not in g1  # no es de su rol
    g2 = _tipos(dom.listar(dict(GERENTE_2)))
    assert "DESCUENTO_APROBADO" in g2 and "TRANSFERENCIA_SOLICITADA" not in g2
    assert "RIESGO_PRE_MERMA" not in g2
    assert fuentes["mongo"][-1]["id_locacion"] == 2  # Mongo se consulta con la tienda del usuario


def test_no_se_notifica_lo_que_hizo_uno_mismo(fuentes):
    p = _tipos(dom.listar(dict(PLANEADOR)))
    assert "TRANSFERENCIA_SOLICITADA" in p and "DESCUENTO_APROBADO" not in p
    assert "ORDEN_COMPRA_EMITIDA" not in _tipos(dom.listar(dict(COMPRADOR)))


def test_proveedor_solo_ve_sus_ordenes(fuentes):
    res = dom.listar(dict(PROVEEDOR))
    assert [n["mensaje"] for n in res["items"]] == ["Folio: OC-1 · Total: 100"]


def test_rol_sin_alertas_no_consulta_mongo(fuentes):
    assert dom.listar(dict(AUDITOR))["items"] == []
    assert fuentes["mongo"] == []


def test_orden_mas_reciente_primero(fuentes):
    fechas = [n["fecha"] for n in dom.listar(dict(GERENTE_1))["items"]]
    assert fechas == sorted(fechas, reverse=True)


def test_marcar_una_y_todas_y_conteo_cacheado(fuentes):
    u = dict(GERENTE_1)
    res = dom.listar(u)
    assert res["no_leidas"] == 2 and dom.contar_no_leidas(u) == 2
    assert fuentes["redis"].ttl("notif:no_leidas:g1") > 0
    assert dom.marcar_leidas(u, [res["items"][0]["id"]])
    assert fuentes["redis"].get("notif:no_leidas:g1") is None  # se invalida al marcar
    assert dom.contar_no_leidas(u) == 1
    assert dom.marcar_todas(u)
    assert dom.contar_no_leidas(u) == 0
    assert all(n["leida"] for n in dom.listar(u)["items"])
    assert fuentes["redis"].ttl("notif:leidas:g1") > 0


def test_mongo_caido_muestra_el_resto(fuentes, monkeypatch):
    monkeypatch.setattr(doc_store, "get_mongo_db", lambda: None)
    res = dom.listar(dict(GERENTE_1))
    assert _tipos(res) == ["TRANSFERENCIA_SOLICITADA"]
    assert res["fuentes"]["alertas_mongo"] is False and res["fuentes"]["eventos"] is True


def test_postgres_caido_no_rompe(fuentes, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("sin conexión")

    monkeypatch.setattr(dom, "query", falla)
    res = dom.listar(dict(GERENTE_1))
    assert res["fuentes"]["alertas"] is False and res["items"]


def test_redis_caido_muestra_alertas_y_no_guarda(fuentes, monkeypatch):
    monkeypatch.setattr(cache_service, "get_redis_client", lambda: None)
    u = dict(GERENTE_1)
    res = dom.listar(u)
    assert _tipos(res) == ["RIESGO_PRE_MERMA"] and res["fuentes"]["eventos"] is False
    assert dom.contar_no_leidas(u) == 1
    assert dom.marcar_leidas(u, ["x"]) is False


def test_alertas_postgres_se_incluyen(fuentes, monkeypatch):
    monkeypatch.setattr(dom, "query", lambda sql, **p: [{
        "id_alerta": "u1", "tipo": "LOTE_VENCIDO", "severidad": "CRITICA", "mensaje": "Lote vencido",
        "fecha_generacion": datetime(2026, 11, 24, 10, 0)}])
    items = {n["id"]: n for n in dom.listar(dict(GERENTE_1))["items"]}
    assert items["alerta:u1"]["titulo"] == "Lote vencido" and items["alerta:u1"]["severidad"] == "CRITICA"


# --- Vista web ---------------------------------------------------------------
def test_vista_lista_y_marca(fuentes, monkeypatch):
    monkeypatch.setenv("AGREGADOS_AUTO_REFRESCO", "false")
    from app import create_app, security

    monkeypatch.setattr(security, "sesion_web_vigente", lambda: True)
    c = create_app().test_client()
    with c.session_transaction() as s:
        s.update({"user_id": "g1", "role": "store_manager", "id_locacion": 1, "jti": "j",
                  "user_name": "Gerente Uno", "role_label": "Gerente"})
    html = c.get("/notificaciones").get_data(as_text=True)
    assert "Transferencia solicitada" in html and 'class="topbar-badge">2<' in html
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    r = c.post("/notificaciones/leer", data={"csrf_token": token})
    assert r.status_code == 302
    assert "Todo leído" in c.get("/notificaciones").get_data(as_text=True)
