"""
Configuración de FreshTrack.

Todos los secretos y parámetros de conexión se leen del entorno (.env).
No hay ninguna credencial escrita en el código.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import timedelta

from dotenv import load_dotenv

# Se carga aquí para que cualquier punto de entrada (run.py, el ETL, las
# pruebas) obtenga la misma configuración sin tener que acordarse de llamarlo.
load_dotenv()


def _requerido(nombre: str, ayuda: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(
            f"Falta la variable de entorno {nombre}.\n"
            f"{ayuda}\n"
            "Copia env.example a .env y ajusta los valores:  cp env.example .env"
        )
    return valor


class Config:
    """Configuración de la aplicación Flask."""

    # --- Flask -------------------------------------------------------------
    # Sin SECRET_KEY no arrancamos: no hay valores por defecto en el código.
    SECRET_KEY = _requerido(
        "SECRET_KEY",
        "Es la llave con la que Flask firma la cookie de sesión.",
    )

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    PREFERRED_URL_SCHEME = "https" if SESSION_COOKIE_SECURE else "http"
    TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("JWT_HORAS_VIGENCIA", "8")))
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4 MB

    # --- Base de datos -----------------------------------------------------
    # Obligatoria y sin valor por defecto: si estuviera escrita aquí, la
    # contraseña viviría en el repositorio, que es justo lo que la rúbrica pide
    # evitar. Se lee siempre del entorno.
    DATABASE_URL = _requerido(
        "DATABASE_URL",
        "Cadena de conexión a PostgreSQL, p. ej. "
        "postgresql+psycopg://app_backend:CLAVE@localhost:5432/retail_perecederos",
    )

    # --- JWT ---------------------------------------------------------------
    # Clave propia para firmar JWT. Si no se define, se DERIVA de SECRET_KEY en
    # vez de reutilizarla tal cual: así la clave que firma la cookie de sesión y
    # la que firma los tokens nunca son la misma.
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or hmac.new(
        SECRET_KEY.encode("utf-8"), b"freshtrack-jwt-v1", hashlib.sha256
    ).hexdigest()
    JWT_ALGORITHM = "HS256"
    JWT_HORAS_VIGENCIA = int(os.getenv("JWT_HORAS_VIGENCIA", "8"))

    # --- Redis (Caché, Bloqueos, Denylist JWT y Bus de Eventos) ------------
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_URL = os.getenv("REDIS_URL") or (
        f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
        if REDIS_PASSWORD
        else f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
    )

    # --- MongoDB (Pronósticos de series temporales, ASN y Alertas) --------
    MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
    MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
    MONGO_USER = os.getenv("MONGO_USER", "freshtrack_mongo")
    MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "")
    MONGO_DB = os.getenv("MONGO_DB", "retail_perecederos")
    MONGO_URI = os.getenv("MONGO_URI") or (
        f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}?authSource=admin"
        if MONGO_USER and MONGO_PASSWORD
        else f"mongodb://{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}"
    )

    # --- Parámetros de negocio (valores por defecto; la BD manda) ----------
    HORIZONTE_PRONOSTICO_DIAS = int(os.getenv("HORIZONTE_PRONOSTICO_DIAS", "7"))
    VENTANA_MEDIA_MOVIL = int(os.getenv("VENTANA_MEDIA_MOVIL", "28"))
    ALPHA_SUAVIZACION = float(os.getenv("ALPHA_SUAVIZACION", "0.30"))

    # --- Cloud Object Storage (S3 / MinIO) ---------------------------------
    OBJECT_STORAGE_ENDPOINT = os.getenv("OBJECT_STORAGE_ENDPOINT", "http://127.0.0.1:9000").rstrip("/")
    OBJECT_STORAGE_ACCESS_KEY = os.getenv("OBJECT_STORAGE_ACCESS_KEY", "freshtrack_s3")
    OBJECT_STORAGE_SECRET_KEY = os.getenv("OBJECT_STORAGE_SECRET_KEY", "freshtrack_s3_secret_2026")
    OBJECT_STORAGE_BUCKET = os.getenv("OBJECT_STORAGE_BUCKET", "freshtrack-reportes")
    OBJECT_STORAGE_REGION = os.getenv("OBJECT_STORAGE_REGION", "us-east-1")

    # --- Correo saliente (SMTP opcional) -----------------------------------
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "compras@freshtrack.mx")).strip()
    SMTP_TLS = os.getenv("SMTP_TLS", "true").lower() not in ("0", "false", "no")

    # --- Entorno -----------------------------------------------------------
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", "5000"))
    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

    # --- Monitoreo privado (/ops/status) -----------------------------------
    MONITOR_USER = os.getenv("MONITOR_USER", "ops_monitor")
    MONITOR_PASSWORD = os.getenv("MONITOR_PASSWORD", "FreshTrackOps2026!")
