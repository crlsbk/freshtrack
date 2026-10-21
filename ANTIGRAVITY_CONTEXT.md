1. Visión General del Producto y Dominio de Negocio1.1 ¿Qué es FreshTrack?FreshTrack es una plataforma web B2B de gestión inteligente de productos perecederos (frutas, verduras, carnes, pescados, lácteos, panadería y embutidos) diseñada para grandes cadenas de retail y autoservicio mayoristas/minoristas (p. ej. Soriana, H-E-B, Walmart, La Comer).1.2 Problema Central que ResuelveMerma y Desperdicio: Pérdidas millonarias por caducidad en anaquel y almacén.Falta de Rotación Eficiente: Inadecuada aplicación de la estrategia FEFO (First Expired, First Out).Falta de Automatización en Descuentos: Pérdida de oportunidad de venta al no liquidar a tiempo productos con fecha de vencimiento próxima.Impacto Ambiental y Sostenibilidad (ESG): Emisiones innecesarias de CO₂ y metano por alimentos desechados en lugar de ser donados o vendidos a tiempo.1.3 Objetivos de NegocioMaximizar la frescura de los perecederos para el consumidor final.Minimizar la merma operativa y aumentar el margen de recuperación financiera.Facilitar auditorías, trazabilidad por lote y donaciones a bancos de alimentos.2. Arquitectura de Software y Stack TecnológicoCapa / ComponenteTecnología / VersiónDescripciónLenguaje CorePython 3.14Configurado en .python-versionBackend / FrameworkFlaskServidor web modular en app/app.pyMotor de PlantillasJinja2Templates HTML modulares extendiendo base.htmlFrontend UIHTML5, CSS3, Vanilla JSapp/static/css/style.css, app/static/js/app.jsCapa de Datos ActualMock Data en Memoria / Pythonapp/data/mock_data.py (listas y diccionarios estructurados)Capa de Datos DestinoBase de Datos RelacionalEsquema relacional detallado en docs/BD_Diseño.docx-2.pdfContenedorizaciónDocker & Docker ComposeDockerfile, docker-compose.yml, Makefile3. Estructura del RepositorioPlaintextfreshtrack/
├── .editorconfig
├── .gitattributes
├── .gitignore
├── .python-version               # Versión de Python especificada (3.14)
├── Dockerfile                    # Configuración de contenedor para la app Flask
├── docker-compose.yml            # Orquestación de servicios
├── Makefile                      # Comandos de automatización (build, run, lint)
├── README.md                     # Descripción del proyecto
├── app/
│   ├── __init__.py / init.py
│   ├── app.py                    # Controlador principal, rutas y lógica de Flask
│   ├── data/
│   │   ├── __init__.py
│   │   └── mock_data.py          # Conjunto de datos simulados de tiendas, lotes, etc.
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css         # Estilos, variables CSS y diseño de dashboard
│   │   └── js/
│   │       └── app.js            # Interacciones, filtros dinámicos y modales
│   └── templates/                # Vistas Jinja2
│       ├── base.html             # Shell maestro: Sidebar, Topbar, Alerts
│       ├── dashboard.html        # Resumen ejecutivo con KPIs y semáforo de riesgo
│       ├── inventory.html        # Inventario general por tienda/almacén
│       ├── batches.html          # Control de lotes con fechas de ingreso y caducidad
│       ├── fefo.html             # Matriz de priorización de salida FEFO
│       ├── alerts.html           # Alertas críticas de riesgo y caducidad próxima
│       ├── discounts.html        # Gestión y sugerencias de descuentos dinámicos
│       ├── replenishment.html    # Sugerencias y órdenes de reabastecimiento
│       ├── shrinkage.html        # Registro, causas y estadísticas de merma
│       ├── forecast.html         # Pronósticos de demanda y vida útil
│       ├── sustainability.html   # Impacto ambiental, CO2 evitado y donaciones
│       ├── audit.html            # Log de trazabilidad y auditoría de acciones
│       ├── stores.html           # Sucursales / Tiendas registradas
│       ├── products.html         # Catálogo maestro de SKUs perecederos
│       ├── suppliers.html        # Proveedores y acuerdos de entrega
│       ├── sales.html            # Historial y registro de ventas
│       ├── transfers.html        # Transferencias inter-sucursales
│       ├── users.html            # Administración de usuarios y perfiles
│       ├── settings.html         # Parámetros del sistema y umbrales de alerta
│       └── login.html            # Autenticación y acceso
└── docs/                         # Documentación de diseño y especificaciones funcionales
    ├── BD_Diseño.docx-2.pdf
    ├── DocumentoAnalítico.docx.pdf
    ├── Estrategia de Ramas.docx.pdf
    ├── HU_ProyectoRetail_IAC - Historias de Usuario.pdf
    ├── Matriz_Perfiles_Permisos_IAC.pdf
    ├── Plan de Trabajo.docx.pdf
    ├── Presentacion_Tecnica_FreshTrack.pdf
    └── Prototipo de interfaces.pdf
