# Registro de incidencias

Incidencias detectadas durante el desarrollo, el despliegue y las pruebas de FreshTrack, con su causa, su solución y el commit que la cierra (búsquese su mensaje con `git log --grep`). Las incidencias de severidad alta de los simulacros se re-verificaron en vivo; el detalle está en `docs/pruebas/FALLAS_Y_RECUPERACION.md`.

**Severidad:** Alta = bloquea una función o expone datos · Media = degrada la operación · Baja = detalle o mejora.

## 1. Incidencias cerradas

| ID y fecha | Componente | Incidencia | Sev. | Causa | Solución (commit) |
| --- | --- | --- | --- | --- | --- |
| INC-01 · 2026-09-07 | ETL | El script de proveedores fallaba al cargar datos | Media | Datos de proveedores inconsistentes en el ETL | Corrección del script de carga (`git log --grep "proveedores script etl"`) |
| INC-02 · 2026-09-07 | Base de datos | Error de tipo UUID en identificadores | Media | Conversión incorrecta de UUID | Conversión explícita a uuid («Fix de UUID») |
| INC-03 · 2026-09-08 | Seguridad | Roles con permisos incorrectos en la web | Alta | Mapeo de roles incompleto | Corrección de la asignación de roles («Fix bug roles») |
| INC-04 · 2026-09-08 | Web | El panel se colgaba y había columnas vacías | Alta | Consultas N+1 sin agregados ni índices | Agregados SQL, índices y joins nativos (fix(perf), fix(ui)) |
| INC-05 · 2026-09-28 | Seguridad | Contraseñas literales en un volcado de roles | Alta | Secretos versionados por error | Se quitaron del repositorio; vienen del entorno (fix(security)) |
| INC-06 · 2026-09-28 | Infraestructura | La app se colgaba si no había base de datos | Media | Sin timeout de conexión | Falla rápida con mensaje claro (fix(db)) |
| INC-07 · 2026-10-22 | Web | Interfaz poco legible y errores visuales del panel | Baja | Estilos inconsistentes | Ajustes de la interfaz (fix(web)) |
| INC-08 · 2026-10-23 | Eventos | Los eventos perdían usuario, rol y correlation_id | Media | El evento no heredaba el contexto del request | Herencia del contexto en el publicador (fix(events)) |
| INC-09 · 2026-10-23 | Pronóstico | WMAPE global mal calculado | Media | Numerador y denominador con universos distintos | Mismo universo en ambos (fix(pronostico)) |
| INC-10 · 2026-11-22 | Base de datos | Llave foránea de `orden_compra_detalle` fallaba al inicializar | Alta | Orden de creación entre esquemas | FK diferida a `04_ddl_analitica.sql` (fix(sql)) |
| INC-11 · 2026-11-22 | svc-commercial | Una fila mala abortaba toda la importación de ventas | Media | Sin aislamiento de errores por ticket | Aislamiento por ticket y límite de tasa (fix(comercial)) |
| INC-12 · 2026-11-23 | Escritorio | Cierre inesperado (segfault) al recolectar memoria | Alta | Recolector de basura en hilos del pool de Qt | Recolección solo en el hilo de la interfaz (fix(escritorio)) |
| INC-13 · 2026-11-23 | Escritorio | Doble aviso de sesión expirada y carrera en el refresh | Media | Manejo de 401 duplicado | Un solo manejador y refresh serializado (fix(escritorio)) |
| INC-14 · 2026-11-23 | Escritorio / gateway | Los 8 servicios aparecían caídos detrás de Caddy | Alta | `/health` no tenía ruta en el gateway | Alias `/api/v1/{servicio}/health` (fix(escritorio)) |
| INC-15 · 2026-11-23 | Correo | Gmail rechazaba el envío por SMTP | Alta | Sin STARTTLS en el puerto 587 | El puerto 587 siempre usa STARTTLS (fix(correo)) |
| INC-16 · 2026-11-23 | Pronóstico | Error por valores flotantes y nulos en el pronóstico | Media | Datos nulos en la volumetría masiva | Manejo de nulos y conversión numérica (corrección / resolución) |
| INC-17 · 2026-11-24 | Código | Etapas de entrenamiento y validación incompletas rompían el pronóstico | Alta | Cambios no terminados en la rama compartida | Reversión conservando la volumetría (revert) |
| INC-18 · 2026-11-24 | Desperdicio evitado | Lo vendido tras un traslado o descuento no contaba como recuperado | Media | Solo se recalculaba con un botón manual | Recálculo automático al consultar (fix(desperdicio)) |
| INC-19 · 2026-11-24 | Rendimiento | /proveedores tardaba 10 s en la primera carga | Media | Pronóstico por producto y tienda sin caché | Caché en Redis con protección anti-estampida (perf(planeación)) |
| INC-20 · 2026-11-24 | App Android | La app no usaba el refresh token rotatorio | Alta | Contrato de refresh cambiado en el servidor | Cliente actualizado al nuevo contrato (fix(android)) |
| INC-21 · 2026-11-24 | Backend móvil | La app llamaba a 4 endpoints inexistentes (conteo, transferencia, evidencias) | Alta | Endpoints no implementados en el backend | Endpoints, XSD, tablas y pruebas nuevas (feat(movil)) |
| INC-22 · 2026-11-24 | Archivos | Fotos de 4 a 8 MB rechazadas con 413 en inglés | Alta | Límite global de 4 MB | Límite de 9 MB y mensaje en español (fix: hallazgos) |
| INC-23 · 2026-11-24 | Redis / MongoDB | Con la dependencia caída, peticiones de 5–28 s y alertas «vacías» | Alta | Cliente guardado en memoria sin verificar | PING cada 5 s y corte por 10 s; 503 claro (fix: hallazgos) |
| INC-24 · 2026-11-24 | Seguridad | Con PostgreSQL caído, las apps cerraban sesión (401) | Alta | No se distinguía «sesión inválida» de «base caída» | 503 `sesion_no_verificable` (fix: hallazgos) |

## 2. Incidencias abiertas (trabajo futuro)

| ID | Componente | Incidencia | Sev. | Plan |
| --- | --- | --- | --- | --- |
| INC-25 | Health checks | Con el bucket o MongoDB caídos, los 8 `/health` dan 503 y Docker los marca no sanos | Media | Separar dependencias críticas de opcionales |
| INC-26 | PostgreSQL | Sin `statement_timeout`: con la base congelada `/health` se cuelga más de 45 s | Media | Agregar `statement_timeout` y timeout de socket |
| INC-27 | Sesiones | Un token emitido con Redis caído se invalida cuando Redis vuelve | Media | Reconstruir la sesión en Redis desde PostgreSQL |
| INC-28 | svc-alerts | Con Redis caído, el escaneo de alertas responde 409 en lugar de 503 | Media | Distinguir bloqueo ocupado de Redis caído |
| INC-29 | Archivos | El PDF creado con el bucket caído no se sube cuando vuelve | Baja | Tarea de sincronización de `local_fallback` |
| INC-30 | Gateway web | El 502 no incluye `correlation_id` | Baja | Agregar el identificador en el gateway |
| INC-31 | Rendimiento | p95 de 9 s con 30 usuarios en la línea base (antes de optimizar) | Media | Repetir Locust con el overlay de producción |
