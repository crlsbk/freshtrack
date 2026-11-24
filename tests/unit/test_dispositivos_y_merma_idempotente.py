"""Registro seguro de dispositivos (svc-auth) y merma idempotente (svc-commercial) para la app Android."""

from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from sqlalchemy.exc import IntegrityError

from app.config import Config
from app.domain import dispositivos as dom_disp
from app.domain import mermas as dom_mermas
from app.services import cache_service
from app.services.common import auth as auth_mod

RAIZ = Path(__file__).resolve().parents[2]
DISP = "3f6c1d2e-8a9b-4c0d-9e1f-2a3b4c5d6e7f"
LOTE = "0f8b6f8e-6a7c-4b1e-9d1a-2b3c4d5e6f70"
U1 = "11111111-1111-1111-1111-111111111111"


@pytest.fixture()
def tokens(redis_falso, monkeypatch):
    def decodificar(token):
        try:
            return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None

    monkeypatch.setattr(auth_mod, "decodificar_token", decodificar)
    cache_service.crear_sesion_redis("jti-disp", {"id_usuario": U1})

    def auth(rol, loc=3, sub=U1):
        tok = jwt.encode({"sub": sub, "rol": rol, "email": "g@freshtrack.mx", "jti": "jti-disp", "id_locacion": loc},
                         Config.JWT_SECRET_KEY, algorithm="HS256")
        return {"Authorization": f"Bearer {tok}"}

    return auth


@pytest.fixture()
def auth_svc(tokens):
    from app.services.auth_service import app as m
    return m, m.app.test_client()


@pytest.fixture()
def com(tokens):
    from app.services.commercial_service import app as m
    return m, m.app.test_client()


# --- Dispositivos -------------------------------------------------------------------
def test_registrar_dispositivo_ligado_al_usuario_del_jwt(auth_svc, tokens, monkeypatch):
    m, c = auth_svc
    vistos = {}

    def falso(**kw):
        vistos.update(kw)
        return {"id_registro": "r-1", "id_dispositivo": kw["id_dispositivo"], "nuevo": True, "estado": "REGISTRADO"}

    monkeypatch.setattr(m.dom_dispositivos, "registrar", falso)
    cuerpo = {"id_dispositivo": DISP, "modelo": "Pixel 8", "version_so": "15", "version_app": "1.3.0",
              "id_usuario": "22222222-2222-2222-2222-222222222222"}  # se ignora: manda el JWT
    r = c.post("/api/v1/auth/devices", json=cuerpo, headers=tokens("store_manager"))
    assert r.status_code == 201, r.data
    assert vistos["usuario"]["id_usuario"] == U1 and vistos["id_dispositivo"] == DISP
    assert vistos["modelo"] == "Pixel 8"


def test_registrar_dispositivo_existente_200(auth_svc, tokens, monkeypatch):
    m, c = auth_svc
    monkeypatch.setattr(m.dom_dispositivos, "registrar",
                        lambda **kw: {"id_registro": "r-1", "id_dispositivo": DISP, "nuevo": False, "estado": "REGISTRADO"})
    assert c.post("/api/v1/auth/devices", json={"id_dispositivo": DISP}, headers=tokens("warehouse")).status_code == 200


def test_dispositivo_revocado_403(auth_svc, tokens, monkeypatch):
    m, c = auth_svc

    def revocado(**kw):
        raise dom_disp.DispositivoRevocado("Este dispositivo fue revocado por un administrador.")

    monkeypatch.setattr(m.dom_dispositivos, "registrar", revocado)
    r = c.post("/api/v1/auth/devices", json={"id_dispositivo": DISP}, headers=tokens("store_manager"))
    assert r.status_code == 403 and r.get_json()["error"] == "dispositivo_revocado"


def test_dispositivo_id_invalido_400_y_sin_token_401(auth_svc, tokens):
    _, c = auth_svc
    assert c.post("/api/v1/auth/devices", json={"id_dispositivo": "no-uuid"}, headers=tokens("admin")).status_code == 400
    assert c.post("/api/v1/auth/devices", json={"id_dispositivo": DISP}).status_code == 401


def test_dispositivo_xml_valida_xsd(auth_svc, tokens):
    _, c = auth_svc
    r = c.post("/api/v1/auth/devices", data=b"<device_register_request><id_dispositivo>x</id_dispositivo></device_register_request>",
               headers={**tokens("admin"), "Content-Type": "application/xml"})
    assert r.status_code == 400 and r.get_json()["error"] == "xml_no_cumple_contrato"


