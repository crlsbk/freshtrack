# Guía Maestra de Demostración: Operación Real del Planeador de Demanda

**FreshTrack — Gestión Inteligente de Inventario Perecedero (FEFO, Pronóstico y Merma)**  
**Rol del Presentador / Usuario**: Carlos Vega — *Planeador de Demanda* (`planner@freshtrack.mx`)

Esta guía técnica está diseñada para realizar una demostración en vivo, paso a paso, de la operación de FreshTrack desde la perspectiva del **Planeador de Demanda**. Cada paso especifica con exactitud **qué mostrar en el navegador (Web UI y Swagger)**, **qué comandos ejecutar en la terminal (cURL JSON/XML)**, y **qué consultar en las bases de datos (PostgreSQL, MongoDB y Redis)** para comprobar la persistencia políglota y la arquitectura de microservicios contenerizada con Docker.

---

## Ficha de Credenciales y Accesos

| Elemento | Detalle |
|---|---|
| **Usuario Web / API** | `planner@freshtrack.mx` |
| **Contraseña** | `Plan2026!` |
| **Rol en Sistema** | `planner` (`id_rol: 3`, Planeador de Demanda) |
| **URL del Sitio Web (UI)** | `http://127.0.0.1:5000` |
| **Swagger UI Microservicios** | • `svc-auth` (5001): `http://127.0.0.1:5001/api/v1/docs`<br>• `svc-catalog` (5002): `http://127.0.0.1:5002/api/v1/docs`<br>• `svc-inventory` (5003): `http://127.0.0.1:5003/api/v1/docs`<br>• `svc-commercial` (5004): `http://127.0.0.1:5004/api/v1/docs`<br>• `svc-asn` (5005): `http://127.0.0.1:5005/api/v1/docs`<br>• `svc-planning` (5006): `http://127.0.0.1:5006/api/v1/docs`<br>• `svc-alerts` (5007): `http://127.0.0.1:5007/api/v1/docs`<br>• `svc-audit` (5008): `http://127.0.0.1:5008/api/v1/docs` |

### Antes de empezar

Los comandos de Redis y MongoDB usan las contraseñas del `.env`. Cárgalas en la terminal una vez:

```bash
set -a; source .env; set +a
```

Para comprobar todo el flujo de esta guía de un jalón (JSON/XML, JWT, Redis, 401/403 y logout) sin `jq`:

```bash
make check-planeador                 # resumen de comprobaciones
make check-planeador CHECK_ARGS=-v   # además imprime los cuerpos JSON y XML
```

---

## Paso 1: Topología Docker y Salud de la Red de Microservicios

### 1.1 Qué mostrar en la Terminal
Ejecuta el siguiente comando para evidenciar que todos los contenedores están aislados en su propia red Docker y con puertos mapeados:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Salida que se debe señalar a la audiencia**:
- **3 Motores de Datos**: `freshtrack_db` (Postgres 5432), `freshtrack_redis` (Redis 6379), `freshtrack_mongo` (Mongo 27017).
- **Microservicios Flask**: Los 8 microservicios (`freshtrack_svc_auth`, `freshtrack_svc_planning`, etc.) en puertos `5001` a `5008`.

### 1.2 Demostración de Healthcheck (JSON vs XML)
Muestra cómo los microservicios negocian contenido nativamente desde el endpoint de infraestructura `/health`:

**Petición JSON**:
```bash
curl -s -X GET http://127.0.0.1:5006/health -H "Accept: application/json" | jq .
```
> **Observar**: `status: "HEALTHY"` y las 3 dependencias activas: `"postgres": true`, `"mongo": true`, `"redis": true`.

**Petición XML**:
```bash
curl -s -X GET http://127.0.0.1:5006/health -H "Accept: application/xml"
```
> **Observar**: Respuesta estructurada `<service_health><dependencies><mongo>true</mongo><postgres>true</postgres><redis>true</redis></dependencies><service>svc-planning</service><status>HEALTHY</status></service_health>`.

---

## Paso 2: Autenticación del Planeador, JWT, RBAC y Redis

### 2.1 Qué mostrar en el Navegador (Web UI)
1. Abrir `http://127.0.0.1:5000/login`.
2. Ingresar:
   - **Correo**: `planner@freshtrack.mx`
   - **Contraseña**: `Plan2026!`
