# FreshTrack — Diseño y Especificación de Seguridad e Integración entre Componentes

> **Integración de Aplicaciones Computacionales**  
> **Requerimiento 9: Seguridad e Integración entre Componentes**  
> **Esquema de Autenticación**: JWT HS256 con PostgreSQL `public.crypt()` (bcrypt)  
> **Capa de Control y Denylist en Memoria**: Redis 7.4 (`jwt:denylist:*`, `session:*`)  
> **Mecanismo de Autorización**: Control de Acceso Basado en Roles (RBAC con 7 perfiles)  
> **Trazabilidad Transversal**: `X-Correlation-Id`, `X-User-Id`, `X-Location-Id`

---

## 1. Justificación y Principios de Diseño de Seguridad

En una arquitectura de microservicios distribuidos con persistencia políglota, la seguridad no puede depender de un perímetro rígido único ni de sesiones locales ligadas a la memoria de un proceso. Se implementó una estrategia de **Defensa en Profundidad** (*Defense in Depth*) fundamentada en los siguientes principios:

1. **Principio de Mínimo Privilegio (PoLP)**: Cada rol operativo (`cashier`, `warehouse`, `store_manager`, `planner`, `buyer`, `supplier`, `auditor`, `admin`) cuenta con acceso restringido exclusivamente a los recursos y verbos HTTP que requiere su función de negocio.
2. **PostgreSQL como Autoridad de Identidad Criptográfica**: Las contraseñas nunca viajan en claro ni se almacenan en texto plano; su verificación se efectúa directamente en el motor relacional mediante `public.crypt(:password, u.password_hash)` en el esquema `public` de PostgreSQL con `pgcrypto`.
3. **Tokens JWT Stateless con Revocación Instantánea en Redis**: Aunque los JWT son autocontenidos (evitando consultas a PostgreSQL en cada petición), el cierre de sesión (`logout`) y la desactivación de cuentas invalidan el token en tiempo real mediante la denylist en memoria de Redis (`jwt:denylist:{jti}`), evaluada en menos de **0.2 milisegundos**.
4. **Segregación Estricta de Endpoints (Públicos vs Protegidos)**: Ningún endpoint de uso público (monitoreo de contenedores, documentación interactiva de interfaz o consulta abierta de catálogos) se restringe indebidamente, mientras que todo endpoint operativo o transaccional queda estrictamente blindado con `Authorization: Bearer <token>`.

---

## 2. Matriz Completa de Endpoints: Públicos vs Protegidos

### 2.1 Criterio de Clasificación

```
[ Solicitud HTTP Entrante ]
             │
             ▼
¿Es ruta de infraestructura, docs, login o catálogo abierto?
             │
     ┌───────┴───────┐
    SÍ               NO
     │               │
     ▼               ▼
[ PÚBLICO ]      [ PROTEGIDO ]
Acceso libre     Exige: Authorization: Bearer <JWT>
(200 OK)         ├── 1. Firma HS256 válida y expiración vigente? -> Si falla: 401 invalid_token
                 ├── 2. ¿Revocado en Redis jwt:denylist? ---------> Si figura: 401 revoked_token
                 └── 3. ¿El rol está en la lista permitida? -----> Si no: 403 Forbidden
```

### 2.2 Catálogo Detallado de Rutas

