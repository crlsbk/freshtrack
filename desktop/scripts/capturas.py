"""Captura cada página de la app (offscreen) contra el stack real y guarda PNG.

    python desktop/scripts/capturas.py --email planner@freshtrack.mx --password 'Plan2026!' --prefijo planner
    python desktop/scripts/capturas.py --email buyer@freshtrack.mx --password 'Compras2026!' --prefijo buyer

Requiere los microservicios arriba (por defecto localhost:5001..5008; ver FRESHTRACK_HOST / FRESHTRACK_GATEWAY_URL).
"""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
DESKTOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from freshtrack_desktop.app import build_context  # noqa: E402
from freshtrack_desktop.ui import theme  # noqa: E402
from freshtrack_desktop.ui.main_window import MainWindow  # noqa: E402
from freshtrack_desktop.ui.pages import ALL_PAGES  # noqa: E402


def _slug(texto: str) -> str:
    sin = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "_".join(sin.lower().split())


def _esperar(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", default="planner@freshtrack.mx")
    ap.add_argument("--password", default="Plan2026!")
    ap.add_argument("--out", type=Path, default=DESKTOP / "docs" / "capturas")
    ap.add_argument("--espera-ms", type=int, default=6000, help="espera por página antes de capturar")
    ap.add_argument("--prefijo", default="", help="prefijo del nombre de archivo (p. ej. el rol)")
    args = ap.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    theme.apply(app)
    ctx = build_context()
    ctx.api.login(args.email, args.password)
    w = MainWindow(ctx)
    w.register_pages(ALL_PAGES)
    w.resize(1366, 820)
    w.show()
    _esperar(1500)
    pref = f"{args.prefijo}_" if args.prefijo else ""
    for i in range(w.sidebar.count()):
        w.sidebar.setCurrentRow(i)
        _esperar(args.espera_ms)
        nombre = f"{pref}{i:02d}_{_slug(w.sidebar.item(i).text())}.png"
        w.grab().save(str(args.out / nombre))
        print("captura", nombre)
    ctx.api.logout()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
