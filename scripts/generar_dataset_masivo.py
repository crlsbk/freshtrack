#!/usr/bin/env python3
"""
Generador masivo multi-perfil por streaming para FreshTrack.

Crea un dataset realista y coherente para pruebas de carga, índices, caché,
concurrencia y discriminación estadística de modelos:

  * 12 ubicaciones con GPS real (10 Tiendas + 2 CEDIS).
  * 200 SKUs perecederos con vida útil fija (2..14 días) divididos en 4 perfiles:
      - 50% (100) ESTABLE_ESTACIONAL : Poisson(λ~20) × vector semanal (Vie/Sáb ×1.6, Mar ×0.7)
      - 20%  (40) DRIFT_TENDENCIA    : 20 escalón ±45% reciente + 20 tendencia 60d ±40%
      - 20%  (40) INTERMITENTE       : ~60% de días en 0 y picos esporádicos de 1–3 u.
      - 10%  (20) QUIEBRE_STOCK      : alta venta con bloques de 5 días seguidos en 0
  * Consumo diario estricto FEFO (siempre del lote más viejo vigente).
  * Streaming tienda por tienda con PostgreSQL COPY (RAM < 150 MB en e2-standard-2).
  * Usuarios masivos (1,200), órdenes, bitácora de auditoría y documentos MongoDB.

Uso:
    python scripts/generar_dataset_masivo.py --modo masivo --reset
    python scripts/generar_dataset_masivo.py --modo demo-rapida --reset
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import random
import sys
import time
import uuid

from dotenv import load_dotenv
import psycopg

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

load_dotenv(RAIZ / ".env")

# Vector semanal (lunes=0 … domingo=6): martes ×0.7, viernes/sábado ×1.6
VECTOR_SEMANAL: dict[int, float] = {
    0: 0.85,
    1: 0.70,
    2: 0.85,
    3: 0.95,
    4: 1.60,
    5: 1.60,
    6: 1.25,
}

LOCACIONES_GPS: list[tuple[str, str, str, float, float]] = [
    ("CEDIS",  "CEDIS Central",               "Querétaro",               20.6040, -100.4040),
    ("CEDIS",  "CEDIS Norte",                 "Monterrey",               25.7700, -100.2450),
    ("Tienda", "Tienda San Pedro",            "San Pedro Garza García",  25.6575, -100.4020),
    ("Tienda", "Tienda Cumbres",              "Monterrey",               25.7290, -100.3940),
    ("Tienda", "Tienda Valle Oriente",        "San Pedro Garza García",  25.6500, -100.3360),
    ("Tienda", "Tienda Centro",               "Saltillo",                25.4232, -101.0053),
    ("Tienda", "Tienda Sur",                  "Monterrey",               25.6200, -100.2750),
    ("Tienda", "Tienda Guadalajara Prov.",    "Guadalajara",             20.6996, -103.3852),
    ("Tienda", "Tienda CDMX Polanco",         "Ciudad de México",        19.4335,  -99.1945),
    ("Tienda", "Tienda Puebla Angelópolis",   "Puebla",                  19.0279,  -98.2340),
    ("Tienda", "Tienda León Campestre",       "León",                    21.1520, -101.6940),
    ("Tienda", "Tienda Mérida Altabrisa",     "Mérida",                  21.0185,  -89.5844),
]

CATEGORIAS_CATALOGO: list[tuple[str, str, tuple[int, int], tuple[float, float], list[str]]] = [
    (
        "Panadería", "PAA", (2, 4), (12.0, 48.0),
        ["Bolillo Artesanal", "Pan Integral", "Croissant Mantequilla", "Baguette Rústica",
         "Concha Vainilla", "Pan de Caja Blanco", "Chapata Multigrano", "Medialuna"],
    ),
    (
        "Carnes", "CRN", (3, 5), (48.0, 145.0),
        ["Pechuga de Pollo", "Molida de Res", "Bistec Diezmillo", "Filete Salmón",
         "Pierna de Cerdo", "Pechuga Pavo", "Arrachera Marinada", "Filete Tilapia"],
    ),
    (
        "Verduras", "VFR", (5, 9), (7.0, 32.0),
        ["Espinaca Baby", "Tomate Bola", "Lechuga Romana", "Brócoli Fresco",
         "Calabacita Italiana", "Cilantro Manojo", "Champiñón Blanco", "Pimiento Morrón"],
    ),
    (
        "Frutas", "FDB", (5, 9), (9.0, 44.0),
        ["Fresa Orgánica", "Manzana Gala", "Plátano Chiapas", "Aguacate Hass",
         "Arándano Azul", "Mango Ataúlfo", "Uva Roja sin Semilla", "Papaya Maradol"],
    ),
    (
        "Lácteos", "LDN", (10, 14), (16.0, 72.0),
        ["Leche Entera", "Yogur Natural", "Queso Panela", "Crema Ácida",
         "Leche Deslactosada", "Queso Oaxaca", "Mantequilla Sin Sal", "Kéfir Natural"],
    ),
]

UNIDADES_POR_CAT = {
    "Panadería": "Pieza",
    "Carnes": "Kg",
    "Verduras": "Kg",
    "Frutas": "Kg",
    "Lácteos": "Pieza",
}

MODOS_CONFIG: dict[str, dict] = {
    "demo-rapida": {
        "tiendas": 10,
        "dias": 90,
        "skus": 200,
        "usuarios": 400,
        "ordenes": 800,
        "lineas_por_oc": 5,
        "eventos": 25000,
        "docs_mongo": 1500,
        "kardex_dias": None,
        "lineas_por_ticket": 5,
    },
    "masivo": {
        "tiendas": 10,
        "dias": 365,
        "skus": 200,
        "usuarios": 1200,
        "ordenes": 3000,
        "lineas_por_oc": 10,
        "eventos": 100000,
        "docs_mongo": 6000,
        "kardex_dias": None,
        "lineas_por_ticket": 5,
    },
    "rubrica": {
        "tiendas": 50,
        "dias": 730,
        "skus": 200,
        "usuarios": 2000,
        "ordenes": 18250,         # 50 tiendas × 365 días
        "lineas_por_oc": 50,      # 18,250 × 50 = 912,500 líneas de OC (streaming)
        "eventos": 150000,
        "docs_mongo": 6500,       # 5,000+ docs JSON (backtests, A/B, drift, ASN)
        "kardex_dias": 50,        # ~650,000–850,000 eventos FEFO acotados en kardex
        "lineas_por_ticket": 10,  # agrupa canastas de ~10 líneas para cuidar RAM/disco en venta
    },
}

CIUDADES_EXPANSION_MX: list[tuple[str, float, float]] = [
    ("Monterrey",              25.6866, -100.3161),
    ("San Pedro Garza García", 25.6573, -100.4027),
    ("Guadalajara",            20.6597, -103.3496),
    ("Zapopan",                20.7214, -103.3918),
    ("Ciudad de México",       19.4326,  -99.1332),
    ("Puebla",                 19.0414,  -98.2063),
    ("Querétaro",              20.5888, -100.3899),
    ("Saltillo",               25.4232, -101.0053),
    ("León",                   21.1221, -101.6826),
    ("Mérida",                 20.9674,  -89.5926),
    ("Tijuana",                32.5149, -117.0382),
    ("Cancún",                 21.1619,  -86.8515),
    ("Toluca",                 19.2826,  -99.6557),
    ("Aguascalientes",         21.8853, -102.2916),
    ("San Luis Potosí",        22.1565, -100.9855),
]


def generar_locaciones_gps(n_tiendas: int = 10) -> list[tuple[str, str, str, float, float]]:
    """
    Devuelve 2 CEDIS + `n_tiendas` tiendas con coordenadas GPS WGS84 válidas en México.
    Preserva intactas las 12 ubicaciones originales de `LOCACIONES_GPS`.
    """
    n_req = max(1, int(n_tiendas))
    cedis = [loc for loc in LOCACIONES_GPS if loc[0] == "CEDIS"]
    tiendas_base = [loc for loc in LOCACIONES_GPS if loc[0] == "Tienda"]
    if n_req <= len(tiendas_base):
        return cedis + tiendas_base[:n_req]

    salida = list(cedis) + list(tiendas_base)
    rng_geo = random.Random(20261124)
    for k in range(len(tiendas_base) + 1, n_req + 1):
        ciudad, lat_c, lon_c = CIUDADES_EXPANSION_MX[(k - 1) % len(CIUDADES_EXPANSION_MX)]
        lat = round(min(32.9, max(14.5, lat_c + rng_geo.uniform(-0.045, 0.045))), 6)
        lon = round(min(-86.5, max(-117.5, lon_c + rng_geo.uniform(-0.045, 0.045))), 6)
        nombre = f"Tienda {ciudad} Suc. {k:02d}"
        salida.append(("Tienda", nombre, ciudad, lat, lon))
    return salida


def url_psycopg() -> str:
    url = os.getenv("ETL_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("Falta ETL_DATABASE_URL o DATABASE_URL en el entorno.")
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+psycopg2://", "postgresql://"
    )


def poisson(lam: float, rng: random.Random) -> int:
    """Muestreo Poisson exacto con estado local `rng` (sin estado global)."""
    if lam <= 0:
        return 0
    if lam < 30.0:
        limit = math.exp(-lam)
        k = 0
        p = 1.0
        while p > limit:
            k += 1
            p *= rng.random()
        return k - 1
    # Aproximación normal acotada para lambdas grandes
    return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))


def generar_catalogo_200_skus(n_skus: int = 200, seed: int = 20261123) -> list[dict]:
    """
    Genera exactamente `n_skus` productos perecederos (vida útil fija 2..14 días)
    distribuidos en:
      - 50% ESTABLE_ESTACIONAL
      - 20% DRIFT_TENDENCIA (mitad escalón reciente ±45%, mitad rampa 60d ±40%)
      - 20% INTERMITENTE (60% días en 0 + picos 1-3 u.)
      - 10% QUIEBRE_STOCK (bloques de 5 días seguidos en 0)
    """
    rng = random.Random(seed)
    n_estable = round(n_skus * 0.50)
    n_drift = round(n_skus * 0.20)
    n_interm = round(n_skus * 0.20)
    n_quiebre = max(1, n_skus - n_estable - n_drift - n_interm)
    while n_estable + n_drift + n_interm + n_quiebre > n_skus:
        n_estable -= 1

    perfiles: list[tuple[str, str]] = []
    perfiles.extend([("ESTABLE_ESTACIONAL", "estable")] * n_estable)
    mitad_drift = n_drift // 2
    perfiles.extend([("DRIFT_TENDENCIA", "escalon_reciente")] * mitad_drift)
    perfiles.extend([("DRIFT_TENDENCIA", "rampa_60d")] * (n_drift - mitad_drift))
    perfiles.extend([("INTERMITENTE", "intermitente")] * n_interm)
    perfiles.extend([("QUIEBRE_STOCK", "quiebre")] * n_quiebre)
    rng.shuffle(perfiles)

    productos: list[dict] = []
    for idx in range(n_skus):
        cat, pref_prov, (vmin, vmax), (cmin, cmax), bases = CATEGORIAS_CATALOGO[
            idx % len(CATEGORIAS_CATALOGO)
        ]
        nombre_base = bases[(idx // len(CATEGORIAS_CATALOGO)) % len(bases)]
        variante = idx // (len(CATEGORIAS_CATALOGO) * len(bases)) + 1
        presentacion = ["250g", "400g", "500g", "750g", "1kg", "Sel.", "Org.", "Pack"][
            (idx + variante) % 8
        ]
        nombre = f"{nombre_base} {presentacion} #{idx + 1:03d}"

        vida = rng.randint(vmin, vmax)
        costo = round(rng.uniform(cmin, cmax), 2)
        margen = rng.uniform(1.32, 1.72)
        venta = round(costo * margen, 2)
        perfil, subtipo = perfiles[idx]

        if perfil == "ESTABLE_ESTACIONAL":
            lam = round(rng.uniform(16.0, 25.0), 1)
        elif perfil == "DRIFT_TENDENCIA":
            lam = round(rng.uniform(15.0, 24.0), 1)
        elif perfil == "INTERMITENTE":
            lam = 1.6  # picos de 1-3 unidades
        else:
            lam = round(rng.uniform(22.0, 32.0), 1)

        direccion_drift = 1 if (idx % 2 == 0) else -1
        productos.append(
            {
                "indice": idx,
                "codigo_gtin": f"075099{idx + 1:08d}",
                "nombre": nombre,
                "categoria": cat,
                "prefijo_prov": pref_prov,
                "vida_util_estandar": vida,
                "unidad_medida": UNIDADES_POR_CAT[cat],
                "precio_costo": costo,
                "precio_venta": venta,
                "moq_lote": float(rng.choice([10, 15, 20, 25, 30])),
                "stock_seguridad": round(lam * 1.5, 2),
                "punto_reorden": round(lam * 2.5, 2),
                "perfil_demanda": perfil,
                "subtipo": subtipo,
                "lambda_base": lam,
                "direccion_drift": direccion_drift,
            }
        )
    return productos


def demanda_dia_perfil(
    sku_cfg: dict,
    dia: date,
    dia_idx: int,
    total_dias: int,
    rng: random.Random,
) -> tuple[int, bool]:
    """
    Calcula (demanda_del_dia, en_quiebre) para el día `dia_idx` (0..total_dias-1)
    según uno de los 4 perfiles estadísticos.
    """
    subtipo = sku_cfg["subtipo"]
    lam = float(sku_cfg["lambda_base"])
    factor_sem = VECTOR_SEMANAL[dia.weekday()]
    restantes = (total_dias - 1) - dia_idx

    if subtipo == "estable":
        return poisson(lam * factor_sem, rng), False

    if subtipo == "escalon_reciente":
        # Últimos 16 días: salto brusco ±45% para disparar alerta PSI / z-score en Etapa 1
        mult = (1.48 if sku_cfg["direccion_drift"] > 0 else 0.52) if restantes < 16 else 1.0
        return poisson(lam * factor_sem * mult, rng), False

    if subtipo == "rampa_60d":
        # Últimos 60 días: tendencia progresiva ±40% para ETS_HOLT_WINTERS en Etapa 2
        if restantes < 60:
            avance = (60 - restantes) / 60.0
            mult = 1.0 + (0.45 * sku_cfg["direccion_drift"] * avance)
        else:
            mult = 1.0
        return poisson(max(1.0, lam * factor_sem * mult), rng), False

    if subtipo == "intermitente":
        # 60% de los días en 0 y 40% con picos de 1–3 unidades
        if rng.random() < 0.60:
            return 0, False
        return rng.randint(1, 3), False

    if subtipo == "quiebre":
        # Inyecta bloques exactos de 5 días seguidos en 0 (histórico + reciente)
        bloque_reciente = 2 <= restantes <= 6
        bloque_medio = total_dias >= 70 and (35 <= (dia_idx % 50) <= 39)
        if bloque_reciente or bloque_medio:
            return 0, True
        return poisson(lam * factor_sem, rng), False

    return poisson(lam * factor_sem, rng), False


def simular_serie_fefo_sku(
    sku_cfg: dict,
    id_locacion: int,
    fecha_inicio: date,
    dias: int,
    rng: random.Random,
    *,
    prefijo_prov: str,
    usuario_id,
    seq_lote: dict[str, int],
    kardex_desde: date | None = None,
) -> dict:
    """
    Simula `dias + 1` días de operación FEFO estricta para un SKU en una tienda.
    Cada lote tiene vida útil fija (`sku_cfg['vida_util_estandar']` entre 2 y 14 días)
    y el consumo diario descuenta siempre del lote vigente más antiguo.
    Si `kardex_desde` se especifica, solo acumula eventos de kardex a partir de esa fecha
    sin alterar lotes, existencias, mermas ni ventas históricas.
    """
    sku = sku_cfg["id_sku"]
    vida = int(sku_cfg["vida_util_estandar"])
    costo = float(sku_cfg["precio_costo"])
    precio = float(sku_cfg["precio_venta"])
    lam = float(sku_cfg["lambda_base"])
    punto_reorden = float(sku_cfg.get("punto_reorden") or lam * 2.5)
    moq = float(sku_cfg.get("moq_lote") or 10.0)
    id_prov = sku_cfg["id_proveedor"]

    cobertura = min(5.5, max(2.0, vida * 0.65))
    objetivo = max(moq, round(lam * cobertura))
    if sku_cfg["subtipo"] == "intermitente":
        punto_reorden = max(2.0, lam * 2.0)
        objetivo = max(6.0, round(lam * min(5.0, vida * 0.7)))

    activos: list[dict] = []
    lotes: list[tuple] = []
    existencias: dict[tuple, float] = {}
    ventas_lineas: list[dict] = []
    mermas: list[tuple] = []
    movimientos: list[tuple] = []

    def recibir(dia: date, cantidad: float) -> None:
        cant = float(max(1, int(round(cantidad))))
        clave = f"{prefijo_prov}-{id_locacion}-{dia.strftime('%y%m%d')}"
        seq_lote[clave] = seq_lote.get(clave, 0) + 1
        codigo = f"{clave}-{seq_lote[clave]:03d}"[:50]
        f_cad = dia + timedelta(days=vida)
        f_prod = dia
        id_lote = uuid.uuid4()
        lote = {
            "id_lote": id_lote,
            "codigo": codigo,
            "f_cad": f_cad,
            "costo": costo,
            "restante": cant,
        }
        activos.append(lote)
        momento_rec = datetime.combine(dia, datetime.min.time(), tzinfo=timezone.utc).replace(hour=6)
        lotes.append(
            (
                id_lote, sku, id_prov, codigo, f_prod, dia, f_cad,
                cant, costo, id_locacion, "DISPONIBLE", None, momento_rec,
            )
        )
        existencias[(id_lote, id_locacion)] = cant
        if kardex_desde is None or dia >= kardex_desde:
            movimientos.append(
                (id_lote, id_locacion, "RECEPCION", cant, cant, costo,
                 "LOTE", id_lote, usuario_id, momento_rec)
            )

    recibir(fecha_inicio, max(moq, round(objetivo * rng.uniform(0.75, 1.0))))
    total_dias = dias + 1

    for i in range(total_dias):
        dia = fecha_inicio + timedelta(days=i)

        # 1. Caducidad de lotes vencidos con saldo remanente
        for lote in list(activos):
            if lote["f_cad"] < dia and lote["restante"] > 0:
                cant = round(lote["restante"], 2)
                lote["restante"] = 0.0
                momento_m = datetime.combine(dia, datetime.min.time(), tzinfo=timezone.utc).replace(hour=7)
                mermas.append(
                    (lote["id_lote"], id_locacion, usuario_id, cant, "CADUCIDAD", costo, None, momento_m)
                )
                existencias[(lote["id_lote"], id_locacion)] = 0.0
                if kardex_desde is None or dia >= kardex_desde:
                    movimientos.append(
                        (lote["id_lote"], id_locacion, "MERMA", -cant, 0.0, costo,
                         "MERMA", None, usuario_id, momento_m)
                    )
                activos.remove(lote)

        demanda, en_quiebre = demanda_dia_perfil(sku_cfg, dia, i, total_dias, rng)

        # 2. Reposición normal (se suspende durante bloques de quiebre de stock)
        disponible = sum(l["restante"] for l in activos if l["f_cad"] >= dia)
        if not en_quiebre and disponible < punto_reorden:
            pedir_cant = max(moq, objetivo - disponible)
            recibir(dia, pedir_cant * rng.uniform(0.95, 1.08))

        if demanda <= 0 or en_quiebre:
            continue

        # 3. Consumo FEFO estricto: lote vigente más antiguo primero
        restante_dem = float(demanda)
        activos.sort(key=lambda l: (l["f_cad"], l["codigo"]))
        for lote in activos:
            if restante_dem <= 0:
                break
            if lote["f_cad"] < dia or lote["restante"] <= 0:
                continue
            toma = min(lote["restante"], restante_dem)
            if toma <= 0:
                continue
            lote["restante"] = round(lote["restante"] - toma, 2)
            restante_dem = round(restante_dem - toma, 2)
            existencias[(lote["id_lote"], id_locacion)] = lote["restante"]
            ventas_lineas.append(
                {
                    "dia": dia,
                    "id_sku": sku,
                    "id_lote": lote["id_lote"],
                    "cantidad": round(toma, 2),
                    "precio": precio,
                    "costo": costo,
                    "restante_lote": lote["restante"],
                }
            )

    fecha_fin = fecha_inicio + timedelta(days=dias)
    mermados = {m[0] for m in mermas}
    lotes_final: list[tuple] = []
    for lt in lotes:
        id_lt = lt[0]
        f_cad = lt[6]
        saldo = existencias.get((id_lt, id_locacion), 0.0)
        if saldo <= 0.0:
            estado_f = "MERMA" if id_lt in mermados else "AGOTADO"
        elif f_cad < fecha_fin:
            estado_f = "VENCIDO"
        else:
            estado_f = "DISPONIBLE"
        lotes_final.append((*lt[:10], estado_f, *lt[11:]))

    return {
        "lotes": lotes_final,
        "existencias": existencias,
        "ventas_lineas": ventas_lineas,
        "mermas": mermas,
        "movimientos": movimientos,
    }


def _copiar(cur, tabla: str, columnas: list[str], filas: list[tuple]) -> int:
    if not filas:
        return 0
    sentencia = f"COPY {tabla} ({', '.join(columnas)}) FROM STDIN"
    with cur.copy(sentencia) as cp:
        for f in filas:
            cp.write_row(f)
    return len(filas)


def _copiar_en_lotes(
    cur,
    tabla: str,
    columnas: list[str],
    filas: list[tuple],
    chunk_size: int = 50000,
) -> int:
    total = 0
    for ini in range(0, len(filas), chunk_size):
        total += _copiar(cur, tabla, columnas, filas[ini:ini + chunk_size])
    return total


def _limpiar_previo(cur) -> None:
    tablas = (
        "analitica.experimento_ab_bitacora",
        "analitica.experimento_ab_asignacion",
        "analitica.experimento_ab",
        "analitica.desperdicio_evitado",
        "analitica.descuento",
        "analitica.transferencia",
        "analitica.alerta",
        "operacion.recepcion_etiqueta",
        "operacion.orden_compra_detalle",
        "operacion.orden_compra",
        "analitica.orden_reabastecimiento",
        "analitica.forecast_result",
        "analitica.forecast_run",
        "operacion.movimiento_inventario",
        "operacion.merma",
        "operacion.venta_detalle",
        "operacion.venta",
        "operacion.existencia",
        "operacion.lote",
    )
    for t in tablas:
        cur.execute(f"DELETE FROM {t}")
    cur.execute("DELETE FROM operacion.usuario WHERE email LIKE 'op_%@freshtrack.mx'")
    cur.execute("DELETE FROM operacion.producto WHERE codigo_gtin LIKE '075099%'")
    cur.execute("DELETE FROM auditoria.bitacora_eventos WHERE descripcion LIKE '[BENCH]%'")


def _sembrar_locaciones_y_usuarios(
    cur,
    n_tiendas: int,
    n_usuarios: int,
    rng: random.Random,
    reset: bool = False,
) -> tuple[list[dict], list[dict], list]:
    locaciones_objetivo = generar_locaciones_gps(n_tiendas)
    nombres_tiendas = [nom for tipo, nom, _, _, _ in locaciones_objetivo if tipo == "Tienda"]

    for tipo, nombre, ciudad, lat, lon in locaciones_objetivo:
        cur.execute(
            """
            INSERT INTO operacion.locacion (tipo_locacion, nombre, ciudad, latitud, longitud, activo)
            VALUES (%s, %s, %s, %s, %s, true)
            ON CONFLICT (nombre) DO UPDATE
               SET latitud = EXCLUDED.latitud,
                   longitud = EXCLUDED.longitud,
                   ciudad = EXCLUDED.ciudad,
                   activo = true
            """,
            (tipo, nombre, ciudad, lat, lon),
        )

    if reset and nombres_tiendas:
        cur.execute(
            """
            UPDATE operacion.locacion
               SET activo = (nombre = ANY(%s))
             WHERE tipo_locacion = 'Tienda'
            """,
            (nombres_tiendas,),
        )

    cur.execute(
        "SELECT id_locacion, nombre, tipo_locacion FROM operacion.locacion WHERE activo ORDER BY id_locacion"
    )
    locs = [{"id_locacion": r[0], "nombre": r[1], "tipo_locacion": r[2]} for r in cur.fetchall()]
    tiendas = [l for l in locs if l["tipo_locacion"] == "Tienda" and l["nombre"] in set(nombres_tiendas)]

    cur.execute("SELECT id_rol, clave FROM operacion.rol")
    roles = {r[1]: r[0] for r in cur.fetchall()}

    cur.execute("SELECT id_usuario, password_hash FROM operacion.usuario LIMIT 1")
    row_u = cur.fetchone()
    if not row_u:
        raise RuntimeError("Faltan usuarios base (ejecuta sql/07_seed_base.sql).")
    usuario_default_id, hash_reutilizable = row_u[0], row_u[1]

    cur.execute("SELECT COUNT(*) FROM operacion.usuario")
    actuales = cur.fetchone()[0]
    por_crear = max(0, n_usuarios - actuales)
    if por_crear > 0:
        roles_pool = [roles[k] for k in ("store_manager", "warehouse", "buyer", "planner", "auditor") if k in roles]
        filas_u = []
        base_idx = 1000
        for i in range(por_crear):
            loc_id = tiendas[i % len(tiendas)]["id_locacion"]
            rol_id = roles_pool[i % len(roles_pool)]
            filas_u.append(
                (
                    uuid.uuid4(),
                    rol_id,
                    loc_id,
                    f"Operador FreshTrack {i + 1:04d}",
                    f"op_{base_idx + i}@freshtrack.mx",
                    hash_reutilizable,
                    True,
                )
            )
        _copiar(
            cur,
            "operacion.usuario",
            ["id_usuario", "id_rol", "id_locacion", "nombre_completo", "email", "password_hash", "estado_activo"],
            filas_u,
        )

    cur.execute("SELECT id_usuario, id_locacion, email FROM operacion.usuario WHERE estado_activo = true")
    usuarios = [{"id_usuario": r[0], "id_locacion": r[1], "email": r[2]} for r in cur.fetchall()]
    return locs, tiendas, usuarios


def _sembrar_productos(cur, n_skus: int, seed: int) -> list[dict]:
    cur.execute("SELECT id_proveedor, rfc FROM operacion.proveedor WHERE activo = true")
    provs_por_rfc = {r[1]: r[0] for r in cur.fetchall()}
    mapa_prefijo_rfc = {
        "LDN": "LDN850312AA1",
        "FDB": "FDB920614BB2",
        "VFR": "VFR011030CC3",
        "CRN": "CRN781205DD4",
        "PAA": "PAA640918EE5",
    }
    prov_fallback = next(iter(provs_por_rfc.values()))

    catalogo = generar_catalogo_200_skus(n_skus=n_skus, seed=seed)
    for p in catalogo:
        id_prov = provs_por_rfc.get(mapa_prefijo_rfc.get(p["prefijo_prov"], ""), prov_fallback)
        p["id_proveedor"] = id_prov
        cur.execute(
            """
            INSERT INTO operacion.producto
                (codigo_gtin, nombre, id_proveedor, categoria, vida_util_estandar,
                 unidad_medida, precio_costo, precio_venta, stock_seguridad,
                 punto_reorden, moq_lote, perecedero, activo, perfil_demanda)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, true, %s)
            ON CONFLICT (codigo_gtin) DO UPDATE
               SET nombre = EXCLUDED.nombre,
                   id_proveedor = EXCLUDED.id_proveedor,
                   categoria = EXCLUDED.categoria,
                   vida_util_estandar = EXCLUDED.vida_util_estandar,
                   precio_costo = EXCLUDED.precio_costo,
                   precio_venta = EXCLUDED.precio_venta,
                   stock_seguridad = EXCLUDED.stock_seguridad,
                   punto_reorden = EXCLUDED.punto_reorden,
                   moq_lote = EXCLUDED.moq_lote,
                   perfil_demanda = EXCLUDED.perfil_demanda
            RETURNING id_sku
            """,
            (
                p["codigo_gtin"], p["nombre"], id_prov, p["categoria"],
                p["vida_util_estandar"], p["unidad_medida"], p["precio_costo"],
                p["precio_venta"], p["stock_seguridad"], p["punto_reorden"],
                p["moq_lote"], p["perfil_demanda"],
            ),
        )
        p["id_sku"] = cur.fetchone()[0]
    return catalogo


def _generar_ordenes_y_auditoria(
    cur,
    *,
    productos: list[dict],
    tiendas: list[dict],
    usuarios: list[dict],
    n_ordenes: int,
    lineas_por_oc: int,
    n_eventos: int,
    fecha_inicio: date,
    fecha_fin: date,
    rng: random.Random,
) -> dict[str, int]:
    u_id = usuarios[0]["id_usuario"]
    dias_span = max(1, (fecha_fin - fecha_inicio).days)
    n_skus = len(productos)
    n_lineas_oc = max(1, min(int(lineas_por_oc), n_skus))

    # 1. Sugerencias Newsvendor FEFO en analitica.orden_reabastecimiento (en lotes)
    n_reab = min(n_ordenes, max(400, len(tiendas) * 100))
    c_reab = 0
    filas_reab: list[tuple] = []
    cols_reab = [
        "id_orden", "id_sku", "id_locacion", "id_proveedor", "demanda_pronosticada",
        "inventario_fisico", "inventario_riesgo", "inventario_util", "stock_seguridad",
        "lead_time_dias", "moq", "necesidad_neta", "cantidad_sugerida", "prioridad",
        "estado", "explicacion", "id_usuario_solicita", "fecha_creacion",
    ]
    for i in range(n_reab):
        p = productos[i % n_skus]
        t = tiendas[(i // n_skus) % len(tiendas)]
        cant = round(p["lambda_base"] * 5, 2)
        f_crea = datetime.combine(fecha_inicio + timedelta(days=i % dias_span), datetime.min.time(), tzinfo=timezone.utc)
        filas_reab.append(
            (
                uuid.uuid4(), p["id_sku"], t["id_locacion"], p["id_proveedor"],
                cant, round(cant * 0.4, 2), round(cant * 0.1, 2), round(cant * 0.3, 2),
                p["stock_seguridad"], 2, p["moq_lote"], round(cant * 0.7, 2),
                max(p["moq_lote"], round(cant * 0.7, 2)),
                "ALTA" if i % 5 == 0 else ("MEDIA" if i % 2 == 0 else "BAJA"),
                "EJECUTADA" if i % 3 else "PENDIENTE",
                "Sugerencia generada por simulación masiva Newsvendor FEFO",
                u_id, f_crea,
            )
        )
        if len(filas_reab) >= 5000:
            c_reab += _copiar(cur, "analitica.orden_reabastecimiento", cols_reab, filas_reab)
            filas_reab.clear()
    if filas_reab:
        c_reab += _copiar(cur, "analitica.orden_reabastecimiento", cols_reab, filas_reab)
        filas_reab.clear()
    cur.connection.commit()

    # 2. Órdenes de Compra reales multi-línea en streaming (500 OCs por flush ≈ 25k líneas)
    cols_oc = [
        "id_oc", "folio", "id_proveedor", "id_usuario", "estado", "total_lotes",
        "total_unidades", "subtotal", "total", "fecha_creacion",
    ]
    cols_ocd = [
        "id_detalle", "id_oc", "id_sku", "id_locacion_destino", "cantidad_lotes",
        "unidades_por_lote", "cantidad_unidades", "precio_unitario", "subtotal",
        "sugerencia_newsvendor",
    ]
    c_oc = 0
    c_ocd = 0
    filas_oc: list[tuple] = []
    filas_ocd: list[tuple] = []

    for i in range(n_ordenes):
        t = tiendas[i % len(tiendas)]
        base_sku = (i * 7) % n_skus
        prov_id = productos[base_sku]["id_proveedor"]
        id_oc = uuid.uuid4()
        f_crea = datetime.combine(
            fecha_inicio + timedelta(days=(i // max(1, len(tiendas))) % dias_span),
            datetime.min.time(),
            tzinfo=timezone.utc,
        ).replace(hour=8 + (i % 10))
        tot_lotes = 0
        tot_unid = 0.0
        tot_sub = 0.0
        for j in range(n_lineas_oc):
            p = productos[(base_sku + j) % n_skus]
            lotes_n = rng.randint(1, 4)
            u_lote = float(p["moq_lote"])
            u_tot = round(lotes_n * u_lote, 2)
            sub_ln = round(u_tot * p["precio_costo"], 2)
            sug_nv = round(u_tot * rng.uniform(0.88, 1.05), 2)
            tot_lotes += lotes_n
            tot_unid += u_tot
            tot_sub += sub_ln
            filas_ocd.append(
                (
                    uuid.uuid4(), id_oc, p["id_sku"], t["id_locacion"],
                    lotes_n, u_lote, u_tot, p["precio_costo"], sub_ln, sug_nv,
                )
            )

        filas_oc.append(
            (
                id_oc, f"OC-MAS-{i + 1:06d}", prov_id, u_id,
                "RECIBIDA" if i % 4 else "EMITIDA",
                tot_lotes, round(tot_unid, 2), round(tot_sub, 2), round(tot_sub, 2), f_crea,
            )
        )
        if len(filas_oc) >= 500:
            c_oc += _copiar(cur, "operacion.orden_compra", cols_oc, filas_oc)
            c_ocd += _copiar(cur, "operacion.orden_compra_detalle", cols_ocd, filas_ocd)
            filas_oc.clear()
            filas_ocd.clear()
            cur.connection.commit()

    if filas_oc:
        c_oc += _copiar(cur, "operacion.orden_compra", cols_oc, filas_oc)
        c_ocd += _copiar(cur, "operacion.orden_compra_detalle", cols_ocd, filas_ocd)
        filas_oc.clear()
        filas_ocd.clear()
        cur.connection.commit()

    # 3. Eventos masivos en auditoria.bitacora_eventos (en bloques de 25,000)
    acciones = [
        ("REGISTER_SALE", "INSERT", "venta"),
        ("RECEIVE_INVENTORY", "INSERT", "lote"),
        ("RUN_FORECAST", "INSERT", "forecast_run"),
        ("CREATE_REPLENISHMENT", "INSERT", "orden_reabastecimiento"),
        ("REGISTER_SHRINKAGE", "INSERT", "merma"),
    ]
    insertados_ev = 0
    bloque: list[tuple] = []
    cols_ev = [
        "id_evento", "fecha_evento", "accion", "tipo_operacion", "nombre_tabla",
        "id_registro", "id_usuario_app", "usuario_email", "descripcion",
    ]
    for i in range(n_eventos):
        acc, t_op, tbl = acciones[i % len(acciones)]
        u = usuarios[i % len(usuarios)]
        f_ev = datetime.combine(
            fecha_inicio + timedelta(days=i % dias_span), datetime.min.time(), tzinfo=timezone.utc
        ).replace(hour=i % 24, minute=i % 60)
        bloque.append(
            (
                uuid.uuid4(), f_ev, acc, t_op, tbl, str(i + 1),
                u["id_usuario"], u["email"], f"[BENCH] Evento operativo masivo #{i + 1}",
            )
        )
        if len(bloque) >= 25000:
            insertados_ev += _copiar(cur, "auditoria.bitacora_eventos", cols_ev, bloque)
            bloque.clear()
            cur.connection.commit()
    if bloque:
        insertados_ev += _copiar(cur, "auditoria.bitacora_eventos", cols_ev, bloque)
        bloque.clear()
        cur.connection.commit()

    return {
        "ordenes_reabastecimiento": c_reab,
        "ordenes_compra_cabeceras": c_oc,
        "ordenes_compra_lineas": c_ocd,
        "ordenes_compra": c_oc + c_ocd,
        "eventos_auditoria": insertados_ev,
    }


def _cargar_mongodb(
    *,
    productos: list[dict],
    tiendas: list[dict],
    n_docs: int,
    reset: bool,
    rng: random.Random,
) -> dict[str, int]:
    from app.services import doc_store

    db = doc_store.get_mongo_db()
    if db is None:
        return {"pronosticos_demanda": 0, "avisos_asn": 0, "alertas_operativas": 0}

    if reset:
        db.pronosticos_demanda.delete_many({})
        db.avisos_asn.delete_many({})
        db.alertas_operativas.delete_many({})

    n_pron = int(n_docs * 0.45)
    n_asn = int(n_docs * 0.25)
    n_al = max(1, n_docs - n_pron - n_asn)
    ahora = datetime.now(timezone.utc)
    tipos_snap = ("backtest_auto", "snapshot_ab_test", "inferencia_produccion")

    # 1. pronosticos_demanda (reportes de backtest AUTO + snapshots A/B + inferencia)
    docs_pron = []
    ins_pron = 0
    for i in range(n_pron):
        p = productos[i % len(productos)]
        t = tiendas[(i // len(productos)) % len(tiendas)]
        f_calc = ahora - timedelta(days=i % 45)
        puntos = [
            {
                "fecha": f_calc + timedelta(days=h),
                "demanda_pronosticada": round(max(0.0, p["lambda_base"] * VECTOR_SEMANAL[(f_calc + timedelta(days=h)).weekday()]), 2),
                "intervalo_inferior": round(max(0.0, p["lambda_base"] * 0.8), 2),
                "intervalo_superior": round(p["lambda_base"] * 1.25, 2),
                "percentil": 50,
            }
            for h in range(1, 8)
        ]
        modelo_doc = "ETS_HOLT_WINTERS" if p["perfil_demanda"] == "DRIFT_TENDENCIA" else "SUAVIZACION_EXPONENCIAL"
        docs_pron.append(
            {
                "id_sku": int(p["id_sku"]),
                "id_locacion": int(t["id_locacion"]),
                "fecha_calculo": f_calc,
                "horizonte_proyeccion": {
                    "fecha_inicio": puntos[0]["fecha"],
                    "fecha_fin": puntos[-1]["fecha"],
                    "dias": 7,
                },
                "modelo": modelo_doc,
                "version_modelo": "1.0",
                "linaje": {
                    "hash_entrada": f"bench-{i}",
                    "ventana_entrenamiento_dias": 120,
                    "generado_por": "benchmark",
                    "tipo_documento": tipos_snap[i % len(tipos_snap)],
                    "grupo_ab": "TRATAMIENTO" if i % 2 else "CONTROL",
                },
                "metricas": {
                    "mae": round(rng.uniform(1.2, 4.5), 2),
                    "rmse": round(rng.uniform(1.8, 5.8), 2),
                    "wmape": round(rng.uniform(8.0, 22.0), 2),
                    "fva_pp": round(rng.uniform(1.5, 9.5), 2),
                    "bias": round(rng.uniform(-1.2, 1.2), 2),
                },
                "backtest_resumen": {
                    "modelo_ganador": modelo_doc,
                    "merma_simulada_valor": round(rng.uniform(45.0, 420.0), 2),
                    "costo_newsvendor": round(rng.uniform(90.0, 680.0), 2),
                },
                "puntos": puntos,
                "version_esquema": 1,
            }
        )
        if len(docs_pron) >= 500:
            ins_pron += len(db.pronosticos_demanda.insert_many(docs_pron).inserted_ids)
            docs_pron.clear()
    if docs_pron:
        ins_pron += len(db.pronosticos_demanda.insert_many(docs_pron).inserted_ids)

    # 2. avisos_asn (2 SKUs por embarque)
    docs_asn = []
    ins_asn = 0
    estados_asn = ("ANUNCIADO", "EN_TRANSITO", "RECIBIDO")
    prefijo_run = uuid.uuid4().hex[:6].upper()
    for i in range(n_asn):
        p = productos[i % len(productos)]
        p2 = productos[(i + 1) % len(productos)]
        f_emb = ahora - timedelta(days=i % 90)
        docs_asn.append(
            {
                "folio_asn": f"ASN-MAS-{prefijo_run}-{i + 1:06d}",
                "id_proveedor": int(p["id_proveedor"]),
                "fecha_embarque": f_emb,
                "fecha_arribo_estimada": f_emb + timedelta(days=2),
                "estado": estados_asn[i % len(estados_asn)],
                "detalle_carga": [
                    {
                        "id_sku": int(p["id_sku"]),
                        "cantidad_declarada": float(p["moq_lote"] * 2),
                        "lote_proveedor": f"LP-{i + 1:06d}-A",
                        "fecha_caducidad": f_emb + timedelta(days=int(p["vida_util_estandar"])),
                    },
                    {
                        "id_sku": int(p2["id_sku"]),
                        "cantidad_declarada": float(p2["moq_lote"]),
                        "lote_proveedor": f"LP-{i + 1:06d}-B",
                        "fecha_caducidad": f_emb + timedelta(days=int(p2["vida_util_estandar"])),
                    },
                ],
                "inspecciones": [],
                "version_esquema": 1,
            }
        )
        if len(docs_asn) >= 500:
            ins_asn += len(db.avisos_asn.insert_many(docs_asn).inserted_ids)
            docs_asn.clear()
    if docs_asn:
        ins_asn += len(db.avisos_asn.insert_many(docs_asn).inserted_ids)

    # 3. alertas_operativas (bitácora JSON de drift y alertas pre-merma)
    docs_al = []
    ins_al = 0
    tipos_al = ("RIESGO_PRE_MERMA", "RUPTURA_CADENA_FRIO", "EXCESO_COBERTURA")
    crits_al = ("INFO", "WARNING", "CRITICAL")
    for i in range(n_al):
        p = productos[i % len(productos)]
        t = tiendas[(i // len(productos)) % len(tiendas)]
        docs_al.append(
            {
                "tipo": tipos_al[i % len(tipos_al)],
                "criticidad": crits_al[i % len(crits_al)],
                "id_sku": int(p["id_sku"]),
                "id_locacion": int(t["id_locacion"]),
                "mensaje": f"Bitácora operativa/drift #{i + 1} para {p['nombre']}",
                "generada_en": ahora - timedelta(hours=i % 720),
                "atendida": bool(i % 3 == 0),
                "contexto": {
                    "tipo_auditoria": "bitacora_drift",
                    "perfil": p["perfil_demanda"],
                    "psi": round(rng.uniform(0.05, 0.45), 3),
                    "z_nivel": round(rng.uniform(-3.5, 3.5), 2),
                    "cambio_nivel_pct": round(rng.uniform(-45.0, 48.0), 1),
                    "dias_restantes": (i % 5) + 1,
                },
                "version_esquema": 1,
            }
        )
        if len(docs_al) >= 500:
            ins_al += len(db.alertas_operativas.insert_many(docs_al).inserted_ids)
            docs_al.clear()
    if docs_al:
        ins_al += len(db.alertas_operativas.insert_many(docs_al).inserted_ids)

    return {"pronosticos_demanda": ins_pron, "avisos_asn": ins_asn, "alertas_operativas": ins_al}



def _refrescar_agregados(conn) -> None:
    """
    Refresca la demanda diaria materializada (sql/08_optimizacion.sql).

    La carga usa session_replication_role=replica, así que el trigger que marca
    el histórico como "sucio" no se dispara: sin este refresco, las ventas
    cargadas no aparecerían en analitica.v_demanda_diaria (pronóstico, alertas,
    reabastecimiento). Si la base aún no tiene 08_optimizacion.sql, no hace nada.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regprocedure('analitica.fn_refrescar_agregados()') IS NOT NULL")
            if not cur.fetchone()[0]:
                return
            cur.execute("SELECT analitica.fn_refrescar_agregados()")
            ms = cur.fetchone()[0]
        conn.commit()
        print(f"[MASIVO] Demanda diaria materializada refrescada en {ms} ms.")
    except psycopg.Error as e:
        conn.rollback()
        print(f"[MASIVO] AVISO: no se pudo refrescar la demanda materializada: {e}")

