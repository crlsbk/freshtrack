"""
Seguridad, Contexto y Control de Acceso (RBAC) para Microservicios FreshTrack.

Proporciona:
- Extracción de contexto de headers HTTP: X-User-Id, X-User-Role, X-Location-Id, X-Correlation-Id.
- Decorador 'requiere_auth': Valida el token JWT y comprueba denylist en Redis en < 1ms.
- Control de roles autorizados.
"""

from __future__ import annotations

import functools
import uuid
from typing import Any, Callable

from flask import g, request

from app.security import decodificar_token
from app.services.cache_service import esta_jwt_revocado
from app.services.common.response import render_response


def obtener_contexto() -> dict[str, Any]:
    """Extrae el contexto del request para trazabilidad y reglas de negocio."""
    correlation_id = request.headers.get("X-Correlation-Id") or uuid.uuid4().hex
    user_id = request.headers.get("X-User-Id")
    user_role = request.headers.get("X-User-Role")
    user_email = request.headers.get("X-User-Email")
    location_id = request.headers.get("X-Location-Id")

    return {
        "correlation_id": correlation_id,
        "user_id": user_id,
        "user_role": user_role,
        "user_email": user_email,
        "location_id": int(location_id) if (location_id and location_id.isdigit()) else None,
    }


def requiere_auth(*roles_permitidos: str) -> Callable:
    """
    Decorador para proteger endpoints de microservicios con JWT y RBAC.
    Verifica firma, vigencia y denylist en Redis (< 1ms).
    """
    def decorador(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            auth_header = request.headers.get("Authorization", "")
            token = None
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()

            if not token:
                return render_response(
                    {"error": "unauthorized", "mensaje": "Token de autenticación requerido (Bearer token)."},
                    status=401,
                    root_tag="error_response",
                )

            payload = decodificar_token(token)
            if not payload:
                return render_response(
                    {"error": "invalid_token", "mensaje": "Token inválido, expirado o revocado en Redis."},
                    status=401,
                    root_tag="error_response",
                )

            # Verificar denylist en Redis de forma directa por JTI
            jti = payload.get("jti")
            if jti and esta_jwt_revocado(jti):
                return render_response(
                    {"error": "revoked_token", "mensaje": "La sesión fue revocada (logout)."},
                    status=401,
                    root_tag="error_response",
                )

            # Verificar rol si se especificaron roles permitidos
            rol_usuario = payload.get("rol", "").lower()
            if roles_permitidos:
                roles_lower = [r.lower() for r in roles_permitidos]
                if "admin" not in rol_usuario and rol_usuario not in roles_lower:
                    return render_response(
                        {
                            "error": "forbidden",
                            "mensaje": f"Acceso denegado para el rol '{rol_usuario}'. Se requiere: {roles_permitidos}",
                        },
                        status=403,
                        root_tag="error_response",
                    )

            g.usuario_actual = payload
            g.contexto = obtener_contexto()
            return fn(*args, **kwargs)

        return wrapper

    return decorador
