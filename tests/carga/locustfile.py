"""
Pruebas de carga de FreshTrack con Locust.

Simula los 8 perfiles reales que usan la plataforma al mismo tiempo, contra la web
(:5000) y los microservicios (:5001-5008) levantados con docker compose:

    Perfil                              Cuenta             Qué hace
    ----------------------------------  -----------------  ---------------------------------------------
    UsuarioConsulta                     gerente (web)      Navega pantallas: inventario, productos, alertas
    UsuarioRegistraOperaciones          gerente (API)      Ventas POS (Saga + FEFO) y mermas
    AppMovil                            almacén (API)      Carrito POS en Redis, stock y cola FEFO
    AppEscritorioReportes               planner (API)      Reportes analíticos (KPIs, backtest, compras)
    Sensor                              almacén (API)      Lecturas de temperatura de cámaras frías
    Conductor                           almacén (API)      Consulta su ASN y reporta ubicación GPS
    AdministradorPaneles                admin (web+API)    Paneles: dashboard, triaje, bitácora, sesiones
    ProcesoAutomatico                   almacén (API)      Escaneos de caducidad y de alertas (cron)

El escenario por defecto lo marca `EscenarioEscalonado` (al final del archivo):
calentamiento → carga normal → carga alta → saturación → pico → recuperación.
Ver tests/carga/README.md para cómo correrlo y cómo se arma el reporte.
"""

from __future__ import annotations

import os
import random
import re
import threading
import time
import uuid

from locust import HttpUser, LoadTestShape, between, constant_pacing, events, task

HOST = os.getenv("CARGA_HOST", "127.0.0.1")
WEB = f"http://{HOST}:{os.getenv('CARGA_WEB_PORT', '5000')}"
SVC = {
    "auth": f"http://{HOST}:5001",
    "catalog": f"http://{HOST}:5002",
    "inventory": f"http://{HOST}:5003",
    "commercial": f"http://{HOST}:5004",
    "asn": f"http://{HOST}:5005",
    "planning": f"http://{HOST}:5006",
    "alerts": f"http://{HOST}:5007",
    "audit": f"http://{HOST}:5008",
    "web": WEB,  # API JSON de la web (/api/...)
}

CUENTAS = {
    "admin": ("admin@freshtrack.mx", "Admin2026!"),
    "gerente": ("gerente@freshtrack.mx", "Tienda2026!"),
    "almacen": ("almacen@freshtrack.mx", "Almacen2026!"),
    "planner": ("planner@freshtrack.mx", "Plan2026!"),
}

# Tiendas sembradas (sql/07_seed_base.sql) con su ubicación aproximada.
TIENDAS_GPS = [(25.6575, -100.4020), (25.7290, -100.3940), (25.6500, -100.3360), (25.4232, -101.0053), (25.6200, -100.2750)]


# ---------------------------------------------------------------------------
# Tokens compartidos: un login por cuenta, reutilizado por todos los usuarios
# virtuales de esa cuenta (como varias pestañas/dispositivos con la misma sesión).
# Así la prueba mide la operación y no el bcrypt del login en cada usuario.
# ---------------------------------------------------------------------------
_tokens: dict[str, dict] = {}
_tokens_lock = threading.Lock()


def sesion_api(cliente, cuenta: str, forzar: bool = False) -> dict:
    with _tokens_lock:
        if forzar or cuenta not in _tokens:
            email, clave = CUENTAS[cuenta]
            with cliente.post(f"{SVC['auth']}/api/v1/auth/login", json={"email": email, "password": clave},
                              name="[auth] POST login", catch_response=True) as r:
                if r.status_code != 200:
                    r.failure(f"login {cuenta}: {r.status_code}")
                    raise RuntimeError(f"No se pudo iniciar sesión como {cuenta}: {r.status_code}")
                d = r.json()
            _tokens[cuenta] = {"token": d["token"], "usuario": d["usuario"]}
        return _tokens[cuenta]