3. **Punto clave a explicar**:
   - En la esquina superior derecha aparece **Carlos Vega** con el badge `Planeador de Demanda`.
   - En el menú lateral (Sidebar), el sistema aplica **control de acceso basado en roles (RBAC)**: el planeador tiene acceso a *Pronóstico*, *Reabastecimiento*, *Transferencias*, *Desperdicio evitado*, *Alertas* y *Explorador Mongo*, pero **no** tiene acceso a cobro en caja POS ni a administración general.
   - Demostrar el interruptor de tema en la barra superior (Modo Claro / Modo Oscuro) y el colapso del menú lateral con `#sidebar-logo-btn`.

### 2.2 Qué mostrar en la Terminal (Microservicio `svc-auth` en puerto 5001)

#### Login en JSON:
```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"email":"planner@freshtrack.mx","password":"Plan2026!"}' | jq -r .token)

echo "Token JWT emitido: ${TOKEN:0:45}..."
```

#### Login en XML (Validado con contrato XSD `login_request.xsd`):
```bash
curl -s -X POST http://127.0.0.1:5001/api/v1/auth/login \
  -H "Content-Type: application/xml" \
  -H "Accept: application/xml" \
  -d '<login_request><email>planner@freshtrack.mx</email><password>Plan2026!</password></login_request>'
```
> **Observar**: El microservicio responde con `<auth_response><token>...</token><token_type>Bearer</token_type><usuario><rol>planner</rol></usuario></auth_response>`.

#### Inspección de la Sesión en Redis:
```bash
docker exec freshtrack_redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning keys "session:*"
```
> **Observar**: Se crea una clave `session:<jti>` con tiempo de vida (TTL) alineado a la vigencia del JWT.

#### Demostración de RBAC (Separación de Funciones):
El planeador intenta listar los usuarios del sistema (facultad exclusiva del Administrador):
```bash
curl -s -X GET http://127.0.0.1:5001/api/v1/auth/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" | jq .
```
> **Observar**: Código HTTP **403 Forbidden** con error `"acceso_denegado"` y la lista `roles_permitidos: ["admin"]`, demostrando que RBAC protege la segregación de funciones. Con `-H "Accept: application/xml"` el mismo rechazo llega en XML.
>
> Nota: aprobar o rechazar órdenes de reabastecimiento **sí** está permitido al planeador (además de `buyer` y `store_manager`), así que no sirve para demostrar el 403.

---

## Paso 3: Motor de Pronóstico — Swagger UI y Persistencia Políglota

### 3.1 Qué mostrar en Swagger UI (Documentación Interactiva)
1. Abrir en el navegador: `http://127.0.0.1:5006/api/v1/docs` (Swagger UI de `svc-planning`).
2. En la parte superior derecha, hacer clic en el botón verde **Authorize**.
3. En el campo `Value`, escribir `Bearer <tu_token>` (o copiar el valor de `$TOKEN` de la terminal) y dar clic en **Authorize** y luego **Close**.
4. Desplegar el endpoint `POST /api/v1/planning/forecast/run`.
5. Hacer clic en **Try it out**, configurar el cuerpo JSON:
   ```json
   {
     "metodo": "SUAVIZACION_EXPONENCIAL",
     "horizonte": 7,
     "ventana": 28,
     "alpha": 0.3,
     "id_locacion": 3
   }
   ```
6. Hacer clic en **Execute** y observar la respuesta HTTP 201 en vivo con el linaje de la corrida (`id_run`) y las métricas de precisión.

### 3.2 Qué mostrar en la Terminal (cURL JSON vs XML)

**Ejecución en JSON**:
```bash
curl -s -X POST http://127.0.0.1:5006/api/v1/planning/forecast/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"metodo":"SUAVIZACION_EXPONENCIAL","horizonte":7,"ventana":28,"alpha":0.30,"id_locacion":3}' \
  | jq '{id_run, metodo, horizonte, series, mae, rmse, wmape, duracion_ms}'
```

**Ejecución en XML**:
```bash
curl -s -X POST http://127.0.0.1:5006/api/v1/planning/forecast/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/xml" \
  -d '{"metodo":"SUAVIZACION_EXPONENCIAL","horizonte":7,"ventana":28,"alpha":0.30,"id_locacion":3}'
```
> **Observar**: `<forecast_run_result><horizonte>7</horizonte><mae>...</mae><metodo>SUAVIZACION_EXPONENCIAL</metodo><series>12</series></forecast_run_result>`.

