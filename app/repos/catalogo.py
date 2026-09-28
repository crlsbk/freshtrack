"""
CRUD de catálogos: productos, proveedores, tiendas/CEDIS y usuarios.

Cada operación escribe en PostgreSQL dentro de una transacción con el usuario
responsable fijado, de modo que la bitácora registre quién hizo qué.
Todas las entidades tienen alta, consulta, edición y activar/desactivar.
"""

from __future__ import annotations

import re

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, one, query, transaccion


# ===========================================================================
# Normalización de identificadores fiscales / comerciales
#
# Se normalizan SIN alterar el valor: un RFC no se rellena con letras y un
# GTIN no se completa por la derecha. Rellenar cambia el identificador real y
# provocaba colisiones absurdas (un RFC de 12 caracteres chocaba con el de 13
# caracteres al que se le había añadido una «X»).
# ===========================================================================
_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")


def normalizar_rfc(valor: str | None) -> str:
    """
    Devuelve el RFC en mayúsculas, sin espacios y sin modificarlo.

    Acepta el formato del SAT: 3 o 4 letras, 6 dígitos de fecha y 3 caracteres
    de homoclave (12 caracteres para persona moral, 13 para persona física).
    """
    rfc = (valor or "").strip().upper()
    if not rfc:
        raise ValueError("El RFC es obligatorio.")
    if not _RFC_RE.match(rfc):
        raise ValueError(
            "El RFC no tiene un formato válido: se esperan 12 caracteres "
            "(persona moral) o 13 (persona física), p. ej. ABC260101XYZ."
        )
    return rfc


def normalizar_gtin(valor: str | None) -> str:
    """
    Normaliza un GTIN a su forma de 14 dígitos.

    El estándar GTIN-14 se obtiene rellenando por la IZQUIERDA con ceros
    (un GTIN-13 de 13 dígitos se convierte en «0» + el código). La columna es
    varchar(14) y admite GTIN-8, GTIN-12, GTIN-13 y GTIN-14.
    """
    gtin = (valor or "").strip()
    if not gtin:
        raise ValueError("El código GTIN es obligatorio.")
    if not gtin.isdigit():
        raise ValueError("El código GTIN solo puede contener dígitos.")
    if not 8 <= len(gtin) <= 14:
        raise ValueError("El código GTIN debe tener entre 8 y 14 dígitos.")
    return gtin.zfill(14)


# ===========================================================================
# PRODUCTOS
# ===========================================================================
def listar_productos(
    texto: str | None = None, categoria: str | None = None, solo_activos: bool = False
) -> list[dict]:
    condiciones = []
    params: dict = {}
    if solo_activos:
        condiciones.append("p.activo")
    if categoria:
        condiciones.append("p.categoria = :categoria")
        params["categoria"] = categoria
    if texto:
        condiciones.append("(p.nombre ILIKE :texto OR p.codigo_gtin ILIKE :texto)")
        params["texto"] = f"%{texto}%"
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    return query(
        f"""
        SELECT p.id_sku, p.codigo_gtin, p.nombre, p.categoria, p.vida_util_estandar,
               p.unidad_medida, p.precio_costo, p.precio_venta, p.stock_seguridad,
               p.punto_reorden, p.perecedero, p.activo, p.fecha_alta,
               p.id_proveedor, pr.razon_social AS proveedor, pr.lead_time_dias,
               pr.moq,
               (SELECT COUNT(*) FROM operacion.lote l WHERE l.id_sku = p.id_sku) AS n_lotes,
               (SELECT COALESCE(SUM(e.cantidad_disponible), 0)
                  FROM operacion.existencia e
                  JOIN operacion.lote l2 ON l2.id_lote = e.id_lote
                 WHERE l2.id_sku = p.id_sku) AS existencia_total
        FROM operacion.producto p
        LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        {where}
        ORDER BY p.activo DESC, p.nombre
        """,
        **params,
    )


def obtener_producto(id_sku: int) -> dict | None:
    return one(
        """
        SELECT p.*, pr.razon_social AS proveedor
        FROM operacion.producto p
        LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        WHERE p.id_sku = :id
        """,
        id=id_sku,
    )


def categorias() -> list[str]:
    return [
        f["categoria"]
        for f in query(
            "SELECT DISTINCT categoria FROM operacion.producto ORDER BY categoria"
        )
    ]


