"""
Generador corporativo de Órdenes de Compra en PDF 1.4 (Python puro).

No depende de librerías nativas externas; produce documentos PDF multipágina válidos
con soporte de caracteres en español (WinAnsiEncoding / cp1252), cabecera FreshTrack,
datos de proveedor/comprador, tabla detallada de lotes enrutados por tienda y totales.
"""

from __future__ import annotations

from datetime import date, datetime


def _ascii_o_winansi(texto: object) -> bytes:
    """Convierte texto a bytes WinAnsi (cp1252) reemplazando caracteres no soportados."""
    s = str(texto or "")
    s = s.replace("→", "->").replace("↔", "<->").replace("—", "-").replace("–", "-")
    raw = s.encode("cp1252", errors="replace")
    # Escapar caracteres especiales de cadenas PDF: \, (, )
    out = bytearray()
    for b in raw:
        if b in (0x5C, 0x28, 0x29):  # '\', '(', ')'
            out.append(0x5C)
        out.append(b)
    return bytes(out)


def _cortar(texto: object, max_chars: int) -> str:
    s = str(texto or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max(1, max_chars - 1)] + "."


def _fmt_num(valor: object, dec: int = 2) -> str:
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        return str(valor or "0")
    if dec and abs(v - round(v)) < 0.005:
        return f"{int(round(v)):,}"
    return f"{v:,.{dec}f}"


def _fmt_moneda(valor: object) -> str:
    try:
        v = float(valor or 0)
    except (TypeError, ValueError):
        v = 0.0
    return f"${v:,.2f}"


def _fmt_fecha(valor: object) -> str:
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    s = str(valor or "")
    return s[:16].replace("T", " ") if s else "-"


class _LienzoPDF:
    """Constructor simple de páginas PDF en tamaño Carta (612 x 792 pt)."""

    ANCHO = 612
    ALTO = 792

    def __init__(self) -> None:
        self.paginas: list[list[bytes]] = []
        self._actual: list[bytes] = []
        self.y = 750.0

    def nueva_pagina(self) -> None:
        if self._actual:
            self.paginas.append(self._actual)
        self._actual = []
        self.y = 750.0

    def cerrar(self) -> list[bytes]:
        if self._actual:
            self.paginas.append(self._actual)
            self._actual = []
        return [b"\n".join(cmds) for cmds in self.paginas]

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        fill_rgb: tuple[float, float, float] | None = None,
        stroke_rgb: tuple[float, float, float] | None = None,
    ) -> None:
        cmds: list[bytes] = []
        if fill_rgb:
            cmds.append(f"{fill_rgb[0]:.3f} {fill_rgb[1]:.3f} {fill_rgb[2]:.3f} rg".encode("ascii"))
        if stroke_rgb:
            cmds.append(f"{stroke_rgb[0]:.3f} {stroke_rgb[1]:.3f} {stroke_rgb[2]:.3f} RG 0.6 w".encode("ascii"))
        op = "B" if (fill_rgb and stroke_rgb) else ("f" if fill_rgb else "S")
        cmds.append(f"{x:.1f} {y:.1f} {w:.1f} {h:.1f} re {op}".encode("ascii"))
        self._actual.extend(cmds)

    def linea(self, x1: float, y1: float, x2: float, y2: float, rgb=(0.82, 0.85, 0.88)) -> None:
        self._actual.append(
            f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} RG 0.6 w {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S".encode("ascii")
        )

    def texto(
        self,
        x: float,
        y: float,
        txt: object,
        *,
        size: float = 9.5,
        bold: bool = False,
        rgb: tuple[float, float, float] = (0.12, 0.16, 0.22),
        align: str = "left",
    ) -> None:
        font = "F2" if bold else "F1"
        s = str(txt or "")
        # Aproximación de ancho para alineación derecha en Helvetica
        if align == "right":
            x = x - len(s) * size * 0.49
        seguro = _ascii_o_winansi(s)
        cmd = (
            b"BT "
            + f"/{font} {size:.1f} Tf {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg {x:.1f} {y:.1f} Td (".encode("ascii")
            + seguro
            + b") Tj ET"
        )
        self._actual.append(cmd)


