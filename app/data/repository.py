import os
from typing import Any
import unicodedata

from sqlalchemy import create_engine, text

from data.mock_data import (
    ALERTS as _MOCK_ALERTS,
    BITACORA as _MOCK_BITACORA,
    CAUSA_MERMA_OPTS as _MOCK_CAUSA_MERMA_OPTS,
    CATEGORY_WASTE as _MOCK_CATEGORY_WASTE,
    DISCOUNTS as _MOCK_DISCOUNTS,
    EXISTENCIAS as _MOCK_EXISTENCIAS,
    FORECAST_DATA as _MOCK_FORECAST_DATA,
    LOCACIONES as _MOCK_LOCACIONES,
    LOTES as _MOCK_LOTES,
    MERMAS as _MOCK_MERMAS,
    MICROSERVICES as _MOCK_MICROSERVICES,
    NAV_SECTIONS as _MOCK_NAV_SECTIONS,
    PRODUCTOS as _MOCK_PRODUCTOS,
    PROVEEDORES as _MOCK_PROVEEDORES,
    REPLENISHMENT as _MOCK_REPLENISHMENT,
    ROLE_ACCENT as _MOCK_ROLE_ACCENT,
    ROLE_DEFAULT_VIEW as _MOCK_ROLE_DEFAULT_VIEW,
    ROLE_KEY_MAP as _MOCK_ROLE_KEY_MAP,
    ROLE_KEYS as _MOCK_ROLE_KEYS,
    ROLE_VIEWS as _MOCK_ROLE_VIEWS,
    ROLES as _MOCK_ROLES,
    SALES_MONTHLY as _MOCK_SALES_MONTHLY,
    SAVINGS_DATA as _MOCK_SAVINGS_DATA,
    TRANSFERS as _MOCK_TRANSFERS,
    USUARIOS as _MOCK_USUARIOS,
    VENTAS as _MOCK_VENTAS,
)

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or "postgresql+psycopg://app_backend:backend_secure_pass@localhost:5432/retail_perecederos"
)

try:
    engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
except Exception:
    engine = None


def _safe_query(sql: str, params: dict[str, Any] | None = None):
    if engine is None:
        return None
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


