#!/usr/bin/env python
"""
ETL de FreshTrack — genera la operación histórica real en PostgreSQL.

A diferencia de un generador de datos aleatorios, este ETL **simula la operación
día a día** de cada tienda:

  1. Recepción de lotes cuando el inventario cae por debajo del punto de reorden.
  2. Cálculo de la demanda diaria (estacionalidad semanal y mensual + tendencia + ruido).
  3. Consumo FEFO: la demanda se cubre primero con el lote que vence antes.
  4. Merma automática de los lotes que caducan con existencia remanente, más
     mermas incidentales por daño, calidad, cadena de frío, manipulación y devolución.

Consecuencia: los lotes, las existencias, las ventas, las mermas y el kardex
quedan coherentes entre sí. El pronóstico se calcula después sobre estas ventas.

Uso:
    python scripts/ETL.py                 # carga 180 días de historia
    python scripts/ETL.py --dias 90
    python scripts/ETL.py --reset         # borra la operación histórica y recarga
    python scripts/ETL.py --sin-kardex    # omite el kardex de movimientos
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta

import psycopg
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------
def url_psycopg() -> str:
    """
    URL de conexión del ETL.

    Usa ETL_DATABASE_URL si está definida (recomendado: un usuario con
    privilegios para desactivar los triggers de auditoría durante la carga
    masiva) y si no, cae a DATABASE_URL. Ambas vienen del entorno: no hay
    credenciales escritas en el código.
    """
    url = os.getenv("ETL_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "Falta ETL_DATABASE_URL o DATABASE_URL.\n"
            "Copia env.example a .env y ajusta los valores:  cp env.example .env"
        )
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )


# ---------------------------------------------------------------------------
# Parámetros de la simulación
# ---------------------------------------------------------------------------
CAUSAS_INCIDENTALES = [
    ("DANO", 0.35),
    ("CALIDAD", 0.25),
    ("CADENA_DE_FRIO", 0.15),
    ("MANIPULACION", 0.15),
    ("DEVOLUCION", 0.10),
]

PREFIJOS_PROVEEDOR = {
    "Lácteos del Norte S.A. de C.V.": "LDN",
    "Frutas del Bajío S.A. de C.V.": "FDB",
    "Verduras Frescas del Rancho": "VFR",
    "Carnes Refrigeradas del Norte": "CRN",
    "Panificadora Artesanal S.A.": "PAA",
    "Abarrotes del Centro": "ADC",
}


def demanda_base(precio_venta: float) -> float:
    """
    Demanda diaria base por tienda, derivada del precio real del producto:
    los productos baratos rotan más. No es una tabla fija de valores simulados,
    sale del catálogo que está en PostgreSQL.
    """
    if precio_venta <= 0:
        return 20.0
    return max(8.0, min(70.0, round(900.0 / float(precio_venta), 1)))


def factor_estacional(fecha: date) -> float:
    """Fin de semana +35 %, quincena +20 %."""
    f = 1.0
    if fecha.weekday() >= 4:  # viernes, sábado, domingo
        f *= 1.35
    if fecha.day in (14, 15, 16, 29, 30, 31, 1):
        f *= 1.20
    return f


# ---------------------------------------------------------------------------
# Carga de catálogos
# ---------------------------------------------------------------------------
def cargar_catalogos(cur):
    cur.execute(
        """
        SELECT p.id_sku, p.nombre, p.categoria, p.vida_util_estandar,
               p.precio_costo, p.precio_venta, p.punto_reorden, p.stock_seguridad,
               p.id_proveedor, pr.razon_social, pr.lead_time_dias, pr.moq
        FROM operacion.producto p
        JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        WHERE p.activo AND p.perecedero
        ORDER BY p.id_sku
        """
    )
    productos = [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]
    # Los tipos NUMERIC llegan como Decimal: los pasamos a float para el cálculo
    for p in productos:
        for campo in ("precio_costo", "precio_venta", "punto_reorden", "stock_seguridad", "moq"):
            if p.get(campo) is not None:
                p[campo] = float(p[campo])

    cur.execute(
        "SELECT id_locacion, nombre, tipo_locacion FROM operacion.locacion "
        "WHERE activo ORDER BY id_locacion"
    )
    locaciones = [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]

    tiendas = [l for l in locaciones if l["tipo_locacion"] == "Tienda"]
    cedis = [l for l in locaciones if l["tipo_locacion"] == "CEDIS"]

    cur.execute(
        "SELECT id_usuario, id_locacion FROM operacion.usuario "
        "WHERE estado_activo ORDER BY id_usuario"
    )
    usuarios = [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]

    return productos, tiendas, cedis, usuarios


def limpiar_operacion(cur):
    """Borra la operación histórica conservando catálogos y usuarios."""
    print("[ETL] Limpiando operación previa...")
    for tabla in (
        "analitica.desperdicio_evitado",
        "analitica.descuento",
        "analitica.transferencia",
        "analitica.alerta",
        "analitica.orden_reabastecimiento",
        "analitica.forecast_result",
        "analitica.forecast_run",
        "operacion.movimiento_inventario",
        "operacion.merma",
        "operacion.venta_detalle",
        "operacion.venta",
        "operacion.existencia",
        "operacion.lote",
    ):
        cur.execute(f"DELETE FROM {tabla}")


# ---------------------------------------------------------------------------
# Simulación
# ---------------------------------------------------------------------------
def simular(productos, tiendas, usuarios, fecha_inicio, fecha_fin, rng):
    """Devuelve las colecciones de filas a insertar."""
    lotes: list[tuple] = []
    existencias: dict[tuple, float] = {}   # (id_lote, id_locacion) -> cantidad
    ventas: list[tuple] = []               # cabeceras
    detalles: list[tuple] = []             # líneas
    mermas: list[tuple] = []
    movimientos: list[tuple] = []

    usuarios_por_locacion: dict[int, list] = {}
    for u in usuarios:
        usuarios_por_locacion.setdefault(u["id_locacion"], []).append(u["id_usuario"])
    usuario_global = usuarios[0]["id_usuario"] if usuarios else None

    secuencia_lote: dict[str, int] = {}
    secuencia_folio: dict[str, int] = {}
    dias = (fecha_fin - fecha_inicio).days

    for tienda in tiendas:
        id_loc = tienda["id_locacion"]

        for prod in productos:
            sku = prod["id_sku"]
            vida = int(prod["vida_util_estandar"])
            costo = float(prod["precio_costo"])
            precio = float(prod["precio_venta"])
            base = demanda_base(precio)
            punto_reorden = float(prod["punto_reorden"] or 0) or base * 3

            # Lotes activos en esta tienda: cada uno es un dict mutable
            activos: list[dict] = []

            def recibir(dia: date, cantidad: float) -> dict:
                """Da de alta un lote nuevo en esta tienda."""
                prod_prov = prod["razon_social"]
                prefijo = PREFIJOS_PROVEEDOR.get(prod_prov, "PRV")
                # El código de lote lo asigna el proveedor: es único por
                # (proveedor, fecha de producción). Varios SKUs del mismo
                # proveedor en la misma fecha reciben secuencias distintas.
                clave = f"{prefijo}-{dia.isoformat()}"
                secuencia_lote[clave] = secuencia_lote.get(clave, 0) + 1
                seq = secuencia_lote[clave]

                # El lote se produce con la vida útil estándar del producto.
                # Una fracción de las veces llega con menos vida (sobre-stock del proveedor).
                vida_real = vida if rng.random() > 0.18 else max(2, int(vida * rng.uniform(0.35, 0.7)))
                f_cad = dia + timedelta(days=vida_real)
                f_prod = f_cad - timedelta(days=vida)
                id_lote = uuid.uuid4()

                lote = {
                    "id_lote": id_lote,
                    "id_sku": sku,
                    "id_proveedor": prod["id_proveedor"],
                    "codigo": f"{prefijo}-{dia.strftime('%Y%m%d')}-{seq:03d}",
                    "f_prod": f_prod,
                    "f_recep": dia,
                    "f_cad": f_cad,
                    "costo": costo,
                    "restante": cantidad,
                    "id_locacion": id_loc,
                }
                activos.append(lote)
                lotes.append(
                    (
                        id_lote, sku, prod["id_proveedor"], lote["codigo"],
                        f_prod, dia, f_cad, cantidad, costo, id_loc,
                        "DISPONIBLE", None,
                        datetime.combine(dia, datetime.min.time()),
                    )
                )
                existencias[(id_lote, id_loc)] = cantidad
                movimientos.append(
                    (id_lote, id_loc, "RECEPCION", cantidad, cantidad, costo,
                     "LOTE", id_lote, usuario_global,
                     datetime.combine(dia, datetime.min.time()))
                )
                return lote

            def consumir_fefo(cantidad: float) -> list[tuple]:
                """
                Reparte `cantidad` entre los lotes disponibles, empezando por el
                que vence antes. Devuelve [(lote, cantidad_consumida)].
                """
                restante = cantidad
                consumos = []
                for lote in sorted(
                    (l for l in activos if l["restante"] > 0),
                    key=lambda l: (l["f_cad"], l["codigo"]),
                ):
                    if restante <= 1e-9:
                        break
                    if lote["f_cad"] < dia:
                        continue  # ya vencido: no se vende
                    toma = min(lote["restante"], restante)
                    lote["restante"] -= toma
                    restante -= toma
                    consumos.append((lote, toma))
                return consumos

            # Cobertura objetivo: nunca se pide más de lo que el producto puede
            # venderse antes de vencer. Un producto de 4 días de vida no debe
            # recibir 7 días de inventario.
            cobertura_dias = min(7.0, max(2.0, vida * 0.6))
            objetivo = base * cobertura_dias

            # Arranque: inventario inicial acorde a la vida útil del producto
            recibir(fecha_inicio, round(objetivo * rng.uniform(0.7, 1.0), 2))

            for i in range(dias + 1):
                dia = fecha_inicio + timedelta(days=i)

                # --- 1. Caducidades: los lotes vencidos con existencia se merman
                for lote in list(activos):
                    if lote["f_cad"] < dia and lote["restante"] > 0:
                        cant = round(lote["restante"], 2)
                        lote["restante"] = 0.0
                        mermas.append(
                            (lote["id_lote"], id_loc, usuario_global, cant,
                             "CADUCIDAD", lote["costo"], None,
                             datetime.combine(dia, datetime.min.time()).replace(hour=7))
                        )
                        existencias[(lote["id_lote"], id_loc)] = 0.0
                        movimientos.append(
                            (lote["id_lote"], id_loc, "MERMA", -cant, 0.0, lote["costo"],
                             "MERMA", None, usuario_global,
                             datetime.combine(dia, datetime.min.time()).replace(hour=7))
                        )
                        lote["estado"] = "VENCIDO"

                # --- 2. Reposición: se pide lo que falta para llegar al objetivo,
                #        nunca el objetivo completo (evita sobreinventario).
                disponible = sum(l["restante"] for l in activos if l["f_cad"] >= dia)
                if disponible < punto_reorden:
                    cantidad = max(prod["moq"] or 0, objetivo - disponible)
                    cantidad = round(cantidad * rng.uniform(0.95, 1.1), 2)
                    recibir(dia, cantidad)

                # --- 3. Merma incidental (no por caducidad)
                if rng.random() < 0.012:
                    candidatos = [l for l in activos if l["restante"] > 1 and l["f_cad"] >= dia]
                    if candidatos:
                        lote = rng.choice(candidatos)
                        cant = round(min(lote["restante"], rng.uniform(1, 6)), 2)
                        causa = rng.choices(
                            [c for c, _ in CAUSAS_INCIDENTALES],
                            weights=[w for _, w in CAUSAS_INCIDENTALES],
                        )[0]
                        lote["restante"] -= cant
                        mermas.append(
                            (lote["id_lote"], id_loc, usuario_global, cant, causa,
                             lote["costo"], None,
                             datetime.combine(dia, datetime.min.time()).replace(hour=rng.randint(9, 20)))
                        )
                        movimientos.append(
                            (lote["id_lote"], id_loc, "MERMA", -cant,
                             round(lote["restante"], 2), lote["costo"], "MERMA", None,
                             usuario_global,
                             datetime.combine(dia, datetime.min.time()).replace(hour=rng.randint(9, 20)))
                        )

                # --- 4. Demanda del día
                tendencia = 1.0 + 0.0006 * i
                ruido = rng.gauss(1.0, 0.14)
                demanda = max(0.0, base * factor_estacional(dia) * tendencia * ruido)
                if demanda < 1:
                    continue

                consumos = consumir_fefo(round(demanda, 2))
                if not consumos:
                    continue

                id_venta = uuid.uuid4()
                clave_folio = f"{id_loc}-{dia.isoformat()}"
                secuencia_folio[clave_folio] = secuencia_folio.get(clave_folio, 0) + 1
                folio = f"VT-{id_loc}-{dia.strftime('%Y%m%d')}-{secuencia_folio[clave_folio]:04d}"
                hora = rng.randint(8, 21)
                momento = datetime.combine(dia, datetime.min.time()).replace(
                    hour=hora, minute=rng.randint(0, 59)
                )
                total = 0.0
                for lote, cant in consumos:
                    subtotal = round(cant * precio, 2)
                    total += subtotal
                    detalles.append(
                        (uuid.uuid4(), id_venta, sku, lote["id_lote"], id_loc,
                         cant, precio, subtotal, momento)
                    )
                    restante = round(lote["restante"], 2)
                    existencias[(lote["id_lote"], id_loc)] = restante
                    movimientos.append(
                        (lote["id_lote"], id_loc, "VENTA", -cant, restante,
                         lote["costo"], "VENTA", id_venta, usuario_global, momento)
                    )
                ventas.append(
                    (id_venta, folio, id_loc, usuario_global, "TIENDA", round(total, 2), momento)
                )

    return lotes, existencias, ventas, detalles, mermas, movimientos


# ---------------------------------------------------------------------------
# Inserción masiva (COPY)
# ---------------------------------------------------------------------------
def copiar(cur, tabla, columnas, filas, etiqueta):
    if not filas:
        print(f"[ETL] {etiqueta}: sin filas")
        return 0
    cols = ", ".join(columnas)
    sentencia = f"COPY {tabla} ({cols}) FROM STDIN"
    with cur.copy(sentencia) as copy:
        for fila in filas:
            copy.write_row(fila)
    print(f"[ETL] {etiqueta}: {len(filas):,} filas")
    return len(filas)


def main() -> int:
    ap = argparse.ArgumentParser(description="ETL histórico de FreshTrack")
    ap.add_argument("--dias", type=int, default=180, help="días de historia a generar")
    ap.add_argument("--reset", action="store_true", help="borrar la operación previa")
    ap.add_argument("--sin-kardex", action="store_true", help="no generar movimientos de inventario")
    ap.add_argument("--seed", type=int, default=20260928, help="semilla aleatoria")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    fecha_fin = date.today()
    fecha_inicio = fecha_fin - timedelta(days=args.dias)

    print(f"[ETL] Conectando a {url_psycopg().split('@')[-1]}")
    with psycopg.connect(url_psycopg()) as conn:
        with conn.cursor() as cur:
            # La carga histórica no debe ensuciar la bitácora de auditoría.
            # Si el usuario tiene privilegios, desactivamos los triggers.
            triggers_off = False
            try:
                cur.execute("SET session_replication_role = replica")
                triggers_off = True
            except psycopg.Error:
                conn.rollback()
            print(f"[ETL] Triggers de auditoría desactivados: {triggers_off}")

            if args.reset:
                limpiar_operacion(cur)

            productos, tiendas, cedis, usuarios = cargar_catalogos(cur)
            print(f"[ETL] {len(productos)} productos · {len(tiendas)} tiendas · {len(usuarios)} usuarios")
            if not productos or not tiendas:
                print("[ETL] ERROR: faltan catálogos. Ejecuta primero sql/07_seed_base.sql")
                return 1

            cur.execute("SELECT count(*) FROM operacion.lote")
            if cur.fetchone()[0] > 0 and not args.reset:
                print("[ETL] Ya existen lotes. Usa --reset para recargar. Nada que hacer.")
                return 0

            print(f"[ETL] Simulando {args.dias} días ({fecha_inicio} → {fecha_fin})...")
            lotes, existencias, ventas, detalles, mermas, movimientos = simular(
                productos, tiendas, usuarios, fecha_inicio, fecha_fin, rng
            )

            copiar(
                cur, "operacion.lote",
                ["id_lote", "id_sku", "id_proveedor", "codigo_lote_prov",
                 "fecha_produccion", "fecha_recepcion", "fecha_caducidad",
                 "cantidad_recibida", "costo_unitario", "id_locacion_recepcion",
                 "estado", "observaciones", "creado_en"],
                lotes, "Lotes",
            )

            filas_exist = [
                (uuid.uuid4(), id_lote, id_loc, round(cant, 2))
                for (id_lote, id_loc), cant in existencias.items()
            ]
            copiar(
                cur, "operacion.existencia",
                ["id_existencia", "id_lote", "id_locacion", "cantidad_disponible"],
                filas_exist, "Existencias",
            )

            copiar(
                cur, "operacion.venta",
                ["id_venta", "folio", "id_locacion", "id_usuario", "canal", "total", "fecha_venta"],
                ventas, "Ventas (cabeceras)",
            )
            copiar(
                cur, "operacion.venta_detalle",
                ["id_detalle", "id_venta", "id_sku", "id_lote", "id_locacion",
                 "cantidad", "precio_unitario", "subtotal", "fecha_transaccion"],
                detalles, "Ventas (líneas)",
            )
            copiar(
                cur, "operacion.merma",
                ["id_lote", "id_locacion", "id_usuario", "cantidad", "causa_merma",
                 "costo_unitario", "observacion", "fecha_registro"],
                mermas, "Mermas",
            )

            if not args.sin_kardex:
                copiar(
                    cur, "operacion.movimiento_inventario",
                    ["id_lote", "id_locacion", "tipo", "cantidad", "cantidad_resultante",
                     "costo_unitario", "referencia_tipo", "referencia_id", "id_usuario", "fecha"],
                    movimientos, "Kardex",
                )

            if triggers_off:
                cur.execute("SET session_replication_role = origin")

            # Marcar como AGOTADO los lotes sin existencia
            cur.execute(
                """
                UPDATE operacion.lote l SET estado = 'AGOTADO'
                WHERE l.estado = 'DISPONIBLE'
                  AND NOT EXISTS (
                      SELECT 1 FROM operacion.existencia e
                      WHERE e.id_lote = l.id_lote AND e.cantidad_disponible > 0
                  )
                """
            )

        conn.commit()

    print("[ETL] Carga histórica completada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
