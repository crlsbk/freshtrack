ROLES = [
    {"id_rol": 1, "nombre_rol": "Administrador"},
    {"id_rol": 2, "nombre_rol": "Comprador"},
    {"id_rol": 3, "nombre_rol": "Planeador"},
    {"id_rol": 4, "nombre_rol": "Gerente de Tienda"},
    {"id_rol": 5, "nombre_rol": "Operador de Almacén"},
    {"id_rol": 6, "nombre_rol": "Proveedor"},
    {"id_rol": 7, "nombre_rol": "Auditor"},
]

ROLE_KEYS = [
    {"key": "admin",         "id_rol": 1, "label": "Administrador",       "color": "#4ade80"},
    {"key": "buyer",         "id_rol": 2, "label": "Comprador",           "color": "#38bdf8"},
    {"key": "planner",       "id_rol": 3, "label": "Planeador",           "color": "#a78bfa"},
    {"key": "store_manager", "id_rol": 4, "label": "Gerente de Tienda",   "color": "#34d399"},
    {"key": "warehouse",     "id_rol": 5, "label": "Operador de Almacén", "color": "#fb923c"},
    {"key": "supplier",      "id_rol": 6, "label": "Proveedor",           "color": "#86efac"},
    {"key": "auditor",       "id_rol": 7, "label": "Auditor",             "color": "#94a3b8"},
]

ROLE_KEY_MAP = {1: "admin", 2: "buyer", 3: "planner", 4: "store_manager", 5: "warehouse", 6: "supplier", 7: "auditor"}

ROLE_VIEWS = {
    "admin":         ["dashboard","products","stores","suppliers","batches","inventory","sales","forecast","fefo","replenishment","transfers","discounts","shrinkage","savings","sustainability","alerts","users","audit","settings"],
    "buyer":         ["dashboard","products","suppliers","batches","inventory","replenishment","alerts"],
    "planner":       ["dashboard","products","inventory","sales","forecast","replenishment","transfers","savings","sustainability"],
    "store_manager": ["dashboard","batches","inventory","sales","fefo","discounts","shrinkage","alerts"],
    "warehouse":     ["dashboard","batches","inventory","fefo","shrinkage","transfers"],
    "supplier":      ["dashboard","products","batches","replenishment"],
    "auditor":       ["dashboard","sales","shrinkage","sustainability","audit"],
}

ROLE_DEFAULT_VIEW = {
    "admin":         "dashboard",
    "buyer":         "replenishment",
    "planner":       "forecast",
    "store_manager": "dashboard",
    "warehouse":     "fefo",
    "supplier":      "replenishment",
    "auditor":       "audit",
}

ROLE_ACCENT = {
    "admin":         "#4ade80",
    "buyer":         "#38bdf8",
    "planner":       "#a78bfa",
    "store_manager": "#34d399",
    "warehouse":     "#fb923c",
    "supplier":      "#86efac",
    "auditor":       "#94a3b8",
}

NAV_SECTIONS = [
    {"label": "Principal", "items": [
        {"id": "dashboard",  "label": "Panel de Control"},
        {"id": "alerts",     "label": "Alertas"},
    ]},
    {"label": "Catálogos", "items": [
        {"id": "products",   "label": "Productos"},
        {"id": "stores",     "label": "Tiendas"},
        {"id": "suppliers",  "label": "Proveedores"},
    ]},
    {"label": "Operaciones", "items": [
        {"id": "batches",    "label": "Lotes / Caducidades"},
        {"id": "inventory",  "label": "Inventario"},
        {"id": "sales",      "label": "Ventas"},
        {"id": "fefo",       "label": "FEFO"},
    ]},
    {"label": "Predicción", "items": [
        {"id": "forecast",      "label": "Pronósticos"},
        {"id": "replenishment", "label": "Reabastecimiento"},
        {"id": "transfers",     "label": "Transferencias"},
    ]},
    {"label": "Desperdicio", "items": [
        {"id": "discounts",      "label": "Descuentos"},
        {"id": "shrinkage",      "label": "Mermas"},
        {"id": "savings",        "label": "Ahorro Estimado"},
        {"id": "sustainability", "label": "Sostenibilidad"},
    ]},
    {"label": "Admin", "items": [
        {"id": "users",    "label": "Usuarios y Roles"},
        {"id": "audit",    "label": "Bitácora"},
        {"id": "settings", "label": "Configuración"},
    ]},
]