def main() -> int:
    ap = argparse.ArgumentParser(description="Generador masivo multi-perfil para FreshTrack")
    ap.add_argument("--modo", choices=("demo-rapida", "masivo", "rubrica"), default="masivo")
    ap.add_argument("--tiendas", type=int, default=None)
    ap.add_argument("--dias", type=int, default=None)
    ap.add_argument("--skus", type=int, default=None)
    ap.add_argument("--usuarios", type=int, default=None)
    ap.add_argument("--ordenes", type=int, default=None)
    ap.add_argument("--lineas-por-oc", type=int, default=None)
    ap.add_argument("--lineas-por-ticket", type=int, default=None)
    ap.add_argument("--kardex-dias", type=int, default=None)
    ap.add_argument("--eventos", type=int, default=None)
    ap.add_argument("--docs-mongo", type=int, default=None)
    ap.add_argument("--seed", type=int, default=20261123)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--sin-mongo", action="store_true")
    ap.add_argument("--salida-metricas", default="docs/ingesta_resultados.json")
    args = ap.parse_args()

    defaults = MODOS_CONFIG[args.modo]
    n_tiendas = args.tiendas if args.tiendas is not None else defaults["tiendas"]
    dias = args.dias if args.dias is not None else defaults["dias"]
    n_skus = args.skus if args.skus is not None else defaults["skus"]
    n_usuarios = args.usuarios if args.usuarios is not None else defaults["usuarios"]
    n_ordenes = args.ordenes if args.ordenes is not None else defaults["ordenes"]
    lineas_por_oc = args.lineas_por_oc if args.lineas_por_oc is not None else defaults["lineas_por_oc"]
    lineas_por_ticket = max(1, args.lineas_por_ticket if args.lineas_por_ticket is not None else defaults["lineas_por_ticket"])
    kardex_dias = args.kardex_dias if args.kardex_dias is not None else defaults["kardex_dias"]
    n_eventos = args.eventos if args.eventos is not None else defaults["eventos"]
    n_docs_mongo = args.docs_mongo if args.docs_mongo is not None else defaults["docs_mongo"]

    rng = random.Random(args.seed)
    fecha_fin = date.today()
    fecha_inicio = fecha_fin - timedelta(days=dias)
    kardex_desde = (fecha_fin - timedelta(days=kardex_dias)) if (kardex_dias and kardex_dias > 0) else None
    t_total_0 = time.perf_counter()

    print(
        f"[MASIVO] Modo={args.modo} | {n_tiendas} tiendas × {n_skus} SKUs × {dias} días | "
        f"{n_usuarios} usuarios | {n_ordenes} OCs ({lineas_por_oc} lín/OC) | {n_docs_mongo} docs Mongo"
        + (f" | kardex últimos {kardex_dias}d" if kardex_desde else "")
    )
    totales = {
        "lotes": 0, "existencias": 0, "ventas": 0, "venta_detalle": 0,
        "mermas": 0, "movimientos": 0,
        "ordenes_reabastecimiento": 0, "ordenes_compra_cabeceras": 0,
        "ordenes_compra_lineas": 0, "ordenes": 0, "eventos_auditoria": 0,
    }

    with psycopg.connect(url_psycopg()) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SET session_replication_role = replica")
            except psycopg.Error:
                conn.rollback()

            if args.reset:
                print("[MASIVO] Limpiando operación previa...")
                _limpiar_previo(cur)
                conn.commit()

            t_cat0 = time.perf_counter()
            _, tiendas, usuarios = _sembrar_locaciones_y_usuarios(
                cur, n_tiendas, n_usuarios, rng, reset=args.reset
            )
            productos = _sembrar_productos(cur, n_skus, args.seed)
            conn.commit()
            t_cat = round(time.perf_counter() - t_cat0, 3)
            print(f"[MASIVO] Catálogos listos en {t_cat}s: {len(tiendas)} tiendas GPS, {len(productos)} SKUs, {len(usuarios)} usuarios.")

            usuario_op = usuarios[0]["id_usuario"]
            seq_lote: dict[str, int] = {}
            seq_folio: dict[str, int] = {}
            fraccionar_intradia = args.modo == "rubrica"

            indices_secundarios = [
                ("operacion", "idx_vd_serie", "operacion.venta_detalle (id_sku, id_locacion, fecha_transaccion)"),
                ("operacion", "idx_vd_fecha", "operacion.venta_detalle (fecha_transaccion DESC)"),
                ("operacion", "idx_vd_lote", "operacion.venta_detalle (id_lote)"),
                ("operacion", "idx_vd_loc_fecha", "operacion.venta_detalle (id_locacion, fecha_transaccion DESC)"),
                ("operacion", "idx_vd_venta", "operacion.venta_detalle (id_venta)"),
                ("operacion", "idx_mov_lote", "operacion.movimiento_inventario (id_lote, fecha DESC)"),
                ("operacion", "idx_mov_fecha", "operacion.movimiento_inventario (fecha DESC)"),
                ("operacion", "idx_mov_tipo", "operacion.movimiento_inventario (tipo, fecha DESC)"),
                ("operacion", "idx_mov_loc_fecha", "operacion.movimiento_inventario (id_locacion, fecha DESC)"),
            ]
            indices_soltados = False
            if args.modo == "rubrica" and args.reset:
                print("[MASIVO] Soltando índices secundarios de alto volumen para acelerar COPY...")
                for schema_idx, nombre_idx, _ in indices_secundarios:
                    cur.execute(f"DROP INDEX IF EXISTS {schema_idx}.{nombre_idx}")
                conn.commit()
                indices_soltados = True

            t_stream0 = time.perf_counter()
            for idx_t, tienda in enumerate(tiendas, 1):
                id_loc = tienda["id_locacion"]
                t_lotes: list[tuple] = []
                t_exist: dict[tuple, float] = {}
                t_lineas_por_dia: dict[date, list[dict]] = {}
                t_mermas: list[tuple] = []
                t_movs: list[tuple] = []

                for prod in productos:
                    sim = simular_serie_fefo_sku(
                        prod,
                        id_loc,
                        fecha_inicio,
                        dias,
                        rng,
                        prefijo_prov=prod["prefijo_prov"],
                        usuario_id=usuario_op,
                        seq_lote=seq_lote,
                        kardex_desde=kardex_desde,
                    )
                    t_lotes.extend(sim["lotes"])
                    t_exist.update(sim["existencias"])
                    t_mermas.extend(sim["mermas"])
                    t_movs.extend(sim["movimientos"])
                    for ln in sim["ventas_lineas"]:
                        t_lineas_por_dia.setdefault(ln["dia"], []).append(ln)

                # Agrupa líneas del mismo día en tickets multi-línea realistas
                t_ventas: list[tuple] = []
                t_detalles: list[tuple] = []
                for dia_v, lineas_dia in sorted(t_lineas_por_dia.items()):
                    if fraccionar_intradia:
                        expandidas: list[dict] = []
                        dia_ord = dia_v.toordinal()
                        for ln in lineas_dia:
                            if ln["cantidad"] >= 6.0 and (ln["id_sku"] + dia_ord) % 4 == 0:
                                q1 = round(ln["cantidad"] * 0.60, 2)
                                q2 = round(ln["cantidad"] - q1, 2)
                                if q1 > 0 and q2 > 0:
                                    expandidas.append({**ln, "cantidad": q1, "restante_lote": round(ln["restante_lote"] + q2, 2)})
                                    expandidas.append({**ln, "cantidad": q2})
                                    continue
                            expandidas.append(ln)
                        lineas_dia = expandidas

                    for chunk_start in range(0, len(lineas_dia), lineas_por_ticket):
                        grupo = lineas_dia[chunk_start:chunk_start + lineas_por_ticket]
                        id_venta = uuid.uuid4()
                        k_fol = f"{id_loc}-{dia_v.strftime('%y%m%d')}"
                        seq_folio[k_fol] = seq_folio.get(k_fol, 0) + 1
                        folio = f"V-{k_fol}-{seq_folio[k_fol]:05d}"[:30]
                        momento = datetime.combine(dia_v, datetime.min.time(), tzinfo=timezone.utc).replace(
                            hour=rng.randint(8, 21), minute=rng.randint(0, 59)
                        )
                        emitir_kardex_venta = kardex_desde is None or dia_v >= kardex_desde
                        total_v = 0.0
                        for ln in grupo:
                            sub = round(ln["cantidad"] * ln["precio"], 2)
                            total_v += sub
                            t_detalles.append(
                                (uuid.uuid4(), id_venta, ln["id_sku"], ln["id_lote"], id_loc,
                                 ln["cantidad"], ln["precio"], sub, momento)
                            )
                            if emitir_kardex_venta:
                                t_movs.append(
                                    (ln["id_lote"], id_loc, "VENTA", -ln["cantidad"], ln["restante_lote"],
                                     ln["costo"], "VENTA", id_venta, usuario_op, momento)
                                )
                        t_ventas.append((id_venta, folio, id_loc, usuario_op, "TIENDA", round(total_v, 2), momento))

                filas_exist = [
                    (uuid.uuid4(), lid, loc_k, round(cant, 2))
                    for (lid, loc_k), cant in t_exist.items()
                ]
                n_det_t = len(t_detalles)
                n_mov_t = len(t_movs)
                totales["lotes"] += _copiar_en_lotes(
                    cur, "operacion.lote",
                    ["id_lote", "id_sku", "id_proveedor", "codigo_lote_prov",
                     "fecha_produccion", "fecha_recepcion", "fecha_caducidad",
                     "cantidad_recibida", "costo_unitario", "id_locacion_recepcion",
                     "estado", "observaciones", "creado_en"],
                    t_lotes,
                )
                totales["existencias"] += _copiar_en_lotes(
                    cur, "operacion.existencia",
                    ["id_existencia", "id_lote", "id_locacion", "cantidad_disponible"],
                    filas_exist,
                )
                totales["ventas"] += _copiar_en_lotes(
                    cur, "operacion.venta",
                    ["id_venta", "folio", "id_locacion", "id_usuario", "canal", "total", "fecha_venta"],
                    t_ventas,
                )
                totales["venta_detalle"] += _copiar_en_lotes(
                    cur, "operacion.venta_detalle",
                    ["id_detalle", "id_venta", "id_sku", "id_lote", "id_locacion",
                     "cantidad", "precio_unitario", "subtotal", "fecha_transaccion"],
                    t_detalles,
                )
                totales["mermas"] += _copiar_en_lotes(
                    cur, "operacion.merma",
                    ["id_lote", "id_locacion", "id_usuario", "cantidad", "causa_merma",
                     "costo_unitario", "observacion", "fecha_registro"],
                    t_mermas,
                )
                totales["movimientos"] += _copiar_en_lotes(
                    cur, "operacion.movimiento_inventario",
                    ["id_lote", "id_locacion", "tipo", "cantidad", "cantidad_resultante",
                     "costo_unitario", "referencia_tipo", "referencia_id", "id_usuario", "fecha"],
                    t_movs,
                )
                t_lotes.clear()
                t_exist.clear()
                t_lineas_por_dia.clear()
                t_mermas.clear()
                t_movs.clear()
                t_ventas.clear()
                t_detalles.clear()
                filas_exist.clear()
                conn.commit()
                print(
                    f"  -> Tienda {idx_t}/{len(tiendas)} ({tienda['nombre']}): "
                    f"+{n_det_t:,} ventas · +{n_mov_t:,} movs kardex"
                )

            t_stream = round(time.perf_counter() - t_stream0, 3)

            t_extra0 = time.perf_counter()
            extra = _generar_ordenes_y_auditoria(
                cur,
                productos=productos,
                tiendas=tiendas,
                usuarios=usuarios,
                n_ordenes=n_ordenes,
                lineas_por_oc=lineas_por_oc,
                n_eventos=n_eventos,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                rng=rng,
            )
            totales["ordenes_reabastecimiento"] = extra["ordenes_reabastecimiento"]
            totales["ordenes_compra_cabeceras"] = extra["ordenes_compra_cabeceras"]
            totales["ordenes_compra_lineas"] = extra["ordenes_compra_lineas"]
            totales["ordenes"] = extra["ordenes_reabastecimiento"] + extra["ordenes_compra"]
            totales["eventos_auditoria"] = extra["eventos_auditoria"]
            t_extra = round(time.perf_counter() - t_extra0, 3)

            try:
                cur.execute("SET session_replication_role = origin")
            except psycopg.Error:
                pass

            if indices_soltados:
                print("[MASIVO] Reconstruyendo índices secundarios con maintenance_work_mem=256MB...")
                cur.execute("SET LOCAL maintenance_work_mem = '256MB'")
                for schema_idx, nombre_idx, definicion_idx in indices_secundarios:
                    cur.execute(f"CREATE INDEX IF NOT EXISTS {nombre_idx} ON {definicion_idx}")
                conn.commit()

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
            cur.execute(
                "ANALYZE operacion.lote, operacion.existencia, operacion.venta, "
                "operacion.venta_detalle, operacion.merma, operacion.movimiento_inventario, "
                "operacion.orden_compra, operacion.orden_compra_detalle, "
                "analitica.orden_reabastecimiento, auditoria.bitacora_eventos"
            )
        conn.commit()
        _refrescar_agregados(conn)

    t_mongo0 = time.perf_counter()
    mongo_res = {"pronosticos_demanda": 0, "avisos_asn": 0, "alertas_operativas": 0}
    if not args.sin_mongo:
        mongo_res = _cargar_mongodb(
            productos=productos,
            tiendas=tiendas,
            n_docs=n_docs_mongo,
            reset=args.reset,
            rng=rng,
        )
    t_mongo = round(time.perf_counter() - t_mongo0, 3)

    try:
        from app.services import cache_service

        cache_service.invalidar_patron("web:*")
        cache_service.invalidar_patron("catalog:*")
    except Exception:
        pass

    duracion_total = round(time.perf_counter() - t_total_0, 3)
    total_pg = sum(totales.values()) + len(productos) + len(usuarios)
    total_mg = sum(mongo_res.values())
    resumen = {
        "modo": args.modo,
        "dias": dias,
        "skus": len(productos),
        "tiendas": len(tiendas),
        "usuarios_totales": len(usuarios),
        "registros_postgres": total_pg,
        "documentos_mongo": total_mg,
        "desglose_postgres": totales,
        "desglose_mongo": mongo_res,
        "tiempos_seg": {
            "catalogos": t_cat,
            "streaming_fefo": t_stream,
            "ordenes_y_auditoria": t_extra,
            "mongodb": t_mongo,
            "total": duracion_total,
        },
        "throughput": {
            "pg_filas_por_seg": round(total_pg / max(0.01, t_stream + t_extra), 1),
            "mongo_docs_por_seg": round(total_mg / max(0.01, t_mongo), 1) if total_mg else 0.0,
        },
    }

    if args.salida_metricas:
        out_path = Path(args.salida_metricas)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n[MASIVO] Resumen de carga completado:")
    print(f"  - PostgreSQL: {total_pg:,} registros ({resumen['throughput']['pg_filas_por_seg']:,.0f} filas/s)")
    print(f"  - MongoDB:    {total_mg:,} documentos ({resumen['throughput']['mongo_docs_por_seg']:,.0f} docs/s)")
    print(f"  - Tiempo total: {duracion_total}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
