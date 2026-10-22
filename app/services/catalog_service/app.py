"""
Microservicio 2: Master Catalog & Locations Service (`svc-catalog`) — FreshTrack (Flask).

Puerto: 5002
Responsabilidad:
- Catálogo maestro de productos perecederos (alta, consulta, edición total/parcial, baja lógica).
- Tiendas y CEDIS de la red de distribución; proveedores con lead time y MOQ.
- Patrón Cache-Aside en Redis con invalidación por patrón al escribir.
- Soporte dual JSON y XML (entrada validada con XSD producto_request).
"""

from __future__ import annotations

import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from flask import request
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import a_float, one, query, transaccion
from app.events.dispatcher import publicar_evento
from app.services import cache_service
from app.services.common.auth import requiere_auth
from app.services.common.rate_limit import limite_tasa
from app.services.common.response import (
    ErrorApi,
    decimal_pos,
    entero,
    error_response,
    leer_cuerpo,
    meta_paginacion,
    paginacion,
    render_response,
    requerir_campos,
)
from app.services.common.servicio import crear_servicio, ejecutar
from app.services.common.swagger import documentar

app = crear_servicio(
    "svc-catalog",
    "Master Catalog & Locations Service (FreshTrack)",
    "Productos perecederos, proveedores, tiendas y CEDIS con Cache-Aside en Redis.",
    dependencias=("postgres", "redis"),
)

CACHE_PREFIX_PRODUCTS = "catalog:products:"
CACHE_KEY_LOCATIONS = "catalog:locations:all"
CAMPOS_PRODUCTO = """p.id_sku, p.codigo_gtin, p.nombre, p.categoria, p.unidad_medida,
                     p.vida_util_estandar, p.precio_costo, p.precio_venta, p.activo"""

_PRODUCTO_EJEMPLO = {
    "codigo_gtin": "7501234567890",
    "nombre": "Fresa orgánica 500 g",
    "categoria": "Frutas",
    "unidad_medida": "Pieza",
    "vida_util_estandar": 6,
    "precio_costo": 28.5,
    "precio_venta": 45.9,
}


def _producto(fila: dict) -> dict:
    d = dict(fila)
    d["precio_venta"] = a_float(d["precio_venta"])
    d["precio_costo"] = a_float(d["precio_costo"])
    d.pop("_total", None)
    return d


def _validar_producto(datos: dict, parcial: bool) -> dict:
    """Normaliza y valida los campos de un producto. En PATCH solo valida los presentes."""
    if not parcial:
        requerir_campos(datos, "nombre", "categoria", "precio_venta", "precio_costo")
    limpio: dict = {}
    for campo, largo in (("codigo_gtin", 14), ("nombre", 150), ("categoria", 60), ("unidad_medida", 20)):
        if campo in datos and datos[campo] not in (None, ""):
            valor = str(datos[campo]).strip()
            if len(valor) > largo:
                raise ErrorApi(400, "parametro_invalido", f"'{campo}' admite como máximo {largo} caracteres.")
            limpio[campo] = valor
    if "vida_util_estandar" in datos or "vida_util_dias" in datos:
        limpio["vida_util_estandar"] = entero(
            {"vida_util_estandar": datos.get("vida_util_estandar", datos.get("vida_util_dias"))},
            "vida_util_estandar", minimo=1,
        )
    if "precio_venta" in datos:
        limpio["precio_venta"] = decimal_pos(datos, "precio_venta")
    if "precio_costo" in datos:
        limpio["precio_costo"] = decimal_pos(datos, "precio_costo")
    if "activo" in datos:
        v = datos["activo"]
        limpio["activo"] = v if isinstance(v, bool) else str(v).lower() in ("true", "1")
    if not limpio:
        raise ErrorApi(400, "cuerpo_vacio", "No se recibió ningún campo de producto para actualizar.")
    return limpio


def _validar_margen(venta: float | None, costo: float | None) -> None:
    if venta is not None and costo is not None and venta < costo:
        raise ErrorApi(409, "regla_negocio", "El precio de venta no puede ser menor que el costo.")