LOCACIONES = [
    {"id_locacion": 1, "tipo_locacion": "Tienda", "nombre": "Sucursal Norte — Monterrey"},
    {"id_locacion": 2, "tipo_locacion": "Tienda", "nombre": "Sucursal Centro — CDMX"},
    {"id_locacion": 3, "tipo_locacion": "Tienda", "nombre": "Sucursal Sur — Guadalajara"},
    {"id_locacion": 4, "tipo_locacion": "Tienda", "nombre": "Sucursal Oriente — Puebla"},
    {"id_locacion": 5, "tipo_locacion": "Tienda", "nombre": "Sucursal Occidente — León"},
    {"id_locacion": 6, "tipo_locacion": "CEDIS",  "nombre": "CEDIS Central — Querétaro"},
]

PROVEEDORES = [
    {"id_proveedor": 1, "rfc": "LVA850312AA1", "razon_social": "Lácteos del Valle S.A. de C.V.", "lead_time_dias": 2, "contacto": "rsoto@lacteosvalle.mx",    "confiabilidad": 96},
    {"id_proveedor": 2, "rfc": "FMX920614BB2", "razon_social": "Frutas México S.A. de C.V.",    "lead_time_dias": 1, "contacto": "ventas@frutasmx.com",     "confiabilidad": 88},
    {"id_proveedor": 3, "rfc": "VFR011030CC3", "razon_social": "Verduras Frescas del Rancho",   "lead_time_dias": 1, "contacto": "pedidos@verdurasfr.mx",   "confiabilidad": 92},
    {"id_proveedor": 4, "rfc": "CRF781205DD4", "razon_social": "Carnes Refrigeradas del Norte", "lead_time_dias": 3, "contacto": "crf@carnesrefri.mx",       "confiabilidad": 85},
    {"id_proveedor": 5, "rfc": "PAN640918EE5", "razon_social": "Panificadora Artesanal S.A.",   "lead_time_dias": 1, "contacto": "dist@panartesanal.mx",     "confiabilidad": 79},
]

PRODUCTOS = [
    {"id_sku": 1, "codigo_gtin": "07501234560010", "nombre": "Leche Entera 1L",         "vida_util_estandar": 15, "id_proveedor": 1, "categoria": "Lácteos",   "precio_costo": 18.50, "precio_venta": 24.90, "unidad": "Litro",      "stock_min": 50,  "punto_reorden": 80},
    {"id_sku": 2, "codigo_gtin": "07501234560027", "nombre": "Yogur Natural 900g",      "vida_util_estandar": 21, "id_proveedor": 1, "categoria": "Lácteos",   "precio_costo": 22.00, "precio_venta": 31.50, "unidad": "Pieza",      "stock_min": 30,  "punto_reorden": 50},
    {"id_sku": 3, "codigo_gtin": "07501234560034", "nombre": "Manzana Gala kg",         "vida_util_estandar": 10, "id_proveedor": 2, "categoria": "Frutas",    "precio_costo":  8.00, "precio_venta": 14.90, "unidad": "Kg",         "stock_min": 40,  "punto_reorden": 60},
    {"id_sku": 4, "codigo_gtin": "07501234560041", "nombre": "Tomate Bola kg",          "vida_util_estandar":  7, "id_proveedor": 3, "categoria": "Verduras",  "precio_costo":  6.50, "precio_venta": 11.90, "unidad": "Kg",         "stock_min": 30,  "punto_reorden": 50},
    {"id_sku": 5, "codigo_gtin": "07501234560058", "nombre": "Pechuga de Pollo kg",     "vida_util_estandar":  5, "id_proveedor": 4, "categoria": "Carnes",    "precio_costo": 55.00, "precio_venta": 89.90, "unidad": "Kg",         "stock_min": 20,  "punto_reorden": 35},
    {"id_sku": 6, "codigo_gtin": "07501234560065", "nombre": "Pan Integral 600g",       "vida_util_estandar":  4, "id_proveedor": 5, "categoria": "Panadería", "precio_costo": 18.00, "precio_venta": 28.50, "unidad": "Pieza",      "stock_min": 25,  "punto_reorden": 40},
    {"id_sku": 7, "codigo_gtin": "07501234560072", "nombre": "Queso Oaxaca 400g",       "vida_util_estandar": 30, "id_proveedor": 1, "categoria": "Lácteos",   "precio_costo": 42.00, "precio_venta": 62.00, "unidad": "Pieza",      "stock_min": 20,  "punto_reorden": 35},
    {"id_sku": 8, "codigo_gtin": "07501234560089", "nombre": "Espinaca 250g",           "vida_util_estandar":  5, "id_proveedor": 3, "categoria": "Verduras",  "precio_costo": 14.00, "precio_venta": 22.90, "unidad": "Bolsa",      "stock_min": 20,  "punto_reorden": 35},
]

