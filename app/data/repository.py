import os
from typing import Any

from sqlalchemy import create_engine, text

from data.mock_data import (
    ALERTS as _MOCK_ALERTS,
    BITACORA as _MOCK_BITACORA,
    CAUSA_MERMA_OPTS as _MOCK_CAUSA_MERMA_OPTS,
    CATEGORY_WASTE as _MOCK_CATEGORY_WASTE,
    DISCOUNTS as _MOCK_DISCOUNTS,
    FORECAST_DATA as _MOCK_FORECAST_DATA,
    LOCACIONES as _MOCK_LOCACIONES,
    LOTES as _MOCK_LOTES,
    MERMAS as _MOCK_MERMAS,
    MICROSERVICES as _MOCK_MICROSERVICES,
    NAV_SECTIONS as _MOCK_NAV_SECTIONS,
    PROVEEDORES as _MOCK_PROVEEDORES,
    PRODUCTOS as _MOCK_PRODUCTOS,
    REPLENISHMENT as _MOCK_REPLENISHMENT,
    ROLE_ACCENT as _MOCK_ROLE_ACCENT,
    ROLE_DEFAULT_VIEW as _MOCK_ROLE_DEFAULT_VIEW,
    ROLE_KEYS as _MOCK_ROLE_KEYS,
    ROLE_KEY_MAP as _MOCK_ROLE_KEY_MAP,
    ROLE_VIEWS as _MOCK_ROLE_VIEWS,
    ROLES as _MOCK_ROLES,
    SALES_MONTHLY as _MOCK_SALES_MONTHLY,
    SAVINGS_DATA as _MOCK_SAVINGS_DATA,
    TRANSFERS as _MOCK_TRANSFERS,
    USUARIOS as _MOCK_USUARIOS,
    VENTAS as _MOCK_VENTAS,
    EXISTENCIAS as _MOCK_EXISTENCIAS,
)

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or "postgresql+psycopg://app_backend:backend_secure_pass@localhost:5432/retail_perecederos"
)

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)


def _safe_query(sql: str, params: dict[str, Any] | None = None):
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            return [dict(row) for row in result.mappings()]
    except Exception:
        return None


def _as_native(value):
    if hasattr(value, "__float__") and value.__class__.__name__ not in {"str", "bytes"}:
        try:
            return float(value)
        except Exception:
            pass
    return value


ROLES = _safe_query("SELECT id_rol, nombre_rol FROM operacion.rol ORDER BY id_rol") or _MOCK_ROLES
ROLE_KEYS = _MOCK_ROLE_KEYS
ROLE_KEY_MAP = _MOCK_ROLE_KEY_MAP
ROLE_VIEWS = _MOCK_ROLE_VIEWS
ROLE_DEFAULT_VIEW = _MOCK_ROLE_DEFAULT_VIEW
ROLE_ACCENT = _MOCK_ROLE_ACCENT
NAV_SECTIONS = _MOCK_NAV_SECTIONS


LOCACIONES = _safe_query(
    """
    SELECT id_locacion, tipo_locacion, nombre
    FROM operacion.locacion
    ORDER BY id_locacion
    """
) or _MOCK_LOCACIONES

PROVEEDORES = _safe_query(
    """
    SELECT id_proveedor, rfc, razon_social, lead_time_dias
    FROM operacion.proveedor
    ORDER BY id_proveedor
    """
) or _MOCK_PROVEEDORES

PRODUCTOS = _safe_query(
    """
    SELECT id_sku, codigo_gtin, nombre, vida_util_estandar
    FROM operacion.producto
    ORDER BY id_sku
    """
) or _MOCK_PRODUCTOS

LOTES = _safe_query(
    """
    SELECT id_lote, id_sku, id_proveedor, codigo_lote_prov, fecha_caducidad
    FROM operacion.lote
    ORDER BY fecha_caducidad
    """
) or _MOCK_LOTES

EXISTENCIAS = _safe_query(
    """
    SELECT id_existencia, id_lote, id_locacion, cantidad_disponible, cantidad_reservada
    FROM operacion.existencia
    ORDER BY id_existencia
    """
) or _MOCK_EXISTENCIAS

VENTAS = _safe_query(
    """
    SELECT id_venta, id_lote, id_locacion, cantidad, fecha_transaccion
    FROM operacion.venta_detalle
    ORDER BY fecha_transaccion
    """
) or _MOCK_VENTAS

