from __future__ import annotations

from decimal import Decimal

import pytest

from freshtrack_desktop.core.errors import ApiError, XmlContractError
from freshtrack_desktop.core.xml_codec import as_list, num, parse_xml, to_xml, validate


def test_lista_vacia_es_cadena_y_as_list_la_vuelve_lista():
    raiz, valor = parse_xml(b'<?xml version="1.0"?><ordenes><total>0</total><ordenes/></ordenes>')
    assert raiz == "ordenes"
    assert valor == {"total": "0", "ordenes": ""}
    assert as_list(valor["ordenes"]) == []


def test_un_solo_item_es_lista():
    _, valor = parse_xml("<r><ordenes><item><id>7</id></item></ordenes></r>")
    assert valor == {"ordenes": [{"id": "7"}]}
    assert as_list(valor["ordenes"]) == [{"id": "7"}]


def test_varios_hijos_con_misma_etiqueta_son_lista():
    _, valor = parse_xml("<r><datos><orden>1</orden><orden>2</orden></datos></r>")
    assert valor == {"datos": ["1", "2"]}


@pytest.mark.parametrize("tag", ["item", "item_carga", "linea", "subitem", "ticket"])
def test_etiquetas_de_lista_con_un_hijo(tag):
    _, valor = parse_xml(f"<r><x><{tag}>a</{tag}></x></r>")
    assert valor == {"x": ["a"]}


def test_un_hijo_no_lista_es_dict():
    _, valor = parse_xml("<r><x><orden>1</orden></x></r>")
    assert valor == {"x": {"orden": "1"}}


def test_raiz_que_es_lista():
    raiz, valor = parse_xml("<lista><item>1</item><item>2</item></lista>")
    assert (raiz, valor) == ("lista", ["1", "2"])


def test_texto_se_recorta():
    assert parse_xml("<r>  hola \n</r>") == ("r", "hola")


def test_xml_mal_formado_lanza_contrato():
    with pytest.raises(XmlContractError) as exc:
        parse_xml(b"<html><body>502 Bad Gateway</body>")
    assert exc.value.error == "xml_invalido"
    assert isinstance(exc.value, ApiError)
    assert isinstance(exc.value.detalles, list) and exc.value.detalles


def test_ida_y_vuelta_to_xml_parse_xml():
    datos = {
        "id_locacion": 3,
        "activo": True,
        "nota": None,
        "precio": Decimal("12.50"),
        "items": [{"id_sku": 1}, {"id_sku": 2}],
        "uno": [{"id_sku": 9}],
        "tickets": [{"folio_externo": "T-1", "lineas": [{"id_sku": 5, "cantidad": 2.5}]}],
    }
    xml = to_xml(datos, "sales_import_request")
    assert isinstance(xml, bytes)
    assert b"<ticket>" in xml and b"<linea>" in xml
    raiz, valor = parse_xml(xml)
    assert raiz == "sales_import_request"
    assert valor == {
        "id_locacion": "3",
        "activo": "true",
        "nota": "",
        "precio": "12.50",
        "items": [{"id_sku": "1"}, {"id_sku": "2"}],
        "uno": [{"id_sku": "9"}],
        "tickets": [{"folio_externo": "T-1", "lineas": [{"id_sku": "5", "cantidad": "2.5"}]}],
    }


def test_to_xml_escapa_caracteres():
    _, valor = parse_xml(to_xml({"nota": "a < b & \"c\""}, "r"))
    assert valor == {"nota": 'a < b & "c"'}


def test_validate_acepta_login_valido():
    validate(to_xml({"email": "a@b.com", "password": "x"}, "login_request"), "login_request")


def test_validate_rechaza_login_sin_password():
    with pytest.raises(XmlContractError) as exc:
        validate(to_xml({"email": "a@b.com"}, "login_request"), "login_request")
    assert exc.value.error == "xml_invalido"
    assert 1 <= len(exc.value.detalles) <= 10
    assert any("password" in m for m in exc.value.detalles)


def test_validate_acepta_nombre_con_extension():
    validate(to_xml({"email": "a@b.com", "password": "x"}, "login_request"), "login_request.xsd")


def test_validate_contrato_inexistente():
    with pytest.raises(XmlContractError):
        validate(b"<r/>", "no_existe_este_contrato")


def test_as_list_y_num():
    assert as_list(None) == []
    assert as_list("") == []
    assert as_list({"a": 1}) == [{"a": 1}]
    assert as_list([1, 2]) == [1, 2]
    assert as_list("x") == ["x"]
    assert num("3.5") == 3.5
    assert num("") == 0.0
    assert num(None, default=-1) == -1
    assert num("abc", default=2.0) == 2.0
    assert num(4) == 4.0
