# Bitácora de participación

Registro de la participación de cada integrante construido a partir del historial real del repositorio `github.com/crlsbk/freshtrack` (138 commits sin contar fusiones, del 25 de agosto al 24 de noviembre de 2026). Cada entrada es verificable con `git log`.

## 1. Resumen por integrante

| Integrante | Cuenta de git | Commits | Primer commit | Último commit | Áreas principales |
| --- | --- | --- | --- | --- | --- |
| Juan Nicolás Núñez Mendoza | `crlsbk` | 71 | 2026-08-25 | 2026-11-24 | App de escritorio (PySide6, XML/XSD), contratos XSD, servicio de correo, recuperación de contraseña, notificaciones, endpoints móviles, pruebas de sistema y de fallas, documentación y despliegue |
| Santiago López Cervantes | `vrdtska` | 45 | 2026-09-07 | 2026-11-24 | Microservicios y dominio (pronóstico, reabastecimiento, triaje), volumetría masiva, optimización de PostgreSQL y Redis, Locust, seguridad (CSRF, refresh token) |
| Fabián Azaed Orta Singlaterry | `Fabian Orta` | 13 | 2026-09-28 | 2026-10-23 | Contratos JSON/XML con XSD, errores uniformes, JWT con sesión en Redis, interfaz web y arranque reproducible del proyecto |
| Cuenta «fivi» (rFaos) | `fivi` | 9 | 2026-09-08 | 2026-11-24 | App Android (Kotlin): escáner QR, recepción, FEFO, mermas con foto, transferencias, alertas; optimización de consultas del panel web |

> La cuenta `fivi` (usuario de GitHub `rFaos`) no tiene nombre real en git: el equipo debe confirmar a qué integrante corresponde antes de entregar.

## 2. Participación por mes

| Mes | Juan Nicolás | Santiago | Fabián | fivi | Hitos |
| --- | --- | --- | --- | --- | --- |
| 2026-08 | 2 | 0 | 0 | 0 | Arranque del repositorio y estructura base |
| 2026-09 | 10 | 12 | 4 | 6 | Web Flask, ETL, PostgreSQL, primeros microservicios y optimización del panel |
| 2026-10 | 11 | 6 | 9 | 0 | Segundo parcial: contratos JSON/XML con XSD, JWT con sesión en Redis, 8 microservicios, Swagger |
| 2026-11 | 48 | 27 | 0 | 3 | Entrega final: apps de escritorio y Android, despliegue en GCP, volumetría, Locust, seguridad, pruebas de sistema y de fallas, manuales |

## 3. Herramientas de apoyo

El equipo usó un asistente de programación con IA (Claude Code) como apoyo: 81 commits llevan la línea `Co-Authored-By: Claude`. Todo cambio fue revisado, probado y aprobado por el integrante que hizo el commit, que es el responsable de su contenido.

## 4. Registro completo de commits