MERMAS = _safe_query(
    """
    SELECT id_merma, id_lote, id_usuario, id_locacion, cantidad, causa_merma, fecha_registro
    FROM operacion.merma
    ORDER BY fecha_registro
    """
) or _MOCK_MERMAS

USUARIOS = _safe_query(
    """
    SELECT id_usuario, id_rol, id_locacion, nombre_completo, estado_activo,
           email, password, ultimo_acceso
    FROM operacion.usuario
    ORDER BY nombre_completo
    """
) or _MOCK_USUARIOS

CAUSA_MERMA_OPTS = _MOCK_CAUSA_MERMA_OPTS
BITACORA = _safe_query(
    """
    SELECT id_evento, nombre_tabla, tipo_operacion, id_usuario_app,
           estado_anterior, estado_nuevo, fecha_evento
    FROM auditoria.bitacora_eventos
    ORDER BY fecha_evento DESC
    """
) or _MOCK_BITACORA

REPLENISHMENT = _MOCK_REPLENISHMENT
TRANSFERS = _MOCK_TRANSFERS
ALERTS = _MOCK_ALERTS
DISCOUNTS = _MOCK_DISCOUNTS
FORECAST_DATA = _MOCK_FORECAST_DATA
SALES_MONTHLY = _MOCK_SALES_MONTHLY
CATEGORY_WASTE = _MOCK_CATEGORY_WASTE
SAVINGS_DATA = _MOCK_SAVINGS_DATA
MICROSERVICES = _MOCK_MICROSERVICES

# ---------------------------------------------------------------------------
# PostgreSQL read-model queries for the main operational screens.
# These are the exact joined queries that expose real database data for:
# 1) login/roles/users
# 2) products + supplier catalog
# 3) inventory + lot + location
# 4) sales + product + location
#
# Note: the current schema in sql/02_ddl_operacion.sql is the minimal operational
# core, so these queries assume the expected database has the matching columns.
# ---------------------------------------------------------------------------

LOGIN_USERS_SQL = """
SELECT DISTINCT ON (u.id_rol)
    u.id_usuario,
    u.id_rol,
    r.nombre_rol,
    u.id_locacion,
    l.nombre AS locacion_nombre,
    u.nombre_completo,
    u.estado_activo,
    u.email,
    u.password
FROM operacion.usuario AS u
JOIN operacion.rol AS r
    ON r.id_rol = u.id_rol
JOIN operacion.locacion AS l
    ON l.id_locacion = u.id_locacion
WHERE u.estado_activo = true
ORDER BY u.id_rol, u.id_usuario;
"""

PRODUCTS_CATALOG_SQL = """
SELECT
    p.id_sku,
    p.codigo_gtin,
    p.nombre,
    p.vida_util_estandar,
    pr.id_proveedor,
    pr.razon_social AS proveedor_nombre,
    pr.lead_time_dias
FROM operacion.producto AS p
JOIN operacion.proveedor AS pr
    ON pr.id_proveedor = p.id_proveedor
ORDER BY p.id_sku;
"""

INVENTORY_REPORT_SQL = """
SELECT
    e.id_existencia,
    e.id_lote,
    l.id_sku,
    p.nombre AS producto,
    e.id_locacion,
    loc.nombre AS locacion,
    e.cantidad_disponible,
    e.cantidad_reservada,
    l.fecha_caducidad
FROM operacion.existencia AS e
JOIN operacion.lote AS l
    ON l.id_lote = e.id_lote
JOIN operacion.producto AS p
    ON p.id_sku = l.id_sku
JOIN operacion.locacion AS loc
    ON loc.id_locacion = e.id_locacion
ORDER BY e.id_existencia;
"""

SALES_REPORT_SQL = """
SELECT
    vd.id_venta,
    vd.id_lote,
    l.id_sku,
    p.nombre AS producto,
    vd.id_locacion,
    loc.nombre AS locacion,
    vd.cantidad,
    vd.fecha_transaccion
FROM operacion.venta_detalle AS vd
JOIN operacion.lote AS l
    ON l.id_lote = vd.id_lote
JOIN operacion.producto AS p
    ON p.id_sku = l.id_sku
JOIN operacion.locacion AS loc
    ON loc.id_locacion = vd.id_locacion
ORDER BY vd.fecha_transaccion DESC;
"""


def get_login_users():
    return _safe_query(LOGIN_USERS_SQL)


def get_products_catalog():
    return _safe_query(PRODUCTS_CATALOG_SQL)


def get_inventory_report():
    return _safe_query(INVENTORY_REPORT_SQL)


def get_sales_report():
    return _safe_query(SALES_REPORT_SQL)
