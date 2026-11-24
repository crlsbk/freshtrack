# Fallas y recuperación — FreshTrack

**Equipo 05 · Proyecto 12 · 24 de noviembre de 2026 · stack local de docker compose (commit 1926a17)**

Cada simulacro detiene (`docker stop`) o congela (`docker pause`) una sola dependencia, registra lo que responden la web, los microservicios y el panel `/ops/status`, y siempre restaura en un bloque `finally`.

- Script: `docs/pruebas/scripts/simulacro_fallas.py <escenario>`.
- Bitácoras y datos: `docs/pruebas/fallas/<escenario>.txt|.json`.
- Al terminar se verificaron los 14 contenedores (healthy) y /health 200 en la web y en 5001–5008.

## Resumen

| Escenario | Comportamiento esperado | Observado | ¿Cumple? | Recuperación |
|---|---|---|---|---|
| 1. Se detiene svc-planning | Los demás siguen; mensaje claro; el monitoreo lo marca caído | Gateway 502 `servicio_no_disponible`; la web muestra «El módulo solicitado no está disponible…»; inventario, ventas y alertas OK; panel DEGRADADO (planning DOWN) | Sí | /health 1.9 s; negocio 2.0 s; healthy 6.3 s |
| 2. Redis no responde | Respaldo de sesión en PostgreSQL; fail-closed; importación 503 | Tokens previos aceptados (respaldo PG); token revocado rechazado; importación y carrito 503; rate limit abierto. Pero las peticiones tardan de 5 a 28 s, los tokens emitidos durante la caída se invalidan al volver Redis y alerts/scan da 409 | Parcial | /health 0.6 s; negocio 0.6 s; healthy 15.7 s |
| 3. MongoDB no responde | Alertas 503 «MongoDB no está disponible»; inventario y FEFO siguen | Inventario, FEFO, checkout y login OK. Pero alerts/active da **200 con lista vacía**, ASN **500** y forecast/latest **404** | No | /health y negocio 4.3 s; healthy 6.6 s |
| 4. PostgreSQL no responde | Errores seguros, /health 503 y reconexión sola | /health 503 en los 9; 500 `error_interno` sin trazas y con correlation_id; la web da 500 con referencia. Pero los tokens válidos reciben **401 token_invalido** | Parcial | pg_isready 0.8 s; /health y negocio 0.1 s después; healthy 10.9 s; sin reiniciar servicios |
| 5. Bucket (MinIO) no disponible | Evidencia 503 almacenamiento_no_disponible; PDFs | Evidencia 503; merma sin foto 201; PDFs de OC y ASN servidos desde la copia local; OC nueva 201 (local_fallback). Pero los 8 servicios pasan a 503 y Docker los marca unhealthy a los 76 s | Parcial | /health 0.6 s; healthy 15.5 s |
| 6. Petición excede el tiempo máximo | El llamador no se queda colgado | planning en pausa: el cliente de 20 s corta a 20.0 s; gateway 502 a 30.0 s; /pronostico 200 a los 10.5 s con datos locales; el panel lo marca DOWN. Redis en pausa: cada petición tarda 16 s. PG en pausa: token 401 a los 5 s, pero /health de servicios y web **colgado más de 45 s** | Parcial | Inmediata al reanudar (0.0–0.1 s) |
| 7. Archivos grandes | ≤ 8 MB → 201; > 8 MB → 413; no imagen → 415 | 1 KB y 3.9 MB → 201; **4.1 MB y 7.9 MB → 413**; 8.1 MB → 413; PDF renombrado y texto → 415; vacío → 400; XML de 5.5 MB → 413 | No (límite real de 4 MB) | n/a |
| 8. Recuperación | Sin reiniciar servicios | Todos reconectan solos (PG por pool_pre_ping; Redis y Mongo por sus drivers); /health verde en ≤ 4.3 s y contenedores healthy en ≤ 16 s | Sí | ver filas anteriores |

## 1. Se detiene un microservicio (svc-planning)

**Pasos:** `docker stop freshtrack_svc_planning` a las 13:23:31 CST.

