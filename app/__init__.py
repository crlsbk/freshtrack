"""
FreshTrack — sistema de gestión de inventario de perecederos.

Fábrica de la aplicación. Registra los blueprints y el procesador de contexto
que arma el menú lateral según el rol de la sesión.
"""

from __future__ import annotations

from decimal import Decimal

from flask import Flask, session
from flask.json.provider import DefaultJSONProvider

from app.config import Config
from app.navegacion import (
    ICONOS,
    VISTAS_POR_ROL,
    acento_para,
    menu_para,
    ruta_inicial,
)


class ProveedorJSON(DefaultJSONProvider):
    """Serializa Decimal como número y las fechas en ISO."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _registrar_filtros(app: Flask) -> None:
    """Filtros de presentación: miles con coma, decimales solo si hacen falta, fechas legibles."""
    from datetime import date, datetime

    @app.template_filter("cantidad")
    def cantidad(valor, decimales: int = 2) -> str:
        try:
            n = float(valor or 0)
        except (TypeError, ValueError):
            return str(valor)
        if decimales and abs(n - round(n)) < 0.005:
            decimales = 0
        return f"{n:,.{decimales}f}"

    UNIDADES_DISCRETAS = {
        "bolsa", "bolsas", "pieza", "piezas", "pza", "pzas",
        "paquete", "paquetes", "caja", "cajas", "frasco", "frascos", "botella", "botellas"
    }

    @app.template_filter("formato_unidad")
    def formato_unidad(valor, unidad: str | None = None) -> str:
        """Formatea cantidades declarando siempre la unidad de medida y evitando decimales incoherentes en productos discretos."""
        try:
            n = float(valor or 0)
        except (TypeError, ValueError):
            return f"{valor} {unidad or ''}".strip()

        u_str = (unidad or "").strip()
        u_lower = u_str.lower()
        es_discreta = u_lower in UNIDADES_DISCRETAS

        if es_discreta:
            num_str = f"{int(round(n)):,}"
        else:
            if abs(n - round(n)) < 0.005:
                num_str = f"{int(round(n)):,}"
            else:
                num_str = f"{n:,.2f}"

        if not u_str:
            return num_str

        # Pluralización en español
        n_abs = abs(n)
        if es_discreta and round(n_abs) != 1:
            if u_lower == "bolsa": u_display = "bolsas"
            elif u_lower in ("pieza", "pza"): u_display = "piezas"
            elif u_lower == "paquete": u_display = "paquetes"
            elif u_lower == "caja": u_display = "cajas"
            elif u_lower == "botella": u_display = "botellas"
            else: u_display = u_str
        else:
            u_display = u_str.lower() if es_discreta else u_str

        return f"{num_str} {u_display}"

    acentos = {
        "critico": "crítico", "critica": "crítica", "recepcion": "recepción", "dano": "daño",
        "frio": "frío", "devolucion": "devolución", "transito": "tránsito", "revision": "revisión",
        "manipulacion": "manipulación", "transferencia": "transferencia", "media": "media",
    }

    @app.template_filter("legible")
    def legible(valor) -> str:
        """CADENA_DE_FRIO → «Cadena de frío»: convierte códigos internos en texto para personas."""
        if not valor:
            return ""
        palabras = [acentos.get(p, p) for p in str(valor).lower().split("_")]
        texto = " ".join(palabras)
        return texto[:1].upper() + texto[1:]

    @app.template_filter("fecha_hora")
    def fecha_hora(valor) -> str:
        if isinstance(valor, str):
            try:
                valor = datetime.fromisoformat(valor)
            except ValueError:
                return valor
        if isinstance(valor, datetime):
            return f"{valor.day} {_MESES[valor.month - 1]} {valor.year}, {valor:%H:%M}"
        if isinstance(valor, date):
            return f"{valor.day} {_MESES[valor.month - 1]} {valor.year}"
        return "—" if valor is None else str(valor)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    app.json = ProveedorJSON(app)
    _registrar_filtros(app)

    # --- Blueprints --------------------------------------------------------
    from app.blueprints.analitica import bp as bp_analitica
    from app.blueprints.api import bp as bp_api
    from app.blueprints.auth import bp as bp_auth
    from app.blueprints.catalogo import bp as bp_catalogo
    from app.blueprints.operacion import bp as bp_operacion
    from app.blueprints.panel import bp as bp_panel
    from app.blueprints.publico import bp as bp_publico

    app.register_blueprint(bp_publico)
    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_catalogo)
    app.register_blueprint(bp_operacion)
    app.register_blueprint(bp_analitica)
    app.register_blueprint(bp_panel)
    app.register_blueprint(bp_api)

    @app.get("/health")
    def health():
        """Healthcheck del sistema web (lo usan Docker y el pipeline de despliegue)."""
        from app.db import escalar

        try:
            ok = escalar("SELECT 1") == 1
        except Exception:
            ok = False
        return {"service": "web", "status": "HEALTHY" if ok else "DEGRADED", "dependencies": {"postgres": ok}}, (200 if ok else 503)

    # --- Contexto de plantillas -------------------------------------------
    @app.context_processor
    def inyectar_navegacion():
        if "user_id" not in session:
            return {}

        from app.auditoria import ACCIONES  # noqa: F401  (útil en plantillas)

        rol = session.get("role", "")
        permitidas = set(VISTAS_POR_ROL.get(rol, []))
        avisos = 0
        try:
            from app.domain import alertas as motor_alertas

            avisos = motor_alertas.resumen_alertas()["total"]
        except Exception:
            avisos = 0

        nombre = session.get("user_name", "")
        return {
            "nav_sections": menu_para(rol),
            "allowed_views": sorted(permitidas),
            "current_role": rol,
            "role_label": session.get("role_label", rol),
            "user_name": nombre,
            "user_email": session.get("user_email", ""),
            "user_initials": "".join(w[0] for w in nombre.split()[:2]).upper() or "?",
            "nav_icons": ICONOS,
            "notifications": avisos,
            "ruta_inicial": ruta_inicial(rol),
            "role_accent": acento_para(rol),
        }

    # --- Manejo de errores ------------------------------------------------
    @app.errorhandler(404)
    def no_encontrado(_e):
        from flask import render_template

        return render_template("error.html", codigo=404,
                               mensaje="La página que buscas no existe."), 404

    @app.errorhandler(500)
    def error_interno(e):
        from flask import render_template

        return render_template("error.html", codigo=500,
                               mensaje=f"Error interno: {e}"), 500

    return app
