"""Newsvendor: cantidad óptima de compra para un SKU y tienda frente a una política simple.

El servicio (`POST /planning/newsvendor/evaluate`) solo acepta `id_sku`, `id_locacion` y
`horizonte`; los costos de faltante y excedente y el valor de salvamento los deriva él
mismo del catálogo, por eso aquí se muestran como resultado y no como entrada.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QSpinBox

from ..widgets import DataTable, KpiCard, button, secondary_label, set_tone
from .base import BasePage
from .tablero import _dic, _lista, _num

HORIZONTE_MAX = 365


def validar_parametros(id_sku, id_locacion, horizonte) -> list[str]:
    """Errores (en español) de los parámetros del formulario; vacío si todo es válido."""
    errores = []
    if not isinstance(id_sku, int) or isinstance(id_sku, bool) or id_sku < 1:
        errores.append("Elige un SKU.")
    if not isinstance(id_locacion, int) or isinstance(id_locacion, bool) or id_locacion < 1:
        errores.append("Elige una tienda.")
    if not isinstance(horizonte, int) or isinstance(horizonte, bool) or not 1 <= horizonte <= HORIZONTE_MAX:
        errores.append(f"El horizonte debe estar entre 1 y {HORIZONTE_MAX} días.")
    return errores


class NewsvendorPage(BasePage):
    title = "Newsvendor"
    subtitle = "Cantidad óptima a comprar según el costo de faltante y de excedente, contra una política simple"
    icon = "SP_DialogApplyButton"
    roles = ("planner", "buyer")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.btn_actualizar = self.actions.add_button("Actualizar catálogos", self.refresh,
                                                      icon="SP_BrowserReload")
        self.cmb_sku = QComboBox()
        self.cmb_tienda = QComboBox()
        self.spn_horizonte = QSpinBox()
        self.spn_horizonte.setRange(1, HORIZONTE_MAX)
        self.spn_horizonte.setValue(7)
        form = QFormLayout()
        form.addRow("SKU", self.cmb_sku)
        form.addRow("Tienda", self.cmb_tienda)
        form.addRow("Horizonte (días)", self.spn_horizonte)
        self.btn_evaluar = button("Evaluar", self.evaluar, variant="primary", icon="SP_DialogApplyButton")
        self.lbl_estado = secondary_label("")
        fila = QHBoxLayout()
        fila.addLayout(form, 1)
        fila.addWidget(self.btn_evaluar)
        fila.addStretch(2)
        self.body.addLayout(fila)
        self.body.addWidget(self.lbl_estado)

        kpis = QHBoxLayout()
        kpis.setSpacing(12)
        self.kpi_sugerida = KpiCard("Cantidad sugerida")
        self.kpi_optima = KpiCard("Cantidad Newsvendor")
        self.kpi_fractil = KpiCard("Ratio crítico")
        self.kpi_costo = KpiCard("Costo esperado")
        self.kpi_ahorro = KpiCard("Ahorro vs política simple")
        for k in (self.kpi_sugerida, self.kpi_optima, self.kpi_fractil, self.kpi_costo, self.kpi_ahorro):
            kpis.addWidget(k)
        kpis.addStretch(1)
        self.body.addLayout(kpis)

        self.lbl_advertencias = QLabel("")
        self.lbl_advertencias.setWordWrap(True)
        self.lbl_advertencias.hide()
        set_tone(self.lbl_advertencias, "warning")
        self.body.addWidget(self.lbl_advertencias)

        self.tabla_comp = DataTable(empty_text="Aún no hay evaluación. Elige SKU y tienda y pulsa Evaluar.",
                                    title="Newsvendor vs política simple", filterable=False)
        self.tabla_comp.set_columns([("politica", "Política"), ("cantidad", "Cantidad", "num"),
                                     ("stock_objetivo", "Stock objetivo", "num"),
                                     ("costo_esperado", "Costo esperado", "money")])
        self.tabla_det = DataTable(empty_text="Sin detalle", title="Detalle del modelo", filterable=False)
        self.tabla_det.set_columns([("concepto", "Concepto"), ("valor", "Valor")])
        fila_t = QHBoxLayout()
        fila_t.addWidget(self.tabla_comp, 1)
        fila_t.addWidget(self.tabla_det, 1)
        self.body.addLayout(fila_t, 1)

    # ---- catálogos
    def refresh(self) -> None:
        self.ctx.run(self._cargar, on_ok=self._llenar, on_error=self._error, busy=self.btn_actualizar)

    def _cargar(self) -> tuple[list, list]:
        locs = self.ctx.api.call("catalog", "GET", "/api/v1/catalog/locations")
        prods = self.ctx.api.call("catalog", "GET", "/api/v1/catalog/products", params={"por_pagina": 100})
        return _lista(_dic(locs).get("locaciones")), _lista(_dic(prods).get("productos"))

    def _llenar(self, res) -> None:
        locs, prods = res
        self._rellenar(self.cmb_tienda, [(int(_num(x.get("id_locacion"))), f"{x.get('nombre')} ({x.get('tipo_locacion')})")
                                         for x in locs if str(x.get("activo", "true")).lower() != "false"])
        self._rellenar(self.cmb_sku, [(int(_num(x.get("id_sku"))), f"{x.get('nombre')} (#{x.get('id_sku')})")
                                      for x in prods])

    @staticmethod
    def _rellenar(combo: QComboBox, items: list[tuple[int, str]]) -> None:
        actual = combo.currentData()
        combo.clear()
        for dato, texto in items:
            combo.addItem(texto, dato)
        idx = combo.findData(actual) if actual is not None else 0
        combo.setCurrentIndex(max(idx, 0))

    # ---- evaluación
    def evaluar(self) -> None:
        sku, loc, h = self.cmb_sku.currentData(), self.cmb_tienda.currentData(), self.spn_horizonte.value()
        errores = validar_parametros(sku, loc, h)
        if errores:
            self.lbl_estado.setText(" ".join(errores))
            set_tone(self.lbl_estado, "danger")
            return
        set_tone(self.lbl_estado, None)
        self.lbl_estado.setText("")
        cuerpo = {"id_sku": sku, "id_locacion": loc, "horizonte": h}
        self.ctx.run(self._llamar, cuerpo, on_ok=lambda r, c=cuerpo: self._mostrar(r, c),
                     on_error=self._error, busy=self.btn_evaluar)

    def _llamar(self, cuerpo: dict):
        return self.ctx.api.call("planning", "POST", "/api/v1/planning/newsvendor/evaluate", body=cuerpo,
                                 body_root="newsvendor_request", expect_root="newsvendor_evaluation")

    def _mostrar(self, datos, cuerpo: dict) -> None:
        d = _dic(datos)
        nv = _dic(d.get("newsvendor"))
        self.ctx.log.record("NEWSVENDOR", f"sku={cuerpo['id_sku']} tienda={cuerpo['id_locacion']} "
                            f"h={cuerpo['horizonte']} cantidad={nv.get('cantidad_newsvendor', '-')}")
        self.kpi_sugerida.set_value(f"{_num(d.get('cantidad_sugerida')):,.0f}",
                                    sub=f"{d.get('producto', '')} · {d.get('locacion', '')}", tone="success")
        self.kpi_optima.set_value(f"{_num(nv.get('cantidad_newsvendor')):,.1f}",
                                  sub=f"Demanda del horizonte {_num(d.get('demanda_horizonte')):,.1f}")
        self.kpi_fractil.set_value(f"{_num(nv.get('fractil_critico')):.3f}",
                                   sub=f"z = {_num(nv.get('z_score')):.2f}")
        self.kpi_costo.set_value(f"${_num(nv.get('costo_esperado_newsvendor')):,.2f}",
                                 sub=f"Simple: ${_num(nv.get('costo_esperado_simple')):,.2f}")
        ahorro = _num(nv.get("ahorro_esperado"))
        self.kpi_ahorro.set_value(f"${ahorro:,.2f}", tone="success" if ahorro > 0 else None)
        self.tabla_comp.set_rows([
            {"politica": "Newsvendor", "cantidad": nv.get("cantidad_newsvendor"),
             "stock_objetivo": nv.get("stock_objetivo_newsvendor"), "costo_esperado": nv.get("costo_esperado_newsvendor")},
            {"politica": "Política simple", "cantidad": nv.get("cantidad_politica_simple"),
             "stock_objetivo": nv.get("stock_objetivo_simple"), "costo_esperado": nv.get("costo_esperado_simple")},
        ])
        self.tabla_det.set_rows([
            {"concepto": "Costo de faltante", "valor": f"${_num(nv.get('costo_faltante')):,.2f}"},
            {"concepto": "Costo de excedente", "valor": f"${_num(nv.get('costo_excedente')):,.2f}"},
            {"concepto": "Valor de salvamento", "valor": f"${_num(nv.get('valor_salvamento')):,.2f}"},
            {"concepto": "Ratio crítico", "valor": f"{_num(nv.get('fractil_critico')):.4f}"},
            {"concepto": "Desviación del horizonte", "valor": f"{_num(nv.get('sigma_horizonte')):,.2f}"},
            {"concepto": "Inventario útil", "valor": f"{_num(d.get('inventario_util')):,.0f}"},
            {"concepto": "Inventario en riesgo", "valor": f"{_num(d.get('inventario_riesgo')):,.0f}"},
            {"concepto": "Acotado por caducidad",
             "valor": "Sí" if str(nv.get("acotado_por_caducidad")).lower() == "true" else "No"},
        ])
        adv = d.get("advertencias")
        textos = [str(x) for x in adv] if isinstance(adv, list) else ([str(adv)] if adv else [])
        self.lbl_advertencias.setText("Advertencias: " + " · ".join(textos) if textos else "")
        self.lbl_advertencias.setVisible(bool(textos))

    def _error(self, exc: BaseException) -> None:
        self.ctx.show_error(exc, self)
