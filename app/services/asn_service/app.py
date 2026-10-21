"""
Microservicio 5: Inbound Logistics & ASN Reception (`svc-asn`) — FreshTrack (Flask).

Puerto: 5005
Responsabilidad:
- Recepción de Avisos Anticipados de Embarque (ASN) de proveedores mayoristas en CEDIS.
- Ingesta de manifiestos nativa en JSON y XML (GS1 XML Despatch Advice / EDI).
- Almacenamiento de documentos anidados y control de cadena de frío en MongoDB ('avisos_asn').
- Emisión de eventos logísticos a Redis Streams ('ASN_INGRESADO', 'ASN_RECIBIDO').
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import Flask, g, request

from app.config import Config
from app.db import a_int
from app.events.dispatcher import publicar_evento
from app.services import cache_service, doc_store
from app.services.common.auth import requiere_auth
from app.services.common.response import render_response
from app.services.common.swagger import registrar_openapi

app = Flask(__name__)
app.config.from_object(Config)


@app.get("/health")
def health():
    mongo_ok = False
    try:
        db = doc_store.get_mongo_db()
        mongo_ok = bool(db is not None)
    except Exception:
        pass

    redis_ok = False
    try:
        r = cache_service.get_redis_client()
        redis_ok = bool(r and r.ping())
    except Exception:
        pass

    estado = "HEALTHY" if (mongo_ok and redis_ok) else "DEGRADED"
    return render_response({
        "service": "svc-asn",
        "status": estado,
        "dependencies": {"mongo": mongo_ok, "redis": redis_ok},
    }, status=200 if estado == "HEALTHY" else 503, root_tag="service_health")


def _parsear_asn_xml(xml_texto: str) -> dict:
    """Parsea un manifiesto ASN en formato XML estándar."""
    raiz = ET.fromstring(xml_texto)
    folio = raiz.findtext("folio_asn") or raiz.attrib.get("folio", "ASN-XML-001")
    id_prov = int(raiz.findtext("id_proveedor") or 1)
    estado = raiz.findtext("estado") or "ANUNCIADO"
    
    detalle_carga = []
    detalles = raiz.findall(".//item_carga") or raiz.findall(".//item")
    for d in detalles:
        sku = int(d.findtext("id_sku") or 1)
        cant = float(d.findtext("cantidad_declarada") or 0.0)
        lote_prov = d.findtext("lote_proveedor") or "LOTE-PROV"
        rango_temp = d.findtext("rango_temperatura_controlada") or "2C a 6C"
        cad_str = d.findtext("fecha_caducidad")
        cad_dt = datetime.fromisoformat(cad_str) if cad_str else datetime.now(timezone.utc)
        
        detalle_carga.append({
            "id_sku": sku,
            "cantidad_declarada": cant,
            "lote_proveedor": lote_prov,
            "fecha_caducidad": cad_dt,
            "rango_temperatura_controlada": rango_temp,
        })
    
    return {
        "folio_asn": folio,
        "id_proveedor": id_prov,
        "estado": estado,
        "detalle_carga": detalle_carga,
    }


@app.post("/api/v1/asn")
@requiere_auth("admin", "buyer", "warehouse", "supplier")
def crear_aviso_asn():
    """
    Ingesta de un Aviso Anticipado de Embarque (ASN).
    Soporta 'Content-Type: application/xml' o 'Content-Type: application/json'.
    Persiste el documento con detalle embebido en MongoDB.
    """
    content_type = request.headers.get("Content-Type", "").lower()
    if "xml" in content_type:
        try:
            datos = _parsear_asn_xml(request.data.decode("utf-8"))
        except Exception as exc:
            return render_response({"error": "xml_parse_error", "detalle": str(exc)}, status=400, root_tag="error_asn")
    else:
        datos = request.get_json(silent=True) or {}

    folio = datos.get("folio_asn")
    id_proveedor = a_int(datos.get("id_proveedor"), 0)
    detalle = datos.get("detalle_carga", [])

    if not folio or not id_proveedor or not detalle:
        return render_response({"error": "bad_request", "mensaje": "folio_asn, id_proveedor y detalle_carga son obligatorios."}, status=400, root_tag="error_asn")

    # Formatear fechas si vienen en string
    for item in detalle:
        if isinstance(item.get("fecha_caducidad"), str):
            item["fecha_caducidad"] = datetime.fromisoformat(item["fecha_caducidad"])

    id_mongo = doc_store.registrar_aviso_asn(
        folio_asn=folio,
        id_proveedor=id_proveedor,
        detalle_carga=detalle,
        estado=datos.get("estado", "ANUNCIADO"),
    )

    if not id_mongo:
        return render_response({"error": "error_mongo", "mensaje": "Fallo al registrar ASN en MongoDB o folio duplicado."}, status=500, root_tag="error_asn")

    publicar_evento(
        "ASN_INGRESADO",
        {"folio_asn": folio, "id_proveedor": id_proveedor, "items_count": len(detalle)},
        contexto={"user_id": g.usuario_actual.get("sub")},
    )

    return render_response({"id_mongo": id_mongo, "folio_asn": folio, "estado": "REGISTRADO"}, status=201, root_tag="asn_creado")


@app.get("/api/v1/asn")
@requiere_auth()
def listar_asns():
    """Consulta de avisos ASN desde MongoDB con soporte JSON y XML."""
    db = doc_store.get_mongo_db()
    if db is None:
        return render_response({"error": "db_unavailable"}, status=503, root_tag="asns_list")

    id_proveedor = a_int(request.args.get("id_proveedor"), 0) or None
    estado = request.args.get("estado")
    filtro = {}
    if id_proveedor:
        filtro["id_proveedor"] = id_proveedor
    if estado:
        filtro["estado"] = estado

    cursor = db.avisos_asn.find(filtro).sort([("fecha_embarque", -1)]).limit(30)
    lista = []
    for doc in cursor:
        doc["_id"] = str(doc["_id"])
        lista.append(doc)

    return render_response({"total": len(lista), "avisos_asn": lista}, status=200, root_tag="asns_list")


@app.get("/api/v1/asn/<folio_asn>")
@requiere_auth()
def detalle_asn(folio_asn: str):
    """Consulta de un aviso ASN por folio único."""
    db = doc_store.get_mongo_db()
    if db is None:
        return render_response({"error": "db_unavailable"}, status=503, root_tag="asn_detalle")

    doc = db.avisos_asn.find_one({"folio_asn": folio_asn})
    if not doc:
        return render_response({"error": "not_found", "mensaje": f"ASN {folio_asn} no encontrado."}, status=404, root_tag="asn_detalle")

    doc["_id"] = str(doc["_id"])
    return render_response(doc, status=200, root_tag="asn_detalle")


@app.patch("/api/v1/asn/<folio_asn>/status")
@requiere_auth("admin", "warehouse")
def actualizar_estado_asn(folio_asn: str):
    """Actualiza el estado de recepción del ASN."""
    datos = request.get_json(silent=True) or {}
    nuevo_estado = datos.get("estado", "").upper()

    estados_validos = {"ANUNCIADO", "EN_TRANSITO", "RECIBIDO", "REVISION_CALIDAD", "CANCELADO"}
    if nuevo_estado not in estados_validos:
        return render_response({"error": "invalid_status", "estados_validos": list(estados_validos)}, status=400, root_tag="asn_status")

    db = doc_store.get_mongo_db()
    res = db.avisos_asn.update_one({"folio_asn": folio_asn}, {"$set": {"estado": nuevo_estado}})
    if res.matched_count == 0:
        return render_response({"error": "not_found"}, status=404, root_tag="asn_status")

    publicar_evento("ASN_ESTADO_ACTUALIZADO", {"folio_asn": folio_asn, "nuevo_estado": nuevo_estado})
    return render_response({"folio_asn": folio_asn, "estado": nuevo_estado}, status=200, root_tag="asn_status")


@app.get("/api/v1/asn/analytics/summary")
@requiere_auth()
def analitica_resumen_asn():
    """Ejecuta pipeline de agregación en MongoDB ($unwind + $group) para consolidar carga ASN por proveedor."""
    resumen = doc_store.analitica_carga_asn_por_proveedor()
    return render_response({"total_grupos": len(resumen), "carga_consolidada": resumen}, status=200, root_tag="asn_analytics")


@app.post("/api/v1/asn/<folio_asn>/inspection")
@requiere_auth("admin", "warehouse", "quality")
def registrar_inspeccion_asn(folio_asn: str):
    """Agrega atómicamente una evidencia/inspección de calidad a un ASN con operador $push en MongoDB."""
    datos = request.get_json(silent=True) or {}
    inspector = datos.get("inspector") or g.usuario_actual.get("sub", "auditor_cedis")
    resultado = datos.get("resultado", "CONFORME")
    temperatura = datos.get("temperatura_registrada")
    if temperatura is not None:
        try:
            temperatura = float(temperatura)
        except (ValueError, TypeError):
            temperatura = None
    obs = datos.get("observaciones", "")

    ok = doc_store.agregar_inspeccion_asn(
        folio_asn,
        inspector=inspector,
        resultado=resultado,
        temperatura_registrada=temperatura,
        observaciones=obs,
    )
    if not ok:
        return render_response({"error": "not_found", "mensaje": f"ASN {folio_asn} no encontrado en MongoDB."}, status=404, root_tag="asn_inspection")

    publicar_evento("ASN_INSPECCION_REGISTRADA", {"folio_asn": folio_asn, "resultado": resultado, "temperatura": temperatura})
    return render_response({"folio_asn": folio_asn, "status": "INSPECCION_AGREGADA", "resultado": resultado}, status=201, root_tag="asn_inspection")


registrar_openapi(
    app,
    titulo="Inbound Logistics & ASN Reception Service (FreshTrack)",
    descripcion="Microservicio para recepción de avisos anticipados de embarque (ASN) en XML y JSON persistidos en MongoDB.",
    version="1.0.0",
    paths={
        "/health": {
            "get": {"summary": "Healthcheck del microservicio", "responses": {"200": {"description": "Estado saludable"}}}
        },
        "/api/v1/asn": {
            "post": {
                "summary": "Ingesta de ASN (JSON / XML EDI)",
                "security": [{"bearerAuth": []}],
                "responses": {"201": {"description": "ASN registrado en MongoDB"}},
            },
            "get": {
                "summary": "Listado de avisos ASN",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "Lista de avisos"}},
            },
        },
        "/api/v1/asn/{folio_asn}": {
            "get": {
                "summary": "Detalle de ASN por folio",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "Detalle del aviso"}},
            }
        },
        "/api/v1/asn/{folio_asn}/status": {
            "patch": {
                "summary": "Cambio de estado del ASN",
                "security": [{"bearerAuth": []}],
                "responses": {"200": {"description": "Estado actualizado"}},
            }
        },
    },
)

if __name__ == "__main__":
    port = int(os.getenv("ASN_SERVICE_PORT", "5005"))
    app.run(host="0.0.0.0", port=port, debug=False)
