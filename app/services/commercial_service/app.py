"""
Microservicio 4: Commercial, POS & Shrinkage Service (`svc-commercial`) — FreshTrack (Flask).

Puerto: 5004
Responsabilidad:
- Punto de Venta (POS) y orquestación de la Saga Venta-Inventario (FEFO + compensación).
- Carritos POS temporales en Redis con TTL.
- Registro auditado de mermas operativas (7 causas) en PostgreSQL ('operacion.merma').
- Historial de ventas con filtros y paginación, en JSON o XML.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import g, request
from redis.exceptions import RedisError

from app.db import a_float, query
from app.domain import mermas as dom_mermas
from app.domain import saga_venta
from app.domain import ventas as dom_ventas
from app.services import cache_service
from app.services.common.auth import requiere_auth, usuario_desde_token, validar_alcance_locacion
from app.services.common.rate_limit import limite_tasa
from app.services.common.response import (
    ErrorApi,
    decimal_pos,
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

logger = logging.getLogger(__name__)

app = crear_servicio(
    "svc-commercial",
    "Commercial, POS & Shrinkage Service (FreshTrack)",
    "Cobro POS orquestado con Saga (reserva FEFO → venta → compensación), carritos en Redis, mermas e historial de ventas.",
    dependencias=("postgres", "mongo", "redis", "bucket"),
)

CANALES = {"TIENDA", "ONLINE", "MAYOREO"}
CAUSAS_MERMA = set(dom_mermas.CAUSAS_CODIGOS)
TTL_CARRITO = 900

_CHECKOUT_EJEMPLO = {"id_locacion": 2, "canal": "TIENDA", "lineas": [{"id_sku": 1, "cantidad": 2}, {"id_sku": 3, "cantidad": 1}]}


def _locacion(datos: dict) -> int:
    loc = g.contexto.get("location_id") or entero(datos, "id_locacion", minimo=1)
    if not loc:
        raise ErrorApi(400, "campos_requeridos", "Falta 'id_locacion' (en el cuerpo o en el header X-Location-Id).", {"faltantes": ["id_locacion"]})
    validar_alcance_locacion(loc)
    return loc


@app.post("/api/v1/commercial/checkout")
@documentar(
    "Venta POS con Saga orquestada y consumo FEFO",
    cuerpo=_CHECKOUT_EJEMPLO,
    raiz_xml="checkout_request",
    contrato_xsd="checkout_request",
    respuesta={"saga_id": "4e1f…", "estado": "COMPLETADA", "folio": "V-20261021-0001", "total": 137.7},
    raiz_respuesta="comprobante_venta",
    errores=("400", "409", "415"),
)
@requiere_auth("store_manager", "warehouse")
@limite_tasa(limite=60, ventana_segundos=60)
def checkout_saga():
    """
    Ejecuta la venta: reserva FEFO → registro de venta y descuento de existencias →
    confirmación; si un paso falla se compensa (se liberan las reservas) y responde 409.
    """
    datos = leer_cuerpo("checkout_request", requerido=True)
    requerir_campos(datos, "lineas")
    id_locacion = _locacion(datos)
    lineas = datos.get("lineas")
    if not isinstance(lineas, list):
        raise ErrorApi(400, "parametro_invalido", "'lineas' debe ser una lista.")
    for i, l in enumerate(lineas):
        if not isinstance(l, dict):
            raise ErrorApi(400, "parametro_invalido", f"La línea {i + 1} debe tener id_sku y cantidad.")
        requerir_campos(l, "id_sku", "cantidad")
        l["id_sku"] = entero(l, "id_sku", minimo=1)
        l["cantidad"] = decimal_pos(l, "cantidad")
    canal = str(datos.get("canal") or "TIENDA").upper()
    if canal not in CANALES:
        raise ErrorApi(400, "parametro_invalido", f"Canal inválido. Valores: {sorted(CANALES)}")

    try:
        resultado = saga_venta.ejecutar_saga_venta(
            id_locacion=id_locacion, lineas=lineas, usuario=usuario_desde_token(), canal=canal,
        )
    except saga_venta.ErrorSagaVenta as err:
        cache_service.incrementar_contador("commercial", "checkout_failed")
        return error_response(409, "venta_rechazada", str(err))
    cache_service.incrementar_contador("commercial", "checkout_success")
    return render_response(resultado, status=201, root_tag="comprobante_venta")


@app.put("/api/v1/commercial/cart/<cart_id>")
@documentar(
    "Guarda (o reemplaza) un carrito POS temporal en Redis",
    cuerpo={"id_locacion": 2, "lineas": [{"id_sku": 1, "cantidad": 2}]},
    raiz_xml="carrito_request",
    respuesta={"cart_id": "caja1-0001", "status": "GUARDADO", "ttl_segundos": TTL_CARRITO},
    raiz_respuesta="cart_response",
    errores=("400",),
    exito="200",
)
@requiere_auth()
def guardar_carrito_temporal(cart_id: str):
    """Guarda el borrador del carrito en Redis (temp:pos_cart:{cart_id}) con TTL de 15 minutos."""
    datos = leer_cuerpo(requerido=True)
    if not cache_service.guardar_temporal("pos_cart", cart_id, datos, ttl_segundos=TTL_CARRITO):
        return error_response(503, "redis_no_disponible", "No se pudo almacenar el carrito temporal.")
    cache_service.incrementar_contador("commercial", "cart_saved")
    return render_response({"cart_id": cart_id, "status": "GUARDADO", "ttl_segundos": TTL_CARRITO}, status=200, root_tag="cart_response")


# Compatibilidad con clientes que usaban POST para guardar el carrito.
app.add_url_rule("/api/v1/commercial/cart/<cart_id>", "guardar_carrito_post", guardar_carrito_temporal, methods=["POST"])


@app.get("/api/v1/commercial/cart/<cart_id>")
@documentar("Consulta un carrito temporal y su TTL", raiz_respuesta="cart_response")
@requiere_auth()
def obtener_carrito_temporal(cart_id: str):
    """Recupera un carrito POS temporal desde Redis junto con los segundos que le quedan."""
    datos = cache_service.obtener_temporal("pos_cart", cart_id)
    if datos is None:
        return error_response(404, "no_encontrado", "Carrito expirado o inexistente.")
    ttl = cache_service.obtener_ttl(f"temp:pos_cart:{cart_id}")
    return render_response({"cart_id": cart_id, "ttl_restante": ttl, "datos": datos}, status=200, root_tag="cart_response")


@app.delete("/api/v1/commercial/cart/<cart_id>")
@documentar("Consume y elimina el carrito temporal", raiz_respuesta="cart_response")
@requiere_auth()
def consumir_carrito_temporal(cart_id: str):
    """GET + DEL atómico (script Lua) para que un carrito no se cobre dos veces."""
    datos = cache_service.consumir_temporal("pos_cart", cart_id)
    if datos is None:
        return error_response(404, "no_encontrado", "Carrito no encontrado o ya consumido.")
    cache_service.incrementar_contador("commercial", "cart_consumed")
    return render_response({"cart_id": cart_id, "status": "CONSUMIDO", "datos": datos}, status=200, root_tag="cart_response")


@app.post("/api/v1/commercial/shrinkage")
@documentar(
    "Registro justificado de merma",
    cuerpo={"id_lote": "0f8b6f8e-6a7c-4b1e-9d1a-2b3c4d5e6f70", "id_locacion": 2, "cantidad": 1.5, "causa": "CADUCIDAD", "observacion": "Producto vencido en anaquel"},
    raiz_xml="merma_request",
    contrato_xsd="merma_request",
    raiz_respuesta="merma_registrada",
    errores=("400", "409"),
)
@requiere_auth("store_manager", "warehouse")
def registrar_merma():
    """Registra la merma vinculada al lote y la existencia, descontando inventario en la misma transacción."""
    datos = leer_cuerpo("merma_request", requerido=True)
    requerir_campos(datos, "id_lote", "cantidad", "causa")
    causa = str(datos["causa"]).upper()
    if causa not in CAUSAS_MERMA:
        raise ErrorApi(400, "parametro_invalido", f"Causa inválida. Valores: {sorted(CAUSAS_MERMA)}")
    try:
        res = dom_mermas.registrar_merma(
            id_lote=validar_uuid(datos["id_lote"], "id_lote"),
            id_locacion=_locacion(datos),
            cantidad=decimal_pos(datos, "cantidad"),
            causa=causa,
            observacion=datos.get("observacion"),
            usuario=usuario_desde_token(),
        )
    except ValueError as err:
        return error_response(409, "regla_negocio", str(err))
    cache_service.incrementar_contador("commercial", "shrinkage_registered")
    return render_response(res, status=201, root_tag="merma_registrada")


TTL_IMPORTACION = 30 * 24 * 3600

_IMPORT_EJEMPLO = {
    "id_locacion": 2,
    "tickets": [{"folio_externo": "POS-0001", "canal": "TIENDA", "lineas": [{"id_sku": 1, "cantidad": 2}]}],
}


@app.post("/api/v1/commercial/sales/import")
@documentar(
    "Importación masiva de ventas (idempotente por folio externo)",
    cuerpo=_IMPORT_EJEMPLO,
    raiz_xml="sales_import_request",
    contrato_xsd="sales_import_request",
    respuesta={"importados": 1, "duplicados": 0, "errores": 0,
               "resultados": [{"folio_externo": "POS-0001", "estado": "IMPORTADO", "id_venta": 10, "folio": "V-20261021-0010"}]},
    raiz_respuesta="sales_import_result",
    errores=("400", "403", "503"),
    exito="200",
)
@requiere_auth("buyer", "planner")
@limite_tasa(limite=20, ventana_segundos=60)
def importar_ventas():
    """
    Registra cada ticket como una venta. La idempotencia se garantiza con una clave en Redis
    (`importacion:venta:{id_locacion}:{folio_externo}`, SET NX EX 30 días); si Redis no responde no se importa nada.
    """
    datos = leer_cuerpo("sales_import_request", requerido=True)
    requerir_campos(datos, "id_locacion", "tickets")
    id_locacion = entero(datos, "id_locacion", minimo=1)
    tickets = datos.get("tickets")
    if not isinstance(tickets, list):
        raise ErrorApi(400, "parametro_invalido", "'tickets' debe ser una lista.")
    redis_cli = cache_service.get_redis_client()
    if redis_cli is None:
        return error_response(503, "redis_no_disponible", "Redis no disponible: no se importó ningún ticket.")

    usuario = usuario_desde_token()
    resultados = []
    conteo = {"IMPORTADO": 0, "DUPLICADO": 0, "ERROR": 0}
    for i, ticket in enumerate(tickets):
        folio_ext = str(ticket.get("folio_externo") or "") if isinstance(ticket, dict) else ""
        if not folio_ext:
            resultados.append({"folio_externo": folio_ext, "estado": "ERROR", "mensaje": f"El ticket {i + 1} no tiene folio_externo."})
            conteo["ERROR"] += 1
            continue
        clave = f"importacion:venta:{id_locacion}:{folio_ext}"
        try:
            reservada = redis_cli.set(clave, "1", nx=True, ex=TTL_IMPORTACION)
        except RedisError:
            return error_response(503, "redis_no_disponible", "Redis no disponible: importación interrumpida.",
                                  {"procesados": resultados})
        if not reservada:
            resultados.append({"folio_externo": folio_ext, "estado": "DUPLICADO"})
            conteo["DUPLICADO"] += 1
            continue
        try:
            lineas = [{"id_sku": entero(l, "id_sku", minimo=1), "cantidad": decimal_pos(l, "cantidad")}
                      for l in (ticket.get("lineas") or [])]
            canal = str(ticket.get("canal") or "TIENDA").upper()
            if canal not in CANALES:
                raise ValueError(f"Canal inválido. Valores: {sorted(CANALES)}")
            venta = dom_ventas.registrar_venta(id_locacion=id_locacion, lineas=lineas, usuario=usuario, canal=canal)
        except Exception as err:  # noqa: BLE001 - un ticket fallido no debe tumbar el lote
            try:
                redis_cli.delete(clave)
            except RedisError:
                pass
            if isinstance(err, (ValueError, ErrorApi)):
                mensaje = getattr(err, "mensaje", None) or str(err)
            else:
                logger.exception("Error inesperado importando el ticket %s", folio_ext)
                mensaje = "Error interno al registrar la venta."
            resultados.append({"folio_externo": folio_ext, "estado": "ERROR", "mensaje": mensaje})
            conteo["ERROR"] += 1
            continue
        resultados.append({"folio_externo": folio_ext, "estado": "IMPORTADO",
                           "id_venta": venta.get("id_venta"), "folio": venta.get("folio")})
        conteo["IMPORTADO"] += 1

    cache_service.incrementar_contador("commercial", "sales_imported")
    return render_response(
        {"importados": conteo["IMPORTADO"], "duplicados": conteo["DUPLICADO"], "errores": conteo["ERROR"], "resultados": resultados},
        status=200, root_tag="sales_import_result",
    )


@app.get("/api/v1/commercial/sales")
@documentar(
    "Historial de ventas (filtros y paginación)",
    consulta=[("id_locacion", "integer", "Tienda"), ("canal", "string", "TIENDA/ONLINE/MAYOREO"),
              ("desde", "string", "Fecha inicial YYYY-MM-DD"), ("hasta", "string", "Fecha final YYYY-MM-DD"),
              ("pagina", "integer", "Página"), ("por_pagina", "integer", "Tamaño (máx. 100)")],
    raiz_respuesta="historial_ventas",
)
@requiere_auth()
def historial_ventas():
    """Consulta de ventas por tienda, canal y rango de fechas."""
    pagina, por_pagina, offset = paginacion()
    condiciones, params = [], {"lim": por_pagina, "off": offset}
    id_locacion = g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1)
    if id_locacion:
        condiciones.append("v.id_locacion = :loc")
        params["loc"] = id_locacion
    if request.args.get("canal"):
        condiciones.append("v.canal = :canal")
        params["canal"] = request.args["canal"].upper()
    for campo, op in (("desde", ">="), ("hasta", "<")):
        valor = request.args.get(campo)
        if valor:
            try:
                fecha = date.fromisoformat(valor)
            except ValueError as exc:
                raise ErrorApi(400, "parametro_invalido", f"'{campo}' debe tener formato YYYY-MM-DD.") from exc
            params[campo] = fecha + timedelta(days=1) if campo == "hasta" else fecha
            condiciones.append(f"v.fecha_venta {op} :{campo}")
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = query(
        f"""
        SELECT v.id_venta::text AS id_venta, v.folio, v.id_locacion, loc.nombre AS locacion,
               v.canal, v.total, v.fecha_venta, COUNT(*) OVER () AS _total
        FROM operacion.venta v
        JOIN operacion.locacion loc ON loc.id_locacion = v.id_locacion
        {where}
        ORDER BY v.fecha_venta DESC
        LIMIT :lim OFFSET :off
        """,
        **params,
    )
    total = filas[0]["_total"] if filas else 0
    for v in filas:
        v.pop("_total", None)
        v["total"] = a_float(v["total"])
    return render_response(
        {"paginacion": meta_paginacion(pagina, por_pagina, total), "ventas": filas},
        status=200,
        root_tag="historial_ventas",
    )


if __name__ == "__main__":
    ejecutar(app, "COMMERCIAL_SERVICE_PORT", 5004)
