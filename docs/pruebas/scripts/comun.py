"""
Utilidades compartidas por los simulacros de fallas y las pruebas de sistema.

- Las credenciales de prueba se leen del dict CUENTAS de scripts/smoke_rutas.py
  (sin ejecutar ese script) y nunca se escriben en los reportes.
- Los tokens se ocultan en todo lo que se registra.
- Solo habla con el stack LOCAL (localhost:5000..5008).
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

RAIZ = Path(__file__).resolve().parents[3]
DIR_FALLAS = RAIZ / "docs" / "pruebas" / "fallas"
DIR_SISTEMA = RAIZ / "docs" / "pruebas" / "sistema"

HOST = "http://localhost"
PUERTOS = {"web": 5000, "auth": 5001, "catalog": 5002, "inventory": 5003, "commercial": 5004,
           "asn": 5005, "planning": 5006, "alerts": 5007, "audit": 5008}
CONTENEDORES_APP = ["freshtrack_app"] + [f"freshtrack_svc_{s}" for s in PUERTOS if s != "web"]
CONTENEDORES_INFRA = ["freshtrack_db", "freshtrack_mongo", "freshtrack_redis", "freshtrack_minio", "freshtrack_mail"]


def url(svc: str, ruta: str) -> str:
    return f"{HOST}:{PUERTOS[svc]}{ruta}"


def ahora() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


# ---------------------------------------------------------------------------
# Credenciales
# ---------------------------------------------------------------------------
def cuentas() -> dict[str, tuple[str, str]]:
    fuente = (RAIZ / "scripts" / "smoke_rutas.py").read_text(encoding="utf-8")
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == "CUENTAS" for t in nodo.targets):
            return ast.literal_eval(nodo.value)
    raise RuntimeError("No se encontró CUENTAS en scripts/smoke_rutas.py")


def credenciales_monitor() -> tuple[str, str]:
    def env(nombre: str) -> str:
        return subprocess.run(["docker", "exec", "freshtrack_app", "printenv", nombre],
                              capture_output=True, text=True).stdout.strip()
    return env("MONITOR_USER"), env("MONITOR_PASSWORD")


# ---------------------------------------------------------------------------
# Redacción de secretos
# ---------------------------------------------------------------------------
_RE_JWT = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
_SECRETOS = {"token", "refresh_token", "access_token", "password"}


def redactar(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("***" if k in _SECRETOS and isinstance(v, str) else redactar(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redactar(v) for v in obj]
    if isinstance(obj, str):
        s = _RE_JWT.sub("<JWT-oculto>", obj)
        return re.sub(r"X-Amz-Signature=[0-9a-f]+", "X-Amz-Signature=<oculta>", s)
    return obj


def recortar(texto: str, n: int = 700) -> str:
    return texto if len(texto) <= n else texto[:n] + f"… (+{len(texto) - n} caracteres)"


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Resp(dict):
    """Resultado normalizado de una petición (status 0 = sin respuesta)."""

    @property
    def status(self) -> int:
        return self["status"]

    @property
    def cuerpo(self) -> Any:
        return self.get("json") if self.get("json") is not None else self.get("texto")


def pedir(metodo: str, u: str, *, token: str | None = None, timeout: float = 30, sesion: requests.Session | None = None,
          **kw) -> Resp:
    headers = dict(kw.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    t0 = time.perf_counter()
    cli = sesion or requests
    try:
        r = cli.request(metodo, u, headers=headers, timeout=timeout, **kw)
    except requests.exceptions.Timeout as exc:
        return Resp(status=0, ms=round((time.perf_counter() - t0) * 1000), error=f"TIMEOUT del cliente ({timeout}s): {type(exc).__name__}",
                    metodo=metodo, url=u)
    except requests.exceptions.RequestException as exc:
        return Resp(status=0, ms=round((time.perf_counter() - t0) * 1000), error=f"{type(exc).__name__}: {str(exc)[:160]}",
                    metodo=metodo, url=u)
    ms = round((time.perf_counter() - t0) * 1000)
    out = Resp(status=r.status_code, ms=ms, metodo=metodo, url=u,
               content_type=r.headers.get("Content-Type", ""),
               correlation_id=r.headers.get("X-Correlation-Id"),
               headers={k: v for k, v in r.headers.items() if k.lower().startswith(("x-ratelimit", "retry-after", "x-servicio", "x-service", "location"))},
               bytes=len(r.content))
    try:
        out["json"] = r.json()
    except ValueError:
        ct = out["content_type"]
        if "pdf" in ct or "octet" in ct or "image" in ct:
            out["texto"] = f"<{len(r.content)} bytes binarios {ct}; inicio={r.content[:5]!r}>"
        else:
            out["texto"] = r.text
    return out


def resumen(r: Resp, n: int = 600) -> str:
    """Una línea/párrafo legible para el reporte."""
    if r.status == 0:
        return f"{r['metodo']} {r['url']} → SIN RESPUESTA en {r['ms']} ms ({r.get('error')})"
    cuerpo = r.cuerpo
    if isinstance(cuerpo, (dict, list)):
        txt = json.dumps(redactar(cuerpo), ensure_ascii=False, default=str)
    else:
        txt = redactar(str(cuerpo or ""))
        txt = re.sub(r"\s+", " ", txt)
    cid = f" cid={r.get('correlation_id')}" if r.get("correlation_id") else ""
    extra = f" hdr={r['headers']}" if r.get("headers") else ""
    return f"{r['metodo']} {r['url']} → HTTP {r.status} en {r['ms']} ms{cid}{extra}\n      {recortar(txt, n)}"


def login(rol: str) -> dict:
    email, pwd = cuentas()[rol]
    r = pedir("POST", url("auth", "/api/v1/auth/login"), json={"email": email, "password": pwd})
    if r.status != 200:
        raise RuntimeError(f"login {rol} falló: {resumen(r)}")
    return r["json"]


def sesion_web(rol: str) -> tuple[requests.Session, Resp]:
    """Inicia sesión en la web por formulario (con token CSRF). Devuelve (sesión, respuesta del POST)."""
    email, pwd = cuentas()[rol]
    s = requests.Session()
    g = s.get(url("web", "/login"), timeout=20)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', g.text) or re.search(r'value="([^"]+)"\s+name="csrf_token"', g.text)
    datos = {"email": email, "password": pwd}
    if m:
        datos["csrf_token"] = m.group(1)
    r = pedir("POST", url("web", "/login"), sesion=s, data=datos, allow_redirects=False, timeout=30)
    return s, r


def csrf_de(s: requests.Session, ruta: str) -> str | None:
    g = s.get(url("web", ruta), timeout=30)
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', g.text) or re.search(r'name="csrf_token"\s+value="([^"]+)"', g.text)
    return m.group(1) if m else None


def health_todos(timeout: float = 10) -> dict[str, Resp]:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=9) as pool:
        futs = {s: pool.submit(pedir, "GET", url(s, "/health"), timeout=timeout) for s in PUERTOS}
        return {s: f.result() for s, f in futs.items()}


def tabla_health(h: dict[str, Resp]) -> str:
    filas = []
    for s, r in h.items():
        if r.status == 0:
            filas.append(f"  {s:<11} SIN RESPUESTA ({r.get('error', '')[:60]}) {r['ms']} ms")
        else:
            j = r.get("json") or {}
            filas.append(f"  {s:<11} HTTP {r.status} {j.get('status')} deps={j.get('dependencies')} {r['ms']} ms")
    return "\n".join(filas)


# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
def docker(*args: str) -> str:
    p = subprocess.run(["docker", *args], capture_output=True, text=True)
    return (p.stdout + p.stderr).strip()


def estado_contenedores() -> str:
    return docker("ps", "-a", "--filter", "name=freshtrack_", "--format", "{{.Names}}\t{{.Status}}")


def esperar(cond, limite: float = 180, paso: float = 0.5) -> float | None:
    """Repite cond() hasta que sea verdadera; devuelve los segundos que tardó o None."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < limite:
        try:
            if cond():
                return round(time.monotonic() - t0, 1)
        except Exception:
            pass
        time.sleep(paso)
    return None


def todo_sano() -> bool:
    return all(r.status == 200 for r in health_todos(timeout=6).values())


def contenedores_sanos() -> bool:
    salida = estado_contenedores()
    return all("(healthy)" in linea for linea in salida.splitlines() if linea.strip())


# ---------------------------------------------------------------------------
# Bitácora de un simulacro
# ---------------------------------------------------------------------------
class Bitacora:
    def __init__(self, nombre: str, carpeta: Path = DIR_FALLAS):
        carpeta.mkdir(parents=True, exist_ok=True)
        self.ruta = carpeta / f"{nombre}.txt"
        self.f = self.ruta.open("w", encoding="utf-8")
        self.datos: dict[str, Any] = {}

    def __call__(self, *lineas: str) -> None:
        for linea in lineas:
            texto = redactar(linea)
            print(texto, flush=True)
            self.f.write(texto + "\n")
        self.f.flush()

    def paso(self, titulo: str) -> None:
        self(f"\n[{ahora()}] ### {titulo}")

    def http(self, etiqueta: str, r: Resp, n: int = 600) -> Resp:
        self(f"  - {etiqueta}: {resumen(r, n)}")
        return r

    def cerrar(self) -> None:
        self.f.close()
