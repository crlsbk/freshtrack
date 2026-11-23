"""La app valida contra `contracts/xsd/<raiz>.xsd` toda respuesta cuya raíz tenga contrato."""

from __future__ import annotations

import pytest

from freshtrack_desktop.core.api_client import ApiClient
from freshtrack_desktop.core.errors import XmlContractError

RUTA = "/api/v1/planning/newsvendor/evaluate"

NEWSVENDOR = """<?xml version="1.0" encoding="UTF-8"?>
<newsvendor_evaluation><id_sku>1</id_sku><producto>Leche Entera 1L</producto><id_locacion>1</id_locacion>
<horizonte>7</horizonte><demanda_horizonte>0.0</demanda_horizonte><cantidad_sugerida>{cantidad}</cantidad_sugerida>
<newsvendor><costo_faltante>6.4</costo_faltante><fractil_critico>0.3156</fractil_critico><z_score>-0.48</z_score>
<acotado_por_caducidad>false</acotado_por_caducidad></newsvendor><advertencias /></newsvendor_evaluation>"""

ORDENES = """<?xml version="1.0" encoding="UTF-8"?>
<replenishment_orders><paginacion><pagina>1</pagina><por_pagina>5</por_pagina><total>1</total>
<total_paginas>1</total_paginas></paginacion><ordenes><item><id_orden>abc-1</id_orden><id_sku>{id_sku}</id_sku>
<cantidad_sugerida>266.0</cantidad_sugerida><cantidad_aprobada /><prioridad>ALTA</prioridad>
<estado>PENDIENTE</estado></item></ordenes></replenishment_orders>"""


@pytest.fixture
def api(settings) -> ApiClient:
    return ApiClient(settings)


def test_respuesta_valida_pasa(api, fake_http):
    fake_http.add("POST", RUTA, body=NEWSVENDOR.format(cantidad="120"))
    datos = api.call("planning", "POST", RUTA, body=b"<newsvendor_request/>")
    assert datos["cantidad_sugerida"] == "120"


def test_decimal_invalido_lanza_error_de_contrato(api, fake_http):
    fake_http.add("POST", RUTA, body=NEWSVENDOR.format(cantidad="abc"))
    with pytest.raises(XmlContractError) as exc:
        api.call("planning", "POST", RUTA, body=b"<newsvendor_request/>")
    assert "newsvendor_evaluation.xsd" in str(exc.value)
    assert exc.value.status == 200
    assert exc.value.correlation_id == fake_http.calls[0].headers["X-Correlation-Id"]


def test_campo_anidado_invalido_tambien_se_detecta(api, fake_http):
    ruta = "/api/v1/planning/replenishment/orders"
    fake_http.add("GET", ruta, body=ORDENES.format(id_sku="10"))
    fake_http.add("GET", ruta, body=ORDENES.format(id_sku="diez"))
    assert api.call("planning", "GET", ruta)["ordenes"][0]["id_sku"] == "10"
    with pytest.raises(XmlContractError):
        api.call("planning", "GET", ruta)


def test_raiz_sin_xsd_no_se_valida(api, fake_http):
    fake_http.add("GET", "/api/v1/x", body=b"<foo_bar><cantidad_sugerida>abc</cantidad_sugerida></foo_bar>")
    assert api.call("planning", "GET", "/api/v1/x") == {"cantidad_sugerida": "abc"}
