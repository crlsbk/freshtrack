# Guía de Despliegue Productivo en GCP (CentOS Stream 10 · Caddy HTTPS · Google Cloud Storage)

Esta guía está adaptada al perfil de instancia ya aprovisionado:
- **VM Compute Engine**: `e2-standard-2` (2 vCPUs, 8 GB RAM), `centos-stream-10-v20260609` (`x86_64`)
- **Exposición pública**: **Caddy 2** en puertos `80` / `443` con certificado TLS automático (dominio propio o `<IP>.nip.io`)
- **Almacenamiento de PDFs**: **Google Cloud Storage (GCS)** nativo vía llaves **HMAC (S3 Interoperability)**

Ningún puerto interno (`5432`, `6379`, `27017`, `5000–5008`) queda abierto hacia Internet.

---

## 1. Aprovisionamiento de Red y Storage en GCP (Google Cloud Shell)

Ejecuta estos comandos desde **Cloud Shell** (ícono `>_` en la consola web de GCP) ajustando tu `PROJECT_ID`, `ZONE` y `VM_NAME`:

```bash
export PROJECT_ID="tu-proyecto-gcp"
export REGION="us-central1"
export ZONE="us-central1-a"
export VM_NAME="nombre-de-tu-vm"
export BUCKET_PDF="freshtrack-reportes-${PROJECT_ID}"
export BUCKET_BK="freshtrack-backups-${PROJECT_ID}"

gcloud config set project "$PROJECT_ID"
```

### 1.1 Fijar IP estática y abrir Firewall VPC (solo 80 y 443)

1. Obtén la IP efímera actual de la VM y promuévela a IP estática regional (para que el DNS/certificado HTTPS no se rompa al reiniciar):

```bash
EXT_IP=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --format="get(networkInterfaces[0].accessConfigs[0].natIP)")
gcloud compute addresses create freshtrack-ip --region="$REGION" --addresses="$EXT_IP"
echo "IP estática asignada: $EXT_IP"
```

2. Etiqueta la VM y abre únicamente HTTP (`80`) y HTTPS (`443`) en la VPC:

```bash
gcloud compute instances add-tags "$VM_NAME" --zone="$ZONE" --tags=freshtrack-web

gcloud compute firewall-rules create allow-freshtrack-web \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:80,tcp:443 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=freshtrack-web
```

> [!TIP]
> **¿No tienes dominio propio?** Usa **`${EXT_IP}.nip.io`** en `PUBLIC_DOMAIN` (por ejemplo `34.122.10.25.nip.io`). Es gratuito, resuelve automáticamente a tu IP pública y Caddy generará un certificado TLS válido de Let's Encrypt sin configuración DNS extra. Si tienes dominio propio, crea un registro DNS `A` apuntando a `$EXT_IP`.

### 1.2 Crear Bucket de Cloud Storage + Llaves HMAC para PDFs

```bash
# Bucket regional privado para almacenar PDFs de Órdenes de Compra
gcloud storage buckets create "gs://${BUCKET_PDF}" \
  --location="$REGION" \
  --uniform-bucket-level-access \
  --public-access-prevention

# (Opcional) Bucket para respaldos nocturnos de PostgreSQL y MongoDB
gcloud storage buckets create "gs://${BUCKET_BK}" \
  --location="$REGION" \
  --uniform-bucket-level-access \
  --public-access-prevention

# Service Account dedicada con privilegio mínimo sobre el bucket de reportes
gcloud iam service-accounts create freshtrack-storage \
  --display-name="FreshTrack Object Storage S3"

SA_EMAIL="freshtrack-storage@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_PDF}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_PDF}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.legacyBucketReader"

# Generar llaves HMAC (copia Access ID y Secret en el .env del paso 2)
gcloud storage hmac create "$SA_EMAIL"
```

---

## 2. Preparación de la VM CentOS Stream 10 (por SSH)

Conéctate por SSH a tu VM de GCP y entra al directorio donde clonaste el proyecto:

```bash
cd ~/iac-proyecto
git pull
sudo bash deploy/gcp_bootstrap.sh
```

El script realiza automáticamente:
- Instalación oficial de **Docker Engine + Docker Compose v2** (`docker-ce.repo` vía `dnf`).
- Apertura de `http` y `https` en `firewalld` (si `firewalld` está activo en CentOS Stream 10).
- Permisos en `sql/00_init_roles.sh` y `deploy/backup_db.sh` y creación de `/var/backups/freshtrack`.
- Generación de `.env` con contraseñas aleatorias seguras para PostgreSQL, roles transaccionales, MongoDB, Redis, `SECRET_KEY` y `JWT_SECRET_KEY`.

