"""Endurecimiento de seguridad: revocación completa, permisos, redirecciones, errores y JWT."""

from __future__ import annotations

import time
from contextlib import contextmanager

import jwt
import pytest
from flask import Flask, session

from app import security
from app.config import Config
from app.services import cache_service


# --- JWT ---------------------------------------------------------------------
def _firmar(**claims):
    base = {"sub": "u-1", "rol": "admin", "jti": "j-1", "iat": int(time.time()),
            "exp": int(time.time()) + 600, "iss": "freshtrack"}
    base.update(claims)
    base = {k: v for k, v in base.items() if v is not None}
    return jwt.encode(base, Config.JWT_SECRET_KEY, algorithm="HS256")


@pytest.fixture()
def sesion_bd_ok(monkeypatch, redis_falso):
    monkeypatch.setattr(security, "verificar_sesion_respaldo_bd", lambda jti: True)


def test_jwt_valido_pasa(sesion_bd_ok):
    assert security.decodificar_token(_firmar())["sub"] == "u-1"


@pytest.mark.parametrize("claims", [{"exp": None}, {"jti": None}, {"iss": "otro"}, {"iss": None}])
def test_jwt_sin_claims_obligatorios_o_emisor_ajeno(sesion_bd_ok, claims):
    assert security.decodificar_token(_firmar(**claims)) is None


def test_clave_jwt_no_es_la_de_la_cookie():
    assert Config.JWT_SECRET_KEY != Config.SECRET_KEY


# --- Sesión web ----------------------------------------------------------------
def _app_sesion():
    app = Flask(__name__)
    app.secret_key = "k" * 40
    return app


def test_sesion_web_sin_jti_o_revocada_no_vale(redis_falso):
    app = _app_sesion()
    with app.test_request_context():
        session["user_id"] = "u-1"
        assert security.sesion_web_vigente() is False  # sin jti
        session["jti"] = "j-ok"
        cache_service.crear_sesion_redis("j-ok", {"id_usuario": "u-1"})
        assert security.sesion_web_vigente() is True
        cache_service.revocar_jwt("j-ok")
        assert security.sesion_web_vigente() is False


def test_revocar_sesiones_usuario_llega_a_redis(redis_falso, monkeypatch):
    """Desactivar/restablecer/cambiar rol: la sesión muere también en Redis."""

    class _Res:
        def mappings(self):
            return self

        def all(self):
            return [{"jti": "j-a", "ttl": 3600}, {"jti": "j-b", "ttl": 120}]

    class _Conn:
        def execute(self, *a, **k):
            return _Res()

    @contextmanager
    def _tx(**k):
        yield _Conn()

    monkeypatch.setattr(security, "transaccion", _tx)
    for jti in ("j-a", "j-b"):
        cache_service.crear_sesion_redis(jti, {"id_usuario": "u-9"})
    assert security.revocar_sesiones_usuario("u-9") == 2
    for jti in ("j-a", "j-b"):
        assert cache_service.esta_jwt_revocado(jti)
        assert cache_service.sesion_activa(jti) is False


def test_repo_usuarios_revoca_al_desactivar_y_al_cambiar_rol(monkeypatch):
    from app.repos import catalogo as repo

    revocados = []
    monkeypatch.setattr(repo, "revocar_sesiones_usuario", lambda u: revocados.append(u) or 1)
    monkeypatch.setattr(repo.auditoria, "registrar", lambda *a, **k: None)

    @contextmanager
    def _tx(**k):
        class _C:
            def execute(self, *a, **k):
                return None
        yield _C()

    monkeypatch.setattr(repo, "transaccion", _tx)
    monkeypatch.setattr(repo, "escalar", lambda *a, **k: "planner")  # clave del rol: no supplier
    admin = {"id_usuario": "adm", "email": "admin@x.mx"}

    monkeypatch.setattr(repo, "one", lambda *a, **k: {
        "id_usuario": "u-1", "nombre_completo": "Ana", "email": "ana@x.mx", "estado_activo": True})
    repo.cambiar_estado_usuario("u-1", False, admin)
    repo.restablecer_password("u-1", "NuevaClave2026", admin)
    assert revocados == ["u-1", "u-1"]

    monkeypatch.setattr(repo, "one", lambda *a, **k: {
        "id_usuario": "u-1", "nombre_completo": "Ana", "email": "ana@x.mx", "id_rol": 4, "id_locacion": 3})
    repo.actualizar_usuario("u-1", {"nombre_completo": "Ana", "email": "ana@x.mx", "id_rol": "4", "id_locacion": "3"}, admin)
    assert revocados == ["u-1", "u-1"]  # nada sensible cambió: no se revoca
    repo.actualizar_usuario("u-1", {"nombre_completo": "Ana", "email": "ana@x.mx", "id_rol": "2", "id_locacion": "3"}, admin)
    assert revocados == ["u-1", "u-1", "u-1"]


# --- Redirección abierta -------------------------------------------------------
@pytest.mark.parametrize("destino,ok", [
    ("/panel", True), ("/lotes?pagina=2", True),
    ("//evil.com", False), ("/\\evil.com", False), ("https://evil.com", False), ("panel", False), (None, False),
])
def test_destino_login(destino, ok):
    from app.blueprints.auth import _destino_local_seguro
    assert _destino_local_seguro(destino) is ok


