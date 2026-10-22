"""
Negociación de Contenido Dual (JSON y XML) para Microservicios FreshTrack.

Permite que cualquier endpoint responda en JSON (por omisión) o XML cuando
el cliente envíe 'Accept: application/xml' o 'Accept: text/xml', conforme
a las especificaciones de 'instrucciones_microservicios.md'.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from flask import Response, jsonify, request


def _construir_xml_element(padre: Element, datos: Any, nombre_item: str = "item") -> None:
    """Construye un árbol XML recursivamente a partir de diccionarios, listas y escalares."""
    if isinstance(datos, dict):
        for k, v in datos.items():
            # Sanear nombre de etiqueta para que sea válido en XML
            tag = str(k).replace(" ", "_").replace("-", "_").replace("@", "")
            sub = SubElement(padre, tag)
            _construir_xml_element(sub, v, nombre_item="item")
    elif isinstance(datos, (list, tuple, set)):
        for elem in datos:
            sub = SubElement(padre, nombre_item)
            _construir_xml_element(sub, elem, nombre_item="subitem")
    elif isinstance(datos, (datetime, date)):
        padre.text = datos.isoformat()
    elif datos is None:
        padre.text = ""
    elif isinstance(datos, bool):
        padre.text = "true" if datos else "false"
    else:
        padre.text = str(datos)


def dict_a_xml(datos: dict[str, Any] | list[Any], root_tag: str = "freshtrack_response") -> str:
    """Serializa una estructura de datos a un documento XML bien formado."""
    root = Element(root_tag)
    if isinstance(datos, list):
        _construir_xml_element(root, datos, nombre_item="item")
    else:
        _construir_xml_element(root, datos)
    
    xml_bytes = tostring(root, encoding="utf-8")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes.decode("utf-8")


def render_response(
    datos: Any,
    status: int = 200,
    root_tag: str = "response",
    headers: dict[str, str] | None = None,
) -> Response:
    """
    Inspecciona el encabezado 'Accept' del cliente:
    - Si pide 'application/xml' o 'text/xml', devuelve XML.
    - En caso contrario, devuelve JSON estándar.
    """
    accept = request.headers.get("Accept", "").lower()
    resp_headers = headers.copy() if headers else {}

    if "application/xml" in accept or "text/xml" in accept:
        if not isinstance(datos, (dict, list)):
            datos = {"data": datos}
        contenido_xml = dict_a_xml(datos, root_tag=root_tag)
        resp_headers["Content-Type"] = "application/xml; charset=utf-8"
        return Response(contenido_xml, status=status, headers=resp_headers)

    # Respuesta JSON estándar
    resp = jsonify(datos)
    resp.status_code = status
    for k, v in resp_headers.items():
        resp.headers[k] = str(v)
    return resp
