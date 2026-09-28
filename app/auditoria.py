"""
Registro de eventos en la bitácora de auditoría.

Los cambios a nivel de fila los capturan los triggers de PostgreSQL sin que la
aplicación haga nada. Lo que sí tiene que avisar la aplicación son las acciones
que no corresponden a una fila concreta: LOGIN, LOGOUT, RUN_FORECAST,
APPROVE_TRANSFER, etc.
"""

from __future__ import annotations

import json
from typing import Any

from app.db import escribir

# Acciones exigidas por la rúbrica
ACCIONES = {
    "LOGIN": "Inicio de sesión",
    "LOGOUT": "Cierre de sesión",
    "LOGIN_FALLIDO": "Intento de acceso fallido",
    "CREATE_PRODUCT": "Alta de producto",
    "UPDATE_PRODUCT": "Edición de producto",
    "DEACTIVATE_PRODUCT": "Producto desactivado",
    "ACTIVATE_PRODUCT": "Producto activado",
    "CREATE_SUPPLIER": "Alta de proveedor",
    "UPDATE_SUPPLIER": "Edición de proveedor",
    "DEACTIVATE_SUPPLIER": "Proveedor desactivado",
    "CREATE_LOCATION": "Alta de tienda o CEDIS",
    "UPDATE_LOCATION": "Edición de tienda o CEDIS",
    "CREATE_BATCH": "Alta de lote",
    "RECEIVE_INVENTORY": "Recepción de inventario",
    "REGISTER_SALE": "Registro de venta",
    "REGISTER_SHRINKAGE": "Registro de merma",
    "RUN_FORECAST": "Ejecución de pronóstico",
    "CREATE_REPLENISHMENT": "Orden de reabastecimiento generada",
    "APPROVE_REPLENISHMENT": "Reabastecimiento aprobado",
    "REJECT_REPLENISHMENT": "Reabastecimiento rechazado",
    "CREATE_TRANSFER": "Transferencia sugerida",
    "APPROVE_TRANSFER": "Transferencia aprobada",
    "REJECT_TRANSFER": "Transferencia rechazada",
    "EXECUTE_TRANSFER": "Transferencia ejecutada",
    "CREATE_DISCOUNT": "Descuento sugerido",
    "APPROVE_DISCOUNT": "Descuento aprobado",
    "CREATE_USER": "Alta de usuario",
    "UPDATE_USER": "Edición de usuario",
    "ACTIVATE_USER": "Usuario activado",
    "DEACTIVATE_USER": "Usuario desactivado",
    "RUN_ALERTS": "Motor de alertas ejecutado",
}


def _json(valor: Any) -> str | None:
    if valor is None:
        return None
    return json.dumps(valor, default=str, ensure_ascii=False)


def registrar(
    accion: str,
    tabla: str | None = None,
    id_registro: Any = None,
    descripcion: str | None = None,
    estado_anterior: Any = None,
    estado_nuevo: Any = None,
    id_usuario: Any = None,
    usuario_email: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> str | None:
    """
    Inserta un evento en auditoria.bitacora_eventos.

    Si no se pasa id_usuario, la función de PostgreSQL toma el usuario de la
    variable de sesión `app.current_user_id` que fija app.db.transaccion().

    Se usa `escribir()` y no `escalar()`: la función INSERTA, y una lectura
    con `connect()` revertiría la fila al cerrar la conexión.
    """
    return escribir(
        """
        SELECT auditoria.fn_registrar_accion(
            p_accion          => :accion,
            p_tabla           => :tabla,
            p_id_registro     => :id_registro,
            p_descripcion     => :descripcion,
            p_estado_anterior => CAST(:anterior AS jsonb),
            p_estado_nuevo    => CAST(:nuevo AS jsonb),
            p_id_usuario      => CAST(:id_usuario AS uuid),
            p_usuario_email   => :usuario_email,
            p_ip              => :ip,
            p_user_agent      => :user_agent
        )
        """,
        accion=accion,
        tabla=tabla or "-",
        id_registro=str(id_registro) if id_registro is not None else None,
        descripcion=descripcion,
        anterior=_json(estado_anterior),
        nuevo=_json(estado_nuevo),
        id_usuario=str(id_usuario) if id_usuario else None,
        usuario_email=usuario_email,
        ip=ip,
        user_agent=(user_agent or "")[:300] or None,
    )


def registrar_desde_request(request, accion: str, **kwargs) -> str | None:
    """Igual que registrar(), pero toma IP y user-agent de la petición Flask."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    ip = ip.split(",")[0].strip() or None
    return registrar(
        accion,
        ip=ip,
        user_agent=request.headers.get("User-Agent"),
        **kwargs,
    )
