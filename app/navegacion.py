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
    "dashboard": '<path d="M3 4a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm8 0a1 1 0 011-1h4a1 1 0 011 1v2a1 1 0 01-1 1h-4a1 1 0 01-1-1V4zm0 6a1 1 0 011-1h4a1 1 0 011 1v6a1 1 0 01-1 1h-4a1 1 0 01-1-1v-6zM3 12a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H4a1 1 0 01-1-1v-4z"/>',
    "map": '<path fill-rule="evenodd" d="M10 18s6-5.33 6-10a6 6 0 10-12 0c0 4.67 6 10 6 10zm0-7.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" clip-rule="evenodd"/>',
    "alerts": '<path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zm0 16a2 2 0 01-2-2h4a2 2 0 01-2 2z"/>',
    "products": '<path fill-rule="evenodd" d="M10 2.2l7 3.5v8.6l-7 3.5-7-3.5V5.7l7-3.5zm0 2.24L4.8 6.94 10 9.54l5.2-2.6L10 4.44zM4.5 8.35v6.15l5 2.5V10.8l-5-2.45zm6 8.65l5-2.5V8.35l-5 2.45v6.2z" clip-rule="evenodd"/>',
    "stores": '<path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2.5a2.5 2.5 0 01-4 2 2.5 2.5 0 01-4-2 2.5 2.5 0 01-4 2 2.5 2.5 0 01-2-2.5V4zm1 7.27V16a1 1 0 001 1h10a1 1 0 001-1v-4.73A4.47 4.47 0 0114.5 12a4.47 4.47 0 01-3.5-1.7 4.47 4.47 0 01-3.5 1.7A4.47 4.47 0 014 11.27zM8 15v-2h4v2H8z"/>',
    "suppliers": '<path d="M2 4a1 1 0 00-1 1v8a1 1 0 001 1h1.08a2.5 2.5 0 004.84 0h4.16a2.5 2.5 0 004.84 0H18a1 1 0 001-1V8.5a1 1 0 00-.29-.71l-2.5-2.5A1 1 0 0015.5 5H13V4a1 1 0 00-1-1H2zm3.5 11a1 1 0 110-2 1 1 0 010 2zm9 0a1 1 0 110-2 1 1 0 010 2zM13 6.5h2.09l1.91 1.91V10H13V6.5z"/>',
    "batches": '<path fill-rule="evenodd" d="M3 4a2 2 0 012-2h5.586a2 2 0 011.414.586l5.414 5.414a2 2 0 010 2.828l-5.586 5.586a2 2 0 01-2.828 0L3.586 11A2 2 0 013 9.586V4zm4 3a1.5 1.5 0 100-3 1.5 1.5 0 000 3z" clip-rule="evenodd"/>',
    "inventory": '<path fill-rule="evenodd" d="M2 4a1 1 0 011-1h14a1 1 0 110 2H3a1 1 0 01-1-1zm1 4a1 1 0 00-1 1v7a1 1 0 001 1h14a1 1 0 001-1V9a1 1 0 00-1-1H3zm2 2h4v5H5v-5zm6 0h4v5h-4v-5z" clip-rule="evenodd"/>',
    "sales": '<path fill-rule="evenodd" d="M2 17a1 1 0 011-1h14a1 1 0 110 2H3a1 1 0 01-1-1zM4 12a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1v-2zm5-4a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1V8zm5-4a1 1 0 011-1h2a1 1 0 011 1v10a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" clip-rule="evenodd"/>',
    "fefo": '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-12a.75.75 0 00-1.5 0v4.25c0 .2.08.39.22.53l2.5 2.5a.75.75 0 001.06-1.06L10.75 9.94V6z" clip-rule="evenodd"/>',
    "forecast": '<path d="M2 15a1 1 0 001 1h14a1 1 0 100-2H3a1 1 0 00-1 1zm2.7-5.3a1 1 0 011.4 0L8.5 12.1l3.3-4.4a1 1 0 011.5-.1l3.4 3.4a1 1 0 11-1.4 1.4l-2.7-2.7-3.3 4.4a1 1 0 01-1.5.1L6.1 11.1a1 1 0 010-1.4zM13 4a1 1 0 011-1h3a1 1 0 011 1v3a1 1 0 11-2 0V5.41l-2.29 2.3a1 1 0 11-1.42-1.42L14.59 4H14a1 1 0 01-1-1z"/>',
    "replenishment": '<path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>',
    "transfers": '<path fill-rule="evenodd" d="M4.293 7.707a1 1 0 010-1.414l3-3a1 1 0 011.414 1.414L7.414 6H15a1 1 0 110 2H7.414l1.293 1.293a1 1 0 01-1.414 1.414l-3-3zm11.414 4.586a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L12.586 14H5a1 1 0 110-2h7.586l-1.293-1.293a1 1 0 011.414-1.414l3 3z" clip-rule="evenodd"/>',
    "discounts": '<path fill-rule="evenodd" d="M17.707 9.293a1 1 0 010 1.414l-7 7a1 1 0 01-1.414 0l-7-7A.997.997 0 012 10V5a3 3 0 013-3h5c.256 0 .512.098.707.293l7 7zM5 6a1 1 0 100-2 1 1 0 000 2zm7.707 3.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414-1.414l-2-2z" clip-rule="evenodd"/>',
    "shrinkage": '<path fill-rule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm2 3a1 1 0 011 1v6a2 2 0 002 2h4a2 2 0 002-2V8a1 1 0 112 0v6a4 4 0 01-4 4H8a4 4 0 01-4-4V8a1 1 0 011-1zm5 1a1 1 0 011 1v3.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 111.414-1.414L9 12.586V9a1 1 0 011-1z" clip-rule="evenodd"/>',
    "savings": '<path fill-rule="evenodd" d="M10 2a1 1 0 01.78.375l2.5 3.125a1 1 0 00.78.375h3.94a1 1 0 01.894 1.447l-1.97 3.94a1 1 0 000 .894l1.97 3.94a1 1 0 01-.894 1.447h-3.94a1 1 0 00-.78.375l-2.5 3.125a1 1 0 01-1.56 0l-2.5-3.125a1 1 0 00-.78-.375H2.47a1 1 0 01-.894-1.447l1.97-3.94a1 1 0 000-.894L1.576 7.322a1 1 0 01.894-1.447h3.94a1 1 0 00.78-.375l2.5-3.125A1 1 0 0110 2zm3.707 6.707a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>',
    "sustainability": '<path fill-rule="evenodd" d="M16.5 3.5c-4.5 0-9 2.5-10.5 7-1.2 3.6.3 6.5 3.5 6.5 4.5 0 8.5-4 9-11 .1-.8-.4-1.5-1-1.7-.3-.1-.6-.1-1-.1zm-1.8 3.2c-.3 2.5-2.2 5.5-5.2 6.5 1-1.5 2.2-3.2 2.7-4.7.3-.8.2-1.4-.2-1.9-.4-.4-1-.5-1.8-.3-.6.2-1.3.5-2 1 .8-2.6 3.4-4.2 6.5-4.2.3 1.2.2 2.4 0 3.6z" clip-rule="evenodd"/>',
    "users": '<path d="M10 3a3 3 0 100 6 3 3 0 000-6zM3 15a4 4 0 014-4h6a4 4 0 014 4v1a1 1 0 01-1 1H4a1 1 0 01-1-1v-1z"/>',
    "audit": '<path fill-rule="evenodd" d="M10 2a1 1 0 01.78.375l5 6.25A1 1 0 0116 9.25V13a7 7 0 01-6 6.93A7 7 0 014 13V9.25a1 1 0 01.22-.625l5-6.25A1 1 0 0110 2zm0 3.125L6 8.125V13a5 5 0 004 4.9 5 5 0 004-4.9V8.125L10 5.125zm2.707 4.582a1 1 0 010 1.414l-3 3a1 1 0 01-1.414 0l-1.5-1.5a1 1 0 111.414-1.414L9 11.879l2.293-2.293a1 1 0 011.414 0z" clip-rule="evenodd"/>',
    "traceability": '<path fill-rule="evenodd" d="M4 3a2 2 0 100 4 2 2 0 000-4zm4 2a1 1 0 011-1h6a1 1 0 110 2H9a1 1 0 01-1-1zm8 5a2 2 0 100 4 2 2 0 000-4zm-8 2a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1zm-4 5a2 2 0 100 4 2 2 0 000-4zm4 2a1 1 0 011-1h6a1 1 0 110 2H9a1 1 0 01-1-1z" clip-rule="evenodd"/>',
    "settings": '<path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>',
    "services": '<path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v3a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm0 9a1 1 0 011-1h12a1 1 0 011 1v3a1 1 0 01-1 1H4a1 1 0 01-1-1v-3zm3-7.5a1 1 0 100 2 1 1 0 000-2zm0 9a1 1 0 100 2 1 1 0 000-2z"/>',
    "mongo_explorer": '<path fill-rule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1V4zm0 6a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2zm0 6a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-1 1H4a1 1 0 01-1-1v-2z" clip-rule="evenodd"/>',
}

