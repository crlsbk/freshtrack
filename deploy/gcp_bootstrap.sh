#!/usr/bin/env bash
# =============================================================================
# Prepara una instancia GCP (CentOS Stream 10 / RHEL o Ubuntu/Debian) para
# ejecutar FreshTrack en producción con Docker Compose + Caddy HTTPS + GCS.
#
# Uso (como root o con sudo desde la raíz del repositorio):
#   sudo bash deploy/gcp_bootstrap.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

TARGET_USER="${SUDO_USER:-$USER}"

echo "[1/5] Instalando Docker Engine y Docker Compose v2..."
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  if command -v dnf >/dev/null 2>&1; then
    dnf -y install curl openssl ca-certificates >/dev/null
    curl -fsSL https://download.docker.com/linux/centos/docker-ce.repo -o /etc/yum.repos.d/docker-ce.repo
    dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg openssl
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    # shellcheck disable=SC1091
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
  else
    echo "[ERROR] Gestor de paquetes no soportado automáticamente; instala Docker Compose v2 manualmente." >&2
    exit 1
  fi
else
  systemctl enable --now docker >/dev/null 2>&1 || true
  echo "  -> Docker y Docker Compose v2 ya instalados."
fi

if [ -n "$TARGET_USER" ] && id "$TARGET_USER" >/dev/null 2>&1; then
  usermod -aG docker "$TARGET_USER" || true
fi

echo "[2/5] Configurando firewall local (solo HTTP 80 y HTTPS 443)..."
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
  firewall-cmd --permanent --add-service=http
  firewall-cmd --permanent --add-service=https
  firewall-cmd --reload
elif command -v ufw >/dev/null 2>&1; then
  ufw allow 22/tcp || true
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
  ufw --force enable || true
else
  echo "  -> No se detectó firewalld ni ufw activo (asegura reglas de firewall en VPC GCP)."
fi

echo "[3/5] Verificando memoria y swap..."
RAM_MB="$(free -m | awk '/^Mem:/ {print $2}')"
if [ "${RAM_MB:-8192}" -lt 6000 ] && [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "  -> Swap de 2 GB creada (RAM detectada: ${RAM_MB} MB)."
else
  echo "  -> RAM suficiente (${RAM_MB} MB) o swap ya presente."
fi

echo "[4/5] Asegurando permisos de ejecución y directorio de respaldos..."
chmod +x sql/00_init_roles.sh deploy/backup_db.sh deploy/gcp_bootstrap.sh
mkdir -p /var/backups/freshtrack
chmod 750 /var/backups/freshtrack

echo "[5/5] Generando archivo .env productivo (si aún no existe)..."
if [ ! -f .env ]; then
  cp env.example .env
  python3 - <<'PY'
import pathlib, secrets

p = pathlib.Path(".env")
text = p.read_text(encoding="utf-8")

pg_pass = secrets.token_hex(16)
be_pass = secrets.token_hex(16)
au_pass = secrets.token_hex(16)
mg_pass = secrets.token_hex(16)
rd_pass = secrets.token_hex(16)
sk = secrets.token_hex(32)
jwt_sk = secrets.token_hex(32)

repl = {
    "POSTGRES_SUPERUSER_PASSWORD=": f"POSTGRES_SUPERUSER_PASSWORD={pg_pass}",
    "APP_BACKEND_PASSWORD=": f"APP_BACKEND_PASSWORD={be_pass}",
    "APP_AUDITOR_PASSWORD=": f"APP_AUDITOR_PASSWORD={au_pass}",
    "MONGO_PASSWORD=": f"MONGO_PASSWORD={mg_pass}",
    "REDIS_PASSWORD=": f"REDIS_PASSWORD={rd_pass}",
    "SECRET_KEY=": f"SECRET_KEY={sk}",
    "JWT_SECRET_KEY=": f"JWT_SECRET_KEY={jwt_sk}",
    "DATABASE_URL=": f"DATABASE_URL=postgresql+psycopg://app_backend:{be_pass}@localhost:5432/retail_perecederos",
    "ETL_DATABASE_URL=": f"ETL_DATABASE_URL=postgresql://postgres:{pg_pass}@localhost:5432/retail_perecederos",
    "OBJECT_STORAGE_ENDPOINT=": "OBJECT_STORAGE_ENDPOINT=https://storage.googleapis.com",
    "OBJECT_STORAGE_REGION=": "OBJECT_STORAGE_REGION=auto",
    "OBJECT_STORAGE_ACCESS_KEY=": "OBJECT_STORAGE_ACCESS_KEY=REEMPLAZAR_CON_HMAC_ACCESS_ID",
    "OBJECT_STORAGE_SECRET_KEY=": "OBJECT_STORAGE_SECRET_KEY=REEMPLAZAR_CON_HMAC_SECRET",
    "OBJECT_STORAGE_BUCKET=": "OBJECT_STORAGE_BUCKET=REEMPLAZAR_CON_BUCKET_GCS",
    "SESSION_COOKIE_SECURE=": "SESSION_COOKIE_SECURE=true",
    "TRUST_PROXY=": "TRUST_PROXY=true",
    "PUBLIC_DOMAIN=": "PUBLIC_DOMAIN=REEMPLAZAR_CON_DOMINIO_O_IP_NIP_IO",
    "SVC_PUBLIC_HOST=": "SVC_PUBLIC_HOST=REEMPLAZAR_CON_DOMINIO_O_IP_NIP_IO",
}

out = []
for line in text.splitlines():
    matched = False
    for prefix, new_line in repl.items():
        if line.startswith(prefix):
            out.append(new_line)
            matched = True
            break
    if not matched:
        out.append(line)
p.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
  if [ -n "$TARGET_USER" ] && id "$TARGET_USER" >/dev/null 2>&1; then
    chown "$TARGET_USER":"$TARGET_USER" .env
  fi
  chmod 600 .env
  echo "  -> .env creado con secretos aleatorios."
else
  echo "  -> .env ya existe; se conserva sin sobrescribir."
fi

cat <<EOF

Bootstrap completado. Próximos pasos:
  1. Cierra y vuelve a abrir tu sesión SSH si acabas de ser agregado al grupo 'docker'.
  2. Edita '.env' y reemplaza:
       PUBLIC_DOMAIN / SVC_PUBLIC_HOST (ej. 34.x.x.x.nip.io o tudominio.com)
       ACME_EMAIL
       OBJECT_STORAGE_BUCKET
       OBJECT_STORAGE_ACCESS_KEY / OBJECT_STORAGE_SECRET_KEY (llaves HMAC de GCS)
  3. Despliega el stack productivo:
       docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --wait
  4. Carga 180 días de historia operativa (primera vez):
       docker compose -f docker-compose.yml -f docker-compose.prod.yml exec app python scripts/ETL.py
EOF
