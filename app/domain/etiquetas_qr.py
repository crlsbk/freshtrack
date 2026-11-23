"""
Generación y verificación criptográfica de códigos QR y Hoja de Empaque PDF para ASN.

Protocolo compacto FT1 (agnóstico de medio QR / NFC / RFID):
    FT1|<codigo_etiqueta>|<folio_oc>|L<id_locacion_destino>|S<id_sku>|<hmac12>
"""

from __future__ import annotations

import hashlib
import hmac
import re

import segno

from app.config import Config
from app.domain.pdf_oc import _LienzoPDF, _cortar, _fmt_fecha, _fmt_num, empaquetar_pdf

_GS1_GTIN = re.compile(r"\(01\)([0-9]{8,14})")
_GS1_LOTE = re.compile(r"\(10\)([^\(]+)")
_GS1_CAD = re.compile(r"\(17\)([0-9]{6})")
_GS1_CANT = re.compile(r"\(30\)([0-9]+(?:\.[0-9]+)?)")
_GS1_OC = re.compile(r"\(400\)([^\(]+)")


def firmar_etiqueta(codigo_etiqueta: str, folio_oc: str | None, id_locacion_destino: int, id_sku: int) -> str:
    """Genera firma HMAC-SHA256 truncada a 12 caracteres hexadecimales."""
    clave = Config.JWT_SECRET_KEY.encode("utf-8")
    oc_norm = (folio_oc or "SIN-OC").strip()
    mensaje = f"{codigo_etiqueta.strip()}|{oc_norm}|{int(id_locacion_destino)}|{int(id_sku)}".encode("utf-8")
    return hmac.new(clave, mensaje, hashlib.sha256).hexdigest()[:12]


def construir_payload_qr(codigo_etiqueta: str, folio_oc: str | None, id_locacion_destino: int, id_sku: int) -> str:
    """Construye el payload compacto FT1 firmado listo para codificar en QR o chip NFC."""
    oc_norm = (folio_oc or "SIN-OC").strip()
    sig = firmar_etiqueta(codigo_etiqueta, oc_norm, id_locacion_destino, id_sku)
    return f"FT1|{codigo_etiqueta.strip()}|{oc_norm}|L{int(id_locacion_destino)}|S{int(id_sku)}|{sig}"


def parsear_y_verificar_qr(texto: str) -> dict:
    """
    Analiza un código escaneado por la app móvil o lector de muelle:
    - FT1|...  -> valida estructura y firma HMAC estricta.
    - (01)...  -> extrae campos estándar GS1-128.
    - otro     -> lo trata como codigo_etiqueta corto (FTL-...) o EPC RFID.
    """
    crudo = str(texto or "").strip()
    if not crudo:
        raise ValueError("El código escaneado está vacío.")

    if crudo.startswith("FT1|"):
        partes = crudo.split("|")
        if len(partes) != 6:
            raise ValueError("Formato de código QR FT1 incompleto o dañado.")
        _, codigo_etiqueta, folio_oc, loc_str, sku_str, sig_recibida = partes
        if not loc_str.startswith("L") or not sku_str.startswith("S"):
            raise ValueError("Identificadores de tienda o producto inválidos en el código QR.")
        try:
            id_loc = int(loc_str[1:])
            id_sku = int(sku_str[1:])
        except ValueError as exc:
            raise ValueError("El código QR contiene destino o producto no numérico.") from exc

        sig_esperada = firmar_etiqueta(codigo_etiqueta, folio_oc, id_loc, id_sku)
        if not hmac.compare_digest(sig_recibida.lower(), sig_esperada.lower()):
            raise ValueError("La firma de seguridad del código QR no es válida.")
        return {
            "formato": "FT1",
            "codigo_etiqueta": codigo_etiqueta,
            "folio_oc": None if folio_oc == "SIN-OC" else folio_oc,
            "id_locacion_destino": id_loc,
            "id_sku": id_sku,
            "firma_valida": True,
        }

    if "(01)" in crudo:
        m_gtin = _GS1_GTIN.search(crudo)
        if not m_gtin:
            raise ValueError("Código GS1 sin GTIN válido en identificador (01).")
        m_cad = _GS1_CAD.search(crudo)
        fecha_cad = None
        if m_cad:
            yy, mm, dd = m_cad.group(1)[:2], m_cad.group(1)[2:4], m_cad.group(1)[4:6]
            fecha_cad = f"20{yy}-{mm}-{dd}"
        m_lote = _GS1_LOTE.search(crudo)
        m_cant = _GS1_CANT.search(crudo)
        m_oc = _GS1_OC.search(crudo)
        return {
            "formato": "GS1",
            "codigo_etiqueta": None,
            "codigo_gtin": m_gtin.group(1),
            "lote_proveedor": m_lote.group(1).strip() if m_lote else None,
            "fecha_caducidad": fecha_cad,
            "cantidad": float(m_cant.group(1)) if m_cant else None,
            "folio_oc": m_oc.group(1).strip() if m_oc else None,
            "firma_valida": False,
        }

    if len(crudo) < 3 or len(crudo) > 64:
        raise ValueError("El código de etiqueta debe tener entre 3 y 64 caracteres.")
    return {
        "formato": "CODIGO",
        "codigo_etiqueta": crudo,
        "folio_oc": None,
        "id_locacion_destino": None,
        "id_sku": None,
        "firma_valida": False,
    }


