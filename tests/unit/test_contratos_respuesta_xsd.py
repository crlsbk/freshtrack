"""
Contratos XSD de las respuestas XML que consume la app de escritorio.

Cada raíz de respuesta tiene su `contracts/xsd/<raiz>.xsd`: raíz abierta (xs:any lax) y
elementos globales tipados para los campos clave. Las muestras de
`tests/fixtures/xml_respuestas/` son respuestas reales del stack (o armadas a partir del
código del endpoint cuando la base no tenía datos) y deben validar contra su XSD.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import xmlschema
from lxml import etree

from app.services.common.response import DIR_XSD

DIR_MUESTRAS = Path(__file__).resolve().parents[1] / "fixtures" / "xml_respuestas"

RAICES_RESPUESTA = (
    "forecast_run_result", "forecast_backtest", "forecast_drift", "kpis_pronosticos",
    "newsvendor_evaluation", "replenishment_orders", "planning_cycle_result", "transfers_list",
    "discounts_list", "triage_evaluation", "medicion_desperdicio", "reporte_esg_sostenibilidad",
    "kpis_alertas", "alertas_activas", "purchase_orders_list", "procurement_suppliers",
    "supplier_procurement_catalog", "sales_import_result", "catalogo_locaciones",
    "catalogo_productos", "auth_response",
)

_cache: dict[str, xmlschema.XMLSchema] = {}


def esquema(raiz: str) -> xmlschema.XMLSchema:
    if raiz not in _cache:
        _cache[raiz] = xmlschema.XMLSchema(str(DIR_XSD / f"{raiz}.xsd"))
    return _cache[raiz]


def raiz_de(texto: str) -> str:
    return etree.fromstring(texto.encode("utf-8")).tag


def muestras() -> list[Path]:
    return sorted(DIR_MUESTRAS.glob("*.xml"))


def muestra(nombre: str) -> str:
    return (DIR_MUESTRAS / nombre).read_text(encoding="utf-8")


@pytest.mark.parametrize("raiz", RAICES_RESPUESTA)
def test_cada_raiz_tiene_xsd_que_compila(raiz):
    ruta = DIR_XSD / f"{raiz}.xsd"
    assert ruta.is_file(), f"falta {ruta.name}"
    esquema(raiz)
    # La raíz declarada es exactamente la del nombre de archivo.
    assert raiz in esquema(raiz).elements


@pytest.mark.parametrize("raiz", RAICES_RESPUESTA)
def test_cada_xsd_tiene_comentario_de_endpoint(raiz):
    texto = (DIR_XSD / f"{raiz}.xsd").read_text(encoding="utf-8")
    assert re.search(r"<!-- svc-\w+ (GET|POST) /api/v1/\S+.*\(respuesta\) -->", texto), raiz


def test_hay_una_muestra_por_cada_raiz():
    raices = {raiz_de(p.read_text(encoding="utf-8")) for p in muestras()}
    faltan = set(RAICES_RESPUESTA) - raices
    assert not faltan, f"sin muestra: {sorted(faltan)}"


@pytest.mark.parametrize("ruta", muestras(), ids=lambda p: p.name)
def test_muestra_real_valida_contra_su_xsd(ruta):
    texto = ruta.read_text(encoding="utf-8")
    raiz = raiz_de(texto)
    if not (DIR_XSD / f"{raiz}.xsd").is_file():
        pytest.skip(f"{raiz} no tiene XSD")
    errores = [str(e.reason) for e in esquema(raiz).iter_errors(texto)][:5]
    assert not errores, f"{ruta.name} ({raiz}): {errores}"


@pytest.mark.parametrize(
    ("archivo", "original", "inyectado"),
    [
        # campo directo bajo la raíz
        ("newsvendor.xml", "<cantidad_sugerida>120</cantidad_sugerida>", "<cantidad_sugerida>abc</cantidad_sugerida>"),
        # fracción crítica fuera de 0..1
        ("newsvendor.xml", "<fractil_critico>0.3156</fractil_critico>", "<fractil_critico>1.5</fractil_critico>"),
        # campo anidado dentro de <ordenes><item>
        ("repl_orders.xml", "<id_sku>10</id_sku>", "<id_sku>abc</id_sku>"),
        # enumeración cerrada (CHECK de la base)
        ("repl_orders.xml", "<estado>PENDIENTE</estado>", "<estado>INVENTADO</estado>"),
        ("transfers.xml", "<estado>SUGERIDA</estado>", "<estado>SUGERIDO</estado>"),
        ("discounts.xml", "<descuento_pct>30.0</descuento_pct>", "<descuento_pct>treinta</descuento_pct>"),
        ("drift.xml", "<psi>0.458</psi>", "<psi>alto</psi>"),
        ("triage.xml", "<accion>MERMA</accion>", "<accion>REGALAR</accion>"),
        ("locations.xml", "<activo>true</activo>", "<activo>quizas</activo>"),
        ("auth_login.xml", "<expira_en_segundos>28800</expira_en_segundos>",
         "<expira_en_segundos>mucho</expira_en_segundos>"),
    ],
)
def test_valor_con_tipo_invalido_no_valida(archivo, original, inyectado):
    texto = muestra(archivo)
    assert original in texto, f"{archivo} ya no contiene {original}"
    malo = texto.replace(original, inyectado, 1)
    assert not esquema(raiz_de(malo)).is_valid(malo)


def test_valores_vacios_y_campos_nuevos_siguen_siendo_validos():
    xml = (
        "<newsvendor_evaluation><id_sku>1</id_sku><cantidad_sugerida /><fractil_critico />"
        "<campo_que_el_backend_agrego_despues><x>1</x></campo_que_el_backend_agrego_despues>"
        "<newsvendor><z_score>1e-05</z_score><sigma_horizonte>nan</sigma_horizonte></newsvendor>"
        "</newsvendor_evaluation>"
    )
    assert esquema("newsvendor_evaluation").is_valid(xml)


def test_un_campo_escalar_con_hijos_no_valida():
    xml = "<newsvendor_evaluation><cantidad_sugerida><x>1</x></cantidad_sugerida></newsvendor_evaluation>"
    assert not esquema("newsvendor_evaluation").is_valid(xml)
