"""
Dominio de Despachos de Proveedor (ASN + Etiquetas QR) y Recepción Escaneada en Almacén.

Conecta el ciclo completo Procure-to-Receive:
    Orden de Compra (OC) -> Aviso de Embarque + Hoja QR PDF (ASN) -> Escaneo en Muelle (FEFO).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, one, query, transaccion
from app.domain import compras as dom_compras
from app.domain import etiquetas_qr
from app.events.dispatcher import publicar_evento
from app.services import doc_store, mailer, object_storage

logger = logging.getLogger("freshtrack.recepcion")

ACCIONES_CALIDAD_VALIDAS = {"ACEPTAR_DISPONIBLE", "ACEPTAR_CUARENTENA", "RECHAZAR_MUELLE"}
RESULTADOS_INSPECCION_VALIDOS = {"CONFORME", "NO_CONFORME", "CONFORME_CON_OBSERVACIONES"}
MEDIOS_LECTURA_VALIDOS = {"QR", "NFC", "RFID", "MANUAL"}


class ErrorRecepcion(ValueError):
    """Error de dominio con código semántico y estatus HTTP sugerido."""

    def __init__(self, mensaje: str, *, codigo: str = "regla_negocio", http_status: int = 400, detalles: dict | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.http_status = http_status
        self.detalles = detalles or {}


def generar_codigo_etiqueta() -> str:
    """Genera un identificador corto único de etiqueta agnóstico de medio (QR/NFC/RFID)."""
    return f"FTL-{date.today():%y%m%d}-{uuid.uuid4().hex[:6].upper()}"


def _siguiente_folio_asn() -> str:
    prefijo = f"ASN-{date.today():%Y%m%d}-"
    row = one(
        "SELECT folio FROM operacion.reporte_documento "
        "WHERE tipo_reporte = 'ETIQUETA_ASN' AND folio LIKE :pref "
        "ORDER BY folio DESC LIMIT 1",
        pref=prefijo + "%",
    )
    seq = 1
    if row and row["folio"].startswith(prefijo):
        try:
            seq = int(row["folio"].split("-")[-1]) + 1
        except ValueError:
            seq = 1

    db = doc_store.get_mongo_db()
    if db is not None:
        while db.avisos_asn.find_one({"folio_asn": f"{prefijo}{seq:04d}"}, {"_id": 1}):
            seq += 1
    return f"{prefijo}{seq:04d}"


def _parse_fecha(valor: object, defecto: date | None = None) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor or "").strip()
    if not s:
        return defecto
    return datetime.fromisoformat(s[:10]).date()


def construir_etiquetas_para_asn(
    *,
    folio_oc: str | None,
    detalle_carga: list[dict],
    info_skus: dict[int, dict],
    info_tiendas: dict[int, dict],
) -> list[dict]:
    """Construye etiquetas firmadas (FT1) para cada partida que tenga id_locacion_destino."""
    etiquetas: list[dict] = []
    for item in detalle_carga:
        loc_id = item.get("id_locacion_destino")
        if not loc_id:
            continue
        loc_id = int(loc_id)
        sku_id = int(item["id_sku"])
        codigo = str(item.get("codigo_etiqueta") or generar_codigo_etiqueta()).strip()
        sku_info = info_skus.get(sku_id) or {}
        loc_info = info_tiendas.get(loc_id) or {}
        f_cad = item.get("fecha_caducidad")
        f_prod = item.get("fecha_produccion")
        etiquetas.append(
            {
                "codigo_etiqueta": codigo,
                "qr_payload": etiquetas_qr.construir_payload_qr(codigo, folio_oc, loc_id, sku_id),
                "id_detalle_oc": item.get("id_detalle_oc"),
                "id_sku": sku_id,
                "producto": sku_info.get("nombre") or item.get("producto") or f"SKU {sku_id}",
                "codigo_gtin": sku_info.get("codigo_gtin") or item.get("codigo_gtin") or "",
                "unidad_medida": sku_info.get("unidad_medida") or item.get("unidad_medida") or "u",
                "id_locacion_destino": loc_id,
                "locacion_destino": loc_info.get("nombre") or item.get("locacion_destino") or f"Tienda {loc_id}",
                "lote_proveedor": str(item.get("lote_proveedor") or "SIN-LOTE"),
                "fecha_produccion": f_prod.isoformat()[:10] if isinstance(f_prod, (date, datetime)) else (str(f_prod)[:10] if f_prod else None),
                "fecha_caducidad": f_cad.isoformat()[:10] if isinstance(f_cad, (date, datetime)) else (str(f_cad)[:10] if f_cad else None),
                "cantidad_declarada": round(a_float(item.get("cantidad_declarada")), 2),
                "rango_temperatura_controlada": str(item.get("rango_temperatura_controlada") or "2C a 6C"),
                "codigo_rfid_epc": str(item.get("codigo_rfid_epc") or "").strip() or None,
                "estado_escaneo": "PENDIENTE",
            }
        )
    return etiquetas


def _generar_y_guardar_pdf_asn(
    asn_doc: dict,
    *,
    orden_compra: dict | None,
    usuario: dict,
) -> dict:
    pdf_bytes = etiquetas_qr.generar_pdf_hoja_asn(asn_doc, orden_compra=orden_compra)
    hoy = date.today()
    folio_asn = asn_doc["folio_asn"]
    nombre_archivo = f"{folio_asn}_etiquetas.pdf"
    object_key = f"etiquetas_asn/{hoy:%Y}/{hoy:%m}/{nombre_archivo}"
    meta = object_storage.subir_pdf(object_key, pdf_bytes)

    ref_id = (orden_compra or {}).get("id_oc") or str(uuid.uuid5(uuid.NAMESPACE_DNS, f"freshtrack:asn:{folio_asn}"))
    ref_tipo = "ORDEN_COMPRA" if orden_compra else "ASN"

    with transaccion(id_usuario=usuario.get("id_usuario"), usuario_email=usuario.get("email")) as conn:
        id_doc = conn.execute(
            text(
                """
                INSERT INTO operacion.reporte_documento
                    (tipo_reporte, referencia_tipo, referencia_id, folio, nombre_archivo,
                     content_type, storage_provider, bucket, object_key, etag, sha256,
                     tamano_bytes, id_usuario, metadatos)
                VALUES
                    ('ETIQUETA_ASN', :rt, CAST(:rid AS uuid), :folio, :arch,
                     'application/pdf', :prov, :bkt, :key, :etag, :sha,
                     :tam, CAST(:uid AS uuid), CAST(:meta AS jsonb))
                RETURNING id_documento::text
                """
            ),
            {
                "rt": ref_tipo,
                "rid": ref_id,
                "folio": folio_asn,
                "arch": nombre_archivo,
                "prov": meta["storage_provider"],
                "bkt": meta["bucket"],
                "key": meta["object_key"],
                "etag": meta["etag"],
                "sha": meta["sha256"],
                "tam": meta["tamano_bytes"],
                "uid": usuario.get("id_usuario"),
                "meta": '{"formato":"PDF-1.4","qr":"FT1"}',
            },
        ).scalar()

    doc_store.actualizar_pdf_asn(folio_asn, id_doc, meta)
    return {"id_documento": id_doc, "nombre_archivo": nombre_archivo, "pdf_bytes": pdf_bytes, **meta}


def crear_despacho_desde_oc(
    *,
    id_oc: str,
    partidas: list[dict],
    usuario: dict,
    transporte: dict | None = None,
    folio_asn: str | None = None,
) -> dict:
    """
    Registra un Aviso de Embarque (ASN) ligado a una Orden de Compra, genera las
    etiquetas QR firmadas por tienda/producto y almacena la Hoja QR PDF en Cloud Storage.
    """
    orden = dom_compras.obtener_orden_compra(id_oc)
    if orden is None:
        raise ErrorRecepcion("La orden de compra indicada no existe.", codigo="no_encontrado", http_status=404)
    if orden["estado"] == "CANCELADA":
        raise ErrorRecepcion("No se pueden despachar órdenes de compra canceladas.", codigo="regla_negocio", http_status=409)
    if not partidas:
        raise ErrorRecepcion("Debes capturar al menos una partida con cantidad mayor a cero.")

    lineas_por_det = {l["id_detalle"]: l for l in orden["lineas"]}
    lineas_por_par = {(l["id_sku"], l["id_locacion_destino"]): l for l in orden["lineas"]}
    hoy = date.today()

    detalle_limpio: list[dict] = []
    for idx, p in enumerate(partidas, start=1):
        cant = round(a_float(p.get("cantidad_declarada")), 2)
        if cant <= 0:
            continue
        id_sku = a_int(p.get("id_sku"), 0)
        id_loc = a_int(p.get("id_locacion_destino"), 0)
        id_det = p.get("id_detalle_oc")
        linea_oc = lineas_por_det.get(id_det) or lineas_por_par.get((id_sku, id_loc))
        if linea_oc is None:
            raise ErrorRecepcion(f"La partida {idx} no pertenece a esta orden de compra.")

        lote_prov = str(p.get("lote_proveedor") or "").strip()
        if len(lote_prov) < 3:
            raise ErrorRecepcion(f"Captura un código de lote de proveedor válido en la partida {idx}.")
        f_cad = _parse_fecha(p.get("fecha_caducidad"))
        if f_cad is None or f_cad <= hoy:
            raise ErrorRecepcion(f"La fecha de caducidad de la partida {idx} debe ser posterior a hoy.")
        f_prod = _parse_fecha(p.get("fecha_produccion"), defecto=hoy)
        if f_prod and f_prod > hoy:
            raise ErrorRecepcion(f"La fecha de producción de la partida {idx} no puede ser futura.")

        detalle_limpio.append(
            {
                "id_detalle_oc": linea_oc["id_detalle"],
                "id_sku": linea_oc["id_sku"],
                "id_locacion_destino": linea_oc["id_locacion_destino"],
                "cantidad_declarada": cant,
                "lote_proveedor": lote_prov,
                "fecha_produccion": datetime.combine(f_prod, datetime.min.time()) if f_prod else None,
                "fecha_caducidad": datetime.combine(f_cad, datetime.min.time()),
                "rango_temperatura_controlada": str(p.get("rango_temperatura_controlada") or "2C a 6C").strip(),
                "codigo_rfid_epc": str(p.get("codigo_rfid_epc") or "").strip() or None,
            }
        )

    if not detalle_limpio:
        raise ErrorRecepcion("Debes incluir al menos una partida con cantidad mayor a cero.")

    skus_rows = query("SELECT id_sku, nombre, codigo_gtin, unidad_medida FROM operacion.producto WHERE id_sku = ANY(:s)", s=[d["id_sku"] for d in detalle_limpio])
    locs_rows = query("SELECT id_locacion, nombre FROM operacion.locacion WHERE id_locacion = ANY(:l)", l=[d["id_locacion_destino"] for d in detalle_limpio])
    info_skus = {r["id_sku"]: r for r in skus_rows}
    info_tiendas = {r["id_locacion"]: r for r in locs_rows}

    folio = (folio_asn or _siguiente_folio_asn()).strip()
    db = doc_store.get_mongo_db()
    if db is None:
        raise ErrorRecepcion("El servicio documental no está disponible en este momento.", codigo="mongo_no_disponible", http_status=503)
    if db.avisos_asn.find_one({"folio_asn": folio}, {"_id": 1}):
        raise ErrorRecepcion(f"El folio de despacho {folio} ya existe.", codigo="duplicado", http_status=409)

    etiquetas = construir_etiquetas_para_asn(
        folio_oc=orden["folio"],
        detalle_carga=detalle_limpio,
        info_skus=info_skus,
        info_tiendas=info_tiendas,
    )

    f_emb = datetime.now(timezone.utc)
    f_arr = datetime.combine(
        _parse_fecha(orden.get("fecha_entrega_estimada"), defecto=hoy) or hoy,
        datetime.min.time(),
        tzinfo=timezone.utc,
    )

    id_mongo = doc_store.registrar_aviso_asn(
        folio_asn=folio,
        id_proveedor=orden["id_proveedor"],
        detalle_carga=[
            {
                "id_sku": d["id_sku"],
                "id_locacion_destino": d["id_locacion_destino"],
                "cantidad_declarada": d["cantidad_declarada"],
                "lote_proveedor": d["lote_proveedor"],
                "fecha_caducidad": d["fecha_caducidad"],
                "rango_temperatura_controlada": d["rango_temperatura_controlada"],
            }
            for d in detalle_limpio
        ],
        fecha_embarque=f_emb,
        fecha_arribo_estimada=f_arr,
        estado="EN_TRANSITO",
        folio_oc=orden["folio"],
        id_oc=orden["id_oc"],
        transporte=transporte or {},
        etiquetas=etiquetas,
    )
    if not id_mongo:
        raise ErrorRecepcion("No se pudo registrar el despacho.", codigo="error_interno", http_status=500)

    asn_doc = db.avisos_asn.find_one({"folio_asn": folio}) or {
        "folio_asn": folio,
        "folio_oc": orden["folio"],
        "id_oc": orden["id_oc"],
        "id_proveedor": orden["id_proveedor"],
        "fecha_embarque": f_emb,
        "fecha_arribo_estimada": f_arr,
        "estado": "EN_TRANSITO",
        "transporte": transporte or {},
        "etiquetas": etiquetas,
    }
    pdf_info = _generar_y_guardar_pdf_asn(asn_doc, orden_compra=orden, usuario=usuario)

    publicar_evento(
        "ASN_INGRESADO",
        {"folio_asn": folio, "folio_oc": orden["folio"], "id_proveedor": orden["id_proveedor"], "etiquetas_count": len(etiquetas)},
        contexto={"user_id": usuario.get("id_usuario")},
    )
    auditoria.registrar(
        "CREATE_ASN_DISPATCH",
        tabla="reporte_documento",
        id_registro=pdf_info["id_documento"],
        descripcion=f"Despacho {folio} generado para OC {orden['folio']} con {len(etiquetas)} etiqueta(s) QR",
        estado_nuevo={"folio_asn": folio, "folio_oc": orden["folio"], "etiquetas": len(etiquetas)},
        id_usuario=usuario.get("id_usuario"),
        usuario_email=usuario.get("email"),
    )

    return {
        "id_mongo": id_mongo,
        "folio_asn": folio,
        "folio_oc": orden["folio"],
        "id_oc": orden["id_oc"],
        "estado": "EN_TRANSITO",
        "etiquetas": etiquetas,
        "id_documento_pdf": pdf_info["id_documento"],
        "storage_provider": pdf_info["storage_provider"],
        "nombre_archivo": pdf_info["nombre_archivo"],
    }


def obtener_pdf_hoja_asn(folio_asn: str, usuario: dict | None = None) -> tuple[bytes, dict]:
    """Recupera los bytes de la Hoja QR PDF desde Cloud Object Storage (o la regenera)."""
    doc_sql = one(
        """
        SELECT id_documento::text, folio, nombre_archivo, bucket, object_key, storage_provider
        FROM operacion.reporte_documento
        WHERE tipo_reporte = 'ETIQUETA_ASN' AND folio = :f
        ORDER BY creado_en DESC LIMIT 1
        """,
        f=folio_asn,
    )
    db = doc_store.get_mongo_db()
    asn_doc = db.avisos_asn.find_one({"folio_asn": folio_asn}) if db is not None else None
    if asn_doc and "_id" in asn_doc:
        asn_doc["_id"] = str(asn_doc["_id"])

    if doc_sql and doc_sql.get("object_key"):
        pdf_bytes = object_storage.descargar_pdf(
            doc_sql["object_key"],
            bucket=doc_sql.get("bucket"),
            storage_provider=doc_sql.get("storage_provider") or "s3",
        )
        if pdf_bytes:
            return pdf_bytes, asn_doc or {"folio_asn": folio_asn, **doc_sql}

    if asn_doc is None:
        raise ErrorRecepcion(f"El despacho {folio_asn} no existe.", codigo="no_encontrado", http_status=404)

    orden = dom_compras.obtener_orden_compra(asn_doc["id_oc"]) if asn_doc.get("id_oc") else None
    u_fallback = usuario or {"id_usuario": None, "email": "sistema@freshtrack.mx"}
    pdf_info = _generar_y_guardar_pdf_asn(asn_doc, orden_compra=orden, usuario=u_fallback)
    return pdf_info["pdf_bytes"], asn_doc


def enviar_hoja_asn_correo(
    folio_asn: str,
    correo_destino: str,
    usuario: dict,
    mensaje_extra: str | None = None,
) -> dict:
    """
    Envía por correo la Hoja de Empaque con las etiquetas QR del despacho (PDF adjunto).

    Usa el SMTP configurado (Mailpit en Docker). Sin SMTP_HOST el envío queda solo
    registrado en bitácora (modo demostración), igual que las Órdenes de Compra.
    """
    destino = (correo_destino or "").strip()
    if not mailer.correo_valido(destino):
        raise ErrorRecepcion("Ingresa un correo electrónico válido.", codigo="parametro_invalido")

    pdf_bytes, asn_doc = obtener_pdf_hoja_asn(folio_asn, usuario=usuario)
    asn_doc = asn_doc or {}
    folio_oc = asn_doc.get("folio_oc") or "-"
    etiquetas = asn_doc.get("etiquetas") or asn_doc.get("items") or []
    cuerpo = (
        f"Hola,\n\n"
        f"Adjuntamos la Hoja de Empaque del despacho {folio_asn} (Orden de Compra {folio_oc}) "
        f"con {len(etiquetas) if isinstance(etiquetas, list) else 0} etiqueta(s) QR.\n"
        f"Imprime las etiquetas y pégalas en cada lote: en el CEDIS se escanean para registrar la recepción.\n"
    )
    if mensaje_extra and mensaje_extra.strip():
        cuerpo += f"\nNota:\n{mensaje_extra.strip()[:2000]}\n"
    cuerpo += "\nSaludos,\nFreshTrack"

    try:
        estado = mailer.enviar_correo(
            destino,
            f"Hoja de Empaque y etiquetas QR {folio_asn} - FreshTrack",
            cuerpo,
            [(pdf_bytes, f"{folio_asn}_etiquetas.pdf", "application/pdf")],
        )
    except mailer.ErrorCorreo as exc:
        raise ErrorRecepcion(str(exc), codigo="correo_no_enviado", http_status=502) from exc

    db = doc_store.get_mongo_db()
    if db is not None:
        try:
            db.avisos_asn.update_one(
                {"folio_asn": folio_asn},
                {"$push": {"envios_correo": {
                    "correo": destino, "estado": estado,
                    "fecha": datetime.now(timezone.utc).isoformat(), "usuario": usuario.get("email"),
                }}},
            )
        except Exception:  # noqa: BLE001 - el historial en Mongo no debe impedir el envío
            logger.warning("No se pudo guardar el envío de %s en Mongo", folio_asn, exc_info=True)

    auditoria.registrar(
        "SEND_ASN_LABELS_EMAIL",
        tabla="avisos_asn",
        id_registro=folio_asn,
        descripcion=f"Envío de la Hoja QR {folio_asn} al correo {destino} ({estado})",
        estado_nuevo={"correo_envio": destino, "estado_envio_correo": estado},
        id_usuario=usuario.get("id_usuario"),
        usuario_email=usuario.get("email"),
    )
    publicar_evento(
        "HOJA_ASN_ENVIADA",
        {"folio_asn": folio_asn, "correo_envio": destino, "modo": estado},
        contexto={"user_id": usuario.get("id_usuario"), "correlation_id": folio_asn},
    )
    return {
        "folio_asn": folio_asn,
        "folio_oc": folio_oc,
        "correo_envio": destino,
        "estado_envio_correo": estado,
        "enviado_real": estado == mailer.ENVIADO,
    }


def consultar_etiqueta_para_recepcion(codigo_o_qr: str, id_locacion_usuario: int | None = None) -> dict:
    """
    Decodifica y valida criptográficamente un QR/código escaneado, recupera su ASN
    y devuelve los datos operativos + alertas de destino o vida útil.
    """
    try:
        parsed = etiquetas_qr.parsear_y_verificar_qr(codigo_o_qr)
    except ValueError as err:
        raise ErrorRecepcion(str(err), codigo="etiqueta_invalida", http_status=400) from err

    codigo = parsed.get("codigo_etiqueta")
    if not codigo:
        raise ErrorRecepcion(
            "El código GS1 requiere asociación previa con una etiqueta de despacho.",
            codigo="etiqueta_no_encontrada",
            http_status=404,
        )

    asn_doc, etq = doc_store.obtener_asn_por_etiqueta(codigo)
    if not asn_doc or not etq:
        raise ErrorRecepcion(
            f"No existe ningún despacho registrado con la etiqueta «{codigo}».",
            codigo="etiqueta_no_encontrada",
            http_status=404,
        )

    sku = one(
        """
        SELECT p.id_sku, p.nombre, p.codigo_gtin, p.unidad_medida,
               p.vida_util_estandar, p.precio_costo, p.id_proveedor,
               pr.razon_social AS proveedor
        FROM operacion.producto p
        LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        WHERE p.id_sku = :s
        """,
        s=int(etq["id_sku"]),
    )
    loc = one("SELECT id_locacion, nombre, tipo_locacion FROM operacion.locacion WHERE id_locacion = :l", l=int(etq["id_locacion_destino"]))
    ya = one(
        """
        SELECT codigo_etiqueta, id_locacion, cantidad_recibida, accion_calidad,
               resultado_inspeccion, temperatura_c, recibido_en, id_lote::text
        FROM operacion.recepcion_etiqueta
        WHERE codigo_etiqueta = :c
        """,
        c=etq["codigo_etiqueta"],
    )

    f_cad = _parse_fecha(etq.get("fecha_caducidad"))
    dias_restantes = (f_cad - date.today()).days if f_cad else 0
    vida_est = max(1, int((sku or {}).get("vida_util_estandar") or 7))
    vida_util_pct = round(max(0.0, min(100.0, (dias_restantes / vida_est) * 100.0)), 1)
    id_loc_dest = int(etq["id_locacion_destino"])

    return {
        "codigo_etiqueta": etq["codigo_etiqueta"],
        "qr_payload": etq.get("qr_payload"),
        "firma_valida": parsed.get("firma_valida", False),
        "folio_asn": asn_doc["folio_asn"],
        "estado_asn": asn_doc.get("estado"),
        "folio_oc": asn_doc.get("folio_oc"),
        "id_oc": asn_doc.get("id_oc"),
        "id_detalle_oc": etq.get("id_detalle_oc"),
        "id_proveedor": asn_doc.get("id_proveedor"),
        "proveedor": (sku or {}).get("proveedor") or f"Proveedor {asn_doc.get('id_proveedor')}",
        "id_sku": int(etq["id_sku"]),
        "producto": (sku or {}).get("nombre") or etq.get("producto"),
        "codigo_gtin": (sku or {}).get("codigo_gtin") or etq.get("codigo_gtin"),
        "unidad_medida": (sku or {}).get("unidad_medida") or etq.get("unidad_medida") or "u",
        "costo_unitario": round(a_float((sku or {}).get("precio_costo")), 2),
        "id_locacion_destino": id_loc_dest,
        "locacion_destino": (loc or {}).get("nombre") or etq.get("locacion_destino"),
        "lote_proveedor": etq.get("lote_proveedor"),
        "fecha_produccion": etq.get("fecha_produccion"),
        "fecha_caducidad": etq.get("fecha_caducidad"),
        "cantidad_declarada": round(a_float(etq.get("cantidad_declarada")), 2),
        "rango_temperatura_controlada": etq.get("rango_temperatura_controlada") or "2C a 6C",
        "dias_restantes": dias_restantes,
        "vida_util_pct": vida_util_pct,
        "alerta_vida_util_baja": vida_util_pct < 50.0,
        "alerta_destino_incorrecto": bool(id_locacion_usuario and int(id_locacion_usuario) != id_loc_dest),
        "ya_recibida": ya is not None,
        "recepcion_previa": (
            {
                **ya,
                "cantidad_recibida": a_float(ya["cantidad_recibida"]),
                "temperatura_c": a_float(ya["temperatura_c"]) if ya["temperatura_c"] is not None else None,
                "recibido_en": ya["recibido_en"].isoformat() if ya.get("recibido_en") else None,
            }
            if ya
            else None
        ),
    }


def _estado_escaneo_etiqueta(accion_calidad: str) -> str:
    if accion_calidad == "ACEPTAR_CUARENTENA":
        return "CUARENTENA"
    if accion_calidad == "RECHAZAR_MUELLE":
        return "RECHAZADA"
    return "RECIBIDA"


def procesar_recepcion_escaneo(
    *,
    codigo_o_qr: str,
    id_locacion_recepcion: int,
    cantidad_recibida: float,
    usuario: dict,
    fecha_caducidad_verificada: str | None = None,
    temperatura_registrada_c: float | None = None,
    resultado_inspeccion: str = "CONFORME",
    accion_calidad: str = "ACEPTAR_DISPONIBLE",
    medio_lectura: str = "QR",
    observaciones: str | None = None,
    idempotency_key: str | None = None,
    forzar_desvio: bool = False,
) -> dict:
    """
    Confirma el escaneo de una etiqueta en muelle de tienda:
    - Idempotente por Idempotency-Key y bloquea doble escaneo de la misma etiqueta.
    - Valida tienda destino (salvo desvio autorizado por gerente/admin).
    - Ingresa el lote, existencia y kardex FEFO en PostgreSQL.
    - Actualiza avance de la Orden de Compra (RECIBIDA_PARCIAL / RECIBIDA) y MongoDB.
    """
    accion = str(accion_calidad or "ACEPTAR_DISPONIBLE").upper()
    if accion not in ACCIONES_CALIDAD_VALIDAS:
        raise ErrorRecepcion(f"Acción de calidad inválida. Opciones: {sorted(ACCIONES_CALIDAD_VALIDAS)}")
    res_insp = str(resultado_inspeccion or "CONFORME").upper()
    if res_insp not in RESULTADOS_INSPECCION_VALIDOS:
        raise ErrorRecepcion(f"Resultado de inspección inválido. Opciones: {sorted(RESULTADOS_INSPECCION_VALIDOS)}")
    medio = str(medio_lectura or "QR").upper()
    if medio not in MEDIOS_LECTURA_VALIDOS:
        medio = "QR"

    idem_key = str(idempotency_key).strip()[:80] if idempotency_key else None
    if idem_key:
        existente = one(
            """
            SELECT codigo_etiqueta, folio_asn, id_oc::text, id_lote::text, id_sku,
                   id_locacion, cantidad_esperada, cantidad_recibida, accion_calidad,
                   resultado_inspeccion, recibido_en
            FROM operacion.recepcion_etiqueta
            WHERE idempotency_key = :k
            """,
            k=idem_key,
        )
        if existente:
            return {
                **existente,
                "cantidad_esperada": a_float(existente["cantidad_esperada"]),
                "cantidad_recibida": a_float(existente["cantidad_recibida"]),
                "recibido_en": existente["recibido_en"].isoformat() if existente.get("recibido_en") else None,
                "idempotente": True,
                "codigo_http": 200,
                "estado_orden_compra": None,
            }

    info = consultar_etiqueta_para_recepcion(codigo_o_qr, id_locacion_usuario=id_locacion_recepcion)
    if info["ya_recibida"]:
        prev = info["recepcion_previa"]
        raise ErrorRecepcion(
            f"La etiqueta {info['codigo_etiqueta']} ya fue escaneada y recibida previamente ({prev['recibido_en']}).",
            codigo="etiqueta_ya_recibida",
            http_status=409,
            detalles={"recepcion_previa": prev},
        )

    if int(id_locacion_recepcion) != int(info["id_locacion_destino"]):
        rol_usuario = str(usuario.get("rol_clave") or "")
        if not (forzar_desvio and rol_usuario in ("admin", "store_manager")):
            raise ErrorRecepcion(
                f"Etiqueta destinada a «{info['locacion_destino']}» (locación {info['id_locacion_destino']}), "
                f"no corresponde a la tienda de recepción {id_locacion_recepcion}.",
                codigo="destino_incorrecto",
                http_status=409,
                detalles={"id_locacion_destino": info["id_locacion_destino"], "locacion_destino": info["locacion_destino"]},
            )

    cant_rec = round(float(cantidad_recibida or 0), 2)
    if accion != "RECHAZAR_MUELLE" and cant_rec <= 0:
        raise ErrorRecepcion("La cantidad recibida debe ser mayor que cero para ingresar inventario.")
    if accion == "RECHAZAR_MUELLE" and cant_rec < 0:
        cant_rec = 0.0

    hoy = date.today()
    f_cad = _parse_fecha(fecha_caducidad_verificada or info["fecha_caducidad"])
    if accion != "RECHAZAR_MUELLE" and (f_cad is None or f_cad <= hoy):
        raise ErrorRecepcion("La fecha de caducidad debe ser posterior a la fecha actual.")
    f_prod = _parse_fecha(info.get("fecha_produccion"))
    if f_prod and f_prod > hoy:
        f_prod = hoy

    estado_lote = "CUARENTENA" if accion == "ACEPTAR_CUARENTENA" else "DISPONIBLE"
    id_lote: str | None = None
    nuevo_estado_oc: str | None = None

    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        if accion in ("ACEPTAR_DISPONIBLE", "ACEPTAR_CUARENTENA"):
            lote_existente = conn.execute(
                text(
                    "SELECT id_lote::text, estado FROM operacion.lote "
                    "WHERE id_proveedor = :p AND codigo_lote_prov = :cod"
                ),
                {"p": info["id_proveedor"], "cod": info["lote_proveedor"]},
            ).mappings().first()

            if lote_existente:
                id_lote = lote_existente["id_lote"]
                conn.execute(
                    text(
                        """
                        UPDATE operacion.lote
                        SET cantidad_recibida = cantidad_recibida + :cant,
                            temperatura_recepcion = COALESCE(:temp, temperatura_recepcion),
                            id_oc = COALESCE(id_oc, CAST(:id_oc AS uuid)),
                            folio_asn = COALESCE(folio_asn, :folio_asn),
                            estado = CASE WHEN :est = 'CUARENTENA' THEN 'CUARENTENA' ELSE estado END
                        WHERE id_lote = CAST(:id_lote AS uuid)
                        """
                    ),
                    {
                        "cant": cant_rec,
                        "temp": temperatura_registrada_c,
                        "id_oc": info["id_oc"],
                        "folio_asn": info["folio_asn"],
                        "est": estado_lote,
                        "id_lote": id_lote,
                    },
                )
            else:
                id_lote = conn.execute(
                    text(
                        """
                        INSERT INTO operacion.lote
                            (id_sku, id_proveedor, codigo_lote_prov, fecha_produccion,
                             fecha_recepcion, fecha_caducidad, cantidad_recibida,
                             costo_unitario, id_locacion_recepcion, estado, observaciones,
                             id_oc, folio_asn, temperatura_recepcion)
                        VALUES
                            (:sku, :prov, :cod, :f_prod, :f_rec, :f_cad,
                             :cant, :costo, :loc, :est, :obs,
                             CAST(:id_oc AS uuid), :folio_asn, :temp)
                        RETURNING id_lote::text
                        """
                    ),
                    {
                        "sku": info["id_sku"],
                        "prov": info["id_proveedor"],
                        "cod": info["lote_proveedor"],
                        "f_prod": f_prod,
                        "f_rec": hoy,
                        "f_cad": f_cad,
                        "cant": cant_rec,
                        "costo": info["costo_unitario"],
                        "loc": id_locacion_recepcion,
                        "est": estado_lote,
                        "obs": observaciones or f"Recepción {medio} · {info['folio_asn']}",
                        "id_oc": info["id_oc"],
                        "folio_asn": info["folio_asn"],
                        "temp": temperatura_registrada_c,
                    },
                ).scalar()

            conn.execute(
                text(
                    """
                    INSERT INTO operacion.existencia
                        (id_lote, id_locacion, cantidad_disponible, cantidad_reservada)
                    VALUES (CAST(:lote AS uuid), :loc, :cant, 0)
                    ON CONFLICT (id_lote, id_locacion) DO UPDATE
                        SET cantidad_disponible = operacion.existencia.cantidad_disponible + EXCLUDED.cantidad_disponible,
                            actualizado_en = now()
                    """
                ),
                {"lote": id_lote, "loc": id_locacion_recepcion, "cant": cant_rec},
            )

            saldo = conn.execute(
                text("SELECT cantidad_disponible FROM operacion.existencia WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc"),
                {"lote": id_lote, "loc": id_locacion_recepcion},
            ).scalar()

            conn.execute(
                text(
                    """
                    INSERT INTO operacion.movimiento_inventario
                        (id_lote, id_locacion, tipo, cantidad, cantidad_resultante,
                         costo_unitario, referencia_tipo, referencia_id, id_usuario)
                    VALUES
                        (CAST(:lote AS uuid), :loc, 'RECEPCION', :cant, :saldo,
                         :costo, 'ASN', CAST(:lote AS uuid), CAST(:uid AS uuid))
                    """
                ),
                {
                    "lote": id_lote,
                    "loc": id_locacion_recepcion,
                    "cant": cant_rec,
                    "saldo": a_float(saldo or cant_rec),
                    "costo": info["costo_unitario"],
                    "uid": usuario["id_usuario"],
                },
            )

        conn.execute(
            text(
                """
                INSERT INTO operacion.recepcion_etiqueta
                    (codigo_etiqueta, folio_asn, id_oc, id_detalle_oc, id_lote,
                     id_sku, id_locacion, cantidad_esperada, cantidad_recibida,
                     temperatura_c, resultado_inspeccion, accion_calidad, medio_lectura,
                     idempotency_key, observaciones, recibido_por)
                VALUES
                    (:etq, :asn, CAST(:id_oc AS uuid), CAST(:id_det AS uuid), CAST(:id_lote AS uuid),
                     :sku, :loc, :esp, :rec,
                     :temp, :res_insp, :accion, :medio,
                     :idem, :obs, CAST(:uid AS uuid))
                """
            ),
            {
                "etq": info["codigo_etiqueta"],
                "asn": info["folio_asn"],
                "id_oc": info["id_oc"],
                "id_det": info["id_detalle_oc"],
                "id_lote": id_lote,
                "sku": info["id_sku"],
                "loc": id_locacion_recepcion,
                "esp": info["cantidad_declarada"],
                "rec": cant_rec,
                "temp": temperatura_registrada_c,
                "res_insp": res_insp,
                "accion": accion,
                "medio": medio,
                "idem": idem_key,
                "obs": observaciones,
                "uid": usuario["id_usuario"],
            },
        )

        if info["id_oc"] and cant_rec > 0 and accion != "RECHAZAR_MUELLE":
            if info.get("id_detalle_oc"):
                conn.execute(
                    text(
                        "UPDATE operacion.orden_compra_detalle "
                        "SET cantidad_recibida = cantidad_recibida + :rec "
                        "WHERE id_detalle = CAST(:det AS uuid)"
                    ),
                    {"rec": cant_rec, "det": info["id_detalle_oc"]},
                )
            else:
                conn.execute(
                    text(
                        "UPDATE operacion.orden_compra_detalle "
                        "SET cantidad_recibida = cantidad_recibida + :rec "
                        "WHERE id_oc = CAST(:oc AS uuid) AND id_sku = :sku AND id_locacion_destino = :loc"
                    ),
                    {"rec": cant_rec, "oc": info["id_oc"], "sku": info["id_sku"], "loc": info["id_locacion_destino"]},
                )

            lineas_oc = conn.execute(
                text(
                    "SELECT cantidad_unidades, cantidad_recibida "
                    "FROM operacion.orden_compra_detalle WHERE id_oc = CAST(:oc AS uuid)"
                ),
                {"oc": info["id_oc"]},
            ).mappings().all()
            if lineas_oc:
                if all(a_float(x["cantidad_recibida"]) >= a_float(x["cantidad_unidades"]) * 0.995 for x in lineas_oc):
                    nuevo_estado_oc = "RECIBIDA"
                elif any(a_float(x["cantidad_recibida"]) > 0 for x in lineas_oc):
                    nuevo_estado_oc = "RECIBIDA_PARCIAL"
                if nuevo_estado_oc:
                    conn.execute(
                        text(
                            "UPDATE operacion.orden_compra SET estado = :est "
                            "WHERE id_oc = CAST(:oc AS uuid) AND estado <> 'CANCELADA'"
                        ),
                        {"est": nuevo_estado_oc, "oc": info["id_oc"]},
                    )

    # Sincronización documental y eventos asíncronos
    doc_store.agregar_inspeccion_asn(
        info["folio_asn"],
        inspector=usuario["email"],
        resultado=res_insp,
        temperatura_registrada=temperatura_registrada_c,
        observaciones=observaciones or f"[{info['codigo_etiqueta']}] {accion} ({cant_rec:g} {info['unidad_medida']})",
    )
    doc_store.marcar_etiqueta_recibida(
        info["folio_asn"],
        info["codigo_etiqueta"],
        {
            "estado_escaneo": _estado_escaneo_etiqueta(accion),
            "cantidad_recibida": cant_rec,
            "id_lote": id_lote,
            "temperatura_c": temperatura_registrada_c,
            "accion_calidad": accion,
            "recibido_por": usuario["email"],
            "recibido_en": datetime.now(timezone.utc).isoformat(),
        },
    )

    hay_discrepancia = accion != "ACEPTAR_DISPONIBLE" or (cant_rec + 0.01 < info["cantidad_declarada"])
    if hay_discrepancia:
        msg_disc = (
            f"Discrepancia en recepción de {info['producto']} ({info['folio_asn']} · {info['codigo_etiqueta']}): "
            f"esperado {info['cantidad_declarada']:g}, recibido {cant_rec:g}, acción {accion}."
        )
        doc_store.guardar_alerta_operativa(
            tipo="DISCREPANCIA_ASN",
            criticidad="CRITICAL" if accion == "RECHAZAR_MUELLE" else "WARNING",
            mensaje=msg_disc,
            id_sku=info["id_sku"],
            id_locacion=id_locacion_recepcion,
            contexto={"folio_asn": info["folio_asn"], "folio_oc": info["folio_oc"], "codigo_etiqueta": info["codigo_etiqueta"], "accion": accion},
        )
        publicar_evento(
            "DISCREPANCIA_RECEPCION",
            {"folio_asn": info["folio_asn"], "folio_oc": info["folio_oc"], "codigo_etiqueta": info["codigo_etiqueta"], "esperado": info["cantidad_declarada"], "recibido": cant_rec, "accion": accion},
            contexto={"user_id": usuario["id_usuario"]},
        )

    publicar_evento(
        "LOTE_RECIBIDO",
        {
            "id_lote": id_lote,
            "id_sku": info["id_sku"],
            "id_locacion": id_locacion_recepcion,
            "cantidad": cant_rec,
            "codigo_etiqueta": info["codigo_etiqueta"],
            "folio_asn": info["folio_asn"],
            "folio_oc": info["folio_oc"],
            "accion_calidad": accion,
        },
        contexto={"user_id": usuario["id_usuario"]},
    )
    auditoria.registrar(
        "RECEIVE_QR_BATCH",
        tabla="recepcion_etiqueta",
        id_registro=id_lote or info["codigo_etiqueta"],
        descripcion=f"Recepción {medio} etiqueta {info['codigo_etiqueta']} ({info['producto']} · {cant_rec:g} {info['unidad_medida']} -> {accion})",
        estado_nuevo={"codigo_etiqueta": info["codigo_etiqueta"], "id_lote": id_lote, "cantidad_recibida": cant_rec, "accion_calidad": accion, "estado_oc": nuevo_estado_oc},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    return {
        "codigo_etiqueta": info["codigo_etiqueta"],
        "folio_asn": info["folio_asn"],
        "folio_oc": info["folio_oc"],
        "id_oc": info["id_oc"],
        "id_lote": id_lote,
        "id_sku": info["id_sku"],
        "producto": info["producto"],
        "unidad_medida": info["unidad_medida"],
        "lote_proveedor": info["lote_proveedor"],
        "id_locacion": id_locacion_recepcion,
        "cantidad_esperada": info["cantidad_declarada"],
        "cantidad_recibida": cant_rec,
        "accion_calidad": accion,
        "resultado_inspeccion": res_insp,
        "elegible_fefo": accion == "ACEPTAR_DISPONIBLE",
        "estado_orden_compra": nuevo_estado_oc,
        "idempotente": False,
        "codigo_http": 201,
    }


def listar_ordenes_para_despacho(id_proveedor: int | None = None) -> list[dict]:
    """Lista órdenes de compra emitidas, enviadas o recibidas parcialmente listas para despachar."""
    cond = "WHERE oc.estado IN ('EMITIDA', 'ENVIADA', 'RECIBIDA_PARCIAL')"
    params: dict = {}
    if id_proveedor:
        cond += " AND oc.id_proveedor = :prov"
        params["prov"] = id_proveedor
    filas = query(
        f"""
        SELECT oc.id_oc::text, oc.folio, oc.id_proveedor, pr.razon_social AS proveedor,
               oc.estado, oc.total_lotes, oc.total_unidades, oc.fecha_entrega_estimada, oc.fecha_creacion
        FROM operacion.orden_compra oc
        JOIN operacion.proveedor pr ON pr.id_proveedor = oc.id_proveedor
        {cond}
        ORDER BY oc.fecha_creacion DESC
        LIMIT 30
        """,
        **params,
    )
    for f in filas:
        f["total_lotes"] = int(f["total_lotes"] or 0)
        f["total_unidades"] = a_float(f["total_unidades"])
        if f.get("fecha_entrega_estimada"):
            f["fecha_entrega_estimada"] = str(f["fecha_entrega_estimada"])
        if f.get("fecha_creacion"):
            f["fecha_creacion"] = f["fecha_creacion"].isoformat()
    return filas


def listar_despachos_recientes(limite: int = 40, id_proveedor: int | None = None) -> list[dict]:
    """Recupera los avisos de despacho recientes desde MongoDB con conteo de etiquetas."""
    db = doc_store.get_mongo_db()
    if db is None:
        return []
    try:
        provs = {p["id_proveedor"]: p["razon_social"] for p in query("SELECT id_proveedor, razon_social FROM operacion.proveedor")}
        filtro = {"id_proveedor": id_proveedor} if id_proveedor is not None else {}
        docs = list(db.avisos_asn.find(filtro).sort([("fecha_embarque", -1)]).limit(limite))
        out: list[dict] = []
        for d in docs:
            etqs = d.get("etiquetas") or []
            recibidas = sum(1 for e in etqs if e.get("estado_escaneo", "PENDIENTE") != "PENDIENTE")
            d["_id"] = str(d["_id"])
            d["proveedor"] = provs.get(d.get("id_proveedor"), f"Proveedor #{d.get('id_proveedor')}")
            d["total_etiquetas"] = len(etqs)
            d["etiquetas_recibidas"] = recibidas
            if isinstance(d.get("fecha_embarque"), datetime):
                d["fecha_embarque_iso"] = d["fecha_embarque"].isoformat()
            else:
                d["fecha_embarque_iso"] = str(d.get("fecha_embarque") or "")
            out.append(d)
        return out
    except Exception as exc:
        logger.warning("Error al listar despachos recientes: %s", exc)
        return []
