"""Protección CSRF de la web (app/csrf.py)."""

from __future__ import annotations

import re

import pytest
from flask import Flask, render_template_string

from app import csrf


@pytest.fixture()
def app_csrf(redis_falso):
    app = Flask(__name__)
    app.secret_key = "k" * 40
    csrf.iniciar(app)

    @app.get("/form")
    def form():
        return render_template_string(
            "<html><head></head><body>"
            "<form method='post' action='/accion'><input name='x'></form>"
            "<form method=\"POST\" action=\"/accion\"></form>"
            "<form method='get' action='/buscar'></form>"
            "</body></html>"
        )

    @app.post("/accion")
    def accion():
        return {"ok": True}

    return app


def _token(client):
    html = client.get("/form").get_data(as_text=True)
    return html, re.findall(r'name="csrf_token" value="([^"]+)"', html)


def test_inyecta_token_en_cada_form_post_y_meta(app_csrf):
    c = app_csrf.test_client()
    html, tokens = _token(c)
    assert len(tokens) == 2 and len(set(tokens)) == 1  # los 2 POST, no el GET
    assert f'<meta name="csrf-token" content="{tokens[0]}">' in html


def test_post_sin_token_o_con_token_ajeno_400(app_csrf):
    c = app_csrf.test_client()
    _token(c)
    assert c.post("/accion", data={"x": "1"}).status_code == 400
    assert c.post("/accion", data={"x": "1", "csrf_token": "otro"}).status_code == 400


def test_post_con_token_en_campo_o_cabecera_pasa(app_csrf):
    c = app_csrf.test_client()
    _, tokens = _token(c)
    assert c.post("/accion", data={"csrf_token": tokens[0]}).status_code == 200
    assert c.post("/accion", json={}, headers={"X-CSRF-Token": tokens[0]}).status_code == 200


def test_clientes_bearer_exentos(app_csrf):
    # Escritorio / móvil / API: no usan la cookie y un sitio ajeno no puede fijar Authorization.
    assert app_csrf.test_client().post("/accion", headers={"Authorization": "Bearer t"}).status_code == 200


def test_token_de_otra_sesion_no_sirve(app_csrf):
    _, tokens_a = _token(app_csrf.test_client())
    b = app_csrf.test_client()
    _token(b)
    assert b.post("/accion", data={"csrf_token": tokens_a[0]}).status_code == 400


def test_logout_por_get_desde_otro_sitio_no_cierra_sesion(redis_falso, monkeypatch):
    monkeypatch.setenv("AGREGADOS_AUTO_REFRESCO", "false")
    from app import create_app
    from app.blueprints import auth as auth_bp

    cerradas = []
    monkeypatch.setattr(auth_bp, "cerrar_sesion_web", lambda: cerradas.append(1))
    monkeypatch.setattr(auth_bp.clientes, "activo", lambda: False)
    c = create_app().test_client()
    c.get("/logout", headers={"Referer": "https://otro-sitio.example/"})
    assert cerradas == []
    c.get("/logout", headers={"Referer": "http://localhost/panel"})
    assert cerradas == [1]