**Cierra y vuelve a abrir la sesión SSH** (`exit` y reconectar) para que tu usuario tome los permisos del grupo `docker`.

### Editar `.env` con tu dominio y credenciales GCS

```bash
nano .env
```

Asegúrate de completar estos valores:

```dotenv
PUBLIC_DOMAIN=34.x.x.x.nip.io
SVC_PUBLIC_HOST=34.x.x.x.nip.io
ACME_EMAIL=tu_correo@empresa.mx

OBJECT_STORAGE_ENDPOINT=https://storage.googleapis.com
OBJECT_STORAGE_REGION=auto
OBJECT_STORAGE_BUCKET=freshtrack-reportes-tu-proyecto-gcp
OBJECT_STORAGE_ACCESS_KEY=GOOG1E...tu_hmac_access_id
OBJECT_STORAGE_SECRET_KEY=...tu_hmac_secret

SESSION_COOKIE_SECURE=true
TRUST_PROXY=true

# Opcional: si deseas respaldo nocturno en GCS además de /var/backups/freshtrack
GCS_BACKUP_BUCKET=freshtrack-backups-tu-proyecto-gcp

# Opcional: correo saliente real (si se omite, el sistema registra envío y ofrece mailto:)
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=compras@tuempresa.mx
# SMTP_PASSWORD=clave_de_aplicacion
```

---

## 3. Arranque Productivo, Carga Histórica y Respaldos

### 3.1 Construir y levantar la arquitectura de producción

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Todos los contenedores (`freshtrack_app`, `freshtrack_caddy`, `freshtrack_db`, `freshtrack_redis`, `freshtrack_mongo` y los 8 `freshtrack_svc_*`) deben quedar **`Up (healthy)`**. El contenedor `freshtrack_minio` no arranca en producción porque los PDFs se guardan directamente en Google Cloud Storage.

> [!NOTE]
> **Notas para CentOS Stream 10 (`SELinux`)**: `docker-compose.yml` y `docker-compose.prod.yml` ya incluyen el sufijo `:ro,z` en los montajes (`./sql`, `./mongo`, `./deploy/Caddyfile`), evitando bloqueos de lectura por contexto SELinux. Si en algún momento ejecutas `restorecon` o creas otro bind mount, conserva `:z`.

### 3.2 Cargar 180 días de historia operativa (solo primer despliegue)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec app python scripts/ETL.py
```

### 3.3 Programar respaldos automáticos diarios (Cron)

```bash
# Verifica una corrida manual primero
sudo /ruta/absoluta/a/iac-proyecto/deploy/backup_db.sh

# Agendar todos los días a las 03:00 AM
(crontab -l 2>/dev/null; echo "0 3 * * * /ruta/absoluta/a/iac-proyecto/deploy/backup_db.sh >> /var/log/freshtrack_backup.log 2>&1") | crontab -
```

*(Si deseas también habilitar subida automática del backup a `GCS_BACKUP_BUCKET`, asegúrate de que la VM tenga un rol Storage Object Creator o `gcloud auth` en la cuenta raíz/cron).*

---

## 4. Verificación Final, Simulador POS y App de Escritorio

### 4.1 Verificar TLS y salud desde tu equipo local

```bash
curl -fsS "https://34.x.x.x.nip.io/health"
curl -fsS "https://34.x.x.x.nip.io/api/v1/catalog/products?por_pagina=2"
```

### 4.2 Emitir una Orden de Compra y confirmar almacenamiento en GCS

1. Inicia sesión en `https://34.x.x.x.nip.io` con `buyer@freshtrack.mx` (`Compras2026!`) y genera una Orden de Compra desde **Proveedores y Compras por Lotes**.
2. Confirma que el visor `<iframe>` embebido carga el PDF sin bloqueos de frame y permite descargarlo.
3. Confirma el objeto en Cloud Storage desde Cloud Shell:
   ```bash
   gcloud storage ls "gs://${BUCKET_PDF}/ordenes_compra/**"
   ```

### 4.3 Simular ventas POS en tiempo real (JSON y XML) hacia GCP

Desde tu computadora local:

```bash
.venv/bin/python scripts/simulador_pos.py \
  --base-url "https://34.x.x.x.nip.io" \
  --cantidad 5 --intervalo 1.5 --formato mixto
```

### 4.4 Endpoints unificados para tu futura Aplicación de Escritorio

