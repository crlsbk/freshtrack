# Catálogo de endpoints — Microservicios FreshTrack

Generado automáticamente desde `/api/v1/openapi.json` de cada servicio con
`python scripts/generar_catalogo_endpoints.py`. Todos los endpoints aceptan
`Accept: application/xml` para responder en XML; los que reciben cuerpo aceptan
`Content-Type: application/json` o `application/xml`.

**67 operaciones** en 8 servicios.

## svc-auth — puerto 5001

_Auth & Identity Service (FreshTrack)_

Swagger UI: `http://localhost:5001/api/v1/docs`

| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |
|---|---|---|---|---|---|
| `GET` | `/api/v1/auth/counters` | Contadores operativos en Redis | JWT · admin |  | 200, 400, 401, 403, 500 |
| `POST` | `/api/v1/auth/login` | Inicio de sesión y emisión de JWT | Pública | JSON/XML + XSD | 200, 400, 401, 429, 500 |
| `POST` | `/api/v1/auth/logout` | Cierre de sesión y revocación del token | JWT · cualquier usuario autenticado |  | 200, 401, 500 |
| `GET` | `/api/v1/auth/me` | Perfil del usuario autenticado | JWT · cualquier usuario autenticado |  | 200, 401, 500 |
| `GET` | `/api/v1/auth/sessions/{id_usuario}` | Sesiones activas de un usuario (Redis) | JWT · admin |  | 200, 401, 403, 404, 500 |
| `DELETE` | `/api/v1/auth/sessions/{id_usuario}` | Cierra todas las sesiones de un usuario | JWT · admin |  | 200, 401, 403, 404, 500 |
| `GET` | `/api/v1/auth/users` | Listado paginado de usuarios | JWT · admin |  | 200, 400, 401, 403, 500 |
| `PATCH` | `/api/v1/auth/users/{id_usuario}/status` | Activa o desactiva un usuario | JWT · admin | JSON/XML | 200, 400, 401, 403, 404, 409, 500 |
| `POST` | `/api/v1/auth/verify` | Verificación de token para otros componentes | Pública |  | 200, 400, 401, 500 |
| `GET` | `/api/v1/contracts/{nombre_xsd}.xsd` | Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request). | Pública |  | 200, 404, 500 |
| `GET` | `/health` | Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis). | Pública |  | 200, 500 |

<details><summary><code>POST /api/v1/auth/login</code> — ejemplo de cuerpo</summary>

```json
{
  "email": "admin@freshtrack.mx",
  "password": "Admin2026!"
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<login_request><email>admin@freshtrack.mx</email><password>Admin2026!</password></login_request>
```

</details>

<details><summary><code>PATCH /api/v1/auth/users/{id_usuario}/status</code> — ejemplo de cuerpo</summary>

```json
{
  "estado_activo": false
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<user_status_request><estado_activo>false</estado_activo></user_status_request>
```

</details>

## svc-catalog — puerto 5002

_Master Catalog & Locations Service (FreshTrack)_

Swagger UI: `http://localhost:5002/api/v1/docs`

| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |
|---|---|---|---|---|---|
| `GET` | `/api/v1/catalog/locations` | Tiendas y CEDIS (Cache-Aside) | Pública |  | 200, 400, 500 |
| `GET` | `/api/v1/catalog/products` | Listado paginado de productos (Cache-Aside en Redis) | Pública |  | 200, 400, 429, 500 |
| `POST` | `/api/v1/catalog/products` | Alta de producto perecedero | JWT · admin, buyer | JSON/XML + XSD | 201, 400, 401, 403, 409, 415, 500 |
| `GET` | `/api/v1/catalog/products/{id_sku}` | Detalle de un producto por SKU | Pública |  | 200, 404, 500 |
| `PUT` | `/api/v1/catalog/products/{id_sku}` | Reemplazo completo de un producto | JWT · admin, buyer | JSON/XML + XSD | 200, 400, 401, 403, 404, 409, 500 |
| `PATCH` | `/api/v1/catalog/products/{id_sku}` | Actualización parcial de un producto | JWT · admin, buyer | JSON/XML + XSD | 200, 400, 401, 403, 404, 409, 500 |
| `DELETE` | `/api/v1/catalog/products/{id_sku}` | Baja lógica de producto | JWT · admin |  | 200, 401, 403, 404, 500 |
| `GET` | `/api/v1/catalog/suppliers` | Proveedores con lead time y MOQ | JWT · admin, buyer, planner |  | 200, 400, 401, 403, 500 |
| `GET` | `/api/v1/contracts/{nombre_xsd}.xsd` | Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request). | Pública |  | 200, 404, 500 |
| `GET` | `/health` | Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis). | Pública |  | 200, 500 |

