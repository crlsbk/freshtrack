#!/usr/bin/env python3
"""
scripts/check_planeador.py — Revisión en vivo del flujo del Planeador por HTTP real.

A diferencia de verify_*.py (que usan el test_client de Flask), este script pega
contra los contenedores levantados con `docker compose up`, igual que curl:

  1. /health de cada microservicio del planeador en JSON y en XML.
  2. Login del planeador en JSON y en XML (contrato login_request.xsd).
  3. Inspección del JWT: header, claims, vigencia y firma HS256 con JWT_SECRET_KEY.
  4. Redis: session:{jti} con su TTL, último evento de freshtrack:events.
  5. Endpoints del planeador (pronóstico, reabastecimiento, KPIs, ESG) en JSON y XML.
  6. Seguridad: sin token -> 401, token alterado -> 401, rol ajeno -> 403.
  7. Logout: jwt:denylist:{jti} en Redis y rechazo 401 token_revocado.

Solo usa la biblioteca estándar (no hace falta jq ni el .venv). Redis se consulta
con `docker exec freshtrack_redis redis-cli` o con un redis-cli local.

Uso:
  python scripts/check_planeador.py               # resumen
  python scripts/check_planeador.py -v            # imprime los cuerpos JSON/XML
  python scripts/check_planeador.py --host 192.168.1.20
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.dom.minidom
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

EMAIL = "planner@freshtrack.mx"
PASSWORD = "Plan2026!"

PUERTOS = {"auth": 5001, "catalog": 5002, "inventory": 5003, "planning": 5006, "alerts": 5007}

VERDE, ROJO, AMARILLO, GRIS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
if not sys.stdout.isatty():
    VERDE = ROJO = AMARILLO = GRIS = FIN = ""

resultados: list[tuple[str, bool]] = []
VERBOSO = False


# --- utilidades ----------------------------------------------------------------
def leer_env() -> dict[str, str]:
    """Lee .env sin depender de python-dotenv; el entorno del proceso tiene prioridad."""
    valores: dict[str, str] = {}
    archivo = RAIZ / ".env"
    if archivo.is_file():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip().strip('"').strip("'")
    valores.update({k: v for k, v in os.environ.items() if k in valores or k.startswith(("REDIS_", "JWT_"))})
    return valores


def seccion(titulo: str) -> None:
    print(f"\n{'=' * 72}\n  {titulo}\n{'=' * 72}")


def check(nombre: str, ok: bool, detalle: str = "") -> bool:
    marca = f"{VERDE}[OK]{FIN}" if ok else f"{ROJO}[FALLA]{FIN}"
    print(f"  {marca} {nombre}" + (f"  {GRIS}{detalle}{FIN}" if detalle else ""))
    resultados.append((nombre, ok))
    return ok


def mostrar(cuerpo: str, es_xml: bool) -> None:
    if not VERBOSO or not cuerpo:
        return
    try:
        if es_xml:
            texto = xml.dom.minidom.parseString(cuerpo).toprettyxml(indent="  ")
            texto = "\n".join(l for l in texto.splitlines() if l.strip())
        else:
            texto = json.dumps(json.loads(cuerpo), indent=2, ensure_ascii=False)
    except Exception:
        texto = cuerpo
    lineas = texto.splitlines()
    if len(lineas) > 40:
        lineas = lineas[:40] + [f"... ({len(lineas) - 40} líneas más)"]
    print("\n".join(f"      {GRIS}{l}{FIN}" for l in lineas))


def http(metodo: str, url: str, *, token: str | None = None, cuerpo: str | None = None,
         content_type: str = "application/json", accept: str = "application/json") -> tuple[int, str, str]:
    """Devuelve (status, content-type, cuerpo). Nunca lanza por códigos 4xx/5xx."""
    headers = {"Accept": accept, "X-Correlation-Id": f"check-planeador-{int(time.time())}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    datos = None
    if cuerpo is not None:
        datos = cuerpo.encode("utf-8")
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=datos, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8")
    except (urllib.error.URLError, OSError) as e:
        return 0, "", str(e)


def es_xml_valido(cuerpo: str) -> bool:
    try:
        xml.dom.minidom.parseString(cuerpo)
        return True
    except Exception:
        return False


def es_json_valido(cuerpo: str) -> bool:
    try:
        json.loads(cuerpo)
        return True
    except Exception:
        return False


def par_json_xml(nombre: str, metodo: str, url: str, token: str | None, cuerpo_json: dict | None = None,
                 cuerpo_xml: str | None = None, esperado: int = 200) -> dict | None:
    """Hace la misma petición pidiendo JSON y luego XML; comprueba status y formato."""
    st, ct, body = http(metodo, url, token=token, cuerpo=json.dumps(cuerpo_json) if cuerpo_json is not None else None)
    check(f"{nombre} [JSON]", st == esperado and "json" in ct and es_json_valido(body), f"HTTP {st} {ct}")
    mostrar(body, es_xml=False)
    datos = json.loads(body) if es_json_valido(body) else None

    if cuerpo_xml is not None:
        st, ct, body = http(metodo, url, token=token, cuerpo=cuerpo_xml, content_type="application/xml", accept="application/xml")
    else:
        st, ct, body = http(metodo, url, token=token, cuerpo=json.dumps(cuerpo_json) if cuerpo_json is not None else None,
                            accept="application/xml")
    check(f"{nombre} [XML]", st == esperado and "xml" in ct and es_xml_valido(body), f"HTTP {st} {ct}")
    mostrar(body, es_xml=True)
    return datos


# --- JWT -----------------------------------------------------------------------
def b64url(segmento: str) -> bytes:
    return base64.urlsafe_b64decode(segmento + "=" * (-len(segmento) % 4))


def inspeccionar_jwt(token: str, secreto: str | None) -> dict:
    header_b64, payload_b64, firma_b64 = token.split(".")
    header = json.loads(b64url(header_b64))
    payload = json.loads(b64url(payload_b64))
    print(f"  header : {json.dumps(header)}")
    print(f"  claims : {json.dumps(payload, ensure_ascii=False)}")

    check("Algoritmo HS256", header.get("alg") == "HS256", header.get("alg", "?"))
    check("Claims sub/jti/rol/exp presentes", all(k in payload for k in ("sub", "jti", "rol", "exp")))
    check("Rol del token = planner", str(payload.get("rol", "")).lower() == "planner", str(payload.get("rol")))
    restante = int(payload.get("exp", 0)) - int(time.time())
    check("Token vigente", restante > 0, f"expira en {restante // 3600}h {restante % 3600 // 60}m")

    if secreto:
        esperado = hmac.new(secreto.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
        if not check("Firma HS256 válida con JWT_SECRET_KEY de .env", hmac.compare_digest(esperado, b64url(firma_b64))):
            print(f"      {AMARILLO}el JWT_SECRET_KEY del .env local no coincide con el de los contenedores{FIN}")
    else:
        print(f"  {AMARILLO}[--]{FIN} JWT_SECRET_KEY no está en .env; no se verifica la firma")
    return payload


def token_alterado(token: str) -> str:
    """Cambia el rol en el payload sin volver a firmar: la firma ya no corresponde."""
    h, p, f = token.split(".")
    datos = json.loads(b64url(p))
    datos["rol"] = "admin"
    nuevo = base64.urlsafe_b64encode(json.dumps(datos).encode()).decode().rstrip("=")
    return f"{h}.{nuevo}.{f}"


# --- Redis ---------------------------------------------------------------------
class Redis:
    def __init__(self, env: dict[str, str]):
        self.password = env.get("REDIS_PASSWORD", "")
        self.base: list[str] | None = None
        if shutil.which("docker"):
            prueba = subprocess.run(["docker", "exec", "freshtrack_redis", "true"], capture_output=True)
            if prueba.returncode == 0:
                self.base = ["docker", "exec", "freshtrack_redis", "redis-cli"]
        if self.base is None and shutil.which("redis-cli"):
            self.base = ["redis-cli", "-h", env.get("REDIS_HOST", "127.0.0.1"), "-p", env.get("REDIS_PORT", "6379")]

    def __call__(self, *args: str) -> str:
        if self.base is None:
            return ""
        cmd = self.base + (["-a", self.password, "--no-auth-warning"] if self.password else []) + list(args)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()

    @property
    def disponible(self) -> bool:
        return self.base is not None and self("PING") == "PONG"


# --- flujo ---------------------------------------------------------------------
def main() -> int:
    global VERBOSO
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="Host donde están publicados los puertos 5001-5008")
    ap.add_argument("-v", "--verbose", action="store_true", help="Imprime los cuerpos JSON y XML")
    args = ap.parse_args()
    VERBOSO = args.verbose

    env = leer_env()
    url = {k: f"http://{args.host}:{p}" for k, p in PUERTOS.items()}

    seccion("1. Salud de los microservicios (JSON vs XML)")
    for nombre, base in url.items():
        par_json_xml(f"svc-{nombre} /health", "GET", f"{base}/health", None)
    if not any(ok for n, ok in resultados):
        print(f"\n  {ROJO}Ningún servicio responde. Levanta todo con: docker compose up -d --build{FIN}")
        return 1

    seccion("2. Login del planeador en svc-auth (JSON y XML)")
    datos = par_json_xml(
        "POST /auth/login", "POST", f"{url['auth']}/api/v1/auth/login", None,
        cuerpo_json={"email": EMAIL, "password": PASSWORD},
        cuerpo_xml=f"<login_request><email>{EMAIL}</email><password>{PASSWORD}</password></login_request>",
    )
    if not datos or "token" not in datos:
        print(f"\n  {ROJO}Sin token no se puede seguir (¿base sembrada? ¿rate limit? revisa docker compose logs svc_auth).{FIN}")
        return 1
    token = datos["token"]
    print(f"  token: {token[:40]}...  jti={datos.get('jti')}")

    seccion("3. Inspección del JWT")
    payload = inspeccionar_jwt(token, env.get("JWT_SECRET_KEY"))
    jti = payload["jti"]
    par_json_xml("GET /auth/me", "GET", f"{url['auth']}/api/v1/auth/me", token)
    par_json_xml("POST /auth/verify", "POST", f"{url['auth']}/api/v1/auth/verify", token)

    seccion("4. Sesión en Redis")
    redis = Redis(env)
    if redis.disponible:
        check(f"Existe session:{jti[:12]}...", redis("EXISTS", f"session:{jti}") == "1")
        ttl = redis("TTL", f"session:{jti}")
        check("La sesión tiene TTL", ttl.lstrip("-").isdigit() and int(ttl) > 0, f"TTL={ttl}s")
        print(f"  sesiones activas: {redis('EVAL', 'return #redis.call(\"KEYS\", \"session:*\")', '0')}"
              f" | tokens revocados: {redis('EVAL', 'return #redis.call(\"KEYS\", \"jwt:denylist:*\")', '0')}")
    else:
        print(f"  {AMARILLO}[--]{FIN} No hay acceso a Redis (ni docker exec ni redis-cli); se omiten estas pruebas")

    seccion("5. Endpoints del planeador (JSON vs XML)")
    loc = 3
    forecast = {"metodo": "SUAVIZACION_EXPONENCIAL", "horizonte": 7, "ventana": 28, "alpha": 0.3, "id_locacion": loc}
    forecast_xml = ("<forecast_request><metodo>SUAVIZACION_EXPONENCIAL</metodo><horizonte>7</horizonte>"
                    f"<ventana>28</ventana><alpha>0.3</alpha><id_locacion>{loc}</id_locacion></forecast_request>")
    res = par_json_xml("POST /planning/forecast/run", "POST", f"{url['planning']}/api/v1/planning/forecast/run",
                       token, cuerpo_json=forecast, cuerpo_xml=forecast_xml, esperado=201)
    if res:
        print(f"  id_run={res.get('id_run')} series={res.get('series')} mae={res.get('mae')} wmape={res.get('wmape')}")
    par_json_xml("GET /planning/forecast/analytics/kpis", "GET", f"{url['planning']}/api/v1/planning/forecast/analytics/kpis", token)
    par_json_xml("POST /planning/replenishment/generate", "POST", f"{url['planning']}/api/v1/planning/replenishment/generate",
                 token, cuerpo_json={"horizonte": 7}, cuerpo_xml="<replenishment_request><horizonte>7</horizonte></replenishment_request>",
                 esperado=201)
    par_json_xml("GET /planning/replenishment/orders", "GET",
                 f"{url['planning']}/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=2", token)
    par_json_xml("GET /planning/sku/1/full-context", "GET", f"{url['planning']}/api/v1/planning/sku/1/full-context?id_locacion={loc}", token)
    par_json_xml("GET /alerts/esg/carbon-avoided", "GET", f"{url['alerts']}/api/v1/alerts/esg/carbon-avoided", token)

    st, ct, body = http("GET", f"{url['planning']}/api/v1/contracts/forecast_request.xsd", accept="application/xml")
    check("Contrato XSD publicado (forecast_request.xsd)", st == 200 and "schema" in body, f"HTTP {st}")

    if redis.disponible:
        evento = redis("XREVRANGE", "freshtrack:events", "+", "-", "COUNT", "1")
        campos = evento.splitlines()[1:]
        campos = dict(zip(campos[::2], campos[1::2]))
        check("Último evento en el stream freshtrack:events", bool(evento),
              f"{campos.get('event_type')} user_role={campos.get('user_role') or '(vacío)'}")

    seccion("6. Seguridad: 401 y 403")
    st, _, body = http("GET", f"{url['auth']}/api/v1/auth/me")
    check("Sin token -> 401 token_requerido", st == 401 and "token_requerido" in body, f"HTTP {st}")
    st, _, body = http("GET", f"{url['auth']}/api/v1/auth/me", token=token_alterado(token))
    check("Token alterado (rol=admin sin firmar) -> 401 token_invalido", st == 401 and "token_invalido" in body, f"HTTP {st}")
    st, ct, body = http("GET", f"{url['auth']}/api/v1/auth/users", token=token)
    check("Planeador en endpoint solo-admin (/auth/users) -> 403", st == 403 and "acceso_denegado" in body, f"HTTP {st}")
    st, ct, body = http("GET", f"{url['auth']}/api/v1/auth/users", token=token, accept="application/xml")
    check("El 403 también sale en XML", st == 403 and "xml" in ct and es_xml_valido(body), ct)
    mostrar(body, es_xml=True)

    seccion("7. Logout y revocación (denylist en Redis)")
    # El logout revoca el token, así que la variante XML necesita una sesión propia.
    st, _, body = http("POST", f"{url['auth']}/api/v1/auth/logout", token=token)
    check("POST /auth/logout [JSON]", st == 200 and "LOGOUT_EXITOSO" in body, f"HTTP {st}")
    mostrar(body, es_xml=False)
    _, _, body = http("POST", f"{url['auth']}/api/v1/auth/login", cuerpo=json.dumps({"email": EMAIL, "password": PASSWORD}))
    token_xml = json.loads(body).get("token") if es_json_valido(body) else None
    st, ct, body = http("POST", f"{url['auth']}/api/v1/auth/logout", token=token_xml, accept="application/xml")
    check("POST /auth/logout [XML]", st == 200 and "xml" in ct and "LOGOUT_EXITOSO" in body, f"HTTP {st} {ct}")
    mostrar(body, es_xml=True)
    if redis.disponible:
        check(f"Existe jwt:denylist:{jti[:12]}...", redis("EXISTS", f"jwt:denylist:{jti}") == "1",
              f"TTL={redis('TTL', f'jwt:denylist:{jti}')}s")
        check("session:{jti} eliminada", redis("EXISTS", f"session:{jti}") == "0")
    st, _, body = http("GET", f"{url['auth']}/api/v1/auth/me", token=token)
    check("Token revocado -> 401 token_revocado (svc-auth)", st == 401 and "token_revocado" in body, f"HTTP {st}")
    st, _, body = http("GET", f"{url['planning']}/api/v1/planning/forecast/analytics/kpis", token=token)
    check("Token revocado -> 401 también en svc-planning", st == 401 and "token_revocado" in body, f"HTTP {st}")

    fallas = [n for n, ok in resultados if not ok]
    seccion(f"RESUMEN: {len(resultados) - len(fallas)}/{len(resultados)} comprobaciones OK")
    for n in fallas:
        print(f"  {ROJO}- {n}{FIN}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