# Existencias reales de la tienda del gerente: se leen una vez y se reparten.
_stock: dict[int, list[dict]] = {}
_stock_lock = threading.Lock()


def existencias(cliente, headers: dict, id_locacion: int) -> list[dict]:
    with _stock_lock:
        if id_locacion not in _stock:
            lotes: list[dict] = []
            for pagina in (1, 2, 3):
                r = cliente.get(f"{SVC['inventory']}/api/v1/inventory/stock",
                                params={"id_locacion": id_locacion, "por_pagina": 100, "pagina": pagina},
                                headers=headers, name="[inventory] GET stock (precarga)")
                if r.status_code == 200:
                    lotes += [e for e in r.json().get("existencias", []) if (e.get("disponible_neto") or 0) >= 5]
            _stock[id_locacion] = lotes
        return _stock[id_locacion]


class UsuarioApi(HttpUser):
    """Base de los perfiles que hablan con los microservicios por JWT."""

    abstract = True
    host = WEB
    cuenta = "gerente"

    def on_start(self):
        s = sesion_api(self.client, self.cuenta)
        self.usuario = s["usuario"]
        self.headers = {"Authorization": f"Bearer {s['token']}", "Accept": "application/json"}

    def api(self, metodo: str, servicio: str, ruta: str, nombre: str, ok=(200,), **kw):
        """Petición a un microservicio. 401 → re-login una vez; códigos fuera de `ok` son fallo."""
        url = SVC[servicio] + ruta
        with self.client.request(metodo, url, headers=self.headers, name=f"[{servicio}] {nombre}",
                                 catch_response=True, **kw) as r:
            if r.status_code == 401:
                r.failure("401 token vencido/revocado")
                self.on_start_forzado()
            elif r.status_code not in ok:
                r.failure(f"{r.status_code}: {r.text[:160]}")
            else:
                r.success()
            return r

    def on_start_forzado(self):
        s = sesion_api(self.client, self.cuenta, forzar=True)
        self.headers["Authorization"] = f"Bearer {s['token']}"


class UsuarioWeb(HttpUser):
    """Base de los perfiles que usan la aplicación web con sesión por cookie."""

    abstract = True
    host = WEB
    cuenta = "gerente"

    def on_start(self):
        email, clave = CUENTAS[self.cuenta]
        self.client.cookies.clear()
        with self.client.post("/login", data={"email": email, "password": clave}, name="[web] POST /login",
                              catch_response=True, allow_redirects=False) as r:
            sesion = r.cookies.get("session")
            if r.status_code != 302 or not sesion or "/login" in r.headers.get("Location", ""):
                m = re.search(r'class="[^"]*(?:error|alerta|flash)[^"]*"[^>]*>\s*([^<]{3,160})', r.text or "")
                r.failure(f"login web {self.cuenta}: {r.status_code} {m.group(1).strip() if m else ''}")
                return
        self._fijar_cookie(sesion)

    def _fijar_cookie(self, valor: str) -> None:
        # La app marca la cookie como Secure; por HTTP local `requests` no la reenviaría,
        # así que se guarda una copia sin Secure (lo que hace un navegador en localhost).
        self.client.cookies.clear()
        self.client.cookies.set("session", valor, domain=HOST, path="/")

    def pagina(self, ruta: str, nombre: str | None = None):
        with self.client.get(ruta, name=f"[web] {nombre or ruta}", catch_response=True) as r:
            # Flask puede rotar la cookie en cualquier respuesta (también en redirecciones).
            nueva = next((h.cookies.get("session") for h in [*r.history, r] if h.cookies.get("session")), None)
            if nueva:
                self._fijar_cookie(nueva)
            if r.status_code != 200:
                r.failure(f"{r.status_code}")
            elif "/login" in r.url:
                r.failure("sesión perdida (redirige a /login)")
                self.on_start()


