"""Importar ventas: CSV → vista previa validada → POST /commercial/sales/import (XML, bloques de 500)."""

from __future__ import annotations

import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox

from ...core.xml_codec import as_list
from .. import theme
from ..widgets import ROW_ROLE, DataTable, KpiCard, confirm, secondary_label
from .base import BasePage

COLUMNAS = ("folio_externo", "id_locacion", "id_sku", "cantidad")
CANALES = ("TIENDA", "ONLINE", "MAYOREO")
BLOQUE = 500          # máximo de tickets por petición (XSD)
MAX_LINEAS = 100      # máximo de líneas por ticket (XSD)
MAX_FOLIO = 60
_RE_ENTERO = re.compile(r"^\d+$")
PLANTILLA = (
    "folio_externo,id_locacion,id_sku,cantidad,canal\n"
    "POS-0001,3,1,2,TIENDA\n"
    "POS-0001,3,5,1.5,TIENDA\n"
    "POS-0002,4,9,3,ONLINE\n"
)


def _entero_positivo(texto: str) -> int | None:
    texto = (texto or "").strip()
    if _RE_ENTERO.match(texto) and int(texto) > 0:
        return int(texto)
    return None


def _cantidad(texto: str) -> Decimal | None:
    try:
        d = Decimal((texto or "").strip())
    except InvalidOperation:
        return None
    return d if d.is_finite() and d > 0 else None


def parsear_csv(path: str | Path) -> tuple[list[dict], list[dict]]:
    """Lee el CSV y valida cada fila.

    Devuelve (filas de la vista previa con `estado` OK/ERROR y `mensaje`, tickets válidos).
    Un ticket = (id_locacion, folio_externo); las filas con error no entran a los tickets.
    Lanza ValueError si faltan columnas obligatorias.
    """
    with open(path, encoding="utf-8-sig", newline="") as fh:
        lector = csv.DictReader(fh)
        encabezados = [(h or "").strip().lower() for h in (lector.fieldnames or [])]
        faltan = [c for c in COLUMNAS if c not in encabezados]
        if faltan:
            raise ValueError("Faltan columnas obligatorias: " + ", ".join(faltan)
                             + ". Se esperan: folio_externo, id_locacion, id_sku, cantidad[, canal].")
        lector.fieldnames = encabezados
        registros = list(lector)

    filas: list[dict] = []
    tickets: dict[tuple[int, str], dict] = {}
    for n, reg in enumerate(registros, start=2):  # la fila 1 es el encabezado
        folio = (reg.get("folio_externo") or "").strip()
        loc_txt, sku_txt = (reg.get("id_locacion") or "").strip(), (reg.get("id_sku") or "").strip()
        cant_txt, canal = (reg.get("cantidad") or "").strip(), (reg.get("canal") or "").strip().upper()
        loc, sku, cant = _entero_positivo(loc_txt), _entero_positivo(sku_txt), _cantidad(cant_txt)
        errores = []
        if not folio:
            errores.append("Falta el folio externo")
        elif len(folio) > MAX_FOLIO:
            errores.append(f"El folio excede {MAX_FOLIO} caracteres")
        if loc is None:
            errores.append("id_locacion debe ser un entero positivo")
        if sku is None:
            errores.append("id_sku debe ser un entero positivo")
        if cant is None:
            errores.append("cantidad debe ser un número mayor que 0")
        if canal and canal not in CANALES:
            errores.append("canal debe ser " + "/".join(CANALES))
        ticket = None
        if not errores:
            ticket = tickets.get((loc, folio))
            if ticket is not None and canal and ticket["canal"] and canal != ticket["canal"]:
                errores.append(f"El folio ya se usó con otro canal ({ticket['canal']})")
            elif ticket is not None and len(ticket["lineas"]) >= MAX_LINEAS:
                errores.append(f"El ticket excede {MAX_LINEAS} líneas")
        if not errores:
            if ticket is None:
                ticket = tickets[(loc, folio)] = {"folio_externo": folio, "id_locacion": loc, "canal": canal, "lineas": []}
            elif canal and not ticket["canal"]:
                ticket["canal"] = canal
            ticket["lineas"].append({"id_sku": sku, "cantidad": format(cant, "f")})
        filas.append({"fila": n, "folio_externo": folio, "id_locacion": loc_txt, "id_sku": sku_txt,
                      "cantidad": cant_txt, "canal": canal, "estado": "ERROR" if errores else "OK",
                      "mensaje": "; ".join(errores)})
    return filas, list(tickets.values())


