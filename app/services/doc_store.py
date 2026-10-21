"""
Almacén Documental en MongoDB para FreshTrack.

Maneja colecciones de esquema variable y series temporales:
- `pronosticos_demanda`: Inmutabilidad algorítmica, intervalos de confianza y percentiles.
- `avisos_asn`: Avisos anticipados de embarque con detalle de carga anidado.
- `alertas_operativas`: Alertas con criticidad, contexto JSON y retención TTL (180 días).

Nota: PostgreSQL es la fuente de verdad transaccional del negocio; MongoDB
almacena proyecciones documentales y series históricas detalladas.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pymongo
from pymongo.database import Database
from app.config import Config

logger = logging.getLogger("freshtrack.mongo")

_client: pymongo.MongoClient | None = None
_db: Database | None = None
ESQUEMA_VERSION = 1


def get_mongo_db() -> Database | None:
    """Devuelve la base de datos de MongoDB reutilizando el cliente."""
    global _client, _db
    if _db is not None:
        return _db

    try:
        _client = pymongo.MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=2500)
        # Ping para validar conectividad inmediata
        _client.admin.command("ping")
        _db = _client[Config.MONGO_DB]
        return _db
    except Exception as exc:
        logger.warning("No se pudo conectar a MongoDB en %s:%s: %s", Config.MONGO_HOST, Config.MONGO_PORT, exc)
        return None


# -----------------------------------------------------------------------------
# 1. Pronósticos de Demanda
# -----------------------------------------------------------------------------
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
    """
    Persiste una corrida de pronóstico con linaje inmutable en MongoDB.
    Cumple con el validador de esquema de 'pronosticos_demanda'.
    """
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


def obtener_ultimo_pronostico(id_sku: int, id_locacion: int) -> dict | None:
    """Obtiene el pronóstico más reciente para un SKU y sucursal."""
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


# -----------------------------------------------------------------------------
# 2. Alertas Operativas Pre-Merma
# -----------------------------------------------------------------------------
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
    """
    Inserta una alerta operativa con validación de tipo y criticidad.
    Tipos permitidos: RIESGO_PRE_MERMA, RUPTURA_CADENA_FRIO, DISCREPANCIA_ASN, EXCESO_COBERTURA.
    Criticidad: INFO, WARNING, CRITICAL.
    """
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


def marcar_alerta_atendida(id_mongo: str) -> bool:
    """Marca una alerta como atendida para el ciclo de vida y TTL."""
    db = get_mongo_db()
    if db is None:
        return False
    from bson import ObjectId

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


# -----------------------------------------------------------------------------
# 3. Avisos Anticipados de Embarque (ASN)
# -----------------------------------------------------------------------------
def registrar_aviso_asn(
    *,
    folio_asn: str,
    id_proveedor: int,
    detalle_carga: list[dict],
    fecha_embarque: datetime | None = None,
    fecha_arribo_estimada: datetime | None = None,
    estado: str = "ANUNCIADO",
) -> str | None:
    """Registra un aviso ASN con documentos embebidos para recepción en CEDIS."""
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
        "version_esquema": ESQUEMA_VERSION,
    }

    try:
        res = db.avisos_asn.insert_one(documento)
        return str(res.inserted_id)
    except Exception as exc:
        logger.error("Error al registrar aviso ASN en MongoDB: %s", exc)
        return None
