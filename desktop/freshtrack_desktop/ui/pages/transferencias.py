"""Transferencias entre tiendas: detectar oportunidades, aprobar, rechazar y ejecutar."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton

from ...core.xml_codec import as_list, num
from ..widgets import ask_text, button, confirm  # noqa: F401 - la base los resuelve por módulo
from .reabastecimiento import NOTA_MOTIVO, DecisionPage, _fijar_ancho, _spin  # noqa: F401

ESTADOS = ("SUGERIDA", "APROBADA", "RECHAZADA", "EJECUTADA", "CANCELADA")
_VALIDACIONES = {
    "destino_necesita": "El destino lo necesita",
    "origen_suficiente": "El origen tiene suficiente",
    "llega_antes_de_vencer": "Llega antes de vencer",
    "destino_puede_consumirlo": "El destino puede consumirlo",
}


class TransferenciasPage(DecisionPage):
    title = "Transferencias"
    subtitle = "Traslados sugeridos entre tiendas para evitar merma: detecta, aprueba y ejecuta"
    icon = "SP_DirLinkIcon"
    roles = ("planner",)
    id_field = "id_transferencia"
    entidad = "transferencia"

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
        fila.addWidget(QLabel("Horizonte"))
        self.spin_horizonte = _spin(7, 1, 90, " días")
        fila.addWidget(self.spin_horizonte)
        self.btn_detectar = button("Detectar transferencias", self._detectar, variant="primary",
                                   icon="SP_FileDialogContentsView")
        fila.addWidget(self.btn_detectar)
        fila.addStretch(1)
        self.btn_aprobar = button("Aprobar", self._aprobar, variant="primary", icon="SP_DialogApplyButton")
        self.btn_rechazar = button("Rechazar", self._rechazar, variant="danger", icon="SP_DialogCancelButton")
        self.btn_ejecutar = button("Ejecutar", self._ejecutar, icon="SP_MediaPlay",
                                   tooltip="Mueve el inventario entre tiendas (solo transferencias aprobadas)")
        for b in (self.btn_aprobar, self.btn_rechazar, self.btn_ejecutar):
            fila.addWidget(b)
        _fijar_ancho(*(fila.itemAt(i).widget() for i in range(fila.count())
                       if isinstance(fila.itemAt(i).widget(), QPushButton)))
        self.body.addLayout(fila)

        self.table.set_empty_text("Sin propuestas. Pulsa «Detectar transferencias» para calcularlas.")
        self.table.set_columns([
            ("producto", "Producto"), ("origen", "Origen"), ("destino", "Destino"), ("cantidad", "Cantidad", "num"),
            ("unidad_medida", "Unidad"), ("estado", "Estado", "status"), ("dias_para_vencer", "Días a vencer", "int"),
            ("fecha_caducidad", "Caducidad"), ("codigo_lote_prov", "Lote"), ("fecha_creacion", "Creada"),
            ("motivo", "Motivo"),
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
        return self.ctx.api.call("planning", "GET", "/api/v1/planning/transfers", params=params)

    def _filas_de(self, datos: Any) -> list[dict]:
        d = datos if isinstance(datos, dict) else {}
        return [f for f in as_list(d.get("transferencias")) if isinstance(f, dict)]

    def _despues_de_mostrar(self, datos: Any, filas: list[dict]) -> None:
        r = datos.get("resumen") if isinstance(datos, dict) and isinstance(datos.get("resumen"), dict) else {}
        self.status_label.setText(
            f"{len(filas)} transferencias · sugeridas {int(num(r.get('sugeridas')))}, aprobadas "
            f"{int(num(r.get('aprobadas')))}, ejecutadas {int(num(r.get('ejecutadas')))}, rechazadas "
            f"{int(num(r.get('rechazadas')))} · unidades movidas {num(r.get('unidades_movidas')):,.2f}")

    def _detalle(self, fila: dict) -> str:
        lineas = [str(fila.get("motivo") or ""), "",
                  f"Exceso en origen: {num(fila.get('exceso_origen')):,.2f} · "
                  f"Faltante en destino: {num(fila.get('faltante_destino')):,.2f}", "Validaciones:"]
        val = fila.get("validaciones") if isinstance(fila.get("validaciones"), dict) else {}
        for clave, nombre in _VALIDACIONES.items():
            v = val.get(clave) if isinstance(val.get(clave), dict) else {}
            if v:
                marca = "OK" if str(v.get("pasa")).lower() == "true" else "NO"
                lineas.append(f"  [{marca}] {nombre}: {v.get('detalle', '')}")
        return "\n".join(lineas)

    def _etiqueta(self, fila: dict) -> str:
        return (f"transferencia {fila.get('id_transferencia', '')} "
                f"({fila.get('producto', '')}: {fila.get('origen', '')} → {fila.get('destino', '')})")

    def _actualizar_botones(self) -> None:
        puede = self._es_rol("planner")
        sug = bool(self._filas_con_estado("SUGERIDA"))
        self.btn_aprobar.setEnabled(puede and sug)
        self.btn_rechazar.setEnabled(puede and sug)
        self.btn_ejecutar.setEnabled(puede and bool(self._filas_con_estado("APROBADA")))
        self.btn_detectar.setEnabled(puede)

    # ---- acciones
    def _post(self, accion: str, cuerpo: dict | None = None, root: str | None = None):
        def hacer(fila: dict) -> Any:
            return self.ctx.api.call("planning", "POST",
                                     f"/api/v1/planning/transfers/{fila['id_transferencia']}/{accion}",
                                     body=cuerpo, body_root=root)
        return hacer

    def _aprobar(self) -> None:
        filas = self._filas_con_estado("SUGERIDA")
        if not filas:
            self.ctx.notify("Selecciona transferencias SUGERIDA para aprobar")
            return
        if len(filas) > 1 and not self._confirmar(f"¿Aprobar {len(filas)} transferencias?"):
            return
        self._lote(filas, "APROBAR_TRANSFERENCIA", "aprobada", self._post("approve"), self.btn_aprobar)

    def _rechazar(self) -> None:
        filas = self._filas_con_estado("SUGERIDA")
        if not filas:
            self.ctx.notify("Selecciona transferencias SUGERIDA para rechazar")
            return
        motivo = self._pedir_texto("Rechazar transferencias",
                                   f"Motivo del rechazo ({len(filas)} transferencia(s)):{NOTA_MOTIVO}")
        if not motivo:
            return
        self._lote(filas, "RECHAZAR_TRANSFERENCIA", f"rechazada (motivo: {motivo})",
                   self._post("reject", {"motivo": motivo}, "rechazo_request"), self.btn_rechazar)

    def _ejecutar(self) -> None:
        filas = self._filas_con_estado("APROBADA")
        if not filas:
            self.ctx.notify("Selecciona transferencias APROBADA para ejecutar")
            return
        if not self._confirmar(f"Se moverá inventario entre tiendas ({len(filas)} transferencia(s)). "
                               "La acción no se puede deshacer. ¿Ejecutar?"):
            return
        self._lote(filas, "EJECUTAR_TRANSFERENCIA", "ejecutada", self._post("execute"), self.btn_ejecutar)

    def _detectar(self) -> None:
        horizonte = self.spin_horizonte.value()

        def hacer():
            return self.ctx.api.call("planning", "POST", "/api/v1/planning/transfers/detect",
                                     body={"horizonte": horizonte}, body_root="transfers_detect_request")

        def detalle(res: Any) -> str:
            r = res if isinstance(res, dict) else {}
            return (f"Transferencias detectadas: {int(num(r.get('total')))} nueva(s), "
                    f"{int(num(r.get('descartadas')))} descartada(s)")

        self._disparar(hacer, "DETECTAR_TRANSFERENCIAS", detalle, self.btn_detectar)