| Cliente o vista | Resultado |
|---|---|
| Cliente directo (escritorio o Android en modo local) | Conexión rechazada en 4 ms. Según sus README, la app de escritorio muestra «El servicio planning no está disponible» y Android «Servicio degradado: Planeación» (no verificado aquí; solo se probó el HTTP). |
| Gateway web `/svc/planning/...` | HTTP 502 `{"error":"servicio_no_disponible","mensaje":"svc-planning no respondió."}` en 4 s, sin correlation_id. |
| Web `/reabastecimiento` | 200; lee PostgreSQL directamente. |
| Web `/pronostico` | 200 con respaldo local. |
| Web, botón «Generar» | 302 con el aviso «No se generaron recomendaciones: El módulo solicitado no está disponible en este momento. Intenta de nuevo en unos segundos.» |
| Otros servicios | inventory 200, checkout 201, alerts 200. |
| Monitoreo | planning sin respuesta en /health; los demás HEALTHY. Panel DEGRADADO: 7 sanos, 1 caído, 87.5 %. |

**Recuperación** (`docker start`): /health 1.9 s, primer GET de transferencias 2.0 s, contenedor healthy 6.3 s; el panel vuelve a OPERATIVO. **Cumple.**

## 2. Redis no responde

**Pasos:** `docker stop freshtrack_redis` (corrida final a las ~13:43; la corrida 1, `redis_corrida1.txt`, dio resultados equivalentes).

**Autenticación**
- Token emitido antes de la caída: 200 (respaldo en PostgreSQL), con 12.7 s la primera vez.
- Login nuevo: 200, y su token sirve durante la caída.
- Logout durante la caída: 200. Después ese token se rechaza con 401 `token_invalido` porque PostgreSQL lo marca revocado (fail-closed correcto).

**Rate limit:** 12 logins fallidos seguidos dan 12 × 401, sin ningún 429. El limitador queda abierto (fail-open), como dice el código.

**Operaciones que usan Redis**
- Catálogo: 200 desde PostgreSQL, pero en 28.2 s.
- Importación de ventas: 503 `redis_no_disponible` «importación interrumpida» en 21 s, sin importar nada.
- Carrito: 503 en 12.8 s.
- Checkout: 201 en 5.6 s (22.5 s en la corrida 1).
- alerts/scan: **409 `escaneo_en_curso`** (engañoso; debería ser 503).

**Web:** la sesión abierta sigue funcionando (/inventario 200 en 2–11 s) y el login nuevo funciona.

**Monitoreo:** la web da 200 DEGRADED; los 8 servicios 503 DEGRADED (redis=false); el panel queda DEGRADADO.

**Recuperación:** /health y primer carrito en 0.6 s; healthy en 15.7 s. El token emitido antes de la caída sigue con 200 y el revocado sigue con 401. **El token emitido durante la caída da 401 `sesion_inexistente`, así que ese usuario es expulsado (BUG).**

**Cumple parcialmente.**

## 3. MongoDB no responde

**Pasos:** `docker stop freshtrack_mongo` a las 13:31:40 CST.

**Lo que falla**
- alerts/active: **200 `{"total":0,"alertas":[]}`** en 2.6 s, en lugar del 503 documentado.
- alerts/analytics/kpis: 200 vacío.
- asn (listado): **500 `error_interno`** (el log muestra ServerSelectionTimeoutError).
- forecast/latest/9/3: **404 «Sin corrida previa»**.
- forecast/run: 201, pero tardó 32 s.

**Lo que sigue funcionando**
- audit/events: 200 (PostgreSQL).
- Inventario y FEFO: 200.
- Checkout: 201.
- Login: 200.
- Web /alertas, /panel e /inventario: 200; /despachos 200 en 2.8 s.

**Monitoreo:** los 8 servicios dan 503 DEGRADED; el panel queda DEGRADADO con «deps caídas: MongoDB».

**Causa:** `doc_store.get_mongo_db()` guarda `_db` en memoria. Si Mongo cae después del arranque, la verificación que debería responder 503 (`_mongo()`) nunca se activa y los listados se tragan el error.

**Recuperación:** 4.3 s (/health y alertas); healthy en 6.6 s. **No cumple** el 503 documentado.

## 4. PostgreSQL no responde

**Pasos:** `docker stop freshtrack_db` a las 13:32:54 CST.

