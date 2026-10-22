"""
Dispatcher de Eventos de Dominio Asíncronos sobre Redis Streams.

Permite a los módulos y microservicios emitir eventos de negocio desacoplados
(ej. LOTE_CREADO, VENTA_REGISTRADA, MERMA_REGISTRADA, SAGA_VENTA_*) incorporando
automáticamente trazabilidad de contexto:
- Correlation ID (UUIDv4)
- Usuario y rol del actor
- Locación / tienda origen
- Timestamp UTC

Redis Streams mantiene persistencia en memoria/disco (AOF) y soporta Consumer Groups.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.cache_service import get_redis_client

logger = logging.getLogger("freshtrack.events")

STREAM_EVENTOS_DEFAULT = "freshtrack:events"


def publicar_evento(
    tipo_evento: str,
    payload: dict[str, Any],
    *,
    contexto: dict[str, Any] | None = None,
    stream: str = STREAM_EVENTOS_DEFAULT,
) -> str | None:
    """
    Publica un evento estructurado en un Stream de Redis.
    Retorna el ID del mensaje en Redis (ej. '1695938492000-0') o None si falla.
    """
    r = get_redis_client()
    if r is None:
        logger.warning("Redis no disponible para emitir evento '%s'. Omitiendo.", tipo_evento)
        return None

    ctx = contexto or {}
    correlation_id = ctx.get("correlation_id") or uuid.uuid4().hex
    ahora = datetime.now(timezone.utc).isoformat()

    mensaje = {
        "event_id": uuid.uuid4().hex,
        "event_type": tipo_evento,
        "timestamp": ahora,
        "correlation_id": str(correlation_id),
        "user_id": str(ctx.get("user_id") or ""),
        "user_role": str(ctx.get("user_role") or ""),
        "location_id": str(ctx.get("location_id") or ""),
        "payload": json.dumps(payload, default=str),
    }

    try:
        # XADD agrega el mensaje al stream con id automático '*'
        # MAXLEN aproximado: el stream conserva los ~10 000 eventos más recientes.
        msg_id = r.xadd(stream, mensaje, maxlen=10_000, approximate=True)
        logger.debug("Evento '%s' publicado en stream %s (ID: %s)", tipo_evento, stream, msg_id)
        return str(msg_id)
    except Exception as exc:
        logger.error("Error al publicar evento '%s' en Redis Stream: %s", tipo_evento, exc)
        return None


def leer_ultimos_eventos(
    stream: str = STREAM_EVENTOS_DEFAULT,
    cantidad: int = 10,
) -> list[dict[str, Any]]:
    """Lee los eventos más recientes del stream (para monitoreo o auditoría)."""
    r = get_redis_client()
    if r is None:
        return []

    try:
        # XREVRANGE lee en orden cronológico inverso
        entradas = r.xrevrange(stream, max="+", min="-", count=cantidad)
        eventos = []
        for msg_id, data in entradas:
            evento = dict(data)
            evento["id"] = msg_id
            if "payload" in evento:
                try:
                    evento["payload"] = json.loads(evento["payload"])
                except Exception:
                    pass
            eventos.append(evento)
        return eventos
    except Exception as exc:
        logger.warning("Error al leer stream %s: %s", stream, exc)
        return []


def asegurar_consumer_group(
    stream: str,
    grupo: str,
    posicion_inicial: str = "$",
) -> bool:
    """Crea un grupo de consumidores en Redis Streams si no existe previamente."""
    r = get_redis_client()
    if r is None:
        return False
    try:
        r.xgroup_create(stream, grupo, id=posicion_inicial, mkstream=True)
        return True
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            return True  # Ya existe
        logger.error("Error al crear consumer group %s en stream %s: %s", grupo, stream, exc)
        return False
