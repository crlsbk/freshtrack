"""
Reabastecimiento: órdenes sugeridas por el motor de planeación (aprobar, rechazar, generar, ciclo).

Contiene también `DecisionPage`, la base privada que comparten Transferencias y Descuentos:
tabla con selección múltiple, panel de detalle, decisiones en lote y registro en la bitácora.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QSpinBox, QWidget,
)

from ...core.errors import ApiError
from ...core.xml_codec import as_list, num
from ..widgets import DataTable, ask_text, button, confirm, secondary_label
from .base import BasePage

POR_PAGINA = 100  # máximo que acepta el servicio
ESTADOS_ORDEN = ("PENDIENTE", "APROBADA", "RECHAZADA", "EJECUTADA", "CANCELADA")
# El backend ignora el motivo: solo queda en la bitácora local y, al sincronizar, en svc-audit.
NOTA_MOTIVO = "\nEl motivo queda en la bitácora de actividad; el servidor no lo guarda."


class DecisionPage(BasePage):
    """Base de las páginas de decisión humana (lista + acciones sobre filas seleccionadas)."""

    id_field = ""          # clave del identificador en cada fila
    estado_field = "estado"
    entidad = ""           # texto para mensajes: "orden", "transferencia", "descuento"
    roles_accion: tuple[str, ...] = ("planner",)

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self._gen = 0  # generación de la última lectura pedida; respuestas viejas se ignoran
        self.table = DataTable(empty_text=f"Sin {self.entidad}s para mostrar", title=self.title)
        self.table.selection_changed.connect(self._seleccion_cambio)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(115)
        self.detail.setPlaceholderText("Selecciona una fila para ver el detalle.")
        self.status_label = secondary_label("")

    # ---- utilidades compartidas
    def _modulo(self):
        return sys.modules[type(self).__module__]

    def _confirmar(self, texto: str) -> bool:
        return self._modulo().confirm(self, texto)

    def _pedir_texto(self, titulo: str, etiqueta: str) -> str | None:
        return self._modulo().ask_text(self, titulo, etiqueta)

    def _es_rol(self, *roles: str) -> bool:
        sesion = self.ctx.api.session
        return sesion is not None and sesion.can(*roles)

    def _filas_con_estado(self, *estados: str) -> list[dict]:
        sel = self.table.selected_rows()
        return [r for r in sel if str(r.get(self.estado_field, "")).upper() in estados]

    def _pie(self) -> None:
        """Agrega detalle + etiqueta de estado debajo de la tabla (llamar al armar la página)."""
        self.body.addWidget(self.table, 1)
        self.body.addWidget(self.detail)
        self.body.addWidget(self.status_label)

    def _herramientas_tabla(self) -> None:
        self.btn_csv = self.actions.add_button("Exportar CSV", self.table.export_csv_dialog,
                                               icon="SP_DialogSaveButton")
        self.btn_imprimir = self.actions.add_button(
            "Imprimir", lambda: self.table.print_table(self.title, self), icon="SP_FileDialogDetailedView")

    def _seleccion_cambio(self) -> None:
        fila = self.table.selected_row()
        self.detail.setPlainText(self._detalle(fila) if fila else "")
        self._actualizar_botones()

    def _detalle(self, fila: dict) -> str:  # se sobrescribe
        return ""

    def _actualizar_botones(self) -> None:  # se sobrescribe
        pass

    def _etiqueta(self, fila: dict) -> str:
        return f"{self.entidad} {fila.get(self.id_field, '')}"

    # ---- lectura
    def _consulta(self) -> Any:  # hilo de trabajo; se sobrescribe
        raise NotImplementedError

    def _filas_de(self, datos: Any) -> list[dict]:  # se sobrescribe
        raise NotImplementedError

    def refresh(self) -> None:
        self._gen += 1
        gen = self._gen
        self.ctx.run(self._consulta, on_ok=lambda datos: self._mostrar(datos, gen),
                     on_error=lambda exc: self._fallo_lectura(exc, gen),
                     busy=getattr(self, "btn_actualizar", None))

    def _mostrar(self, datos: Any, gen: int | None = None) -> None:
        if gen is not None and gen != self._gen:
            return  # llegó tarde: ya se pidió una lectura más nueva
        filas = self._filas_de(datos)
        self.table.set_rows(filas)
        self.detail.clear()
        self._despues_de_mostrar(datos, filas)
        self._actualizar_botones()

    def _despues_de_mostrar(self, datos: Any, filas: list[dict]) -> None:
        pass

    def _fallo_lectura(self, exc: BaseException, gen: int | None = None) -> None:
        if gen is not None and gen != self._gen:
            return
        self.ctx.show_error(exc, self)

    # ---- decisiones en lote
    def _lote(self, filas: list[dict], accion_log: str, verbo: str,
              hacer: Callable[[dict], Any], busy: QWidget | None = None) -> None:
        """Ejecuta `hacer(fila)` por cada fila en el pool; al final resume éxitos y errores."""
        if not filas:
            return
        self.ctx.run(self._correr_lote, filas, hacer,
                     on_ok=lambda res: self._fin_lote(res, accion_log, verbo), busy=busy)

    @staticmethod
    def _correr_lote(filas: list[dict], hacer: Callable[[dict], Any]) -> dict:
        oks, errores = [], []
        for i, fila in enumerate(filas):
            try:
                oks.append((fila, hacer(fila)))
            except Exception as exc:  # noqa: BLE001 - cada fila falla por separado
                errores.append((fila, exc))
                if isinstance(exc, ApiError) and exc.status == 401:
                    break  # sesión vencida: no insistir con el resto
        return {"oks": oks, "errores": errores}

    def _fin_lote(self, res: dict, accion_log: str, verbo: str) -> None:
        oks, errores = res["oks"], res["errores"]
        for fila, _ in oks:
            self.ctx.log.record(accion_log, f"{verbo}: {self._etiqueta(fila)}")
        for fila, exc in errores:
            self.ctx.log.record(accion_log, f"{self._etiqueta(fila)}: {exc}", ok=False)
        if errores and not oks and len(errores) == 1:
            self.ctx.show_error(errores[0][1], self)
        elif errores:
            self._resumen(verbo, len(oks), errores)
        else:
            self.ctx.notify(f"{verbo.capitalize()}: {len(oks)} {self.entidad}(s) correcta(s)")
        self.refresh()

    def _resumen(self, verbo: str, n_ok: int, errores: list[tuple[dict, BaseException]]) -> QMessageBox:
        from ..context import error_message

        dlg = QMessageBox(self)
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setWindowTitle("Resultado de la operación")
        dlg.setText(f"{verbo.capitalize()}: {n_ok} correcta(s) y {len(errores)} con error.")
        dlg.setDetailedText("\n".join(f"{self._etiqueta(f)}: {error_message(e)}" for f, e in errores))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.open()
        return dlg

    # ---- acciones de un solo disparo (generar / detectar / ciclo)
    def _disparar(self, hacer: Callable[[], Any], accion_log: str, detalle: Callable[[Any], str],
                  busy: QWidget | None, despues: Callable[[Any], None] | None = None) -> None:
        def ok(res: Any) -> None:
            texto = detalle(res)
            self.ctx.log.record(accion_log, texto)
            self.ctx.notify(texto)
            if despues is not None:
                despues(res)
            else:
                self.refresh()

        def fallo(exc: BaseException) -> None:
            self.ctx.log.record(accion_log, str(exc), ok=False)
            self.ctx.show_error(exc, self)

        self.ctx.run(hacer, on_ok=ok, on_error=fallo, busy=busy)


def _spin(valor: int, minimo: int, maximo: int, sufijo: str) -> QSpinBox:
    s = QSpinBox()
    s.setRange(minimo, maximo)
    s.setValue(valor)
    s.setSuffix(sufijo)
    return s


def _fijar_ancho(*botones: QWidget) -> None:
    """Ancho mínimo = el que pide el texto, para que nunca se trunque."""
    for b in botones:
        b.setMinimumWidth(b.sizeHint().width())


def _todas(combo: QComboBox, texto: str) -> None:
    combo.clear()
    combo.addItem(texto, "")


class ReabastecimientoPage(DecisionPage):
    title = "Reabastecimiento"
    subtitle = "Órdenes sugeridas por el motor de planeación: revisa, aprueba o rechaza"
    icon = "SP_BrowserReload"
    roles = ("planner", "buyer")
    id_field = "id_orden"
    entidad = "orden"

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self._tiendas_cargadas = False
        self._proveedores: dict[str, str] = {}  # id_proveedor → razón social (catálogo, una vez)
        self.btn_actualizar = self.actions.add_button("Actualizar", self.refresh, icon="SP_BrowserReload")
        self._herramientas_tabla()

        filtros = QHBoxLayout()
        filtros.setSpacing(8)
        filtros.addWidget(QLabel("Estado"))
        self.cmb_estado = QComboBox()
        self.cmb_estado.addItem("Todos", "")
        for e in ESTADOS_ORDEN:
            self.cmb_estado.addItem(e.capitalize(), e)
        self.cmb_estado.setCurrentIndex(self.cmb_estado.findData("PENDIENTE"))
        filtros.addWidget(self.cmb_estado)
        filtros.addWidget(QLabel("Tienda"))
        self.cmb_tienda = QComboBox()
        _todas(self.cmb_tienda, "Todas")
        filtros.addWidget(self.cmb_tienda)
        self.cmb_estado.currentIndexChanged.connect(lambda _i: self.refresh())
        self.cmb_tienda.currentIndexChanged.connect(lambda _i: self.refresh())
        filtros.addStretch(1)
        self.btn_aprobar = button("Aprobar", self._aprobar, variant="primary", icon="SP_DialogApplyButton")
        self.btn_rechazar = button("Rechazar", self._rechazar, variant="danger", icon="SP_DialogCancelButton")
        self.btn_contexto = button("Contexto del SKU", self._contexto, icon="SP_FileDialogInfoView")
        for b in (self.btn_aprobar, self.btn_rechazar, self.btn_contexto):
            filtros.addWidget(b)
        self.body.addLayout(filtros)

        gen = QHBoxLayout()
        gen.setSpacing(8)
        gen.addWidget(QLabel("Horizonte"))
        self.spin_horizonte = _spin(7, 1, 90, " días")
        gen.addWidget(self.spin_horizonte)
        self.btn_generar = button("Generar órdenes", self._generar, variant="primary", icon="SP_FileDialogNewFolder")
        gen.addWidget(self.btn_generar)
        self.btn_ciclo = button("Ejecutar ciclo de planeación", self._ciclo, icon="SP_MediaPlay",
                                tooltip="Pronóstico por tienda, triaje y reabastecimiento neto en un solo paso. "
                                        "Requiere rol planificador (el servidor rechaza a otros roles con 403).")
        gen.addWidget(self.btn_ciclo)
        gen.addStretch(1)
        _fijar_ancho(self.btn_aprobar, self.btn_rechazar, self.btn_contexto, self.btn_generar, self.btn_ciclo)
        self.body.addLayout(gen)

        self.table.set_empty_text("Sin órdenes. Pulsa «Generar órdenes» o «Ejecutar ciclo de planeación».")
        # Sin identificadores internos: el proveedor por nombre y el id de la orden en el detalle.
        self.table.set_columns([
            ("producto", "Producto"), ("locacion", "Tienda"), ("proveedor", "Proveedor"),
            ("cantidad_sugerida", "Sugerida", "num"), ("cantidad_aprobada", "Aprobada", "num"),
            ("prioridad", "Prioridad"), ("estado", "Estado", "status"),
            ("fecha_creacion", "Creada"), ("fecha_decision", "Decisión"),
        ])
        self._pie()
        self._actualizar_botones()

    # ---- lectura
    def on_show(self) -> None:
        self._actualizar_botones()
        super().on_show()

    def _consulta(self) -> dict:
        params: dict[str, Any] = {"por_pagina": POR_PAGINA}
        estado = self.cmb_estado.currentData()
        if estado:
            params["estado"] = estado
        tienda = self.cmb_tienda.currentData()
        if tienda:
            params["id_locacion"] = tienda
        datos = self.ctx.api.call("planning", "GET", "/api/v1/planning/replenishment/orders", params=params)
        tiendas = None
        if not self._tiendas_cargadas:
            try:
                tiendas = self.ctx.api.call("catalog", "GET", "/api/v1/catalog/locations", params={"tipo": "TIENDA"})
            except Exception:  # noqa: BLE001 - el filtro de tienda es opcional
                tiendas = None
        proveedores = None
        if not self._proveedores:
            try:
                proveedores = self.ctx.api.call("catalog", "GET", "/api/v1/catalog/suppliers")
            except Exception:  # noqa: BLE001 - sin catálogo se muestra «Proveedor <id>»
                proveedores = None
        return {"ordenes": datos, "tiendas": tiendas, "proveedores": proveedores}

    def _filas_de(self, datos: dict) -> list[dict]:
        ordenes = datos["ordenes"] if isinstance(datos["ordenes"], dict) else {}
        provs = datos.get("proveedores")
        if isinstance(provs, dict):
            self._proveedores = {str(p.get("id_proveedor", "")): str(p.get("razon_social", ""))
                                 for p in as_list(provs.get("proveedores"))
                                 if isinstance(p, dict) and p.get("razon_social")}
        filas = []
        for f in as_list(ordenes.get("ordenes")):
            if not isinstance(f, dict):
                continue
            fila = dict(f)
            idp = str(fila.get("id_proveedor") or "")
            fila["proveedor"] = fila.get("proveedor") or self._proveedores.get(idp) or (f"Proveedor {idp}" if idp else "")
            filas.append(fila)
        return filas

    def _despues_de_mostrar(self, datos: dict, filas: list[dict]) -> None:
        ordenes = datos["ordenes"] if isinstance(datos["ordenes"], dict) else {}
        pag = ordenes.get("paginacion") if isinstance(ordenes.get("paginacion"), dict) else {}
        total = int(num(pag.get("total"), len(filas)))
        self.status_label.setText(f"Mostrando {len(filas)} de {total} órdenes")
        tiendas = datos.get("tiendas")
        if isinstance(tiendas, dict) and not self._tiendas_cargadas:
            self._tiendas_cargadas = True
            actual = self.cmb_tienda.currentData()
            self.cmb_tienda.blockSignals(True)
            _todas(self.cmb_tienda, "Todas")
            for loc in as_list(tiendas.get("locaciones")):
                if isinstance(loc, dict) and str(loc.get("tipo_locacion", "")).upper() == "TIENDA":
                    self.cmb_tienda.addItem(str(loc.get("nombre", "")), str(loc.get("id_locacion", "")))
            i = self.cmb_tienda.findData(actual)
            self.cmb_tienda.setCurrentIndex(max(i, 0))
            self.cmb_tienda.blockSignals(False)

    # ---- botones
    def _actualizar_botones(self) -> None:
        pendientes = bool(self._filas_con_estado("PENDIENTE"))
        puede = self._es_rol("planner", "buyer")
        self.btn_aprobar.setEnabled(puede and pendientes)
        self.btn_rechazar.setEnabled(puede and pendientes)
        self.btn_generar.setEnabled(puede)
        # Habilitado también para buyer: el servidor decide (403) y la app muestra el aviso.
        self.btn_ciclo.setEnabled(puede)
        self.btn_contexto.setEnabled(self.table.selected_row() is not None)

    def _detalle(self, fila: dict) -> str:
        cabecera = f"Orden {fila.get('id_orden', '')} · {fila.get('proveedor') or 'sin proveedor'}"
        return cabecera + "\n\n" + str(fila.get("explicacion") or "Sin explicación del motor.")

    # ---- acciones
    def _aprobar(self) -> None:
        filas = self._filas_con_estado("PENDIENTE")
        if not filas:
            self.ctx.notify("Selecciona órdenes PENDIENTE para aprobar")
            return
        if len(filas) > 1 and not self._confirmar(f"¿Aprobar {len(filas)} órdenes?"):
            return
        self._lote(filas, "APROBAR_ORDEN", "aprobada", self._post_decision("approve"), self.btn_aprobar)

    def _rechazar(self) -> None:
        filas = self._filas_con_estado("PENDIENTE")
        if not filas:
            self.ctx.notify("Selecciona órdenes PENDIENTE para rechazar")
            return
        motivo = self._pedir_texto("Rechazar órdenes",
                                   f"Motivo del rechazo ({len(filas)} orden(es)):{NOTA_MOTIVO}")
        if not motivo:
            return
        self._lote(filas, "RECHAZAR_ORDEN", f"rechazada (motivo: {motivo})",
                   self._post_decision("reject", motivo), self.btn_rechazar)

    def _post_decision(self, accion: str, motivo: str | None = None) -> Callable[[dict], Any]:
        def hacer(fila: dict) -> Any:
            cuerpo = {"motivo": motivo} if motivo else None
            return self.ctx.api.call(
                "planning", "POST", f"/api/v1/planning/replenishment/orders/{fila['id_orden']}/{accion}",
                body=cuerpo, body_root="rechazo_request" if cuerpo else None)
        return hacer

    def _generar(self) -> None:
        horizonte = self.spin_horizonte.value()

        def hacer():
            return self.ctx.api.call("planning", "POST", "/api/v1/planning/replenishment/generate",
                                     body={"horizonte": horizonte}, body_root="replenishment_request")

        def detalle(res: Any) -> str:
            n = res.get("total", len(as_list(res.get("ordenes")))) if isinstance(res, dict) else 0
            return f"Reabastecimiento generado: {n} orden(es), horizonte {horizonte} días"

        self._disparar(hacer, "GENERAR_ORDENES", detalle, self.btn_generar)

    def _ciclo(self) -> None:
        if not self._confirmar("Se ejecutará el ciclo completo: pronóstico por tienda, triaje y "
                               "reabastecimiento neto. Puede tardar. ¿Continuar?"):
            return
        horizonte = self.spin_horizonte.value()

        def hacer():
            return self.ctx.api.call("planning", "POST", "/api/v1/planning/cycle/run",
                                     body={"horizonte": horizonte}, body_root="planning_cycle_request")

        def detalle(res: Any) -> str:
            r = res if isinstance(res, dict) else {}
            reab = r.get("reabastecimiento") if isinstance(r.get("reabastecimiento"), dict) else {}
            triaje = r.get("triaje") if isinstance(r.get("triaje"), dict) else {}
            apl = triaje.get("aplicados") if isinstance(triaje.get("aplicados"), dict) else {}
            pron = r.get("pronostico") if isinstance(r.get("pronostico"), dict) else {}
            return (f"Ciclo de planeación: {int(num(pron.get('total_recalibradas')))} tienda(s) recalibrada(s), "
                    f"{int(num(apl.get('traslados_creados')))} traslado(s), "
                    f"{int(num(apl.get('descuentos_creados')))} descuento(s), "
                    f"{int(num(reab.get('total'), len(as_list(reab.get('generadas')))))} orden(es)")

        self._disparar(hacer, "EJECUTAR_CICLO", detalle, self.btn_ciclo, despues=self._tras_ciclo)

    def _tras_ciclo(self, _res: Any) -> None:
        """El ciclo cambia las tres listas: actualiza esta y las hermanas ya creadas."""
        self.refresh()
        ventana = self.window()
        for nombre in ("TransferenciasPage", "DescuentosPage"):
            for pagina in ventana.findChildren(BasePage):
                if type(pagina).__name__ == nombre:
                    pagina.refresh()

    def _contexto(self) -> None:
        fila = self.table.selected_row()
        if not fila:
            return
        sku, loc = fila.get("id_sku"), fila.get("id_locacion")

        def ok(datos: Any) -> None:
            self.detail.setPlainText(self._detalle(fila) + "\n\n" + _texto_contexto(datos))

        self.ctx.run(lambda: self.ctx.api.call("planning", "GET", f"/api/v1/planning/sku/{sku}/full-context",
                                               params={"id_locacion": loc}),
                     on_ok=ok, busy=self.btn_contexto)


def _texto_contexto(datos: Any) -> str:
    d = datos if isinstance(datos, dict) else {}
    p = d.get("producto_postgres") if isinstance(d.get("producto_postgres"), dict) else {}
    m = d.get("contexto_mongo") if isinstance(d.get("contexto_mongo"), dict) else {}
    lineas = [
        "Contexto del SKU",
        f"  Producto: {p.get('nombre', '')} ({p.get('categoria', '')}), GTIN {p.get('codigo_gtin', '')}",
        f"  Precio venta ${num(p.get('precio_venta')):,.2f} · costo ${num(p.get('precio_costo')):,.2f} "
        f"· vida útil {p.get('vida_util_estandar', '')} días",
        f"  Alertas activas en la tienda: {m.get('alertas_activas_count', 0)}",
        f"  Pronóstico reciente: {'disponible' if m.get('pronostico_reciente') else 'sin corrida previa'}",
    ]
    return "\n".join(lineas)
