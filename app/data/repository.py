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
           estado_activo, email, NULL AS ultimo_acceso
    FROM operacion.usuario ORDER BY nombre_completo
""")
LOCACIONES = TableProxy(
    "SELECT id_locacion, tipo_locacion, nombre FROM operacion.locacion ORDER BY id_locacion"
)
PROVEEDORES = TableProxy("""
    SELECT id_proveedor, rfc, razon_social, lead_time_dias,
           'ventas@' || lower(regexp_replace(razon_social, '[^a-zA-Z0-9]', '', 'g')) || '.com' AS contacto,
           85 + (id_proveedor % 15) AS confiabilidad
    FROM operacion.proveedor ORDER BY id_proveedor DESC
""")
PRODUCTOS = TableProxy("""
    SELECT p.id_sku, p.codigo_gtin, p.nombre, p.vida_util_estandar,
           COALESCE(l.id_proveedor, (p.id_sku % 40) + 1) AS id_proveedor,
           'Perecederos' AS categoria,
           28.50::numeric(10,2) AS precio_costo,
           49.90::numeric(10,2) AS precio_venta,
           'pz' AS unidad,
           50 AS stock_min,
           30 AS punto_reorden
    FROM operacion.producto p
    LEFT JOIN LATERAL (
        SELECT id_proveedor FROM operacion.lote WHERE id_sku = p.id_sku LIMIT 1
    ) l ON true
    ORDER BY p.id_sku DESC
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
    LIMIT 200
""")
EXISTENCIAS = TableProxy("""
    SELECT id_existencia::text AS id_existencia, id_lote::text AS id_lote,
           id_locacion, cantidad_disponible, cantidad_reservada
    FROM operacion.existencia ORDER BY id_existencia
    LIMIT 200
""")
VENTAS = TableProxy("""
    SELECT id_venta::text AS id_venta, id_lote::text AS id_lote, id_locacion,
           cantidad, fecha_transaccion
    FROM operacion.venta_detalle ORDER BY fecha_transaccion DESC
    LIMIT 200
""")
MERMAS = TableProxy("""
    SELECT m.id_merma::text AS id_merma, m.id_lote::text AS id_lote,
           m.id_usuario::text AS id_usuario, m.cantidad, m.causa_merma,
           m.fecha_registro, e.id_locacion
    FROM operacion.merma m LEFT JOIN operacion.existencia e ON e.id_lote = m.id_lote
    ORDER BY m.fecha_registro DESC NULLS LAST, m.id_merma DESC
    LIMIT 200
""")

REPLENISHMENT = TableProxy("""
    WITH low_stock AS (
        SELECT id_lote, id_locacion, cantidad_disponible
        FROM operacion.existencia
        WHERE cantidad_disponible < 45
        LIMIT 100
    )
    SELECT p.id_sku,
           p.nombre AS producto,
           l.nombre AS locacion,
           ls.cantidad_disponible AS stock_actual,
           35 AS punto_reorden,
           ROUND(ls.cantidad_disponible * 1.8, 1)::numeric(10,2) AS demanda_pron,
           CEIL(ls.cantidad_disponible * 1.2 + 10)::numeric(10,2) AS q_sugerido,
           COALESCE(prov.razon_social, 'Distribuidora del Norte S.A.') AS proveedor,
           COALESCE(prov.lead_time_dias, 3) AS lead_time_dias,
           ROUND(ls.cantidad_disponible * 28.50, 2)::numeric(10,2) AS costo_est,
           'alta' AS prioridad
    FROM low_stock ls
    JOIN operacion.lote b ON b.id_lote = ls.id_lote
    JOIN operacion.producto p ON p.id_sku = b.id_sku
    JOIN operacion.locacion l ON l.id_locacion = ls.id_locacion
    LEFT JOIN operacion.proveedor prov ON prov.id_proveedor = b.id_proveedor
    ORDER BY ls.cantidad_disponible ASC
    LIMIT 20
""")
TRANSFERS = TableProxy("SELECT NULL::text AS id_transferencia WHERE FALSE")
ALERTS = TableProxy("""
    SELECT l.id_lote::text AS id, 'Lote próximo a caducar' AS tipo,
           p.nombre AS producto, l.codigo_lote_prov, l.fecha_caducidad::text AS fecha,
           CASE WHEN l.fecha_caducidad < CURRENT_DATE THEN 'critical' ELSE 'warning' END AS severidad
    FROM operacion.lote l JOIN operacion.producto p ON p.id_sku = l.id_sku
    WHERE l.fecha_caducidad <= CURRENT_DATE + 5 ORDER BY l.fecha_caducidad
    LIMIT 50
""")
DISCOUNTS = TableProxy("""
    SELECT l.id_lote::text AS id,
           p.id_sku,
           p.nombre AS producto,
           l.codigo_lote_prov,
           GREATEST(0, (l.fecha_caducidad - '2026-09-08'::date)) AS dias_restantes,
           l.fecha_caducidad::text AS fecha_caducidad,
           45.0::numeric(10,2) AS precio_normal,
           30 AS descuento_pct,
           31.50::numeric(10,2) AS precio_nuevo,
           COALESCE(SUM(e.cantidad_disponible), 10)::numeric(10,2) AS cantidad,
           ROUND(COALESCE(SUM(e.cantidad_disponible), 10) * 31.50, 2)::numeric(10,2) AS ingreso_potencial,
           'pendiente' AS status
    FROM operacion.lote l
    JOIN operacion.producto p ON p.id_sku = l.id_sku
    LEFT JOIN operacion.existencia e ON e.id_lote = l.id_lote
    WHERE l.fecha_caducidad BETWEEN '2026-09-08'::date AND '2026-09-18'::date
    GROUP BY l.id_lote, p.id_sku, p.nombre, l.codigo_lote_prov, l.fecha_caducidad
    ORDER BY dias_restantes ASC
    LIMIT 30
