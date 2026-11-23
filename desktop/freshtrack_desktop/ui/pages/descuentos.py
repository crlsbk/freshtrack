"""Descuentos preventivos por lote: generar sugerencias, aprobar y rechazar."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel

from ...core.xml_codec import as_list, num
from ..widgets import ask_text, button, confirm  # noqa: F401 - la base los resuelve por módulo
from .reabastecimiento import DecisionPage, _spin  # noqa: F401

ESTADOS = ("SUGERIDO", "APROBADO", "RECHAZADO", "APLICADO")


def margen_pct(fila: dict) -> float | None:
    """Margen sobre el precio con descuento: (nuevo - costo) / nuevo, en %."""
    nuevo, costo = num(fila.get("precio_nuevo"), 0.0), num(fila.get("precio_costo"), 0.0)
    return (nuevo - costo) / nuevo * 100 if nuevo > 0 else None


def _vigencia(fila: dict) -> str:
    dias, cad = fila.get("dias_restantes"), fila.get("fecha_caducidad")
    return f"{dias} d (vence {cad})" if dias not in (None, "") and cad else str(cad or dias or "")


class DescuentosPage(DecisionPage):
    title = "Descuentos"
    subtitle = "Descuentos preventivos para lotes próximos a caducar, respetando el margen"
    icon = "SP_DialogResetButton"
    roles = ("planner",)
    id_field = "id_descuento"
    entidad = "descuento"

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.btn_actualizar = self.actions.add_button("Actualizar", self.refresh, icon="SP_BrowserReload")
        self._herramientas_tabla()

        fila = QHBoxLayout()
        fila.setSpacing(8)
        fila.addWidget(QLabel("Estado"))
        self.cmb_estado = QComboBox()
        self.cmb_estado.addItem("Todos", "")
        for e in ESTADOS:
            self.cmb_estado.addItem(e.capitalize(), e)
        self.cmb_estado.currentIndexChanged.connect(lambda _i: self.refresh())
        fila.addWidget(self.cmb_estado)
        fila.addSpacing(16)
        fila.addWidget(QLabel("Caduca en"))
        self.spin_dias = _spin(5, 0, 60, " días")
        fila.addWidget(self.spin_dias)
        self.btn_generar = button("Generar descuentos", self._generar, variant="primary",
                                  icon="SP_FileDialogNewFolder")
        fila.addWidget(self.btn_generar)
        fila.addStretch(1)
        self.btn_aprobar = button("Aprobar", self._aprobar, variant="primary", icon="SP_DialogApplyButton")
        self.btn_rechazar = button("Rechazar", self._rechazar, variant="danger", icon="SP_DialogCancelButton")
        fila.addWidget(self.btn_aprobar)
        fila.addWidget(self.btn_rechazar)
        self.body.addLayout(fila)

        self.table.set_columns([
            ("producto", "Producto"), ("locacion", "Tienda"), ("descuento_pct", "Descuento", "pct"),
            ("precio_normal", "Precio normal", "money"), ("precio_nuevo", "Precio nuevo", "money"),
            ("margen", "Margen", "pct"), ("cantidad", "Cantidad", "num"), ("vigencia", "Vigencia"),
            ("ingreso_potencial", "Ingreso potencial", "money"), ("estado", "Estado", "status"),
            ("codigo_lote_prov", "Lote"),
        ])
        self._pie()
        self._actualizar_botones()

    def on_show(self) -> None:
        self._actualizar_botones()
        super().on_show()

    # ---- lectura
    def _consulta(self) -> Any:
        params: dict[str, Any] = {"limite": 300}
        estado = self.cmb_estado.currentData()
        if estado:
            params["estado"] = estado
        return self.ctx.api.call("planning", "GET", "/api/v1/planning/discounts", params=params)

    def _filas_de(self, datos: Any) -> list[dict]:
        d = datos if isinstance(datos, dict) else {}
        filas = [dict(f) for f in as_list(d.get("descuentos")) if isinstance(f, dict)]
        for f in filas:
            f["margen"] = margen_pct(f)
            f["vigencia"] = _vigencia(f)
        return filas

    def _despues_de_mostrar(self, datos: Any, filas: list[dict]) -> None:
        r = datos.get("resumen") if isinstance(datos, dict) and isinstance(datos.get("resumen"), dict) else {}
        self.status_label.setText(
            f"{len(filas)} descuentos · sugeridos {int(num(r.get('sugeridos')))}, aprobados "
            f"{int(num(r.get('aprobados')))}, rechazados {int(num(r.get('rechazados')))} · "
            f"ingreso potencial ${num(r.get('ingreso_potencial')):,.2f}")

    def _detalle(self, fila: dict) -> str:
        m = fila.get("margen")
        return (f"{fila.get('producto', '')} en {fila.get('locacion', '')} (lote {fila.get('codigo_lote_prov', '')})\n"
                f"Precio ${num(fila.get('precio_normal')):,.2f} → ${num(fila.get('precio_nuevo')):,.2f} "
                f"(-{num(fila.get('descuento_pct')):.1f} %), costo ${num(fila.get('precio_costo')):,.2f}\n"
                f"Margen con descuento: {'' if m is None else f'{m:.1f} %'}\n"
                f"Vigencia: {fila.get('vigencia', '')} · {num(fila.get('cantidad')):,.2f} {fila.get('unidad_medida', '')}")

    def _etiqueta(self, fila: dict) -> str:
        return (f"descuento {fila.get('id_descuento', '')} "
                f"({fila.get('producto', '')} en {fila.get('locacion', '')})")

    def _actualizar_botones(self) -> None:
        puede = self._es_rol("planner")
        sug = bool(self._filas_con_estado("SUGERIDO"))
        self.btn_aprobar.setEnabled(puede and sug)
        self.btn_rechazar.setEnabled(puede and sug)
        self.btn_generar.setEnabled(puede)

    # ---- acciones
    def _post(self, accion: str, cuerpo: dict | None = None, root: str | None = None):
        def hacer(fila: dict) -> Any:
            return self.ctx.api.call("planning", "POST",
                                     f"/api/v1/planning/discounts/{fila['id_descuento']}/{accion}",
                                     body=cuerpo, body_root=root)
        return hacer

    def _aprobar(self) -> None:
        filas = self._filas_con_estado("SUGERIDO")
        if not filas:
            self.ctx.notify("Selecciona descuentos SUGERIDO para aprobar")
            return
        if len(filas) > 1 and not self._confirmar(f"¿Aprobar {len(filas)} descuentos?"):
            return
        self._lote(filas, "APROBAR_DESCUENTO", "aprobado", self._post("approve"), self.btn_aprobar)

    def _rechazar(self) -> None:
        filas = self._filas_con_estado("SUGERIDO")
        if not filas:
            self.ctx.notify("Selecciona descuentos SUGERIDO para rechazar")
            return
        motivo = self._pedir_texto("Rechazar descuentos", f"Motivo del rechazo ({len(filas)} descuento(s)):")
        if not motivo:
            return
        self._lote(filas, "RECHAZAR_DESCUENTO", f"rechazado (motivo: {motivo})",
                   self._post("reject", {"motivo": motivo}, "rechazo_request"), self.btn_rechazar)

    def _generar(self) -> None:
        dias = self.spin_dias.value()

        def hacer():
            return self.ctx.api.call("planning", "POST", "/api/v1/planning/discounts/generate",
                                     body={"dias_hasta": dias}, body_root="discounts_generate_request")

        def detalle(res: Any) -> str:
            r = res if isinstance(res, dict) else {}
            return f"Descuentos generados: {int(num(r.get('total')))} sugerencia(s) (caducidad en {dias} días)"

        self._disparar(hacer, "GENERAR_DESCUENTOS", detalle, self.btn_generar)