def role_key_from_name(role_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", role_name or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold().strip()
    if "admin" in normalized:
        return "admin"
    if "compr" in normalized or "buyer" in normalized:
        return "buyer"
    if "plane" in normalized or "demanda" in normalized or "plan" in normalized:
        return "planner"
    if "gerente" in normalized or "tienda" in normalized or "store" in normalized:
        return "store_manager"
    if "almacen" in normalized or "warehouse" in normalized or "bodega" in normalized:
        return "warehouse"
    if "proveedor" in normalized or "supplier" in normalized:
        return "supplier"
    if "auditor" in normalized:
        return "auditor"
    return "auditor"


# ---------------------------------------------------------------------------
# 1. Configuración de Roles y Navegación
# ---------------------------------------------------------------------------
ROLE_KEYS = _MOCK_ROLE_KEYS
ROLE_KEY_MAP = _MOCK_ROLE_KEY_MAP
ROLE_VIEWS = _MOCK_ROLE_VIEWS
ROLE_DEFAULT_VIEW = _MOCK_ROLE_DEFAULT_VIEW
ROLE_ACCENT = _MOCK_ROLE_ACCENT
NAV_SECTIONS = _MOCK_NAV_SECTIONS

# ---------------------------------------------------------------------------
# 2. Catálogos Maestros (PostgreSQL -> Fallback Mock)
# ---------------------------------------------------------------------------
_db_roles = _safe_query("SELECT id_rol, nombre_rol FROM operacion.rol ORDER BY id_rol")
ROLES = _db_roles if _db_roles else _MOCK_ROLES

_db_locaciones = _safe_query(
    "SELECT id_locacion, tipo_locacion, nombre FROM operacion.locacion ORDER BY id_locacion"
)
LOCACIONES = _db_locaciones if _db_locaciones else _MOCK_LOCACIONES

# Proveedores: En PostgreSQL solo existen (id_proveedor, rfc, razon_social, lead_time_dias).
# Atributos mock enriquecidos: contacto, confiabilidad.
_db_proveedores = _safe_query(
    """
    SELECT id_proveedor, rfc, razon_social, lead_time_dias
    FROM operacion.proveedor
    ORDER BY id_proveedor
    """
)
if _db_proveedores:
    PROVEEDORES = []
    _mock_prov_map = {p["id_proveedor"]: p for p in _MOCK_PROVEEDORES}
    for p in _db_proveedores:
        m = _mock_prov_map.get(p["id_proveedor"], {})
        PROVEEDORES.append({
            "id_proveedor": p["id_proveedor"],
            "rfc": p["rfc"],
            "razon_social": p["razon_social"],
            "lead_time_dias": p["lead_time_dias"],
            "contacto": m.get("contacto", f"contacto@proveedor{p['id_proveedor']}.mx"),
            "confiabilidad": m.get("confiabilidad", 92),
        })
else:
    PROVEEDORES = _MOCK_PROVEEDORES

# Productos: En PostgreSQL solo existen (id_sku, codigo_gtin, nombre, vida_util_estandar).
# Atributos mock enriquecidos: id_proveedor, categoria, precio_costo, precio_venta, unidad, stock_min, punto_reorden.
_db_productos = _safe_query(
    """
    SELECT id_sku, codigo_gtin, nombre, vida_util_estandar
    FROM operacion.producto
    ORDER BY id_sku
    """
)
if _db_productos:
    PRODUCTOS = []
    _mock_prod_map = {p["id_sku"]: p for p in _MOCK_PRODUCTOS}
    for p in _db_productos:
        m = _mock_prod_map.get(p["id_sku"], {})
        PRODUCTOS.append({
            "id_sku": p["id_sku"],
            "codigo_gtin": p["codigo_gtin"],
            "nombre": p["nombre"],
            "vida_util_estandar": p["vida_util_estandar"],
            "id_proveedor": m.get("id_proveedor", (p["id_sku"] % 5) + 1),
            "categoria": m.get("categoria", "Perecederos"),
            "precio_costo": m.get("precio_costo", 22.50),
            "precio_venta": m.get("precio_venta", 35.00),
            "unidad": m.get("unidad", "Pieza"),
            "stock_min": m.get("stock_min", 25),
            "punto_reorden": m.get("punto_reorden", 45),
        })
else:
    PRODUCTOS = _MOCK_PRODUCTOS

# ---------------------------------------------------------------------------
# 3. Transaccionales (PostgreSQL -> Fallback Mock)
# ---------------------------------------------------------------------------
# Lotes: En PostgreSQL solo existen (id_lote, id_sku, id_proveedor, codigo_lote_prov, fecha_caducidad).
# Atributos mock/calculados: id_locacion, status, fecha_recepcion.
_db_lotes = _safe_query(
    """
    SELECT l.id_lote::text AS id_lote, l.id_sku, l.id_proveedor, l.codigo_lote_prov,
           l.fecha_caducidad::text AS fecha_caducidad,
           COALESCE(MIN(e.id_locacion), 1) AS id_locacion,
           CASE WHEN l.fecha_caducidad < CURRENT_DATE THEN 'expired'
                WHEN l.fecha_caducidad <= CURRENT_DATE + 2 THEN 'critical'
                WHEN l.fecha_caducidad <= CURRENT_DATE + 5 THEN 'warning'
                ELSE 'ok' END AS status
    FROM operacion.lote l
    LEFT JOIN operacion.existencia e ON e.id_lote = l.id_lote
    GROUP BY l.id_lote, l.id_sku, l.id_proveedor, l.codigo_lote_prov, l.fecha_caducidad
    ORDER BY l.fecha_caducidad
    LIMIT 250
    """
)
if _db_lotes:
    LOTES = []
    for l in _db_lotes:
        LOTES.append({
            "id_lote": l["id_lote"],
            "id_sku": l["id_sku"],
            "id_proveedor": l["id_proveedor"],
            "codigo_lote_prov": l["codigo_lote_prov"],
            "fecha_caducidad": str(l["fecha_caducidad"]),
            "fecha_recepcion": "2026-09-01",
            "id_locacion": l["id_locacion"],
            "status": l["status"],
        })
else:
    LOTES = _MOCK_LOTES

# Existencias: En PostgreSQL existen (id_existencia, id_lote, id_locacion, cantidad_disponible, cantidad_reservada).
_db_existencias = _safe_query(
    """
    SELECT id_existencia::text AS id_existencia, id_lote::text AS id_lote,
           id_locacion, cantidad_disponible, cantidad_reservada
    FROM operacion.existencia
    ORDER BY id_existencia
    LIMIT 250
    """
)
if _db_existencias:
    EXISTENCIAS = [
        {
            "id_existencia": e["id_existencia"],
            "id_lote": e["id_lote"],
            "id_locacion": e["id_locacion"],
            "cantidad_disponible": _as_native(e["cantidad_disponible"]),
            "cantidad_reservada": _as_native(e["cantidad_reservada"]),
        }
        for e in _db_existencias
    ]
else:
    EXISTENCIAS = _MOCK_EXISTENCIAS

# Ventas: En PostgreSQL existen (id_venta, id_lote, id_locacion, cantidad, fecha_transaccion).
_db_ventas = _safe_query(
    """
    SELECT id_venta::text AS id_venta, id_lote::text AS id_lote,
           id_locacion, cantidad,
           to_char(fecha_transaccion, 'YYYY-MM-DD HH24:MI:SS') AS fecha_transaccion
    FROM operacion.venta_detalle
    ORDER BY fecha_transaccion DESC
    LIMIT 250
    """
)
if _db_ventas:
    VENTAS = [
        {
            "id_venta": v["id_venta"],
            "id_lote": v["id_lote"],
            "id_locacion": v["id_locacion"],
            "cantidad": _as_native(v["cantidad"]),
            "fecha_transaccion": str(v["fecha_transaccion"]),
        }
        for v in _db_ventas
    ]
else:
    VENTAS = _MOCK_VENTAS

# Mermas: En PostgreSQL existen (id_merma, id_lote, id_usuario, cantidad, causa_merma, fecha_registro).
# Atributos mock enriquecidos: id_locacion.
_db_mermas = _safe_query(
    """
    SELECT m.id_merma::text AS id_merma, m.id_lote::text AS id_lote,
           m.id_usuario::text AS id_usuario, m.cantidad, m.causa_merma,
           to_char(m.fecha_registro, 'YYYY-MM-DD HH24:MI:SS') AS fecha_registro,
           COALESCE(MIN(e.id_locacion), 1) AS id_locacion
    FROM operacion.merma m
    LEFT JOIN operacion.existencia e ON e.id_lote = m.id_lote
    GROUP BY m.id_merma, m.id_lote, m.id_usuario, m.cantidad, m.causa_merma, m.fecha_registro
    ORDER BY m.fecha_registro DESC
    LIMIT 250
    """
)
if _db_mermas:
    MERMAS = [
        {
            "id_merma": m["id_merma"],
            "id_lote": m["id_lote"],
            "id_usuario": m["id_usuario"],
            "cantidad": _as_native(m["cantidad"]),
            "causa_merma": m["causa_merma"],
            "fecha_registro": str(m["fecha_registro"]),
            "id_locacion": m["id_locacion"],
        }
        for m in _db_mermas
    ]
else:
    MERMAS = _MOCK_MERMAS

# Usuarios: En PostgreSQL existen (id_usuario, id_rol, id_locacion, nombre_completo, estado_activo).
# Atributos mock enriquecidos: email, password, ultimo_acceso.
_db_usuarios = _safe_query(
    """
    SELECT u.id_usuario::text AS id_usuario, u.id_rol, u.id_locacion,
           u.nombre_completo, u.estado_activo, r.nombre_rol
    FROM operacion.usuario u
    LEFT JOIN operacion.rol r ON r.id_rol = u.id_rol
    ORDER BY u.nombre_completo
    LIMIT 100
    """
)
if _db_usuarios:
    USUARIOS = []
    _mock_user_map = {u["nombre_completo"]: u for u in _MOCK_USUARIOS}
    for u in _db_usuarios:
        m = _mock_user_map.get(u["nombre_completo"], {})
        clean_name = unicodedata.normalize("NFKD", u["nombre_completo"])
        clean_name = "".join(c for c in clean_name if not unicodedata.combining(c)).lower()
        parts = clean_name.split()
        gen_email = f"{parts[0][0]}{parts[-1]}@freshtrack.mx" if len(parts) > 1 else f"{clean_name}@freshtrack.mx"
        USUARIOS.append({
            "id_usuario": u["id_usuario"],
            "id_rol": u["id_rol"],
            "id_locacion": u["id_locacion"],
            "nombre_completo": u["nombre_completo"],
            "estado_activo": bool(u["estado_activo"]),
            "email": m.get("email", gen_email),
            "password": m.get("password", "freshtrack"),
            "ultimo_acceso": m.get("ultimo_acceso", "2026-09-08 09:00"),
            "role_key": role_key_from_name(u.get("nombre_rol", "")),
        })
else:
    USUARIOS = _MOCK_USUARIOS

# Bitácora de Auditoría: En PostgreSQL existen (id_evento, nombre_tabla, tipo_operacion, id_usuario_app, estado_anterior, estado_nuevo, fecha_evento).
# Atributo mock enriquecido: descripcion.
_db_bitacora = _safe_query(
    """
    SELECT id_evento::text AS id_evento, nombre_tabla, tipo_operacion,
           id_usuario_app::text AS id_usuario_app, estado_anterior, estado_nuevo,
           to_char(fecha_evento, 'YYYY-MM-DD HH24:MI:SS') AS fecha_evento
    FROM auditoria.bitacora_eventos
    ORDER BY fecha_evento DESC
    LIMIT 200
    """
)
if _db_bitacora:
    BITACORA = [
        {
            "id_evento": b["id_evento"],
            "nombre_tabla": b["nombre_tabla"],
            "tipo_operacion": b["tipo_operacion"],
            "id_usuario_app": b["id_usuario_app"],
            "estado_anterior": b["estado_anterior"],
            "estado_nuevo": b["estado_nuevo"],
            "fecha_evento": str(b["fecha_evento"]),
            "descripcion": f"Operación {b['tipo_operacion']} sobre tabla {b['nombre_tabla']}",
        }
        for b in _db_bitacora
    ]
else:
    BITACORA = _MOCK_BITACORA

# ---------------------------------------------------------------------------
# 4. Datos que NO existen en la Base de Datos (100% Mock Data)
# ---------------------------------------------------------------------------
REPLENISHMENT = _MOCK_REPLENISHMENT
TRANSFERS = _MOCK_TRANSFERS
ALERTS = _MOCK_ALERTS
DISCOUNTS = _MOCK_DISCOUNTS
FORECAST_DATA = _MOCK_FORECAST_DATA
SALES_MONTHLY = _MOCK_SALES_MONTHLY
CATEGORY_WASTE = _MOCK_CATEGORY_WASTE
SAVINGS_DATA = _MOCK_SAVINGS_DATA
MICROSERVICES = _MOCK_MICROSERVICES
CAUSA_MERMA_OPTS = _MOCK_CAUSA_MERMA_OPTS

# ---------------------------------------------------------------------------
# 5. Cuentas Muestra por Rol Único para Verificación de Vistas
# ---------------------------------------------------------------------------
SAMPLE_ACCOUNTS = [
    {
        "role_key": "admin",
        "id_rol": 1,
        "role_label": "Administrador",
        "color": "#4ade80",
        "user_name": "Jorge Almanza",
        "email": "admin@freshtrack.mx",
        "password": "freshtrack",
        "alt_password": "Admin2026!",
        "scope": "Acceso total al sistema (19 vistas)",
        "default_view": "dashboard",
    },
    {
        "role_key": "buyer",
        "id_rol": 2,
        "role_label": "Comprador",
        "color": "#38bdf8",
        "user_name": "Martha López",
        "email": "compras@freshtrack.mx",
        "alt_email": "mlopez@freshtrack.mx",
        "password": "freshtrack",
        "alt_password": "Compras26!",
        "scope": "Catálogo, Proveedores y Reabastecimiento",
        "default_view": "replenishment",
    },
    {
        "role_key": "planner",
        "id_rol": 3,
        "role_label": "Planeador de Demanda",
        "color": "#a78bfa",
        "user_name": "Carlos Vega",
        "email": "planeacion@freshtrack.mx",
        "alt_email": "cvega@freshtrack.mx",
        "password": "freshtrack",
        "alt_password": "Plan2026!",
        "scope": "Pronósticos, Reabastecimiento y Sostenibilidad",
        "default_view": "forecast",
    },
    {
        "role_key": "store_manager",
        "id_rol": 4,
        "role_label": "Gerente de Tienda",
        "color": "#34d399",
        "user_name": "Luis Pérez",
        "email": "tienda@freshtrack.mx",
        "alt_email": "lperez@freshtrack.mx",
        "password": "freshtrack",
        "alt_password": "Tienda26!",
        "scope": "Operación de tienda, FEFO, Descuentos y Mermas",
        "default_view": "dashboard",
    },
    {
        "role_key": "warehouse",
        "id_rol": 5,
        "role_label": "Operador de Almacén",
        "color": "#fb923c",
        "user_name": "Pedro Vargas",
        "email": "almacen@freshtrack.mx",
        "alt_email": "pvargas@freshtrack.mx",
        "password": "freshtrack",
        "alt_password": "Almacen26!",
        "scope": "Inventario físico, Transferencias y cola FEFO",
        "default_view": "fefo",
    },
    {
        "role_key": "supplier",
        "id_rol": 6,
        "role_label": "Proveedor",
        "color": "#86efac",
        "user_name": "Roberto Soto",
        "email": "proveedor@freshtrack.mx",
        "alt_email": "rsoto@lacteosvalle.mx",
        "password": "freshtrack",
        "alt_password": "Prov2026!",
        "scope": "Monitoreo de Lotes y Reabastecimiento",
        "default_view": "replenishment",
    },
    {
        "role_key": "auditor",
        "id_rol": 7,
        "role_label": "Auditor",
        "color": "#94a3b8",
        "user_name": "Irma Auditoría",
        "email": "auditor@freshtrack.mx",
        "alt_email": "iaudit@freshtrack.mx",
        "password": "freshtrack",
        "alt_password": "Audit2026!",
        "scope": "Bitácora inmutable, Mermas y Cumplimiento",
        "default_view": "audit",
    },
]


def get_sample_accounts():
    return SAMPLE_ACCOUNTS


def authenticate_user(identifier: str, password: str | None = None) -> dict[str, Any] | None:
    val = (identifier or "").strip().lower()
    pass_clean = (password or "").strip()
    app_pwd = os.getenv("APP_LOGIN_PASSWORD", "freshtrack")

    # 1. Búsqueda directa en cuentas muestra por rol o email
    for acc in SAMPLE_ACCOUNTS:
        is_match = (
            val == acc["role_key"].lower()
            or val == acc["email"].lower()
            or val == acc.get("alt_email", "").lower()
            or val == acc["role_label"].lower()
        )
        if is_match:
            if pass_clean and pass_clean not in (acc["password"], acc.get("alt_password", ""), app_pwd, "freshtrack", "admin"):
                return None
            return {
                "id_usuario": f"sample-{acc['role_key']}",
                "id_rol": acc["id_rol"],
                "nombre_completo": acc["user_name"],
                "estado_activo": True,
                "role_key": acc["role_key"],
                "email": acc["email"],
            }

    # 2. Búsqueda por palabra clave de rol (ej: 'gerente', 'comprador', 'admin', 'auditor')
    kw_map = {
        "admin": "admin",
        "compr": "buyer",
        "buyer": "buyer",
        "plan": "planner",
        "gerente": "store_manager",
        "tienda": "store_manager",
        "store": "store_manager",
        "almacen": "warehouse",
        "bodega": "warehouse",
        "warehouse": "warehouse",
        "proveed": "supplier",
        "supplier": "supplier",
        "audit": "auditor",
    }
    for kw, rkey in kw_map.items():
        if kw in val:
            acc = next((a for a in SAMPLE_ACCOUNTS if a["role_key"] == rkey), None)
            if acc:
                if pass_clean and pass_clean not in (acc["password"], acc.get("alt_password", ""), app_pwd, "freshtrack", "admin"):
                    return None
                return {
                    "id_usuario": f"sample-{acc['role_key']}",
                    "id_rol": acc["id_rol"],
                    "nombre_completo": acc["user_name"],
                    "estado_activo": True,
                    "role_key": acc["role_key"],
                    "email": acc["email"],
                }

    # 3. Búsqueda en la lista de usuarios (PostgreSQL o Mock)
    for u in USUARIOS:
        u_email = str(u.get("email", "")).lower()
        u_id = str(u.get("id_usuario", "")).lower()
        if val in (u_email, u_id):
            u_pwd = str(u.get("password", "freshtrack"))
            if pass_clean and pass_clean not in (u_pwd, app_pwd, "freshtrack", "admin"):
                return None
            role_key = u.get("role_key") or ROLE_KEY_MAP.get(u.get("id_rol"), "auditor")
            return {
                "id_usuario": u["id_usuario"],
                "id_rol": u["id_rol"],
                "nombre_completo": u["nombre_completo"],
                "estado_activo": u.get("estado_activo", True),
                "role_key": role_key,
                "email": u.get("email", f"{val}@freshtrack.mx"),
            }

    # 4. Si la base de datos PostgreSQL está activa, consultar directamente por UUID o rol
    if engine is not None:
        db_rows = _safe_query(
            """
            SELECT u.id_usuario::text AS id_usuario, u.id_rol, u.id_locacion,
                   u.nombre_completo, u.estado_activo, r.nombre_rol
            FROM operacion.usuario u
            LEFT JOIN operacion.rol r ON r.id_rol = u.id_rol
            WHERE u.id_usuario::text = :val
            LIMIT 1
            """,
            {"val": val},
        )
        if db_rows:
            db_u = db_rows[0]
            if pass_clean and pass_clean not in (app_pwd, "freshtrack", "admin"):
                return None
            return {
                "id_usuario": db_u["id_usuario"],
                "id_rol": db_u["id_rol"],
                "nombre_completo": db_u["nombre_completo"],
                "estado_activo": bool(db_u["estado_activo"]),
                "role_key": role_key_from_name(db_u.get("nombre_rol", "")),
                "email": f"{val}@freshtrack.mx",
            }

    return None


# ---------------------------------------------------------------------------
# 6. Consultas Read-Model Sanitizadas para Pantallas Operativas
# ---------------------------------------------------------------------------
def get_login_users():
    return USUARIOS


def get_products_catalog():
    return PRODUCTOS


def get_inventory_report():
    return EXISTENCIAS


def get_sales_report():
    return VENTAS
