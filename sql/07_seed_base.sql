-- =============================================================================
-- 07_seed_base.sql — Datos base del sistema
--
-- Carga los catálogos mínimos para operar: roles, locaciones, proveedores,
-- productos, reglas de riesgo, configuración y usuarios con contraseña
-- hasheada. NO carga lotes, existencias ni ventas: eso lo genera el ETL o el
-- propio flujo de la aplicación.
--
-- Idempotente: puede ejecutarse varias veces sin duplicar información.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Roles
-- -----------------------------------------------------------------------------
INSERT INTO operacion.rol (nombre_rol, clave, descripcion) VALUES
    ('Administrador',        'admin',         'Acceso total al sistema'),
    ('Comprador',            'buyer',         'Gestión de proveedores y órdenes de compra'),
    ('Planeador de Demanda', 'planner',       'Pronóstico, reabastecimiento y transferencias'),
    ('Gerente de Tienda',    'store_manager', 'Operación de su tienda: ventas, mermas, descuentos'),
    ('Operador de Almacén',  'warehouse',     'Recepción de lotes, FEFO y registro de mermas'),
    ('Proveedor',            'supplier',      'Consulta de sus productos y pedidos'),
    ('Auditor',              'auditor',       'Consulta de bitácora, mermas y trazabilidad')
ON CONFLICT (nombre_rol) DO UPDATE
    SET clave = EXCLUDED.clave,
        descripcion = EXCLUDED.descripcion;

-- -----------------------------------------------------------------------------
-- Locaciones (tiendas y CEDIS)
-- -----------------------------------------------------------------------------
INSERT INTO operacion.locacion (tipo_locacion, nombre, ciudad) VALUES
    ('CEDIS',  'CEDIS Central',      'Querétaro'),
    ('CEDIS',  'CEDIS Norte',        'Monterrey'),
    ('Tienda', 'Tienda San Pedro',   'San Pedro Garza García'),
    ('Tienda', 'Tienda Cumbres',     'Monterrey'),
    ('Tienda', 'Tienda Valle Oriente','San Pedro Garza García'),
    ('Tienda', 'Tienda Centro',      'Saltillo'),
    ('Tienda', 'Tienda Sur',         'Monterrey')
ON CONFLICT (nombre) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Proveedores (lead time y MOQ son obligatorios para el motor de reabastecimiento)
-- -----------------------------------------------------------------------------
INSERT INTO operacion.proveedor (rfc, razon_social, lead_time_dias, moq, contacto_email, telefono) VALUES
    ('LDN850312AA1', 'Lácteos del Norte S.A. de C.V.',      3, 50,  'ventas@lacteosdelnorte.mx',   '8181234501'),
    ('FDB920614BB2', 'Frutas del Bajío S.A. de C.V.',       1, 100, 'pedidos@frutasdelbajio.mx',   '4771234502'),
    ('VFR011030CC3', 'Verduras Frescas del Rancho',         1, 80,  'ventas@verdurasrancho.mx',    '4771234503'),
    ('CRN781205DD4', 'Carnes Refrigeradas del Norte',       3, 40,  'contacto@carnesrefri.mx',     '8181234504'),
    ('PAA640918EE5', 'Panificadora Artesanal S.A.',         1, 60,  'dist@panartesanal.mx',        '8181234505'),
    ('ADC150701FF6', 'Abarrotes del Centro',                5, 200, 'compras@abarrotescentro.mx',  '4421234506')
ON CONFLICT (rfc) DO UPDATE
    SET razon_social   = EXCLUDED.razon_social,
        lead_time_dias = EXCLUDED.lead_time_dias,
        moq            = EXCLUDED.moq,
        contacto_email = EXCLUDED.contacto_email,
        telefono       = EXCLUDED.telefono;

-- -----------------------------------------------------------------------------
-- Productos
-- -----------------------------------------------------------------------------
INSERT INTO operacion.producto
    (codigo_gtin, nombre, id_proveedor, categoria, vida_util_estandar,
     unidad_medida, precio_costo, precio_venta, stock_seguridad, punto_reorden)
