"""Endpoints que usa la app Android: conteo cíclico, solicitud de transferencia y evidencia fotográfica."""

from __future__ import annotations

import io
import urllib.parse

import jwt
import pytest

from app.config import Config
from app.domain import movil
from app.services import cache_service, object_storage
from app.services.common import auth as auth_mod

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


# --- utilidades puras -------------------------------------------------------------
def test_tipo_real_por_magic_bytes():
    assert movil.tipo_imagen(JPEG) == "image/jpeg"
    assert movil.tipo_imagen(PNG) == "image/png"
    assert movil.tipo_imagen(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    with pytest.raises(ValueError):
        movil.tipo_imagen(b"%PDF-1.4 no es imagen")


def test_url_firmada_v4(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT", "https://storage.googleapis.com")
    monkeypatch.setenv("OBJECT_STORAGE_REGION", "auto")
    monkeypatch.setenv("OBJECT_STORAGE_BUCKET", "bkt")
    url = object_storage.url_firmada("evidencias/3/a b.jpg", expira_segundos=900)
    partes = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qs(partes.query)
    assert partes.netloc == "storage.googleapis.com"
    assert partes.path == "/bkt/evidencias/3/a%20b.jpg"
    assert q["X-Amz-Expires"] == ["900"] and q["X-Amz-SignedHeaders"] == ["host"]
    assert len(q["X-Amz-Signature"][0]) == 64


def test_url_firmada_usa_endpoint_publico(monkeypatch):
    monkeypatch.setenv("OBJECT_STORAGE_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("OBJECT_STORAGE_PUBLIC_ENDPOINT", "https://archivos.ejemplo.mx")
    assert object_storage.url_firmada("x.jpg").startswith("https://archivos.ejemplo.mx/")


# --- clientes de los microservicios -------------------------------------------------
@pytest.fixture()
def tokens(redis_falso, monkeypatch):
    def decodificar(token):
        try:
            return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None

    monkeypatch.setattr(auth_mod, "decodificar_token", decodificar)
    cache_service.crear_sesion_redis("jti-movil", {"id_usuario": "u-1"})

    def auth(rol, loc=3):
        tok = jwt.encode({"sub": "u-1", "rol": rol, "email": "g@freshtrack.mx", "jti": "jti-movil", "id_locacion": loc},
                         Config.JWT_SECRET_KEY, algorithm="HS256")
        return {"Authorization": f"Bearer {tok}"}

    return auth


@pytest.fixture()
def inv(tokens):
    from app.services.inventory_service import app as m
    return m, m.app.test_client()


@pytest.fixture()
def plan(tokens):
    from app.services.planning_service import app as m
    return m, m.app.test_client()


@pytest.fixture()
def com(tokens):
    from app.services.commercial_service import app as m
    return m, m.app.test_client()


CONTEO = {"id_locacion": 3, "id_sku": 5, "lineas": [{"id_lote": "0f8b6f8e-6a7c-4b1e-9d1a-2b3c4d5e6f70", "cantidad_contada": 4}]}


def test_conteo_ok_pasa_idempotency_key(inv, tokens, monkeypatch):
    m, c = inv
    vistos = {}

    def falso(**kw):
        vistos.update(kw)
        return {"id_conteo": "c-1", "lineas_contadas": 1, "lineas_con_diferencia": 1, "exactitud_pct": 0.0, "ajustes": []}

    monkeypatch.setattr(m.dom_movil, "registrar_conteo", falso)
    r = c.post("/api/v1/inventory/counts", json=CONTEO, headers={**tokens("store_manager"), "Idempotency-Key": "k-1"})
    assert r.status_code == 201, r.data
    assert r.get_json()["id_conteo"] == "c-1"
    assert vistos["idempotency_key"] == "k-1" and vistos["id_locacion"] == 3
    assert vistos["lineas"] == [{"id_lote": CONTEO["lineas"][0]["id_lote"], "cantidad_contada": 4.0}]


def test_conteo_otra_sucursal_403(inv, tokens):
    _, c = inv
    r = c.post("/api/v1/inventory/counts", json={**CONTEO, "id_locacion": 9}, headers=tokens("store_manager", loc=3))
    assert r.status_code == 403 and r.get_json()["error"] == "sucursal_no_autorizada"


def test_conteo_sin_lineas_400(inv, tokens):
    _, c = inv
    r = c.post("/api/v1/inventory/counts", json={"id_locacion": 3, "lineas": []}, headers=tokens("warehouse"))
    assert r.status_code == 400


def test_conteo_cantidad_negativa_400(inv, tokens):
    _, c = inv
    cuerpo = {"id_locacion": 3, "lineas": [{"id_lote": CONTEO["lineas"][0]["id_lote"], "cantidad_contada": -1}]}
    r = c.post("/api/v1/inventory/counts", json=cuerpo, headers=tokens("warehouse"))
    assert r.status_code == 400


def test_conteo_xml_valida_xsd(inv, tokens):
    _, c = inv
    r = c.post("/api/v1/inventory/counts", data=b"<count_request><id_locacion>x</id_locacion></count_request>",
               headers={**tokens("warehouse"), "Content-Type": "application/xml"})
    assert r.status_code == 400 and r.get_json()["error"] == "xml_no_cumple_contrato"


def test_conteo_comprador_403(inv, tokens):
    _, c = inv
    assert c.post("/api/v1/inventory/counts", json=CONTEO, headers=tokens("buyer")).status_code == 403


SOLICITUD = {"id_lote": "0f8b6f8e-6a7c-4b1e-9d1a-2b3c4d5e6f70", "id_locacion_origen": 3, "id_locacion_destino": 4,
             "cantidad": 5, "motivo": "Exceso"}


def test_solicitar_transferencia_201(plan, tokens, monkeypatch):
    m, c = plan
    monkeypatch.setattr(m.dom_movil, "solicitar_transferencia",
                        lambda **kw: {"id_transferencia": "t-1", "estado": "SUGERIDA", "cantidad": kw["cantidad"]})
    r = c.post("/api/v1/planning/transfers", json=SOLICITUD, headers=tokens("store_manager"))
    assert r.status_code == 201, r.data
    assert r.get_json()["estado"] == "SUGERIDA"


def test_solicitar_transferencia_regla_409(plan, tokens, monkeypatch):
    m, c = plan

    def falla(**kw):
        raise ValueError("El lote vence antes de llegar.")

    monkeypatch.setattr(m.dom_movil, "solicitar_transferencia", falla)
    r = c.post("/api/v1/planning/transfers", json=SOLICITUD, headers=tokens("store_manager"))
    assert r.status_code == 409 and "vence" in r.get_json()["mensaje"]


def test_solicitar_transferencia_desde_otra_sucursal_403(plan, tokens):
    _, c = plan
    r = c.post("/api/v1/planning/transfers", json={**SOLICITUD, "id_locacion_origen": 8}, headers=tokens("store_manager", 3))
    assert r.status_code == 403


def test_subir_evidencia_jpeg(com, tokens, monkeypatch):
    m, c = com
    vistos = {}

    def falso(**kw):
        vistos.update(kw)
        return {"id_evidencia": "e-1", "content_type": kw["content_type"], "url_firmada": "https://x", "url_expira_en_segundos": 900}

    monkeypatch.setattr(m.dom_movil, "guardar_evidencia", falso)
    r = c.post("/api/v1/commercial/evidence", headers=tokens("store_manager"), content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(JPEG), "foto.jpg", "image/jpeg"), "tipo": "MERMA",
                     "referencia_tipo": "LOTE", "referencia_id": "abc", "id_locacion": "3"})
    assert r.status_code == 201, r.data
    assert vistos["content_type"] == "image/jpeg" and vistos["tipo"] == "MERMA" and vistos["id_locacion"] == 3


def test_evidencia_rechaza_archivo_que_no_es_imagen(com, tokens):
    _, c = com
    r = c.post("/api/v1/commercial/evidence", headers=tokens("store_manager"), content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(b"%PDF-1.4 x"), "foto.jpg", "image/jpeg"), "tipo": "OTRO"})
    assert r.status_code == 415