LOTES = [
    {"id_lote": "a1b2c3d4-0001-0001-0001-000000000001", "id_sku": 1, "id_proveedor": 1, "codigo_lote_prov": "LDV-2026-0901", "fecha_caducidad": "2026-09-14", "fecha_recepcion": "2026-09-01", "id_locacion": 1, "status": "ok"},
    {"id_lote": "a1b2c3d4-0002-0002-0002-000000000002", "id_sku": 2, "id_proveedor": 1, "codigo_lote_prov": "LDV-2026-0902", "fecha_caducidad": "2026-09-09", "fecha_recepcion": "2026-09-01", "id_locacion": 2, "status": "critical"},
    {"id_lote": "a1b2c3d4-0003-0003-0003-000000000003", "id_sku": 3, "id_proveedor": 2, "codigo_lote_prov": "FMX-2026-0831", "fecha_caducidad": "2026-09-08", "fecha_recepcion": "2026-08-31", "id_locacion": 1, "status": "expired"},
    {"id_lote": "a1b2c3d4-0004-0004-0004-000000000004", "id_sku": 4, "id_proveedor": 3, "codigo_lote_prov": "VFR-2026-0905", "fecha_caducidad": "2026-09-11", "fecha_recepcion": "2026-09-05", "id_locacion": 3, "status": "warning"},
    {"id_lote": "a1b2c3d4-0005-0005-0005-000000000005", "id_sku": 5, "id_proveedor": 4, "codigo_lote_prov": "CRF-2026-0906", "fecha_caducidad": "2026-09-10", "fecha_recepcion": "2026-09-06", "id_locacion": 2, "status": "critical"},
    {"id_lote": "a1b2c3d4-0006-0006-0006-000000000006", "id_sku": 6, "id_proveedor": 5, "codigo_lote_prov": "PAN-2026-0907", "fecha_caducidad": "2026-09-12", "fecha_recepcion": "2026-09-07", "id_locacion": 4, "status": "warning"},
    {"id_lote": "a1b2c3d4-0007-0007-0007-000000000007", "id_sku": 7, "id_proveedor": 1, "codigo_lote_prov": "LDV-2026-0820", "fecha_caducidad": "2026-10-05", "fecha_recepcion": "2026-08-20", "id_locacion": 5, "status": "ok"},
    {"id_lote": "a1b2c3d4-0008-0008-0008-000000000008", "id_sku": 8, "id_proveedor": 3, "codigo_lote_prov": "VFR-2026-0906", "fecha_caducidad": "2026-09-09", "fecha_recepcion": "2026-09-06", "id_locacion": 1, "status": "critical"},
]

