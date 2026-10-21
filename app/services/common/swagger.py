"""
Generador de Documentación OpenAPI / Swagger UI para Microservicios FreshTrack.

Proporciona especificación OpenAPI 3.0 y UI interactiva Swagger en:
- /api/v1/openapi.json
- /api/v1/docs
"""

from __future__ import annotations

from typing import Any
from flask import Flask, jsonify, render_template_string


SWAGGER_UI_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>{{ title }} — Documentación OpenAPI / Swagger</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css" />
  <style>
    body { margin: 0; background: #fafafa; font-family: sans-serif; }
    .topbar { display: none; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: "{{ spec_url }}",
        dom_id: '#swagger-ui',
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIBundle.SwaggerUIStandalonePreset
        ],
        layout: "BaseLayout",
        deepLinking: true
      });
    };
  </script>
</body>
</html>
"""


def registrar_openapi(
    app: Flask,
    titulo: str,
    descripcion: str,
    version: str,
    paths: dict[str, Any],
    schemas: dict[str, Any] | None = None,
) -> None:
    """Registra los endpoints /api/v1/openapi.json y /api/v1/docs en la aplicación Flask."""
    
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": titulo,
            "description": descripcion,
            "version": version,
            "contact": {"name": "FreshTrack Engineering", "email": "dev@freshtrack.mx"},
        },
        "servers": [{"url": "/", "description": "Servidor Local / Contenedor"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Ingrese su token JWT (sin el prefijo 'Bearer')",
                }
            },
            "schemas": schemas or {},
        },
        "paths": paths,
    }

    @app.get("/api/v1/openapi.json")
    def openapi_json():
        return jsonify(spec)

    @app.get("/api/v1/docs")
    def swagger_ui():
        return render_template_string(
            SWAGGER_UI_HTML,
            title=titulo,
            spec_url="/api/v1/openapi.json",
        )