# ===========================================================================
# 1. Usuarios consultando (web)
# ===========================================================================
class UsuarioConsulta(UsuarioWeb):
    weight = 6
    wait_time = between(2, 6)
    cuenta = "gerente"

    @task(4)
    def inventario(self):
        self.pagina("/inventario")

    @task(3)
    def productos(self):
        self.pagina("/productos")

    @task(3)
    def alertas(self):
        self.pagina("/alertas")

    @task(2)
    def lotes(self):
        self.pagina("/lotes")

    @task(2)
    def ventas(self):
        self.pagina("/ventas")

    @task(1)
    def mapa(self):
        self.pagina("/mapa")


# ===========================================================================
# 2. Usuarios registrando operaciones (POS y mermas por API)
# ===========================================================================
class UsuarioRegistraOperaciones(UsuarioApi):
    weight = 3
    wait_time = between(3, 8)
    cuenta = "gerente"

    def on_start(self):
        super().on_start()
        self.loc = self.usuario["id_locacion"]
        self.lotes = existencias(self.client, self.headers, self.loc)

    @task(5)
    def venta_pos(self):
        if not self.lotes:
            return
        skus = random.sample(self.lotes, k=min(len(self.lotes), random.randint(1, 3)))
        cuerpo = {"id_locacion": self.loc, "canal": "TIENDA",
                  "lineas": [{"id_sku": e["id_sku"], "cantidad": 1} for e in skus]}
        # 409 = la Saga rechazó y compensó (sin existencia): es respuesta de negocio válida.
        self.api("POST", "commercial", "/api/v1/commercial/checkout", "POST checkout (Saga FEFO)",
                 ok=(201, 409), json=cuerpo)

    @task(1)
    def merma(self):
        if not self.lotes:
            return
        e = random.choice(self.lotes)
        self.api("POST", "commercial", "/api/v1/commercial/shrinkage", "POST shrinkage (merma)", ok=(201, 409),
                 json={"id_lote": e["id_lote"], "id_locacion": self.loc, "cantidad": 0.5,
                       "causa": random.choice(["DANO", "CALIDAD", "MANIPULACION"]),
                       "observacion": "prueba de carga"})

    @task(2)
    def historial(self):
        self.api("GET", "commercial", f"/api/v1/commercial/sales?id_locacion={self.loc}&por_pagina=20",
                 "GET sales")


# ===========================================================================
# 3. Aplicaciones móviles enviando datos (handheld de piso de venta)
# ===========================================================================
class AppMovil(UsuarioApi):
    weight = 3
    wait_time = between(1, 4)
    cuenta = "gerente"

    def on_start(self):
        super().on_start()
        self.loc = self.usuario["id_locacion"]
        self.lotes = existencias(self.client, self.headers, self.loc)
        self.carrito = f"movil-{uuid.uuid4().hex[:10]}"

    @task(4)
    def guardar_carrito(self):
        lineas = [{"id_sku": e["id_sku"], "cantidad": random.randint(1, 3)}
                  for e in random.sample(self.lotes, k=min(len(self.lotes), 3))] if self.lotes else []
        self.api("PUT", "commercial", f"/api/v1/commercial/cart/{self.carrito}", "PUT cart (Redis)",
                 json={"id_locacion": self.loc, "lineas": lineas})

    @task(2)
    def leer_carrito(self):
        self.api("GET", "commercial", f"/api/v1/commercial/cart/{self.carrito}", "GET cart (Redis)", ok=(200, 404))

    @task(3)
    def stock_sku(self):
        if self.lotes:
            sku = random.choice(self.lotes)["id_sku"]
            self.api("GET", "inventory", f"/api/v1/inventory/stock?id_locacion={self.loc}&id_sku={sku}",
                     "GET stock?id_sku")

    @task(2)
    def cola_fefo(self):
        if self.lotes:
            sku = random.choice(self.lotes)["id_sku"]
            self.api("GET", "inventory", f"/api/v1/inventory/fefo-queue/{sku}/{self.loc}", "GET fefo-queue")

    @task(1)
    def catalogo(self):
        self.api("GET", "catalog", f"/api/v1/catalog/products?pagina={random.randint(1, 10)}&por_pagina=20",
                 "GET products (cache Redis)")