def generar_svg_qr(payload: str, escala: int = 3) -> str:
    """Genera un QR SVG embebible en HTML para la vista previa de etiquetas."""
    qr = segno.make(payload, error="q")
    return qr.svg_inline(scale=escala, border=1)


def _dibujar_qr_vectorial(pdf: _LienzoPDF, payload: str, x: float, y_top: float, tamano_pt: float = 104.0) -> None:
    """Dibuja un código QR nítido en vectores PDF agrupando módulos horizontales por fila."""
    qr = segno.make(payload, error="q")
    matriz = qr.matrix
    n = len(matriz)
    if n == 0:
        return
    modulo = tamano_pt / n
    # Fondo blanco y marco sutil
    pdf.rect(x - 4, y_top - tamano_pt - 4, tamano_pt + 8, tamano_pt + 8, fill_rgb=(1, 1, 1), stroke_rgb=(0.82, 0.86, 0.90))

    for r_idx, row in enumerate(matriz):
        y_cell = y_top - (r_idx + 1) * modulo
        col = 0
        while col < n:
            if row[col]:
                inicio = col
                while col < n and row[col]:
                    col += 1
                ancho_run = (col - inicio) * modulo
                pdf.rect(x + inicio * modulo, y_cell, ancho_run, modulo, fill_rgb=(0.06, 0.10, 0.14))
            else:
                col += 1


def _dibujar_encabezado_asn(pdf: _LienzoPDF, asn_doc: dict, orden_compra: dict | None, continuacion: bool) -> None:
    pdf.nueva_pagina()
    pdf.rect(0, 738, pdf.ANCHO, 54, fill_rgb=(0.086, 0.639, 0.290))
    pdf.texto(36, 766, "FRESHTRACK · HOJA DE EMPAQUE Y ETIQUETAS QR", size=12.5, bold=True, rgb=(1, 1, 1))
    pdf.texto(36, 750, "Presentar al almacenista en muelle de tienda para escaneo y alta FEFO", size=9, rgb=(0.90, 0.98, 0.92))
    pdf.texto(576, 766, f"ASN: {asn_doc.get('folio_asn', '-')}", size=11, bold=True, rgb=(1, 1, 1), align="right")
    if asn_doc.get("folio_oc"):
        pdf.texto(576, 750, f"OC: {asn_doc['folio_oc']}", size=9, rgb=(0.90, 0.98, 0.92), align="right")

    if continuacion:
        pdf.y = 716
        return

    prov_nombre = (orden_compra or {}).get("proveedor") or f"Proveedor #{asn_doc.get('id_proveedor', '-')}"
    trans = asn_doc.get("transporte") or {}
    pdf.rect(36, 680, 540, 44, fill_rgb=(0.975, 0.980, 0.985), stroke_rgb=(0.85, 0.88, 0.91))
    pdf.texto(46, 708, f"Proveedor: {_cortar(prov_nombre, 52)}", size=9.5, bold=True)
    pdf.texto(
        46,
        692,
        f"Embarque: {_fmt_fecha(asn_doc.get('fecha_embarque'))}  ·  Arribo est.: {_fmt_fecha(asn_doc.get('fecha_arribo_estimada'))}"
        + (f"  ·  Transporte: {_cortar(trans.get('placas') or trans.get('chofer'), 28)}" if (trans.get("placas") or trans.get("chofer")) else ""),
        size=8.3,
    )
    pdf.y = 666


