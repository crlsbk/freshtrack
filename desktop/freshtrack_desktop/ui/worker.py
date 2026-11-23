"""
Ejecución en segundo plano: `Worker` (QRunnable) + `WorkerSignals` (QObject).

`WorkerSignals` se crea en el hilo de UI, así que sus señales emitidas desde el hilo del
pool llegan encoladas al hilo de UI. Quien lance el worker debe conservar una referencia a
`signals` hasta recibir `finished` (AppContext lo hace); si no, el QObject podría
destruirse antes de entregar el resultado.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(object)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:  # corre en un hilo del QThreadPool: nada de widgets aquí
        signals = self.signals
        try:
            valor = self.fn(*self.args, **self.kwargs)
        except BaseException as exc:  # noqa: BLE001 - se entrega al hilo de UI
            signals.error.emit(exc)
        else:
            signals.result.emit(valor)
        finally:
            signals.finished.emit()
