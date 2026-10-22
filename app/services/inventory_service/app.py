"""
Microservicio 3: Inventory & FEFO Engine (`svc-inventory`) — FreshTrack (Flask).

Puerto: 5003
Responsabilidad:
- Gestión de existencias y lotes perecederos en PostgreSQL ('operacion.existencia', 'operacion.lote').
- Algoritmo FEFO estricto con cálculo dinámico de días restantes.
- Bloqueo distribuido atómico (Redlock en Redis) para concurrencia en reserva.
- Pasos de Reserva, Confirmación y Compensación para la Saga Orquestada de Ventas.
- Soporte dual JSON y XML para consultas de inventario.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import Flask, g, request
from sqlalchemy import text

from app.config import Config
from app.db import a_float, a_int, one, query, transaccion
from app.domain.ventas import _lotes_para_consumo, repartir_fefo
from app.events.dispatcher import publicar_evento
from app.services import cache_service
from app.services.common.auth import requiere_auth
from app.services.common.rate_limit import limite_tasa
from app.services.common.response import render_response
from app.services.common.swagger import registrar_openapi

app = Flask(__name__)
app.config.from_object(Config)


@app.get("/health")
def health():
    pg_ok = False
    try:
        res = one("SELECT 1 AS ok")
        pg_ok = bool(res and res["ok"] == 1)
    except Exception:
        pass

    redis_ok = False
    try:
        r = cache_service.get_redis_client()
        redis_ok = bool(r and r.ping())
    except Exception:
        pass

    estado = "HEALTHY" if (pg_ok and redis_ok) else "DEGRADED"
    return render_response({
        "service": "svc-inventory",
        "status": estado,
        "dependencies": {"postgres": pg_ok, "redis": redis_ok},
    }, status=200 if estado == "HEALTHY" else 503, root_tag="service_health")


@app.get("/api/v1/inventory/stock")
@requiere_auth()
def consultar_stock():
    """Consulta existencias disponibles con soporte JSON/XML y contexto de tienda."""
    ctx = g.contexto
    id_locacion = ctx.get("location_id") or a_int(request.args.get("id_locacion"), 0) or None
    id_sku = a_int(request.args.get("id_sku"), 0) or None

    condiciones = ["e.cantidad_disponible > 0"]
    params = {}
    if id_locacion:
        condiciones.append("e.id_locacion = :loc")
        params["loc"] = id_locacion
    if id_sku:
        condiciones.append("l.id_sku = :sku")
        params["sku"] = id_sku

    where = " AND ".join(condiciones)
    sql = f"""
        SELECT e.id_existencia::text AS id_existencia,
               e.id_locacion,
               loc.nombre AS locacion,
               l.id_sku,
               p.nombre AS producto,
               l.codigo_lote_prov,
               l.fecha_caducidad,
               (l.fecha_caducidad - CURRENT_DATE) AS dias_restantes,
               e.cantidad_disponible,
               e.cantidad_reservada,
               (e.cantidad_disponible - e.cantidad_reservada) AS disponible_neto
        FROM operacion.existencia e
        JOIN operacion.lote l ON l.id_lote = e.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
        WHERE {where}
        ORDER BY l.fecha_caducidad ASC
    """
    filas = query(sql, **params)
    items = []
    for f in filas:
        d = dict(f)
        d["cantidad_disponible"] = a_float(d["cantidad_disponible"])
        d["cantidad_reservada"] = a_float(d["cantidad_reservada"])
        d["disponible_neto"] = a_float(d["disponible_neto"])
        items.append(d)

    return render_response({"total": len(items), "existencias": items}, status=200, root_tag="inventario_stock")


@app.get("/api/v1/inventory/fefo-queue/<int:id_sku>/<int:id_locacion>")
@requiere_auth()
def cola_fefo(id_sku: int, id_locacion: int):
    """Devuelve la cola de consumo FEFO estricta ordenada por vencimiento más próximo."""
    with transaccion() as conn:
        lotes = _lotes_para_consumo(conn, id_sku, id_locacion, bloquear=False)
    for l in lotes:
        l["cantidad_disponible"] = a_float(l["cantidad_disponible"])
        l["cantidad_reservada"] = a_float(l.get("cantidad_reservada") or 0)
        l["costo_unitario"] = a_float(l["costo_unitario"])
    return render_response({"id_sku": id_sku, "id_locacion": id_locacion, "lotes_fefo": lotes}, status=200, root_tag="fefo_queue")


@app.post("/api/v1/inventory/reserve-fefo")
@requiere_auth("admin", "store_manager", "warehouse")
@limite_tasa(limite=60, ventana_segundos=60)
def reservar_fefo():
    """
    PASO 1 DE SAGA: Reserva temporal de lotes en orden FEFO con bloqueo Redlock en Redis.
    Incrementa 'cantidad_reservada' en operacion.existencia.
    """
    datos = request.get_json(silent=True) or {}
    id_locacion = a_int(datos.get("id_locacion"), 0)
    lineas = datos.get("lineas", [])
    saga_id = datos.get("saga_id")

    if not id_locacion or not lineas:
        return render_response({"error": "bad_request", "mensaje": "id_locacion y lineas son obligatorios."}, status=400, root_tag="reserva_response")

    # Bloqueo atómico distribuido en Redis para evitar condiciones de carrera simultáneas
    lock_token = cache_service.adquirir_bloqueo(f"inventory:loc:{id_locacion}:reserve", timeout_segundos=8)

    reservas = []
    try:
        with transaccion() as conn:
            for item in lineas:
                sku = int(item["id_sku"])
                cantidad = float(item["cantidad"])

                lotes = _lotes_para_consumo(conn, sku, id_locacion, bloquear=True)
                consumos = repartir_fefo(lotes, cantidad)
                cubierto = sum(c["consumido"] for c in consumos)

                if round(cubierto, 3) < round(cantidad, 3):
                    cache_service.incrementar_contador("inventory", "reserve_failed")
                    return render_response({
                        "error": "insufficient_stock",
                        "id_sku": sku,
                        "disponible": cubierto,
                        "solicitado": cantidad,
                    }, status=409, root_tag="reserva_response")

                for c in consumos:
                    conn.execute(
                        text(
                            """
                            UPDATE operacion.existencia
                            SET cantidad_reservada = cantidad_reservada + :cant,
                                actualizado_en = now()
                            WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc
                            """
                        ),
                        {"cant": c["consumido"], "lote": c["id_lote"], "loc": id_locacion},
                    )
                    reservas.append({
                        "id_lote": c["id_lote"],
                        "id_sku": sku,
                        "cantidad": c["consumido"],
                        "costo_unitario": c["costo_unitario"],
                        "codigo_lote": c.get("codigo_lote_prov"),
                    })

        # Almacenar temporalmente el estado de la reserva en Redis (TTL 10 min)
        if saga_id:
            cache_service.guardar_temporal("reservation", saga_id, {"id_locacion": id_locacion, "reservas": reservas}, ttl_segundos=600)

        cache_service.incrementar_contador("inventory", "reserve_success")
        return render_response({"status": "RESERVADO", "saga_id": saga_id, "reservas": reservas}, status=200, root_tag="reserva_response")
    except Exception as exc:
        return render_response({"error": "error_reserva", "detalle": str(exc)}, status=500, root_tag="reserva_response")
    finally:
        if lock_token:
            cache_service.liberar_bloqueo(f"inventory:loc:{id_locacion}:reserve", lock_token)


@app.post("/api/v1/inventory/cancel-reservation")
@requiere_auth("admin", "store_manager", "warehouse")
def cancelar_reserva():
    """COMPENSACIÓN DE SAGA: Cancela la reserva si la venta falló."""
    datos = request.get_json(silent=True) or {}
    id_locacion = a_int(datos.get("id_locacion"), 0)
    reservas = datos.get("reservas", [])

    try:
        with transaccion() as conn:
            for r in reservas:
                conn.execute(
                    text(
                        """
                        UPDATE operacion.existencia
                        SET cantidad_reservada = GREATEST(0, cantidad_reservada - :cant),
                            actualizado_en = now()
                        WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc
                        """
                    ),
                    {"cant": r["cantidad"], "lote": r["id_lote"], "loc": id_locacion},
                )
        return render_response({"status": "RESERVA_CANCELADA", "liberados": len(reservas)}, status=200, root_tag="compensacion_response")
    except Exception as exc:
        return render_response({"error": "error_compensacion", "detalle": str(exc)}, status=500, root_tag="compensacion_response")


registrar_openapi(
    app,
    titulo="Inventory & FEFO Engine Service (FreshTrack)",
    descripcion="Microservicio para existencias de lotes perecederos, algoritmo FEFO y reservas para Sagas.",
    version="1.0.0",
    paths={
        "/health": {"get": {"summary": "Healthcheck del microservicio", "responses": {"200": {"description": "Estado saludable"}}}},
        "/api/v1/inventory/stock": {"get": {"summary": "Existencias por tienda con soporte JSON/XML", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Lista de existencias"}}}},
        "/api/v1/inventory/fefo-queue/{id_sku}/{id_locacion}": {"get": {"summary": "Cola FEFO ordenada", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Cola FEFO"}}}},
        "/api/v1/inventory/reserve-fefo": {"post": {"summary": "Paso 1 de Saga: reserva FEFO", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Lotes reservados"}}}},
        "/api/v1/inventory/cancel-reservation": {"post": {"summary": "Compensación de Saga: liberación de reserva", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Reserva liberada"}}}},
    },
)

if __name__ == "__main__":
    port = int(os.getenv("INVENTORY_SERVICE_PORT", "5003"))
    app.run(host="0.0.0.0", port=port, debug=False)
