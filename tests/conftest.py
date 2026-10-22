"""
Configuración común de pytest para FreshTrack.

- Las pruebas unitarias (tests/unit) no requieren ningún servidor: Redis se sustituye
  por fakeredis (con soporte Lua) y PostgreSQL no se toca.
- Las pruebas de integración (tests/integration) usan PostgreSQL real. Redis y MongoDB
  se usan reales si responden (así corre en CI con docker compose); si no, se
  sustituyen por fakeredis/mongomock para poder ejecutarlas en una laptop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")
# Valores mínimos para poder importar app.config sin un .env (p. ej. en CI unitario).
os.environ.setdefault("SECRET_KEY", "clave-de-pruebas-freshtrack-0123456789abcdef")
os.environ.setdefault("JWT_SECRET_KEY", "jwt-de-pruebas-freshtrack-0123456789abcdef")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app_backend:x@127.0.0.1:1/inexistente")
os.environ.setdefault("DB_CONNECT_TIMEOUT", "2")

import fakeredis  # noqa: E402
import pytest  # noqa: E402

from app.services import cache_service  # noqa: E402


def _redis_real_disponible() -> bool:
    import redis

    from app.config import Config

    try:
        cliente = redis.Redis(
            host=Config.REDIS_HOST, port=Config.REDIS_PORT, password=Config.REDIS_PASSWORD,
            socket_connect_timeout=1, decode_responses=True,
        )
        return bool(cliente.ping())
    except Exception:
        return False


@pytest.fixture()
def redis_falso(monkeypatch):
    """Redis en memoria (con Lua) para pruebas unitarias aisladas."""
    cliente = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache_service, "_client", cliente)
    return cliente


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        else:
            item.add_marker(pytest.mark.unit)


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: pruebas unitarias sin servicios externos")
    config.addinivalue_line("markers", "integration: pruebas de integración con PostgreSQL y los microservicios")
