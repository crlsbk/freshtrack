"""Pronósticos: corrida de pronóstico, comparación de modelos (backtest) y deriva (drift)."""

from __future__ import annotations

from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis,
)
from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from ...core.errors import ApiError
from .. import theme
from ..widgets import DataTable, KpiCard, button, secondary_label
from .base import BasePage
from .tablero import _dic, _lista, _num, productos_todos, etiqueta_metodo  # noqa: F401 - etiqueta_metodo se reexporta

METODOS = (("AUTO", "Automático (mejor modelo por serie)"), ("MEDIA_MOVIL", "Media móvil"),
           ("MEDIA_MOVIL_PONDERADA", "Media móvil ponderada"),
           ("SUAVIZACION_EXPONENCIAL", "Suavización exponencial"))
_ESTADO_DRIFT = {"CONFIABLE": "OK", "VIGILANCIA": "VIGILANCIA", "NO_CONFIABLE": "CRÍTICO", "SIN_DATOS": "INFO"}
_COLORES = ("primary", "info", "warning", "danger")
GRAFICA_INICIAL = "Elige tienda y SKU y pulsa «Generar pronóstico»."


def _fecha(texto) -> QDateTime:
    return QDateTime.fromString(str(texto)[:10], "yyyy-MM-dd")


def nuevo_grafico(titulo: str) -> QChartView:
    """QChartView con fondo transparente y leyenda visible, siguiendo el tema."""
    chart = QChart()
    chart.setTitle(titulo)
    chart.setBackgroundVisible(False)
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
    chart.setTitleBrush(theme.color("text"))
    chart.legend().setLabelColor(theme.color("text"))
    vista = QChartView(chart)
    vista.setRenderHint(QPainter.RenderHint.Antialiasing)
    vista.setStyleSheet("background: transparent;")
    vista.setMinimumHeight(240)
    return vista


def _ejes_texto(eje) -> None:
    eje.setLabelsColor(theme.color("text2"))
    eje.setGridLineColor(QColor(theme.tokens()["border"]))