EXISTENCIAS = [
    {"id_existencia": "ex-001", "id_lote": "a1b2c3d4-0001-0001-0001-000000000001", "id_locacion": 1, "cantidad_disponible": 142.0, "cantidad_reservada": 20.0},
    {"id_existencia": "ex-002", "id_lote": "a1b2c3d4-0002-0002-0002-000000000002", "id_locacion": 2, "cantidad_disponible":  58.0, "cantidad_reservada": 10.0},
    {"id_existencia": "ex-003", "id_lote": "a1b2c3d4-0003-0003-0003-000000000003", "id_locacion": 1, "cantidad_disponible":   0.0, "cantidad_reservada":  0.0},
    {"id_existencia": "ex-004", "id_lote": "a1b2c3d4-0004-0004-0004-000000000004", "id_locacion": 3, "cantidad_disponible":  34.0, "cantidad_reservada":  5.0},
    {"id_existencia": "ex-005", "id_lote": "a1b2c3d4-0005-0005-0005-000000000005", "id_locacion": 2, "cantidad_disponible":  18.0, "cantidad_reservada":  3.0},
    {"id_existencia": "ex-006", "id_lote": "a1b2c3d4-0006-0006-0006-000000000006", "id_locacion": 4, "cantidad_disponible":  28.0, "cantidad_reservada":  0.0},
    {"id_existencia": "ex-007", "id_lote": "a1b2c3d4-0007-0007-0007-000000000007", "id_locacion": 5, "cantidad_disponible":  75.0, "cantidad_reservada":  8.0},
    {"id_existencia": "ex-008", "id_lote": "a1b2c3d4-0008-0008-0008-000000000008", "id_locacion": 1, "cantidad_disponible":  22.0, "cantidad_reservada":  0.0},
]

VENTAS = [
    {"id_venta": "vd-001", "id_lote": "a1b2c3d4-0001-0001-0001-000000000001", "id_locacion": 1, "cantidad": 58.0, "fecha_transaccion": "2026-09-08 08:15:22"},
    {"id_venta": "vd-002", "id_lote": "a1b2c3d4-0002-0002-0002-000000000002", "id_locacion": 2, "cantidad": 24.0, "fecha_transaccion": "2026-09-08 08:42:10"},
    {"id_venta": "vd-003", "id_lote": "a1b2c3d4-0004-0004-0004-000000000004", "id_locacion": 3, "cantidad": 18.0, "fecha_transaccion": "2026-09-08 09:05:55"},
    {"id_venta": "vd-004", "id_lote": "a1b2c3d4-0005-0005-0005-000000000005", "id_locacion": 2, "cantidad":  6.0, "fecha_transaccion": "2026-09-08 09:30:01"},
    {"id_venta": "vd-005", "id_lote": "a1b2c3d4-0006-0006-0006-000000000006", "id_locacion": 4, "cantidad": 12.0, "fecha_transaccion": "2026-09-08 10:12:44"},
    {"id_venta": "vd-006", "id_lote": "a1b2c3d4-0007-0007-0007-000000000007", "id_locacion": 5, "cantidad":  9.0, "fecha_transaccion": "2026-09-08 10:55:18"},
]

CAUSA_MERMA_OPTS = ["Vencimiento", "Deterioro físico", "Error operativo", "Robo/Hurto", "Daño en transporte", "Temperatura incorrecta"]

MERMAS = [
    {"id_merma": "mrm-001", "id_lote": "a1b2c3d4-0003-0003-0003-000000000003", "id_usuario": "usr-006", "cantidad": 12.0, "causa_merma": "Vencimiento",      "fecha_registro": "2026-09-08 07:00:00", "id_locacion": 1},
    {"id_merma": "mrm-002", "id_lote": "a1b2c3d4-0005-0005-0005-000000000005", "id_usuario": "usr-004", "cantidad":  4.0, "causa_merma": "Deterioro físico",  "fecha_registro": "2026-09-07 18:30:00", "id_locacion": 2},
    {"id_merma": "mrm-003", "id_lote": "a1b2c3d4-0006-0006-0006-000000000006", "id_usuario": "usr-006", "cantidad":  8.0, "causa_merma": "Temperatura incorrecta", "fecha_registro": "2026-09-07 09:15:00", "id_locacion": 4},
]

