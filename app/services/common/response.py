"""
Negociación de Contenido Dual (JSON y XML) para Microservicios FreshTrack.

- Respuestas: JSON por omisión, XML cuando el cliente envía
  'Accept: application/xml' o 'Accept: text/xml'.
- Peticiones: el cuerpo se acepta en JSON o en XML ('Content-Type: application/xml').
  Si el endpoint tiene contrato XSD (contracts/xsd/<nombre>.xsd), el XML se valida
  contra el esquema antes de llegar a la lógica de negocio.
- Errores: todos los servicios responden con la misma estructura
  {error, mensaje, status, correlation_id[, detalles]} con raíz <error_response>.
- Paginación: ?pagina=N&por_pagina=M uniforme en los listados.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, ParseError, SubElement, fromstring, tostring

from flask import Response, g, has_request_context, jsonify, request
from werkzeug.exceptions import BadRequest

DIR_XSD = Path(__file__).resolve().parents[3] / "contracts" / "xsd"

POR_PAGINA_DEFECTO = 20
POR_PAGINA_MAXIMO = 100

# Etiquetas que siempre representan elementos de una lista al leer XML.
_ETIQUETAS_LISTA = {"item", "item_carga", "linea", "subitem"}


# =============================================================================
# Serialización a XML
# =============================================================================
def _etiqueta_valida(nombre: Any) -> str:
    tag = re.sub(r"[^A-Za-z0-9_.-]", "_", str(nombre))
    if not tag or not (tag[0].isalpha() or tag[0] == "_"):
        tag = f"_{tag}"
    return tag


def _construir_xml_element(padre: Element, datos: Any, nombre_item: str = "item") -> None:
    """Construye un árbol XML recursivamente a partir de diccionarios, listas y escalares."""
    if isinstance(datos, dict):
        for k, v in datos.items():
            sub = SubElement(padre, _etiqueta_valida(k))
            _construir_xml_element(sub, v, nombre_item="item")
    elif isinstance(datos, (list, tuple, set)):
        for elem in datos:
            sub = SubElement(padre, nombre_item)
            _construir_xml_element(sub, elem, nombre_item="item")
    elif isinstance(datos, (datetime, date)):
        padre.text = datos.isoformat()
    elif datos is None:
        padre.text = ""
    elif isinstance(datos, bool):
        padre.text = "true" if datos else "false"
    elif isinstance(datos, Decimal):
        padre.text = format(datos, "f")
    else:
        padre.text = str(datos)


def dict_a_xml(datos: dict[str, Any] | list[Any], root_tag: str = "freshtrack_response") -> str:
    """Serializa una estructura de datos a un documento XML UTF-8 bien formado."""
    root = Element(_etiqueta_valida(root_tag))
    _construir_xml_element(root, datos, nombre_item="item")
    xml_bytes = tostring(root, encoding="utf-8")
    texto = xml_bytes.decode("utf-8")
    if texto.startswith("<?xml"):
        texto = texto.split("?>", 1)[1].lstrip()
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + texto


def _quiere_xml() -> bool:
    if not has_request_context():
        return False
    accept = request.headers.get("Accept", "").lower()
    if "application/xml" in accept or "text/xml" in accept:
        return True
    return request.args.get("formato", "").lower() == "xml"


def render_response(
    datos: Any,
    status: int = 200,
    root_tag: str = "response",
    headers: dict[str, str] | None = None,
) -> Response:
    """
    Inspecciona el encabezado 'Accept' del cliente (o ?formato=xml):
    - Si pide 'application/xml' o 'text/xml', devuelve XML.
    - En caso contrario, devuelve JSON estándar.
    """
    resp_headers = dict(headers) if headers else {}

    if _quiere_xml():
        if not isinstance(datos, (dict, list)):
            datos = {"data": datos}
        contenido_xml = dict_a_xml(datos, root_tag=root_tag)
        resp_headers["Content-Type"] = "application/xml; charset=utf-8"
        return Response(contenido_xml, status=status, headers=resp_headers)

    resp = jsonify(datos)
    resp.status_code = status
    for k, v in resp_headers.items():
        resp.headers[k] = str(v)
    return resp


# =============================================================================
# Errores estandarizados
# =============================================================================
def correlation_id() -> str:
    if not has_request_context():
        return uuid.uuid4().hex
    cid = getattr(g, "correlation_id", None)
    if not cid:
        cid = request.headers.get("X-Correlation-Id") or uuid.uuid4().hex
        g.correlation_id = cid
    return cid


def error_response(
    status: int,
    codigo: str,
    mensaje: str,
    detalles: Any = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """Respuesta de error uniforme para todos los microservicios (JSON o XML)."""
    cuerpo: dict[str, Any] = {
        "error": codigo,
        "mensaje": mensaje,
        "status": status,
        "correlation_id": correlation_id(),
    }
    if detalles is not None:
        cuerpo["detalles"] = detalles
    return render_response(cuerpo, status=status, root_tag="error_response", headers=headers)


class ErrorApi(Exception):
    """Error de negocio o validación que se traduce a una respuesta HTTP estándar."""

    def __init__(self, status: int, codigo: str, mensaje: str, detalles: Any = None):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalles = detalles


# =============================================================================
# Lectura del cuerpo de la petición (JSON o XML)
# =============================================================================
def _valor_xml(elem: Element) -> Any:
    hijos = list(elem)
    if not hijos:
        return (elem.text or "").strip()
    etiquetas = [_sin_ns(h.tag) for h in hijos]
    es_lista = len(set(etiquetas)) == 1 and (len(hijos) > 1 or etiquetas[0] in _ETIQUETAS_LISTA)
    if es_lista:
        return [_valor_xml(h) for h in hijos]
    return {_sin_ns(h.tag): _valor_xml(h) for h in hijos}


def _sin_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def xml_a_dict(texto: str | bytes) -> dict[str, Any]:
    """Convierte un documento XML en diccionario (la raíz se descarta)."""
    try:
        raiz = fromstring(texto)
    except ParseError as exc:
        raise ErrorApi(400, "xml_mal_formado", f"El XML no está bien formado: {exc}") from exc
    valor = _valor_xml(raiz)
    if isinstance(valor, list):
        return {"items": valor}
    if not isinstance(valor, dict):
        return {}
    return valor


_cache_esquemas: dict[str, Any] = {}


def validar_xsd(texto: str | bytes, contrato: str) -> None:
    """Valida un documento XML contra contracts/xsd/<contrato>.xsd. Lanza ErrorApi 400."""
    import xmlschema

    esquema = _cache_esquemas.get(contrato)
    if esquema is None:
        ruta = DIR_XSD / f"{contrato}.xsd"
        if not ruta.exists():
            raise ErrorApi(500, "contrato_inexistente", f"No existe el contrato XSD '{contrato}'.")
        esquema = xmlschema.XMLSchema(str(ruta))
        _cache_esquemas[contrato] = esquema
    errores = [
        {"ruta": e.path, "motivo": e.reason}
        for e in esquema.iter_errors(texto if isinstance(texto, str) else texto.decode("utf-8"))
    ]
    if errores:
        raise ErrorApi(400, "xml_no_cumple_contrato", f"El XML no cumple el contrato {contrato}.xsd", errores[:10])


def leer_cuerpo(contrato_xsd: str | None = None, requerido: bool = False) -> dict[str, Any]:
    """
    Devuelve el cuerpo de la petición como diccionario, venga en JSON, XML o formulario.
    Si llega en XML y se indica `contrato_xsd`, se valida contra el esquema.
    """
    content_type = (request.headers.get("Content-Type") or "").lower()
    crudo = request.get_data(cache=True)

    if "xml" in content_type:
        if not crudo:
            raise ErrorApi(400, "cuerpo_vacio", "Se esperaba un documento XML en el cuerpo.")
        if contrato_xsd:
            validar_xsd(crudo, contrato_xsd)
        return xml_a_dict(crudo)

    if "json" in content_type or (crudo and crudo.strip()[:1] in (b"{", b"[")):
        try:
            datos = request.get_json(force=True, silent=False) if crudo else None
        except BadRequest as exc:
            raise ErrorApi(400, "json_mal_formado", "El cuerpo JSON no es válido.") from exc
        if datos is None:
            datos = {}
        if not isinstance(datos, dict):
            raise ErrorApi(400, "json_invalido", "El cuerpo JSON debe ser un objeto.")
        return datos

    if request.form:
        return request.form.to_dict()

    if crudo and requerido:
        raise ErrorApi(415, "tipo_no_soportado", "Content-Type no soportado: use application/json o application/xml.")
    if requerido:
        raise ErrorApi(400, "cuerpo_vacio", "La petición requiere un cuerpo JSON o XML.")
    return {}


def requerir_campos(datos: dict[str, Any], *campos: str) -> None:
    """Lanza 400 listando los campos obligatorios faltantes o vacíos."""
    faltantes = [c for c in campos if datos.get(c) in (None, "", [], {})]
    if faltantes:
        raise ErrorApi(400, "campos_requeridos", "Faltan campos obligatorios.", {"faltantes": faltantes})


def entero(datos: dict[str, Any], campo: str, *, minimo: int | None = None, defecto: int | None = None) -> int | None:
    """Convierte un campo a entero o lanza 400 con un mensaje claro."""
    valor = datos.get(campo)
    if valor in (None, ""):
        return defecto
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError) as exc:
        raise ErrorApi(400, "parametro_invalido", f"'{campo}' debe ser un número entero.") from exc
    if minimo is not None and n < minimo:
        raise ErrorApi(400, "parametro_invalido", f"'{campo}' debe ser mayor o igual a {minimo}.")
    return n


def decimal_pos(datos: dict[str, Any], campo: str, *, defecto: float | None = None, permitir_cero: bool = False) -> float | None:
    """Convierte un campo a número positivo o lanza 400."""
    valor = datos.get(campo)
    if valor in (None, ""):
        return defecto
    try:
        n = float(str(valor).strip())
    except (TypeError, ValueError) as exc:
        raise ErrorApi(400, "parametro_invalido", f"'{campo}' debe ser numérico.") from exc
    if n < 0 or (n == 0 and not permitir_cero) or math.isnan(n):
        raise ErrorApi(400, "parametro_invalido", f"'{campo}' debe ser mayor que cero.")
    return n


def validar_uuid(valor: str, campo: str = "id") -> str:
    try:
        return str(uuid.UUID(str(valor)))
    except (TypeError, ValueError) as exc:
        raise ErrorApi(400, "parametro_invalido", f"'{campo}' debe ser un UUID válido.") from exc


# =============================================================================
# Paginación
# =============================================================================
def paginacion() -> tuple[int, int, int]:
    """Lee ?pagina y ?por_pagina (o ?limite por compatibilidad). Devuelve (pagina, por_pagina, offset)."""
    args = request.args
    pagina = entero(args, "pagina", minimo=1, defecto=1)
    por_pagina = entero(args, "por_pagina", minimo=1, defecto=None)
    if por_pagina is None:
        por_pagina = entero(args, "limite", minimo=1, defecto=POR_PAGINA_DEFECTO)
    por_pagina = min(por_pagina, POR_PAGINA_MAXIMO)
    return pagina, por_pagina, (pagina - 1) * por_pagina


def meta_paginacion(pagina: int, por_pagina: int, total: int) -> dict[str, int]:
    return {
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "total_paginas": max(1, math.ceil(total / por_pagina)) if por_pagina else 1,
    }