# ---------------------------------------------------------------------------
# Secciones del menú
# ---------------------------------------------------------------------------
SECCIONES = [
    {
        "label": "Principal",
        "items": [
            {"id": "dashboard", "label": "Panel de control", "endpoint": "panel.dashboard"},
            {"id": "alerts", "label": "Alertas", "endpoint": "panel.alertas"},
            {"id": "map", "label": "Mapa de tiendas", "endpoint": "panel.mapa"},
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
            {"id": "fefo", "label": "Orden de salida (FEFO)", "endpoint": "operacion.fefo"},
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
            {"id": "mongo_explorer", "label": "Documentos (MongoDB)", "endpoint": "panel.mongo_explorer"},
        ],
    },
    {
        "label": "Desperdicio",
        "items": [
            {"id": "shrinkage", "label": "Mermas", "endpoint": "operacion.mermas"},
            {"id": "savings", "label": "Desperdicio evitado", "endpoint": "panel.desperdicio_evitado"},
            {"id": "sustainability", "label": "Sostenibilidad", "endpoint": "panel.sostenibilidad"},
        ],
    },
    {
        "label": "Administración",
        "items": [
            {"id": "users", "label": "Usuarios y Roles", "endpoint": "panel.usuarios"},
            {"id": "audit", "label": "Bitácora", "endpoint": "panel.auditoria_bitacora"},
            {"id": "settings", "label": "Configuración", "endpoint": "panel.configuracion"},
            {"id": "services", "label": "Microservicios", "endpoint": "panel.microservicios"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Permisos por rol (clave de operacion.rol.clave)
# ---------------------------------------------------------------------------
VISTAS_POR_ROL: dict[str, list[str]] = {
    "admin": [
        "dashboard", "alerts", "map", "products", "stores", "suppliers", "batches",
        "inventory", "sales", "fefo", "traceability", "forecast",
        "replenishment", "transfers", "discounts", "shrinkage", "savings",
        "sustainability", "users", "audit", "settings", "mongo_explorer",
        "services",
    ],
    "buyer": [
        "dashboard", "alerts", "map", "products", "suppliers", "batches", "inventory",
        "replenishment", "traceability", "forecast", "mongo_explorer",
    ],
    "planner": [
        "dashboard", "alerts", "map", "products", "inventory", "sales", "forecast",
        "replenishment", "transfers", "discounts", "savings", "sustainability",
        "traceability", "batches", "mongo_explorer",
    ],
    "store_manager": [
        # El gerente de tienda es quien aprueba o rechaza lo que el sistema
        # recomienda (reabastecimiento, transferencias y descuentos), así que
        # necesita ver esas pantallas además de la operación de su tienda.
        "dashboard", "alerts", "map", "batches", "inventory", "sales", "fefo",
        "shrinkage", "discounts", "transfers", "replenishment", "traceability",
        "mongo_explorer",
    ],
    "warehouse": [
        "dashboard", "alerts", "map", "batches", "inventory", "fefo", "shrinkage",
        "transfers", "traceability", "mongo_explorer",
    ],
    "supplier": ["dashboard", "products", "batches", "replenishment"],
    "auditor": [
        "dashboard", "map", "sales", "shrinkage", "sustainability", "audit",
        "traceability", "savings", "mongo_explorer",
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
    "admin": "#16a34a",
    "buyer": "#0284c7",
    "planner": "#7c3aed",
    "store_manager": "#d97706",
    "warehouse": "#0d9488",
    "supplier": "#db2777",
    "auditor": "#dc2626",
}


def acento_para(clave_rol: str) -> str:
    return ACENTO_POR_ROL.get(clave_rol, "#16a34a")


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
