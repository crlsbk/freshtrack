"""
bootstrap_db.py — Deja la base de datos de FreshTrack lista desde cero.

Hace, en orden:

    1. Crea la base de datos si no existe.
    2. Crea los roles transaccionales (app_backend, app_auditor, app_etl).
    3. Ejecuta los scripts de sql/ en orden: esquemas, auditoría, operación,
       analítica, funciones de negocio, vistas y datos base.

Es idempotente: si ya está hecho, no rompe nada. Se usa desde el Makefile
(`make bootstrap`) y es el equivalente local de lo que hace el contenedor de
PostgreSQL al inicializar el volumen con docker-entrypoint-initdb.d.

Uso:
    python scripts/bootstrap_db.py
    python scripts/bootstrap_db.py --db freshtrack_pruebas   # otra base
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

SQL_DIR = RAIZ / "sql"

# Orden de ejecución. 00_init_roles.sh no va aquí: los roles se crean desde
# Python para no depender de que exista el cliente psql.
SCRIPTS = [
    "01_init_schemas.sql",
    "02_ddl_auditoria.sql",
    "03_ddl_operacion.sql",
    "04_ddl_analitica.sql",
    "05_funciones_negocio.sql",
    "06_views.sql",
    "07_seed_base.sql",
]


def _parametros(clave: str, defecto: str | None = None) -> str:
    valor = os.getenv(clave, defecto)
    if not valor:
        raise SystemExit(
            f"Falta la variable de entorno {clave}.\n"
            "Copia env.example a .env y ajusta los valores:  cp env.example .env"
        )
    return valor


def _url_superusuario(db: str) -> str:
    """URL del superusuario, apuntando a la base indicada."""
    base = os.getenv("ETL_DATABASE_URL") or _parametros("DATABASE_URL")
    base = re.sub(r"^postgresql\+(psycopg2?|psycopg)://", "postgresql://", base)
    # Reemplaza la base y el usuario por los del superusuario.
    sin_base = re.sub(r"/[^/?]+(\?.*)?$", "", base)
    return f"{sin_base}/{db}"


def _ejecutar_sql(conn: psycopg.Connection, ruta: Path) -> None:
    contenido = ruta.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(contenido)


def main() -> int:
    ap = argparse.ArgumentParser(description="Inicializa la base de datos de FreshTrack")
    ap.add_argument("--db", default=os.getenv("POSTGRES_DB", "retail_perecederos"),
                    help="Nombre de la base de datos a inicializar")
    ap.add_argument("--solo-verificar", action="store_true",
                    help="No escribe nada: comprueba que los objetos existen")
    args = ap.parse_args()

    db = args.db
    url = _url_superusuario(db)

    if args.solo_verificar:
        return _verificar(url)

    print(f"[bootstrap] Base de datos objetivo: {db}")

    # --- 1) La base existe? -------------------------------------------------
    url_admin = _url_superusuario("postgres")
    with psycopg.connect(url_admin, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
            existe = cur.fetchone() is not None
            if not existe:
                print(f"[bootstrap] Creando la base «{db}»…")
                # El nombre no puede ir como parámetro: se cita a mano y se
                # valida contra un patrón estricto para no permitir inyección.
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", db):
                    raise SystemExit(f"Nombre de base no válido: {db!r}")
                cur.execute(f'CREATE DATABASE "{db}"')
            else:
                print(f"[bootstrap] La base «{db}» ya existe.")

    # --- 2) Roles transaccionales ------------------------------------------
    backend = _parametros("APP_BACKEND_PASSWORD")
    auditor = _parametros("APP_AUDITOR_PASSWORD")
    print("[bootstrap] Creando/actualizando roles app_backend, app_auditor, app_etl…")

    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for rol, clave in (("app_backend", backend), ("app_auditor", auditor),
                               ("app_etl", backend)):
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rol,))
                existe = cur.fetchone() is not None
                # Ojo: PostgreSQL no acepta un parámetro en PASSWORD, así que el
                # literal se compone con psycopg.sql (que lo cita correctamente).
                verbo = "ALTER ROLE" if existe else "CREATE ROLE"
                cur.execute(
                    sql.SQL(f"{verbo} {{}} LOGIN PASSWORD {{}}").format(
                        sql.Identifier(rol), sql.Literal(clave)
                    )
                )
            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO app_backend, app_auditor, app_etl")
                .format(sql.Identifier(db))
            )

    # --- 3) Scripts de sql/ en orden ---------------------------------------
    for nombre in SCRIPTS:
        ruta = SQL_DIR / nombre
        if not ruta.exists():
            print(f"[bootstrap]   ! falta {nombre}, se omite", file=sys.stderr)
            continue
        print(f"[bootstrap] Ejecutando {nombre}…")
        with psycopg.connect(url, autocommit=True) as conn:
            try:
                _ejecutar_sql(conn, ruta)
            except psycopg.Error as e:
                print(f"\n[bootstrap] ERROR en {nombre}:\n{e}\n", file=sys.stderr)
                return 1

    print("\n[bootstrap] Listo. Comprobando el resultado:")
    return _verificar(url)


def _verificar(url: str) -> int:
    """Cuenta los objetos clave; devuelve 1 si falta alguno."""
    esperado = [
        ("operacion", "producto"),
        ("operacion", "proveedor"),
        ("operacion", "locacion"),
        ("operacion", "usuario"),
        ("operacion", "lote"),
        ("operacion", "existencia"),
        ("operacion", "venta"),
        ("operacion", "merma"),
        ("operacion", "regla_riesgo"),
        ("analitica", "forecast_run"),
        ("analitica", "forecast_result"),
        ("analitica", "orden_reabastecimiento"),
        ("analitica", "transferencia"),
        ("analitica", "alerta"),
        ("analitica", "desperdicio_evitado"),
        ("auditoria", "bitacora_eventos"),
    ]
    fallos = []
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        for esquema, tabla in esperado:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s",
                (esquema, tabla),
            )
            if cur.fetchone()[0] == 0:
                fallos.append(f"{esquema}.{tabla}")
        cur.execute("SELECT COUNT(*) FROM operacion.usuario")
        usuarios = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM operacion.regla_riesgo")
        reglas = cur.fetchone()[0]

    if fallos:
        print(f"[bootstrap] Faltan objetos: {', '.join(fallos)}", file=sys.stderr)
        return 1
    print(f"[bootstrap] 16 objetos clave presentes · {usuarios} usuarios · "
          f"{reglas} reglas de riesgo")
    print("[bootstrap] Todo en orden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
