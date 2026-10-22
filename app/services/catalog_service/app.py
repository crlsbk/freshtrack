"""
Microservicio 2: Master Catalog & Locations Service (`svc-catalog`) — FreshTrack (Flask).

Puerto: 5002
Responsabilidad:
- Catálogo maestro de productos perecederos, reglas de riesgo, categorías y proveedores.
- Gestión de tiendas y CEDIS con contexto de red de distribución.
- Patrón Cache-Aside en Redis para consultas de ultra-baja latencia (< 1 ms).
- Soporte dual JSON y XML (estándar GS1 XML B2B).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import Flask, request
from sqlalchemy import text

from app.config import Config
from app.db import a_float, a_int, one, query, transaccion
from app.events.dispatcher import publicar_evento
from app.services import cache_service
from app.services.common.auth import requiere_auth
from app.services.common.rate_limit import limite_tasa
from app.services.common.response import render_response
from app.services.common.swagger import registrar_openapi

app = Flask(__name__)
app.config.from_object(Config)

CACHE_KEY_PRODUCTS = "catalog:products:all"
CACHE_KEY_LOCATIONS = "catalog:locations:all"


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
        "service": "svc-catalog",
        "status": estado,
        "dependencies": {"postgres": pg_ok, "redis": redis_ok},
    }, status=200 if estado == "HEALTHY" else 503, root_tag="service_health")


@app.get("/api/v1/catalog/products")
@limite_tasa(limite=120, ventana_segundos=60)
def listar_productos():
    """Consulta de productos perecederos con estrategia Cache-Aside en Redis."""
    categoria = request.args.get("categoria")
    
    # Si no hay filtros específicos, intentar servir desde memoria Redis
    if not categoria:
        cached = cache_service.get_json(CACHE_KEY_PRODUCTS)
        if cached:
            cache_service.incrementar_contador("catalog", "products_cache_hit")
            return render_response({"total": len(cached), "productos": cached, "fuente": "redis_cache"}, status=200, root_tag="catalogo_productos")

    cache_service.incrementar_contador("catalog", "products_db_miss")

    filtro = "WHERE p.categoria = :cat" if categoria else ""
    params = {"cat": categoria} if categoria else {}
    sql = f"""
        SELECT p.id_sku, p.codigo_gtin, p.nombre, p.categoria, p.unidad_medida,
               p.vida_util_estandar, p.precio_costo, p.precio_venta, p.activo
        FROM operacion.producto p
        {filtro}
        ORDER BY p.nombre ASC
    """
    filas = query(sql, **params)
    productos = []
    for f in filas:
        d = dict(f)
        d["precio_venta"] = a_float(d["precio_venta"])
        d["precio_costo"] = a_float(d["precio_costo"])
        productos.append(d)

    if not categoria:
        cache_service.set_json(CACHE_KEY_PRODUCTS, productos, ttl_segundos=300)

    return render_response({"total": len(productos), "productos": productos, "fuente": "postgres_live"}, status=200, root_tag="catalogo_productos")


@app.get("/api/v1/catalog/products/<int:id_sku>")
def detalle_producto(id_sku: int):
    """Consulta individual de un SKU."""
    sql = """
        SELECT p.id_sku, p.codigo_gtin, p.nombre, p.categoria, p.unidad_medida,
               p.vida_util_estandar, p.precio_costo, p.precio_venta, p.activo
        FROM operacion.producto p
        WHERE p.id_sku = :s
    """
    prod = one(sql, s=id_sku)
    if not prod:
        return render_response({"error": "not_found", "mensaje": f"SKU {id_sku} no encontrado."}, status=404, root_tag="producto_detalle")
    
    d = dict(prod)
    d["precio_venta"] = a_float(d["precio_venta"])
    d["precio_costo"] = a_float(d["precio_costo"])
    return render_response(d, status=200, root_tag="producto_detalle")


@app.post("/api/v1/catalog/products")
@requiere_auth("admin", "buyer")
def crear_producto():
    """Alta de nuevo producto perecedero con invalidación de caché en Redis."""
    datos = request.get_json(silent=True) or request.form
    nombre = datos.get("nombre")
    categoria = datos.get("categoria")
    precio = a_float(datos.get("precio_venta"))
    costo = a_float(datos.get("precio_costo") or datos.get("costo_estandar"))
    vida_util = a_int(datos.get("vida_util_estandar") or datos.get("vida_util_dias"), 7)

    if not nombre or not categoria or precio <= 0:
        return render_response({"error": "bad_request", "mensaje": "Nombre, categoría y precio son obligatorios."}, status=400, root_tag="producto_creado")

    with transaccion() as conn:
        res = conn.execute(
            text(
                """
                INSERT INTO operacion.producto
                    (codigo_gtin, nombre, categoria, unidad_medida, vida_util_estandar,
                     precio_venta, precio_costo)
                VALUES (:cod, :nom, :cat, :uni, :vu, :p, :c)
                RETURNING id_sku
                """
            ),
            {
                "cod": datos.get("codigo_gtin") or f"GTIN-{nombre[:3].upper()}",
                "nom": nombre,
                "cat": categoria,
                "uni": datos.get("unidad_medida", "Pieza"),
                "vu": vida_util,
                "p": precio,
                "c": costo,
            },
        ).scalar()

    # Invalidar caché en Redis por patrón y emitir evento
    cache_service.invalidar_patron("catalog:products:*")
    cache_service.incrementar_contador("catalog", "product_created")
    publicar_evento("PRODUCTO_CREADO", {"id_sku": res, "nombre": nombre, "categoria": categoria})

    return render_response({"id_sku": res, "nombre": nombre, "status": "CREADO"}, status=201, root_tag="producto_creado")


@app.delete("/api/v1/catalog/products/<int:id_sku>")
@requiere_auth("admin")
def desactivar_producto(id_sku: int):
    """Baja lógica de producto e invalidación de caché."""
    with transaccion() as conn:
        conn.execute(
            text("UPDATE operacion.producto SET activo = false WHERE id_sku = :s"),
            {"s": id_sku},
        )
    cache_service.invalidar_patron("catalog:products:*")
    cache_service.incrementar_contador("catalog", "product_deactivated")
    publicar_evento("PRODUCTO_DESACTIVADO", {"id_sku": id_sku})
    return render_response({"id_sku": id_sku, "activo": False}, status=200, root_tag="producto_baja")


@app.get("/api/v1/catalog/locations")
def listar_locaciones():
    """Consulta de tiendas y CEDIS con Cache-Aside."""
    cached = cache_service.get_json(CACHE_KEY_LOCATIONS)
    if cached:
        return render_response({"total": len(cached), "locaciones": cached, "fuente": "redis_cache"}, status=200, root_tag="catalogo_locaciones")

    filas = query(
        """
        SELECT id_locacion, tipo_locacion, nombre, ciudad, direccion, activo
        FROM operacion.locacion
        ORDER BY id_locacion ASC
        """
    )
    locs = [dict(f) for f in filas]
    cache_service.set_json(CACHE_KEY_LOCATIONS, locs, ttl_segundos=600)
    return render_response({"total": len(locs), "locaciones": locs, "fuente": "postgres_live"}, status=200, root_tag="catalogo_locaciones")


@app.get("/api/v1/catalog/suppliers")
@requiere_auth("admin", "buyer", "planner")
def listar_proveedores():
    """Consulta de proveedores con lead time y MOQ."""
    filas = query(
        """
        SELECT id_proveedor, rfc, razon_social, lead_time_dias, moq,
               contacto_email, telefono, activo
        FROM operacion.proveedor
        ORDER BY razon_social ASC
        """
    )
    provs = [dict(f) for f in filas]
    return render_response({"total": len(provs), "proveedores": provs}, status=200, root_tag="catalogo_proveedores")


registrar_openapi(
    app,
    titulo="Master Catalog & Locations Service (FreshTrack)",
    descripcion="Microservicio para gestión de productos perecederos, reglas de riesgo, proveedores y tiendas con Cache-Aside en Redis.",
    version="1.0.0",
    paths={
        "/health": {"get": {"summary": "Healthcheck del microservicio", "responses": {"200": {"description": "Estado saludable"}}}},
        "/api/v1/catalog/products": {
            "get": {"summary": "Listado de productos (con Cache-Aside y soporte XML/JSON)", "responses": {"200": {"description": "Lista de productos"}}},
            "post": {"summary": "Creación de nuevo producto perecedero", "security": [{"bearerAuth": []}], "responses": {"201": {"description": "Producto creado"}}},
        },
        "/api/v1/catalog/products/{id_sku}": {
            "get": {"summary": "Detalle de un producto por SKU", "responses": {"200": {"description": "Detalle del producto"}}},
            "delete": {"summary": "Baja lógica de producto", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Producto desactivado"}}},
        },
        "/api/v1/catalog/locations": {"get": {"summary": "Lista de tiendas y centros de distribución", "responses": {"200": {"description": "Lista de locaciones"}}}},
        "/api/v1/catalog/suppliers": {"get": {"summary": "Lista de proveedores con Lead Time y MOQ", "security": [{"bearerAuth": []}], "responses": {"200": {"description": "Lista de proveedores"}}}},
    },
)

if __name__ == "__main__":
    port = int(os.getenv("CATALOG_SERVICE_PORT", "5002"))
    app.run(host="0.0.0.0", port=port, debug=False)
