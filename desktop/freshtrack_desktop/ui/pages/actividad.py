"""Actividad: bitácora local del usuario y sincronización con svc-audit."""

from __future__ import annotations

from .base import BasePage
from ..widgets import DataTable


def _fecha(ts) -> str:
    """ISO 8601 con zona → "AAAA-MM-DD HH:MM:SS"."""
    return str(ts or "").replace("T", " ")[:19]


class ActividadPage(BasePage):
    title = "Actividad"
    subtitle = "Registro local de acciones; se puede enviar a svc-audit"
    icon = "SP_FileDialogInfoView"
    roles = ()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(ctx, parent)
        self.actions.add_button("Actualizar", self.refresh, icon="SP_BrowserReload")
        self.btn_sync = self.actions.add_button("Sincronizar con auditoría", self.sync, variant="primary",
                                                icon="SP_ArrowUp")
        self.subtitle_label.setText(f"{self.subtitle} · archivo: {ctx.log.path}")
        self.subtitle_label.show()
        self.table = DataTable(empty_text="Sin actividad registrada", title="Actividad")
        self.table.set_columns([("ts", "Fecha y hora", _fecha), ("usuario", "Usuario"), ("accion", "Acción"),
                                ("resultado", "Resultado", "status"), ("detalle", "Detalle")])
        self.body.addWidget(self.table, 1)

    def refresh(self) -> None:
        filas = []
        for e in reversed(self.ctx.log.tail()):  # más reciente primero
            fila = dict(e)
            fila["resultado"] = "OK" if e.get("ok", True) else "ERROR"
            filas.append(fila)
        self.table.set_rows(filas)

    def sync(self) -> None:
        self.ctx.run(self.ctx.log.sync_remote, self.ctx.api, on_ok=self._sincronizado, busy=self.btn_sync)

    def _sincronizado(self, enviados: int) -> None:
        if self.ctx.api.session is None:
            self.ctx.notify("Inicia sesión para sincronizar con auditoría")
        elif enviados:
            self.ctx.notify(f"Se enviaron {enviados} acciones a svc-audit")
        else:
            self.ctx.notify("No hay acciones pendientes por enviar (o svc-audit no respondió)")