@app.get("/api/v1/catalog/products")
@documentar(
    "Listado paginado de productos (Cache-Aside en Redis)",
    consulta=[("categoria", "string", "Filtra por categoría"), ("q", "string", "Busca por nombre o GTIN"),
              ("activo", "boolean", "true/false"), ("pagina", "integer", "Página"), ("por_pagina", "integer", "Tamaño (máx. 100)")],
    raiz_respuesta="catalogo_productos",
)
@limite_tasa(limite=120, ventana_segundos=60)
def listar_productos():
    """Consulta pública del catálogo. Cada combinación de filtros se cachea 5 minutos en Redis."""
    pagina, por_pagina, offset = paginacion()
    categoria = request.args.get("categoria")
    q = request.args.get("q")
    activo = request.args.get("activo")

    firma = hashlib.sha1(f"{categoria}|{q}|{activo}|{pagina}|{por_pagina}".encode()).hexdigest()[:16]
    clave = f"{CACHE_PREFIX_PRODUCTS}{firma}"
    cached = cache_service.get_json(clave)
    if cached:
        cache_service.incrementar_contador("catalog", "products_cache_hit")
        cached["fuente"] = "redis_cache"
        cached["cache_ttl_segundos"] = cache_service.obtener_ttl(clave)
        return render_response(cached, status=200, root_tag="catalogo_productos")
    cache_service.incrementar_contador("catalog", "products_cache_miss")

    condiciones, params = [], {"lim": por_pagina, "off": offset}
    if categoria:
        condiciones.append("p.categoria = :cat")
        params["cat"] = categoria
    if q:
        condiciones.append("(p.nombre ILIKE :q OR p.codigo_gtin ILIKE :q)")
        params["q"] = f"%{q}%"
    if activo in ("true", "false"):
        condiciones.append("p.activo = :act")
        params["act"] = activo == "true"
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = query(
        f"""
        SELECT {CAMPOS_PRODUCTO}, COUNT(*) OVER () AS _total
        FROM operacion.producto p
        {where}
        ORDER BY p.nombre ASC
        LIMIT :lim OFFSET :off
        """,
        **params,
    )
    total = filas[0]["_total"] if filas else 0
    cuerpo = {"paginacion": meta_paginacion(pagina, por_pagina, total), "productos": [_producto(f) for f in filas]}
    cache_service.set_json(clave, cuerpo, ttl_segundos=300)
    cuerpo["fuente"] = "postgres"
    return render_response(cuerpo, status=200, root_tag="catalogo_productos")


@app.get("/api/v1/catalog/products/<int:id_sku>")
@documentar("Detalle de un producto por SKU", respuesta={"id_sku": 1, **_PRODUCTO_EJEMPLO, "activo": True}, raiz_respuesta="producto")
def detalle_producto(id_sku: int):
    """Consulta individual de un SKU."""
    prod = one(f"SELECT {CAMPOS_PRODUCTO} FROM operacion.producto p WHERE p.id_sku = :s", s=id_sku)
    if not prod:
        return error_response(404, "no_encontrado", f"SKU {id_sku} no encontrado.")
    return render_response(_producto(prod), status=200, root_tag="producto")


def _invalidar_y_publicar(evento: str, payload: dict) -> None:
    cache_service.invalidar_patron(f"{CACHE_PREFIX_PRODUCTS}*")
    cache_service.incrementar_contador("catalog", evento.lower())
    publicar_evento(evento, payload)


@app.post("/api/v1/catalog/products")
@documentar(
    "Alta de producto perecedero",
    cuerpo=_PRODUCTO_EJEMPLO,
    raiz_xml="producto_request",
    contrato_xsd="producto_request",
    respuesta={"id_sku": 101, "nombre": "Fresa orgánica 500 g", "status": "CREADO"},
    raiz_respuesta="producto_creado",
    errores=("400", "409", "415"),
)
@requiere_auth("buyer")
def crear_producto():
    """Crea un producto en PostgreSQL, invalida la caché de Redis y emite PRODUCTO_CREADO."""
    datos = _validar_producto(leer_cuerpo("producto_request", requerido=True), parcial=False)
    _validar_margen(datos["precio_venta"], datos["precio_costo"])
    datos.setdefault("unidad_medida", "Pieza")
    datos.setdefault("vida_util_estandar", 7)
    # GTIN interno (prefijo 2 = uso interno GS1) cuando el comprador no lo captura.
    datos.setdefault("codigo_gtin", f"2{time.time_ns() // 1_000_000 % 10**13:013d}")
    try:
        with transaccion() as conn:
            id_sku = conn.execute(
                text(
                    """
                    INSERT INTO operacion.producto
                        (codigo_gtin, nombre, categoria, unidad_medida, vida_util_estandar, precio_venta, precio_costo)
                    VALUES (:codigo_gtin, :nombre, :categoria, :unidad_medida, :vida_util_estandar, :precio_venta, :precio_costo)
                    RETURNING id_sku
                    """
                ),
                datos,
            ).scalar()
    except IntegrityError:
        return error_response(409, "duplicado", "Ya existe un producto con ese código GTIN o nombre.")

    _invalidar_y_publicar("PRODUCTO_CREADO", {"id_sku": id_sku, "nombre": datos["nombre"]})
    return render_response({"id_sku": id_sku, "nombre": datos["nombre"], "status": "CREADO"}, status=201, root_tag="producto_creado")