**Servicios**
- /health: los 9 dan 503 DEGRADED (postgres=false) en ~0.25 s; la web en 1.7 s.
- Login: 500 `error_interno` con correlation_id.
- Catálogo: 500 en 4.8 s.
- Con token válido (inventory, commercial, alerts, asn, audit): **401 `token_invalido` «Token inválido, expirado o manipulado»**. Validar la sesión requiere PostgreSQL, y un cliente móvil mandaría al usuario al login en vez de mostrar «servicio no disponible».
- Sin token: 401 `token_requerido`.

**Web**
- /inventario y /ventas: página «Error 500 … reporta la referencia 3f52cfa8b9».
- Login: «Ocurrió un error inesperado. Consulte el log con el correlation_id», pero no muestra el id.

Ninguna respuesta filtra trazas, SQL ni psycopg.

**Panel:** DEGRADADO; svc-auth aparece DOWN por su timeout de 5 s.

**Recuperación, sin reiniciar servicios:** pg_isready a los 0.8 s; /health y la primera operación OK 0.1 s después; healthy en 10.9 s. El token y la sesión web emitidos antes siguen funcionando (200).

**Cumple parcialmente** (401 en lugar de 503).

## 5. Servicio de archivos (MinIO) no disponible

**Pasos:** `docker stop freshtrack_minio` a las 13:33:33 CST.

**PDFs**
- PDF de una OC existente: 200 desde la copia local (382 ms).
- PDF de etiquetas del ASN: 200.
- Web /compras/ordenes/<id>/pdf: 200.
- OC nueva: 201 con `storage_provider: local_fallback`; su PDF se descarga con 200. Al volver el bucket **no se sube** (no aparece en MinIO).

**Evidencias**
- POST /commercial/evidence: **503 `almacenamiento_no_disponible`** «El almacenamiento de archivos no está disponible; la operación puede registrarse sin foto.»
- Merma sin foto: 201.

**Salud**
- La web da 200 DEGRADED y los 8 servicios 503.
- El panel los clasifica CRITICO: 5 DOWN y 3 DEGRADED, aunque los procesos funcionan.
- Docker marcó **unhealthy** auth, catalog, inventory, commercial, asn, planning, alerts y audit a los 76 s (healthcheck de 15 s × 5).

**Recuperación:** /health y primera evidencia 201 en 0.6 s; healthy en 15.5 s. **La funcionalidad cumple**; lo que falla es el criterio de salud.

## 6. Petición que excede el tiempo máximo

**Timeouts configurados**

| Componente | Timeout |
|---|---|
| Web → servicio (`clientes.llamar`) | 3 s |
| `como_usuario` | 15 s (`/reabastecimiento/generar`: 120 s) |
| Gateway `/svc` | 30 s |
| PDF | 20 s |
| /health en el panel | 5 s |
| Redis | connect 2 s, socket 2 s |
| Mongo | serverSelection 2.5 s |
| PostgreSQL | connect_timeout 5 s y pool_timeout 10 s; **sin statement timeout** |
| S3 | 8 s (subida 15 s, salud 2 s) |
| gunicorn en producción | 60 s (web 90 s, planning 120 s) |
| Caddy | sin timeouts explícitos |
| App de escritorio | **15 s** |
| Android | read 20 s, connect 10 s, call 90 s; Estado de servicios 5 s; refresh 15 s |

**A) `docker pause` de svc-planning (30 s)**
- El cliente con timeout de 20 s cortó (ReadTimeout) a los 20.0 s.
- El gateway web respondió 502 `servicio_no_disponible` a los 30.0 s.
- /pronostico respondió 200 a los 10.5 s (timeout de drift más respaldo local).
- El panel lo marcó DOWN en 4 s; inventory siguió respondiendo 200 en 147 ms.
- La recuperación fue inmediata.

**B) `docker pause` de Redis**
- Inventario con token válido: 200 en 16.1 s, tres veces seguidas.
- svc-auth /health: 503 en 2 s.
- Recuperación en 0.1 s.

