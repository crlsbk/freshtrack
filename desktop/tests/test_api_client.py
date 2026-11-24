from __future__ import annotations

import re
from typing import Any

import pytest
import requests

from freshtrack_desktop.core.api_client import ApiClient, Exchange
from freshtrack_desktop.core.config import Settings
from freshtrack_desktop.core.errors import ApiError, ServiceUnavailable, XmlContractError
from freshtrack_desktop.core.session import Session


def auth_xml(token="tok-1", rol="buyer") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<auth_response><token>{token}</token><jti>jti-{token}</jti><token_type>Bearer</token_type>
<expira_en_segundos>28800</expira_en_segundos>
<usuario><id_usuario>4</id_usuario><email>u@freshtrack.mx</email><nombre>Usuario</nombre>
<rol>{rol}</rol><id_locacion>1</id_locacion></usuario></auth_response>""".encode()


def error_xml(status: int, codigo: str, mensaje: str = "Mensaje") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<error_response><error>{codigo}</error><mensaje>{mensaje}</mensaje><status>{status}</status>
<correlation_id>cid-servidor</correlation_id></error_response>""".encode()


PRODUCTOS = b"""<?xml version="1.0" encoding="UTF-8"?>
<productos><total>1</total><productos><item><id_sku>1</id_sku></item></productos></productos>"""

HEALTH = b"""<?xml version="1.0" encoding="UTF-8"?>
<service_health><service>catalog</service><status>HEALTHY</status><version>1.0.0</version>
<dependencies><postgres>true</postgres><redis>true</redis></dependencies></service_health>"""


@pytest.fixture
def api(settings) -> ApiClient:
    return ApiClient(settings)


def _con_sesion(api: ApiClient, token="tok-viejo") -> ApiClient:
    api.session = Session(token=token, jti="j", usuario={"rol": "buyer"}, expira_en=0)
    return api


# --- login / sesión --------------------------------------------------------------
def test_login_crea_sesion_y_envia_xml(api, fake_http):
    fake_http.add("POST", "/api/v1/auth/login", body=auth_xml())
    s = api.login("u@freshtrack.mx", "secreta")
    assert isinstance(s, Session) and api.session is s
    assert s.token == "tok-1" and s.rol == "buyer" and s.usuario["email"] == "u@freshtrack.mx"
    (call,) = fake_http.calls
    assert call.url == "http://localhost:5001/api/v1/auth/login"
    assert call.headers["Content-Type"] == "application/xml; charset=utf-8"
    assert "<login_request>" in call.text and "<password>secreta</password>" in call.text
    assert "Authorization" not in call.headers


def test_login_con_rol_warehouse_devuelve_sesion(api, fake_http):
    fake_http.add("POST", "/api/v1/auth/login", body=auth_xml(rol="warehouse"))
    s = api.login("w@freshtrack.mx", "x")
    assert s.rol == "warehouse"
    assert not s.can("buyer", "planner")


def test_login_invalido_no_sale_a_la_red(api, fake_http):
    with pytest.raises(XmlContractError):
        api.login("no-es-correo", "x")
    assert fake_http.calls == []


def test_login_401_no_intenta_refresh(api, fake_http):
    fake_http.add("POST", "/api/v1/auth/login", status=401, body=error_xml(401, "credenciales_invalidas"))
    with pytest.raises(ApiError) as exc:
        api.login("u@freshtrack.mx", "mala")
    assert exc.value.status == 401 and exc.value.error == "credenciales_invalidas"
    assert fake_http.calls_to("POST", "/api/v1/auth/refresh") == []


def test_session_can():
    admin = Session(token="t", jti="j", usuario={"rol": "admin"}, expira_en=0)
    planner = Session(token="t", jti="j", usuario={"rol": "planner"}, expira_en=0)
    assert admin.can("buyer") and admin.can()
    assert planner.can("planner", "buyer") and not planner.can("buyer")
    assert Session.DESKTOP_ROLES == {"buyer", "planner", "admin"}


