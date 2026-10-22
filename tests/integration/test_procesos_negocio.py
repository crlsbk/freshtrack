"""
Procesos de negocio distribuidos sobre PostgreSQL, MongoDB y Redis:
catálogo (CRUD + caché), saga de venta FEFO, reservas, mermas, ASN, alertas,
planeación y auditoría.
"""

from __future__ import annotations

import uuid

from app.db import a_float, one
from app.services import cache_service
from tests.integration.conftest import TIENDA, bearer


def _stock(id_lote: str) -> tuple[float, float]:
    f = one(
        "SELECT cantidad_disponible, cantidad_reservada FROM operacion.existencia WHERE id_lote = CAST(:l AS uuid) AND id_locacion = :t",
        l=id_lote,
        t=TIENDA,
    )
    return a_float(f["cantidad_disponible"]), a_float(f["cantidad_reservada"])


# --- svc-catalog ----------------------------------------------------------------
def test_crud_de_producto_con_xml_y_cache(svc, tokens):
    h = bearer(tokens["buyer"])
    nombre = f"PYTEST Fresa {uuid.uuid4().hex[:6]}"
    xml = (
        f"<producto_request><nombre>{nombre}</nombre><categoria>Frutas</categoria>"
        "<precio_costo>20</precio_costo><precio_venta>35.5</precio_venta><vida_util_estandar>5</vida_util_estandar></producto_request>"
    )
    r = svc["catalog"].post("/api/v1/catalog/products", data=xml, content_type="application/xml", headers={**h, "Accept": "application/xml"})
    assert r.status_code == 201 and b"<producto_creado>" in r.data
    id_sku = one("SELECT id_sku FROM operacion.producto WHERE nombre = :n", n=nombre)["id_sku"]

    assert svc["catalog"].get(f"/api/v1/catalog/products/{id_sku}").get_json()["precio_venta"] == 35.5
    r = svc["catalog"].patch(f"/api/v1/catalog/products/{id_sku}", json={"precio_venta": 30}, headers=h)
    assert r.status_code == 200 and r.get_json()["precio_venta"] == 30
    r = svc["catalog"].put(f"/api/v1/catalog/products/{id_sku}", json={"precio_venta": 31}, headers=h)
    assert r.status_code == 400  # PUT exige el recurso completo
    r = svc["catalog"].patch(f"/api/v1/catalog/products/{id_sku}", json={"precio_venta": 5}, headers=h)
    assert r.status_code == 409  # regla de negocio: venta < costo

    assert svc["catalog"].delete(f"/api/v1/catalog/products/{id_sku}", headers=h).status_code == 403  # solo admin
    assert svc["catalog"].delete(f"/api/v1/catalog/products/{id_sku}", headers=bearer(tokens["admin"])).status_code == 200
    assert one("SELECT activo FROM operacion.producto WHERE id_sku = :s", s=id_sku)["activo"] is False
    assert svc["catalog"].get("/api/v1/catalog/products/99999999").status_code == 404


def test_listado_paginado_usa_cache_redis(svc):
    q = f"?categoria=Lacteos&por_pagina=5&pagina=1&q={uuid.uuid4().hex[:4]}"
    primero = svc["catalog"].get("/api/v1/catalog/products" + q).get_json()
    segundo = svc["catalog"].get("/api/v1/catalog/products" + q).get_json()
    assert primero["fuente"] == "postgres" and segundo["fuente"] == "redis_cache"
    assert set(primero["paginacion"]) == {"pagina", "por_pagina", "total", "total_paginas"}