VALUES
    ('07501234560010', 'Leche Entera 1L',       (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='LDN850312AA1'), 'Lácteos',   15, 'Litro',  18.50, 24.90, 120, 200),
    ('07501234560027', 'Yogur Natural 900g',    (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='LDN850312AA1'), 'Lácteos',   21, 'Pieza',  22.00, 31.50,  60, 100),
    ('07501234560034', 'Manzana Gala kg',       (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='FDB920614BB2'), 'Frutas',    10, 'Kg',      8.00, 14.90,  80, 150),
    ('07501234560041', 'Tomate Bola kg',        (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='VFR011030CC3'), 'Verduras',   7, 'Kg',      6.50, 11.90,  70, 130),
    ('07501234560058', 'Pechuga de Pollo kg',   (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='CRN781205DD4'), 'Carnes',     5, 'Kg',     55.00, 89.90,  40,  80),
    ('07501234560065', 'Pan Integral 600g',     (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='PAA640918EE5'), 'Panadería',  4, 'Pieza',  18.00, 28.50,  50,  90),
    ('07501234560072', 'Queso Oaxaca 400g',     (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='LDN850312AA1'), 'Lácteos',   30, 'Pieza',  42.00, 62.00,  30,  60),
    ('07501234560089', 'Espinaca 250g',         (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='VFR011030CC3'), 'Verduras',   5, 'Bolsa',  14.00, 22.90,  40,  80),
    ('07501234560096', 'Crema Ácida 450g',      (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='LDN850312AA1'), 'Lácteos',   20, 'Pieza',  26.00, 38.00,  35,  70),
    ('07501234560102', 'Zanahoria kg',          (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='VFR011030CC3'), 'Verduras',  14, 'Kg',      5.00,  9.50,  60, 110),
    ('07501234560119', 'Jitomate Saladet kg',   (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='VFR011030CC3'), 'Verduras',   9, 'Kg',      9.50, 16.90,  55, 100),
    ('07501234560126', 'Arroz 1kg',             (SELECT id_proveedor FROM operacion.proveedor WHERE rfc='ADC150701FF6'), 'Abarrotes', 365, 'Paquete', 22.00, 33.50, 100, 180)
ON CONFLICT (codigo_gtin) DO UPDATE
    SET nombre             = EXCLUDED.nombre,
        id_proveedor       = EXCLUDED.id_proveedor,
        categoria          = EXCLUDED.categoria,
        vida_util_estandar = EXCLUDED.vida_util_estandar,
        unidad_medida      = EXCLUDED.unidad_medida,
        precio_costo       = EXCLUDED.precio_costo,
        precio_venta       = EXCLUDED.precio_venta,
        stock_seguridad    = EXCLUDED.stock_seguridad,
        punto_reorden      = EXCLUDED.punto_reorden;

-- -----------------------------------------------------------------------------
-- Reglas de clasificación de riesgo
--
-- DOCUMENTACIÓN DE UMBRALES (queda también en analitica.configuracion y en
-- el reporte técnico):
--
--   Categoría     Vigilancia        Crítico
--   ------------  ---------------   ----------------
--   Lácteos       4 días / 25 %     2 días / 10 %
--   Carnes        2 días / 40 %     1 día  / 20 %
--   Frutas        3 días / 25 %     1 día  / 10 %
--   Verduras      3 días / 30 %     1 día  / 15 %
--   Panadería     2 días / 40 %     1 día  / 20 %
--   Abarrotes    15 días / 20 %     5 días /  5 %
--   (default)     5 días / 30 %     2 días / 10 %
--
-- Un lote entra en CRÍTICO si cumple CUALQUIERA de las dos condiciones
-- (por días o por porcentaje de vida residual restante).
-- -----------------------------------------------------------------------------
INSERT INTO operacion.regla_riesgo
    (categoria, dias_vigilancia, dias_critico, pct_vigilancia, pct_critico, descripcion)
VALUES
    ('Lácteos',   4, 2, 25.00, 10.00, 'Productos lácteos: vida media, rotación alta'),
    ('Carnes',    2, 1, 40.00, 20.00, 'Cárnicos: altamente perecederos'),
    ('Frutas',    3, 1, 25.00, 10.00, 'Frutas frescas'),
    ('Verduras',  3, 1, 30.00, 15.00, 'Verduras y hortalizas'),
    ('Panadería', 2, 1, 40.00, 20.00, 'Panadería de vida corta'),
    ('Abarrotes', 15, 5, 20.00,  5.00, 'Abarrotes de vida larga')
ON CONFLICT DO NOTHING;

INSERT INTO operacion.regla_riesgo
    (es_default, dias_vigilancia, dias_critico, pct_vigilancia, pct_critico, descripcion)
SELECT true, 5, 2, 30.00, 10.00, 'Regla por defecto para categorías sin regla específica'
WHERE NOT EXISTS (SELECT 1 FROM operacion.regla_riesgo WHERE es_default);