def test_logout_limpia_sesion_aunque_falle(api, fake_http):
    _con_sesion(api)
    fake_http.add_error("POST", "/api/v1/auth/logout", requests.ConnectionError("x"))
    api.logout()
    assert api.session is None


# --- call: cabeceras y errores ------------------------------------------------------
def test_todas_las_peticiones_llevan_cabeceras(api, fake_http):
    fake_http.add("POST", "/api/v1/auth/login", body=auth_xml())
    fake_http.add("GET", "/api/v1/catalog/productos", body=PRODUCTOS)
    fake_http.add("GET", "/health", body=HEALTH)
    api.login("u@freshtrack.mx", "x")
    valor = api.call("catalog", "GET", "/api/v1/catalog/productos", params={"pagina": 1}, expect_root="productos")
    assert valor["productos"] == [{"id_sku": "1"}]
    api.health("catalog")
    assert len(fake_http.calls) == 3
    cids = set()
    for c in fake_http.calls:
        assert c.headers["Accept"] == "application/xml"
        assert c.headers["User-Agent"] == "FreshTrack-Desktop/1.0"
        assert re.fullmatch(r"[0-9a-f]{32}", c.headers["X-Correlation-Id"])
        cids.add(c.headers["X-Correlation-Id"])
    assert len(cids) == 3
    assert fake_http.calls[1].headers["Authorization"] == "Bearer tok-1"
    assert fake_http.calls[1].params == {"pagina": 1}
    assert fake_http.calls[1].url == "http://localhost:5002/api/v1/catalog/productos"


def test_call_con_cuerpo_valida_y_serializa(api, fake_http):
    _con_sesion(api)
    fake_http.add("POST", "/api/v1/audit/log", status=201, body=b"<log_creado><status>OK</status></log_creado>")
    body = {"accion": "DESKTOP_X", "tabla": "desktop", "descripcion": "hola"}
    v = api.call("audit", "POST", "/api/v1/audit/log", body=body, body_root="audit_log_request",
                 body_xsd="audit_log_request", expect_root="log_creado")
    assert v == {"status": "OK"}
    assert "<audit_log_request>" in fake_http.calls[0].text
    with pytest.raises(XmlContractError):
        api.call("audit", "POST", "/api/v1/audit/log", body={"accion": "x"}, body_root="audit_log_request",
                 body_xsd="audit_log_request")
    assert len(fake_http.calls) == 1


def test_html_como_respuesta_es_error_de_contrato(api, fake_http):
    _con_sesion(api)
    fake_http.add("GET", "/api/v1/catalog/productos", status=502,
                  body=b"<html><head><title>502</title></head><body>Bad Gateway<br></body></html>",
                  headers={"Content-Type": "text/html"})
    with pytest.raises(XmlContractError) as exc:
        api.call("catalog", "GET", "/api/v1/catalog/productos")
    assert exc.value.error == "xml_invalido"


def test_json_como_respuesta_es_error_de_contrato(api, fake_http):
    _con_sesion(api)
    fake_http.add("GET", "/api/v1/catalog/productos", body=b'{"productos": []}',
                  headers={"Content-Type": "application/json"})
    with pytest.raises(XmlContractError):
        api.call("catalog", "GET", "/api/v1/catalog/productos")


def test_error_response_403_es_api_error(api, fake_http):
    _con_sesion(api)
    fake_http.add("GET", "/api/v1/planning/forecast", status=403, body=error_xml(403, "acceso_denegado", "Sin permiso"))
    with pytest.raises(ApiError) as exc:
        api.call("planning", "GET", "/api/v1/planning/forecast")
    e = exc.value
    assert not isinstance(e, XmlContractError)
    assert (e.status, e.error, e.mensaje, e.correlation_id) == (403, "acceso_denegado", "Sin permiso", "cid-servidor")


