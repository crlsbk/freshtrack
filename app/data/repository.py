"""PostgreSQL repository for the schema described in docs/BD_Diseño.docx."""

from functools import lru_cache
import os
import unicodedata

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


ROLE_KEYS = [
    {"key": "admin", "id_rol": 1, "label": "Administrador", "color": "#4ade80"},
    {"key": "buyer", "id_rol": 2, "label": "Comprador", "color": "#38bdf8"},
    {"key": "planner", "id_rol": 3, "label": "Planeador", "color": "#a78bfa"},
    {
        "key": "store_manager",
        "id_rol": 4,
        "label": "Gerente de Tienda",
        "color": "#34d399",
    },
    {
        "key": "warehouse",
        "id_rol": 5,
        "label": "Operador de Almacén",
        "color": "#fb923c",
    },
    {"key": "supplier", "id_rol": 6, "label": "Proveedor", "color": "#86efac"},
    {"key": "auditor", "id_rol": 7, "label": "Auditor", "color": "#94a3b8"},
]
ROLE_KEY_MAP = {role["id_rol"]: role["key"] for role in ROLE_KEYS}
ROLE_DEFAULT_VIEW = {
    "admin": "dashboard",
    "buyer": "replenishment",
    "planner": "forecast",
    "store_manager": "dashboard",
    "warehouse": "fefo",
    "supplier": "replenishment",
    "auditor": "audit",
}
ROLE_ACCENT = {role["key"]: role["color"] for role in ROLE_KEYS}
ROLE_VIEWS = {
    "admin": [
        "dashboard",
        "products",
        "stores",
        "suppliers",
        "batches",
        "inventory",
        "sales",
        "forecast",
        "fefo",
        "replenishment",
        "transfers",
        "discounts",
        "shrinkage",
        "savings",
        "sustainability",
        "alerts",
        "users",
        "audit",
        "settings",
    ],
    "buyer": [
        "dashboard",
        "products",
        "suppliers",
        "batches",
        "inventory",
        "replenishment",
        "alerts",
    ],
    "planner": [
        "dashboard",
        "products",
        "inventory",
        "sales",
        "forecast",
        "replenishment",
        "transfers",
        "savings",
        "sustainability",
    ],
    "store_manager": [
        "dashboard",
        "batches",
        "inventory",
        "sales",
        "fefo",
        "discounts",
        "shrinkage",
        "alerts",
    ],
    "warehouse": [
        "dashboard",
        "batches",
        "inventory",
        "fefo",
        "shrinkage",
        "transfers",
    ],
    "supplier": ["dashboard", "products", "batches", "replenishment"],
    "auditor": ["dashboard", "sales", "shrinkage", "sustainability", "audit"],
}
NAV_SECTIONS = [
    {
        "label": "Principal",
        "items": [
            {"id": "dashboard", "label": "Panel de Control"},
            {"id": "alerts", "label": "Alertas"},
        ],
    },
    {
        "label": "Catálogos",
        "items": [
            {"id": "products", "label": "Productos"},
            {"id": "stores", "label": "Tiendas"},
            {"id": "suppliers", "label": "Proveedores"},
        ],
    },
    {
        "label": "Operaciones",
        "items": [
            {"id": "batches", "label": "Lotes / Caducidades"},
            {"id": "inventory", "label": "Inventario"},
            {"id": "sales", "label": "Ventas"},
            {"id": "fefo", "label": "FEFO"},
        ],
    },
    {
        "label": "Predicción",
        "items": [
            {"id": "forecast", "label": "Pronósticos"},
            {"id": "replenishment", "label": "Reabastecimiento"},
            {"id": "transfers", "label": "Transferencias"},
        ],
    },
    {
        "label": "Desperdicio",
        "items": [
            {"id": "discounts", "label": "Descuentos"},
            {"id": "shrinkage", "label": "Mermas"},
            {"id": "savings", "label": "Ahorro Estimado"},
            {"id": "sustainability", "label": "Sostenibilidad"},
        ],
    },
    {
        "label": "Admin",
        "items": [
            {"id": "users", "label": "Usuarios y Roles"},
            {"id": "audit", "label": "Bitácora"},
            {"id": "settings", "label": "Configuración"},
        ],
    },
]
CAUSA_MERMA_OPTS = ["Caducidad", "Daño"]


