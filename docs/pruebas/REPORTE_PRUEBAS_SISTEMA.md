# Reporte de pruebas de sistema — FreshTrack

**Equipo 05 · Proyecto 12 · Entrega final (24 de noviembre de 2026)**

## 1. Objetivo

Comprobar, con todos los componentes reales en ejecución (web, 8 microservicios, PostgreSQL, MongoDB, Redis y bucket de archivos), que los flujos de negocio de FreshTrack funcionan de punta a punta como un solo sistema. Ningún componente se simula: cada caso envía peticiones HTTP reales a los puertos publicados por `docker compose` y verifica la respuesta y su efecto en los datos (existencias, cola FEFO, indicadores).

## 2. Entorno

| Elemento | Valor |
|---|---|
| Fecha | 2026-11-24, 13:17–13:21 CST (corrida final 13:20–13:21) |
| Código | rama `avance2-postgresql-real`, commit `1926a17` (imágenes construidas 12:57 CST) |
| Orquestación | Docker 29.9.2, Docker Compose v5.6.1, `docker-compose.yml` local |
| Web | `freshtrack/web:latest` — Flask en :5000 (Python 3.13) |
| Microservicios | `freshtrack/svc-*:latest` — puertos 5001–5008 |
| PostgreSQL | `postgres:17-alpine` (17.11) |
| MongoDB | `mongo:7` (7.0.45) |
| Redis | `redis:7-alpine` (7.4.11), AOF + contraseña |
| Archivos | almacenamiento compatible S3 en :9000 |
| Correo | `axllent/mailpit:v1.27` |
| Cliente de pruebas | Python 3.14 (`.venv`), `requests` 2.34; parser CSV de la app de escritorio |
| Credenciales | Se leen en tiempo de ejecución del dict `CUENTAS` de `scripts/smoke_rutas.py`; no aparecen en este reporte y los JWT se ocultan en las bitácoras. |

## 3. Cómo reproducir

```bash
docker compose up -d --wait
.venv/bin/python docs/pruebas/scripts/pruebas_sistema.py
.venv/bin/python scripts/smoke_http.py
.venv/bin/python scripts/smoke_rutas.py
.venv/bin/python scripts/generar_evidencias.py --salida docs/pruebas/sistema/EVIDENCIAS_REQUEST_RESPONSE.md
```

Evidencia en `docs/pruebas/sistema/`:
- `salida_pruebas_sistema.txt`: cada petición con código, X-Correlation-Id, tiempo y extracto del cuerpo.
- `resultados_pruebas_sistema.json`: un registro por caso.
- Salidas de los scripts existentes y `EVIDENCIAS_REQUEST_RESPONSE.md`.

## 4. Casos de prueba

Datos base: tienda 3 (San Pedro, sucursal del gerente y del almacenista), tienda 4 (Cumbres) como destino, proveedor 1 (Lácteos del Norte), SKU 9 (Crema Ácida 450 g).

