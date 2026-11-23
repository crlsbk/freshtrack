"""
Cliente ligero de Cloud Object Storage compatible con Amazon S3 / MinIO.

Implementa firma AWS Signature V4 (AWS4-HMAC-SHA256) con biblioteca estándar de Python,
permitiendo subir y recuperar documentos PDF de reportes y órdenes de compra sin dependencias externas.
Ante indisponibilidad temporal del servidor de almacenamiento (por ejemplo en pruebas unitarias
sin red), conserva respaldo local determinista en /tmp/freshtrack_object_storage.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from app.config import Config

logger = logging.getLogger("freshtrack.object_storage")

FALLBACK_DIR = Path("/tmp/freshtrack_object_storage")


def _config_actual() -> dict[str, str]:
    """Lee configuración vigente desde entorno o Config."""
    return {
        "endpoint": os.getenv("OBJECT_STORAGE_ENDPOINT", Config.OBJECT_STORAGE_ENDPOINT).rstrip("/"),
        "access_key": os.getenv("OBJECT_STORAGE_ACCESS_KEY", Config.OBJECT_STORAGE_ACCESS_KEY),
        "secret_key": os.getenv("OBJECT_STORAGE_SECRET_KEY", Config.OBJECT_STORAGE_SECRET_KEY),
        "bucket": os.getenv("OBJECT_STORAGE_BUCKET", Config.OBJECT_STORAGE_BUCKET),
        "region": os.getenv("OBJECT_STORAGE_REGION", Config.OBJECT_STORAGE_REGION),
    }


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret_key: str, date_stamp: str, region: str, service: str = "s3") -> bytes:
    k_date = _hmac_sha256(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, "aws4_request")


def _peticion_s3(
    metodo: str,
    ruta_objeto: str,
    *,
    cuerpo: bytes = b"",
    content_type: str | None = None,
    timeout: float = 8.0,
) -> tuple[int, bytes, dict[str, str]]:
    """Ejecuta una petición HTTP firmada con AWS Signature V4 hacia S3/MinIO."""
    cfg = _config_actual()
    parsed = urllib.parse.urlparse(cfg["endpoint"])
    host = parsed.netloc
    base_path = parsed.path.rstrip("/")
    canonical_uri = f"{base_path}/{ruta_objeto.lstrip('/')}"
    if not canonical_uri.startswith("/"):
        canonical_uri = "/" + canonical_uri
    canonical_uri = urllib.parse.quote(canonical_uri, safe="/-_.~")

    ahora = datetime.now(timezone.utc)
    amz_date = ahora.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = ahora.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(cuerpo).hexdigest()

    headers_canon = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type and metodo in ("PUT", "POST"):
        headers_canon["content-type"] = content_type

    sorted_keys = sorted(headers_canon)
    canonical_headers = "".join(f"{k}:{headers_canon[k]}\n" for k in sorted_keys)
    signed_headers = ";".join(sorted_keys)

    canonical_request = "\n".join(
        [
            metodo.upper(),
            canonical_uri,
            "",  # canonical query string vacío
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    scope = f"{date_stamp}/{cfg['region']}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(cfg["secret_key"], date_stamp, cfg["region"]),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={cfg['access_key']}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"{parsed.scheme}://{host}{canonical_uri}"
    data = cuerpo if metodo.upper() in ("PUT", "POST") else None
    req = urllib.request.Request(url, data=data, method=metodo.upper())
    req.add_header("Authorization", auth_header)
    req.add_header("x-amz-date", amz_date)
    req.add_header("x-amz-content-sha256", payload_hash)
    if content_type and metodo.upper() in ("PUT", "POST"):
        req.add_header("Content-Type", content_type)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp.read(), hdrs
    except urllib.error.HTTPError as err:
        hdrs = {k.lower(): v for k, v in err.headers.items()} if err.headers else {}
        return err.code, err.read(), hdrs
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Object Storage no accesible (%s): %s", cfg["endpoint"], exc)
        return 0, b"", {}


def asegurar_bucket(bucket: str | None = None) -> bool:
    """Verifica la existencia del bucket y lo crea si aún no existe."""
    bkt = bucket or _config_actual()["bucket"]
    status, _, _ = _peticion_s3("HEAD", bkt)
    if status == 200:
        return True
    if status == 404:
        st_put, _, _ = _peticion_s3("PUT", bkt)
        return st_put in (200, 204, 409)
    return False


def subir_pdf(object_key: str, contenido: bytes, bucket: str | None = None) -> dict:
    """
    Sube un PDF al Cloud Object Storage y retorna sus metadatos de ubicación e integridad.
    Si el servidor remoto no está accesible, utiliza respaldo local determinista.
    """
    bkt = bucket or _config_actual()["bucket"]
    key = object_key.lstrip("/")
    sha256 = hashlib.sha256(contenido).hexdigest()
    tamano = len(contenido)

    if asegurar_bucket(bkt):
        status, _, hdrs = _peticion_s3(
            "PUT",
            f"{bkt}/{key}",
            cuerpo=contenido,
            content_type="application/pdf",
            timeout=12.0,
        )
        if status in (200, 201, 204):
            etag = (hdrs.get("etag") or "").strip('"') or sha256[:32]
            return {
                "storage_provider": "s3",
                "bucket": bkt,
                "object_key": key,
                "etag": etag,
                "sha256": sha256,
                "tamano_bytes": tamano,
                "content_type": "application/pdf",
            }

    destino_local = FALLBACK_DIR / bkt / key
    destino_local.parent.mkdir(parents=True, exist_ok=True)
    destino_local.write_bytes(contenido)
    return {
        "storage_provider": "local_fallback",
        "bucket": bkt,
        "object_key": key,
        "etag": sha256[:32],
        "sha256": sha256,
        "tamano_bytes": tamano,
        "content_type": "application/pdf",
    }


def descargar_pdf(
    object_key: str,
    bucket: str | None = None,
    storage_provider: str = "s3",
) -> bytes | None:
    """Recupera un PDF almacenado en Cloud Object Storage o respaldo local."""
    bkt = bucket or _config_actual()["bucket"]
    key = object_key.lstrip("/")

    if storage_provider != "local_fallback":
        status, data, _ = _peticion_s3("GET", f"{bkt}/{key}", timeout=12.0)
        if status == 200 and data:
            return data

    ruta_local = FALLBACK_DIR / bkt / key
    if ruta_local.is_file():
        return ruta_local.read_bytes()
    return None


def verificar_salud() -> bool:
    """Comprueba que el servicio de Cloud Object Storage responda en /minio/health/live."""
    cfg = _config_actual()
    try:
        with urllib.request.urlopen(f"{cfg['endpoint']}/minio/health/live", timeout=2.5) as r:
            return r.status == 200
    except Exception:
        return False