def test_expect_root_distinto_es_error_de_contrato(api, fake_http):
    _con_sesion(api)
    fake_http.add("GET", "/api/v1/catalog/productos", body=PRODUCTOS)
    with pytest.raises(XmlContractError):
        api.call("catalog", "GET", "/api/v1/catalog/productos", expect_root="ordenes")


def test_connection_error_es_servicio_no_disponible(api, fake_http):
    _con_sesion(api)
    fake_http.add_error("GET", "/api/v1/alerts/alertas", requests.ConnectionError("rechazada"))
    with pytest.raises(ServiceUnavailable) as exc:
        api.call("alerts", "GET", "/api/v1/alerts/alertas")
    e = exc.value
    assert isinstance(e, ApiError)
    assert e.status == 0 and e.error == "servicio_no_disponible" and e.service == "alerts"


def test_timeout_es_servicio_no_disponible(api, fake_http):
    fake_http.add_error("GET", "/health", requests.Timeout("lento"))
    with pytest.raises(ServiceUnavailable):
        api.health("inventory")


# --- 401 y refresh ---------------------------------------------------------------
def test_401_refresh_ok_reintenta(api, fake_http):
    _con_sesion(api)
    fake_http.add("GET", "/api/v1/catalog/productos", status=401, body=error_xml(401, "token_invalido"))
    fake_http.add("GET", "/api/v1/catalog/productos", body=PRODUCTOS)
    fake_http.add("POST", "/api/v1/auth/refresh", body=auth_xml(token="tok-nuevo"))
    avisos = []
    api.on_unauthorized = lambda: avisos.append(1)
    valor = api.call("catalog", "GET", "/api/v1/catalog/productos")
    assert valor["total"] == "1"
    llamadas = fake_http.calls_to("GET", "/api/v1/catalog/productos")
    assert len(llamadas) == 2
    assert llamadas[0].headers["Authorization"] == "Bearer tok-viejo"
    assert llamadas[1].headers["Authorization"] == "Bearer tok-nuevo"
    refresh = fake_http.calls_to("POST", "/api/v1/auth/refresh")
    assert len(refresh) == 1 and refresh[0].headers["Authorization"] == "Bearer tok-viejo"
    assert api.session.token == "tok-nuevo" and avisos == []


def test_401_refresh_401_cierra_sesion(settings, fake_http):
    avisos = []
    api = _con_sesion(ApiClient(settings, on_unauthorized=lambda: avisos.append(1)))
    fake_http.add("GET", "/api/v1/catalog/productos", status=401, body=error_xml(401, "token_revocado"))
    fake_http.add("POST", "/api/v1/auth/refresh", status=401, body=error_xml(401, "token_revocado"))
    with pytest.raises(ApiError) as exc:
        api.call("catalog", "GET", "/api/v1/catalog/productos")
    assert exc.value.status == 401
    assert api.session is None
    assert avisos == [1]
    assert len(fake_http.calls_to("GET", "/api/v1/catalog/productos")) == 1
    assert len(fake_http.calls_to("POST", "/api/v1/auth/refresh")) == 1


def test_401_tras_refresh_ok_cierra_sesion(settings, fake_http):
    avisos = []
    api = _con_sesion(ApiClient(settings, on_unauthorized=lambda: avisos.append(1)))
    fake_http.add("GET", "/api/v1/catalog/productos", status=401, body=error_xml(401, "token_revocado"))
    fake_http.add("POST", "/api/v1/auth/refresh", body=auth_xml(token="tok-nuevo"))
    with pytest.raises(ApiError):
        api.call("catalog", "GET", "/api/v1/catalog/productos")
    assert len(fake_http.calls_to("GET", "/api/v1/catalog/productos")) == 2
    assert api.session is None and avisos == [1]


def test_refresh_sin_sesion_devuelve_false(api, fake_http):
    assert api.refresh() is False
    assert fake_http.calls == []


