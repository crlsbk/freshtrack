"""Mercancía por recibir: clasificación de envíos y permisos por rol."""

from datetime import date

from app.domain import por_recibir as pr
from app.navegacion import VISTAS_POR_ROL, endpoint_de

HOY = date(2026, 11, 24)


def test_completo_es_recibido_aunque_haya_pasado_la_fecha():
    assert pr.situacion(100, 100, True, date(2026, 11, 1), HOY) == pr.RECIBIDO
    assert pr.situacion(100, 99.6, True, None, HOY) == pr.RECIBIDO  # tolerancia 0.5 %


def test_fecha_vencida_sin_completar_es_atrasado():
    assert pr.situacion(100, 0, False, date(2026, 11, 23), HOY) == pr.ATRASADO
    assert pr.situacion(100, 40, True, date(2026, 11, 20), HOY) == pr.ATRASADO


def test_parcial_en_camino_y_por_enviar():
    assert pr.situacion(100, 40, True, date(2026, 11, 26), HOY) == pr.PARCIAL
    assert pr.situacion(100, 0, True, date(2026, 11, 24), HOY) == pr.EN_CAMINO  # llega hoy: no atrasado
    assert pr.situacion(100, 0, False, None, HOY) == pr.POR_ENVIAR


def test_agrupa_por_orden_y_tienda_y_ordena_lo_urgente_primero(monkeypatch):
    filas = [
        {"id_oc": "a", "folio": "OC-1", "estado_oc": "ENVIADA", "fecha_entrega_estimada": date(2026, 11, 20),
         "fecha_creacion": date(2026, 11, 10), "proveedor": "Lácteos", "id_locacion": 1, "locacion": "San Pedro",
         "producto": "Crema", "unidad_medida": "pz", "pedido": 60, "recibido": 0},
        {"id_oc": "a", "folio": "OC-1", "estado_oc": "ENVIADA", "fecha_entrega_estimada": date(2026, 11, 20),
         "fecha_creacion": date(2026, 11, 10), "proveedor": "Lácteos", "id_locacion": 1, "locacion": "San Pedro",
         "producto": "Leche", "unidad_medida": "pz", "pedido": 40, "recibido": 0},
        {"id_oc": "b", "folio": "OC-2", "estado_oc": "EMITIDA", "fecha_entrega_estimada": date(2026, 11, 28),
         "fecha_creacion": date(2026, 11, 22), "proveedor": "Pan", "id_locacion": 1, "locacion": "San Pedro",
         "producto": "Bolillo", "unidad_medida": "pz", "pedido": 50, "recibido": 0},
    ]
    monkeypatch.setattr(pr, "query", lambda *a, **k: filas)
    monkeypatch.setattr(pr, "_embarques", lambda ids: {"b": {"folio_asn": "ASN-9", "fecha_embarque": "2026-11-23T10:00:00"}})
    r = pr.listar_por_recibir(id_locacion=1, hoy=HOY)
    assert [e["folio"] for e in r["envios"]] == ["OC-1", "OC-2"]
    atrasado, camino = r["envios"]
    assert atrasado["situacion"] == pr.ATRASADO and atrasado["pedido"] == 100 and len(atrasado["productos"]) == 2
    assert atrasado["dias_para_llegar"] == -4
    assert camino["situacion"] == pr.EN_CAMINO and camino["folio_asn"] == "ASN-9"
    assert camino["fecha_embarque"] == date(2026, 11, 23)
    assert r["proxima_llegada"] == date(2026, 11, 28)
    assert r["conteo"][pr.ATRASADO] == 1


def test_sin_mongo_la_vista_sigue(monkeypatch):
    monkeypatch.setattr(pr.doc_store, "get_mongo_db", lambda: None)
    assert pr._embarques(["x"]) == {}


def test_vista_visible_para_gerente_y_almacen_no_para_proveedor():
    assert endpoint_de("incoming") == "operacion.por_recibir"
    for rol in ("store_manager", "warehouse", "buyer", "admin"):
        assert "incoming" in VISTAS_POR_ROL[rol], rol
    for rol in ("supplier", "auditor", "planner"):
        assert "incoming" not in VISTAS_POR_ROL[rol], rol
