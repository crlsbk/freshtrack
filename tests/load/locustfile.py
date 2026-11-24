"""
Pruebas de carga de FreshTrack con Locust — solo operaciones que existen en el sitio.

Ejecutar con el runner (pre-vuelo, curva, análisis y reporte):
    .venv/bin/python scripts/locust_ejecutar.py --host https://<dominio> --escenario rendimiento

Perfiles (rúbrica → FreshTrack):
  Usuarios consultando ..................... ConsultaTienda
  Usuarios registrando operaciones ......... CajaPOS (ventas reales en TODAS las tiendas)
  Aplicaciones móviles enviando datos ...... MovilAlmacen
  Aplicaciones de escritorio (reportes) .... EscritorioReportes (XML)
  Sensores transmitiendo lecturas .......... SensorRecepcion (termógrafo en inspección de ASN)
  Administradores consultando paneles ...... PanelesWeb (sitio web con sesión + CSRF)
  Procesos automáticos ..................... ProcesosProgramados + CicloRescate
  Conductores actualizando ubicación ....... no existe en FreshTrack: omitido

Variables (las fija el runner): LOCUST_CONTEXTO, LOCUST_ESCENARIO, LOCUST_FASES,
LOCUST_MODO (curva|manual), LOCUST_SALIDA, LOCUST_RUN_ID, LOCUST_PASSWORD_POOL.
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from locust import HttpUser, LoadTestShape, between, events, task  # noqa: E402

from tests.load import analisis  # noqa: E402
from tests.load.contexto import (  # noqa: E402
    CONTEXTO,
    RUN_ID,
    Medicion,
    SesionApi,
    SesionWeb,
    pedir,
    registrar_intervencion,
    skus_intervenidos,
    stock,
    tomar_cuenta,
    url,
)

ESCENARIO = os.getenv("LOCUST_ESCENARIO", "rendimiento")
MODO = os.getenv("LOCUST_MODO", "curva")
if os.getenv("LOCUST_FASES"):
    FASES = analisis.parsear_fases(os.environ["LOCUST_FASES"])
else:
    FASES = analisis.FASES_VENTAS if ESCENARIO == "ventas" else analisis.FASES_RENDIMIENTO

# Pesos por escenario: «ventas» concentra la carga en la caja POS para generar el
# dato de desperdicio evitado sin estresar el resto.
PESOS = {
    "rendimiento": {"consulta": 25, "pos": 18, "movil": 15, "escritorio": 12, "sensor": 10, "paneles": 15},
    "ventas": {"consulta": 12, "pos": 60, "movil": 8, "escritorio": 4, "sensor": 4, "paneles": 12},
}[ESCENARIO if ESCENARIO in ("rendimiento", "ventas") else "rendimiento"]

PROPORCION_TICKETS_RESCATE = 0.4  # tickets que compran SKUs con intervención en la tienda
INSEGURO = os.getenv("LOCUST_INSEGURO") == "1"  # certificados de prueba (sin verificar TLS)


@events.init.add_listener
def _tls(environment, **_kw):
    if INSEGURO:
        import urllib3

        urllib3.disable_warnings()


def _xml_checkout(id_locacion: int, lineas: list[dict]) -> str:
    items = "".join(f"<item><id_sku>{l['id_sku']}</id_sku><cantidad>{l['cantidad']}</cantidad></item>" for l in lineas)
    return f"<checkout_request><id_locacion>{id_locacion}</id_locacion><canal>TIENDA</canal><lineas>{items}</lineas></checkout_request>"


class _Base(HttpUser):
    abstract = True
    roles: tuple[str, ...] = ()
    con_stock = False

    def on_start(self) -> None:
        self.client.verify = not INSEGURO
        cuenta = tomar_cuenta(self.roles, solo_con_stock=self.con_stock)
        if cuenta is None:
            raise RuntimeError(f"Sin cuentas en el pool para {self.roles}")
        self.api = SesionApi(self, cuenta)
        if not self.api.iniciar():
            self.stop()

    @property
    def loc(self) -> int:
        return int(self.api.id_locacion or 0)


# ---------------------------------------------------------------------------- perfiles
class ConsultaTienda(_Base):
    """Gerentes y compradores consultando existencias, FEFO, órdenes y alertas."""

    weight = PESOS["consulta"]
    wait_time = between(3, 8)
    roles = ("store_manager", "buyer")

    @task(3)
    def existencias(self):
        pedir(self, "GET", url("inventory", f"/api/v1/inventory/stock?id_locacion={self.loc}&dias_max=5&por_pagina=50"),
              "/api/v1/inventory/stock", headers=self.api.cabeceras())

    @task(3)
    def cola_fefo(self):
        filas = stock(self.loc) or stock(random.choice(CONTEXTO["tiendas"]))
        if filas:
            f = random.choice(filas)
            pedir(self, "GET", url("inventory", f"/api/v1/inventory/fefo-queue/{f['id_sku']}/{f['id_locacion']}"),
                  "/api/v1/inventory/fefo-queue/[sku]/[loc]", headers=self.api.cabeceras())

    @task(2)
    def ordenes_reabastecimiento(self):
        pedir(self, "GET", url("planning", "/api/v1/planning/replenishment/orders?estado=PENDIENTE&por_pagina=20"),
              "/api/v1/planning/replenishment/orders", headers=self.api.cabeceras())

    @task(2)
    def alertas(self):
        pedir(self, "GET", url("alerts", "/api/v1/alerts/active?limite=20"), "/api/v1/alerts/active",
              headers=self.api.cabeceras())

    @task(1)
    def catalogo(self):
        q = random.choice(["leche", "pan", "fresa", "pollo", "queso", "manzana"])
        pedir(self, "GET", url("catalog", f"/api/v1/catalog/products?q={q}&por_pagina=20"),
              "/api/v1/catalog/products", headers=self.api.cabeceras())


class CajaPOS(_Base):
    """Cajas registrando ventas reales (FEFO) en su sucursal; parte de los tickets rescata lotes intervenidos."""

    weight = PESOS["pos"]
    wait_time = between(4, 10)
    roles = ("store_manager", "warehouse")
    con_stock = True

    def _lineas(self) -> tuple[list[dict], int]:
        filas = stock(self.loc)
        rescate = skus_intervenidos(self.loc)
        lineas, rescatadas = [], 0
        for _ in range(random.randint(1, 3)):
            if rescate and random.random() < PROPORCION_TICKETS_RESCATE:
                sku = random.choice(rescate)
                rescatadas += 1
            else:
                sku = random.choice(filas)["id_sku"]
            if all(l["id_sku"] != sku for l in lineas):
                lineas.append({"id_sku": sku, "cantidad": round(random.choice([1, 1, 1, 1.5, 2]), 2)})
        return lineas, rescatadas

    def _contar_venta(self, lineas: list[dict], rescatadas: int) -> None:
        c = Medicion.colector
        c.sumar("ventas_registradas")
        c.sumar("unidades_vendidas", sum(l["cantidad"] for l in lineas))
        if rescatadas:
            c.sumar("tickets_con_sku_intervenido")

    @task(5)
    def venta_directa(self):
        lineas, rescatadas = self._lineas()
        if random.random() < 0.5:
            cuerpo = {"data": _xml_checkout(self.loc, lineas),
                      "headers": {**self.api.cabeceras(), "Content-Type": "application/xml"}}
            nombre = "/api/v1/commercial/checkout [XML]"
        else:
            cuerpo = {"json": {"id_locacion": self.loc, "canal": "TIENDA", "lineas": lineas},
                      "headers": self.api.cabeceras()}
            nombre = "/api/v1/commercial/checkout [JSON]"
        st, _, _ = pedir(self, "POST", url("commercial", "/api/v1/commercial/checkout"), nombre, **cuerpo)
        if st in (200, 201):
            self._contar_venta(lineas, rescatadas)

    @task(2)
    def venta_con_carrito(self):
        lineas, rescatadas = self._lineas()
        carrito = uuid.uuid4().hex
        ruta = url("commercial", f"/api/v1/commercial/cart/{carrito}")
        h = self.api.cabeceras()
        pedir(self, "PUT", ruta, "/api/v1/commercial/cart/[id] [PUT]", json={"id_locacion": self.loc, "lineas": lineas}, headers=h)
        pedir(self, "GET", ruta, "/api/v1/commercial/cart/[id] [GET]", headers=h)
        st, _, _ = pedir(self, "POST", url("commercial", "/api/v1/commercial/checkout"), "/api/v1/commercial/checkout [JSON]",
                         json={"id_locacion": self.loc, "canal": "TIENDA", "lineas": lineas}, headers=h)
        pedir(self, "DELETE", ruta, "/api/v1/commercial/cart/[id] [DELETE]", headers=h)
        if st in (200, 201):
            self._contar_venta(lineas, rescatadas)

    @task(1)
    def merma(self):
        if random.random() > 0.3:  # merma ocasional, no en cada visita
            return
        filas = [f for f in stock(self.loc) if f.get("id_lote")]
        if not filas:
            return
        f = random.choice(filas)
        st, _, _ = pedir(self, "POST", url("commercial", "/api/v1/commercial/shrinkage"), "/api/v1/commercial/shrinkage",
                         json={"id_lote": f["id_lote"], "id_locacion": self.loc, "cantidad": 1, "causa": "DANO",
                               "observacion": f"Prueba de carga {RUN_ID}"},
                         headers=self.api.cabeceras())
        if st in (200, 201):
            Medicion.colector.sumar("mermas_registradas")


class MovilAlmacen(_Base):
    """App móvil de almacén: existencias, avisos ASN, escaneo de etiquetas y reserva FEFO (se cancela)."""

    weight = PESOS["movil"]
    wait_time = between(2, 6)
    roles = ("warehouse",)

    @task(3)
    def existencias(self):
        pedir(self, "GET", url("inventory", f"/api/v1/inventory/stock?id_locacion={self.loc}&por_pagina=30"),
              "/api/v1/inventory/stock", headers=self.api.cabeceras())

    @task(2)
    def avisos(self):
        pedir(self, "GET", url("asn", f"/api/v1/asn?id_locacion_destino={self.loc}&por_pagina=10"), "/api/v1/asn",
              headers=self.api.cabeceras())

    @task(2)
    def escanear_etiqueta(self):
        codigos = CONTEXTO.get("etiquetas") or []
        if codigos:
            pedir(self, "GET", url("asn", f"/api/v1/asn/labels?codigo={random.choice(codigos)}&id_locacion={self.loc}"),
                  "/api/v1/asn/labels", headers=self.api.cabeceras())

    @task(2)
    def reservar_y_cancelar(self):
        filas = stock(self.loc)
        if not filas:
            return
        saga = f"locust-{uuid.uuid4().hex[:12]}"
        h = self.api.cabeceras()
        st, _, _ = pedir(self, "POST", url("inventory", "/api/v1/inventory/reserve-fefo"), "/api/v1/inventory/reserve-fefo",
                         json={"id_locacion": self.loc, "saga_id": saga,
                               "lineas": [{"id_sku": random.choice(filas)["id_sku"], "cantidad": 1}]}, headers=h)
        if st in (200, 201):
            pedir(self, "POST", url("inventory", "/api/v1/inventory/cancel-reservation"),
                  "/api/v1/inventory/cancel-reservation", json={"saga_id": saga}, headers=h)


class EscritorioReportes(_Base):
    """App de escritorio (XML): órdenes de compra y PDF, pronósticos, desperdicio, triaje y bitácora."""

    weight = PESOS["escritorio"]
    wait_time = between(5, 15)
    roles = ("buyer", "planner", "auditor")

    OPERACIONES = {
        "buyer": ["ordenes", "pdf", "triaje", "desperdicio", "backtest"],
        "planner": ["triaje", "drift", "backtest", "desperdicio"],
        "auditor": ["bitacora", "ordenes", "pdf", "desperdicio", "drift"],
    }

    @task
    def reporte(self):
        op = random.choice(self.OPERACIONES.get(self.api.rol, ["desperdicio"]))
        h = self.api.cabeceras("application/xml")
        ordenes = CONTEXTO.get("ordenes_compra") or []
        rutas = {
            "ordenes": ("planning", "/api/v1/planning/purchase-orders?limite=50", "/api/v1/planning/purchase-orders"),
            "triaje": ("planning", "/api/v1/planning/triage", "/api/v1/planning/triage"),
            "drift": ("planning", "/api/v1/planning/forecast/drift", "/api/v1/planning/forecast/drift"),
            "backtest": ("planning", "/api/v1/planning/forecast/backtest", "/api/v1/planning/forecast/backtest"),
            "desperdicio": ("alerts", "/api/v1/alerts/waste-measurement", "/api/v1/alerts/waste-measurement"),
            "bitacora": ("audit", "/api/v1/audit/events?por_pagina=50", "/api/v1/audit/events"),
        }
        if op == "pdf":
            if not ordenes:
                return
            pedir(self, "GET", url("planning", f"/api/v1/planning/purchase-orders/{random.choice(ordenes)}/pdf"),
                  "/api/v1/planning/purchase-orders/[id]/pdf", headers={**h, "Accept": "application/pdf"})
            return
        svc, ruta, nombre = rutas[op]
        pedir(self, "GET", url(svc, ruta), nombre, headers=h, timeout=120)


class SensorRecepcion(_Base):
    """Termógrafos del muelle enviando lecturas de temperatura como inspección del ASN."""

    weight = PESOS["sensor"]
    wait_time = between(2, 5)
    roles = ("warehouse",)

    @task
    def lectura(self):
        folios = CONTEXTO.get("asn") or []
        if not folios:
            return
        temp = round(random.gauss(4.0, 1.2), 2)
        resultado = "CONFORME" if 1.0 <= temp <= 6.0 else "CONFORME_CON_OBSERVACIONES"
        st, _, _ = pedir(self, "POST", url("asn", f"/api/v1/asn/{random.choice(folios)}/inspection"),
                         "/api/v1/asn/[folio]/inspection",
                         json={"resultado": resultado, "temperatura_registrada": temp,
                               "observaciones": f"Lectura de termógrafo ({RUN_ID})"},
                         headers=self.api.cabeceras())
        if st in (200, 201):
            Medicion.colector.sumar("lecturas_sensor")


class PanelesWeb(HttpUser):
    """Planeadores y auditores consultando los paneles del sitio web (sesión con cookie + CSRF)."""

    weight = PESOS["paneles"]
    wait_time = between(5, 12)
    PAGINAS = {
        "planner": ["/panel", "/mapa", "/pronostico", "/triaje", "/reabastecimiento", "/inventario", "/desperdicio-evitado"],
        "auditor": ["/panel", "/mapa", "/auditoria", "/desperdicio-evitado", "/ventas"],
    }

    def on_start(self) -> None:
        self.client.verify = not INSEGURO
        cuenta = tomar_cuenta(("planner", "auditor"))
        if cuenta is None:
            raise RuntimeError("Sin cuentas planner/auditor en el pool")
        self.web = SesionWeb(self, cuenta)
        if not self.web.iniciar():
            self.stop()

    @task(4)
    def pagina(self):
        ruta = random.choice(self.PAGINAS.get(self.web.rol, ["/panel"]))
        pedir(self, "GET", ruta, f"WEB {ruta}", timeout=120)

    @task(1)
    def kpis_ventana(self):
        dias = random.choice(["7", "30", "90"])
        pedir(self, "GET", f"/api/kpis/ventana?dias={dias}", "WEB /api/kpis/ventana")


class ProcesosProgramados(HttpUser):
    """Tareas automáticas: barrido de caducidad, alertas, traslados, pronóstico y recálculo de desperdicio."""

    fixed_count = 1
    wait_time = between(20, 40)

    def on_start(self) -> None:
        self.client.verify = not INSEGURO
        self.planner = SesionApi(self, tomar_cuenta(("planner",)))
        self.almacen = SesionApi(self, tomar_cuenta(("warehouse",)))
        self.web = SesionWeb(self, tomar_cuenta(("planner",)))
        self.ciclo = 0
        if not (self.planner.iniciar() and self.almacen.iniciar() and self.web.iniciar()):
            self.stop()

    @task
    def ejecutar(self):
        self.ciclo += 1
        pedir(self, "POST", url("inventory", "/api/v1/inventory/expiration/scan"), "/api/v1/inventory/expiration/scan",
              json={}, headers=self.almacen.cabeceras())
        pedir(self, "POST", url("alerts", "/api/v1/alerts/scan"), "/api/v1/alerts/scan", json={},
              headers=self.almacen.cabeceras())
        pedir(self, "POST", url("planning", "/api/v1/planning/transfers/detect"), "/api/v1/planning/transfers/detect",
              json={}, headers=self.planner.cabeceras(), timeout=180)
        if self.ciclo % 4 == 0 and CONTEXTO.get("tiendas"):
            pedir(self, "POST", url("planning", "/api/v1/planning/forecast/run"), "/api/v1/planning/forecast/run",
                  json={"metodo": "AUTO", "horizonte": 7, "id_locacion": random.choice(CONTEXTO["tiendas"])},
                  headers=self.planner.cabeceras(), timeout=300)
        self.recalcular_desperdicio()

    def recalcular_desperdicio(self) -> None:
        _, _, html = pedir(self, "GET", "/desperdicio-evitado", "WEB /desperdicio-evitado")
        self.web.actualizar_csrf(html)
        if self.web.csrf:
            st, _, _ = pedir(self, "POST", "/desperdicio-evitado/recalcular", "WEB /desperdicio-evitado/recalcular",
                             data={"csrf_token": self.web.csrf})
            if st in (200, 302):
                Medicion.colector.sumar("recalculos_desperdicio")


class CicloRescate(HttpUser):
    """
    Planeador que ejecuta el ciclo de rescate con las herramientas del sitio:
    genera y aprueba descuentos, detecta/aprueba/ejecuta traslados. Cada
    intervención se comparte con CajaPOS para que las ventas la «rescaten».
    """

    fixed_count = 1
    wait_time = between(45, 90)

    def on_start(self) -> None:
        self.client.verify = not INSEGURO
        self.api = SesionApi(self, tomar_cuenta(("planner",)))
        if not self.api.iniciar():
            self.stop()

    @task
    def rescatar(self):
        h = self.api.cabeceras()
        _, datos, _ = pedir(self, "GET", url("planning", "/api/v1/planning/discounts?estado=SUGERIDO&limite=20"),
                            "/api/v1/planning/discounts", headers=h, esperar_json=True)
        sugeridos = (datos or {}).get("descuentos") or []
        if not sugeridos:
            pedir(self, "POST", url("planning", "/api/v1/planning/discounts/generate"),
                  "/api/v1/planning/discounts/generate", json={}, headers=h, timeout=180)
            _, datos, _ = pedir(self, "GET", url("planning", "/api/v1/planning/discounts?estado=SUGERIDO&limite=20"),
                                "/api/v1/planning/discounts", headers=h, esperar_json=True)
            sugeridos = (datos or {}).get("descuentos") or []
        for d in sugeridos[:3]:
            st, _, _ = pedir(self, "POST", url("planning", f"/api/v1/planning/discounts/{d['id_descuento']}/approve"),
                             "/api/v1/planning/discounts/[id]/approve", json={}, headers=h)
            if st in (200, 201):
                registrar_intervencion(d["id_locacion"], d["id_sku"])
                Medicion.colector.sumar("descuentos_aprobados")

        _, datos, _ = pedir(self, "GET", url("planning", "/api/v1/planning/transfers?estado=SUGERIDA&limite=20"),
                            "/api/v1/planning/transfers", headers=h, esperar_json=True)
        for t in ((datos or {}).get("transferencias") or [])[:2]:
            st, _, _ = pedir(self, "POST", url("planning", f"/api/v1/planning/transfers/{t['id_transferencia']}/approve"),
                             "/api/v1/planning/transfers/[id]/approve", json={}, headers=h)
            if st not in (200, 201):
                continue
            st, _, _ = pedir(self, "POST", url("planning", f"/api/v1/planning/transfers/{t['id_transferencia']}/execute"),
                             "/api/v1/planning/transfers/[id]/execute", json={}, headers=h)
            if st in (200, 201):
                registrar_intervencion(t["id_destino"], t["id_sku"])
                Medicion.colector.sumar("traslados_ejecutados")


# ---------------------------------------------------------------------------- curva de carga
if MODO != "manual":

    class CurvaFreshTrack(LoadTestShape):
        """Fases de LOCUST_FASES / escenario: línea base → carga → pico → recuperación."""

        def tick(self):
            info = analisis.fase_en(FASES, self.get_run_time())
            if info is None:
                return None
            fase, _ = info
            return fase.usuarios, max(1.0, fase.usuarios / 30.0)


# ---------------------------------------------------------------------------- medición y volcado
@events.test_start.add_listener
def _inicio(environment, **_kw):
    Medicion.t0 = time.time()
    Medicion.fases = () if MODO == "manual" else FASES
    Medicion.usuarios = lambda: environment.runner.user_count if environment.runner else 0


@events.test_stop.add_listener
def _fin(environment, **_kw):
    salida = os.getenv("LOCUST_SALIDA")
    if not salida:
        return
    d = Path(salida)
    d.mkdir(parents=True, exist_ok=True)
    c = Medicion.colector
    serie = c.serie()
    if serie:
        with (d / "serie_segundos.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(serie[0].keys()))
            w.writeheader()
            w.writerows(serie)

    def volcar(nombre, valor):
        (d / nombre).write_text(json.dumps(valor, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    volcar("fases.json", c.fases(FASES if MODO != "manual" else (analisis.Fase("MANUAL", 0, 0),)))
    volcar("endpoints.json", c.endpoints())
    volcar("fase_endpoints.json", c.fase_endpoints())
    volcar("errores.json", c.lista_errores())
    volcar("global.json", c.global_())
    volcar("negocio.json", dict(c.negocio))