def _dibujar_encabezado_pagina(pdf: _LienzoPDF, orden: dict, continuacion: bool = False) -> None:
    pdf.nueva_pagina()
    # Banda superior FreshTrack
    pdf.rect(0, 738, pdf.ANCHO, 54, fill_rgb=(0.086, 0.639, 0.290))
    pdf.texto(36, 766, "FRESHTRACK · ABASTECIMIENTO INTELIGENTE", size=13, bold=True, rgb=(1, 1, 1))
    pdf.texto(36, 750, "Orden de Compra de Lotes Enrutados a Tiendas", size=9.5, rgb=(0.90, 0.98, 0.92))
    pdf.texto(576, 766, f"FOLIO: {orden['folio']}", size=11.5, bold=True, rgb=(1, 1, 1), align="right")
    pdf.texto(576, 750, f"Estado: {orden.get('estado', 'EMITIDA')}", size=9, rgb=(0.90, 0.98, 0.92), align="right")

    if continuacion:
        pdf.y = 716
        pdf.texto(36, pdf.y, f"Continuación de Orden de Compra {orden['folio']}", size=9, bold=True)
        pdf.y -= 18
        return

    # Cajas Proveedor y Comprador
    pdf.rect(36, 636, 264, 88, fill_rgb=(0.975, 0.980, 0.985), stroke_rgb=(0.85, 0.88, 0.91))
    pdf.texto(46, 710, "PROVEEDOR", size=8.5, bold=True, rgb=(0.086, 0.50, 0.22))
    pdf.texto(46, 695, _cortar(orden.get("proveedor"), 38), size=10, bold=True)
    pdf.texto(46, 681, f"RFC: {orden.get('rfc') or '-'}  ·  Entrega: {orden.get('lead_time_dias', 0)} d", size=8.5)
    pdf.texto(46, 667, f"Correo: {_cortar(orden.get('contacto_email') or '-', 34)}", size=8.5)
    pdf.texto(46, 653, f"Tel: {_cortar(orden.get('telefono') or '-', 34)}", size=8.5)

    pdf.rect(312, 636, 264, 88, fill_rgb=(0.975, 0.980, 0.985), stroke_rgb=(0.85, 0.88, 0.91))
    pdf.texto(322, 710, "DATOS DE EMISIÓN Y COMPRA", size=8.5, bold=True, rgb=(0.086, 0.50, 0.22))
    pdf.texto(322, 695, f"Emitida por: {_cortar(orden.get('comprador') or '-', 30)}", size=9.5, bold=True)
    pdf.texto(322, 681, f"Correo comprador: {_cortar(orden.get('comprador_email') or '-', 28)}", size=8.5)
    pdf.texto(322, 667, f"Fecha emisión: {_fmt_fecha(orden.get('fecha_creacion'))}", size=8.5)
    pdf.texto(322, 653, f"Entrega estimada: {_fmt_fecha(orden.get('fecha_entrega_estimada'))}", size=8.5)

    pdf.y = 616


def _dibujar_cabecera_tabla_detalle(pdf: _LienzoPDF) -> None:
    pdf.rect(36, pdf.y - 4, 540, 20, fill_rgb=(0.93, 0.95, 0.97), stroke_rgb=(0.82, 0.85, 0.88))
    pdf.texto(42, pdf.y + 2, "Tienda Destino", size=8.2, bold=True)
    pdf.texto(162, pdf.y + 2, "Producto", size=8.2, bold=True)
    pdf.texto(338, pdf.y + 2, "Lotes", size=8.2, bold=True, align="right")
    pdf.texto(398, pdf.y + 2, "MOQ/Lote", size=8.2, bold=True, align="right")
    pdf.texto(456, pdf.y + 2, "Unidades", size=8.2, bold=True, align="right")
    pdf.texto(514, pdf.y + 2, "Costo U.", size=8.2, bold=True, align="right")
    pdf.texto(570, pdf.y + 2, "Subtotal", size=8.2, bold=True, align="right")
    pdf.y -= 20