USUARIOS = [
    {"id_usuario": "usr-001", "id_rol": 1, "id_locacion": 6, "nombre_completo": "Jorge Almanza",  "estado_activo": True,  "email": "admin@freshtrack.mx",     "password": "Admin2026!",  "ultimo_acceso": "2026-09-08 09:31"},
    {"id_usuario": "usr-002", "id_rol": 2, "id_locacion": 6, "nombre_completo": "Martha López",   "estado_activo": True,  "email": "mlopez@freshtrack.mx",    "password": "Compras26!",  "ultimo_acceso": "2026-09-07 17:22"},
    {"id_usuario": "usr-003", "id_rol": 3, "id_locacion": 6, "nombre_completo": "Carlos Vega",    "estado_activo": True,  "email": "cvega@freshtrack.mx",     "password": "Plan2026!",   "ultimo_acceso": "2026-09-08 09:15"},
    {"id_usuario": "usr-004", "id_rol": 4, "id_locacion": 1, "nombre_completo": "Luis Pérez",     "estado_activo": True,  "email": "lperez@freshtrack.mx",    "password": "Tienda26!",   "ultimo_acceso": "2026-09-08 09:58"},
    {"id_usuario": "usr-005", "id_rol": 4, "id_locacion": 2, "nombre_completo": "Ana Ruiz",       "estado_activo": False, "email": "aruiz@freshtrack.mx",     "password": "Tienda26!",   "ultimo_acceso": "2026-09-08 10:42"},
    {"id_usuario": "usr-006", "id_rol": 5, "id_locacion": 1, "nombre_completo": "Pedro Vargas",   "estado_activo": True,  "email": "pvargas@freshtrack.mx",   "password": "Almacen26!",  "ultimo_acceso": "2026-09-08 07:30"},
    {"id_usuario": "usr-007", "id_rol": 6, "id_locacion": 6, "nombre_completo": "Roberto Soto",   "estado_activo": True,  "email": "rsoto@lacteosvalle.mx",   "password": "Prov2026!",   "ultimo_acceso": "2026-09-05 14:10"},
    {"id_usuario": "usr-008", "id_rol": 7, "id_locacion": 6, "nombre_completo": "Irma Auditoría", "estado_activo": False, "email": "iaudit@freshtrack.mx",    "password": "Audit2026!",  "ultimo_acceso": "2026-09-01 11:00"},
]

BITACORA = [
    {"id_evento": "evt-2890", "nombre_tabla": "existencia",    "tipo_operacion": "UPDATE", "id_usuario_app": "usr-005", "estado_anterior": '{"cantidad_disponible": 62}',  "estado_nuevo": '{"cantidad_disponible": 58}',  "fecha_evento": "2026-09-08 10:42:11", "descripcion": "Despacho FEFO Yogur — Sucursal Centro"},
    {"id_evento": "evt-2889", "nombre_tabla": "merma",         "tipo_operacion": "INSERT", "id_usuario_app": "usr-006", "estado_anterior": None,                             "estado_nuevo": '{"cantidad": 12, "causa_merma": "Vencimiento"}', "fecha_evento": "2026-09-08 07:00:44", "descripcion": "Baja por vencimiento Manzana Gala"},
    {"id_evento": "evt-2888", "nombre_tabla": "venta_detalle", "tipo_operacion": "INSERT", "id_usuario_app": "usr-004", "estado_anterior": None,                             "estado_nuevo": '{"cantidad": 58, "id_locacion": 1}',            "fecha_evento": "2026-09-08 08:15:22", "descripcion": "Venta Leche Entera — Sucursal Norte"},
    {"id_evento": "evt-2887", "nombre_tabla": "lote",          "tipo_operacion": "INSERT", "id_usuario_app": "usr-001", "estado_anterior": None,                             "estado_nuevo": '{"codigo_lote_prov": "PAN-2026-0907"}',          "fecha_evento": "2026-09-07 16:30:00", "descripcion": "Recepción lote Pan Integral"},
    {"id_evento": "evt-2886", "nombre_tabla": "existencia",    "tipo_operacion": "UPDATE", "id_usuario_app": "usr-006", "estado_anterior": '{"cantidad_disponible": 26}',  "estado_nuevo": '{"cantidad_disponible": 18}',  "fecha_evento": "2026-09-07 14:20:05", "descripcion": "Ajuste inventario Pechuga de Pollo"},
]

