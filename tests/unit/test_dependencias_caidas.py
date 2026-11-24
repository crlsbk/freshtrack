"""Regresión: si Redis o MongoDB caen después del arranque, el cliente guardado en memoria
no debe seguir usándose (cada petición pagaba el timeout y los 503 nunca se activaban)."""

from __future__ import annotations

import time

import pytest

from app.services import cache_service, doc_store


class _Caido:
    def __init__(self):
        self.pings = 0

    def ping(self):
        self.pings += 1
        raise ConnectionError("Redis no responde")


@pytest.fixture()
def redis_cacheado_caido(monkeypatch):
    cli = _Caido()
    monkeypatch.setattr(cache_service, "_client", cli)
    monkeypatch.setattr(cache_service, "_ultimo_ping", 0.0)
    monkeypatch.setattr(cache_service, "_ultimo_fallo", 0.0)
    return cli


def test_redis_cacheado_que_cae_devuelve_none(redis_cacheado_caido):
    assert cache_service.get_redis_client() is None
    assert redis_cacheado_caido.pings == 1


def test_redis_caido_no_reintenta_en_cada_llamada(redis_cacheado_caido, monkeypatch):
    intentos = []
    monkeypatch.setattr(cache_service.redis, "ConnectionPool", lambda **kw: intentos.append(kw) or (_ for _ in ()).throw(ConnectionError()))
    for _ in range(5):
        assert cache_service.get_redis_client() is None
    assert redis_cacheado_caido.pings == 1 and intentos == []


def test_redis_sano_no_hace_ping_en_cada_llamada(redis_falso, monkeypatch):
    pings = []
    original = redis_falso.ping
    monkeypatch.setattr(redis_falso, "ping", lambda: pings.append(1) or original())
    monkeypatch.setattr(cache_service, "_ultimo_ping", time.monotonic())
    for _ in range(20):
        assert cache_service.get_redis_client() is redis_falso
    assert pings == []


class _MongoCaido:
    class admin:  # noqa: N801
        @staticmethod
        def command(_):
            raise RuntimeError("ServerSelectionTimeoutError")


class _DbCaida:
    client = _MongoCaido()


def test_mongo_cacheado_que_cae_devuelve_none(monkeypatch):
    monkeypatch.setattr(doc_store, "_db", _DbCaida())
    monkeypatch.setattr(doc_store, "_ultimo_ping", 0.0)
    monkeypatch.setattr(doc_store, "_ultimo_fallo", 0.0)
    assert doc_store.get_mongo_db() is None
    # y dentro de la ventana de reintento ni siquiera intenta conectar
    monkeypatch.setattr(doc_store.pymongo, "MongoClient", lambda *a, **k: pytest.fail("no debía reintentar"))
    assert doc_store.get_mongo_db() is None


def test_alertas_responden_503_si_mongo_cae_despues_del_arranque(redis_falso, monkeypatch):
    import jwt

    from app.config import Config
    from app.services.alerts_service import app as alerts
    from app.services.common import auth as auth_mod

    monkeypatch.setattr(auth_mod, "decodificar_token",
                        lambda t: jwt.decode(t, Config.JWT_SECRET_KEY, algorithms=["HS256"]))
    cache_service.crear_sesion_redis("jti-m", {"id_usuario": "u-1"})
    tok = jwt.encode({"sub": "u-1", "rol": "store_manager", "jti": "jti-m", "id_locacion": 3},
                     Config.JWT_SECRET_KEY, algorithm="HS256")
    monkeypatch.setattr(doc_store, "_db", _DbCaida())
    monkeypatch.setattr(doc_store, "_ultimo_ping", 0.0)
    monkeypatch.setattr(doc_store, "_ultimo_fallo", 0.0)
    r = alerts.app.test_client().get("/api/v1/alerts/active", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 503 and r.get_json()["error"] == "mongo_no_disponible"


def test_postgres_caido_responde_503_no_401(redis_falso, monkeypatch):
    """Regresión: con PostgreSQL caído un token válido recibía 401 y las apps cerraban la sesión."""
    import jwt

    from app import security
    from app.config import Config
    from app.services.inventory_service import app as inv

    def bd_caida(*a, **k):
        raise RuntimeError("could not connect to server")

    monkeypatch.setattr(security, "one", bd_caida)
    ahora = int(time.time())
    tok = jwt.encode({"sub": "u-1", "rol": "store_manager", "jti": "jti-pg", "iss": "freshtrack", "iat": ahora,
                      "exp": ahora + 600, "id_locacion": 3}, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)
    r = inv.app.test_client().get("/api/v1/inventory/stock", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 503 and r.get_json()["error"] == "sesion_no_verificable"


def test_token_manipulado_sigue_siendo_401(redis_falso):
    from app.services.inventory_service import app as inv

    r = inv.app.test_client().get("/api/v1/inventory/stock", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401