def generar_pdf_orden_compra(orden: dict) -> bytes:
    """Genera los bytes de un documento PDF 1.4 para la orden de compra indicada."""
    pdf = _LienzoPDF()
    _dibujar_encabezado_pagina(pdf, orden, continuacion=False)

    pdf.texto(36, pdf.y, "Detalle de lotes solicitados por tienda destino", size=10.5, bold=True)
    pdf.y -= 18
    _dibujar_cabecera_tabla_detalle(pdf)

    for idx, lin in enumerate(orden.get("lineas") or []):
        if pdf.y < 110:
            _dibujar_encabezado_pagina(pdf, orden, continuacion=True)
            _dibujar_cabecera_tabla_detalle(pdf)

        if idx % 2 == 1:
            pdf.rect(36, pdf.y - 4, 540, 17, fill_rgb=(0.985, 0.988, 0.992))
        pdf.texto(42, pdf.y, _cortar(lin.get("locacion_destino"), 22), size=8.3)
        pdf.texto(162, pdf.y, _cortar(f"{lin.get('producto')} ({lin.get('unidad_medida', '')})", 30), size=8.3)
        pdf.texto(338, pdf.y, _fmt_num(lin.get("cantidad_lotes"), 0), size=8.3, bold=True, align="right")
        pdf.texto(398, pdf.y, _fmt_num(lin.get("unidades_por_lote"), 2), size=8.3, align="right")
        pdf.texto(456, pdf.y, _fmt_num(lin.get("cantidad_unidades"), 2), size=8.3, align="right")
        pdf.texto(514, pdf.y, _fmt_moneda(lin.get("precio_unitario")), size=8.3, align="right")
        pdf.texto(570, pdf.y, _fmt_moneda(lin.get("subtotal")), size=8.3, bold=True, align="right")
        pdf.linea(36, pdf.y - 4, 576, pdf.y - 4, rgb=(0.90, 0.92, 0.94))
        pdf.y -= 17

    # Resumen por tienda destino
    resumen_tiendas = orden.get("resumen_tiendas") or []
    if resumen_tiendas:
        if pdf.y < 150:
            _dibujar_encabezado_pagina(pdf, orden, continuacion=True)
        pdf.y -= 12
        pdf.texto(36, pdf.y, "Resumen de entrega por tienda destino", size=10, bold=True)
        pdf.y -= 16
        pdf.rect(36, pdf.y - 4, 340, 18, fill_rgb=(0.93, 0.95, 0.97), stroke_rgb=(0.82, 0.85, 0.88))
        pdf.texto(42, pdf.y + 1, "Tienda Destino", size=8.2, bold=True)
        pdf.texto(220, pdf.y + 1, "Lotes", size=8.2, bold=True, align="right")
        pdf.texto(295, pdf.y + 1, "Unidades", size=8.2, bold=True, align="right")
        pdf.texto(370, pdf.y + 1, "Importe", size=8.2, bold=True, align="right")
        pdf.y -= 18
        for rt in resumen_tiendas:
            if pdf.y < 110:
                _dibujar_encabezado_pagina(pdf, orden, continuacion=True)
            pdf.texto(42, pdf.y, _cortar(rt.get("locacion_destino"), 28), size=8.3)
            pdf.texto(220, pdf.y, _fmt_num(rt.get("lotes"), 0), size=8.3, align="right")
            pdf.texto(295, pdf.y, _fmt_num(rt.get("unidades"), 2), size=8.3, align="right")
            pdf.texto(370, pdf.y, _fmt_moneda(rt.get("subtotal")), size=8.3, bold=True, align="right")
            pdf.linea(36, pdf.y - 4, 376, pdf.y - 4, rgb=(0.90, 0.92, 0.94))
            pdf.y -= 16

    # Totales y observaciones
    if pdf.y < 115:
        _dibujar_encabezado_pagina(pdf, orden, continuacion=True)

    y_tot = max(62.0, pdf.y - 52.0)
    if orden.get("observaciones"):
        pdf.rect(36, y_tot, 310, 48, fill_rgb=(0.985, 0.985, 0.990), stroke_rgb=(0.85, 0.88, 0.91))
        pdf.texto(44, y_tot + 34, "Observaciones:", size=8.3, bold=True)
        pdf.texto(44, y_tot + 20, _cortar(orden.get("observaciones"), 55), size=8.2)

    pdf.rect(360, y_tot, 216, 48, fill_rgb=(0.94, 0.98, 0.95), stroke_rgb=(0.086, 0.639, 0.290))
    pdf.texto(370, y_tot + 33, "Total lotes:", size=8.5)
    pdf.texto(566, y_tot + 33, _fmt_num(orden.get("total_lotes"), 0), size=8.5, bold=True, align="right")
    pdf.texto(370, y_tot + 20, "Total unidades:", size=8.5)
    pdf.texto(566, y_tot + 20, _fmt_num(orden.get("total_unidades"), 2), size=8.5, bold=True, align="right")
    pdf.texto(370, y_tot + 6, "TOTAL ORDEN:", size=10, bold=True, rgb=(0.06, 0.45, 0.20))
    pdf.texto(566, y_tot + 6, _fmt_moneda(orden.get("total")), size=10.5, bold=True, rgb=(0.06, 0.45, 0.20), align="right")

    streams = pdf.cerrar()
    total_paginas = len(streams)

    # Añadir pie de página numerado antes de empaquetar
    streams_con_pie: list[bytes] = []
    for idx, st in enumerate(streams, start=1):
        pie = (
            b"\nBT /F1 8.0 Tf 0.450 0.480 0.520 rg 36.0 24.0 Td ("
            + _ascii_o_winansi(f"FreshTrack · Documento generado automáticamente · Folio {orden['folio']} · Página {idx} de {total_paginas}")
            + b") Tj ET"
        )
        streams_con_pie.append(st + pie)

    # Ensamblar objetos PDF 1.4
    # 1: Catalog, 2: Pages, 3: Font F1 (Helvetica), 4: Font F2 (Helvetica-Bold),
    # luego por cada página i: obj_page (5 + 2*i), obj_content (6 + 2*i)
    objetos: list[tuple[int, bytes]] = []
    page_ids = [5 + 2 * i for i in range(total_paginas)]
    kids_str = " ".join(f"{pid} 0 R" for pid in page_ids)

    objetos.append((1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    objetos.append((2, f"<< /Type /Pages /Kids [{kids_str}] /Count {total_paginas} >>".encode("ascii")))
    objetos.append((3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"))
    objetos.append((4, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"))

    for i, stream_bytes in enumerate(streams_con_pie):
        p_id = 5 + 2 * i
        c_id = p_id + 1
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pdf.ANCHO} {pdf.ALTO}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {c_id} 0 R >>"
        ).encode("ascii")
        content_obj = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream"
        )
        objetos.append((p_id, page_obj))
        objetos.append((c_id, content_obj))

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for obj_id, cuerpo in objetos:
        offsets[obj_id] = len(buf)
        buf.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        buf.extend(cuerpo)
        buf.extend(b"\nendobj\n")

    xref_pos = len(buf)
    total_objs = len(objetos) + 1
    buf.extend(f"xref\n0 {total_objs}\n".encode("ascii"))
    buf.extend(b"0000000000 65535 f \n")
    for obj_id, _ in objetos:
        buf.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))
    buf.extend(
        (
            f"trailer\n<< /Size {total_objs} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(buf)