-- -----------------------------------------------------------------------------
-- Usuarios con contraseña hasheada (bcrypt vía pgcrypto)
--   Las contraseñas de demostración se documentan en el README y deben
--   cambiarse antes de cualquier despliegue real.
-- -----------------------------------------------------------------------------
INSERT INTO operacion.usuario (id_rol, id_locacion, nombre_completo, email, password_hash, estado_activo)
VALUES
    ((SELECT id_rol FROM operacion.rol WHERE clave='admin'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='CEDIS Central'),
     'Jorge Almanza', 'admin@freshtrack.mx',
     crypt('Admin2026!', gen_salt('bf')), true),

    ((SELECT id_rol FROM operacion.rol WHERE clave='buyer'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='CEDIS Central'),
     'Martha López', 'buyer@freshtrack.mx',
     crypt('Compras2026!', gen_salt('bf')), true),

    ((SELECT id_rol FROM operacion.rol WHERE clave='planner'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='CEDIS Central'),
     'Carlos Vega', 'planner@freshtrack.mx',
     crypt('Plan2026!', gen_salt('bf')), true),

    ((SELECT id_rol FROM operacion.rol WHERE clave='store_manager'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='Tienda San Pedro'),
     'Luis Pérez', 'gerente@freshtrack.mx',
     crypt('Tienda2026!', gen_salt('bf')), true),

    ((SELECT id_rol FROM operacion.rol WHERE clave='store_manager'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='Tienda Cumbres'),
     'Ana Ruiz', 'gerente2@freshtrack.mx',
     crypt('Tienda2026!', gen_salt('bf')), true),

    ((SELECT id_rol FROM operacion.rol WHERE clave='warehouse'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='Tienda San Pedro'),
     'Pedro Vargas', 'almacen@freshtrack.mx',
     crypt('Almacen2026!', gen_salt('bf')), true),

    ((SELECT id_rol FROM operacion.rol WHERE clave='supplier'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='CEDIS Central'),
     'Roberto Soto', 'proveedor@freshtrack.mx',
     crypt('Proveedor2026!', gen_salt('bf')), true),

    ((SELECT id_rol FROM operacion.rol WHERE clave='auditor'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='CEDIS Central'),
     'Irma Salinas', 'auditor@freshtrack.mx',
     crypt('Auditor2026!', gen_salt('bf')), true),

    -- Usuario desactivado: sirve para demostrar el control activo/inactivo
    ((SELECT id_rol FROM operacion.rol WHERE clave='warehouse'),
     (SELECT id_locacion FROM operacion.locacion WHERE nombre='CEDIS Norte'),
     'Ex Empleado (inactivo)', 'inactivo@freshtrack.mx',
     crypt('Inactivo2026!', gen_salt('bf')), false)
ON CONFLICT (email) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Configuración del sistema
-- -----------------------------------------------------------------------------
INSERT INTO analitica.configuracion (clave, valor, tipo, descripcion) VALUES
    ('horizonte_pronostico_dias',      '7',    'entero',  'Horizonte por defecto del pronóstico en días'),
    ('metodo_pronostico_default',      'SUAVIZACION_EXPONENCIAL', 'texto', 'Método de pronóstico por defecto'),
    ('ventana_media_movil',            '28',   'entero',  'Días de historia usados por la media móvil'),
    ('alpha_suavizacion',              '0.30', 'decimal', 'Factor de suavización exponencial (0-1)'),
    ('min_dias_historia_pronostico',   '14',   'entero',  'Mínimo de días con ventas para pronosticar una serie'),
    ('cobertura_stock_seguridad_dias', '2',    'entero',  'Días de demanda que debe cubrir el stock de seguridad'),
    ('dias_ventana_riesgo_lote',       '5',    'entero',  'Horizonte con el que se estima el riesgo de desperdicio por lote'),
    ('umbral_sobreinventario_dias',    '21',   'entero',  'Días de cobertura por encima de los cuales hay sobreinventario'),
    ('descuento_pct_critico',          '30',   'decimal', 'Descuento sugerido para lotes en estado CRÍTICO'),
    ('descuento_pct_vigilancia',       '15',   'decimal', 'Descuento sugerido para lotes en estado VIGILANCIA'),
    ('jwt_horas_vigencia',             '8',    'entero',  'Horas de vigencia del token JWT'),
    ('max_intentos_login',             '5',    'entero',  'Intentos fallidos antes de bloquear temporalmente la cuenta')
ON CONFLICT (clave) DO UPDATE
    SET valor = EXCLUDED.valor,
        tipo = EXCLUDED.tipo,
        descripcion = EXCLUDED.descripcion;