@lru_cache
def get_engine():
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://app_backend:backend_secure_pass@localhost:5432/retail_perecederos",
    )
    return create_engine(url, pool_pre_ping=True, future=True)


def query(sql, **params):
    try:
        with get_engine().connect() as connection:
            return [
                dict(row) for row in connection.execute(text(sql), params).mappings()
            ]
    except SQLAlchemyError as exc:
        raise RuntimeError(
            "No se pudo consultar PostgreSQL. Revisa DATABASE_URL y el esquema operacion."
        ) from exc


def role_key_from_name(role_name):
    normalized = unicodedata.normalize("NFKD", role_name or "")
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold().strip()
    if "admin" in normalized:
        return "admin"
    if "compr" in normalized:
        return "buyer"
    if "plane" in normalized:
        return "planner"
    if "gerente" in normalized and "tienda" in normalized:
        return "store_manager"
    if "almacen" in normalized or "warehouse" in normalized:
        return "warehouse"
    if "proveedor" in normalized or "supplier" in normalized:
        return "supplier"
    if "auditor" in normalized:
        return "auditor"
    return "auditor"


class TableProxy:
    def __init__(self, sql):
        self.sql = sql

    def __iter__(self):
        return iter(query(self.sql))

    def __len__(self):
        return len(query(self.sql))

    def __bool__(self):
        return bool(len(self))


USUARIOS = TableProxy("""
    SELECT id_usuario::text AS id_usuario, id_rol, id_locacion, nombre_completo,
           estado_activo, id_usuario::text AS email, '' AS password, NULL AS ultimo_acceso
    FROM operacion.usuario ORDER BY nombre_completo
""")
LOCACIONES = TableProxy(
    "SELECT id_locacion, tipo_locacion, nombre FROM operacion.locacion ORDER BY id_locacion"
)
PROVEEDORES = TableProxy("""
    SELECT id_proveedor, rfc, razon_social, lead_time_dias,
           NULL AS contacto, NULL AS confiabilidad
    FROM operacion.proveedor ORDER BY razon_social
""")
PRODUCTOS = TableProxy("""
    SELECT id_sku, codigo_gtin, nombre, vida_util_estandar,
           NULL AS id_proveedor, NULL AS categoria, NULL AS precio_costo,
           NULL AS precio_venta, NULL AS unidad, NULL AS stock_min, NULL AS punto_reorden
    FROM operacion.producto ORDER BY nombre
""")
LOTES = TableProxy("""
    SELECT l.id_lote::text AS id_lote, l.id_sku, l.id_proveedor, l.codigo_lote_prov,
           l.fecha_caducidad::text AS fecha_caducidad,
           MIN(e.id_locacion) AS id_locacion,
           CASE WHEN l.fecha_caducidad < CURRENT_DATE THEN 'expired'
                WHEN l.fecha_caducidad <= CURRENT_DATE + 2 THEN 'critical'
                WHEN l.fecha_caducidad <= CURRENT_DATE + 5 THEN 'warning'
                ELSE 'ok' END AS status
    FROM operacion.lote l LEFT JOIN operacion.existencia e ON e.id_lote = l.id_lote
    GROUP BY l.id_lote, l.id_sku, l.id_proveedor, l.codigo_lote_prov, l.fecha_caducidad
    ORDER BY l.fecha_caducidad
""")
EXISTENCIAS = TableProxy("""
    SELECT id_existencia::text AS id_existencia, id_lote::text AS id_lote,
           id_locacion, cantidad_disponible, cantidad_reservada
    FROM operacion.existencia ORDER BY id_existencia
""")
VENTAS = TableProxy("""
    SELECT id_venta::text AS id_venta, id_lote::text AS id_lote, id_locacion,
           cantidad, fecha_transaccion
    FROM operacion.venta_detalle ORDER BY fecha_transaccion DESC
""")
MERMAS = TableProxy("""
    SELECT m.id_merma::text AS id_merma, m.id_lote::text AS id_lote,
           m.id_usuario::text AS id_usuario, m.cantidad, m.causa_merma,
           NULL AS fecha_registro, e.id_locacion
    FROM operacion.merma m LEFT JOIN operacion.existencia e ON e.id_lote = m.id_lote
    ORDER BY m.id_merma
""")

