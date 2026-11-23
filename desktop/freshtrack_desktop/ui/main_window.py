"""Ventana principal: barra lateral + páginas, menús, inspector XML y barra de estado."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.api_client import Exchange
from .login_dialog import ROLE_NAMES
from .pages.base import BasePage
from . import icons
from .widgets import std_icon
from .xml_inspector import XmlInspector

SESSION_EXPIRED_MSG = "Tu sesión terminó o fue revocada"


class MainWindow(QMainWindow):
    session_ended = Signal(str)   # cerrar sesión ("") o sesión vencida (mensaje): volver al login
    quit_requested = Signal()     # Salir / cerrar la ventana
    _exchange_desde_hilo = Signal(object)

    def __init__(self, ctx, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.pages: list[BasePage] = []
        self._cerrando_sesion = False
        self._actual = -1
        self.setWindowTitle("FreshTrack Desktop")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.setWindowIcon(QIcon(icons.app_logo(64)))
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setIconSize(QSize(18, 18))
        self.sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar.currentRowChanged.connect(self._activar)
        self.stack = QStackedWidget()
        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._panel_lateral())
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.inspector = XmlInspector(ctx, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector)
        self.inspector.hide()

        self.user_label = QLabel()
        self.service_label = QLabel("Último servicio: —")
        self.statusBar().addPermanentWidget(self.service_label)
        self.statusBar().addPermanentWidget(self.user_label)
        self._actualizar_usuario()

        self._menus()
        # Los listeners del ApiClient corren en el hilo de la petición: se encola al hilo de UI.
        self._exchange_desde_hilo.connect(self._ultima_llamada, Qt.ConnectionType.QueuedConnection)
        self._listener = self._exchange_desde_hilo.emit
        ctx.api.listeners.append(self._listener)
        ctx.unauthorized.connect(self.on_unauthorized)
        ctx.window = self

    # ------------------------------------------------------------------ armado
    def _panel_lateral(self) -> QFrame:
        """Barra lateral: marca arriba, páginas al centro y tarjeta del usuario abajo."""
        panel = QFrame()
        panel.setObjectName("SidebarPanel")
        panel.setFixedWidth(232)
        v = QVBoxLayout(panel)
        v.setContentsMargins(12, 16, 12, 12)
        v.setSpacing(10)

        marca = QHBoxLayout()
        marca.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.app_logo(34))
        nombre = QVBoxLayout()
        nombre.setSpacing(0)
        t1 = QLabel("FreshTrack")
        t1.setObjectName("BrandName")
        t2 = QLabel("Planeación y compras")
        t2.setObjectName("BrandSub")
        nombre.addWidget(t1)
        nombre.addWidget(t2)
        marca.addWidget(logo)
        marca.addLayout(nombre, 1)
        v.addLayout(marca)
        v.addSpacing(6)

        seccion = QLabel("MENÚ")
        seccion.setObjectName("SidebarSection")
        v.addWidget(seccion)
        v.addWidget(self.sidebar, 1)

        tarjeta = QFrame()
        tarjeta.setObjectName("UserCard")
        h = QHBoxLayout(tarjeta)
        h.setContentsMargins(10, 8, 6, 8)
        h.setSpacing(8)
        self.avatar = QLabel()
        self.avatar.setObjectName("Avatar")
        self.avatar.setFixedSize(32, 32)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        datos = QVBoxLayout()
        datos.setSpacing(0)
        self.card_name = QLabel()
        self.card_name.setObjectName("UserName")
        self.card_role = QLabel()
        self.card_role.setObjectName("UserRole")
        datos.addWidget(self.card_name)
        datos.addWidget(self.card_role)
        salir = QToolButton()
        salir.setObjectName("LogoutButton")
        salir.setIcon(std_icon("logout"))
        salir.setIconSize(QSize(18, 18))
        salir.setToolTip("Cerrar sesión")
        salir.setCursor(Qt.CursorShape.PointingHandCursor)
        salir.clicked.connect(lambda: self.logout())
        h.addWidget(self.avatar)
        h.addLayout(datos, 1)
        h.addWidget(salir)
        v.addWidget(tarjeta)
        return panel

    def _menus(self) -> None:
        mb = self.menuBar()
        archivo = mb.addMenu("&Archivo")
        self.act_logout = self._accion(archivo, "Cerrar sesión", self.logout, icon="SP_DialogCloseButton")
        archivo.addSeparator()
        self._accion(archivo, "Salir", self.close, QKeySequence.StandardKey.Quit)

        ver = mb.addMenu("&Ver")
        self._accion(ver, "Actualizar página", self.refresh_current, "Ctrl+R", icon="SP_BrowserReload")
        ver.addSeparator()
        self.act_inspector = self.inspector.toggleViewAction()
        self.act_inspector.setText("Inspector XML")
        self.act_inspector.setShortcut(QKeySequence("F12"))
        ver.addAction(self.act_inspector)
        self._accion(ver, "Actividad", lambda: self.show_page("Actividad"), icon="SP_FileDialogInfoView")

        ayuda = mb.addMenu("Ay&uda")
        self._accion(ayuda, "Acerca de FreshTrack Desktop", self._acerca_de)

    def _accion(self, menu, texto, slot, atajo=None, icon="") -> QAction:
        a = QAction(texto, self)
        if atajo is not None:
            a.setShortcut(QKeySequence(atajo))
        if icon:
            a.setIcon(std_icon(icon))
        a.triggered.connect(lambda _c=False: slot())
        menu.addAction(a)
        return a

    def register_pages(self, page_classes: list[type[BasePage]]) -> None:
        """Crea las páginas que el rol de la sesión puede ver (roles vacíos = todos)."""
        session = self.ctx.api.session
        for cls in page_classes:
            if not cls.allowed_for(session):
                continue
            page = cls(self.ctx)
            self.pages.append(page)
            self.stack.addWidget(page)
            item = QListWidgetItem(std_icon(icons.PAGE_ICONS.get(cls.title, cls.icon)), cls.title)
            item.setSizeHint(QSize(200, 40))
            self.sidebar.addItem(item)
        if self.pages and self.sidebar.currentRow() < 0:
            self.sidebar.setCurrentRow(0)

    # ------------------------------------------------------------------ navegación
    def page_titles(self) -> list[str]:
        return [p.title for p in self.pages]

    def current_page(self) -> BasePage | None:
        w = self.stack.currentWidget()
        return w if isinstance(w, BasePage) else None

    def page(self, title: str) -> BasePage | None:
        return next((p for p in self.pages if p.title == title), None)

    def show_page(self, title: str) -> bool:
        for i, p in enumerate(self.pages):
            if p.title == title:
                self.sidebar.setCurrentRow(i)
                return True
        return False

    def _activar(self, fila: int) -> None:
        if fila < 0 or fila >= len(self.pages):
            return
        if 0 <= self._actual < len(self.pages) and self._actual != fila:
            self.pages[self._actual].on_hide()
        self._actual = fila
        self.stack.setCurrentIndex(fila)
        self.pages[fila].on_show()

    def refresh_current(self) -> None:
        p = self.current_page()
        if p is not None:
            p.refresh()

    # ------------------------------------------------------------------ estado
    def _actualizar_usuario(self) -> None:
        s = self.ctx.api.session
        if s is None:
            self.user_label.setText("Sin sesión")
            self.card_name.setText("Sin sesión")
            self.card_role.setText("")
            self.avatar.setText("?")
            return
        nombre = s.usuario.get("nombre") or s.email
        self.user_label.setText(f"{nombre} · {ROLE_NAMES.get(s.rol, s.rol)} ({s.rol})")
        self.card_name.setText(nombre)
        self.card_name.setToolTip(s.email)
        self.card_role.setText(ROLE_NAMES.get(s.rol, s.rol))
        iniciales = "".join(p[0] for p in str(nombre).split()[:2] if p).upper() or "?"
        self.avatar.setText(iniciales)

    def _ultima_llamada(self, ex: Exchange) -> None:
        svc = self.ctx.service_for_url(ex.url) or "?"
        estado = ex.status if ex.status else "sin conexión"
        self.service_label.setText(f"Último servicio: {svc} · {estado} · {ex.elapsed_ms:.0f} ms")

    def _acerca_de(self) -> None:
        QMessageBox.about(
            self, "Acerca de FreshTrack Desktop",
            f"<b>FreshTrack Desktop {__version__}</b><br>Cliente de escritorio para compradores y "
            "planeadores. Consume solo XML de los microservicios (validado con XSD).<br>"
            "IAC, Proyecto 12, Equipo 05.")

    # ------------------------------------------------------------------ sesión
    def logout(self) -> None:
        """Envía la bitácora pendiente a auditoría, revoca el token y vuelve al login."""
        if self._cerrando_sesion:
            return
        self.ctx.log.record("LOGOUT", "Cierre de sesión")
        api, log = self.ctx.api, self.ctx.log

        def trabajo():
            log.sync_remote(api)
            api.logout()

        self.act_logout.setEnabled(False)
        self.ctx.run(trabajo, on_ok=lambda _r: self._terminar_sesion(""),
                     on_error=lambda _e: self._terminar_sesion(""))

    def on_unauthorized(self) -> None:
        """Token vencido o revocado: cierra la ventana y regresa al login con aviso."""
        if self._cerrando_sesion:
            return
        self.ctx.log.record("SESION_TERMINADA", SESSION_EXPIRED_MSG, ok=False)
        self._terminar_sesion(SESSION_EXPIRED_MSG)

    def _terminar_sesion(self, mensaje: str) -> None:
        if self._cerrando_sesion:
            return
        self._cerrando_sesion = True
        self.ctx.log.set_user(None)
        self.close()
        self.session_ended.emit(mensaje)

    def detach(self) -> None:
        """Deja de escuchar al ApiClient y al contexto (al cerrar)."""
        try:
            self.ctx.api.listeners.remove(self._listener)
        except ValueError:
            pass
        try:
            self.ctx.unauthorized.disconnect(self.on_unauthorized)
        except (RuntimeError, TypeError):
            pass
        self.inspector.detach()
        if self.ctx.window is self:
            self.ctx.window = None

    def closeEvent(self, event) -> None:
        p = self.current_page()
        if p is not None:
            p.on_hide()
        self.detach()
        super().closeEvent(event)
        if not self._cerrando_sesion:
            self.quit_requested.emit()
