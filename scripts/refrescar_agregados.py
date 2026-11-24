"""
Refresca los agregados materializados de FreshTrack (sql/08_optimizacion.sql).

La app web ya lo hace sola cada 10 min cuando hace falta; este script sirve
para forzarlo tras una carga manual o desde un cron:

    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec app \
        python scripts/refrescar_agregados.py [--forzar]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.domain import agregados  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--forzar", action="store_true", help="Refrescar aunque el histórico esté al día")
    args = ap.parse_args()
    if not agregados.disponible():
        print("[agregados] La base no tiene sql/08_optimizacion.sql aplicado.", file=sys.stderr)
        return 1
    ms = agregados.refrescar(forzar=args.forzar)
    print("[agregados] Ya estaba al día." if ms is None else f"[agregados] Refrescado en {ms} ms.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
