"""
Fixtures de integración: PostgreSQL real + los 8 microservicios en proceso.

Redis y MongoDB son compartidos por todos los servicios dentro de la prueba (igual
que en docker compose), así que un logout en svc-auth se observa en svc-inventory.
"""

from __future__ import annotations

import importlib
import uuid
from datetime import date, timedelta

import fakeredis
import pytest

from app.services import cache_service, doc_store
from tests.conftest import _redis_real_disponible

USUARIOS = {
    "admin": ("admin@freshtrack.mx", "Admin2026!"),
    "buyer": ("buyer@freshtrack.mx", "Compras2026!"),
    "planner": ("planner@freshtrack.mx", "Plan2026!"),
    "store_manager": ("gerente@freshtrack.mx", "Tienda2026!"),
    "warehouse": ("almacen@freshtrack.mx", "Almacen2026!"),
    "supplier": ("proveedor@freshtrack.mx", "Proveedor2026!"),
    "auditor": ("auditor@freshtrack.mx", "Auditor2026!"),
}
TIENDA = 3  # Tienda San Pedro (seed base)


def _postgres_disponible() -> bool:
    try:
        from app.db import escalar

        return escalar("SELECT count(*) FROM operacion.usuario") > 0
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def infraestructura():
    if not _postgres_disponible():
        pytest.skip("PostgreSQL con el seed de FreshTrack no está disponible (ver README: make infra / make bootstrap).")

    if not _redis_real_disponible():
        cache_service._client = fakeredis.FakeRedis(decode_responses=True)
    if doc_store.get_mongo_db() is None:
        import mongomock

        doc_store._db = mongomock.MongoClient()["freshtrack_pruebas"]
        try:
            doc_store.asegurar_indices(doc_store._db)
        except Exception:
            pass
    yield


@pytest.fixture(scope="session")
def svc():
    """Clientes de prueba de los 8 microservicios: svc['auth'].post(...)."""
    nombres = ["auth", "catalog", "inventory", "commercial", "asn", "planning", "alerts", "audit"]
    return {n: importlib.import_module(f"app.services.{n}_service.app").app.test_client() for n in nombres}


def _limpiar_rate_limit_login():
    cache_service.invalidar_patron("ratelimit:*login*")


@pytest.fixture(scope="session")
def login(svc):
    def _login(rol: str) -> str:
        _limpiar_rate_limit_login()
        email, password = USUARIOS[rol]
        r = svc["auth"].post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.get_json()
        return r.get_json()["token"]

    return _login


@pytest.fixture(scope="session")
def tokens(login):
    return {rol: login(rol) for rol in USUARIOS}


def bearer(token: str, **extra) -> dict:
    return {"Authorization": f"Bearer {token}", **extra}


@pytest.fixture()
def lote_con_stock():
    """Recibe un lote nuevo (50 u., caduca en 10 días) en la tienda de pruebas y devuelve su id."""
    from app.db import one
    from app.domain.inventario import registrar_recepcion

    admin = one(
        "SELECT id_usuario::text AS id_usuario, email, 'admin' AS rol_clave FROM operacion.usuario WHERE email = 'admin@freshtrack.mx'"
    )
    hoy = date.today()
    res = registrar_recepcion(
        id_sku=1,
        id_proveedor=1,
        id_locacion=TIENDA,
        codigo_lote_prov=f"PYTEST-{uuid.uuid4().hex[:8]}",
        fecha_produccion=hoy - timedelta(days=1),
        fecha_recepcion=hoy,
        fecha_caducidad=hoy + timedelta(days=10),
        cantidad=50,
        costo_unitario=12.5,
        observaciones="Lote creado por las pruebas de integración",
        usuario=admin,
    )
    return res
