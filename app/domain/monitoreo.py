"""
Motor de monitoreo centralizado de microservicios y dependencias.

Consulta `/health` de los 8 microservicios en paralelo, consolida errores
registrados en Redis (contadores y el «último error registrado» de
app/services/registro_errores.py) y mantiene un historial reciente de disponibilidad en
Redis (con respaldo thread-safe en memoria por si Redis no responde).
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import threading
import time
import uuid
from typing import Any

from app.services import cache_service, clientes, registro_errores

DEPENDENCIAS_CLAVE: tuple[str, ...] = ("postgres", "mongo", "redis", "bucket")
DEPENDENCIAS_ETIQUETAS: dict[str, str] = {
    "postgres": "PostgreSQL",
    "mongo": "MongoDB",
    "redis": "Redis",
    "bucket": "Bucket (Object Storage)",
}

_HISTORIAL_CLAVE_REDIS = "monitor:health:history"
_HISTORIAL_MAX = 60
_HISTORIAL_TTL_SEGUNDOS = 604800  # 7 días
_LOCK = threading.Lock()
_HISTORIAL_MEMORIA: deque[dict[str, Any]] = deque(maxlen=_HISTORIAL_MAX)


def _limpiar_historial() -> None:
    """Limpia el historial en memoria (útil para pruebas unitarias aisladas)."""
    with _LOCK:
        _HISTORIAL_MEMORIA.clear()


def _guardar_entrada_historial(entrada: dict[str, Any]) -> None:
    with _LOCK:
        _HISTORIAL_MEMORIA.appendleft(entrada)
    r = cache_service.get_redis_client()
    if r is None:
        return
    try:
        serializado = json.dumps(entrada, default=str)
        pipe = r.pipeline()
        pipe.lpush(_HISTORIAL_CLAVE_REDIS, serializado)
        pipe.ltrim(_HISTORIAL_CLAVE_REDIS, 0, _HISTORIAL_MAX - 1)
        pipe.expire(_HISTORIAL_CLAVE_REDIS, _HISTORIAL_TTL_SEGUNDOS)
        pipe.execute()
    except Exception:
        pass


def obtener_historial(limite: int = 30) -> list[dict[str, Any]]:
    """Devuelve las verificaciones más recientes (más reciente primero)."""
    r = cache_service.get_redis_client()
    if r is not None:
        try:
            crudo = r.lrange(_HISTORIAL_CLAVE_REDIS, 0, max(0, limite - 1))
            if crudo:
                items = []
                for elem in crudo:
                    try:
                        items.append(json.loads(elem))
                    except (TypeError, ValueError):
                        continue
                if items:
                    return items
        except Exception:
            pass
    with _LOCK:
        return list(_HISTORIAL_MEMORIA)[:limite]


def obtener_errores_servicios() -> dict[str, dict[str, int]]:
    """
    Lee contadores de Redis del día actual (`counter:ops:{servicio}:{op}:{YYYYMMDD}`)
    y agrega errores 5xx y 4xx por nombre de microservicio.
    """
    contadores = cache_service.obtener_contadores()
    por_servicio: dict[str, dict[str, int]] = {}
    http_500_por_svc: dict[str, int] = {}
    internos_por_svc: dict[str, int] = {}
    otros_5xx_por_svc: dict[str, int] = {}
    errores_4xx_por_svc: dict[str, int] = {}

    for clave, valor in contadores.items():
        partes = clave.split(":")
        # Formato esperado: counter:ops:{servicio}:{operacion}:{YYYYMMDD}
        if len(partes) < 5 or partes[0] != "counter" or partes[1] != "ops":
            continue
        svc = partes[2]
        op = partes[3]
        try:
            cant = int(valor)
        except (TypeError, ValueError):
            continue

        if op == "http_500":
            http_500_por_svc[svc] = http_500_por_svc.get(svc, 0) + cant
        elif op == "errores_internos":
            internos_por_svc[svc] = internos_por_svc.get(svc, 0) + cant
        elif op.startswith("http_5") and op != "http_500":
            otros_5xx_por_svc[svc] = otros_5xx_por_svc.get(svc, 0) + cant
        elif op.startswith("http_4"):
            errores_4xx_por_svc[svc] = errores_4xx_por_svc.get(svc, 0) + cant

    todos = set(http_500_por_svc) | set(internos_por_svc) | set(otros_5xx_por_svc) | set(errores_4xx_por_svc)
    for svc in todos:
        # Evita doble conteo entre http_500 (after_request) y errores_internos (errorhandler 500)
        base_500 = max(http_500_por_svc.get(svc, 0), internos_por_svc.get(svc, 0))
        e5xx = base_500 + otros_5xx_por_svc.get(svc, 0)
        e4xx = errores_4xx_por_svc.get(svc, 0)
        por_servicio[svc] = {"http_5xx": e5xx, "http_4xx": e4xx}
    return por_servicio


def _normalizar_dependencias(raw: Any, respondio: bool) -> dict[str, bool | None]:
    if not respondio or not isinstance(raw, dict):
        return {dep: None for dep in DEPENDENCIAS_CLAVE}
    deps: dict[str, bool | None] = {}
    for dep in DEPENDENCIAS_CLAVE:
        if dep in raw:
            deps[dep] = bool(raw[dep])
        else:
            deps[dep] = None
    return deps


def _registrar_health_fallido(svc: dict[str, Any], status: int, estado: str, deps_caidas: list[str]) -> None:
    if deps_caidas:
        codigo, mensaje = "dependencia_caida", f"Dependencias con falla: {', '.join(deps_caidas)}"
    elif estado == "DOWN":
        codigo = "servicio_sin_respuesta"
        mensaje = f"El health check respondió HTTP {status}." if status else "El servicio no respondió al health check."
    else:
        codigo, mensaje = "servicio_degradado", f"El health check respondió {estado} (HTTP {status})."
    registro_errores.registrar_error(
        svc["nombre"],
        endpoint="GET /health",
        codigo=codigo,
        mensaje=mensaje,
        status=status or None,
        correlation_id=uuid.uuid4().hex,
        origen="monitor",
    )


def _consultar_servicio(svc: dict[str, Any], ahora_iso: str) -> dict[str, Any]:
    inicio = time.perf_counter()
    status, cuerpo = clientes.llamar(svc["clave"], "GET", "/health", timeout=4.0)
    latencia_red_ms = round((time.perf_counter() - inicio) * 1000.0, 2)

    respondio_valido = bool(status) and isinstance(cuerpo, dict) and ("status" in cuerpo or "service" in cuerpo)
    if respondio_valido:
        estado_raw = str(cuerpo.get("status", "")).upper()
        if status == 200 and estado_raw == "HEALTHY":
            estado = "HEALTHY"
        elif estado_raw == "DEGRADED" or status == 503 or status == 200:
            estado = "DEGRADED"
        else:
            estado = "DOWN"
    else:
        estado = "DOWN"

    deps = _normalizar_dependencias((cuerpo or {}).get("dependencies") if respondio_valido else None, respondio_valido)
    deps_caidas = [DEPENDENCIAS_ETIQUETAS[k] for k, v in deps.items() if v is False]

    proc_raw = (cuerpo or {}).get("process") if respondio_valido and isinstance((cuerpo or {}).get("process"), dict) else {}
    proceso = {
        "status": str(proc_raw.get("status") or ("UP" if respondio_valido else "DOWN")),
        "pid": proc_raw.get("pid"),
        "uptime_seconds": proc_raw.get("uptime_seconds"),
        "started_at": proc_raw.get("started_at"),
    }

    resp_ms = (
        cuerpo.get("response_time_ms")
        if respondio_valido and isinstance(cuerpo.get("response_time_ms"), (int, float))
        else None
    )
    tiempo_respuesta_ms = float(resp_ms) if resp_ms is not None else (latencia_red_ms if status else None)

    # Un health check fallido también cuenta como «último error» del servicio.
    if estado != "HEALTHY":
        _registrar_health_fallido(svc, status, estado, deps_caidas)
    checked_at = (cuerpo.get("checked_at") if respondio_valido else None) or ahora_iso

    return {
        "clave": svc["clave"],
        "nombre": svc["nombre"],
        "descripcion": svc["descripcion"],
        "url": clientes.url_interna(svc["clave"]),
        "http": status,
        "estado": estado,
        "version": str((cuerpo or {}).get("version") or "—") if respondio_valido else "—",
        "proceso": proceso,
        "dependencias": deps,
        "dependencias_caidas": deps_caidas,
        "tiempo_respuesta_ms": round(tiempo_respuesta_ms, 2) if tiempo_respuesta_ms is not None else None,
        "latencia_red_ms": latencia_red_ms if status else None,
        "ultima_verificacion": checked_at,
    }


def _consolidar_dependencias(servicios: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resumen_deps: list[dict[str, Any]] = []
    caidas: list[dict[str, Any]] = []

    for dep in DEPENDENCIAS_CLAVE:
        ok_count = 0
        fail_services: list[str] = []
        sin_dato = 0
        for svc in servicios:
            val = svc["dependencias"].get(dep)
            if val is True:
                ok_count += 1
            elif val is False:
                fail_services.append(svc["nombre"])
            else:
                sin_dato += 1

        if fail_services:
            estado = "CAIDA"
        elif ok_count > 0:
            estado = "OK"
        else:
            estado = "SIN_DATOS"

        item = {
            "clave": dep,
            "nombre": DEPENDENCIAS_ETIQUETAS[dep],
            "estado": estado,
            "ok_servicios": ok_count,
            "fallas_servicios": len(fail_services),
            "sin_respuesta": sin_dato,
            "servicios_afectados": fail_services,
        }
        resumen_deps.append(item)
        if estado == "CAIDA":
            caidas.append(item)

    return resumen_deps, caidas


def verificar_plataforma(*, guardar_historial: bool = True) -> dict[str, Any]:
    """
    Ejecuta una verificación completa de los 8 microservicios, guarda el punto en
    el historial de disponibilidad y construye el snapshot para el panel central.
    """
    ahora_dt = datetime.now(timezone.utc)
    ahora_iso = ahora_dt.isoformat()

    with ThreadPoolExecutor(max_workers=len(clientes.SERVICIOS)) as pool:
        servicios = list(pool.map(lambda s: _consultar_servicio(s, ahora_iso), clientes.SERVICIOS))

    errores_redis = obtener_errores_servicios()
    sanos = sum(1 for s in servicios if s["estado"] == "HEALTHY")
    degradados = sum(1 for s in servicios if s["estado"] == "DEGRADED")
    caidos = sum(1 for s in servicios if s["estado"] == "DOWN")
    total = len(servicios)

    tiempos = [s["tiempo_respuesta_ms"] for s in servicios if s["tiempo_respuesta_ms"] is not None]
    latencia_prom = round(sum(tiempos) / len(tiempos), 2) if tiempos else None
    disponibilidad_actual = round((sanos / total) * 100.0, 1) if total else 0.0

    deps_resumen, deps_caidas = _consolidar_dependencias(servicios)

    if sanos == total:
        estado_global = "OPERATIVO"
    elif caidos == total or caidos > total / 2:
        estado_global = "CRITICO"
    else:
        estado_global = "DEGRADADO"

    entrada_historial = {
        "timestamp": ahora_iso,
        "hora_utc": ahora_dt.strftime("%H:%M:%S UTC"),
        "fecha_hora_utc": ahora_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "estado_global": estado_global,
        "disponibilidad_pct": disponibilidad_actual,
        "sanos": sanos,
        "degradados": degradados,
        "caidos": caidos,
        "latencia_promedio_ms": latencia_prom,
        "dependencias_caidas": [d["nombre"] for d in deps_caidas],
        "estados_por_servicio": {s["clave"]: s["estado"] for s in servicios},
    }
    if guardar_historial:
        _guardar_entrada_historial(entrada_historial)

    historial = obtener_historial(limite=60)
    if not historial:
        historial = [entrada_historial]

    total_errores = 0
    for s in servicios:
        clave = s["clave"]
        nombre = s["nombre"]
        err_svc = errores_redis.get(nombre) or errores_redis.get(clave) or {"http_5xx": 0, "http_4xx": 0}

        estados_hist = [
            h.get("estados_por_servicio", {}).get(clave)
            for h in historial
            if isinstance(h.get("estados_por_servicio"), dict) and clave in h["estados_por_servicio"]
        ]
        # Si aún no existía en historial por solo_lectura, incluye al menos el estado actual
        if not estados_hist:
            estados_hist = [s["estado"]]

        fallos_hist = sum(1 for st in estados_hist if st in ("DEGRADED", "DOWN"))
        ok_hist = sum(1 for st in estados_hist if st == "HEALTHY")
        disp_svc = round((ok_hist / len(estados_hist)) * 100.0, 1) if estados_hist else 0.0

        errores_totales_svc = fallos_hist + err_svc["http_5xx"] + err_svc["http_4xx"]
        total_errores += errores_totales_svc

        s["disponibilidad_pct"] = disp_svc
        s["historial_reciente"] = list(reversed(estados_hist[:24]))  # más antiguo -> más reciente
        s["errores"] = errores_totales_svc
        s["errores_detalle"] = {
            "verificaciones": fallos_hist,
            "http_5xx": err_svc["http_5xx"],
            "http_4xx": err_svc["http_4xx"],
        }
        recientes = registro_errores.ultimos_errores(nombre, limite=5)
        s["errores_recientes"] = recientes or []
        s["ultimo_error"] = recientes[0] if recientes else None
        s["ultimo_error_disponible"] = recientes is not None  # False = Redis caído («sin datos»)

    servicios_degradados = [
        {
            "clave": s["clave"],
            "nombre": s["nombre"],
            "estado": s["estado"],
            "http": s["http"],
            "dependencias_caidas": s["dependencias_caidas"],
            "motivo": (
                f"Dependencias con falla: {', '.join(s['dependencias_caidas'])}"
                if s["dependencias_caidas"]
                else (f"HTTP {s['http']} / sin respuesta" if s["estado"] == "DOWN" else "Servicio degradado")
            ),
        }
        for s in servicios
        if s["estado"] in ("DEGRADED", "DOWN")
    ]

    return {
        "estado_global": estado_global,
        "ultima_verificacion": ahora_iso,
        "ultima_verificacion_legible": ahora_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "resumen": {
            "total_servicios": total,
            "sanos": sanos,
            "degradados": degradados,
            "caidos": caidos,
            "disponibilidad_actual_pct": disponibilidad_actual,
            "tiempo_respuesta_promedio_ms": latencia_prom,
            "total_errores": total_errores,
            "verificaciones_registradas": len(historial),
        },
        "servicios": servicios,
        "servicios_degradados": servicios_degradados,
        "dependencias": deps_resumen,
        "dependencias_caidas": deps_caidas,
        "historial": historial[:30],
    }
