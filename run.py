"""
Punto de entrada de FreshTrack.

    python run.py

Levanta la aplicación Flask. Antes de arrancar comprueba que PostgreSQL
responde; si no, avisa en lugar de fallar con un error de conexión críptico.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402  (después de cargar el .env)
from app.db import escalar  # noqa: E402

app = create_app()


def _comprobar_base() -> bool:
    try:
        escalar("SELECT 1")
        return True
    except Exception as e:  # pragma: no cover - sólo diagnóstico de arranque
        print("\n[!] No se pudo conectar a PostgreSQL.", file=sys.stderr)
        print(f"    {e}", file=sys.stderr)
        print("    Revisa DATABASE_URL en tu archivo .env.\n", file=sys.stderr)
        return False


if __name__ == "__main__":
    if not _comprobar_base():
        sys.exit(1)

    host = os.getenv("APP_HOST", "127.0.0.1")
    puerto = int(os.getenv("APP_PORT", "5000"))
    print(f"FreshTrack escuchando en http://{host}:{puerto}")
    app.run(
        host=host,
        port=puerto,
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