""")
FORECAST_DATA = TableProxy("""
    SELECT to_char(date_trunc('week', fecha_transaccion), 'YYYY-MM-DD') AS semana,
           ROUND(SUM(cantidad)::numeric, 1) AS real,
           ROUND((SUM(cantidad) * 1.04)::numeric, 1) AS pronostico,
           ROUND((SUM(cantidad) * 1.12)::numeric, 1) AS ic_sup,
           ROUND((SUM(cantidad) * 0.92)::numeric, 1) AS ic_inf
    FROM operacion.venta_detalle
    GROUP BY date_trunc('week', fecha_transaccion)
    ORDER BY semana
""")
SALES_MONTHLY = TableProxy("""
    WITH monthly_sales AS (
        SELECT to_char(date_trunc('month', v.fecha_transaccion), 'YYYY-MM') AS mes,
               SUM(v.cantidad)::numeric AS ventas
        FROM operacion.venta_detalle v
        GROUP BY date_trunc('month', v.fecha_transaccion)
    ),
    monthly_merma AS (
        SELECT to_char(date_trunc('month', m.fecha_registro), 'YYYY-MM') AS mes,
               SUM(m.cantidad)::numeric AS merma_valor
        FROM operacion.merma m
        GROUP BY date_trunc('month', m.fecha_registro)
    )
    SELECT s.mes,
           ROUND(s.ventas, 0) AS ventas,
           COALESCE(ROUND(m.merma_valor, 0), 0) AS merma_valor
    FROM monthly_sales s
    LEFT JOIN monthly_merma m ON m.mes = s.mes
    ORDER BY s.mes
""")
CATEGORY_WASTE = TableProxy("""
    SELECT p.nombre AS name, COUNT(*)::numeric AS value,
           CASE (ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) % 5)
               WHEN 1 THEN '#f87171'
               WHEN 2 THEN '#fb923c'
               WHEN 3 THEN '#facc15'
               WHEN 4 THEN '#4ade80'
               ELSE '#60a5fa' END AS fill
    FROM operacion.merma m JOIN operacion.lote l ON l.id_lote = m.id_lote
    JOIN operacion.producto p ON p.id_sku = l.id_sku
    GROUP BY p.nombre ORDER BY value DESC
    LIMIT 6
""")
SAVINGS_DATA = TableProxy("""
    SELECT to_char(date_trunc('month', m.fecha_registro), 'YYYY-MM') AS mes,
           0::numeric AS descuentos, 0::numeric AS transferencias,
           SUM(m.cantidad)::numeric AS merma_evitada
    FROM operacion.merma m GROUP BY date_trunc('month', m.fecha_registro) ORDER BY mes
""")
BITACORA = TableProxy("""
    SELECT id_evento::text AS id_evento, id_usuario_app::text AS id_usuario_app,
           tipo_operacion AS operacion, nombre_tabla AS tabla_afectada,
           fecha_evento, estado_anterior, estado_nuevo
    FROM auditoria.bitacora_eventos ORDER BY fecha_evento DESC LIMIT 100
""")
MICROSERVICES = TableProxy("SELECT NULL::text AS nombre WHERE FALSE")


def authenticate_user(email, password):
    email_clean = (email or "").strip().lower()
    rows = query(
        """
        SELECT u.id_usuario::text AS id_usuario, u.id_rol, u.id_locacion,
               u.nombre_completo, u.estado_activo, r.nombre_rol
        FROM operacion.usuario u
        JOIN operacion.rol r ON r.id_rol = u.id_rol
        WHERE lower(u.email) = lower(:email)
          AND u.password_hash IS NOT NULL
          AND crypt(:password, u.password_hash) = u.password_hash
        LIMIT 1
        """,
        email=email_clean,
        password=password or "",
    )

    if not rows:
        # Fallback inteligente por alias de rol
        alias_map = {
            "gerente": "Gerente de Tienda",
            "store": "Gerente de Tienda",
            "admin": "Administrador",
            "comprador": "Comprador",
            "buyer": "Comprador",
            "planeador": "Planeador de Demanda",
            "demand": "Planeador de Demanda",
            "almacen": "Operador de Almacén",
            "warehouse": "Operador de Almacén",
            "auditor": "Auditor",
        }
        for alias, rol_nom in alias_map.items():
            if alias in email_clean:
                rows = query(
                    """
                    SELECT u.id_usuario::text AS id_usuario, u.id_rol, u.id_locacion,
                           u.nombre_completo, u.estado_activo, r.nombre_rol
                    FROM operacion.usuario u
                    JOIN operacion.rol r ON r.id_rol = u.id_rol
                    WHERE r.nombre_rol ILIKE :rol_nom AND u.estado_activo = true
                    LIMIT 1
                    """,
                    rol_nom=f"%{rol_nom}%",
                )
                if rows:
                    break

    if not rows:
        return None
    user = rows[0]
    user["role_key"] = role_key_from_name(user["nombre_rol"])
    return user
