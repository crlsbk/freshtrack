# Evidencias de petición y respuesta — Microservicios FreshTrack

Generado el 2026-10-23 23:46 con `python scripts/generar_evidencias.py --host 127.0.0.1` mediante peticiones HTTP reales contra los contenedores. Los tokens se muestran abreviados.

**88 de 88 casos** respondieron con el código esperado.

| # | Servicio | Método | Ruta | Objetivo | Esperado | Obtenido |
|---|---|---|---|---|---|---|
| [1](#caso-1) | svc-auth | POST | `/api/v1/auth/login` | Inicio de sesión correcto (JSON): emite JWT y crea session:{jti} en Redis | 200 | ✅ 200 |
| [2](#caso-2) | svc-auth | POST | `/api/v1/auth/login` | Inicio de sesión con cuerpo XML y respuesta XML | 200 | ✅ 200 |
| [3](#caso-3) | svc-auth | POST | `/api/v1/auth/login` | Credenciales incorrectas (no revela si el correo existe) | 401 | ✅ 401 |
| [4](#caso-4) | svc-auth | POST | `/api/v1/auth/login` | XML que no cumple login_request.xsd | 400 | ✅ 400 |
| [5](#caso-5) | svc-auth | POST | `/api/v1/auth/login` | Cuenta desactivada | 401 | ✅ 401 |
| [6](#caso-6) | svc-auth | POST | `/api/v1/auth/verify` | Verificación de token (firma, vigencia, sesión Redis, denylist) | 200 | ✅ 200 |
| [7](#caso-7) | svc-auth | GET | `/api/v1/auth/me` | Perfil del usuario del token | 200 | ✅ 200 |
| [8](#caso-8) | svc-auth | GET | `/api/v1/auth/users?rol=store_manager&pagina=1&por_pagina=5` | Usuarios filtrados y paginados (admin) | 200 | ✅ 200 |
| [9](#caso-9) | svc-auth | GET | `/api/v1/auth/users` | Rol sin permiso intenta listar usuarios | 403 | ✅ 403 |
| [10](#caso-10) | svc-auth | GET | `/api/v1/auth/users` | Petición sin token | 401 | ✅ 401 |
| [11](#caso-11) | svc-auth | GET | `/api/v1/auth/sessions/no-es-uuid` | Parámetro de ruta inválido | 400 | ✅ 400 |
| [12](#caso-12) | svc-auth | GET | `/api/v1/auth/sessions/c1f89119-9220-4071-a87a-cd71d3eeb862` | Usuario inexistente | 404 | ✅ 404 |
| [13](#caso-13) | svc-auth | GET | `/api/v1/auth/sessions/f14c3ee2-1985-4e26-9915-45c26503a876` | Sesiones activas en Redis con TTL restante | 200 | ✅ 200 |
| [14](#caso-14) | svc-auth | DELETE | `/api/v1/auth/sessions/f14c3ee2-1985-4e26-9915-45c26503a876` | Cierre forzado de todas las sesiones de un usuario | 200 | ✅ 200 |
| [15](#caso-15) | svc-planning | GET | `/api/v1/planning/replenishment/orders` | El token del usuario cuyas sesiones se cerraron ya no sirve en otro servicio | 401 | ✅ 401 |
| [16](#caso-16) | svc-auth | GET | `/api/v1/auth/counters?servicio=auth` | Contadores de operación en Redis | 200 | ✅ 200 |
| [17](#caso-17) | svc-auth | POST | `/api/v1/auth/logout` | Logout: revoca en PostgreSQL y agrega jti a la denylist de Redis | 200 | ✅ 200 |
| [18](#caso-18) | svc-inventory | GET | `/api/v1/inventory/stock` | Token revocado usado en OTRO microservicio | 401 | ✅ 401 |
| [19](#caso-19) | svc-inventory | GET | `/api/v1/inventory/stock` | Token con firma alterada | 401 | ✅ 401 |
| [20](#caso-20) | svc-catalog | GET | `/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3` | Productos filtrados y paginados (Cache-Aside: 1.ª vez PostgreSQL) | 200 | ✅ 200 |
| [21](#caso-21) | svc-catalog | GET | `/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3` | Misma consulta servida desde caché Redis (campo fuente y TTL) | 200 | ✅ 200 |
| [22](#caso-22) | svc-catalog | GET | `/api/v1/catalog/products?por_pagina=2` | Respuesta en XML | 200 | ✅ 200 |
| [23](#caso-23) | svc-catalog | GET | `/api/v1/catalog/products?pagina=0` | Parámetro de paginación inválido | 400 | ✅ 400 |
| [24](#caso-24) | svc-catalog | POST | `/api/v1/catalog/products` | Alta de producto con XML validado contra producto_request.xsd | 201 | ✅ 201 |
| [25](#caso-25) | svc-catalog | GET | `/api/v1/catalog/products/20` | Detalle por SKU | 200 | ✅ 200 |
| [26](#caso-26) | svc-catalog | PATCH | `/api/v1/catalog/products/20` | Actualización parcial (PATCH) | 200 | ✅ 200 |
| [27](#caso-27) | svc-catalog | PUT | `/api/v1/catalog/products/20` | Reemplazo completo (PUT) | 200 | ✅ 200 |
| [28](#caso-28) | svc-catalog | PATCH | `/api/v1/catalog/products/20` | Regla de negocio: precio de venta menor al costo | 409 | ✅ 409 |
| [29](#caso-29) | svc-catalog | POST | `/api/v1/catalog/products` | Campos obligatorios faltantes | 400 | ✅ 400 |
| [30](#caso-30) | svc-catalog | DELETE | `/api/v1/catalog/products/20` | Baja reservada a admin | 403 | ✅ 403 |
| [31](#caso-31) | svc-catalog | DELETE | `/api/v1/catalog/products/20` | Baja lógica (activo=false) | 200 | ✅ 200 |
| [32](#caso-32) | svc-catalog | GET | `/api/v1/catalog/products/99999999` | SKU inexistente | 404 | ✅ 404 |
| [33](#caso-33) | svc-catalog | GET | `/api/v1/catalog/locations?tipo=Tienda` | Tiendas (Cache-Aside) | 200 | ✅ 200 |
| [34](#caso-34) | svc-inventory | GET | `/api/v1/inventory/stock?id_locacion=3&dias_max=7&por_pagina=5` | Existencias por vencer en ≤7 días (paginado, orden FEFO) | 200 | ✅ 200 |
| [35](#caso-35) | svc-inventory | GET | `/api/v1/inventory/fefo-queue/1/3` | Cola FEFO en XML | 200 | ✅ 200 |
| [36](#caso-36) | svc-inventory | GET | `/api/v1/inventory/fefo-queue/99999999/3` | SKU inexistente en la cola FEFO | 404 | ✅ 404 |
| [37](#caso-37) | svc-inventory | POST | `/api/v1/inventory/reserve-fefo` | Reserva FEFO con lock distribuido en Redis (XML) | 200 | ✅ 200 |
| [38](#caso-38) | svc-inventory | POST | `/api/v1/inventory/cancel-reservation` | Compensación: libera la reserva guardada en Redis | 200 | ✅ 200 |
| [39](#caso-39) | svc-inventory | POST | `/api/v1/inventory/reserve-fefo` | Stock insuficiente (rollback) | 409 | ✅ 409 |
| [40](#caso-40) | svc-inventory | POST | `/api/v1/inventory/reserve-fefo` | Tipo de dato inválido | 400 | ✅ 400 |
| [41](#caso-41) | svc-inventory | POST | `/api/v1/inventory/reserve-fefo` | Auditor no puede reservar | 403 | ✅ 403 |
| [42](#caso-42) | svc-commercial | POST | `/api/v1/commercial/checkout` | Venta POS por Saga: reserva FEFO → venta → descuento de existencias | 201 | ✅ 201 |
| [43](#caso-43) | svc-commercial | POST | `/api/v1/commercial/checkout` | Venta rechazada por stock (compensación de la saga, respuesta XML) | 409 | ✅ 409 |
| [44](#caso-44) | svc-commercial | POST | `/api/v1/commercial/checkout` | XML que no cumple checkout_request.xsd | 400 | ✅ 400 |
| [45](#caso-45) | svc-commercial | PUT | `/api/v1/commercial/cart/caja1-aa5a` | Carrito temporal en Redis (TTL 15 min) | 200 | ✅ 200 |
| [46](#caso-46) | svc-commercial | GET | `/api/v1/commercial/cart/caja1-aa5a` | Consulta del carrito con TTL restante | 200 | ✅ 200 |
| [47](#caso-47) | svc-commercial | DELETE | `/api/v1/commercial/cart/caja1-aa5a` | Consumo atómico (GET+DEL en Lua) | 200 | ✅ 200 |
| [48](#caso-48) | svc-commercial | GET | `/api/v1/commercial/cart/caja1-aa5a` | Carrito ya consumido | 404 | ✅ 404 |
| [49](#caso-49) | svc-commercial | POST | `/api/v1/commercial/shrinkage` | Merma sobre un lote que no existe | 409 | ✅ 409 |
| [50](#caso-50) | svc-commercial | POST | `/api/v1/commercial/shrinkage` | Causa de merma inválida | 400 | ✅ 400 |
| [51](#caso-51) | svc-commercial | GET | `/api/v1/commercial/sales?id_locacion=3&desde=2026-09-23&por_pagina=3` | Historial de ventas por rango de fechas | 200 | ✅ 200 |
| [52](#caso-52) | svc-asn | POST | `/api/v1/asn` | Ingesta de ASN en XML (validado con asn_request.xsd) → documento en MongoDB | 201 | ✅ 201 |
| [53](#caso-53) | svc-asn | POST | `/api/v1/asn` | Folio duplicado (índice único en MongoDB) | 409 | ✅ 409 |
| [54](#caso-54) | svc-asn | POST | `/api/v1/asn` | SKU inexistente en PostgreSQL (integración PG↔Mongo) | 409 | ✅ 409 |
| [55](#caso-55) | svc-asn | GET | `/api/v1/asn/ASN-EV-32F77E` | Recuperación por folio | 200 | ✅ 200 |
| [56](#caso-56) | svc-asn | PATCH | `/api/v1/asn/ASN-EV-32F77E/status` | Transición de estado inválida | 409 | ✅ 409 |
| [57](#caso-57) | svc-asn | PATCH | `/api/v1/asn/ASN-EV-32F77E/status` | Actualización de documento ($set) | 200 | ✅ 200 |
| [58](#caso-58) | svc-asn | POST | `/api/v1/asn/ASN-EV-32F77E/inspection` | Inspección agregada con $push | 201 | ✅ 201 |
| [59](#caso-59) | svc-asn | GET | `/api/v1/asn?id_sku=2&estado=EN_TRANSITO&por_pagina=5` | Filtrado por campo anidado y estado | 200 | ✅ 200 |
| [60](#caso-60) | svc-asn | GET | `/api/v1/asn/analytics/summary` | Pipeline de agregación ($unwind/$group/$sort) | 200 | ✅ 200 |
| [61](#caso-61) | svc-asn | GET | `/api/v1/asn/NO-EXISTE` | Folio inexistente | 404 | ✅ 404 |
| [62](#caso-62) | svc-planning | POST | `/api/v1/planning/forecast/run` | Corrida de pronóstico (linaje en PostgreSQL, serie en MongoDB) | 201 | ✅ 201 |
| [63](#caso-63) | svc-planning | POST | `/api/v1/planning/forecast/run` | Método no soportado | 400 | ✅ 400 |
| [64](#caso-64) | svc-planning | GET | `/api/v1/planning/forecast/latest/1/3` | Última serie pronosticada (MongoDB) | 200 | ✅ 200 |
| [65](#caso-65) | svc-planning | GET | `/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=3` | Órdenes pendientes paginadas | 200 | ✅ 200 |
| [66](#caso-66) | svc-planning | POST | `/api/v1/planning/replenishment/orders/18269bf6-d12e-4ed2-b12a-a94af6c674f9/approve` | Aprobar orden inexistente | 404 | ✅ 404 |
| [67](#caso-67) | svc-planning | GET | `/api/v1/planning/sku/1/full-context?id_locacion=3` | Contexto híbrido PostgreSQL + MongoDB | 200 | ✅ 200 |
| [68](#caso-68) | svc-planning | GET | `/api/v1/planning/forecast/analytics/kpis` | Métricas por modelo (agregación) | 200 | ✅ 200 |
| [69](#caso-69) | svc-alerts | POST | `/api/v1/alerts/scan?id_locacion=3&dias=5` | Escaneo con lock distribuido → alertas en MongoDB + eventos en Redis Streams | 200 | ✅ 200 |
| [70](#caso-70) | svc-alerts | GET | `/api/v1/alerts/active?id_locacion=3&limite=3` | Alertas abiertas filtradas | 200 | ✅ 200 |
| [71](#caso-71) | svc-alerts | PATCH | `/api/v1/alerts/6adc4624976c8bfea977970a/resolve` | Atender alerta (inicia retención TTL) | 200 | ✅ 200 |
| [72](#caso-72) | svc-alerts | PATCH | `/api/v1/alerts/zzz/resolve` | ObjectId inválido | 400 | ✅ 400 |
| [73](#caso-73) | svc-alerts | GET | `/api/v1/alerts/esg/carbon-avoided` | Reporte ESG en XML | 200 | ✅ 200 |
| [74](#caso-74) | svc-alerts | GET | `/api/v1/alerts/analytics/kpis` | Alertas por locación y criticidad (agregación) | 200 | ✅ 200 |
| [75](#caso-75) | svc-audit | POST | `/api/v1/audit/log` | Registro explícito de cumplimiento (identidad tomada del JWT) | 201 | ✅ 201 |
| [76](#caso-76) | svc-audit | GET | `/api/v1/audit/events?accion=REVISION_CUMPLIMIENTO&por_pagina=3` | Bitácora filtrada y paginada | 200 | ✅ 200 |
| [77](#caso-77) | svc-audit | GET | `/api/v1/audit/events?desde=2026-13-01` | Fecha inválida | 400 | ✅ 400 |
| [78](#caso-78) | svc-audit | GET | `/api/v1/audit/events` | Gerente sin permiso sobre la bitácora | 403 | ✅ 403 |
| [79](#caso-79) | svc-audit | GET | `/api/v1/audit/traceability/no-es-uuid` | Identificador de lote inválido | 400 | ✅ 400 |
| [80](#caso-80) | svc-audit | GET | `/api/v1/audit/stream/recent?n=5` | Eventos de dominio en Redis Streams | 200 | ✅ 200 |
| [81](#caso-81) | svc-auth | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [82](#caso-82) | svc-catalog | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [83](#caso-83) | svc-inventory | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [84](#caso-84) | svc-commercial | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [85](#caso-85) | svc-asn | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [86](#caso-86) | svc-planning | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [87](#caso-87) | svc-alerts | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [88](#caso-88) | svc-audit | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |

<a id="caso-1"></a>
## 1. svc-auth — POST /api/v1/auth/login

- **Objetivo:** Inicio de sesión correcto (JSON): emite JWT y crea session:{jti} en Redis
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/login`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Content-Type: application/json
X-Correlation-Id: 2ecfbd0aa6d043f2
```

**Cuerpo de la petición:**

```json
{
  "email": "gerente@freshtrack.mx",
  "password": "Tienda2026!"
}
```

**Respuesta (application/json):**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkMjJlMjE2ZS1mYzA4LTQ1MTQtYmIxNS05MzQyNTZlMjYyYWQiLCJlbWFpbCI6ImdlcmVudGVAZnJlc2h0cmFjay5teCIsIm5vbWJyZSI6Ikx1aXMgUFx1MDBlOXJleiIsInJvbCI6InN0b3JlX21hbmFnZXIiLCJpZF9sb2NhY2lvbiI6MywianRpIjoiZDJiMDZlZjEyOTI3NGM0OTlmYjNjNzM2ZjcyOGQwMzQiLCJpYXQiOjE3OTI4MjA3NzAsImV4cCI6MTc5Mjg0OTU3MCwiaXNzIjoiZnJlc2h0cmFjayJ9.L3mN0MTmPL8DZzMos_zvje5W6b27srnSON4P9uaBHSE",
  "jti": "d2b06ef129274c499fb3c736f728d034",
  "token_type": "Bearer",
  "expira_en_segundos": 28800,
  "usuario": {
    "id_usuario": "d22e216e-fc08-4514-bb15-934256e262ad",
    "email": "gerente@freshtrack.mx",
    "nombre": "Luis Pérez",
    "rol": "store_manager",
    "id_locacion": 3
  }
}
```

<a id="caso-2"></a>
## 2. svc-auth — POST /api/v1/auth/login

- **Objetivo:** Inicio de sesión con cuerpo XML y respuesta XML
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/login`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Content-Type: application/xml
Accept: application/xml
X-Correlation-Id: 499dcc828f9d4b9c
```

**Cuerpo de la petición:**

```xml
<login_request><email>auditor@freshtrack.mx</email><password>Auditor2026!</password></login_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<auth_response><token>eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5ODA4MWFiNS0xY2FhLTQ5MDQtYmY1YS04MzZhZDI0ZDg1NjMiLCJlbWFpbCI6ImF1ZGl0b3JAZnJlc2h0cmFjay5teCIsIm5vbWJyZSI6IklybWEgU2FsaW5hcyIsInJvbCI6ImF1ZGl0b3IiLCJpZF9sb2NhY2lvbiI6MSwianRpIjoiMDFlZGJlMjY2NzcxNDVhYWJhZDZjNzkzYWI3NDExYTIiLCJpYXQiOjE3OTI4MjA3NzEsImV4cCI6MTc5Mjg0OTU3MSwiaXNzIjoiZnJlc2h0cmFjayJ9.q7_Pn34vH7bUt7jDNR4oNDE0-XJvdOyYrzi2krLqIxw</token><jti>01edbe26677145aabad6c793ab7411a2</jti><token_type>Bearer</token_type><expira_en_segundos>28800</expira_en_segundos><usuario><id_usuario>98081ab5-1caa-4904-bf5a-836ad24d8563</id_usuario><email>auditor@freshtrack.mx</email><nombre>Irma Salinas</nombre><rol>auditor</rol><id_locacion>1</id_locacion></usuario></auth_response>
```

<a id="caso-3"></a>
## 3. svc-auth — POST /api/v1/auth/login

- **Objetivo:** Credenciales incorrectas (no revela si el correo existe)
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/login`
- **Código HTTP:** `401` (esperado `401`)
- **Headers:**

```http
Content-Type: application/json
X-Correlation-Id: afa77a5c5efa47f2
```

**Cuerpo de la petición:**

```json
{
  "email": "admin@freshtrack.mx",
  "password": "equivocada"
}
```

**Respuesta (application/json):**

```json
{
  "error": "credenciales_invalidas",
  "mensaje": "Correo o contraseña incorrectos.",
  "status": 401,
  "correlation_id": "afa77a5c5efa47f2"
}
```

<a id="caso-4"></a>
## 4. svc-auth — POST /api/v1/auth/login

- **Objetivo:** XML que no cumple login_request.xsd
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/login`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Content-Type: application/xml
X-Correlation-Id: 7ba68e4674164780
```

**Cuerpo de la petición:**

```xml
<login_request><email>no-es-correo</email></login_request>
```

**Respuesta (application/json):**

```json
{
  "error": "xml_no_cumple_contrato",
  "mensaje": "El XML no cumple el contrato login_request.xsd",
  "status": 400,
  "correlation_id": "7ba68e4674164780",
  "detalles": [
    {
      "ruta": "/login_request/email",
      "motivo": "value doesn't match any pattern of ['[^@\\\\s]+@[^@\\\\s]+\\\\.[^@\\\\s]+']"
    },
    {
      "ruta": "/login_request",
      "motivo": "The content of element 'login_request' is not complete. Tag 'password' expected."
    }
  ]
}
```

<a id="caso-5"></a>
## 5. svc-auth — POST /api/v1/auth/login

- **Objetivo:** Cuenta desactivada
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/login`
- **Código HTTP:** `401` (esperado `401`)
- **Headers:**

```http
Content-Type: application/json
X-Correlation-Id: 078f995be5784939
```

**Cuerpo de la petición:**

```json
{
  "email": "inactivo@freshtrack.mx",
  "password": "Inactivo2026!"
}
```

**Respuesta (application/json):**

```json
{
  "error": "credenciales_invalidas",
  "mensaje": "Esta cuenta está desactivada. Contacta al administrador.",
  "status": 401,
  "correlation_id": "078f995be5784939"
}
```

<a id="caso-6"></a>
## 6. svc-auth — POST /api/v1/auth/verify

- **Objetivo:** Verificación de token (firma, vigencia, sesión Redis, denylist)
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/verify`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: c644e84bc0de42bd
```

**Respuesta (application/json):**

```json
{
  "valido": true,
  "usuario": {
    "id_usuario": "0b762fd5-c616-4f6b-81cd-54acbb43abf1",
    "email": "almacen@freshtrack.mx",
    "nombre": "Pedro Vargas",
    "rol": "warehouse",
    "id_locacion": 3
  },
  "sesion_ttl_segundos": 28800
}
```

<a id="caso-7"></a>
## 7. svc-auth — GET /api/v1/auth/me

- **Objetivo:** Perfil del usuario del token
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/me`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: fe94836aa6184aef
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "2245d1e2-4a25-4b92-a480-1426f58d7e73",
  "email": "buyer@freshtrack.mx",
  "nombre": "Martha López",
  "rol": "buyer",
  "id_locacion": 1
}
```

<a id="caso-8"></a>
## 8. svc-auth — GET /api/v1/auth/users

- **Objetivo:** Usuarios filtrados y paginados (admin)
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/users?rol=store_manager&pagina=1&por_pagina=5`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 222a9701330b447a
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 5,
    "total": 2,
    "total_paginas": 1
  },
  "usuarios": [
    {
      "id_usuario": "71a3b469-dbfd-47c2-bf73-3d661a70e1a0",
      "email": "gerente2@freshtrack.mx",
      "nombre_completo": "Ana Ruiz",
      "rol": "store_manager",
      "id_locacion": 4,
      "estado_activo": true,
      "fecha_alta": "2026-10-23T20:57:24.367662+00:00"
    },
    {
      "id_usuario": "d22e216e-fc08-4514-bb15-934256e262ad",
      "email": "gerente@freshtrack.mx",
      "nombre_completo": "Luis Pérez",
      "rol": "store_manager",
      "id_locacion": 3,
      "estado_activo": true,
      "fecha_alta": "2026-10-23T20:57:24.367662+00:00"
    }
  ]
}
```

<a id="caso-9"></a>
## 9. svc-auth — GET /api/v1/auth/users

- **Objetivo:** Rol sin permiso intenta listar usuarios
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/users`
- **Código HTTP:** `403` (esperado `403`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: b99106ca726d45cc
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'auditor' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "b99106ca726d45cc",
  "detalles": {
    "roles_permitidos": [
      "admin"
    ]
  }
}
```

<a id="caso-10"></a>
## 10. svc-auth — GET /api/v1/auth/users

- **Objetivo:** Petición sin token
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/users`
- **Código HTTP:** `401` (esperado `401`)
- **Headers:**

```http
X-Correlation-Id: c38d1ff6d70f4864
```

**Respuesta (application/json):**

```json
{
  "error": "token_requerido",
  "mensaje": "Token de autenticación requerido (Authorization: Bearer <token>).",
  "status": 401,
  "correlation_id": "c38d1ff6d70f4864"
}
```

<a id="caso-11"></a>
## 11. svc-auth — GET /api/v1/auth/sessions/no-es-uuid

- **Objetivo:** Parámetro de ruta inválido
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/sessions/no-es-uuid`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 250e4306a3af45a0
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_usuario' debe ser un UUID válido.",
  "status": 400,
  "correlation_id": "250e4306a3af45a0"
}
```

<a id="caso-12"></a>
## 12. svc-auth — GET /api/v1/auth/sessions/c1f89119-9220-4071-a87a-cd71d3eeb862

- **Objetivo:** Usuario inexistente
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/sessions/c1f89119-9220-4071-a87a-cd71d3eeb862`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 0ec144feda5c476b
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Usuario c1f89119-9220-4071-a87a-cd71d3eeb862 no encontrado.",
  "status": 404,
  "correlation_id": "0ec144feda5c476b"
}
```

<a id="caso-13"></a>
## 13. svc-auth — GET /api/v1/auth/sessions/f14c3ee2-1985-4e26-9915-45c26503a876

- **Objetivo:** Sesiones activas en Redis con TTL restante
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/sessions/f14c3ee2-1985-4e26-9915-45c26503a876`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: db6924ec7fc246ec
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "f14c3ee2-1985-4e26-9915-45c26503a876",
  "total_activas": 2,
  "sesiones": [
    {
      "id_usuario": "f14c3ee2-1985-4e26-9915-45c26503a876",
      "email": "planner@freshtrack.mx",
      "nombre": "Carlos Vega",
      "rol": "planner",
      "id_locacion": 1,
      "jti": "e7bc29ec044049a49326b4f8aaa966d0",
      "ip": "172.19.0.1",
      "user_agent": "Python-urllib/3.14",
      "login_en": "2026-10-24T05:46:10.928368+00:00",
      "ttl_restante_segundos": 28800
    },
    {
      "id_usuario": "f14c3ee2-1985-4e26-9915-45c26503a876",
      "email": "planner@freshtrack.mx",
      "nombre": "Carlos Vega",
      "rol": "planner",
      "id_locacion": 1,
      "jti": "d52fec1b7e554a21a51e4c78895d2428",
      "ip": "172.19.0.1",
      "user_agent": "Python-urllib/3.14",
      "login_en": "2026-10-24T05:46:11.311284+00:00",
      "ttl_restante_segundos": 28800
    }
  ]
}
```

<a id="caso-14"></a>
## 14. svc-auth — DELETE /api/v1/auth/sessions/f14c3ee2-1985-4e26-9915-45c26503a876

- **Objetivo:** Cierre forzado de todas las sesiones de un usuario
- **URL:** `DELETE http://127.0.0.1:5001/api/v1/auth/sessions/f14c3ee2-1985-4e26-9915-45c26503a876`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 8a58b91cc3154a1b
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "f14c3ee2-1985-4e26-9915-45c26503a876",
  "sesiones_cerradas": 2,
  "mensaje": "Sesiones revocadas"
}
```

<a id="caso-15"></a>
## 15. svc-planning — GET /api/v1/planning/replenishment/orders

- **Objetivo:** El token del usuario cuyas sesiones se cerraron ya no sirve en otro servicio
- **URL:** `GET http://127.0.0.1:5006/api/v1/planning/replenishment/orders`
- **Código HTTP:** `401` (esperado `401`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 4e8a33c278ff476f
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "4e8a33c278ff476f"
}
```

<a id="caso-16"></a>
## 16. svc-auth — GET /api/v1/auth/counters

- **Objetivo:** Contadores de operación en Redis
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/counters?servicio=auth`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 59e411cf6b7e458f
```

**Respuesta (application/json):**

```json
{
  "total_metricas": 7,
  "contadores": {
    "counter:ops:auth:access_denied_invalid:20261024": 13,
    "counter:ops:auth:access_denied_no_token:20261024": 6,
    "counter:ops:auth:login_failed:20261024": 50,
    "counter:ops:auth:login_success:20261024": 56,
    "counter:ops:auth:access_denied_revoked:20261024": 17,
    "counter:ops:auth:access_denied_role:20261024": 17,
    "counter:ops:auth:access_granted:20261024": 232
  }
}
```

<a id="caso-17"></a>
## 17. svc-auth — POST /api/v1/auth/logout

- **Objetivo:** Logout: revoca en PostgreSQL y agrega jti a la denylist de Redis
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/logout`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 313528f14d5044fc
```

**Respuesta (application/json):**

```json
{
  "status": "LOGOUT_EXITOSO",
  "jti": "357773d401e847a4b087ade33b5b3c41"
}
```

<a id="caso-18"></a>
## 18. svc-inventory — GET /api/v1/inventory/stock

- **Objetivo:** Token revocado usado en OTRO microservicio
- **URL:** `GET http://127.0.0.1:5003/api/v1/inventory/stock`
- **Código HTTP:** `401` (esperado `401`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 4a66892e5bb34cd1
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "4a66892e5bb34cd1"
}
```

<a id="caso-19"></a>
## 19. svc-inventory — GET /api/v1/inventory/stock

- **Objetivo:** Token con firma alterada
- **URL:** `GET http://127.0.0.1:5003/api/v1/inventory/stock`
- **Código HTTP:** `401` (esperado `401`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: b73d39d1ac9c483e
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "b73d39d1ac9c483e"
}
```

<a id="caso-20"></a>
## 20. svc-catalog — GET /api/v1/catalog/products

- **Objetivo:** Productos filtrados y paginados (Cache-Aside: 1.ª vez PostgreSQL)
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: eaca362d005346b7
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 0,
    "total_paginas": 1
  },
  "productos": [],
  "fuente": "postgres"
}
```

<a id="caso-21"></a>
## 21. svc-catalog — GET /api/v1/catalog/products

- **Objetivo:** Misma consulta servida desde caché Redis (campo fuente y TTL)
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: bdcf0410dd37459f
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 0,
    "total_paginas": 1
  },
  "productos": [],
  "fuente": "redis_cache",
  "cache_ttl_segundos": 300
}
```

<a id="caso-22"></a>
## 22. svc-catalog — GET /api/v1/catalog/products

- **Objetivo:** Respuesta en XML
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products?por_pagina=2`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Accept: application/xml
X-Correlation-Id: bdc24dde4eec4770
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalogo_productos><paginacion><pagina>1</pagina><por_pagina>2</por_pagina><total>19</total><total_paginas>10</total_paginas></paginacion><productos><item><id_sku>12</id_sku><codigo_gtin>07501234560126</codigo_gtin><nombre>Arroz 1kg</nombre><categoria>Abarrotes</categoria><unidad_medida>Paquete</unidad_medida><id_proveedor>6</id_proveedor><stock_seguridad>100.0</stock_seguridad><punto_reorden>180.0</punto_reorden><perecedero>true</perecedero><vida_util_estandar>365</vida_util_estandar><precio_costo>22.0</precio_costo><precio_venta>33.5</precio_venta><activo>true</activo></item><item><id_sku>9</id_sku><codigo_gtin>07501234560096</codigo_gtin><nombre>Crema Ácida 450g</nombre><categoria>Lácteos</categoria><unidad_medida>Pieza</unidad_medida><id_proveedor>1</id_proveedor><stock_seguridad>35.0</stock_seguridad><punto_reorden>70.0</punto_reorden><perecedero>true</perecedero><vida_util_estandar>20</vida_util_estandar><precio_costo>26.0</precio_costo><precio_venta>38.0</precio_venta><activo>true</activo></item></productos><fuente>postgres</fuente></catalogo_productos>
```

<a id="caso-23"></a>
## 23. svc-catalog — GET /api/v1/catalog/products

- **Objetivo:** Parámetro de paginación inválido
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products?pagina=0`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
X-Correlation-Id: dffd6cb63d5a48a8
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'pagina' debe ser mayor o igual a 1.",
  "status": 400,
  "correlation_id": "dffd6cb63d5a48a8"
}
```

<a id="caso-24"></a>
## 24. svc-catalog — POST /api/v1/catalog/products

- **Objetivo:** Alta de producto con XML validado contra producto_request.xsd
- **URL:** `POST http://127.0.0.1:5002/api/v1/catalog/products`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
Accept: application/xml
X-Correlation-Id: 70a0d78d06904da7
```

**Cuerpo de la petición:**

```xml
<producto_request><nombre>Fresa evidencia 1b385</nombre><categoria>Frutas</categoria><precio_costo>20</precio_costo><precio_venta>35.5</precio_venta><vida_util_estandar>5</vida_util_estandar></producto_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<producto_creado><id_sku>20</id_sku><nombre>Fresa evidencia 1b385</nombre><status>CREADO</status></producto_creado>
```

<a id="caso-25"></a>
## 25. svc-catalog — GET /api/v1/catalog/products/20

- **Objetivo:** Detalle por SKU
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products/20`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 4f5eee76ace04a68
```

**Respuesta (application/json):**

```json
{
  "id_sku": 20,
  "codigo_gtin": "21792820771638",
  "nombre": "Fresa evidencia 1b385",
  "categoria": "Frutas",
  "unidad_medida": "Pieza",
  "id_proveedor": null,
  "stock_seguridad": 0.0,
  "punto_reorden": 0.0,
  "perecedero": true,
  "vida_util_estandar": 5,
  "precio_costo": 20.0,
  "precio_venta": 35.5,
  "activo": true
}
```

<a id="caso-26"></a>
## 26. svc-catalog — PATCH /api/v1/catalog/products/20

- **Objetivo:** Actualización parcial (PATCH)
- **URL:** `PATCH http://127.0.0.1:5002/api/v1/catalog/products/20`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 7e08e1f4a3fd490c
```

**Cuerpo de la petición:**

```json
{
  "precio_venta": 39.9
}
```

**Respuesta (application/json):**

```json
{
  "id_sku": 20,
  "codigo_gtin": "21792820771638",
  "nombre": "Fresa evidencia 1b385",
  "categoria": "Frutas",
  "unidad_medida": "Pieza",
  "id_proveedor": null,
  "stock_seguridad": 0.0,
  "punto_reorden": 0.0,
  "perecedero": true,
  "vida_util_estandar": 5,
  "precio_costo": 20.0,
  "precio_venta": 39.9,
  "activo": true
}
```

<a id="caso-27"></a>
## 27. svc-catalog — PUT /api/v1/catalog/products/20

- **Objetivo:** Reemplazo completo (PUT)
- **URL:** `PUT http://127.0.0.1:5002/api/v1/catalog/products/20`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 038643faf70b4e49
```

**Cuerpo de la petición:**

```json
{
  "nombre": "Fresa evidencia 1b385",
  "categoria": "Frutas",
  "precio_costo": 21,
  "precio_venta": 40,
  "vida_util_estandar": 6,
  "unidad_medida": "Pieza"
}
```

**Respuesta (application/json):**

```json
{
  "id_sku": 20,
  "codigo_gtin": "21792820771638",
  "nombre": "Fresa evidencia 1b385",
  "categoria": "Frutas",
  "unidad_medida": "Pieza",
  "id_proveedor": null,
  "stock_seguridad": 0.0,
  "punto_reorden": 0.0,
  "perecedero": true,
  "vida_util_estandar": 6,
  "precio_costo": 21.0,
  "precio_venta": 40.0,
  "activo": true
}
```

<a id="caso-28"></a>
## 28. svc-catalog — PATCH /api/v1/catalog/products/20

- **Objetivo:** Regla de negocio: precio de venta menor al costo
- **URL:** `PATCH http://127.0.0.1:5002/api/v1/catalog/products/20`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: f2fe6313d3334faa
```

**Cuerpo de la petición:**

```json
{
  "precio_venta": 5
}
```

**Respuesta (application/json):**

```json
{
  "error": "regla_negocio",
  "mensaje": "El precio de venta no puede ser menor que el costo.",
  "status": 409,
  "correlation_id": "f2fe6313d3334faa"
}
```

<a id="caso-29"></a>
## 29. svc-catalog — POST /api/v1/catalog/products

- **Objetivo:** Campos obligatorios faltantes
- **URL:** `POST http://127.0.0.1:5002/api/v1/catalog/products`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 8597d2a071aa4b7c
```

**Cuerpo de la petición:**

```json
{
  "nombre": "Sin precio"
}
```

**Respuesta (application/json):**

```json
{
  "error": "campos_requeridos",
  "mensaje": "Faltan campos obligatorios.",
  "status": 400,
  "correlation_id": "8597d2a071aa4b7c",
  "detalles": {
    "faltantes": [
      "categoria",
      "precio_venta",
      "precio_costo"
    ]
  }
}
```

<a id="caso-30"></a>
## 30. svc-catalog — DELETE /api/v1/catalog/products/20

- **Objetivo:** Baja reservada a admin
- **URL:** `DELETE http://127.0.0.1:5002/api/v1/catalog/products/20`
- **Código HTTP:** `403` (esperado `403`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 12486c4ef7584b04
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'buyer' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "12486c4ef7584b04",
  "detalles": {
    "roles_permitidos": [
      "admin"
    ]
  }
}
```

<a id="caso-31"></a>
## 31. svc-catalog — DELETE /api/v1/catalog/products/20

- **Objetivo:** Baja lógica (activo=false)
- **URL:** `DELETE http://127.0.0.1:5002/api/v1/catalog/products/20`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: c5e3eeeeeacb4918
```

**Respuesta (application/json):**

```json
{
  "id_sku": 20,
  "activo": false
}
```

<a id="caso-32"></a>
## 32. svc-catalog — GET /api/v1/catalog/products/99999999

- **Objetivo:** SKU inexistente
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products/99999999`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
X-Correlation-Id: 83fc164cc6ea468f
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "SKU 99999999 no encontrado.",
  "status": 404,
  "correlation_id": "83fc164cc6ea468f"
}
```

<a id="caso-33"></a>
## 33. svc-catalog — GET /api/v1/catalog/locations

- **Objetivo:** Tiendas (Cache-Aside)
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/locations?tipo=Tienda`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: f6a8cfc7b6dc409e
```

**Respuesta (application/json):**

```json
{
  "total": 5,
  "locaciones": [
    {
      "id_locacion": 3,
      "tipo_locacion": "Tienda",
      "nombre": "Tienda San Pedro",
      "ciudad": "San Pedro Garza García",
      "direccion": null,
      "activo": true
    },
    {
      "id_locacion": 4,
      "tipo_locacion": "Tienda",
      "nombre": "Tienda Cumbres",
      "ciudad": "Monterrey",
      "direccion": null,
      "activo": true
    },
    {
      "id_locacion": 5,
      "tipo_locacion": "Tienda",
      "nombre": "Tienda Valle Oriente",
      "ciudad": "San Pedro Garza García",
      "direccion": null,
      "activo": true
    },
    {
      "id_locacion": 6,
      "tipo_locacion": "Tienda",
      "nombre": "Tienda Centro",
      "ciudad": "Saltillo",
      "direccion": null,
      "activo": true
    },
    {
      "id_locacion": 7,
      "tipo_locacion": "Tienda",
      "nombre": "Tienda Sur",
      "ciudad": "Monterrey",
      "direccion": null,
      "activo": true
    }
  ],
  "fuente": "postgres"
}
```

<a id="caso-34"></a>
## 34. svc-inventory — GET /api/v1/inventory/stock

- **Objetivo:** Existencias por vencer en ≤7 días (paginado, orden FEFO)
- **URL:** `GET http://127.0.0.1:5003/api/v1/inventory/stock?id_locacion=3&dias_max=7&por_pagina=5`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: fff2d11b00f249a1
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 5,
    "total": 7,
    "total_paginas": 2
  },
  "existencias": [
    {
      "id_existencia": "a6cd547b-13d9-432e-9c53-ef663f9bd7ed",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "cf156836-cb48-45d2-a31d-1ae8f874a220",
      "id_sku": 6,
      "producto": "Pan Integral 600g",
      "codigo_lote_prov": "PAA-20261023-001",
      "fecha_caducidad": "2026-10-25",
      "dias_restantes": 1,
      "cantidad_disponible": 61.37,
      "cantidad_reservada": 0.0,
      "disponible_neto": 61.37
    },
    {
      "id_existencia": "d0551815-7c19-4fd8-a23d-c7233fa010ea",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "7a6d7bad-82f5-411f-9988-515b8233aef4",
      "id_sku": 5,
      "producto": "Pechuga de Pollo kg",
      "codigo_lote_prov": "CRN-20261020-001",
      "fecha_caducidad": "2026-10-25",
      "dias_restantes": 1,
      "cantidad_disponible": 35.31,
      "cantidad_reservada": 0.0,
      "disponible_neto": 35.31
    },
    {
      "id_existencia": "0a00080f-8790-47ed-a4fb-c5cd941b6344",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "b8e9216c-c38d-4b1f-bf8d-2bba00afc33e",
      "id_sku": 6,
      "producto": "Pan Integral 600g",
      "codigo_lote_prov": "PAA-20261021-001",
      "fecha_caducidad": "2026-10-25",
      "dias_restantes": 1,
      "cantidad_disponible": 1.5,
      "cantidad_reservada": 0.0,
      "disponible_neto": 1.5
    },
    {
      "id_existencia": "07437a50-fe2d-41ee-b3c3-84fca0bcab7c",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "7df82c7f-3daa-4914-9bb2-5a7edc812c5d",
      "id_sku": 5,
      "producto": "Pechuga de Pollo kg",
      "codigo_lote_prov": "CRN-20261021-001",
      "fecha_caducidad": "2026-10-26",
      "dias_restantes": 2,
      "cantidad_disponible": 42.31,
      "cantidad_reservada": 0.0,
      "disponible_neto": 42.31
    },
    {
      "id_existencia": "7242e830-adc0-482f-a1ef-1899e71e7c3a",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "a59e1fc5-0672-41ac-a0cd-7ce18159a448",
      "id_sku": 8,
      "producto": "Espinaca 250g",
      "codigo_lote_prov": "VFR-20261022-002",
      "fecha_caducidad": "2026-10-27",
      "dias_restantes": 3,
      "cantidad_disponible": 48.31,
      "cantidad_reservada": 0.0,
      "disponible_neto": 48.31
    }
  ]
}
```

<a id="caso-35"></a>
## 35. svc-inventory — GET /api/v1/inventory/fefo-queue/1/3

- **Objetivo:** Cola FEFO en XML
- **URL:** `GET http://127.0.0.1:5003/api/v1/inventory/fefo-queue/1/3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Accept: application/xml
X-Correlation-Id: 5f3c377d41424a13
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<fefo_queue><id_sku>1</id_sku><id_locacion>3</id_locacion><total_lotes>37</total_lotes><lotes_fefo><item><id_existencia>1e03a990-b100-4169-8b69-8d70178dc6d9</id_existencia><id_lote>af4e1351-5dea-421a-b66e-4b92a5177168</id_lote><codigo_lote_prov>LDN-20261018-001</codigo_lote_prov><cantidad_disponible>46.12</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-11-02</fecha_caducidad><dias_restantes>9</dias_restantes><costo_unitario>18.5</costo_unitario></item><item><id_existencia>f9fd9f36-2d40-43b9-bdd0-2f36a5dc1e8d</id_existencia><id_lote>f486351c-ca71-41d7-aad0-248b335d58c8</id_lote><codigo_lote_prov>PYTEST-048108e3</codigo_lote_prov><cantidad_disponible>49.0</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-11-02</fecha_caducidad><dias_restantes>9</dias_restantes><costo_unitario>12.5</costo_unitario></item><item><id_existencia>12ebf283-a102-4767-9994-bccd40e14806</id_existencia><id_lote>36bb6625-379c-4b4a-b1b9-bf322519acd6</id_lote><codigo_lote_prov>PYTEST-0925f183</codigo_lote_prov><cantidad_disponible>50.0</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-11-02</fecha_caducidad><dias_restantes>9</dias_restantes><costo_unitario>12.5</costo_unitario></item><item><id_existencia>a52b54c4-6ccc-463a-bef3-02139018ab46</id_existencia><id_lote>5641bac6-4629-4c72-8082-9b2a3bd0a6d7</id_lote><codigo_lote_prov>PYTEST-1b4a7f38</codigo_lote_prov><cantidad_disponible>50.0</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-11-02</fecha_caducidad><dias_restantes>9</dias_restantes><costo_unitario>12.5</costo_unitario></item><item><id_existencia>92c667de-fee9-4123-be06-e142079da559</id_existencia><id_lote>bfdf4f6a-33c0-47c6-866b-2ea312d7acb6</id_lote><codigo_lote_prov>PYTEST-1cfd05c9</codigo_lote_prov><cantidad_disponible>50.0</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-11-02</fecha_caducidad><dias_restantes>9</dias_restantes><costo_unitario>12.5</costo_unitario></item><item><id_existencia>676b9f17-dcd3-47e5-9f7b-f8db289ca3ad</id_existencia><id_lote>f81a2bbd-3a35-47e9-a596-105744168c4d</id_lote><codigo_lote_prov>PYTEST-20ddd7b5</codigo_lote_prov><cantidad_disponible>50.0</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-11-02</fecha_caducidad><dias_restantes>9</dias_restantes><costo_unitario>12.5</costo_unitario></i
… (respuesta recortada)
```

<a id="caso-36"></a>
## 36. svc-inventory — GET /api/v1/inventory/fefo-queue/99999999/3

- **Objetivo:** SKU inexistente en la cola FEFO
- **URL:** `GET http://127.0.0.1:5003/api/v1/inventory/fefo-queue/99999999/3`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 7b960c4917d54946
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "SKU 99999999 no existe.",
  "status": 404,
  "correlation_id": "7b960c4917d54946"
}
```

<a id="caso-37"></a>
## 37. svc-inventory — POST /api/v1/inventory/reserve-fefo

- **Objetivo:** Reserva FEFO con lock distribuido en Redis (XML)
- **URL:** `POST http://127.0.0.1:5003/api/v1/inventory/reserve-fefo`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
X-Correlation-Id: 0009fc7980f34472
```

**Cuerpo de la petición:**

```xml
<reserva_request><id_locacion>3</id_locacion><saga_id>evidencia-82f59a29</saga_id><lineas><item><id_sku>1</id_sku><cantidad>1</cantidad></item></lineas></reserva_request>
```

**Respuesta (application/json):**

```json
{
  "status": "RESERVADO",
  "saga_id": "evidencia-82f59a29",
  "id_locacion": 3,
  "reservas": [
    {
      "id_lote": "af4e1351-5dea-421a-b66e-4b92a5177168",
      "id_sku": 1,
      "cantidad": 1.0,
      "costo_unitario": 18.5,
      "codigo_lote": "LDN-20261018-001"
    }
  ]
}
```

<a id="caso-38"></a>
## 38. svc-inventory — POST /api/v1/inventory/cancel-reservation

- **Objetivo:** Compensación: libera la reserva guardada en Redis
- **URL:** `POST http://127.0.0.1:5003/api/v1/inventory/cancel-reservation`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 8fdd8149a278432f
```

**Cuerpo de la petición:**

```json
{
  "saga_id": "evidencia-82f59a29"
}
```

**Respuesta (application/json):**

```json
{
  "status": "RESERVA_CANCELADA",
  "liberados": 1
}
```

<a id="caso-39"></a>
## 39. svc-inventory — POST /api/v1/inventory/reserve-fefo

- **Objetivo:** Stock insuficiente (rollback)
- **URL:** `POST http://127.0.0.1:5003/api/v1/inventory/reserve-fefo`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 41cd0ecd01df46a9
```

**Cuerpo de la petición:**

```json
{
  "id_locacion": 3,
  "lineas": [
    {
      "id_sku": 1,
      "cantidad": 99999999
    }
  ]
}
```

**Respuesta (application/json):**

```json
{
  "error": "stock_insuficiente",
  "mensaje": "Stock insuficiente para el SKU 1.",
  "status": 409,
  "correlation_id": "41cd0ecd01df46a9",
  "detalles": {
    "id_sku": 1,
    "disponible": 1880.43,
    "solicitado": 99999999.0
  }
}
```

<a id="caso-40"></a>
## 40. svc-inventory — POST /api/v1/inventory/reserve-fefo

- **Objetivo:** Tipo de dato inválido
- **URL:** `POST http://127.0.0.1:5003/api/v1/inventory/reserve-fefo`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 0095b53332644caa
```

**Cuerpo de la petición:**

```json
{
  "id_locacion": 3,
  "lineas": [
    {
      "id_sku": "abc",
      "cantidad": 1
    }
  ]
}
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_sku' debe ser un número entero.",
  "status": 400,
  "correlation_id": "0095b53332644caa"
}
```

<a id="caso-41"></a>
## 41. svc-inventory — POST /api/v1/inventory/reserve-fefo

- **Objetivo:** Auditor no puede reservar
- **URL:** `POST http://127.0.0.1:5003/api/v1/inventory/reserve-fefo`
- **Código HTTP:** `403` (esperado `403`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: aa6cac21cf5c47e9
```

**Cuerpo de la petición:**

```json
{
  "id_locacion": 3,
  "lineas": [
    {
      "id_sku": 1,
      "cantidad": 1
    }
  ]
}
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'auditor' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "aa6cac21cf5c47e9",
  "detalles": {
    "roles_permitidos": [
      "admin",
      "store_manager",
      "warehouse"
    ]
  }
}
```

<a id="caso-42"></a>
## 42. svc-commercial — POST /api/v1/commercial/checkout

- **Objetivo:** Venta POS por Saga: reserva FEFO → venta → descuento de existencias
- **URL:** `POST http://127.0.0.1:5004/api/v1/commercial/checkout`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 20c99973174b4616
```

**Cuerpo de la petición:**

```json
{
  "id_locacion": 3,
  "canal": "TIENDA",
  "lineas": [
    {
      "id_sku": 1,
      "cantidad": 1
    }
  ]
}
```

**Respuesta (application/json):**

```json
{
  "saga_id": "1ab092cef7574a33a16458ef042293e6",
  "id_venta": "2bfad9f3-f42b-4a25-a1bf-d275e13277fb",
  "folio": "VT-3-20261024-000013",
  "total": 24.9,
  "lineas": [
    {
      "id_sku": 1,
      "producto": "Leche Entera 1L",
      "codigo_lote": "LDN-20261018-001",
      "cantidad": 1.0,
      "precio_unitario": 24.9,
      "subtotal": 24.9
    }
  ],
  "estado": "COMPLETADA"
}
```

<a id="caso-43"></a>
## 43. svc-commercial — POST /api/v1/commercial/checkout

- **Objetivo:** Venta rechazada por stock (compensación de la saga, respuesta XML)
- **URL:** `POST http://127.0.0.1:5004/api/v1/commercial/checkout`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
Accept: application/xml
X-Correlation-Id: 9362848ecaf94882
```

**Cuerpo de la petición:**

```xml
<checkout_request><id_locacion>3</id_locacion><lineas><item><id_sku>1</id_sku><cantidad>99999999</cantidad></item></lineas></checkout_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<error_response><error>venta_rechazada</error><mensaje>Stock insuficiente para 'Leche Entera 1L' (disponible: 1879.43, solicitado: 99999999.00).</mensaje><status>409</status><correlation_id>9362848ecaf94882</correlation_id></error_response>
```

<a id="caso-44"></a>
## 44. svc-commercial — POST /api/v1/commercial/checkout

- **Objetivo:** XML que no cumple checkout_request.xsd
- **URL:** `POST http://127.0.0.1:5004/api/v1/commercial/checkout`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
X-Correlation-Id: e8e75e0185bb4975
```

**Cuerpo de la petición:**

```xml
<checkout_request><canal>OTRO</canal><lineas/></checkout_request>
```

**Respuesta (application/json):**

```json
{
  "error": "xml_no_cumple_contrato",
  "mensaje": "El XML no cumple el contrato checkout_request.xsd",
  "status": 400,
  "correlation_id": "e8e75e0185bb4975",
  "detalles": [
    {
      "ruta": "/checkout_request/canal",
      "motivo": "value must be one of ['TIENDA', 'ONLINE', 'MAYOREO']"
    },
    {
      "ruta": "/checkout_request/lineas",
      "motivo": "The content of element 'lineas' is not complete. Tag 'item' expected."
    }
  ]
}
```

<a id="caso-45"></a>
## 45. svc-commercial — PUT /api/v1/commercial/cart/caja1-aa5a

- **Objetivo:** Carrito temporal en Redis (TTL 15 min)
- **URL:** `PUT http://127.0.0.1:5004/api/v1/commercial/cart/caja1-aa5a`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: e338d683262a4eb6
```

**Cuerpo de la petición:**

```json
{
  "lineas": [
    {
      "id_sku": 1,
      "cantidad": 2
    }
  ]
}
```

**Respuesta (application/json):**

```json
{
  "cart_id": "caja1-aa5a",
  "status": "GUARDADO",
  "ttl_segundos": 900
}
```

<a id="caso-46"></a>
## 46. svc-commercial — GET /api/v1/commercial/cart/caja1-aa5a

- **Objetivo:** Consulta del carrito con TTL restante
- **URL:** `GET http://127.0.0.1:5004/api/v1/commercial/cart/caja1-aa5a`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: f1285b3bfad74c6d
```

**Respuesta (application/json):**

```json
{
  "cart_id": "caja1-aa5a",
  "ttl_restante": 900,
  "datos": {
    "lineas": [
      {
        "id_sku": 1,
        "cantidad": 2
      }
    ]
  }
}
```

<a id="caso-47"></a>
## 47. svc-commercial — DELETE /api/v1/commercial/cart/caja1-aa5a

- **Objetivo:** Consumo atómico (GET+DEL en Lua)
- **URL:** `DELETE http://127.0.0.1:5004/api/v1/commercial/cart/caja1-aa5a`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: ca3d609b071440d4
```

**Respuesta (application/json):**

```json
{
  "cart_id": "caja1-aa5a",
  "status": "CONSUMIDO",
  "datos": {
    "lineas": [
      {
        "id_sku": 1,
        "cantidad": 2
      }
    ]
  }
}
```

<a id="caso-48"></a>
## 48. svc-commercial — GET /api/v1/commercial/cart/caja1-aa5a

- **Objetivo:** Carrito ya consumido
- **URL:** `GET http://127.0.0.1:5004/api/v1/commercial/cart/caja1-aa5a`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 8fdd1a74778640f0
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Carrito expirado o inexistente.",
  "status": 404,
  "correlation_id": "8fdd1a74778640f0"
}
```

<a id="caso-49"></a>
## 49. svc-commercial — POST /api/v1/commercial/shrinkage

- **Objetivo:** Merma sobre un lote que no existe
- **URL:** `POST http://127.0.0.1:5004/api/v1/commercial/shrinkage`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 82e6b9d5198e46c1
```

**Cuerpo de la petición:**

```json
{
  "id_lote": "4e5cc385-da01-4f41-9d15-5e0b82bdd6cb",
  "id_locacion": 3,
  "cantidad": 1,
  "causa": "DANO"
}
```

**Respuesta (application/json):**

```json
{
  "error": "regla_negocio",
  "mensaje": "Ese lote no tiene existencia registrada en la tienda seleccionada.",
  "status": 409,
  "correlation_id": "82e6b9d5198e46c1"
}
```

<a id="caso-50"></a>
## 50. svc-commercial — POST /api/v1/commercial/shrinkage

- **Objetivo:** Causa de merma inválida
- **URL:** `POST http://127.0.0.1:5004/api/v1/commercial/shrinkage`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 89db850c0af24114
```

**Cuerpo de la petición:**

```json
{
  "id_lote": "cd181c1c-5f7c-4b6c-bb86-fa198f1d0291",
  "id_locacion": 3,
  "cantidad": 1,
  "causa": "INVENTADA"
}
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "Causa inválida. Valores: ['CADENA_DE_FRIO', 'CADUCIDAD', 'CALIDAD', 'DANO', 'DEVOLUCION', 'MANIPULACION', 'OTRA']",
  "status": 400,
  "correlation_id": "89db850c0af24114"
}
```

<a id="caso-51"></a>
## 51. svc-commercial — GET /api/v1/commercial/sales

- **Objetivo:** Historial de ventas por rango de fechas
- **URL:** `GET http://127.0.0.1:5004/api/v1/commercial/sales?id_locacion=3&desde=2026-09-23&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 65c36b9fd23746db
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 380,
    "total_paginas": 127
  },
  "ventas": [
    {
      "id_venta": "2bfad9f3-f42b-4a25-a1bf-d275e13277fb",
      "folio": "VT-3-20261024-000013",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "canal": "TIENDA",
      "total": 24.9,
      "fecha_venta": "2026-10-24T05:46:11.997143+00:00"
    },
    {
      "id_venta": "d0c34387-8c19-4aba-af23-633a787a7a21",
      "folio": "VT-3-20261024-000012",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "canal": "TIENDA",
      "total": 49.8,
      "fecha_venta": "2026-10-24T05:38:28.903786+00:00"
    },
    {
      "id_venta": "59dfb5bd-6746-4f82-a7b3-97dd2ebee655",
      "folio": "VT-3-20261024-000011",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "canal": "TIENDA",
      "total": 49.8,
      "fecha_venta": "2026-10-24T05:38:16.444859+00:00"
    }
  ]
}
```

<a id="caso-52"></a>
## 52. svc-asn — POST /api/v1/asn

- **Objetivo:** Ingesta de ASN en XML (validado con asn_request.xsd) → documento en MongoDB
- **URL:** `POST http://127.0.0.1:5005/api/v1/asn`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
X-Correlation-Id: ac9467a02ecd41a9
```

**Cuerpo de la petición:**

```xml
<asn_request><folio_asn>ASN-EV-32F77E</folio_asn><id_proveedor>1</id_proveedor><detalle_carga><item_carga><id_sku>1</id_sku><cantidad_declarada>120</cantidad_declarada><lote_proveedor>LP-7781</lote_proveedor><fecha_caducidad>2026-11-12</fecha_caducidad><rango_temperatura_controlada>2C a 6C</rango_temperatura_controlada></item_carga><item_carga><id_sku>2</id_sku><cantidad_declarada>40</cantidad_declarada><fecha_caducidad>2026-11-12</fecha_caducidad></item_carga></detalle_carga></asn_request>
```

**Respuesta (application/json):**

```json
{
  "id_mongo": "6adc462496ed3c0489cdfe4a",
  "folio_asn": "ASN-EV-32F77E",
  "estado": "REGISTRADO"
}
```

<a id="caso-53"></a>
## 53. svc-asn — POST /api/v1/asn

- **Objetivo:** Folio duplicado (índice único en MongoDB)
- **URL:** `POST http://127.0.0.1:5005/api/v1/asn`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
X-Correlation-Id: 7e98525c81e9470a
```

**Cuerpo de la petición:**

```xml
<asn_request><folio_asn>ASN-EV-32F77E</folio_asn><id_proveedor>1</id_proveedor><detalle_carga><item_carga><id_sku>1</id_sku><cantidad_declarada>120</cantidad_declarada><lote_proveedor>LP-7781</lote_proveedor><fecha_caducidad>2026-11-12</fecha_caducidad><rango_temperatura_controlada>2C a 6C</rango_temperatura_controlada></item_carga><item_carga><id_sku>2</id_sku><cantidad_declarada>40</cantidad_declarada><fecha_caducidad>2026-11-12</fecha_caducidad></item_carga></detalle_carga></asn_request>
```

**Respuesta (application/json):**

```json
{
  "error": "duplicado",
  "mensaje": "El folio ASN-EV-32F77E ya fue registrado.",
  "status": 409,
  "correlation_id": "7e98525c81e9470a"
}
```

<a id="caso-54"></a>
## 54. svc-asn — POST /api/v1/asn

- **Objetivo:** SKU inexistente en PostgreSQL (integración PG↔Mongo)
- **URL:** `POST http://127.0.0.1:5005/api/v1/asn`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 06f19f046c314263
```

**Cuerpo de la petición:**

```json
{
  "folio_asn": "ASN-X-78f6",
  "id_proveedor": 1,
  "detalle_carga": [
    {
      "id_sku": 99999999,
      "cantidad_declarada": 1,
      "fecha_caducidad": "2026-11-12"
    }
  ]
}
```

**Respuesta (application/json):**

```json
{
  "error": "regla_negocio",
  "mensaje": "Hay SKU que no existen en el catálogo.",
  "status": 409,
  "correlation_id": "06f19f046c314263",
  "detalles": {
    "skus_inexistentes": [
      99999999
    ]
  }
}
```

<a id="caso-55"></a>
## 55. svc-asn — GET /api/v1/asn/ASN-EV-32F77E

- **Objetivo:** Recuperación por folio
- **URL:** `GET http://127.0.0.1:5005/api/v1/asn/ASN-EV-32F77E`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 21717b2c8e8f4451
```

**Respuesta (application/json):**

```json
{
  "_id": "6adc462496ed3c0489cdfe4a",
  "folio_asn": "ASN-EV-32F77E",
  "id_proveedor": 1,
  "fecha_embarque": "2026-10-24T05:46:12.554000",
  "fecha_arribo_estimada": "2026-10-26T05:46:12.554000",
  "estado": "ANUNCIADO",
  "detalle_carga": [
    {
      "id_sku": 1,
      "cantidad_declarada": 120.0,
      "lote_proveedor": "LP-7781",
      "fecha_caducidad": "2026-11-12T00:00:00",
      "rango_temperatura_controlada": "2C a 6C"
    },
    {
      "id_sku": 2,
      "cantidad_declarada": 40.0,
      "lote_proveedor": "SIN-LOTE",
      "fecha_caducidad": "2026-11-12T00:00:00",
      "rango_temperatura_controlada": "2C a 6C"
    }
  ],
  "inspecciones": [],
  "version_esquema": 1
}
```

<a id="caso-56"></a>
## 56. svc-asn — PATCH /api/v1/asn/ASN-EV-32F77E/status

- **Objetivo:** Transición de estado inválida
- **URL:** `PATCH http://127.0.0.1:5005/api/v1/asn/ASN-EV-32F77E/status`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 2c0d95fd0dee4158
```

**Cuerpo de la petición:**

```json
{
  "estado": "RECIBIDO"
}
```

**Respuesta (application/json):**

```json
{
  "error": "transicion_invalida",
  "mensaje": "No se puede pasar de ANUNCIADO a RECIBIDO.",
  "status": 409,
  "correlation_id": "2c0d95fd0dee4158",
  "detalles": {
    "permitidas": [
      "CANCELADO",
      "EN_TRANSITO"
    ]
  }
}
```

<a id="caso-57"></a>
## 57. svc-asn — PATCH /api/v1/asn/ASN-EV-32F77E/status

- **Objetivo:** Actualización de documento ($set)
- **URL:** `PATCH http://127.0.0.1:5005/api/v1/asn/ASN-EV-32F77E/status`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 38fbfce22f734c93
```

**Cuerpo de la petición:**

```json
{
  "estado": "EN_TRANSITO"
}
```

**Respuesta (application/json):**

```json
{
  "folio_asn": "ASN-EV-32F77E",
  "estado_anterior": "ANUNCIADO",
  "estado": "EN_TRANSITO"
}
```

<a id="caso-58"></a>
## 58. svc-asn — POST /api/v1/asn/ASN-EV-32F77E/inspection

- **Objetivo:** Inspección agregada con $push
- **URL:** `POST http://127.0.0.1:5005/api/v1/asn/ASN-EV-32F77E/inspection`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 5b6518beb32946a8
```

**Cuerpo de la petición:**

```json
{
  "resultado": "CONFORME",
  "temperatura_registrada": 4.2,
  "observaciones": "Sellos íntegros"
}
```

**Respuesta (application/json):**

```json
{
  "folio_asn": "ASN-EV-32F77E",
  "status": "INSPECCION_AGREGADA",
  "resultado": "CONFORME"
}
```

<a id="caso-59"></a>
## 59. svc-asn — GET /api/v1/asn

- **Objetivo:** Filtrado por campo anidado y estado
- **URL:** `GET http://127.0.0.1:5005/api/v1/asn?id_sku=2&estado=EN_TRANSITO&por_pagina=5`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: e0d105af6e8d4dc8
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 5,
    "total": 8,
    "total_paginas": 2
  },
  "avisos_asn": [
    {
      "_id": "6adc462496ed3c0489cdfe4a",
      "folio_asn": "ASN-EV-32F77E",
      "id_proveedor": 1,
      "fecha_embarque": "2026-10-24T05:46:12.554000",
      "fecha_arribo_estimada": "2026-10-26T05:46:12.554000",
      "estado": "EN_TRANSITO",
      "detalle_carga": [
        {
          "id_sku": 1,
          "cantidad_declarada": 120.0,
          "lote_proveedor": "LP-7781",
          "fecha_caducidad": "2026-11-12T00:00:00",
          "rango_temperatura_controlada": "2C a 6C"
        },
        {
          "id_sku": 2,
          "cantidad_declarada": 40.0,
          "lote_proveedor": "SIN-LOTE",
          "fecha_caducidad": "2026-11-12T00:00:00",
          "rango_temperatura_controlada": "2C a 6C"
        }
      ],
      "inspecciones": [
        {
          "id_inspeccion": "6adc462496ed3c0489cdfe4b",
          "fecha": "2026-10-24T05:46:12.591000",
          "inspector": "almacen@freshtrack.mx",
          "resultado": "CONFORME",
          "temperatura_registrada": 4.2,
          "observaciones": "Sellos íntegros"
        }
      ],
      "version_esquema": 1,
      "actualizado_en": "2026-10-24T05:46:12.585000",
      "ultima_inspeccion": "2026-10-24T05:46:12.591000"
    },
    {
      "_id": "6adc4455613f5e48950f0b64",
      "folio_asn": "ASN-PYTEST-f2655b",
      "id_proveedor": 1,
      "fecha_embarque": "2026-10-24T05:38:29.355000",
      "fecha_arribo_estimada": "2026-10-26T05:38:29.355000",
      "estado": "EN_TRANSITO",
      "detalle_carga": [
        {
          "id_sku": 1,
          "cantidad_declarada": 40.0,
          "lote_proveedor": "SIN-LOTE",
          "fecha_caducidad": "2026-12-01T00:00:00",
          "rango_temperatura_controlada": "2C a 6C"
        },
        {
          "id_sku": 2,
          "cantidad_declarada": 15.0,
          "lote_proveedor": "SIN-LOTE",
          "fecha_caducidad": "2026-11-20T00:00:00",
          "rango_temperatura_controlada": "2C a 6C"
        }
      ],
      "inspecciones": [
        {
          "id_inspeccion": "6adc4455613f5e48950f0b65",
          "fecha": "2026-10-24T05:38:29.419000",
          "inspector": "almacen@freshtrack.mx",
          "resultado": "CONFORME",
          "temperatura_registrada": 4.1,
          "observaciones": ""
        }
      ],
      "version_esquema": 1,
      "actualizado_en": "2026-10-24T05:38:29.407000",
      "ultima_inspeccion": "2026-1
… (respuesta recortada)
```

<a id="caso-60"></a>
## 60. svc-asn — GET /api/v1/asn/analytics/summary

- **Objetivo:** Pipeline de agregación ($unwind/$group/$sort)
- **URL:** `GET http://127.0.0.1:5005/api/v1/asn/analytics/summary`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 7e4771ce1afa4a70
```

**Respuesta (application/json):**

```json
{
  "total_grupos": 2,
  "carga_consolidada": [
    {
      "despachos_asociados": 8,
      "id_proveedor": 1,
      "id_sku": 1,
      "piezas_totales": 400.0
    },
    {
      "despachos_asociados": 8,
      "id_proveedor": 1,
      "id_sku": 2,
      "piezas_totales": 145.0
    }
  ]
}
```

<a id="caso-61"></a>
## 61. svc-asn — GET /api/v1/asn/NO-EXISTE

- **Objetivo:** Folio inexistente
- **URL:** `GET http://127.0.0.1:5005/api/v1/asn/NO-EXISTE`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 4df5970e1ed14fca
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "ASN NO-EXISTE no encontrado.",
  "status": 404,
  "correlation_id": "4df5970e1ed14fca"
}
```

<a id="caso-62"></a>
## 62. svc-planning — POST /api/v1/planning/forecast/run

- **Objetivo:** Corrida de pronóstico (linaje en PostgreSQL, serie en MongoDB)
- **URL:** `POST http://127.0.0.1:5006/api/v1/planning/forecast/run`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: f732f50716304396
```

**Cuerpo de la petición:**

```json
{
  "metodo": "SUAVIZACION_EXPONENCIAL",
  "horizonte": 7,
  "alpha": 0.3,
  "id_locacion": 3,
  "id_sku": 1
}
```

**Respuesta (application/json):**

```json
{
  "id_run": "e1a47ffe-8025-47bc-adbf-f35f61cbecaa",
  "metodo": "SUAVIZACION_EXPONENCIAL",
  "metodo_etiqueta": "Suavización exponencial",
  "horizonte": 7,
  "series": 1,
  "mae": 11.6313,
  "rmse": 18.1679,
  "wmape": 29.9005,
  "resultados": [
    {
      "id_sku": 1,
      "id_locacion": 3,
      "metricas": {
        "mae": 11.6313,
        "rmse": 18.1679,
        "wmape": 29.9005,
        "n": 7,
        "suma_real": 272.3
      },
      "pronostico": [
        {
          "fecha": "2026-10-25",
          "horizonte_dia": 1,
          "valor": 41.17
        },
        {
          "fecha": "2026-10-26",
          "horizonte_dia": 2,
          "valor": 30.96
        },
        {
          "fecha": "2026-10-27",
          "horizonte_dia": 3,
          "valor": 31.04
        },
        {
          "fecha": "2026-10-28",
          "horizonte_dia": 4,
          "valor": 31.03
        },
        {
          "fecha": "2026-10-29",
          "horizonte_dia": 5,
          "valor": 29.92
        },
        {
          "fecha": "2026-10-30",
          "horizonte_dia": 6,
          "valor": 42.76
        },
        {
          "fecha": "2026-10-31",
          "horizonte_dia": 7,
          "valor": 39.27
        }
      ]
    }
  ],
  "duracion_ms": 9
}
```

<a id="caso-63"></a>
## 63. svc-planning — POST /api/v1/planning/forecast/run

- **Objetivo:** Método no soportado
- **URL:** `POST http://127.0.0.1:5006/api/v1/planning/forecast/run`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 75feb823a8814295
```

**Cuerpo de la petición:**

```json
{
  "metodo": "MAGIA"
}
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "Método no soportado. Valores: ['MEDIA_MOVIL', 'MEDIA_MOVIL_PONDERADA', 'SUAVIZACION_EXPONENCIAL']",
  "status": 400,
  "correlation_id": "75feb823a8814295"
}
```

<a id="caso-64"></a>
## 64. svc-planning — GET /api/v1/planning/forecast/latest/1/3

- **Objetivo:** Última serie pronosticada (MongoDB)
- **URL:** `GET http://127.0.0.1:5006/api/v1/planning/forecast/latest/1/3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 7061656d4f4845b9
```

**Respuesta (application/json):**

```json
{
  "_id": "6adc46249590d804a81644f0",
  "id_sku": 1,
  "id_locacion": 3,
  "fecha_calculo": "2026-10-24T05:46:12.639000",
  "horizonte_proyeccion": {
    "fecha_inicio": "2026-10-25T00:00:00",
    "fecha_fin": "2026-10-31T00:00:00",
    "dias": 7
  },
  "modelo": "SUAVIZACION_EXPONENCIAL",
  "version_modelo": "1.0",
  "linaje": {
    "id_run": "e1a47ffe-8025-47bc-adbf-f35f61cbecaa",
    "generado_por": "planner@freshtrack.mx"
  },
  "metricas": {
    "mae": 11.6313,
    "rmse": 18.1679,
    "wmape": 29.9005,
    "n": 7,
    "suma_real": 272.3
  },
  "puntos": [
    {
      "fecha": "2026-10-25T00:00:00",
      "demanda_pronosticada": 41.17,
      "intervalo_inferior": 34.99,
      "intervalo_superior": 47.35,
      "percentil": 50
    },
    {
      "fecha": "2026-10-26T00:00:00",
      "demanda_pronosticada": 30.96,
      "intervalo_inferior": 26.32,
      "intervalo_superior": 35.6,
      "percentil": 50
    },
    {
      "fecha": "2026-10-27T00:00:00",
      "demanda_pronosticada": 31.04,
      "intervalo_inferior": 26.38,
      "intervalo_superior": 35.7,
      "percentil": 50
    },
    {
      "fecha": "2026-10-28T00:00:00",
      "demanda_pronosticada": 31.03,
      "intervalo_inferior": 26.38,
      "intervalo_superior": 35.68,
      "percentil": 50
    },
    {
      "fecha": "2026-10-29T00:00:00",
      "demanda_pronosticada": 29.92,
      "intervalo_inferior": 25.43,
      "intervalo_superior": 34.41,
      "percentil": 50
    },
    {
      "fecha": "2026-10-30T00:00:00",
      "demanda_pronosticada": 42.76,
      "intervalo_inferior": 36.35,
      "intervalo_superior": 49.17,
      "percentil": 50
    },
    {
      "fecha": "2026-10-31T00:00:00",
      "demanda_pronosticada": 39.27,
      "intervalo_inferior": 33.38,
      "intervalo_superior": 45.16,
      "percentil": 50
    }
  ],
  "version_esquema": 1
}
```

<a id="caso-65"></a>
## 65. svc-planning — GET /api/v1/planning/replenishment/orders

- **Objetivo:** Órdenes pendientes paginadas
- **URL:** `GET http://127.0.0.1:5006/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 3e126f323fb4474f
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 60,
    "total_paginas": 20
  },
  "ordenes": [
    {
      "id_orden": "7244d821-6df6-4629-ae02-eb6fdc75edfc",
      "id_sku": 10,
      "producto": "Zanahoria kg",
      "id_locacion": 5,
      "locacion": "Tienda Valle Oriente",
      "id_proveedor": 3,
      "cantidad_sugerida": 582.0,
      "cantidad_aprobada": null,
      "prioridad": "MEDIA",
      "estado": "PENDIENTE",
      "explicacion": "Producto: Zanahoria kg\nTienda: Tienda Valle Oriente\n\nDemanda prevista 7 días         656.55\nInventario físico                      134.87\nInventario próximo a vencer              0.00\nInventario útil                        134.87\nStock de seguridad                      60.00\nEntradas confirmadas                     0.00\nLead time                                   1 días\nMOQ                                     80.00\n\nNecesidad neta                         581.68\n\nRecomendación: ordenar 582 Kg",
      "fecha_creacion": "2026-10-23T21:01:06.410732+00:00",
      "fecha_decision": null
    },
    {
      "id_orden": "6c8f952f-2b7f-4a95-9b02-a3640e7e8b14",
      "id_sku": 10,
      "producto": "Zanahoria kg",
      "id_locacion": 7,
      "locacion": "Tienda Sur",
      "id_proveedor": 3,
      "cantidad_sugerida": 513.0,
      "cantidad_aprobada": null,
      "prioridad": "MEDIA",
      "estado": "PENDIENTE",
      "explicacion": "Producto: Zanahoria kg\nTienda: Tienda Sur\n\nDemanda prevista 7 días         638.89\nInventario físico                      186.21\nInventario próximo a vencer              0.00\nInventario útil                        186.21\nStock de seguridad                      60.00\nEntradas confirmadas                     0.00\nLead time                                   1 días\nMOQ                                     80.00\n\nNecesidad neta                         512.68\n\nRecomendación: ordenar 513 Kg",
      "fecha_creacion": "2026-10-23T21:01:06.365865+00:00",
      "fecha_decision": null
    },
    {
      "id_orden": "3cdeb919-20a0-4a86-874f-c29207017455",
      "id_sku": 10,
      "producto": "Zanahoria kg",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_proveedor": 3,
      "cantidad_sugerida": 480.0,
      "cantidad_aprobada": null,
      "prioridad": "MEDIA",
      "estado": "PENDIENTE",
      "explicacion": "Producto: Zanahoria kg\nTienda: Tienda San Pedro\n\nDemanda prevista 7 días         586.04\nInventario físico             
… (respuesta recortada)
```

<a id="caso-66"></a>
## 66. svc-planning — POST /api/v1/planning/replenishment/orders/18269bf6-d12e-4ed2-b12a-a94af6c674f9/approve

- **Objetivo:** Aprobar orden inexistente
- **URL:** `POST http://127.0.0.1:5006/api/v1/planning/replenishment/orders/18269bf6-d12e-4ed2-b12a-a94af6c674f9/approve`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: d859225a07d24e30
```

**Cuerpo de la petición:**

```json
{}
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Orden 18269bf6-d12e-4ed2-b12a-a94af6c674f9 no encontrada.",
  "status": 404,
  "correlation_id": "d859225a07d24e30"
}
```

<a id="caso-67"></a>
## 67. svc-planning — GET /api/v1/planning/sku/1/full-context

- **Objetivo:** Contexto híbrido PostgreSQL + MongoDB
- **URL:** `GET http://127.0.0.1:5006/api/v1/planning/sku/1/full-context?id_locacion=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 3cdad41712fa420c
```

**Respuesta (application/json):**

```json
{
  "producto_postgres": {
    "id_sku": 1,
    "codigo_gtin": "07501234560010",
    "nombre": "Leche Entera 1L",
    "categoria": "Lácteos",
    "vida_util_estandar": 15,
    "precio_venta": 24.9,
    "precio_costo": 18.5,
    "activo": true
  },
  "contexto_mongo": {
    "id_sku": 1,
    "id_locacion": 3,
    "pronostico_reciente": {
      "_id": "6adc46249590d804a81644f0",
      "fecha_calculo": "2026-10-24T05:46:12.639000",
      "horizonte_proyeccion": {
        "fecha_inicio": "2026-10-25T00:00:00",
        "fecha_fin": "2026-10-31T00:00:00",
        "dias": 7
      },
      "modelo": "SUAVIZACION_EXPONENCIAL",
      "version_modelo": "1.0",
      "metricas": {
        "mae": 11.6313,
        "rmse": 18.1679,
        "wmape": 29.9005,
        "n": 7,
        "suma_real": 272.3
      },
      "puntos_count": 7
    },
    "alertas_activas_count": 5,
    "alertas_activas": [
      {
        "_id": "6adc4455613f5e48950f0b92",
        "tipo": "RIESGO_PRE_MERMA",
        "criticidad": "WARNING",
        "mensaje": "Lote de 'Leche Entera 1L' vence en 11 día(s). Stock: 91.31 u.",
        "generada_en": "2026-10-24T05:38:29.605000",
        "atendida": false,
        "version_esquema": 1,
        "contexto": {
          "dias_restantes": 11,
          "producto": "Leche Entera 1L",
          "id_lote": "707d8618-9985-4565-ae58-a69046ebdfe0",
          "cantidad": 91.31
        },
        "id_sku": 1,
        "id_locacion": 3
      },
      {
        "_id": "6adc4455613f5e48950f0b90",
        "tipo": "RIESGO_PRE_MERMA",
        "criticidad": "WARNING",
        "mensaje": "Lote de 'Leche Entera 1L' vence en 9 día(s). Stock: 46.12 u.",
        "generada_en": "2026-10-24T05:38:29.601000",
        "atendida": false,
        "version_esquema": 1,
        "contexto": {
          "dias_restantes": 9,
          "producto": "Leche Entera 1L",
          "id_lote": "af4e1351-5dea-421a-b66e-4b92a5177168",
          "cantidad": 46.12
        },
        "id_sku": 1,
        "id_locacion": 3
      },
      {
        "_id": "6adc4455613f5e48950f0b8f",
        "tipo": "RIESGO_PRE_MERMA",
        "criticidad": "WARNING",
        "mensaje": "Lote de 'Leche Entera 1L' vence en 9 día(s). Stock: 49 u.",
        "generada_en": "2026-10-24T05:38:29.599000",
        "atendida": false,
        "version_esquema": 1,
        "contexto": {
          "dias_restantes": 9,
          "producto": "Leche Entera 1L",
          "id_lote": "f486351c-ca71-41d7-aad0-248b335d58c8",
          "cantida
… (respuesta recortada)
```

<a id="caso-68"></a>
## 68. svc-planning — GET /api/v1/planning/forecast/analytics/kpis

- **Objetivo:** Métricas por modelo (agregación)
- **URL:** `GET http://127.0.0.1:5006/api/v1/planning/forecast/analytics/kpis`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 447fe9a465154fe7
```

**Respuesta (application/json):**

```json
{
  "total_modelos": 1,
  "kpis_modelos": [
    {
      "total_corridas": 97,
      "modelo": "SUAVIZACION_EXPONENCIAL",
      "mae_promedio": 5.962,
      "rmse_promedio": 7.031
    }
  ]
}
```

<a id="caso-69"></a>
## 69. svc-alerts — POST /api/v1/alerts/scan

- **Objetivo:** Escaneo con lock distribuido → alertas en MongoDB + eventos en Redis Streams
- **URL:** `POST http://127.0.0.1:5007/api/v1/alerts/scan?id_locacion=3&dias=5`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: f6e909b639d74333
```

**Respuesta (application/json):**

```json
{
  "status": "COMPLETADO",
  "ventana_dias": 5,
  "total_escaneados": 6,
  "alertas_emitidas": 6,
  "detalle": [
    {
      "id_mongo": "6adc4624976c8bfea9779705",
      "id_lote": "b8e9216c-c38d-4b1f-bf8d-2bba00afc33e",
      "criticidad": "CRITICAL"
    },
    {
      "id_mongo": "6adc4624976c8bfea9779706",
      "id_lote": "7a6d7bad-82f5-411f-9988-515b8233aef4",
      "criticidad": "CRITICAL"
    },
    {
      "id_mongo": "6adc4624976c8bfea9779707",
      "id_lote": "cf156836-cb48-45d2-a31d-1ae8f874a220",
      "criticidad": "CRITICAL"
    },
    {
      "id_mongo": "6adc4624976c8bfea9779708",
      "id_lote": "7df82c7f-3daa-4914-9bb2-5a7edc812c5d",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6adc4624976c8bfea9779709",
      "id_lote": "a59e1fc5-0672-41ac-a0cd-7ce18159a448",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6adc4624976c8bfea977970a",
      "id_lote": "03c21649-e3c4-4e15-9d00-127e8a1b4ec8",
      "criticidad": "WARNING"
    }
  ]
}
```

<a id="caso-70"></a>
## 70. svc-alerts — GET /api/v1/alerts/active

- **Objetivo:** Alertas abiertas filtradas
- **URL:** `GET http://127.0.0.1:5007/api/v1/alerts/active?id_locacion=3&limite=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 89a2b0d0ec7344ac
```

**Respuesta (application/json):**

```json
{
  "total": 3,
  "alertas": [
    {
      "_id": "6adc4624976c8bfea977970a",
      "tipo": "RIESGO_PRE_MERMA",
      "criticidad": "WARNING",
      "mensaje": "Lote de 'Tomate Bola kg' vence en 5 día(s). Stock: 116.43 u.",
      "generada_en": "2026-10-24T05:46:12.697000",
      "atendida": false,
      "version_esquema": 1,
      "contexto": {
        "dias_restantes": 5,
        "producto": "Tomate Bola kg",
        "id_lote": "03c21649-e3c4-4e15-9d00-127e8a1b4ec8",
        "cantidad": 116.43
      },
      "id_sku": 4,
      "id_locacion": 3
    },
    {
      "_id": "6adc4624976c8bfea9779709",
      "tipo": "RIESGO_PRE_MERMA",
      "criticidad": "WARNING",
      "mensaje": "Lote de 'Espinaca 250g' vence en 3 día(s). Stock: 48.31 u.",
      "generada_en": "2026-10-24T05:46:12.696000",
      "atendida": false,
      "version_esquema": 1,
      "contexto": {
        "dias_restantes": 3,
        "producto": "Espinaca 250g",
        "id_lote": "a59e1fc5-0672-41ac-a0cd-7ce18159a448",
        "cantidad": 48.31
      },
      "id_sku": 8,
      "id_locacion": 3
    },
    {
      "_id": "6adc4624976c8bfea9779708",
      "tipo": "RIESGO_PRE_MERMA",
      "criticidad": "WARNING",
      "mensaje": "Lote de 'Pechuga de Pollo kg' vence en 2 día(s). Stock: 42.31 u.",
      "generada_en": "2026-10-24T05:46:12.695000",
      "atendida": false,
      "version_esquema": 1,
      "contexto": {
        "dias_restantes": 2,
        "producto": "Pechuga de Pollo kg",
        "id_lote": "7df82c7f-3daa-4914-9bb2-5a7edc812c5d",
        "cantidad": 42.31
      },
      "id_sku": 5,
      "id_locacion": 3
    }
  ]
}
```

<a id="caso-71"></a>
## 71. svc-alerts — PATCH /api/v1/alerts/6adc4624976c8bfea977970a/resolve

- **Objetivo:** Atender alerta (inicia retención TTL)
- **URL:** `PATCH http://127.0.0.1:5007/api/v1/alerts/6adc4624976c8bfea977970a/resolve`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: e096fe7681b24af0
```

**Respuesta (application/json):**

```json
{
  "id_mongo": "6adc4624976c8bfea977970a",
  "status": "ATENDIDA"
}
```

<a id="caso-72"></a>
## 72. svc-alerts — PATCH /api/v1/alerts/zzz/resolve

- **Objetivo:** ObjectId inválido
- **URL:** `PATCH http://127.0.0.1:5007/api/v1/alerts/zzz/resolve`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: dd7367041d514acd
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_mongo' debe ser un ObjectId de 24 caracteres hexadecimales.",
  "status": 400,
  "correlation_id": "dd7367041d514acd"
}
```

<a id="caso-73"></a>
## 73. svc-alerts — GET /api/v1/alerts/esg/carbon-avoided

- **Objetivo:** Reporte ESG en XML
- **URL:** `GET http://127.0.0.1:5007/api/v1/alerts/esg/carbon-avoided`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Accept: application/xml
X-Correlation-Id: ed522b5f814f4e4f
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<reporte_esg_sostenibilidad><alimento_recuperado_kg>0.0</alimento_recuperado_kg><ahorro_financiero_mxn>0.0</ahorro_financiero_mxn><co2e_evitado_kg>0.0</co2e_evitado_kg><co2e_evitado_toneladas>0.0</co2e_evitado_toneladas><factor_conversion>2.5 kg CO2e / kg perecedero</factor_conversion><fuente>postgres</fuente></reporte_esg_sostenibilidad>
```

<a id="caso-74"></a>
## 74. svc-alerts — GET /api/v1/alerts/analytics/kpis

- **Objetivo:** Alertas por locación y criticidad (agregación)
- **URL:** `GET http://127.0.0.1:5007/api/v1/alerts/analytics/kpis`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 180686ffa36e43f5
```

**Respuesta (application/json):**

```json
{
  "total_grupos": 10,
  "kpis_alertas": [
    {
      "total_alertas": 240,
      "id_locacion": 3,
      "criticidad": "WARNING",
      "promedio_dias_restantes": 9.3
    },
    {
      "total_alertas": 15,
      "id_locacion": 3,
      "criticidad": "CRITICAL",
      "promedio_dias_restantes": 1.0
    },
    {
      "total_alertas": 15,
      "id_locacion": 7,
      "criticidad": "WARNING",
      "promedio_dias_restantes": 2.6
    },
    {
      "total_alertas": 12,
      "id_locacion": 5,
      "criticidad": "WARNING",
      "promedio_dias_restantes": 3.0
    },
    {
      "total_alertas": 9,
      "id_locacion": 7,
      "criticidad": "CRITICAL",
      "promedio_dias_restantes": 0.7
    },
    {
      "total_alertas": 6,
      "id_locacion": 4,
      "criticidad": "WARNING",
      "promedio_dias_restantes": 2.0
    },
    {
      "total_alertas": 6,
      "id_locacion": 6,
      "criticidad": "WARNING",
      "promedio_dias_restantes": 2.0
    },
    {
      "total_alertas": 3,
      "id_locacion": 4,
      "criticidad": "CRITICAL",
      "promedio_dias_restantes": 0.0
    },
    {
      "total_alertas": 3,
      "id_locacion": 5,
      "criticidad": "CRITICAL",
      "promedio_dias_restantes": 0.0
    },
    {
      "total_alertas": 3,
      "id_locacion": 6,
      "criticidad": "CRITICAL",
      "promedio_dias_restantes": 1.0
    }
  ]
}
```

<a id="caso-75"></a>
## 75. svc-audit — POST /api/v1/audit/log

- **Objetivo:** Registro explícito de cumplimiento (identidad tomada del JWT)
- **URL:** `POST http://127.0.0.1:5008/api/v1/audit/log`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
X-Correlation-Id: 2d5679137370430b
```

**Cuerpo de la petición:**

```xml
<audit_log_request><accion>REVISION_CUMPLIMIENTO</accion><descripcion>Revisión de mermas de octubre</descripcion></audit_log_request>
```

**Respuesta (application/json):**

```json
{
  "id_evento": "e3c880e9-b047-4716-b0a9-de292d2852bf",
  "status": "REGISTRADO"
}
```

<a id="caso-76"></a>
## 76. svc-audit — GET /api/v1/audit/events

- **Objetivo:** Bitácora filtrada y paginada
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/events?accion=REVISION_CUMPLIMIENTO&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 16d12c33645c41b2
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 8,
    "total_paginas": 3
  },
  "bitacora": [
    {
      "id_evento": "e3c880e9-b047-4716-b0a9-de292d2852bf",
      "fecha_evento": "2026-10-24T05:46:12.960545+00:00",
      "accion": "REVISION_CUMPLIMIENTO",
      "nombre_tabla": "sistema",
      "id_registro": null,
      "descripcion": "Revisión de mermas de octubre",
      "usuario_email": "auditor@freshtrack.mx",
      "ip": "172.19.0.1/32"
    },
    {
      "id_evento": "3e015501-e178-4a31-b16b-0c8286252976",
      "fecha_evento": "2026-10-24T05:38:29.744595+00:00",
      "accion": "REVISION_CUMPLIMIENTO",
      "nombre_tabla": "sistema",
      "id_registro": null,
      "descripcion": "pytest-a0cfc12c",
      "usuario_email": "auditor@freshtrack.mx",
      "ip": "127.0.0.1/32"
    },
    {
      "id_evento": "dc5eec4b-d9a7-4e7c-b53b-ae2909d4ba40",
      "fecha_evento": "2026-10-24T05:38:17.295875+00:00",
      "accion": "REVISION_CUMPLIMIENTO",
      "nombre_tabla": "sistema",
      "id_registro": null,
      "descripcion": "pytest-db0fc99d",
      "usuario_email": "auditor@freshtrack.mx",
      "ip": "127.0.0.1/32"
    }
  ]
}
```

<a id="caso-77"></a>
## 77. svc-audit — GET /api/v1/audit/events

- **Objetivo:** Fecha inválida
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/events?desde=2026-13-01`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 9a6ac63d96474fa7
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'desde' debe tener formato YYYY-MM-DD.",
  "status": 400,
  "correlation_id": "9a6ac63d96474fa7"
}
```

<a id="caso-78"></a>
## 78. svc-audit — GET /api/v1/audit/events

- **Objetivo:** Gerente sin permiso sobre la bitácora
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/events`
- **Código HTTP:** `403` (esperado `403`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 83af21a0e4a14d0c
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'store_manager' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "83af21a0e4a14d0c",
  "detalles": {
    "roles_permitidos": [
      "admin",
      "auditor"
    ]
  }
}
```

<a id="caso-79"></a>
## 79. svc-audit — GET /api/v1/audit/traceability/no-es-uuid

- **Objetivo:** Identificador de lote inválido
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/traceability/no-es-uuid`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: fe8b823fc08e4c5a
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_lote' debe ser un UUID válido.",
  "status": 400,
  "correlation_id": "fe8b823fc08e4c5a"
}
```

<a id="caso-80"></a>
## 80. svc-audit — GET /api/v1/audit/stream/recent

- **Objetivo:** Eventos de dominio en Redis Streams
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/stream/recent?n=5`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: e92e33285f66436f
```

**Respuesta (application/json):**

```json
{
  "total": 5,
  "stream_eventos": [
    {
      "event_id": "f83fac62acc244d5b9bcbec67c4bb96e",
      "event_type": "ALERTA_ATENDIDA",
      "timestamp": "2026-10-24T05:46:12.710048+00:00",
      "correlation_id": "e096fe7681b24af0",
      "user_id": "d22e216e-fc08-4514-bb15-934256e262ad",
      "user_role": "store_manager",
      "location_id": "",
      "payload": {
        "id_mongo": "6adc4624976c8bfea977970a"
      },
      "id": "1792820772710-0"
    },
    {
      "event_id": "13f2c34a68034da6aeb93af7414a967e",
      "event_type": "ALERTA_EMITIDA",
      "timestamp": "2026-10-24T05:46:12.698055+00:00",
      "correlation_id": "f6e909b639d74333",
      "user_id": "d22e216e-fc08-4514-bb15-934256e262ad",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "mongo_id": "6adc4624976c8bfea977970a",
        "criticidad": "WARNING",
        "id_sku": 4,
        "dias_restantes": 5
      },
      "id": "1792820772698-0"
    },
    {
      "event_id": "82751f548fe24fa6b84a9584d7de7777",
      "event_type": "ALERTA_EMITIDA",
      "timestamp": "2026-10-24T05:46:12.697072+00:00",
      "correlation_id": "f6e909b639d74333",
      "user_id": "d22e216e-fc08-4514-bb15-934256e262ad",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "mongo_id": "6adc4624976c8bfea9779709",
        "criticidad": "WARNING",
        "id_sku": 8,
        "dias_restantes": 3
      },
      "id": "1792820772697-0"
    },
    {
      "event_id": "d736e834456e4e6783fadb47ed0087bc",
      "event_type": "ALERTA_EMITIDA",
      "timestamp": "2026-10-24T05:46:12.696093+00:00",
      "correlation_id": "f6e909b639d74333",
      "user_id": "d22e216e-fc08-4514-bb15-934256e262ad",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "mongo_id": "6adc4624976c8bfea9779708",
        "criticidad": "WARNING",
        "id_sku": 5,
        "dias_restantes": 2
      },
      "id": "1792820772696-0"
    },
    {
      "event_id": "cb7eae00a68346c29b8d1cde191ad7d0",
      "event_type": "ALERTA_EMITIDA",
      "timestamp": "2026-10-24T05:46:12.695198+00:00",
      "correlation_id": "f6e909b639d74333",
      "user_id": "d22e216e-fc08-4514-bb15-934256e262ad",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "mongo_id": "6adc4624976c8bfea9779707",
        "criticidad": "CRITICAL",
        "id_sku": 6,
        "dias_restantes": 1
      },
      "id": "1792820772695
… (respuesta recortada)
```

<a id="caso-81"></a>
## 81. svc-auth — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5001/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Accept: application/xml
X-Correlation-Id: a4ebcfccb7d2477c
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<service_health><service>svc-auth</service><status>HEALTHY</status><version>1.0.0</version><dependencies><postgres>true</postgres><redis>true</redis></dependencies></service_health>
```

<a id="caso-82"></a>
## 82. svc-catalog — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5002/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 8ddeeb901b7d4d4b
```

**Respuesta (application/json):**

```json
{
  "service": "svc-catalog",
  "status": "HEALTHY",
  "version": "1.0.0",
  "dependencies": {
    "postgres": true,
    "redis": true
  }
}
```

<a id="caso-83"></a>
## 83. svc-inventory — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5003/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 441039e27c324ed0
```

**Respuesta (application/json):**

```json
{
  "service": "svc-inventory",
  "status": "HEALTHY",
  "version": "1.0.0",
  "dependencies": {
    "postgres": true,
    "redis": true
  }
}
```

<a id="caso-84"></a>
## 84. svc-commercial — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5004/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 5fd03984272b42a9
```

**Respuesta (application/json):**

```json
{
  "service": "svc-commercial",
  "status": "HEALTHY",
  "version": "1.0.0",
  "dependencies": {
    "postgres": true,
    "redis": true
  }
}
```

<a id="caso-85"></a>
## 85. svc-asn — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5005/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: cefa7a2179d7486f
```

**Respuesta (application/json):**

```json
{
  "service": "svc-asn",
  "status": "HEALTHY",
  "version": "1.0.0",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true
  }
}
```

<a id="caso-86"></a>
## 86. svc-planning — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5006/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 936c1e265dc14f17
```

**Respuesta (application/json):**

```json
{
  "service": "svc-planning",
  "status": "HEALTHY",
  "version": "1.0.0",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true
  }
}
```

<a id="caso-87"></a>
## 87. svc-alerts — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5007/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 4914ec9ef4704b5e
```

**Respuesta (application/json):**

```json
{
  "service": "svc-alerts",
  "status": "HEALTHY",
  "version": "1.0.0",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true
  }
}
```

<a id="caso-88"></a>
## 88. svc-audit — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5008/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 444945cd0ddf4c55
```

**Respuesta (application/json):**

```json
{
  "service": "svc-audit",
  "status": "HEALTHY",
  "version": "1.0.0",
  "dependencies": {
    "postgres": true,
    "redis": true
  }
}
```