def generar_pdf_hoja_asn(asn_doc: dict, orden_compra: dict | None = None) -> bytes:
    """Genera PDF 1.4 multipágina con tarjetas imprimibles y código QR vectorial por etiqueta."""
    etiquetas = asn_doc.get("etiquetas") or []
    pdf = _LienzoPDF()
    _dibujar_encabezado_asn(pdf, asn_doc, orden_compra, continuacion=False)

    alto_tarjeta = 192.0
    for idx, etq in enumerate(etiquetas):
        if pdf.y - alto_tarjeta < 42:
            _dibujar_encabezado_asn(pdf, asn_doc, orden_compra, continuacion=True)

        y_top = pdf.y
        y_bot = y_top - alto_tarjeta
        # Contenedor tarjeta
        pdf.rect(36, y_bot, 540, alto_tarjeta, fill_rgb=(0.995, 0.998, 0.999), stroke_rgb=(0.78, 0.83, 0.88))
        # Barra de tienda destino en grande
        pdf.rect(36, y_top - 28, 540, 28, fill_rgb=(0.91, 0.96, 0.93), stroke_rgb=(0.78, 0.83, 0.88))
        pdf.texto(
            48,
            y_top - 18,
            f"TIENDA DESTINO: {_cortar(etq.get('locacion_destino') or ('Locacion ' + str(etq.get('id_locacion_destino'))), 40)}",
            size=10.5,
            bold=True,
            rgb=(0.06, 0.42, 0.18),
        )
        pdf.texto(564, y_top - 18, f"Partida {idx + 1} de {len(etiquetas)}", size=8.5, bold=True, align="right")

        # Bloque QR a la izquierda
        payload = etq.get("qr_payload") or construir_payload_qr(
            etq["codigo_etiqueta"],
            asn_doc.get("folio_oc"),
            int(etq["id_locacion_destino"]),
            int(etq["id_sku"]),
        )
        _dibujar_qr_vectorial(pdf, payload, x=52, y_top=y_top - 40, tamano_pt=104.0)
        pdf.texto(50, y_bot + 16, etq.get("codigo_etiqueta", "-"), size=8.5, bold=True)
        pdf.texto(50, y_bot + 6, "Escaneo QR / NFC muelle", size=7.2, rgb=(0.42, 0.46, 0.52))

        # Metadatos de lote a la derecha del QR
        dx = 176.0
        pdf.texto(dx, y_top - 50, _cortar(etq.get("producto") or f"SKU #{etq.get('id_sku')}", 48), size=11, bold=True)
        pdf.texto(dx, y_top - 66, f"GTIN: {etq.get('codigo_gtin') or '-'}   |   OC: {asn_doc.get('folio_oc') or '-'}", size=8.5)
        pdf.linea(dx, y_top - 74, 562, y_top - 74)

        pdf.texto(dx, y_top - 92, f"Lote proveedor: {etq.get('lote_proveedor') or '-'}", size=9.5, bold=True)
        pdf.texto(dx, y_top - 108, f"Cantidad declarada: {_fmt_num(etq.get('cantidad_declarada'), 2)} {etq.get('unidad_medida') or 'u'}", size=9.5, bold=True, rgb=(0.06, 0.45, 0.20))
        pdf.texto(dx, y_top - 125, f"Producción: {_fmt_fecha(etq.get('fecha_produccion'))}     Caducidad: {_fmt_fecha(etq.get('fecha_caducidad'))}", size=8.8)
        pdf.texto(dx, y_top - 141, f"Temperatura sugerida: {etq.get('rango_temperatura_controlada') or '2C a 6C'}", size=8.5)
        if etq.get("codigo_rfid_epc"):
            pdf.texto(dx, y_top - 156, f"RFID EPC: {_cortar(etq['codigo_rfid_epc'], 38)}", size=7.8, rgb=(0.35, 0.40, 0.45))

        # Talón de verificación manual
        pdf.linea(dx, y_bot + 26, 562, y_bot + 26)
        pdf.texto(dx, y_bot + 12, "Recibido tienda: Cant. real _________   Temp ____ C   Firma _________________", size=7.8, rgb=(0.35, 0.40, 0.45))

        pdf.y = y_bot - 14

    if not etiquetas:
        pdf.texto(36, pdf.y - 20, "Este aviso ASN no contiene etiquetas de despacho generadas.", size=10)

    return empaquetar_pdf(
        pdf.cerrar(),
        folio=str(asn_doc.get("folio_asn", "ASN")),
        prefijo_pie="FreshTrack · Hoja de Empaque y Recepción QR",
        ancho=pdf.ANCHO,
        alto=pdf.ALTO,
    )
