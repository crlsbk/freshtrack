"""
Microservicio 8: Immutable Audit & Compliance (`svc-audit`) — FreshTrack (Flask).

Puerto: 5008
Responsabilidad:
- Consulta de la bitácora inmutable auditoria.bitacora_eventos (filtros, rango de fechas y paginación).
- Reconstrucción de la trazabilidad completa de un lote (kardex de movimientos).
- Registro explícito de eventos de cumplimiento, con la identidad tomada del JWT.
- Monitoreo del stream de eventos de dominio en Redis Streams.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import g, request

from app import auditoria
from app.db import a_float, one, query
from app.events.dispatcher import leer_ultimos_eventos
from app.services.common.auth import requiere_auth
from app.services.common.response import (
    ErrorApi,
    entero,
    error_response,
    leer_cuerpo,
    meta_paginacion,
    paginacion,
    render_response,
    requerir_campos,
    validar_uuid,
)
from app.services.common.servicio import crear_servicio, ejecutar
from app.services.common.swagger import documentar

app = crear_servicio(
    "svc-audit",
    "Immutable Audit & Compliance Service (FreshTrack)",
    "Bitácora inmutable, trazabilidad de lotes y monitoreo de eventos de dominio.",
    dependencias=("postgres", "redis"),
)


@app.get("/api/v1/audit/events")
@documentar(
    "Bitácora de auditoría (filtros y paginación)",
    consulta=[("tabla", "string", "Tabla afectada"), ("accion", "string", "INSERT/UPDATE/LOGIN_FALLIDO/..."),
              ("usuario", "string", "Correo del actor (parcial)"), ("desde", "string", "YYYY-MM-DD"), ("hasta", "string", "YYYY-MM-DD"),
              ("pagina", "integer", "Página"), ("por_pagina", "integer", "Tamaño (máx. 100)")],
    raiz_respuesta="bitacora_auditoria",
)
@requiere_auth("auditor")
def listar_eventos():
    """Consulta de bitácora con exportación JSON o XML."""
    pagina, por_pagina, offset = paginacion()
    condiciones, params = [], {"lim": por_pagina, "off": offset}
    if request.args.get("tabla"):
        condiciones.append("nombre_tabla = :tab")
        params["tab"] = request.args["tabla"]
    if request.args.get("accion"):
        condiciones.append("accion = :acc")
        params["acc"] = request.args["accion"].upper()
    if request.args.get("usuario"):
        condiciones.append("usuario_email ILIKE :usr")
        params["usr"] = f"%{request.args['usuario']}%"
    for campo, op in (("desde", ">="), ("hasta", "<")):
        valor = request.args.get(campo)
        if valor:
            try:
                fecha = date.fromisoformat(valor)
            except ValueError as exc:
                raise ErrorApi(400, "parametro_invalido", f"'{campo}' debe tener formato YYYY-MM-DD.") from exc
            params[campo] = fecha + timedelta(days=1) if campo == "hasta" else fecha
            condiciones.append(f"fecha_evento {op} :{campo}")
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = query(
        f"""
        SELECT id_evento::text AS id_evento, fecha_evento, accion, nombre_tabla,
               id_registro, descripcion, usuario_email, ip::text AS ip, COUNT(*) OVER () AS _total
        FROM auditoria.bitacora_eventos
        {where}
        ORDER BY fecha_evento DESC
        LIMIT :lim OFFSET :off
        """,
        **params,
    )
    total = filas[0]["_total"] if filas else 0
    for f in filas:
        f.pop("_total", None)
    return render_response(
        {"paginacion": meta_paginacion(pagina, por_pagina, total), "bitacora": filas},
        status=200,
        root_tag="bitacora_auditoria",
    )


@app.get("/api/v1/audit/traceability/<id_lote>")
@documentar("Trazabilidad completa de un lote (kardex)", raiz_respuesta="trazabilidad_lote")
@requiere_auth("auditor", "warehouse")
def trazabilidad_lote(id_lote: str):
    """Datos del lote, proveedor y todos sus movimientos de inventario en orden cronológico."""
    id_lote = validar_uuid(id_lote, "id_lote")
    lote = one(
        """
        SELECT l.id_lote::text AS id_lote, l.codigo_lote_prov, l.fecha_recepcion,
               l.fecha_caducidad, p.id_sku, p.nombre AS producto, pr.razon_social AS proveedor
        FROM operacion.lote l
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        JOIN operacion.proveedor pr ON pr.id_proveedor = l.id_proveedor
        WHERE l.id_lote = CAST(:id AS uuid)
        """,
        id=id_lote,
    )
    if not lote:
        return error_response(404, "no_encontrado", f"Lote {id_lote} no encontrado.")
    movs = query(
        """
        SELECT id_movimiento, tipo, cantidad, cantidad_resultante, fecha, referencia_tipo
        FROM operacion.movimiento_inventario
        WHERE id_lote = CAST(:id AS uuid)
        ORDER BY fecha ASC
        """,
        id=id_lote,
    )
    for m in movs:
        m["cantidad"] = a_float(m["cantidad"])
        m["cantidad_resultante"] = a_float(m["cantidad_resultante"])
    return render_response(
        {"lote": lote, "movimientos_kardex": movs, "total_movimientos": len(movs)},
        status=200,
        root_tag="trazabilidad_lote",
    )


@app.post("/api/v1/audit/log")
@documentar(
    "Registro explícito de un evento de cumplimiento",
    cuerpo={"accion": "REVISION_CUMPLIMIENTO", "tabla": "sistema", "descripcion": "Revisión mensual de mermas"},
    raiz_xml="audit_log_request",
    contrato_xsd="audit_log_request",
    respuesta={"id_evento": "…", "status": "REGISTRADO"},
    raiz_respuesta="log_creado",
    errores=("400",),
)
@requiere_auth()
def registrar_log_explicit():
    """Inserta en la bitácora con el usuario del JWT (no se aceptan identidades enviadas por headers)."""
    datos = leer_cuerpo("audit_log_request", requerido=True)
    requerir_campos(datos, "accion", "descripcion")
    accion = str(datos["accion"]).upper()[:40]
    evento_id = auditoria.registrar_desde_request(
        request,
        accion,
        tabla=str(datos.get("tabla") or "sistema")[:60],
        descripcion=str(datos["descripcion"])[:500],
        id_usuario=g.usuario_actual.get("sub"),
        usuario_email=g.usuario_actual.get("email"),
    )
    if not evento_id:
        return error_response(500, "error_bitacora", "No se pudo registrar el evento en la bitácora.")
    return render_response({"id_evento": evento_id, "status": "REGISTRADO"}, status=201, root_tag="log_creado")


@app.get("/api/v1/audit/stream/recent")
@documentar("Últimos eventos de dominio en Redis Streams", consulta=[("n", "integer", "Cantidad (máx. 200)")], raiz_respuesta="redis_stream")
@requiere_auth("auditor")
def ver_stream_eventos():
    """XREVRANGE sobre freshtrack:events: eventos emitidos por todos los microservicios."""
    eventos = leer_ultimos_eventos(cantidad=min(entero(request.args, "n", minimo=1, defecto=25), 200))
    return render_response({"total": len(eventos), "stream_eventos": eventos}, status=200, root_tag="redis_stream")


if __name__ == "__main__":
    ejecutar(app, "AUDIT_SERVICE_PORT", 5008)