REPLENISHMENT = [
    {"id_sku": 1, "producto": "Leche Entera 1L",     "id_locacion": 2, "locacion": "Sucursal Centro — CDMX",      "stock_actual": 28,  "punto_reorden": 80, "demanda_pron": 320, "q_sugerido": 350, "id_proveedor": 1, "proveedor": "Lácteos del Valle", "lead_time_dias": 2, "costo_est": 6475,  "prioridad": "alta"},
    {"id_sku": 4, "producto": "Tomate Bola kg",       "id_locacion": 1, "locacion": "Sucursal Norte — Monterrey", "stock_actual": 34,  "punto_reorden": 50, "demanda_pron": 180, "q_sugerido": 200, "id_proveedor": 3, "proveedor": "Verduras Frescas",  "lead_time_dias": 1, "costo_est": 1300,  "prioridad": "alta"},
    {"id_sku": 5, "producto": "Pechuga de Pollo kg",  "id_locacion": 3, "locacion": "Sucursal Sur — Guadalajara", "stock_actual": 12,  "punto_reorden": 35, "demanda_pron":  90, "q_sugerido": 120, "id_proveedor": 4, "proveedor": "Carnes Refrigeradas","lead_time_dias": 3, "costo_est": 6600,  "prioridad": "alta"},
    {"id_sku": 2, "producto": "Yogur Natural 900g",   "id_locacion": 4, "locacion": "Sucursal Oriente — Puebla",  "stock_actual": 48,  "punto_reorden": 50, "demanda_pron": 140, "q_sugerido": 100, "id_proveedor": 1, "proveedor": "Lácteos del Valle", "lead_time_dias": 2, "costo_est": 2200,  "prioridad": "media"},
    {"id_sku": 6, "producto": "Pan Integral 600g",    "id_locacion": 5, "locacion": "Sucursal Occidente — León",  "stock_actual": 38,  "punto_reorden": 40, "demanda_pron":  80, "q_sugerido":  60, "id_proveedor": 5, "proveedor": "Panificadora Artesanal","lead_time_dias": 1, "costo_est": 1080, "prioridad": "media"},
]

TRANSFERS = [
    {"id": "TRF-001", "id_sku": 1, "producto": "Leche Entera 1L",    "id_locacion_orig": 1, "origen": "Sucursal Norte",  "id_locacion_dest": 2, "destino": "Sucursal Centro", "cantidad": 60, "motivo": "Exceso de inventario pre-vencimiento", "status": "pendiente",  "fecha": "2026-09-08"},
    {"id": "TRF-002", "id_sku": 5, "producto": "Pechuga de Pollo kg","id_locacion_orig": 6, "origen": "CEDIS Central",   "id_locacion_dest": 3, "destino": "Sucursal Sur",    "cantidad": 40, "motivo": "Reabastecimiento urgente",            "status": "aprobada",   "fecha": "2026-09-07"},
    {"id": "TRF-003", "id_sku": 3, "producto": "Manzana Gala kg",    "id_locacion_orig": 5, "origen": "Sucursal Occidente","id_locacion_dest": 4, "destino": "Sucursal Oriente","cantidad": 25,"motivo": "Balanceo de inventario FEFO",         "status": "ejecutada",  "fecha": "2026-09-06"},
]