**C) `docker pause` de PostgreSQL (45 s)**
- Petición con token: 401 `token_invalido` a los 5 s.
- **/health de inventory y de la web: sin respuesta tras 45 s (cuelgue).**
- Al reanudar todo respondió en 0.1 s. Docker marcó temporalmente unhealthy a db, auth, catalog, commercial y audit.

**Cumple parcialmente:** los clientes no se cuelgan porque tienen timeout, pero el servidor sí se puede quedar colgado con PostgreSQL congelado. La corrida 1 quedó cortada por el apagado de Docker Desktop (`timeout_corrida1_interrumpida.txt`).

## 7. Archivos grandes

POST /commercial/evidence como gerente:

| Archivo | Resultado |
|---|---|
| 1 KB | 201 |
| 3.9 MB | 201 |
| **4.1 MB** | **413** `cuerpo_demasiado_grande` «The data value transmitted exceeds the capacity limit.» |
| **7.9 MB** | **413** |
| 8.1 MB | 413 |
| PDF renombrado a .jpg | 415 `tipo_no_soportado` (detectado por magic bytes) |
| Texto plano | 415 |
| Archivo vacío | 400 `archivo_vacio` |

También:
- Un XML de importación de 5.5 MB da 413.
- El gateway web con 5 MB devuelve 413 en HTML de Werkzeug.

**Causa:** `Config.MAX_CONTENT_LENGTH = 4 MB` (`app/config.py`) aplica a todos los servicios antes de la validación de 8 MB del endpoint. **No cumple** lo documentado en `android-app/README.md`.

## 8. Recuperación

Ningún escenario requirió reiniciar servicios: los pools y los clientes reconectan solos.

| Escenario | /health en verde | Primera operación de negocio | Contenedores healthy |
|---|---|---|---|
| planning | 1.9 s | 2.0 s | 6.3 s |
| Redis | 0.6 s | 0.6 s | 15.7 s |
| Mongo | 4.3 s | 4.3 s | 6.6 s |
| PostgreSQL | 0.8 s + 0.1 s | 0.1 s | 10.9 s |
| MinIO | 0.6 s | 0.6 s | 15.5 s |
| Pausas | 0.0–0.1 s | — | — |

## Hallazgos

1. **(Alta)** Los clientes de Redis y Mongo se guardan en memoria (`cache_service.get_redis_client`, `doc_store.get_mongo_db`). Con Redis caído cada petición tarda de 5 a 28 s, más que el timeout del escritorio (15 s) y de Android (20 s), y checkout y merma no son idempotentes. Con Mongo caído, alertas da 200 vacío, ASN 500 y pronóstico 404 en vez del 503 documentado.
2. **(Alta)** Con PostgreSQL caído, los tokens válidos reciben 401 `token_invalido` y las apps fuerzan logout; debería ser 503.
3. **(Alta)** El límite efectivo de fotos es 4 MB, no 8 MB (MAX_CONTENT_LENGTH global), y el mensaje del 413 sale en inglés.
4. **(Media)** Los tokens emitidos con Redis caído quedan inválidos (`sesion_inexistente`) cuando Redis vuelve.
5. **(Media)** No hay statement timeout ni timeout de socket hacia PostgreSQL: con la base congelada, /health se cuelga más de 45 s.
6. **(Media)** /health exige las 4 dependencias, así que con MinIO o Mongo caídos los 8 servicios dan 503 y Docker los marca unhealthy. Además, `/ops/status` (timeout de 5 s) reporta como DOWN servicios que solo están DEGRADED.
7. **(Media)** Con Redis caído, `alerts/scan` da 409 `escaneo_en_curso` en vez de 503, y el rate limit queda abierto (fail-open) sin aviso.
8. **(Baja)** El PDF de una OC creada con el bucket caído queda como `local_fallback` y no se sincroniza cuando el bucket vuelve.
9. **(Baja)** El 502 del gateway web no incluye correlation_id, y el login web con PG caído pide «consultar el correlation_id» sin mostrarlo.
10. **(Documentación)** El timeout real de la app de escritorio es 15 s, no 20 s.

**Limitaciones:**
- Las reacciones de las apps de escritorio y Android se tomaron de sus README; aquí solo se verificó el HTTP.
- Caddy y gunicorn solo existen en producción y no se probaron, porque la regla era no tocar la VM.
