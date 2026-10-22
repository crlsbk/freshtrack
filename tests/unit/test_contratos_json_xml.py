"""Contratos JSON/XML: negociación de contenido, lectura de XML, XSD, errores y paginación."""

from __future__ import annotations

import pytest
import xmlschema
from flask import Flask

from app.services.common.response import (
    DIR_XSD,
    ErrorApi,
    dict_a_xml,
    error_response,
    leer_cuerpo,
    meta_paginacion,
    paginacion,
    render_response,
    validar_xsd,
    xml_a_dict,
)

app = Flask(__name__)


def test_respuesta_json_por_omision():
    with app.test_request_context("/"):
        resp = render_response({"a": 1}, status=201)
    assert resp.status_code == 201
    assert resp.mimetype == "application/json"
    assert resp.get_json() == {"a": 1}


@pytest.mark.parametrize("accept", ["application/xml", "text/xml", "application/xml;q=0.9"])
def test_respuesta_xml_con_accept(accept):
    with app.test_request_context("/", headers={"Accept": accept}):
        resp = render_response({"producto": {"id_sku": 7, "activo": True}, "lotes": [1, 2]}, root_tag="detalle")
    cuerpo = resp.get_data(as_text=True)
    assert resp.mimetype == "application/xml"
    assert cuerpo.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<detalle><producto><id_sku>7</id_sku><activo>true</activo></producto>" in cuerpo
    assert "<lotes><item>1</item><item>2</item></lotes>" in cuerpo


def test_respuesta_xml_con_parametro_formato():
    with app.test_request_context("/?formato=xml"):
        resp = render_response({"ok": True})
    assert resp.mimetype == "application/xml"


def test_dict_a_xml_sanea_etiquetas_invalidas():
    xml = dict_a_xml({"1campo": "x", "con espacio": "y", "_id": "z"}, root_tag="r")
    assert "<_1campo>x</_1campo>" in xml
    assert "<con_espacio>y</con_espacio>" in xml


def test_xml_a_dict_ida_y_vuelta():
    original = {"id_locacion": "2", "lineas": [{"id_sku": "1", "cantidad": "3"}]}
    assert xml_a_dict(dict_a_xml(original, "checkout_request")) == original


def test_xml_a_dict_un_solo_item_sigue_siendo_lista():
    datos = xml_a_dict("<r><lineas><item><id_sku>1</id_sku></item></lineas></r>")
    assert datos["lineas"] == [{"id_sku": "1"}]


def test_xml_mal_formado_da_400():
    with pytest.raises(ErrorApi) as exc:
        xml_a_dict("<r><sin_cerrar></r>")
    assert exc.value.status == 400 and exc.value.codigo == "xml_mal_formado"


def test_xsd_acepta_documento_valido():
    validar_xsd(
        "<asn_request><folio_asn>ASN-1</folio_asn><id_proveedor>1</id_proveedor>"
        "<detalle_carga><item_carga><id_sku>1</id_sku><cantidad_declarada>5</cantidad_declarada>"
        "<fecha_caducidad>2026-12-01</fecha_caducidad></item_carga></detalle_carga></asn_request>",
        "asn_request",
    )


def test_xsd_rechaza_tipos_y_campos_faltantes():
    with pytest.raises(ErrorApi) as exc:
        validar_xsd("<checkout_request><lineas><item><id_sku>abc</id_sku></item></lineas></checkout_request>", "checkout_request")
    assert exc.value.status == 400
    assert exc.value.codigo == "xml_no_cumple_contrato"
    assert exc.value.detalles


def test_todos_los_xsd_compilan():
    archivos = sorted(DIR_XSD.glob("*.xsd"))
    assert len(archivos) >= 9
    for f in archivos:
        xmlschema.XMLSchema(str(f))


def test_leer_cuerpo_json_y_xml():
    with app.test_request_context("/", method="POST", json={"a": 1}):
        assert leer_cuerpo() == {"a": 1}
    with app.test_request_context(
        "/", method="POST", data="<login_request><email>a@b.mx</email><password>x</password></login_request>",
        content_type="application/xml",
    ):
        assert leer_cuerpo("login_request") == {"email": "a@b.mx", "password": "x"}


def test_leer_cuerpo_json_invalido_y_vacio():
    with app.test_request_context("/", method="POST", data="{malo", content_type="application/json"):
        with pytest.raises(ErrorApi) as exc:
            leer_cuerpo()
        assert exc.value.codigo == "json_mal_formado"
    with app.test_request_context("/", method="POST"):
        with pytest.raises(ErrorApi) as exc:
            leer_cuerpo(requerido=True)
        assert exc.value.status == 400


def test_error_response_cumple_su_xsd():
    with app.test_request_context("/", headers={"Accept": "application/xml", "X-Correlation-Id": "abc123"}):
        resp = error_response(404, "no_encontrado", "No existe", {"id": 5})
    assert resp.status_code == 404
    esquema = xmlschema.XMLSchema(str(DIR_XSD / "error_response.xsd"))
    assert esquema.is_valid(resp.get_data(as_text=True))
    assert "<correlation_id>abc123</correlation_id>" in resp.get_data(as_text=True)


def test_error_response_json_estructura():
    with app.test_request_context("/"):
        cuerpo = error_response(409, "conflicto", "Ya existe").get_json()
    assert set(cuerpo) == {"error", "mensaje", "status", "correlation_id"}
    assert cuerpo["status"] == 409


def test_paginacion_por_defecto_y_limites():
    with app.test_request_context("/"):
        assert paginacion() == (1, 20, 0)
    with app.test_request_context("/?pagina=3&por_pagina=500"):
        assert paginacion() == (3, 100, 200)
    with app.test_request_context("/?pagina=0"):
        with pytest.raises(ErrorApi):
            paginacion()
    assert meta_paginacion(2, 10, 41) == {"pagina": 2, "por_pagina": 10, "total": 41, "total_paginas": 5}