# --- health, bytes, listeners, config ----------------------------------------------
def test_health_devuelve_dict_con_elapsed(api, fake_http):
    fake_http.add("GET", "/health", body=HEALTH)
    h = api.health("catalog")
    assert h["service"] == "catalog" and h["status"] == "HEALTHY"
    assert h["dependencies"] == {"postgres": "true", "redis": "true"}
    assert isinstance(h["elapsed_ms"], float)
    assert fake_http.calls[0].url == "http://localhost:5002/health"


def test_health_degradado_503_no_es_error(api, fake_http):
    fake_http.add("GET", "/health", status=503, body=HEALTH.replace(b"HEALTHY", b"DEGRADED"))
    assert api.health("catalog")["status"] == "DEGRADED"


def test_get_bytes_pdf(api, fake_http):
    _con_sesion(api)
    fake_http.add("GET", "/api/v1/asn/1/etiqueta", body=b"%PDF-1.4 ...", headers={"Content-Type": "application/pdf"})
    assert api.get_bytes("asn", "/api/v1/asn/1/etiqueta").startswith(b"%PDF")
    assert fake_http.calls[0].headers["Accept"] == "application/pdf"
    assert "X-Correlation-Id" in fake_http.calls[0].headers


def test_get_bytes_error_xml(api, fake_http):
    _con_sesion(api)
    fake_http.add("GET", "/api/v1/asn/9/etiqueta", status=404, body=error_xml(404, "no_encontrado"))
    with pytest.raises(ApiError) as exc:
        api.get_bytes("asn", "/api/v1/asn/9/etiqueta")
    assert exc.value.status == 404


def test_listeners_reciben_exchange_sin_password(api, fake_http):
    vistos: list[Exchange] = []
    api.listeners.append(vistos.append)
    fake_http.add("POST", "/api/v1/auth/login", body=auth_xml())
    api.login("u@freshtrack.mx", "secreta")
    (ex,) = vistos
    assert ex.method == "POST" and ex.status == 200 and ex.url.endswith("/api/v1/auth/login")
    assert "secreta" not in ex.request_xml and "<login_request>" in ex.request_xml
    assert "<auth_response>" in ex.response_text
    assert re.fullmatch(r"[0-9a-f]{32}", ex.correlation_id) and ex.elapsed_ms >= 0


def test_settings_gateway_y_host(tmp_path, monkeypatch):
    monkeypatch.delenv("FRESHTRACK_HOST", raising=False)
    monkeypatch.setenv("FRESHTRACK_GATEWAY_URL", "https://freshtrack.example.com/")
    s = Settings.load(data_dir=tmp_path)
    assert set(s.base_urls) == {"auth", "catalog", "inventory", "commercial", "asn", "planning", "alerts", "audit"}
    assert all(u == "https://freshtrack.example.com" for u in s.base_urls.values())
    monkeypatch.delenv("FRESHTRACK_GATEWAY_URL")
    monkeypatch.setenv("FRESHTRACK_HOST", "10.0.0.5")
    s = Settings.load(data_dir=tmp_path)
    assert s.base_urls["audit"] == "http://10.0.0.5:5008"


def test_settings_save_y_load(tmp_path, monkeypatch):
    monkeypatch.delenv("FRESHTRACK_HOST", raising=False)
    monkeypatch.delenv("FRESHTRACK_GATEWAY_URL", raising=False)
    s = Settings(data_dir=tmp_path)
    s.set_servers(host="http://192.168.1.20")
    s.timeout = 7
    s.save()
    assert (tmp_path / "config.ini").exists()
    t = Settings.load(data_dir=tmp_path)
    assert t.base_urls["auth"] == "http://192.168.1.20:5001" and t.timeout == 7


def test_xsd_dir(monkeypatch, tmp_path):
    from freshtrack_desktop.core.config import xsd_dir

    monkeypatch.delenv("FRESHTRACK_XSD_DIR", raising=False)
    assert (xsd_dir() / "login_request.xsd").exists()
    monkeypatch.setenv("FRESHTRACK_XSD_DIR", str(tmp_path))
    assert xsd_dir() == tmp_path


