# Pruebas de carga con Locust

Simulan a la vez los 8 perfiles que usan FreshTrack contra la web y los 8
microservicios levantados con `docker compose`, en escalones que llevan el sistema
hasta la saturación y luego miden cuánto tarda en recuperarse.

| Archivo | Qué es |
|---|---|
| `locustfile.py` | Perfiles de usuario y escenario escalonado (`EscenarioEscalonado`) |
| `correr.sh` | Corre Locust sin interfaz y muestrea CPU/memoria de los contenedores |
| `analizar.py` | Convierte una corrida en `REPORTE.md` + `grafica.svg` |

## Perfiles

| Perfil | Peso | Cuenta | Endpoints |
|---|---:|---|---|
| Usuarios consultando | 6 | gerente (web) | `/inventario`, `/productos`, `/alertas`, `/lotes`, `/ventas`, `/mapa` |
| Usuarios registrando operaciones | 3 | gerente (API) | `POST checkout` (Saga + FEFO), `POST shrinkage`, `GET sales` |
| Apps móviles enviando datos | 3 | gerente (API) | carrito POS en Redis (`PUT/GET cart`), `GET stock`, `GET fefo-queue`, catálogo |
| App de escritorio pidiendo reportes | 1 | planner (API) | KPIs de pronóstico, backtest, órdenes de reabasto, desperdicio, ASN, stock en XML |
| Sensores transmitiendo lecturas | 4 | almacén (API) | `POST /api/alertas/documentos` cada 5 s (MongoDB con TTL) |
| Conductores actualizando ubicación | 2 | almacén (API) | `POST /api/v1/audit/log` cada 10 s, `GET asn` en tránsito |
| Administradores consultando paneles | 1 | admin (web + API) | `/panel`, `/triaje`, `/desperdicio-evitado`, `/auditoria`, `/usuarios`, contadores y bitácora |
| Procesos automáticos | 1 fijo | almacén (API) | `POST alerts/scan` y `POST expiration/scan` cada 30 s |

La plataforma no tiene endpoints dedicados de telemetría ni de GPS. Los sensores
publican su lectura como documento operativo en MongoDB y los conductores dejan su
posición en la bitácora de svc-audit, que son los registros más cercanos que existen.

## Escenario

| Escalón | Fin (s) | Usuarios |
|---|---:|---:|
| 1-calentamiento | 60 | 10 |
| 2-carga-normal | 180 | 30 |
| 3-carga-alta | 300 | 60 |
| 4-saturacion | 420 | 100 |
| 5-pico | 480 | 150 |
| 6-recuperacion | 660 | 10 |

`CARGA_ESCALA_TIEMPO=0.1` lo comprime para una prueba de humo.

## Cómo correrlo

```bash
# 0. Dependencias (una vez)
.venv/bin/pip install -r requirements-dev.txt

# 1. (Opcional, recomendado) respaldar la BD: los perfiles de escritura crean ventas,
#    mermas, alertas y registros de bitácora reales.
docker compose stop app svc_auth svc_catalog svc_inventory svc_commercial svc_asn svc_planning svc_alerts svc_audit
docker exec freshtrack_db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE retail_perecederos_bak_carga TEMPLATE retail_perecederos"'

# 2. Levantar con el rate limit multiplicado, para medir la capacidad real y no el limitador
#    (en este host también: POSTGRES_PORT=5433 REDIS_PORT=6380)
RATE_LIMIT_FACTOR=1000 docker compose up -d --build --wait

# 3. Correr y analizar
tests/carga/correr.sh docs/pruebas/carga/escalonada 1
.venv/bin/python tests/carga/analizar.py docs/pruebas/carga/escalonada

# 4. Regresar el rate limit y restaurar la BD
docker compose stop app svc_auth svc_catalog svc_inventory svc_commercial svc_asn svc_planning svc_alerts svc_audit
docker exec freshtrack_db sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE retail_perecederos" -c "ALTER DATABASE retail_perecederos_bak_carga RENAME TO retail_perecederos"'
docker compose up -d --wait
```

También se puede abrir la interfaz web de Locust (`.venv/bin/locust -f tests/carga/locustfile.py`,
http://localhost:8089) para ver las gráficas en vivo.

`RATE_LIMIT_FACTOR` (en `app/services/common/rate_limit.py`) multiplica todos los
límites de `@limite_tasa`; por defecto vale 1 y no cambia nada.