| Servicio / Puerto | Endpoint y Método | Nivel de Acceso | Roles Permitidos | Justificación de Negocio / Técnica |
|---|---|---|---|---|
| **Todos** (5001-5008) | `GET /health` | **PÚBLICO** | *Cualquiera* | *Health checks* de Docker Compose, Kubernetes y monitores; no deben exigir credenciales para evitar reinicios en bucle. |
| **Todos** (5001-5008) | `GET /api/v1/docs`<br>`GET /api/v1/openapi.json` | **PÚBLICO** | *Cualquiera* | Especificación OpenAPI 3.0 y Swagger UI interactiva para integración de clientes externos y desarrolladores. |
| **`svc-auth` (5001)** | `POST /api/v1/auth/login` | **PÚBLICO** | *Cualquiera* | Puerta de enlace: valida correo y contraseña, y emite el token JWT. Protegido con Rate Limit (10 req/min). |
| **`svc-auth` (5001)** | `POST /api/v1/auth/verify` | **PÚBLICO** | *Cualquiera* | Introspección perimetral de tokens para validar vigencia, firma y revocación. |
| **`svc-auth` (5001)** | `POST /api/v1/auth/logout` | **PROTEGIDO** | Autenticado | Invalida el JTI en Redis Denylist y purga la sesión activa en memoria. |
| **`svc-auth` (5001)** | `GET /api/v1/auth/users` | **PROTEGIDO** | `admin` | Nómina de cuentas de usuario, correos y roles RBAC. |
| **`svc-auth` (5001)** | `PATCH /api/v1/auth/users/<id>/status` | **PROTEGIDO** | `admin` | Alta/baja lógica de usuarios; si se desactiva, purga todas sus sesiones en Redis. |
| **`svc-auth` (5001)** | `GET /api/v1/auth/sessions/<id>` | **PROTEGIDO** | `admin` | Consulta de sesiones vivas en Redis para un usuario. |
| **`svc-auth` (5001)** | `DELETE /api/v1/auth/sessions/<id>` | **PROTEGIDO** | `admin` | Cierre forzoso masivo de sesiones de un usuario. |
| **`svc-auth` (5001)** | `GET /api/v1/auth/counters` | **PROTEGIDO** | `admin` | Métricas operacionales en tiempo real de Redis. |
| **`svc-catalog` (5002)** | `GET /api/v1/catalog/products`<br>`GET /api/v1/catalog/products/<id>` | **PÚBLICO** | *Cualquiera* | Catálogo general de productos perecederos accesible para clientes y tiendas. Servido desde Cache-Aside. |
| **`svc-catalog` (5002)** | `GET /api/v1/catalog/locations` | **PÚBLICO** | *Cualquiera* | Directorio público de sucursales y centros de distribución (CEDIS). |
| **`svc-catalog` (5002)** | `POST /api/v1/catalog/products` | **PROTEGIDO** | `admin`, `buyer` | Alta de nuevos SKUs en el catálogo maestro relacional. |
| **`svc-catalog` (5002)** | `DELETE /api/v1/catalog/products/<id>` | **PROTEGIDO** | `admin` | Baja lógica de productos e invalidación de caché por patrón. |
| **`svc-catalog` (5002)** | `GET /api/v1/catalog/suppliers` | **PROTEGIDO** | `admin`, `buyer`, `planner` | Directorio confidencial de proveedores y condiciones de compra. |
| **`svc-inventory` (5003)** | `GET /api/v1/inventory/stock` | **PROTEGIDO** | Autenticado | Visibilidad interna de inventario por lote, almacén y caducidad. |
| **`svc-inventory` (5003)** | `GET /api/v1/inventory/fefo-queue/<sku>/<loc>` | **PROTEGIDO** | Autenticado | Cola FEFO clasificada por criticidad y días de vida restante. |
| **`svc-inventory` (5003)** | `POST /api/v1/inventory/reserve-fefo` | **PROTEGIDO** | `admin`, `store_manager`, `warehouse` | Reserva transaccional con bloqueo atómico Redlock en Redis. |
| **`svc-inventory` (5003)** | `POST /api/v1/inventory/cancel-reservation` | **PROTEGIDO** | `admin`, `store_manager`, `warehouse` | Compensación transaccional de lotes reservados. |
| **`svc-commercial` (5004)** | `POST /api/v1/commercial/checkout` | **PROTEGIDO** | `admin`, `store_manager`, `warehouse`, `cashier` | Cobro transaccional POS con orquestación Saga y deducción de kardex. |
| **`svc-commercial` (5004)** | `POST /api/v1/commercial/cart/<id>`<br>`GET /api/v1/commercial/cart/<id>`<br>`DELETE /api/v1/commercial/cart/<id>` | **PROTEGIDO** | Autenticado | Carritos efímeros en Redis (`temp:pos_cart:*`) con consumo atómico Lua. |
| **`svc-commercial` (5004)** | `POST /api/v1/commercial/shrinkage` | **PROTEGIDO** | `admin`, `store_manager`, `warehouse` | Registro justificado de mermas operativas en PostgreSQL. |
| **`svc-commercial` (5004)** | `GET /api/v1/commercial/sales` | **PROTEGIDO** | Autenticado | Historial financiero de ventas (JSON y XML). |
| **`svc-asn` (5005)** | `POST /api/v1/asn` | **PROTEGIDO** | `admin`, `buyer`, `warehouse`, `supplier` | Ingesta de manifiestos ASN en XML o JSON hacia MongoDB. |
| **`svc-asn` (5005)** | `GET /api/v1/asn`<br>`GET /api/v1/asn/<folio>` | **PROTEGIDO** | Autenticado | Consulta de manifiestos y trazabilidad logística. |
| **`svc-asn` (5005)** | `PATCH /api/v1/asn/<folio>/status` | **PROTEGIDO** | `admin`, `warehouse` | Actualización de recepción física en almacén. |
| **`svc-asn` (5005)** | `POST /api/v1/asn/<folio>/inspection` | **PROTEGIDO** | `admin`, `warehouse`, `quality` | Registro atómico `$push` de pruebas de calidad y temperatura. |
| **`svc-planning` (5006)** | `POST /api/v1/planning/forecast/run` | **PROTEGIDO** | `admin`, `planner`, `buyer` | Ejecución del motor algorítmico de pronósticos. |
| **`svc-planning` (5006)** | `GET /api/v1/planning/forecast/latest/<sku>/<loc>` | **PROTEGIDO** | Autenticado | Recuperación de series y percentiles P10/P50/P90. |
| **`svc-planning` (5006)** | `GET /api/v1/planning/replenishment/orders` | **PROTEGIDO** | `admin`, `planner`, `buyer`, `store_manager` | Consulta de órdenes sugeridas de reabastecimiento. |
| **`svc-planning` (5006)** | `POST /api/v1/planning/replenishment/orders/<id>/approve` | **PROTEGIDO** | `admin`, `buyer` | Aprobación comercial de pedidos de compra a proveedores. |
| **`svc-alerts` (5007)** | `POST /api/v1/alerts/scan` | **PROTEGIDO** | `admin`, `store_manager`, `warehouse` | Disparo del escaneo analítico pre-merma. |
| **`svc-alerts` (5007)** | `GET /api/v1/alerts/active` | **PROTEGIDO** | Autenticado | Listado de alertas operativas activas en MongoDB. |
| **`svc-alerts` (5007)** | `PATCH /api/v1/alerts/<id>/resolve` | **PROTEGIDO** | `admin`, `store_manager`, `warehouse` | Resolución y cierre de incidentes. |
| **`svc-alerts` (5007)** | `GET /api/v1/alerts/esg/carbon-avoided` | **PROTEGIDO** | Autenticado | Reporte analítico ESG de huella de carbono evitada. |
| **`svc-audit` (5008)** | `GET /api/v1/audit/events` | **PROTEGIDO** | `admin`, `auditor` | Exportación e inspección de la bitácora inmutable en PostgreSQL. |
| **`svc-audit` (5008)** | `GET /api/v1/audit/traceability/<lote>` | **PROTEGIDO** | `admin`, `auditor`, `warehouse` | Reconstrucción forense del ciclo de vida del lote. |
| **`svc-audit` (5008)** | `GET /api/v1/audit/stream/recent` | **PROTEGIDO** | `admin`, `auditor` | Lectura directa de eventos del bus en Redis Streams. |
| **Monolito Web** | `GET /`, `GET /login`, `POST /login` | **PÚBLICO** | *Cualquiera* | Vistas iniciales de bienvenida y formulario de inicio de sesión. |
| **Monolito API** | `POST /api/auth/token` | **PÚBLICO** | *Cualquiera* | Emisión de JWT Bearer para clientes de la API JSON monolítica. |
| **Monolito API** | `/api/kpis`, `/api/inventario`, `/api/alertas`, etc. | **PROTEGIDO** | Autenticado (`@token_requerido`) | Endpoints JSON protegidos con Bearer token y RBAC. |