# --- svc-commercial + svc-inventory: Saga de venta --------------------------------
def test_saga_de_venta_descuenta_inventario_fefo(svc, tokens, lote_con_stock):
    id_lote = lote_con_stock["id_lote"]
    disp_antes, _ = _stock(id_lote)
    h = bearer(tokens["store_manager"])

    cola = svc["inventory"].get(f"/api/v1/inventory/fefo-queue/1/{TIENDA}", headers=h).get_json()["lotes_fefo"]
    fechas = [l["fecha_caducidad"] for l in cola]
    assert fechas == sorted(fechas)

    total_antes = sum(l["cantidad_disponible"] - l["cantidad_reservada"] for l in cola)
    r = svc["commercial"].post("/api/v1/commercial/checkout", json={"id_locacion": TIENDA, "lineas": [{"id_sku": 1, "cantidad": 2}]}, headers=h)
    assert r.status_code == 201, r.get_json()
    cola_despues = svc["inventory"].get(f"/api/v1/inventory/fefo-queue/1/{TIENDA}", headers=h).get_json()["lotes_fefo"]
    assert round(total_antes - sum(l["cantidad_disponible"] - l["cantidad_reservada"] for l in cola_despues), 2) == 2
    # El lote nuevo caduca en 10 días: solo se toca si los anteriores no alcanzaron.
    assert _stock(id_lote)[0] <= disp_antes

    ventas = svc["commercial"].get(f"/api/v1/commercial/sales?id_locacion={TIENDA}&por_pagina=5", headers=h).get_json()["ventas"]
    assert ventas, "La venta debe aparecer en el historial"


def test_saga_rechaza_stock_insuficiente_sin_dejar_reservas(svc, tokens, lote_con_stock):
    h = bearer(tokens["store_manager"])
    _, reservado_antes = _stock(lote_con_stock["id_lote"])
    r = svc["commercial"].post("/api/v1/commercial/checkout", json={"id_locacion": TIENDA, "lineas": [{"id_sku": 1, "cantidad": 10_000_000}]}, headers=h)
    assert r.status_code == 409 and r.get_json()["error"] == "venta_rechazada"
    assert _stock(lote_con_stock["id_lote"])[1] == reservado_antes  # compensación aplicada


def test_checkout_valida_entrada(svc, tokens):
    h = bearer(tokens["store_manager"])
    assert svc["commercial"].post("/api/v1/commercial/checkout", json={"id_locacion": TIENDA, "lineas": [{"id_sku": 1, "cantidad": -1}]}, headers=h).status_code == 400
    r = svc["commercial"].post("/api/v1/commercial/checkout", data="<checkout_request><lineas/></checkout_request>", content_type="application/xml", headers=h)
    assert r.status_code == 400 and r.get_json()["error"] == "xml_no_cumple_contrato"


def test_reserva_y_compensacion_por_saga_id(svc, tokens, lote_con_stock):
    h = bearer(tokens["warehouse"])
    saga = f"pytest-{uuid.uuid4().hex[:8]}"
    # Se reserva todo lo disponible del SKU para forzar que el lote nuevo participe.
    cola = svc["inventory"].get(f"/api/v1/inventory/fefo-queue/1/{TIENDA}", headers=h).get_json()["lotes_fefo"]
    total = round(sum(l["cantidad_disponible"] - l["cantidad_reservada"] for l in cola), 2)
    _, reservado_antes = _stock(lote_con_stock["id_lote"])

    r = svc["inventory"].post("/api/v1/inventory/reserve-fefo", json={"id_locacion": TIENDA, "saga_id": saga, "lineas": [{"id_sku": 1, "cantidad": total}]}, headers=h)
    assert r.status_code == 200, r.get_json()
    assert _stock(lote_con_stock["id_lote"])[1] > reservado_antes
    assert cache_service.obtener_temporal("reservation", saga) is not None

    r = svc["inventory"].post("/api/v1/inventory/cancel-reservation", json={"saga_id": saga}, headers=h)
    assert r.status_code == 200
    assert _stock(lote_con_stock["id_lote"])[1] == reservado_antes
    # La reserva temporal se consumió: compensar dos veces no es posible.
    assert svc["inventory"].post("/api/v1/inventory/cancel-reservation", json={"saga_id": saga}, headers=h).status_code == 404


