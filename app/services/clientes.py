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


def llamar(clave: str, metodo: str, ruta: str, *, token: str | None = None, cuerpo: Any = None, timeout: float = 3.0) -> tuple[int, Any]:
    """Petición JSON a un microservicio. Devuelve (status, cuerpo); status 0 si no respondió."""
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url_interna(clave) + ruta, data=datos, method=metodo)
    req.add_header("Accept", "application/json")
    if datos is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
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
