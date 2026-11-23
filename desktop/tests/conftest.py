"""
Configuración común de pytest para la app de escritorio.

- Qt corre sin pantalla (`QT_QPA_PLATFORM=offscreen`).
- `settings`: un `Settings` con URLs por defecto y `data_dir` aislado en `tmp_path`.
- `fake_http`: servidor HTTP falso (monkeypatch de `requests.Session.request`).

Uso de `fake_http`::

    def test_algo(fake_http, settings):
        fake_http.add("GET", "/api/v1/catalog/productos", body=b"<productos/>")
        fake_http.add("POST", "/api/v1/auth/refresh", status=401, body=XML_ERROR)
        fake_http.add("GET", "/health", body=lambda req: (200, b"<x/>", {}))
        fake_http.add_error("GET", "/api/v1/alerts", requests.ConnectionError("apagado"))
        ...
        fake_http.calls          # lista de FakeRequest (method, url, headers, body, params)
        fake_http.calls_to("POST", "/api/v1/auth/refresh")

Reglas de coincidencia:
- `path` se compara contra el final de la URL sin query string (`url.endswith(path)`),
  así sirve tanto la ruta como la URL completa (`http://localhost:5001/api/v1/...`).
- Si una ruta se registra varias veces, las respuestas se consumen en orden y la
  última se repite (útil para "primero 401, luego 200").
- `body` puede ser bytes, str o un callable `fn(FakeRequest) -> (status, body, headers)`.
- Una petición sin ruta registrada responde 404 con un cuerpo no-XML y queda en `calls`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
import requests  # noqa: E402
from requests.structures import CaseInsensitiveDict  # noqa: E402

from freshtrack_desktop.core.config import Settings  # noqa: E402

FIXTURES_XML = Path(__file__).parent / "fixtures" / "xml"


def muestra(nombre: str) -> bytes:
    """XML real de un servicio guardado en tests/fixtures/xml/<nombre>.xml."""
    return (FIXTURES_XML / f"{nombre}.xml").read_bytes()


@dataclass
class FakeRequest:
    method: str
    url: str
    headers: CaseInsensitiveDict
    body: bytes | None
    params: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        return (self.body or b"").decode("utf-8")


@dataclass
class _Ruta:
    method: str
    path: str
    respuestas: list[Any] = field(default_factory=list)


class FakeHttp:
    """Registro de rutas falsas y de las peticiones recibidas."""

    def __init__(self) -> None:
        self._rutas: list[_Ruta] = []
        self.calls: list[FakeRequest] = []

    # --- registro ---------------------------------------------------------------
    def _ruta(self, method: str, path: str) -> _Ruta:
        method = method.upper()
        for r in self._rutas:
            if r.method == method and r.path == path:
                return r
        r = _Ruta(method, path)
        self._rutas.append(r)
        return r

    def add(
        self,
        method: str,
        path: str,
        status: int = 200,
        body: bytes | str | Callable[[FakeRequest], tuple[int, Any, dict | None]] = b"",
        headers: dict[str, str] | None = None,
    ) -> "FakeHttp":
        """Registra una respuesta (se encolan si la ruta se registra varias veces)."""
        if callable(body):
            self._ruta(method, path).respuestas.append(("fn", body))
        else:
            self._ruta(method, path).respuestas.append(("ok", (status, body, headers)))
        return self

    def add_error(self, method: str, path: str, exc: BaseException) -> "FakeHttp":
        """La petición a esa ruta lanza `exc` (p. ej. requests.ConnectionError)."""
        self._ruta(method, path).respuestas.append(("exc", exc))
        return self

    def calls_to(self, method: str, path: str) -> list[FakeRequest]:
        method = method.upper()
        return [c for c in self.calls if c.method == method and c.url.split("?", 1)[0].endswith(path)]

    # --- despacho ---------------------------------------------------------------
    def _buscar(self, method: str, url: str) -> _Ruta | None:
        sin_query = url.split("?", 1)[0]
        candidatas = [r for r in self._rutas if r.method == method and sin_query.endswith(r.path)]
        # La ruta más específica (más larga) gana.
        return max(candidatas, key=lambda r: len(r.path)) if candidatas else None

    def handle(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        method = method.upper()
        body = kwargs.get("data")
        if isinstance(body, str):
            body = body.encode("utf-8")
        req = FakeRequest(
            method=method,
            url=url,
            headers=CaseInsensitiveDict(kwargs.get("headers") or {}),
            body=body,
            params=kwargs.get("params"),
        )
        self.calls.append(req)
        ruta = self._buscar(method, url)
        if ruta is None or not ruta.respuestas:
            return _respuesta(url, 404, b"no hay ruta falsa registrada", None)
        tipo, valor = ruta.respuestas.pop(0) if len(ruta.respuestas) > 1 else ruta.respuestas[0]
        if tipo == "exc":
            raise valor
        if tipo == "fn":
            status, cuerpo, headers = valor(req)
        else:
            status, cuerpo, headers = valor
        return _respuesta(url, status, cuerpo, headers)


def _respuesta(url: str, status: int, body: Any, headers: dict | None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = body.encode("utf-8") if isinstance(body, str) else (body or b"")
    hdrs = {"Content-Type": "application/xml; charset=utf-8"}
    hdrs.update(headers or {})
    resp.headers = CaseInsensitiveDict(hdrs)
    resp.url = url
    resp.encoding = "utf-8"
    return resp


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> FakeHttp:
    fake = FakeHttp()

    def _request(self, method, url, *args, **kwargs):  # noqa: ANN001
        return fake.handle(method, url, **kwargs)

    monkeypatch.setattr(requests.Session, "request", _request)
    return fake


@pytest.fixture
def settings(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings por defecto (localhost) con data_dir aislado en tmp_path."""
    for var in ("FRESHTRACK_GATEWAY_URL", "FRESHTRACK_HOST"):
        monkeypatch.delenv(var, raising=False)
    return Settings(data_dir=tmp_path / "data")