### 3.3 Demostración de la Persistencia Políglota en Vivo

#### 1. PostgreSQL (Fuente Única de la Verdad — Serie Relacional):
```bash
docker exec freshtrack_db psql -U app_backend -d retail_perecederos -c \
  "SELECT id_run, metodo, horizonte_dias, n_series, mae, rmse, wmape, duracion_ms, fecha_ejecucion FROM analitica.forecast_run ORDER BY fecha_ejecucion DESC LIMIT 1;"
```
> **Explicación**: PostgreSQL mantiene el registro legal e inmutable de la corrida analítica con su usuario y parámetros.

#### 2. MongoDB (Proyecciones de Alta Velocidad y Series Temporales No Estructuradas):
```bash
docker exec freshtrack_mongo mongosh -u "$MONGO_USER" -p "$MONGO_PASSWORD" --authenticationDatabase admin retail_perecederos --eval \
  'db.pronosticos_demanda.find().sort({fecha_ejecucion:-1}).limit(1)'
```
> **Explicación**: MongoDB almacena el documento BSON enriquecido con la serie completa de predicción día a día, intervalos de confianza y percentiles **P10** (escenario pesimista), **P50** (demanda esperada) y **P90** (pico estacional), enlazado mediante `id_sku` e `id_locacion` relacionales.

#### 3. Redis Streams (Event-Driven Broker):
```bash
docker exec freshtrack_redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning xrevrange freshtrack:events + - COUNT 1
```
> **Explicación**: Se observa el evento streaming `PRONOSTICO_CALCULADO` con su `correlation_id`, `user_id` (UUID de Carlos Vega), `user_role` (`planner`) y payload analítico emitido al bus distribuido.

### 3.4 Qué mostrar en la Web UI
1. Navegar a `http://127.0.0.1:5000/pronostico`.
   - Mostrar la gráfica de ventas reales vs pronóstico a 7 días.
   - Pasar el cursor sobre los tooltips explicativos `?`:
     - **MAE**: Error absoluto medio (desviación promedio en unidades).
     - **RMSE**: Raíz del error cuadrático medio (penaliza desviaciones atípicas grandes).
     - **WMAPE**: Error porcentual ponderado por el volumen de venta (ya viene en %: `12.5` = 12.5 %).
     - **Alpha (α)**: Factor de amortiguación (0.30 pondera 70% historia y 30% tendencia reciente).
2. Navegar a `http://127.0.0.1:5000/mongo`.
   - Mostrar la colección `pronosticos_demanda` en el explorador interactivo integrado, demostrando cómo la interfaz web consulta en vivo la base de datos documental.

---

## Paso 4: Reabastecimiento Inteligente & Variables Operativas

### 4.1 Qué mostrar en la Terminal (Microservicio `svc-planning`)

#### Generación de Recomendaciones en JSON:
```bash
curl -s -X POST http://127.0.0.1:5006/api/v1/planning/replenishment/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"horizonte": 7}' | jq .
```

#### Consulta de Órdenes Pendientes en XML:
```bash
curl -s -X GET "http://127.0.0.1:5006/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=2" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/xml"
```
> **Observar**: Se recibe el nodo `<replenishment_orders>` conteniendo `<explicacion>` detallada de la necesidad neta, riesgo de quiebre e inventario útil.

### 4.2 Qué mostrar en el Navegador (Web UI)
1. Ir a `http://127.0.0.1:5000/reabastecimiento`.
2. Señalar a la audiencia las tarjetas de recomendación calculadas y hacer clic en los tooltips `?`:
   - **Demanda pronosticada**: Volumen proyectado en la ventana temporal (7 días).
   - **Inventario físico vs útil**: Existencias reales descontando mermas o lotes por vencer.
   - **Stock de seguridad**: Margen para amortiguar desviaciones en la entrega o demanda.
   - **Entradas confirmadas**: Pedidos a proveedores en tránsito que llegarán antes de la fecha límite.
   - **Lead Time**: Tiempo en días que tarda el proveedor en entregar en tienda.
   - **MOQ (Minimum Order Quantity)**: Tamaño mínimo de lote o empaque exigido por el proveedor.
3. Mostrar la **Explicación en lenguaje natural** generada automáticamente para justificar la orden ante compras o auditoría.

---

