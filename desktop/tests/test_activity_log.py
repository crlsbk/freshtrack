from __future__ import annotations

import json

from freshtrack_desktop.core.activity_log import ActivityLog
from freshtrack_desktop.core.api_client import ApiClient
from freshtrack_desktop.core.session import Session

AUTH_OK = b"""<?xml version="1.0" encoding="UTF-8"?>
<log_creado><id_evento>abc</id_evento><status>REGISTRADO</status></log_creado>"""


def test_record_escribe_y_tail_lee(tmp_path):
    log = ActivityLog(tmp_path / "actividad.log")
    log.set_user("buyer@freshtrack.mx")
    log.record("login", "Inicio de sesión")
    log.record("exportar_csv", "Órdenes exportadas", ok=False)
    filas = log.tail()
    assert [f["accion"] for f in filas] == ["login", "exportar_csv"]
    assert filas[0]["usuario"] == "buyer@freshtrack.mx"
    assert filas[0]["ok"] is True and filas[1]["ok"] is False
    assert filas[1]["detalle"] == "Órdenes exportadas"
    assert "T" in filas[0]["ts"]
    lineas = (tmp_path / "actividad.log").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2 and json.loads(lineas[0])["accion"] == "login"
    log.close()


def test_tail_limita(tmp_path):
    log = ActivityLog(tmp_path / "a.log")
    for i in range(10):
        log.record("accion", f"d{i}")
    assert [f["detalle"] for f in log.tail(3)] == ["d7", "d8", "d9"]
    log.close()


def _api_con_sesion(settings) -> ApiClient:
    api = ApiClient(settings)
    api.session = Session(token="tok", jti="j", usuario={"rol": "buyer", "email": "b@f.mx"}, expira_en=0)
    return api


def test_sync_remote_envia_pendientes(tmp_path, settings, fake_http):
    fake_http.add("POST", "/api/v1/audit/log", status=201, body=AUTH_OK)
    log = ActivityLog(tmp_path / "a.log")
    log.set_user("b@f.mx")
    log.record("exportar csv!", "x" * 800)
    log.record("ok", "")
    api = _api_con_sesion(settings)
    log.sync_remote(api)
    calls = fake_http.calls_to("POST", "/api/v1/audit/log")
    assert len(calls) == 2
    assert calls[0].url.startswith("http://localhost:5008")
    assert "<accion>DESKTOP_EXPORTAR_CSV_</accion>" in calls[0].text
    assert "<tabla>desktop</tabla>" in calls[0].text
    # Ya no quedan pendientes.
    log.sync_remote(api)
    assert len(fake_http.calls_to("POST", "/api/v1/audit/log")) == 2
    log.close()


def test_sync_remote_no_propaga_errores(tmp_path, settings, fake_http):
    import requests

    fake_http.add_error("POST", "/api/v1/audit/log", requests.ConnectionError("apagado"))
    log = ActivityLog(tmp_path / "a.log")
    log.set_user("b@f.mx")
    log.record("login", "x")
    log.sync_remote(_api_con_sesion(settings))  # no lanza
    log.close()


def test_sync_remote_descarta_rechazos_definitivos(tmp_path, settings, fake_http):
    error = b"""<error_response><error>validacion</error><mensaje>x</mensaje><status>400</status>
<correlation_id>c</correlation_id></error_response>"""
    fake_http.add("POST", "/api/v1/audit/log", status=400, body=error)
    fake_http.add("POST", "/api/v1/audit/log", status=201, body=AUTH_OK)
    log = ActivityLog(tmp_path / "a.log")
    log.set_user("b@f.mx")
    log.record("uno", "rechazado")
    log.record("dos", "aceptado")
    assert log.sync_remote(_api_con_sesion(settings)) == 1
    assert len(fake_http.calls_to("POST", "/api/v1/audit/log")) == 2
    log.sync_remote(_api_con_sesion(settings))
    assert len(fake_http.calls_to("POST", "/api/v1/audit/log")) == 2
    log.close()


def test_sync_remote_conserva_pendientes_si_servicio_caido(tmp_path, settings, fake_http):
    import requests

    fake_http.add_error("POST", "/api/v1/audit/log", requests.ConnectionError("apagado"))
    fake_http.add("POST", "/api/v1/audit/log", status=201, body=AUTH_OK)
    log = ActivityLog(tmp_path / "a.log")
    log.set_user("b@f.mx")
    log.record("login", "x")
    assert log.sync_remote(_api_con_sesion(settings)) == 0
    assert log.sync_remote(_api_con_sesion(settings)) == 1
    log.close()


def test_sync_remote_solo_envia_las_acciones_del_usuario_de_la_sesion(tmp_path, settings, fake_http):
    """Planner con token revocado → login de buyer: lo del planner no se registra a nombre de buyer."""
    fake_http.add("POST", "/api/v1/audit/log", status=201, body=AUTH_OK)
    log = ActivityLog(tmp_path / "a.log")
    log.set_user("planner@f.mx")
    log.record("APROBAR_ORDEN", "aprobada: orden 1")
    log.set_user(None)
    log.record("LOGIN", "intento fallido")
    log.set_user("B@F.mx")
    log.record("LOGIN", "Inicio de sesión como buyer")
    assert log.sync_remote(_api_con_sesion(settings)) == 1  # sesión de b@f.mx
    (call,) = fake_http.calls_to("POST", "/api/v1/audit/log")
    assert "Inicio de sesión como buyer" in call.text
    # Las otras se descartan de la cola (no se reintentan) pero siguen en el archivo local.
    assert log.sync_remote(_api_con_sesion(settings)) == 0
    assert len(fake_http.calls_to("POST", "/api/v1/audit/log")) == 1
    assert [f["usuario"] for f in log.tail()] == ["planner@f.mx", "", "B@F.mx"]
    log.close()