# ===========================================================================
# 4. Aplicaciones de escritorio solicitando reportes
# ===========================================================================
class AppEscritorioReportes(UsuarioApi):
    weight = 1
    wait_time = between(5, 12)
    cuenta = "planner"

    @task(3)
    def kpis_pronostico(self):
        self.api("GET", "planning", "/api/v1/planning/forecast/analytics/kpis", "GET forecast kpis")

    @task(2)
    def ordenes_reabasto(self):
        self.api("GET", "planning", "/api/v1/planning/replenishment/orders", "GET replenishment orders")

    @task(2)
    def desperdicio(self):
        self.api("GET", "alerts", "/api/v1/alerts/waste-measurement", "GET waste-measurement")

    @task(1)
    def backtest(self):
        self.api("GET", "planning", "/api/v1/planning/forecast/backtest", "GET forecast backtest")

    @task(1)
    def resumen_asn(self):
        self.api("GET", "asn", "/api/v1/asn/analytics/summary", "GET asn analytics summary")

    @task(1)
    def reporte_xml(self):
        # Los clientes de escritorio piden XML (contratos XSD).
        h = {**self.headers, "Accept": "application/xml"}
        with self.client.get(f"{SVC['inventory']}/api/v1/inventory/stock?por_pagina=100&dias_max=3", headers=h,
                             name="[inventory] GET stock (XML)", catch_response=True) as r:
            if r.status_code != 200 or not r.text.startswith("<?xml"):
                r.failure(f"{r.status_code}")


# ===========================================================================
# 5. Sensores transmitiendo lecturas (cámaras frías)
# ===========================================================================
class Sensor(UsuarioApi):
    """
    No hay un endpoint dedicado de telemetría; el sensor publica su lectura como
    documento operativo en MongoDB (con TTL), igual que las alertas de cadena de frío.
    """

    weight = 4
    wait_time = constant_pacing(5)  # una lectura cada 5 s por sensor
    cuenta = "almacen"

    def on_start(self):
        super().on_start()
        self.sensor_id = f"CF-{uuid.uuid4().hex[:6].upper()}"
        self.loc = random.randint(1, 6)
        self.temp = random.uniform(2.5, 5.0)

    @task
    def lectura(self):
        self.temp = min(9.0, max(0.5, self.temp + random.uniform(-0.4, 0.4)))
        fuera = self.temp > 6.0
        self.api("POST", "web", "/api/alertas/documentos", "POST lectura sensor (Mongo)", ok=(201,),
                 json={"tipo": "EXCURSION_TEMPERATURA" if fuera else "LECTURA_SENSOR",
                       "criticidad": "CRITICAL" if fuera else "INFO",
                       "mensaje": f"Sensor {self.sensor_id}: {self.temp:.1f} °C",
                       "id_locacion": self.loc,
                       "contexto": {"sensor_id": self.sensor_id, "temperatura_c": round(self.temp, 2),
                                    "humedad_pct": round(random.uniform(80, 95), 1), "ts": time.time()}})


