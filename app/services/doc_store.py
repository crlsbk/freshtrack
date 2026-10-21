"""
Almacén Documental en MongoDB para FreshTrack.

Maneja colecciones de esquema variable, series temporales y eventos:
- `pronosticos_demanda`: Inmutabilidad algorítmica, intervalos de confianza y percentiles.
- `avisos_asn`: Avisos anticipados de embarque con detalle de carga anidado y evidencias.
- `alertas_operativas`: Alertas con criticidad, contexto JSON y retención TTL (180 días).

Demuestra las 7 operaciones requeridas:
1. Inserción de documentos (individual y masiva con validación).
2. Consultas y recuperación de información con proyecciones selectivas.
3. Actualización de documentos con operadores atómicos ($set, $push, $inc).
4. Filtrado por criterios combinados ($gte, $lte, $in, campos anidados).
5. Agregaciones analíticas mediante pipelines ($match, $unwind, $group, $project, $sort).
6. Creación y uso de índices (Únicos, Compuestos y TTL).
7. Recuperación contextual vinculada a identificadores relacionales de PostgreSQL.

Nota: PostgreSQL es la fuente de verdad transaccional del negocio; MongoDB
almacena proyecciones documentales y series históricas detalladas.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
import pymongo
from pymongo.database import Database

from app.config import Config

logger = logging.getLogger("freshtrack.mongo")

_client: pymongo.MongoClient | None = None
_db: Database | None = None
ESQUEMA_VERSION = 1
DIAS_RETENCION_ALERTAS = 180


def get_mongo_db() -> Database | None:
    """Devuelve la base de datos de MongoDB reutilizando el cliente y asegurando índices."""
    global _client, _db
    if _db is not None:
        return _db

    try:
        _client = pymongo.MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=2500)
        _client.admin.command("ping")
        _db = _client[Config.MONGO_DB]
        asegurar_indices(_db)
        return _db
    except Exception as exc:
        logger.warning("No se pudo conectar a MongoDB en %s:%s: %s", Config.MONGO_HOST, Config.MONGO_PORT, exc)
        return None


# =============================================================================
# 6. Creación y Garantía de Índices
# =============================================================================
def asegurar_indices(db: Database | None = None) -> dict[str, list[str]]:
    """
    Crea y garantiza de forma idempotente los índices obligatorios de FreshTrack:
    - avisos_asn: Índice único en folio_asn, compuesto en proveedor+fecha.
    - pronosticos_demanda: Compuesto en id_sku+id_locacion+fecha_calculo.
    - alertas_operativas: Compuestos y TTL de retención a 180 días en generada_en.
    """
    if db is None:
        db = get_mongo_db()
        if db is None:
            return {}

    indices_creados: dict[str, list[str]] = {
        "pronosticos_demanda": [],
        "avisos_asn": [],
        "alertas_operativas": [],
    }

    try:
        # 1. pronosticos_demanda
        r1 = db.pronosticos_demanda.create_index(
            [("id_sku", pymongo.ASCENDING), ("id_locacion", pymongo.ASCENDING), ("fecha_calculo", pymongo.DESCENDING)],
            name="idx_pronostico_sku_locacion_fecha",
        )
        r2 = db.pronosticos_demanda.create_index(
            [("horizonte_proyeccion.fecha_fin", pymongo.ASCENDING), ("id_locacion", pymongo.ASCENDING)],
            name="idx_pronostico_horizonte_locacion",
        )
        r3 = db.pronosticos_demanda.create_index(
            [("modelo", pymongo.ASCENDING), ("version_modelo", pymongo.ASCENDING), ("fecha_calculo", pymongo.DESCENDING)],
            name="idx_pronostico_modelo_version",
        )
        indices_creados["pronosticos_demanda"].extend([r1, r2, r3])

        # 2. avisos_asn
        r4 = db.avisos_asn.create_index(
            [("folio_asn", pymongo.ASCENDING)],
            name="uq_asn_folio",
            unique=True,
        )
        r5 = db.avisos_asn.create_index(
            [("id_proveedor", pymongo.ASCENDING), ("fecha_embarque", pymongo.DESCENDING)],
            name="idx_asn_proveedor_fecha",
        )
        r6 = db.avisos_asn.create_index(
            [("estado", pymongo.ASCENDING)],
            name="idx_asn_estado",
        )
        indices_creados["avisos_asn"].extend([r4, r5, r6])

        # 3. alertas_operativas
        r7 = db.alertas_operativas.create_index(
            [("atendida", pymongo.ASCENDING), ("criticidad", pymongo.ASCENDING), ("generada_en", pymongo.DESCENDING)],
            name="idx_alerta_abierta_criticidad",
        )
        r8 = db.alertas_operativas.create_index(
            [("id_locacion", pymongo.ASCENDING), ("tipo", pymongo.ASCENDING), ("generada_en", pymongo.DESCENDING)],
            name="idx_alerta_locacion_tipo",
        )
        r9 = db.alertas_operativas.create_index(
            [("generada_en", pymongo.ASCENDING)],
            name="idx_alerta_retencion_ttl",
            expireAfterSeconds=DIAS_RETENCION_ALERTAS * 86400,
        )
        indices_creados["alertas_operativas"].extend([r7, r8, r9])

    except Exception as exc:
        logger.warning("Aviso al asegurar índices en MongoDB: %s", exc)

    return indices_creados


# =============================================================================
# 1. Inserción de Documentos
# =============================================================================
def guardar_pronostico(
    *,
    id_sku: int,
    id_locacion: int,
    modelo: str,
    puntos: list[dict],
    fecha_inicio: datetime,
    fecha_fin: datetime,
    dias_horizonte: int,
    version_modelo: str = "1.0",
    linaje: dict | None = None,
    metricas: dict | None = None,
) -> str | None:
    """Persiste una corrida de pronóstico con linaje inmutable en MongoDB."""
    db = get_mongo_db()
    if db is None:
        return None

    ahora = datetime.now(timezone.utc)
    documento = {
        "id_sku": int(id_sku),
        "id_locacion": int(id_locacion),
        "fecha_calculo": ahora,
        "horizonte_proyeccion": {
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "dias": max(7, int(dias_horizonte)),
        },
        "modelo": modelo,
        "version_modelo": version_modelo,
        "linaje": linaje or {},
        "metricas": metricas or {},
        "puntos": puntos,
        "version_esquema": ESQUEMA_VERSION,
    }

    try:
        res = db.pronosticos_demanda.insert_one(documento)
        return str(res.inserted_id)
    except Exception as exc:
        logger.error("Error al guardar pronóstico en MongoDB: %s", exc)
        return None


def guardar_alerta_operativa(
    *,
    tipo: str,
    criticidad: str,
    mensaje: str,
    id_sku: int | None = None,
    id_locacion: int | None = None,
    id_lote: int | None = None,
    contexto: dict | None = None,
) -> str | None:
    """Inserta una alerta operativa en MongoDB."""
    db = get_mongo_db()
    if db is None:
        return None

    tipos_validos = {"RIESGO_PRE_MERMA", "RUPTURA_CADENA_FRIO", "DISCREPANCIA_ASN", "EXCESO_COBERTURA"}
    if tipo not in tipos_validos:
        tipo = "RIESGO_PRE_MERMA"

    criticidades_validas = {"INFO", "WARNING", "CRITICAL"}
    if criticidad not in criticidades_validas:
        criticidad = "WARNING"

    ahora = datetime.now(timezone.utc)
    documento: dict[str, Any] = {
        "tipo": tipo,
        "criticidad": criticidad,
        "mensaje": mensaje,
        "generada_en": ahora,
        "atendida": False,
        "version_esquema": ESQUEMA_VERSION,
        "contexto": contexto or {},
    }
    if id_sku is not None:
        documento["id_sku"] = int(id_sku)
    if id_locacion is not None:
        documento["id_locacion"] = int(id_locacion)
    if id_lote is not None:
        documento["id_lote"] = int(id_lote)

    try:
        res = db.alertas_operativas.insert_one(documento)
        return str(res.inserted_id)
    except Exception as exc:
        logger.error("Error al registrar alerta operativa en MongoDB: %s", exc)
        return None


def guardar_alertas_lote(alertas: list[dict]) -> list[str]:
    """Inserción masiva de alertas operativas mediante insert_many."""
    db = get_mongo_db()
    if db is None or not alertas:
        return []

    ahora = datetime.now(timezone.utc)
    docs_normalizados = []
    for a in alertas:
        doc = {
            "tipo": a.get("tipo", "RIESGO_PRE_MERMA"),
            "criticidad": a.get("criticidad", "WARNING"),
            "mensaje": a.get("mensaje", "Alerta automática"),
            "generada_en": ahora,
            "atendida": False,
            "version_esquema": ESQUEMA_VERSION,
            "contexto": a.get("contexto", {}),
        }
        if "id_sku" in a:
            doc["id_sku"] = int(a["id_sku"])
        if "id_locacion" in a:
            doc["id_locacion"] = int(a["id_locacion"])
        if "id_lote" in a:
            doc["id_lote"] = int(a["id_lote"])
        docs_normalizados.append(doc)

    try:
        res = db.alertas_operativas.insert_many(docs_normalizados)
        return [str(_id) for _id in res.inserted_ids]
    except Exception as exc:
        logger.error("Error en inserción masiva de alertas en MongoDB: %s", exc)
        return []


def registrar_aviso_asn(
    *,
    folio_asn: str,
    id_proveedor: int,
    detalle_carga: list[dict],
    fecha_embarque: datetime | None = None,
    fecha_arribo_estimada: datetime | None = None,
    estado: str = "ANUNCIADO",
    evidencias: list[dict] | None = None,
) -> str | None:
    """Registra un aviso anticipado de embarque (ASN) con documentos embebidos."""
    db = get_mongo_db()
    if db is None:
        return None

    estados_validos = {"ANUNCIADO", "EN_TRANSITO", "RECIBIDO", "REVISION_CALIDAD", "CANCELADO"}
    if estado not in estados_validos:
        estado = "ANUNCIADO"

    from datetime import timedelta
    f_embarque = fecha_embarque or datetime.now(timezone.utc)
    f_arribo = fecha_arribo_estimada or (f_embarque + timedelta(days=2))

    documento = {
        "folio_asn": folio_asn,
        "id_proveedor": int(id_proveedor),
        "fecha_embarque": f_embarque,
        "fecha_arribo_estimada": f_arribo,
        "estado": estado,
        "detalle_carga": detalle_carga,
        "inspecciones": evidencias or [],
        "version_esquema": ESQUEMA_VERSION,
    }

    try:
        res = db.avisos_asn.insert_one(documento)
        return str(res.inserted_id)
    except Exception as exc:
        logger.error("Error al registrar aviso ASN en MongoDB: %s", exc)
        return None


# =============================================================================
# 2. Consultas y Recuperación con Proyección
# =============================================================================
def obtener_ultimo_pronostico(id_sku: int, id_locacion: int) -> dict | None:
    """Obtiene el pronóstico más reciente completo para un SKU y sucursal."""
    db = get_mongo_db()
    if db is None:
        return None

    try:
        doc = db.pronosticos_demanda.find_one(
            {"id_sku": int(id_sku), "id_locacion": int(id_locacion)},
            sort=[("fecha_calculo", pymongo.DESCENDING)],
        )
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception as exc:
        logger.warning("Error al consultar último pronóstico en MongoDB: %s", exc)
        return None


def obtener_resumen_pronostico(id_sku: int, id_locacion: int) -> dict | None:
    """Recupera únicamente el resumen del pronóstico mediante proyección selectiva."""
    db = get_mongo_db()
    if db is None:
        return None

    try:
        doc = db.pronosticos_demanda.find_one(
            {"id_sku": int(id_sku), "id_locacion": int(id_locacion)},
            projection={
                "_id": 1,
                "modelo": 1,
                "version_modelo": 1,
                "fecha_calculo": 1,
                "horizonte_proyeccion": 1,
                "metricas": 1,
                "puntos_count": {"$size": "$puntos"},
            },
            sort=[("fecha_calculo", pymongo.DESCENDING)],
        )
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception as exc:
        logger.warning("Error en proyección de resumen de pronóstico: %s", exc)
        return None


def listar_alertas_operativas(
    *,
    id_locacion: int | None = None,
    atendida: bool = False,
    criticidad: str | None = None,
    limite: int = 50,
) -> list[dict]:
    """Lista alertas activas ordenadas por criticidad y fecha descendente."""
    db = get_mongo_db()
    if db is None:
        return []

    filtro: dict[str, Any] = {"atendida": atendida}
    if id_locacion is not None:
        filtro["id_locacion"] = int(id_locacion)
    if criticidad:
        filtro["criticidad"] = criticidad

    try:
        cursor = db.alertas_operativas.find(filtro).sort([("generada_en", pymongo.DESCENDING)]).limit(limite)
        alertas = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            alertas.append(doc)
        return alertas
    except Exception as exc:
        logger.warning("Error al listar alertas operativas: %s", exc)
        return []


def detalle_asn(folio_asn: str) -> dict | None:
    """Obtiene el documento completo de un ASN por folio."""
    db = get_mongo_db()
    if db is None:
        return None

    try:
        doc = db.avisos_asn.find_one({"folio_asn": folio_asn})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
    except Exception as exc:
        logger.warning("Error al consultar ASN %s: %s", folio_asn, exc)
        return None


# =============================================================================
# 3. Actualización de Documentos ($set, $push)
# =============================================================================
def marcar_alerta_atendida(id_mongo: str) -> bool:
    """Marca una alerta como atendida mediante $set."""
    db = get_mongo_db()
    if db is None:
        return False

    try:
        ahora = datetime.now(timezone.utc)
        res = db.alertas_operativas.update_one(
            {"_id": ObjectId(id_mongo)},
            {"$set": {"atendida": True, "atendida_en": ahora}},
        )
        return res.modified_count > 0
    except Exception as exc:
        logger.error("Error al atender alerta %s en MongoDB: %s", id_mongo, exc)
        return False


def actualizar_estado_asn(folio_asn: str, nuevo_estado: str) -> bool:
    """Actualiza el estado de ciclo de vida de un ASN."""
    db = get_mongo_db()
    if db is None:
        return False

    try:
        res = db.avisos_asn.update_one(
            {"folio_asn": folio_asn},
            {"$set": {"estado": nuevo_estado, "actualizado_en": datetime.now(timezone.utc)}},
        )
        return res.matched_count > 0
    except Exception as exc:
        logger.error("Error al actualizar estado del ASN %s: %s", folio_asn, exc)
        return False


def agregar_inspeccion_asn(
    folio_asn: str,
    *,
    inspector: str,
    resultado: str,
    temperatura_registrada: float | None = None,
    observaciones: str = "",
) -> bool:
    """
    Agrega atómicamente un evento de inspección o evidencia física al ASN
    utilizando el operador $push sobre el arreglo 'inspecciones'.
    """
    db = get_mongo_db()
    if db is None:
        return False

    inspeccion = {
        "id_inspeccion": str(ObjectId()),
        "fecha": datetime.now(timezone.utc),
        "inspector": inspector,
        "resultado": resultado,
        "temperatura_registrada": temperatura_registrada,
        "observaciones": observaciones,
    }

    try:
        res = db.avisos_asn.update_one(
            {"folio_asn": folio_asn},
            {
                "$push": {"inspecciones": inspeccion},
                "$set": {"ultima_inspeccion": inspeccion["fecha"]},
            },
        )
        return res.matched_count > 0
    except Exception as exc:
        logger.error("Error al agregar inspección a ASN %s: %s", folio_asn, exc)
        return False


# =============================================================================
# 4. Filtrado por Criterios Combinados ($in, $gte, $lte)
# =============================================================================
def buscar_alertas_avanzado(
    *,
    id_locacion: int | None = None,
    criticidades: list[str] | None = None,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    atendida: bool | None = None,
    dias_restantes_max: int | None = None,
    limite: int = 50,
) -> list[dict]:
    """
    Filtra alertas operativas usando criterios múltiples y operadores avanzados:
    $in para criticidades múltiples, $gte/$lte para rango de fechas,
    y filtrado en el subdocumento 'contexto.dias_restantes'.
    """
    db = get_mongo_db()
    if db is None:
        return []

    filtro: dict[str, Any] = {}
    if id_locacion is not None:
        filtro["id_locacion"] = int(id_locacion)
    if atendida is not None:
        filtro["atendida"] = bool(atendida)
    if criticidades:
        filtro["criticidad"] = {"$in": criticidades}

    # Rango de fechas
    if fecha_desde or fecha_hasta:
        filtro["generada_en"] = {}
        if fecha_desde:
            filtro["generada_en"]["$gte"] = fecha_desde
        if fecha_hasta:
            filtro["generada_en"]["$lte"] = fecha_hasta

    # Criterio sobre propiedad embebida
    if dias_restantes_max is not None:
        filtro["contexto.dias_restantes"] = {"$lte": int(dias_restantes_max)}

    try:
        cursor = db.alertas_operativas.find(filtro).sort([("generada_en", pymongo.DESCENDING)]).limit(limite)
        alertas = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            alertas.append(doc)
        return alertas
    except Exception as exc:
        logger.warning("Error en filtrado avanzado de alertas: %s", exc)
        return []


def buscar_asns_avanzado(
    *,
    id_proveedor: int | None = None,
    estados: list[str] | None = None,
    fecha_desde: datetime | None = None,
    limite: int = 50,
) -> list[dict]:
    """Filtrado multi-criterio de avisos ASN."""
    db = get_mongo_db()
    if db is None:
        return []

    filtro: dict[str, Any] = {}
    if id_proveedor is not None:
        filtro["id_proveedor"] = int(id_proveedor)
    if estados:
        filtro["estado"] = {"$in": estados}
    if fecha_desde:
        filtro["fecha_embarque"] = {"$gte": fecha_desde}

    try:
        cursor = db.avisos_asn.find(filtro).sort([("fecha_embarque", pymongo.DESCENDING)]).limit(limite)
        asns = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            asns.append(doc)
        return asns
    except Exception as exc:
        logger.warning("Error en filtrado avanzado de ASN: %s", exc)
        return []


# =============================================================================
# 5. Agregaciones Mediante Pipelines (aggregate)
# =============================================================================
def analitica_alertas_por_locacion() -> list[dict]:
    """
    Pipeline de agregación 1:
    Agrupa alertas no atendidas por sucursal y criticidad, calculando total
    de incidencias y promedio de días restantes antes de merma.
    Fases: $match -> $group -> $project -> $sort.
    """
    db = get_mongo_db()
    if db is None:
        return []

    pipeline = [
        {"$match": {"atendida": False}},
        {
            "$group": {
                "_id": {
                    "id_locacion": "$id_locacion",
                    "criticidad": "$criticidad",
                },
                "total_alertas": {"$sum": 1},
                "promedio_dias_restantes": {"$avg": "$contexto.dias_restantes"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "id_locacion": "$_id.id_locacion",
                "criticidad": "$_id.criticidad",
                "total_alertas": 1,
                "promedio_dias_restantes": {"$round": [{"$ifNull": ["$promedio_dias_restantes", 0]}, 1]},
            }
        },
        {"$sort": {"total_alertas": -1, "id_locacion": 1}},
    ]

    try:
        return list(db.alertas_operativas.aggregate(pipeline))
    except Exception as exc:
        logger.error("Error en pipeline analitica_alertas_por_locacion: %s", exc)
        return []


def analitica_carga_asn_por_proveedor() -> list[dict]:
    """
    Pipeline de agregación 2:
    Desenrolla el arreglo de 'detalle_carga' de los ASN y consolida el volumen
    total declarado de piezas por proveedor y por SKU.
    Fases: $unwind -> $group -> $project -> $sort.
    """
    db = get_mongo_db()
    if db is None:
        return []

    pipeline = [
        {"$unwind": "$detalle_carga"},
        {
            "$group": {
                "_id": {
                    "id_proveedor": "$id_proveedor",
                    "id_sku": "$detalle_carga.id_sku",
                },
                "piezas_totales": {"$sum": "$detalle_carga.cantidad_declarada"},
                "despachos_asociados": {"$sum": 1},
            }
        },
        {
            "$project": {
                "_id": 0,
                "id_proveedor": "$_id.id_proveedor",
                "id_sku": "$_id.id_sku",
                "piezas_totales": {"$round": ["$piezas_totales", 2]},
                "despachos_asociados": 1,
            }
        },
        {"$sort": {"piezas_totales": -1}},
    ]

    try:
        return list(db.avisos_asn.aggregate(pipeline))
    except Exception as exc:
        logger.error("Error en pipeline analitica_carga_asn_por_proveedor: %s", exc)
        return []


def analitica_kpis_pronosticos() -> list[dict]:
    """
    Pipeline de agregación 3:
    Consolida las métricas de precisión algorítmica de los pronósticos por modelo.
    Fases: $group -> $project -> $sort.
    """
    db = get_mongo_db()
    if db is None:
        return []

    pipeline = [
        {
            "$group": {
                "_id": "$modelo",
                "total_corridas": {"$sum": 1},
                "mae_promedio": {"$avg": "$metricas.mae"},
                "rmse_promedio": {"$avg": "$metricas.rmse"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "modelo": "$_id",
                "total_corridas": 1,
                "mae_promedio": {"$round": [{"$ifNull": ["$mae_promedio", 0]}, 3]},
                "rmse_promedio": {"$round": [{"$ifNull": ["$rmse_promedio", 0]}, 3]},
            }
        },
        {"$sort": {"total_corridas": -1}},
    ]

    try:
        return list(db.pronosticos_demanda.aggregate(pipeline))
    except Exception as exc:
        logger.error("Error en pipeline analitica_kpis_pronosticos: %s", exc)
        return []


# =============================================================================
# 7. Recuperación Mediante Identificadores del Sistema (Cruce PostgreSQL)
# =============================================================================
def obtener_contexto_documental_sku(id_sku: int, id_locacion: int) -> dict:
    """
    Dada la identidad de un producto y una tienda (provenientes de PostgreSQL),
    recupera de MongoDB su linaje algorítmico, proyección a futuro y alertas
    operativas activas no atendidas.
    """
    db = get_mongo_db()
    if db is None:
        return {"id_sku": id_sku, "id_locacion": id_locacion, "error": "mongo_offline"}

    ultimo_pronostico = obtener_resumen_pronostico(id_sku, id_locacion)
    alertas = buscar_alertas_avanzado(id_locacion=id_locacion, atendida=False, limite=10)
    alertas_sku = [a for a in alertas if a.get("id_sku") == int(id_sku)]

    return {
        "id_sku": int(id_sku),
        "id_locacion": int(id_locacion),
        "pronostico_reciente": ultimo_pronostico,
        "alertas_activas_count": len(alertas_sku),
        "alertas_activas": alertas_sku,
        "consultado_en": datetime.now(timezone.utc).isoformat(),
    }