def construir_xml(id_locacion: int, tickets: list[dict]) -> bytes:
    """`sales_import_request` (id_locacion + tickets/ticket/lineas/linea), sin canal si va vacío."""
    raiz = etree.Element("sales_import_request")
    etree.SubElement(raiz, "id_locacion").text = str(id_locacion)
    nodo_tickets = etree.SubElement(raiz, "tickets")
    for t in tickets:
        nodo = etree.SubElement(nodo_tickets, "ticket")
        etree.SubElement(nodo, "folio_externo").text = str(t["folio_externo"])
        if t.get("canal"):
            etree.SubElement(nodo, "canal").text = t["canal"]
        lineas = etree.SubElement(nodo, "lineas")
        for l in t["lineas"]:
            linea = etree.SubElement(lineas, "linea")
            etree.SubElement(linea, "id_sku").text = str(l["id_sku"])
            etree.SubElement(linea, "cantidad").text = str(l["cantidad"])
    return etree.tostring(raiz, encoding="UTF-8", xml_declaration=True)


def bloques(tickets: list[dict]) -> list[tuple[int, list[dict]]]:
    """Agrupa por tienda y parte en bloques de hasta 500 tickets: [(id_locacion, tickets)]."""
    por_tienda: dict[int, list[dict]] = {}
    for t in tickets:
        por_tienda.setdefault(t["id_locacion"], []).append(t)
    salida = []
    for loc, lista in sorted(por_tienda.items()):
        for i in range(0, len(lista), BLOQUE):
            salida.append((loc, lista[i:i + BLOQUE]))
    return salida


