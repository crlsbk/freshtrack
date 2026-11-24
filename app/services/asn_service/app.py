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

from flask import Response, g, request

from app.db import query
from app.domain import recepcion as dom_recepcion
from app.events.dispatcher import publicar_evento
from app.services import cache_service, doc_store
from app.services.common.auth import requiere_auth, usuario_desde_token, validar_alcance_locacion
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
    validar_uuid,
)
from app.services.common.rate_limit import limite_tasa
from app.services.common.servicio import crear_servicio, ejecutar
from app.services.common.swagger import documentar

app = crear_servicio(
    "svc-asn",
    "Inbound Logistics & ASN Reception Service (FreshTrack)",
    "Avisos anticipados de embarque (ASN) en JSON o XML, persistidos como documentos en MongoDB.",
    dependencias=("postgres", "mongo", "redis", "bucket"),
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
            "fecha_produccion": str(item["fecha_produccion"])[:10] if item.get("fecha_produccion") else None,
            "fecha_caducidad": caducidad,
            "rango_temperatura_controlada": str(item.get("rango_temperatura_controlada") or "2C a 6C"),
            "id_locacion_destino": entero(item, "id_locacion_destino", minimo=1) if item.get("id_locacion_destino") else None,
            "cantidad_lotes": entero(item, "cantidad_lotes", minimo=1) if item.get("cantidad_lotes") else None,
            "codigo_rfid_epc": str(item.get("codigo_rfid_epc") or "").strip() or None,
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
    Valida que el proveedor y los SKU existan en PostgreSQL antes de insertar y,
    cuando incluye tiendas destino, genera etiquetas QR firmadas (FT1).
    """
    datos = leer_cuerpo("asn_request", requerido=True)
    requerir_campos(datos, "folio_asn", "id_proveedor", "detalle_carga")
    folio = str(datos["folio_asn"]).strip()
    id_proveedor = entero(datos, "id_proveedor", minimo=1)
    folio_oc = str(datos.get("folio_oc") or "").strip() or None
    id_oc = str(datos.get("id_oc") or "").strip() or None
    transporte = datos.get("transporte") if isinstance(datos.get("transporte"), dict) else None
    detalle = _detalle_valido(datos["detalle_carga"])
    estado = str(datos.get("estado") or "ANUNCIADO").upper()
    if estado not in ESTADOS_ASN:
        raise ErrorApi(400, "parametro_invalido", f"Estado inválido. Valores: {sorted(ESTADOS_ASN)}")

    if not query("SELECT 1 FROM operacion.proveedor WHERE id_proveedor = :p AND activo", p=id_proveedor):
        return error_response(409, "regla_negocio", f"El proveedor {id_proveedor} no existe o está inactivo.")
    skus = sorted({d["id_sku"] for d in detalle})
    skus_rows = query("SELECT id_sku, nombre, codigo_gtin, unidad_medida FROM operacion.producto WHERE id_sku = ANY(:s)", s=skus)
    info_skus = {f["id_sku"]: f for f in skus_rows}
    faltan = [s for s in skus if s not in info_skus]
    if faltan:
        return error_response(409, "regla_negocio", "Hay SKU que no existen en el catálogo.", {"skus_inexistentes": faltan})

    locs = sorted({int(d["id_locacion_destino"]) for d in detalle if d.get("id_locacion_destino")})
    info_tiendas = (
        {r["id_locacion"]: r for r in query("SELECT id_locacion, nombre FROM operacion.locacion WHERE id_locacion = ANY(:l)", l=locs)}
        if locs
        else {}
    )
    etiquetas = dom_recepcion.construir_etiquetas_para_asn(
        folio_oc=folio_oc,
        detalle_carga=detalle,
        info_skus=info_skus,
        info_tiendas=info_tiendas,
    )

    db = _mongo()
    if db.avisos_asn.find_one({"folio_asn": folio}, {"_id": 1}):
        return error_response(409, "duplicado", f"El folio {folio} ya fue registrado.")

    id_mongo = doc_store.registrar_aviso_asn(
        folio_asn=folio,
        id_proveedor=id_proveedor,
        detalle_carga=detalle,
        estado=estado,
        folio_oc=folio_oc,
        id_oc=id_oc,
        transporte=transporte,
        etiquetas=etiquetas or None,
    )
    if not id_mongo:
        return error_response(500, "error_mongo", "No se pudo registrar el ASN en MongoDB.")

    cache_service.incrementar_contador("asn", "asn_registrado")
    publicar_evento(
        "ASN_INGRESADO",
        {"folio_asn": folio, "folio_oc": folio_oc, "id_proveedor": id_proveedor, "items_count": len(detalle)},
        contexto={"user_id": g.usuario_actual.get("sub")},
    )
    return render_response(
        {"id_mongo": id_mongo, "folio_asn": folio, "estado": "REGISTRADO", "etiquetas": etiquetas},
        status=201,
        root_tag="asn_creado",
    )


@app.get("/api/v1/asn")
@documentar(
    "Listado de ASN con filtros y paginación",
    consulta=[("id_proveedor", "integer", "Proveedor"), ("estado", "string", "Estado del ASN"),
              ("folio_oc", "string", "Folio de orden de compra"), ("id_locacion_destino", "integer", "Tienda destino"),
              ("id_sku", "integer", "ASN que contienen el SKU"), ("pagina", "integer", "Página"), ("por_pagina", "integer", "Tamaño")],
    raiz_respuesta="asns_list",
)
@requiere_auth()
def listar_asns():
    """Consulta documentos de MongoDB filtrando por proveedor, estado, OC, tienda o SKU."""
    pagina, por_pagina, offset = paginacion()
    db = _mongo()
    filtro: dict = {}
    id_proveedor = entero(request.args, "id_proveedor", minimo=1)
    if id_proveedor:
        filtro["id_proveedor"] = id_proveedor
    if request.args.get("estado"):
        filtro["estado"] = request.args["estado"].upper()
    if request.args.get("folio_oc"):
        filtro["folio_oc"] = request.args["folio_oc"].strip()
    id_loc_dest = entero(request.args, "id_locacion_destino", minimo=1)
    if id_loc_dest:
        filtro["detalle_carga.id_locacion_destino"] = id_loc_dest
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


@app.post("/api/v1/asn/from-purchase-order")
@documentar(
    "Genera un Aviso de Embarque (ASN), etiquetas QR firmadas y Hoja QR PDF desde una Orden de Compra",
    cuerpo={
        "id_oc": "00000000-0000-0000-0000-000000000001",
        "transporte": {"chofer": "Carlos Mendoza", "placas": "NL-8492-A", "temperatura_salida_c": 3.5},
        "partidas": [{"id_sku": 1, "id_locacion_destino": 3, "cantidad_declarada": 50, "lote_proveedor": "LP-01", "fecha_caducidad": "2026-12-10"}],
    },
    raiz_xml="asn_from_oc_request",
    raiz_respuesta="asn_from_oc_response",
    errores=("400", "403", "404", "409"),
    exito="201",
)
@requiere_auth("supplier", "buyer")
def crear_despacho_desde_oc_api():
    """Genera ASN en tránsito, códigos QR firmados y Hoja de Empaque PDF en Cloud Object Storage."""
    datos = leer_cuerpo(requerido=True)
    requerir_campos(datos, "id_oc", "partidas")
    id_oc = validar_uuid(datos["id_oc"], "id_oc")
    partidas = datos["partidas"] if isinstance(datos["partidas"], list) else []
    transporte = datos.get("transporte") if isinstance(datos.get("transporte"), dict) else {}
    try:
        res = dom_recepcion.crear_despacho_desde_oc(
            id_oc=id_oc,
            partidas=partidas,
            usuario=usuario_desde_token(),
            transporte=transporte,
            folio_asn=datos.get("folio_asn"),
        )
    except dom_recepcion.ErrorRecepcion as err:
        return error_response(err.http_status, err.codigo, str(err), err.detalles or None)
    cache_service.incrementar_contador("asn", "asn_from_oc")
    return render_response(res, status=201, root_tag="asn_from_oc_response")


@app.get("/api/v1/asn/labels")
@app.get("/api/v1/asn/labels/<path:codigo>")
@documentar(
    "Consulta y valida una etiqueta QR / NFC / RFID antes de confirmar recepción en almacén",
    consulta=[("codigo", "string", "Payload QR FT1|... o folio corto FTL-..."), ("id_locacion", "integer", "Tienda donde se escanea")],
    raiz_respuesta="asn_label_lookup",
    errores=("400", "404"),
)
@requiere_auth("warehouse", "store_manager", "buyer", "supplier")
def consultar_etiqueta_api(codigo: str | None = None):
    """Valida firma HMAC y retorna los datos esperados del lote y alertas de recepción."""
    codigo_val = request.args.get("codigo") or codigo
    if not codigo_val:
        return error_response(400, "campos_requeridos", "Debes enviar el código de la etiqueta QR.")
    loc_usuario = (getattr(g, "contexto", None) or {}).get("location_id") or entero(request.args, "id_locacion", minimo=1)
    try:
        info = dom_recepcion.consultar_etiqueta_para_recepcion(codigo_val, id_locacion_usuario=loc_usuario)
    except dom_recepcion.ErrorRecepcion as err:
        return error_response(err.http_status, err.codigo, str(err), err.detalles or None)
    return render_response(info, status=200, root_tag="asn_label_lookup")


@app.get("/api/v1/asn/<folio_asn>/labels-pdf")
@documentar("Descarga el documento PDF con la Hoja de Empaque y Etiquetas QR del ASN", exito="200", errores=("404",))
@requiere_auth("supplier", "buyer", "warehouse", "store_manager")
def descargar_hoja_qr_api(folio_asn: str):
    """Retorna el PDF de la Hoja de Empaque con QR vectoriales desde Cloud Object Storage."""
    descargar = request.args.get("download") == "1"
    try:
        pdf_bytes, _ = dom_recepcion.obtener_pdf_hoja_asn(folio_asn, usuario=usuario_desde_token())
    except dom_recepcion.ErrorRecepcion as err:
        return error_response(err.http_status, err.codigo, str(err))
    disp = "attachment" if descargar else "inline"
    return Response(
        pdf_bytes,
        status=200,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{folio_asn}_etiquetas.pdf"', "Cache-Control": "no-store"},
    )



@app.post("/api/v1/asn/<folio_asn>/send-email")
@documentar(
    "Envía por correo la Hoja de Empaque con etiquetas QR del ASN (PDF adjunto)",
    cuerpo={"correo": "proveedor@ejemplo.com", "mensaje": "Favor de imprimir las etiquetas."},
    raiz_xml="send_email_request",
    contrato_xsd="send_email_request",
    respuesta={"folio_asn": "ASN-2026-000123", "folio_oc": "OC-2026-000045", "correo_envio": "proveedor@ejemplo.com",
               "estado_envio_correo": "ENVIADO_SMTP", "enviado_real": True},
    raiz_respuesta="send_email_result",
    errores=("400", "403", "404", "502"),
    exito="200",
)
@requiere_auth("supplier", "buyer", "warehouse", "store_manager")
@limite_tasa(limite=10, ventana_segundos=60)
def enviar_hoja_qr_correo_api(folio_asn: str):
    """Adjunta el PDF de etiquetas QR y lo envía al correo indicado vía SMTP (Mailpit en Docker)."""
    datos = leer_cuerpo("send_email_request", requerido=True)
    requerir_campos(datos, "correo")
    try:
        res = dom_recepcion.enviar_hoja_asn_correo(
            folio_asn,
            str(datos["correo"]),
            usuario=usuario_desde_token(),
            mensaje_extra=datos.get("mensaje"),
        )
    except dom_recepcion.ErrorRecepcion as err:
        return error_response(err.http_status, err.codigo, str(err))
    return render_response(res, status=200, root_tag="send_email_result")

if __name__ == "__main__":
    ejecutar(app, "ASN_SERVICE_PORT", 5005)