ALERTS = [
    {"id": "ALT-001", "tipo": "critical", "mensaje": "Yogur Natural — Lote LDV-2026-0902 vence en 1 día (Sucursal Centro)",          "id_sku": 2, "id_locacion": 2, "dias_restantes": 1, "accion": "Aplicar descuento 30%"},
    {"id": "ALT-002", "tipo": "critical", "mensaje": "Pechuga de Pollo — Lote CRF-2026-0906 vence en 2 días (Sucursal Centro)",     "id_sku": 5, "id_locacion": 2, "dias_restantes": 2, "accion": "Transferir a CEDIS o descontar"},
    {"id": "ALT-003", "tipo": "critical", "mensaje": "Espinaca — Lote VFR-2026-0906 vence en 1 día (Sucursal Norte)",               "id_sku": 8, "id_locacion": 1, "dias_restantes": 1, "accion": "Aplicar descuento 40%"},
    {"id": "ALT-004", "tipo": "warning",  "mensaje": "Tomate Bola — Lote VFR-2026-0905 vence en 3 días (Sucursal Sur)",             "id_sku": 4, "id_locacion": 3, "dias_restantes": 3, "accion": "Monitorear y aplicar FEFO"},
    {"id": "ALT-005", "tipo": "warning",  "mensaje": "Pan Integral — Lote PAN-2026-0907 vence en 4 días (Sucursal Oriente)",        "id_sku": 6, "id_locacion": 4, "dias_restantes": 4, "accion": "Colocar en zona visible / descuento 15%"},
    {"id": "ALT-006", "tipo": "info",     "mensaje": "Stock de Leche Entera en Sucursal Centro bajo el punto de reorden (28 uds)",   "id_sku": 1, "id_locacion": 2, "dias_restantes": None, "accion": "Generar orden de reabastecimiento"},
]

DISCOUNTS = [
    {"id_sku": 2, "producto": "Yogur Natural 900g",  "codigo_lote_prov": "LDV-2026-0902", "dias_restantes": 1,  "precio_normal": 31.50, "descuento_pct": 30, "precio_nuevo": 22.05, "cantidad": 58,  "ingreso_potencial": 1279, "status": "pendiente"},
    {"id_sku": 5, "producto": "Pechuga de Pollo kg", "codigo_lote_prov": "CRF-2026-0906", "dias_restantes": 2,  "precio_normal": 89.90, "descuento_pct": 25, "precio_nuevo": 67.43, "cantidad": 18,  "ingreso_potencial": 1214, "status": "pendiente"},
    {"id_sku": 8, "producto": "Espinaca 250g",       "codigo_lote_prov": "VFR-2026-0906", "dias_restantes": 1,  "precio_normal": 22.90, "descuento_pct": 40, "precio_nuevo": 13.74, "cantidad": 22,  "ingreso_potencial": 302,  "status": "pendiente"},
    {"id_sku": 4, "producto": "Tomate Bola kg",      "codigo_lote_prov": "VFR-2026-0905", "dias_restantes": 3,  "precio_normal": 11.90, "descuento_pct": 15, "precio_nuevo": 10.12, "cantidad": 34,  "ingreso_potencial": 344,  "status": "pendiente"},
    {"id_sku": 6, "producto": "Pan Integral 600g",   "codigo_lote_prov": "PAN-2026-0907", "dias_restantes": 4,  "precio_normal": 28.50, "descuento_pct": 15, "precio_nuevo": 24.23, "cantidad": 28,  "ingreso_potencial": 679,  "status": "aplicado"},
]

FORECAST_DATA = [
    {"semana": "S34", "real": 1840, "pronostico": 1780, "ic_sup": 1940, "ic_inf": 1620},
    {"semana": "S35", "real": 1920, "pronostico": 1860, "ic_sup": 2020, "ic_inf": 1700},
    {"semana": "S36", "real": 1780, "pronostico": 1900, "ic_sup": 2060, "ic_inf": 1740},
    {"semana": "S37", "real": 2010, "pronostico": 1950, "ic_sup": 2110, "ic_inf": 1790},
    {"semana": "S38", "real": None, "pronostico": 2020, "ic_sup": 2200, "ic_inf": 1840},
    {"semana": "S39", "real": None, "pronostico": 2080, "ic_sup": 2260, "ic_inf": 1900},
    {"semana": "S40", "real": None, "pronostico": 2140, "ic_sup": 2320, "ic_inf": 1960},
]