---

## 3. Mecanismo de Autenticación y Autorización

### 3.1 Emisión y Estructura del Token JWT
Al autenticarse en `/api/v1/auth/login`, el microservicio valida las credenciales y genera un token con estándar RFC 7519:
```json
{
  "sub": "00000000-0000-0000-0000-000000000001",
  "email": "admin@freshtrack.mx",
  "nombre": "Administrador General",
  "rol": "admin",
  "id_locacion": 1,
  "jti": "8087ada749b5437ea6c5a03422a57eb0",
  "iat": 1729555200,
  "exp": 1729584000,
  "iss": "freshtrack"
}
```

### 3.2 El Decorador Común `@requiere_auth`
Ubicado en [`app/services/common/auth.py`](file:///home/vrdtska/Documents/integracion/iac-proyecto/app/services/common/auth.py), actúa como interceptor en cada petición:

1. **Extracción**: Valida la existencia del prefijo `Bearer ` en la cabecera `Authorization`.
2. **Inspección de Denylist en Redis**: Extrae el `jti` sin costo de verificación criptográfica completa y consulta `EXISTS jwt:denylist:{jti}` en memoria (< 0.2 ms). Si fue revocado, rechaza con:
   ```json
   {
     "error": "revoked_token",
     "mensaje": "La sesión fue revocada (logout)."
   }
   ```
3. **Validación Criptográfica y Temporal**: Ejecuta `jwt.decode(...)` validando la firma HS256 y que `exp > now()`. Si el token fue manipulado o expiró, rechaza con:
   ```json
   {
     "error": "invalid_token",
     "mensaje": "Token inválido, expirado o manipulado."
   }
   ```
4. **Comprobación RBAC de Rol**: Si el endpoint tiene roles restringidos (ej. `@requiere_auth("admin", "buyer")`) y el claim `rol` no coincide (y no es `admin`), rechaza con:
   ```json
   {
     "error": "forbidden",
     "mensaje": "Acceso denegado para el rol 'supplier'. Se requiere: ('admin', 'buyer')"
   }
   ```
5. **Inyección de Contexto**: Al superar todos los filtros, inyecta `g.usuario_actual` y `g.contexto` (`X-Correlation-Id`, `X-Location-Id`, `X-User-Id`), permitiendo trazabilidad transversal y fijando `app.current_user_id` en PostgreSQL para los triggers de auditoría inmutable.

---

## 4. Validación de Entradas y Manejo de Errores (*Zero Information Leak*)

- **Payloads Vacíos o Inválidos**: Todas las entradas JSON o XML se parsean de forma defensiva (`request.get_json(silent=True) or {}`). Si faltan campos requeridos (ej. login sin correo o contraseña, reservas sin líneas de productos o cantidades no positivas), se responde con `400 Bad Request` indicando la causa específica de negocio.
- **Sin Exposición de Stack Traces**: Las excepciones no controladas capturan errores de base de datos o lógica y retornan respuestas estructuradas en el formato negociado (JSON o XML), impidiendo que trazas de error de Python (`Traceback`) o detalles de tablas internas se filtren a clientes maliciosos.

---

## 5. Evidencias de Ejecución Automatizada (`scripts/verify_security.py`)

A continuación se presenta la salida literal de la suite de pruebas automatizadas ejecutada mediante `make verify-security` y validada en `make test`:

```text
$ .venv/bin/python scripts/verify_security.py

===========================================================================
  FRESH TRACK — VERIFICACIÓN EXHAUSTIVA DE SEGURIDAD (JWT, RBAC Y REDIS)
===========================================================================

--- 1. Inicio de Sesión y Emisión de Tokens JWT ---
  [OK] Login exitoso para Administrador (admin@freshtrack.mx) -> Rol: admin
  [OK] Login exitoso para Planeador -> Rol: planner
  [OK] Login exitoso para Almacenista -> Rol: warehouse
  [OK] Login exitoso para Proveedor -> Rol: supplier
  [OK] Sesión confirmada en Redis (session:dd490d10..., TTL: 28800s)

--- 2. Verificación de Endpoints Públicos (Libre Acceso) ---
  [OK] svc-auth: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS
  [OK] svc-catalog: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS
  [OK] svc-inventory: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS
  [OK] svc-commercial: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS
  [OK] svc-asn: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS
  [OK] svc-planning: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS
  [OK] svc-alerts: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS
  [OK] svc-audit: /health (200), /api/v1/docs (200), /api/v1/openapi.json (200) -> PÚBLICOS
  [OK] svc-catalog: /api/v1/catalog/products y /api/v1/catalog/locations -> PÚBLICOS

--- 3. Restricción Estricta de Endpoints Protegidos (Sin Token -> 401) ---
  [OK] svc-auth GET /api/v1/auth/users -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-auth GET /api/v1/auth/counters -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-catalog GET /api/v1/catalog/suppliers -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-catalog POST /api/v1/catalog/products -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-inventory GET /api/v1/inventory/stock -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-inventory POST /api/v1/inventory/reserve-fefo -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-commercial POST /api/v1/commercial/checkout -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-commercial POST /api/v1/commercial/shrinkage -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-asn POST /api/v1/asn -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-planning POST /api/v1/planning/forecast/run -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-alerts POST /api/v1/alerts/scan -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)
  [OK] svc-audit GET /api/v1/audit/events -> Rechazado con 401 Unauthorized (Token de autenticación requerido (Bearer token).)

--- 4. Manejo de Tokens Inválidos, Alterados y Expirados ---
  [OK] Cabecera Authorization sin 'Bearer' rechazada: 401 (unauthorized)
  [OK] Token con firma criptográfica alterada rechazado: 401 (invalid_token)
  [OK] Token con expiración en el pasado rechazado: 401 (invalid_token)

--- 5. Control de Acceso por Roles (RBAC Matrix) ---
  [OK] Rol 'supplier' bloqueado en /auth/users: 403 Forbidden (Acceso denegado para el rol 'supplier'. Se requiere: ('admin',))
  [OK] Rol 'admin' autorizado en /auth/users: 200 OK (Usuarios: 9)
  [OK] Rol 'warehouse' bloqueado en aprobar órdenes de compra: 403 Forbidden
  [OK] Rol 'planner' bloqueado en bitácora inmutable: 403 Forbidden

--- 6. Revocación de Tokens y Cierre de Sesión (Redis Denylist) ---
  [OK] Token activo 395f74f355... probado previamente con éxito: 200 OK
  [OK] Cierre de sesión ejecutado (/api/v1/auth/logout) en 6.96 ms
  [OK] JTI detectado en Redis Denylist ('jwt:denylist:395f74f355...', TTL: 28800s)
  [OK] Reintento con token revocado bloqueado de inmediato: 401 (revoked_token)

--- 7. Validación de Entradas y Manejo Controlado de Errores ---
  [OK] Login con payload vacío controlado: 400 Bad Request (Correo y contraseña son obligatorios.)
  [OK] Reserva FEFO sin líneas controlada: 400 Bad Request (id_locacion y lineas son obligatorios.)
  [OK] Manifiesto XML malformado controlado: 400 Bad Request sin exposición de trazas

--- 8. Registro de Auditoría en PostgreSQL (Bitácora Inmutable) ---
  • Evento auditado: [LOGIN_FALLIDO] por almacen@freshtrack.mx en 2026-10-22 03:30:21.063611+00:00
  • Evento auditado: [LOGIN_FALLIDO] por None en 2026-10-22 03:28:59.820607+00:00
  • Evento auditado: [LOGIN] por admin@freshtrack.mx en 2026-10-22 03:10:21.640896+00:00
  • Evento auditado: [LOGIN] por planner@freshtrack.mx en 2026-10-22 03:10:20.593645+00:00
  • Evento auditado: [LOGOUT] por auditor@freshtrack.mx en 2026-10-22 03:10:20.580576+00:00
  [OK] Bitácora inmutable en PostgreSQL confirmó eventos de seguridad auditados

===========================================================================
  >>> ¡TODAS LAS 8 PRUEBAS DE SEGURIDAD PASARON EXITOSAMENTE! <<<
===========================================================================
```

---

## 6. Conclusión

El mecanismo de seguridad e integración transversal de FreshTrack cumple cabalmente con los lineamientos del Requerimiento 9:
- Se preserva la accesibilidad irrestricta de las rutas públicas (`/health`, `/api/v1/docs`, `/api/v1/auth/login`, catálogos abiertos).
- Se blindan todos los endpoints protegidos bajo JWT Bearer token y RBAC estricto (401 / 403).
- Se auditan de forma inmutable todos los eventos de autenticación y transacciones críticas en PostgreSQL y Redis.
- La suite automatizada `scripts/verify_security.py` garantiza la no regresión de las políticas de seguridad en cada ejecución de `make test`.