def crear_producto(datos: dict, usuario: dict) -> dict:
    nombre = (datos.get("nombre") or "").strip()
    gtin_crudo = (datos.get("codigo_gtin") or "").strip()
    if not nombre:
        raise ValueError("El nombre del producto es obligatorio.")
    gtin = normalizar_gtin(gtin_crudo) if gtin_crudo else _gtin_automatico()

    vida_util = a_int(datos.get("vida_util_estandar"), 0)
    if vida_util <= 0:
        raise ValueError("La vida útil estándar debe ser mayor que cero.")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        fila = conn.execute(
            text(
                """
                INSERT INTO operacion.producto
                    (codigo_gtin, nombre, id_proveedor, categoria, vida_util_estandar,
                     unidad_medida, precio_costo, precio_venta, stock_seguridad,
                     punto_reorden, perecedero, activo)
                VALUES
                    (:gtin, :nombre, :proveedor, :categoria, :vida, :unidad,
                     :costo, :venta, :seguridad, :reorden, :perecedero, true)
                RETURNING id_sku
                """
            ),
            {
                "gtin": gtin,
                "nombre": nombre,
                "proveedor": datos.get("id_proveedor") or None,
                "categoria": (datos.get("categoria") or "Abarrotes").strip(),
                "vida": vida_util,
                "unidad": (datos.get("unidad_medida") or "Pieza").strip(),
                "costo": a_float(datos.get("precio_costo")),
                "venta": a_float(datos.get("precio_venta")),
                "seguridad": a_float(datos.get("stock_seguridad")),
                "reorden": a_float(datos.get("punto_reorden")),
                "perecedero": bool(datos.get("perecedero", True)),
            },
        ).scalar()

    auditoria.registrar(
        "CREATE_PRODUCT",
        tabla="producto",
        id_registro=fila,
        descripcion=f"Alta del producto «{nombre}» (SKU {fila}, GTIN {gtin})",
        estado_nuevo={"id_sku": fila, "nombre": nombre, "vida_util": vida_util},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_sku": fila, "nombre": nombre}


def actualizar_producto(id_sku: int, datos: dict, usuario: dict) -> None:
    anterior = obtener_producto(id_sku)
    if anterior is None:
        raise ValueError("El producto no existe.")

    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("El nombre del producto es obligatorio.")
    vida_util = a_int(datos.get("vida_util_estandar"), 0)
    if vida_util <= 0:
        raise ValueError("La vida útil estándar debe ser mayor que cero.")

    nuevo = {
        "nombre": nombre,
        "id_proveedor": datos.get("id_proveedor") or None,
        "categoria": (datos.get("categoria") or anterior["categoria"]).strip(),
        "vida_util_estandar": vida_util,
        "unidad_medida": (datos.get("unidad_medida") or anterior["unidad_medida"]).strip(),
        "precio_costo": a_float(datos.get("precio_costo")),
        "precio_venta": a_float(datos.get("precio_venta")),
        "stock_seguridad": a_float(datos.get("stock_seguridad")),
        "punto_reorden": a_float(datos.get("punto_reorden")),
        "perecedero": bool(datos.get("perecedero", True)),
    }

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE operacion.producto
                   SET nombre = :nombre, id_proveedor = :id_proveedor,
                       categoria = :categoria, vida_util_estandar = :vida_util_estandar,
                       unidad_medida = :unidad_medida, precio_costo = :precio_costo,
                       precio_venta = :precio_venta, stock_seguridad = :stock_seguridad,
                       punto_reorden = :punto_reorden, perecedero = :perecedero
                 WHERE id_sku = :id
                """
            ),
            {**nuevo, "id": id_sku},
        )

    auditoria.registrar(
        "UPDATE_PRODUCT",
        tabla="producto",
        id_registro=id_sku,
        descripcion=f"Edición del producto «{nombre}» (SKU {id_sku})",
        estado_anterior={k: str(anterior.get(k)) for k in nuevo},
        estado_nuevo={k: str(v) for k, v in nuevo.items()},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


def cambiar_estado_producto(id_sku: int, activo: bool, usuario: dict) -> None:
    producto = obtener_producto(id_sku)
    if producto is None:
        raise ValueError("El producto no existe.")
    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text("UPDATE operacion.producto SET activo = :a WHERE id_sku = :id"),
            {"a": activo, "id": id_sku},
        )
    auditoria.registrar(
        "ACTIVATE_PRODUCT" if activo else "DEACTIVATE_PRODUCT",
        tabla="producto",
        id_registro=id_sku,
        descripcion=(
            f"{'Activado' if activo else 'Desactivado'} el producto "
            f"«{producto['nombre']}» (SKU {id_sku})"
        ),
        estado_anterior={"activo": producto["activo"]},
        estado_nuevo={"activo": activo},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


def _gtin_automatico() -> str:
    """Genera un GTIN-14 único cuando el usuario no lo captura."""
    ultimo = one(
        "SELECT MAX(CAST(codigo_gtin AS bigint)) AS m FROM operacion.producto "
        "WHERE codigo_gtin ~ '^[0-9]{14}$'"
    )
    base = int(ultimo["m"]) if ultimo and ultimo["m"] else 7501234560000
    return str(base + 1).rjust(14, "0")


# ===========================================================================
# PROVEEDORES
# ===========================================================================
def listar_proveedores(texto: str | None = None, solo_activos: bool = False) -> list[dict]:
    condiciones = []
    params: dict = {}
    if solo_activos:
        condiciones.append("pr.activo")
    if texto:
        condiciones.append("(pr.razon_social ILIKE :texto OR pr.rfc ILIKE :texto)")
        params["texto"] = f"%{texto}%"
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    return query(
        f"""
        SELECT pr.id_proveedor, pr.rfc, pr.razon_social, pr.lead_time_dias, pr.moq,
               pr.contacto_email, pr.telefono, pr.activo, pr.fecha_alta,
               (SELECT COUNT(*) FROM operacion.producto p WHERE p.id_proveedor = pr.id_proveedor)
                   AS n_productos,
               (SELECT COUNT(*) FROM operacion.lote l WHERE l.id_proveedor = pr.id_proveedor)
                   AS n_lotes
        FROM operacion.proveedor pr
        {where}
        ORDER BY pr.activo DESC, pr.razon_social
        """,
        **params,
    )


def obtener_proveedor(id_proveedor: int) -> dict | None:
    return one("SELECT * FROM operacion.proveedor WHERE id_proveedor = :id", id=id_proveedor)


def crear_proveedor(datos: dict, usuario: dict) -> dict:
    razon = (datos.get("razon_social") or "").strip()
    if not razon:
        raise ValueError("La razón social es obligatoria.")
    rfc = normalizar_rfc(datos.get("rfc"))

    lead_time = a_int(datos.get("lead_time_dias"), 3)
    if lead_time < 0:
        raise ValueError("El lead time no puede ser negativo.")
    moq = a_float(datos.get("moq")) or 1.0
    if moq <= 0:
        raise ValueError("El pedido mínimo (MOQ) debe ser mayor que cero.")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        fila = conn.execute(
            text(
                """
                INSERT INTO operacion.proveedor
                    (rfc, razon_social, lead_time_dias, moq, contacto_email, telefono, activo)
                VALUES (:rfc, :razon, :lead, :moq, :email, :tel, true)
                RETURNING id_proveedor
                """
            ),
            {
                "rfc": rfc,
                "razon": razon,
                "lead": lead_time,
                "moq": moq,
                "email": (datos.get("contacto_email") or "").strip() or None,
                "tel": (datos.get("telefono") or "").strip() or None,
            },
        ).scalar()

    auditoria.registrar(
        "CREATE_SUPPLIER",
        tabla="proveedor",
        id_registro=fila,
        descripcion=(
            f"Alta del proveedor «{razon}» (RFC {rfc}) con lead time de "
            f"{lead_time} días y MOQ de {moq:g}"
        ),
        estado_nuevo={"id_proveedor": fila, "razon_social": razon, "lead_time": lead_time, "moq": moq},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_proveedor": fila, "razon_social": razon}


def actualizar_proveedor(id_proveedor: int, datos: dict, usuario: dict) -> None:
    anterior = obtener_proveedor(id_proveedor)
    if anterior is None:
        raise ValueError("El proveedor no existe.")
    razon = (datos.get("razon_social") or "").strip()
    if not razon:
        raise ValueError("La razón social es obligatoria.")
    rfc = normalizar_rfc(datos.get("rfc"))
    lead_time = a_int(datos.get("lead_time_dias"), 3)
    if lead_time < 0:
        raise ValueError("El lead time no puede ser negativo.")
    moq = a_float(datos.get("moq")) or 1.0

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE operacion.proveedor
                   SET razon_social = :razon, rfc = :rfc, lead_time_dias = :lead,
                       moq = :moq, contacto_email = :email, telefono = :tel
                 WHERE id_proveedor = :id
                """
            ),
            {
                "razon": razon,
                "rfc": rfc,
                "lead": lead_time,
                "moq": moq,
                "email": (datos.get("contacto_email") or "").strip() or None,
                "tel": (datos.get("telefono") or "").strip() or None,
                "id": id_proveedor,
            },
        )

    auditoria.registrar(
        "UPDATE_SUPPLIER",
        tabla="proveedor",
        id_registro=id_proveedor,
        descripcion=f"Edición del proveedor «{razon}»",
        estado_anterior={
            "razon_social": anterior["razon_social"],
            "lead_time_dias": anterior["lead_time_dias"],
            "moq": str(anterior["moq"]),
        },
        estado_nuevo={"razon_social": razon, "lead_time_dias": lead_time, "moq": moq},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


def cambiar_estado_proveedor(id_proveedor: int, activo: bool, usuario: dict) -> None:
    proveedor = obtener_proveedor(id_proveedor)
    if proveedor is None:
        raise ValueError("El proveedor no existe.")
    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text("UPDATE operacion.proveedor SET activo = :a WHERE id_proveedor = :id"),
            {"a": activo, "id": id_proveedor},
        )
    auditoria.registrar(
        "ACTIVATE_SUPPLIER" if activo else "DEACTIVATE_SUPPLIER",
        tabla="proveedor",
        id_registro=id_proveedor,
        descripcion=(
            f"{'Activado' if activo else 'Desactivado'} el proveedor "
            f"«{proveedor['razon_social']}»"
        ),
        estado_anterior={"activo": proveedor["activo"]},
        estado_nuevo={"activo": activo},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


# ===========================================================================
# TIENDAS Y CEDIS
# ===========================================================================
def listar_locaciones(solo_activas: bool = False) -> list[dict]:
    filtro = "WHERE l.activo" if solo_activas else ""
    return query(
        f"""
        SELECT l.id_locacion, l.tipo_locacion, l.nombre, l.ciudad, l.direccion,
               l.activo, l.fecha_alta,
               (SELECT COUNT(DISTINCT b.id_sku)
                  FROM operacion.existencia e
                  JOIN operacion.lote b ON b.id_lote = e.id_lote
                 WHERE e.id_locacion = l.id_locacion AND e.cantidad_disponible > 0) AS skus,
               (SELECT COUNT(DISTINCT e.id_lote)
                  FROM operacion.existencia e
                 WHERE e.id_locacion = l.id_locacion AND e.cantidad_disponible > 0) AS lotes,
               (SELECT COALESCE(SUM(e.cantidad_disponible), 0)
                  FROM operacion.existencia e
                 WHERE e.id_locacion = l.id_locacion) AS unidades,
               (SELECT COUNT(*) FROM operacion.usuario u
                 WHERE u.id_locacion = l.id_locacion AND u.estado_activo) AS usuarios
        FROM operacion.locacion l
        {filtro}
        ORDER BY l.activo DESC, l.tipo_locacion, l.nombre
        """
    )


def obtener_locacion(id_locacion: int) -> dict | None:
    return one("SELECT * FROM operacion.locacion WHERE id_locacion = :id", id=id_locacion)


def crear_locacion(datos: dict, usuario: dict) -> dict:
    nombre = (datos.get("nombre") or "").strip()
    tipo = (datos.get("tipo_locacion") or "Tienda").strip()
    if not nombre:
        raise ValueError("El nombre es obligatorio.")
    if tipo not in ("Tienda", "CEDIS"):
        raise ValueError("El tipo debe ser «Tienda» o «CEDIS».")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        fila = conn.execute(
            text(
                """
                INSERT INTO operacion.locacion
                    (tipo_locacion, nombre, ciudad, direccion, activo)
                VALUES (:tipo, :nombre, :ciudad, :direccion, true)
                RETURNING id_locacion
                """
            ),
            {
                "tipo": tipo,
                "nombre": nombre,
                "ciudad": (datos.get("ciudad") or "").strip() or None,
                "direccion": (datos.get("direccion") or "").strip() or None,
            },
        ).scalar()

    auditoria.registrar(
        "CREATE_LOCATION",
        tabla="locacion",
        id_registro=fila,
        descripcion=f"Alta de {tipo.lower()} «{nombre}»",
        estado_nuevo={"id_locacion": fila, "nombre": nombre, "tipo": tipo},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_locacion": fila, "nombre": nombre}


def actualizar_locacion(id_locacion: int, datos: dict, usuario: dict) -> None:
    anterior = obtener_locacion(id_locacion)
    if anterior is None:
        raise ValueError("La locación no existe.")
    nombre = (datos.get("nombre") or "").strip()
    tipo = (datos.get("tipo_locacion") or anterior["tipo_locacion"]).strip()
    if not nombre:
        raise ValueError("El nombre es obligatorio.")
    if tipo not in ("Tienda", "CEDIS"):
        raise ValueError("El tipo debe ser «Tienda» o «CEDIS».")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE operacion.locacion
                   SET nombre = :nombre, tipo_locacion = :tipo, ciudad = :ciudad,
                       direccion = :direccion
                 WHERE id_locacion = :id
                """
            ),
            {
                "nombre": nombre,
                "tipo": tipo,
                "ciudad": (datos.get("ciudad") or "").strip() or None,
                "direccion": (datos.get("direccion") or "").strip() or None,
                "id": id_locacion,
            },
        )

    auditoria.registrar(
        "UPDATE_LOCATION",
        tabla="locacion",
        id_registro=id_locacion,
        descripcion=f"Edición de la locación «{nombre}»",
        estado_anterior={"nombre": anterior["nombre"], "tipo": anterior["tipo_locacion"]},
        estado_nuevo={"nombre": nombre, "tipo": tipo},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


def cambiar_estado_locacion(id_locacion: int, activo: bool, usuario: dict) -> None:
    locacion = obtener_locacion(id_locacion)
    if locacion is None:
        raise ValueError("La locación no existe.")
    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text("UPDATE operacion.locacion SET activo = :a WHERE id_locacion = :id"),
            {"a": activo, "id": id_locacion},
        )
    auditoria.registrar(
        "ACTIVATE_LOCATION" if activo else "DEACTIVATE_LOCATION",
        tabla="locacion",
        id_registro=id_locacion,
        descripcion=(
            f"{'Activada' if activo else 'Desactivada'} la locación «{locacion['nombre']}»"
        ),
        estado_anterior={"activo": locacion["activo"]},
        estado_nuevo={"activo": activo},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


# ===========================================================================
# USUARIOS
# ===========================================================================
def listar_usuarios(texto: str | None = None) -> list[dict]:
    params: dict = {}
    where = ""
    if texto:
        where = "WHERE (u.nombre_completo ILIKE :texto OR u.email ILIKE :texto)"
        params["texto"] = f"%{texto}%"
    return query(
        f"""
        SELECT u.id_usuario::text, u.nombre_completo, u.email, u.estado_activo,
               u.intentos_fallidos, u.bloqueado_hasta, u.ultimo_acceso, u.fecha_alta,
               u.id_rol, u.id_locacion,
               r.nombre_rol, r.clave AS rol_clave,
               loc.nombre AS locacion
        FROM operacion.usuario u
        JOIN operacion.rol r ON r.id_rol = u.id_rol
        LEFT JOIN operacion.locacion loc ON loc.id_locacion = u.id_locacion
        {where}
        ORDER BY u.estado_activo DESC, u.nombre_completo
        """,
        **params,
    )


def roles() -> list[dict]:
    return query("SELECT id_rol, nombre_rol, clave, descripcion FROM operacion.rol ORDER BY id_rol")


def crear_usuario(datos: dict, usuario: dict) -> dict:
    nombre = (datos.get("nombre_completo") or "").strip()
    email = (datos.get("email") or "").strip().lower()
    password = datos.get("password") or ""
    id_rol = a_int(datos.get("id_rol"), 0)
    if not nombre:
        raise ValueError("El nombre completo es obligatorio.")
    if not email:
        raise ValueError("El correo es obligatorio.")
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if not id_rol:
        raise ValueError("Debes asignar un rol.")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        fila = conn.execute(
            text(
                """
                INSERT INTO operacion.usuario
                    (id_rol, id_locacion, nombre_completo, email, password_hash, estado_activo)
                VALUES (:rol, :loc, :nombre, :email, crypt(:password, gen_salt('bf')), true)
                RETURNING id_usuario::text
                """
            ),
            {
                "rol": id_rol,
                "loc": datos.get("id_locacion") or None,
                "nombre": nombre,
                "email": email,
                "password": password,
            },
        ).scalar()

    auditoria.registrar(
        "CREATE_USER",
        tabla="usuario",
        id_registro=fila,
        descripcion=f"Alta del usuario «{nombre}» ({email})",
        estado_nuevo={"id_usuario": fila, "email": email, "id_rol": id_rol},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_usuario": fila, "email": email}


def actualizar_usuario(id_usuario: str, datos: dict, usuario: dict) -> None:
    anterior = one(
        "SELECT id_usuario::text, nombre_completo, email, id_rol, id_locacion "
        "FROM operacion.usuario WHERE id_usuario = CAST(:id AS uuid)",
        id=id_usuario,
    )
    if anterior is None:
        raise ValueError("El usuario no existe.")
    nombre = (datos.get("nombre_completo") or "").strip()
    email = (datos.get("email") or "").strip().lower()
    id_rol = a_int(datos.get("id_rol"), 0)
    if not nombre or not email or not id_rol:
        raise ValueError("Nombre, correo y rol son obligatorios.")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE operacion.usuario
                   SET nombre_completo = :nombre, email = :email, id_rol = :rol,
                       id_locacion = :loc
                 WHERE id_usuario = CAST(:id AS uuid)
                """
            ),
            {
                "nombre": nombre,
                "email": email,
                "rol": id_rol,
                "loc": datos.get("id_locacion") or None,
                "id": id_usuario,
            },
        )

    auditoria.registrar(
        "UPDATE_USER",
        tabla="usuario",
        id_registro=id_usuario,
        descripcion=f"Edición del usuario «{nombre}»",
        estado_anterior={
            "nombre_completo": anterior["nombre_completo"],
            "email": anterior["email"],
            "id_rol": anterior["id_rol"],
        },
        estado_nuevo={"nombre_completo": nombre, "email": email, "id_rol": id_rol},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


def cambiar_estado_usuario(id_usuario: str, activo: bool, usuario: dict) -> None:
    registro = one(
        "SELECT id_usuario::text, nombre_completo, email, estado_activo "
        "FROM operacion.usuario WHERE id_usuario = CAST(:id AS uuid)",
        id=id_usuario,
    )
    if registro is None:
        raise ValueError("El usuario no existe.")
    if registro["email"] == usuario["email"] and not activo:
        raise ValueError("No puedes desactivar tu propia cuenta.")

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                "UPDATE operacion.usuario SET estado_activo = :a, intentos_fallidos = 0, "
                "bloqueado_hasta = NULL WHERE id_usuario = CAST(:id AS uuid)"
            ),
            {"a": activo, "id": id_usuario},
        )
        if not activo:
            conn.execute(
                text(
                    "UPDATE operacion.sesion_usuario SET revocado = true, revocado_en = now() "
                    "WHERE id_usuario = CAST(:id AS uuid) AND NOT revocado"
                ),
                {"id": id_usuario},
            )

    auditoria.registrar(
        "ACTIVATE_USER" if activo else "DEACTIVATE_USER",
        tabla="usuario",
        id_registro=id_usuario,
        descripcion=(
            f"{'Activado' if activo else 'Desactivado'} el usuario «{registro['nombre_completo']}»"
        ),
        estado_anterior={"estado_activo": registro["estado_activo"]},
        estado_nuevo={"estado_activo": activo},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )


def restablecer_password(id_usuario: str, nueva: str, usuario: dict) -> None:
    if len(nueva or "") < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                "UPDATE operacion.usuario "
                "SET password_hash = crypt(:p, gen_salt('bf')), intentos_fallidos = 0, "
                "bloqueado_hasta = NULL WHERE id_usuario = CAST(:id AS uuid)"
            ),
            {"p": nueva, "id": id_usuario},
        )
        conn.execute(
            text(
                "UPDATE operacion.sesion_usuario SET revocado = true, revocado_en = now() "
                "WHERE id_usuario = CAST(:id AS uuid) AND NOT revocado"
            ),
            {"id": id_usuario},
        )
    auditoria.registrar(
        "UPDATE_USER",
        tabla="usuario",
        id_registro=id_usuario,
        descripcion="Restablecimiento de contraseña",
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
