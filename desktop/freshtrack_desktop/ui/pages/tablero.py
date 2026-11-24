"""Tablero: KPIs de pronóstico, alertas y desperdicio, más la tabla de alertas activas.

Cada bloque hace su propia petición y falla por separado: un servicio caído deja su
bloque en "No disponible" sin vaciar el resto.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QLabel

from ..widgets import DataTable, KpiCard, secondary_label, set_tone
from .base import BasePage

_CRITICIDAD = {"CRITICAL": "CRÍTICO", "WARNING": "ADVERTENCIA", "INFO": "INFO"}


def _lista(valor) -> list[dict]:
    """El códec XML devuelve "" si el contenedor está vacío y un dict si hay un único hijo."""
    if isinstance(valor, list):
        return [v for v in valor if isinstance(v, dict)]
    if isinstance(valor, dict):
        return [valor]
    return []


def _num(valor, defecto: float = 0.0) -> float:
    try:
        return float(str(valor).replace(",", "").strip())
    except (TypeError, ValueError):
        return defecto


_ETIQUETAS_METODO = {
    "AUTO": "Automático",
    "MEDIA_MOVIL": "Media móvil",
    "MEDIA_MOVIL_PONDERADA": "Media móvil ponderada",
    "SUAVIZACION_EXPONENCIAL": "Suavización exponencial",
    "NAIVE": "Ingenuo",
}


def etiqueta_metodo(valor) -> str:
    """Nombre legible de un método de pronóstico (`SUAVIZACION_EXPONENCIAL` → "Suavización exponencial")."""
    clave = str(valor or "").strip()
    if not clave:
        return ""
    return _ETIQUETAS_METODO.get(clave.upper()) or clave.replace("_", " ").capitalize()


def _dic(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def productos_todos(api, por_pagina: int = 100, max_paginas: int = 50) -> list[dict]:
    """
    Recorre todas las páginas de /api/v1/catalog/products.

    El servicio limita por_pagina a 100; pedir solo la primera página dejaba
    fuera de los combos a los SKUs 101+ (el catálogo masivo tiene 200). Cada
    página la cachea svc-catalog en Redis, así que recorrerlas es barato.
    """
    productos: list[dict] = []
    pagina = 1
    while pagina <= max_paginas:
        resp = _dic(api.call("catalog", "GET", "/api/v1/catalog/products",
                             params={"por_pagina": por_pagina, "pagina": pagina}))
        lote = _lista(resp.get("productos"))
        productos.extend(lote)
        total_paginas = int(_num(_dic(resp.get("paginacion")).get("total_paginas"), 1) or 1)
        if not lote or pagina >= total_paginas:
            break
        pagina += 1
    return productos


class TableroPage(BasePage):
    title = "Tablero"
    subtitle = "Resumen de pronósticos, alertas y desperdicio con las alertas abiertas"
    icon = "SP_FileDialogDetailedView"
    roles = ()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.btn_actualizar = self.actions.add_button("Actualizar", self.refresh, variant="primary",
                                                      icon="SP_BrowserReload")
        self.kpi_modelos = KpiCard("Corridas de pronóstico")
        self.kpi_mejor = KpiCard("Mejor modelo (MAE)")
        self.kpi_alertas = KpiCard("Alertas abiertas")
        self.kpi_criticas = KpiCard("Alertas críticas")
        self.kpi_riesgo = KpiCard("Producto en riesgo")
        self.kpi_merma = KpiCard("Desperdicio proyectado")
        self.kpi_recuperado = KpiCard("Reducción de merma")
        fila1, fila2 = QHBoxLayout(), QHBoxLayout()
        for fila, tarjetas in ((fila1, (self.kpi_modelos, self.kpi_mejor)),
                               (fila2, (self.kpi_alertas, self.kpi_criticas, self.kpi_riesgo,
                                        self.kpi_merma, self.kpi_recuperado))):
            fila.setSpacing(12)
            for k in tarjetas:
                fila.addWidget(k)
            fila.addStretch(1)
        self.body.addLayout(fila1)
        self.body.addLayout(fila2)

        self.aviso = QLabel("")
        set_tone(self.aviso, "warning")
        self.aviso.setWordWrap(True)
        self.aviso.hide()
        self.body.addWidget(self.aviso)

        self.table = DataTable(empty_text="Sin alertas activas", title="Alertas activas")
        self.table.set_columns([
            ("criticidad", "Criticidad", "status"), ("tipo", "Tipo"), ("mensaje", "Mensaje"),
            ("id_locacion", "Tienda"), ("id_sku", "SKU"), ("generada_en", "Generada"),
        ])
        self.body.addWidget(self.table, 1)
        self.updated_label = secondary_label("")
        self.body.addWidget(self.updated_label)
        self._fallos: dict[str, str] = {}

    # ---- carga
    def refresh(self) -> None:
        self._fallos = {}
        self._actualizar_aviso()
        run, b = self.ctx.run, self.btn_actualizar
        api = self.ctx.api
        run(api.call, "planning", "GET", "/api/v1/planning/forecast/analytics/kpis",
            on_ok=self._mostrar_pronosticos, on_error=self._fallo_pronosticos, busy=b)
        run(api.call, "alerts", "GET", "/api/v1/alerts/analytics/kpis",
            on_ok=self._mostrar_kpis_alertas, on_error=self._fallo_kpis_alertas, busy=b)
        run(api.call, "alerts", "GET", "/api/v1/alerts/waste-measurement",
            on_ok=self._mostrar_desperdicio, on_error=self._fallo_desperdicio, busy=b)
        run(api.call, "alerts", "GET", "/api/v1/alerts/active", on_ok=self._mostrar_activas,
            on_error=self._fallo_activas, busy=b)

    # ---- resultados (hilo de UI)
    def _marca(self) -> None:
        self.updated_label.setText(f"Última actualización: {datetime.now():%H:%M:%S}")

    def _mostrar_pronosticos(self, datos) -> None:
        modelos = _lista(_dic(datos).get("kpis_modelos"))
        self.kpi_modelos.set_value(f"{sum(_num(m.get('total_corridas')) for m in modelos):,.0f}",
                                   sub=f"{len(modelos)} modelo(s)")
        con_mae = [m for m in modelos if str(m.get("mae_promedio", "")).strip()]
        if con_mae:
            m = min(con_mae, key=lambda x: _num(x.get("mae_promedio")))
            self.kpi_mejor.set_value(etiqueta_metodo(m.get("modelo")) or "—", sub=f"MAE {_num(m.get('mae_promedio')):,.2f}",
                                     tone="success")
        else:
            self.kpi_mejor.set_value("—", sub="Sin corridas")
        self._marca()

    def _mostrar_kpis_alertas(self, datos) -> None:
        grupos = _lista(_dic(datos).get("kpis_alertas"))
        total = sum(_num(g.get("total_alertas")) for g in grupos)
        crit = sum(_num(g.get("total_alertas")) for g in grupos if str(g.get("criticidad")).upper() == "CRITICAL")
        self.kpi_alertas.set_value(f"{total:,.0f}", sub=f"{len(grupos)} grupo(s) tienda/criticidad")
        self.kpi_criticas.set_value(f"{crit:,.0f}", tone="danger" if crit else "success")
        self._marca()

    def _mostrar_desperdicio(self, datos) -> None:
        d = _dic(datos)
        riesgo, proy = _dic(d.get("producto_en_riesgo")), _dic(d.get("desperdicio_proyectado"))
        red = _dic(d.get("reduccion_observada_merma"))
        self.kpi_riesgo.set_value(f"${_num(riesgo.get('valor')):,.2f}",
                                  sub=f"{_num(riesgo.get('unidades')):,.0f} u · {_num(riesgo.get('lotes')):,.0f} lotes",
                                  tone="warning" if _num(riesgo.get("valor")) else None)
        self.kpi_merma.set_value(f"${_num(proy.get('valor')):,.2f}",
                                 sub=f"{_num(proy.get('unidades')):,.0f} u si no se interviene",
                                 tone="danger" if _num(proy.get("valor")) else None)
        cambio = _num(red.get("cambio_puntos_pct"))
        self.kpi_recuperado.set_value(f"{cambio:.2f} pts",
                                      sub=f"Tasa reciente {_num(red.get('tasa_reciente_pct')):.2f} %",
                                      tone="success" if cambio >= 0 else "danger")
        self._marca()

    def _mostrar_activas(self, datos) -> None:
        self.table.set_empty_text("Sin alertas activas")
        filas = []
        for a in _lista(_dic(datos).get("alertas")):
            fila = dict(a)
            fila["criticidad"] = _CRITICIDAD.get(str(a.get("criticidad", "")).upper(), a.get("criticidad", ""))
            tipo = str(a.get("tipo", ""))
            fila["tipo"] = tipo.replace("_", " ").capitalize().replace("pre merma", "pre-merma") if tipo else ""
            filas.append(fila)
        self.table.set_rows(filas)
        self._marca()

    # ---- fallos por bloque
    def _fallo(self, bloque: str, exc: BaseException, *tarjetas: KpiCard) -> None:
        self._fallos[bloque] = str(getattr(exc, "mensaje", "") or exc) or type(exc).__name__
        for k in tarjetas:
            k.set_value("—", sub="No disponible", tone="warning")
        self._actualizar_aviso()

    def _actualizar_aviso(self) -> None:
        if not self._fallos:
            self.aviso.hide()
            return
        self.aviso.setText("Bloques sin datos: " + "; ".join(f"{b} ({m})" for b, m in self._fallos.items()))
        self.aviso.show()

    def _fallo_pronosticos(self, exc) -> None:
        self._fallo("Pronósticos", exc, self.kpi_modelos, self.kpi_mejor)

    def _fallo_kpis_alertas(self, exc) -> None:
        self._fallo("KPIs de alertas", exc, self.kpi_alertas, self.kpi_criticas)

    def _fallo_desperdicio(self, exc) -> None:
        self._fallo("Desperdicio", exc, self.kpi_riesgo, self.kpi_merma, self.kpi_recuperado)

    def _fallo_activas(self, exc) -> None:
        self._fallo("Alertas activas", exc)
        self.table.set_rows([])
        self.table.set_empty_text("No se pudieron cargar las alertas activas")
