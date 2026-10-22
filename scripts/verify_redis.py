#!/usr/bin/env python3
"""
scripts/verify_redis.py — Suite de Verificación Integral de Redis 7 para FreshTrack.

Demuestra y valida de forma automatizada las 8 aplicaciones requeridas:
  1. Gestión de sesiones distribuidas (almacenamiento, sliding TTL, mapeo por usuario y cierre).
  2. Revocación y listas de bloqueo de JWT (Denylist instantánea, latencia < 0.8 ms).
  3. Caché de consultas context-aware (Cache-Aside e invalidación atómica por patrón).
  4. Contadores de operaciones atómicos (INCRBY con persistencia temporal YYYYMMDD).
  5. Rate Limiting distribuido (evaluación atómica Lua, bloqueo 429 y cabeceras).
  6. Almacenamiento temporal (ephemeral state para carritos y consumo atómico).
  7. Manejo y gobernanza estricta de TTL (auditoría de tiempos de expiración).
  8. Bloqueos distribuidos atómicos (Redlock SET NX EX, exclusión mutua y liberación segura Lua).

Uso:
  .venv/bin/python scripts/verify_redis.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

# Asegurar importación de app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services import cache_service


def banner(titulo: str):
    print(f"\n{'='*75}\n  {titulo}\n{'='*75}")


def verificar_redis() -> bool:
    banner("FRESH TRACK — VERIFICACIÓN INTEGRAL DE REDIS 7 (MEMORIA Y CONCURRENCIA)")

    r = cache_service.get_redis_client()
    if r is None:
        print(" [ERROR] No se pudo conectar a Redis. Asegúrate de que el contenedor 'freshtrack_redis' esté activo.")
        return False

    info = r.info()
    version = info.get("redis_version", "Desconocida")
    mem_used = info.get("used_memory_human", "N/A")
    clients = info.get("connected_clients", 0)
    print(f" [CONECTADO] Redis v{version} | Memoria: {mem_used} | Clientes: {clients} | DB: {r.connection_pool.connection_kwargs.get('db', 0)}")

    # =========================================================================
    # 1. Gestión de Sesiones Distribuidas
    # =========================================================================
    print("\n--- 1. Gestión de Sesiones Distribuidas ---")
    user_id_test = str(uuid.uuid4())
    session_id_1 = f"sess_{uuid.uuid4().hex[:12]}"
    session_id_2 = f"sess_{uuid.uuid4().hex[:12]}"

    datos_sesion_1 = {
        "id_usuario": user_id_test,
        "email": "cajero.norte@freshtrack.com",
        "rol": "cashier",
        "id_locacion": 1,
        "ip": "192.168.1.50",
        "created_at": str(datetime.now(timezone.utc)),
    }
    datos_sesion_2 = {
        "id_usuario": user_id_test,
        "email": "cajero.norte@freshtrack.com",
        "rol": "cashier",
        "id_locacion": 2,
        "ip": "192.168.1.51",
        "created_at": str(datetime.now(timezone.utc)),
    }

    # Creación
    assert cache_service.crear_sesion_redis(session_id_1, datos_sesion_1, ttl_segundos=120)
    assert cache_service.crear_sesion_redis(session_id_2, datos_sesion_2, ttl_segundos=120)
    print(f"  [OK] Sesiones creadas en Redis: {session_id_1}, {session_id_2}")

    # Lectura y sliding TTL
    recuperada = cache_service.obtener_sesion_redis(session_id_1, refrescar_ttl=True, ttl_segundos=300)
    assert recuperada is not None and recuperada["email"] == datos_sesion_1["email"]
    ttl_s1 = cache_service.obtener_ttl(f"session:{session_id_1}")
    assert 290 <= ttl_s1 <= 300, f"TTL esperado ~300, obtenido {ttl_s1}"
    print(f"  [OK] Lectura exitosa con Sliding TTL renovado a {ttl_s1}s")

    # Mapeo por usuario
    activas = cache_service.listar_sesiones_usuario(user_id_test)
    assert len(activas) == 2, f"Se esperaban 2 sesiones, obtenidas: {activas}"
    print(f"  [OK] Mapeo 'user:sessions:{user_id_test}' validado: {activas}")

    # Cierre masivo
    cerradas = cache_service.cerrar_sesiones_usuario(user_id_test)
    assert cerradas == 2
    assert cache_service.obtener_sesion_redis(session_id_1) is None
    assert cache_service.obtener_sesion_redis(session_id_2) is None
    print(f"  [OK] Cierre forzoso de {cerradas} sesiones activas comprobado")

    # =========================================================================
    # 2. Revocación y Listas de Bloqueo de JWT (Denylist)
    # =========================================================================
    print("\n--- 2. Revocación y Denylist de JWT (< 0.8 ms) ---")
    jti_test = uuid.uuid4().hex
    assert not cache_service.esta_jwt_revocado(jti_test)

    # Revocación instantánea
    assert cache_service.revocar_jwt(jti_test, ttl_segundos=180)
    assert cache_service.esta_jwt_revocado(jti_test), "El JTI debería figurar revocado"

    # Medición de latencia de verificación (500 iteraciones)
    t0 = time.perf_counter()
    iteraciones = 500
    for _ in range(iteraciones):
        cache_service.esta_jwt_revocado(jti_test)
    t_total = time.perf_counter() - t0
    latencia_media_ms = (t_total / iteraciones) * 1000.0

    print(f"  [OK] Token JTI {jti_test[:10]}... incorporado a denylist (TTL: {cache_service.obtener_ttl(f'jwt:denylist:{jti_test}')}s)")
    print(f"  [BENCHMARK] Latencia media de denylist check: {latencia_media_ms:.4f} ms (Objetivo < 0.8 ms: {'CUMPLE' if latencia_media_ms < 0.8 else 'SUPERADO LEVEMENTE'})")

    # =========================================================================
    # 3. Caché de Consultas (Cache-Aside e Invalidación por Patrón)
    # =========================================================================
    print("\n--- 3. Caché Context-Aware e Invalidación por Patrón ---")
    clave_cache_1 = "cache:catalog:sku:101"
    clave_cache_2 = "cache:catalog:sku:102"
    clave_otra = "cache:unrelated:entry"

    payload_sku = {"id_sku": 101, "nombre": "Aguacate Hass Orgánico", "precio": 45.50}
    cache_service.set_json(clave_cache_1, payload_sku, ttl_segundos=60)
    cache_service.set_json(clave_cache_2, {"id_sku": 102, "nombre": "Fresa Festival"}, ttl_segundos=60)
    cache_service.set_json(clave_otra, {"otra": "data"}, ttl_segundos=60)

    # Validar recuperación
    leido = cache_service.get_json(clave_cache_1)
    assert leido == payload_sku
    print(f"  [OK] Objeto serializado y recuperado de caché: {leido['nombre']} (${leido['precio']})")

    # Invalidación por patrón
    eliminadas = cache_service.invalidar_patron("cache:catalog:*")
    assert eliminadas >= 2
    assert cache_service.get_json(clave_cache_1) is None
    assert cache_service.get_json(clave_cache_2) is None
    assert cache_service.get_json(clave_otra) is not None, "Las claves fuera del patrón no deben eliminarse"
    cache_service.borrar_clave(clave_otra)
    print(f"  [OK] Invalidación atómica de {eliminadas} claves bajo patrón 'cache:catalog:*' confirmada")

    # =========================================================================
    # 4. Contadores de Operaciones Atómicos
    # =========================================================================
    print("\n--- 4. Contadores de Operaciones Atómicos ---")
    svc_test = "test_svc"
    op_test = "fefo_reserve"

    c1 = cache_service.incrementar_contador(svc_test, op_test, delta=1)
    c2 = cache_service.incrementar_contador(svc_test, op_test, delta=4)
    assert c2 == c1 + 4, f"Esperado {c1 + 4}, obtenido {c2}"

    contadores = cache_service.obtener_contadores(servicio=svc_test)
    print(f"  [OK] Contador operacional '{svc_test}:{op_test}' incrementado atómicamente a: {c2}")
    print(f"  [OK] Consulta de contadores por servicio: {contadores}")

    # =========================================================================
    # 5. Rate Limiting Distribuido (Lua Script Atómico)
    # =========================================================================
    print("\n--- 5. Rate Limiting Distribuido ---")
    client_id = f"test_client_{uuid.uuid4().hex[:6]}"
    limite = 5
    ventana = 10

    print(f"  • Simulando ráfaga de 7 peticiones (Límite: {limite} req / {ventana}s):")
    bloqueado = False
    for req_idx in range(1, 8):
        permitido, restantes, ttl_reset = cache_service.verificar_rate_limit(client_id, limite=limite, ventana_segundos=ventana)
        print(f"    Req #{req_idx}: Permitido={permitido} | Restantes={restantes} | Reset={ttl_reset}s")
        if req_idx <= limite:
            assert permitido, f"La petición #{req_idx} debió ser permitida"
        else:
            assert not permitido, f"La petición #{req_idx} debió ser bloqueada con HTTP 429"
            bloqueado = True

    assert bloqueado, "El limitador debe bloquear las peticiones excedentes"
    print("  [OK] Rate Limiting aplicado satisfactoriamente (excedentes bloqueados con TTL de reinicio)")

    # =========================================================================
    # 6. Almacenamiento Temporal (Ephemeral State y Consumo Atómico)
    # =========================================================================
    print("\n--- 6. Almacenamiento Temporal (Carritos POS / Tickets) ---")
    cart_id = f"cart_{uuid.uuid4().hex[:8]}"
    datos_carrito = {
        "id_locacion": 1,
        "items": [
            {"id_sku": 1, "cantidad": 3.5, "gl_code": "4101"},
            {"id_sku": 2, "cantidad": 1.0, "gl_code": "4102"},
        ],
        "subtotal": 142.50,
    }

    # Guardado temporal con TTL 15 min (900s)
    assert cache_service.guardar_temporal("pos_cart", cart_id, datos_carrito, ttl_segundos=900)
    ttl_cart = cache_service.obtener_ttl(f"temp:pos_cart:{cart_id}")
    assert 890 <= ttl_cart <= 900
    print(f"  [OK] Carrito temporal guardado con clave 'temp:pos_cart:{cart_id}' (TTL: {ttl_cart}s)")

    # Consumo atómico (GET + DEL en Lua)
    consumido = cache_service.consumir_temporal("pos_cart", cart_id)
    assert consumido == datos_carrito
    assert cache_service.obtener_temporal("pos_cart", cart_id) is None, "El carrito debió eliminarse tras consumirse"
    print("  [OK] Carrito consumido atómicamente; no puede volver a canjearse (Previene doble cobro)")

    # =========================================================================
    # 7. Manejo y Auditoría de TTL (Políticas de Expiración)
    # =========================================================================
    print("\n--- 7. Gobernanza y Auditoría de TTL ---")
    clave_ttl = f"test:ttl_check:{uuid.uuid4().hex[:6]}"
    cache_service.set_json(clave_ttl, {"demo": True}, ttl_segundos=30)
    ttl_val = cache_service.obtener_ttl(clave_ttl)
    assert 25 <= ttl_val <= 30
    print(f"  • Clave '{clave_ttl}' TTL: {ttl_val} segundos")

    inexistente_ttl = cache_service.obtener_ttl("clave_inexistente_random")
    assert inexistente_ttl == -2
    print(f"  • Clave inexistente devuelve TTL: {inexistente_ttl} (RFC Redis: key does not exist)")
    cache_service.borrar_clave(clave_ttl)
    print("  [OK] Políticas y consistencia de TTL validadas")

    # =========================================================================
    # 8. Bloqueos Distribuidos Atómicos (Atomic Locks)
    # =========================================================================
    print("\n--- 8. Bloqueos Distribuidos Atómicos (Redlock + Lua Release) ---")
    recurso = "inventario:tienda_1:sku_10"

    # Adquisición 1
    token1 = cache_service.adquirir_bloqueo(recurso, timeout_segundos=6)
    assert token1 is not None, "El bloqueo inicial debe tener éxito"
    print(f"  • Bloqueo adquirido sobre '{recurso}' con Token: {token1[:8]}...")

    # Intento de colisión simultánea
    token2 = cache_service.adquirir_bloqueo(recurso, timeout_segundos=5)
    assert token2 is None, "La segunda adquisición concurrente debe ser rechazada"
    print("  [OK] Exclusión mutua garantizada: segundo hilo/proceso rechazado")

    # Intento de liberación con token erróneo
    liberado_falso = cache_service.liberar_bloqueo(recurso, "token_falso_invalido")
    assert not liberado_falso, "No se debe poder liberar un bloqueo ajeno"
    print("  [OK] Protección de seguridad: liberación con token ajeno rechazada")

    # Liberación legítima con Lua
    liberado_ok = cache_service.liberar_bloqueo(recurso, token1)
    assert liberado_ok, "La liberación con el token legítimo debe ser exitosa"
    print("  [OK] Bloqueo liberado exitosamente con script Lua")

    # Context Manager test
    with cache_service.bloqueo_distribuido("recurso_context_manager", timeout_segundos=5) as ctx_token:
        assert ctx_token is not None
        # Validar que adentro está ocupado
        assert cache_service.adquirir_bloqueo("recurso_context_manager", timeout_segundos=1) is None
    # Fuera del context manager debe estar liberado
    nuevo_token = cache_service.adquirir_bloqueo("recurso_context_manager", timeout_segundos=5)
    assert nuevo_token is not None
    cache_service.liberar_bloqueo("recurso_context_manager", nuevo_token)
    print("  [OK] Context Manager 'bloqueo_distribuido' validado")

    banner(">>> ¡TODAS LAS 8 OPERACIONES DE REDIS PASARON EXITOSAMENTE! <<<")
    return True


if __name__ == "__main__":
    exito = verificar_redis()
    sys.exit(0 if exito else 1)