def _actualizar(id_sku: int, parcial: bool):
    actual = one("SELECT precio_venta, precio_costo FROM operacion.producto WHERE id_sku = :s", s=id_sku)
    if not actual:
        return error_response(404, "no_encontrado", f"SKU {id_sku} no encontrado.")
    datos = _validar_producto(leer_cuerpo("producto_request", requerido=True), parcial=parcial)
    _validar_margen(
        datos.get("precio_venta", a_float(actual["precio_venta"])),
        datos.get("precio_costo", a_float(actual["precio_costo"])),
    )
    asignaciones = ", ".join(f"{c} = :{c}" for c in datos)
    try:
        with transaccion() as conn:
            conn.execute(text(f"UPDATE operacion.producto SET {asignaciones} WHERE id_sku = :id_sku"), {**datos, "id_sku": id_sku})
    except IntegrityError:
        return error_response(409, "duplicado", "El código GTIN ya pertenece a otro producto.")
    _invalidar_y_publicar("PRODUCTO_ACTUALIZADO", {"id_sku": id_sku, "campos": sorted(datos)})
    prod = one(f"SELECT {CAMPOS_PRODUCTO} FROM operacion.producto p WHERE p.id_sku = :s", s=id_sku)
    return render_response(_producto(prod), status=200, root_tag="producto")


@app.put("/api/v1/catalog/products/<int:id_sku>")
@documentar(
    "Reemplazo completo de un producto",
    cuerpo=_PRODUCTO_EJEMPLO,
    raiz_xml="producto_request",
    contrato_xsd="producto_request",
    raiz_respuesta="producto",
    errores=("400", "409"),
    exito="200",
)
@requiere_auth("buyer")
def reemplazar_producto(id_sku: int):
    """PUT: exige todos los campos obligatorios del producto."""
    return _actualizar(id_sku, parcial=False)


@app.patch("/api/v1/catalog/products/<int:id_sku>")
@documentar(
    "Actualización parcial de un producto",
    cuerpo={"precio_venta": 39.9},
    raiz_xml="producto_request",
    contrato_xsd="producto_request",
    raiz_respuesta="producto",
    errores=("400", "409"),
    exito="200",
)
@requiere_auth("buyer")
def modificar_producto(id_sku: int):
    """PATCH: actualiza solo los campos enviados (precio, vida útil, estado...)."""
    return _actualizar(id_sku, parcial=True)


@app.delete("/api/v1/catalog/products/<int:id_sku>")
@documentar("Baja lógica de producto", respuesta={"id_sku": 1, "activo": False}, raiz_respuesta="producto_baja")
@requiere_auth("admin")
def desactivar_producto(id_sku: int):
    """Desactiva el producto (no se borra: conserva la trazabilidad de sus lotes)."""
    with transaccion() as conn:
        res = conn.execute(text("UPDATE operacion.producto SET activo = false WHERE id_sku = :s"), {"s": id_sku})
        if res.rowcount == 0:
            return error_response(404, "no_encontrado", f"SKU {id_sku} no encontrado.")
    _invalidar_y_publicar("PRODUCTO_DESACTIVADO", {"id_sku": id_sku})
    return render_response({"id_sku": id_sku, "activo": False}, status=200, root_tag="producto_baja")


@app.get("/api/v1/catalog/locations")
@documentar("Tiendas y CEDIS (Cache-Aside)", consulta=[("tipo", "string", "TIENDA o CEDIS")], raiz_respuesta="catalogo_locaciones")
def listar_locaciones():
    """Consulta de tiendas y CEDIS con caché de 10 minutos en Redis."""
    locs = cache_service.get_json(CACHE_KEY_LOCATIONS)
    fuente = "redis_cache"
    if not locs:
        fuente = "postgres"
        locs = query(
            """
            SELECT id_locacion, tipo_locacion, nombre, ciudad, direccion, activo
            FROM operacion.locacion
            ORDER BY id_locacion ASC
            """
        )
        cache_service.set_json(CACHE_KEY_LOCATIONS, locs, ttl_segundos=600)
    tipo = (request.args.get("tipo") or "").upper()
    if tipo:
        locs = [l for l in locs if str(l.get("tipo_locacion", "")).upper() == tipo]
    return render_response({"total": len(locs), "locaciones": locs, "fuente": fuente}, status=200, root_tag="catalogo_locaciones")


@app.get("/api/v1/catalog/suppliers")
@documentar("Proveedores con lead time y MOQ", consulta=[("q", "string", "Busca por razón social o RFC")], raiz_respuesta="catalogo_proveedores")
@requiere_auth("buyer", "planner")
def listar_proveedores():
    """Consulta de proveedores."""
    q = request.args.get("q")
    filtro = "WHERE razon_social ILIKE :q OR rfc ILIKE :q" if q else ""
    filas = query(
        f"""
        SELECT id_proveedor, rfc, razon_social, lead_time_dias, moq,
               contacto_email, telefono, activo
        FROM operacion.proveedor
        {filtro}
        ORDER BY razon_social ASC
        """,
        **({"q": f"%{q}%"} if q else {}),
    )
    for f in filas:
        f["moq"] = a_float(f.get("moq"))
    return render_response({"total": len(filas), "proveedores": filas}, status=200, root_tag="catalogo_proveedores")


if __name__ == "__main__":
    ejecutar(app, "CATALOG_SERVICE_PORT", 5002)
