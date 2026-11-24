"""
Protección CSRF para la web (formularios y fetch con cookie de sesión).

Patrón «synchronizer token»:
  * Cada sesión tiene un token aleatorio (session["csrf_token"]).
  * Toda respuesta HTML recibe el token inyectado como <input type="hidden">
    en cada <form method="post">, y como <meta name="csrf-token"> para fetch().
    Así ningún formulario de las ~20 plantillas puede quedarse sin él.
  * Toda petición POST/PUT/PATCH/DELETE que se autentica con la COOKIE debe
    traerlo (campo `csrf_token` o cabecera `X-CSRF-Token`); si no, 400.

Exentas: peticiones con `Authorization: Bearer …` (escritorio, móvil, API).
Un sitio ajeno no puede añadir esa cabecera a una petición del navegador sin
pasar por CORS, y esas peticiones no usan la cookie. Complementa a
SESSION_COOKIE_SAMESITE=Lax, que ya bloquea el POST entre sitios en
navegadores modernos pero no en subdominios ni en navegadores antiguos.
"""

from __future__ import annotations

import hmac
import re
import secrets

from flask import Flask, abort, request, session
from markupsafe import escape

CAMPO = "csrf_token"
CABECERA = "X-CSRF-Token"
_METODOS_PROTEGIDOS = {"POST", "PUT", "PATCH", "DELETE"}
_RE_FORM_POST = re.compile(r"(<form\b[^>]*\bmethod\s*=\s*[\"']?post[\"']?[^>]*>)", re.IGNORECASE)


def token() -> str:
    """Token de la sesión actual (se crea la primera vez)."""
    valor = session.get(CAMPO)
    if not valor:
        valor = secrets.token_urlsafe(32)
        session[CAMPO] = valor
    return valor


def _token_recibido() -> str:
    return request.form.get(CAMPO) or request.headers.get(CABECERA) or ""


def _exenta() -> bool:
    if request.method not in _METODOS_PROTEGIDOS:
        return True
    if request.headers.get("Authorization", "").startswith("Bearer "):
        return True
    return False


def _verificar() -> None:
    if _exenta():
        return
    esperado = session.get(CAMPO)
    recibido = _token_recibido()
    if not esperado or not recibido or not hmac.compare_digest(str(esperado), str(recibido)):
        from app.services.cache_service import incrementar_contador

        incrementar_contador("web", "csrf_rechazado")
        abort(400, description="csrf")


def _inyectar(resp):
    if resp.direct_passthrough or resp.mimetype != "text/html" or resp.status_code >= 300:
        return resp
    html = resp.get_data(as_text=True)
    if "<form" not in html.lower() and "</head>" not in html.lower():
        return resp
    valor = str(escape(token()))
    campo = f'<input type="hidden" name="{CAMPO}" value="{valor}">'
    html = _RE_FORM_POST.sub(lambda m: m.group(1) + campo, html)
    html = html.replace("</head>", f'<meta name="csrf-token" content="{valor}">\n</head>', 1)
    resp.set_data(html)
    return resp


def iniciar(app: Flask) -> None:
    app.config.setdefault("CSRF_ACTIVO", True)

    @app.before_request
    def _csrf_antes():
        if app.config.get("CSRF_ACTIVO"):
            _verificar()

    @app.after_request
    def _csrf_despues(resp):
        if app.config.get("CSRF_ACTIVO"):
            return _inyectar(resp)
        return resp

    @app.errorhandler(400)
    def _csrf_error(e):
        if getattr(e, "description", "") != "csrf":
            return e
        from flask import flash, redirect, render_template

        if request.path.startswith(("/api/", "/svc/")) or request.accept_mimetypes.best == "application/json":
            return {"error": "csrf_invalido", "mensaje": "Falta o no coincide el token CSRF. Recarga la página."}, 400
        destino = request.referrer if request.referrer and request.referrer.startswith(request.host_url) else None
        if destino:
            flash("El formulario expiró o no es válido. Vuelve a intentarlo.", "error")
            return redirect(destino)
        mensaje = "El formulario expiró o no es válido. Recarga la página e intenta de nuevo."
        try:
            return render_template("error.html", codigo=400, mensaje=mensaje), 400
        except Exception:  # noqa: BLE001 — app sin plantilla de error
            return mensaje, 400