Cualquier cliente nativo (Electron, Tauri, PyQt, .NET, etc.) consume un único dominio HTTPS en el puerto estándar `443`:

| Dominio funcional | Ruta base pública |
|---|---|
| Login, JWT y usuarios | `https://<PUBLIC_DOMAIN>/api/v1/auth/...` |
| Productos (`moq_lote`), tiendas y proveedores | `https://<PUBLIC_DOMAIN>/api/v1/catalog/...` |
| Existencias, cola FEFO y recepción/bloqueos | `https://<PUBLIC_DOMAIN>/api/v1/inventory/...` |
| Ventas POS (JSON/XML) y mermas | `https://<PUBLIC_DOMAIN>/api/v1/commercial/...` |
| Avisos ASN inbound | `https://<PUBLIC_DOMAIN>/api/v1/asn/...` |
| Pronóstico, Newsvendor, compras por proveedor y PDF OC | `https://<PUBLIC_DOMAIN>/api/v1/planning/...` |
| Alertas y sostenibilidad ESG | `https://<PUBLIC_DOMAIN>/api/v1/alerts/...` |
| Bitácora y trazabilidad | `https://<PUBLIC_DOMAIN>/api/v1/audit/...` |

### 4.5 Actualizaciones futuras del sistema

Cuando subas nuevos commits:

```bash
cd ~/iac-proyecto
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```

### 4.6 Optimización de consultas sobre el dataset masivo (en caliente, sin borrar datos)

`sql/08_optimizacion.sql` es idempotente: crea los índices que faltaban, materializa
la demanda diaria histórica (`analitica.mv_demanda_diaria_hist`) y redefine
`analitica.v_demanda_diaria` como *histórico materializado ∪ ventas de hoy en vivo*
(mismas columnas). En un volumen nuevo se ejecuta solo; sobre la base ya cargada:

```bash
cd ~/iac-proyecto
git pull

# 1. Base de datos (tarda segundos a pocos minutos según el volumen; no borra nada)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 \
         -f /docker-entrypoint-initdb.d/08_optimizacion.sql'

# 2. Código, pool de conexiones, tuning de Postgres y límites de memoria
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```

Mantenimiento del histórico materializado:

- La app web lo refresca sola cada 10 min **solo si hace falta** (cambió el día o se
  registraron ventas con fecha retroactiva). Variables: `AGREGADOS_AUTO_REFRESCO`,
  `AGREGADOS_INTERVALO_SEG`.
- `scripts/ETL.py` y `scripts/generar_dataset_masivo.py` lo refrescan al terminar.
  Cualquier otra carga masiva con `session_replication_role=replica` debe ejecutar:
  `docker compose ... exec app python scripts/refrescar_agregados.py --forzar`.
- La vista nunca devuelve datos incompletos: si el histórico está desfasado agrega
  en vivo (más lento) hasta el siguiente refresco.

Consultas lentas: Postgres registra todo lo que tarde más de 500 ms:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs postgres | grep duration
```

### 4.7 Endurecimiento de seguridad (en caliente)

Dos cambios de esquema pequeños e idempotentes, más el código nuevo:

```bash
cd ~/iac-proyecto && git pull
for f in 09_usuario_proveedor.sql 10_refresh_token.sql; do
  docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
    sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -v ON_ERROR_STOP=1 -f /docker-entrypoint-initdb.d/$f"
done
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
```

- **09**: `usuario.id_proveedor`. Un usuario con rol Proveedor solo ve y modifica
  productos, órdenes de compra y avisos ASN de su proveedor. Se asigna en /usuarios.
- **10**: refresh tokens. El access token dura `JWT_MINUTOS_ACCESO` (15 min) y el
  refresh token lo renueva (rotándolo) hasta `jwt_horas_vigencia` (8 h) desde el
  login. Reutilizar un refresh ya rotado revoca la sesión completa y queda como
  `REFRESH_REUTILIZADO` en la bitácora.
- **App móvil**: `POST /api/v1/auth/login` ahora devuelve también `refresh_token` y
  `refresh_expira_en_segundos`. Para renovar: `POST /api/v1/auth/refresh` con
  `{"refresh_token": "..."}` (o `<refresh_request>` en XML). Mientras la app no lo
  implemente, renovar con el Bearer vigente sigue funcionando; si eso no basta,
  sube `JWT_MINUTOS_ACCESO` en el `.env` de la VM.
- Tras desplegar, las sesiones abiertas antes del cambio siguen hasta su
  expiración; los inicios de sesión nuevos ya usan el esquema de refresh.