| Fecha | Integrante | Cambio |
| --- | --- | --- |
| 2026-11-24 | Juan | chore: limpieza para la entrega final |
| 2026-11-24 | Juan | docs: reporte técnico final alineado con el código, manuales y reportes de pruebas (1c213e4) |
| 2026-11-24 | Juan | docs(pruebas): correcciones de los simulacros verificadas en vivo |
| 2026-11-24 | Juan | fix: hallazgos de los simulacros de fallas (fotos 8 MB, Redis/Mongo caídos, PostgreSQL caído) |
| 2026-11-24 | Juan | docs: manuales (instalación, técnico, usuario) y reportes de fallas y pruebas de sistema |
| 2026-11-24 | Juan | feat(android): trabajo sin conexión, sincronización posterior y registro del dispositivo |
| 2026-11-24 | Juan | feat(movil-backend): registro seguro de dispositivos y merma idempotente |
| 2026-11-24 | Juan | feat(monitoreo): «último error registrado» por microservicio en /ops/status |
| 2026-11-24 | Juan | feat(web): centro de notificaciones con campana y /notificaciones |
| 2026-11-24 | Juan | feat(auth): recuperación de contraseña por correo en la web |
| 2026-11-24 | fivi | docs: reporte técnico final (entrega final) con el formato del segundo parcial |
| 2026-11-24 | fivi | fix(android): usar el refresh token rotatorio del servidor |
| 2026-11-24 | Juan | feat(movil): endpoints que usa la app Android: conteo cíclico, solicitud de transferencia y evidencia con URL firmada |
| 2026-11-24 | Juan | fix(desperdicio): lo vendido tras un traslado o descuento cuenta como recuperado sin pulsar Recalcular |
| 2026-11-24 | Santiago | perf(productos): agregar lotes y existencias en una pasada en vez de por fila |
| 2026-11-24 | fivi | feat(android): app móvil para personal de tienda (FreshTrack Mobile) |
| 2026-11-24 | Santiago | test(carga): suite Locust con perfiles reales, ventas en tiendas y resultados en archivos + PostgreSQL |
| 2026-11-24 | Santiago | test(carga): pruebas de carga con Locust de 8 perfiles y reporte de línea base |
| 2026-11-24 | Santiago | security: refresh token real con rotación, tope absoluto y detección de robo |
| 2026-11-24 | Santiago | security: protección CSRF en la web y cierre de sesión por POST |
| 2026-11-24 | Santiago | security: usuarios proveedor ligados a su proveedor (permisos por recurso) |
| 2026-11-24 | Santiago | security: revocación completa, permisos de triaje, redirección segura y errores sin detalles internos |
| 2026-11-24 | Santiago | docs/tests: despliegue en caliente de 08_optimizacion.sql y pruebas de la caché, MV y cálculos en lote |
| 2026-11-24 | Santiago | perf(microservicios): conteos cacheados, topes de paginación, índices Mongo y combos completos en escritorio |
| 2026-11-24 | Santiago | perf(infra): pool de conexiones acotado, timeouts Redis y tuning de producción |
| 2026-11-24 | Santiago | perf(ventas/auditoría): caché estable ante ventas, auditoría indexada y usuarios paginados |
| 2026-11-24 | Santiago | perf(inventario): paginación real en /lotes, /inventario y /reabastecimiento |
| 2026-11-24 | Santiago | perf(planeación): caché Redis y triaje sin N+1 en pronóstico, reabastecimiento y compras |
| 2026-11-24 | Santiago | perf(db): demanda diaria materializada, índices faltantes y filtros sargables |
| 2026-11-24 | Santiago | Postgres y redis optimizacion |
| 2026-11-24 | Juan | revert: quitar etapas de entrenamiento/validación/testeo (a5da7ca, db36d1d, 9f48392); conservar volumetría |
| 2026-11-23 | Santiago | implementacion de volumetria masiva |
| 2026-11-23 | Santiago | resolucion de query a challenger para resolver por nulos |
| 2026-11-23 | Santiago | corrección a error de valor flotante en pronostico |
| 2026-11-23 | Santiago | Implementacion de etapas de entrenamiento, validacion y testeo de modelos |
| 2026-11-23 | Santiago | Implementacion de dashboard de monitoreo de microservicios |
| 2026-11-23 | Juan | fix(correo): el puerto 587 siempre usa STARTTLS |
| 2026-11-23 | Juan | fix(escritorio): salud de servicios a través del gateway |
| 2026-11-23 | Juan | feat(escritorio): rediseño visual — íconos de línea, barra lateral con marca y tarjeta de usuario |
| 2026-11-23 | Juan | feat(correo): servidor SMTP (Mailpit) y envío por correo de la Hoja QR del ASN |
| 2026-11-23 | Juan | docs(escritorio): capturas regeneradas de planner y buyer tras la ola de corrección |
| 2026-11-23 | Juan | docs(escritorio): guion de la demo de fallas reproducible y README fiel a la app |
| 2026-11-23 | Juan | docs(commercial): /sales/import documenta 503 (Redis no disponible) en OpenAPI |
| 2026-11-23 | Juan | feat(escritorio): auditoría visual — sin UUID en tablas, métodos legibles y estados vacíos con siguiente paso |
| 2026-11-23 | Juan | fix(escritorio): sin diálogo de error huérfano por un 401 cuando ya se volvió al login |
| 2026-11-23 | Juan | fix(escritorio): la bitácora solo sincroniza con svc-audit las acciones del usuario de la sesión |
| 2026-11-23 | Juan | feat(escritorio): validar toda petición contra su XSD, token enmascarado en el inspector |
| 2026-11-23 | Juan | feat(contratos): XSD de las 8 peticiones XML que envía la app de escritorio |
| 2026-11-23 | Juan | fix(escritorio): Ctrl+R sin ambigüedad y «Ejecutar ciclo» habilitado para buyer (403 del servidor) |
| 2026-11-23 | Juan | fix(escritorio): recolectar basura solo en el hilo de UI (segfault de shiboken en el pool) |
| 2026-11-23 | Juan | feat(escritorio): validar toda respuesta contra contracts/xsd/<raiz>.xsd si existe |
| 2026-11-23 | Juan | feat(contratos): XSD de las 21 respuestas XML que consume la app de escritorio |
| 2026-11-23 | Juan | feat(escritorio): empaquetado PyInstaller, README, capturas reales y targets de Makefile |
| 2026-11-23 | Juan | test(escritorio): pruebas de decisiones leen las muestras XML versionadas |
| 2026-11-23 | Juan | test(escritorio): pruebas operativas leen las muestras XML versionadas |
| 2026-11-23 | Juan | fix(escritorio): barra en dos filas, refresh por generación y columnas de descuentos |
| 2026-11-23 | Juan | fix(escritorio): ticket completo excluido si una fila falla, envío se detiene ante 401/403/429 y limpieza de PDF temporal |
| 2026-11-23 | Juan | fix(escritorio): fixtures XML versionados y ajustes de Tablero y Pronósticos |
| 2026-11-23 | Juan | feat(escritorio): fechas ISO legibles en hora local en todas las tablas |
| 2026-11-23 | Juan | feat(escritorio): conectar las páginas reales al menú y tonos de estado faltantes |
| 2026-11-23 | Juan | feat(escritorio): páginas Mermas y desperdicio, Órdenes de compra e Importar ventas |
| 2026-11-23 | Juan | feat(escritorio): páginas Tablero, Pronósticos y Newsvendor |
| 2026-11-23 | Juan | feat(escritorio): páginas de decisión (reabastecimiento, transferencias y descuentos) |
| 2026-11-23 | Juan | fix(escritorio): mensaje literal para roles no permitidos y ajustes menores del shell |
| 2026-11-22 | Juan | feat(escritorio): shell Qt (ventana, login, contexto, widgets, inspector XML, estado y actividad) |
| 2026-11-22 | Santiago | Implementacion de logica de embargues asn con ordenes de compra |
| 2026-11-22 | Juan | fix(escritorio): on_unauthorized una sola vez y refresh que solo expira ante 401/403 |
| 2026-11-22 | Juan | feat(escritorio): núcleo de la app (config, códec XML, cliente HTTP, sesión y bitácora) |
| 2026-11-22 | Juan | fix(comercial): importación de ventas tolera excepciones por ticket y limita tasa |
| 2026-11-22 | Juan | feat(comercial): endpoint POST /api/v1/commercial/sales/import (importación masiva XML idempotente) |
| 2026-11-22 | Juan | feat(auth): endpoint POST /api/v1/auth/refresh para renovar el JWT |
| 2026-11-22 | Juan | docs(escritorio): diseño y plan de la app de escritorio |
| 2026-11-22 | Santiago | fix(sql): diferir FK de orden_compra_detalle a 04_ddl_analitica |
| 2026-11-22 | Santiago | Bootstrap implementation for gcp |
| 2026-11-22 | Santiago | Implementación de correo electrónico en órdenes de compra como comprador |
| 2026-11-21 | Santiago | Implementacion de automl |
| 2026-11-16 | Santiago | Implementación de tráfico JSON para ventas concurrentes |
| 2026-11-16 | Santiago | Implementación de Newsvendor, robustez de microservicios, automatización de procesamiento inteligente de merma. |
| 2026-10-23 | Juan | docs(evidencias): 88 peticiones reales request/response contra los 8 servicios |
| 2026-10-23 | Juan | docs: quitar documentos de docs/ y enlazar la entrega desde el README |
| 2026-10-23 | Juan | docs(pruebas): reporte por caso del punto 12 generado desde pytest |
| 2026-10-23 | Juan | chore: quitar archivos de agentes y documentos irrelevantes |
| 2026-10-23 | Juan | feat(web): mapa de tiendas con indicadores por ubicacion |
| 2026-10-23 | Juan | feat(web): boton ES/EN para ver la interfaz en ingles |
| 2026-10-23 | Juan | feat(scripts): barrido de los 8 microservicios por HTTP real |
| 2026-10-23 | Juan | docs(planeador): corregir comandos de la guia de demostracion |
| 2026-10-23 | Juan | fix(pronostico): WMAPE global con el mismo universo que el numerador |
| 2026-10-23 | Juan | fix(events): heredar usuario, rol y correlation_id del request en los eventos |
| 2026-10-23 | Juan | feat(scripts): checador del planeador por HTTP real (JSON/XML, JWT y Redis) |
| 2026-10-23 | Santiago | resolucion de microservicios |
| 2026-10-23 | Fabián | feat(web): la web consume los microservicios por HTTP |
| 2026-10-23 | Santiago | Verified app |
| 2026-10-22 | Fabián | feat(web): tema claro, menos datos a la vez y tarjetas mas limpias |
| 2026-10-22 | Fabián | feat(web): panel por secciones, ayudas en lenguaje simple y etiquetas legibles |
| 2026-10-22 | Fabián | fix(web): interfaz mas legible y bugs visuales del panel |
| 2026-10-22 | Fabián | docs: documentacion del segundo parcial y generadores de evidencias |
| 2026-10-22 | Fabián | ci: compose listo para despliegue y pipeline de GitHub Actions |
| 2026-10-22 | Fabián | feat(web): pantalla de microservicios y textos de interfaz mas claros |
| 2026-10-22 | Fabián | test: pruebas unitarias y de integracion con pytest (106) |
| 2026-10-22 | Fabián | feat(microservicios): contratos JSON/XML con XSD, errores uniformes y JWT con sesion en Redis |
| 2026-10-21 | Santiago | Implementación de medios de seguridad de endpoints |
| 2026-10-21 | Santiago | Implementación de mejoras en REDIS, jwt y sistema orquestador |
| 2026-10-21 | Santiago | Extension y mejora de MONGODB |
| 2026-10-21 | Santiago | Implementación de microservicios con su documnentacion |
| 2026-09-28 | Fabián | fix(security): quitar contrasenas literales del volcado legacy de roles |
| 2026-09-28 | Fabián | fix(dev): hacer que el proyecto arranque igual en cualquier maquina |
| 2026-09-28 | Fabián | fix(db): fallar rapido si no hay base escuchando, en vez de colgarse |
| 2026-09-28 | Fabián | feat(avance2): operar sobre PostgreSQL real, sin datos simulados |
| 2026-09-08 | fivi | feat(auth): add role alias fallback, restore quick-demo buttons, and update DDL with email/password |
| 2026-09-08 | Juan | aa |
| 2026-09-08 | Juan | Backend ahora checa contrasenia y correo |
| 2026-09-08 | Juan | Usuarios ahora tienen correo y contrasenia |
| 2026-09-08 | fivi | chore(sql): include PostgreSQL DDL scripts and exclude binary dumps from git |
| 2026-09-08 | fivi | fix(ui): eliminate blank columns in inventory, batches, alerts and stores with native SQL joins |
| 2026-09-08 | fivi | feat(data): full end-to-end persistence for products, supplier linking, and real-time database charts |
| 2026-09-08 | fivi | feat(auth): support email login, role aliases and quick-demo login buttons |
| 2026-09-08 | fivi | fix(perf): optimize queries with SQL aggregates, indexes and dictionary lookups to eliminate dashboard hangs |
| 2026-09-08 | Juan | Fix bug roles |
| 2026-09-08 | Juan | Fix app.py |
| 2026-09-08 | Juan | a |
| 2026-09-07 | Juan | ui |
| 2026-09-07 | Santiago | Sleep a app build en docker-compose para no tener que construir app aún |
| 2026-09-07 | Santiago | Dockerfile y docker-compose actualizados para mongodb y redis |
| 2026-09-07 | Santiago | Se agregan documentos de desarrollo del proyecto. |
| 2026-09-07 | Santiago | README fix |
| 2026-09-07 | Santiago | Docker SQL config, env.example, makefile, gitignore y gitattributes implementados |
| 2026-09-07 | Santiago | Docker SQL config, env.example, makefile, gitignore y gitattributes implementados |
| 2026-09-07 | Santiago | aaa |
| 2026-09-07 | Santiago | aa |
| 2026-09-07 | Santiago | Fix de UUID |
| 2026-09-07 | Santiago | fix proveedores script etl |
| 2026-09-07 | Santiago | ETL script ready |
| 2026-09-07 | Santiago | ETL pipeline implementation |
| 2026-09-03 | Juan | requirements |
| 2026-09-03 | Juan | mejor estructura |
| 2026-09-03 | Juan | cambio a flask |
| 2026-08-28 | Juan | setup django |
| 2026-08-25 | Juan | Initial commit |
