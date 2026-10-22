"""
Integración de seguridad entre componentes: el token que emite svc-auth sirve en los
demás servicios, y su revocación (logout o cierre forzado) se refleja en todos vía Redis.
"""

from __future__ import annotations

import jwt

from app.config import Config
from app.db import one
from app.services import cache_service
from tests.integration.conftest import USUARIOS, bearer


def test_login_json_entrega_jwt_y_crea_sesion_en_redis(svc, login):
    token = login("warehouse")
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["rol"] == "warehouse" and claims["iss"] == "freshtrack"
    assert cache_service.sesion_activa(claims["jti"]) is True
    assert cache_service.obtener_ttl(f"session:{claims['jti']}") > 0
    fila = one("SELECT revocado FROM operacion.sesion_usuario WHERE jti = :j", j=claims["jti"])
    assert fila is not None and fila["revocado"] is False


def test_login_xml_con_respuesta_xml(svc):
    cache_service.invalidar_patron("ratelimit:*login*")
    email, password = USUARIOS["auditor"]
    r = svc["auth"].post(
        "/api/v1/auth/login",
        data=f"<login_request><email>{email}</email><password>{password}</password></login_request>",
        content_type="application/xml",
        headers={"Accept": "application/xml"},
    )
    assert r.status_code == 200
    assert r.mimetype == "application/xml"
    assert b"<auth_response>" in r.data and b"<token>" in r.data


def test_login_errores_controlados(svc):
    cache_service.invalidar_patron("ratelimit:*login*")
    malo = svc["auth"].post("/api/v1/auth/login", json={"email": "admin@freshtrack.mx", "password": "incorrecta"})
    assert malo.status_code == 401 and malo.get_json()["error"] == "credenciales_invalidas"
    falta = svc["auth"].post("/api/v1/auth/login", json={"email": "admin@freshtrack.mx"})
    assert falta.status_code == 400 and falta.get_json()["detalles"]["faltantes"] == ["password"]
    xsd = svc["auth"].post("/api/v1/auth/login", data="<login_request><email>no-es-correo</email></login_request>", content_type="application/xml")
    assert xsd.status_code == 400 and xsd.get_json()["error"] == "xml_no_cumple_contrato"
    inactivo = svc["auth"].post("/api/v1/auth/login", json={"email": "inactivo@freshtrack.mx", "password": "Inactivo2026!"})
    assert inactivo.status_code == 401


def test_rate_limit_de_login(svc):
    cache_service.invalidar_patron("ratelimit:*login*")
    if cache_service.get_redis_client() is None:
        return
    codigos = [
        svc["auth"].post("/api/v1/auth/login", json={"email": "nadie@freshtrack.mx", "password": "x"}).status_code
        for _ in range(11)
    ]
    assert codigos[:10] == [401] * 10 and codigos[10] == 429
    cache_service.invalidar_patron("ratelimit:*login*")


def test_token_de_auth_funciona_en_otros_servicios(svc, tokens):
    t = tokens["warehouse"]
    assert svc["inventory"].get("/api/v1/inventory/stock?por_pagina=1", headers=bearer(t)).status_code == 200
    assert svc["commercial"].get("/api/v1/commercial/sales?por_pagina=1", headers=bearer(t)).status_code == 200
    assert svc["auth"].post("/api/v1/auth/verify", headers=bearer(t)).get_json()["valido"] is True


def test_rbac_entre_servicios(svc, tokens):
    # Auditor: puede leer la bitácora, no puede dar de alta productos ni vender.
    assert svc["audit"].get("/api/v1/audit/events?por_pagina=1", headers=bearer(tokens["auditor"])).status_code == 200
    r = svc["catalog"].post("/api/v1/catalog/products", json={"nombre": "x"}, headers=bearer(tokens["auditor"]))
    assert r.status_code == 403 and r.get_json()["error"] == "acceso_denegado"
    assert svc["commercial"].post("/api/v1/commercial/checkout", json={}, headers=bearer(tokens["auditor"])).status_code == 403
    # Gerente de tienda no puede ver la bitácora.
    assert svc["audit"].get("/api/v1/audit/events", headers=bearer(tokens["store_manager"])).status_code == 403
    # Admin pasa en todos.
    assert svc["auth"].get("/api/v1/auth/users?por_pagina=2", headers=bearer(tokens["admin"])).status_code == 200


def test_tokens_invalidos_y_expirados(svc, tokens):
    manipulado = tokens["admin"][:-4] + "AAAA"
    assert svc["catalog"].get("/api/v1/catalog/suppliers", headers=bearer(manipulado)).status_code == 401
    claims = jwt.decode(tokens["admin"], options={"verify_signature": False})
    claims["exp"] = 1
    expirado = jwt.encode(claims, Config.JWT_SECRET_KEY, algorithm="HS256")
    assert svc["catalog"].get("/api/v1/catalog/suppliers", headers=bearer(expirado)).status_code == 401
    otro_secreto = jwt.encode({**claims, "exp": 4102444800}, "secreto-ajeno-de-32-bytes-o-mas-xxxxxxxx", algorithm="HS256")
    assert svc["catalog"].get("/api/v1/catalog/suppliers", headers=bearer(otro_secreto)).status_code == 401
    assert svc["catalog"].get("/api/v1/catalog/suppliers").status_code == 401


def test_logout_revoca_en_todos_los_servicios(svc, login):
    token = login("store_manager")
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    assert svc["inventory"].get("/api/v1/inventory/stock?por_pagina=1", headers=bearer(token)).status_code == 200

    assert svc["auth"].post("/api/v1/auth/logout", headers=bearer(token)).status_code == 200

    assert cache_service.esta_jwt_revocado(jti)
    assert cache_service.sesion_activa(jti) is False
    assert one("SELECT revocado FROM operacion.sesion_usuario WHERE jti = :j", j=jti)["revocado"] is True
    for nombre, ruta in (("inventory", "/api/v1/inventory/stock"), ("commercial", "/api/v1/commercial/sales"), ("alerts", "/api/v1/alerts/esg/carbon-avoided")):
        r = svc[nombre].get(ruta, headers=bearer(token))
        assert r.status_code == 401, nombre
        assert r.get_json()["error"] == "token_revocado"


def test_admin_cierra_sesiones_de_otro_usuario(svc, login, tokens):
    token = login("planner")
    id_usuario = jwt.decode(token, options={"verify_signature": False})["sub"]
    sesiones = svc["auth"].get(f"/api/v1/auth/sessions/{id_usuario}", headers=bearer(tokens["admin"])).get_json()
    assert sesiones["total_activas"] >= 1

    r = svc["auth"].delete(f"/api/v1/auth/sessions/{id_usuario}", headers=bearer(tokens["admin"]))
    assert r.status_code == 200 and r.get_json()["sesiones_cerradas"] >= 1
    assert svc["planning"].get("/api/v1/planning/replenishment/orders", headers=bearer(token)).status_code == 401


def test_ids_invalidos_dan_400_no_500(svc, tokens):
    r = svc["auth"].get("/api/v1/auth/sessions/no-es-uuid", headers=bearer(tokens["admin"]))
    assert r.status_code == 400
    r = svc["audit"].get("/api/v1/audit/traceability/123", headers=bearer(tokens["auditor"]))
    assert r.status_code == 400
