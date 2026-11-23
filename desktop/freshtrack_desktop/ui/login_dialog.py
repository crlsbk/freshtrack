"""Inicio de sesión (POST /auth/login en XML) y configuración de servidores."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from ..core.config import PUERTOS
from ..core.session import Session
from . import theme
from .context import error_message
from .widgets import button, secondary_label, set_tone

# Cuentas de demostración del seed (sql/07_seed_base.sql, README).
DEMO_ACCOUNTS = {
    "buyer": ("buyer@freshtrack.mx", "Compras2026!"),
    "planner": ("planner@freshtrack.mx", "Plan2026!"),
}
ROLE_REJECTED_MSG = "Esta aplicación es para compradores y planeadores"
_RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROLE_NAMES = {"buyer": "Comprador", "planner": "Planeador", "admin": "Administrador"}


class ServersDialog(QDialog):
    """Edita host o gateway y los guarda en config.ini (Settings.save)."""

    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Servidores")
        self.setMinimumWidth(460)
        self.host = QLineEdit(settings.host)
        self.host.setPlaceholderText("http://localhost")
        self.gateway = QLineEdit(settings.gateway_url)
        self.gateway.setPlaceholderText("https://gateway.ejemplo.com (opcional)")
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1, 120)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(float(settings.timeout))
        form = QFormLayout()
        form.addRow("Host de los servicios", self.host)
        form.addRow("Gateway (opcional)", self.gateway)
        form.addRow("Tiempo de espera", self.timeout)
        puertos = ", ".join(f"{s} {p}" for s, p in PUERTOS.items())
        ayuda = secondary_label(
            f"Sin gateway se usa host:puerto de cada servicio ({puertos}). "
            "Con gateway, los 8 servicios van a esa URL.")
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(ayuda)
        lay.addWidget(botones)

    def accept(self) -> None:
        self.settings.set_servers(self.host.text(), self.gateway.text())
        self.settings.timeout = float(self.timeout.value())
        try:
            self.settings.save()
        except OSError as exc:  # sin permiso de escritura: los cambios valen para esta ejecución
            QMessageBox.warning(self, "Servidores", f"No se pudo guardar ({exc}); los cambios valen solo para esta sesión.")
        super().accept()


class LoginDialog(QDialog):
    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("FreshTrack Desktop: iniciar sesión")
        self.setMinimumWidth(400)

        marca = QLabel("FreshTrack")
        marca.setStyleSheet(f"font-size: {theme.TITLE_PT + 5}pt; font-weight: 700; color: {theme.tokens()['primary']};")
        sub = secondary_label("App de escritorio para compradores y planeadores")

        self.email = QLineEdit()
        self.email.setPlaceholderText("correo@freshtrack.mx")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Contraseña")
        form = QFormLayout()
        form.addRow("Correo", self.email)
        form.addRow("Contraseña", self.password)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message.hide()

        self.btn_entrar = button("Entrar", self._entrar, variant="primary")
        self.btn_entrar.setDefault(True)
        self.btn_servidores = button("Servidores…", self._servidores, icon="SP_DriveNetIcon")
        acciones = QHBoxLayout()
        acciones.addWidget(self.btn_servidores)
        acciones.addStretch(1)
        acciones.addWidget(self.btn_entrar)

        self.btn_demo_buyer = button("Cuenta demo: Comprador", lambda: self._demo("buyer"), variant="link")
        self.btn_demo_planner = button("Cuenta demo: Planeador", lambda: self._demo("planner"), variant="link")
        demos = QHBoxLayout()
        demos.addWidget(self.btn_demo_buyer)
        demos.addWidget(self.btn_demo_planner)
        demos.addStretch(1)

        self.server_label = secondary_label("")
        self._actualizar_servidor()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 16)
        lay.setSpacing(12)
        lay.addWidget(marca)
        lay.addWidget(sub)
        lay.addLayout(form)
        lay.addWidget(self.message)
        lay.addLayout(acciones)
        lay.addLayout(demos)
        lay.addWidget(self.server_label)
        self.email.setFocus()

    # ---- UI
    def set_message(self, text: str, tone: str = "danger") -> None:
        self.message.setText(text)
        set_tone(self.message, tone)
        self.message.setVisible(bool(text))

    def _actualizar_servidor(self) -> None:
        s = self.ctx.settings
        destino = f"gateway {s.gateway_url}" if s.gateway_url else f"{s.host} (puertos 5001 a 5008)"
        self.server_label.setText(f"Servidor: {destino}")

    def _demo(self, rol: str) -> None:
        email, pw = DEMO_ACCOUNTS[rol]
        self.email.setText(email)
        self.password.setText(pw)

    def _servidores(self) -> None:
        dlg = ServersDialog(self.ctx.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._actualizar_servidor()
            self.ctx.log.record("CONFIGURAR_SERVIDORES", self.server_label.text())

    def _habilitar(self, si: bool) -> None:
        for w in (self.email, self.password, self.btn_servidores, self.btn_demo_buyer, self.btn_demo_planner):
            w.setEnabled(si)

    # ---- login
    def _entrar(self) -> None:
        email, pw = self.email.text().strip(), self.password.text()
        if not email or not pw:
            self.set_message("Escribe tu correo y tu contraseña.", "warning")
            return
        if not _RE_CORREO.match(email):
            self.set_message("El correo no tiene un formato válido.", "warning")
            return
        self.set_message("Conectando…", "info")
        self._habilitar(False)
        self.ctx.run(self.ctx.api.login, email, pw, on_ok=self._ok, on_error=self._error, busy=self.btn_entrar)

    def _ok(self, session: Session) -> None:
        self._habilitar(True)
        if session.rol not in Session.DESKTOP_ROLES:
            self.ctx.log.record("LOGIN_RECHAZADO", f"{session.email} con rol {session.rol}", ok=False)
            self.set_message(f"{ROLE_REJECTED_MSG}\nLa cuenta {session.email or self.email.text()} tiene rol "
                             f"«{session.rol}».")
            self.ctx.run(self.ctx.api.logout, on_error=lambda _exc: None)
            return
        self.ctx.log.set_user(session.email)
        self.ctx.log.record("LOGIN", f"Inicio de sesión como {session.rol}")
        self.set_message("")
        self.password.clear()
        self.accept()

    def _error(self, exc: BaseException) -> None:
        self._habilitar(True)
        cid = getattr(exc, "correlation_id", "")
        texto = error_message(exc)
        if cid:
            texto += f"\ncorrelation_id: {cid}"
        self.set_message(texto)
        self.ctx.log.record("LOGIN", f"{self.email.text().strip()}: {error_message(exc)} cid={cid or '-'}", ok=False)
        self.password.selectAll()
        self.password.setFocus()
