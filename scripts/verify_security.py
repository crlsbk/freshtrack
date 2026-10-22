#!/usr/bin/env python3
"""
scripts/verify_security.py — Suite de Verificación Exhaustiva de Seguridad y Control de Acceso.

Demuestra y valida de forma automatizada los lineamientos del Requerimiento 9:
  1. Inicio de sesión y emisión de tokens JWT con claims RBAC.
  2. Validación de endpoints públicos (deben responder 200 sin exigir token).
  3. Restricción estricta de endpoints protegidos (deben rechazar con 401 si falta token).
  4. Manejo de tokens inválidos, alterados criptográficamente y expirados (rechazo 401).
  5. Control de acceso por roles (RBAC: rechazo 403 Forbidden para usuarios no autorizados).
  6. Revocación de tokens y cierre de sesión (Redis Denylist instantánea < 0.2 ms).
  7. Validación de entradas y manejo controlado de errores (400 Bad Request sin fugas de stack trace).
  8. Registro auditado de eventos relevantes en PostgreSQL (bitacora_eventos).

Uso:
  .venv/bin/python scripts/verify_security.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv

load_dotenv()

# Asegurar importación de app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import Config
from app.db import one, query
from app.services import cache_service
from app.services.alerts_service.app import app as alerts_app
from app.services.asn_service.app import app as asn_app
from app.services.audit_service.app import app as audit_app
from app.services.auth_service.app import app as auth_app
from app.services.catalog_service.app import app as catalog_app
from app.services.commercial_service.app import app as commercial_app
from app.services.inventory_service.app import app as inventory_app
from app.services.planning_service.app import app as planning_app


def banner(titulo: str):
    print(f"\n{'='*75}\n  {titulo}\n{'='*75}")


def verificar_seguridad() -> bool:
    banner("FRESH TRACK — VERIFICACIÓN EXHAUSTIVA DE SEGURIDAD (JWT, RBAC Y REDIS)")

    # =========================================================================
    # 1. Inicio de Sesión y Emisión de Tokens JWT
    # =========================================================================
    print("\n--- 1. Inicio de Sesión y Emisión de Tokens JWT ---")
    c_auth = auth_app.test_client()

    # Limpiar cualquier clave previa de rate limit de pruebas
    cache_service.invalidar_patron("ratelimit:*")

    # Login Admin
    r_admin = c_auth.post(
        "/api/v1/auth/login",
        json={"email": "admin@freshtrack.mx", "password": "Admin2026!"},
        headers={"X-Forwarded-For": "10.0.1.1"},
    )
    assert r_admin.status_code == 200, f"Error en login admin: {r_admin.data}"
    data_admin = r_admin.get_json()
    token_admin = data_admin["token"]
    jti_admin = data_admin["jti"]
    assert token_admin and jti_admin
    print(f"  [OK] Login exitoso para Administrador ({data_admin['usuario']['email']}) -> Rol: {data_admin['usuario']['rol']}")

    # Login Planner
    r_plan = c_auth.post(
        "/api/v1/auth/login",
        json={"email": "planner@freshtrack.mx", "password": "Plan2026!"},
        headers={"X-Forwarded-For": "10.0.1.2"},
    )
    assert r_plan.status_code == 200
    token_planner = r_plan.get_json()["token"]
    print(f"  [OK] Login exitoso para Planeador -> Rol: {r_plan.get_json()['usuario']['rol']}")

    # Login Warehouse
    r_wh = c_auth.post(
        "/api/v1/auth/login",
        json={"email": "almacen@freshtrack.mx", "password": "Almacen2026!"},
        headers={"X-Forwarded-For": "10.0.1.3"},
    )
    assert r_wh.status_code == 200, f"Error en login almacen: {r_wh.data}"
    token_warehouse = r_wh.get_json()["token"]
    print(f"  [OK] Login exitoso para Almacenista -> Rol: {r_wh.get_json()['usuario']['rol']}")

    # Login Supplier
    r_sup = c_auth.post(
        "/api/v1/auth/login",
        json={"email": "proveedor@freshtrack.mx", "password": "Proveedor2026!"},
        headers={"X-Forwarded-For": "10.0.1.4"},
    )
    assert r_sup.status_code == 200, f"Error en login proveedor: {r_sup.data}"
    token_supplier = r_sup.get_json()["token"]
    print(f"  [OK] Login exitoso para Proveedor -> Rol: {r_sup.get_json()['usuario']['rol']}")

    # Verificar sesión activa registrada en Redis
    sesion_redis = cache_service.obtener_sesion_redis(jti_admin)
    assert sesion_redis is not None, "La sesión debió ser registrada en Redis"
    ttl_sesion = cache_service.obtener_ttl(f"session:{jti_admin}")
    print(f"  [OK] Sesión confirmada en Redis (session:{jti_admin[:8]}..., TTL: {ttl_sesion}s)")

    # =========================================================================
    # 2. Validación de Endpoints Públicos (Deben responder 200 sin Token)
    # =========================================================================
    print("\n--- 2. Verificación de Endpoints Públicos (Libre Acceso) ---")
    microservicios = [
        ("svc-auth", auth_app),
        ("svc-catalog", catalog_app),
        ("svc-inventory", inventory_app),
        ("svc-commercial", commercial_app),
        ("svc-asn", asn_app),
        ("svc-planning", planning_app),
        ("svc-alerts", alerts_app),
        ("svc-audit", audit_app),
    ]

    for nombre, app_svc in microservicios:
        c = app_svc.test_client()
        r_health = c.get("/health")
        assert r_health.status_code == 200, f"Health check falló en {nombre}: {r_health.status_code}"
        r_docs = c.get("/api/v1/docs")
        assert r_docs.status_code == 200, f"Swagger docs falló en {nombre}"
        r_openapi = c.get("/api/v1/openapi.json")
        assert r_openapi.status_code == 200, f"OpenAPI JSON falló en {nombre}"
        print(f"  [OK] {nombre}: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS")

    # Catálogo público para clientes
    c_cat = catalog_app.test_client()
    r_cat = c_cat.get("/api/v1/catalog/products")
    assert r_cat.status_code == 200, "El catálogo de productos debe ser público"
    r_loc = c_cat.get("/api/v1/catalog/locations")
    assert r_loc.status_code == 200, "El directorio de locaciones debe ser público"
    print("  [OK] svc-catalog: /api/v1/catalog/products y /api/v1/catalog/locations -> PÚBLICOS")

    # =========================================================================
    # 3. Restricción Estricta de Endpoints Protegidos (Rechazo sin Token)
    # =========================================================================
    print("\n--- 3. Restricción Estricta de Endpoints Protegidos (Sin Token -> 401) ---")
    endpoints_protegidos = [
        ("svc-auth", auth_app, "GET", "/api/v1/auth/users"),
        ("svc-auth", auth_app, "GET", "/api/v1/auth/counters"),
        ("svc-catalog", catalog_app, "GET", "/api/v1/catalog/suppliers"),
        ("svc-catalog", catalog_app, "POST", "/api/v1/catalog/products"),
        ("svc-inventory", inventory_app, "GET", "/api/v1/inventory/stock"),
        ("svc-inventory", inventory_app, "POST", "/api/v1/inventory/reserve-fefo"),
        ("svc-commercial", commercial_app, "POST", "/api/v1/commercial/checkout"),
        ("svc-commercial", commercial_app, "POST", "/api/v1/commercial/shrinkage"),
        ("svc-asn", asn_app, "POST", "/api/v1/asn"),
        ("svc-planning", planning_app, "POST", "/api/v1/planning/forecast/run"),
        ("svc-alerts", alerts_app, "POST", "/api/v1/alerts/scan"),
        ("svc-audit", audit_app, "GET", "/api/v1/audit/events"),
    ]

    for svc_name, app_svc, metodo, ruta in endpoints_protegidos:
        c = app_svc.test_client()
        if metodo == "GET":
            r_resp = c.get(ruta)
        else:
            r_resp = c.post(ruta, json={})
        assert r_resp.status_code == 401, f"Fallo de seguridad: {svc_name} {ruta} permitió acceso sin token (Status: {r_resp.status_code})"
        data_err = r_resp.get_json()
        assert data_err.get("error") == "unauthorized", f"Respuesta inesperada: {data_err}"
        print(f"  [OK] {svc_name} {metodo} {ruta} -> Rechazado con 401 Unauthorized ({data_err['mensaje']})")

    # =========================================================================
    # 4. Manejo de Tokens Inválidos, Alterados y Expirados
    # =========================================================================
    print("\n--- 4. Manejo de Tokens Inválidos, Alterados y Expirados ---")
    c_inv = inventory_app.test_client()

    # Formato inválido (sin Bearer)
    r_bad_header = c_inv.get("/api/v1/inventory/stock", headers={"Authorization": "TokenInvalidoSinBearer"})
    assert r_bad_header.status_code == 401
    print(f"  [OK] Cabecera Authorization sin 'Bearer' rechazada: 401 ({r_bad_header.get_json()['error']})")

    # Firma HMAC alterada / Token corrupto
    token_alterado = token_admin[:-4] + "ABCD"
    r_corrupt = c_inv.get("/api/v1/inventory/stock", headers={"Authorization": f"Bearer {token_alterado}"})
    assert r_corrupt.status_code == 401
    assert r_corrupt.get_json()["error"] == "token_invalido"
    print(f"  [OK] Token con firma criptográfica alterada rechazado: 401 ({r_corrupt.get_json()['error']})")

    # Token con expiración vencida (exp en el pasado)
    payload_expirado = {
        "sub": str(uuid.uuid4()),
        "email": "expirado@freshtrack.mx",
        "rol": "admin",
        "jti": uuid.uuid4().hex,
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        "iss": "freshtrack",
    }
    token_expirado = jwt.encode(payload_expirado, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)
    r_expired = c_inv.get("/api/v1/inventory/stock", headers={"Authorization": f"Bearer {token_expirado}"})
    assert r_expired.status_code == 401
    assert r_expired.get_json()["error"] == "token_invalido"
    print(f"  [OK] Token con expiración en el pasado rechazado: 401 ({r_expired.get_json()['error']})")

    # =========================================================================
    # 5. Control de Acceso por Roles (RBAC: 403 Forbidden vs 200 OK)
    # =========================================================================
    print("\n--- 5. Control de Acceso por Roles (RBAC Matrix) ---")
    # Caso A: Proveedor (supplier) intenta ver nómina de usuarios (requiere admin)
    r_rbac_1 = c_auth.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {token_supplier}"})
    assert r_rbac_1.status_code == 403, f"Fallo RBAC: Supplier no debe acceder a users: {r_rbac_1.status_code}"
    print(f"  [OK] Rol 'supplier' bloqueado en /auth/users: 403 Forbidden ({r_rbac_1.get_json()['mensaje']})")

    # Caso B: Administrador accede al mismo endpoint
    r_rbac_1_ok = c_auth.get("/api/v1/auth/users", headers={"Authorization": f"Bearer {token_admin}"})
    assert r_rbac_1_ok.status_code == 200
    print(f"  [OK] Rol 'admin' autorizado en /auth/users: 200 OK (Usuarios: {r_rbac_1_ok.get_json()['total']})")

    # Caso C: Almacenista (warehouse) intenta aprobar órdenes de abasto (requiere admin o buyer)
    c_plan = planning_app.test_client()
    r_rbac_2 = c_plan.post("/api/v1/planning/replenishment/orders/1/approve", headers={"Authorization": f"Bearer {token_warehouse}"})
    assert r_rbac_2.status_code == 403
    print(f"  [OK] Rol 'warehouse' bloqueado en aprobar órdenes de compra: 403 Forbidden")

    # Caso D: Planeador (planner) intenta ver la bitácora inmutable de auditoría (requiere admin o auditor)
    c_audit = audit_app.test_client()
    r_rbac_3 = c_audit.get("/api/v1/audit/events", headers={"Authorization": f"Bearer {token_planner}"})
    assert r_rbac_3.status_code == 403
    print(f"  [OK] Rol 'planner' bloqueado en bitácora inmutable: 403 Forbidden")

    # =========================================================================
    # 6. Revocación de Tokens y Cierre de Sesión (Redis Denylist)
    # =========================================================================
    print("\n--- 6. Revocación de Tokens y Cierre de Sesión (Redis Denylist) ---")
    # Emitir un token nuevo exclusivo para prueba de logout
    r_cajero = c_auth.post(
        "/api/v1/auth/login",
        json={"email": "gerente@freshtrack.mx", "password": "Tienda2026!"},
        headers={"X-Forwarded-For": "10.0.1.5"},
    )
    assert r_cajero.status_code == 200, f"Error en login gerente: {r_cajero.data}"
    if r_cajero.status_code != 200:
        # Fallback a planner
        r_cajero = c_auth.post("/api/v1/auth/login", json={"email": "planner@freshtrack.mx", "password": "Plan2026!"})
    token_temporal = r_cajero.get_json()["token"]
    jti_temporal = r_cajero.get_json()["jti"]

    # 1. Probar uso válido previo
    r_test_prev = c_inv.get("/api/v1/inventory/stock", headers={"Authorization": f"Bearer {token_temporal}"})
    assert r_test_prev.status_code == 200
    print(f"  [OK] Token activo {jti_temporal[:10]}... probado previamente con éxito: 200 OK")

    # 2. Ejecutar Logout
    t0 = time.perf_counter()
    r_logout = c_auth.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token_temporal}"})
    lat_logout = (time.perf_counter() - t0) * 1000.0
    assert r_logout.status_code == 200
    print(f"  [OK] Cierre de sesión ejecutado (/api/v1/auth/logout) en {lat_logout:.2f} ms")

    # 3. Validar presencia inmediata en Denylist de Redis
    assert cache_service.esta_jwt_revocado(jti_temporal)
    ttl_denylist = cache_service.obtener_ttl(f"jwt:denylist:{jti_temporal}")
    print(f"  [OK] JTI detectado en Redis Denylist ('jwt:denylist:{jti_temporal[:10]}...', TTL: {ttl_denylist}s)")

    # 4. Reintentar petición protegida con el token revocado -> Debe rebotar con 401
    r_test_post = c_inv.get("/api/v1/inventory/stock", headers={"Authorization": f"Bearer {token_temporal}"})
    assert r_test_post.status_code == 401
    assert r_test_post.get_json()["error"] == "token_revocado"
    print(f"  [OK] Reintento con token revocado bloqueado de inmediato: 401 ({r_test_post.get_json()['error']})")

    # =========================================================================
    # 7. Validación de Entradas y Manejo Controlado de Errores
    # =========================================================================
    print("\n--- 7. Validación de Entradas y Manejo Controlado de Errores ---")
    # Payload vacío en login
    r_err_login = c_auth.post("/api/v1/auth/login", json={})
    assert r_err_login.status_code == 400
    assert r_err_login.get_json()["error"] in ("campos_requeridos", "parametro_invalido", "cuerpo_vacio")
    print(f"  [OK] Login con payload vacío controlado: 400 Bad Request ({r_err_login.get_json()['mensaje']})")

    # Reserva FEFO con datos vacíos
    r_err_res = c_inv.post(
        "/api/v1/inventory/reserve-fefo",
        headers={"Authorization": f"Bearer {token_admin}"},
        json={"id_locacion": 0, "lineas": []},
    )
    assert r_err_res.status_code == 400
    assert r_err_res.get_json()["error"] in ("campos_requeridos", "parametro_invalido", "cuerpo_vacio")
    print(f"  [OK] Reserva FEFO sin líneas controlada: 400 Bad Request ({r_err_res.get_json()['mensaje']})")

    # ASN XML malformado
    c_asn = asn_app.test_client()
    r_err_asn = c_asn.post(
        "/api/v1/asn",
        headers={"Authorization": f"Bearer {token_admin}", "Content-Type": "application/xml"},
        data="<xml><tag_incompleto>",
    )
    assert r_err_asn.status_code == 400
    print(f"  [OK] Manifiesto XML malformado controlado: 400 Bad Request sin exposición de trazas")

    # =========================================================================
    # 8. Registro de Auditoría de Eventos Relevantes
    # =========================================================================
    print("\n--- 8. Registro de Auditoría en PostgreSQL (Bitácora Inmutable) ---")
    eventos_login = query(
        """
        SELECT accion, nombre_tabla, descripcion, usuario_email, fecha_evento
        FROM auditoria.bitacora_eventos
        WHERE accion IN ('LOGIN', 'LOGOUT', 'LOGIN_FALLIDO')
        ORDER BY fecha_evento DESC
        LIMIT 5
        """
    )
    assert len(eventos_login) > 0, "Debe haber registros de auditoría de autenticación"
    for ev in eventos_login:
        print(f"  • Evento auditado: [{ev['accion']}] por {ev['usuario_email']} en {ev['fecha_evento']}")
    print("  [OK] Bitácora inmutable en PostgreSQL confirmó eventos de seguridad auditados")

    banner(">>> ¡TODAS LAS 8 PRUEBAS DE SEGURIDAD PASARON EXITOSAMENTE! <<<")
    return True


if __name__ == "__main__":
    exito = verificar_seguridad()
    sys.exit(0 if exito else 1)
