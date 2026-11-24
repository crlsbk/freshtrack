"""
Seguridad, Contexto y Control de Acceso (RBAC) para Microservicios FreshTrack.

Mecanismo común a los 8 servicios (y a la API de la web):

1. Se exige 'Authorization: Bearer <JWT>'                       → 401 token_requerido
2. Se rechaza si el jti está en la denylist de Redis              → 401 token_revocado
3. Se valida firma HS256, expiración y registro en PostgreSQL     → 401 token_invalido
4. Se verifica que la sesión siga viva en Redis (session:{jti})   → 401 sesion_inexistente
   (si Redis no está disponible, PostgreSQL decide como respaldo)
5. Se comprueba el rol contra los roles permitidos del endpoint    → 403 acceso_denegado

La identidad del usuario se toma SIEMPRE de los claims del JWT, nunca de headers
que el cliente pueda falsificar. Los headers X-Correlation-Id y X-Location-Id
solo aportan contexto de trazabilidad.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

import jwt
from flask import g, request

from app.security import decodificar_token, verificar_sesion_respaldo_bd
from app.services.cache_service import esta_jwt_revocado, incrementar_contador, sesion_activa
from app.services.common.response import ErrorApi, correlation_id, error_response

logger = logging.getLogger("freshtrack.auth")

ROLES_ACOTADOS_SUCURSAL = {"store_manager", "warehouse"}


def validar_alcance_locacion(id_locacion_objetivo: int | None) -> None:
    """
    Restringe operaciones de escritura por sucursal para roles operativos de tienda/almacén:
    si el usuario está asignado a una sucursal en su JWT, no puede modificar datos de otra.
    """
    payload = getattr(g, "usuario_actual", None) or {}
    rol = (payload.get("rol") or "").lower()
    if rol not in ROLES_ACOTADOS_SUCURSAL:
        return
    loc_token = payload.get("id_locacion")
    if loc_token is None or id_locacion_objetivo is None:
        return
    if int(loc_token) != int(id_locacion_objetivo):
        incrementar_contador("auth", "access_denied_branch")
        raise ErrorApi(
            403,
            "sucursal_no_autorizada",
            f"El usuario de la sucursal {loc_token} no tiene permiso para modificar datos de la sucursal {id_locacion_objetivo}.",
            {"id_locacion_token": int(loc_token), "id_locacion_solicitada": int(id_locacion_objetivo)},
        )


def proveedor_del_usuario(id_usuario: str | None) -> int | None:
    """Proveedor ligado a un usuario (operacion.usuario.id_proveedor), leído de la base."""
    if not id_usuario:
        return None
    from app.db import escalar

    try:
        valor = escalar(
            "SELECT id_proveedor FROM operacion.usuario WHERE id_usuario = CAST(:u AS uuid)", u=str(id_usuario)
        )
    except Exception:
        return None
    return int(valor) if valor is not None else None


def proveedor_forzado() -> int | None:
    """
    Para un usuario con rol supplier devuelve SU proveedor (lo usan los listados
    para filtrar y las altas para fijarlo); para cualquier otro rol, None.
    Un supplier sin proveedor asignado recibe 403: no puede ver ni operar nada
    de ningún proveedor.
    """
    payload = getattr(g, "usuario_actual", None) or {}
    if (payload.get("rol") or "").lower() != "supplier":
        return None
    propio = proveedor_del_usuario(payload.get("sub"))
    if propio is None:
        incrementar_contador("auth", "access_denied_supplier_unlinked")
        raise ErrorApi(
            403,
            "proveedor_no_asignado",
            "Tu usuario de proveedor no está ligado a ningún proveedor. Pide al administrador que lo asigne.",
        )
    return propio


def validar_alcance_proveedor(id_proveedor_objetivo: int | None) -> None:
    """Un supplier solo opera sobre recursos de su propio proveedor (403 si no)."""
    propio = proveedor_forzado()
    if propio is None:
        return
    if id_proveedor_objetivo is None or int(id_proveedor_objetivo) != propio:
        incrementar_contador("auth", "access_denied_supplier")
        raise ErrorApi(
            403,
            "proveedor_no_autorizado",
            "Solo puedes operar sobre productos, órdenes y avisos de tu propio proveedor.",
            {"id_proveedor_usuario": propio, "id_proveedor_solicitado": id_proveedor_objetivo},
        )


def obtener_contexto() -> dict[str, Any]:
    """Contexto del request para trazabilidad y reglas de negocio."""
    payload = getattr(g, "usuario_actual", None) or {}
    location_id = request.headers.get("X-Location-Id")
    return {
        "correlation_id": correlation_id(),
        "user_id": payload.get("sub"),
        "user_role": payload.get("rol"),
        "user_email": payload.get("email"),
        "location_id": int(location_id) if (location_id and location_id.isdigit()) else None,
    }


def usuario_desde_token() -> dict[str, Any]:
    """Diccionario 'usuario' que esperan las funciones de dominio (auditoría)."""
    payload = g.usuario_actual
    return {
        "id_usuario": str(payload.get("sub")),
        "email": payload.get("email"),
        "rol_clave": payload.get("rol"),
        "id_locacion": payload.get("id_locacion"),
    }


def _extraer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip() or None
    return None


def requiere_auth(*roles_permitidos: str) -> Callable:
    """
    Decorador para proteger endpoints de microservicios con JWT, sesión Redis y RBAC.
    Sin argumentos: basta con estar autenticado. Con roles: el rol 'admin' siempre pasa.
    """
    def decorador(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            token = _extraer_token()
            if not token:
                incrementar_contador("auth", "access_denied_no_token")
                return error_response(401, "token_requerido", "Token de autenticación requerido (Authorization: Bearer <token>).")

            # Denylist de Redis antes de tocar PostgreSQL: un logout se refleja de inmediato.
            try:
                sin_verificar = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
                jti = sin_verificar.get("jti")
            except jwt.PyJWTError:
                jti = None
            if jti and esta_jwt_revocado(jti):
                incrementar_contador("auth", "access_denied_revoked")
                return error_response(401, "token_revocado", "La sesión fue cerrada; el token ya no es válido.")

            payload = decodificar_token(token)
            if not payload:
                incrementar_contador("auth", "access_denied_invalid")
                return error_response(401, "token_invalido", "Token inválido, expirado o manipulado.")

            estado_redis = sesion_activa(payload["jti"])
            if estado_redis is False:
                incrementar_contador("auth", "access_denied_no_session")
                return error_response(401, "sesion_inexistente", "La sesión no existe o expiró en Redis. Inicie sesión de nuevo.")
            if estado_redis is None:
                # Fail-Closed ante fallo de Redis: si el respaldo en PostgreSQL no confirma sesión vigente, rechazar.
                if not verificar_sesion_respaldo_bd(payload["jti"]):
                    incrementar_contador("auth", "access_denied_redis_fail_closed")
                    return error_response(
                        401,
                        "sesion_no_verificable",
                        "No se pudo verificar la vigencia de la sesión ante la indisponibilidad de Redis (Fail-Closed).",
                    )

            rol_usuario = (payload.get("rol") or "").lower()
            if roles_permitidos:
                permitidos = {r.lower() for r in roles_permitidos}
                if rol_usuario != "admin" and rol_usuario not in permitidos:
                    incrementar_contador("auth", "access_denied_role")
                    logger.info("403 %s %s rol=%s", request.method, request.path, rol_usuario)
                    return error_response(
                        403,
                        "acceso_denegado",
                        f"El rol '{rol_usuario}' no tiene permiso para esta operación.",
                        {"roles_permitidos": sorted(permitidos | {"admin"})},
                    )

            incrementar_contador("auth", "access_granted")
            g.usuario_actual = payload
            g.contexto = obtener_contexto()
            return fn(*args, **kwargs)

        # Metadatos que lee el generador de OpenAPI.
        wrapper._requiere_auth = True  # type: ignore[attr-defined]
        wrapper._roles = tuple(roles_permitidos)  # type: ignore[attr-defined]
        return wrapper

    return decorador
