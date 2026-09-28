"""
Navegación y permisos.

La clave del rol vive en PostgreSQL (operacion.rol.clave) y aquí se traduce en
qué pantallas ve cada perfil. El menú se construye filtrando las secciones por
los permisos del rol que tiene la sesión.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Iconos del menú lateral (SVG en línea, sin dependencias externas)
# ---------------------------------------------------------------------------
ICONOS: dict[str, str] = {
    "dashboard": '<path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zm0 8a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zm6-6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zm0 8a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/>',
    "alerts": '<path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zm0 16a2 2 0 01-2-2h4a2 2 0 01-2 2z"/>',
    "products": '<path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"/>',
    "stores": '<path d="M2 5a2 2 0 012-2h12a2 2 0 012 2v2a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm14 6a2 2 0 012 2v3a2 2 0 01-2 2H4a2 2 0 01-2-2v-3a2 2 0 012-2h12z"/>',
    "suppliers": '<path d="M8 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm7 0a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM3 4a1 1 0 00-1 1v9a1 1 0 001 1h.5a2.5 2.5 0 014.95 0h3.1a2.5 2.5 0 014.95 0H17a1 1 0 001-1v-5l-3-4H3z"/>',
    "batches": '<path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd"/>',
    "inventory": '<path d="M10 3.5L2.5 8 10 12.5 17.5 8 10 3.5zm-7.5 7L10 15l7.5-4.5L10 16.5 2.5 10.5z"/>',
    "sales": '<path fill-rule="evenodd" d="M3 3a1 1 0 000 2v8a2 2 0 002 2h2.586l-1.293 1.293a1 1 0 101.414 1.414L10 15.414l2.293 2.293a1 1 0 001.414-1.414L12.414 15H15a2 2 0 002-2V5a1 1 0 100-2H3zm11 4a1 1 0 10-2 0v4a1 1 0 102 0V7zm-3 1a1 1 0 10-2 0v3a1 1 0 102 0V8zM8 9a1 1 0 00-2 0v2a1 1 0 102 0V9z" clip-rule="evenodd"/>',
    "fefo": '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/>',
    "forecast": '<path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z"/><path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z"/>',
    "replenishment": '<path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>',
    "transfers": '<path d="M8 5a1 1 0 100 2h5.586l-1.293 1.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L13.586 5H8zm-5 10a1 1 0 100-2H2.414l1.293-1.293a1 1 0 10-1.414-1.414l-3 3a1 1 0 000 1.414l3 3a1 1 0 001.414-1.414L2.414 15H3z"/>',
    "discounts": '<path fill-rule="evenodd" d="M17.707 9.293a1 1 0 010 1.414l-7 7a1 1 0 01-1.414 0l-7-7A.997.997 0 012 10V5a3 3 0 013-3h5c.256 0 .512.098.707.293l7 7zM5 6a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>',
    "shrinkage": '<path fill-rule="evenodd" d="M3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd"/>',
    "savings": '<path fill-rule="evenodd" d="M3.172 5.172a4 4 0 015.656 0L10 6.343l1.172-1.171a4 4 0 115.656 5.656L10 17.657l-6.828-6.829a4 4 0 010-5.656z" clip-rule="evenodd"/>',
    "sustainability": '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z" clip-rule="evenodd"/>',
    "users": '<path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zm8 0a3 3 0 11-6 0 3 3 0 016 0zm-4.07 11c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>',
    "audit": '<path fill-rule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>',
    "traceability": '<path fill-rule="evenodd" d="M4 3a1 1 0 011-1h10a1 1 0 011 1v1h1a1 1 0 011 1v3a1 1 0 01-.293.707L16 10.414V17a1 1 0 01-1 1H5a1 1 0 01-1-1v-6.586l-1.707-1.707A1 1 0 012 8V5a1 1 0 011-1h1V3zm2 1v12h8V4H6z" clip-rule="evenodd"/>',
    "settings": '<path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>',
}

# ---------------------------------------------------------------------------
# Secciones del menú
# ---------------------------------------------------------------------------
SECCIONES = [
    {
        "label": "Principal",
        "items": [
            {"id": "dashboard", "label": "Panel de Control", "endpoint": "panel.dashboard"},
            {"id": "alerts", "label": "Alertas", "endpoint": "panel.alertas"},
        ],
    },
    {
        "label": "Catálogos",
        "items": [
            {"id": "products", "label": "Productos", "endpoint": "catalogo.productos"},
            {"id": "stores", "label": "Tiendas y CEDIS", "endpoint": "catalogo.locaciones"},
            {"id": "suppliers", "label": "Proveedores", "endpoint": "catalogo.proveedores"},
        ],
    },
    {
        "label": "Operación",
        "items": [
            {"id": "batches", "label": "Lotes y Recepción", "endpoint": "operacion.lotes"},
            {"id": "inventory", "label": "Inventario", "endpoint": "operacion.inventario"},
            {"id": "sales", "label": "Ventas", "endpoint": "operacion.ventas"},
            {"id": "fefo", "label": "Cola FEFO", "endpoint": "operacion.fefo"},
            {"id": "traceability", "label": "Trazabilidad", "endpoint": "operacion.trazabilidad"},
        ],
    },
    {
        "label": "Analítica",
        "items": [
            {"id": "forecast", "label": "Pronósticos", "endpoint": "analitica.pronostico"},
            {"id": "replenishment", "label": "Reabastecimiento", "endpoint": "analitica.reabastecimiento"},
            {"id": "transfers", "label": "Transferencias", "endpoint": "analitica.transferencias"},
            {"id": "discounts", "label": "Descuentos", "endpoint": "analitica.descuentos"},
        ],
    },
    {
        "label": "Desperdicio",
        "items": [
            {"id": "shrinkage", "label": "Mermas", "endpoint": "operacion.mermas"},
            {"id": "savings", "label": "Desperdicio Evitado", "endpoint": "panel.desperdicio_evitado"},
            {"id": "sustainability", "label": "Sostenibilidad", "endpoint": "panel.sostenibilidad"},
        ],
    },
    {
        "label": "Administración",
        "items": [
            {"id": "users", "label": "Usuarios y Roles", "endpoint": "panel.usuarios"},
            {"id": "audit", "label": "Bitácora", "endpoint": "panel.auditoria_bitacora"},
            {"id": "settings", "label": "Configuración", "endpoint": "panel.configuracion"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Permisos por rol (clave de operacion.rol.clave)
# ---------------------------------------------------------------------------
VISTAS_POR_ROL: dict[str, list[str]] = {
    "admin": [
        "dashboard", "alerts", "products", "stores", "suppliers", "batches",
        "inventory", "sales", "fefo", "traceability", "forecast",
        "replenishment", "transfers", "discounts", "shrinkage", "savings",
        "sustainability", "users", "audit", "settings",
    ],
    "buyer": [
        "dashboard", "alerts", "products", "suppliers", "batches", "inventory",
        "replenishment", "traceability", "forecast",
    ],
    "planner": [
        "dashboard", "alerts", "products", "inventory", "sales", "forecast",
        "replenishment", "transfers", "discounts", "savings", "sustainability",
        "traceability", "batches",
    ],
    "store_manager": [
        # El gerente de tienda es quien aprueba o rechaza lo que el sistema
        # recomienda (reabastecimiento, transferencias y descuentos), así que
        # necesita ver esas pantallas además de la operación de su tienda.
        "dashboard", "alerts", "batches", "inventory", "sales", "fefo",
        "shrinkage", "discounts", "transfers", "replenishment", "traceability",
    ],
    "warehouse": [
        "dashboard", "alerts", "batches", "inventory", "fefo", "shrinkage",
        "transfers", "traceability",
    ],
    "supplier": ["dashboard", "products", "batches", "replenishment"],
    "auditor": [
        "dashboard", "sales", "shrinkage", "sustainability", "audit",
        "traceability", "savings",
    ],
}

VISTA_INICIAL: dict[str, str] = {
    "admin": "dashboard",
    "buyer": "replenishment",
    "planner": "forecast",
    "store_manager": "dashboard",
    "warehouse": "fefo",
    "supplier": "replenishment",
    "auditor": "audit",
}

# Color con el que se pinta la interfaz según el rol activo. Sirve para que en
# la demostración se vea de un vistazo con qué perfil se inició sesión.
ACENTO_POR_ROL: dict[str, str] = {
    "admin": "#4ade80",
    "buyer": "#38bdf8",
    "planner": "#a78bfa",
    "store_manager": "#fbbf24",
    "warehouse": "#2dd4bf",
    "supplier": "#f472b6",
    "auditor": "#f87171",
}


def acento_para(clave_rol: str) -> str:
    return ACENTO_POR_ROL.get(clave_rol, "#4ade80")


def menu_para(clave_rol: str) -> list[dict]:
    """Devuelve las secciones del menú visibles para un rol."""
    permitidas = set(VISTAS_POR_ROL.get(clave_rol, []))
    secciones = []
    for seccion in SECCIONES:
        items = [i for i in seccion["items"] if i["id"] in permitidas]
        if items:
            secciones.append({"label": seccion["label"], "items": items})
    return secciones


def puede_ver(clave_rol: str, vista: str) -> bool:
    return vista in VISTAS_POR_ROL.get(clave_rol, [])


def ruta_inicial(clave_rol: str) -> str:
    """
    Endpoint de la pantalla inicial del rol.

    VISTA_INICIAL guarda el *id* de la vista («dashboard»), pero quien llama a
    esta función lo hace dentro de un url_for(), así que hay que traducirlo al
    nombre del endpoint («panel.dashboard»).
    """
    vista = VISTA_INICIAL.get(clave_rol)
    if vista:
        endpoint = endpoint_de(vista)
        if endpoint:
            return endpoint
    return "panel.dashboard"


def endpoint_de(vista: str) -> str | None:
    for seccion in SECCIONES:
        for item in seccion["items"]:
            if item["id"] == vista:
                return item["endpoint"]
    return None
