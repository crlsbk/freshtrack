"""
Generador de Documentación OpenAPI 3 / Swagger UI para Microservicios FreshTrack.

La especificación se construye a partir de las rutas reales registradas en Flask,
así que ningún endpoint queda sin documentar:

- Ruta, método HTTP, parámetros de ruta (con su tipo) y de consulta.
- Seguridad JWT (bearerAuth) y roles permitidos, leídos de @requiere_auth.
- Cuerpo de la petición con ejemplos JSON y XML (y referencia a su XSD).
- Respuestas exitosas y de error (400/401/403/404/409/429/500) en JSON y XML.

Expone:
- /api/v1/openapi.json
- /api/v1/docs   (Swagger UI, permite ejecutar peticiones reales)
"""

from __future__ import annotations

import re
from typing import Any, Callable

from flask import Flask, jsonify, render_template_string, request

from app.services.common.response import dict_a_xml

SWAGGER_UI_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>{{ title }} — OpenAPI / Swagger</title>
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
        presets: [SwaggerUIBundle.presets.apis],
        layout: "BaseLayout",
        deepLinking: true,
        persistAuthorization: true,
        displayRequestDuration: true
      });
    };
  </script>
</body>
</html>
"""

ERROR_SCHEMA = {
    "type": "object",
    "required": ["error", "mensaje", "status", "correlation_id"],
    "properties": {
        "error": {"type": "string", "example": "parametro_invalido"},
        "mensaje": {"type": "string", "example": "'id_sku' debe ser un número entero."},
        "status": {"type": "integer", "example": 400},
        "correlation_id": {"type": "string", "example": "3f2a9c1e0b7d4e6f8a1b2c3d4e5f6a7b"},
        "detalles": {"description": "Información adicional (campos faltantes, errores XSD, roles permitidos)."},
    },
    "xml": {"name": "error_response"},
}

_DESCRIPCION_ERRORES = {
    "400": ("Parámetros o cuerpo inválidos", "parametro_invalido", "'cantidad' debe ser mayor que cero."),
    "401": ("Token ausente, inválido, expirado o revocado", "token_invalido", "Token inválido, expirado o manipulado."),
    "403": ("El rol del usuario no tiene permiso", "acceso_denegado", "El rol 'auditor' no tiene permiso para esta operación."),
    "404": ("Registro inexistente", "no_encontrado", "El recurso solicitado no existe."),
    "409": ("Conflicto con una regla de negocio", "conflicto", "La operación viola una regla de negocio."),
    "415": ("Content-Type no soportado", "tipo_no_soportado", "Use application/json o application/xml."),
    "429": ("Límite de peticiones excedido (rate limit en Redis)", "limite_excedido", "Intente de nuevo en 42 segundos."),
    "500": ("Error interno controlado (sin exponer detalles)", "error_interno", "Ocurrió un error inesperado."),
}


def documentar(
    resumen: str | None = None,
    *,
    cuerpo: dict[str, Any] | None = None,
    raiz_xml: str = "request",
    contrato_xsd: str | None = None,
    consulta: list[tuple[str, str, str]] | None = None,
    respuesta: dict[str, Any] | None = None,
    raiz_respuesta: str = "response",
    errores: tuple[str, ...] = (),
    exito: str | None = None,
) -> Callable:
    """
    Adjunta metadatos OpenAPI a una vista. Debe ir debajo de @app.<método>(...).

    consulta: [(nombre, tipo, descripción)] con tipo 'integer'|'string'|'number'|'boolean'.
    """
    def decorador(fn: Callable) -> Callable:
        fn._openapi = {  # type: ignore[attr-defined]
            "resumen": resumen,
            "cuerpo": cuerpo,
            "raiz_xml": raiz_xml,
            "contrato_xsd": contrato_xsd,
            "consulta": consulta or [],
            "respuesta": respuesta,
            "raiz_respuesta": raiz_respuesta,
            "errores": errores,
            "exito": exito,
        }
        return fn

    return decorador


def _meta(fn: Callable) -> dict[str, Any]:
    actual = fn
    while actual is not None:
        if hasattr(actual, "_openapi"):
            return actual._openapi
        actual = getattr(actual, "__wrapped__", None)
    return {}


def _ejemplo_error(codigo: str) -> dict[str, Any]:
    _, err, msg = _DESCRIPCION_ERRORES[codigo]
    return {"error": err, "mensaje": msg, "status": int(codigo), "correlation_id": "3f2a9c1e0b7d4e6f8a1b2c3d4e5f6a7b"}


def _contenido(ejemplo: Any, raiz: str, esquema: dict | None = None) -> dict[str, Any]:
    esquema = esquema or {"type": "object"}
    contenido: dict[str, Any] = {"application/json": {"schema": esquema}}
    xml_schema = dict(esquema)
    xml_schema.setdefault("xml", {"name": raiz})
    contenido["application/xml"] = {"schema": xml_schema}
    if ejemplo is not None:
        contenido["application/json"]["example"] = ejemplo
        contenido["application/xml"]["example"] = dict_a_xml(ejemplo, root_tag=raiz)
    return contenido


def _parametros_ruta(regla: str) -> tuple[str, list[dict[str, Any]]]:
    params = []
    tipos = {"int": "integer", "float": "number", "uuid": "string", "string": "string", "path": "string"}

    def sustituir(m: re.Match) -> str:
        conv, nombre = (m.group(1) or "string"), m.group(2)
        params.append({
            "name": nombre,
            "in": "path",
            "required": True,
            "schema": {"type": tipos.get(conv, "string")},
        })
        return "{" + nombre + "}"

    ruta = re.sub(r"<(?:(\w+):)?(\w+)>", sustituir, regla)
    return ruta, params


def construir_spec(app: Flask, titulo: str, descripcion: str, version: str) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for regla in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if regla.endpoint in ("static", "openapi_json", "swagger_ui"):
            continue
        vista = app.view_functions[regla.endpoint]
        meta = _meta(vista)
        ruta, params_ruta = _parametros_ruta(regla.rule)
        doc = (vista.__doc__ or "").strip()
        resumen = meta.get("resumen") or (doc.splitlines()[0] if doc else regla.endpoint)
        protegido = getattr(vista, "_requiere_auth", False)
        roles = getattr(vista, "_roles", ())
        limitado = getattr(vista, "_rate_limit", None)

        for metodo in sorted(regla.methods - {"HEAD", "OPTIONS"}):
            op: dict[str, Any] = {
                "summary": resumen,
                "description": doc,
                "operationId": f"{regla.endpoint}_{metodo.lower()}",
                "tags": [ruta.split("/")[3] if ruta.startswith("/api/v1/") else "infra"],
                "parameters": list(params_ruta),
                "responses": {},
            }
            for nombre, tipo, desc in meta.get("consulta", []):
                op["parameters"].append({"name": nombre, "in": "query", "required": False, "description": desc, "schema": {"type": tipo}})
            op["parameters"].append({
                "name": "X-Correlation-Id", "in": "header", "required": False,
                "description": "Identificador de trazabilidad; se devuelve en la respuesta.",
                "schema": {"type": "string"},
            })

            if protegido:
                op["security"] = [{"bearerAuth": []}]
                roles_txt = ", ".join(sorted(set(roles) | {"admin"})) if roles else "cualquier usuario autenticado"
                op["description"] = f"{doc}\n\n**Roles permitidos:** {roles_txt}".strip()

            if meta.get("cuerpo") is not None and metodo in ("POST", "PUT", "PATCH"):
                contenido = _contenido(meta["cuerpo"], meta.get("raiz_xml", "request"))
                if meta.get("contrato_xsd"):
                    contenido["application/xml"]["schema"]["description"] = (
                        f"Validado contra contracts/xsd/{meta['contrato_xsd']}.xsd "
                        f"(GET /api/v1/contracts/{meta['contrato_xsd']}.xsd)"
                    )
                op["requestBody"] = {"required": True, "content": contenido}

            exito = meta.get("exito") or ("201" if metodo == "POST" and meta.get("cuerpo") is not None else "200")
            op["responses"][exito] = {
                "description": "Operación exitosa",
                "content": _contenido(meta.get("respuesta"), meta.get("raiz_respuesta", "response")),
            }

            codigos = set(meta.get("errores", ()))
            codigos.add("500")
            if protegido:
                codigos.add("401")
            if roles:
                codigos.add("403")
            if params_ruta:
                codigos.add("404")
            if op.get("requestBody") or meta.get("consulta"):
                codigos.add("400")
            if limitado:
                codigos.add("429")
            for codigo in sorted(codigos):
                titulo_err = _DESCRIPCION_ERRORES[codigo][0]
                op["responses"][codigo] = {
                    "description": titulo_err,
                    "content": _contenido(_ejemplo_error(codigo), "error_response", {"$ref": "#/components/schemas/ErrorResponse"}),
                }
            paths.setdefault(ruta, {})[metodo.lower()] = op

    return {
        "openapi": "3.0.3",
        "info": {
            "title": titulo,
            "description": (
                f"{descripcion}\n\n"
                "Todas las respuestas pueden pedirse en JSON (por omisión) o XML con `Accept: application/xml`. "
                "Los cuerpos de petición se aceptan en JSON o XML (`Content-Type: application/xml`); "
                "los contratos XSD se publican en `/api/v1/contracts/{nombre}.xsd`.\n\n"
                "Para probar endpoints protegidos: obtén un token en svc-auth `POST /api/v1/auth/login` "
                "y pégalo en **Authorize**."
            ),
            "version": version,
            "contact": {"name": "FreshTrack — Equipo 05"},
        },
        "servers": [{"url": "/", "description": "Este microservicio"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Token emitido por svc-auth (pegar sin el prefijo 'Bearer').",
                }
            },
            "schemas": {"ErrorResponse": ERROR_SCHEMA},
        },
        "paths": paths,
    }


def registrar_openapi(app: Flask, titulo: str, descripcion: str, version: str = "1.0.0", **_ignorado: Any) -> None:
    """Registra /api/v1/openapi.json y /api/v1/docs. La spec se genera al primer acceso."""
    cache: dict[str, Any] = {}

    @app.get("/api/v1/openapi.json", endpoint="openapi_json")
    def openapi_json():
        if "spec" not in cache:
            cache["spec"] = construir_spec(app, titulo, descripcion, version)
        return jsonify(cache["spec"])

    @app.get("/api/v1/docs", endpoint="swagger_ui")
    def swagger_ui():
        return render_template_string(SWAGGER_UI_HTML, title=titulo, spec_url=request.script_root + "/api/v1/openapi.json")
