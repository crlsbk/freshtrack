"""
Acceso a PostgreSQL.

Dos reglas que se respetan en todo el proyecto:

1. Toda consulta pasa por aquí. No hay datos simulados en ningún flujo.
2. Cada transacción de escritura abre un bloque `transaccion(...)` que fija
   `app.current_user_id` en la sesión de PostgreSQL. Los triggers de auditoría
   leen esa variable para saber quién hizo el cambio, de modo que la bitácora
   se llena sola sin que la aplicación tenga que insertar nada a mano.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import Config

_engine: Engine | None = None


def get_engine() -> Engine:
    """Motor SQLAlchemy compartido (creación perezosa)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            Config.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            future=True,
        )
    return _engine


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------
def query(sql: str, **params: Any) -> list[dict]:
    """Ejecuta un SELECT y devuelve una lista de diccionarios."""
    with get_engine().connect() as conn:
        filas = conn.execute(text(sql), params).mappings().all()
    return [dict(f) for f in filas]


def one(sql: str, **params: Any) -> dict | None:
    """Ejecuta un SELECT y devuelve la primera fila (o None)."""
    filas = query(sql, **params)
    return filas[0] if filas else None


def escalar(sql: str, **params: Any) -> Any:
    """
    Ejecuta un SELECT y devuelve el primer valor de la primera fila.

    OJO: usa `connect()`, así que la transacción se revierte al salir. Sirve
    para leer, nunca para escribir (ver `escribir()`).
    """
    with get_engine().connect() as conn:
        return conn.execute(text(sql), params).scalar()


def escribir(sql: str, **params: Any) -> Any:
    """
    Ejecuta una sentencia que MODIFICA datos y devuelve el primer valor.

    SQLAlchemy 2.x revierte la transacción al cerrar un `connect()`, de modo
    que una escritura lanzada con `escalar()` se perdería en silencio: la
    función devolvía el id recién insertado pero la fila no quedaba en la base.
    Este ayudante abre la transacción con `begin()`, que sí confirma.

    Se usa para INSERT/UPDATE/DELETE sueltos y para funciones volátiles
    (p. ej. auditoria.fn_registrar_accion), que no son un SELECT puro.

    Devuelve el primer valor si la sentencia devuelve filas (un `RETURNING`, o
    la llamada a una función) y, si no, el número de filas afectadas. Así sirve
    tanto para `SELECT fn(...)` como para un `DELETE` a secas.
    """
    with get_engine().begin() as conn:
        resultado = conn.execute(text(sql), params)
        if resultado.returns_rows:
            return resultado.scalar()
        return resultado.rowcount


def escalares(sql: str, **params: Any) -> list[Any]:
    """Ejecuta un SELECT y devuelve la primera columna de todas las filas."""
    with get_engine().connect() as conn:
        return [fila[0] for fila in conn.execute(text(sql), params).all()]


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------
@contextmanager
def transaccion(id_usuario: str | None = None, usuario_email: str | None = None):
    """
    Abre una transacción de escritura con el usuario responsable fijado.

    Ejemplo:
        with transaccion(id_usuario=uid, usuario_email=mail) as conn:
            conn.execute(text("INSERT INTO ..."), {...})
        # el commit es automático al salir sin excepciones
    """
    with get_engine().begin() as conn:
        if id_usuario:
            conn.execute(
                text("SELECT set_config('app.current_user_id', :v, true)"),
                {"v": str(id_usuario)},
            )
        if usuario_email:
            conn.execute(
                text("SELECT set_config('app.current_user_email', :v, true)"),
                {"v": str(usuario_email)},
            )
        yield conn


def ejecutar(sql: str, **params: Any) -> int:
    """Ejecuta una sentencia de escritura suelta y devuelve el número de filas."""
    with get_engine().begin() as conn:
        res = conn.execute(text(sql), params)
        return res.rowcount or 0


def ejecutar_devolviendo(sql: str, **params: Any) -> dict | None:
    """Ejecuta un INSERT/UPDATE ... RETURNING y devuelve la fila resultante."""
    with get_engine().begin() as conn:
        fila = conn.execute(text(sql), params).mappings().first()
        return dict(fila) if fila else None


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def sql_error(exc: SQLAlchemyError) -> str:
    """
    Traduce el error crudo de PostgreSQL en un mensaje entendible para el usuario.
    """
    mensaje = str(getattr(exc, "orig", exc))
    # Las claves son el nombre REAL de la restricción en PostgreSQL, tal como
    # aparece en el mensaje de error. Los nombres por defecto de una columna
    # UNIQUE son <tabla>_<columna>_key.
    traducciones = {
        "producto_codigo_gtin_key": "Ya existe un producto con ese código GTIN.",
        "uq_codigo_gtin": "Ya existe un producto con ese código GTIN.",
        "proveedor_rfc_key": "Ya existe un proveedor con ese RFC.",
        "uq_rfc": "Ya existe un proveedor con ese RFC.",
        "locacion_nombre_key": "Ya existe una tienda o CEDIS con ese nombre.",
        "usuario_email_key": "Ya existe un usuario con ese correo.",
        "uq_lote_proveedor": "Ese proveedor ya tiene un lote con el mismo código.",
        "chk_lote_fechas": "La fecha de caducidad debe ser posterior a la de recepción.",
        "chk_lote_prod": "La fecha de producción no puede ser posterior a la de recepción.",
        "chk_cantidad_disponible": "El inventario no puede quedar en negativo.",
        "chk_causa_merma": "Causa de merma no válida.",
        "chk_email_formato": "El correo no tiene un formato válido.",
    }
    for clave, texto in traducciones.items():
        if clave in mensaje:
            return texto
    return mensaje.split("\n")[0]


def a_float(valor: Any) -> float:
    """Convierte Decimal/None a float de forma segura para plantillas y JSON."""
    if valor is None:
        return 0.0
    if isinstance(valor, Decimal):
        return float(valor)
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def a_int(valor: Any, default: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


def normalizar_numeros(fila: dict) -> dict:
    """Convierte todos los Decimal de una fila a float (para JSON y plantillas)."""
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in fila.items()}


def normalizar_filas(filas: Iterable[dict]) -> list[dict]:
    return [normalizar_numeros(f) for f in filas]


def paginar(items: Sequence, pagina: int, por_pagina: int = 25) -> dict:
    """Paginación simple para los listados."""
    total = len(items)
    paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = max(1, min(pagina, paginas))
    inicio = (pagina - 1) * por_pagina
    return {
        "items": list(items[inicio : inicio + por_pagina]),
        "total": total,
        "pagina": pagina,
        "paginas": paginas,
        "por_pagina": por_pagina,
    }


def config_valor(clave: str, default: str | None = None) -> str | None:
    """Lee un parámetro de analitica.configuracion."""
    return escalar("SELECT analitica.fn_config(:c, :d)", c=clave, d=default)