def test_evidencia_demasiado_grande_413(com, tokens, monkeypatch):
    m, c = com
    monkeypatch.setattr(m, "MAX_EVIDENCIA_BYTES", 100)
    r = c.post("/api/v1/commercial/evidence", headers=tokens("store_manager"), content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(JPEG + b"0" * 200), "f.jpg"), "tipo": "OTRO"})
    assert r.status_code == 413


def test_evidencia_bucket_caido_503(com, tokens, monkeypatch):
    m, c = com

    def falla(**kw):
        raise object_storage.AlmacenamientoNoDisponible("sin conexión")

    monkeypatch.setattr(m.dom_movil, "guardar_evidencia", falla)
    r = c.post("/api/v1/commercial/evidence", headers=tokens("warehouse"), content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(JPEG), "f.jpg"), "tipo": "OTRO"})
    assert r.status_code == 503 and r.get_json()["error"] == "almacenamiento_no_disponible"


def test_listar_y_url_evidencia(com, tokens, monkeypatch):
    m, c = com
    monkeypatch.setattr(m.dom_movil, "listar_evidencias", lambda id_locacion, limite: [{"id_evidencia": "e-1"}])
    monkeypatch.setattr(m.dom_movil, "evidencia_con_url",
                        lambda id_ev: {"id_evidencia": id_ev, "id_locacion": 3, "url_firmada": "https://firmada"})
    r = c.get("/api/v1/commercial/evidence?id_locacion=3", headers=tokens("store_manager"))
    assert r.status_code == 200 and r.get_json()["total"] == 1
    r = c.get("/api/v1/commercial/evidence/0f8b6f8e-6a7c-4b1e-9d1a-2b3c4d5e6f70/url", headers=tokens("store_manager"))
    assert r.status_code == 200 and r.get_json()["url_firmada"] == "https://firmada"


