"""
Contexto compartido de la UI: settings, ApiClient, ActivityLog y la ventana activa.

- `run()` ejecuta trabajo de red en un QThreadPool y entrega el resultado en el hilo de UI.
- `show_error()` muestra el diálogo de error estándar (mensaje, HTTP, correlation_id).
- `ApiClient.on_unauthorized` llega desde un hilo de trabajo: se reenvía al hilo de UI con
  la señal `unauthorized` (conexión encolada) antes de tocar ningún widget.
"""

from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urlsplit

import shiboken6
from PySide6.QtCore import QObject, Qt, QThreadPool, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QWidget

from ..core.activity_log import ActivityLog
from ..core.api_client import ApiClient
from ..core.config import PUERTOS, Settings
from ..core.errors import ApiError, ServiceUnavailable, XmlContractError
from .worker import Worker, WorkerSignals

_RE_SERVICIO = re.compile(r"/api/v\d+/([a-z_]+)")


def error_message(exc: BaseException) -> str:
    """Mensaje en español para el usuario según el tipo de error."""
    if isinstance(exc, ServiceUnavailable):
        return f"El servicio {exc.service} no está disponible"
    if isinstance(exc, XmlContractError):
        if exc.status == 0:  # falló la validación local: la petición no salió a la red
            return f"El XML enviado no cumple su contrato: {exc.mensaje}" if exc.mensaje else \
                "El XML enviado no cumple su contrato"
        return "La respuesta no cumple el contrato XML"
    if isinstance(exc, ApiError):
        if exc.status == 403:
            return "No tienes permiso para esta acción"
        return exc.mensaje or f"Error HTTP {exc.status}"
    return f"Error inesperado: {exc}"


def _vivo(obj: Any) -> bool:
    """False si `obj` es un QObject cuyo objeto C++ ya se destruyó."""
    return not isinstance(obj, QObject) or shiboken6.isValid(obj)


def _objeto_destruido(exc: RuntimeError) -> bool:
    return "already deleted" in str(exc)