REPLENISHMENT = TableProxy("""
    SELECT p.id_sku, p.nombre AS producto, l.nombre AS locacion,
           SUM(e.cantidad_disponible) AS stock_actual,
           0 AS q_sugerido, 'alta' AS prioridad, 0 AS costo_est
    FROM operacion.producto p
    JOIN operacion.lote b ON b.id_sku = p.id_sku
    JOIN operacion.existencia e ON e.id_lote = b.id_lote
    JOIN operacion.locacion l ON l.id_locacion = e.id_locacion
    GROUP BY p.id_sku, p.nombre, l.nombre
    HAVING SUM(e.cantidad_disponible) <= 0
    ORDER BY stock_actual
""")
TRANSFERS = TableProxy("SELECT NULL::text AS id_transferencia WHERE FALSE")
ALERTS = TableProxy("""
    SELECT l.id_lote::text AS id, 'Lote próximo a caducar' AS tipo,
           p.nombre AS producto, l.codigo_lote_prov, l.fecha_caducidad::text AS fecha,
           CASE WHEN l.fecha_caducidad < CURRENT_DATE THEN 'critical' ELSE 'warning' END AS severidad
    FROM operacion.lote l JOIN operacion.producto p ON p.id_sku = l.id_sku
    WHERE l.fecha_caducidad <= CURRENT_DATE + 5 ORDER BY l.fecha_caducidad
""")
DISCOUNTS = TableProxy("""
    SELECT l.id_lote::text AS id, p.nombre AS producto, l.codigo_lote_prov,
           l.fecha_caducidad::text AS fecha_caducidad, 0::numeric AS ingreso_potencial
    FROM operacion.lote l JOIN operacion.producto p ON p.id_sku = l.id_sku
    WHERE l.fecha_caducidad <= CURRENT_DATE + 5 ORDER BY l.fecha_caducidad
""")
FORECAST_DATA = TableProxy("""
    SELECT to_char(date_trunc('week', fecha_transaccion), 'YYYY-MM-DD') AS semana,
           SUM(cantidad)::numeric AS real, SUM(cantidad)::numeric AS pronostico,
           SUM(cantidad)::numeric AS ic_sup, SUM(cantidad)::numeric AS ic_inf
    FROM operacion.venta_detalle
    GROUP BY date_trunc('week', fecha_transaccion) ORDER BY semana
""")
SALES_MONTHLY = TableProxy("""
    SELECT to_char(date_trunc('month', v.fecha_transaccion), 'YYYY-MM') AS mes,
           SUM(v.cantidad)::numeric AS ventas, 0::numeric AS merma_valor
    FROM operacion.venta_detalle v GROUP BY date_trunc('month', v.fecha_transaccion) ORDER BY mes
""")
CATEGORY_WASTE = TableProxy("""
    SELECT p.nombre AS name, COUNT(*)::numeric AS value, '#f87171' AS fill
    FROM operacion.merma m JOIN operacion.lote l ON l.id_lote = m.id_lote
    JOIN operacion.producto p ON p.id_sku = l.id_sku
    GROUP BY p.nombre ORDER BY value DESC
""")
SAVINGS_DATA = TableProxy("""
    SELECT to_char(date_trunc('month', m.fecha_registro), 'YYYY-MM') AS mes,
           0::numeric AS descuentos, 0::numeric AS transferencias,
           SUM(m.cantidad)::numeric AS merma_evitada
    FROM operacion.merma m GROUP BY date_trunc('month', m.fecha_registro) ORDER BY mes
""")
BITACORA = TableProxy("""
    SELECT id_evento::text AS id_evento, id_usuario::text AS id_usuario_app,
           tipo_operacion AS operacion, nombre_tabla AS tabla_afectada,
           fecha_evento, estado_anterior, estado_nuevo
    FROM esquema_auditoria.bitacora_eventos ORDER BY fecha_evento DESC
""")
MICROSERVICES = TableProxy("SELECT NULL::text AS nombre WHERE FALSE")


def authenticate_user(user_id, password):
    if password != os.getenv("APP_LOGIN_PASSWORD", "freshtrack"):
        return None
    rows = query(
        """
         SELECT u.id_usuario::text AS id_usuario, u.id_rol, u.id_locacion,
             u.nombre_completo, u.estado_activo, r.nombre_rol
         FROM operacion.usuario u
         JOIN operacion.rol r ON r.id_rol = u.id_rol
         WHERE u.id_usuario::text = :user_id
    """,
        user_id=user_id,
    )
    if not rows:
        return None
    user = rows[0]
    user["role_key"] = role_key_from_name(user["nombre_rol"])
    return user
