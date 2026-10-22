"""
Rate Limiting Distribuido con Redis para Microservicios y API de FreshTrack.

Proporciona el decorador @limite_tasa para proteger endpoints contra abusos,
fuerza bruta y picos descontrolados de concurrencia.
Devuelve cabeceras estándar RFC:
- X-RateLimit-Limit
- X-RateLimit-Remaining
- X-RateLimit-Reset
- Retry-After (en caso de 429)
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from flask import g, make_response, request

from app.services.cache_service import incrementar_contador, verificar_rate_limit
from app.services.common.response import error_response


def _extraer_identificador_cliente(por_ip: bool = True, por_usuario: bool = True) -> str:
    """Extrae el identificador para rate limiting combinando usuario/token e IP."""
    partes = []
    endpoint = request.endpoint or request.path

    if por_usuario:
        user_id = None
        if hasattr(g, "usuario_actual") and isinstance(g.usuario_actual, dict):
            user_id = g.usuario_actual.get("sub") or g.usuario_actual.get("id_usuario")
        if not user_id:
            user_id = request.headers.get("X-User-Id")
        if user_id:
            partes.append(f"user:{user_id}")

    if por_ip or not partes:
        ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.remote_addr
            or "127.0.0.1"
        )
        partes.append(f"ip:{ip}")

    partes.append(f"ep:{endpoint}")
    return ":".join(partes)


def limite_tasa(
    limite: int = 60,
    ventana_segundos: int = 60,
    clave_func: Callable[[], str] | None = None,
    por_ip: bool = True,
    por_usuario: bool = True,
) -> Callable:
    """
    Decorador para aplicar rate limiting distribuido con Redis a una ruta Flask.

    Ejemplo:
        @app.post("/api/v1/auth/login")
        @limite_tasa(limite=10, ventana_segundos=60)
        def login():
            ...
    """
    def decorador(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            identificador = clave_func() if clave_func else _extraer_identificador_cliente(por_ip, por_usuario)

            permitido, restantes, ttl_reset = verificar_rate_limit(
                identificador, limite=limite, ventana_segundos=ventana_segundos
            )

            headers_rl = {
                "X-RateLimit-Limit": str(limite),
                "X-RateLimit-Remaining": str(restantes),
                "X-RateLimit-Reset": str(ttl_reset),
            }

            incrementar_contador("ratelimit", "checked")

            if not permitido:
                incrementar_contador("ratelimit", "throttled")
                headers_rl["Retry-After"] = str(ttl_reset)
                return error_response(
                    429,
                    "limite_excedido",
                    f"Límite de solicitudes excedido ({limite} por {ventana_segundos}s). "
                    f"Intente nuevamente en {ttl_reset} segundos.",
                    {"retry_after": ttl_reset},
                    headers=headers_rl,
                )

            # Ejecutar la función original
            res = fn(*args, **kwargs)

            # Cualquier valor de retorno (dict, tupla o Response) lleva las cabeceras.
            res = make_response(res)
            for k, v in headers_rl.items():
                res.headers[k] = v
            return res

        wrapper._rate_limit = (limite, ventana_segundos)  # type: ignore[attr-defined]
        return wrapper

    return decorador