# --- Logs sin secretos y verify solo por cabecera -----------------------------------
def test_ruta_log_oculta_tokens():
    from app.services.common.servicio import _ruta_sin_secretos

    app = Flask(__name__)
    with app.test_request_context("/api/v1/auth/verify?token=abc.def&x=1&Password=p"):
        ruta = _ruta_sin_secretos()
    assert "abc.def" not in ruta and "=p" not in ruta and "x=1" in ruta


def test_verify_rechaza_token_en_query(redis_falso):
    from app.services.auth_service.app import app as svc_auth

    r = svc_auth.test_client().post(f"/api/v1/auth/verify?token={_firmar()}")
    assert r.status_code == 400


# --- Errores sin detalles internos ----------------------------------------------------
def test_sql_error_no_expone_detalles_internos():
    from sqlalchemy.exc import ProgrammingError

    from app.db import sql_error

    class _Orig(Exception):
        sqlstate = "42P01"

        def __str__(self):
            return 'relation "operacion.tabla_secreta" does not exist'

    msg = sql_error(ProgrammingError("SELECT 1", {}, _Orig()))
    assert "tabla_secreta" not in msg and "referencia" in msg

    class _Negocio(Exception):
        sqlstate = "P0001"

        def __str__(self):
            return "Existencia insuficiente para el lote\nCONTEXT: ..."

    assert sql_error(ProgrammingError("x", {}, _Negocio())) == "Existencia insuficiente para el lote"


# --- Bitácora: acciones reservadas ------------------------------------------------------
def test_audit_log_no_permite_acciones_del_sistema(redis_falso, monkeypatch):
    from app.services.audit_service import app as audit_mod
    from app.services.common import auth as auth_mod

    monkeypatch.setattr(auth_mod, "decodificar_token", lambda t: {"sub": "u-1", "rol": "store_manager", "jti": "j-1", "email": "g@x.mx"})
    cache_service.crear_sesion_redis("j-1", {"id_usuario": "u-1"})
    llamadas = []
    monkeypatch.setattr(audit_mod.auditoria, "registrar_desde_request", lambda *a, **k: llamadas.append(a) or "ev-1")
    c = audit_mod.app.test_client()
    h = {"Authorization": "Bearer x"}
    for accion in ("LOGIN_FALLIDO", "APPROVE_REPLENISHMENT", "delete"):
        r = c.post("/api/v1/audit/log", json={"accion": accion, "descripcion": "falso"}, headers=h)
        assert r.status_code == 403, accion
    r = c.post("/api/v1/audit/log", json={"accion": "DESKTOP_EXPORTAR", "descripcion": "ok"}, headers=h)
    assert r.status_code == 201 and len(llamadas) == 1


# --- Rutas web: KPIs y triaje -----------------------------------------------------------
@pytest.fixture()
def web(redis_falso, monkeypatch):
    monkeypatch.setenv("AGREGADOS_AUTO_REFRESCO", "false")
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


def test_kpis_ventana_rechaza_authorization_falso(web):
    c = web.test_client()
    assert c.get("/api/kpis/ventana?dias=30", headers={"Authorization": "x"}).status_code == 401
    assert c.get("/api/kpis/ventana?dias=30", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_kpis_ventana_acota_dias(web, monkeypatch):
    monkeypatch.setattr(security, "sesion_web_vigente", lambda: True)
    assert web.test_client().get("/api/kpis/ventana?dias=99999").status_code == 400


def _login_web(c, rol, id_locacion=3):
    cache_service.crear_sesion_redis("j-web", {"id_usuario": "u-1"})
    with c.session_transaction() as s:
        s.update(user_id="u-1", user_email="u@x.mx", user_name="U", role=rol, role_label=rol,
                 id_locacion=id_locacion, jti="j-web", csrf_token="tok-prueba")


@pytest.mark.parametrize("rol,accion,loc,permitido", [
    ("auditor", "MERMA", 3, False),
    ("buyer", "DESCUENTO", 3, False),
    ("warehouse", "TRASLADO", 3, False),
    ("warehouse", "MERMA", 3, True),
    ("warehouse", "MERMA", 7, False),   # otra sucursal
    ("planner", "TRASLADO", 7, True),
])
def test_triaje_accion_lote_respeta_rol_y_sucursal(web, monkeypatch, rol, accion, loc, permitido):
    from app.blueprints import analitica

    ejecutadas = []
    monkeypatch.setattr(analitica.dom_triaje, "ejecutar_accion_directa_lote",
                        lambda **k: ejecutadas.append(k) or {"mensaje": "ok"})
    monkeypatch.setattr(analitica.motor_alertas, "generar_alertas", lambda *a, **k: None)
    c = web.test_client()
    _login_web(c, rol)
    r = c.post("/triaje/accion-lote", data={"id_lote": "l-1", "tipo_accion": accion, "id_locacion": str(loc),
                                            "csrf_token": "tok-prueba"})
    assert r.status_code == 302
    assert bool(ejecutadas) is permitido
