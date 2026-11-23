"""
Arranque de la app: QApplication, tema, contexto y flujo login → ventana principal.

    python -m freshtrack_desktop            (desde desktop/)
    python desktop/run_desktop.py           (desde la raíz del repo)
    ... --smoke                             abre el login y sale con código 0 a los ~300 ms
"""

from __future__ import annotations

import argparse
import sys
from typing import Callable

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from . import __version__
from .core.activity_log import ActivityLog
from .core.api_client import ApiClient
from .core.config import Settings
from .ui import theme
from .ui.context import AppContext
from .ui.login_dialog import LoginDialog
from .ui.main_window import MainWindow
from .ui.pages import ALL_PAGES

SMOKE_MS = 300


class AppController(QObject):
    """Alterna entre LoginDialog y MainWindow durante la vida de la app."""

    def __init__(self, ctx: AppContext, pages: list | None = None,
                 quit_fn: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.ctx = ctx
        self.pages = list(pages if pages is not None else ALL_PAGES)
        self.quit_fn = quit_fn or QApplication.quit
        self.login_dialog: LoginDialog | None = None
        self.window: MainWindow | None = None

    def show_login(self, message: str = "") -> LoginDialog:
        if self.login_dialog is not None:
            self.login_dialog.deleteLater()
        dlg = LoginDialog(self.ctx)
        if message:
            dlg.set_message(message, "warning")
        dlg.accepted.connect(self._abrir_ventana)
        dlg.rejected.connect(self.quit_fn)
        self.login_dialog = dlg
        dlg.show()
        dlg.raise_()
        return dlg

    def _abrir_ventana(self) -> None:
        w = MainWindow(self.ctx)
        w.register_pages(self.pages)
        w.session_ended.connect(self._sesion_terminada)
        w.quit_requested.connect(self.quit_fn)
        self.window = w
        w.show()

    def _sesion_terminada(self, message: str) -> None:
        self.window = None
        self.show_login(message)


def build_context() -> AppContext:
    settings = Settings.load()
    log = ActivityLog(settings.data_dir / "actividad.log")
    return AppContext(settings, ApiClient(settings), log)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="freshtrack_desktop", description="FreshTrack Desktop")
    parser.add_argument("--smoke", action="store_true",
                        help="abre la ventana de login y sale con código 0 (prueba de arranque)")
    parser.add_argument("--version", action="version", version=f"FreshTrack Desktop {__version__}")
    args = parser.parse_args(argv)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("FreshTrack Desktop")
    app.setOrganizationName("FreshTrack")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    theme.apply(app)

    ctx = build_context()
    try:
        if args.smoke:
            dlg = LoginDialog(ctx)
            dlg.show()
            QTimer.singleShot(SMOKE_MS, app.quit)
            codigo = app.exec()
            dlg.deleteLater()
            return int(codigo)
        controller = AppController(ctx)
        controller.show_login()
        return int(app.exec())
    finally:
        ctx.pool.waitForDone(3000)
        ctx.log.close()
