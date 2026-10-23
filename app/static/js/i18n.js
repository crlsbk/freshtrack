// ── Traducción ES → EN de la interfaz ─────────────────────────────────────────
// Las plantillas están escritas en español. Este script traduce en el navegador
// los textos visibles, los tooltips (title, data-ayuda, aria-label, placeholder)
// y las etiquetas de las gráficas. Cada texto original se guarda, así que volver
// a español no requiere recargar la página.
//
// - DICCIONARIO: frases exactas de la interfaz (menú, títulos, botones, ayudas).
// - REGLAS: textos que arma el servidor con datos (alertas, explicaciones, fechas,
//   unidades, conteos). Los nombres de productos, tiendas y proveedores son datos
//   y se dejan como están.
//
// Para agregar una frase nueva basta con sumarla a DICCIONARIO.
(function () {
  const LANG_KEY = "freshtrack_lang";

  const DICCIONARIO = {
    // ── Estructura general, menú y barra superior ──
    "FreshTrack": "FreshTrack",
    "Perecederos · IA": "Perishables · AI",
    "GESTIÓN DE PERECEDEROS": "PERISHABLES MANAGEMENT",
    "Principal": "Main",
    "Panel de control": "Dashboard",
    "Alertas": "Alerts",
    "Catálogos": "Catalogs",
    "Catálogo": "Catalog",
    "Productos": "Products",
    "Tiendas y CEDIS": "Stores and DCs",
    "Proveedores": "Suppliers",
    "Operación": "Operations",
    "Lotes y Recepción": "Batches and Receiving",
    "Lotes y recepción": "Batches and receiving",
    "Inventario": "Inventory",
    "Ventas": "Sales",
    "Orden de salida (FEFO)": "Picking order (FEFO)",
    "Trazabilidad": "Traceability",
    "Analítica": "Analytics",
    "Pronósticos": "Forecasts",
    "Reabastecimiento": "Replenishment",
    "Transferencias": "Transfers",
    "Descuentos": "Discounts",
    "Documentos (MongoDB)": "Documents (MongoDB)",
    "Desperdicio": "Waste",
    "Mermas": "Shrinkage",
    "Desperdicio evitado": "Waste avoided",
    "Sostenibilidad": "Sustainability",
    "Administración": "Administration",
    "Usuarios y Roles": "Users and Roles",
    "Usuarios y roles": "Users and roles",
    "Bitácora": "Audit log",
    "Configuración": "Settings",
    "Microservicios": "Microservices",
    "Base de datos en vivo · Tiempo real": "Live database · Real time",
    "Conexión activa en tiempo real a la base de datos operacional de FreshTrack": "Live connection to the FreshTrack operational database",
    "Alternar modo claro / oscuro": "Toggle light / dark mode",
    "Alternar tema": "Toggle theme",
    "Alternar menú lateral": "Toggle sidebar",
    "FreshTrack · Alternar menú lateral": "FreshTrack · Toggle sidebar",
    "Colapsar menú lateral": "Collapse sidebar",
    "Colapsar menú": "Collapse menu",
    "Alertas abiertas": "Open alerts",
    "Salir": "Log out",
    "Cerrar": "Close",
    "Vista": "View",
    "Cambiar a inglés": "Switch to English",
    "Cambiar a español": "Switch to Spanish",

    // ── Roles ──
    "Administrador": "Administrator",
    "Administrador (admin)": "Administrator (admin)",
    "Administrador ·": "Administrator ·",
    "Comprador": "Buyer",
    "Comprador (buyer)": "Buyer (buyer)",
    "Comprador ·": "Buyer ·",
    "Planeador": "Planner",
    "Planeador de Demanda": "Demand Planner",
    "Planeador de Demanda (planner)": "Demand Planner (planner)",
    "Planeador ·": "Planner ·",
    "Gerente de Tienda": "Store Manager",
    "Gerente de tienda": "Store manager",
    "Gerente de Tienda (store_manager)": "Store Manager (store_manager)",
    "Gerente de tienda ·": "Store manager ·",
    "Operador de Almacén": "Warehouse Operator",
    "Operador de Almacén (warehouse)": "Warehouse Operator (warehouse)",
    "Almacén": "Warehouse",
    "Almacén ·": "Warehouse ·",
    "Proveedor": "Supplier",
    "Proveedor (supplier)": "Supplier (supplier)",
    "Proveedor ·": "Supplier ·",
    "Auditor": "Auditor",
    "Auditor (auditor)": "Auditor (auditor)",
    "Auditor ·": "Auditor ·",
    "Usuario inactivo ·": "Inactive user ·",
    "Acceso total al sistema": "Full system access",
    "Acceso completo, usuarios y bitácora": "Full access, users and audit log",
    "Gestión de proveedores y órdenes de compra": "Supplier and purchase order management",
    "Proveedores, lotes y reabastecimiento": "Suppliers, batches and replenishment",
    "Pronóstico, reabastecimiento y transferencias": "Forecasting, replenishment and transfers",
    "Pronósticos, transferencias y descuentos": "Forecasts, transfers and discounts",
    "Operación de su tienda: ventas, mermas, descuentos": "Operations of their store: sales, shrinkage, discounts",
    "Recepción de lotes, FEFO y registro de mermas": "Batch receiving, FEFO and shrinkage logging",
    "Recepción, ventas, FEFO y mermas": "Receiving, sales, FEFO and shrinkage",
    "Consulta de sus productos y pedidos": "View their products and orders",
    "Consulta de productos y órdenes": "View products and orders",
    "Consulta de bitácora, mermas y trazabilidad": "Audit log, shrinkage and traceability queries",
    "Bitácora, mermas y trazabilidad": "Audit log, shrinkage and traceability",
    "Inventario, FEFO y transferencias": "Inventory, FEFO and transfers",
    "Pronóstico y reabastecimiento": "Forecasting and replenishment",
    "Productos, tiendas y proveedores": "Products, stores and suppliers",
    "Transferencias y descuentos": "Transfers and discounts",
    "Bitácora y trazabilidad": "Audit log and traceability",

    // ── Landing ──
    "FreshTrack — Gestión inteligente de inventario de perecederos": "FreshTrack — Smart perishable inventory management",
    "Acceder al sistema": "Sign in to the system",
    "Iniciar sesión": "Sign in",
    "Ver cómo funciona": "See how it works",
    "Entrar al sistema": "Enter the system",
    "FreshTrack es un sistema de gestión de inventario para productos perecederos. Controla la caducidad lote por lote, prioriza la salida de lo que está por vencer, pronostica la demanda por producto y tienda, y propone reabastecimiento y transferencias entre sucursales antes de que el producto se pierda.": "FreshTrack is an inventory management system for perishable products. It tracks expiration batch by batch, prioritizes moving out what is about to expire, forecasts demand by product and store, and proposes replenishment and transfers between branches before the product is lost.",
    "El problema": "The problem",
    "El problema: el producto perecedero se pierde antes de venderse": "The problem: perishable product is lost before it is sold",
    "En el comercio de alimentos, el inventario tiene fecha límite. Lo que no se vende a tiempo no se puede recuperar: se convierte en merma, en pérdida económica y en desperdicio con impacto ambiental.": "In food retail, inventory has a deadline. What is not sold in time cannot be recovered: it becomes shrinkage, financial loss and waste with an environmental impact.",
    "En el comercio minorista de perecederos, entre el 2% y el 4% de lo recibido termina como merma, y la mayor parte se debe a caducidad.": "In perishable retail, between 2% and 4% of what is received ends up as shrinkage, and most of it is due to expiration.",
    "Sin visibilidad de la caducidad por lote, la tienda reordena «a ojo»: compra de más lo que se vence y de menos lo que se agota. Ambos errores cuestan dinero.": "Without batch-level visibility of expiration, the store reorders by gut feeling: it overbuys what expires and underbuys what sells out. Both mistakes cost money.",
    "Decisiones sin información": "Decisions without information",
    "Saber qué se va a perder": "Know what will be lost",
    "Qué se propone FreshTrack": "What FreshTrack sets out to do",
    "Objetivos": "Objectives",
    "Clasificar cada lote según su vida útil restante —normal, vigilancia, crítico o vencido— con umbrales configurables por tipo de producto.": "Classify every batch by its remaining shelf life (normal, watch, critical or expired) with thresholds configurable by product type.",
    "Distinguir el inventario físico del realmente aprovechable. Lo que está por vencer no cubre demanda futura, y el sistema lo trata como tal.": "Tell physical inventory apart from inventory that can actually be sold. What is about to expire does not cover future demand, and the system treats it that way.",
    "Anticipar la demanda": "Anticipate demand",
    "Pronosticar la demanda por producto y por tienda a partir del historial de ventas, y medir el error del pronóstico en lugar de suponer que es bueno.": "Forecast demand by product and store from sales history, and measure the forecast error instead of assuming it is good.",
    "Decidir con respaldo": "Decide with evidence",
    "Proponer cuánto reordenar y qué mover entre tiendas, explicando el cálculo completo. La decisión final siempre la toma una persona.": "Propose how much to reorder and what to move between stores, explaining the full calculation. A person always makes the final decision.",
    "Detectar los lotes en riesgo antes de que caduquen y actuar sobre ellos: transferirlos a donde sí se venden, o descontarlos a tiempo.": "Detect at-risk batches before they expire and act on them: transfer them to where they do sell, or discount them in time.",
    "Menos merma": "Less shrinkage",
    "Cómo funciona": "How it works",
    "Cómo funciona el sistema": "How the system works",
    "El flujo sigue la operación real de una tienda, desde que el producto llega hasta que se vende o se da de baja.": "The flow follows the real operation of a store, from when the product arrives until it is sold or written off.",
    "Recepción por lote": "Receiving by batch",
    "Cada entrega se registra con proveedor, fechas de producción y caducidad, cantidad y costo. El sistema calcula la vida útil restante al instante.": "Each delivery is recorded with supplier, production and expiration dates, quantity and cost. The system calculates the remaining shelf life instantly.",
    "Salida FEFO": "FEFO picking",
    "Cada venta consume primero el lote que vence antes. La asignación se hace en una sola transacción: o se descuenta todo el inventario involucrado, o no se registra nada.": "Each sale consumes the batch that expires first. The allocation happens in a single transaction: either all the inventory involved is deducted, or nothing is recorded.",
    "Pronóstico y riesgo": "Forecast and risk",
    "Con el historial de ventas se estima la demanda por producto y tienda, y se compara contra el inventario aprovechable antes de la caducidad.": "Sales history is used to estimate demand by product and store, and it is compared against the inventory that can be sold before expiration.",
    "Recomendación y aprobación": "Recommendation and approval",
    "El sistema propone reabastecer, transferir o descontar, con su explicación. Un responsable revisa y aprueba; la decisión queda en la bitácora.": "The system proposes to replenish, transfer or discount, with its explanation. A person in charge reviews and approves; the decision is kept in the audit log.",
    "Beneficios": "Benefits",
    "Beneficios esperados": "Expected benefits",
    "Cada beneficio se mide con datos que el propio sistema registra, para poder comprobar si el resultado se está cumpliendo.": "Each benefit is measured with data the system itself records, so you can check whether the result is being achieved.",
    "Cómo se mide:": "How it is measured:",
    "Menos comida a la basura.": "Less food in the trash.",
    "Más valor en el anaquel.": "More value on the shelf.",
    "Inventario más sano": "Healthier inventory",
    "Bitácora auditable": "Auditable log",
    "Accesos, altas, recepciones, ventas, mermas, pronósticos y aprobaciones quedan registrados con fecha, usuario, rol y valores anterior y nuevo.": "Logins, new records, receipts, sales, shrinkage, forecasts and approvals are recorded with date, user, role and old and new values.",
    "Acceso al sistema": "System access",
    "El acceso es con cuentas registradas. Cada usuario entra con su correo y contraseña, y el sistema le habilita únicamente las pantallas que corresponden a su rol: administración, compras, planeación, gerencia de tienda, almacén, proveedor o auditoría.": "Access is with registered accounts. Each user signs in with their email and password, and the system only enables the screens that match their role: administration, purchasing, planning, store management, warehouse, supplier or audit.",
    "1,050 millones de toneladas de alimentos se desperdician cada año en el mundo, cerca de un tercio de todo lo que se produce (FAO).": "1.05 billion tonnes of food are wasted every year worldwide, close to a third of everything that is produced (FAO).",
    "Lote por vencer, lote vencido, riesgo de merma, sobreinventario, riesgo de faltante, reabastecimiento requerido y transferencia sugerida. Se generan por reglas sobre los datos, no se capturan a mano.": "Batch about to expire, expired batch, shrinkage risk, overstock, stockout risk, replenishment required and suggested transfer. They are generated by rules over the data, not entered by hand.",
    "El objetivo no es adivinar el futuro, sino tomar mejores decisiones con la información que ya existe en la operación diaria.": "The goal is not to guess the future, but to make better decisions with the information that already exists in daily operations.",
    "FreshTrack · Sistema de gestión de inventario de perecederos · Equipo 05": "FreshTrack · Perishable inventory management system · Team 05",
    "Proyecto académico · Equipo 05": "Academic project · Team 05",
    "Segundo parcial · 2026": "Second term · 2026",

    // ── Login y error ──
    "FreshTrack — Iniciar sesión": "FreshTrack — Sign in",
    "Accede con tu correo y contraseña.": "Sign in with your email and password.",
    "Correo": "Email",
    "Correo electrónico": "Email address",
    "Correo electrónico *": "Email address *",
    "Contraseña": "Password",
    "Ver usuarios de demostración": "Show demo users",
    "La cuenta «inactivo@freshtrack.mx» está desactivada: sirve para comprobar que el sistema rechaza usuarios inactivos.": "The «inactivo@freshtrack.mx» account is deactivated: it is used to check that the system rejects inactive users.",
    "Usuario inactivo": "Inactive user",
    "Correo o contraseña incorrectos.": "Wrong email or password.",
    "FreshTrack — Error 404": "FreshTrack — Error 404",
    "No encontramos esa página": "We couldn't find that page",
    "La página que buscas no existe.": "The page you are looking for does not exist.",
    "Ir al inicio": "Go to home",
    "Algo falló del lado del servidor": "Something went wrong on the server",
    "Volver al panel": "Back to the dashboard",
    "← Volver a la página principal": "← Back to the main page",

    // ── Títulos de pestaña y migas ──
    "FreshTrack — Alertas": "FreshTrack — Alerts",
    "FreshTrack — Bitácora": "FreshTrack — Audit log",
    "FreshTrack — Cola FEFO": "FreshTrack — FEFO queue",
    "FreshTrack — Configuración": "FreshTrack — Settings",
    "FreshTrack — Descuentos": "FreshTrack — Discounts",
    "FreshTrack — Desperdicio Evitado": "FreshTrack — Waste Avoided",
    "FreshTrack — Inventario": "FreshTrack — Inventory",
    "FreshTrack — Lotes y Recepción": "FreshTrack — Batches and Receiving",
    "FreshTrack — Mermas": "FreshTrack — Shrinkage",
    "FreshTrack — Microservicios": "FreshTrack — Microservices",
    "FreshTrack — MongoDB Políglota": "FreshTrack — Polyglot MongoDB",
    "FreshTrack — Panel de Control": "FreshTrack — Dashboard",
    "FreshTrack — Productos": "FreshTrack — Products",
    "FreshTrack — Pronósticos": "FreshTrack — Forecasts",
    "FreshTrack — Proveedores": "FreshTrack — Suppliers",
    "FreshTrack — Reabastecimiento": "FreshTrack — Replenishment",
    "FreshTrack — Sostenibilidad": "FreshTrack — Sustainability",
    "FreshTrack — Tiendas y CEDIS": "FreshTrack — Stores and DCs",
    "FreshTrack — Transferencias": "FreshTrack — Transfers",
    "FreshTrack — Trazabilidad": "FreshTrack — Traceability",
    "FreshTrack — Usuarios y Roles": "FreshTrack — Users and Roles",
    "FreshTrack — Ventas": "FreshTrack — Sales",
    "Panel de Control": "Dashboard",
    "Cola FEFO": "FEFO queue",
    "Desperdicio Evitado": "Waste Avoided",
    "MongoDB Políglota": "Polyglot MongoDB",
    "Bitácora de auditoría": "Audit log",
    "Usuarios": "Users",

    // ── Panel de control ──
    "Resumen operacional": "Operational summary",
    "Monitoreo en tiempo real de la red de tiendas y CEDIS con indicadores calculados directamente contra la base de datos operacional activa.": "Real-time monitoring of the store and DC network with indicators calculated directly against the live operational database.",
    "Indicadores calculados dinámicamente en tiempo real contra la base de datos operacional.": "Indicators calculated dynamically in real time against the operational database.",
    "Qué atender hoy": "What to handle today",
    "Requieren acción inmediata": "Require immediate action",
    "Requieren baja inmediata": "Require immediate write-off",
    "Esperan aprobación": "Awaiting approval",
    "Esperan aprobación humana": "Awaiting human approval",
    "Esperan decisión": "Awaiting decision",
    "Compras por aprobar": "Purchases to approve",
    "Lotes críticos": "Critical batches",
    "Lotes críticos o vencidos": "Critical or expired batches",
    "lotes en estado crítico o vencido": "batches in critical or expired state",
    "Lotes en riesgo": "At-risk batches",
    "Lotes en vigilancia": "Batches on watch",
    "Lotes por vencer": "Batches about to expire",
    "Lotes a 2 días o menos de vencer": "Batches 2 days or less from expiring",
    "Lotes con existencia": "Batches with stock",
    "Lotes que entran en la ventana de riesgo": "Batches entering the risk window",
    "Valor del inventario": "Inventory value",
    "Dinero invertido en el producto que hay hoy en tiendas y CEDIS, a costo de compra.": "Money invested in the product currently in stores and DCs, at purchase cost.",
    "Ventas del período": "Sales for the period",
    "Ingreso total del período": "Total revenue for the period",
    "Unidades vendidas en el período": "Units sold in the period",
    "Ticket promedio": "Average ticket",
    "Tickets": "Tickets",
    "Tickets generados": "Tickets generated",
    "Ventas y merma por mes": "Sales and shrinkage by month",
    "Merma por categoría": "Shrinkage by category",
    "Merma por categoría (donde más se pierde)": "Shrinkage by category (where most is lost)",
    "Productos con más merma": "Products with the most shrinkage",
    "Productos con mayor merma (valorizada)": "Products with the highest shrinkage (by value)",
    "Tiendas con más merma": "Stores with the most shrinkage",
    "Tasa de merma": "Shrinkage rate",
    "Tasa de merma sobre lo recibido (180 días)": "Shrinkage rate over received units (180 days)",
    "productos perecederos en catálogo": "perishable products in catalog",
    "tiendas y CEDIS conectados": "stores and DCs connected",
    "unidades bajo seguimiento por lote": "units tracked by batch",
    "Ventana de tiempo": "Time window",
    "Último mes (30 d)": "Last month (30 d)",
    "Último mes (30 días)": "Last month (30 days)",
    "Últimos 3 meses (90 d)": "Last 3 months (90 d)",
    "Últimos 6 meses (180 d)": "Last 6 months (180 d)",
    "Histórico completo": "Full history",
    "Ver detalle →": "View details →",
    "Ver el listado →": "View list →",
    "Consultada en vivo": "Queried live",
    "En total ahora mismo": "Total right now",
    "Con los filtros actuales": "With the current filters",

    // ── Alertas ──
    "Alertas automáticas": "Automatic alerts",
    "Alertas del sistema": "System alerts",
    "Avisos generados automáticamente sobre lotes por vencer, inventario bajo y órdenes pendientes. Al recalcular, las que ya no aplican se cierran solas.": "Notices generated automatically about batches about to expire, low inventory and pending orders. When recalculated, the ones that no longer apply close by themselves.",
    "Avisos automáticos: lotes por vencer, riesgo de faltante, sobreinventario y órdenes pendientes.": "Automatic notices: batches about to expire, stockout risk, overstock and pending orders.",
    "Alertas abiertas por tipo": "Open alerts by type",
    "Recalcular alertas": "Recalculate alerts",
    "Pulsa «Recalcular alertas» para que el motor vuelva a evaluar todas las reglas sobre el inventario y las órdenes actuales.": "Press «Recalculate alerts» so the engine re-evaluates all rules against the current inventory and orders.",
    "No hay alertas en este filtro": "No alerts for this filter",
    "Tipo de alerta": "Alert type",
    "Severidad": "Severity",
    "Abiertas": "Open",
    "Atendidas": "Handled",
    "Descartadas": "Dismissed",
    "Urgentes": "Urgent",
    "Lote por vencer": "Batch about to expire",
    "Lote vencido": "Expired batch",
    "Riesgo de merma": "Shrinkage risk",
    "Sobreinventario": "Overstock",
    "Riesgo de faltante": "Stockout risk",
    "Reabastecimiento requerido": "Replenishment required",
    "Transferencia sugerida": "Suggested transfer",
    "Le quedan pocos días; conviene venderlo primero o ponerle descuento.": "It has few days left; sell it first or discount it.",
    "Ya pasó su fecha de caducidad y debe retirarse del anaquel.": "It is past its expiration date and must be removed from the shelf.",
    "Al ritmo de venta actual no se alcanzará a vender antes de caducar.": "At the current sales pace it will not sell before it expires.",
    "Hay mucho más producto del que se espera vender.": "There is much more product than expected to sell.",
    "La existencia se acabaría antes de que llegue un nuevo pedido.": "Stock would run out before a new order arrives.",
    "Hay una orden de compra sugerida esperando aprobación.": "There is a suggested purchase order awaiting approval.",
    "Conviene mover producto a otra tienda donde se vende mejor.": "It is worth moving product to another store where it sells better.",
    "La existencia alcanza para menos días que el tiempo de entrega del proveedor.": "Stock covers fewer days than the supplier's lead time.",
    "Lotes con muy poca vida útil. Conviene venderlos con descuento, transferirlos o darlos de baja.": "Batches with very little shelf life left. Sell them at a discount, transfer them or write them off.",
    "Alerta marcada como atendida.": "Alert marked as handled.",
    "Total Alertas": "Total Alerts",

    // ── Productos, tiendas, proveedores ──
    "+ Nuevo producto": "+ New product",
    "+ Nueva tienda o CEDIS": "+ New store or DC",
    "+ Nuevo proveedor": "+ New supplier",
    "+ Nuevo usuario": "+ New user",
    "+ Registrar recepción": "+ Record receipt",
    "Alta, edición y activación de productos. Cada cambio queda registrado en la bitácora.": "Create, edit and activate products. Every change is recorded in the audit log.",
    "Alta, consulta, edición y activación de puntos de venta y centros de distribución.": "Create, view, edit and activate points of sale and distribution centers.",
    "Alta, consulta, edición y activación de proveedores, con su tiempo de entrega (lead time) y pedido mínimo (MOQ).": "Create, view, edit and activate suppliers, with their lead time and minimum order quantity (MOQ).",
    "Registrar producto": "Register product",
    "Registrar proveedor": "Register supplier",
    "Registrar ubicación": "Register location",
    "Registrar usuario": "Register user",
    "Nombre": "Name",
    "Nombre *": "Name *",
    "Nombre completo *": "Full name *",
    "Nombre o código GTIN": "Name or GTIN code",
    "Nombre o correo": "Name or email",
    "Código GTIN": "GTIN code",
    "Categoría": "Category",
    "Categoría *": "Category *",
    "Unidad": "Unit",
    "Unidad de medida *": "Unit of measure *",
    "Vida útil": "Shelf life",
    "Vida útil (días)": "Shelf life (days)",
    "Vida útil del producto": "Product shelf life",
    "Vida útil estándar (días) *": "Standard shelf life (days) *",
    "La vida útil estándar se usa para calcular la vida útil restante de cada lote cuando el lote no trae fecha de producción.": "The standard shelf life is used to calculate each batch's remaining shelf life when the batch has no production date.",
    "Precio": "Price",
    "Precio de costo": "Cost price",
    "Precio de venta": "Sale price",
    "Precio normal": "Regular price",
    "Precio nuevo": "New price",
    "Perecedero": "Perishable",
    "Tipo": "Type",
    "Tipo *": "Type *",
    "Ciudad": "City",
    "Dirección": "Address",
    "Teléfono": "Phone",
    "Contacto": "Contact",
    "Correo de contacto": "Contact email",
    "Razón social": "Company name",
    "Razón social *": "Company name *",
    "Razón social o RFC": "Company name or RFC",
    "RFC *": "RFC (tax ID) *",
    "Lead time": "Lead time",
    "Lead time (días)": "Lead time (days)",
    "Lead time (días) *": "Lead time (days) *",
    "MOQ (Pedido mínimo)": "MOQ (Minimum order)",
    "MOQ (pedido mínimo) *": "MOQ (minimum order) *",
    "El lead time y el MOQ alimentan el motor de reabastecimiento: sin ellos no se puede calcular si el pedido llega a tiempo ni si el mínimo obliga a sobreinventar.": "Lead time and MOQ feed the replenishment engine: without them it cannot calculate whether the order arrives in time or whether the minimum forces overstocking.",
    "Tienda": "Store",
    "Tienda *": "Store *",
    "Tienda / CEDIS": "Store / DC",
    "Tienda / CEDIS *": "Store / DC *",
    "Tienda / CEDIS de destino *": "Destination store / DC *",
    "Tienda asignada": "Assigned store",
    "Ubicación": "Location",
    "Ubicaciones": "Locations",
    "Activar": "Activate",
    "Desactivar": "Deactivate",
    "Editar": "Edit",
    "Guardar": "Save",
    "Guardar cambios": "Save changes",
    "Guardar datos": "Save data",
    "Cancelar": "Cancel",
    "Buscar": "Search",
    "Filtrar": "Filter",
    "Limpiar": "Clear",
    "Ver": "View",
    "Acciones": "Actions",
    "Acción": "Action",
    "Estado": "Status",
    "Válida": "Valid",
    "Sí": "Yes",
    "No": "No",
    "Todos": "All",
    "Todas": "All",
    "Todos los productos": "All products",
    "Selecciona…": "Select…",
    "Sin asignar": "Unassigned",
    "Sin registros": "No records",
    "Se genera automáticamente": "Generated automatically",
    "Siguiente ›": "Next ›",
    "‹ Anterior": "‹ Previous",
    "Página actual": "Current page",
    "Desde": "From",
    "Hasta": "To",
    "Clave": "Key",
    "Valor": "Value",
    "Descripción": "Description",
    "Fecha": "Date",
    "Detalle": "Details",
    "Registro": "Record",
    "Origen → Destino": "Origin → Destination",

    // ── Lotes, inventario y FEFO ──
    "Registrar recepción de mercancía": "Record goods receipt",
    "Registra cada entrega como un lote con proveedor, fechas, cantidad y costo. Su vida útil restante y riesgo se calculan al momento.": "Record each delivery as a batch with supplier, dates, quantity and cost. Its remaining shelf life and risk are calculated on the spot.",
    "Al guardar se crean el lote, su existencia en la ubicación y el movimiento de entrada en el kardex, todo en una sola transacción y con registro en la bitácora.": "Saving creates the batch, its stock at the location and the inbound movement in the stock ledger, all in a single transaction and recorded in the audit log.",
    "Código de lote del proveedor *": "Supplier batch code *",
    "Fecha de recepción *": "Receipt date *",
    "Fecha de producción": "Production date",
    "Fecha de caducidad *": "Expiration date *",
    "Cantidad recibida *": "Quantity received *",
    "Costo unitario": "Unit cost",
    "Costo unitario *": "Unit cost *",
    "Proveedor *": "Supplier *",
    "Producto": "Product",
    "Producto *": "Product *",
    "Lote": "Batch",
    "Lotes": "Batches",
    "Caducidad": "Expiration",
    "Caduca": "Expires",
    "Días restantes": "Days left",
    "Días": "Days",
    "Riesgo": "Risk",
    "Recepción": "Receipt",
    "Recibido": "Received",
    "Existencia": "Stock",
    "Disponible": "Available",
    "Total disponible": "Total available",
    "Cantidad": "Quantity",
    "Cantidad *": "Quantity *",
    "Costo": "Cost",
    "Observaciones": "Notes",
    "Observación": "Note",
    "Normal": "Normal",
    "Vigilancia": "Watch",
    "En vigilancia": "On watch",
    "Crítico": "Critical",
    "Crítica": "Critical",
    "Críticas": "Critical",
    "CRÍTICO": "CRITICAL",
    "Vencido": "Expired",
    "vence hoy": "expires today",
    "En riesgo": "At risk",
    "Existencias por producto, tienda y lote, con su fecha de caducidad y nivel de riesgo.": "Stock by product, store and batch, with its expiration date and risk level.",
    "Inventario por lote": "Inventory by batch",
    "Inventario por ubicación": "Inventory by location",
    "Inventario en riesgo": "Inventory at risk",
    "Inventario físico": "Physical inventory",
    "Inventario útil": "Usable inventory",
    "Inventario ya movido": "Inventory already moved",
    "Unidades en existencia": "Units in stock",
    "Unidades": "Units",
    "Buscar producto o lote": "Search product or batch",
    "Producto, lote o proveedor": "Product, batch or supplier",
    "Limitar a una tienda": "Limit to one store",
    "Orden de salida": "Picking order",
    "First Expired, First Out: este es el orden exacto en el que el sistema debe sacar el inventario. El primer lote de la lista es el que vence antes y el que se consumirá primero en la próxima venta.": "First Expired, First Out: this is the exact order in which the system must take inventory out. The first batch in the list is the one that expires first and will be consumed first in the next sale.",
    "Ver cola": "View queue",
    "Lote consumido": "Batch consumed",
    "Previsualizar reparto FEFO": "Preview FEFO allocation",
    "La previsualización consulta el inventario real y muestra cómo se repartiría la cantidad entre lotes, sin escribir nada en la base.": "The preview reads the real inventory and shows how the quantity would be split across batches, without writing anything to the database.",
    "Reparto FEFO calculado": "Calculated FEFO allocation",
    "Días vs caducidad": "Days vs expiration",
    "Margen vs caducidad": "Margin vs expiration",
    "Umbrales de clasificación de riesgo": "Risk classification thresholds",
    "Un lote se clasifica comparando sus días restantes y su porcentaje de vida útil contra estos umbrales. La resolución es por precedencia:": "A batch is classified by comparing its days left and its shelf-life percentage against these thresholds. Resolution is by precedence:",
    "Un lote se marca": "A batch is marked",
    "cuando los días restantes son negativos. Se marca": "when the days left are negative. It is marked",
    "cuando entra en la ventana crítica por días o por porcentaje de vida útil,": "when it enters the critical window by days or by shelf-life percentage,",
    "cuando entra en la ventana intermedia, y": "when it enters the intermediate window, and",
    "en cualquier otro caso. La clasificación se calcula en el momento de la consulta: no se guarda, así nunca queda desactualizada.": "in any other case. The classification is calculated at query time: it is not stored, so it is never out of date.",
    "Crítico — días": "Critical — days",
    "Vigilancia — días": "Watch — days",
    "regla de la categoría": "category rule",
    "regla del SKU": "SKU rule",
    "regla por defecto": "default rule",
    "Aplica a": "Applies to",
    "Alcance": "Scope",
    "Por defecto": "Default",

    // ── Ventas ──
    "Registrar venta": "Record sale",
    "Registro de ventas con FEFO": "Sales recording with FEFO",
    "Las ventas consumen primero el lote que vence antes. La asignación se hace en una sola transacción y el inventario se descuenta lote por lote.": "Sales consume the batch that expires first. The allocation happens in a single transaction and inventory is deducted batch by batch.",
    "Movimientos de venta (200 líneas)": "Sales movements (200 lines)",
    "Folio": "Receipt no.",
    "Folio, producto o lote": "Receipt no., product or batch",
    "Subtotal": "Subtotal",
    "Venta": "Sale",
    "Unidades vendidas": "Units sold",
    "El detalle de cada venta y el registro de nuevas ventas están en": "The detail of each sale and the recording of new sales are in",

    // ── Mermas ──
    "Registrar merma": "Record shrinkage",
    "Registro de mermas": "Shrinkage log",
    "Registra producto perdido indicando tienda, lote, cantidad y causa. El inventario se descuenta en el mismo paso.": "Record lost product with store, batch, quantity and cause. Inventory is deducted in the same step.",
    "Causas disponibles: caducidad, daño, calidad, cadena de frío, manipulación, devolución y otra. La merma por caducidad es la que el motor de alertas intenta anticipar.": "Available causes: expiration, damage, quality, cold chain, handling, return and other. Expiration shrinkage is what the alert engine tries to anticipate.",
    "Lote (producto — caducidad — existencia) *": "Batch (product — expiration — stock) *",
    "Causa": "Cause",
    "Causa *": "Cause *",
    "Daño": "Damage",
    "Calidad": "Quality",
    "Cadena de frío": "Cold chain",
    "Manipulación": "Handling",
    "Devolución": "Return",
    "Otra": "Other",
    "Caducidad, daño o cadena de frío": "Expiration, damage or cold chain",
    "Ej. llegó con 2 cajas dañadas": "E.g. arrived with 2 damaged boxes",
    "Detalle de lo ocurrido": "Details of what happened",
    "Merma": "Shrinkage",
    "Merma acumulada": "Accumulated shrinkage",
    "Merma en tienda": "In-store shrinkage",
    "Merma por caducidad": "Expiration shrinkage",
    "Merma por causa": "Shrinkage by cause",
    "Merma por tienda": "Shrinkage by store",
    "Mermas recientes (200)": "Recent shrinkage (200)",
    "Mermado": "Lost",
    "Valor de la merma": "Shrinkage value",
    "Valor monetario perdido": "Monetary value lost",
    "Unidades mermadas": "Units lost",
    "Unidades mermadas (180 d)": "Units lost (180 d)",
    "Unidades perdidas acumuladas": "Accumulated lost units",
    "Unidades vencidas": "Expired units",
    "Desperdicio global": "Overall waste",
    "De lo recibido en último mes (30 días)": "Of what was received in the last month (30 days)",
    "Cifras agregadas del inventario en línea. No se muestra información comercial sensible.": "Aggregated figures of the live inventory. No sensitive commercial information is shown.",
    "Pérdida inevitable registrada": "Unavoidable loss recorded",

    // ── Trazabilidad ──
    "Trazabilidad completa": "Full traceability",
    "Trazabilidad de lote": "Batch traceability",
    "Del proveedor al anaquel y del anaquel a la merma. Cada movimiento queda registrado y auditable, con el usuario que lo ejecutó.": "From supplier to shelf and from shelf to shrinkage. Every movement is recorded and auditable, with the user who performed it.",
    "Selecciona un lote y reconstruye su ciclo completo: proveedor, recepción, existencias por ubicación, ventas FEFO, transferencias, mermas y estado final.": "Select a batch and rebuild its full lifecycle: supplier, receipt, stock by location, FEFO sales, transfers, shrinkage and final state.",
    "Selecciona un lote": "Select a batch",
    "Selecciona un lote…": "Select a batch…",
    "Elige un lote en la lista de arriba para ver su ciclo de vida completo.": "Pick a batch in the list above to see its full lifecycle.",
    "Consultar trazabilidad": "Look up traceability",
    "Trazar": "Trace",

    // ── Pronóstico ──
    "Pronóstico": "Forecast",
    "Pronóstico de demanda": "Demand forecast",
    "Demanda esperada por producto y tienda para los próximos días, con el error de cada modelo para saber qué tan confiable es.": "Expected demand by product and store for the coming days, with each model's error so you know how reliable it is.",
    "Ejecutar pronóstico": "Run forecast",
    "Ejecutar y guardar corrida": "Run and save forecast run",
    "Método": "Method",
    "Media móvil": "Moving average",
    "Media móvil:": "Moving average:",
    "Media móvil ponderada": "Weighted moving average",
    "Media móvil ponderada:": "Weighted moving average:",
    "Suavización exponencial": "Exponential smoothing",
    "Suavización exponencial:": "Exponential smoothing:",
    "Promedio simple de los últimos N días de venta.": "Simple average of the last N days of sales.",
    "Promedio con pesos crecientes: los días recientes pesan más.": "Average with increasing weights: recent days weigh more.",
    "Suavización exponencial simple (SES) con factor alfa.": "Simple exponential smoothing (SES) with an alpha factor.",
    "Alfa (suavización exponencial)": "Alpha (exponential smoothing)",
    "Horizonte": "Horizon",
    "Horizonte (días)": "Horizon (days)",
    "Ventana de historia (días)": "History window (days)",
    "Ventana de la media móvil": "Moving average window",
    "Historial de corridas": "Forecast run history",
    "Series": "Series",
    "Duración": "Duration",
    "Ejecutó": "Run by",
    "Error promedio (MAE)": "Average error (MAE)",
    "Error con castigo (RMSE)": "Penalized error (RMSE)",
    "Error porcentual (WMAPE)": "Percentage error (WMAPE)",
    "Error sobre la demanda total": "Error over total demand",
    "Sobre la demanda total": "Over total demand",
    "Penaliza errores grandes": "Penalizes large errors",
    "Pesa más los errores grandes": "Weighs large errors more",
    "Unidades de diferencia por producto y día": "Units of difference per product and day",
    "Unidades por producto y día": "Units per product and day",
    "MAE (error absoluto medio)": "MAE (mean absolute error)",
    "Demanda diaria": "Daily demand",
    "Promedio diario": "Daily average",
    "Próximo día": "Next day",
    "Tiempo de cómputo": "Computation time",
    "Nota metodológica:": "Methodology note:",
    "sobre el tramo final del historial se pronostica hacia adelante y se compara con la demanda real ya registrada (validación retrospectiva). El MAE dice cuántas unidades se desvía en promedio el pronóstico; el WMAPE expresa ese error como porcentaje de la demanda total, que es la cifra comparable entre productos de tamaños muy distintos.": "on the last stretch of history the forecast runs forward and is compared with the actual demand already recorded (backtesting). MAE tells how many units the forecast is off on average; WMAPE expresses that error as a percentage of total demand, which is the figure that is comparable across products of very different sizes.",
    "Algoritmo utilizado para proyectar la serie temporal: Promedio móvil simple, Suavización exponencial, o Descomposición estacional por día de semana.": "Algorithm used to project the time series: simple moving average, exponential smoothing, or seasonal decomposition by day of week.",
    "Ventana temporal futura: cantidad de días hacia adelante que se pronosticarán para cada SKU en cada tienda.": "Future time window: number of days ahead to forecast for each SKU in each store.",
    "Días de ventas históricas que el modelo analiza para entrenar los patrones de consumo (mínimo 14 días para capturar estacionalidad semanal).": "Days of sales history the model analyzes to learn consumption patterns (at least 14 days to capture weekly seasonality).",
    "Número de días recientes considerados en el cálculo de la media móvil para suavizar picos aislados de demanda.": "Number of recent days considered in the moving average to smooth isolated demand spikes.",
    "Factor de ponderación α entre 0.05 y 0.95. Un valor alto da mayor peso a los días más recientes; un valor bajo genera proyecciones más estables.": "Weighting factor α between 0.05 and 0.95. A high value gives more weight to recent days; a low value produces more stable projections.",
    "Permite ejecutar el modelo de demanda para una sola sucursal o para toda la red de tiendas de forma agregada.": "Lets you run the demand model for a single branch or for the whole store network in aggregate.",
    "En promedio, el pronóstico se equivoca por esta cantidad de unidades al día. Menor es mejor.": "On average, the forecast is off by this many units per day. Lower is better.",
    "Si es mucho mayor que el MAE, hubo días con errores fuertes.": "If it is much higher than MAE, there were days with large errors.",
    "Porcentaje de la demanda que el pronóstico no acertó. Menos de 30% suele considerarse bueno en perecederos.": "Percentage of demand the forecast missed. Under 30% is usually considered good for perishables.",
    "Mean Absolute Error: desviación promedio en unidades entre la predicción y las ventas reales en la validación retrospectiva.": "Mean Absolute Error: average deviation in units between the prediction and actual sales in the backtest.",
    "Root Mean Squared Error: penaliza cuadráticamente los errores grandes, alertando sobre quiebres imprevistos o picos no detectados.": "Root Mean Squared Error: penalizes large errors quadratically, warning about unexpected stockouts or undetected spikes.",
    "Weighted Mean Absolute Percentage Error: error porcentual ponderado por volumen. Es el estándar de oro en retail porque no se distorsiona con SKUs de baja rotación.": "Weighted Mean Absolute Percentage Error: volume-weighted percentage error. It is the gold standard in retail because low-turnover SKUs don't distort it.",
    "Tiempo total transcurrido en procesar y proyectar todas las series temporales.": "Total time spent processing and projecting all time series.",
    "No hay series con historia suficiente para pronosticar. Carga datos con el ETL o registra ventas primero.": "There are no series with enough history to forecast. Load data with the ETL or record sales first.",

    // ── Reabastecimiento ──
    "Recomendaciones de reabastecimiento": "Replenishment recommendations",
    "Órdenes de compra sugeridas: demanda pronosticada + stock de seguridad − inventario útil − entradas confirmadas. El inventario por vencer no cuenta como útil.": "Suggested purchase orders: forecast demand + safety stock − usable inventory − confirmed inbound. Inventory about to expire does not count as usable.",
    "Generar recomendaciones": "Generate recommendations",
    "Horizonte de la recomendación": "Recommendation horizon",
    "Órdenes pendientes": "Pending orders",
    "Órdenes de compra que el sistema sugiere y esperan la decisión de una persona.": "Purchase orders the system suggests that await a person's decision.",
    "Pendiente": "Pending",
    "Aprobadas": "Approved",
    "Aprobados": "Approved",
    "Ejecutadas": "Executed",
    "Sugeridas": "Suggested",
    "Sugeridos": "Suggested",
    "Listas para ejecutar": "Ready to execute",
    "Aprobar": "Approve",
    "Rechazar": "Reject",
    "aprobar": "approve",
    "rechazar": "reject",
    "Cantidad sugerida": "Suggested quantity",
    "Cantidad a aprobar": "Quantity to approve",
    "Prioridad alta": "High priority",
    "Prioridad media": "Medium priority",
    "Prioridad baja": "Low priority",
    "Alta": "High",
    "Media": "Medium",
    "Baja": "Low",
    "Necesidad neta": "Net need",
    "Punto de reorden": "Reorder point",
    "Stock de seguridad": "Safety stock",
    "Entradas confirmadas": "Confirmed inbound",
    "Días de cobertura": "Days of coverage",
    "Descontado lo que está por vencer": "Excluding what is about to expire",
    "No cubre demanda futura": "Does not cover future demand",
    "Ver el cálculo completo y desglose de variables": "See the full calculation and variable breakdown",
    "La decisión queda registrada con tu usuario y la fecha.": "The decision is recorded with your user and the date.",
    "Advertencias:": "Warnings:",
    "Productos que se acabarían antes del siguiente pedido": "Products that would run out before the next order",
    "Cantidad a ordenar calculada a partir de la necesidad neta y ajustada hacia arriba para cumplir con el MOQ del proveedor.": "Quantity to order calculated from the net need and rounded up to meet the supplier's MOQ.",
    "Colchón de reserva mínimo necesario para absorber variaciones imprevistas en la demanda diaria o retrasos en la entrega del proveedor.": "Minimum reserve buffer needed to absorb unexpected variation in daily demand or supplier delivery delays.",
    "Existencia física que efectivamente alcanzará a venderse antes de su fecha de caducidad.": "Physical stock that will actually sell before its expiration date.",
    "Existencia física total registrada en esta tienda en todos los lotes del producto.": "Total physical stock recorded in this store across all batches of the product.",
    "Fórmula de balance: (Demanda pronosticada + Stock de seguridad) − (Inventario útil + Entradas confirmadas).": "Balance formula: (Forecast demand + Safety stock) − (Usable inventory + Confirmed inbound).",
    "Inventario físico disponible que sí alcanza a venderse antes de vencer (Físico − En riesgo).": "Available physical inventory that will sell before expiring (Physical − At risk).",
    "Minimum Order Quantity: cantidad mínima exigida contractualmente por el proveedor en cada orden de compra.": "Minimum Order Quantity: the minimum quantity the supplier contractually requires on each purchase order.",
    "Tiempo de entrega del proveedor en días: lapso transcurrido desde que se aprueba la orden hasta que la mercancía física está disponible.": "Supplier lead time in days: the time from when the order is approved until the physical goods are available.",
    "Unidades cuya caducidad llegará antes de poder venderse. Se excluyen del inventario útil para no generar faltantes.": "Units that will expire before they can be sold. They are excluded from usable inventory to avoid stockouts.",
    "Unidades proyectadas a vender durante la ventana de cobertura según el modelo de pronóstico vigente o la media móvil histórica.": "Units projected to sell during the coverage window according to the current forecast model or the historical moving average.",
    "Unidades que caducarán antes de que la velocidad de venta estimada pueda consumirlas. Se descartan del inventario útil.": "Units that will expire before the estimated sales velocity can consume them. They are excluded from usable inventory.",
    "Órdenes de compra ya autorizadas o manifiestos ASN en tránsito hacia la tienda que aún no han sido recibidos en el muelle.": "Purchase orders already approved or ASN manifests in transit to the store that have not yet been received at the dock.",
    "Sobreinventario detectado (0)": "Overstock detected (0)",
    "Ninguna combinación de producto y tienda supera el umbral de cobertura.": "No product and store combination exceeds the coverage threshold.",

    // ── Transferencias ──
    "Transferencias entre tiendas": "Transfers between stores",
    "Transferencias sugeridas": "Suggested transfers",
    "Sugerencias para mover producto de una tienda donde sobra y está por vencer a otra donde se puede vender a tiempo.": "Suggestions to move product from a store where it is in excess and about to expire to another where it can be sold in time.",
    "Mover producto por vencer de una tienda donde sobra a otra donde sí se vende.": "Move product about to expire from a store with excess to one where it does sell.",
    "Detectar oportunidades": "Detect opportunities",
    "Pulsa «Detectar oportunidades»: el motor compara cada tienda con exceso de producto por vencer contra las tiendas con faltante proyectado.": "Press «Detect opportunities»: the engine compares each store with excess product about to expire against stores with a projected shortage.",
    "No hay transferencias en este estado": "No transfers in this status",
    "Una transferencia en estado": "A transfer in status",
    "aún no mueve inventario. Debe pulsar": "does not move inventory yet. You must press",
    "«Ejecutar y mover inventario»": "«Execute and move inventory»",
    "en la pantalla de transferencias para que se descuente del origen, ingrese al destino y se registre la intervención aquí.": "on the transfers screen so it is deducted from the origin, received at the destination and the intervention is recorded here.",
    "Unidades movidas": "Units moved",
    "Diagnóstico": "Diagnosis",

    // ── Descuentos ──
    "Descuentos para lotes por vencer": "Discounts for batches about to expire",
    "Descuentos sugeridos para lotes que están por vencer. Apruébalos o recházalos para acelerar su venta antes de que se conviertan en merma.": "Suggested discounts for batches about to expire. Approve or reject them to speed up their sale before they become shrinkage.",
    "Generar sugerencias": "Generate suggestions",
    "No hay descuentos en este estado. Genera sugerencias para ver los lotes en vigilancia o crítico.": "No discounts in this status. Generate suggestions to see batches on watch or critical.",
    "Descuento": "Discount",
    "Descuentos (0)": "Discounts (0)",
    "% del valor": "% of value",
    "Unidades en promoción": "Units on promotion",
    "Unidades en riesgo crítico": "Units at critical risk",
    "Unidades en vigilancia": "Units on watch",
    "Ingreso potencial": "Potential revenue",
    "Si se vende todo lo descontado": "If everything discounted sells",
    "Valor estimado pendiente": "Estimated pending value",

    // ── Desperdicio evitado y sostenibilidad ──
    "Medición del desperdicio evitado": "Waste avoided measurement",
    "Cuando una intervención rescata producto, se registra cuánto se recuperó realmente y cómo se calculó: unidades en riesgo, unidades intervenidas y unidades efectivamente vendidas antes de caducar.": "When an intervention rescues product, the system records how much was actually recovered and how it was calculated: units at risk, units intervened and units actually sold before expiring.",
    "Recalcular con las ventas reales": "Recalculate with actual sales",
    "Recalcula las 0 intervenciones contra las ventas registradas.": "Recalculates the 0 interventions against recorded sales.",
    "Intervenciones registradas": "Interventions recorded",
    "Todavía no hay intervenciones registradas. Ejecuta una transferencia aprobada para generar el primer registro.": "There are no interventions recorded yet. Execute an approved transfer to create the first record.",
    "Intervenido": "Intervened",
    "Recuperado": "Recovered",
    "Valor recuperado": "Value recovered",
    "valor recuperado": "value recovered",
    "Unidades recuperadas": "Units recovered",
    "unidades recuperadas": "units recovered",
    "Unidades intervenidas": "Units intervened",
    "Unidades mermadas igualmente": "Units lost anyway",
    "Unidades rescatadas por intervenciones": "Units rescued by interventions",
    "Riesgo estimado inicial": "Initial estimated risk",
    "Tasa de recuperación": "Recovery rate",
    "Tasa de aprovechamiento": "Utilization rate",
    "Recuperado sobre recuperado + mermado": "Recovered over recovered + lost",
    "Merma residual del mismo lote y periodo": "Residual shrinkage of the same batch and period",
    "Vendidas antes de caducar gracias a una intervención": "Sold before expiring thanks to an intervention",
    "Ingreso acumulado": "Accumulated revenue",
    "Valor económico rescatado": "Economic value rescued",
    "Ahorro": "Savings",
    "Metodología de medición real y auditoría:": "Real measurement and audit methodology:",
    "se calculan contra los tickets de venta reales del lote en la tienda destino entre la fecha de ejecución y la fecha de caducidad. Si el destino aún no vende el producto, el valor recuperado permanece en cero hasta que se registre la venta.": "are calculated against the batch's actual sales tickets in the destination store between the execution date and the expiration date. If the destination has not sold the product yet, the value recovered stays at zero until the sale is recorded.",
    "Unidades del lote que iban a vencer sin intervención: existencia menos la demanda esperada antes de la caducidad.": "Units of the batch that would have expired without intervention: stock minus the demand expected before expiration.",
    "Transferencia aprobada y ejecutada, o descuento aprobado. Siempre pasa por una decisión humana registrada.": "Approved and executed transfer, or approved discount. It always goes through a recorded human decision.",
    "Ventas reales de ese lote en la tienda destino entre la ejecución y la caducidad. Se limita a lo intervenido.": "Actual sales of that batch in the destination store between execution and expiration. Capped at what was intervened.",
    "Unidades de ese mismo lote dadas de baja en el destino dentro del mismo intervalo. Es lo que no se alcanzó a rescatar.": "Units of that same batch written off at the destination within the same interval. It is what could not be rescued.",
    "Cualquier unidad del lote intervenido que venza sin venderse se computa como merma residual para reflejar la eficiencia neta.": "Any unit of the intervened batch that expires unsold counts as residual shrinkage to reflect net efficiency.",
    "Unidades que se vendieron gracias a una intervención (descuento o transferencia) antes de su fecha de caducidad.": "Units that sold thanks to an intervention (discount or transfer) before their expiration date.",
    "Ingreso por ventas de lotes que estaban en riesgo de merma y se vendieron antes de caducar, medido en la tienda destino después de la intervención.": "Revenue from sales of batches that were at risk of shrinkage and sold before expiring, measured in the destination store after the intervention.",
    "Producto que iba a perderse y se vendió antes de caducar · valor $0.00": "Product that was going to be lost and sold before expiring · value $0.00",
    "El alimento que no se desperdicia no genera emisiones. Estas cifras traducen el producto rescatado a impacto ambiental, con la equivalencia declarada para que se pueda revisar.": "Food that is not wasted does not generate emissions. These figures translate the rescued product into environmental impact, with the equivalence stated so it can be reviewed.",
    "CO₂e evitado": "CO₂e avoided",
    "Alimento recuperado": "Food recovered",
    "Equivalencia declarada abajo": "Equivalence stated below",
    "Metodología de las equivalencias": "Equivalence methodology",
    "el factor de 2.5 kg CO₂e por kg de alimento desperdiciado es una referencia de la FAO y se aplica de forma uniforme a todas las categorías. Es una aproximación: no distingue entre un kilo de carne y un kilo de arroz. Se declara para que el número sea interpretable, no para presentarlo como una medición de laboratorio.": "the factor of 2.5 kg CO₂e per kg of wasted food is an FAO reference and is applied uniformly to all categories. It is an approximation: it does not distinguish between a kilo of meat and a kilo of rice. It is stated so the number can be interpreted, not to present it as a laboratory measurement.",
    "Unidades recuperadas mediante transferencias y descuentos aprobados, medidas como ventas reales del lote antes de su caducidad. La equivalencia de CO2e usa 2.5 kg CO2e por kg de alimento (referencia FAO).": "Units recovered through approved transfers and discounts, measured as actual sales of the batch before its expiration. The CO2e equivalence uses 2.5 kg CO2e per kg of food (FAO reference).",
    "Calculado por el microservicio de alertas y sostenibilidad.": "Calculated by the alerts and sustainability microservice.",
    "Elige un tema para ver sus cifras completas.": "Pick a topic to see its full figures.",
    "Reporte ESG de svc-alerts": "ESG report from svc-alerts",
    "Reporte ESG · svc-alerts": "ESG report · svc-alerts",

    // ── Usuarios ──
    "Usuarios del sistema, su rol, su tienda y si están activos.": "System users, their role, their store and whether they are active.",
    "Perfiles del sistema": "System profiles",
    "Roles definidos en la base de datos": "Roles defined in the database",
    "El menú lateral se arma con los permisos del rol: cada perfil ve únicamente las pantallas que le corresponden.": "The sidebar is built from the role's permissions: each profile only sees the screens that belong to it.",
    "Usuario": "User",
    "Rol": "Role",
    "Rol *": "Role *",
    "Último acceso": "Last login",
    "Intentos fallidos": "Failed attempts",
    "Crear usuario": "Create user",
    "Contraseña * (mínimo 8 caracteres)": "Password * (at least 8 characters)",
    "Nueva contraseña (mínimo 8 caracteres)": "New password (at least 8 characters)",
    "La contraseña se guarda cifrada; nadie puede verla después.": "The password is stored encrypted; nobody can see it afterwards.",
    "Restablecer contraseña": "Reset password",
    "Cambiar y revocar sesiones": "Change and revoke sessions",
    "Al cambiar la contraseña se revocan todas las sesiones abiertas del usuario.": "Changing the password revokes all of the user's open sessions.",
    "Contraseña restablecida y sesiones revocadas.": "Password reset and sessions revoked.",
    "Usuario actualizado.": "User updated.",

    // ── Bitácora ──
    "Historial de operaciones: quién hizo qué, cuándo y sobre qué registro, con los valores antes y después del cambio.": "Operations history: who did what, when and on which record, with the values before and after the change.",
    "Descripción, acción o tabla": "Description, action or table",
    "Eventos registrados": "Events recorded",
    "Tipos con actividad": "Types with activity",
    "De los 7 tipos definidos": "Of the 7 defined types",
    "Tipos de acción distintos": "Distinct action types",
    "Transacciones registradas": "Transactions recorded",
    "Responsable": "Responsible",
    "Tabla": "Table",
    "Tabla de origen": "Source table",
    "Estado anterior": "Previous state",
    "Estado nuevo": "New state",
    "Cambio": "Change",
    "Decisión": "Decision",
    "El cambio queda registrado en la bitácora de auditoría.": "The change is recorded in the audit log.",
    "Inicio de sesión correcto como Administrador": "Successful login as Administrator",

    // ── Configuración ──
    "Configuración del sistema": "System settings",
    "Parámetros y umbrales que usan las alertas, el pronóstico y el reabastecimiento. Los cambios aplican de inmediato.": "Parameters and thresholds used by alerts, forecasting and replenishment. Changes apply immediately.",
    "Guardar parámetros": "Save parameters",
    "Parámetros guardados en analitica.configuracion.": "Parameters saved in analitica.configuracion.",
    "Usar el configurado": "Use the configured one",
    "Descuento sugerido para lotes en estado CRÍTICO": "Suggested discount for batches in CRITICAL state",
    "Descuento sugerido para lotes en estado VIGILANCIA": "Suggested discount for batches in WATCH state",
    "Días de cobertura por encima de los cuales hay sobreinventario": "Days of coverage above which there is overstock",
    "Días de demanda que debe cubrir el stock de seguridad": "Days of demand the safety stock must cover",
    "Días de historia usados por la media móvil": "Days of history used by the moving average",
    "Factor de suavización exponencial (0-1)": "Exponential smoothing factor (0-1)",
    "Horas de vigencia del token JWT": "JWT token validity in hours",
    "Horizonte con el que se estima el riesgo de desperdicio por lote": "Horizon used to estimate waste risk per batch",
    "Horizonte por defecto del pronóstico en días": "Default forecast horizon in days",
    "Intentos fallidos antes de bloquear temporalmente la cuenta": "Failed attempts before temporarily locking the account",
    "Método de pronóstico por defecto": "Default forecasting method",
    "Mínimo de días con ventas para pronosticar una serie": "Minimum days with sales to forecast a series",
    "Actualizado": "Updated",

    // ── Microservicios y MongoDB ──
    "Estado del sistema": "System status",
    "Estado en vivo de los 8 servicios y de sus bases de datos. Desde aquí puedes abrir la documentación Swagger de cada uno para probar sus endpoints.": "Live status of the 8 services and their databases. From here you can open each one's Swagger docs to try its endpoints.",
    "Servicios": "Services",
    "Servicios en línea": "Services online",
    "Responden /health con todas sus dependencias": "Respond to /health with all their dependencies",
    "Servicio": "Service",
    "Responsabilidad": "Responsibility",
    "En línea": "Online",
    "Latencia": "Latency",
    "Respuesta en": "Response in",
    "Probar los microservicios desde la web": "Try the microservices from the web",
    "Cada botón hace una petición real desde tu navegador a": "Each button makes a real request from your browser to",
    "; la web la reenvía al contenedor con tu token. Ábrelo con F12 → Red para ver las peticiones.": "; the web forwards it to the container with your token. Open F12 → Network to see the requests.",
    "Elige una consulta.": "Pick a query.",
    "Tu sesión en svc-auth": "Your session in svc-auth",
    "Mi sesión · svc-auth": "My session · svc-auth",
    "Productos · svc-catalog": "Products · svc-catalog",
    "Lotes por vencer · svc-inventory": "Batches about to expire · svc-inventory",
    "Últimas ventas · svc-commercial": "Latest sales · svc-commercial",
    "Avisos ASN · svc-asn": "ASN notices · svc-asn",
    "Órdenes · svc-planning": "Orders · svc-planning",
    "Bitácora · svc-audit": "Audit log · svc-audit",
    "Login, JWT, sesiones y revocación": "Login, JWT, sessions and revocation",
    "Existencias, cola FEFO y reservas": "Stock, FEFO queue and reservations",
    "Ventas POS (Saga), carritos y mermas": "POS sales (Saga), carts and shrinkage",
    "Avisos de embarque (ASN) en JSON/XML": "Advance shipping notices (ASN) in JSON/XML",
    "Alertas pre-merma y ESG": "Pre-shrinkage alerts and ESG",
    "Alertas Pre-Merma & ESG (5007)": "Pre-Shrinkage Alerts & ESG (5007)",
    "Logística ASN (5005)": "ASN Logistics (5005)",
    "Planeación & Demanda (5006)": "Planning & Demand (5006)",
    "Contadores en Redis": "Counters in Redis",
    "Contadores de operación (Redis)": "Operation counters (Redis)",
    "Operaciones registradas hoy por los servicios": "Operations recorded today by the services",
    "Microservicios Desacoplados y Documentación Interactiva (Swagger UI)": "Decoupled Microservices and Interactive Documentation (Swagger UI)",
    "Swagger UI ›": "Swagger UI ›",
    "Almacén Documental & Agregaciones MongoDB": "Document Store & MongoDB Aggregations",
    "Pronósticos, avisos de embarque (ASN) de proveedores y alertas operativas almacenados como documentos, con sus análisis agregados.": "Forecasts, supplier advance shipping notices (ASN) and operational alerts stored as documents, with their aggregated analysis.",
    "Persistencia Políglota": "Polyglot Persistence",
    "Estado MongoDB": "MongoDB status",
    "Colección": "Collection",
    "Propósito Arquitectónico": "Architectural Purpose",
    "Series temporales y percentiles": "Time series and percentiles",
    "Percentiles P10/P50/P90 y cruce relacional.": "P10/P50/P90 percentiles and relational join.",
    "Manifiestos con carga anidada": "Manifests with nested cargo",
    "Manifiestos XML/JSON y evidencias $push.": "XML/JSON manifests and $push evidence.",
    "Alertas TTL": "TTL alerts",
    "Alertas operativas con TTL y CO2e evitado.": "Operational alerts with TTL and CO2e avoided.",
    "Retención automática 180 días": "Automatic 180-day retention",
    "Índices Activos & Políticas de Almacenamiento": "Active Indexes & Storage Policies",
    "Índices Registrados": "Registered Indexes",
    "Índice TTL": "TTL index",
    "Índice compuesto": "Compound index",
    "Garantiza unicidad de folio (": "Guarantees folio uniqueness (",
    ") y optimiza búsquedas por proveedor y estado.": ") and optimizes lookups by supplier and status.",
    "para recuperación en O(log N).": "for O(log N) retrieval.",
    "purga alertas solas a los 180 días sin degradar PostgreSQL.": "purges alerts on its own after 180 days without degrading PostgreSQL.",
    "Los microservicios de FreshTrack exponen estas colecciones mediante endpoints REST con negociación dual JSON/XML:": "FreshTrack microservices expose these collections through REST endpoints with dual JSON/XML negotiation:",
    "Pipeline 1: Analítica de Alertas Operativas por Sucursal ($match + $group + $project + $sort)": "Pipeline 1: Operational Alerts Analytics by Branch ($match + $group + $project + $sort)",
    "Pipeline 2: Consolidación de Carga ASN por Proveedor y SKU ($unwind + $group + $project + $sort)": "Pipeline 2: ASN Cargo Consolidation by Supplier and SKU ($unwind + $group + $project + $sort)",
    "Pipeline 3: Rendimiento Algorítmico de Pronósticos ($group + $project + $sort)": "Pipeline 3: Forecast Algorithm Performance ($group + $project + $sort)",
    "Filtra alertas abiertas, las agrupa por": "Filters open alerts, groups them by",
    ", acumulando el total y calculando el promedio de días restantes antes de merma.": ", accumulating the total and calculating the average days left before shrinkage.",
    "Desenrolla el arreglo embebido": "Unwinds the embedded array",
    ", agrupando por": ", grouping by",
    "para totalizar piezas declaradas y despachos asociados.": "to total declared pieces and associated dispatches.",
    "Consolida las métricas de error (MAE y RMSE) calculadas en las corridas inmutables agrupadas por modelo estadístico.": "Consolidates the error metrics (MAE and RMSE) calculated in the immutable runs grouped by statistical model.",
    "Promedio Días a Caducidad": "Average Days to Expiration",
    "Piezas Totales Declaradas": "Total Declared Pieces",
    "Despachos Asociados": "Associated Dispatches",
    "Modelo Algorítmico": "Algorithmic Model",
    "MAE Promedio": "Average MAE",
    "RMSE Promedio": "Average RMSE",
    "Total Corridas Inmutables": "Total Immutable Runs",
    "Locación (FK Lógica)": "Location (Logical FK)",
    "Proveedor (FK Lógica)": "Supplier (Logical FK)",
    "SKU (FK Lógica)": "SKU (Logical FK)",
    "Criticidad": "Criticality",
    "Métrica": "Metric",
    "Qué significa": "What it means",
    "Cómo se calcula": "How it is calculated",
    "SKU en piso": "SKUs on the floor",
    "Productos / ubicaciones": "Products / locations",
    "Vigencia": "Validity",
    "Completado": "Completed",
    "Catálogo de productos": "Product catalog",
    "Parámetros del sistema": "System parameters",
    "Mermas recientes": "Recent shrinkage",
    "Sobreinventario detectado": "Overstock detected",
    "Movimientos de venta": "Sales movements",
    "vida útil": "shelf life",
    "1. Ejecución física requerida:": "1. Physical execution required:",
    "2. Medición por venta real:": "2. Measurement by actual sale:",
    "1. Riesgo estimado inicial": "1. Initial estimated risk",
    "2. Intervención": "2. Intervention",
    "3. Recuperado": "3. Recovered",
    "4. Merma residual": "4. Residual shrinkage",
    "2.5 kg CO₂e por kg de alimento (FAO)": "2.5 kg CO₂e per kg of food (FAO)",
    "Las": "The",
    "y el": "and the",
    "(vencido)": "(expired)",
    "(en curso)": "(in progress)",
    "Altas": "High",
    "3. Merma residual:": "3. Residual shrinkage:",
    "Avisos ASN": "ASN notices",
    "KPIs Modelos ›": "Model KPIs ›",
    "Pipeline API ›": "API pipeline ›",
    "Pipeline Alertas ›": "Alerts pipeline ›",
    "Detalle del cálculo": "Calculation details",
    "Marcar atendida": "Mark as handled",
    // Claves del desglose de cada alerta (vienen de la base con «_» cambiado por espacio)
    "cantidad": "quantity", "cantidad sugerida": "suggested quantity", "clasificacion": "classification",
    "demanda antes caducidad": "demand before expiration", "demanda diaria": "daily demand",
    "destino": "destination", "dias cobertura": "days of coverage", "dias para vencer": "days to expire",
    "dias restantes": "days left", "existencia": "stock", "id orden": "order id",
    "id transferencia": "transfer id", "inventario util": "usable inventory", "lead time dias": "lead time days",
    "necesidad neta": "net need", "origen": "origin", "prioridad": "priority",
    "unidades en riesgo": "units at risk", "valor": "value", "valor en riesgo": "value at risk",
    "vida util pct": "shelf life pct",

    // Lo que sigue a una cifra («154.68 unidades …»): ver la regla de cifra + texto.
    "unidades": "units",
    "unidades vencen en 2 días o menos": "units expire in 2 days or less",
    "unidades cerca de su fecha límite": "units close to their expiration date",
    "unidades en existencia hoy": "units in stock today",
    "en existencia hoy": "in stock today",
    "ya aprobadas": "already approved",
    "ya ejecutadas": "already executed",
    "lotes con existencia vigente": "batches with current stock",
    "ubicaciones registradas": "locations registered",
    "registros": "records",
    "por página": "per page",
    "kg": "kg",
  };

  // Palabras sueltas que aparecen dentro de textos con datos (enums, unidades,
  // categorías). Se usan desde las reglas, no para el texto completo.
  const PALABRAS = {
    // Unidades de medida
    "Pieza": "Piece", "Piezas": "Pieces", "Kg": "Kg", "Kilogramo": "Kilogram", "Litro": "Liter",
    "Paquete": "Package", "Caja": "Box", "Bolsa": "Bag", "Gramo": "Gram", "Unidad": "Unit",
    // Categorías
    "Lácteos": "Dairy", "Carnes": "Meat", "Frutas": "Fruit", "Verduras": "Vegetables",
    "Panadería": "Bakery", "Abarrotes": "Groceries",
    // Tipos de locación y estados
    "Tienda": "Store", "CEDIS": "DC",
    "PENDIENTE": "PENDING", "APROBADA": "APPROVED", "APROBADO": "APPROVED", "RECHAZADA": "REJECTED",
    "RECHAZADO": "REJECTED", "EJECUTADA": "EXECUTED", "CANCELADA": "CANCELED", "SUGERIDA": "SUGGESTED",
    "SUGERIDO": "SUGGESTED", "ABIERTA": "OPEN", "ATENDIDA": "HANDLED", "DESCARTADA": "DISMISSED",
    "NORMAL": "NORMAL", "VIGILANCIA": "WATCH", "CRÍTICO": "CRITICAL", "VENCIDO": "EXPIRED",
    "ALTA": "HIGH", "MEDIA": "MEDIUM", "BAJA": "LOW", "COMPLETADA": "COMPLETED", "COMPLETADO": "COMPLETED",
    "PARCIAL": "PARTIAL", "ACTIVO": "ACTIVE", "INACTIVO": "INACTIVE",
    "Aprobado": "Approved", "Rechazado": "Rejected", "aprobada": "approved", "rechazada": "rejected",
    "ejecutada": "executed",
    "Activo": "Active", "Inactivo": "Inactive", "Activa": "Active", "Inactiva": "Inactive",
    "Pendiente": "Pending", "Aprobada": "Approved", "Rechazada": "Rejected", "Ejecutada": "Executed",
    "Cancelada": "Canceled", "Sugerida": "Suggested", "Abierta": "Open", "Atendida": "Handled",
    "Caducidad": "Expiration", "Daño": "Damage", "Calidad": "Quality", "Manipulación": "Handling",
    "Devolución": "Return", "Otra": "Other", "Cadena de frío": "Cold chain",
    "CADUCIDAD": "EXPIRATION", "DANO": "DAMAGE", "DAÑO": "DAMAGE", "CALIDAD": "QUALITY",
    "CADENA_DE_FRIO": "COLD_CHAIN", "MANIPULACION": "HANDLING", "DEVOLUCION": "RETURN", "OTRA": "OTHER",
    "TIENDA": "STORE", "ONLINE": "ONLINE",
    "vencido": "expired", "en curso": "in progress", "inactivo": "inactive",
    "abierta": "open", "atendida": "handled", "descartada": "dismissed",
    "SUAVIZACION_EXPONENCIAL": "EXPONENTIAL_SMOOTHING", "MEDIA_MOVIL": "MOVING_AVERAGE",
    "MEDIA_MOVIL_PONDERADA": "WEIGHTED_MOVING_AVERAGE",
    "Suavización exponencial": "Exponential smoothing", "Media móvil": "Moving average",
    "Media móvil ponderada": "Weighted moving average",
    "LOTE_POR_VENCER": "BATCH_ABOUT_TO_EXPIRE", "LOTE_VENCIDO": "BATCH_EXPIRED",
    "RIESGO_DE_MERMA": "SHRINKAGE_RISK", "SOBREINVENTARIO": "OVERSTOCK", "RIESGO_DE_FALTANTE": "STOCKOUT_RISK",
    "REABASTECIMIENTO_REQUERIDO": "REPLENISHMENT_REQUIRED", "TRANSFERENCIA_SUGERIDA": "TRANSFER_SUGGESTED",
  };

  const MESES = { ene: "Jan", feb: "Feb", mar: "Mar", abr: "Apr", may: "May", jun: "Jun",
    jul: "Jul", ago: "Aug", sep: "Sep", oct: "Oct", nov: "Nov", dic: "Dec" };

  const p = (w) => PALABRAS[w] || DICCIONARIO[w] || w;
  const unidad = (u) => PALABRAS[u] || u;
  const dias = (n) => (n === "1" ? "1 day" : `${n} days`);

  // Textos que arma el servidor con datos. Orden: de lo más específico a lo general.
  const N = "(-?[\\d.,]+)";
  const REGLAS = [
    // Fechas: «23 oct 2026», «23 oct 2026, 14:20»
    [new RegExp("^(\\d{1,2}) (ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\\.? (\\d{4})(.*)$"),
      (m, d, mes, a, resto) => `${MESES[mes]} ${d}, ${a}${resto.replace("(vencido)", "(expired)")}`],
    // Cantidades con unidad: «22.02 Kg», «290.94 Pieza»
    [new RegExp(`^${N} ([A-Za-zÁ-ú]+)$`), (m, n, u) => (PALABRAS[u] ? `${n} ${unidad(u)}` : null)],
    [/^en (\d+) días?$/, (m, n) => `in ${dias(n)}`],
    [/^hace (\d+) días?$/, (m, n) => `${dias(n)} ago`],
    [/^lote (.+)$/, (m, c) => `batch ${c}`],
    [/^Locación #(\d+)$/, (m, n) => `Location #${n}`],
    [/^Proveedor #(\d+)$/, (m, n) => `Supplier #${n}`],
    [/^lead time (\d+) d$/, (m, n) => `lead time ${n} d`],
    [/^vida útil (\d+) d$/, (m, n) => `shelf life ${n} d`],
    [/^vence (.+?)( \(vencido\))?$/, (m, f, v) => `expires ${tr(f)}${v ? " (expired)" : ""}`],
    [/^\(vencido\)$/, () => "(expired)"],
    [/^Rol (\S+) · expira en (\d+) min$/, (m, r, n) => `Role ${r} · expires in ${n} min`],
    [/^Solicitó: (.+)\.$/, (m, u) => `Requested by: ${u}.`],
    [/^Ejecutada el (.+?) por (.+?) · (\d+) series · horizonte (\d+) días$/,
      (m, f, u, s, h) => `Run on ${tr(f)} by ${u} · ${s} series · ${dias(h)} horizon`],
    [/^Horizonte de (\d+) días · (\d+) puntos comparados · calculado el (.+)$/,
      (m, h, n, f) => `${dias(h)} horizon · ${n} points compared · calculated on ${tr(f)}`],
    [/^Demanda pronosticada \(horizonte de (\d+) d\)$/, (m, n) => `Forecast demand (${n} d horizon)`],
    [/^Total horizonte \((\d+) d\)$/, (m, n) => `Horizon total (${n} d)`],
    [/^Pronóstico por producto y tienda \((\d+) series\)$/, (m, n) => `Forecast by product and store (${n} series)`],
    [/^Última corrida — (.+)$/, (m, x) => `Latest run — ${p(x)}`],
    [/^Eventos \((\d+) en esta página\)$/, (m, n) => `Events (${n} on this page)`],
    [/^(\d+) líneas$/, (m, n) => `${n} lines`],
    [/^Recalcula las (\d+) intervenciones contra las ventas registradas\.$/, (m, n) => `Recalculates the ${n} interventions against recorded sales.`],
    [/^Inicio de sesión correcto como (.+)$/, (m, r) => `Successful login as ${tr(r)}`],
    [/^Venta (\S+) por (\S+) procesada exitosamente vía Saga en locación (\d+)\.$/,
      (m, f, t, l) => `Sale ${f} for ${t} processed successfully via Saga at location ${l}.`],
    [/^(INSERT|UPDATE|DELETE) sobre (.+)$/, (m, op, t) => `${op} on ${t}`],
    [/^Producto que iba a perderse y se vendió antes de caducar · valor (.+)$/,
      (m, v) => `Product that was going to be lost and sold before expiring · value ${v}`],
    [/^(.+) de (.+) unidades recibidas \((.+)\)$/, (m, a, b, per) => `${a} of ${b} units received (${tr(per.charAt(0).toUpperCase() + per.slice(1)).toLowerCase()})`],
    [/^De lo recibido en (.+)$/, (m, per) => `Of what was received in the ${tr(per.charAt(0).toUpperCase() + per.slice(1)).toLowerCase()}`],
    [new RegExp(`^${N} registros de merma$`), (m, n) => `${n} shrinkage records`],
    [new RegExp(`^${N} unidades perdidas$`), (m, n) => `${n} units lost`],
    [new RegExp(`^${N} unidades vendidas$`), (m, n) => `${n} units sold`],
    [/^Error de red: (.*)$/, (m, e) => `Network error: ${e}`],
    // Etiquetas de mes en las gráficas: «oct 2026», «oct 2026 (en curso)»
    [/^(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic) (\d{4})( \(en curso\))?$/,
      (m, mes, a, c) => `${MESES[mes]} ${a}${c ? " (in progress)" : ""}`],
    [new RegExp(`^${N} días$`), (m, n) => dias(n)],
    [new RegExp(`^lead time ${N} días$`), (m, n) => `lead time ${dias(n)}`],
    [new RegExp(`^${N} críticas y ${N} altas$`), (m, c, a) => `${c} critical and ${a} high`],
    [new RegExp(`^${N} lotes en ${N} ubicaciones$`), (m, l, u) => `${l} batches in ${u} locations`],
    [new RegExp(`^${N} unidades mermadas de ${N} recibidas\\.$`), (m, a, b) => `${a} units lost out of ${b} received.`],
    [/^(\d+) aviso\(s\)$/, (m, n) => `${n} notice(s)`],
    [/^página (\d+) de (\d+)$/, (m, a, b) => `page ${a} of ${b}`],
    [/^(\d+) de (\d+)$/, (m, a, b) => `${a} of ${b}`],
    [/^creada el (.+)$/, (m, f) => `created on ${tr(f)}`],
    [/^Generada el (.+?)(?: · (.+))?$/, (m, f, e) => `Generated on ${tr(f)}${e ? ` · ${tr(e)}` : ""}`],
    [/^Alertas recalculadas desde PostgreSQL: (\d+) reglas aplicadas, (\d+) cerradas por dejar de aplicar, (\d+) abiertas en total\.$/,
      (m, a, c, t) => `Alerts recalculated from PostgreSQL: ${a} rules applied, ${c} closed because they no longer apply, ${t} open in total.`],
    [/^(\S+) en puerto (\d+)$/, (m, db, n) => `${db} on port ${n}`],
    // Cifra seguida de un texto conocido: «154.68 unidades cerca de su fecha límite»
    [/^([$\d][\d.,]*%?) (.+)$/, (m, n, resto) => {
      const t = tr(resto);
      return t !== resto ? `${n} ${t}` : null;
    }],

    // Explicaciones de reabastecimiento (cada línea del bloque <pre>)
    [/^Producto: (.+)$/, (m, x) => `Product: ${x}`],
    [/^Tienda: (.+)$/, (m, x) => `Store: ${x}`],
    [/^Demanda prevista (\d+) días(\s+)(\S+)$/, (m, h, s, v) => `Forecast demand ${h} days${s}${v}`],
    [/^Inventario físico(\s+)(\S+)$/, (m, s, v) => `Physical inventory${s}${v}`],
    [/^Inventario próximo a vencer(\s+)(\S+)$/, (m, s, v) => `Inventory about to expire${s}${v}`],
    [/^Inventario útil(\s+)(\S+)$/, (m, s, v) => `Usable inventory${s}${v}`],
    [/^Stock de seguridad(\s+)(\S+)$/, (m, s, v) => `Safety stock${s}${v}`],
    [/^Entradas confirmadas(\s+)(\S+)$/, (m, s, v) => `Confirmed inbound${s}${v}`],
    [/^Lead time(\s+)(\S+) días$/, (m, s, v) => `Lead time${s}${v} days`],
    [/^Necesidad neta(\s+)(\S+)$/, (m, s, v) => `Net need${s}${v}`],
    [/^Recomendación: ordenar (\S+) (.+)$/, (m, n, u) => `Recommendation: order ${n} ${unidad(u)}`],
    [/^Recomendación: no ordenar\. El inventario útil cubre la demanda\.$/, () => "Recommendation: do not order. Usable inventory covers demand."],
    [/^· (.+)$/, (m, x) => `· ${tr(x)}`],
    [new RegExp(`^El inventario útil cubre ${N} días y el proveedor tarda ${N} días en surtir: hay riesgo de faltante si no se pide ahora\\.$`),
      (m, c, l) => `Usable inventory covers ${c} days and the supplier takes ${l} days to deliver: there is a stockout risk if you don't order now.`],
    [new RegExp(`^El proveedor tiene un pedido mínimo \\(MOQ\\) de ${N} unidades y la necesidad calculada es de ${N}\\. Se sugiere comprar ${N}, es decir ${N} unidades por encima de lo necesario\\.$`),
      (m, q, n, c, d) => `The supplier has a minimum order (MOQ) of ${q} units and the calculated need is ${n}. Buying ${c} is suggested, that is ${d} units more than needed.`],
    [new RegExp(`^Riesgo de vencimiento: con ${N} unidades se tardarían ${N} días en venderse, pero el producto dura ${N} días\\. Parte del pedido podría caducar\\.$`),
      (m, u, d, v) => `Expiration risk: with ${u} units it would take ${d} days to sell, but the product lasts ${v} days. Part of the order could expire.`],
    [new RegExp(`^${N} unidades del inventario actual están en riesgo de vencer antes de poder venderse; no se contaron como inventario útil\\.$`),
      (m, n) => `${n} units of current inventory are at risk of expiring before they can be sold; they were not counted as usable inventory.`],
    [new RegExp(`^Sobreinventario: hay ${N} unidades útiles, suficientes para ${N} días de demanda \\(el umbral es ${N} días\\)\\. No conviene pedir más\\.$`),
      (m, u, c, t) => `Overstock: there are ${u} usable units, enough for ${c} days of demand (the threshold is ${t} days). Ordering more is not advisable.`],
    [new RegExp(`^Advertencia: si se compran ${N} unidades, la cobertura subiría a ${N} días \\(umbral de sobreinventario: ${N} días\\)\\. Revisa si conviene ajustar la cantidad\\.$`),
      (m, u, c, t) => `Warning: if ${u} units are bought, coverage would rise to ${c} days (overstock threshold: ${t} days). Check whether to adjust the quantity.`],

    // Mensajes de alertas
    [new RegExp(`^El lote (\\S+) de (.+) venció hace ${N} día\\(s\\) y aún tiene ${N} (\\S+) en (.+)\\. Debe darse de baja\\.$`),
      (m, l, pr, d, c, u, loc) => `Batch ${l} of ${pr} expired ${d} day(s) ago and still has ${c} ${unidad(u)} at ${loc}. It must be written off.`],
    [new RegExp(`^El lote (\\S+) de (.+) vence en ${N} día\\(s\\) \\(${N}% de vida útil\\) con ${N} (\\S+) en (.+)\\.$`),
      (m, l, pr, d, pct, c, u, loc) => `Batch ${l} of ${pr} expires in ${d} day(s) (${pct}% of shelf life) with ${c} ${unidad(u)} at ${loc}.`],
    [new RegExp(`^El lote (\\S+) de (.+) vence en ${N} día\\(s\\): de ${N} unidades, solo se esperan vender ${N} antes de que caduque\\. Hay ${N} en riesgo \\((.+) de valor\\)\\.$`),
      (m, l, pr, d, u, v, r, val) => `Batch ${l} of ${pr} expires in ${d} day(s): of ${u} units, only ${v} are expected to sell before it expires. ${r} are at risk (${val} in value).`],
    [new RegExp(`^(.+) en (.+): ${N} unidades útiles cubren ${N} días de demanda \\(umbral ${N} días\\)\\. El producto dura ${N} días: hay riesgo de que parte se venza\\.$`),
      (m, pr, loc, u, c, t, v) => `${pr} at ${loc}: ${u} usable units cover ${c} days of demand (threshold ${t} days). The product lasts ${v} days: part of it may expire.`],
    [new RegExp(`^(.+) en (.+): el inventario útil cubre ${N} días, pero el proveedor tarda ${N} días en surtir\\. Riesgo de quedarse sin producto\\.$`),
      (m, pr, loc, c, l) => `${pr} at ${loc}: usable inventory covers ${c} days, but the supplier takes ${l} days to deliver. Risk of running out of product.`],
    [new RegExp(`^Hay una orden pendiente de aprobar: ${N} (\\S+) de (.+) para (.+) \\(prioridad (\\S+)\\)\\.$`),
      (m, c, u, pr, loc, pri) => `There is an order pending approval: ${c} ${unidad(u)} of ${pr} for ${loc} (${p(pri).toLowerCase()} priority).`],
    [new RegExp(`^Transferencia sugerida: (.+) → (.+) · ${N} (\\S+) de (.+) \\(lote (\\S+), vence en ${N} días\\)\\.?$`),
      (m, o, d, c, u, pr, l, v) => `Suggested transfer: ${o} → ${d} · ${c} ${unidad(u)} of ${pr} (batch ${l}, expires in ${v} days).`],
    [new RegExp(`^Descuento sugerido del ${N}% para el lote (\\S+) de (.+) en (.+) \\(${N} (\\S+), vence en ${N} días\\)$`),
      (m, pct, l, pr, loc, c, u, v) => `Suggested ${pct}% discount for batch ${l} of ${pr} at ${loc} (${c} ${unidad(u)}, expires in ${v} days)`],
    [new RegExp(`^(.+) tiene ${N} unidades del lote (\\S+)$`), (m, t, n, l) => `${t} has ${n} units of batch ${l}`],
    [new RegExp(`^(.+) tiene un faltante de ${N} unidades$`), (m, t, n) => `${t} has a shortage of ${n} units`],
    [new RegExp(`^El lote vence en ${N} días y el traslado toma ${N} día\\(s\\)$`), (m, v, t) => `The batch expires in ${v} days and the transfer takes ${t} day(s)`],
    [new RegExp(`^Con ${N} unidades/día de demanda, (.+) alcanzaría a vender ${N} antes de que el lote venza$`),
      (m, d, t, v) => `With ${d} units/day of demand, ${t} could sell ${v} before the batch expires`],
    [new RegExp(`^(.+) tiene ${N} unidades de exceso útil; (.+) tiene un faltante de ${N} unidades para los próximos ${N} días$`),
      (m, o, e, d, f, h) => `${o} has ${e} units of usable excess; ${d} has a shortage of ${f} units for the next ${h} days`],

    // Mensajes flash con prefijo fijo y motivo variable
    [/^(La venta no se registró|La merma no se registró|La merma NO se registró|No se registró la recepción|El producto no se registró|El producto no cambió|El pronóstico no se ejecutó|La orden no cambió|No se generaron recomendaciones): (.+)$/,
      (m, pre, motivo) => `${{ "La venta no se registró": "The sale was not recorded", "La merma no se registró": "The shrinkage was not recorded",
        "La merma NO se registró": "The shrinkage was NOT recorded", "No se registró la recepción": "The receipt was not recorded",
        "El producto no se registró": "The product was not registered", "El producto no cambió": "The product did not change",
        "El pronóstico no se ejecutó": "The forecast did not run", "La orden no cambió": "The order did not change",
        "No se generaron recomendaciones": "No recommendations were generated" }[pre]}: ${tr(motivo)}`],
    [/^Stock insuficiente para '(.+)' \(disponible: (\S+), solicitado: (\S+)\)\.$/, (m, pr, d, s) => `Insufficient stock for '${pr}' (available: ${d}, requested: ${s}).`],
    [/^Producto SKU (\d+) (activado|desactivado|actualizado)( por svc-catalog)?\.$/,
      (m, s, a, por) => `Product SKU ${s} ${{ activado: "activated", desactivado: "deactivated", actualizado: "updated" }[a]}${por ? " by svc-catalog" : ""}.`],
    [/^Producto «(.+)» dado de alta por svc-catalog \(SKU (\d+)\)\.$/, (m, n, s) => `Product «${n}» created by svc-catalog (SKU ${s}).`],
    [/^Producto «(.+)» registrado en PostgreSQL\.$/, (m, n) => `Product «${n}» registered in PostgreSQL.`],
    [/^«(.+)» registrada en PostgreSQL\.$/, (m, n) => `«${n}» registered in PostgreSQL.`],
    [/^Locación (\d+) (activada|desactivada|actualizada)\.$/, (m, l, a) => `Location ${l} ${{ activada: "activated", desactivada: "deactivated", actualizada: "updated" }[a]}.`],
    [/^Proveedor (\d+) actualizado\.$/, (m, n) => `Supplier ${n} updated.`],
    [/^Descuento (aprobado|rechazado)\.$/, (m, a) => `Discount ${a === "aprobado" ? "approved" : "rejected"}.`],
    [/^La (orden|transferencia) ya está en estado (\S+)\.$/, (m, t, e) => `The ${t === "orden" ? "order" : "transfer"} is already in status ${p(e)}.`],
    [/^El descuento ya está en estado (\S+)\.$/, (m, e) => `The discount is already in status ${p(e)}.`],
    [/^Lote «(.+)» recibido\. Inventario actualizado en PostgreSQL\.$/, (m, l) => `Batch «${l}» received. Inventory updated in PostgreSQL.`],
    [/^Venta (\S+) registrada por (\S+) a través de svc-commercial\. Lotes consumidos \(FEFO\): (.+)\.$/,
      (m, f, t, r) => `Sale ${f} recorded for ${t} through svc-commercial. Batches consumed (FEFO): ${r}.`],
    [/^Venta (\S+) registrada por (\S+)\. FEFO consumió: (.+)\.$/, (m, f, t, r) => `Sale ${f} recorded for ${t}. FEFO consumed: ${r}.`],
    [/^Merma registrada (a través de svc-commercial|en PostgreSQL): (\S+) (\S*) de (.+) \(lote (\S+)\) por (.+?)\. Valor (\S+)\. (?:Quedan (\S+) en existencia|Inventario descontado: quedan (\S+))\.$/,
      (m, via, c, u, pr, l, causa, v, q1, q2) => `Shrinkage recorded ${via === "en PostgreSQL" ? "in PostgreSQL" : "through svc-commercial"}: ${c} ${unidad(u)} of ${pr} (batch ${l}) due to ${tr(causa).toLowerCase()}. Value ${v}. ${q1 != null ? `${q1} left in stock` : `Inventory deducted: ${q2} left`}.`],
    [/^Pronóstico ejecutado(?: por svc-planning)? \((.+?)\): (\d+) series de producto \+ tienda, horizonte (\d+) días\. Error medido — MAE (\S+), RMSE (\S+), WMAPE (\S+)%\.( Corrida guardada con su trazabilidad\.)?$/,
      (m, met, n, h, mae, rmse, w, g) => `Forecast run (${p(met)}): ${n} product + store series, ${dias(h)} horizon. Measured error — MAE ${mae}, RMSE ${rmse}, WMAPE ${w}%.${g ? " Run saved with its traceability." : ""}`],
    [/^svc-planning revisó (\d+) combinaciones de producto y tienda y generó (\d+) recomendaciones nuevas \(quedan pendientes de aprobación\)\.$/,
      (m, r, t) => `svc-planning reviewed ${r} product and store combinations and generated ${t} new recommendations (pending approval).`],
    [/^Se revisaron (\d+) combinaciones de producto y tienda: ninguna necesita reabastecimiento en este momento \(o ya hay una orden pendiente para las que sí lo necesitan\)\.$/,
      (m, r) => `${r} product and store combinations were reviewed: none needs replenishment right now (or there is already a pending order for those that do).`],
    [/^Se generaron (\d+) recomendaciones de reabastecimiento a partir de (\d+) combinaciones evaluadas\. Cada una incluye su explicación y queda pendiente de aprobación\.$/,
      (m, t, r) => `${t} replenishment recommendations were generated from ${r} combinations evaluated. Each one includes its explanation and is pending approval.`],
    [/^(Orden|Transferencia) (\S+)( a través de svc-planning)?(?: por (\S+) unidades)?\.(?: La encuentras con el filtro «(.+)»\.)?$/,
      (m, t, e, via, c, f) => `${t === "Orden" ? "Order" : "Transfer"} ${p(e.charAt(0).toUpperCase() + e.slice(1)).toLowerCase()}${via ? " through svc-planning" : ""}${c ? ` for ${c} units` : ""}.${f ? ` You can find it with the «${p(f)}» filter.` : ""}`],
    [/^No se encontraron transferencias que pasaran las cuatro validaciones \((\d+) candidatas descartadas por no cumplirlas\)\.$/,
      (m, n) => `No transfers passed the four validations (${n} candidates discarded for not meeting them).`],
    [/^Se sugirieron (\d+) transferencias entre tiendas\. Cada una pasó las validaciones de origen suficiente, destino con necesidad, llegada antes de vencer y capacidad de consumo\.$/,
      (m, n) => `${n} transfers between stores were suggested. Each one passed the checks for sufficient origin, destination with need, arrival before expiration and consumption capacity.`],
    [/^Transferencia ejecutada: (\S+) unidades de (.+) a (.+)\. Inventario movido en PostgreSQL \(origen queda con (\S+), destino con (\S+)\)\.$/,
      (m, c, o, d, eo, ed) => `Transfer executed: ${c} units from ${o} to ${d}. Inventory moved in PostgreSQL (origin left with ${eo}, destination with ${ed}).`],
    [/^Se generaron (\d+) sugerencias de descuento para lotes próximos a vencer\.$/, (m, n) => `${n} discount suggestions were generated for batches about to expire.`],
    [/^No hay lotes en vigilancia o crítico que necesiten descuento\.$/, () => "There are no batches on watch or critical that need a discount."],
    [/^Desperdicio evitado recalculado con las ventas reales: (\d+) intervenciones actualizadas\.$/, (m, n) => `Waste avoided recalculated with actual sales: ${n} interventions updated.`],
    [/^Usuario «(.+)» creado en PostgreSQL con su contraseña cifrada con bcrypt\.$/, (m, u) => `User «${u}» created in PostgreSQL with their password encrypted with bcrypt.`],
    [/^Usuario (activado|desactivado)( y sus sesiones revocadas)?\.?$/, (m, a, r) => `User ${a === "activado" ? "activated" : "deactivated"}${r ? " and their sessions revoked" : ""}.`],
    [/^Proveedor «(.+)» registrado en PostgreSQL\.$/, (m, n) => `Supplier «${n}» registered in PostgreSQL.`],
    [/^Proveedor (\d+) (activado|desactivado)\.$/, (m, n, a) => `Supplier ${n} ${a === "activado" ? "activated" : "deactivated"}.`],
    [/^Producto SKU (\d+) (activado|desactivado)\.$/, (m, n, a) => `Product SKU ${n} ${a === "activado" ? "activated" : "deactivated"}.`],
  ];

  // Separadores con los que la interfaz junta un texto fijo con datos.
  const SEPARADORES = [" › ", " · ", " — ", " / "];

  function tr(texto) {
    if (!texto) return texto;
    if (Object.prototype.hasOwnProperty.call(DICCIONARIO, texto)) return DICCIONARIO[texto];
    if (Object.prototype.hasOwnProperty.call(PALABRAS, texto)) return PALABRAS[texto];
    for (const [re, fn] of REGLAS) {
      const m = texto.match(re);
      if (m) {
        const r = fn(...m);
        if (r != null) return r;
      }
    }
    // «Texto (dato)»: traducir la parte fija y lo que esté entre paréntesis si se conoce.
    let m = texto.match(/^(.+?) \((.+)\)$/);
    if (m) {
      const a = tr(m[1]), b = tr(m[2]);
      if (a !== m[1] || b !== m[2]) return `${a} (${b})`;
    }
    for (const sep of SEPARADORES) {
      if (texto.includes(sep)) {
        const partes = texto.split(sep);
        const traducidas = partes.map(tr);
        if (traducidas.some((t, i) => t !== partes[i])) return traducidas.join(sep);
      }
    }
    return texto;
  }

  // Traduce conservando espacios iniciales/finales. En bloques <pre> cada línea es
  // un texto aparte; en el resto los saltos de línea son solo formato del HTML.
  function trConEspacios(valor, porLinea = false) {
    if (porLinea && valor.includes("\n")) return valor.split("\n").map((l) => trConEspacios(l)).join("\n");
    const m = valor.match(/^(\s*)([\s\S]*?)(\s*)$/);
    if (!m[2]) return valor;
    const limpio = m[2].replace(/\s+/g, " ");
    const t = tr(limpio);
    return t === limpio ? valor : m[1] + t + m[3];
  }

  // ── Aplicar al DOM ──────────────────────────────────────────────────────────
  const ATRIBUTOS = ["title", "placeholder", "aria-label", "data-ayuda", "alt"];
  const OMITIR = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA", "CODE"]);
  const textoOriginal = new WeakMap();
  const atribOriginal = new WeakMap();
  let idioma = "es";
  let aplicando = false;

  function traducirTexto(nodo) {
    const padre = nodo.parentElement;
    if (!padre || OMITIR.has(padre.tagName) || padre.closest("[data-no-traducir]")) return;
    if (!textoOriginal.has(nodo)) textoOriginal.set(nodo, nodo.nodeValue);
    const original = textoOriginal.get(nodo);
    const nuevo = idioma === "en" ? trConEspacios(original, !!padre.closest("pre")) : original;
    if (nodo.nodeValue !== nuevo) nodo.nodeValue = nuevo;
  }

  function traducirAtributos(el) {
    if (el.closest("[data-no-traducir]")) return;
    let guardados = atribOriginal.get(el);
    for (const a of ATRIBUTOS) {
      if (!el.hasAttribute(a)) continue;
      if (!guardados) { guardados = {}; atribOriginal.set(el, guardados); }
      if (!(a in guardados)) guardados[a] = el.getAttribute(a);
      const nuevo = idioma === "en" ? trConEspacios(guardados[a]) : guardados[a];
      if (el.getAttribute(a) !== nuevo) el.setAttribute(a, nuevo);
    }
    // Botones <input type="submit|button"> muestran su texto en value.
    if (el.tagName === "INPUT" && /^(submit|button|reset)$/i.test(el.type)) {
      if (!guardados) { guardados = {}; atribOriginal.set(el, guardados); }
      if (!("value" in guardados)) guardados.value = el.value;
      el.value = idioma === "en" ? trConEspacios(guardados.value) : guardados.value;
    }
  }

  function recorrer(raiz) {
    if (raiz.nodeType === Node.TEXT_NODE) { traducirTexto(raiz); return; }
    if (raiz.nodeType !== Node.ELEMENT_NODE) return;
    if (OMITIR.has(raiz.tagName)) return;
    traducirAtributos(raiz);
    const walker = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n = walker.nextNode();
    while (n) {
      if (n.nodeType === Node.TEXT_NODE) traducirTexto(n);
      else traducirAtributos(n);
      n = walker.nextNode();
    }
  }

  // Las gráficas se dibujan en <canvas>: hay que traducir sus etiquetas en Chart.js.
  function traducirGraficas() {
    if (!window.Chart || !window.Chart.instances) return;
    Object.values(window.Chart.instances).forEach((chart) => {
      try {
        if (!chart.$i18n) {
          chart.$i18n = {
            labels: (chart.data.labels || []).slice(),
            datasets: chart.data.datasets.map((d) => d.label),
          };
        }
        const o = chart.$i18n;
        const f = (t) => (typeof t === "string" && idioma === "en" ? tr(t) : t);
        chart.data.labels = o.labels.map(f);
        chart.data.datasets.forEach((d, i) => { d.label = f(o.datasets[i]); });
        chart.update("none");
      } catch (e) { /* una gráfica rara no debe romper la página */ }
    });
  }

  let tituloOriginal = null;
  function aplicar() {
    aplicando = true;
    try {
      if (tituloOriginal === null) tituloOriginal = document.title;
      document.title = idioma === "en" ? tr(tituloOriginal) : tituloOriginal;
      document.documentElement.setAttribute("lang", idioma);
      recorrer(document.body);
      traducirGraficas();
      document.querySelectorAll("[data-lang-toggle]").forEach((b) => {
        b.textContent = idioma === "en" ? "ES" : "EN";
        b.setAttribute("title", idioma === "en" ? "Cambiar a español" : "Switch to English");
        b.setAttribute("aria-label", b.getAttribute("title"));
      });
    } finally {
      aplicando = false;
    }
  }

  // Contenido que llega después (fetch, tablas armadas con JS, mensajes).
  const observador = new MutationObserver((mutaciones) => {
    if (aplicando || idioma !== "en") return;
    aplicando = true;
    try {
      for (const m of mutaciones) {
        if (m.type === "characterData") {
          // El JS de la página cambió el texto: ése es el nuevo original.
          textoOriginal.set(m.target, m.target.nodeValue);
          traducirTexto(m.target);
        } else {
          m.addedNodes.forEach((n) => {
            if (n.nodeType === Node.TEXT_NODE) textoOriginal.set(n, n.nodeValue);
            recorrer(n);
          });
        }
      }
    } finally {
      aplicando = false;
    }
  });

  function leerIdioma() {
    try { return localStorage.getItem(LANG_KEY) === "en" ? "en" : "es"; } catch (e) { return "es"; }
  }
  function guardarIdioma(v) {
    try { localStorage.setItem(LANG_KEY, v); } catch (e) { /* sin almacenamiento: solo dura esta página */ }
  }

  function iniciar() {
    idioma = leerIdioma();
    document.querySelectorAll("[data-lang-toggle]").forEach((b) => {
      b.addEventListener("click", () => {
        idioma = idioma === "en" ? "es" : "en";
        guardarIdioma(idioma);
        aplicar();
      });
    });
    // Aunque la página esté en español se marca el botón (EN) y su tooltip.
    aplicar();
    observador.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  window.FreshTrackI18n = { traducir: tr, idioma: () => idioma };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
