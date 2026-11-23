"""POST /api/v1/commercial/sales/import: importación masiva idempotente de ventas (XML + XSD)."""

from __future__ import annotations

import sys

import jwt
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.config import Config
from app.services import cache_service
from app.services.common import auth as auth_mod
from app.services.common.response import xml_a_dict


def _token(rol="buyer", jti="jti-1"):
    return jwt.encode({"sub": "u-1", "rol": rol, "email": "x@freshtrack.mx", "jti": jti}, Config.JWT_SECRET_KEY, algorithm="HS256")


def _ticket(folio, cantidad="2", canal=None):
    canal_xml = f"<canal>{canal}</canal>" if canal else ""
    return (f"<ticket><folio_externo>{folio}</folio_externo>{canal_xml}"
            f"<lineas><linea><id_sku>1</id_sku><cantidad>{cantidad}</cantidad></linea></lineas></ticket>")


def _xml(*tickets):
    return f"<sales_import_request><id_locacion>2</id_locacion><tickets>{''.join(tickets)}</tickets></sales_import_request>"


@pytest.fixture()
def ctx(redis_falso, monkeypatch):
    from app.services.commercial_service import app as mod

    def decodificar(token):
        try:
            return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None

    monkeypatch.setattr(auth_mod, "decodificar_token", decodificar)
    cache_service.crear_sesion_redis("jti-1", {"id_usuario": "u-1"})
    llamadas = []

    def falsa(*, id_locacion, lineas, usuario, canal="TIENDA"):
        llamadas.append({"id_locacion": id_locacion, "lineas": lineas, "canal": canal})
        n = len(llamadas)
        return {"id_venta": n, "folio": f"V-{n:04d}"}

    monkeypatch.setattr(mod.dom_ventas, "registrar_venta", falsa)
    return mod.app.test_client(), llamadas, mod


def _post(cli, cuerpo, rol="buyer"):
    return cli.post(
        "/api/v1/commercial/sales/import",
        data=cuerpo.encode(),
        headers={"Content-Type": "application/xml", "Accept": "application/xml", "Authorization": f"Bearer {_token(rol)}"},
    )


def _resultado(resp):
    d = xml_a_dict(resp.data)
    for k in ("importados", "duplicados", "errores"):
        d[k] = int(d[k])
    return d


def test_dos_tickets_importados(ctx):
    cli, llamadas, _ = ctx
    r = _post(cli, _xml(_ticket("A-1"), _ticket("A-2", canal="ONLINE")))
    assert r.status_code == 200, r.data
    d = _resultado(r)
    assert d["importados"] == 2 and d["duplicados"] == 0 and d["errores"] == 0
    assert [x["estado"] for x in d["resultados"]] == ["IMPORTADO", "IMPORTADO"]
    assert d["resultados"][0]["folio"] == "V-0001"
    assert llamadas[0]["canal"] == "TIENDA" and llamadas[1]["canal"] == "ONLINE"
    assert llamadas[0]["id_locacion"] == 2


def test_reenvio_es_duplicado(ctx):
    cli, llamadas, _ = ctx
    cuerpo = _xml(_ticket("A-1"), _ticket("A-2"))
    _post(cli, cuerpo)
    d = _resultado(_post(cli, cuerpo))
    assert d["duplicados"] == 2 and d["importados"] == 0
    assert [x["estado"] for x in d["resultados"]] == ["DUPLICADO", "DUPLICADO"]
    assert len(llamadas) == 2


def test_xsd_violado_400(ctx):
    cli, _, _ = ctx
    r = _post(cli, _xml(_ticket("A-1", cantidad="0")))
    assert r.status_code == 400
    assert "xml_no_cumple_contrato" in r.get_data(as_text=True)


def test_rol_no_permitido_403(ctx):
    cli, _, _ = ctx
    assert _post(cli, _xml(_ticket("A-1")), rol="warehouse").status_code == 403


def test_error_en_un_ticket_no_detiene_los_demas(ctx, monkeypatch, redis_falso):
    cli, _, mod = ctx

    def falsa(*, id_locacion, lineas, usuario, canal="TIENDA"):
        if lineas and any(float(l["cantidad"]) == 99 for l in lineas):
            raise ValueError("Inventario insuficiente")
        return {"id_venta": 7, "folio": "V-0007"}

    monkeypatch.setattr(mod.dom_ventas, "registrar_venta", falsa)
    d = _resultado(_post(cli, _xml(_ticket("B-1", cantidad="99"), _ticket("B-2"))))
    assert d["errores"] == 1 and d["importados"] == 1
    assert d["resultados"][0]["estado"] == "ERROR" and "insuficiente" in d["resultados"][0]["mensaje"]
    assert d["resultados"][1]["estado"] == "IMPORTADO"
    # la clave del ticket fallido se liberó: se puede reintentar
    assert redis_falso.get("importacion:venta:2:B-1") is None
    assert redis_falso.get("importacion:venta:2:B-2") is not None


def test_sin_redis_503(ctx, monkeypatch, redis_falso):
    cli, llamadas, mod = ctx
    real = cache_service.get_redis_client

    def solo_endpoint_sin_redis():
        # La autenticación sigue viendo Redis; solo el endpoint lo ve caído.
        return None if sys._getframe(1).f_globals["__name__"] == mod.__name__ else real()

    monkeypatch.setattr(cache_service, "get_redis_client", solo_endpoint_sin_redis)
    r = _post(cli, _xml(_ticket("A-1")))
    assert r.status_code == 503 and "redis_no_disponible" in r.get_data(as_text=True)
    assert llamadas == []


def test_error_de_conexion_redis_503(ctx, monkeypatch, redis_falso):
    cli, llamadas, _ = ctx

    def falla(*a, **k):
        raise RedisConnectionError("caído")

    monkeypatch.setattr(redis_falso, "set", falla)
    r = _post(cli, _xml(_ticket("A-1")))
    assert r.status_code == 503 and "redis_no_disponible" in r.get_data(as_text=True)
    assert llamadas == []


def test_excepcion_inesperada_libera_clave_y_permite_reintento(ctx, monkeypatch, redis_falso):
    cli, _, mod = ctx
    fallar = {"si": True}

    def falsa(*, id_locacion, lineas, usuario, canal="TIENDA"):
        if fallar["si"] and float(lineas[0]["cantidad"]) == 99:
            raise RuntimeError("deadlock interno secreto")
        return {"id_venta": 9, "folio": "V-0009"}

    monkeypatch.setattr(mod.dom_ventas, "registrar_venta", falsa)
    cuerpo = _xml(_ticket("C-1", cantidad="99"), _ticket("C-2"))
    r = _post(cli, cuerpo)
    assert r.status_code == 200
    d = _resultado(r)
    assert [x["estado"] for x in d["resultados"]] == ["ERROR", "IMPORTADO"]
    assert "secreto" not in d["resultados"][0]["mensaje"]
    assert redis_falso.get("importacion:venta:2:C-1") is None
    fallar["si"] = False
    d2 = _resultado(_post(cli, cuerpo))
    assert [x["estado"] for x in d2["resultados"]] == ["IMPORTADO", "DUPLICADO"]


def test_folio_duplicado_en_el_mismo_lote(ctx):
    cli, llamadas, _ = ctx
    d = _resultado(_post(cli, _xml(_ticket("D-1"), _ticket("D-1"))))
    assert [x["estado"] for x in d["resultados"]] == ["IMPORTADO", "DUPLICADO"]
    assert len(llamadas) == 1
