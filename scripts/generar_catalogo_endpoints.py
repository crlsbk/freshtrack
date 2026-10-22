#!/usr/bin/env python3
"""
Genera docs/ENDPOINTS_MICROSERVICIOS.md a partir de la especificación OpenAPI que
expone cada microservicio, para que el catálogo de endpoints nunca se desfase del código.

No necesita bases de datos: solo importa las aplicaciones Flask y lee /api/v1/openapi.json.

    python scripts/generar_catalogo_endpoints.py
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("SECRET_KEY", "solo-para-generar-documentacion-0000000000")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@127.0.0.1:1/x")

SERVICIOS = [("auth", 5001), ("catalog", 5002), ("inventory", 5003), ("commercial", 5004),
             ("asn", 5005), ("planning", 5006), ("alerts", 5007), ("audit", 5008)]


def main() -> None:
    lineas = [
        "# Catálogo de endpoints — Microservicios FreshTrack",
        "",
        "Generado automáticamente desde `/api/v1/openapi.json` de cada servicio con",
        "`python scripts/generar_catalogo_endpoints.py`. Todos los endpoints aceptan",
        "`Accept: application/xml` para responder en XML; los que reciben cuerpo aceptan",
        "`Content-Type: application/json` o `application/xml`.",
        "",
    ]
    total = 0
    for nombre, puerto in SERVICIOS:
        modulo = importlib.import_module(f"app.services.{nombre}_service.app")
        spec = modulo.app.test_client().get("/api/v1/openapi.json").get_json()
        lineas += [f"## svc-{nombre} — puerto {puerto}", "", f"_{spec['info']['title']}_", "",
                   f"Swagger UI: `http://localhost:{puerto}/api/v1/docs`", "",
                   "| Método | Ruta | Descripción | Seguridad / roles | Cuerpo | Códigos |",
                   "|---|---|---|---|---|---|"]
        for ruta, ops in spec["paths"].items():
            for metodo, op in ops.items():
                total += 1
                desc = op.get("description", "")
                roles = desc.split("**Roles permitidos:**")[1].strip() if "**Roles permitidos:**" in desc else ""
                seguridad = f"JWT · {roles}" if op.get("security") else "Pública"
                cuerpo = ""
                if "requestBody" in op:
                    xsd = op["requestBody"]["content"]["application/xml"]["schema"].get("description", "")
                    cuerpo = "JSON/XML" + (" + XSD" if "xsd" in xsd.lower() else "")
                codigos = ", ".join(sorted(op["responses"]))
                lineas.append(f"| `{metodo.upper()}` | `{ruta}` | {op['summary']} | {seguridad} | {cuerpo} | {codigos} |")
        lineas.append("")
        # Ejemplos de cuerpo
        ejemplos = [(r, m, o) for r, ops in spec["paths"].items() for m, o in ops.items() if "requestBody" in o]
        for ruta, metodo, op in ejemplos:
            contenido = op["requestBody"]["content"]
            lineas += [f"<details><summary><code>{metodo.upper()} {ruta}</code> — ejemplo de cuerpo</summary>", "",
                       "```json", json.dumps(contenido["application/json"]["example"], ensure_ascii=False, indent=2), "```", "",
                       "```xml", contenido["application/xml"]["example"], "```", "", "</details>", ""]
    lineas.insert(7, f"**{total} operaciones** en 8 servicios.\n")
    salida = RAIZ / "docs" / "ENDPOINTS_MICROSERVICIOS.md"
    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"{total} operaciones → {salida}")


if __name__ == "__main__":
    main()
