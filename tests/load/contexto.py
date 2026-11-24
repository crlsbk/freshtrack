"""
Estado compartido de la prueba de carga (lado Locust).

  * Contexto descubierto por el runner antes de la corrida (tests/load → JSON):
    cuentas del pool por rol y sucursal, tiendas, existencias por tienda, ASN,
    órdenes de compra e intervenciones (descuentos aprobados / traslados
    ejecutados). Así la prueba solo pide recursos que existen.
  * Sesión por usuario virtual: login real en svc-auth, renovación con el
    refresh token antes de que venza el access (15 min), login web con CSRF.
  * Petición instrumentada: clasifica la respuesta (analisis.clasificar),
    marca éxito/fallo en Locust y la registra en el Colector por segundo/fase.

Ninguna contraseña ni token se escribe en disco.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from tests.load import analisis

RUN_ID = os.getenv("LOCUST_RUN_ID", "manual")
USER_AGENT = f"FreshTrack-Locust/{RUN_ID}"
PASSWORD_POOL = os.getenv("LOCUST_PASSWORD_POOL", "")
MARGEN_RENOVACION_S = 60
_RE_CSRF = re.compile(r'name="csrf_token" value="([^"]+)"')
_RE_META_CSRF = re.compile(r'<meta name="csrf-token" content="([^"]+)"')


# --- Contexto descubierto ------------------------------------------------------
def _cargar_contexto() -> dict:
    ruta = os.getenv("LOCUST_CONTEXTO")
    if not ruta or not Path(ruta).is_file():
        return {}
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


CONTEXTO: dict = _cargar_contexto()
SERVICIOS: dict[str, str] = CONTEXTO.get("servicios") or {}

# Intervenciones vivas por tienda (id_locacion → set de SKUs). Las descubre el
# runner y las amplía en vivo el perfil CicloRescate.
_intervenciones: dict[int, set[int]] = defaultdict(set)
for _loc, _skus in (CONTEXTO.get("intervenciones") or {}).items():
    _intervenciones[int(_loc)].update(int(s) for s in _skus)
_lock_interv = threading.Lock()


def registrar_intervencion(id_locacion: int, id_sku: int) -> None:
    with _lock_interv:
        _intervenciones[int(id_locacion)].add(int(id_sku))


def skus_intervenidos(id_locacion: int) -> list[int]:
    with _lock_interv:
        return list(_intervenciones.get(int(id_locacion), ()))


def stock(id_locacion: int) -> list[dict]:
    return (CONTEXTO.get("stock") or {}).get(str(id_locacion)) or []


# --- Reparto de cuentas ----------------------------------------------------------
_lock_cuentas = threading.Lock()
_ciclos: dict[str, itertools.cycle] = {}


def tomar_cuenta(roles: tuple[str, ...], solo_con_stock: bool = False) -> dict | None:
    """Siguiente cuenta del pool (rotación) para los roles dados."""
    clave = ",".join(roles) + ("|stock" if solo_con_stock else "")
    with _lock_cuentas:
        if clave not in _ciclos:
            pool = [c | {"rol": r} for r in roles for c in (CONTEXTO.get("pool") or {}).get(r, [])]
            if solo_con_stock:
                pool = [c for c in pool if stock(c.get("id_locacion") or 0)]
            if not pool:
                return None
            random.Random(RUN_ID + clave).shuffle(pool)
            _ciclos[clave] = itertools.cycle(pool)
        return next(_ciclos[clave])


def url(servicio: str, ruta: str) -> str:
    """URL de un microservicio: relativa al host (gateway Caddy) o base propia (local)."""
    base = SERVICIOS.get(servicio)
    return f"{base.rstrip('/')}{ruta}" if base else ruta


# --- Petición instrumentada ---------------------------------------------------------
class Medicion:
    """Lo fija el locustfile: colector, inicio de la prueba, fases y conteo de usuarios."""

    colector = analisis.Colector()
    t0: float | None = None
    fases: tuple[analisis.Fase, ...] = ()
    usuarios = staticmethod(lambda: 0)

    @classmethod
    def fase_actual(cls, ahora: float) -> tuple[str, int]:
        if cls.t0 is None:
            return "PREPARACION", 0
        t = ahora - cls.t0
        if not cls.fases:
            return "MANUAL", int(t)
        info = analisis.fase_en(cls.fases, t)
        return (info[0].nombre if info else cls.fases[-1].nombre), int(t)


def pedir(user, metodo: str, destino: str, nombre: str, *, esperar_json: bool = False, **kw):
    """
    Hace la petición con catch_response, la clasifica y la registra.
    Devuelve (status, cuerpo_json_o_None, texto).
    """
    headers = {"User-Agent": USER_AGENT, **(kw.pop("headers", None) or {})}
    inicio = time.time()
    t_ini = time.perf_counter()
    status, datos, texto, excepcion = 0, None, "", None
    with user.client.request(metodo, destino, name=nombre, headers=headers, catch_response=True,
                             timeout=kw.pop("timeout", 60), **kw) as resp:
        ms = (time.perf_counter() - t_ini) * 1000.0
        status = resp.status_code or 0
        excepcion = getattr(resp, "error", None) if not status else None
        texto = resp.text if status else ""
        clase = analisis.clasificar(status, excepcion)
        mensaje = ""
        if clase in ("ok", "negocio"):
            resp.success()
        else:
            mensaje = _mensaje_error(texto) or (str(excepcion)[:120] if excepcion else "")
            resp.failure(f"{clase} {status} {mensaje}".strip())
        if esperar_json and status and texto:
            try:
                datos = resp.json()
            except ValueError:
                datos = None
    fase, segundo = Medicion.fase_actual(inicio)
    Medicion.colector.registrar(
        segundo=segundo, fase=fase, vus=Medicion.usuarios(), metodo=metodo.upper(), nombre=nombre,
        ms=ms, status=status, clase=clase, tam=len(texto or ""), mensaje=mensaje,
    )
    return status, datos, texto


def _mensaje_error(texto: str) -> str:
    try:
        datos = json.loads(texto)
        return str(datos.get("error") or datos.get("mensaje") or "")[:120]
    except (ValueError, AttributeError):
        m = re.search(r"<error>([^<]+)</error>", texto or "")
        return m.group(1)[:120] if m else ""


# --- Sesiones ------------------------------------------------------------------------------
class SesionApi:
    """Sesión JWT de un usuario virtual: login, renovación con refresh token y cabeceras."""

    def __init__(self, user, cuenta: dict) -> None:
        self.user = user
        self.cuenta = cuenta
        self.token = ""
        self.refresh_token = ""
        self.vence = 0.0

    def iniciar(self) -> bool:
        for intento in range(4):
            st, datos, _ = pedir(
                self.user, "POST", url("auth", "/api/v1/auth/login"), "/api/v1/auth/login",
                json={"email": self.cuenta["email"], "password": PASSWORD_POOL}, esperar_json=True,
            )
            if st == 200 and datos:
                self._guardar(datos)
                return True
            if st != 429:
                return False
            time.sleep(15 * (intento + 1))  # límite de login: esperar y reintentar
        return False

    def _guardar(self, datos: dict) -> None:
        self.token = datos["token"]
        self.refresh_token = datos.get("refresh_token") or ""
        self.vence = time.time() + float(datos.get("expira_en_segundos") or 900)

    def cabeceras(self, accept: str = "application/json") -> dict:
        if self.vence - time.time() < MARGEN_RENOVACION_S:
            self.renovar()
        return {"Authorization": f"Bearer {self.token}", "Accept": accept}

    def renovar(self) -> None:
        if self.refresh_token:
            st, datos, _ = pedir(
                self.user, "POST", url("auth", "/api/v1/auth/refresh"), "/api/v1/auth/refresh",
                json={"refresh_token": self.refresh_token}, esperar_json=True,
            )
            if st == 200 and datos:
                self._guardar(datos)
                return
        self.iniciar()  # refresh rechazado o sin refresh: nuevo login

    @property
    def id_locacion(self) -> int | None:
        return self.cuenta.get("id_locacion")

    @property
    def rol(self) -> str:
        return self.cuenta.get("rol", "")


class SesionWeb:
    """Sesión del sitio web (cookie del cliente HTTP del usuario virtual + CSRF)."""

    def __init__(self, user, cuenta: dict) -> None:
        self.user = user
        self.cuenta = cuenta
        self.csrf = ""

    def iniciar(self) -> bool:
        for intento in range(4):
            _, _, html = pedir(self.user, "GET", "/login", "/login [GET]")
            m = _RE_CSRF.search(html or "")
            if not m:
                return False
            st, _, html = pedir(
                self.user, "POST", "/login", "/login [POST]",
                data={"email": self.cuenta["email"], "password": PASSWORD_POOL, "csrf_token": m.group(1)},
                allow_redirects=True,
            )
            # Éxito: tras la redirección ya no se ve el formulario de contraseña.
            if st == 200 and 'type="password"' not in (html or ""):
                self.actualizar_csrf(html)
                return True
            if st != 429:
                return False
            time.sleep(15 * (intento + 1))
        return False

    def actualizar_csrf(self, html: str) -> None:
        m = _RE_META_CSRF.search(html or "")
        if m:
            self.csrf = m.group(1)

    @property
    def rol(self) -> str:
        return self.cuenta.get("rol", "")