<details><summary><code>POST /api/v1/catalog/products</code> — ejemplo de cuerpo</summary>

```json
{
  "codigo_gtin": "7501234567890",
  "nombre": "Fresa orgánica 500 g",
  "categoria": "Frutas",
  "unidad_medida": "Pieza",
  "vida_util_estandar": 6,
  "precio_costo": 28.5,
  "precio_venta": 45.9
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<producto_request><codigo_gtin>7501234567890</codigo_gtin><nombre>Fresa orgánica 500 g</nombre><categoria>Frutas</categoria><unidad_medida>Pieza</unidad_medida><vida_util_estandar>6</vida_util_estandar><precio_costo>28.5</precio_costo><precio_venta>45.9</precio_venta></producto_request>
```

</details>

<details><summary><code>PUT /api/v1/catalog/products/{id_sku}</code> — ejemplo de cuerpo</summary>

```json
{
  "codigo_gtin": "7501234567890",
  "nombre": "Fresa orgánica 500 g",
  "categoria": "Frutas",
  "unidad_medida": "Pieza",
  "vida_util_estandar": 6,
  "precio_costo": 28.5,
  "precio_venta": 45.9
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<producto_request><codigo_gtin>7501234567890</codigo_gtin><nombre>Fresa orgánica 500 g</nombre><categoria>Frutas</categoria><unidad_medida>Pieza</unidad_medida><vida_util_estandar>6</vida_util_estandar><precio_costo>28.5</precio_costo><precio_venta>45.9</precio_venta></producto_request>
```

</details>

<details><summary><code>PATCH /api/v1/catalog/products/{id_sku}</code> — ejemplo de cuerpo</summary>

```json
{
  "precio_venta": 39.9
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<producto_request><precio_venta>39.9</precio_venta></producto_request>
```

</details>

## svc-inventory — puerto 5003

_Inventory & FEFO Engine Service (FreshTrack)_

Swagger UI: `http://localhost:5003/api/v1/docs`

| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |
|---|---|---|---|---|---|
| `GET` | `/api/v1/contracts/{nombre_xsd}.xsd` | Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request). | Pública |  | 200, 404, 500 |
| `POST` | `/api/v1/inventory/cancel-reservation` | Compensación de la Saga: libera una reserva | JWT · admin, store_manager, warehouse | JSON/XML | 200, 400, 401, 403, 404, 500 |
| `GET` | `/api/v1/inventory/fefo-queue/{id_sku}/{id_locacion}` | Cola de consumo FEFO de un SKU en una locación | JWT · cualquier usuario autenticado |  | 200, 401, 404, 500 |
| `POST` | `/api/v1/inventory/reserve-fefo` | Paso 1 de la Saga: reserva de lotes en orden FEFO | JWT · admin, store_manager, warehouse | JSON/XML + XSD | 200, 400, 401, 403, 409, 429, 500 |
| `GET` | `/api/v1/inventory/stock` | Existencias disponibles por lote (paginado) | JWT · cualquier usuario autenticado |  | 200, 400, 401, 500 |
| `GET` | `/health` | Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis). | Pública |  | 200, 500 |

<details><summary><code>POST /api/v1/inventory/cancel-reservation</code> — ejemplo de cuerpo</summary>

```json
{
  "saga_id": "saga-demo-001"
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<cancelacion_request><saga_id>saga-demo-001</saga_id></cancelacion_request>
```

</details>

<details><summary><code>POST /api/v1/inventory/reserve-fefo</code> — ejemplo de cuerpo</summary>

```json
{
  "id_locacion": 2,
  "saga_id": "saga-demo-001",
  "lineas": [
    {
      "id_sku": 1,
      "cantidad": 3
    }
  ]
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<reserva_request><id_locacion>2</id_locacion><saga_id>saga-demo-001</saga_id><lineas><item><id_sku>1</id_sku><cantidad>3</cantidad></item></lineas></reserva_request>
```

</details>

## svc-commercial — puerto 5004

_Commercial, POS & Shrinkage Service (FreshTrack)_

Swagger UI: `http://localhost:5004/api/v1/docs`

| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |
|---|---|---|---|---|---|
| `PUT` | `/api/v1/commercial/cart/{cart_id}` | Guarda (o reemplaza) un carrito POS temporal en Redis | JWT · cualquier usuario autenticado | JSON/XML | 200, 400, 401, 404, 500 |
| `POST` | `/api/v1/commercial/cart/{cart_id}` | Guarda (o reemplaza) un carrito POS temporal en Redis | JWT · cualquier usuario autenticado | JSON/XML | 200, 400, 401, 404, 500 |
| `GET` | `/api/v1/commercial/cart/{cart_id}` | Consulta un carrito temporal y su TTL | JWT · cualquier usuario autenticado |  | 200, 401, 404, 500 |
| `DELETE` | `/api/v1/commercial/cart/{cart_id}` | Consume y elimina el carrito temporal | JWT · cualquier usuario autenticado |  | 200, 401, 404, 500 |
| `POST` | `/api/v1/commercial/checkout` | Venta POS con Saga orquestada y consumo FEFO | JWT · admin, store_manager, warehouse | JSON/XML + XSD | 201, 400, 401, 403, 409, 415, 429, 500 |
| `GET` | `/api/v1/commercial/sales` | Historial de ventas (filtros y paginación) | JWT · cualquier usuario autenticado |  | 200, 400, 401, 500 |
| `POST` | `/api/v1/commercial/shrinkage` | Registro justificado de merma | JWT · admin, store_manager, warehouse | JSON/XML + XSD | 201, 400, 401, 403, 409, 500 |
| `GET` | `/api/v1/contracts/{nombre_xsd}.xsd` | Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request). | Pública |  | 200, 404, 500 |
| `GET` | `/health` | Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis). | Pública |  | 200, 500 |

<details><summary><code>PUT /api/v1/commercial/cart/{cart_id}</code> — ejemplo de cuerpo</summary>

```json
{
  "id_locacion": 2,
  "lineas": [
    {
      "id_sku": 1,
      "cantidad": 2
    }
  ]
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<carrito_request><id_locacion>2</id_locacion><lineas><item><id_sku>1</id_sku><cantidad>2</cantidad></item></lineas></carrito_request>
```

</details>

<details><summary><code>POST /api/v1/commercial/cart/{cart_id}</code> — ejemplo de cuerpo</summary>

```json
{
  "id_locacion": 2,
  "lineas": [
    {
      "id_sku": 1,
      "cantidad": 2
    }
  ]
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<carrito_request><id_locacion>2</id_locacion><lineas><item><id_sku>1</id_sku><cantidad>2</cantidad></item></lineas></carrito_request>
```

</details>

<details><summary><code>POST /api/v1/commercial/checkout</code> — ejemplo de cuerpo</summary>

```json
{
  "id_locacion": 2,
  "canal": "TIENDA",
  "lineas": [
    {
      "id_sku": 1,
      "cantidad": 2
    },
    {
      "id_sku": 3,
      "cantidad": 1
    }
  ]
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<checkout_request><id_locacion>2</id_locacion><canal>TIENDA</canal><lineas><item><id_sku>1</id_sku><cantidad>2</cantidad></item><item><id_sku>3</id_sku><cantidad>1</cantidad></item></lineas></checkout_request>
```

</details>

<details><summary><code>POST /api/v1/commercial/shrinkage</code> — ejemplo de cuerpo</summary>

```json
{
  "id_lote": "0f8b6f8e-6a7c-4b1e-9d1a-2b3c4d5e6f70",
  "id_locacion": 2,
  "cantidad": 1.5,
  "causa": "CADUCIDAD",
  "observacion": "Producto vencido en anaquel"
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<merma_request><id_lote>0f8b6f8e-6a7c-4b1e-9d1a-2b3c4d5e6f70</id_lote><id_locacion>2</id_locacion><cantidad>1.5</cantidad><causa>CADUCIDAD</causa><observacion>Producto vencido en anaquel</observacion></merma_request>
```

</details>

## svc-asn — puerto 5005

_Inbound Logistics & ASN Reception Service (FreshTrack)_

Swagger UI: `http://localhost:5005/api/v1/docs`

| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |
|---|---|---|---|---|---|
| `POST` | `/api/v1/asn` | Ingesta de un ASN (JSON o XML) | JWT · admin, buyer, supplier, warehouse | JSON/XML + XSD | 201, 400, 401, 403, 409, 415, 500 |
| `GET` | `/api/v1/asn` | Listado de ASN con filtros y paginación | JWT · cualquier usuario autenticado |  | 200, 400, 401, 500 |
| `GET` | `/api/v1/asn/{folio_asn}` | Detalle de un ASN por folio | JWT · cualquier usuario autenticado |  | 200, 401, 404, 500 |
| `POST` | `/api/v1/asn/{folio_asn}/inspection` | Agrega una inspección de calidad / cadena de frío | JWT · admin, warehouse | JSON/XML | 201, 400, 401, 403, 404, 500 |
| `PATCH` | `/api/v1/asn/{folio_asn}/status` | Cambio de estado del ASN | JWT · admin, warehouse | JSON/XML | 200, 400, 401, 403, 404, 409, 500 |
| `GET` | `/api/v1/asn/analytics/summary` | Carga consolidada por proveedor (pipeline de agregación) | JWT · cualquier usuario autenticado |  | 200, 401, 500 |
| `GET` | `/api/v1/contracts/{nombre_xsd}.xsd` | Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request). | Pública |  | 200, 404, 500 |
| `GET` | `/health` | Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis). | Pública |  | 200, 500 |

<details><summary><code>POST /api/v1/asn</code> — ejemplo de cuerpo</summary>

```json
{
  "folio_asn": "ASN-2026-0001",
  "id_proveedor": 1,
  "detalle_carga": [
    {
      "id_sku": 1,
      "cantidad_declarada": 120,
      "lote_proveedor": "LP-7781",
      "fecha_caducidad": "2026-11-05",
      "rango_temperatura_controlada": "2C a 6C"
    }
  ]
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<asn_request><folio_asn>ASN-2026-0001</folio_asn><id_proveedor>1</id_proveedor><detalle_carga><item><id_sku>1</id_sku><cantidad_declarada>120</cantidad_declarada><lote_proveedor>LP-7781</lote_proveedor><fecha_caducidad>2026-11-05</fecha_caducidad><rango_temperatura_controlada>2C a 6C</rango_temperatura_controlada></item></detalle_carga></asn_request>
```

</details>

<details><summary><code>POST /api/v1/asn/{folio_asn}/inspection</code> — ejemplo de cuerpo</summary>

```json
{
  "resultado": "CONFORME",
  "temperatura_registrada": 4.2,
  "observaciones": "Sellos íntegros"
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<inspeccion_request><resultado>CONFORME</resultado><temperatura_registrada>4.2</temperatura_registrada><observaciones>Sellos íntegros</observaciones></inspeccion_request>
```

</details>

<details><summary><code>PATCH /api/v1/asn/{folio_asn}/status</code> — ejemplo de cuerpo</summary>

```json
{
  "estado": "EN_TRANSITO"
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<asn_status_request><estado>EN_TRANSITO</estado></asn_status_request>
```

</details>

## svc-planning — puerto 5006

_Demand Planning & Replenishment Service (FreshTrack)_

Swagger UI: `http://localhost:5006/api/v1/docs`

| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |
|---|---|---|---|---|---|
| `GET` | `/api/v1/contracts/{nombre_xsd}.xsd` | Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request). | Pública |  | 200, 404, 500 |
| `GET` | `/api/v1/planning/forecast/analytics/kpis` | Métricas de precisión por modelo (pipeline de agregación) | JWT · cualquier usuario autenticado |  | 200, 401, 500 |
| `GET` | `/api/v1/planning/forecast/latest/{sku_id}/{locacion_id}` | Última serie pronosticada (MongoDB) para un SKU y tienda | JWT · cualquier usuario autenticado |  | 200, 401, 404, 500 |
| `POST` | `/api/v1/planning/forecast/run` | Ejecuta una corrida de pronóstico | JWT · admin, buyer, planner | JSON/XML + XSD | 201, 400, 401, 403, 500 |
| `POST` | `/api/v1/planning/replenishment/generate` | Genera órdenes de reabastecimiento sugeridas | JWT · admin, buyer, planner | JSON/XML | 201, 400, 401, 403, 500 |
| `GET` | `/api/v1/planning/replenishment/orders` | Órdenes de reabastecimiento (filtros y paginación) | JWT · admin, buyer, planner, store_manager |  | 200, 400, 401, 403, 500 |
| `POST` | `/api/v1/planning/replenishment/orders/{id_orden}/approve` | Aprueba una orden PENDIENTE (cantidad opcional) | JWT · admin, buyer, planner, store_manager | JSON/XML | 200, 400, 401, 403, 404, 409, 500 |
| `POST` | `/api/v1/planning/replenishment/orders/{id_orden}/reject` | Rechaza una orden PENDIENTE | JWT · admin, buyer, planner, store_manager |  | 200, 401, 403, 404, 409, 500 |
| `GET` | `/api/v1/planning/sku/{sku_id}/full-context` | Contexto híbrido PostgreSQL + MongoDB de un SKU | JWT · cualquier usuario autenticado |  | 200, 400, 401, 404, 500 |
| `GET` | `/health` | Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis). | Pública |  | 200, 500 |

