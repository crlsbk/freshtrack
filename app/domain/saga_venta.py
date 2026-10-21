"""
Orquestador de Saga para Ventas e Inventario FEFO (Saga Pattern Orquestada).

Coordina la transacción distribuida entre el dominio comercial (Ventas)
y el dominio logístico (Inventario / FEFO) mediante pasos compensables:

    [Paso 1: Reservar Inventario FEFO]
          │
          ├── (Éxito) ──> [Paso 2: Registrar Venta y Detalle]
          │                     │
          │                     ├── (Éxito) ──> [Paso 3: Confirmar y Descontar Inventario + Kardex]
          │                     │                     │
          │                     │                     └──> Evento: SAGA_VENTA_COMPLETADA
          │                     │
          │                     └── (Falla) ──> [Compensación: Cancelar Reserva de Inventario]
          │                                           │
          │                                           └──> Evento: SAGA_VENTA_COMPENSADA
          │
          └── (Falla) ──> Abortar (Stock insuficiente o caducado)

Cumple con la premisa: PostgreSQL es la única fuente de verdad transaccional,
mientras Redis Streams registra los eventos de dominio y estado de la saga.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text

from app import auditoria
from app.db import a_float, transaccion
from app.domain.ventas import _lotes_para_consumo, repartir_fefo
from app.events.dispatcher import publicar_evento

logger = logging.getLogger("freshtrack.saga")


class ErrorSagaVenta(Exception):
    """Excepción base para fallas durante la ejecución de la saga."""
    pass


def ejecutar_saga_venta(
    *,
    id_locacion: int,
    lineas: list[dict[str, Any]],
    usuario: dict[str, Any],
    canal: str = "TIENDA",
) -> dict[str, Any]:
    """
    Ejecuta el flujo orquestado de la saga de venta con compensación garantizada.
    
    lineas: [{"id_sku": int, "cantidad": float}]
    """
    if not lineas:
        raise ErrorSagaVenta("La venta no tiene líneas de producto.")

    lineas_limpias = []
    for l in lineas:
        cant = a_float(l.get("cantidad"))
        if cant > 0:
            lineas_limpias.append({"id_sku": int(l["id_sku"]), "cantidad": cant})
    if not lineas_limpias:
        raise ErrorSagaVenta("No hay cantidades válidas para procesar en la venta.")

    saga_id = uuid.uuid4().hex
    contexto = {
        "correlation_id": saga_id,
        "user_id": usuario.get("id_usuario"),
        "user_role": usuario.get("rol_clave"),
        "location_id": id_locacion,
    }

    publicar_evento(
        "SAGA_VENTA_INICIADA",
        {"saga_id": saga_id, "id_locacion": id_locacion, "lineas": lineas_limpias},
        contexto=contexto,
    )

    reservas_realizadas: list[dict[str, Any]] = []
    id_venta = str(uuid.uuid4())
    total_venta = 0.0
    asignaciones_finales: list[dict[str, Any]] = []

    try:
        with transaccion(
            id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
        ) as conn:
            # -----------------------------------------------------------------
            # PASO 1: Reservar Inventario en orden FEFO (Logística / Inventario)
            # -----------------------------------------------------------------
            for lin in lineas_limpias:
                id_sku = lin["id_sku"]
                solicitado = lin["cantidad"]

                prod = conn.execute(
                    text("SELECT nombre, precio_venta FROM operacion.producto WHERE id_sku = :s"),
                    {"s": id_sku},
                ).mappings().first()
                if not prod:
                    raise ErrorSagaVenta(f"El producto SKU {id_sku} no existe.")

                precio_venta = a_float(prod["precio_venta"])
                lotes_disponibles = _lotes_para_consumo(conn, id_sku, id_locacion, bloquear=True)
                consumos = repartir_fefo(lotes_disponibles, solicitado)
                total_cubierto = sum(c["consumido"] for c in consumos)

                if round(total_cubierto, 3) < round(solicitado, 3):
                    raise ErrorSagaVenta(
                        f"Stock insuficiente para '{prod['nombre']}' (disponible: {total_cubierto:.2f}, "
                        f"solicitado: {solicitado:.2f})."
                    )

                for c in consumos:
                    # Reserva temporal en existencia
                    conn.execute(
                        text(
                            """
                            UPDATE operacion.existencia
                            SET cantidad_reservada = cantidad_reservada + :cant,
                                actualizado_en = now()
                            WHERE id_lote = CAST(:id_lote AS uuid)
                              AND id_locacion = :loc
                            """
                        ),
                        {"cant": c["consumido"], "id_lote": c["id_lote"], "loc": id_locacion},
                    )
                    reservas_realizadas.append(
                        {
                            "id_lote": c["id_lote"],
                            "cantidad": c["consumido"],
                            "id_sku": id_sku,
                            "nombre": prod["nombre"],
                            "precio_unitario": precio_venta,
                            "costo_unitario": c["costo_unitario"],
                            "fecha_caducidad": str(c["fecha_caducidad"]),
                            "codigo_lote_prov": c.get("codigo_lote_prov"),
                        }
                    )

            publicar_evento(
                "SAGA_INVENTARIO_RESERVADO",
                {"saga_id": saga_id, "reservas_count": len(reservas_realizadas)},
                contexto=contexto,
            )

            # -----------------------------------------------------------------
            # PASO 2: Registrar Cabecera y Detalle de Venta (Comercial)
            # -----------------------------------------------------------------
            folio = conn.execute(
                text("SELECT operacion.fn_generar_folio_venta(:l)"), {"l": id_locacion}
            ).scalar()

            conn.execute(
                text(
                    """
                    INSERT INTO operacion.venta
                        (id_venta, folio, id_locacion, id_usuario, canal, total)
                    VALUES (CAST(:id_venta AS uuid), :folio, :id_locacion,
                            CAST(:uid AS uuid), :canal, 0)
                    """
                ),
                {
                    "id_venta": id_venta,
                    "folio": folio,
                    "id_locacion": id_locacion,
                    "uid": usuario["id_usuario"],
                    "canal": canal,
                },
            )

            for num_linea, res in enumerate(reservas_realizadas, start=1):
                subtotal = res["cantidad"] * res["precio_unitario"]
                total_venta += subtotal

                conn.execute(
                    text(
                        """
                        INSERT INTO operacion.venta_detalle
                            (id_venta, id_sku, id_lote, id_locacion, cantidad,
                             precio_unitario, subtotal)
                        VALUES (CAST(:id_v AS uuid), :sku,
                                CAST(:id_lote AS uuid), :loc, :cant,
                                :precio, :sub)
                        """
                    ),
                    {
                        "id_v": id_venta,
                        "sku": res["id_sku"],
                        "id_lote": res["id_lote"],
                        "loc": id_locacion,
                        "cant": res["cantidad"],
                        "precio": res["precio_unitario"],
                        "sub": subtotal,
                    },
                )

                # -------------------------------------------------------------
                # PASO 3: Confirmar Consumo Definitivo de Inventario y Kardex
                # -------------------------------------------------------------
                # Descuenta el inventario físico y libera la reserva
                conn.execute(
                    text(
                        """
                        UPDATE operacion.existencia
                        SET cantidad_disponible = cantidad_disponible - :cant,
                            cantidad_reservada  = cantidad_reservada - :cant,
                            actualizado_en      = now()
                        WHERE id_lote = CAST(:id_lote AS uuid)
                          AND id_locacion = :loc
                        """
                    ),
                    {"cant": res["cantidad"], "id_lote": res["id_lote"], "loc": id_locacion},
                )

                # Obtener la existencia restante actualizada
                saldo_restante = conn.execute(
                    text(
                        """
                        SELECT cantidad_disponible FROM operacion.existencia
                        WHERE id_lote = CAST(:id_lote AS uuid) AND id_locacion = :loc
                        """
                    ),
                    {"id_lote": res["id_lote"], "loc": id_locacion},
                ).scalar()

                # Registrar movimiento oficial de kardex (tipo 'VENTA')
                conn.execute(
                    text(
                        """
                        INSERT INTO operacion.movimiento_inventario
                            (id_lote, id_locacion, tipo, cantidad, cantidad_resultante,
                             costo_unitario, referencia_tipo, referencia_id, id_usuario)
                        VALUES (CAST(:id_lote AS uuid), :loc, 'VENTA',
                                :cant_neg, :resultante, :costo, 'VENTA',
                                CAST(:id_v AS uuid), CAST(:uid AS uuid))
                        """
                    ),
                    {
                        "id_lote": res["id_lote"],
                        "loc": id_locacion,
                        "cant_neg": -res["cantidad"],
                        "resultante": a_float(saldo_restante),
                        "costo": res["costo_unitario"],
                        "id_v": id_venta,
                        "uid": usuario["id_usuario"],
                    },
                )

                asignaciones_finales.append(
                    {
                        "id_sku": res["id_sku"],
                        "producto": res["nombre"],
                        "codigo_lote": res["codigo_lote_prov"],
                        "cantidad": res["cantidad"],
                        "precio_unitario": res["precio_unitario"],
                        "subtotal": round(subtotal, 2),
                    }
                )

            # Actualizar el total final de la venta
            conn.execute(
                text(
                    "UPDATE operacion.venta SET total = :total WHERE id_venta = CAST(:id_v AS uuid)"
                ),
                {"total": total_venta, "id_v": id_venta},
            )

        # Registro de auditoría inmutable
        auditoria.registrar(
            "REGISTER_SALE",
            tabla="venta",
            id_registro=id_venta,
            descripcion=(
                f"Venta {folio} por ${total_venta:,.2f} procesada exitosamente vía Saga "
                f"en locación {id_locacion}."
            ),
            id_usuario=usuario["id_usuario"],
            usuario_email=usuario["email"],
        )

        publicar_evento(
            "SAGA_VENTA_COMPLETADA",
            {
                "saga_id": saga_id,
                "id_venta": id_venta,
                "folio": folio,
                "total": total_venta,
                "asignaciones": asignaciones_finales,
            },
            contexto=contexto,
        )

        return {
            "saga_id": saga_id,
            "id_venta": id_venta,
            "folio": folio,
            "total": round(total_venta, 2),
            "lineas": asignaciones_finales,
            "estado": "COMPLETADA",
        }

    except Exception as exc:
        logger.error("Falla en la saga de venta (ID: %s): %s", saga_id, exc)
        # Emite evento de compensación
        publicar_evento(
            "SAGA_VENTA_COMPENSADA",
            {"saga_id": saga_id, "motivo": str(exc), "reservas_canceladas": len(reservas_realizadas)},
            contexto=contexto,
        )
        raise
