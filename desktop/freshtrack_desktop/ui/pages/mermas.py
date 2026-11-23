"""Mermas y desperdicio: medición de desperdicio, huella de carbono y triage por lote."""

from __future__ import annotations

from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QTabWidget

from ...core.xml_codec import num
from .. import theme
from ..widgets import DataTable, KpiCard, secondary_label
from .base import BasePage

_ACCIONES_TRIAGE = ("TRASLADO", "DESCUENTO", "MERMA", "NORMAL")


def _d(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def filas_indicadores(waste: dict) -> list[dict]:
    """Los 6 indicadores de `medicion_desperdicio` como filas de tabla."""
    riesgo, proy = _d(waste.get("producto_en_riesgo")), _d(waste.get("desperdicio_proyectado"))
    rec, evi = _d(waste.get("producto_recuperado")), _d(waste.get("desperdicio_evitado_estimado"))
    red, co2 = _d(waste.get("reduccion_observada_merma")), _d(waste.get("co2e_evitado_estimado"))
    return [
        {"indicador": "Producto en riesgo", "cantidad": num(riesgo.get("unidades")), "unidad": "unidades",
         "valor": num(riesgo.get("valor")), "detalle": f"{int(num(riesgo.get('lotes')))} lotes",
         "definicion": riesgo.get("definicion", "")},
        {"indicador": "Desperdicio proyectado", "cantidad": num(proy.get("unidades")), "unidad": "unidades",
         "valor": num(proy.get("valor")), "detalle": "", "definicion": proy.get("definicion", "")},
        {"indicador": "Producto recuperado", "cantidad": num(rec.get("unidades")), "unidad": "unidades",
         "valor": num(rec.get("valor")), "detalle": "", "definicion": rec.get("definicion", "")},
        {"indicador": "Desperdicio evitado estimado", "cantidad": num(evi.get("unidades")), "unidad": "unidades",
         "valor": None,
         "detalle": f"Contrafactual orgánico {num(evi.get('contrafactual_organico')):,.2f}; "
                    f"causal {num(evi.get('porcentaje_causal')):.1f} %",
         "definicion": evi.get("definicion", "")},
        {"indicador": "Reducción observada de merma", "cantidad": num(red.get("merma_reciente_unidades")),
         "unidad": "unidades (merma reciente)", "valor": None,
         "detalle": f"Tasa {num(red.get('tasa_reciente_pct')):.2f} % vs base {num(red.get('tasa_base_historica_pct')):.2f} % "
                    f"(cambio {num(red.get('cambio_puntos_pct')):.2f} pp, {int(num(red.get('ventana_dias')))} días)",
         "definicion": red.get("definicion", "")},
        {"indicador": "CO₂e evitado estimado", "cantidad": num(co2.get("kg_co2e")), "unidad": "kg CO₂e", "valor": None,
         "detalle": f"{num(co2.get('toneladas_co2e')):,.3f} t; factor {co2.get('factor', '')}",
         "definicion": co2.get("definicion", "")},
    ]


def _grafica(titulo: str, categorias: list[str], serie: str, valores: list[float], tono: str) -> QChartView:
    """Barras con una serie, fondo transparente y colores del tema."""
    barras = QBarSet(serie)
    barras.append([float(v) for v in valores])
    barras.setColor(theme.color(tono))
    series = QBarSeries()
    series.append(barras)
    series.setLabelsVisible(True)
    chart = QChart()
    chart.addSeries(series)
    chart.setTitle(titulo)
    chart.setBackgroundVisible(False)
    chart.setTitleBrush(theme.color("text"))
    chart.legend().setVisible(True)
    chart.legend().setLabelColor(theme.color("text"))
    eje_x = QBarCategoryAxis()
    eje_x.append(categorias)
    eje_x.setLabelsColor(theme.color("text2"))
    eje_y = QValueAxis()
    eje_y.setLabelFormat("%.0f")
    eje_y.setLabelsColor(theme.color("text2"))
    eje_y.setRange(0, max([float(v) for v in valores] + [1.0]) * 1.3)
    chart.addAxis(eje_x, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(eje_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(eje_x)
    series.attachAxis(eje_y)
    vista = QChartView(chart)
    vista.setRenderHint(QPainter.RenderHint.Antialiasing)
    vista.setMinimumHeight(240)
    vista.setMinimumWidth(380)
    vista.setStyleSheet("background: transparent;")
    return vista


class MermasPage(BasePage):
    title = "Mermas y desperdicio"
    subtitle = "Producto en riesgo, desperdicio proyectado, recuperado, evitado, reducción observada y CO₂e"
    icon = "SP_TrashIcon"
    roles = ()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.btn_actualizar = self.actions.add_button("Actualizar", self.refresh, variant="primary",
                                                      icon="SP_BrowserReload")
        self.btn_exportar = self.actions.add_button("Exportar reporte", self.exportar, icon="SP_DialogSaveButton")
        self.btn_imprimir = self.actions.add_button("Imprimir reporte", self.imprimir, icon="printer")

        self.kpi_riesgo = KpiCard("Producto en riesgo (unid.)")
        self.kpi_proyectado = KpiCard("Desperdicio proyectado (unid.)")
        self.kpi_recuperado = KpiCard("Producto recuperado (unid.)")
        self.kpi_evitado = KpiCard("Desperdicio evitado estimado (unid.)")
        self.kpi_reduccion = KpiCard("Merma reciente vs histórico")
        self.kpi_co2e = KpiCard("CO₂e evitado estimado")
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, k in enumerate((self.kpi_riesgo, self.kpi_proyectado, self.kpi_recuperado,
                               self.kpi_evitado, self.kpi_reduccion, self.kpi_co2e)):
            grid.addWidget(k, i // 3, i % 3)
        self.body.addLayout(grid)
        self.esg_label = secondary_label("")
        self.body.addWidget(self.esg_label)

        self.graficas = QHBoxLayout()
        self.graficas.setSpacing(12)
        self.chart_view = _grafica("Indicadores de desperdicio (unidades)", [], "Unidades", [], "primary")
        self.chart_triage = _grafica("Triage: lotes por acción", [], "Lotes", [], "info")
        self.graficas.addWidget(self.chart_view, 1)
        self.graficas.addWidget(self.chart_triage, 1)
        self.body.addLayout(self.graficas)

        self.table_indicadores = DataTable(empty_text="Sin datos de medición. Pulsa Actualizar.",
                                           title="Mermas y desperdicio: indicadores", filterable=False)
        self.table_indicadores.set_columns([
            ("indicador", "Indicador"), ("cantidad", "Cantidad", "num"), ("unidad", "Medida"),
            ("valor", "Valor", "money"), ("detalle", "Detalle"), ("definicion", "Definición"),
        ])
        self.table_triage = DataTable(empty_text="Sin lotes evaluados por el triage.",
                                      title="Triage por lote")
        self.table_triage.set_columns([
            ("producto", "Producto"), ("locacion", "Locación"), ("codigo_lote_prov", "Lote"),
            ("accion", "Acción"), ("clasificacion", "Clasificación"),
            ("cantidad_disponible", "Disponible", "num"), ("dias_restantes", "Días", "int"),
            ("unidades_en_riesgo", "En riesgo", "num"), ("costo_merma_potencial", "Costo merma", "money"),
            ("explicacion", "Explicación"),
        ])
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table_indicadores, "Indicadores")
        self.tabs.addTab(self.table_triage, "Triage por lote")
        self.body.addWidget(self.tabs, 1)

    # ---- red
    def refresh(self) -> None:
        self.ctx.run(self._consultar, on_ok=self._mostrar, busy=self.btn_actualizar)

    def _consultar(self) -> dict:
        api = self.ctx.api
        return {
            "waste": api.call("alerts", "GET", "/api/v1/alerts/waste-measurement",
                              expect_root="medicion_desperdicio"),
            "carbon": api.call("alerts", "GET", "/api/v1/alerts/esg/carbon-avoided",
                               expect_root="reporte_esg_sostenibilidad"),
            "triage": api.call("planning", "GET", "/api/v1/planning/triage", expect_root="triage_evaluation"),
        }

    # ---- presentación
    def _mostrar(self, datos: dict) -> None:
        waste, carbon, triage = _d(datos.get("waste")), _d(datos.get("carbon")), _d(datos.get("triage"))
        filas = filas_indicadores(waste)
        self.table_indicadores.set_rows(filas)
        riesgo, proy = filas[0], filas[1]
        self.kpi_riesgo.set_value(f"{riesgo['cantidad']:,.2f}", f"${riesgo['valor']:,.2f} · {riesgo['detalle']}",
                                  tone="warning" if riesgo["cantidad"] else None)
        self.kpi_proyectado.set_value(f"{proy['cantidad']:,.2f}", f"${proy['valor']:,.2f}",
                                      tone="danger" if proy["cantidad"] else None)
        self.kpi_recuperado.set_value(f"{filas[2]['cantidad']:,.2f}", f"${filas[2]['valor']:,.2f}")
        self.kpi_evitado.set_value(f"{filas[3]['cantidad']:,.2f}", filas[3]["detalle"])
        red = _d(waste.get("reduccion_observada_merma"))
        self.kpi_reduccion.set_value(f"{num(red.get('tasa_reciente_pct')):.2f} %",
                                     f"base histórica {num(red.get('tasa_base_historica_pct')):.2f} %")
        self.kpi_co2e.set_value(f"{filas[5]['cantidad']:,.1f} kg", f"{num(_d(waste.get('co2e_evitado_estimado')).get('toneladas_co2e')):,.3f} t")
        self.esg_label.setText(
            f"Reporte ESG: alimento recuperado {num(carbon.get('alimento_recuperado_kg')):,.1f} kg · "
            f"desperdicio evitado neto {num(carbon.get('desperdicio_evitado_neto_kg')):,.1f} kg · "
            f"ahorro financiero ${num(carbon.get('ahorro_financiero_mxn')):,.2f} · "
            f"CO₂e evitado {num(carbon.get('co2e_evitado_kg')):,.1f} kg · {carbon.get('factor_conversion', '')}")

        self._reemplazar_grafica("chart_view", "Indicadores de desperdicio (unidades)",
                                 ["Riesgo", "Proyect.", "Recup.", "Evitado"], "Unidades",
                                 [f["cantidad"] for f in filas[:4]], "primary")
        resumen = _d(triage.get("resumen"))
        self._reemplazar_grafica("chart_triage", "Triage: lotes por acción", [a.capitalize() for a in _ACCIONES_TRIAGE], "Lotes",
                                 [num(resumen.get(a)) for a in _ACCIONES_TRIAGE], "info")
        decisiones = triage.get("decisiones")
        self.table_triage.set_rows([d for d in (decisiones if isinstance(decisiones, list) else []) if isinstance(d, dict)])

    def _reemplazar_grafica(self, atributo: str, titulo, categorias, serie, valores, tono) -> None:
        viejo = getattr(self, atributo)
        nuevo = _grafica(titulo, categorias, serie, valores, tono)
        self.graficas.replaceWidget(viejo, nuevo)
        viejo.deleteLater()
        setattr(self, atributo, nuevo)

    # ---- reporte
    def exportar(self) -> None:
        ruta = self.table_indicadores.export_csv_dialog()
        if ruta:
            self.ctx.log.record("EXPORTAR_REPORTE_MERMAS", f"Indicadores de mermas exportados a {ruta}")

    def imprimir(self) -> None:
        if self.table_indicadores.print_table("Mermas y desperdicio: indicadores", self):
            self.ctx.log.record("IMPRIMIR_REPORTE_MERMAS", "Reporte de mermas y desperdicio impreso")
