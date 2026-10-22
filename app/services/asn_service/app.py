"""
Microservicio 5: Inbound Logistics & ASN Reception (`svc-asn`) — FreshTrack (Flask).

Puerto: 5005
Responsabilidad:
- Recepción de Avisos Anticipados de Embarque (ASN) de proveedores en el CEDIS.
- Ingesta nativa en JSON y en XML (validado contra contracts/xsd/asn_request.xsd).
- Documentos con detalle de carga embebido e inspecciones de cadena de frío en MongoDB ('avisos_asn').
- Validación del proveedor y de los SKU contra PostgreSQL (fuente de verdad relacional).
- Eventos logísticos en Redis Streams ('ASN_INGRESADO', 'ASN_ESTADO_ACTUALIZADO', ...).
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import g, request

from app.db import query
from app.events.dispatcher import publicar_evento
from app.services import cache_service, doc_store
from app.services.common.auth import requiere_auth
from app.services.common.response import (
    ErrorApi,
    decimal_pos,
    entero,
    error_response,
    leer_cuerpo,
    meta_paginacion,
    paginacion,
    render_response,
    requerir_campos,
)
from app.services.common.servicio import crear_servicio, ejecutar
from app.services.common.swagger import documentar

app = crear_servicio(
    "svc-asn",
    "Inbound Logistics & ASN Reception Service (FreshTrack)",
    "Avisos anticipados de embarque (ASN) en JSON o XML, persistidos como documentos en MongoDB.",
    dependencias=("postgres", "mongo", "redis"),
)

ESTADOS_ASN = {"ANUNCIADO", "EN_TRANSITO", "RECIBIDO", "REVISION_CALIDAD", "CANCELADO"}
# Transiciones de negocio permitidas: un ASN recibido o cancelado ya no cambia.
TRANSICIONES = {
    "ANUNCIADO": {"EN_TRANSITO", "CANCELADO"},
    "EN_TRANSITO": {"RECIBIDO", "REVISION_CALIDAD", "CANCELADO"},
    "REVISION_CALIDAD": {"RECIBIDO", "CANCELADO"},
    "RECIBIDO": set(),
    "CANCELADO": set(),
}
RESULTADOS_INSPECCION = {"CONFORME", "NO_CONFORME", "CONFORME_CON_OBSERVACIONES"}

_ASN_EJEMPLO = {
    "folio_asn": "ASN-2026-0001",
    "id_proveedor": 1,
    "detalle_carga": [
        {"id_sku": 1, "cantidad_declarada": 120, "lote_proveedor": "LP-7781", "fecha_caducidad": "2026-11-05",
         "rango_temperatura_controlada": "2C a 6C"},
    ],
}


def _mongo():
    db = doc_store.get_mongo_db()
    if db is None:
        raise ErrorApi(503, "mongo_no_disponible", "MongoDB no está disponible en este momento.")
    return db


def _detalle_valido(detalle) -> list[dict]:
    if isinstance(detalle, dict):  # <detalle_carga><item_carga>..</item_carga></detalle_carga> con un solo hijo
        detalle = list(detalle.values())
    if not isinstance(detalle, list) or not detalle:
        raise ErrorApi(400, "campos_requeridos", "'detalle_carga' debe contener al menos una partida.")
    limpio = []
    for i, item in enumerate(detalle):
        if not isinstance(item, dict):
            raise ErrorApi(400, "parametro_invalido", f"La partida {i + 1} del detalle no es un objeto.")
        requerir_campos(item, "id_sku", "cantidad_declarada", "fecha_caducidad")
        try:
            caducidad = datetime.fromisoformat(str(item["fecha_caducidad"]))
        except ValueError as exc:
            raise ErrorApi(400, "parametro_invalido", f"fecha_caducidad inválida en la partida {i + 1} (use YYYY-MM-DD).") from exc
        limpio.append({
            "id_sku": entero(item, "id_sku", minimo=1),
            "cantidad_declarada": decimal_pos(item, "cantidad_declarada"),
            "lote_proveedor": str(item.get("lote_proveedor") or "SIN-LOTE"),
            "fecha_caducidad": caducidad,
            "rango_temperatura_controlada": str(item.get("rango_temperatura_controlada") or "2C a 6C"),
        })
    return limpio


@app.post("/api/v1/asn")
@documentar(
    "Ingesta de un ASN (JSON o XML)",
    cuerpo=_ASN_EJEMPLO,
    raiz_xml="asn_request",
    contrato_xsd="asn_request",
    respuesta={"id_mongo": "6716b0c2f1a2b3c4d5e6f708", "folio_asn": "ASN-2026-0001", "estado": "REGISTRADO"},
    raiz_respuesta="asn_creado",
    errores=("400", "409", "415"),
)
@requiere_auth("buyer", "warehouse", "supplier")
def crear_aviso_asn():
    """
    Registra el aviso en MongoDB (colección avisos_asn, índice único por folio).
    Valida que el proveedor y los SKU existan en PostgreSQL antes de insertar.
    """
    datos = leer_cuerpo("asn_request", requerido=True)
    requerir_campos(datos, "folio_asn", "id_proveedor", "detalle_carga")
    folio = str(datos["folio_asn"]).strip()
    id_proveedor = entero(datos, "id_proveedor", minimo=1)
    detalle = _detalle_valido(datos["detalle_carga"])
    estado = str(datos.get("estado") or "ANUNCIADO").upper()
    if estado not in ESTADOS_ASN:
        raise ErrorApi(400, "parametro_invalido", f"Estado inválido. Valores: {sorted(ESTADOS_ASN)}")

    if not query("SELECT 1 FROM operacion.proveedor WHERE id_proveedor = :p AND activo", p=id_proveedor):
        return error_response(409, "regla_negocio", f"El proveedor {id_proveedor} no existe o está inactivo.")
    skus = sorted({d["id_sku"] for d in detalle})
    existentes = {f["id_sku"] for f in query("SELECT id_sku FROM operacion.producto WHERE id_sku = ANY(:s)", s=skus)}
    faltan = [s for s in skus if s not in existentes]
    if faltan:
        return error_response(409, "regla_negocio", "Hay SKU que no existen en el catálogo.", {"skus_inexistentes": faltan})

    db = _mongo()
    if db.avisos_asn.find_one({"folio_asn": folio}, {"_id": 1}):
        return error_response(409, "duplicado", f"El folio {folio} ya fue registrado.")

    id_mongo = doc_store.registrar_aviso_asn(folio_asn=folio, id_proveedor=id_proveedor, detalle_carga=detalle, estado=estado)
    if not id_mongo:
        return error_response(500, "error_mongo", "No se pudo registrar el ASN en MongoDB.")

    cache_service.incrementar_contador("asn", "asn_registrado")
    publicar_evento(
        "ASN_INGRESADO",
        {"folio_asn": folio, "id_proveedor": id_proveedor, "items_count": len(detalle)},
        contexto={"user_id": g.usuario_actual.get("sub")},
    )
    return render_response({"id_mongo": id_mongo, "folio_asn": folio, "estado": "REGISTRADO"}, status=201, root_tag="asn_creado")


@app.get("/api/v1/asn")
@documentar(
    "Listado de ASN con filtros y paginación",
    consulta=[("id_proveedor", "integer", "Proveedor"), ("estado", "string", "Estado del ASN"),
              ("id_sku", "integer", "ASN que contienen el SKU"), ("pagina", "integer", "Página"), ("por_pagina", "integer", "Tamaño")],
    raiz_respuesta="asns_list",
)
@requiere_auth()
def listar_asns():
    """Consulta documentos de MongoDB filtrando por proveedor, estado o SKU (campo anidado)."""
    pagina, por_pagina, offset = paginacion()
    db = _mongo()
    filtro: dict = {}
    id_proveedor = entero(request.args, "id_proveedor", minimo=1)
    if id_proveedor:
        filtro["id_proveedor"] = id_proveedor
    if request.args.get("estado"):
        filtro["estado"] = request.args["estado"].upper()
    id_sku = entero(request.args, "id_sku", minimo=1)
    if id_sku:
        filtro["detalle_carga.id_sku"] = id_sku
    total = db.avisos_asn.count_documents(filtro)
    cursor = db.avisos_asn.find(filtro).sort([("fecha_embarque", -1)]).skip(offset).limit(por_pagina)
    lista = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        lista.append(doc)
    return render_response(
        {"paginacion": meta_paginacion(pagina, por_pagina, total), "avisos_asn": lista},
        status=200,
        root_tag="asns_list",
    )


@app.get("/api/v1/asn/<folio_asn>")
@documentar("Detalle de un ASN por folio", raiz_respuesta="asn_detalle")
@requiere_auth()
def detalle_asn(folio_asn: str):
    """Recupera el documento completo del ASN (detalle de carga e inspecciones)."""
    doc = _mongo().avisos_asn.find_one({"folio_asn": folio_asn})
    if not doc:
        return error_response(404, "no_encontrado", f"ASN {folio_asn} no encontrado.")
    doc["_id"] = str(doc["_id"])
    return render_response(doc, status=200, root_tag="asn_detalle")


@app.patch("/api/v1/asn/<folio_asn>/status")
@documentar(
    "Cambio de estado del ASN",
    cuerpo={"estado": "EN_TRANSITO"},
    raiz_xml="asn_status_request",
    respuesta={"folio_asn": "ASN-2026-0001", "estado_anterior": "ANUNCIADO", "estado": "EN_TRANSITO"},
    raiz_respuesta="asn_status",
    errores=("400", "409"),
)
@requiere_auth("warehouse")
def actualizar_estado_asn(folio_asn: str):
    """Actualiza el estado ($set) respetando las transiciones válidas del proceso de recepción."""
    datos = leer_cuerpo(requerido=True)
    requerir_campos(datos, "estado")
    nuevo = str(datos["estado"]).upper()
    if nuevo not in ESTADOS_ASN:
        raise ErrorApi(400, "parametro_invalido", f"Estado inválido. Valores: {sorted(ESTADOS_ASN)}")
    db = _mongo()
    doc = db.avisos_asn.find_one({"folio_asn": folio_asn}, {"estado": 1})
    if not doc:
        return error_response(404, "no_encontrado", f"ASN {folio_asn} no encontrado.")
    actual = doc.get("estado", "ANUNCIADO")
    if nuevo not in TRANSICIONES.get(actual, set()):
        return error_response(409, "transicion_invalida", f"No se puede pasar de {actual} a {nuevo}.",
                              {"permitidas": sorted(TRANSICIONES.get(actual, set()))})
    doc_store.actualizar_estado_asn(folio_asn, nuevo)
    publicar_evento("ASN_ESTADO_ACTUALIZADO", {"folio_asn": folio_asn, "de": actual, "a": nuevo})
    return render_response({"folio_asn": folio_asn, "estado_anterior": actual, "estado": nuevo}, status=200, root_tag="asn_status")


@app.get("/api/v1/asn/analytics/summary")
@documentar("Carga consolidada por proveedor (pipeline de agregación)", raiz_respuesta="asn_analytics")
@requiere_auth()
def analitica_resumen_asn():
    """Pipeline $unwind + $group + $sort sobre avisos_asn para consolidar la carga por proveedor."""
    _mongo()
    resumen = doc_store.analitica_carga_asn_por_proveedor()
    return render_response({"total_grupos": len(resumen), "carga_consolidada": resumen}, status=200, root_tag="asn_analytics")


@app.post("/api/v1/asn/<folio_asn>/inspection")
@documentar(
    "Agrega una inspección de calidad / cadena de frío",
    cuerpo={"resultado": "CONFORME", "temperatura_registrada": 4.2, "observaciones": "Sellos íntegros"},
    raiz_xml="inspeccion_request",
    respuesta={"folio_asn": "ASN-2026-0001", "status": "INSPECCION_AGREGADA", "resultado": "CONFORME"},
    raiz_respuesta="asn_inspection",
    errores=("400",),
)
@requiere_auth("warehouse")
def registrar_inspeccion_asn(folio_asn: str):
    """Agrega la evidencia con $push sobre el documento del ASN (operación atómica en MongoDB)."""
    datos = leer_cuerpo(requerido=True)
    resultado = str(datos.get("resultado") or "CONFORME").upper()
    if resultado not in RESULTADOS_INSPECCION:
        raise ErrorApi(400, "parametro_invalido", f"Resultado inválido. Valores: {sorted(RESULTADOS_INSPECCION)}")
    temperatura = None
    if datos.get("temperatura_registrada") not in (None, ""):
        try:
            temperatura = float(datos["temperatura_registrada"])
        except (TypeError, ValueError) as exc:
            raise ErrorApi(400, "parametro_invalido", "'temperatura_registrada' debe ser numérica.") from exc
    _mongo()
    ok = doc_store.agregar_inspeccion_asn(
        folio_asn,
        inspector=g.usuario_actual.get("email"),
        resultado=resultado,
        temperatura_registrada=temperatura,
        observaciones=str(datos.get("observaciones") or ""),
    )
    if not ok:
        return error_response(404, "no_encontrado", f"ASN {folio_asn} no encontrado en MongoDB.")
    publicar_evento("ASN_INSPECCION_REGISTRADA", {"folio_asn": folio_asn, "resultado": resultado, "temperatura": temperatura})
    return render_response({"folio_asn": folio_asn, "status": "INSPECCION_AGREGADA", "resultado": resultado}, status=201, root_tag="asn_inspection")


if __name__ == "__main__":
    ejecutar(app, "ASN_SERVICE_PORT", 5005)