4. Módulos Funcionales y Reglas de Negocio4.1 Semáforo de Riesgo y Estrategia FEFOLógica FEFO (First Expired, First Out): El inventario no se rota por orden de llegada (FIFO), sino estrictamente por la fecha de caducidad más próxima.Semáforo de Vida Útil:Verde (Normal): Producto con más del 50% de vida útil remanente. Venta regular.Amarillo (Atención): Entre 20% y 50% de vida útil remanente. Requiere exhibición preferente.Naranja (Crítico / Descuento): Menos de 20% de vida útil remanente o umbral crítico (ej. 3-5 días antes de vencer). Sugiere descuento dinámico (20% a 50%).Rojo (Inmediato / Retiro o Donación): 24-48 horas antes de caducar. Opciones: Remate final (70%), canalización a Banco de Alimentos (donación con deducibilidad) o baja por merma controlada.4.2 Descuentos DinámicosEl sistema calcula sugerencias de descuento escalonadas para evitar que el lote termine en merma absoluta.Considera la elasticidad del producto, stock remanente y días restantes.4.3 Gestión de Merma (Shrinkage)Clasificación de causas: Vencimiento en anaquel, rotura por manipulación, pérdida de cadena de frío, plagas/daño biológico.Métricas clave: % de merma sobre venta neta, costo financiero y volumen en kilogramos/unidades.4.4 Sostenibilidad y Responsabilidad Social (ESG)Registro de alimentos rescatados vs. desechados.Estimación de emisiones de gases de efecto invernadero (GEI / CO₂ eq) evitadas por donaciones y liquidación oportuna.5. Roles y Permisos (Matriz RACI)Basado en docs/Matriz_Perfiles_Permisos_IAC.pdf:Administrador de Cadena / Retail Ops: Acceso global a todas las tiendas, parametrización de umbrales, gestión de usuarios, catálogos y reportes consolidados.Gerente de Tienda (Store Manager): Control de su sucursal, aprobación de descuentos, autorización de mermas y reabastecimientos.Encargado de Perecederos / Merma: Monitoreo diario de semáforos, registro de bajas, etiquetado de rebajas y asignación a donaciones.Operador de Piso / Almacén: Recepción de lotes, registro de temperatura/vida útil inicial, picking y rotación física en góndolas/cámaras frías.Auditor / Analista de Calidad: Solo lectura y trazabilidad retrospectiva de movimientos, inspecciones y auditorías.6. Flujo de Desarrollo y Buenas Prácticas para el Agente6.1 Convenciones de CódigoPython: PEP 8, tipado estático opcional recomendado (typing), docstrings descriptivos en funciones y rutas de Flask.Templates: Reutilizar siempre bloques de base.html ({% extends "base.html" %}, {% block content %}). Mantener la nomenclatura de clases CSS existente.Separación de Responsabilidades: No acoplar lógica de negocio compleja dentro de app/app.py. A medida que el proyecto escale, refactorizar hacia Blueprints (routes/), servicios de dominio (services/) y repositorios de datos (repositories/).6.2 Estrategia de Git (según Estrategia de Ramas.docx.pdf)main: Producción, versiones estables etiquetadas con tags semánticos (vX.Y.Z).develop: Integración activa de características.feature/<nombre>: Ramas de funcionalidad desarrolladas desde develop.hotfix/<nombre>: Correcciones urgentes directo sobre main.Mensajes de commit en formato convencional (ej. feat: add dynamic discount calculator, fix: resolve FEFO sorting by expiration date).6.3 Tareas Inmediatas y Siguientes Pasos TípicosPersistencia Real: Migrar de mock_data.py a una base de datos relacional (PostgreSQL/SQLite) con SQLAlchemy o psycopg, respetando el modelo ER documentado en docs/BD_Diseño.docx-2.pdf.Autenticación y Sesiones: Implementar Flask-Login o JWT para hacer valer la matriz de roles y permisos.API Endpoints REST: Exponer endpoints JSON para que el frontend o aplicaciones de lectores de código de barras/handhelds puedan interactuar de manera asíncrona (Fetch/Axios).Validación de Formularios: Introducir WTForms o Pydantic para validar entradas de lotes y fechas de vencimiento.