"""
Cliente HTTP de la app: solo XML, con contratos XSD, X-Correlation-Id y sesión JWT.

- Toda respuesta XML cuya raíz tenga `contracts/xsd/<raiz>.xsd` se valida contra él.
- Todo cuerpo de petición se valida antes de enviarse contra `body_xsd` y, si existe,
  contra `contracts/xsd/<body_root>.xsd` (status 0 en el XmlContractError: no salió a la red).
- El Inspector XML recibe la contraseña y el token enmascarados (`***`).
- Toda petición lleva Accept: application/xml (o application/pdf en `get_bytes`),
  X-Correlation-Id (uuid4 hex) y User-Agent FreshTrack-Desktop/1.0.
- 401 fuera de /auth/login, /auth/refresh, /auth/logout y /health → un refresh y un
  reintento; si el servidor rechaza la sesión se cierra y se avisa con `on_unauthorized()`
  una sola vez (solo si la sesión vigente sigue siendo la del token que falló).
- `on_unauthorized` y los listeners corren en el hilo que hizo la petición: la UI debe
  reenviarlos al hilo principal (señal Qt).
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

import requests

from .config import Settings
from .errors import ApiError, ServiceUnavailable, XmlContractError
from .session import Session
from .xml_codec import has_xsd, parse_xml, to_xml, validate

USER_AGENT = "FreshTrack-Desktop/1.0"
CT_XML = "application/xml; charset=utf-8"
_RUTAS_SIN_REFRESH = ("/auth/login", "/auth/refresh")
_RE_PASSWORD = re.compile(r"(<password>).*?(</password>)", re.S)
_RE_TOKEN = re.compile(r"(<(token|refresh_token)>).*?(</\2>)", re.S)


@dataclass
class Exchange:
    method: str
    url: str
    status: int
    request_xml: str
    response_text: str
    correlation_id: str
    elapsed_ms: float


class ApiClient:
    def __init__(self, settings: Settings, *, on_unauthorized: Callable[[], None] = lambda: None) -> None:
        self.settings = settings
        self.on_unauthorized = on_unauthorized
        self.session: Session | None = None
        self.listeners: list[Callable[[Exchange], None]] = []
        self._http = requests.Session()
        self._lock_sesion = threading.Lock()

    # ------------------------------------------------------------------ público
    def login(self, email: str, password: str) -> Session:
        cuerpo = to_xml({"email": email, "password": password}, "login_request")
        validate(cuerpo, "login_request")
        datos = self._ejecutar("auth", "POST", "/api/v1/auth/login", data=cuerpo,
                               expect_root="auth_response", con_token=False, reintentar=False)
        self.session = Session.from_auth_response(datos)
        return self.session

    def logout(self) -> None:
        """Revoca el token en el servidor (si se puede) y siempre limpia la sesión local."""
        try:
            if self.session is not None:
                self._ejecutar("auth", "POST", "/api/v1/auth/logout", reintentar=False)
        except ApiError:
            pass
        finally:
            # Bajo el candado: un refresh en curso no puede «resucitar» la sesión después.
            with self._lock_sesion:
                self.session = None

    def refresh(self) -> bool:
        """Renueva el JWT. False si no hay sesión, el servidor lo rechaza o auth no responde."""
        try:
            return self._refresh(None)
        except ApiError:
            return False

    def call(
        self,
        service: str,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: Any = None,
        body_root: str | None = None,
        body_xsd: str | None = None,
        expect_root: str | None = None,
        response_xsd: str | None = None,
    ) -> Any:
        data: bytes | None = None
        if body is not None:
            if isinstance(body, (bytes, str)):
                data = body.encode("utf-8") if isinstance(body, str) else body
            else:
                if not body_root:
                    raise ValueError("body_root es obligatorio cuando body es un dict")
                data = to_xml(body, body_root)
            if body_xsd:
                validate(data, body_xsd)
            if body_root and body_root != body_xsd and has_xsd(body_root):
                validate(data, body_root)
        return self._ejecutar(service, method, path, params=params, data=data,
                              expect_root=expect_root, response_xsd=response_xsd)

    def get_bytes(self, service: str, path: str, params: dict | None = None) -> bytes:
        return self._ejecutar(service, "GET", path, params=params, accept="application/pdf", binario=True)

    def health(self, service: str) -> dict:
        inicio = time.perf_counter()
        # /health no requiere auth: sin Authorization y sin lógica de 401/refresh.
        datos = self._ejecutar(service, "GET", "/health", expect_root="service_health",
                               con_token=False, reintentar=False, estados_ok={503})
        resultado = dict(datos) if isinstance(datos, dict) else {"valor": datos}
        resultado["elapsed_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
        return resultado

    # ------------------------------------------------------------------ interno
    def _url(self, service: str, path: str) -> str:
        try:
            base = self.settings.base_urls[service]
        except KeyError:
            raise ValueError(f"Servicio desconocido: {service}") from None
        return base.rstrip("/") + "/" + path.lstrip("/")

    def _ejecutar(
        self,
        service: str,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: bytes | None = None,
        expect_root: str | None = None,
        response_xsd: str | None = None,
        accept: str = "application/xml",
        con_token: bool = True,
        reintentar: bool = True,
        binario: bool = False,
        estados_ok: set[int] | None = None,
    ) -> Any:
        token_usado = self.session.token if (con_token and self.session) else None
        resp, cid = self._enviar(service, method, path, params, data, accept, token_usado)
        try:
            if binario and resp.status_code < 400:
                return resp.content
            return self._decodificar(resp, service, cid, expect_root, response_xsd, estados_ok or set())
        except XmlContractError:
            raise  # un 401 con cuerpo no XML (proxy con auth propia) no intenta refresh
        except ApiError as exc:
            if exc.status != 401 or not con_token or path.rstrip("/").endswith(_RUTAS_SIN_REFRESH):
                raise
            if path.rstrip("/").endswith("/auth/logout"):
                raise
            if reintentar and self._refresh(token_usado):
                return self._ejecutar(service, method, path, params=params, data=data, expect_root=expect_root,
                                      response_xsd=response_xsd, accept=accept, con_token=con_token,
                                      reintentar=False, binario=binario, estados_ok=estados_ok)
            self._expirar(token_usado)
            raise

    def _enviar(self, service, method, path, params, data, accept, token):
        url = self._url(service, path)
        cid = uuid.uuid4().hex
        headers = {"Accept": accept, "X-Correlation-Id": cid, "User-Agent": USER_AGENT}
        if data is not None:
            headers["Content-Type"] = CT_XML
        if token:
            headers["Authorization"] = f"Bearer {token}"
        inicio = time.perf_counter()
        try:
            resp = self._http.request(method.upper(), url, params=params, data=data,
                                      headers=headers, timeout=self.settings.timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            self._notificar(Exchange(method.upper(), url, 0, self._texto_peticion(data), str(exc), cid,
                                     (time.perf_counter() - inicio) * 1000))
            raise ServiceUnavailable(service, correlation_id=cid, detalles=str(exc)) from exc
        except requests.RequestException as exc:
            raise ServiceUnavailable(service, f"Servicio {service} no disponible: {exc}", cid, str(exc)) from exc
        elapsed = (time.perf_counter() - inicio) * 1000
        ctype = resp.headers.get("Content-Type", "")
        if "pdf" in ctype.lower() or resp.content.startswith(b"%PDF"):
            texto = f"<{len(resp.content)} bytes {ctype}>"
        else:
            texto = _RE_TOKEN.sub(r"\1***\3", resp.content.decode("utf-8", errors="replace"))
        self._notificar(Exchange(method.upper(), url, resp.status_code, self._texto_peticion(data),
                                 texto, cid, elapsed))
        return resp, cid

    @staticmethod
    def _texto_peticion(data: bytes | None) -> str:
        if not data:
            return ""
        return _RE_PASSWORD.sub(r"\1***\2", data.decode("utf-8", errors="replace"))

    def _notificar(self, ex: Exchange) -> None:
        for fn in list(self.listeners):
            try:
                fn(ex)
            except Exception:  # un listener roto no debe tumbar la petición
                pass

    def _decodificar(self, resp, service, cid, expect_root, response_xsd, estados_ok) -> Any:
        status = resp.status_code
        if not resp.content and status < 400:
            return None
        try:
            raiz, valor = parse_xml(resp.content)
        except XmlContractError as exc:
            muestra = resp.content[:200].decode("utf-8", errors="replace")
            raise XmlContractError(
                f"El servicio {service} respondió algo que no es XML (HTTP {status}).",
                exc.detalles + [f"inicio de la respuesta: {muestra}"],
                status=status, correlation_id=cid,
            ) from exc

        # Toda respuesta cuya raíz tenga contracts/xsd/<raiz>.xsd se valida contra él.
        if has_xsd(raiz):
            self._validar_respuesta(resp.content, raiz, status, cid)
        if response_xsd and response_xsd != raiz:
            self._validar_respuesta(resp.content, response_xsd, status, cid)

        if raiz == "error_response":
            v = valor if isinstance(valor, dict) else {}
            try:
                st = int(v.get("status") or status)
            except (TypeError, ValueError):
                st = status
            raise ApiError(st, str(v.get("error") or "error"), str(v.get("mensaje") or f"HTTP {status}"),
                           str(v.get("correlation_id") or cid), v.get("detalles"))
        if status >= 400 and status not in estados_ok:
            raise ApiError(status, "error_http", f"El servicio {service} respondió HTTP {status}.", cid)
        if expect_root and raiz != expect_root:
            raise XmlContractError(
                f"Se esperaba la raíz <{expect_root}> y llegó <{raiz}>.",
                [f"raíz recibida: {raiz}"], status=status, correlation_id=cid,
            )
        return valor

    @staticmethod
    def _validar_respuesta(contenido: bytes, xsd: str, status: int, cid: str) -> None:
        try:
            validate(contenido, xsd)
        except XmlContractError as exc:
            exc.status, exc.correlation_id = status, cid
            raise

    def _refresh(self, token_fallido: str | None) -> bool:
        """
        Renueva el JWT bajo candado. True → hay un token vigente distinto del que falló
        (renovado aquí o por otro hilo): reintentar. False → el servidor rechazó la
        sesión (401/403) o ya no hay sesión. Otros errores (auth caído, 429, 5xx, XML
        inválido) se propagan sin cerrar la sesión.
        """
        with self._lock_sesion:
            if self.session is None:
                return False  # logout voluntario u otro hilo ya expiró la sesión
            if token_fallido and self.session.token != token_fallido:
                return True  # otro hilo ya renovó: reintentar con el token nuevo
            try:
                datos = self._ejecutar("auth", "POST", "/api/v1/auth/refresh",
                                       expect_root="auth_response", reintentar=False)
            except XmlContractError:
                raise
            except ApiError as exc:
                if exc.status in (401, 403):
                    return False
                raise
            nueva = Session.from_auth_response(datos)
            if not nueva.token:
                raise XmlContractError("La renovación del token no devolvió <token>.", ["token vacío"],
                                       status=200)
            self.session = nueva
            return True

    def _expirar(self, token_fallido: str | None) -> None:
        """Cierra la sesión y avisa una sola vez, solo si sigue vigente la del token que falló."""
        with self._lock_sesion:
            if self.session is None or self.session.token != token_fallido:
                return  # ya expirada, cerrada por logout o renovada por otro hilo
            self.session = None
        try:
            self.on_unauthorized()
        except Exception:
            pass
