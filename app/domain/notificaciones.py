"""
Centro de notificaciones de la web (campana de la barra superior y /notificaciones).

No hay una tabla nueva de notificaciones: se arman al vuelo con lo que ya existe.

  * Alertas abiertas de PostgreSQL (analitica.alerta, las de /alertas) de
    severidad CRÍTICA o ALTA.
  * Alertas operativas de MongoDB (alertas_operativas, las que emite svc-alerts).
  * Eventos de negocio publicados en el stream de Redis «freshtrack:events»
    (app/events/dispatcher.py): transferencias, descuentos, órdenes de
    reabastecimiento y de compra, ASN y discrepancias de recepción.

Cada usuario ve solo lo que corresponde a su rol (EVENTOS_POR_ROL y las vistas
de VISTAS_POR_ROL) y, si tiene tienda asignada, a su tienda. El proveedor solo
ve los eventos de SU proveedor.

Estado de lectura: conjunto de Redis «notif:leidas:<id_usuario>» (TTL 30 días).
Las notificaciones mismas son efímeras (el stream conserva ~10 000 eventos y
las alertas de MongoDB tienen índice TTL), así que su estado de lectura no
necesita sobrevivirles en PostgreSQL. El número de no leídas se guarda 30 s en
«notif:no_leidas:<id_usuario>» para no recalcularlo en cada página.

Si MongoDB, PostgreSQL o Redis no responden, esa fuente se omite y se muestra
el resto: el centro de notificaciones nunca provoca un error 500.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.db import query

logger = logging.getLogger("freshtrack.notificaciones")

TTL_LEIDAS = 30 * 24 * 3600
TTL_CONTEO = 30
LIMITE = 60
EVENTOS_A_REVISAR = 400

_OPERACION = {"admin", "planner", "store_manager", "warehouse"}
_COMPRAS = {"admin", "buyer", "planner"}

# tipo de evento → (roles que lo reciben, título, endpoint de la pantalla relacionada)
EVENTOS: dict[str, tuple[set[str], str, str | None]] = {
    "TRANSFERENCIA_SOLICITADA": (_OPERACION, "Transferencia solicitada", "analitica.transferencias"),
    "TRANSFERENCIA_APROBADA": (_OPERACION, "Transferencia aprobada", "analitica.transferencias"),
    "TRANSFERENCIA_RECHAZADA": (_OPERACION, "Transferencia rechazada", "analitica.transferencias"),
    "TRANSFERENCIA_EJECUTADA": (_OPERACION, "Transferencia ejecutada", "analitica.transferencias"),
    "DESCUENTOS_SUGERIDOS": ({"admin", "planner", "store_manager"}, "Descuentos sugeridos", "analitica.descuentos"),
    "DESCUENTO_APROBADO": ({"admin", "planner", "store_manager"}, "Descuento aprobado", "analitica.descuentos"),
    "DESCUENTO_RECHAZADO": ({"admin", "planner", "store_manager"}, "Descuento rechazado", "analitica.descuentos"),
    "ORDENES_REABASTECIMIENTO_GENERADAS": (_COMPRAS, "Órdenes de reabastecimiento sugeridas", None),
    "ORDEN_REABASTECIMIENTO_APROBADA": (_COMPRAS, "Reabastecimiento aprobado", None),
    "ORDEN_REABASTECIMIENTO_RECHAZADA": (_COMPRAS, "Reabastecimiento rechazado", None),
    "ORDEN_COMPRA_EMITIDA": ({"admin", "buyer", "supplier"}, "Orden de compra emitida", None),
    "ORDEN_COMPRA_ENVIADA": ({"admin", "buyer"}, "Orden de compra enviada al proveedor", None),
    "ASN_INGRESADO": ({"admin", "buyer", "warehouse", "store_manager", "supplier"}, "Aviso de envío (ASN) registrado", None),
    "HOJA_ASN_ENVIADA": ({"admin", "buyer", "supplier"}, "Hoja de empaque del ASN enviada", None),
    "DISCREPANCIA_RECEPCION": ({"admin", "buyer", "warehouse", "store_manager"}, "Discrepancia en recepción", None),
}

_CRITICIDAD_A_SEVERIDAD = {"CRITICAL": "CRITICA", "WARNING": "ALTA", "INFO": "BAJA"}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _redis():
    from app.services import cache_service

    return cache_service.get_redis_client()


def _fecha(valor: Any) -> datetime | None:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, str) and valor:
        try:
            return _fecha(datetime.fromisoformat(valor.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _rol(usuario: dict) -> str:
    return usuario.get("rol_clave") or ""


def _locacion(usuario: dict) -> int | None:
    try:
        return int(usuario["id_locacion"]) if usuario.get("id_locacion") not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _ve_alertas(usuario: dict) -> bool:
    from app.navegacion import VISTAS_POR_ROL

    return "alerts" in VISTAS_POR_ROL.get(_rol(usuario), [])


def _id_proveedor(usuario: dict) -> int | None:
    """Proveedor del usuario supplier (se consulta solo si hace falta)."""
    if _rol(usuario) != "supplier":
        return None
    if "id_proveedor" in usuario:
        return usuario["id_proveedor"]
    try:
        from app.db import escalar

        valor = escalar(
            "SELECT id_proveedor FROM operacion.usuario WHERE id_usuario = CAST(:u AS uuid)",
            u=usuario["id_usuario"],
        )
        usuario["id_proveedor"] = int(valor) if valor is not None else 0
    except Exception:  # noqa: BLE001
        usuario["id_proveedor"] = 0
    return usuario["id_proveedor"]


def _detalle(payload: dict) -> str:
    """Texto breve y seguro a partir de los campos conocidos del payload."""
    partes = []
    for clave, etiqueta in (
        ("folio", "Folio"), ("folio_oc", "OC"), ("folio_asn", "ASN"), ("cantidad", "Cantidad"),
        ("total", "Total"), ("estado", "Estado"), ("accion", "Acción"),
    ):
        valor = payload.get(clave)
        if valor not in (None, "", [], {}) and not isinstance(valor, (dict, list)):
            partes.append(f"{etiqueta}: {valor}")
    return " · ".join(partes)


# ---------------------------------------------------------------------------
# Filtros (funciones puras, probadas en tests/unit/test_notificaciones.py)
# ---------------------------------------------------------------------------
def evento_relevante(evento: dict, usuario: dict) -> bool:
    """¿Este evento del stream le interesa a este usuario?"""
    meta = EVENTOS.get(evento.get("event_type") or "")
    if not meta or _rol(usuario) not in meta[0]:
        return False
    if str(evento.get("user_id") or "") == str(usuario.get("id_usuario")):
        return False  # lo hizo él mismo: no se le notifica
    payload = evento.get("payload") if isinstance(evento.get("payload"), dict) else {}
    if _rol(usuario) == "supplier":
        return bool(payload.get("id_proveedor")) and str(payload.get("id_proveedor")) == str(_id_proveedor(usuario))
    loc_usuario = _locacion(usuario)
    if loc_usuario is None:
        return True
    locs = {str(payload[k]) for k in ("id_locacion", "id_locacion_origen", "id_locacion_destino") if payload.get(k)}
    if not locs and evento.get("location_id"):
        locs = {str(evento["location_id"])}
    return not locs or str(loc_usuario) in locs


def _desde_evento(evento: dict) -> dict:
    roles, titulo, endpoint = EVENTOS[evento["event_type"]]
    payload = evento.get("payload") if isinstance(evento.get("payload"), dict) else {}
    return {
        "id": f"evt:{evento.get('id')}",
        "origen": "evento",
        "tipo": evento["event_type"],
        "titulo": titulo,
        "mensaje": _detalle(payload),
        "fecha": _fecha(evento.get("timestamp")),
        "severidad": "BAJA",
        "endpoint": endpoint,
    }


# ---------------------------------------------------------------------------
# Fuentes (cada una se degrada a [] si su base no responde)
# ---------------------------------------------------------------------------
def _eventos(usuario: dict) -> tuple[list[dict], bool]:
    from app.events.dispatcher import leer_ultimos_eventos

    if _redis() is None:
        return [], False
    try:
        eventos = leer_ultimos_eventos(cantidad=EVENTOS_A_REVISAR)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notificaciones: no se pudo leer el stream de eventos: %s", exc)
        return [], False
    return [_desde_evento(e) for e in eventos if evento_relevante(e, usuario)], True


def _alertas_mongo(usuario: dict) -> tuple[list[dict], bool]:
    if not _ve_alertas(usuario):
        return [], True
    from app.services import doc_store

    try:
        if doc_store.get_mongo_db() is None:
            return [], False
        docs = doc_store.listar_alertas_operativas(id_locacion=_locacion(usuario), atendida=False, limite=30)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notificaciones: MongoDB no disponible: %s", exc)
        return [], False
    return [
        {
            "id": f"mongo:{d.get('_id')}",
            "origen": "alerta",
            "tipo": d.get("tipo") or "ALERTA",
            "titulo": "Alerta operativa: riesgo de merma" if d.get("tipo") == "RIESGO_PRE_MERMA" else "Alerta operativa",
            "mensaje": d.get("mensaje") or "",
            "fecha": _fecha(d.get("generada_en")),
            "severidad": _CRITICIDAD_A_SEVERIDAD.get(d.get("criticidad") or "", "MEDIA"),
            "endpoint": "panel.alertas",
        }
        for d in docs
    ], True


def _alertas_pg(usuario: dict) -> tuple[list[dict], bool]:
    if not _ve_alertas(usuario):
        return [], True
    loc = _locacion(usuario)
    filtro_loc = "AND (a.id_locacion = :loc OR a.id_locacion IS NULL)" if loc is not None else ""
    try:
        filas = query(
            f"""
            SELECT a.id_alerta::text AS id_alerta, a.tipo, a.severidad, a.mensaje, a.fecha_generacion
            FROM analitica.alerta a
            WHERE a.estado = 'ABIERTA' AND a.severidad IN ('CRITICA', 'ALTA') {filtro_loc}
            ORDER BY a.fecha_generacion DESC
            LIMIT 30
            """,
            **({"loc": loc} if loc is not None else {}),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notificaciones: PostgreSQL no disponible: %s", exc)
        return [], False
    from app.domain.alertas import TIPOS

    return [
        {
            "id": f"alerta:{f['id_alerta']}",
            "origen": "alerta",
            "tipo": f["tipo"],
            "titulo": TIPOS.get(f["tipo"], {}).get("etiqueta", "Alerta"),
            "mensaje": f.get("mensaje") or "",
            "fecha": _fecha(f.get("fecha_generacion")),
            "severidad": f.get("severidad") or "MEDIA",
            "endpoint": "panel.alertas",
        }
        for f in filas
    ], True


# ---------------------------------------------------------------------------
# Estado de lectura
# ---------------------------------------------------------------------------
def _clave_leidas(usuario: dict) -> str:
    return f"notif:leidas:{usuario['id_usuario']}"


def _clave_conteo(usuario: dict) -> str:
    return f"notif:no_leidas:{usuario['id_usuario']}"


def _leidas(usuario: dict) -> set[str]:
    r = _redis()
    if r is None:
        return set()
    try:
        return set(r.smembers(_clave_leidas(usuario)))
    except Exception:  # noqa: BLE001
        return set()


def _invalidar_conteo(r, usuario: dict) -> None:
    try:
        r.delete(_clave_conteo(usuario))
    except Exception:  # noqa: BLE001
        pass


def marcar_leidas(usuario: dict, ids: list[str]) -> bool:
    """Marca como leídas las notificaciones indicadas. False si Redis no responde."""
    ids = [i for i in ids if i and len(i) <= 120]
    r = _redis()
    if r is None:
        return False
    try:
        if ids:
            clave = _clave_leidas(usuario)
            r.sadd(clave, *ids)
            r.expire(clave, TTL_LEIDAS)
        _invalidar_conteo(r, usuario)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notificaciones: no se pudo guardar el estado de lectura: %s", exc)
        return False


def marcar_todas(usuario: dict) -> bool:
    return marcar_leidas(usuario, [n["id"] for n in listar(usuario)["items"]])


# ---------------------------------------------------------------------------
# API del módulo
# ---------------------------------------------------------------------------
def listar(usuario: dict, limite: int = LIMITE) -> dict:
    """
    Notificaciones del usuario, de la más reciente a la más antigua.
    Devuelve {"items", "no_leidas", "fuentes": {nombre: disponible}}.
    """
    items: list[dict] = []
    fuentes: dict[str, bool] = {}
    for nombre, fuente in (("alertas", _alertas_pg), ("alertas_mongo", _alertas_mongo), ("eventos", _eventos)):
        try:
            datos, ok = fuente(usuario)
        except Exception as exc:  # noqa: BLE001 — nunca 500 por una fuente
            logger.warning("Notificaciones: fuente %s falló: %s", nombre, exc)
            datos, ok = [], False
        items.extend(datos)
        fuentes[nombre] = ok

    minimo = datetime.min.replace(tzinfo=timezone.utc)
    items.sort(key=lambda n: n.get("fecha") or minimo, reverse=True)
    items = items[:limite]
    leidas = _leidas(usuario)
    for n in items:
        n["leida"] = n["id"] in leidas
    return {"items": items, "no_leidas": sum(1 for n in items if not n["leida"]), "fuentes": fuentes}


def contar_no_leidas(usuario: dict) -> int:
    """Número para la campana; se cachea TTL_CONTEO segundos en Redis."""
    r = _redis()
    if r is not None:
        try:
            cache = r.get(_clave_conteo(usuario))
            if cache is not None:
                return int(cache)
        except Exception:  # noqa: BLE001
            r = None
    n = listar(usuario)["no_leidas"]
    if r is not None:
        try:
            r.set(_clave_conteo(usuario), n, ex=TTL_CONTEO)
        except Exception:  # noqa: BLE001
            pass
    return n