def graficar_lineas(vista: QChartView, titulo: str, series: list[tuple[str, list[tuple[str, float]]]]) -> None:
    """Dibuja hasta 4 series (nombre, [(fecha 'YYYY-MM-DD', valor)])."""
    chart = vista.chart()
    chart.removeAllSeries()
    for eje in chart.axes():
        chart.removeAxis(eje)
    chart.setTitle(titulo)
    xs, ys = QDateTimeAxis(), QValueAxis()
    xs.setFormat("dd MMM")
    ys.setLabelFormat("%.0f")
    for i, (nombre, puntos) in enumerate(series[:4]):
        s = QLineSeries()
        s.setName(nombre)
        pen = s.pen()
        pen.setColor(theme.color(_COLORES[i]))
        pen.setWidth(2)
        s.setPen(pen)
        for fecha, valor in puntos:
            s.append(float(_fecha(fecha).toMSecsSinceEpoch()), float(valor))
        chart.addSeries(s)
    if not chart.series():
        return
    chart.addAxis(xs, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(ys, Qt.AlignmentFlag.AlignLeft)
    for s in chart.series():
        s.attachAxis(xs)
        s.attachAxis(ys)
    _ejes_texto(xs)
    _ejes_texto(ys)
    ys.applyNiceNumbers()


def graficar_barras(vista: QChartView, titulo: str, categorias: list[str], series: list[tuple[str, list[float]]]) -> None:
    chart = vista.chart()
    chart.removeAllSeries()
    for eje in chart.axes():
        chart.removeAxis(eje)
    chart.setTitle(titulo)
    if not categorias:
        return
    barras = QBarSeries()
    for i, (nombre, valores) in enumerate(series[:4]):
        conjunto = QBarSet(nombre)
        conjunto.setColor(theme.color(_COLORES[i]))
        conjunto.append(valores)
        barras.append(conjunto)
    chart.addSeries(barras)
    ex, ey = QBarCategoryAxis(), QValueAxis()
    ex.append(categorias)
    chart.addAxis(ex, Qt.AlignmentFlag.AlignBottom)
    chart.addAxis(ey, Qt.AlignmentFlag.AlignLeft)
    barras.attachAxis(ex)
    barras.attachAxis(ey)
    ey.setLabelFormat("%.1f")
    _ejes_texto(ex)
    _ejes_texto(ey)
    ey.applyNiceNumbers()


def _combo(items: list[tuple[object, str]]) -> QComboBox:
    c = QComboBox()
    for dato, texto in items:
        c.addItem(texto, dato)
    return c


class PronosticosPage(BasePage):
    title = "Pronósticos"
    subtitle = "Corre pronósticos por tienda y SKU, compara modelos contra el ingenuo y vigila la deriva"
    icon = "SP_FileDialogContentsView"
    roles = ("planner", "buyer")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.btn_actualizar = self.actions.add_button("Actualizar catálogos", self.refresh,
                                                      icon="SP_BrowserReload")

        # Filtros comunes (tienda y SKU)
        self.cmb_tienda = _combo([(None, "Todas las tiendas")])
        self.cmb_sku = _combo([(None, "Todos los SKU")])
        filtros = QHBoxLayout()
        filtros.setSpacing(12)
        filtros.addWidget(secondary_label("Tienda"))
        filtros.addWidget(self.cmb_tienda, 1)
        filtros.addWidget(secondary_label("SKU"))
        filtros.addWidget(self.cmb_sku, 1)
        self.body.addLayout(filtros)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._armar_pronostico(), "Pronóstico")
        self.tabs.addTab(self._armar_backtest(), "Comparar modelos")
        self.tabs.addTab(self._armar_drift(), "Drift")
        self.body.addWidget(self.tabs, 1)

    # ================================================================== pestaña Pronóstico
    def _armar_pronostico(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.cmb_metodo = _combo([(k, t) for k, t in METODOS])
        self.spn_horizonte = QSpinBox()
        self.spn_horizonte.setRange(1, 90)
        self.spn_horizonte.setValue(7)
        self.spn_ventana = QSpinBox()
        self.spn_ventana.setRange(2, 365)
        self.spn_ventana.setValue(28)
        self.spn_alpha = QDoubleSpinBox()
        self.spn_alpha.setRange(0.01, 1.0)
        self.spn_alpha.setDecimals(2)
        self.spn_alpha.setSingleStep(0.05)
        self.spn_alpha.setValue(0.30)
        self.spn_historia = QSpinBox()
        self.spn_historia.setRange(14, 730)
        self.spn_historia.setValue(120)
        form.addRow("Método", self.cmb_metodo)
        form.addRow("Horizonte (días)", self.spn_horizonte)
        form.addRow("Ventana (días)", self.spn_ventana)
        form.addRow("Alpha (suavización)", self.spn_alpha)
        form.addRow("Días de historia", self.spn_historia)
        self.btn_correr = button("Generar pronóstico", self.generar, variant="primary", icon="SP_MediaPlay")
        self.btn_ultimo = button("Ver último guardado", self.ver_ultimo, icon="SP_FileDialogContentsView",
                                 tooltip="Serie guardada en MongoDB para la tienda y el SKU elegidos")
        botones = QHBoxLayout()
        botones.addWidget(self.btn_correr)
        botones.addWidget(self.btn_ultimo)
        botones.addStretch(1)
        self.lbl_estado = secondary_label("")
        if not self._puede_correr():
            self.btn_correr.setEnabled(False)
            self.btn_correr.setToolTip("Solo el rol planificador (o admin) puede generar pronósticos")
            self.lbl_estado.setText("Tu rol puede consultar pronósticos pero no generarlos.")
        arriba = QHBoxLayout()
        arriba.addLayout(form, 0)
        izq = QVBoxLayout()
        izq.addLayout(botones)
        izq.addWidget(self.lbl_estado)
        izq.addStretch(1)
        arriba.addLayout(izq, 1)
        lay.addLayout(arriba)

        kpis = QHBoxLayout()
        kpis.setSpacing(12)
        self.kpi_metodo = KpiCard("Método")
        self.kpi_series = KpiCard("Series")
        self.kpi_mae = KpiCard("MAE")
        self.kpi_wmape = KpiCard("WAPE")
        self.kpi_sesgo = KpiCard("Sesgo")
        for k in (self.kpi_metodo, self.kpi_series, self.kpi_mae, self.kpi_wmape, self.kpi_sesgo):
            kpis.addWidget(k)
        kpis.addStretch(1)
        lay.addLayout(kpis)

        self.grafico = nuevo_grafico(GRAFICA_INICIAL)
        self.tabla = DataTable(empty_text="Aún no hay un pronóstico. Elige tienda y SKU y pulsa Generar.",
                               title="Pronóstico diario")
        self.tabla.set_columns([("fecha", "Fecha"), ("id_sku", "SKU"), ("id_locacion", "Tienda"),
                                ("valor", "Pronóstico", "num"), ("inferior", "Inferior", "num"),
                                ("superior", "Superior", "num")])
        self.tabla_series = DataTable(empty_text="Sin métricas por serie", title="Métricas por serie",
                                      filterable=False)
        self.tabla_series.set_columns([("id_sku", "SKU"), ("id_locacion", "Tienda"), ("metodo", "Método ganador"),
                                       ("mae", "MAE", "num"), ("wmape", "WAPE", "pct"), ("sesgo", "Sesgo", "num"),
                                       ("mejora", "Mejora vs ingenuo", "pct")])
        sub = QTabWidget()
        sub.addTab(self.grafico, "Gráfica")
        sub.addTab(self.tabla, "Detalle diario")
        sub.addTab(self.tabla_series, "Métricas por serie")
        self.sub_resultado = sub
        lay.addWidget(sub, 1)
        return w

    def _puede_correr(self) -> bool:
        s = self.ctx.api.session
        return s is None or s.can("planner")

    def _seleccion(self) -> tuple[int | None, int | None]:
        return self.cmb_sku.currentData(), self.cmb_tienda.currentData()

    def cuerpo_pronostico(self) -> dict:
        """Cuerpo de forecast_request; omite tienda y SKU cuando se eligió "todos"."""
        sku, loc = self._seleccion()
        cuerpo: dict = {
            "metodo": self.cmb_metodo.currentData(),
            "horizonte": self.spn_horizonte.value(),
            "ventana": self.spn_ventana.value(),
            "alpha": round(self.spn_alpha.value(), 2),
            "dias_historia": self.spn_historia.value(),
        }
        if loc is not None:
            cuerpo["id_locacion"] = int(loc)
        if sku is not None:
            cuerpo["id_sku"] = int(sku)
        return cuerpo

    def generar(self) -> None:
        if not self._puede_correr():
            return
        cuerpo = self.cuerpo_pronostico()
        self.ctx.run(self._llamar_run, cuerpo, on_ok=lambda r, c=cuerpo: self._mostrar_run(r, c),
                     on_error=self._error, busy=self.btn_correr)

    def _llamar_run(self, cuerpo: dict):
        return self.ctx.api.call("planning", "POST", "/api/v1/planning/forecast/run", body=cuerpo,
                                 body_root="forecast_request", body_xsd="forecast_request",
                                 expect_root="forecast_run_result")

    def _mostrar_run(self, datos, cuerpo: dict) -> None:
        d = _dic(datos)
        self.ctx.log.record("PRONOSTICO", f"{cuerpo.get('metodo')} h={cuerpo.get('horizonte')} "
                            f"sku={cuerpo.get('id_sku', 'todos')} tienda={cuerpo.get('id_locacion', 'todas')} "
                            f"run={d.get('id_run') or '-'}")
        self.kpi_metodo.set_value(str(d.get("metodo_etiqueta") or etiqueta_metodo(d.get("metodo")) or "—"),
                                  sub=str(d.get("locacion") or ""))
        self.kpi_series.set_value(f"{_num(d.get('series')):,.0f}", sub=f"{_num(d.get('duracion_ms')):,.0f} ms")
        for kpi, clave, suf in ((self.kpi_mae, "mae", ""), (self.kpi_wmape, "wmape", " %"),
                                (self.kpi_sesgo, "sesgo", "")):
            v = str(d.get(clave, "")).strip()
            kpi.set_value(f"{_num(v):,.2f}{suf}" if v else "—")
        filas, metricas, series = [], [], []
        for r in _lista(d.get("resultados")):
            sku, loc = r.get("id_sku"), r.get("id_locacion")
            m = _dic(r.get("metricas"))
            metricas.append({"id_sku": sku, "id_locacion": loc, "metodo": etiqueta_metodo(r.get("metodo_ganador")),
                             "mae": m.get("mae"), "wmape": m.get("wmape"), "sesgo": m.get("sesgo"),
                             "mejora": r.get("mejora_vs_naive_pct")})
            puntos = []
            for p in _lista(r.get("pronostico")):
                filas.append({"fecha": p.get("fecha"), "id_sku": sku, "id_locacion": loc, "valor": p.get("valor")})
                puntos.append((str(p.get("fecha")), _num(p.get("valor"))))
            series.append((f"SKU {sku} · tienda {loc}", puntos))
        self.tabla.set_rows(filas)
        self.tabla_series.set_rows(metricas)
        graficar_lineas(self.grafico, "Demanda pronosticada", series)
        msg = f"Pronóstico generado: {len(metricas)} serie(s)."
        if len(series) > 4:
            msg += f" Mostrando 4 de {len(series)} series; filtra por tienda o SKU para ver otra."
        self.lbl_estado.setText(msg)

    def ver_ultimo(self) -> None:
        sku, loc = self._seleccion()
        if sku is None or loc is None:
            self.lbl_estado.setText("Elige una tienda y un SKU concretos para ver el último pronóstico guardado.")
            return
        self.ctx.run(self._llamar_ultimo, int(sku), int(loc), on_ok=self._mostrar_ultimo,
                     on_error=self._error_ultimo, busy=self.btn_ultimo)

    def _llamar_ultimo(self, sku: int, loc: int):
        return self.ctx.api.call("planning", "GET", f"/api/v1/planning/forecast/latest/{sku}/{loc}")

    def _mostrar_ultimo(self, datos) -> None:
        d = _dic(datos)
        m = _dic(d.get("metricas"))
        self.kpi_metodo.set_value(etiqueta_metodo(d.get("modelo")) or "—", sub=f"Calculado {str(d.get('fecha_calculo', ''))[:16]}")
        self.kpi_series.set_value("1")
        for kpi, clave, suf in ((self.kpi_mae, "mae", ""), (self.kpi_wmape, "wmape", " %"),
                                (self.kpi_sesgo, "sesgo", "")):
            v = str(m.get(clave, "")).strip()
            kpi.set_value(f"{_num(v):,.2f}{suf}" if v else "—")
        sku, loc = d.get("id_sku"), d.get("id_locacion")
        filas, central, bajo, alto = [], [], [], []
        for p in _lista(d.get("puntos")):
            f = str(p.get("fecha", ""))[:10]
            filas.append({"fecha": f, "id_sku": sku, "id_locacion": loc, "valor": p.get("demanda_pronosticada"),
                          "inferior": p.get("intervalo_inferior"), "superior": p.get("intervalo_superior")})
            central.append((f, _num(p.get("demanda_pronosticada"))))
            bajo.append((f, _num(p.get("intervalo_inferior"))))
            alto.append((f, _num(p.get("intervalo_superior"))))
        self.tabla.set_rows(filas)
        self.tabla_series.set_rows([])
        graficar_lineas(self.grafico, "Último pronóstico guardado",
                        [("Pronóstico", central), ("Inferior", bajo), ("Superior", alto)])
        self.lbl_estado.setText("Mostrando el último pronóstico guardado.")

    def _error_ultimo(self, exc: BaseException) -> None:
        if isinstance(exc, ApiError) and exc.status == 404:
            self.tabla.set_rows([])
            self.tabla.set_empty_text("Sin pronóstico guardado para este SKU y tienda.")
            self.tabla_series.set_rows([])
            graficar_lineas(self.grafico, "Sin pronóstico guardado", [])
            self.lbl_estado.setText("Sin pronóstico guardado para este SKU y tienda.")
            return
        self.ctx.show_error(exc, self)

    # ================================================================== pestaña Comparar modelos
    def _armar_backtest(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        fila = QHBoxLayout()
        self.spn_bt_horizonte = QSpinBox()
        self.spn_bt_horizonte.setRange(1, 90)
        self.spn_bt_horizonte.setValue(7)
        self.btn_backtest = button("Comparar modelos", self.cargar_backtest, variant="primary",
                                   icon="SP_BrowserReload")
        fila.addWidget(secondary_label("Horizonte (días)"))
        fila.addWidget(self.spn_bt_horizonte)
        fila.addWidget(self.btn_backtest)
        fila.addStretch(1)
        lay.addLayout(fila)
        self.lbl_backtest = secondary_label("Usa la tienda y el SKU de arriba para acotar; sin elegir compara todo.")
        lay.addWidget(self.lbl_backtest)
        self.tabla_bt = DataTable(empty_text="Pulsa Comparar modelos para ver MAE, WAPE y sesgo por modelo.",
                                  title="Comparación de modelos", filterable=False)
        self.tabla_bt.set_columns([("modelo", "Modelo"), ("mae", "MAE", "num"), ("rmse", "RMSE", "num"),
                                   ("wmape", "WAPE", "pct"), ("sesgo", "Sesgo", "num"),
                                   ("puntos", "Puntos", "int"), ("mejora", "Mejora MAE vs ingenuo", "pct")])
        self.grafico_bt = nuevo_grafico("MAE y WAPE por modelo")
        lay.addWidget(self.tabla_bt, 1)
        lay.addWidget(self.grafico_bt, 1)
        return w

    def cargar_backtest(self) -> None:
        sku, loc = self._seleccion()
        params: dict = {"horizonte": self.spn_bt_horizonte.value()}
        if sku is not None:
            params["id_sku"] = int(sku)
        if loc is not None:
            params["id_locacion"] = int(loc)
        self.ctx.run(self._llamar_backtest, params, on_ok=self._mostrar_backtest, on_error=self._error,
                     busy=self.btn_backtest)

    def _llamar_backtest(self, params: dict):
        return self.ctx.api.call("planning", "GET", "/api/v1/planning/forecast/backtest", params=params,
                                 expect_root="forecast_backtest")

    def _mostrar_backtest(self, datos) -> None:
        d = _dic(datos)
        resumen = _dic(d.get("resumen_global"))
        naive = _dic(resumen.get("NAIVE"))
        naive_mae = _num(naive.get("mae"))
        filas = []
        for modelo, m in resumen.items():
            m = _dic(m)
            mae = _num(m.get("mae"))
            mejora = (naive_mae - mae) / naive_mae * 100 if modelo != "NAIVE" and naive_mae > 0 and m.get("mae") else None
            filas.append({"modelo": etiqueta_metodo(modelo), "mae": m.get("mae"),
                          "rmse": m.get("rmse"), "wmape": m.get("wmape"), "sesgo": m.get("sesgo"),
                          "puntos": m.get("puntos"), "mejora": mejora})
        self.tabla_bt.set_rows(filas)
        graficar_barras(self.grafico_bt, "MAE y WAPE por modelo", [f["modelo"] for f in filas],
                        [("MAE", [_num(f["mae"]) for f in filas]), ("WAPE (%)", [_num(f["wmape"]) for f in filas])])
        self.lbl_backtest.setText(f"{_num(d.get('total_series')):,.0f} serie(s) evaluadas con horizonte "
                                  f"{_num(d.get('horizonte')):,.0f} día(s).")

    # ================================================================== pestaña Drift
    def _armar_drift(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        fila = QHBoxLayout()
        self.spn_ventana_drift = QSpinBox()
        self.spn_ventana_drift.setRange(7, 90)
        self.spn_ventana_drift.setValue(14)
        self.btn_drift = button("Revisar deriva", self.cargar_drift, variant="primary", icon="SP_BrowserReload")
        fila.addWidget(secondary_label("Ventana reciente (días)"))
        fila.addWidget(self.spn_ventana_drift)
        fila.addWidget(self.btn_drift)
        fila.addStretch(1)
        lay.addLayout(fila)
        kpis = QHBoxLayout()
        kpis.setSpacing(12)
        self.kpi_confiables = KpiCard("Confiables")
        self.kpi_vigilancia = KpiCard("En vigilancia")
        self.kpi_no_conf = KpiCard("No confiables")
        self.kpi_anomalias = KpiCard("SKU con anomalía")
        for k in (self.kpi_confiables, self.kpi_vigilancia, self.kpi_no_conf, self.kpi_anomalias):
            kpis.addWidget(k)
        kpis.addStretch(1)
        lay.addLayout(kpis)
        self.tabla_drift = DataTable(empty_text="Pulsa Revisar deriva para ver la confiabilidad por tienda.",
                                     title="Deriva de modelos por tienda")
        self.tabla_drift.set_columns([
            ("locacion", "Tienda"), ("estado", "Estado", "status"), ("confiabilidad", "Confiabilidad"),
            ("psi", "PSI", "num"), ("cambio_nivel_pct", "Cambio de nivel", "pct"),
            ("ratio_volatilidad", "Volatilidad", "num"), ("dias_atipicos", "Días atípicos", "int"),
            ("productos_con_anomalia", "SKU con anomalía", "int"), ("motivos", "Motivos"),
            ("recomendacion", "Recomendación"),
        ])
        lay.addWidget(self.tabla_drift, 1)
        return w

    def cargar_drift(self) -> None:
        _sku, loc = self._seleccion()
        params: dict = {"ventana_reciente": self.spn_ventana_drift.value()}
        if loc is not None:
            params["id_locacion"] = int(loc)
        self.ctx.run(self._llamar_drift, params, on_ok=self._mostrar_drift, on_error=self._error,
                     busy=self.btn_drift)

    def _llamar_drift(self, params: dict):
        return self.ctx.api.call("planning", "GET", "/api/v1/planning/forecast/drift", params=params,
                                 expect_root="forecast_drift")

    def _mostrar_drift(self, datos) -> None:
        d = _dic(datos)
        r = _dic(d.get("resumen"))
        self.kpi_confiables.set_value(f"{_num(r.get('confiables')):,.0f}", tone="success")
        self.kpi_vigilancia.set_value(f"{_num(r.get('vigilancia')):,.0f}",
                                      tone="warning" if _num(r.get("vigilancia")) else None)
        self.kpi_no_conf.set_value(f"{_num(r.get('no_confiables')):,.0f}",
                                   tone="danger" if _num(r.get("no_confiables")) else None)
        self.kpi_anomalias.set_value(f"{_num(r.get('total_anomalias_sku')):,.0f}")
        filas = []
        for t in _lista(d.get("tiendas")):
            fila = dict(t)
            fila["estado"] = _ESTADO_DRIFT.get(str(t.get("estado", "")).upper(), t.get("estado", ""))
            motivos = t.get("motivos")
            fila["motivos"] = " · ".join(str(x) for x in motivos) if isinstance(motivos, list) else (motivos or "")
            filas.append(fila)
        self.tabla_drift.set_rows(filas)

    # ================================================================== catálogos y errores
    def refresh(self) -> None:
        self.ctx.run(self._cargar_catalogos, on_ok=self._llenar_catalogos, on_error=self._error,
                     busy=self.btn_actualizar)

    def _cargar_catalogos(self) -> tuple[list, list]:
        locs = self.ctx.api.call("catalog", "GET", "/api/v1/catalog/locations")
        return _lista(_dic(locs).get("locaciones")), productos_todos(self.ctx.api)

    def _llenar_catalogos(self, res) -> None:
        locs, prods = res
        self._rellenar(self.cmb_tienda, "Todas las tiendas",
                       [(int(_num(x.get("id_locacion"))), f"{x.get('nombre')} ({x.get('tipo_locacion')})")
                        for x in locs if str(x.get("activo", "true")).lower() != "false"])
        self._rellenar(self.cmb_sku, "Todos los SKU",
                       [(int(_num(x.get("id_sku"))), f"{x.get('nombre')} (#{x.get('id_sku')})") for x in prods])

    @staticmethod
    def _rellenar(combo: QComboBox, todos: str, items: list[tuple[int, str]]) -> None:
        actual = combo.currentData()
        combo.clear()
        combo.addItem(todos, None)
        for dato, texto in items:
            combo.addItem(texto, dato)
        idx = combo.findData(actual) if actual is not None else 0
        combo.setCurrentIndex(max(idx, 0))

    def _error(self, exc: BaseException) -> None:
        self.ctx.show_error(exc, self)
