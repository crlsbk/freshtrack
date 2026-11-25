"""Mercancía por recibir: qué viene en camino a cada tienda y cuándo debería llegar.

Une la orden de compra (PostgreSQL: fecha de entrega estimada y avance por línea)
con el aviso de embarque del proveedor (MongoDB: fecha de embarque). Si MongoDB
no responde, la vista sigue funcionando y solo pierde el dato de embarque.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from app.db import a_float, query
from app.services import doc_store

logger = logging.getLogger(__name__)

# Situación de cada envío, de la más urgente a la menos.
ATRASADO = "ATRASADO"
POR_ENVIAR = "POR_ENVIAR"
EN_CAMINO = "EN_CAMINO"
PARCIAL = "PARCIAL"
RECIBIDO = "RECIBIDO"

TOLERANCIA_COMPLETO = 0.995   # igual que el avance de la OC en recepcion.py
DIAS_HISTORIAL = 14          # cuánto tiempo se siguen mostrando los ya recibidos


def _como_fecha(valor) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def situacion(pedido: float, recibido: float, embarcado: bool, eta: date | None, hoy: date) -> str:
    """Clasifica un envío. Atrasado solo aplica a lo que aún no llega completo."""
    if pedido > 0 and recibido >= pedido * TOLERANCIA_COMPLETO:
        return RECIBIDO
    if eta is not None and eta < hoy:
        return ATRASADO
    if recibido > 0:
        return PARCIAL
    return EN_CAMINO if embarcado else POR_ENVIAR


def _embarques(ids_oc: list[str]) -> dict[str, dict]:
    """Último aviso de embarque (ASN) por orden de compra, desde MongoDB."""
    if not ids_oc:
        return {}
    db = doc_store.get_mongo_db()
    if db is None:
        return {}
    try:
        docs = db.avisos_asn.find(
            {"id_oc": {"$in": ids_oc}},
            {"id_oc": 1, "folio_asn": 1, "fecha_embarque": 1, "estado": 1},
        ).sort([("fecha_embarque", 1)])
        return {str(d.get("id_oc")): d for d in docs}
    except Exception as exc:  # MongoDB caído: la vista se degrada, no se rompe
        logger.warning("No se pudieron leer los embarques para «Por recibir»: %s", exc)
        return {}


def listar_por_recibir(id_locacion: int | None = None, hoy: date | None = None) -> dict:
    """Envíos (orden de compra × tienda destino) pendientes o recibidos hace poco."""
    hoy = hoy or date.today()
    filtro_loc = "AND d.id_locacion_destino = :loc" if id_locacion else ""
    params: dict = {"dias": DIAS_HISTORIAL}
    if id_locacion:
        params["loc"] = int(id_locacion)
    filas = query(
        f"""
        SELECT oc.id_oc::text AS id_oc, oc.folio, oc.estado AS estado_oc,
               oc.fecha_entrega_estimada, oc.fecha_creacion,
               pr.razon_social AS proveedor,
               d.id_locacion_destino AS id_locacion, l.nombre AS locacion,
               p.nombre AS producto, p.unidad_medida,
               d.cantidad_unidades AS pedido, d.cantidad_recibida AS recibido
        FROM operacion.orden_compra oc
        JOIN operacion.orden_compra_detalle d ON d.id_oc = oc.id_oc
        JOIN operacion.proveedor pr ON pr.id_proveedor = oc.id_proveedor
        JOIN operacion.locacion l ON l.id_locacion = d.id_locacion_destino
        JOIN operacion.producto p ON p.id_sku = d.id_sku
        WHERE oc.estado <> 'CANCELADA'
          AND (oc.estado <> 'RECIBIDA' OR oc.fecha_creacion >= now() - make_interval(days => :dias))
          {filtro_loc}
        ORDER BY oc.fecha_entrega_estimada NULLS LAST, oc.folio, l.nombre, p.nombre
        LIMIT 600
        """,
        **params,
    )

    envios: dict[tuple[str, int], dict] = {}
    for f in filas:
        clave = (f["id_oc"], int(f["id_locacion"]))
        e = envios.get(clave)
        if e is None:
            e = envios[clave] = {
                "id_oc": f["id_oc"],
                "folio": f["folio"],
                "estado_oc": f["estado_oc"],
                "proveedor": f["proveedor"],
                "id_locacion": int(f["id_locacion"]),
                "locacion": f["locacion"],
                "fecha_entrega_estimada": _como_fecha(f["fecha_entrega_estimada"]),
                "fecha_creacion": _como_fecha(f["fecha_creacion"]),
                "pedido": 0.0,
                "recibido": 0.0,
                "productos": [],
            }
        ped, rec = a_float(f["pedido"]), a_float(f["recibido"])
        e["pedido"] += ped
        e["recibido"] += rec
        e["productos"].append({"producto": f["producto"], "unidad_medida": f["unidad_medida"],
                               "pedido": ped, "recibido": rec})

    embarques = _embarques(sorted({e["id_oc"] for e in envios.values()}))
    resultado = []
    for e in envios.values():
        asn = embarques.get(e["id_oc"])
        e["folio_asn"] = asn.get("folio_asn") if asn else None
        e["fecha_embarque"] = _como_fecha(asn.get("fecha_embarque")) if asn else None
        e["situacion"] = situacion(e["pedido"], e["recibido"], asn is not None, e["fecha_entrega_estimada"], hoy)
        e["avance_pct"] = round(min(100.0, e["recibido"] / e["pedido"] * 100), 1) if e["pedido"] else 0.0
        eta = e["fecha_entrega_estimada"]
        e["dias_para_llegar"] = (eta - hoy).days if eta else None
        resultado.append(e)

    orden = {ATRASADO: 0, PARCIAL: 1, EN_CAMINO: 2, POR_ENVIAR: 3, RECIBIDO: 4}
    resultado.sort(key=lambda x: (orden[x["situacion"]],
                                  x["fecha_entrega_estimada"] or date.max, x["folio"], x["locacion"]))
    conteo = {s: sum(1 for x in resultado if x["situacion"] == s) for s in orden}
    proxima = min((x["fecha_entrega_estimada"] for x in resultado
                   if x["situacion"] in (EN_CAMINO, POR_ENVIAR, PARCIAL) and x["fecha_entrega_estimada"]
                   and x["fecha_entrega_estimada"] >= hoy), default=None)
    return {"envios": resultado, "conteo": conteo, "proxima_llegada": proxima, "hoy": hoy}
