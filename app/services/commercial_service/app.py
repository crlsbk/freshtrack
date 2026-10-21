"""
Microservicio 4: Commercial, POS & Shrinkage Service (`svc-commercial`) — FreshTrack (Flask).

Puerto: 5004
Responsabilidad:
- Punto de Venta (POS) y orquestación de la Saga Venta-Inventario.
- Registro auditado de mermas operativas (7 causas) en PostgreSQL ('operacion.merma').
- Soporte dual JSON y XML (comprobantes de venta y reportes de merma).
- Trazabilidad y emisión de eventos de negocio a Redis Streams.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import Flask, g, request

from app.config import Config
from app.db import a_float, a_int, one, query
from app.domain import mermas as dom_mermas
from app.domain import saga_venta
from app.events.dispatcher import publicar_evento
from app.services import cache_service
from app.services.common.auth import requiere_auth
from app.services.common.response import render_response
from app.services.common.swagger import registrar_openapi

app = Flask(__name__)
app.config.from_object(Config)


@app.get("/health")
def health():
    pg_ok = False
    try:
        res = one("SELECT 1 AS ok")
        pg_ok = bool(res and res["ok"] == 1)
    except Exception:
        pass

    redis_ok = False
    try:
        r = cache_service.get_redis_client()
        redis_ok = bool(r and r.ping())
    except Exception:
        pass

    estado = "HEALTHY" if (pg_ok and redis_ok) else "DEGRADED"
    return render_response({
        "service": "svc-commercial",
        "status": estado,
        "dependencies": {"postgres": pg_ok, "redis": redis_ok},
    }, status=200 if estado == "HEALTHY" else 503, root_tag="service_health")


@app.post("/api/v1/commercial/checkout")
@requiere_auth("admin", "store_manager", "warehouse")
def checkout_saga():
    """Ejecuta la venta transaccional POS mediante la Saga Orquestada con soporte JSON/XML."""
    datos = request.get_json(silent=True) or request.form
    ctx = g.contexto
    id_locacion = a_int(ctx.get("location_id") or datos.get("id_locacion"), 0)
    lineas = datos.get("lineas", [])

    usuario = {
        "id_usuario": ctx.get("user_id") or str(g.usuario_actual.get("sub")),
        "email": ctx.get("user_email") or g.usuario_actual.get("email"),
        "rol_clave": ctx.get("user_role") or g.usuario_actual.get("rol"),
    }

    try:
        resultado = saga_venta.ejecutar_saga_venta(
            id_locacion=id_locacion,
            lineas=lineas,
            usuario=usuario,
            canal=datos.get("canal", "TIENDA"),
        )
        return render_response(resultado, status=201, root_tag="comprobante_venta")
    except saga_venta.ErrorSagaVenta as err:
        return render_response({"error": "venta_rechazada", "mensaje": str(err)}, status=400, root_tag="error_venta")
    except Exception as exc:
        return render_response({"error": "internal_error", "detalle": str(exc)}, status=500, root_tag="error_venta")


@app.post("/api/v1/commercial/shrinkage")
@requiere_auth("admin", "store_manager", "warehouse")
def registrar_merma():
    """Registra una merma justificada en PostgreSQL vinculada al lote y existencia."""
    datos = request.get_json(silent=True) or request.form
    ctx = g.contexto
    id_locacion = a_int(ctx.get("location_id") or datos.get("id_locacion"), 0)

    usuario = {
        "id_usuario": ctx.get("user_id") or str(g.usuario_actual.get("sub")),
        "email": ctx.get("user_email") or g.usuario_actual.get("email"),
        "rol_clave": ctx.get("user_role") or g.usuario_actual.get("rol"),
    }

    try:
        res = dom_mermas.registrar_merma(
            id_lote=datos.get("id_lote"),
            id_locacion=id_locacion,
            cantidad=float(datos.get("cantidad")),
            causa=datos.get("causa"),
            observacion=datos.get("observacion"),
            usuario=usuario,
        )
        return render_response(res, status=201, root_tag="merma_registrada")
    except Exception as exc:
        return render_response({"error": "error_merma", "detalle": str(exc)}, status=400, root_tag="error_merma")


@app.get("/api/v1/commercial/sales")
@requiere_auth()
def historial_ventas():
    """Consulta de transacciones de venta con soporte JSON y XML."""
    ctx = g.contexto
    id_locacion = a_int(ctx.get("location_id") or request.args.get("id_locacion"), 0) or None
    limite = a_int(request.args.get("limite"), 20)

    filtro = "WHERE v.id_locacion = :loc" if id_locacion else ""
    params = {"loc": id_locacion, "lim": limite} if id_locacion else {"lim": limite}

    sql = f"""
        SELECT v.id_venta::text AS id_venta,
               v.folio,
               v.id_locacion,
               loc.nombre AS locacion,
               v.canal,
               v.total,
               v.fecha_venta
        FROM operacion.venta v
        JOIN operacion.locacion loc ON loc.id_locacion = v.id_locacion
        {filtro}
        ORDER BY v.fecha_venta DESC
        LIMIT :lim
    """
    ventas = query(sql, **params)
    items = []
    for v in ventas:
        d = dict(v)
        d["total"] = a_float(d["total"])
        items.append(d)

    return render_response({"total": len(items), "ventas": items}, status=200, root_tag="historial_ventas")


registrar_openapi(
    app,
    titulo="Commercial, POS & Shrinkage Service (FreshTrack)",
    descripcion="Microservicio para cobro POS orquestado con Sagas, registro de mermas e historial de ventas.",
    version="1.0.0",
    paths={
        "/health": {"get": {"summary": "Healthcheck del microservicio", "responses": {"200": {"description": "Estado saludable"}}}},
        "/api/v1/commercial/checkout": {"post": {"summary": "Checkout POS con Saga Orquestada y FEFO", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Venta procesada exitosamente"}}}},
        "/api/v1/commercial/shrinkage": {"post": {"summary": "Registro justificado de mermas (7 causas)", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Merma registrada"}}}},
        "/api/v1/commercial/sales": {"get": {"summary": "Historial de ventas (JSON / XML)", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Lista de ventas"}}}},
    },
)

if __name__ == "__main__":
    port = int(os.getenv("COMMERCIAL_SERVICE_PORT", "5004"))
    app.run(host="0.0.0.0", port=port, debug=False)