# ===========================================================================
# 6. Conductores actualizando ubicación
# ===========================================================================
class Conductor(UsuarioApi):
    """
    Tampoco hay endpoint de GPS: el conductor consulta sus ASN en tránsito y deja su
    posición en la bitácora de cumplimiento (svc-audit), que es lo más cercano que
    existe hoy a un registro de ubicación con usuario y hora.
    """

    weight = 2
    wait_time = constant_pacing(10)
    cuenta = "almacen"

    def on_start(self):
        super().on_start()
        self.unidad = f"UNI-{random.randint(100, 999)}"
        self.lat, self.lon = random.choice(TIENDAS_GPS)

    @task(4)
    def ubicacion(self):
        self.lat += random.uniform(-0.003, 0.003)
        self.lon += random.uniform(-0.003, 0.003)
        self.api("POST", "audit", "/api/v1/audit/log", "POST ubicación conductor", ok=(201,),
                 json={"accion": "UBICACION_CONDUCTOR", "tabla": "transporte",
                       "descripcion": f"{self.unidad} lat={self.lat:.5f} lon={self.lon:.5f}"})

    @task(1)
    def mis_asn(self):
        self.api("GET", "asn", "/api/v1/asn?estado=EN_TRANSITO&por_pagina=10", "GET asn en tránsito")


# ===========================================================================
# 7. Administradores consultando paneles
# ===========================================================================
class AdministradorPaneles(UsuarioWeb):
    weight = 1
    wait_time = between(5, 15)
    cuenta = "admin"

    def on_start(self):
        super().on_start()
        s = sesion_api(self.client, "admin")
        self.headers = {"Authorization": f"Bearer {s['token']}", "Accept": "application/json"}

    @task(4)
    def dashboard(self):
        self.pagina("/panel")

    @task(2)
    def desperdicio(self):
        self.pagina("/desperdicio-evitado")

    @task(2)
    def triaje(self):
        self.pagina("/triaje")

    @task(1)
    def bitacora(self):
        self.pagina("/auditoria")

    @task(1)
    def usuarios(self):
        self.pagina("/usuarios")

    @task(2)
    def contadores_auth(self):
        with self.client.get(f"{SVC['auth']}/api/v1/auth/counters", headers=self.headers,
                             name="[auth] GET counters", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")

    @task(2)
    def eventos_auditoria(self):
        with self.client.get(f"{SVC['audit']}/api/v1/audit/events?por_pagina=50", headers=self.headers,
                             name="[audit] GET events", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"{r.status_code}")


# ===========================================================================
# 8. Procesos automáticos (cron)
# ===========================================================================
class ProcesoAutomatico(UsuarioApi):
    fixed_count = 1  # un solo "cron" sin importar cuántos usuarios haya
    wait_time = constant_pacing(30)
    cuenta = "almacen"

    @task(2)
    def escaneo_alertas(self):
        self.api("POST", "alerts", "/api/v1/alerts/scan?dias=3", "POST alerts/scan", ok=(200, 409, 423))

    @task(1)
    def escaneo_caducidades(self):
        self.api("POST", "inventory", "/api/v1/inventory/expiration/scan", "POST expiration/scan",
                 json={"dias_critico": 2})


# ===========================================================================
# Escenario: escalones de carga para medir saturación y recuperación
# ===========================================================================
ESCALONES = [
    # (fin_en_segundos, usuarios, tasa_de_alta, etiqueta)
    (60, 10, 2, "1-calentamiento"),
    (180, 30, 2, "2-carga-normal"),
    (300, 60, 3, "3-carga-alta"),
    (420, 100, 4, "4-saturacion"),
    (480, 150, 10, "5-pico"),
    (660, 10, 20, "6-recuperacion"),
]
ESCALA = float(os.getenv("CARGA_ESCALA_TIEMPO", "1"))  # 0.25 = corrida rápida de humo


class EscenarioEscalonado(LoadTestShape):
    use_common_options = False

    def tick(self):
        t = self.get_run_time()
        for fin, usuarios, tasa, _ in ESCALONES:
            if t < fin * ESCALA:
                return usuarios, tasa
        return None


@events.test_start.add_listener
def _anotar_inicio(environment, **_kw):
    # El analizador necesita saber en qué segundo arrancó cada escalón.
    ruta = os.getenv("CARGA_MARCAS")
    if ruta:
        with open(ruta, "w") as f:
            f.write(f"{time.time()}\n{ESCALA}\n")