class ImportarVentasPage(BasePage):
    title = "Importar ventas"
    subtitle = "Carga un CSV de tickets (folio_externo, id_locacion, id_sku, cantidad[, canal]), revísalo e impórtalo"
    icon = "SP_DialogOpenButton"
    roles = ("buyer", "planner")

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self._tickets: list[dict] = []
        self._archivo = ""
        self.btn_elegir = self.actions.add_button("Elegir CSV…", self.elegir_csv, icon="SP_DialogOpenButton")
        self.btn_plantilla = self.actions.add_button("Plantilla CSV…", self.descargar_plantilla,
                                                     icon="SP_DialogSaveButton")
        self.btn_importar = self.actions.add_button("Importar", self.importar, variant="primary",
                                                    icon="SP_ArrowUp")
        self.btn_importar.setEnabled(False)

        kpis = QHBoxLayout()
        kpis.setSpacing(12)
        self.kpi_filas = KpiCard("Filas leídas")
        self.kpi_tickets = KpiCard("Tickets válidos")
        self.kpi_errores = KpiCard("Filas con error")
        for k in (self.kpi_filas, self.kpi_tickets, self.kpi_errores):
            kpis.addWidget(k)
        kpis.addStretch(1)
        self.body.addLayout(kpis)
        self.archivo_label = secondary_label("Ningún archivo seleccionado. Las filas con error no se envían.")
        self.body.addWidget(self.archivo_label)

        self.table_vista = DataTable(empty_text="Elige un CSV para ver la vista previa.", title="Vista previa de ventas")
        self.table_vista.set_columns([
            ("fila", "Fila", "int"), ("folio_externo", "Folio externo"), ("id_locacion", "Locación"),
            ("id_sku", "SKU"), ("cantidad", "Cantidad"), ("canal", "Canal"),
            ("estado", "Validación", "status"), ("mensaje", "Detalle"),
        ])
        self.table_resultados = DataTable(empty_text="Aún no se importa nada.", title="Resultado de la importación")
        self.table_resultados.set_columns([
            ("folio_externo", "Folio externo"), ("id_locacion", "Locación"), ("estado", "Resultado", "status"),
            ("folio", "Folio de venta"), ("mensaje", "Mensaje"),
        ])
        self.resumen_label = secondary_label("")
        self.body.addWidget(self.table_vista, 3)
        self.body.addWidget(self.resumen_label)
        self.body.addWidget(self.table_resultados, 2)

    # ---- archivo
    def elegir_csv(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir CSV de ventas", "", "CSV (*.csv);;Todos (*)")
        if ruta:
            self.cargar_csv(ruta)

    def cargar_csv(self, ruta) -> None:
        try:
            filas, tickets = parsear_csv(ruta)
        except (OSError, UnicodeDecodeError, csv.Error, ValueError) as exc:
            self._tickets = []
            self.table_vista.set_rows([])
            self.btn_importar.setEnabled(False)
            QMessageBox.warning(self, "Importar ventas", f"No se pudo leer el archivo:\n{exc}")
            return
        self._tickets, self._archivo = tickets, str(ruta)
        self.table_vista.set_rows(filas)
        self._pintar_errores()
        errores = sum(f["estado"] == "ERROR" for f in filas)
        self.kpi_filas.set_value(str(len(filas)))
        self.kpi_tickets.set_value(str(len(tickets)), tone="success" if tickets else None)
        self.kpi_errores.set_value(str(errores), tone="danger" if errores else None)
        self.archivo_label.setText(f"{Path(ruta).name}: {len(filas)} filas, {len(tickets)} tickets válidos, "
                                   f"{errores} filas con error (no se enviarán).")
        self.btn_importar.setEnabled(bool(tickets))

    def _pintar_errores(self) -> None:
        """Texto en rojo para las filas con error (además del estado y el detalle)."""
        modelo, rojo = self.table_vista.model, theme.color("danger")
        filas = self.table_vista.rows()
        for r in range(modelo.rowCount()):
            if filas[modelo.item(r, 0).data(ROW_ROLE)]["estado"] == "ERROR":
                for c in range(modelo.columnCount()):
                    modelo.item(r, c).setForeground(rojo)

    def descargar_plantilla(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar plantilla CSV", "plantilla_ventas.csv", "CSV (*.csv)")
        if not ruta:
            return
        try:
            Path(ruta).write_text(PLANTILLA, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Plantilla CSV", f"No se pudo guardar el archivo:\n{exc}")
            return
        QMessageBox.information(self, "Plantilla CSV", f"Plantilla guardada en:\n{ruta}")

    # ---- importación
    def importar(self) -> None:
        if not self._tickets:
            return
        lotes = bloques(self._tickets)
        if not confirm(self, f"Se importarán {len(self._tickets)} tickets en {len(lotes)} petición(es). "
                             "Los folios ya importados se marcan como duplicados. ¿Continuar?", "Importar ventas"):
            return
        self.ctx.run(self._enviar, lotes, on_ok=self._mostrar, busy=self.btn_importar)

    def _enviar(self, lotes: list[tuple[int, list[dict]]]) -> list[dict]:
        """Un POST por bloque (hilo de trabajo). Un bloque que falla marca sus tickets como ERROR."""
        resultados: list[dict] = []
        for loc, tickets in lotes:
            try:
                resp = self.ctx.api.call(
                    "commercial", "POST", "/api/v1/commercial/sales/import",
                    body=construir_xml(loc, tickets), body_xsd="sales_import_request",
                    expect_root="sales_import_result")
            except Exception as exc:  # noqa: BLE001 - el resto de bloques sigue
                resultados += [{"folio_externo": t["folio_externo"], "id_locacion": loc, "estado": "ERROR",
                                "folio": "", "mensaje": str(exc) or type(exc).__name__} for t in tickets]
                continue
            items = as_list((resp or {}).get("resultados")) if isinstance(resp, dict) else []
            for it in items:
                if isinstance(it, dict):
                    resultados.append({"folio_externo": it.get("folio_externo", ""), "id_locacion": loc,
                                       "estado": str(it.get("estado", "")).upper(), "folio": it.get("folio", ""),
                                       "mensaje": it.get("mensaje", "")})
        return resultados

    def _mostrar(self, resultados: list[dict]) -> None:
        self.table_resultados.set_rows(resultados)
        cuenta = {e: sum(r["estado"] == e for r in resultados) for e in ("IMPORTADO", "DUPLICADO", "ERROR")}
        texto = (f"Importados: {cuenta['IMPORTADO']} · Duplicados: {cuenta['DUPLICADO']} · "
                 f"Errores: {cuenta['ERROR']}")
        self.resumen_label.setText(texto)
        self.ctx.log.record("IMPORTAR_VENTAS", f"{Path(self._archivo).name}: {texto}", ok=cuenta["ERROR"] == 0)
        self.ctx.notify(texto)