def test_merma_descuenta_y_valida_causa(svc, tokens, lote_con_stock):
    h = bearer(tokens["warehouse"])
    id_lote = lote_con_stock["id_lote"]
    disp_antes, _ = _stock(id_lote)
    r = svc["commercial"].post("/api/v1/commercial/shrinkage", json={"id_lote": id_lote, "id_locacion": TIENDA, "cantidad": 1, "causa": "DANO"}, headers=h)
    assert r.status_code == 201, r.get_json()
    assert _stock(id_lote)[0] == disp_antes - 1
    assert svc["commercial"].post("/api/v1/commercial/shrinkage", json={"id_lote": id_lote, "id_locacion": TIENDA, "cantidad": 1, "causa": "INVENTADA"}, headers=h).status_code == 400
    assert svc["commercial"].post("/api/v1/commercial/shrinkage", json={"id_lote": id_lote, "id_locacion": TIENDA, "cantidad": 999999, "causa": "DANO"}, headers=h).status_code == 409


def test_carrito_temporal_con_ttl(svc, tokens):
    h = bearer(tokens["store_manager"])
    cart = f"caja-{uuid.uuid4().hex[:6]}"
    assert svc["commercial"].put(f"/api/v1/commercial/cart/{cart}", json={"lineas": [{"id_sku": 1, "cantidad": 1}]}, headers=h).status_code == 200
    r = svc["commercial"].get(f"/api/v1/commercial/cart/{cart}", headers=h).get_json()
    assert 0 < r["ttl_restante"] <= 900
    assert svc["commercial"].delete(f"/api/v1/commercial/cart/{cart}", headers=h).status_code == 200
    assert svc["commercial"].get(f"/api/v1/commercial/cart/{cart}", headers=h).status_code == 404


# --- svc-asn (MongoDB) -------------------------------------------------------------
def test_ciclo_de_vida_asn_en_mongodb(svc, tokens):
    h = bearer(tokens["warehouse"])
    folio = f"ASN-PYTEST-{uuid.uuid4().hex[:6]}"
    xml = (
        f"<asn_request><folio_asn>{folio}</folio_asn><id_proveedor>1</id_proveedor><detalle_carga>"
        "<item_carga><id_sku>1</id_sku><cantidad_declarada>40</cantidad_declarada><fecha_caducidad>2026-12-01</fecha_caducidad></item_carga>"
        "<item_carga><id_sku>2</id_sku><cantidad_declarada>15</cantidad_declarada><fecha_caducidad>2026-11-20</fecha_caducidad></item_carga>"
        "</detalle_carga></asn_request>"
    )
    r = svc["asn"].post("/api/v1/asn", data=xml, content_type="application/xml", headers=h)
    assert r.status_code == 201, r.get_json()
    assert svc["asn"].post("/api/v1/asn", data=xml, content_type="application/xml", headers=h).status_code == 409  # folio duplicado

    detalle = svc["asn"].get(f"/api/v1/asn/{folio}", headers=h).get_json()
    assert len(detalle["detalle_carga"]) == 2 and detalle["estado"] == "ANUNCIADO"

    assert svc["asn"].patch(f"/api/v1/asn/{folio}/status", json={"estado": "RECIBIDO"}, headers=h).status_code == 409
    assert svc["asn"].patch(f"/api/v1/asn/{folio}/status", json={"estado": "EN_TRANSITO"}, headers=h).status_code == 200
    assert svc["asn"].post(f"/api/v1/asn/{folio}/inspection", json={"resultado": "CONFORME", "temperatura_registrada": 4.1}, headers=h).status_code == 201
    assert len(svc["asn"].get(f"/api/v1/asn/{folio}", headers=h).get_json()["inspecciones"]) == 1

    lista = svc["asn"].get("/api/v1/asn?id_sku=2&por_pagina=50", headers=h).get_json()
    assert any(a["folio_asn"] == folio for a in lista["avisos_asn"])
    assert svc["asn"].get("/api/v1/asn/NO-EXISTE", headers=h).status_code == 404


