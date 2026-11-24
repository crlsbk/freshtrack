"""
Blueprint del panel oculto de monitoreo operacional (/ops/status).

No está enlazado en ninguna barra de navegación ni página pública. Requiere
credenciales dedicadas (MONITOR_USER / MONITOR_PASSWORD) independientes del
login de negocio.
"""

from __future__ import annotations

import hmac
import os
import threading
import time

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.config import Config
from app.domain import monitoreo as dom_monitoreo
from app.services import cache_service

bp = Blueprint("monitoreo", __name__, url_prefix="/ops/status")

_INTENTOS_FALLIDOS: dict[str, list[float]] = {}
_INTENTOS_LOCK = threading.Lock()
_LIMITE_INTENTOS = 10
_VENTANA_SEGUNDOS = 300


def _credenciales_configuradas() -> tuple[str, str]:
    user = os.getenv("MONITOR_USER", Config.MONITOR_USER).strip() or "ops_monitor"
    password = os.getenv("MONITOR_PASSWORD", Config.MONITOR_PASSWORD)
    return user, password


def _credenciales_validas(usuario: str, clave: str) -> bool:
    cfg_user, cfg_pass = _credenciales_configuradas()
    if not usuario or not clave or not cfg_pass:
        return False
    user_ok = hmac.compare_digest(usuario.encode("utf-8"), cfg_user.encode("utf-8"))
    pass_ok = hmac.compare_digest(clave.encode("utf-8"), cfg_pass.encode("utf-8"))
    return bool(user_ok and pass_ok)


def _esta_autenticado() -> bool:
    if session.get("ops_monitor_auth") is True and session.get("ops_monitor_user"):
        return True
    auth = request.authorization
    if auth and auth.username is not None and auth.password is not None:
        return _credenciales_validas(auth.username, auth.password)
    return False


def _permitido_intento(ip: str) -> bool:
    if cache_service.get_redis_client() is not None:
        ok, _, _ = cache_service.verificar_rate_limit(
            f"ops_monitor_login:{ip}", limite=_LIMITE_INTENTOS, ventana_segundos=_VENTANA_SEGUNDOS
        )
        return ok
    ahora = time.monotonic()
    with _INTENTOS_LOCK:
        previos = [t for t in _INTENTOS_FALLIDOS.get(ip, []) if ahora - t < _VENTANA_SEGUNDOS]
        previos.append(ahora)
        _INTENTOS_FALLIDOS[ip] = previos
        return len(previos) <= _LIMITE_INTENTOS


@bp.after_request
def _cabeceras_privadas(resp):
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("ops_monitor_auth") is True:
        return redirect(url_for("monitoreo.panel"))

    error = None
    usuario = ""
    if request.method == "POST":
        usuario = (request.form.get("username") or "").strip()
        clave = request.form.get("password") or ""
        ip = request.remote_addr or "desconocida"
        if not _permitido_intento(ip):
            error = "Demasiados intentos recientes. Espera unos minutos e intenta de nuevo."
        elif _credenciales_validas(usuario, clave):
            session["ops_monitor_auth"] = True
            session["ops_monitor_user"] = usuario
            return redirect(url_for("monitoreo.panel"))
        else:
            error = "Usuario o contraseña incorrectos."

    return render_template("monitoreo/login.html", error=error, username=usuario)


@bp.post("/logout")
def logout():
    session.pop("ops_monitor_auth", None)
    session.pop("ops_monitor_user", None)
    return redirect(url_for("monitoreo.login"))


@bp.get("")
@bp.get("/")
def panel():
    if not _esta_autenticado():
        return redirect(url_for("monitoreo.login"))
    snapshot = dom_monitoreo.verificar_plataforma(guardar_historial=True)
    return render_template(
        "monitoreo/panel.html",
        snapshot=snapshot,
        monitor_user=session.get("ops_monitor_user") or _credenciales_configuradas()[0],
    )


@bp.get("/api/snapshot")
def api_snapshot():
    if not _esta_autenticado():
        return jsonify({"error": "no_autenticado", "mensaje": "Autenticación de monitoreo requerida."}), 401
    solo_lectura = request.args.get("solo_lectura", "0") == "1"
    snapshot = dom_monitoreo.verificar_plataforma(guardar_historial=not solo_lectura)
    return jsonify(snapshot)