<details><summary><code>POST /api/v1/planning/forecast/run</code> — ejemplo de cuerpo</summary>

```json
{
  "metodo": "SUAVIZACION_EXPONENCIAL",
  "horizonte": 7,
  "ventana": 28,
  "alpha": 0.3,
  "dias_historia": 120,
  "id_locacion": 2
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<forecast_request><metodo>SUAVIZACION_EXPONENCIAL</metodo><horizonte>7</horizonte><ventana>28</ventana><alpha>0.3</alpha><dias_historia>120</dias_historia><id_locacion>2</id_locacion></forecast_request>
```

</details>

<details><summary><code>POST /api/v1/planning/replenishment/generate</code> — ejemplo de cuerpo</summary>

```json
{
  "horizonte": 7
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<replenishment_request><horizonte>7</horizonte></replenishment_request>
```

</details>

<details><summary><code>POST /api/v1/planning/replenishment/orders/{id_orden}/approve</code> — ejemplo de cuerpo</summary>

```json
{
  "cantidad": 48
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<aprobacion_request><cantidad>48</cantidad></aprobacion_request>
```

</details>

## svc-alerts — puerto 5007

_Pre-Shrinkage Alerts & ESG Service (FreshTrack)_

Swagger UI: `http://localhost:5007/api/v1/docs`

| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |
|---|---|---|---|---|---|
| `PATCH` | `/api/v1/alerts/{id_mongo}/resolve` | Marca una alerta como atendida | JWT · admin, store_manager, warehouse |  | 200, 401, 403, 404, 500 |
| `GET` | `/api/v1/alerts/active` | Alertas abiertas (MongoDB) | JWT · cualquier usuario autenticado |  | 200, 400, 401, 500 |
| `GET` | `/api/v1/alerts/analytics/kpis` | Alertas por locación y criticidad (pipeline de agregación) | JWT · cualquier usuario autenticado |  | 200, 401, 500 |
| `GET` | `/api/v1/alerts/esg/carbon-avoided` | Reporte ESG: alimento rescatado y CO2e evitado | JWT · cualquier usuario autenticado |  | 200, 401, 500 |
| `POST` | `/api/v1/alerts/scan` | Escanea lotes por vencer y emite alertas | JWT · admin, store_manager, warehouse |  | 200, 400, 401, 403, 500 |
| `GET` | `/api/v1/contracts/{nombre_xsd}.xsd` | Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request). | Pública |  | 200, 404, 500 |
| `GET` | `/health` | Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis). | Pública |  | 200, 500 |

## svc-audit — puerto 5008

_Immutable Audit & Compliance Service (FreshTrack)_

Swagger UI: `http://localhost:5008/api/v1/docs`

| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |
|---|---|---|---|---|---|
| `GET` | `/api/v1/audit/events` | Bitácora de auditoría (filtros y paginación) | JWT · admin, auditor |  | 200, 400, 401, 403, 500 |
| `POST` | `/api/v1/audit/log` | Registro explícito de un evento de cumplimiento | JWT · cualquier usuario autenticado | JSON/XML + XSD | 201, 400, 401, 500 |
| `GET` | `/api/v1/audit/stream/recent` | Últimos eventos de dominio en Redis Streams | JWT · admin, auditor |  | 200, 400, 401, 403, 500 |
| `GET` | `/api/v1/audit/traceability/{id_lote}` | Trazabilidad completa de un lote (kardex) | JWT · admin, auditor, warehouse |  | 200, 401, 403, 404, 500 |
| `GET` | `/api/v1/contracts/{nombre_xsd}.xsd` | Descarga un contrato XSD de integración (p. ej. asn_request, checkout_request). | Pública |  | 200, 404, 500 |
| `GET` | `/health` | Estado del microservicio y de sus dependencias (PostgreSQL, MongoDB, Redis). | Pública |  | 200, 500 |

<details><summary><code>POST /api/v1/audit/log</code> — ejemplo de cuerpo</summary>

```json
{
  "accion": "REVISION_CUMPLIMIENTO",
  "tabla": "sistema",
  "descripcion": "Revisión mensual de mermas"
}
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<audit_log_request><accion>REVISION_CUMPLIMIENTO</accion><tabla>sistema</tabla><descripcion>Revisión mensual de mermas</descripcion></audit_log_request>
```

</details>

