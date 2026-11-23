"""
Códec XML de la app: mismas reglas que `app/services/common/response.py` del servidor.

- `parse_xml`: un elemento sin hijos es su texto (recortado); si todas las hijas comparten
  etiqueta y (son >1 o la etiqueta es de lista) el valor es una lista; si no, un dict.
- `to_xml`: dicts → elementos; listas → `<item>` (`tickets`→`<ticket>`, `lineas`→`<linea>`).
- `validate`: valida contra `contracts/xsd/<nombre>.xsd` con lxml (esquemas en caché).
"""

from __future__ import annotations

import re
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from lxml import etree

from .config import xsd_dir
from .errors import XmlContractError

ETIQUETAS_LISTA = {"item", "item_carga", "linea", "subitem", "ticket"}
_ITEM_POR_CLAVE = {"tickets": "ticket", "lineas": "linea"}
_MAX_MOTIVOS = 10

_cache_esquemas: dict[Path, etree.XMLSchema] = {}
_lock_cache = threading.Lock()


def _parser() -> etree.XMLParser:
    # Sin entidades externas ni red (XXE); lxml no es thread-safe compartiendo parsers.
    return etree.XMLParser(resolve_entities=False, no_network=True, remove_comments=True, remove_pis=True)


def _sin_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _a_bytes(data: bytes | str) -> bytes:
    return data.encode("utf-8") if isinstance(data, str) else bytes(data or b"")


def _raiz(data: bytes | str) -> etree._Element:
    crudo = _a_bytes(data)
    if not crudo.strip():
        raise XmlContractError("La respuesta está vacía; se esperaba XML.", ["documento vacío"])
    try:
        return etree.fromstring(crudo, _parser())
    except etree.XMLSyntaxError as exc:
        raise XmlContractError("El documento no es XML bien formado.", [str(exc)]) from exc


def _valor(elem: etree._Element) -> Any:
    hijos = [h for h in elem if isinstance(h.tag, str)]
    if not hijos:
        return (elem.text or "").strip()
    etiquetas = [_sin_ns(h.tag) for h in hijos]
    es_lista = len(set(etiquetas)) == 1 and (len(hijos) > 1 or etiquetas[0] in ETIQUETAS_LISTA)
    if es_lista:
        return [_valor(h) for h in hijos]
    return {_sin_ns(h.tag): _valor(h) for h in hijos}


def parse_xml(data: bytes | str) -> tuple[str, Any]:
    """Devuelve (etiqueta raíz, valor). Lanza XmlContractError si no es XML bien formado."""
    raiz = _raiz(data)
    return _sin_ns(raiz.tag), _valor(raiz)


# --- Serialización ---------------------------------------------------------------
def _etiqueta_valida(nombre: Any) -> str:
    tag = re.sub(r"[^A-Za-z0-9_.-]", "_", str(nombre))
    if not tag or not (tag[0].isalpha() or tag[0] == "_"):
        tag = f"_{tag}"
    return tag


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, Decimal):
        return format(valor, "f")
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return str(valor)


def _construir(padre: etree._Element, datos: Any, nombre_item: str = "item") -> None:
    if isinstance(datos, dict):
        for k, v in datos.items():
            sub = etree.SubElement(padre, _etiqueta_valida(k))
            _construir(sub, v, _ITEM_POR_CLAVE.get(str(k), "item"))
    elif isinstance(datos, (list, tuple, set)):
        for elem in datos:
            _construir(etree.SubElement(padre, nombre_item), elem)
    else:
        padre.text = _texto(datos)


def to_xml(data: dict, root: str) -> bytes:
    """Serializa `data` a un documento XML UTF-8 con raíz `root`."""
    raiz = etree.Element(_etiqueta_valida(root))
    _construir(raiz, data)
    return etree.tostring(raiz, encoding="UTF-8", xml_declaration=True)


# --- Validación XSD --------------------------------------------------------------
def xsd_path(xsd_name: str) -> Path:
    nombre = xsd_name if xsd_name.endswith(".xsd") else f"{xsd_name}.xsd"
    return xsd_dir() / nombre


def has_xsd(xsd_name: str) -> bool:
    return xsd_path(xsd_name).is_file()


def _esquema(xsd_name: str) -> etree.XMLSchema:
    ruta = xsd_path(xsd_name).resolve()
    with _lock_cache:
        esquema = _cache_esquemas.get(ruta)
        if esquema is None:
            if not ruta.is_file():
                raise XmlContractError(f"No existe el contrato XSD '{ruta.name}'.", [str(ruta)])
            esquema = etree.XMLSchema(etree.parse(str(ruta), _parser()))
            _cache_esquemas[ruta] = esquema
        return esquema


def validate(xml: bytes | str, xsd_name: str) -> None:
    """Valida `xml` contra su contrato XSD. Lanza XmlContractError con hasta 10 motivos."""
    esquema = _esquema(xsd_name)
    doc = _raiz(xml)
    with _lock_cache:  # XMLSchema no es seguro entre hilos
        ok = esquema.validate(doc)
        errores = list(esquema.error_log)
    if not ok:
        motivos = [f"línea {e.line}: {e.message}" for e in errores[:_MAX_MOTIVOS]] or ["no cumple el contrato"]
        nombre = Path(xsd_path(xsd_name)).name
        raise XmlContractError(f"El XML no cumple el contrato {nombre}.", motivos)


# --- Utilidades para la UI ---------------------------------------------------------
def as_list(v: Any) -> list:
    """Normaliza un valor a lista: None/'' → [], dict/escalar → [v], lista → lista."""
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, tuple):
        return list(v)
    return [v]


def num(v: Any, default: float = 0.0) -> float:
    """Convierte a float; None, '' o texto no numérico → `default`."""
    if v is None or v == "" or isinstance(v, bool):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