| ID | Flujo | Precondiciones | Pasos | Resultado esperado | Resultado obtenido | Estado | Evidencia |
|---|---|---|---|---|---|---|---|
| PS-01 | Salud de la plataforma | Stack arriba | GET /health web + 8 servicios | 9 × 200 HEALTHY | 9/9 HEALTHY | **PASA** | salida § PS-01 |
| PS-02 | Login por rol | Cuentas del seed | POST /api/v1/auth/login con 7 roles | 200 + JWT + rol correcto | 7/7 | **PASA** | § PS-02 |
| PS-03 | Login inválido y RBAC | Tokens de PS-02 | Contraseña errónea; buyer a /audit/events; auditor a /audit/events; sin token | 401; 403; 200; 401 | 401 · 403 acceso_denegado · 200 · 401 | **PASA** | § PS-03 |
| PS-04 | Logout invalida el token en todos los servicios | Sesión nueva del planner | Usar token → POST /auth/logout → reusar en inventory, planning y audit | 401 token_revocado ×3 | 200/200 → 200 → 401 token_revocado ×3 | **PASA** | § PS-04 |
| PS-05 | Cierre forzado (admin) y logout web | admin, planner, gerente | DELETE /auth/sessions/{planner} y usar su token; web: login con CSRF → gateway /svc/inventory → logout → reintento | 401; el gateway deja de dar datos | API 200 → 200 → 401; web: gateway 200 → logout 302 → 302 a /login | **PASA** | § PS-05 |
| PS-06 | OC con PDF en el bucket | buyer | POST /planning/purchase-orders; GET …/pdf | 201; PDF descargable | OC-20261124-0005 201; PDF 200 application/pdf (4 916 B) | **PASA** | § PS-06 |
| PS-07 | ASN desde la OC con QR firmado | OC de PS-06 | POST /asn/from-purchase-order; GET /asn/labels?codigo=…; GET labels-pdf | 201 EN_TRANSITO; firma_valida=true; PDF | ASN-20261124-0005 201; firma_valida=True; PDF 200 (19 236 B) | **PASA** | § PS-07 |
| PS-08 | Recepción QR → lote en FEFO (idempotente) | Etiqueta de PS-07 | receive-scan con Idempotency-Key; repetir con la misma clave; repetir sin clave; fefo-queue | 201; mismo lote (idempotente); 409; lote en FEFO | 201 → 200 idempotente → 409 etiqueta_ya_recibida; lote en la cola | **PASA** | § PS-08 |
| PS-09 | Venta POS (Saga) con FEFO | Existencias SKU 9 | cola FEFO → checkout de 2 pzas → cola FEFO | 201 COMPLETADA; descuenta el lote que caduca primero | 201 VT-3-…-000025; primer lote 73 → 71 | **PASA** | § PS-09 |
| PS-10 | Merma con foto de evidencia | Gerente | POST /evidence → POST /shrinkage con id_evidencia → GET /evidence/{id}/url → descarga | 201, 201 ligada, URL firmada válida | 201 · 201 ligada · 200 · descarga firmada 200 image/jpeg · sin firma 403 | **PASA** | § PS-10 |
| PS-10b | URL firmada usable fuera de Docker | URL de PS-10 | GET a la URL tal cual | 200 | Apunta a http://minio:9000, no alcanzable desde el host | **FALLA** | § PS-10b, D-01 |
| PS-11 | Conteo cíclico con reintento idempotente | Lote de PS-08 | POST /inventory/counts con clave (contado = disponible − 1) ×2 | Mismo id_conteo, un solo ajuste | 201 → 200 mismo id; 49 → 48 | **PASA** | § PS-11 |
| PS-12 | Transferencia → aprobación → ejecución → desperdicio evitado | Lote en tienda 3 | Solicitud del gerente → aprobación del planner → ejecución del almacenista → venta en tienda 4 → waste-measurement | Estados correctos; sube producto_recuperado | SUGERIDA → APROBADA → EJECUTADA; recuperado 35 → 45 u (visible a los 10 s) | **PASA** | § PS-12, O-01 |
| PS-13 | Descuento: sugerir → aprobar | Lotes por caducar | generate {dias_hasta:5} → listar → aprobar | 201; 200 APROBADO | 201 (27 sugeridos) → 200 APROBADO | **PASA** | § PS-13 |
| PS-14 | Pronóstico y reabastecimiento | Historial de ventas | forecast/run → forecast/latest/9/3 → replenishment/generate → orders | 201 · 200 · 201 · 200 | 201 (158 ms) · 200 · 201 · 200 | **PASA** | § PS-14 |
| PS-15 | Escaneo de alertas | Lotes por vencer | POST /alerts/scan → GET /alerts/active | 200 | 200 · 200 | **PASA** | § PS-15 |
| PS-16 | Importación de ventas idempotente (XML, JSON, CSV) | buyer | XML con 2 folios ×2; JSON; CSV con fila buena y mala (parser de escritorio → XML) | 2 importados; luego 2 duplicados; 1; 1 y la mala rechazada | Exacto | **PASA** | § PS-16 |
| PS-17 | Negociación XML y XSD | Tokens | stock con Accept XML; import con XML inválido; checkout XML inválido pidiendo XML | 200 XML; 400 xml_no_cumple_contrato; error en XML | Exacto | **PASA** | § PS-17 |
| PS-18 | Swagger/OpenAPI | Servicios arriba | /api/v1/docs y /openapi.json en 5001–5008 | 200 | 8/8 | **PASA** | § PS-18 |
| PS-19 | Panel /ops/status | Credenciales MONITOR_* | Sin sesión; snapshot sin y con Basic Auth | 302; 401; 200 OPERATIVO | 302 · 401 · 200 OPERATIVO 8/8 (100 %) | **PASA** | § PS-19 |
| PS-20 | Login web por rol | Seed | Formulario con CSRF + pantalla inicial | 302 + 200 | 7/7 | **PASA** | § PS-20 |
| PS-21 | Todas las pantallas por rol | Web :5000 | GET de cada vista de VISTAS_POR_ROL | 200 | 65/65 | **PASA** | § PS-21 |

**Resultado: 21 de 22 casos PASAN.** El que falla (PS-10b) es de configuración del endpoint público del bucket.

## 5. Scripts que ya existían en el repositorio

| Script | Resultado | Lectura |
|---|---|---|
| scripts/smoke_http.py | 14/15 pasos OK; el paso web da 400 | Envía el login web sin token CSRF. Está desactualizado; con CSRF el flujo pasa (PS-05, PS-20). |
| scripts/smoke_rutas.py | Los 7 logins dan 400 | Misma causa. Su equivalente con CSRF (PS-21) da 65/65. |
| scripts/generar_evidencias.py | 83/88 | 5 casos de catálogo dan 403 porque el buyer ya no puede dar altas; al fallar el alta, da de baja el SKU 1 (se restauró a activo=true). |

## 6. Defectos y observaciones

| ID | Severidad | Descripción | Evidencia |
|---|---|---|---|
| D-01 | Media | La URL firmada de evidencias usa http://minio:9000 porque OBJECT_STORAGE_PUBLIC_ENDPOINT no está en docker-compose.yml. La firma es válida, pero las apps no pueden abrir la foto en local. En GCP firma contra storage.googleapis.com. | PS-10b |
| D-02 | Alta | El límite real de foto es 4 MB (`MAX_CONTENT_LENGTH` global en `app/config.py`), no los 8 MB documentados; el 413 sale en inglés. | fallas/archivos.txt |
| D-03 | Baja | generar_evidencias.py está desactualizado y da de baja el SKU 1. | §5 |
| D-04 | Baja | smoke_http.py y smoke_rutas.py no envían el token CSRF. | §5 |
| O-01 | Observación | producto_recuperado tarda de 60 a 120 s en reflejarse (dos cachés de 60 s anidadas). | PS-12 |

## 7. Conclusión

Con el stack completo arriba, los flujos de punta a punta funcionan:
- autenticación y revocación distribuida;
- compra → ASN → recepción QR → FEFO → venta;
- mermas con evidencia;
- recepción y conteos idempotentes;
- transferencias con medición de desperdicio evitado;
- descuentos, pronóstico y reabastecimiento;
- alertas e importación idempotente (XML, JSON y CSV);
- contratos XSD, Swagger y monitoreo.

Quedan pendientes D-01, D-02 y actualizar los scripts de humo y de evidencias.
