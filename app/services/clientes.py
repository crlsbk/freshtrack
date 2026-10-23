"""
Cliente HTTP del sistema web hacia los microservicios.

La web sigue funcionando por sí sola contra PostgreSQL; además consulta a los
microservicios por HTTP (urllib, sin dependencias extra) para mostrar su estado
y para reenviarles el JWT del usuario cuando una pantalla lo requiere.

URLs configurables por entorno:
- SVC_<NOMBRE>_URL         dirección interna (en Docker: http://svc_auth:5001)
- SVC_PUBLIC_HOST          host que ve el navegador para abrir Swagger (por omisión localhost)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

SERVICIOS: list[dict[str, Any]] = [
    {"clave": "auth", "nombre": "svc-auth", "puerto": 5001, "descripcion": "Login, JWT, sesiones y revocación"},
    {"clave": "catalog", "nombre": "svc-catalog", "puerto": 5002, "descripcion": "Productos, tiendas y proveedores"},
    {"clave": "inventory", "nombre": "svc-inventory", "puerto": 5003, "descripcion": "Existencias, cola FEFO y reservas"},
    {"clave": "commercial", "nombre": "svc-commercial", "puerto": 5004, "descripcion": "Ventas POS (Saga), carritos y mermas"},
    {"clave": "asn", "nombre": "svc-asn", "puerto": 5005, "descripcion": "Avisos de embarque (ASN) en JSON/XML"},
    {"clave": "planning", "nombre": "svc-planning", "puerto": 5006, "descripcion": "Pronóstico y reabastecimiento"},
    {"clave": "alerts", "nombre": "svc-alerts", "puerto": 5007, "descripcion": "Alertas pre-merma y ESG"},
    {"clave": "audit", "nombre": "svc-audit", "puerto": 5008, "descripcion": "Bitácora y trazabilidad"},
]


def url_interna(clave: str) -> str:
    svc = next(s for s in SERVICIOS if s["clave"] == clave)
    return os.getenv(f"SVC_{clave.upper()}_URL", f"http://127.0.0.1:{svc['puerto']}").rstrip("/")


def url_publica(clave: str) -> str:
    svc = next(s for s in SERVICIOS if s["clave"] == clave)
    host = os.getenv("SVC_PUBLIC_HOST", "localhost")
    return f"http://{host}:{svc['puerto']}"


def nombre(clave: str) -> str:
    return next(s["nombre"] for s in SERVICIOS if s["clave"] == clave)


def llamar(
    clave: str,
    metodo: str,
    ruta: str,
    *,
    token: str | None = None,
    cuerpo: Any = None,
    timeout: float = 3.0,
    correlation_id: str | None = None,
) -> tuple[int, Any]:
    """Petición JSON a un microservicio. Devuelve (status, cuerpo); status 0 si no respondió."""
    datos = json.dumps(cuerpo, default=str).encode() if cuerpo is not None else None
    req = urllib.request.Request(url_interna(clave) + ruta, data=datos, method=metodo)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "freshtrack-web")
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if correlation_id:
        req.add_header("X-Correlation-Id", correlation_id)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read() or b"null")
        except ValueError:
            return err.code, None
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None


def estado_servicios() -> list[dict[str, Any]]:
    """Consulta /health de los 8 servicios en paralelo."""
    def consultar(svc: dict) -> dict:
        inicio = time.perf_counter()
        status, cuerpo = llamar(svc["clave"], "GET", "/health", timeout=5)
        latencia = round((time.perf_counter() - inicio) * 1000)
        return {
            **svc,
            "http": status,
            "estado": (cuerpo or {}).get("status") if status else "SIN_RESPUESTA",
            "dependencias": (cuerpo or {}).get("dependencies", {}),
            "latencia_ms": latencia if status else None,
            "swagger": url_publica(svc["clave"]) + "/api/v1/docs",
            "url": url_interna(svc["clave"]),
        }

    with ThreadPoolExecutor(max_workers=len(SERVICIOS)) as pool:
        return list(pool.map(consultar, SERVICIOS))


# =============================================================================
# La web como frontend de los microservicios
# =============================================================================
def como_usuario(clave: str, metodo: str, ruta: str, cuerpo: Any = None, timeout: float = 15.0) -> tuple[int, Any]:
    """
    Llama a un microservicio en nombre del usuario de la sesión web: reenvía su JWT
    (el servicio aplica su propio RBAC) y un X-Correlation-Id para seguir la operación
    en los logs de ambos lados.
    """
    import logging
    import uuid

    from flask import g, has_request_context, session

    token = session.get("token") if has_request_context() else None
    cid = uuid.uuid4().hex
    if has_request_context():
        g.ultimo_correlation_id = cid
    inicio = time.perf_counter()
    status, respuesta = llamar(clave, metodo, ruta, token=token, cuerpo=cuerpo, timeout=timeout, correlation_id=cid)
    logging.getLogger("freshtrack.web").info(
        "web -> %s %s %s = %s (%.0f ms, cid=%s)",
        nombre(clave), metodo, ruta, status or "sin respuesta", (time.perf_counter() - inicio) * 1000, cid,
    )
    return status, respuesta


def mensaje_error(clave: str, status: int, respuesta: Any) -> str:
    """Texto para el usuario cuando un microservicio rechaza o no atiende la operación."""
    if status == 0:
        return f"{nombre(clave)} no está disponible en este momento. Intenta de nuevo en unos segundos."
    texto = (respuesta or {}).get("mensaje") if isinstance(respuesta, dict) else None
    if status == 403:
        return f"Tu rol no tiene permiso para esta operación ({nombre(clave)} respondió 403)."
    if status == 401:
        return "Tu sesión expiró o fue cerrada. Vuelve a iniciar sesión."
    detalle = ""
    if isinstance(respuesta, dict) and isinstance(respuesta.get("detalles"), dict):
        faltantes = respuesta["detalles"].get("faltantes")
        if faltantes:
            detalle = " Faltan: " + ", ".join(faltantes) + "."
    return f"{texto or 'La operación no se completó.'}{detalle} ({nombre(clave)}, HTTP {status})"


def activo() -> bool:
    """
    Si la web delega las operaciones en los microservicios (por omisión sí).
    WEB_USA_MICROSERVICIOS=false deja a la web en modo autónomo, útil al desarrollar
    solo la interfaz sin levantar los 8 servicios.
    """
    return os.getenv("WEB_USA_MICROSERVICIOS", "true").strip().lower() not in ("0", "false", "no")


def reenviar(clave: str, metodo: str, ruta: str, consulta: str, cuerpo: bytes | None,
             content_type: str | None, accept: str | None, token: str | None) -> tuple[int, bytes, str, str]:
    """Reenvía una petición tal cual (para el gateway /svc/... que usa el navegador)."""
    url = url_interna(clave) + ruta + (f"?{consulta}" if consulta else "")
    req = urllib.request.Request(url, data=cuerpo or None, method=metodo)
    req.add_header("Accept", accept or "application/json")
    req.add_header("User-Agent", "freshtrack-web-gateway")
    if content_type and cuerpo:
        req.add_header("Content-Type", content_type)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "application/json"), resp.headers.get("X-Correlation-Id", "")
    except urllib.error.HTTPError as err:
        return err.code, err.read(), err.headers.get("Content-Type", "application/json"), err.headers.get("X-Correlation-Id", "")
    except (urllib.error.URLError, TimeoutError, OSError):
        cuerpo_error = json.dumps({"error": "servicio_no_disponible", "mensaje": f"{nombre(clave)} no respondió."}).encode()
        return 502, cuerpo_error, "application/json", ""
