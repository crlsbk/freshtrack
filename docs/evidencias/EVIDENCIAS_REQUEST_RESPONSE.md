# Evidencias de petición y respuesta — Microservicios FreshTrack

Generado el 2026-10-23 18:46 con `python scripts/generar_evidencias.py --host 127.0.0.1` mediante peticiones HTTP reales contra los contenedores. Los tokens se muestran abreviados.

**83 de 87 casos** respondieron con el código esperado.

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
| [12](#caso-12) | svc-auth | GET | `/api/v1/auth/sessions/b948b8ac-39e1-4f2e-9875-edeadecf45a0` | Usuario inexistente | 404 | ✅ 404 |
| [13](#caso-13) | svc-auth | GET | `/api/v1/auth/sessions/8367ce14-39d4-4f30-bbdf-7778386d17b3` | Sesiones activas en Redis con TTL restante | 200 | ✅ 200 |
| [14](#caso-14) | svc-auth | DELETE | `/api/v1/auth/sessions/8367ce14-39d4-4f30-bbdf-7778386d17b3` | Cierre forzado de todas las sesiones de un usuario | 200 | ✅ 200 |
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
| [25](#caso-25) | svc-catalog | GET | `/api/v1/catalog/products/13` | Detalle por SKU | 200 | ✅ 200 |
| [26](#caso-26) | svc-catalog | PATCH | `/api/v1/catalog/products/13` | Actualización parcial (PATCH) | 200 | ✅ 200 |
| [27](#caso-27) | svc-catalog | PUT | `/api/v1/catalog/products/13` | Reemplazo completo (PUT) | 200 | ✅ 200 |
| [28](#caso-28) | svc-catalog | PATCH | `/api/v1/catalog/products/13` | Regla de negocio: precio de venta menor al costo | 409 | ✅ 409 |
| [29](#caso-29) | svc-catalog | POST | `/api/v1/catalog/products` | Campos obligatorios faltantes | 400 | ✅ 400 |
| [30](#caso-30) | svc-catalog | DELETE | `/api/v1/catalog/products/13` | Baja reservada a admin | 403 | ✅ 403 |
| [31](#caso-31) | svc-catalog | DELETE | `/api/v1/catalog/products/13` | Baja lógica (activo=false) | 200 | ✅ 200 |
| [32](#caso-32) | svc-catalog | GET | `/api/v1/catalog/products/99999999` | SKU inexistente | 404 | ✅ 404 |
| [33](#caso-33) | svc-catalog | GET | `/api/v1/catalog/locations?tipo=Tienda` | Tiendas (Cache-Aside) | 200 | ✅ 200 |
| [34](#caso-34) | svc-inventory | GET | `/api/v1/inventory/stock?id_locacion=3&dias_max=7&por_pagina=5` | Existencias por vencer en ≤7 días (paginado, orden FEFO) | 200 | ✅ 200 |
| [35](#caso-35) | svc-inventory | GET | `/api/v1/inventory/fefo-queue/1/3` | Cola FEFO en XML | 200 | ✅ 200 |
| [36](#caso-36) | svc-inventory | GET | `/api/v1/inventory/fefo-queue/99999999/3` | SKU inexistente en la cola FEFO | 404 | ✅ 404 |
| [37](#caso-37) | svc-inventory | POST | `/api/v1/inventory/reserve-fefo` | Reserva FEFO con lock distribuido en Redis (XML) | 200 | ⚠️ 409 |
| [38](#caso-38) | svc-inventory | POST | `/api/v1/inventory/cancel-reservation` | Compensación: libera la reserva guardada en Redis | 200 | ⚠️ 404 |
| [39](#caso-39) | svc-inventory | POST | `/api/v1/inventory/reserve-fefo` | Stock insuficiente (rollback) | 409 | ✅ 409 |
| [40](#caso-40) | svc-inventory | POST | `/api/v1/inventory/reserve-fefo` | Tipo de dato inválido | 400 | ✅ 400 |
| [41](#caso-41) | svc-inventory | POST | `/api/v1/inventory/reserve-fefo` | Auditor no puede reservar | 403 | ✅ 403 |
| [42](#caso-42) | svc-commercial | POST | `/api/v1/commercial/checkout` | Venta POS por Saga: reserva FEFO → venta → descuento de existencias | 201 | ⚠️ 409 |
| [43](#caso-43) | svc-commercial | POST | `/api/v1/commercial/checkout` | Venta rechazada por stock (compensación de la saga, respuesta XML) | 409 | ✅ 409 |
| [44](#caso-44) | svc-commercial | POST | `/api/v1/commercial/checkout` | XML que no cumple checkout_request.xsd | 400 | ✅ 400 |
| [45](#caso-45) | svc-commercial | PUT | `/api/v1/commercial/cart/caja1-85b0` | Carrito temporal en Redis (TTL 15 min) | 200 | ✅ 200 |
| [46](#caso-46) | svc-commercial | GET | `/api/v1/commercial/cart/caja1-85b0` | Consulta del carrito con TTL restante | 200 | ✅ 200 |
| [47](#caso-47) | svc-commercial | DELETE | `/api/v1/commercial/cart/caja1-85b0` | Consumo atómico (GET+DEL en Lua) | 200 | ✅ 200 |
| [48](#caso-48) | svc-commercial | GET | `/api/v1/commercial/cart/caja1-85b0` | Carrito ya consumido | 404 | ✅ 404 |
| [49](#caso-49) | svc-commercial | POST | `/api/v1/commercial/shrinkage` | Merma sobre un lote que no existe | 409 | ✅ 409 |
| [50](#caso-50) | svc-commercial | POST | `/api/v1/commercial/shrinkage` | Causa de merma inválida | 400 | ✅ 400 |
| [51](#caso-51) | svc-commercial | GET | `/api/v1/commercial/sales?id_locacion=3&desde=2026-09-23&por_pagina=3` | Historial de ventas por rango de fechas | 200 | ✅ 200 |
| [52](#caso-52) | svc-asn | POST | `/api/v1/asn` | Ingesta de ASN en XML (validado con asn_request.xsd) → documento en MongoDB | 201 | ✅ 201 |
| [53](#caso-53) | svc-asn | POST | `/api/v1/asn` | Folio duplicado (índice único en MongoDB) | 409 | ✅ 409 |
| [54](#caso-54) | svc-asn | POST | `/api/v1/asn` | SKU inexistente en PostgreSQL (integración PG↔Mongo) | 409 | ✅ 409 |
| [55](#caso-55) | svc-asn | GET | `/api/v1/asn/ASN-EV-8600DC` | Recuperación por folio | 200 | ✅ 200 |
| [56](#caso-56) | svc-asn | PATCH | `/api/v1/asn/ASN-EV-8600DC/status` | Transición de estado inválida | 409 | ✅ 409 |
| [57](#caso-57) | svc-asn | PATCH | `/api/v1/asn/ASN-EV-8600DC/status` | Actualización de documento ($set) | 200 | ✅ 200 |
| [58](#caso-58) | svc-asn | POST | `/api/v1/asn/ASN-EV-8600DC/inspection` | Inspección agregada con $push | 201 | ✅ 201 |
| [59](#caso-59) | svc-asn | GET | `/api/v1/asn?id_sku=2&estado=EN_TRANSITO&por_pagina=5` | Filtrado por campo anidado y estado | 200 | ✅ 200 |
| [60](#caso-60) | svc-asn | GET | `/api/v1/asn/analytics/summary` | Pipeline de agregación ($unwind/$group/$sort) | 200 | ✅ 200 |
| [61](#caso-61) | svc-asn | GET | `/api/v1/asn/NO-EXISTE` | Folio inexistente | 404 | ✅ 404 |
| [62](#caso-62) | svc-planning | POST | `/api/v1/planning/forecast/run` | Corrida de pronóstico (linaje en PostgreSQL, serie en MongoDB) | 201 | ✅ 201 |
| [63](#caso-63) | svc-planning | POST | `/api/v1/planning/forecast/run` | Método no soportado | 400 | ✅ 400 |
| [64](#caso-64) | svc-planning | GET | `/api/v1/planning/forecast/latest/1/3` | Última serie pronosticada (MongoDB) | 200 | ⚠️ 404 |
| [65](#caso-65) | svc-planning | GET | `/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=3` | Órdenes pendientes paginadas | 200 | ✅ 200 |
| [66](#caso-66) | svc-planning | POST | `/api/v1/planning/replenishment/orders/6edb7681-3eca-4598-8e37-9c774836c962/approve` | Aprobar orden inexistente | 404 | ✅ 404 |
| [67](#caso-67) | svc-planning | GET | `/api/v1/planning/sku/1/full-context?id_locacion=3` | Contexto híbrido PostgreSQL + MongoDB | 200 | ✅ 200 |
| [68](#caso-68) | svc-planning | GET | `/api/v1/planning/forecast/analytics/kpis` | Métricas por modelo (agregación) | 200 | ✅ 200 |
| [69](#caso-69) | svc-alerts | POST | `/api/v1/alerts/scan?id_locacion=3&dias=5` | Escaneo con lock distribuido → alertas en MongoDB + eventos en Redis Streams | 200 | ✅ 200 |
| [70](#caso-70) | svc-alerts | GET | `/api/v1/alerts/active?id_locacion=3&limite=3` | Alertas abiertas filtradas | 200 | ✅ 200 |
| [71](#caso-71) | svc-alerts | PATCH | `/api/v1/alerts/zzz/resolve` | ObjectId inválido | 400 | ✅ 400 |
| [72](#caso-72) | svc-alerts | GET | `/api/v1/alerts/esg/carbon-avoided` | Reporte ESG en XML | 200 | ✅ 200 |
| [73](#caso-73) | svc-alerts | GET | `/api/v1/alerts/analytics/kpis` | Alertas por locación y criticidad (agregación) | 200 | ✅ 200 |
| [74](#caso-74) | svc-audit | POST | `/api/v1/audit/log` | Registro explícito de cumplimiento (identidad tomada del JWT) | 201 | ✅ 201 |
| [75](#caso-75) | svc-audit | GET | `/api/v1/audit/events?accion=REVISION_CUMPLIMIENTO&por_pagina=3` | Bitácora filtrada y paginada | 200 | ✅ 200 |
| [76](#caso-76) | svc-audit | GET | `/api/v1/audit/events?desde=2026-13-01` | Fecha inválida | 400 | ✅ 400 |
| [77](#caso-77) | svc-audit | GET | `/api/v1/audit/events` | Gerente sin permiso sobre la bitácora | 403 | ✅ 403 |
| [78](#caso-78) | svc-audit | GET | `/api/v1/audit/traceability/no-es-uuid` | Identificador de lote inválido | 400 | ✅ 400 |
| [79](#caso-79) | svc-audit | GET | `/api/v1/audit/stream/recent?n=5` | Eventos de dominio en Redis Streams | 200 | ✅ 200 |
| [80](#caso-80) | svc-auth | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [81](#caso-81) | svc-catalog | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [82](#caso-82) | svc-inventory | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [83](#caso-83) | svc-commercial | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [84](#caso-84) | svc-asn | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [85](#caso-85) | svc-planning | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [86](#caso-86) | svc-alerts | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |
| [87](#caso-87) | svc-audit | GET | `/health` | Endpoint de salud con estado de dependencias | 200 | ✅ 200 |

<a id="caso-1"></a>
## 1. svc-auth — POST /api/v1/auth/login

- **Objetivo:** Inicio de sesión correcto (JSON): emite JWT y crea session:{jti} en Redis
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/login`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Content-Type: application/json
X-Correlation-Id: 532c98b0c7e244f4
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
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyYzQzNTZhNi04OWU0LTRlZWYtOWZlNS1kZDkwM2E5MzFmYzIiLCJlbWFpbCI6ImdlcmVudGVAZnJlc2h0cmFjay5teCIsIm5vbWJyZSI6Ikx1aXMgUFx1MDBlOXJleiIsInJvbCI6InN0b3JlX21hbmFnZXIiLCJpZF9sb2NhY2lvbiI6MywianRpIjoiYzdmZGNlOTgzOWFiNGM1ZTlmNWNjYWM4YzFiNjQyM2YiLCJpYXQiOjE3OTI4MDI3OTEsImV4cCI6MTc5MjgzMTU5MSwiaXNzIjoiZnJlc2h0cmFjayJ9.SEwq1w6RZ_2hvfnAL3S2RXLJEG86dsfLQgkTUxxGZas",
  "jti": "c7fdce9839ab4c5e9f5ccac8c1b6423f",
  "token_type": "Bearer",
  "expira_en_segundos": 28800,
  "usuario": {
    "id_usuario": "2c4356a6-89e4-4eef-9fe5-dd903a931fc2",
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
X-Correlation-Id: 0c80e30166384cec
```

**Cuerpo de la petición:**

```xml
<login_request><email>auditor@freshtrack.mx</email><password>Auditor2026!</password></login_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<auth_response><token>eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlMmMwMzc3Mi1lZDNhLTRlMmQtYjM4OS1kMTllYTBlODI5ZmEiLCJlbWFpbCI6ImF1ZGl0b3JAZnJlc2h0cmFjay5teCIsIm5vbWJyZSI6IklybWEgU2FsaW5hcyIsInJvbCI6ImF1ZGl0b3IiLCJpZF9sb2NhY2lvbiI6MSwianRpIjoiMjFlMjFmMGM1MzY0NDBkZTk0YTcyODQ0MmIxMzk2NTEiLCJpYXQiOjE3OTI4MDI3OTEsImV4cCI6MTc5MjgzMTU5MSwiaXNzIjoiZnJlc2h0cmFjayJ9.14HY-0IqP-PkWKfy8saehGHtpYioNE2LF0gzXOTq0jw</token><jti>21e21f0c536440de94a728442b139651</jti><token_type>Bearer</token_type><expira_en_segundos>28800</expira_en_segundos><usuario><id_usuario>e2c03772-ed3a-4e2d-b389-d19ea0e829fa</id_usuario><email>auditor@freshtrack.mx</email><nombre>Irma Salinas</nombre><rol>auditor</rol><id_locacion>1</id_locacion></usuario></auth_response>
```

<a id="caso-3"></a>
## 3. svc-auth — POST /api/v1/auth/login

- **Objetivo:** Credenciales incorrectas (no revela si el correo existe)
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/login`
- **Código HTTP:** `401` (esperado `401`)
- **Headers:**

```http
Content-Type: application/json
X-Correlation-Id: 4d7004cf53194550
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
  "correlation_id": "4d7004cf53194550"
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
X-Correlation-Id: bbf703bb2c394bd7
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
  "correlation_id": "bbf703bb2c394bd7",
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
X-Correlation-Id: dbd27940198c4219
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
  "correlation_id": "dbd27940198c4219"
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
X-Correlation-Id: 4c2725ecb2f44a97
```

**Respuesta (application/json):**

```json
{
  "valido": true,
  "usuario": {
    "id_usuario": "a43bf0c6-2208-453e-ab74-640b452db324",
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
X-Correlation-Id: 8f1efeaefa9f4f2b
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "4c43770c-8ae2-4b3f-a27b-0eb1a1222a9b",
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
X-Correlation-Id: fd3fc265eba94543
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
      "id_usuario": "4b981af5-7857-471c-902a-a4075e6649c9",
      "email": "gerente2@freshtrack.mx",
      "nombre_completo": "Ana Ruiz",
      "rol": "store_manager",
      "id_locacion": 4,
      "estado_activo": true,
      "fecha_alta": "2026-10-23T22:26:29.748035+00:00"
    },
    {
      "id_usuario": "2c4356a6-89e4-4eef-9fe5-dd903a931fc2",
      "email": "gerente@freshtrack.mx",
      "nombre_completo": "Luis Pérez",
      "rol": "store_manager",
      "id_locacion": 3,
      "estado_activo": true,
      "fecha_alta": "2026-10-23T22:26:29.748035+00:00"
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
X-Correlation-Id: d216e551f3bf4ec7
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'auditor' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "d216e551f3bf4ec7",
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
X-Correlation-Id: 88fbf8a0622044b6
```

**Respuesta (application/json):**

```json
{
  "error": "token_requerido",
  "mensaje": "Token de autenticación requerido (Authorization: Bearer <token>).",
  "status": 401,
  "correlation_id": "88fbf8a0622044b6"
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
X-Correlation-Id: ca3515cabe774cf0
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_usuario' debe ser un UUID válido.",
  "status": 400,
  "correlation_id": "ca3515cabe774cf0"
}
```

<a id="caso-12"></a>
## 12. svc-auth — GET /api/v1/auth/sessions/b948b8ac-39e1-4f2e-9875-edeadecf45a0

- **Objetivo:** Usuario inexistente
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/sessions/b948b8ac-39e1-4f2e-9875-edeadecf45a0`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: b3ab9645be9741b1
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Usuario b948b8ac-39e1-4f2e-9875-edeadecf45a0 no encontrado.",
  "status": 404,
  "correlation_id": "b3ab9645be9741b1"
}
```

<a id="caso-13"></a>
## 13. svc-auth — GET /api/v1/auth/sessions/8367ce14-39d4-4f30-bbdf-7778386d17b3

- **Objetivo:** Sesiones activas en Redis con TTL restante
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/sessions/8367ce14-39d4-4f30-bbdf-7778386d17b3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 54426271c7e24e3b
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "8367ce14-39d4-4f30-bbdf-7778386d17b3",
  "total_activas": 2,
  "sesiones": [
    {
      "id_usuario": "8367ce14-39d4-4f30-bbdf-7778386d17b3",
      "email": "planner@freshtrack.mx",
      "nombre": "Carlos Vega",
      "rol": "planner",
      "id_locacion": 1,
      "jti": "5d63e8b3e0e445ad876e96135a3f7fa7",
      "ip": "172.20.0.1",
      "user_agent": "Python-urllib/3.14",
      "login_en": "2026-10-24T00:46:31.587378+00:00",
      "ttl_restante_segundos": 28800
    },
    {
      "id_usuario": "8367ce14-39d4-4f30-bbdf-7778386d17b3",
      "email": "planner@freshtrack.mx",
      "nombre": "Carlos Vega",
      "rol": "planner",
      "id_locacion": 1,
      "jti": "84df797b34104ef0a88a2e823dd905f8",
      "ip": "172.20.0.1",
      "user_agent": "Python-urllib/3.14",
      "login_en": "2026-10-24T00:46:31.945206+00:00",
      "ttl_restante_segundos": 28800
    }
  ]
}
```

<a id="caso-14"></a>
## 14. svc-auth — DELETE /api/v1/auth/sessions/8367ce14-39d4-4f30-bbdf-7778386d17b3

- **Objetivo:** Cierre forzado de todas las sesiones de un usuario
- **URL:** `DELETE http://127.0.0.1:5001/api/v1/auth/sessions/8367ce14-39d4-4f30-bbdf-7778386d17b3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: c5ab5c7a2d9942e7
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "8367ce14-39d4-4f30-bbdf-7778386d17b3",
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
X-Correlation-Id: d8f33f466e2e4a3d
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "d8f33f466e2e4a3d"
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
X-Correlation-Id: a4b3c738484b448e
```

**Respuesta (application/json):**

```json
{
  "total_metricas": 6,
  "contadores": {
    "counter:ops:auth:access_denied_no_token:20261024": 1,
    "counter:ops:auth:login_failed:20261024": 2,
    "counter:ops:auth:access_denied_role:20261024": 1,
    "counter:ops:auth:access_denied_revoked:20261024": 1,
    "counter:ops:auth:access_granted:20261024": 7,
    "counter:ops:auth:login_success:20261024": 10
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
X-Correlation-Id: 6f0a82c5f6174e49
```

**Respuesta (application/json):**

```json
{
  "status": "LOGOUT_EXITOSO",
  "jti": "e0885927ccea4fc3b19ee17ad7874b88"
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
X-Correlation-Id: fc731edd5ede4f6b
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "fc731edd5ede4f6b"
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
X-Correlation-Id: 8f2a5e1ae9284a22
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "8f2a5e1ae9284a22"
}
```

<a id="caso-20"></a>
## 20. svc-catalog — GET /api/v1/catalog/products

- **Objetivo:** Productos filtrados y paginados (Cache-Aside: 1.ª vez PostgreSQL)
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: c94b2ef4181e4ce9
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
X-Correlation-Id: a7d4f845939b409b
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
X-Correlation-Id: 48c91da73bea4acd
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalogo_productos><paginacion><pagina>1</pagina><por_pagina>2</por_pagina><total>12</total><total_paginas>6</total_paginas></paginacion><productos><item><id_sku>12</id_sku><codigo_gtin>07501234560126</codigo_gtin><nombre>Arroz 1kg</nombre><categoria>Abarrotes</categoria><unidad_medida>Paquete</unidad_medida><id_proveedor>6</id_proveedor><stock_seguridad>100.0</stock_seguridad><punto_reorden>180.0</punto_reorden><perecedero>true</perecedero><vida_util_estandar>365</vida_util_estandar><precio_costo>22.0</precio_costo><precio_venta>33.5</precio_venta><activo>true</activo></item><item><id_sku>9</id_sku><codigo_gtin>07501234560096</codigo_gtin><nombre>Crema Ácida 450g</nombre><categoria>Lácteos</categoria><unidad_medida>Pieza</unidad_medida><id_proveedor>1</id_proveedor><stock_seguridad>35.0</stock_seguridad><punto_reorden>70.0</punto_reorden><perecedero>true</perecedero><vida_util_estandar>20</vida_util_estandar><precio_costo>26.0</precio_costo><precio_venta>38.0</precio_venta><activo>true</activo></item></productos><fuente>postgres</fuente></catalogo_productos>
```

<a id="caso-23"></a>
## 23. svc-catalog — GET /api/v1/catalog/products

- **Objetivo:** Parámetro de paginación inválido
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products?pagina=0`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
X-Correlation-Id: 855fa823c5644392
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'pagina' debe ser mayor o igual a 1.",
  "status": 400,
  "correlation_id": "855fa823c5644392"
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
X-Correlation-Id: 6dd2b56370684f8a
```

**Cuerpo de la petición:**

```xml
<producto_request><nombre>Fresa evidencia 2f1ed</nombre><categoria>Frutas</categoria><precio_costo>20</precio_costo><precio_venta>35.5</precio_venta><vida_util_estandar>5</vida_util_estandar></producto_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<producto_creado><id_sku>13</id_sku><nombre>Fresa evidencia 2f1ed</nombre><status>CREADO</status></producto_creado>
```

<a id="caso-25"></a>
## 25. svc-catalog — GET /api/v1/catalog/products/13

- **Objetivo:** Detalle por SKU
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products/13`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 75e470919f3f4714
```

**Respuesta (application/json):**

```json
{
  "id_sku": 13,
  "codigo_gtin": "21792802792254",
  "nombre": "Fresa evidencia 2f1ed",
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
## 26. svc-catalog — PATCH /api/v1/catalog/products/13

- **Objetivo:** Actualización parcial (PATCH)
- **URL:** `PATCH http://127.0.0.1:5002/api/v1/catalog/products/13`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 2246c446f19448bd
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
  "id_sku": 13,
  "codigo_gtin": "21792802792254",
  "nombre": "Fresa evidencia 2f1ed",
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
## 27. svc-catalog — PUT /api/v1/catalog/products/13

- **Objetivo:** Reemplazo completo (PUT)
- **URL:** `PUT http://127.0.0.1:5002/api/v1/catalog/products/13`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: b46e0d6858474232
```

**Cuerpo de la petición:**

```json
{
  "nombre": "Fresa evidencia 2f1ed",
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
  "id_sku": 13,
  "codigo_gtin": "21792802792254",
  "nombre": "Fresa evidencia 2f1ed",
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
## 28. svc-catalog — PATCH /api/v1/catalog/products/13

- **Objetivo:** Regla de negocio: precio de venta menor al costo
- **URL:** `PATCH http://127.0.0.1:5002/api/v1/catalog/products/13`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 2b0ad0fd9ea34291
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
  "correlation_id": "2b0ad0fd9ea34291"
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
X-Correlation-Id: d6c93b5a2e304df5
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
  "correlation_id": "d6c93b5a2e304df5",
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
## 30. svc-catalog — DELETE /api/v1/catalog/products/13

- **Objetivo:** Baja reservada a admin
- **URL:** `DELETE http://127.0.0.1:5002/api/v1/catalog/products/13`
- **Código HTTP:** `403` (esperado `403`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: d5cb97a2183a4d5b
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'buyer' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "d5cb97a2183a4d5b",
  "detalles": {
    "roles_permitidos": [
      "admin"
    ]
  }
}
```

<a id="caso-31"></a>
## 31. svc-catalog — DELETE /api/v1/catalog/products/13

- **Objetivo:** Baja lógica (activo=false)
- **URL:** `DELETE http://127.0.0.1:5002/api/v1/catalog/products/13`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 0b64098192d74592
```

**Respuesta (application/json):**

```json
{
  "id_sku": 13,
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
X-Correlation-Id: d3de0ed356174661
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "SKU 99999999 no encontrado.",
  "status": 404,
  "correlation_id": "d3de0ed356174661"
}
```

<a id="caso-33"></a>
## 33. svc-catalog — GET /api/v1/catalog/locations

- **Objetivo:** Tiendas (Cache-Aside)
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/locations?tipo=Tienda`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 1e224f31a1a14e3c
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
X-Correlation-Id: 2a8eb392a81b40f9
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 5,
    "total": 0,
    "total_paginas": 1
  },
  "existencias": []
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
X-Correlation-Id: 8b0f587276e4415e
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<fefo_queue><id_sku>1</id_sku><id_locacion>3</id_locacion><total_lotes>0</total_lotes><lotes_fefo /></fefo_queue>
```

<a id="caso-36"></a>
## 36. svc-inventory — GET /api/v1/inventory/fefo-queue/99999999/3

- **Objetivo:** SKU inexistente en la cola FEFO
- **URL:** `GET http://127.0.0.1:5003/api/v1/inventory/fefo-queue/99999999/3`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 070fbad0d9944f3b
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "SKU 99999999 no existe.",
  "status": 404,
  "correlation_id": "070fbad0d9944f3b"
}
```

<a id="caso-37"></a>
## 37. svc-inventory — POST /api/v1/inventory/reserve-fefo

- **Objetivo:** Reserva FEFO con lock distribuido en Redis (XML)
- **URL:** `POST http://127.0.0.1:5003/api/v1/inventory/reserve-fefo`
- **Código HTTP:** `409` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
X-Correlation-Id: f996d8e9159642f5
```

**Cuerpo de la petición:**

```xml
<reserva_request><id_locacion>3</id_locacion><saga_id>evidencia-d4de4843</saga_id><lineas><item><id_sku>1</id_sku><cantidad>1</cantidad></item></lineas></reserva_request>
```

**Respuesta (application/json):**

```json
{
  "error": "stock_insuficiente",
  "mensaje": "Stock insuficiente para el SKU 1.",
  "status": 409,
  "correlation_id": "f996d8e9159642f5",
  "detalles": {
    "id_sku": 1,
    "disponible": 0,
    "solicitado": 1.0
  }
}
```

<a id="caso-38"></a>
## 38. svc-inventory — POST /api/v1/inventory/cancel-reservation

- **Objetivo:** Compensación: libera la reserva guardada en Redis
- **URL:** `POST http://127.0.0.1:5003/api/v1/inventory/cancel-reservation`
- **Código HTTP:** `404` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 688f2d02091c4a2a
```

**Cuerpo de la petición:**

```json
{
  "saga_id": "evidencia-d4de4843"
}
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "No hay reserva vigente para la saga evidencia-d4de4843.",
  "status": 404,
  "correlation_id": "688f2d02091c4a2a"
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
X-Correlation-Id: 1017725d91e54526
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
  "correlation_id": "1017725d91e54526",
  "detalles": {
    "id_sku": 1,
    "disponible": 0,
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
X-Correlation-Id: 404fd53889db48a7
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
  "correlation_id": "404fd53889db48a7"
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
X-Correlation-Id: 044c63ad36a34638
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
  "correlation_id": "044c63ad36a34638",
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
- **Código HTTP:** `409` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: a21108a6b4d6480e
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
  "error": "venta_rechazada",
  "mensaje": "Stock insuficiente para 'Leche Entera 1L' (disponible: 0.00, solicitado: 1.00).",
  "status": 409,
  "correlation_id": "a21108a6b4d6480e"
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
X-Correlation-Id: 7c5955a90f044629
```

**Cuerpo de la petición:**

```xml
<checkout_request><id_locacion>3</id_locacion><lineas><item><id_sku>1</id_sku><cantidad>99999999</cantidad></item></lineas></checkout_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<error_response><error>venta_rechazada</error><mensaje>Stock insuficiente para 'Leche Entera 1L' (disponible: 0.00, solicitado: 99999999.00).</mensaje><status>409</status><correlation_id>7c5955a90f044629</correlation_id></error_response>
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
X-Correlation-Id: 6df80e140cbd4ef6
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
  "correlation_id": "6df80e140cbd4ef6",
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
## 45. svc-commercial — PUT /api/v1/commercial/cart/caja1-85b0

- **Objetivo:** Carrito temporal en Redis (TTL 15 min)
- **URL:** `PUT http://127.0.0.1:5004/api/v1/commercial/cart/caja1-85b0`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 9b52007441dc431f
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
  "cart_id": "caja1-85b0",
  "status": "GUARDADO",
  "ttl_segundos": 900
}
```

<a id="caso-46"></a>
## 46. svc-commercial — GET /api/v1/commercial/cart/caja1-85b0

- **Objetivo:** Consulta del carrito con TTL restante
- **URL:** `GET http://127.0.0.1:5004/api/v1/commercial/cart/caja1-85b0`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 6e3af2d80fdd4e40
```

**Respuesta (application/json):**

```json
{
  "cart_id": "caja1-85b0",
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
## 47. svc-commercial — DELETE /api/v1/commercial/cart/caja1-85b0

- **Objetivo:** Consumo atómico (GET+DEL en Lua)
- **URL:** `DELETE http://127.0.0.1:5004/api/v1/commercial/cart/caja1-85b0`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: ebf7892adca04938
```

**Respuesta (application/json):**

```json
{
  "cart_id": "caja1-85b0",
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
## 48. svc-commercial — GET /api/v1/commercial/cart/caja1-85b0

- **Objetivo:** Carrito ya consumido
- **URL:** `GET http://127.0.0.1:5004/api/v1/commercial/cart/caja1-85b0`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: efb177288ac64bb9
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Carrito expirado o inexistente.",
  "status": 404,
  "correlation_id": "efb177288ac64bb9"
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
X-Correlation-Id: 6f5b73aae02740a8
```

**Cuerpo de la petición:**

```json
{
  "id_lote": "e7cade07-08b0-436a-98e7-0e35d130d43a",
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
  "correlation_id": "6f5b73aae02740a8"
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
X-Correlation-Id: 995381836e994de2
```

**Cuerpo de la petición:**

```json
{
  "id_lote": "c5cf5ba5-2ae8-41c8-be99-e71ab6436e44",
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
  "correlation_id": "995381836e994de2"
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
X-Correlation-Id: f9d0e367c9b042a4
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
  "ventas": []
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
X-Correlation-Id: f06e3f1023204c35
```

**Cuerpo de la petición:**

```xml
<asn_request><folio_asn>ASN-EV-8600DC</folio_asn><id_proveedor>1</id_proveedor><detalle_carga><item_carga><id_sku>1</id_sku><cantidad_declarada>120</cantidad_declarada><lote_proveedor>LP-7781</lote_proveedor><fecha_caducidad>2026-11-12</fecha_caducidad><rango_temperatura_controlada>2C a 6C</rango_temperatura_controlada></item_carga><item_carga><id_sku>2</id_sku><cantidad_declarada>40</cantidad_declarada><fecha_caducidad>2026-11-12</fecha_caducidad></item_carga></detalle_carga></asn_request>
```

**Respuesta (application/json):**

```json
{
  "id_mongo": "6adbffe929f19c19f45e66ea",
  "folio_asn": "ASN-EV-8600DC",
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
X-Correlation-Id: d5910c6cb3694baf
```

**Cuerpo de la petición:**

```xml
<asn_request><folio_asn>ASN-EV-8600DC</folio_asn><id_proveedor>1</id_proveedor><detalle_carga><item_carga><id_sku>1</id_sku><cantidad_declarada>120</cantidad_declarada><lote_proveedor>LP-7781</lote_proveedor><fecha_caducidad>2026-11-12</fecha_caducidad><rango_temperatura_controlada>2C a 6C</rango_temperatura_controlada></item_carga><item_carga><id_sku>2</id_sku><cantidad_declarada>40</cantidad_declarada><fecha_caducidad>2026-11-12</fecha_caducidad></item_carga></detalle_carga></asn_request>
```

**Respuesta (application/json):**

```json
{
  "error": "duplicado",
  "mensaje": "El folio ASN-EV-8600DC ya fue registrado.",
  "status": 409,
  "correlation_id": "d5910c6cb3694baf"
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
X-Correlation-Id: 5ba238f4d214442e
```

**Cuerpo de la petición:**

```json
{
  "folio_asn": "ASN-X-a8e2",
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
  "correlation_id": "5ba238f4d214442e",
  "detalles": {
    "skus_inexistentes": [
      99999999
    ]
  }
}
```

<a id="caso-55"></a>
## 55. svc-asn — GET /api/v1/asn/ASN-EV-8600DC

- **Objetivo:** Recuperación por folio
- **URL:** `GET http://127.0.0.1:5005/api/v1/asn/ASN-EV-8600DC`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 1d9d5e39dbbc4fb7
```

**Respuesta (application/json):**

```json
{
  "_id": "6adbffe929f19c19f45e66ea",
  "folio_asn": "ASN-EV-8600DC",
  "id_proveedor": 1,
  "fecha_embarque": "2026-10-24T00:46:33.158000",
  "fecha_arribo_estimada": "2026-10-26T00:46:33.158000",
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
## 56. svc-asn — PATCH /api/v1/asn/ASN-EV-8600DC/status

- **Objetivo:** Transición de estado inválida
- **URL:** `PATCH http://127.0.0.1:5005/api/v1/asn/ASN-EV-8600DC/status`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: ed3888ffad924621
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
  "correlation_id": "ed3888ffad924621",
  "detalles": {
    "permitidas": [
      "CANCELADO",
      "EN_TRANSITO"
    ]
  }
}
```

<a id="caso-57"></a>
## 57. svc-asn — PATCH /api/v1/asn/ASN-EV-8600DC/status

- **Objetivo:** Actualización de documento ($set)
- **URL:** `PATCH http://127.0.0.1:5005/api/v1/asn/ASN-EV-8600DC/status`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: f18df1c667b64c90
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
  "folio_asn": "ASN-EV-8600DC",
  "estado_anterior": "ANUNCIADO",
  "estado": "EN_TRANSITO"
}
```

<a id="caso-58"></a>
## 58. svc-asn — POST /api/v1/asn/ASN-EV-8600DC/inspection

- **Objetivo:** Inspección agregada con $push
- **URL:** `POST http://127.0.0.1:5005/api/v1/asn/ASN-EV-8600DC/inspection`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 489eda2af839416f
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
  "folio_asn": "ASN-EV-8600DC",
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
X-Correlation-Id: ba80b5a6897c46a7
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 5,
    "total": 1,
    "total_paginas": 1
  },
  "avisos_asn": [
    {
      "_id": "6adbffe929f19c19f45e66ea",
      "folio_asn": "ASN-EV-8600DC",
      "id_proveedor": 1,
      "fecha_embarque": "2026-10-24T00:46:33.158000",
      "fecha_arribo_estimada": "2026-10-26T00:46:33.158000",
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
          "id_inspeccion": "6adbffe929f19c19f45e66eb",
          "fecha": "2026-10-24T00:46:33.194000",
          "inspector": "almacen@freshtrack.mx",
          "resultado": "CONFORME",
          "temperatura_registrada": 4.2,
          "observaciones": "Sellos íntegros"
        }
      ],
      "version_esquema": 1,
      "actualizado_en": "2026-10-24T00:46:33.188000",
      "ultima_inspeccion": "2026-10-24T00:46:33.194000"
    }
  ]
}
```

<a id="caso-60"></a>
## 60. svc-asn — GET /api/v1/asn/analytics/summary

- **Objetivo:** Pipeline de agregación ($unwind/$group/$sort)
- **URL:** `GET http://127.0.0.1:5005/api/v1/asn/analytics/summary`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 459247b5a1a94414
```

**Respuesta (application/json):**

```json
{
  "total_grupos": 2,
  "carga_consolidada": [
    {
      "despachos_asociados": 2,
      "id_proveedor": 1,
      "id_sku": 1,
      "piezas_totales": 240.5
    },
    {
      "despachos_asociados": 2,
      "id_proveedor": 1,
      "id_sku": 2,
      "piezas_totales": 125.0
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
X-Correlation-Id: e53f3ecc968041fd
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "ASN NO-EXISTE no encontrado.",
  "status": 404,
  "correlation_id": "e53f3ecc968041fd"
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
X-Correlation-Id: e8885b1f301f480a
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
  "id_run": "9f5e5ac1-185b-4fdd-881c-0463449852fe",
  "metodo": "SUAVIZACION_EXPONENCIAL",
  "metodo_etiqueta": "Suavización exponencial",
  "horizonte": 7,
  "series": 0,
  "mae": null,
  "rmse": null,
  "wmape": null,
  "resultados": [],
  "duracion_ms": 3
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
X-Correlation-Id: 2c3e891a3c7d4458
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
  "correlation_id": "2c3e891a3c7d4458"
}
```

<a id="caso-64"></a>
## 64. svc-planning — GET /api/v1/planning/forecast/latest/1/3

- **Objetivo:** Última serie pronosticada (MongoDB)
- **URL:** `GET http://127.0.0.1:5006/api/v1/planning/forecast/latest/1/3`
- **Código HTTP:** `404` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 2c04a36126b84d18
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Sin corrida previa para este SKU y tienda.",
  "status": 404,
  "correlation_id": "2c04a36126b84d18"
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
X-Correlation-Id: b246a16895284a24
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
  "ordenes": []
}
```

<a id="caso-66"></a>
## 66. svc-planning — POST /api/v1/planning/replenishment/orders/6edb7681-3eca-4598-8e37-9c774836c962/approve

- **Objetivo:** Aprobar orden inexistente
- **URL:** `POST http://127.0.0.1:5006/api/v1/planning/replenishment/orders/6edb7681-3eca-4598-8e37-9c774836c962/approve`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 0ad62561f41049f7
```

**Cuerpo de la petición:**

```json
{}
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Orden 6edb7681-3eca-4598-8e37-9c774836c962 no encontrada.",
  "status": 404,
  "correlation_id": "0ad62561f41049f7"
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
X-Correlation-Id: 75a98e815d6c4821
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
    "pronostico_reciente": null,
    "alertas_activas_count": 0,
    "alertas_activas": [],
    "consultado_en": "2026-10-24T00:46:33.261858+00:00"
  }
}
```

<a id="caso-68"></a>
## 68. svc-planning — GET /api/v1/planning/forecast/analytics/kpis

- **Objetivo:** Métricas por modelo (agregación)
- **URL:** `GET http://127.0.0.1:5006/api/v1/planning/forecast/analytics/kpis`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 51bf5ce8a4734482
```

**Respuesta (application/json):**

```json
{
  "total_modelos": 0,
  "kpis_modelos": []
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
X-Correlation-Id: bb475179503e48cc
```

**Respuesta (application/json):**

```json
{
  "status": "COMPLETADO",
  "ventana_dias": 5,
  "total_escaneados": 0,
  "alertas_emitidas": 0,
  "detalle": []
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
X-Correlation-Id: de27d8cd7abb42a7
```

**Respuesta (application/json):**

```json
{
  "total": 0,
  "alertas": []
}
```

<a id="caso-71"></a>
## 71. svc-alerts — PATCH /api/v1/alerts/zzz/resolve

- **Objetivo:** ObjectId inválido
- **URL:** `PATCH http://127.0.0.1:5007/api/v1/alerts/zzz/resolve`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: d42d479b7db34538
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_mongo' debe ser un ObjectId de 24 caracteres hexadecimales.",
  "status": 400,
  "correlation_id": "d42d479b7db34538"
}
```

<a id="caso-72"></a>
## 72. svc-alerts — GET /api/v1/alerts/esg/carbon-avoided

- **Objetivo:** Reporte ESG en XML
- **URL:** `GET http://127.0.0.1:5007/api/v1/alerts/esg/carbon-avoided`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Accept: application/xml
X-Correlation-Id: de01b86720d8459e
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<reporte_esg_sostenibilidad><alimento_recuperado_kg>0.0</alimento_recuperado_kg><ahorro_financiero_mxn>0.0</ahorro_financiero_mxn><co2e_evitado_kg>0.0</co2e_evitado_kg><co2e_evitado_toneladas>0.0</co2e_evitado_toneladas><factor_conversion>2.5 kg CO2e / kg perecedero</factor_conversion><fuente>postgres</fuente></reporte_esg_sostenibilidad>
```

<a id="caso-73"></a>
## 73. svc-alerts — GET /api/v1/alerts/analytics/kpis

- **Objetivo:** Alertas por locación y criticidad (agregación)
- **URL:** `GET http://127.0.0.1:5007/api/v1/alerts/analytics/kpis`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: e977a36d2c9141d0
```

**Respuesta (application/json):**

```json
{
  "total_grupos": 2,
  "kpis_alertas": [
    {
      "total_alertas": 1,
      "id_locacion": 1,
      "criticidad": "WARNING",
      "promedio_dias_restantes": 5.0
    },
    {
      "total_alertas": 1,
      "id_locacion": 2,
      "criticidad": "INFO",
      "promedio_dias_restantes": 6.0
    }
  ]
}
```

<a id="caso-74"></a>
## 74. svc-audit — POST /api/v1/audit/log

- **Objetivo:** Registro explícito de cumplimiento (identidad tomada del JWT)
- **URL:** `POST http://127.0.0.1:5008/api/v1/audit/log`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
X-Correlation-Id: acacbad5ca81434c
```

**Cuerpo de la petición:**

```xml
<audit_log_request><accion>REVISION_CUMPLIMIENTO</accion><descripcion>Revisión de mermas de octubre</descripcion></audit_log_request>
```

**Respuesta (application/json):**

```json
{
  "id_evento": "b162edde-2f5b-4240-abe5-6bfabd37af7f",
  "status": "REGISTRADO"
}
```

<a id="caso-75"></a>
## 75. svc-audit — GET /api/v1/audit/events

- **Objetivo:** Bitácora filtrada y paginada
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/events?accion=REVISION_CUMPLIMIENTO&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 26d2f59b11fb479a
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 1,
    "total_paginas": 1
  },
  "bitacora": [
    {
      "id_evento": "b162edde-2f5b-4240-abe5-6bfabd37af7f",
      "fecha_evento": "2026-10-24T00:46:33.529525+00:00",
      "accion": "REVISION_CUMPLIMIENTO",
      "nombre_tabla": "sistema",
      "id_registro": null,
      "descripcion": "Revisión de mermas de octubre",
      "usuario_email": "auditor@freshtrack.mx",
      "ip": "172.20.0.1/32"
    }
  ]
}
```

<a id="caso-76"></a>
## 76. svc-audit — GET /api/v1/audit/events

- **Objetivo:** Fecha inválida
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/events?desde=2026-13-01`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 7a3b3878c89c46f1
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'desde' debe tener formato YYYY-MM-DD.",
  "status": 400,
  "correlation_id": "7a3b3878c89c46f1"
}
```

<a id="caso-77"></a>
## 77. svc-audit — GET /api/v1/audit/events

- **Objetivo:** Gerente sin permiso sobre la bitácora
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/events`
- **Código HTTP:** `403` (esperado `403`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 5cde0a1f942a4d85
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'store_manager' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "5cde0a1f942a4d85",
  "detalles": {
    "roles_permitidos": [
      "admin",
      "auditor"
    ]
  }
}
```

<a id="caso-78"></a>
## 78. svc-audit — GET /api/v1/audit/traceability/no-es-uuid

- **Objetivo:** Identificador de lote inválido
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/traceability/no-es-uuid`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 3c6ecb556edf47ad
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_lote' debe ser un UUID válido.",
  "status": 400,
  "correlation_id": "3c6ecb556edf47ad"
}
```

<a id="caso-79"></a>
## 79. svc-audit — GET /api/v1/audit/stream/recent

- **Objetivo:** Eventos de dominio en Redis Streams
- **URL:** `GET http://127.0.0.1:5008/api/v1/audit/stream/recent?n=5`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 0f5b9d36318e42c8
```

**Respuesta (application/json):**

```json
{
  "total": 5,
  "stream_eventos": [
    {
      "event_id": "054ad5a9043d4412a57e4587c172e6ec",
      "event_type": "PRONOSTICO_CALCULADO",
      "timestamp": "2026-10-24T00:46:33.231455+00:00",
      "correlation_id": "9f5e5ac1-185b-4fdd-881c-0463449852fe",
      "user_id": "8367ce14-39d4-4f30-bbdf-7778386d17b3",
      "user_role": "planner",
      "location_id": "",
      "payload": {
        "id_run": "9f5e5ac1-185b-4fdd-881c-0463449852fe",
        "metodo": "SUAVIZACION_EXPONENCIAL",
        "horizonte": 7,
        "series_count": 0,
        "mae": null,
        "rmse": null,
        "wmape": null
      },
      "id": "1792802793231-0"
    },
    {
      "event_id": "e8f60835c2e64ac786ca88f06ed0ebe1",
      "event_type": "ASN_INSPECCION_REGISTRADA",
      "timestamp": "2026-10-24T00:46:33.194924+00:00",
      "correlation_id": "489eda2af839416f",
      "user_id": "a43bf0c6-2208-453e-ab74-640b452db324",
      "user_role": "warehouse",
      "location_id": "",
      "payload": {
        "folio_asn": "ASN-EV-8600DC",
        "resultado": "CONFORME",
        "temperatura": 4.2
      },
      "id": "1792802793195-0"
    },
    {
      "event_id": "ce221c1ffff0484fb101297407bf99e1",
      "event_type": "ASN_ESTADO_ACTUALIZADO",
      "timestamp": "2026-10-24T00:46:33.189207+00:00",
      "correlation_id": "f18df1c667b64c90",
      "user_id": "a43bf0c6-2208-453e-ab74-640b452db324",
      "user_role": "warehouse",
      "location_id": "",
      "payload": {
        "folio_asn": "ASN-EV-8600DC",
        "de": "ANUNCIADO",
        "a": "EN_TRANSITO"
      },
      "id": "1792802793189-0"
    },
    {
      "event_id": "8622ba651b3b4314ae87474cef844f05",
      "event_type": "ASN_INGRESADO",
      "timestamp": "2026-10-24T00:46:33.161847+00:00",
      "correlation_id": "f06e3f1023204c35",
      "user_id": "a43bf0c6-2208-453e-ab74-640b452db324",
      "user_role": "warehouse",
      "location_id": "",
      "payload": {
        "folio_asn": "ASN-EV-8600DC",
        "id_proveedor": 1,
        "items_count": 2
      },
      "id": "1792802793162-0"
    },
    {
      "event_id": "8745a9bd6a4147229cdb8d5989104613",
      "event_type": "SAGA_VENTA_COMPENSADA",
      "timestamp": "2026-10-24T00:46:32.884753+00:00",
      "correlation_id": "48510374dbe44bd89cb5e5dca7aa6989",
      "user_id": "2c4356a6-89e4-4eef-9fe5-dd903a931fc2",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "saga_id": "48510374dbe44bd89cb5e5dca7aa6989",
    
… (respuesta recortada)
```

<a id="caso-80"></a>
## 80. svc-auth — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5001/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Accept: application/xml
X-Correlation-Id: 243903b527d24028
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<service_health><service>svc-auth</service><status>HEALTHY</status><version>1.0.0</version><dependencies><postgres>true</postgres><redis>true</redis></dependencies></service_health>
```

<a id="caso-81"></a>
## 81. svc-catalog — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5002/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: b435628c68914313
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

<a id="caso-82"></a>
## 82. svc-inventory — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5003/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 65ac648fcba247ef
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

<a id="caso-83"></a>
## 83. svc-commercial — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5004/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: dc339bf4605a40be
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

<a id="caso-84"></a>
## 84. svc-asn — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5005/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 7e1fe4db383a4da6
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

<a id="caso-85"></a>
## 85. svc-planning — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5006/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: 719b6e0f476d4b26
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

<a id="caso-86"></a>
## 86. svc-alerts — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5007/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: b3c3bde203fc4b58
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

<a id="caso-87"></a>
## 87. svc-audit — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5008/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: e5e73adbaef549eb
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
