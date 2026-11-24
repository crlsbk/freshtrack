# Evidencias de petición y respuesta — Microservicios FreshTrack

Generado el 2026-11-24 13:20 con `python scripts/generar_evidencias.py --host 127.0.0.1` mediante peticiones HTTP reales contra los contenedores. Los tokens se muestran abreviados.

**83 de 88 casos** respondieron con el código esperado.

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
| [12](#caso-12) | svc-auth | GET | `/api/v1/auth/sessions/40246cbb-b07e-48fe-8328-0d9c91715947` | Usuario inexistente | 404 | ✅ 404 |
| [13](#caso-13) | svc-auth | GET | `/api/v1/auth/sessions/f5ff3293-cf53-437c-b40e-1abec8cbf3ca` | Sesiones activas en Redis con TTL restante | 200 | ✅ 200 |
| [14](#caso-14) | svc-auth | DELETE | `/api/v1/auth/sessions/f5ff3293-cf53-437c-b40e-1abec8cbf3ca` | Cierre forzado de todas las sesiones de un usuario | 200 | ✅ 200 |
| [15](#caso-15) | svc-planning | GET | `/api/v1/planning/replenishment/orders` | El token del usuario cuyas sesiones se cerraron ya no sirve en otro servicio | 401 | ✅ 401 |
| [16](#caso-16) | svc-auth | GET | `/api/v1/auth/counters?servicio=auth` | Contadores de operación en Redis | 200 | ✅ 200 |
| [17](#caso-17) | svc-auth | POST | `/api/v1/auth/logout` | Logout: revoca en PostgreSQL y agrega jti a la denylist de Redis | 200 | ✅ 200 |
| [18](#caso-18) | svc-inventory | GET | `/api/v1/inventory/stock` | Token revocado usado en OTRO microservicio | 401 | ✅ 401 |
| [19](#caso-19) | svc-inventory | GET | `/api/v1/inventory/stock` | Token con firma alterada | 401 | ✅ 401 |
| [20](#caso-20) | svc-catalog | GET | `/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3` | Productos filtrados y paginados (Cache-Aside: 1.ª vez PostgreSQL) | 200 | ✅ 200 |
| [21](#caso-21) | svc-catalog | GET | `/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3` | Misma consulta servida desde caché Redis (campo fuente y TTL) | 200 | ✅ 200 |
| [22](#caso-22) | svc-catalog | GET | `/api/v1/catalog/products?por_pagina=2` | Respuesta en XML | 200 | ✅ 200 |
| [23](#caso-23) | svc-catalog | GET | `/api/v1/catalog/products?pagina=0` | Parámetro de paginación inválido | 400 | ✅ 400 |
| [24](#caso-24) | svc-catalog | POST | `/api/v1/catalog/products` | Alta de producto con XML validado contra producto_request.xsd | 201 | ⚠️ 403 |
| [25](#caso-25) | svc-catalog | GET | `/api/v1/catalog/products/1` | Detalle por SKU | 200 | ✅ 200 |
| [26](#caso-26) | svc-catalog | PATCH | `/api/v1/catalog/products/1` | Actualización parcial (PATCH) | 200 | ⚠️ 403 |
| [27](#caso-27) | svc-catalog | PUT | `/api/v1/catalog/products/1` | Reemplazo completo (PUT) | 200 | ⚠️ 403 |
| [28](#caso-28) | svc-catalog | PATCH | `/api/v1/catalog/products/1` | Regla de negocio: precio de venta menor al costo | 409 | ⚠️ 403 |
| [29](#caso-29) | svc-catalog | POST | `/api/v1/catalog/products` | Campos obligatorios faltantes | 400 | ⚠️ 403 |
| [30](#caso-30) | svc-catalog | DELETE | `/api/v1/catalog/products/1` | Baja reservada a admin | 403 | ✅ 403 |
| [31](#caso-31) | svc-catalog | DELETE | `/api/v1/catalog/products/1` | Baja lógica (activo=false) | 200 | ✅ 200 |
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
| [45](#caso-45) | svc-commercial | PUT | `/api/v1/commercial/cart/caja1-8d65` | Carrito temporal en Redis (TTL 15 min) | 200 | ✅ 200 |
| [46](#caso-46) | svc-commercial | GET | `/api/v1/commercial/cart/caja1-8d65` | Consulta del carrito con TTL restante | 200 | ✅ 200 |
| [47](#caso-47) | svc-commercial | DELETE | `/api/v1/commercial/cart/caja1-8d65` | Consumo atómico (GET+DEL en Lua) | 200 | ✅ 200 |
| [48](#caso-48) | svc-commercial | GET | `/api/v1/commercial/cart/caja1-8d65` | Carrito ya consumido | 404 | ✅ 404 |
| [49](#caso-49) | svc-commercial | POST | `/api/v1/commercial/shrinkage` | Merma sobre un lote que no existe | 409 | ✅ 409 |
| [50](#caso-50) | svc-commercial | POST | `/api/v1/commercial/shrinkage` | Causa de merma inválida | 400 | ✅ 400 |
| [51](#caso-51) | svc-commercial | GET | `/api/v1/commercial/sales?id_locacion=3&desde=2026-10-25&por_pagina=3` | Historial de ventas por rango de fechas | 200 | ✅ 200 |
| [52](#caso-52) | svc-asn | POST | `/api/v1/asn` | Ingesta de ASN en XML (validado con asn_request.xsd) → documento en MongoDB | 201 | ✅ 201 |
| [53](#caso-53) | svc-asn | POST | `/api/v1/asn` | Folio duplicado (índice único en MongoDB) | 409 | ✅ 409 |
| [54](#caso-54) | svc-asn | POST | `/api/v1/asn` | SKU inexistente en PostgreSQL (integración PG↔Mongo) | 409 | ✅ 409 |
| [55](#caso-55) | svc-asn | GET | `/api/v1/asn/ASN-EV-5C6287` | Recuperación por folio | 200 | ✅ 200 |
| [56](#caso-56) | svc-asn | PATCH | `/api/v1/asn/ASN-EV-5C6287/status` | Transición de estado inválida | 409 | ✅ 409 |
| [57](#caso-57) | svc-asn | PATCH | `/api/v1/asn/ASN-EV-5C6287/status` | Actualización de documento ($set) | 200 | ✅ 200 |
| [58](#caso-58) | svc-asn | POST | `/api/v1/asn/ASN-EV-5C6287/inspection` | Inspección agregada con $push | 201 | ✅ 201 |
| [59](#caso-59) | svc-asn | GET | `/api/v1/asn?id_sku=2&estado=EN_TRANSITO&por_pagina=5` | Filtrado por campo anidado y estado | 200 | ✅ 200 |
| [60](#caso-60) | svc-asn | GET | `/api/v1/asn/analytics/summary` | Pipeline de agregación ($unwind/$group/$sort) | 200 | ✅ 200 |
| [61](#caso-61) | svc-asn | GET | `/api/v1/asn/NO-EXISTE` | Folio inexistente | 404 | ✅ 404 |
| [62](#caso-62) | svc-planning | POST | `/api/v1/planning/forecast/run` | Corrida de pronóstico (linaje en PostgreSQL, serie en MongoDB) | 201 | ✅ 201 |
| [63](#caso-63) | svc-planning | POST | `/api/v1/planning/forecast/run` | Método no soportado | 400 | ✅ 400 |
| [64](#caso-64) | svc-planning | GET | `/api/v1/planning/forecast/latest/1/3` | Última serie pronosticada (MongoDB) | 200 | ✅ 200 |
| [65](#caso-65) | svc-planning | GET | `/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=3` | Órdenes pendientes paginadas | 200 | ✅ 200 |
| [66](#caso-66) | svc-planning | POST | `/api/v1/planning/replenishment/orders/9a5bdfc6-93c1-419d-87c9-ff8f799da87a/approve` | Aprobar orden inexistente | 404 | ✅ 404 |
| [67](#caso-67) | svc-planning | GET | `/api/v1/planning/sku/1/full-context?id_locacion=3` | Contexto híbrido PostgreSQL + MongoDB | 200 | ✅ 200 |
| [68](#caso-68) | svc-planning | GET | `/api/v1/planning/forecast/analytics/kpis` | Métricas por modelo (agregación) | 200 | ✅ 200 |
| [69](#caso-69) | svc-alerts | POST | `/api/v1/alerts/scan?id_locacion=3&dias=5` | Escaneo con lock distribuido → alertas en MongoDB + eventos en Redis Streams | 200 | ✅ 200 |
| [70](#caso-70) | svc-alerts | GET | `/api/v1/alerts/active?id_locacion=3&limite=3` | Alertas abiertas filtradas | 200 | ✅ 200 |
| [71](#caso-71) | svc-alerts | PATCH | `/api/v1/alerts/6b05e36807c1e75aee0f321d/resolve` | Atender alerta (inicia retención TTL) | 200 | ✅ 200 |
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
X-Correlation-Id: d443284adc8d44d1
```

**Cuerpo de la petición:**

```json
{
  "email": "gerente@freshtrack.mx",
  "password": "***"
}
```

**Respuesta (application/json):**

```json
{
  "token": "<JWT-OCULTO>",
  "jti": "12990a1d35634004981ab3c9e9355cc0",
  "token_type": "Bearer",
  "expira_en_segundos": 900,
  "refresh_token": "Pp-w2jSqEy2_4tk6GXNtCPzwxm9_djlYp_w12_-GLkY",
  "refresh_expira_en_segundos": 28800,
  "usuario": {
    "id_usuario": "40e4de83-351f-46c9-b6bd-cbabe206b924",
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
X-Correlation-Id: 94fb6cc377564b0f
```

**Cuerpo de la petición:**

```xml
<login_request><email>auditor@freshtrack.mx</email><password>***</password></login_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<auth_response><token><JWT-OCULTO></token><jti>efb5bb6e56624fab9c243c460784781b</jti><token_type>Bearer</token_type><expira_en_segundos>900</expira_en_segundos><refresh_token>RFiWRcg01nedY_EyZL86iGg-FIksntM4JYgrMT_mHAY</refresh_token><refresh_expira_en_segundos>28800</refresh_expira_en_segundos><usuario><id_usuario>75021000-18bb-4ce7-a939-50b22ec6f217</id_usuario><email>auditor@freshtrack.mx</email><nombre>Irma Salinas</nombre><rol>auditor</rol><id_locacion>1</id_locacion></usuario></auth_response>
```

<a id="caso-3"></a>
## 3. svc-auth — POST /api/v1/auth/login

- **Objetivo:** Credenciales incorrectas (no revela si el correo existe)
- **URL:** `POST http://127.0.0.1:5001/api/v1/auth/login`
- **Código HTTP:** `401` (esperado `401`)
- **Headers:**

```http
Content-Type: application/json
X-Correlation-Id: c391f2097d0a48ee
```

**Cuerpo de la petición:**

```json
{
  "email": "admin@freshtrack.mx",
  "password": "***"
}
```

**Respuesta (application/json):**

```json
{
  "error": "credenciales_invalidas",
  "mensaje": "Correo o contraseña incorrectos.",
  "status": 401,
  "correlation_id": "c391f2097d0a48ee"
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
X-Correlation-Id: 97e549fec0b44efd
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
  "correlation_id": "97e549fec0b44efd",
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
X-Correlation-Id: 5bc9e060782543f4
```

**Cuerpo de la petición:**

```json
{
  "email": "inactivo@freshtrack.mx",
  "password": "***"
}
```

**Respuesta (application/json):**

```json
{
  "error": "credenciales_invalidas",
  "mensaje": "Esta cuenta está desactivada. Contacta al administrador.",
  "status": 401,
  "correlation_id": "5bc9e060782543f4"
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
X-Correlation-Id: ccf858cf20c149a1
```

**Respuesta (application/json):**

```json
{
  "valido": true,
  "usuario": {
    "id_usuario": "3aeab741-0f35-4939-b635-2a2b79ea1b17",
    "email": "almacen@freshtrack.mx",
    "nombre": "Pedro Vargas",
    "rol": "warehouse",
    "id_locacion": 3
  },
  "sesion_ttl_segundos": 900
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
X-Correlation-Id: 11f94f10e38d4a8d
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "02af410a-a4ac-4cd2-a660-83f009e3cebc",
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
X-Correlation-Id: 03c13feeba154519
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
      "id_usuario": "0451be7d-f82b-417b-9607-5f208685d36f",
      "email": "gerente2@freshtrack.mx",
      "nombre_completo": "Ana Ruiz",
      "rol": "store_manager",
      "id_locacion": 4,
      "estado_activo": true,
      "fecha_alta": "2026-11-23T05:43:47.486861+00:00"
    },
    {
      "id_usuario": "40e4de83-351f-46c9-b6bd-cbabe206b924",
      "email": "gerente@freshtrack.mx",
      "nombre_completo": "Luis Pérez",
      "rol": "store_manager",
      "id_locacion": 3,
      "estado_activo": true,
      "fecha_alta": "2026-11-23T05:43:47.486861+00:00"
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
X-Correlation-Id: 00eded560eb44ebe
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'auditor' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "00eded560eb44ebe",
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
X-Correlation-Id: ba6241f4e78946f6
```

**Respuesta (application/json):**

```json
{
  "error": "token_requerido",
  "mensaje": "Token de autenticación requerido (Authorization: Bearer <token>).",
  "status": 401,
  "correlation_id": "ba6241f4e78946f6"
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
X-Correlation-Id: 6e06b93a5e8d4c43
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_usuario' debe ser un UUID válido.",
  "status": 400,
  "correlation_id": "6e06b93a5e8d4c43"
}
```

<a id="caso-12"></a>
## 12. svc-auth — GET /api/v1/auth/sessions/40246cbb-b07e-48fe-8328-0d9c91715947

- **Objetivo:** Usuario inexistente
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/sessions/40246cbb-b07e-48fe-8328-0d9c91715947`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 546325beacb94fdc
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Usuario 40246cbb-b07e-48fe-8328-0d9c91715947 no encontrado.",
  "status": 404,
  "correlation_id": "546325beacb94fdc"
}
```

<a id="caso-13"></a>
## 13. svc-auth — GET /api/v1/auth/sessions/f5ff3293-cf53-437c-b40e-1abec8cbf3ca

- **Objetivo:** Sesiones activas en Redis con TTL restante
- **URL:** `GET http://127.0.0.1:5001/api/v1/auth/sessions/f5ff3293-cf53-437c-b40e-1abec8cbf3ca`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: d573dda387c94681
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "f5ff3293-cf53-437c-b40e-1abec8cbf3ca",
  "total_activas": 4,
  "sesiones": [
    {
      "id_usuario": "f5ff3293-cf53-437c-b40e-1abec8cbf3ca",
      "email": "planner@freshtrack.mx",
      "nombre": "Carlos Vega",
      "rol": "planner",
      "id_locacion": 1,
      "jti": "dc67bd6986b74cc882f151d245f84fbe",
      "familia": "f5b7ef84-0ffa-4095-a92f-b0f1ccbfc8dd",
      "ip": "192.168.65.1",
      "user_agent": "python-requests/2.34.2",
      "login_en": "2026-11-24T19:18:54.696813+00:00",
      "ttl_restante_segundos": 827
    },
    {
      "id_usuario": "f5ff3293-cf53-437c-b40e-1abec8cbf3ca",
      "email": "planner@freshtrack.mx",
      "nombre": "Carlos Vega",
      "rol": "planner",
      "id_locacion": 1,
      "jti": "15ca08b862ba4774a290618389a81eba",
      "familia": "ebcc0236-a154-48a9-9bc5-38162f360f49",
      "ip": "172.19.0.15",
      "user_agent": "freshtrack-web",
      "login_en": "2026-11-24T19:19:58.271503+00:00",
      "ttl_restante_segundos": 891
    },
    {
      "id_usuario": "f5ff3293-cf53-437c-b40e-1abec8cbf3ca",
      "email": "planner@freshtrack.mx",
      "nombre": "Carlos Vega",
      "rol": "planner",
      "id_locacion": 1,
      "jti": "f726e7d9d14b41b89e5257b4c24e0bf2",
      "familia": "2f34a89e-2765-4ce4-84eb-9691f1e1c8ce",
      "ip": "192.168.65.1",
      "user_agent": "Python-urllib/3.14",
      "login_en": "2026-11-24T19:20:07.448570+00:00",
      "ttl_restante_segundos": 900
    },
    {
      "id_usuario": "f5ff3293-cf53-437c-b40e-1abec8cbf3ca",
      "email": "planner@freshtrack.mx",
      "nombre": "Carlos Vega",
      "rol": "planner",
      "id_locacion": 1,
      "jti": "6ebfa7daa6c24f359b4597276eb7124e",
      "familia": "99e6393e-0ddc-4ae7-8887-01604a5ad203",
      "ip": "192.168.65.1",
      "user_agent": "Python-urllib/3.14",
      "login_en": "2026-11-24T19:20:07.184252+00:00",
      "ttl_restante_segundos": 900
    }
  ]
}
```

<a id="caso-14"></a>
## 14. svc-auth — DELETE /api/v1/auth/sessions/f5ff3293-cf53-437c-b40e-1abec8cbf3ca

- **Objetivo:** Cierre forzado de todas las sesiones de un usuario
- **URL:** `DELETE http://127.0.0.1:5001/api/v1/auth/sessions/f5ff3293-cf53-437c-b40e-1abec8cbf3ca`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 4bd223a21db64853
```

**Respuesta (application/json):**

```json
{
  "id_usuario": "f5ff3293-cf53-437c-b40e-1abec8cbf3ca",
  "sesiones_cerradas": 4,
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
X-Correlation-Id: 45dcfedba98c4529
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "45dcfedba98c4529"
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
X-Correlation-Id: cb7e9c75d49d4136
```

**Respuesta (application/json):**

```json
{
  "total_metricas": 7,
  "contadores": {
    "counter:ops:auth:access_granted:20261124": 312,
    "counter:ops:auth:access_denied_invalid:20261124": 6,
    "counter:ops:auth:login_failed:20261124": 65,
    "counter:ops:auth:access_denied_revoked:20261124": 22,
    "counter:ops:auth:access_denied_role:20261124": 17,
    "counter:ops:auth:access_denied_no_token:20261124": 6,
    "counter:ops:auth:login_success:20261124": 102
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
X-Correlation-Id: d1acc15b184d44e5
```

**Respuesta (application/json):**

```json
{
  "status": "LOGOUT_EXITOSO",
  "jti": "2b45b20e0be4470bb151986254da5387"
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
X-Correlation-Id: b0f9379e1ffd470c
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "b0f9379e1ffd470c"
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
X-Correlation-Id: f47a6a98df024a51
```

**Respuesta (application/json):**

```json
{
  "error": "token_revocado",
  "mensaje": "La sesión fue cerrada; el token ya no es válido.",
  "status": 401,
  "correlation_id": "f47a6a98df024a51"
}
```

<a id="caso-20"></a>
## 20. svc-catalog — GET /api/v1/catalog/products

- **Objetivo:** Productos filtrados y paginados (Cache-Aside: 1.ª vez PostgreSQL)
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products?categoria=Lacteos&pagina=1&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: b6ea1832cc804335
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
X-Correlation-Id: 1ec833c594b94d4d
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
X-Correlation-Id: d3284ed6706c47e0
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalogo_productos><paginacion><pagina>1</pagina><por_pagina>2</por_pagina><total>14</total><total_paginas>7</total_paginas></paginacion><productos><item><id_sku>12</id_sku><codigo_gtin>07501234560126</codigo_gtin><nombre>Arroz 1kg</nombre><categoria>Abarrotes</categoria><unidad_medida>Paquete</unidad_medida><id_proveedor>6</id_proveedor><stock_seguridad>100.0</stock_seguridad><punto_reorden>180.0</punto_reorden><moq_lote /><perecedero>true</perecedero><vida_util_estandar>365</vida_util_estandar><precio_costo>22.0</precio_costo><precio_venta>33.5</precio_venta><activo>true</activo></item><item><id_sku>9</id_sku><codigo_gtin>07501234560096</codigo_gtin><nombre>Crema Ácida 450g</nombre><categoria>Lácteos</categoria><unidad_medida>Pieza</unidad_medida><id_proveedor>1</id_proveedor><stock_seguridad>35.0</stock_seguridad><punto_reorden>70.0</punto_reorden><moq_lote /><perecedero>true</perecedero><vida_util_estandar>20</vida_util_estandar><precio_costo>26.0</precio_costo><precio_venta>38.0</precio_venta><activo>true</activo></item></productos><fuente>postgres</fuente></catalogo_productos>
```

<a id="caso-23"></a>
## 23. svc-catalog — GET /api/v1/catalog/products

- **Objetivo:** Parámetro de paginación inválido
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products?pagina=0`
- **Código HTTP:** `400` (esperado `400`)
- **Headers:**

```http
X-Correlation-Id: 74bb8ee9a3994499
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'pagina' debe ser mayor o igual a 1.",
  "status": 400,
  "correlation_id": "74bb8ee9a3994499"
}
```

<a id="caso-24"></a>
## 24. svc-catalog — POST /api/v1/catalog/products

- **Objetivo:** Alta de producto con XML validado contra producto_request.xsd
- **URL:** `POST http://127.0.0.1:5002/api/v1/catalog/products`
- **Código HTTP:** `403` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/xml
Accept: application/xml
X-Correlation-Id: e0bb91019e9a4180
```

**Cuerpo de la petición:**

```xml
<producto_request><nombre>Fresa evidencia ee175</nombre><categoria>Frutas</categoria><precio_costo>20</precio_costo><precio_venta>35.5</precio_venta><vida_util_estandar>5</vida_util_estandar></producto_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<error_response><error>acceso_denegado</error><mensaje>El rol 'buyer' no tiene permiso para esta operación.</mensaje><status>403</status><correlation_id>e0bb91019e9a4180</correlation_id><detalles><roles_permitidos><item>admin</item><item>supplier</item></roles_permitidos></detalles></error_response>
```

<a id="caso-25"></a>
## 25. svc-catalog — GET /api/v1/catalog/products/1

- **Objetivo:** Detalle por SKU
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/products/1`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: b7f6d404e32e4ba6
```

**Respuesta (application/json):**

```json
{
  "id_sku": 1,
  "codigo_gtin": "07501234560010",
  "nombre": "Leche Entera 1L",
  "categoria": "Lácteos",
  "unidad_medida": "Litro",
  "id_proveedor": 1,
  "stock_seguridad": 120.0,
  "punto_reorden": 200.0,
  "moq_lote": null,
  "perecedero": true,
  "vida_util_estandar": 15,
  "precio_costo": 18.5,
  "precio_venta": 24.9,
  "activo": true
}
```

<a id="caso-26"></a>
## 26. svc-catalog — PATCH /api/v1/catalog/products/1

- **Objetivo:** Actualización parcial (PATCH)
- **URL:** `PATCH http://127.0.0.1:5002/api/v1/catalog/products/1`
- **Código HTTP:** `403` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 92c6b16610fe4217
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
  "error": "acceso_denegado",
  "mensaje": "El rol 'buyer' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "92c6b16610fe4217",
  "detalles": {
    "roles_permitidos": [
      "admin",
      "supplier"
    ]
  }
}
```

<a id="caso-27"></a>
## 27. svc-catalog — PUT /api/v1/catalog/products/1

- **Objetivo:** Reemplazo completo (PUT)
- **URL:** `PUT http://127.0.0.1:5002/api/v1/catalog/products/1`
- **Código HTTP:** `403` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 8e64316803dd4c49
```

**Cuerpo de la petición:**

```json
{
  "nombre": "Fresa evidencia ee175",
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
  "error": "acceso_denegado",
  "mensaje": "El rol 'buyer' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "8e64316803dd4c49",
  "detalles": {
    "roles_permitidos": [
      "admin",
      "supplier"
    ]
  }
}
```

<a id="caso-28"></a>
## 28. svc-catalog — PATCH /api/v1/catalog/products/1

- **Objetivo:** Regla de negocio: precio de venta menor al costo
- **URL:** `PATCH http://127.0.0.1:5002/api/v1/catalog/products/1`
- **Código HTTP:** `403` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: da2ebc448e844842
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
  "error": "acceso_denegado",
  "mensaje": "El rol 'buyer' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "da2ebc448e844842",
  "detalles": {
    "roles_permitidos": [
      "admin",
      "supplier"
    ]
  }
}
```

<a id="caso-29"></a>
## 29. svc-catalog — POST /api/v1/catalog/products

- **Objetivo:** Campos obligatorios faltantes
- **URL:** `POST http://127.0.0.1:5002/api/v1/catalog/products`
- **Código HTTP:** `403` (esperado `400`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 209d17ddb64743c3
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
  "error": "acceso_denegado",
  "mensaje": "El rol 'buyer' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "209d17ddb64743c3",
  "detalles": {
    "roles_permitidos": [
      "admin",
      "supplier"
    ]
  }
}
```

<a id="caso-30"></a>
## 30. svc-catalog — DELETE /api/v1/catalog/products/1

- **Objetivo:** Baja reservada a admin
- **URL:** `DELETE http://127.0.0.1:5002/api/v1/catalog/products/1`
- **Código HTTP:** `403` (esperado `403`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 1ee62692f3de459f
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'buyer' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "1ee62692f3de459f",
  "detalles": {
    "roles_permitidos": [
      "admin",
      "supplier"
    ]
  }
}
```

<a id="caso-31"></a>
## 31. svc-catalog — DELETE /api/v1/catalog/products/1

- **Objetivo:** Baja lógica (activo=false)
- **URL:** `DELETE http://127.0.0.1:5002/api/v1/catalog/products/1`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 4d84a1e2c35d491e
```

**Respuesta (application/json):**

```json
{
  "id_sku": 1,
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
X-Correlation-Id: d6d83075b95849b0
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "SKU 99999999 no encontrado.",
  "status": 404,
  "correlation_id": "d6d83075b95849b0"
}
```

<a id="caso-33"></a>
## 33. svc-catalog — GET /api/v1/catalog/locations

- **Objetivo:** Tiendas (Cache-Aside)
- **URL:** `GET http://127.0.0.1:5002/api/v1/catalog/locations?tipo=Tienda`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: c5f4b7e3e6e84869
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
X-Correlation-Id: ee28bd9b3d5343de
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 5,
    "total": 14,
    "total_paginas": 3
  },
  "existencias": [
    {
      "id_existencia": "87e4d25b-f05d-430e-8685-19a0ca6e3ae8",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "f8495272-4520-4d25-9505-a50745ecad40",
      "id_sku": 5,
      "producto": "Pechuga de Pollo kg",
      "codigo_lote_prov": "CRN-20261117-001",
      "estado_lote": "VENCIDO",
      "fecha_caducidad": "2026-11-22",
      "dias_restantes": -2,
      "cantidad_disponible": 2.83,
      "cantidad_reservada": 0.0,
      "disponible_neto": 2.83
    },
    {
      "id_existencia": "e66c5924-5d8f-4257-a486-fc0b0b16d03e",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "2e0db727-96c3-48d0-b6d1-30e260fd61aa",
      "id_sku": 5,
      "producto": "Pechuga de Pollo kg",
      "codigo_lote_prov": "CRN-20261118-001",
      "estado_lote": "VENCIDO",
      "fecha_caducidad": "2026-11-23",
      "dias_restantes": -1,
      "cantidad_disponible": 1.0,
      "cantidad_reservada": 0.0,
      "disponible_neto": 1.0
    },
    {
      "id_existencia": "ab3d5dc4-6c94-493b-b7a5-e278febf0944",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "1fa8e517-a010-410e-8eee-7a74ede3ad9d",
      "id_sku": 6,
      "producto": "Pan Integral 600g",
      "codigo_lote_prov": "PAA-20261121-001",
      "estado_lote": "DISPONIBLE",
      "fecha_caducidad": "2026-11-25",
      "dias_restantes": 1,
      "cantidad_disponible": 26.99,
      "cantidad_reservada": 0.0,
      "disponible_neto": 26.99
    },
    {
      "id_existencia": "19392bf0-9aa9-4775-b621-58c007f081cb",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "c525a245-1886-4005-9fc1-a712ca2fc79b",
      "id_sku": 8,
      "producto": "Espinaca 250g",
      "codigo_lote_prov": "VFR-20261121-001",
      "estado_lote": "DISPONIBLE",
      "fecha_caducidad": "2026-11-26",
      "dias_restantes": 2,
      "cantidad_disponible": 9.96,
      "cantidad_reservada": 0.0,
      "disponible_neto": 9.96
    },
    {
      "id_existencia": "9f11787b-f9ba-4053-a130-6e1a5bd79fb2",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "id_lote": "98a38ed2-8bdc-4783-b7ea-57d03033aa74",
      "id_sku": 5,
      "producto": "Pechuga de Pollo kg",
      "codigo_lote_prov": "CRN-20261121-001",
      "estado_lote": "DISPONIBLE",
      "fecha_caducidad": "2026-11-26",
      "dias_restantes"
… (respuesta recortada)
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
X-Correlation-Id: 83ab97c7f85a45f0
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<fefo_queue><id_sku>1</id_sku><id_locacion>3</id_locacion><total_lotes>13</total_lotes><lotes_fefo><item><id_existencia>330ffe5f-9168-4796-a5d2-4fe32fcc1680</id_existencia><id_lote>61562c89-6e72-464a-8601-b54c2cc7d02f</id_lote><codigo_lote_prov>LDN-20261115-001</codigo_lote_prov><estado>DISPONIBLE</estado><cantidad_disponible>2.09</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-11-30</fecha_caducidad><dias_restantes>6</dias_restantes><costo_unitario>18.5</costo_unitario></item><item><id_existencia>76e7215b-65a1-4680-86b9-20ee45cd2403</id_existencia><id_lote>3ace729f-4699-4107-80b8-094cd6f28b99</id_lote><codigo_lote_prov>LDN-20261118-001</codigo_lote_prov><estado>DISPONIBLE</estado><cantidad_disponible>100.41</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-12-03</fecha_caducidad><dias_restantes>9</dias_restantes><costo_unitario>18.5</costo_unitario></item><item><id_existencia>48f80c6c-89da-4525-9b08-62baa3b4e556</id_existencia><id_lote>bb064df8-d031-400a-bd0a-758e31e88629</id_lote><codigo_lote_prov>PYTEST-043cd6fc</codigo_lote_prov><estado>DISPONIBLE</estado><cantidad_disponible>50.0</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-12-04</fecha_caducidad><dias_restantes>10</dias_restantes><costo_unitario>12.5</costo_unitario></item><item><id_existencia>ca8d9bb5-a140-4be9-9b52-18a3b79e9392</id_existencia><id_lote>ace4dce7-fd13-43c6-8948-118a4b88abfe</id_lote><codigo_lote_prov>PYTEST-1c092c6b</codigo_lote_prov><estado>DISPONIBLE</estado><cantidad_disponible>50.0</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-12-04</fecha_caducidad><dias_restantes>10</dias_restantes><costo_unitario>12.5</costo_unitario></item><item><id_existencia>5c8bd7a7-0e1d-4747-af85-2c9c1e628a0e</id_existencia><id_lote>f3a13568-301c-426f-96d2-623678545589</id_lote><codigo_lote_prov>PYTEST-262e4a91</codigo_lote_prov><estado>DISPONIBLE</estado><cantidad_disponible>49.0</cantidad_disponible><cantidad_reservada>0.0</cantidad_reservada><fecha_caducidad>2026-12-04</fecha_caducidad><dias_restantes>10</dias_restantes><costo_unitario>12.5</costo_unitario></item><item><id_existencia>6bf7989b-fc07-41b5-ac47-ef24d105725e</id_existencia><id_lote>e436fe8a-7f1b-4f72-9316-8600ebd7816c</id_lote><codigo_lote_prov>PYTEST-618f84ff</codigo_lote_prov><estado>DISPONIBLE</estado><cantidad_disponible>50.0</cantidad_disponi
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
X-Correlation-Id: de549c532bcd4c7c
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "SKU 99999999 no existe.",
  "status": 404,
  "correlation_id": "de549c532bcd4c7c"
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
X-Correlation-Id: 15a8c80a182f4acd
```

**Cuerpo de la petición:**

```xml
<reserva_request><id_locacion>3</id_locacion><saga_id>evidencia-aded0a10</saga_id><lineas><item><id_sku>1</id_sku><cantidad>1</cantidad></item></lineas></reserva_request>
```

**Respuesta (application/json):**

```json
{
  "status": "RESERVADO",
  "saga_id": "evidencia-aded0a10",
  "id_locacion": 3,
  "reservas": [
    {
      "id_lote": "61562c89-6e72-464a-8601-b54c2cc7d02f",
      "id_sku": 1,
      "cantidad": 1.0,
      "costo_unitario": 18.5,
      "codigo_lote": "LDN-20261115-001"
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
X-Correlation-Id: 14e1c66daca84ced
```

**Cuerpo de la petición:**

```json
{
  "saga_id": "evidencia-aded0a10"
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
X-Correlation-Id: 38a62c3f8d394dfa
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
  "correlation_id": "38a62c3f8d394dfa",
  "detalles": {
    "id_sku": 1,
    "disponible": 697.71,
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
X-Correlation-Id: 6719e8f020b84707
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
  "correlation_id": "6719e8f020b84707"
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
X-Correlation-Id: 168c5287319649e6
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
  "correlation_id": "168c5287319649e6",
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
X-Correlation-Id: 3a368aa89fd54a86
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
  "saga_id": "c5affad6664f438db673e5f8cf0f46ea",
  "id_venta": "998c7574-1de2-456d-829d-e9e596364217",
  "folio": "VT-3-20261124-000024",
  "total": 24.9,
  "lineas": [
    {
      "id_sku": 1,
      "producto": "Leche Entera 1L",
      "codigo_lote": "LDN-20261115-001",
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
X-Correlation-Id: cc024150a23a454c
```

**Cuerpo de la petición:**

```xml
<checkout_request><id_locacion>3</id_locacion><lineas><item><id_sku>1</id_sku><cantidad>99999999</cantidad></item></lineas></checkout_request>
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<error_response><error>venta_rechazada</error><mensaje>Stock insuficiente para 'Leche Entera 1L' (disponible: 696.71, solicitado: 99999999.00).</mensaje><status>409</status><correlation_id>cc024150a23a454c</correlation_id></error_response>
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
X-Correlation-Id: e10dba75ae554d4e
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
  "correlation_id": "e10dba75ae554d4e",
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
## 45. svc-commercial — PUT /api/v1/commercial/cart/caja1-8d65

- **Objetivo:** Carrito temporal en Redis (TTL 15 min)
- **URL:** `PUT http://127.0.0.1:5004/api/v1/commercial/cart/caja1-8d65`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: a7c60bd7eae94c83
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
  "cart_id": "caja1-8d65",
  "status": "GUARDADO",
  "ttl_segundos": 900
}
```

<a id="caso-46"></a>
## 46. svc-commercial — GET /api/v1/commercial/cart/caja1-8d65

- **Objetivo:** Consulta del carrito con TTL restante
- **URL:** `GET http://127.0.0.1:5004/api/v1/commercial/cart/caja1-8d65`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 6fe5cfd64d054662
```

**Respuesta (application/json):**

```json
{
  "cart_id": "caja1-8d65",
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
## 47. svc-commercial — DELETE /api/v1/commercial/cart/caja1-8d65

- **Objetivo:** Consumo atómico (GET+DEL en Lua)
- **URL:** `DELETE http://127.0.0.1:5004/api/v1/commercial/cart/caja1-8d65`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 277784e1bed142b0
```

**Respuesta (application/json):**

```json
{
  "cart_id": "caja1-8d65",
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
## 48. svc-commercial — GET /api/v1/commercial/cart/caja1-8d65

- **Objetivo:** Carrito ya consumido
- **URL:** `GET http://127.0.0.1:5004/api/v1/commercial/cart/caja1-8d65`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: d31ba4ff5e7d43af
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Carrito expirado o inexistente.",
  "status": 404,
  "correlation_id": "d31ba4ff5e7d43af"
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
X-Correlation-Id: 205d1326899c4b32
```

**Cuerpo de la petición:**

```json
{
  "id_lote": "370b2394-38d6-4694-a728-4390d7145664",
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
  "correlation_id": "205d1326899c4b32"
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
X-Correlation-Id: 87ae68c46b904721
```

**Cuerpo de la petición:**

```json
{
  "id_lote": "a45f97f7-d2b0-463a-9968-469b7667903c",
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
  "correlation_id": "87ae68c46b904721"
}
```

<a id="caso-51"></a>
## 51. svc-commercial — GET /api/v1/commercial/sales

- **Objetivo:** Historial de ventas por rango de fechas
- **URL:** `GET http://127.0.0.1:5004/api/v1/commercial/sales?id_locacion=3&desde=2026-10-25&por_pagina=3`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: f184e3a184144fb4
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 367,
    "total_paginas": 123
  },
  "ventas": [
    {
      "id_venta": "998c7574-1de2-456d-829d-e9e596364217",
      "folio": "VT-3-20261124-000024",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "canal": "TIENDA",
      "total": 24.9,
      "fecha_venta": "2026-11-24T19:20:07.794497+00:00"
    },
    {
      "id_venta": "7b88c5f6-4789-4b68-84ba-69a7601b2de3",
      "folio": "VT-3-20261124-000023",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "canal": "TIENDA",
      "total": 38.0,
      "fecha_venta": "2026-11-24T19:19:57.207656+00:00"
    },
    {
      "id_venta": "f8926b9f-bb93-47e7-b5c4-0878b10d7057",
      "folio": "VT-3-20261124-000022",
      "id_locacion": 3,
      "locacion": "Tienda San Pedro",
      "canal": "TIENDA",
      "total": 38.0,
      "fecha_venta": "2026-11-24T19:19:56.932153+00:00"
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
X-Correlation-Id: 2b539b1f9ef94a14
```

**Cuerpo de la petición:**

```xml
<asn_request><folio_asn>ASN-EV-5C6287</folio_asn><id_proveedor>1</id_proveedor><detalle_carga><item_carga><id_sku>1</id_sku><cantidad_declarada>120</cantidad_declarada><lote_proveedor>LP-7781</lote_proveedor><fecha_caducidad>2026-12-14</fecha_caducidad><rango_temperatura_controlada>2C a 6C</rango_temperatura_controlada></item_carga><item_carga><id_sku>2</id_sku><cantidad_declarada>40</cantidad_declarada><fecha_caducidad>2026-12-14</fecha_caducidad></item_carga></detalle_carga></asn_request>
```

**Respuesta (application/json):**

```json
{
  "id_mongo": "6b05e3686f49571e897eaada",
  "folio_asn": "ASN-EV-5C6287",
  "estado": "REGISTRADO",
  "etiquetas": []
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
X-Correlation-Id: 4d5662f54a914ac2
```

**Cuerpo de la petición:**

```xml
<asn_request><folio_asn>ASN-EV-5C6287</folio_asn><id_proveedor>1</id_proveedor><detalle_carga><item_carga><id_sku>1</id_sku><cantidad_declarada>120</cantidad_declarada><lote_proveedor>LP-7781</lote_proveedor><fecha_caducidad>2026-12-14</fecha_caducidad><rango_temperatura_controlada>2C a 6C</rango_temperatura_controlada></item_carga><item_carga><id_sku>2</id_sku><cantidad_declarada>40</cantidad_declarada><fecha_caducidad>2026-12-14</fecha_caducidad></item_carga></detalle_carga></asn_request>
```

**Respuesta (application/json):**

```json
{
  "error": "duplicado",
  "mensaje": "El folio ASN-EV-5C6287 ya fue registrado.",
  "status": 409,
  "correlation_id": "4d5662f54a914ac2"
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
X-Correlation-Id: 24a32014c9bf4b31
```

**Cuerpo de la petición:**

```json
{
  "folio_asn": "ASN-X-2d26",
  "id_proveedor": 1,
  "detalle_carga": [
    {
      "id_sku": 99999999,
      "cantidad_declarada": 1,
      "fecha_caducidad": "2026-12-14"
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
  "correlation_id": "24a32014c9bf4b31",
  "detalles": {
    "skus_inexistentes": [
      99999999
    ]
  }
}
```

<a id="caso-55"></a>
## 55. svc-asn — GET /api/v1/asn/ASN-EV-5C6287

- **Objetivo:** Recuperación por folio
- **URL:** `GET http://127.0.0.1:5005/api/v1/asn/ASN-EV-5C6287`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 74e85e21d3d740cd
```

**Respuesta (application/json):**

```json
{
  "_id": "6b05e3686f49571e897eaada",
  "folio_asn": "ASN-EV-5C6287",
  "id_proveedor": 1,
  "fecha_embarque": "2026-11-24T19:20:08.209000",
  "fecha_arribo_estimada": "2026-11-26T19:20:08.209000",
  "estado": "ANUNCIADO",
  "detalle_carga": [
    {
      "id_sku": 1,
      "cantidad_declarada": 120.0,
      "lote_proveedor": "LP-7781",
      "fecha_produccion": null,
      "fecha_caducidad": "2026-12-14T00:00:00",
      "rango_temperatura_controlada": "2C a 6C",
      "id_locacion_destino": null,
      "cantidad_lotes": null,
      "codigo_rfid_epc": null
    },
    {
      "id_sku": 2,
      "cantidad_declarada": 40.0,
      "lote_proveedor": "SIN-LOTE",
      "fecha_produccion": null,
      "fecha_caducidad": "2026-12-14T00:00:00",
      "rango_temperatura_controlada": "2C a 6C",
      "id_locacion_destino": null,
      "cantidad_lotes": null,
      "codigo_rfid_epc": null
    }
  ],
  "inspecciones": [],
  "version_esquema": 1
}
```

<a id="caso-56"></a>
## 56. svc-asn — PATCH /api/v1/asn/ASN-EV-5C6287/status

- **Objetivo:** Transición de estado inválida
- **URL:** `PATCH http://127.0.0.1:5005/api/v1/asn/ASN-EV-5C6287/status`
- **Código HTTP:** `409` (esperado `409`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 911457f4416e4965
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
  "correlation_id": "911457f4416e4965",
  "detalles": {
    "permitidas": [
      "CANCELADO",
      "EN_TRANSITO"
    ]
  }
}
```

<a id="caso-57"></a>
## 57. svc-asn — PATCH /api/v1/asn/ASN-EV-5C6287/status

- **Objetivo:** Actualización de documento ($set)
- **URL:** `PATCH http://127.0.0.1:5005/api/v1/asn/ASN-EV-5C6287/status`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 7e44f74acedb4c67
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
  "folio_asn": "ASN-EV-5C6287",
  "estado_anterior": "ANUNCIADO",
  "estado": "EN_TRANSITO"
}
```

<a id="caso-58"></a>
## 58. svc-asn — POST /api/v1/asn/ASN-EV-5C6287/inspection

- **Objetivo:** Inspección agregada con $push
- **URL:** `POST http://127.0.0.1:5005/api/v1/asn/ASN-EV-5C6287/inspection`
- **Código HTTP:** `201` (esperado `201`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: 89316b69979649f8
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
  "folio_asn": "ASN-EV-5C6287",
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
X-Correlation-Id: de9cc37742634814
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 5,
    "total": 3,
    "total_paginas": 1
  },
  "avisos_asn": [
    {
      "_id": "6b05e3686f49571e897eaada",
      "folio_asn": "ASN-EV-5C6287",
      "id_proveedor": 1,
      "fecha_embarque": "2026-11-24T19:20:08.209000",
      "fecha_arribo_estimada": "2026-11-26T19:20:08.209000",
      "estado": "EN_TRANSITO",
      "detalle_carga": [
        {
          "id_sku": 1,
          "cantidad_declarada": 120.0,
          "lote_proveedor": "LP-7781",
          "fecha_produccion": null,
          "fecha_caducidad": "2026-12-14T00:00:00",
          "rango_temperatura_controlada": "2C a 6C",
          "id_locacion_destino": null,
          "cantidad_lotes": null,
          "codigo_rfid_epc": null
        },
        {
          "id_sku": 2,
          "cantidad_declarada": 40.0,
          "lote_proveedor": "SIN-LOTE",
          "fecha_produccion": null,
          "fecha_caducidad": "2026-12-14T00:00:00",
          "rango_temperatura_controlada": "2C a 6C",
          "id_locacion_destino": null,
          "cantidad_lotes": null,
          "codigo_rfid_epc": null
        }
      ],
      "inspecciones": [
        {
          "id_inspeccion": "6b05e3686f49571e897eaadb",
          "fecha": "2026-11-24T19:20:08.257000",
          "inspector": "almacen@freshtrack.mx",
          "resultado": "CONFORME",
          "temperatura_registrada": 4.2,
          "observaciones": "Sellos íntegros"
        }
      ],
      "version_esquema": 1,
      "actualizado_en": "2026-11-24T19:20:08.249000",
      "ultima_inspeccion": "2026-11-24T19:20:08.257000"
    },
    {
      "_id": "6b05daa68362bd01583e85b8",
      "folio_asn": "ASN-PYTEST-8fc451",
      "id_proveedor": 1,
      "fecha_embarque": "2026-11-24T18:42:46.742000",
      "fecha_arribo_estimada": "2026-11-26T18:42:46.742000",
      "estado": "EN_TRANSITO",
      "detalle_carga": [
        {
          "id_sku": 1,
          "cantidad_declarada": 40.0,
          "lote_proveedor": "SIN-LOTE",
          "fecha_produccion": null,
          "fecha_caducidad": "2026-12-01T00:00:00",
          "rango_temperatura_controlada": "2C a 6C",
          "id_locacion_destino": null,
          "cantidad_lotes": null,
          "codigo_rfid_epc": null
        },
        {
          "id_sku": 2,
          "cantidad_declarada": 15.0,
          "lote_proveedor": "SIN-LOTE",
          "fecha_produccion": null,
          "fecha_caducidad": "2026-11-20T00:00:00",
          "rango_temperatura_c
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
X-Correlation-Id: 2e96efe3676d4c28
```

**Respuesta (application/json):**

```json
{
  "total_grupos": 3,
  "carga_consolidada": [
    {
      "despachos_asociados": 3,
      "id_proveedor": 1,
      "id_sku": 1,
      "piezas_totales": 200.0
    },
    {
      "despachos_asociados": 4,
      "id_proveedor": 1,
      "id_sku": 9,
      "piezas_totales": 200.0
    },
    {
      "despachos_asociados": 3,
      "id_proveedor": 1,
      "id_sku": 2,
      "piezas_totales": 70.0
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
X-Correlation-Id: fba740fecc034a34
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "ASN NO-EXISTE no encontrado.",
  "status": 404,
  "correlation_id": "fba740fecc034a34"
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
X-Correlation-Id: a565a2d58419462a
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
  "id_run": "88898729-0c9c-4318-8ccb-c38696bfcfac",
  "id_locacion": 3,
  "locacion": "Tienda San Pedro",
  "metodo": "SUAVIZACION_EXPONENCIAL",
  "metodo_etiqueta": "Suavización exponencial",
  "estrategia_dominante": "SUAVIZACION_EXPONENCIAL",
  "distribucion_estrategias": {
    "SUAVIZACION_EXPONENCIAL": 1
  },
  "salud_modelo": {
    "estado": "VIGILANCIA",
    "confiabilidad": "Media",
    "requiere_reemplazo": false,
    "psi": 0.0363,
    "z_nivel": -0.43,
    "cambio_nivel_pct": -9.1,
    "ratio_volatilidad": 1.95,
    "delta_ceros_pp": 7.1,
    "dias_atipicos": 2,
    "media_base": 46.53,
    "media_reciente": 42.3,
    "wmape": 37.3716,
    "mae": 12.709,
    "sesgo": 12.709,
    "mejora_vs_naive_pct": 39.7,
    "motivos": [
      "Error de proyección en zona de seguimiento (37.4%).",
      "Se detectaron 2 día(s) con demanda atípica en las últimas dos semanas.",
      "Sesgo sostenido detectado: el modelo sobreestima la demanda de forma consistente."
    ],
    "recomendacion": "Monitorear los próximos días y recalibrar la tienda si la variación persiste."
  },
  "horizonte": 7,
  "series": 1,
  "mae": 12.709,
  "rmse": 17.4887,
  "wmape": 37.3716,
  "sesgo": 12.709,
  "naive_mae": 21.09,
  "naive_wmape": 62.0164,
  "resultados": [
    {
      "id_sku": 1,
      "id_locacion": 3,
      "metodo_ganador": "SUAVIZACION_EXPONENCIAL",
      "metricas": {
        "mae": 12.709,
        "rmse": 17.4887,
        "wmape": 37.3716,
        "wape": 37.3716,
        "sesgo": 12.709,
        "demanda_intermitente": false,
        "n": 7,
        "suma_real": 238.05
      },
      "metricas_naive": {
        "mae": 21.09,
        "rmse": 26.5951,
        "wmape": 62.0164,
        "wape": 62.0164,
        "sesgo": 16.5757,
        "demanda_intermitente": false,
        "n": 7,
        "suma_real": 238.05
      },
      "mejora_vs_naive_pct": 39.74,
      "pronostico": [
        {
          "fecha": "2026-11-25",
          "horizonte_dia": 1,
          "valor": 21.23
        },
        {
          "fecha": "2026-11-26",
          "horizonte_dia": 2,
          "valor": 21.44
        },
        {
          "fecha": "2026-11-27",
          "horizonte_dia": 3,
          "valor": 27.51
        },
        {
          "fecha": "2026-11-28",
          "horizonte_dia": 4,
          "valor": 29.07
        },
        {
          "fecha": "2026-11-29",
          "horizonte_dia": 5,
          "valor": 27.52
        },
        {
          "fecha": "2026-11-30",
          "
… (respuesta recortada)
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
X-Correlation-Id: c9626c449ab54cbd
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
  "mensaje": "Método no soportado. Valores: ['AUTO', 'MEDIA_MOVIL', 'MEDIA_MOVIL_PONDERADA', 'SUAVIZACION_EXPONENCIAL']",
  "status": 400,
  "correlation_id": "c9626c449ab54cbd"
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
X-Correlation-Id: 4d36a48ecde94c6f
```

**Respuesta (application/json):**

```json
{
  "_id": "6b05e368f0e21a49e4839ab6",
  "id_sku": 1,
  "id_locacion": 3,
  "fecha_calculo": "2026-11-24T19:20:08.315000",
  "horizonte_proyeccion": {
    "fecha_inicio": "2026-11-25T00:00:00",
    "fecha_fin": "2026-12-01T00:00:00",
    "dias": 7
  },
  "modelo": "SUAVIZACION_EXPONENCIAL",
  "version_modelo": "1.0",
  "linaje": {
    "id_run": "88898729-0c9c-4318-8ccb-c38696bfcfac",
    "id_locacion": 3,
    "generado_por": "planner@freshtrack.mx"
  },
  "metricas": {
    "mae": 12.709,
    "rmse": 17.4887,
    "wmape": 37.3716,
    "wape": 37.3716,
    "sesgo": 12.709,
    "demanda_intermitente": false,
    "n": 7,
    "suma_real": 238.05
  },
  "puntos": [
    {
      "fecha": "2026-11-25T00:00:00",
      "demanda_pronosticada": 21.23,
      "intervalo_inferior": 18.05,
      "intervalo_superior": 24.41,
      "percentil": 50
    },
    {
      "fecha": "2026-11-26T00:00:00",
      "demanda_pronosticada": 21.44,
      "intervalo_inferior": 18.22,
      "intervalo_superior": 24.66,
      "percentil": 50
    },
    {
      "fecha": "2026-11-27T00:00:00",
      "demanda_pronosticada": 27.51,
      "intervalo_inferior": 23.38,
      "intervalo_superior": 31.64,
      "percentil": 50
    },
    {
      "fecha": "2026-11-28T00:00:00",
      "demanda_pronosticada": 29.07,
      "intervalo_inferior": 24.71,
      "intervalo_superior": 33.43,
      "percentil": 50
    },
    {
      "fecha": "2026-11-29T00:00:00",
      "demanda_pronosticada": 27.52,
      "intervalo_inferior": 23.39,
      "intervalo_superior": 31.65,
      "percentil": 50
    },
    {
      "fecha": "2026-11-30T00:00:00",
      "demanda_pronosticada": 19.76,
      "intervalo_inferior": 16.8,
      "intervalo_superior": 22.72,
      "percentil": 50
    },
    {
      "fecha": "2026-12-01T00:00:00",
      "demanda_pronosticada": 20.39,
      "intervalo_inferior": 17.33,
      "intervalo_superior": 23.45,
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
X-Correlation-Id: 4ac19dd9c50a4d9b
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 41,
    "total_paginas": 14
  },
  "ordenes": [
    {
      "id_orden": "bb8403b7-dcac-4a49-8efd-6f8b9ebb9e2b",
      "id_sku": 5,
      "producto": "Pechuga de Pollo kg",
      "id_locacion": 5,
      "locacion": "Tienda Valle Oriente",
      "id_proveedor": 4,
      "cantidad_sugerida": 40.0,
      "cantidad_aprobada": null,
      "prioridad": "ALTA",
      "estado": "PENDIENTE",
      "explicacion": "Producto: Pechuga de Pollo kg\nTienda: Tienda Valle Oriente\n\nDemanda prevista 7 días          94.93\nInventario físico                       93.77\nInventario próximo a vencer             54.43\nInventario útil                         39.34\nStock de seguridad                      40.00\nEntradas confirmadas (total)             0.00\n  · Órdenes en curso                     0.00\n  · Traslados entrantes (triaje)         0.00\nLead time                                   3 días\nMOQ                                     40.00\n\nNecesidad neta (Newsvendor)             28.46\n\nModelo Newsvendor:\n  Costo de faltante (Cu)           $    34.90\n  Costo de excedente (Co)          $    41.25\n  Fractil crítico Cu/(Cu+Co)           0.4583\n  Cantidad óptima Newsvendor            28.46\n  Política simple (referencia)          95.59\n  Ahorro esperado en costo         $ 2,086.84\n\nRecomendación: ordenar 40 Kg\n\nAdvertencias:\n  · Restricción de caducidad Newsvendor: el nivel objetivo se acotó a 5 días de vida útil para evitar merma futura.\n  · El proveedor tiene un pedido mínimo (MOQ) de 40 unidades y la necesidad calculada es de 28.46. Se sugiere comprar 40, es decir 11.54 unidades por encima de lo necesario.\n  · Riesgo de vencimiento: con 79.34 unidades se tardarían 5.9 días en venderse, pero el producto dura 5 días. Parte del pedido podría caducar.\n  · Triaje activo en esta tienda (25.39 u. con descuento preventivo vigente y 41.21 u. en traslado saliente): valida la reposición antes de autorizar la compra.\n  · 54.43 unidades del inventario actual están en riesgo de vencer antes de poder venderse; no se contaron como inventario útil.\n  · El inventario útil cubre 2.9 días y el proveedor tarda 3 días en surtir: hay riesgo de faltante si no se pide ahora.",
      "fecha_creacion": "2026-11-24T19:17:23.510014+00:00",
      "fecha_decision": null
    },
    {
      "id_orden": "9a34ffda-47f6-46e3-b9ea-30384f1b7d2c",
      "id_sku": 10,
      "producto": "Zanahoria kg",
      "id_locacion": 5,
… (respuesta recortada)
```

<a id="caso-66"></a>
## 66. svc-planning — POST /api/v1/planning/replenishment/orders/9a5bdfc6-93c1-419d-87c9-ff8f799da87a/approve

- **Objetivo:** Aprobar orden inexistente
- **URL:** `POST http://127.0.0.1:5006/api/v1/planning/replenishment/orders/9a5bdfc6-93c1-419d-87c9-ff8f799da87a/approve`
- **Código HTTP:** `404` (esperado `404`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
Content-Type: application/json
X-Correlation-Id: e8836f42b3444e98
```

**Cuerpo de la petición:**

```json
{}
```

**Respuesta (application/json):**

```json
{
  "error": "no_encontrado",
  "mensaje": "Orden 9a5bdfc6-93c1-419d-87c9-ff8f799da87a no encontrada.",
  "status": 404,
  "correlation_id": "e8836f42b3444e98"
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
X-Correlation-Id: 54bf2912f19246c9
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
    "activo": false
  },
  "contexto_mongo": {
    "id_sku": 1,
    "id_locacion": 3,
    "pronostico_reciente": {
      "_id": "6b05e368f0e21a49e4839ab6",
      "fecha_calculo": "2026-11-24T19:20:08.315000",
      "horizonte_proyeccion": {
        "fecha_inicio": "2026-11-25T00:00:00",
        "fecha_fin": "2026-12-01T00:00:00",
        "dias": 7
      },
      "modelo": "SUAVIZACION_EXPONENCIAL",
      "version_modelo": "1.0",
      "metricas": {
        "mae": 12.709,
        "rmse": 17.4887,
        "wmape": 37.3716,
        "wape": 37.3716,
        "sesgo": 12.709,
        "demanda_intermitente": false,
        "n": 7,
        "suma_real": 238.05
      },
      "puntos_count": 7
    },
    "alertas_activas_count": 0,
    "alertas_activas": [],
    "consultado_en": "2026-11-24T19:20:08.355727+00:00"
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
X-Correlation-Id: ca016c695ad0484f
```

**Respuesta (application/json):**

```json
{
  "total_modelos": 3,
  "kpis_modelos": [
    {
      "total_corridas": 53,
      "modelo": "SUAVIZACION_EXPONENCIAL",
      "mae_promedio": 11.247,
      "rmse_promedio": 15.172
    },
    {
      "total_corridas": 32,
      "modelo": "MEDIA_MOVIL",
      "mae_promedio": 6.586,
      "rmse_promedio": 7.97
    },
    {
      "total_corridas": 13,
      "modelo": "MEDIA_MOVIL_PONDERADA",
      "mae_promedio": 6.692,
      "rmse_promedio": 8.202
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
X-Correlation-Id: 1f78a7324b174f67
```

**Respuesta (application/json):**

```json
{
  "status": "COMPLETADO",
  "ventana_dias": 5,
  "total_escaneados": 9,
  "alertas_emitidas": 9,
  "detalle": [
    {
      "id_mongo": "6b05e36807c1e75aee0f3215",
      "id_lote": "1fa8e517-a010-410e-8eee-7a74ede3ad9d",
      "criticidad": "CRITICAL"
    },
    {
      "id_mongo": "6b05e36807c1e75aee0f3216",
      "id_lote": "c525a245-1886-4005-9fc1-a712ca2fc79b",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6b05e36807c1e75aee0f3217",
      "id_lote": "98a38ed2-8bdc-4783-b7ea-57d03033aa74",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6b05e36807c1e75aee0f3218",
      "id_lote": "2235914a-6b31-4f39-8bd0-28470cc98739",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6b05e36807c1e75aee0f3219",
      "id_lote": "fc6f66fe-4450-4b7b-877d-99fd3966a605",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6b05e36807c1e75aee0f321a",
      "id_lote": "a48e57e3-e6ca-43ad-a6c9-5246574c66f8",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6b05e36807c1e75aee0f321b",
      "id_lote": "393f1d7c-97f2-4436-950a-2fd6ea7d0304",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6b05e36807c1e75aee0f321c",
      "id_lote": "6d5edf70-f9f5-4a0e-b8db-6bddc0860440",
      "criticidad": "WARNING"
    },
    {
      "id_mongo": "6b05e36807c1e75aee0f321d",
      "id_lote": "23cec36a-262f-4aa6-9268-c05e5b274e6a",
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
X-Correlation-Id: fa33e15e457145fb
```

**Respuesta (application/json):**

```json
{
  "total": 3,
  "alertas": [
    {
      "_id": "6b05e36807c1e75aee0f321d",
      "tipo": "RIESGO_PRE_MERMA",
      "criticidad": "WARNING",
      "mensaje": "Lote de 'Tomate Bola kg' vence en 5 día(s). Stock: 189.62 u.",
      "generada_en": "2026-11-24T19:20:08.384000",
      "atendida": false,
      "version_esquema": 1,
      "contexto": {
        "dias_restantes": 5,
        "producto": "Tomate Bola kg",
        "id_lote": "23cec36a-262f-4aa6-9268-c05e5b274e6a",
        "cantidad": 189.62
      },
      "id_sku": 4,
      "id_locacion": 3
    },
    {
      "_id": "6b05e36807c1e75aee0f321c",
      "tipo": "RIESGO_PRE_MERMA",
      "criticidad": "WARNING",
      "mensaje": "Lote de 'Crema Ácida 450g' vence en 4 día(s). Stock: 73 u.",
      "generada_en": "2026-11-24T19:20:08.382000",
      "atendida": false,
      "version_esquema": 1,
      "contexto": {
        "dias_restantes": 4,
        "producto": "Crema Ácida 450g",
        "id_lote": "6d5edf70-f9f5-4a0e-b8db-6bddc0860440",
        "cantidad": 73.0
      },
      "id_sku": 9,
      "id_locacion": 3
    },
    {
      "_id": "6b05e36807c1e75aee0f321b",
      "tipo": "RIESGO_PRE_MERMA",
      "criticidad": "WARNING",
      "mensaje": "Lote de 'Crema Ácida 450g' vence en 4 día(s). Stock: 48 u.",
      "generada_en": "2026-11-24T19:20:08.381000",
      "atendida": false,
      "version_esquema": 1,
      "contexto": {
        "dias_restantes": 4,
        "producto": "Crema Ácida 450g",
        "id_lote": "393f1d7c-97f2-4436-950a-2fd6ea7d0304",
        "cantidad": 48.0
      },
      "id_sku": 9,
      "id_locacion": 3
    }
  ]
}
```

<a id="caso-71"></a>
## 71. svc-alerts — PATCH /api/v1/alerts/6b05e36807c1e75aee0f321d/resolve

- **Objetivo:** Atender alerta (inicia retención TTL)
- **URL:** `PATCH http://127.0.0.1:5007/api/v1/alerts/6b05e36807c1e75aee0f321d/resolve`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 626c09de4e2e4b05
```

**Respuesta (application/json):**

```json
{
  "id_mongo": "6b05e36807c1e75aee0f321d",
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
X-Correlation-Id: 69dd8f3a19974d80
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_mongo' debe ser un ObjectId de 24 caracteres hexadecimales.",
  "status": 400,
  "correlation_id": "69dd8f3a19974d80"
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
X-Correlation-Id: b8e31007a0f94523
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<reporte_esg_sostenibilidad><alimento_recuperado_kg>19.0</alimento_recuperado_kg><desperdicio_evitado_neto_kg>0.0</desperdicio_evitado_neto_kg><contrafactual_organico_kg>110.98</contrafactual_organico_kg><ahorro_financiero_mxn>850.1</ahorro_financiero_mxn><co2e_evitado_kg>0.0</co2e_evitado_kg><co2e_evitado_toneladas>0.0</co2e_evitado_toneladas><factor_conversion>2.5 kg CO2e / kg alimento perecedero (referencia FAO)</factor_conversion><indicadores_6><producto_en_riesgo><unidades>1246.1</unidades><valor>23955.17</valor><lotes>26</lotes><definicion>Existencia vigente en clasificación VIGILANCIA o CRÍTICO con probabilidad de caducar.</definicion></producto_en_riesgo><desperdicio_proyectado><unidades>278.73</unidades><valor>7130.86</valor><definicion>Cantidad estimada que se perdería si no se ejecuta ninguna intervención antes del vencimiento.</definicion></desperdicio_proyectado><producto_recuperado><unidades>19.0</unidades><valor>850.1</valor><definicion>Unidades efectivamente vendidas pertenecientes a lotes con transferencia ejecutada o descuento aprobado.</definicion></producto_recuperado><desperdicio_evitado_estimado><unidades>0.0</unidades><contrafactual_organico>110.98</contrafactual_organico><porcentaje_causal>0.0</porcentaje_causal><definicion>Diferencia neta frente a la línea base contrafactual sin intervención (excluye ventas orgánicas que habrían ocurrido a precio normal).</definicion></desperdicio_evitado_estimado><reduccion_observada_merma><tasa_reciente_pct>1.35</tasa_reciente_pct><tasa_base_historica_pct>1.51</tasa_base_historica_pct><cambio_puntos_pct>0.16</cambio_puntos_pct><merma_reciente_unidades>1240.71</merma_reciente_unidades><ventana_dias>30</ventana_dias><definicion>Cambio empírico comprobado en las mermas registradas frente al histórico base.</definicion></reduccion_observada_merma><co2e_evitado_estimado><kg_co2e>0.0</kg_co2e><toneladas_co2e>0.0</toneladas_co2e><factor>2.5 kg CO2e / kg alimento perecedero (referencia FAO)</factor><definicion>Conversión ambiental calculada únicamente sobre el desperdicio evitado estimado neto (contrafactual).</definicion></co2e_evitado_estimado></indicadores_6><fuente>redis_cache</fuente></reporte_esg_sostenibilidad>
```

<a id="caso-74"></a>
## 74. svc-alerts — GET /api/v1/alerts/analytics/kpis

- **Objetivo:** Alertas por locación y criticidad (agregación)
- **URL:** `GET http://127.0.0.1:5007/api/v1/alerts/analytics/kpis`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs…
X-Correlation-Id: 3d841eb4763a4bba
```

**Respuesta (application/json):**

```json
{
  "total_grupos": 2,
  "kpis_alertas": [
    {
      "total_alertas": 72,
      "id_locacion": 3,
      "criticidad": "WARNING",
      "promedio_dias_restantes": 6.3
    },
    {
      "total_alertas": 6,
      "id_locacion": 3,
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
X-Correlation-Id: 9ed79b94e8354740
```

**Cuerpo de la petición:**

```xml
<audit_log_request><accion>REVISION_CUMPLIMIENTO</accion><descripcion>Revisión de mermas de octubre</descripcion></audit_log_request>
```

**Respuesta (application/json):**

```json
{
  "id_evento": "f49d907c-0a2e-4888-913f-2515925cb698",
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
X-Correlation-Id: 70cbc53a31544d01
```

**Respuesta (application/json):**

```json
{
  "paginacion": {
    "pagina": 1,
    "por_pagina": 3,
    "total": 3,
    "total_paginas": 1
  },
  "bitacora": [
    {
      "id_evento": "f49d907c-0a2e-4888-913f-2515925cb698",
      "fecha_evento": "2026-11-24T19:20:08.759748+00:00",
      "accion": "REVISION_CUMPLIMIENTO",
      "nombre_tabla": "sistema",
      "id_registro": null,
      "descripcion": "Revisión de mermas de octubre",
      "usuario_email": "auditor@freshtrack.mx",
      "ip": "192.168.65.1/32"
    },
    {
      "id_evento": "34e8c8df-9811-4579-bfa3-d4e0b469c2c6",
      "fecha_evento": "2026-11-24T18:42:47.056107+00:00",
      "accion": "REVISION_CUMPLIMIENTO",
      "nombre_tabla": "sistema",
      "id_registro": null,
      "descripcion": "pytest-1cb1f902",
      "usuario_email": "auditor@freshtrack.mx",
      "ip": "127.0.0.1/32"
    },
    {
      "id_evento": "c2a07bb1-3796-4fa1-97a1-529f8b1df8e8",
      "fecha_evento": "2026-11-24T18:27:57.036220+00:00",
      "accion": "REVISION_CUMPLIMIENTO",
      "nombre_tabla": "sistema",
      "id_registro": null,
      "descripcion": "pytest-81fe49b8",
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
X-Correlation-Id: 8898cc809b8a45ab
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'desde' debe tener formato YYYY-MM-DD.",
  "status": 400,
  "correlation_id": "8898cc809b8a45ab"
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
X-Correlation-Id: 79f2d29621324322
```

**Respuesta (application/json):**

```json
{
  "error": "acceso_denegado",
  "mensaje": "El rol 'store_manager' no tiene permiso para esta operación.",
  "status": 403,
  "correlation_id": "79f2d29621324322",
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
X-Correlation-Id: e8bcc04ea6c94e38
```

**Respuesta (application/json):**

```json
{
  "error": "parametro_invalido",
  "mensaje": "'id_lote' debe ser un UUID válido.",
  "status": 400,
  "correlation_id": "e8bcc04ea6c94e38"
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
X-Correlation-Id: ab93ad4b16324541
```

**Respuesta (application/json):**

```json
{
  "total": 5,
  "stream_eventos": [
    {
      "event_id": "76df7b905ff84ce3a40b2fafdd68aa19",
      "event_type": "ALERTA_ATENDIDA",
      "timestamp": "2026-11-24T19:20:08.414579+00:00",
      "correlation_id": "626c09de4e2e4b05",
      "user_id": "40e4de83-351f-46c9-b6bd-cbabe206b924",
      "user_role": "store_manager",
      "location_id": "",
      "payload": {
        "id_mongo": "6b05e36807c1e75aee0f321d"
      },
      "id": "1795548008415-0"
    },
    {
      "event_id": "50ba220e24e74346b23e906e6edda390",
      "event_type": "ALERTA_EMITIDA",
      "timestamp": "2026-11-24T19:20:08.385379+00:00",
      "correlation_id": "1f78a7324b174f67",
      "user_id": "40e4de83-351f-46c9-b6bd-cbabe206b924",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "mongo_id": "6b05e36807c1e75aee0f321d",
        "criticidad": "WARNING",
        "id_sku": 4,
        "dias_restantes": 5
      },
      "id": "1795548008385-0"
    },
    {
      "event_id": "596ed2e8a3e148a5acba4851cb84f64f",
      "event_type": "ALERTA_EMITIDA",
      "timestamp": "2026-11-24T19:20:08.383742+00:00",
      "correlation_id": "1f78a7324b174f67",
      "user_id": "40e4de83-351f-46c9-b6bd-cbabe206b924",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "mongo_id": "6b05e36807c1e75aee0f321c",
        "criticidad": "WARNING",
        "id_sku": 9,
        "dias_restantes": 4
      },
      "id": "1795548008384-0"
    },
    {
      "event_id": "97d313b90d5e4aeab2cfde28b37652b4",
      "event_type": "ALERTA_EMITIDA",
      "timestamp": "2026-11-24T19:20:08.382093+00:00",
      "correlation_id": "1f78a7324b174f67",
      "user_id": "40e4de83-351f-46c9-b6bd-cbabe206b924",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "mongo_id": "6b05e36807c1e75aee0f321b",
        "criticidad": "WARNING",
        "id_sku": 9,
        "dias_restantes": 4
      },
      "id": "1795548008382-0"
    },
    {
      "event_id": "bd667c246b224f6880162fd1878f13be",
      "event_type": "ALERTA_EMITIDA",
      "timestamp": "2026-11-24T19:20:08.380650+00:00",
      "correlation_id": "1f78a7324b174f67",
      "user_id": "40e4de83-351f-46c9-b6bd-cbabe206b924",
      "user_role": "store_manager",
      "location_id": "3",
      "payload": {
        "mongo_id": "6b05e36807c1e75aee0f321a",
        "criticidad": "WARNING",
        "id_sku": 4,
        "dias_restantes": 3
      },
      "id": "1795548008380-
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
X-Correlation-Id: 1242c0c4c1c74247
```

**Respuesta (application/xml; charset=utf-8):**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<service_health><service>svc-auth</service><status>HEALTHY</status><version>1.0.0</version><process><status>UP</status><pid>1</pid><uptime_seconds>1349.4</uptime_seconds><started_at>2026-11-24T18:57:39.559462+00:00</started_at></process><response_time_ms>3.03</response_time_ms><checked_at>2026-11-24T19:20:08.804944+00:00</checked_at><dependencies><postgres>true</postgres><mongo>true</mongo><redis>true</redis><bucket>true</bucket></dependencies></service_health>
```

<a id="caso-82"></a>
## 82. svc-catalog — GET /health

- **Objetivo:** Endpoint de salud con estado de dependencias
- **URL:** `GET http://127.0.0.1:5002/health`
- **Código HTTP:** `200` (esperado `200`)
- **Headers:**

```http
X-Correlation-Id: d9564994168c4cb5
```

**Respuesta (application/json):**

```json
{
  "service": "svc-catalog",
  "status": "HEALTHY",
  "version": "1.0.0",
  "process": {
    "status": "UP",
    "pid": 1,
    "uptime_seconds": 1348.9,
    "started_at": "2026-11-24T18:57:40.070144+00:00"
  },
  "response_time_ms": 2.83,
  "checked_at": "2026-11-24T19:20:08.810569+00:00",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true,
    "bucket": true
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
X-Correlation-Id: 58cd1d082e11430b
```

**Respuesta (application/json):**

```json
{
  "service": "svc-inventory",
  "status": "HEALTHY",
  "version": "1.0.0",
  "process": {
    "status": "UP",
    "pid": 1,
    "uptime_seconds": 1349.7,
    "started_at": "2026-11-24T18:57:39.276148+00:00"
  },
  "response_time_ms": 3.9,
  "checked_at": "2026-11-24T19:20:08.816941+00:00",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true,
    "bucket": true
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
X-Correlation-Id: 387d0be15ee04c90
```

**Respuesta (application/json):**

```json
{
  "service": "svc-commercial",
  "status": "HEALTHY",
  "version": "1.0.0",
  "process": {
    "status": "UP",
    "pid": 1,
    "uptime_seconds": 1349.8,
    "started_at": "2026-11-24T18:57:39.193763+00:00"
  },
  "response_time_ms": 3.44,
  "checked_at": "2026-11-24T19:20:08.822969+00:00",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true,
    "bucket": true
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
X-Correlation-Id: e81de5cab68c405b
```

**Respuesta (application/json):**

```json
{
  "service": "svc-asn",
  "status": "HEALTHY",
  "version": "1.0.0",
  "process": {
    "status": "UP",
    "pid": 1,
    "uptime_seconds": 1349.5,
    "started_at": "2026-11-24T18:57:39.494354+00:00"
  },
  "response_time_ms": 3.28,
  "checked_at": "2026-11-24T19:20:08.828805+00:00",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true,
    "bucket": true
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
X-Correlation-Id: f3697104a3a54f3d
```

**Respuesta (application/json):**

```json
{
  "service": "svc-planning",
  "status": "HEALTHY",
  "version": "1.0.0",
  "process": {
    "status": "UP",
    "pid": 1,
    "uptime_seconds": 1349.7,
    "started_at": "2026-11-24T18:57:39.232059+00:00"
  },
  "response_time_ms": 2.9,
  "checked_at": "2026-11-24T19:20:08.834205+00:00",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true,
    "bucket": true
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
X-Correlation-Id: 60ce2184eefc483e
```

**Respuesta (application/json):**

```json
{
  "service": "svc-alerts",
  "status": "HEALTHY",
  "version": "1.0.0",
  "process": {
    "status": "UP",
    "pid": 1,
    "uptime_seconds": 1349.8,
    "started_at": "2026-11-24T18:57:39.190532+00:00"
  },
  "response_time_ms": 3.02,
  "checked_at": "2026-11-24T19:20:08.839726+00:00",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true,
    "bucket": true
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
X-Correlation-Id: 7def68b1046d4b7f
```

**Respuesta (application/json):**

```json
{
  "service": "svc-audit",
  "status": "HEALTHY",
  "version": "1.0.0",
  "process": {
    "status": "UP",
    "pid": 1,
    "uptime_seconds": 1349.1,
    "started_at": "2026-11-24T18:57:39.877123+00:00"
  },
  "response_time_ms": 2.9,
  "checked_at": "2026-11-24T19:20:08.845379+00:00",
  "dependencies": {
    "postgres": true,
    "mongo": true,
    "redis": true,
    "bucket": true
  }
}
```