def test_listar_dispositivos_propios_o_admin(auth_svc, tokens, monkeypatch):
    m, c = auth_svc
    vistos = []
    monkeypatch.setattr(m.dom_dispositivos, "listar", lambda **kw: vistos.append(kw) or [])
    otro = "22222222-2222-2222-2222-222222222222"
    c.get(f"/api/v1/auth/devices?id_usuario={otro}", headers=tokens("store_manager"))
    c.get(f"/api/v1/auth/devices?id_usuario={otro}", headers=tokens("admin"))
    c.get("/api/v1/auth/devices", headers=tokens("admin"))
    assert vistos == [{"id_usuario": U1}, {"id_usuario": otro}, {"id_usuario": None}]


def test_revocar_solo_admin(auth_svc, tokens, monkeypatch):
    m, c = auth_svc
    monkeypatch.setattr(m.dom_dispositivos, "revocar",
                        lambda id_registro, admin, ip=None: {"id_registro": id_registro, "id_usuario": U1, "revocado": True})
    ruta = f"/api/v1/auth/devices/{DISP}/revoke"
    assert c.post(ruta, headers=tokens("store_manager")).status_code == 403
    r = c.post(ruta, headers=tokens("admin"))
    assert r.status_code == 200 and r.get_json()["revocado"] is True
    monkeypatch.setattr(m.dom_dispositivos, "revocar", lambda *a, **k: None)
    assert c.post(ruta, headers=tokens("admin")).status_code == 404


def test_texto_de_dispositivo_se_sanea():
    assert dom_disp._texto("<script>Pixel 8</script>\n", 120) == "scriptPixel 8/script"
    assert dom_disp._texto("x" * 300, 40) == "x" * 40
    assert dom_disp._texto("   ", 40) is None


def test_sql_13_idempotente_y_en_bootstrap():
    sql = (RAIZ / "sql" / "13_dispositivos_idempotencia.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS operacion.dispositivo_movil" in sql
    assert "ADD COLUMN IF NOT EXISTS idempotency_key" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_merma_idempotency_key" in sql
    assert "13_dispositivos_idempotencia.sql" in (RAIZ / "scripts" / "bootstrap_db.py").read_text(encoding="utf-8")


# --- Merma idempotente -----------------------------------------------------------------
MERMA = {"id_lote": LOTE, "id_locacion": 3, "cantidad": 2, "causa": "DANO"}


def test_merma_pasa_idempotency_key_y_201(com, tokens, monkeypatch):
    m, c = com
    vistos = {}

    def falso(**kw):
        vistos.update(kw)
        return {"id_merma": "m-1", "cantidad": 2.0}

    monkeypatch.setattr(m.dom_mermas, "registrar_merma", falso)
    r = c.post("/api/v1/commercial/shrinkage", json=MERMA, headers={**tokens("store_manager"), "Idempotency-Key": "k-1"})
    assert r.status_code == 201, r.data
    assert vistos["idempotency_key"] == "k-1"


def test_merma_repetida_devuelve_200_sin_volver_a_ligar(com, tokens, monkeypatch):
    m, c = com
    monkeypatch.setattr(m.dom_mermas, "registrar_merma", lambda **kw: {"id_merma": "m-1", "repetido": True})
    ligadas = []
    monkeypatch.setattr(m.dom_movil, "ligar_evidencia_a_merma", lambda *a: ligadas.append(a))
    r = c.post("/api/v1/commercial/shrinkage", json={**MERMA, "id_evidencia": DISP},
               headers={**tokens("store_manager"), "Idempotency-Key": "k-1"})
    assert r.status_code == 200 and r.get_json()["repetido"] is True
    assert ligadas == []


def test_merma_envio_simultaneo_unique_devuelve_la_previa(com, tokens, monkeypatch):
    m, c = com

    def choque(**kw):
        raise IntegrityError("INSERT", {}, Exception("uq_merma_idempotency_key"))

    monkeypatch.setattr(m.dom_mermas, "registrar_merma", choque)
    monkeypatch.setattr(m.dom_mermas, "merma_por_idempotencia", lambda k: {"id_merma": "m-1", "repetido": True})
    r = c.post("/api/v1/commercial/shrinkage", json=MERMA, headers={**tokens("store_manager"), "Idempotency-Key": "k-2"})
    assert r.status_code == 200 and r.get_json()["id_merma"] == "m-1"


def test_dominio_merma_repetida_no_toca_inventario(monkeypatch):
    monkeypatch.setattr(dom_mermas, "merma_por_idempotencia", lambda k: {"id_merma": "m-9", "repetido": True})

    def no_debe_abrir_transaccion(*a, **k):
        raise AssertionError("no debe escribir en la base")

    monkeypatch.setattr(dom_mermas, "transaccion", no_debe_abrir_transaccion)
    res = dom_mermas.registrar_merma(id_lote=LOTE, id_locacion=3, cantidad=1, causa="DANO", observacion=None,
                                     usuario={"id_usuario": U1, "email": "g@x.mx"}, idempotency_key="k-9")
    assert res == {"id_merma": "m-9", "repetido": True}