SALES_MONTHLY = [
    {"mes": "Mar", "ventas": 284200, "merma_valor": 12400},
    {"mes": "Abr", "ventas": 301500, "merma_valor": 11800},
    {"mes": "May", "ventas": 318900, "merma_valor": 14200},
    {"mes": "Jun", "ventas": 295400, "merma_valor": 10900},
    {"mes": "Jul", "ventas": 334200, "merma_valor": 13600},
    {"mes": "Ago", "ventas": 356800, "merma_valor": 11200},
    {"mes": "Sep", "ventas": 98400,  "merma_valor": 3100},
]

CATEGORY_WASTE = [
    {"name": "Lácteos",   "value": 28, "fill": "#38bdf8"},
    {"name": "Frutas",    "value": 22, "fill": "#4ade80"},
    {"name": "Verduras",  "value": 19, "fill": "#a78bfa"},
    {"name": "Carnes",    "value": 18, "fill": "#f87171"},
    {"name": "Panadería", "value": 13, "fill": "#fbbf24"},
]

SAVINGS_DATA = [
    {"mes": "Mar", "descuentos": 8200,  "transferencias": 4100, "merma_evitada": 6300},
    {"mes": "Abr", "descuentos": 9400,  "transferencias": 5200, "merma_evitada": 7200},
    {"mes": "May", "descuentos": 11200, "transferencias": 6100, "merma_evitada": 8900},
    {"mes": "Jun", "descuentos": 9800,  "transferencias": 5800, "merma_evitada": 7400},
    {"mes": "Jul", "descuentos": 13400, "transferencias": 7200, "merma_evitada": 10200},
    {"mes": "Ago", "descuentos": 14800, "transferencias": 8100, "merma_evitada": 11600},
    {"mes": "Sep", "descuentos": 5314,  "transferencias": 3200, "merma_evitada": 4100},
]

MICROSERVICES = [
    {"nombre": "svc-productos",    "desc": "Catálogo de SKUs y metadata",                "puerto": 8001, "status": "ok"},
    {"nombre": "svc-lotes",        "desc": "Recepción y tracking de lotes",              "puerto": 8002, "status": "ok"},
    {"nombre": "svc-ventas",       "desc": "Registro de transacciones de venta",         "puerto": 8003, "status": "ok"},
    {"nombre": "svc-inventario",   "desc": "Existencias en tiempo real",                 "puerto": 8004, "status": "ok"},
    {"nombre": "svc-pronostico",   "desc": "Modelos ARIMA / Holt-Winters",               "puerto": 8005, "status": "ok"},
    {"nombre": "svc-caducidad",    "desc": "Monitor de fechas de caducidad",             "puerto": 8006, "status": "warning"},
    {"nombre": "svc-newsvendor",   "desc": "Cálculo Q* = F⁻¹(Cu/(Cu+Co))",              "puerto": 8007, "status": "ok"},
    {"nombre": "svc-fefo",         "desc": "Cola FEFO y despacho priorizado",            "puerto": 8008, "status": "ok"},
    {"nombre": "svc-transferencias","desc": "Traslados entre locaciones",                "puerto": 8009, "status": "ok"},
    {"nombre": "svc-alertas",      "desc": "Motor de notificaciones y triggers",         "puerto": 8010, "status": "ok"},
    {"nombre": "svc-desperdicio",  "desc": "Registro y cuantificación de mermas",        "puerto": 8011, "status": "ok"},
    {"nombre": "svc-metricas",     "desc": "KPIs y dashboards analíticos",               "puerto": 8012, "status": "ok"},
    {"nombre": "svc-reportes",     "desc": "Exportación de reportes ESG y operativos",   "puerto": 8013, "status": "error"},
]