class AppContext(QObject):
    unauthorized = Signal()
    _unauthorized_desde_hilo = Signal()

    def __init__(self, settings: Settings, api: ApiClient, log: ActivityLog,
                 window: QMainWindow | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.api = api
        self.log = log
        self.window = window
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(6)
        self._activos: set[WorkerSignals] = set()
        self._busy: dict[int, int] = {}
        # ApiClient llama on_unauthorized en el hilo de la petición: se encola al hilo de UI.
        self._unauthorized_desde_hilo.connect(self.unauthorized.emit, Qt.ConnectionType.QueuedConnection)
        api.on_unauthorized = self._unauthorized_desde_hilo.emit

    # ------------------------------------------------------------------ trabajo en 2º plano
    @property
    def pending(self) -> int:
        """Trabajos lanzados con run() que aún no entregan resultado."""
        return len(self._activos)

    def run(self, fn: Callable[..., Any], *args: Any, on_ok: Callable[[Any], None] | None = None,
            on_error: Callable[[BaseException], None] | None = None, busy: QWidget | None = None) -> None:
        """Ejecuta `fn(*args)` en el pool; `on_ok`/`on_error` corren en el hilo de UI.

        Sin `on_error` se muestra el diálogo de error estándar. Mientras corre, `busy`
        queda deshabilitado, el cursor en espera y la barra de estado dice "Cargando…".
        """
        worker = Worker(fn, *args)
        sig = worker.signals
        self._activos.add(sig)
        if busy is not None and _vivo(busy):
            self._busy[id(busy)] = self._busy.get(id(busy), 0) + 1
            busy.setEnabled(False)
        if len(self._activos) == 1:
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.BusyCursor))
        self.notify("Cargando…", 0)

        cola = Qt.ConnectionType.QueuedConnection
        sig.result.connect(lambda valor: self._entregar(on_ok, valor), cola)
        sig.error.connect(lambda exc: self._fallo(exc, on_error, busy), cola)
        sig.finished.connect(lambda: self._terminar(sig, busy), cola)
        self.pool.start(worker)

    def _entregar(self, cb: Callable[[Any], None] | None, valor: Any) -> None:
        if cb is None or not _vivo(getattr(cb, "__self__", None)):
            return
        try:
            cb(valor)
        except RuntimeError as exc:
            if not _objeto_destruido(exc):
                raise

    def _fallo(self, exc: BaseException, on_error, busy) -> None:
        if on_error is not None:
            self._entregar(on_error, exc)
            return
        # Sesión vencida/revocada: lo atiende la señal `unauthorized` (vuelta al login).
        if isinstance(exc, ApiError) and exc.status == 401 and self.api.session is None:
            return
        parent = busy.window() if (busy is not None and _vivo(busy)) else self.window
        self.show_error(exc, parent)

    def _terminar(self, sig: WorkerSignals, busy: QWidget | None) -> None:
        self._activos.discard(sig)
        if busy is not None:
            restantes = self._busy.get(id(busy), 1) - 1
            if restantes <= 0:
                self._busy.pop(id(busy), None)
                if _vivo(busy):
                    busy.setEnabled(True)
            else:
                self._busy[id(busy)] = restantes
        if not self._activos:
            QApplication.restoreOverrideCursor()
            self.notify("Listo", 2000)
        sig.deleteLater()

    # ------------------------------------------------------------------ mensajes
    def show_error(self, exc: BaseException, parent: QWidget | None = None) -> QMessageBox | None:
        """Diálogo de error (no bloqueante) con HTTP y correlation_id copiables; lo registra.

        Un 401 que llega cuando ya no hay sesión ni ventana (la app volvió al login) no muestra
        nada: el aviso «Tu sesión terminó o fue revocada» ya está en el login.
        """
        status = getattr(exc, "status", 0)
        if status == 401 and self.api.session is None and (self.window is None or not _vivo(self.window)):
            return None
        mensaje = error_message(exc)
        cid = getattr(exc, "correlation_id", "") or "-"
        http = f"HTTP {status}" if status else "sin respuesta HTTP"
        if parent is not None and not _vivo(parent):
            parent = None
        dlg = QMessageBox(parent or self.window)
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setWindowTitle("FreshTrack: error")
        dlg.setText(mensaje)
        dlg.setInformativeText(f"{http} · correlation_id: {cid}")
        dlg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info = dlg.findChild(QLabel, "qt_msgbox_informativelabel")  # el cid vive en el texto informativo
        if info is not None:
            info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detalles = getattr(exc, "detalles", None)
        lineas = [f"Tipo: {type(exc).__name__}", f"Código: {getattr(exc, 'error', '-')}",
                  f"Mensaje del servidor: {exc}", f"correlation_id: {cid}"]
        if detalles:
            lineas.append("Detalles:")
            lineas += [f"  {d}" for d in (detalles if isinstance(detalles, list) else [detalles])]
        dlg.setDetailedText("\n".join(lineas))
        dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.log.record("ERROR", f"{mensaje} [{http}] cid={cid}", ok=False)
        dlg.open()
        return dlg

    def notify(self, text: str, timeout_ms: int = 5000) -> None:
        """Mensaje en la barra de estado de la ventana principal (si existe)."""
        w = self.window
        if w is None or not _vivo(w):
            return
        w.statusBar().showMessage(text, timeout_ms)

    def service_for_url(self, url: str) -> str:
        """Nombre del servicio que atendió `url` (por base URL o por la ruta /api/v1/<svc>)."""
        coincidencias = [s for s, base in self.settings.base_urls.items() if url.startswith(base.rstrip("/") + "/")]
        if len(coincidencias) == 1:
            return coincidencias[0]
        m = _RE_SERVICIO.search(urlsplit(url).path)
        if m and m.group(1) in PUERTOS:
            return m.group(1)
        return coincidencias[0] if coincidencias else ""
