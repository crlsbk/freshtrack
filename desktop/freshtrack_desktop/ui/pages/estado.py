"""Estado de servicios: GET /health de los 8 microservicios (en paralelo)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout

from ...core.config import PUERTOS
from ...core.errors import ApiError, ServiceUnavailable, XmlContractError
from ..widgets import DataTable, KpiCard, secondary_label
from .base import BasePage

AUTO_REFRESH_MS = 30_000
_DEPENDENCIAS = ("postgres", "mongo", "redis")


def _dependencias(valor) -> str:
    if not isinstance(valor, dict) or not valor:
        return "sin dependencias"
    partes = []
    for dep in _DEPENDENCIAS:
        if dep in valor:
            ok = str(valor[dep]).strip().lower() in ("true", "1")
            partes.append(f"{dep}: {'OK' if ok else 'FALLA'}")
    return ", ".join(partes) or "sin dependencias"


class EstadoPage(BasePage):
    title = "Estado de servicios"
    subtitle = "Salud de los 8 microservicios (GET /health en XML); se actualiza cada 30 s mientras está abierta"
    icon = "SP_DriveNetIcon"
    roles = ()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self._cargando = False
        self.btn_actualizar = self.actions.add_button("Actualizar", self.refresh, variant="primary",
                                                      icon="SP_BrowserReload")
        kpis = QHBoxLayout()
        kpis.setSpacing(12)
        self.kpi_ok = KpiCard("Operando")
        self.kpi_degradados = KpiCard("Degradados")
        self.kpi_caidos = KpiCard("Caídos")
        for k in (self.kpi_ok, self.kpi_degradados, self.kpi_caidos):
            kpis.addWidget(k)
        kpis.addStretch(1)
        self.body.addLayout(kpis)

        self.table = DataTable(empty_text="Aún no se consulta el estado. Pulsa Actualizar.",
                               title="Estado de servicios", filterable=False)
        self.table.set_columns([
            ("servicio", "Servicio"), ("estado", "Estado", "status"), ("dependencias", "Dependencias"),
            ("latencia_ms", "Latencia (ms)", "int"), ("version", "Versión"), ("url", "URL"),
            ("detalle", "Detalle"),
        ])
        self.body.addWidget(self.table, 1)
        self.updated_label = secondary_label("")
        self.body.addWidget(self.updated_label)

        self.timer = QTimer(self)
        self.timer.setInterval(AUTO_REFRESH_MS)
        self.timer.timeout.connect(self._tick)

    # ---- ciclo de vida
    def on_show(self) -> None:
        self.refresh()
        self.timer.start()

    def on_hide(self) -> None:
        self.timer.stop()

    def _tick(self) -> None:
        if self.isVisible():
            self.refresh()

    def refresh(self) -> None:
        if self._cargando:
            return
        self._cargando = True
        self.ctx.run(self._consultar, on_ok=self._mostrar, on_error=self._fallo, busy=self.btn_actualizar)

    # ---- trabajo (hilo del pool: sin widgets)
    def _consultar(self) -> list[dict]:
        servicios = list(PUERTOS)
        with ThreadPoolExecutor(max_workers=len(servicios)) as ex:
            futuros = {svc: ex.submit(self._uno, svc) for svc in servicios}
        return [futuros[s].result() for s in servicios]

    def _uno(self, svc: str) -> dict:
        fila = {"servicio": svc, "url": self.ctx.settings.base_urls.get(svc, ""), "estado": "CAÍDO",
                "dependencias": "", "latencia_ms": None, "version": "", "detalle": ""}
        try:
            datos = self.ctx.api.health(svc)
        except ServiceUnavailable as exc:
            fila["detalle"] = f"Sin conexión ({exc.mensaje})"
        except XmlContractError as exc:
            if self.ctx.settings.gateway_url:
                # El gateway respondió, pero con la web (HTML): el backend desplegado no tiene el alias.
                fila["estado"] = "DESCONOCIDO"
                fila["detalle"] = ("El gateway no expone /api/v1/" + svc + "/health; despliega la versión "
                                   "nueva del backend para ver la salud de cada servicio.")
            else:
                fila["detalle"] = f"Respuesta fuera de contrato: {exc.mensaje}"
        except ApiError as exc:
            if self.ctx.settings.gateway_url and exc.status == 404:
                fila["estado"] = "DESCONOCIDO"
                fila["detalle"] = f"El gateway no expone /api/v1/{svc}/health (HTTP 404)."
            else:
                fila["detalle"] = f"HTTP {exc.status}: {exc.mensaje}"
        except Exception as exc:  # noqa: BLE001 - cualquier otra falla cuenta como caído
            fila["detalle"] = str(exc) or type(exc).__name__
        else:
            estado = str(datos.get("status", "")).upper()
            fila.update(
                estado="OK" if estado == "HEALTHY" else "DEGRADADO",
                dependencias=_dependencias(datos.get("dependencies")),
                latencia_ms=datos.get("elapsed_ms"),
                version=str(datos.get("version") or ""),
                detalle=str(datos.get("service") or ""),
            )
        return fila

    # ---- resultado (hilo de UI)
    def _mostrar(self, filas: list[dict]) -> None:
        self._cargando = False
        self.table.set_rows(filas)
        n = len(filas)
        ok = sum(f["estado"] == "OK" for f in filas)
        deg = sum(f["estado"] == "DEGRADADO" for f in filas)
        caidos = sum(f["estado"] == "CAÍDO" for f in filas)
        desconocidos = sum(f["estado"] == "DESCONOCIDO" for f in filas)
        self.kpi_ok.set_value(f"{ok}/{n}", tone="success" if ok == n else None)
        self.kpi_degradados.set_value(str(deg), tone="warning" if deg else None)
        self.kpi_caidos.set_value(str(caidos), tone="danger" if caidos else None)
        self.updated_label.setText(f"Última revisión: {datetime.now():%H:%M:%S}")
        if desconocidos:
            self.ctx.notify(f"Estado de servicios: {desconocidos} sin dato a través del gateway")
        elif caidos or deg:
            self.ctx.notify(f"Estado de servicios: {caidos} caído(s), {deg} degradado(s)")

    def _fallo(self, exc: BaseException) -> None:
        self._cargando = False
        self.ctx.show_error(exc, self)
