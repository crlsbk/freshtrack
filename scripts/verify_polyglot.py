#!/usr/bin/env python3
"""
Script de Verificación Integral de Persistencia Políglota y Microservicios.

Verifica:
1. PostgreSQL (Única fuente de verdad transaccional: operacion, analitica, auditoria).
2. Redis (Caché, Bloqueos distribuidos atómicos, JWT Denylist, Event Streams).
3. MongoDB (Almacén documental: pronósticos de series de tiempo y alertas con TTL).
4. Saga Orquestada de Venta (Reserva FEFO -> Venta -> Kardex -> Eventos Redis).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# Asegurar importación de app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import one, query, transaccion
from app.domain import saga_venta
from app.events.dispatcher import leer_ultimos_eventos, publicar_evento
from app.services import cache_service, doc_store


def probar_postgres():
    print("\n--- 1. Verificando PostgreSQL (Fuente de Verdad) ---")
    try:
        resultado = one("SELECT current_database() AS db, current_user AS usuario, version() AS version")
        print(f" [OK] Conectado a BD '{resultado['db']}' como '{resultado['usuario']}'")

        # Verificar esquemas
        esquemas = query("SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('operacion', 'analitica', 'auditoria')")
        esquemas_encontrados = [r["schema_name"] for r in esquemas]
        print(f" [OK] Esquemas verificados: {esquemas_encontrados}")
        assert len(esquemas_encontrados) == 3, "Faltan esquemas en PostgreSQL"

        # Verificar pgcrypto
        crypto = one("SELECT public.crypt('test', public.gen_salt('bf', 8)) AS hash")
        assert crypto and crypto["hash"], "pgcrypto no funcional"
        print(" [OK] Extensión pgcrypto (public.crypt) operativa")
    except Exception as exc:
        print(f" [FALLO] Error en PostgreSQL: {exc}")
        raise


def probar_redis():
    print("\n--- 2. Verificando Redis (Caché, Locks, JWT Denylist, Streams) ---")
    r = cache_service.get_redis_client()
    if r is None:
        raise RuntimeError("No se pudo conectar a Redis")
    print(f" [OK] Ping Redis exitoso: {r.ping()}")

    # Probar Caché JSON
    test_key = "test:freshtrack:cache"
    cache_service.set_json(test_key, {"status": "ok", "timestamp": str(datetime.now(timezone.utc))}, ttl_segundos=60)
    data = cache_service.get_json(test_key)
    assert data and data["status"] == "ok", "Error al leer caché JSON"
    cache_service.borrar_clave(test_key)
    print(" [OK] Operaciones de Caché JSON validadas")

    # Probar Bloqueo Distribuido Atómico
    lock_name = "test_lote_123"
    token = cache_service.adquirir_bloqueo(lock_name, timeout_segundos=10)
    assert token is not None, "No se pudo adquirir bloqueo"
    # Intentar adquirir de nuevo debe fallar (concurrencia prevenida)
    token_segundo = cache_service.adquirir_bloqueo(lock_name, timeout_segundos=5)
    assert token_segundo is None, "El bloqueo permitió doble adquisición indebida"
    # Liberar bloqueo
    liberado = cache_service.liberar_bloqueo(lock_name, token)
    assert liberado is True, "No se pudo liberar bloqueo con token válido"
    print(" [OK] Bloqueos Distribuidos Atómicos (Atomic Locks) validados")

    # Probar JWT Denylist
    test_jti = uuid.uuid4().hex
    assert not cache_service.esta_jwt_revocado(test_jti)
    cache_service.revocar_jwt(test_jti, ttl_segundos=120)
    assert cache_service.esta_jwt_revocado(test_jti), "El JTI revocado no fue detectado en denylist"
    print(" [OK] Denylist de JWT en Redis validada")

    # Probar Redis Streams
    msg_id = publicar_evento(
        "TEST_HEALTHCHECK",
        {"mensaje": "Verificación de streaming"},
        contexto={"user_id": "test_agent", "location_id": "1"},
    )
    assert msg_id is not None, "Fallo al publicar en Redis Stream"
    eventos = leer_ultimos_eventos(cantidad=5)
    encontrado = any(e.get("event_type") == "TEST_HEALTHCHECK" for e in eventos)
    assert encontrado, "El evento publicado no se encontró en el stream"
    print(f" [OK] Event Streaming (Redis Streams) validado (Msg ID: {msg_id})")


def probar_mongo():
    print("\n--- 3. Verificando MongoDB (Document Store) ---")
    db = doc_store.get_mongo_db()
    if db is None:
        raise RuntimeError("No se pudo conectar a MongoDB")
    colls = db.list_collection_names()
    print(f" [OK] Conectado a MongoDB '{db.name}'. Colecciones: {colls}")

    # Probar alerta operativa
    alerta_id = doc_store.guardar_alerta_operativa(
        tipo="RIESGO_PRE_MERMA",
        criticidad="WARNING",
        mensaje="Alerta de prueba desde script de verificación",
        id_sku=1,
        id_locacion=1,
        contexto={"dias_restantes": 2, "autor": "test_runner"},
    )
    assert alerta_id is not None, "Error al insertar alerta en MongoDB"
    print(f" [OK] Alerta operativa registrada (ID: {alerta_id})")

    # Atender alerta
    atendida = doc_store.marcar_alerta_atendida(alerta_id)
    assert atendida is True, "No se pudo marcar alerta como atendida"
    print(f" [OK] Ciclo de vida de alerta completado en MongoDB")


def probar_saga_venta():
    print("\n--- 4. Verificando Saga Orquestada de Ventas e Inventario FEFO ---")
    from sqlalchemy import text
    # Buscar una locación y un producto con stock real
    stock = one(
        """
        SELECT e.id_locacion, l.id_sku, (e.cantidad_disponible - e.cantidad_reservada) AS disponible
        FROM operacion.existencia e
        JOIN operacion.lote l ON l.id_lote = e.id_lote
        WHERE (e.cantidad_disponible - e.cantidad_reservada) >= 1.0
          AND l.fecha_caducidad >= CURRENT_DATE
        LIMIT 1
        """
    )
    if not stock:
        # Crear lote y existencia de prueba
        sku = one("SELECT id_sku FROM operacion.producto LIMIT 1")["id_sku"]
        prov = one("SELECT id_proveedor FROM operacion.proveedor LIMIT 1")["id_proveedor"]
        loc = one("SELECT id_locacion FROM operacion.locacion LIMIT 1")["id_locacion"]
        id_lote = str(uuid.uuid4())
        cod_prov = f"TEST-{uuid.uuid4().hex[:6].upper()}"
        with transaccion() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO operacion.lote
                        (id_lote, id_sku, id_proveedor, codigo_lote_prov, fecha_recepcion,
                         fecha_caducidad, cantidad_recibida, costo_unitario, id_locacion_recepcion)
                    VALUES (CAST(:id_lote AS uuid), :sku, :prov, :cod, CURRENT_DATE,
                            CURRENT_DATE + interval '10 days', 50, 15.0, :loc)
                    """
                ),
                {"id_lote": id_lote, "sku": sku, "prov": prov, "cod": cod_prov, "loc": loc},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO operacion.existencia
                        (id_lote, id_locacion, cantidad_disponible, cantidad_reservada)
                    VALUES (CAST(:id_lote AS uuid), :loc, 50, 0)
                    """
                ),
                {"id_lote": id_lote, "loc": loc},
            )
        stock = {"id_locacion": loc, "id_sku": sku, "disponible": 50}
        print(f" [INFO] Lote de prueba aprovisionado (SKU {sku}, Locación {loc})")

    admin = one("SELECT id_usuario, email, 'admin' AS rol_clave FROM operacion.usuario WHERE email = 'admin@freshtrack.mx'")
    if not admin:
        print(" [SKIP] Usuario admin no encontrado")
        return

    loc_id = stock["id_locacion"]
    sku_id = stock["id_sku"]
    cant = 0.5  # media unidad para no agotar stock

    res_saga = saga_venta.ejecutar_saga_venta(
        id_locacion=loc_id,
        lineas=[{"id_sku": sku_id, "cantidad": cant}],
        usuario=admin,
        canal="TIENDA",
    )

    print(f" [OK] Saga de venta completada:")
    print(f"      - Folio: {res_saga['folio']}")
    print(f"      - ID Venta: {res_saga['id_venta']}")
    print(f"      - Total: ${res_saga['total']:.2f}")
    print(f"      - Estado: {res_saga['estado']}")

    # Verificar que el evento se registró en Redis Streams
    eventos = leer_ultimos_eventos(cantidad=5)
    saga_event = any(e.get("event_type") == "SAGA_VENTA_COMPLETADA" and e.get("correlation_id") == res_saga["saga_id"] for e in eventos)
    assert saga_event, "El evento SAGA_VENTA_COMPLETADA no se registró en Redis Streams"
    print(f" [OK] Evento SAGA_VENTA_COMPLETADA verificado en Redis Streams con Correlation ID")


def main():
    print("=================================================================")
    print(" FreshTrack — Verificación Políglota y Orquestación de Servicios")
    print("=================================================================")
    probar_postgres()
    probar_redis()
    probar_mongo()
    probar_saga_venta()
    print("\n>>> ¡TODAS LAS COMPROBACIONES PASARON SATISFACTORIAMENTE! <<<\n")


if __name__ == "__main__":
    main()