def test_url_evidencia_de_otra_sucursal_403(com, tokens, monkeypatch):
    m, c = com
    monkeypatch.setattr(m.dom_movil, "evidencia_con_url", lambda id_ev: {"id_evidencia": id_ev, "id_locacion": 9})
    r = c.get("/api/v1/commercial/evidence/0f8b6f8e-6a7c-4b1e-9d1a-2b3c4d5e6f70/url", headers=tokens("store_manager", 3))
    assert r.status_code == 403


def test_foto_de_6mb_cabe_bajo_el_limite_global(com, tokens, monkeypatch):
    """Regresión: MAX_CONTENT_LENGTH global (4 MB) cortaba fotos válidas de hasta 8 MB."""
    m, c = com
    monkeypatch.setattr(m.dom_movil, "guardar_evidencia", lambda **kw: {"id_evidencia": "e-6mb"})
    r = c.post("/api/v1/commercial/evidence", headers=tokens("store_manager"), content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(JPEG + b"0" * (6 * 1024 * 1024)), "f.jpg"), "tipo": "OTRO"})
    assert r.status_code == 201, r.data


def test_cuerpo_excesivo_responde_413_en_espanol(com, tokens):
    _, c = com
    r = c.post("/api/v1/commercial/evidence", headers=tokens("store_manager"), content_type="multipart/form-data",
               data={"archivo": (io.BytesIO(JPEG + b"0" * (10 * 1024 * 1024)), "f.jpg"), "tipo": "OTRO"})
    assert r.status_code == 413
    cuerpo = r.get_json()
    assert cuerpo["error"] == "cuerpo_demasiado_grande" and "MB" in cuerpo["mensaje"] and "capacity" not in cuerpo["mensaje"]