def test_asn_valida_contra_postgres(svc, tokens):
    h = bearer(tokens["buyer"])
    cuerpo = {"folio_asn": f"ASN-X-{uuid.uuid4().hex[:6]}", "id_proveedor": 1,
              "detalle_carga": [{"id_sku": 99999999, "cantidad_declarada": 1, "fecha_caducidad": "2026-12-01"}]}
    r = svc["asn"].post("/api/v1/asn", json=cuerpo, headers=h)
    assert r.status_code == 409 and r.get_json()["detalles"]["skus_inexistentes"] == [99999999]


# --- svc-alerts / svc-planning / svc-audit -----------------------------------------
def test_escaneo_y_atencion_de_alertas(svc, tokens):
    h = bearer(tokens["store_manager"])
    r = svc["alerts"].post(f"/api/v1/alerts/scan?id_locacion={TIENDA}&dias=30", headers=h)
    assert r.status_code == 200
    activas = svc["alerts"].get(f"/api/v1/alerts/active?id_locacion={TIENDA}", headers=h).get_json()["alertas"]
    if activas:
        id_mongo = activas[0].get("_id") or activas[0].get("id")
        assert svc["alerts"].patch(f"/api/v1/alerts/{id_mongo}/resolve", headers=h).status_code == 200
    assert svc["alerts"].patch("/api/v1/alerts/zzz/resolve", headers=h).status_code == 400
    assert svc["alerts"].get("/api/v1/alerts/active?criticidad=PANICO", headers=h).status_code == 400


def test_planeacion_ordenes_y_contexto_hibrido(svc, tokens):
    h = bearer(tokens["buyer"])
    r = svc["planning"].get("/api/v1/planning/replenishment/orders?por_pagina=5", headers=h)
    assert r.status_code == 200 and "paginacion" in r.get_json()
    falso = str(uuid.uuid4())
    assert svc["planning"].post(f"/api/v1/planning/replenishment/orders/{falso}/approve", json={}, headers=h).status_code == 404
    ctx = svc["planning"].get("/api/v1/planning/sku/1/full-context?id_locacion=3", headers=h).get_json()
    assert ctx["producto_postgres"]["id_sku"] == 1 and "contexto_mongo" in ctx
    assert svc["planning"].post("/api/v1/planning/forecast/run", json={"metodo": "NO_EXISTE"}, headers=h).status_code == 400


def test_auditoria_registra_con_identidad_del_jwt(svc, tokens):
    marca = f"pytest-{uuid.uuid4().hex[:8]}"
    r = svc["audit"].post("/api/v1/audit/log", json={"accion": "REVISION_CUMPLIMIENTO", "descripcion": marca},
                          headers=bearer(tokens["auditor"], **{"X-User-Email": "suplantado@x.mx"}))
    assert r.status_code == 201
    fila = one("SELECT usuario_email FROM auditoria.bitacora_eventos WHERE descripcion = :d", d=marca)
    assert fila["usuario_email"] == "auditor@freshtrack.mx"
    eventos = svc["audit"].get("/api/v1/audit/events?accion=REVISION_CUMPLIMIENTO&por_pagina=5", headers=bearer(tokens["auditor"])).get_json()
    assert eventos["paginacion"]["total"] >= 1


def test_trazabilidad_de_lote(svc, tokens, lote_con_stock):
    r = svc["audit"].get(f"/api/v1/audit/traceability/{lote_con_stock['id_lote']}", headers=bearer(tokens["auditor"]))
    assert r.status_code == 200
    assert r.get_json()["movimientos_kardex"][0]["tipo"] == "RECEPCION"


def test_health_de_los_ocho_servicios(svc):
    for nombre, cliente in svc.items():
        r = cliente.get("/health")
        assert r.status_code in (200, 503), nombre
        assert r.get_json()["dependencies"]["postgres" if nombre not in ("asn",) else "mongo"] in (True, False)
