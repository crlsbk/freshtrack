# Manual de instalación — FreshTrack

**Proyecto 12 · Plataforma predictiva para reducción de desperdicio de alimentos**
Integración de Aplicaciones Computacionales · UDEM · Equipo 05
Santiago López Cervantes · Juan Nicolás Núñez Mendoza · Fabián Azaed Orta Singlaterry

Versión del documento: 24 de noviembre de 2026 · Rama `avance2-postgresql-real` (commit `1926a17`)

---

## Contenido

1. [Qué se instala](#1-qué-se-instala)
2. [Requisitos](#2-requisitos)
3. [Obtener el código](#3-obtener-el-código)
4. [Configurar el archivo `.env`](#4-configurar-el-archivo-env)
5. [Instalación local con Docker Compose](#5-instalación-local-con-docker-compose)
6. [Base de datos: inicialización, migraciones y datos](#6-base-de-datos-inicialización-migraciones-y-datos)
7. [Verificar la instalación](#7-verificar-la-instalación)
8. [Instalación sin Docker (desarrollo)](#8-instalación-sin-docker-desarrollo)
9. [Producción en Google Cloud (GCP)](#9-producción-en-google-cloud-gcp)
10. [App de escritorio (compradores y planeadores)](#10-app-de-escritorio-compradores-y-planeadores)
11. [App Android (personal de tienda)](#11-app-android-personal-de-tienda)
12. [Ejecutar las pruebas](#12-ejecutar-las-pruebas)
13. [Solución de problemas](#13-solución-de-problemas)
14. [Funciones en integración](#14-funciones-en-integración)

---

## 1. Qué se instala

FreshTrack es un sistema distribuido. Una instalación completa contiene:

| Componente | Tecnología | Dónde corre |
|---|---|---|
| Sistema web | Flask 3.1 + Jinja2 (Gunicorn en producción) | Contenedor `freshtrack_app`, puerto 5000 |
| 8 microservicios REST | Flask (Gunicorn en producción) | Contenedores `freshtrack_svc_*`, puertos 5001–5008 |
| Base transaccional | PostgreSQL 17 | Contenedor `freshtrack_db` |
| Base documental | MongoDB 7 | Contenedor `freshtrack_mongo` |
| Caché, sesiones y eventos | Redis 7 (AOF activado) | Contenedor `freshtrack_redis` |
| Servidor de correo | Mailpit v1.27 (captura y reenvío opcional) | Contenedor `freshtrack_mail` |
| Almacenamiento de objetos | MinIO compatible S3 (local) o Google Cloud Storage (producción) | Contenedor `freshtrack_minio` o bucket GCS |
| Puerta de enlace HTTPS | Caddy 2 (solo producción) | Contenedor `freshtrack_caddy`, puertos 80/443 |
| App de escritorio | Python + PySide6 (Qt) | Equipo del comprador/planeador |
| App móvil | Android nativo (Kotlin) | Teléfono del gerente o almacenista |

---

## 2. Requisitos

### 2.1 Servidor o equipo de desarrollo

| Recurso | Mínimo | Recomendado | Nota |
|---|---|---|---|
| CPU | 2 vCPU | 4 vCPU | La prueba de carga mostró que con 2 vCPU el cuello de botella es PostgreSQL (ver Manual técnico §14) |
| RAM | 8 GB | 8–16 GB | El overlay de producción reserva ~3 GB para PostgreSQL, 2 GB para MongoDB y 512 MB para Redis |
| Disco | 20 GB libres | SSD | El dataset masivo hace crecer PostgreSQL a ~3 GB |
| Sistema operativo | Linux, macOS o Windows con Docker | Linux (probado en Arch y CentOS Stream 10) | En CentOS/RHEL con SELinux los montajes ya llevan `:z` |

### 2.2 Software

| Software | Versión | Para qué |
|---|---|---|
| Docker Engine + Docker Compose v2 | Compose v2 con soporte de `!reset` / `!override` (2.24 o superior) | Levantar todo el sistema |
| Git | cualquiera reciente | Obtener y actualizar el código |
| Python | 3.12 o superior (las imágenes usan 3.13; la app de escritorio se probó con 3.14) | Scripts (`ETL.py`, `bootstrap_db.py`, pruebas), app de escritorio |
| `make` (opcional) | GNU make | Atajos del `Makefile` |
| JDK | 17 o superior | Compilar la app Android |
| Android SDK / Android Studio | compileSdk 36, minSdk 26 | Compilar e instalar el APK |
| `adb` | Android platform-tools | Instalar el APK en el teléfono |
| Google Cloud SDK (`gcloud`) | reciente | Solo para el despliegue en GCP |

Dependencias de Python por archivo:

| Archivo | Contenido |
|---|---|
| `requirements.txt` | Flask, SQLAlchemy, psycopg 3, PyJWT, numpy, pandas, Faker, redis, pymongo, xmlschema, gunicorn, segno |
| `requirements-dev.txt` | Lo anterior + pytest, fakeredis, mongomock, pyyaml, locust |
| `requirements-loadtest.txt` | locust 2.43.4 (solo para generar carga desde una laptop) |
| `desktop/requirements.txt` | PySide6, requests, lxml, pytest-qt, pyinstaller |

---

## 3. Obtener el código

```bash
git clone git@github.com:crlsbk/iac-proyecto.git freshtrack
cd freshtrack
git checkout avance2-postgresql-real
```

Estructura relevante para la instalación:

```text
app/                    sistema web y los 8 microservicios (app/services/*_service)
contracts/xsd/          contratos XML (XSD) que usan servicios, escritorio y pruebas
sql/00..12              scripts de PostgreSQL (se aplican en orden)
mongo/                  colecciones, validadores e índices de MongoDB
deploy/                 Caddyfile, gcp_bootstrap.sh, backup_db.sh
desktop/                app de escritorio (PySide6)
android-app/            app Android (Kotlin)
docker-compose.yml      arquitectura local completa
docker-compose.prod.yml overlay de producción (Caddy + Gunicorn + GCS)
env.example             plantilla de variables de entorno
```

---

## 4. Configurar el archivo `.env`

Toda la configuración se lee del entorno; no hay credenciales en el código. La aplicación
**no arranca** si falta `SECRET_KEY` o `DATABASE_URL`.

```bash
cp env.example .env      # o: make setup
```

`.env` está en `.gitignore`: nunca lo subas al repositorio. Para generar claves aleatorias:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

A continuación se explica cada grupo de variables (los valores reales los decide quien instala).

### 4.1 PostgreSQL

| Variable | Qué es |
|---|---|
| `POSTGRES_DB` | Nombre de la base (por defecto `retail_perecederos`) |
| `POSTGRES_USER` / `POSTGRES_SUPERUSER_PASSWORD` | Superusuario del contenedor; lo usa el ETL y la inicialización |
| `POSTGRES_PORT` | Puerto publicado en el host (5432; cámbialo si ya tienes otro PostgreSQL) |
| `APP_BACKEND_PASSWORD` | Contraseña del rol `app_backend` (permisos mínimos; lo usan la web y los servicios). **Obligatoria** |
| `APP_AUDITOR_PASSWORD` | Contraseña del rol `app_auditor` (solo lectura). **Obligatoria** |
| `DATABASE_URL` | Conexión de la app fuera de Docker (`postgresql+psycopg://app_backend:...@localhost:5432/...`). Dentro de Docker la arma `docker-compose.yml` con el host `postgres` |
| `ETL_DATABASE_URL` | Conexión con superusuario para el ETL (desactiva disparadores durante la carga masiva) |

> La contraseña de `app_backend` debe ser **la misma** en `APP_BACKEND_PASSWORD` y dentro de `DATABASE_URL`.

### 4.2 MongoDB y Redis

| Variable | Qué es |
|---|---|
| `MONGO_DB`, `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_PORT` | Base documental (pronósticos, avisos ASN, alertas operativas) |
| `REDIS_PASSWORD`, `REDIS_PORT` | Redis con contraseña (`--requirepass`) y AOF; guarda sesiones, denylist JWT, caché, contadores, rate limit, bloqueos y el stream de eventos |

### 4.3 Seguridad (JWT y sesión web)

| Variable | Qué es |
|---|---|
| `SECRET_KEY` | Firma la cookie de sesión de la web. **Obligatoria** |
| `JWT_SECRET_KEY` | Firma los JWT (HS256) y las etiquetas QR (HMAC). Si se cambia, todas las sesiones y etiquetas QR ya impresas dejan de ser válidas |
| `JWT_MINUTOS_ACCESO` | Vida del *access token* (15 min por defecto) |
| `JWT_HORAS_VIGENCIA` | Vida máxima de la sesión desde el login; el *refresh token* renueva el acceso hasta este tope (8 h) |
| `SESSION_COOKIE_SECURE` | `true` solo cuando hay HTTPS (producción) |
| `TRUST_PROXY` | `true` detrás de Caddy, para respetar `X-Forwarded-*` |

### 4.4 Parámetros de negocio

`HORIZONTE_PRONOSTICO_DIAS` (7), `VENTANA_MEDIA_MOVIL` (28), `ALPHA_SUAVIZACION` (0.30).
Son valores por defecto: si la tabla `analitica.configuracion` define el parámetro, manda la base
(se edita en la pantalla **Configuración** de la web).

### 4.5 Servidor y microservicios

| Variable | Qué es |
|---|---|
| `APP_HOST`, `APP_PORT`, `FLASK_DEBUG` | Dónde escucha la web cuando se corre con `python run.py` |
| `SVC_PUBLIC_HOST` | Host con el que navegadores y clientes externos llegan a los servicios (en GCP: dominio o `<IP>.nip.io`) |
| `WEB_USA_MICROSERVICIOS` | `true` (por defecto): la web delega login, ventas, mermas, productos, pronóstico, reabastecimiento, etc. a los microservicios por HTTP. `false` solo para trabajar la interfaz sin levantar los 8 servicios |
| `RATE_LIMIT_FACTOR` | Multiplica todos los límites de peticiones. Déjalo en 1; solo se sube para pruebas de carga |
| `APP_VERSION` | Versión que reportan los `/health` |

### 4.6 Almacenamiento de objetos (PDF de órdenes de compra, hojas QR, evidencias)

FreshTrack habla el protocolo S3 (firma AWS SigV4) y funciona igual con MinIO o con Google Cloud Storage.

| Variable | Local (MinIO) | Producción (GCS) |
|---|---|---|
| `OBJECT_STORAGE_ENDPOINT` | `http://127.0.0.1:9000` (dentro de Docker se fuerza `http://minio:9000`) | `https://storage.googleapis.com` |
| `OBJECT_STORAGE_ACCESS_KEY` / `_SECRET_KEY` | Usuario y contraseña raíz de MinIO | **Llaves HMAC** de una cuenta de servicio (ver §9.2) |
| `OBJECT_STORAGE_BUCKET` | `freshtrack-reportes` (se crea solo) | `freshtrack-reportes-<proyecto>` |
| `OBJECT_STORAGE_REGION` | `us-east-1` | `auto` |
| `OBJECT_STORAGE_PUBLIC_ENDPOINT` (opcional) | Host alcanzable desde el teléfono para firmar URLs de evidencias | No hace falta con GCS |

### 4.7 Correo saliente (Mailpit y reenvío a Gmail)

Con Docker siempre hay un servidor SMTP: el contenedor `mail` (Mailpit). Los servicios entregan
a Mailpit (`SMTP_HOST=mail`, puerto 1025) y **todos los correos se ven en http://127.0.0.1:8025**,
aunque no configures nada más.

Para que además lleguen al buzón real, llena las variables `MAIL_RELAY_*` y reinicia el contenedor:

| Variable | Qué es |
|---|---|
| `MAIL_RELAY_HOST` | SMTP real, p. ej. `smtp.gmail.com` o `smtp.office365.com` |
| `MAIL_RELAY_USERNAME` | Cuenta que envía (Mailpit reescribe el remitente con ella) |
| `MAIL_RELAY_PASSWORD` | En Gmail, una **contraseña de aplicación** de 16 letras (requiere verificación en 2 pasos; se crea en *myaccount.google.com/apppasswords*). La contraseña normal de la cuenta da error 535 |
| `MAIL_RELAY_ALL` | `true` para reenviar cada correo al destinatario real |
| `MAIL_RELAY_PORT`, `MAIL_RELAY_STARTTLS`, `MAIL_RELAY_AUTH` | Opcionales (587, `true`, `plain`) |
| `MAIL_UI_PORT`, `MAIL_SMTP_PORT` | Puertos locales de la bandeja web (8025) y del SMTP (1025); solo escuchan en 127.0.0.1 |

```bash
docker compose up -d mail     # aplica los cambios de MAIL_RELAY_*
```

Avanzado: para enviar directo a otro SMTP sin Mailpit, define `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_TLS` y `SMTP_FROM`. Sin Docker y sin `SMTP_HOST`, el envío solo se registra en la bitácora.

### 4.8 Producción y monitoreo

| Variable | Qué es |
|---|---|
| `PUBLIC_DOMAIN` | Dominio público que atiende Caddy (dominio propio o `<IP>.nip.io`) |
| `ACME_EMAIL` | Correo para el certificado Let's Encrypt |
| `GCS_BACKUP_BUCKET` (opcional) | Bucket donde `deploy/backup_db.sh` sube los respaldos |
| `MONITOR_USER` / `MONITOR_PASSWORD` | Credenciales del panel privado `/ops/status` (independientes del login de negocio). **Cámbialas siempre** |

---

## 5. Instalación local con Docker Compose

```bash
cp env.example .env                     # ajusta las claves (sección 4)
docker compose up -d --build --wait     # o: make up
docker compose ps                       # todos deben quedar "healthy"
```

`--wait` espera a que los *healthchecks* pasen. La primera vez tarda varios minutos (construcción de
10 imágenes e inicialización de PostgreSQL y MongoDB).

### 5.1 Puertos publicados en el equipo

| Servicio | Contenedor | Puerto host | URL / uso |
|---|---|---|---|
| Sistema web | `freshtrack_app` | 5000 (`APP_PORT`) | http://localhost:5000 |
| svc-auth | `freshtrack_svc_auth` | 5001 | http://localhost:5001/api/v1/docs |
| svc-catalog | `freshtrack_svc_catalog` | 5002 | http://localhost:5002/api/v1/docs |
| svc-inventory | `freshtrack_svc_inventory` | 5003 | http://localhost:5003/api/v1/docs |
| svc-commercial | `freshtrack_svc_commercial` | 5004 | http://localhost:5004/api/v1/docs |
| svc-asn | `freshtrack_svc_asn` | 5005 | http://localhost:5005/api/v1/docs |
| svc-planning | `freshtrack_svc_planning` | 5006 | http://localhost:5006/api/v1/docs |
| svc-alerts | `freshtrack_svc_alerts` | 5007 | http://localhost:5007/api/v1/docs |
| svc-audit | `freshtrack_svc_audit` | 5008 | http://localhost:5008/api/v1/docs |
| PostgreSQL | `freshtrack_db` | 5432 (`POSTGRES_PORT`) | `psql` |
| MongoDB | `freshtrack_mongo` | 27017 (`MONGO_PORT`) | `mongosh` |
| Redis | `freshtrack_redis` | 6379 (`REDIS_PORT`) | `redis-cli` |
| MinIO (API / consola) | `freshtrack_minio` | 9000 / 9001 | http://localhost:9001 |
| Mailpit (bandeja / SMTP) | `freshtrack_mail` | 127.0.0.1:8025 / 127.0.0.1:1025 | http://127.0.0.1:8025 |

Dentro de la red Docker `freshtrack` los contenedores se llaman por nombre (`postgres`, `redis`,
`svc_auth`, …); cambiar los puertos del host en `.env` no afecta la comunicación interna. Los
puertos 5001–5008 están fijos en `docker-compose.yml`.

### 5.2 Comandos de operación

```bash
docker compose logs -f svc_planning      # registro de un servicio
docker compose restart svc_auth          # reiniciar un servicio
docker compose down                      # detener (conserva datos)
docker compose down -v                   # detener y BORRAR volúmenes (datos)
make infra                               # solo PostgreSQL, MongoDB y Redis
```

---

## 6. Base de datos: inicialización, migraciones y datos

### 6.1 Primer arranque

`docker-compose.yml` monta `./sql` en `/docker-entrypoint-initdb.d` del contenedor de PostgreSQL y
`./mongo` en el de MongoDB. Esos scripts se ejecutan **solo cuando el volumen se crea por primera vez**,
en orden alfabético:

| Archivo | Contenido |
|---|---|
| `00_init_roles.sh` | Roles transaccionales `app_backend`, `app_auditor` (y `app_etl`) con las contraseñas de `.env` |
| `01_init_schemas.sql` | Extensiones (pgcrypto, etc.) y esquemas `operacion`, `analitica`, `auditoria` |
| `02_ddl_auditoria.sql` | Bitácora inmutable y funciones de auditoría |
| `03_ddl_operacion.sql` | Catálogos, lotes, existencias, kardex, ventas, mermas, órdenes de compra, sesiones |
| `04_ddl_analitica.sql` | Pronóstico, reabastecimiento, transferencias, descuentos, alertas, desperdicio evitado, configuración |
| `05_funciones_negocio.sql` | Vida útil, clasificación de riesgo, folios, configuración |
| `06_views.sql` | Vistas de consulta |
| `07_seed_base.sql` | Roles de negocio, catálogos base, tiendas/CEDIS y usuarios de demostración |
| `08_optimizacion.sql` | Índices y demanda diaria materializada (`analitica.mv_demanda_diaria_hist`) |
| `09_usuario_proveedor.sql` | Columna `usuario.id_proveedor` (un proveedor solo ve lo suyo) |
| `10_refresh_token.sql` | Columnas para refresh tokens con rotación y detección de reutilización |
| `11_pruebas_carga.sql` | Esquema `pruebas` para guardar resultados de Locust |
| `12_app_movil.sql` | Tablas `evidencia` y `conteo_ciclico` y liga merma ↔ evidencia (app Android) |

`sql/legacy/` contiene volcados de una versión anterior y **no se ejecuta**.

### 6.2 Aplicar un script nuevo sobre una base existente (migración en caliente)

Si el volumen ya existía cuando llegó un script nuevo (p. ej. actualizaste el código y ahora existe
`12_app_movil.sql`), PostgreSQL **no lo ejecuta solo**. Los scripts 08–12 son idempotentes; aplícalos así:

```bash
# Local
docker compose exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/12_app_movil.sql'

# Varios a la vez
for f in 09_usuario_proveedor.sql 10_refresh_token.sql 11_pruebas_carga.sql 12_app_movil.sql; do
  docker compose exec -T postgres sh -c \
    "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/$f"
done
```

En producción agrega `-f docker-compose.yml -f docker-compose.prod.yml` después de `docker compose`.

Alternativa destructiva (solo en desarrollo): `docker compose down -v && docker compose up -d --build --wait`
recrea las bases desde cero.

### 6.3 Cargar la historia operativa

Los datos base solo traen catálogos y usuarios. Para tener 180 días de ventas, lotes, mermas y kardex:

```bash
python scripts/ETL.py                               # fuera de Docker (usa ETL_DATABASE_URL)
docker compose exec app python scripts/ETL.py       # dentro del contenedor de la web
```

Para la volumetría masiva usada en pruebas de carga existe `scripts/generar_dataset_masivo.py`. Si haces
otra carga masiva con disparadores desactivados, refresca la demanda materializada:
`docker compose exec app python scripts/refrescar_agregados.py --forzar`.

### 6.4 Cuentas de prueba

`07_seed_base.sql` crea una cuenta por rol, todas con el patrón `usuario@freshtrack.mx`:

| Rol | Correo | Ubicación asignada |
|---|---|---|
| Administrador | `admin@freshtrack.mx` | CEDIS Central |
| Comprador | `buyer@freshtrack.mx` | CEDIS Central |
| Planeador | `planner@freshtrack.mx` | CEDIS Central |
| Gerente de tienda | `gerente@freshtrack.mx` | Tienda San Pedro |
| Gerente de tienda (2) | `gerente2@freshtrack.mx` | Tienda Cumbres |
| Almacén | `almacen@freshtrack.mx` | Tienda San Pedro |
| Proveedor | `proveedor@freshtrack.mx` | — (ligado a su proveedor) |
| Auditor | `auditor@freshtrack.mx` | CEDIS Central |
| Inactivo (debe ser rechazado) | `inactivo@freshtrack.mx` | — |

Las contraseñas de demostración **no se reproducen en este manual**: ver `scripts/smoke_rutas.py`
(cuentas de prueba) o `sql/07_seed_base.sql`. La pantalla de acceso de la web también ofrece botones
para rellenarlas. **Cámbialas antes de cualquier uso real** (pantalla *Usuarios y Roles → Restablecer contraseña*).

---

## 7. Verificar la instalación

| Qué | Cómo | Resultado esperado |
|---|---|---|
| Contenedores | `docker compose ps` | Todos `Up (healthy)` |
| Web | `curl -fsS http://localhost:5000/health` | JSON con estado y dependencias |
| Cada microservicio | `curl -fsS http://localhost:5001/health` (5001…5008) | `"status": "HEALTHY"` y `dependencies` en `true`; `503` + `DEGRADED` si falta una dependencia |
| Mismo health con prefijo | `curl http://localhost:5006/api/v1/planning/health` | Igual (es el alias que usa el gateway) |
| Health en XML | `curl -H 'Accept: application/xml' http://localhost:5003/health` | Raíz `<service_health>` |
| Swagger / OpenAPI | http://localhost:500X/api/v1/docs y `/api/v1/openapi.json` | Documentación interactiva de cada servicio |
| Contratos XSD | `curl http://localhost:5004/api/v1/contracts/checkout_request.xsd` | El XSD |
| Correo | http://127.0.0.1:8025 | Bandeja de Mailpit |
| MinIO | http://localhost:9001 | Consola con el bucket `freshtrack-reportes` |
| Login | http://localhost:5000/login con `admin@freshtrack.mx` | Panel de control |
| Monitoreo privado | http://localhost:5000/ops/status | Pide `MONITOR_USER`/`MONITOR_PASSWORD`; muestra los 8 servicios |

Scripts de verificación (requieren el sistema arriba):

```bash
python scripts/smoke_http.py          # comunicación HTTP entre contenedores
python scripts/smoke_rutas.py         # recorre todas las pantallas con los 7 roles   (make smoke)
make check-servicios                  # 8 servicios: JSON/XML, saga, XSD y logs
make verify-security                  # JWT, revocación, RBAC
make verify-polyglot                  # PostgreSQL + Redis + MongoDB + Sagas
```

---

## 8. Instalación sin Docker (desarrollo)

Necesitas un PostgreSQL ya instalado y su contraseña de superusuario (Redis y MongoDB son opcionales
para la web, pero los microservicios los esperan).

```bash
cp env.example .env                    # ajusta DATABASE_URL y ETL_DATABASE_URL a TU PostgreSQL
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt     # Windows: .venv\Scripts\pip
python scripts/bootstrap_db.py         # base + roles + sql/01..12 (idempotente)
python scripts/ETL.py                  # historia operativa
python run.py                          # http://127.0.0.1:5000
make services                          # (otra terminal) los 8 microservicios en 5001-5008
```

Equivalente con make: `make setup venv bootstrap etl app`. Para levantar solo las bases en Docker y
correr Flask en tu equipo: `make infra`.

Puntos de atención:

- `DATABASE_URL` debe apuntar al puerto real de tu PostgreSQL (la instalación portable del equipo usa 5433; Docker usa 5432).
- `bootstrap_db.py` aborta si faltan `APP_BACKEND_PASSWORD` o `APP_AUDITOR_PASSWORD`.
- Si no hay base escuchando, falla en segundos con un mensaje que indica qué revisar.
- PostgreSQL portable: `make db` (arranca), `make db ACCION=status|stop|restart`.

---

## 9. Producción en Google Cloud (GCP)

Perfil probado: VM Compute Engine `e2-standard-2` (2 vCPU, 8 GB) con CentOS Stream 10. Solo Caddy
expone puertos (80/443); PostgreSQL, Redis, MongoDB y los servicios quedan en la red interna.
La guía detallada está en [`docs/DESPLIEGUE_GCP.md`](../DESPLIEGUE_GCP.md); aquí va el resumen.

### 9.1 Red: IP estática y firewall

En Cloud Shell:

```bash
export PROJECT_ID=... REGION=us-central1 ZONE=us-central1-a VM_NAME=...
EXT_IP=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" \
  --format="get(networkInterfaces[0].accessConfigs[0].natIP)")
gcloud compute addresses create freshtrack-ip --region="$REGION" --addresses="$EXT_IP"
gcloud compute instances add-tags "$VM_NAME" --zone="$ZONE" --tags=freshtrack-web
gcloud compute firewall-rules create allow-freshtrack-web --direction=INGRESS \
  --network=default --action=ALLOW --rules=tcp:80,tcp:443 \
  --source-ranges=0.0.0.0/0 --target-tags=freshtrack-web
```

Sin dominio propio se usa `<IP>.nip.io` (p. ej. `34.x.x.x.nip.io`): resuelve a la IP pública y Caddy
obtiene un certificado Let's Encrypt válido sin configurar DNS.

### 9.2 Bucket de Cloud Storage con llaves HMAC

```bash
BUCKET_PDF="freshtrack-reportes-${PROJECT_ID}"
gcloud storage buckets create "gs://${BUCKET_PDF}" --location="$REGION" \
  --uniform-bucket-level-access --public-access-prevention
gcloud iam service-accounts create freshtrack-storage --display-name="FreshTrack Object Storage S3"
SA_EMAIL="freshtrack-storage@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_PDF}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.objectAdmin"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_PDF}" \
  --member="serviceAccount:${SA_EMAIL}" --role="roles/storage.legacyBucketReader"
gcloud storage hmac create "$SA_EMAIL"     # copia Access ID y Secret al .env
```

El bucket es privado: los PDF se descargan a través de los servicios y las evidencias con URL firmada (15 min).

### 9.3 Preparar la VM

Por SSH, en la carpeta del repositorio:

```bash
git pull
sudo bash deploy/gcp_bootstrap.sh
```

El script instala Docker Engine + Compose v2, abre http/https en `firewalld`, da permisos a los scripts,
crea `/var/backups/freshtrack` y genera un `.env` con contraseñas aleatorias (PostgreSQL, roles, MongoDB,
Redis, `SECRET_KEY`, `JWT_SECRET_KEY`). Cierra y vuelve a abrir la sesión SSH para tomar el grupo `docker`.

Completa en `.env`:

```dotenv
PUBLIC_DOMAIN=<IP>.nip.io
SVC_PUBLIC_HOST=<IP>.nip.io
ACME_EMAIL=<correo>
OBJECT_STORAGE_ENDPOINT=https://storage.googleapis.com
OBJECT_STORAGE_REGION=auto
OBJECT_STORAGE_BUCKET=freshtrack-reportes-<proyecto>
OBJECT_STORAGE_ACCESS_KEY=<HMAC access id>
OBJECT_STORAGE_SECRET_KEY=<HMAC secret>
SESSION_COOKIE_SECURE=true
TRUST_PROXY=true
MONITOR_PASSWORD=<propia>
# opcional: MAIL_RELAY_* (sección 4.7) y GCS_BACKUP_BUCKET
```

### 9.4 Levantar con el overlay de producción

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec app python scripts/ETL.py   # solo la 1.ª vez
```

Qué cambia el overlay `docker-compose.prod.yml`:

- Cierra todos los puertos internos (5432, 6379, 27017, 5000–5008, 9000–9001).
- Corre la web y los 8 servicios con **Gunicorn** (1–2 workers × 4 hilos cada uno) y límites de memoria.
- Ajusta PostgreSQL (`shared_buffers=1GB`, `max_connections=120`, `jit=off`, registro de consultas > 500 ms) y MongoDB (caché WiredTiger 1 GB).
- Desactiva MinIO (perfil `local-s3`): los objetos van a GCS.
- Agrega **Caddy** en 80/443 con TLS automático, HSTS y cabeceras de seguridad.

Rutas del gateway Caddy (`deploy/Caddyfile`):

| Ruta pública | Destino |
|---|---|
| `/api/v1/auth*` | `svc_auth:5001` |
| `/api/v1/catalog*` | `svc_catalog:5002` |
| `/api/v1/inventory*` | `svc_inventory:5003` |
| `/api/v1/commercial*` | `svc_commercial:5004` |
| `/api/v1/asn*` | `svc_asn:5005` |
| `/api/v1/planning*` | `svc_planning:5006` |
| `/api/v1/alerts*` | `svc_alerts:5007` |
| `/api/v1/audit*` | `svc_audit:5008` |
| todo lo demás | web `app:5000` |

> En producción el Swagger de cada servicio (`/api/v1/docs`) **no** queda publicado: esa ruta no coincide
> con ningún prefijo del gateway y cae en la web. Úsalo en local (puertos 5001–5008).

Verificación desde tu equipo:

```bash
curl -fsS https://<dominio>/health
curl -fsS https://<dominio>/api/v1/planning/health
curl -fsS "https://<dominio>/api/v1/catalog/products?por_pagina=2"
```

### 9.5 Actualizar el sistema

```bash
cd ~/iac-proyecto
git pull
# 1. Aplicar los scripts SQL nuevos (idempotentes), p. ej. 12_app_movil.sql
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres sh -c \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/12_app_movil.sql'
# 2. Reconstruir y reiniciar
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```

Las sesiones abiertas antes de un cambio de seguridad siguen hasta su expiración.

### 9.6 Respaldos

```bash
sudo /ruta/absoluta/al/repo/deploy/backup_db.sh        # prueba manual
(crontab -l 2>/dev/null; echo "0 3 * * * /ruta/absoluta/al/repo/deploy/backup_db.sh >> /var/log/freshtrack_backup.log 2>&1") | crontab -
```

Respalda PostgreSQL y MongoDB en `/var/backups/freshtrack` y, si existe `GCS_BACKUP_BUCKET`, los sube a GCS.

---

## 10. App de escritorio (compradores y planeadores)

Cliente PySide6 que consume **solo XML** de los microservicios. Detalle en [`desktop/README.md`](../../desktop/README.md).

### 10.1 Ejecutar desde el código

Linux / macOS:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r desktop/requirements.txt
python desktop/run_desktop.py            # o: make desktop
```

Windows (PowerShell):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r desktop\requirements.txt
python desktop\run_desktop.py
```

### 10.2 Generar el ejecutable (PyInstaller)

```bash
make desktop-build      # pyinstaller desktop/freshtrack_desktop.spec → desktop/dist/FreshTrackDesktop/
QT_QPA_PLATFORM=offscreen desktop/dist/FreshTrackDesktop/FreshTrackDesktop --smoke   # código 0 = arranca y encuentra los XSD
```

El *spec* empaqueta `contracts/xsd` dentro del ejecutable (modo *onedir*). Para Windows hay que ejecutar
PyInstaller en Windows (no hay compilación cruzada) y se obtiene `FreshTrackDesktop.exe`. Para entregar,
comprime la carpeta `desktop/dist/FreshTrackDesktop/`.

### 10.3 Configurar el servidor

En la ventana de login, botón **«Servidores…»**. Se guarda en `~/.freshtrack_desktop/config.ini`.

| Escenario | Configuración |
|---|---|
| Local (Docker Compose) | Host `http://localhost` (por defecto): usa los puertos 5001–5008 |
| Producción con Caddy | Campo **Gateway**: `https://<dominio>` (una sola URL para los 8 servicios) |
| Servidor sin gateway | Host = IP o dominio del servidor (requiere puertos 5001–5008 abiertos) |

Variables de entorno con prioridad sobre el archivo: `FRESHTRACK_HOST`, `FRESHTRACK_GATEWAY_URL`,
`FRESHTRACK_XSD_DIR` (carpeta alterna de XSD).

---

## 11. App Android (personal de tienda)

App Kotlin para gerentes de tienda y almacenistas. Detalle en [`android-app/README.md`](../../android-app/README.md).

### 11.1 Compilar e instalar

```bash
cd android-app
./gradlew assembleDebug        # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease      # APK minificado (R8), firmado con la llave debug para la demo
./gradlew testDebugUnitTest    # pruebas unitarias JVM
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

O en Android Studio: **File → Open → `android-app`** y ▶ Run. Requisitos: JDK 17+, compileSdk 36, teléfono
con Android 8.0 (API 26) o superior, con depuración USB activada para `adb`.

### 11.2 Configurar el servidor

La URL por defecto es la del despliegue en GCP (`BuildConfig.DEFAULT_BASE_URL`, definida en
`android-app/app/build.gradle.kts`). Para cambiarla: **Login → icono de ajustes → Servidor**. El botón de
GCP restablece la URL por defecto.

La app exige HTTPS; la única excepción es `10.0.2.2` (el equipo anfitrión visto desde el emulador), para
desarrollo contra el stack local.

---

## 12. Ejecutar las pruebas

| Tipo | Comando | Requiere |
|---|---|---|
| Unitarias (backend) | `make test-unit` (`pytest tests/unit -v`) | Nada (usa fakeredis/mongomock) |
| Integración (backend) | `make test-integration` (`pytest tests/integration -v`) | PostgreSQL con seed, Redis y MongoDB |
| Reporte de pruebas | `make reporte-pruebas` | Genera `docs/pruebas/REPORTE_PRUEBAS.md` |
| Escritorio | `make desktop-test` (pytest-qt, sin pantalla) | Nada (servidor HTTP falso) |
| Android | `cd android-app && ./gradlew testDebugUnitTest` | JDK |
| Humo de pantallas | `make smoke` | Sistema arriba |

### 12.1 Pruebas de carga con Locust

Escenario escalonado de 8 perfiles (`tests/carga/`):

```bash
.venv/bin/pip install -r requirements-dev.txt
RATE_LIMIT_FACTOR=1000 docker compose up -d --build --wait     # medir capacidad real, no el limitador
tests/carga/correr.sh docs/pruebas/carga/escalonada 1
.venv/bin/python tests/carga/analizar.py docs/pruebas/carga/escalonada
docker compose up -d --wait                                      # regresar RATE_LIMIT_FACTOR=1
```

Los perfiles escriben ventas, mermas y bitácora reales: respalda la base antes (ver `tests/carga/README.md`).
Interfaz web de Locust: `.venv/bin/locust -f tests/carga/locustfile.py` → http://localhost:8089.

Contra el despliegue público (desde la laptop, `tests/load/` + `scripts/locust_ejecutar.py`):

```bash
.venv/bin/pip install -r requirements-loadtest.txt
export LOCUST_ADMIN_PASSWORD=...  LOCUST_PASSWORD_POOL=...
.venv/bin/python scripts/locust_ejecutar.py --host https://<dominio> --escenario rendimiento
```

---

## 13. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| Errores `relation ... does not exist` o `column ... does not exist` (p. ej. `operacion.evidencia`, `refresh_hash`, `id_proveedor`) | El volumen de PostgreSQL se creó con una versión anterior y los scripts nuevos de `sql/` no se ejecutaron | Aplica los scripts faltantes con `psql` (§6.2). En desarrollo puedes recrear con `docker compose down -v` (borra datos) |
| La web muestra datos vacíos tras actualizar | Falta cargar la historia o refrescar la demanda materializada | `python scripts/ETL.py`; tras cargas masivas `scripts/refrescar_agregados.py --forzar` |
| `bootstrap_db.py` aborta | Faltan `APP_BACKEND_PASSWORD` / `APP_AUDITOR_PASSWORD` o el puerto de `DATABASE_URL` no es el de tu PostgreSQL | Completa `.env` y verifica el puerto |
| La app no arranca: falta `SECRET_KEY` o `DATABASE_URL` | `.env` incompleto | Copia `env.example` y completa |
| `Bind for 0.0.0.0:5432 failed: port is already allocated` (o 5000, 6379, 27017, 8025) | Otro proceso usa el puerto | Cambia `POSTGRES_PORT`, `REDIS_PORT`, `MONGO_PORT`, `APP_PORT`, `MAIL_UI_PORT` en `.env`, o detén el otro proceso (`ss -ltnp | grep 5432`). Los puertos 5001–5008 están fijos en el compose |
| Correo no llega al buzón real; en `docker compose logs mail` aparece `535 ... Username and Password not accepted` | Gmail rechaza la contraseña normal | Usa una **contraseña de aplicación** de Gmail en `MAIL_RELAY_PASSWORD`, con `MAIL_RELAY_ALL=true`, y `docker compose up -d mail`. El correo siempre queda visible en http://127.0.0.1:8025 |
| Redis caído (`docker stop freshtrack_redis`) | — | Los servicios siguen validando la sesión contra PostgreSQL (respaldo) y operan sin caché; si tampoco pueden verificarla responden `401 sesion_no_verificable` (fail-closed). Recupera con `docker compose up -d redis` |
| MongoDB caído | — | Las funciones que leen documentos (alertas de svc-alerts, avisos ASN, series de pronóstico) fallan o responden 503 (p. ej. la pestaña Alertas de la app móvil); inventario, ventas y mermas siguen funcionando. Recupera con `docker compose up -d mongo` |
| Un servicio `unhealthy` | Dependencia caída o error de arranque | `docker compose logs svc_<nombre>`; `curl localhost:500X/health` muestra qué dependencia falla |
| Generar PDF de OC falla o no se ve | Bucket no disponible o llaves HMAC erróneas | Revisa `OBJECT_STORAGE_*`; en local, que `freshtrack_minio` esté *healthy* |
| `429 limite_excedido` | Se superó el límite de peticiones (p. ej. 10 logins/min) | Espera los segundos de `Retry-After`. Para pruebas de carga usa `RATE_LIMIT_FACTOR` |
| Caddy no obtiene certificado | Puertos 80/443 cerrados o `PUBLIC_DOMAIN` mal escrito | Revisa la regla de firewall VPC y `firewalld`; `docker compose ... logs caddy` |
| En CentOS/RHEL, PostgreSQL no lee `sql/` | Contexto SELinux | Conserva el sufijo `:z` en los montajes |
| La app de escritorio dice «servicio no disponible» | URL de servidor/gateway incorrecta o servicio detenido | «Servidores…» en el login; página **Estado de servicios** |
| La app Android no conecta a `http://...` | La app exige HTTPS | Usa la URL HTTPS del gateway, o `10.0.2.2` en el emulador |
| La base portable aparece vacía de golpe (Windows/Git Bash) | Se arrancó otro clúster por una ruta mal convertida | Revisa el directorio de datos de `postgres` (ver `README.md`, sección «Si la base se detuvo») |

---

## 14. Funciones en integración

Al cierre de este documento, otro integrante del equipo está incorporando las siguientes funciones,
que **todavía no están en esta versión del código** y por eso no se documentan como instalables:

- Recuperación de contraseña desde la web.
- Centro de notificaciones en la web.
- «Último error registrado» en el panel de monitoreo `/ops/status`.
- App Android: cola de operaciones sin conexión, sincronización y registro de dispositivo.

Si llegan con scripts SQL nuevos, se aplican con el procedimiento de §6.2 / §9.5.
