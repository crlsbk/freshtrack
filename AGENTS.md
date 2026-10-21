# AGENTS.md

## Project

FreshTrack — perishable inventory management (FEFO, forecasting, shrinkage).
Architecture: Distributed, context-aware Flask microservices with Polyglot Persistence.
Python 3.14. PostgreSQL is the **ONLY single source of truth** for business data.
Verification is via `make test` (`smoke` + `verify-polyglot` + `demo` + `verify` scripts).

## Critical gotchas & Architecture Rules

- **PostgreSQL is the ONLY source of truth**:
  All money, inventory, catalog, and audit records live in PostgreSQL. MongoDB and Redis are auxiliary:
  - **Redis 7 (Alpine)**: Fast memory layer for JWT denylist (instant revocation on logout), distributed atomic locks (`SET NX EX` + Lua script release), and **message broker / event streaming** via Redis Streams (`freshtrack:events`).
  - **MongoDB 7**: Document projections and time-series (forecasting percentiles in `pronosticos_demanda`, advanced shipping notices in `avisos_asn`, and operational alerts with 180-day TTL in `alertas_operativas`).
- **Schema-per-service strategy**:
  All services run in their own Docker container but share the hardened PostgreSQL container `freshtrack_db`, accessing their designated schema (`operacion`, `analitica`, `auditoria`) with minimal role privileges (`app_backend`, `app_auditor`, `app_etl`).
- **Orchestrated Saga Pattern**:
  Sales and Inventory operations must follow an orchestrated saga (`app/domain/saga_venta.py`):
  1. Reserve FEFO lots with expiration checks (`operacion.existencia.cantidad_reservada`).
  2. Register sale header and lines (`operacion.venta`, `operacion.venta_detalle`).
  3. Confirm inventory deduction and kardex ledger (`operacion.movimiento_inventario`).
  - If step 2 fails, execute compensating transaction (release reservations).
  - Emits events `SAGA_VENTA_INICIADA`, `SAGA_INVENTARIO_RESERVADO`, `SAGA_VENTA_COMPLETADA`, `SAGA_VENTA_COMPENSADA` to Redis Streams.
- **Context-Awareness**:
  Every request carries context headers:
  - `X-Location-Id` (Store / CEDIS context)
  - `X-User-Id` / `X-User-Role` (RACI and permission context)
  - `X-Correlation-Id` (Traceability across logs, sagas, and event streams)
- **`pgcrypto`/`unaccent` live in the `public` schema**:
  App roles need `USAGE ON SCHEMA public` to resolve `public.crypt()`. Password verification is `public.crypt(...)` in `app/security.py`. Never revoke this USAGE without re-granting it.
- **Audit log (`auditoria.bitacora_eventos`) is immutable**:
  Database triggers block UPDATE/DELETE.
- **Microservices Framework**:
  All microservices remain in **Flask** as requested.

## Required environment variables

`SECRET_KEY`, `DATABASE_URL`, `REDIS_PASSWORD`, and `MONGO_PASSWORD` are defined in `.env`.
Copy `env.example` to `.env` and adjust.

## Common commands

```bash
make setup            # copy env.example to .env
make venv             # create .venv and install requirements
make bootstrap        # create DB, roles, schemas, base data (idempotent)
make etl              # load 180 days of operational history
make app              # start Flask on http://127.0.0.1:5000
make smoke            # verify all web views and role permissions
make verify-polyglot  # verify Postgres, Redis, Mongo, Streams, and Sagas
make test             # smoke + verify-polyglot + demo + verify
```

## Database schemas

| Schema | Purpose |
|---|---|
| `operacion` | Catalogs + transactional core (lots, inventory, sales, shrinkage, sessions) |
| `analitica` | Forecasting, replenishment, transfers, alerts, waste avoidance |
| `auditoria` | Immutable event log + audit views |

## Codebase Modules

- `app/services/cache_service.py` — Redis pool, JSON cache, atomic locks, JWT denylist
- `app/services/doc_store.py` — MongoDB connector for forecasting, ASN, and alerts
- `app/services/common/` — Cross-cutting microservices concerns (response negotiation JSON/XML, auth decorators, swagger/openapi)
- `app/services/auth_service/` — svc-auth (5001)
- `app/services/catalog_service/` — svc-catalog (5002)
- `app/services/inventory_service/` — svc-inventory (5003)
- `app/services/commercial_service/` — svc-commercial (5004)
- `app/services/asn_service/` — svc-asn (5005)
- `app/services/planning_service/` — svc-planning (5006)
- `app/services/alerts_service/` — svc-alerts (5007)
- `app/services/audit_service/` — svc-audit (5008)
- `app/events/dispatcher.py` — Redis Streams event bus with context propagation
- `app/domain/saga_venta.py` — Orchestrated Saga for sales & FEFO inventory
- `app/domain/` — business logic (FEFO, shrinkage, forecasting, replenishment)
- `app/repos/` — catalog CRUD
- `app/blueprints/` — HTTP routes (publico, auth, catalogo, operacion, analitica, panel, api)
- `app/db.py` — all DB access; `transaccion()` sets `app.current_user_id` for audit triggers
- `app/security.py` — login, bcrypt in PostgreSQL, JWT + Redis denylist, role decorators
- `app/navegacion.py` — role-based menu/permissions