## Paso 5: Alertas de Pre-Merma, Transferencias y Reporte ESG (CO2e)

### 5.1 Qué mostrar en la Terminal (Microservicio `svc-alerts` en puerto 5007)

#### Reporte de Sostenibilidad ESG (CO2e y Alimento Rescatado):
```bash
curl -s -X GET http://127.0.0.1:5007/api/v1/alerts/esg/carbon-avoided \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" | jq .
```
> **Observar**: Métricas de `alimento_recuperado_kg`, `ahorro_financiero_mxn` y `co2e_evitado_kg` basadas en el factor oficial de `2.5 kg CO2e / kg perecedero`.

#### En formato XML:
```bash
curl -s -X GET http://127.0.0.1:5007/api/v1/alerts/esg/carbon-avoided \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/xml"
```

#### Verificación del Índice TTL en MongoDB:
```bash
docker exec freshtrack_mongo mongosh -u "$MONGO_USER" -p "$MONGO_PASSWORD" --authenticationDatabase admin retail_perecederos --eval \
  'db.alertas_operativas.getIndexes()'
```
> **Explicación**: Señalar el índice `{ expireAfterSeconds: 15552000 }` (180 días). MongoDB purga automáticamente las alertas viejas sin necesidad de tareas cron de mantenimiento.

### 5.2 Qué mostrar en la Web UI
1. Ir a `http://127.0.0.1:5000/transferencias`:
   - Mostrar la matriz de redistribución: cómo el sistema detecta lotes con riesgo de caducidad en tiendas de baja rotación y sugiere moverlos a tiendas con alta velocidad de venta.
2. Ir a `http://127.0.0.1:5000/desperdicio-evitado`:
   - Mostrar el impacto consolidado: dinero recuperado, kilogramos rescatados de merma e impacto ambiental positivo en reducción de huella de carbono.

---

## Paso 6: Cierre de Sesión y Revocación Instantánea (Redis Denylist)

### 6.1 Qué mostrar en la Terminal y Redis

#### 1. Ejecutar Logout en `svc-auth` (5001):
```bash
LOGOUT_RESP=$(curl -s -X POST http://127.0.0.1:5001/api/v1/auth/logout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json")

echo $LOGOUT_RESP | jq .
```
> **Observar**: `"status": "LOGOUT_EXITOSO"` con el identificador único de token (`jti`).

#### 2. Comprobar la Denylist en Redis (< 0.2 ms):
```bash
docker exec freshtrack_redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning keys "jwt:denylist:*"
```
> **Observar**: La clave `jwt:denylist:<jti>` fue creada atómicamente con un TTL exacto a los segundos restantes de vida del token.

#### 3. Probar el Rechazo Inmediato (401 Unauthorized):
Intentar consultar cualquier microservicio con el token recién revocado:
```bash
curl -s -X GET http://127.0.0.1:5001/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" | jq .
```
> **Observar**: Respuesta HTTP **401 Unauthorized** con error `"token_revocado"`. Esto demuestra que la revocación es instantánea en toda la red de microservicios sin esperar la expiración pasiva del JWT.

---

## Resumen Ejecutivo para la Presentación

| Dimensión Demostrada | Evidencia Concreta |
|---|---|
| **Rol Evaluado** | `planner@freshtrack.mx` (Carlos Vega), RBAC estricto en UI y microservicios. |
| **Contenerización Docker** | 11 contenedores activos en red aislada; mapeo de puertos 5001-5008, 5432, 6379, 27017. |
| **Dualidad JSON / XML** | Cabeceras RFC `Accept` y `Content-Type` funcionales en autenticación, pronósticos, órdenes y alertas. |
| **Contratos XSD y Swagger** | OpenAPI 3.0 en `/api/v1/docs`, descarga de XSD en `/api/v1/contracts/*.xsd` y autorización Bearer interactiva. |
| **PostgreSQL (Single Source of Truth)**| Registro relacional e inmutable en esquemas `operacion`, `analitica` y `auditoria`. |
| **MongoDB 7 (Persistencia Documental)**| Serie de pronósticos con percentiles P10/P50/P90 en `pronosticos_demanda` e índice TTL en `alertas_operativas`. |
| **Redis 7 (Memoria y Reactividad)** | Denylist distribuida (`jwt:denylist:*`), sesiones activas y stream de eventos (`freshtrack:events`). |
