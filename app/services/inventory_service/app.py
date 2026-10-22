"""
Microservicio 3: Inventory & FEFO Engine (`svc-inventory`) — FreshTrack (Flask).

Puerto: 5003
Responsabilidad:
- Existencias y lotes perecederos en PostgreSQL ('operacion.existencia', 'operacion.lote').
- Algoritmo FEFO estricto (First Expired, First Out) con días restantes calculados.
- Bloqueo distribuido (SET NX EX + liberación Lua) en Redis para reservar sin carreras.
- Pasos de reserva y compensación de la Saga de Ventas (estado temporal en Redis).
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import g, request
from sqlalchemy import text

from app.db import a_float, one, query, transaccion
from app.domain.ventas import _lotes_para_consumo, repartir_fefo
from app.services import cache_service
from app.services.common.auth import requiere_auth
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

app = crear_servicio(
    "svc-inventory",
    "Inventory & FEFO Engine Service (FreshTrack)",
    "Existencias por lote, cola FEFO y reservas con bloqueo distribuido en Redis para la Saga de Ventas.",
    dependencias=("postgres", "redis"),
)

_RESERVA_EJEMPLO = {
    "id_locacion": 2,
    "saga_id": "saga-demo-001",
    "lineas": [{"id_sku": 1, "cantidad": 3}],
}


def _locacion_contexto() -> int | None:
    return g.contexto.get("location_id") or entero(request.args, "id_locacion", minimo=1)


@app.get("/api/v1/inventory/stock")
@documentar(
    "Existencias disponibles por lote (paginado)",
    consulta=[("id_locacion", "integer", "Tienda o CEDIS"), ("id_sku", "integer", "Producto"),
              ("dias_max", "integer", "Solo lotes que vencen en ≤ N días"), ("pagina", "integer", "Página"),
              ("por_pagina", "integer", "Tamaño (máx. 100)")],
    raiz_respuesta="inventario_stock",
)
@requiere_auth()
def consultar_stock():
    """Consulta existencias con filtros por tienda, SKU y cercanía de caducidad, ordenadas FEFO."""
    pagina, por_pagina, offset = paginacion()
    id_locacion = _locacion_contexto()
    id_sku = entero(request.args, "id_sku", minimo=1)
    dias_max = entero(request.args, "dias_max", minimo=0)

    condiciones = ["e.cantidad_disponible > 0"]
    params: dict = {"lim": por_pagina, "off": offset}
    if id_locacion:
        condiciones.append("e.id_locacion = :loc")
        params["loc"] = id_locacion
    if id_sku:
        condiciones.append("l.id_sku = :sku")
        params["sku"] = id_sku
    if dias_max is not None:
        condiciones.append("(l.fecha_caducidad - CURRENT_DATE) <= :dmax")
        params["dmax"] = dias_max

    filas = query(
        f"""
        SELECT e.id_existencia::text AS id_existencia, e.id_locacion, loc.nombre AS locacion,
               l.id_lote::text AS id_lote, l.id_sku, p.nombre AS producto, l.codigo_lote_prov,
               l.fecha_caducidad, (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
               e.cantidad_disponible, e.cantidad_reservada,
               (e.cantidad_disponible - e.cantidad_reservada) AS disponible_neto,
               COUNT(*) OVER () AS _total
        FROM operacion.existencia e
        JOIN operacion.lote l ON l.id_lote = e.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
        WHERE {" AND ".join(condiciones)}
        ORDER BY l.fecha_caducidad ASC, e.id_locacion
        LIMIT :lim OFFSET :off
        """,
        **params,
    )
    total = filas[0]["_total"] if filas else 0
    for d in filas:
        d.pop("_total", None)
        for campo in ("cantidad_disponible", "cantidad_reservada", "disponible_neto"):
            d[campo] = a_float(d[campo])

    return render_response(
        {"paginacion": meta_paginacion(pagina, por_pagina, total), "existencias": filas},
        status=200,
        root_tag="inventario_stock",
    )


@app.get("/api/v1/inventory/fefo-queue/<int:id_sku>/<int:id_locacion>")
@documentar("Cola de consumo FEFO de un SKU en una locación", raiz_respuesta="fefo_queue")
@requiere_auth()
def cola_fefo(id_sku: int, id_locacion: int):
    """Lotes del SKU en la locación ordenados por caducidad más próxima (orden de surtido)."""
    if not one("SELECT 1 AS x FROM operacion.producto WHERE id_sku = :s", s=id_sku):
        return error_response(404, "no_encontrado", f"SKU {id_sku} no existe.")
    if not one("SELECT 1 AS x FROM operacion.locacion WHERE id_locacion = :l", l=id_locacion):
        return error_response(404, "no_encontrado", f"Locación {id_locacion} no existe.")
    with transaccion() as conn:
        lotes = _lotes_para_consumo(conn, id_sku, id_locacion, bloquear=False)
    for l in lotes:
        l["cantidad_disponible"] = a_float(l["cantidad_disponible"])
        l["cantidad_reservada"] = a_float(l.get("cantidad_reservada") or 0)
        l["costo_unitario"] = a_float(l["costo_unitario"])
    return render_response(
        {"id_sku": id_sku, "id_locacion": id_locacion, "total_lotes": len(lotes), "lotes_fefo": lotes},
        status=200,
        root_tag="fefo_queue",
    )


def _adquirir_con_espera(recurso: str, segundos: float = 3.0) -> tuple[str | None, bool]:
    """Intenta tomar el bloqueo durante unos segundos. Devuelve (token, redis_disponible)."""
    if cache_service.get_redis_client() is None:
        return None, False
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        token = cache_service.adquirir_bloqueo(recurso, timeout_segundos=8)
        if token:
            return token, True
        time.sleep(0.05)
    return None, True


def _lineas_validas(lineas) -> list[dict]:
    if not isinstance(lineas, list) or not lineas:
        raise ErrorApi(400, "campos_requeridos", "'lineas' debe ser una lista con al menos un producto.")
    limpias = []
    for i, item in enumerate(lineas):
        if not isinstance(item, dict):
            raise ErrorApi(400, "parametro_invalido", f"La línea {i + 1} debe ser un objeto con id_sku y cantidad.")
        requerir_campos(item, "id_sku", "cantidad")
        limpias.append({"id_sku": entero(item, "id_sku", minimo=1), "cantidad": decimal_pos(item, "cantidad")})
    return limpias


@app.post("/api/v1/inventory/reserve-fefo")
@documentar(
    "Paso 1 de la Saga: reserva de lotes en orden FEFO",
    cuerpo=_RESERVA_EJEMPLO,
    raiz_xml="reserva_request",
    contrato_xsd="reserva_request",
    respuesta={"status": "RESERVADO", "saga_id": "saga-demo-001", "reservas": [{"id_lote": "…", "id_sku": 1, "cantidad": 3.0}]},
    raiz_respuesta="reserva_response",
    errores=("400", "409"),
    exito="200",
)
@requiere_auth("store_manager", "warehouse")
@limite_tasa(limite=60, ventana_segundos=60)
def reservar_fefo():
    """
    Reserva temporal de lotes en orden FEFO protegida con un bloqueo distribuido en Redis
    (lock:inventory:loc:{id}:reserve). Incrementa 'cantidad_reservada' y guarda la reserva
    en Redis (temp:reservation:{saga_id}, TTL 10 min) para poder compensarla.
    """
    datos = leer_cuerpo("reserva_request", requerido=True)
    requerir_campos(datos, "id_locacion", "lineas")
    id_locacion = entero(datos, "id_locacion", minimo=1)
    lineas = _lineas_validas(datos.get("lineas"))
    saga_id = datos.get("saga_id")

    recurso = f"inventory:loc:{id_locacion}:reserve"
    lock_token, redis_ok = _adquirir_con_espera(recurso)
    if redis_ok and not lock_token:
        return error_response(409, "recurso_bloqueado", "Otra reserva está en curso en esta locación; reintente.")

    reservas = []
    try:
        with transaccion(id_usuario=g.usuario_actual.get("sub"), usuario_email=g.usuario_actual.get("email")) as conn:
            for item in lineas:
                lotes = _lotes_para_consumo(conn, item["id_sku"], id_locacion, bloquear=True)
                consumos = repartir_fefo(lotes, item["cantidad"])
                cubierto = sum(c["consumido"] for c in consumos)
                if round(cubierto, 3) < round(item["cantidad"], 3):
                    cache_service.incrementar_contador("inventory", "reserve_failed")
                    # Se lanza para que la transacción haga rollback de lo reservado antes.
                    raise ErrorApi(
                        409,
                        "stock_insuficiente",
                        f"Stock insuficiente para el SKU {item['id_sku']}.",
                        {"id_sku": item["id_sku"], "disponible": round(cubierto, 3), "solicitado": item["cantidad"]},
                    )
                for c in consumos:
                    conn.execute(
                        text(
                            """
                            UPDATE operacion.existencia
                            SET cantidad_reservada = cantidad_reservada + :cant, actualizado_en = now()
                            WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc
                            """
                        ),
                        {"cant": c["consumido"], "lote": c["id_lote"], "loc": id_locacion},
                    )
                    reservas.append({
                        "id_lote": c["id_lote"],
                        "id_sku": item["id_sku"],
                        "cantidad": c["consumido"],
                        "costo_unitario": a_float(c["costo_unitario"]),
                        "codigo_lote": c.get("codigo_lote_prov"),
                    })
    finally:
        if lock_token:
            cache_service.liberar_bloqueo(recurso, lock_token)

    if saga_id:
        cache_service.guardar_temporal("reservation", str(saga_id), {"id_locacion": id_locacion, "reservas": reservas}, ttl_segundos=600)
    cache_service.incrementar_contador("inventory", "reserve_success")
    return render_response({"status": "RESERVADO", "saga_id": saga_id, "id_locacion": id_locacion, "reservas": reservas}, status=200, root_tag="reserva_response")


@app.post("/api/v1/inventory/cancel-reservation")
@documentar(
    "Compensación de la Saga: libera una reserva",
    cuerpo={"saga_id": "saga-demo-001"},
    raiz_xml="cancelacion_request",
    respuesta={"status": "RESERVA_CANCELADA", "liberados": 1},
    raiz_respuesta="compensacion_response",
    errores=("400", "404"),
    exito="200",
)
@requiere_auth("store_manager", "warehouse")
def cancelar_reserva():
    """
    Libera las cantidades reservadas. Acepta {saga_id} (se recupera y consume la reserva de Redis)
    o {id_locacion, reservas:[{id_lote, cantidad}]} explícitos.
    """
    datos = leer_cuerpo(requerido=True)
    if datos.get("saga_id") and not datos.get("reservas"):
        guardada = cache_service.consumir_temporal("reservation", str(datos["saga_id"]))
        if not guardada:
            return error_response(404, "no_encontrado", f"No hay reserva vigente para la saga {datos['saga_id']}.")
        datos = {**datos, **guardada}
    requerir_campos(datos, "id_locacion", "reservas")
    id_locacion = entero(datos, "id_locacion", minimo=1)
    reservas = datos["reservas"] if isinstance(datos["reservas"], list) else []
    for r in reservas:
        validar_uuid(r.get("id_lote"), "id_lote")
        decimal_pos(r, "cantidad")

    with transaccion(id_usuario=g.usuario_actual.get("sub"), usuario_email=g.usuario_actual.get("email")) as conn:
        for r in reservas:
            conn.execute(
                text(
                    """
                    UPDATE operacion.existencia
                    SET cantidad_reservada = GREATEST(0, cantidad_reservada - :cant), actualizado_en = now()
                    WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc
                    """
                ),
                {"cant": float(r["cantidad"]), "lote": r["id_lote"], "loc": id_locacion},
            )
    cache_service.incrementar_contador("inventory", "reserve_cancelled")
    return render_response({"status": "RESERVA_CANCELADA", "liberados": len(reservas)}, status=200, root_tag="compensacion_response")


if __name__ == "__main__":
    ejecutar(app, "INVENTORY_SERVICE_PORT", 5003)