## Microservices Roadmap & Tasks

### Completed
- [x] Phase 1: Polyglot persistence interfaces (Redis Cache/Locks/Denylist, Mongo Doc Store).
- [x] Phase 1: Asynchronous Event Bus with Redis Streams and context propagation.
- [x] Phase 1: Orchestrated Saga Pattern for Sales & FEFO Inventory with compensations.
- [x] Phase 1: Verification script `scripts/verify_polyglot.py` integrated into `make test`.
- [x] Phase 1: Redis JWT instant revocation integrated into `app/security.py`.
- [x] Phase 1: MongoDB time-series storage and Redis event stream integrated into `app/domain/pronostico.py`.
- [x] Phase 2: Despliegue de suite de 8 Microservicios en Flask ubicados en `app/services/`:
  - `svc-auth` (5001): Autenticación, JWT, Redis Denylist (<0.8ms), RBAC.
  - `svc-catalog` (5002): Catálogos maestros, Cache-Aside en Redis, respuestas JSON y XML.
  - `svc-inventory` (5003): Existencias, FEFO queue, bloqueo atómico Redlock, respuestas JSON y XML.
  - `svc-commercial` (5004): Cobro POS con Saga Orquestada, mermas, respuestas JSON y XML.
  - `svc-asn` (5005): Ingesta nativa de manifiestos ASN en XML y JSON, documentos en MongoDB.
  - `svc-planning` (5006): Pronósticos con percentiles en Mongo, órdenes de reabastecimiento en JSON y XML.
  - `svc-alerts` (5007): Escaneo pre-merma, TTL en MongoDB, reporte ESG de CO2e en JSON y XML.
  - `svc-audit` (5008): Bitácora inmutable en PostgreSQL, exportación en XML y JSON, stream Redis.
- [x] Phase 2: Contenerización en `docker-compose.yml` de los 8 microservicios (`app/services/*/Dockerfile`) con puertos 5001 a 5008 y healthchecks.
- [x] Phase 2: Negociación de contenido dual JSON y XML (`Accept: application/xml`, `Accept: application/json`) vía `app/services/common/response.py`.
- [x] Phase 2: Documentación OpenAPI 3.0 y Swagger UI interactiva (`/api/v1/openapi.json`, `/api/v1/docs`) en cada microservicio.
- [x] Phase 2: Documentación técnica obligatoria generada en `docs/DOCUMENTACION_TECNICA_MICROSERVICIOS.md`.
- [x] Phase 2: Suite de verificación integral `scripts/verify_all_microservices.py` incorporada en `make test`.
- [x] Phase 3: Suite Completa de MongoDB & Persistencia Políglota con demostración de las 7 operaciones:
  - 1. Inserción individual y masiva (`insert_one`, `insert_many` en `app/services/doc_store.py`).
  - 2. Consultas y proyecciones selectivas (`find_one`, `projection`).
  - 3. Actualizaciones avanzadas atómicas (`$set`, `$push` para inspecciones de calidad de ASN).
  - 4. Filtrado multi-criterio (`$in`, `$gte`, `$lte`, filtros en objetos anidados).
  - 5. Agregaciones analíticas mediante pipelines complejos (`$match`, `$unwind`, `$group`, `$project`, `$sort`).
  - 6. Creación y uso de índices validado con `explain()` (`uq_asn_folio` único, compuestos, y TTL a 180 días en `alertas_operativas`).
  - 7. Recuperación contextual vinculada a identidades relacionales de PostgreSQL (`id_sku`, `id_locacion`, `id_proveedor`).
  - Suite automatizada `scripts/verify_mongo.py` integrada en `make verify-mongo` y `make test`.
  - Tablero web interactivo `/mongo` en FreshTrack y documentación técnica en `docs/DISENO_PERSISTENCIA_MONGODB.md`.

### Next Steps
- [ ] Implementar Gateway perimetral dedicado / Reverse Proxy Nginx o Kong si se requiere enrutamiento unificado de puertos externos.
- [ ] Configurar observabilidad distribuida (OpenTelemetry / Prometheus exporters en los endpoints de health).