# --- corrección ronda 1: on_unauthorized una sola vez, refresh y health ---------------
import threading  # noqa: E402


def _dos_hilos(api: ApiClient, path: str) -> list[BaseException | Any]:
    resultados: list = [None, None]

    def trabajo(i: int) -> None:
        try:
            resultados[i] = api.call("catalog", "GET", path)
        except BaseException as exc:  # noqa: BLE001
            resultados[i] = exc

    hilos = [threading.Thread(target=trabajo, args=(i,)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(10)
    return resultados


def _401_sincronizado(barrera: threading.Barrier):
    """Ambos hilos reciben 401 con tok-viejo antes de que cualquiera intente refrescar."""

    def fn(req):
        if req.headers.get("Authorization") == "Bearer tok-viejo":
            barrera.wait(5)
            return 401, error_xml(401, "token_revocado"), None
        return 200, PRODUCTOS, None

    return fn


def test_dos_hilos_con_401_y_refresh_fallido_avisan_una_vez(settings, fake_http):
    avisos = []
    api = _con_sesion(ApiClient(settings, on_unauthorized=lambda: avisos.append(1)))
    fake_http.add("GET", "/api/v1/catalog/productos", body=_401_sincronizado(threading.Barrier(2)))
    fake_http.add("POST", "/api/v1/auth/refresh", status=401, body=error_xml(401, "token_revocado"))
    resultados = _dos_hilos(api, "/api/v1/catalog/productos")
    assert all(isinstance(r, ApiError) and r.status == 401 for r in resultados)
    assert avisos == [1]
    assert api.session is None
    assert len(fake_http.calls_to("POST", "/api/v1/auth/refresh")) == 1


def test_dos_hilos_con_401_refrescan_una_vez_y_reintentan(settings, fake_http):
    avisos = []
    api = _con_sesion(ApiClient(settings, on_unauthorized=lambda: avisos.append(1)))
    fake_http.add("GET", "/api/v1/catalog/productos", body=_401_sincronizado(threading.Barrier(2)))
    fake_http.add("POST", "/api/v1/auth/refresh", body=auth_xml(token="tok-nuevo"))
    resultados = _dos_hilos(api, "/api/v1/catalog/productos")
    assert all(isinstance(r, dict) and r["total"] == "1" for r in resultados)
    assert len(fake_http.calls_to("POST", "/api/v1/auth/refresh")) == 1
    reintentos = [c for c in fake_http.calls_to("GET", "/api/v1/catalog/productos")
                  if c.headers["Authorization"] == "Bearer tok-nuevo"]
    assert len(reintentos) == 2
    assert avisos == [] and api.session.token == "tok-nuevo"


def test_logout_con_peticion_en_curso_no_avisa(settings, fake_http):
    avisos = []
    api = _con_sesion(ApiClient(settings, on_unauthorized=lambda: avisos.append(1)))
    fake_http.add("POST", "/api/v1/auth/logout", body=auth_xml())

    def en_vuelo(req):
        api.logout()  # el usuario cierra sesión mientras la petición está en el aire
        return 401, error_xml(401, "token_revocado"), None

    fake_http.add("GET", "/api/v1/catalog/productos", body=en_vuelo)
    with pytest.raises(ApiError) as exc:
        api.call("catalog", "GET", "/api/v1/catalog/productos")
    assert exc.value.status == 401
    assert avisos == [] and api.session is None
    assert fake_http.calls_to("POST", "/api/v1/auth/refresh") == []


@pytest.mark.parametrize("status,body,tipo", [
    (429, error_xml(429, "demasiadas_peticiones"), ApiError),
    (500, error_xml(500, "error_interno"), ApiError),
    (502, b"<html><body>Bad Gateway<br></body></html>", XmlContractError),
])
def test_refresh_con_error_transitorio_no_expira(settings, fake_http, status, body, tipo):
    avisos = []
    api = _con_sesion(ApiClient(settings, on_unauthorized=lambda: avisos.append(1)))
    fake_http.add("GET", "/api/v1/catalog/productos", status=401, body=error_xml(401, "token_invalido"))
    fake_http.add("POST", "/api/v1/auth/refresh", status=status, body=body)
    with pytest.raises(tipo) as exc:
        api.call("catalog", "GET", "/api/v1/catalog/productos")
    assert exc.value.status == status
    assert api.session is not None and api.session.token == "tok-viejo"
    assert avisos == []


def test_refresh_403_expira(settings, fake_http):
    avisos = []
    api = _con_sesion(ApiClient(settings, on_unauthorized=lambda: avisos.append(1)))
    fake_http.add("GET", "/api/v1/catalog/productos", status=401, body=error_xml(401, "token_invalido"))
    fake_http.add("POST", "/api/v1/auth/refresh", status=403, body=error_xml(403, "usuario_inactivo"))
    with pytest.raises(ApiError):
        api.call("catalog", "GET", "/api/v1/catalog/productos")
    assert api.session is None and avisos == [1]


def test_refresh_publico_con_error_devuelve_false(api, fake_http):
    _con_sesion(api)
    fake_http.add("POST", "/api/v1/auth/refresh", status=500, body=error_xml(500, "error_interno"))
    assert api.refresh() is False
    assert api.session is not None


def test_health_401_no_expira_ni_manda_token(settings, fake_http):
    avisos = []
    api = _con_sesion(ApiClient(settings, on_unauthorized=lambda: avisos.append(1)))
    fake_http.add("GET", "/health", status=401, body=error_xml(401, "token_requerido"))
    with pytest.raises(ApiError) as exc:
        api.health("catalog")
    assert exc.value.status == 401
    assert "Authorization" not in fake_http.calls[0].headers
    assert api.session is not None and avisos == []
    assert fake_http.calls_to("POST", "/api/v1/auth/refresh") == []


# --- enmascarado del token y validación automática de peticiones ---------------------
def test_inspector_enmascara_token_de_la_respuesta(api, fake_http):
    vistos: list[Exchange] = []
    api.listeners.append(vistos.append)
    fake_http.add("POST", "/api/v1/auth/login", body=auth_xml(token="jwt-secreto"))
    fake_http.add("POST", "/api/v1/auth/refresh",
                  body=auth_xml(token="jwt-nuevo").replace(b"</jti>", b"</jti><refresh_token>rt-1</refresh_token>"))
    api.login("u@freshtrack.mx", "secreta")
    assert api.session.token == "jwt-secreto"  # la sesión conserva el token real
    assert api.refresh() and api.session.token == "jwt-nuevo"
    for ex in vistos:
        assert "<token>jwt-secreto</token>" not in ex.response_text
        assert "<token>jwt-nuevo</token>" not in ex.response_text and "rt-1" not in ex.response_text
        assert "<token>***</token>" in ex.response_text
    assert "<refresh_token>***</refresh_token>" in vistos[1].response_text


def test_call_valida_el_cuerpo_contra_el_xsd_de_su_raiz(api, fake_http):
    _con_sesion(api)
    fake_http.add("POST", "/api/v1/planning/replenishment/generate", status=201,
                  body=b"<resultado><total>0</total></resultado>")
    api.call("planning", "POST", "/api/v1/planning/replenishment/generate",
             body={"horizonte": 7}, body_root="replenishment_request")
    with pytest.raises(XmlContractError) as exc:
        api.call("planning", "POST", "/api/v1/planning/replenishment/generate",
                 body={"horizonte": 0}, body_root="replenishment_request")
    assert exc.value.status == 0 and "replenishment_request.xsd" in exc.value.mensaje
    assert len(fake_http.calls_to("POST", "/api/v1/planning/replenishment/generate")) == 1


def test_call_sin_xsd_para_la_raiz_no_valida(api, fake_http):
    _con_sesion(api)
    fake_http.add("POST", "/api/v1/x", body=b"<ok/>")
    api.call("planning", "POST", "/api/v1/x", body={"a": 1}, body_root="raiz_sin_contrato")
    assert len(fake_http.calls) == 1


@pytest.mark.parametrize("root,cuerpo,malo", [
    ("purchase_order_request",
     {"id_proveedor": 2, "lineas": [{"id_sku": 1, "id_locacion_destino": 3, "cantidad_lotes": 2}],
      "observaciones": "Entrega matutina"},
     {"id_proveedor": 2, "lineas": []}),
    ("send_email_request", {"correo": "ventas@proveedor.mx"}, {"correo": "no-es-correo"}),
    ("newsvendor_request", {"id_sku": 1, "id_locacion": 3, "horizonte": 7}, {"id_sku": 1, "id_locacion": 3}),
    ("rechazo_request", {"motivo": "Sin espacio en bodega"}, {"motivo": ""}),
    ("replenishment_request", {"horizonte": 7}, {"horizonte": 91}),
    ("planning_cycle_request", {"horizonte": 7}, {"horizonte": -1}),
    ("transfers_detect_request", {"horizonte": 14}, {"horizonte": "x"}),
    ("discounts_generate_request", {"dias_hasta": 0}, {"dias_hasta": 61}),
])
def test_xsd_de_peticion_aceptan_lo_que_envia_la_app(root, cuerpo, malo):
    from freshtrack_desktop.core.xml_codec import has_xsd, to_xml, validate

    assert has_xsd(root)
    validate(to_xml(cuerpo, root), root)
    with pytest.raises(XmlContractError):
        validate(to_xml(malo, root), root)


def test_logout_toma_el_candado_de_sesion(api, fake_http):
    """Un refresh en curso (con el candado tomado) no puede «resucitar» la sesión tras el logout."""
    import threading

    _con_sesion(api)
    fake_http.add("POST", "/api/v1/auth/logout", body=b"")
    terminado = threading.Event()
    with api._lock_sesion:
        hilo = threading.Thread(target=lambda: (api.logout(), terminado.set()))
        hilo.start()
        assert not terminado.wait(0.3)  # espera al candado
        assert api.session is not None
    hilo.join(2)
    assert terminado.is_set() and api.session is None


def test_401_refresh_usa_el_refresh_token_y_lo_rota(api, fake_http):
    """Con refresh token: se envía en <refresh_request> (sirve aunque el access ya expiró) y se rota."""
    api.session = Session(token="tok-viejo", jti="jti-viejo", usuario={"rol": "buyer"},
                          refresh_token="rt-viejo-" + "a" * 30)
    fake_http.add("GET", "/api/v1/catalog/productos", status=401, body=error_xml(401, "token_invalido"))
    fake_http.add("GET", "/api/v1/catalog/productos", body=PRODUCTOS)
    nuevo = auth_xml(token="tok-nuevo").replace(
        b"</auth_response>",
        b"<refresh_token>rt-nuevo-" + b"b" * 30 + b"</refresh_token>"
        b"<refresh_expira_en_segundos>27000</refresh_expira_en_segundos></auth_response>",
    )
    fake_http.add("POST", "/api/v1/auth/refresh", body=nuevo)
    api.call("catalog", "GET", "/api/v1/catalog/productos")
    refresh = fake_http.calls_to("POST", "/api/v1/auth/refresh")
    assert len(refresh) == 1
    assert "<refresh_request><refresh_token>rt-viejo-" in refresh[0].text
    assert api.session.token == "tok-nuevo"
    assert api.session.refresh_token == "rt-nuevo-" + "b" * 30
    assert api.session.refresh_expira_en > 0
