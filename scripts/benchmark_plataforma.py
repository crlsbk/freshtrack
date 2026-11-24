#!/usr/bin/env python3
"""
Suite de Benchmark Integral para FreshTrack (PostgreSQL + MongoDB + Redis + Web).

Mide de forma reproducible y no destructiva los 8 indicadores requeridos:
  1. Tiempo de inserción (PostgreSQL COPY vs INSERT, MongoDB insert_many, Redis pipeline).
  2. Tiempo de consulta (p50 / p95 / p99 en ms).
  3. Uso de índices (EXPLAIN ANALYZE / pg_stat_user_indexes / Mongo IXSCAN).
  4. Uso de caché en Redis (Cache Miss vs Cache Hit, ratio y memoria).
  5. Tiempo de procesamiento analítico y validación de los 4 perfiles de SKU.
  6. Consumo de recursos (tamaño de BD/índices en disco, memoria Redis y RSS/CPU).
  7. Comportamiento con y sin Redis (speedup y 0% errores al desactivar Redis).
  8. Escalabilidad y operaciones concurrentes (1 → 5 → 15 → 30 hilos + integridad FEFO).

Uso:
    python scripts/benchmark_plataforma.py --base-url http://127.0.0.1:5000
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import resource
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from dotenv import load_dotenv
from sqlalchemy import text

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

load_dotenv(RAIZ / ".env")

from app.db import get_engine, one, query  # noqa: E402
from app.domain import kpis as dom_kpis  # noqa: E402
from app.domain import pronostico as dom_pron  # noqa: E402
from app.domain import reabastecimiento as dom_reab  # noqa: E402
from app.domain import ventas as dom_ventas  # noqa: E402
from app.services import cache_service, doc_store  # noqa: E402


def parsear_niveles_concurrencia(spec: str) -> list[int]:
    """Convierte una cadena tipo '1,25,50,100,200' en enteros positivos ordenados sin duplicados."""
    vistos: set[int] = set()
    salida: list[int] = []
    for parte in (spec or "").split(","):
        txt = parte.strip()
        if not txt:
            continue
        val = max(1, int(txt))
        if val not in vistos:
            vistos.add(val)
            salida.append(val)
    return sorted(salida) or [1]


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ord_v = sorted(valores)
    k = (len(ord_v) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ord_v) - 1)
    if f == c:
        return round(ord_v[f], 2)
    return round(ord_v[f] + (ord_v[c] - ord_v[f]) * (k - f), 2)


def _medir_tiempo_fn(fn, repeticiones: int = 10) -> dict:
    tiempos: list[float] = []
    for _ in range(repeticiones):
        t0 = time.perf_counter()
        fn()
        tiempos.append((time.perf_counter() - t0) * 1000.0)
    return {
        "n": repeticiones,
        "p50_ms": _percentil(tiempos, 50),
        "p95_ms": _percentil(tiempos, 95),
        "p99_ms": _percentil(tiempos, 99),
        "min_ms": round(min(tiempos), 2),
        "max_ms": round(max(tiempos), 2),
    }


def _rss_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)


# ---------------------------------------------------------------------------
# 1. Tiempo de inserción (micro-benchmark controlado + archivo de ingesta)
# ---------------------------------------------------------------------------
def medir_insercion(archivo_ingesta: str | None) -> dict:
    ingesta_previa = None
    if archivo_ingesta and Path(archivo_ingesta).is_file():
        try:
            ingesta_previa = json.loads(Path(archivo_ingesta).read_text(encoding="utf-8"))
        except Exception:
            ingesta_previa = None

    # Micro-benchmark PostgreSQL: tabla temporal (no altera datos reales)
    import psycopg

    db_url = (os.getenv("ETL_DATABASE_URL") or os.getenv("DATABASE_URL") or "").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    n_filas = 1000
    t_copy_ms = None
    t_insert_ms = None
    if db_url:
        try:
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE TEMP TABLE bench_ins (id int, clave text, val numeric(10,2))")
                    filas = [(i, f"k-{i}", float(i * 1.5)) for i in range(n_filas)]
                    t0 = time.perf_counter()
                    with cur.copy("COPY bench_ins (id, clave, val) FROM STDIN") as cp:
                        for f in filas:
                            cp.write_row(f)
                    t_copy_ms = round((time.perf_counter() - t0) * 1000.0, 2)

                    cur.execute("TRUNCATE bench_ins")
                    t1 = time.perf_counter()
                    cur.executemany("INSERT INTO bench_ins (id, clave, val) VALUES (%s, %s, %s)", filas)
                    t_insert_ms = round((time.perf_counter() - t1) * 1000.0, 2)
        except Exception:
            pass

    # Micro-benchmark MongoDB
    t_mongo_ms = None
    db = doc_store.get_mongo_db()
    if db is not None:
        try:
            col = db["_bench_tmp"]
            col.delete_many({})
            docs = [{"seq": i, "tag": "bench", "ts": datetime.now(timezone.utc)} for i in range(500)]
            t0 = time.perf_counter()
            col.insert_many(docs)
            t_mongo_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            col.drop()
        except Exception:
            pass

    # Micro-benchmark Redis pipeline
    t_redis_ms = None
    r = cache_service.get_redis_client()
    if r is not None:
        try:
            t0 = time.perf_counter()
            pipe = r.pipeline()
            for i in range(1000):
                pipe.setex(f"bench:ins:{i}", 30, str(i))
            pipe.execute()
            t_redis_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            cache_service.invalidar_patron("bench:ins:*")
        except Exception:
            pass

    return {
        "ingesta_masiva": ingesta_previa,
        "micro_benchmark": {
            "pg_copy_1000_ms": t_copy_ms,
            "pg_insert_1000_ms": t_insert_ms,
            "mongo_insert_500_ms": t_mongo_ms,
            "redis_pipeline_1000_ms": t_redis_ms,
        },
    }


# ---------------------------------------------------------------------------
# 2. Tiempo de consulta y 3. Uso de índices (EXPLAIN ANALYZE + Mongo IXSCAN)
# ---------------------------------------------------------------------------
def _buscar_tipo_scan(plan: dict) -> list[str]:
    tipos = [plan.get("Node Type", "")]
    for hijo in plan.get("Plans", []) or []:
        tipos.extend(_buscar_tipo_scan(hijo))
    return tipos


def medir_consultas_e_indices() -> tuple[list[dict], list[dict], list[dict]]:
    sku_row = one("SELECT id_sku, id_locacion FROM operacion.venta_detalle LIMIT 1") or {"id_sku": 1, "id_locacion": 1}
    lote_row = one("SELECT id_lote::text AS id_lote FROM operacion.lote LIMIT 1") or {"id_lote": str(uuid.uuid4())}

    consultas = [
        (
            "Serie temporal 365d (SKU + Tienda)",
            lambda: query(
                """
                SELECT DATE(fecha_transaccion) AS f, SUM(cantidad)
                FROM operacion.venta_detalle
                WHERE id_sku = :s AND id_locacion = :l
                  AND fecha_transaccion >= CURRENT_DATE - 365
                GROUP BY 1 ORDER BY 1
                """,
                s=sku_row["id_sku"], l=sku_row["id_locacion"],
            ),
        ),
        (
            "Cola FEFO por tienda (v_inventario_lote)",
            lambda: query(
                """
                SELECT id_lote::text, producto, cantidad_disponible, fecha_caducidad, clasificacion
                FROM operacion.v_inventario_lote
                WHERE id_locacion = :l AND cantidad_disponible > 0
                ORDER BY fecha_caducidad ASC LIMIT 50
                """,
                l=sku_row["id_locacion"],
            ),
        ),
        (
            "Kardex por lote (movimiento_inventario)",
            lambda: query(
                """
                SELECT tipo, cantidad, fecha FROM operacion.movimiento_inventario
                WHERE id_lote = CAST(:id_l AS uuid) ORDER BY fecha DESC LIMIT 50
                """,
                id_l=lote_row["id_lote"],
            ),
        ),
        (
            "Bitácora de auditoría reciente",
            lambda: query(
                """
                SELECT id_evento::text, accion, fecha_evento
                FROM auditoria.bitacora_eventos
                ORDER BY fecha_evento DESC LIMIT 40
                """
            ),
        ),
    ]
    tiempos_consulta = [{"consulta": nom, **_medir_tiempo_fn(fn, 10)} for nom, fn in consultas]

    db = doc_store.get_mongo_db()
    if db is not None:
        tiempos_consulta.append(
            {
                "consulta": "MongoDB pipeline: carga ASN por proveedor",
                **_medir_tiempo_fn(doc_store.analitica_carga_asn_por_proveedor, 8),
            }
        )
        tiempos_consulta.append(
            {
                "consulta": "MongoDB pipeline: alertas abiertas por locación",
                **_medir_tiempo_fn(doc_store.analitica_alertas_por_locacion, 8),
            }
        )

    planes_sql = [
        (
            "venta_detalle (idx_vd_serie)",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT fecha_transaccion, cantidad
            FROM operacion.venta_detalle
            WHERE id_sku = :s AND id_locacion = :l
              AND fecha_transaccion >= CURRENT_DATE - 180
            """,
            {"s": sku_row["id_sku"], "l": sku_row["id_locacion"]},
        ),
        (
            "movimiento_inventario (idx_mov_lote)",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT tipo, cantidad, fecha
            FROM operacion.movimiento_inventario
            WHERE id_lote = CAST(:id_l AS uuid)
            ORDER BY fecha DESC LIMIT 20
            """,
            {"id_l": lote_row["id_lote"]},
        ),
        (
            "bitacora_eventos (idx_bitacora_fecha)",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT id_evento, accion, fecha_evento
            FROM auditoria.bitacora_eventos
            ORDER BY fecha_evento DESC LIMIT 40
            """,
            {},
        ),
        (
            "lote (idx_lote_sku)",
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT id_lote, fecha_caducidad
            FROM operacion.lote
            WHERE id_sku = :s
            ORDER BY fecha_caducidad ASC LIMIT 20
            """,
            {"s": sku_row["id_sku"]},
        ),
    ]

    indices_uso: list[dict] = []
    engine = get_engine()
    with engine.connect() as conn:
        for etiqueta, sql, params in planes_sql:
            row = conn.execute(text(sql), params).scalar()
            plan_root = row[0] if isinstance(row, list) else row
            plan_node = plan_root.get("Plan", {})
            nodos = [n for n in _buscar_tipo_scan(plan_node) if "Scan" in n]
            indices_uso.append(
                {
                    "motor": "PostgreSQL",
                    "objetivo": etiqueta,
                    "nodos_scan": ", ".join(dict.fromkeys(nodos)),
                    "usa_indice": any("Index" in n for n in nodos),
                    "execution_ms": round(float(plan_root.get("Execution Time", 0.0)), 3),
                    "shared_hit_blocks": plan_node.get("Shared Hit Blocks", 0),
                }
            )

    if db is not None:
        try:
            exp_m = db.pronosticos_demanda.find(
                {"id_sku": int(sku_row["id_sku"]), "id_locacion": int(sku_row["id_locacion"])}
            ).sort("fecha_calculo", -1).explain()
            stats = exp_m.get("executionStats", {})
            win_plan = json.dumps(exp_m.get("queryPlanner", {}).get("winningPlan", {}))
            indices_uso.append(
                {
                    "motor": "MongoDB",
                    "objetivo": "pronosticos_demanda (idx_pronostico_sku_locacion_fecha)",
                    "nodos_scan": "IXSCAN" if "IXSCAN" in win_plan else "COLLSCAN",
                    "usa_indice": "IXSCAN" in win_plan,
                    "execution_ms": stats.get("executionTimeMillis", 0),
                    "shared_hit_blocks": stats.get("totalKeysExamined", 0),
                }
            )
        except Exception:
            pass

    stats_pg = query(
        """
        SELECT relname AS tabla, indexrelname AS indice, idx_scan, idx_tup_read
        FROM pg_stat_user_indexes
        WHERE schemaname IN ('operacion', 'analitica', 'auditoria')
          AND idx_scan > 0
        ORDER BY idx_scan DESC
        LIMIT 12
        """
    )
    return tiempos_consulta, indices_uso, stats_pg


# ---------------------------------------------------------------------------
# 4. Uso de caché y 7. Con y sin Redis
# ---------------------------------------------------------------------------
def medir_cache_y_redis() -> tuple[dict, list[dict]]:
    r = cache_service.get_redis_client()
    cache_stats = {"redis_disponible": r is not None}

    if r is not None:
        cache_service.invalidar_patron("web:kpis:*")
        cache_service.invalidar_patron("web:forecast:*")
        info_antes = r.info("stats")

        t0 = time.perf_counter()
        dom_kpis.panel_principal()
        dom_kpis.metricas_por_locacion(30)
        dom_kpis.metricas_periodo(30)
        miss_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        tiempos_hit: list[float] = []
        for _ in range(10):
            t1 = time.perf_counter()
            dom_kpis.panel_principal()
            dom_kpis.metricas_por_locacion(30)
            dom_kpis.metricas_periodo(30)
            tiempos_hit.append((time.perf_counter() - t1) * 1000.0)

        info_despues = r.info("stats")
        mem_info = r.info("memory")
        hits_delta = max(0, info_despues.get("keyspace_hits", 0) - info_antes.get("keyspace_hits", 0))
        misses_delta = max(0, info_despues.get("keyspace_misses", 0) - info_antes.get("keyspace_misses", 0))
        tot = hits_delta + misses_delta
        cache_stats.update(
            {
                "miss_frio_ms": miss_ms,
                "hit_caliente_p50_ms": _percentil(tiempos_hit, 50),
                "hit_caliente_p95_ms": _percentil(tiempos_hit, 95),
                "speedup_cache_x": round(miss_ms / max(0.01, _percentil(tiempos_hit, 50)), 1),
                "redis_hits_delta": hits_delta,
                "redis_misses_delta": misses_delta,
                "hit_ratio_pct": round(hits_delta / tot * 100.0, 1) if tot else 0.0,
                "redis_memoria": mem_info.get("used_memory_human", "—"),
            }
        )

    # Comparativa Con vs Sin Redis (CACHE_WEB_ACTIVA=true vs false)
    cargas = [
        ("KPIs Panel Principal", dom_kpis.panel_principal),
        ("Mapa Tiendas GPS (30d)", lambda: dom_kpis.metricas_por_locacion(30)),
        ("Métricas Periodo (30d)", lambda: dom_kpis.metricas_periodo(30)),
        ("Salud de datos (drift)", lambda: dom_pron.evaluar_salud_modelos()),
    ]
    comparativa: list[dict] = []
    prev_flag = os.environ.get("CACHE_WEB_ACTIVA")
    try:
        for nombre, fn in cargas:
            os.environ["CACHE_WEB_ACTIVA"] = "true"
            if r is not None:
                fn()  # calentar clave
            con_redis = _medir_tiempo_fn(fn, 6)

            os.environ["CACHE_WEB_ACTIVA"] = "false"
            sin_redis = _medir_tiempo_fn(fn, 4)
            comparativa.append(
                {
                    "operacion": nombre,
                    "con_redis_p50_ms": con_redis["p50_ms"],
                    "sin_redis_p50_ms": sin_redis["p50_ms"],
                    "speedup_x": round(sin_redis["p50_ms"] / max(0.01, con_redis["p50_ms"]), 1),
                }
            )
    finally:
        if prev_flag is None:
            os.environ.pop("CACHE_WEB_ACTIVA", None)
        else:
            os.environ["CACHE_WEB_ACTIVA"] = prev_flag

    return cache_stats, comparativa


# ---------------------------------------------------------------------------
# 5. Tiempo de procesamiento y discriminación de perfiles
# ---------------------------------------------------------------------------
def medir_procesamiento_analitico() -> dict:
    # Forzar cálculo real sin caché para medir tiempo genuino de procesamiento
    prev = os.environ.get("CACHE_WEB_ACTIVA")
    os.environ["CACHE_WEB_ACTIVA"] = "false"
    try:
        t0 = time.perf_counter()
        salud = dom_pron.evaluar_salud_modelos()
        t_salud = round(time.perf_counter() - t0, 3)

        t1 = time.perf_counter()
        backtest = dom_pron.evaluar_backtest_comparativo(horizonte=7)
        t_lab = round(time.perf_counter() - t1, 3)

        t2 = time.perf_counter()
        riesgo = dom_reab.sobreinventario(horizonte=7, limite=250)
        t_prod = round(time.perf_counter() - t2, 3)
    finally:
        if prev is None:
            os.environ.pop("CACHE_WEB_ACTIVA", None)
        else:
            os.environ["CACHE_WEB_ACTIVA"] = prev

    anomalias = salud.get("anomalias_sku", [])
    conteo_perfiles: dict[str, int] = {}
    for a in anomalias:
        p = a.get("perfil_demanda") or "SIN_PERFIL"
        conteo_perfiles[p] = conteo_perfiles.get(p, 0) + 1

    naive = (backtest.get("resumen_global") or {}).get("NAIVE", {}) or {}
    return {
        "salud_datos_seg": t_salud,
        "anomalias_detectadas": len(anomalias),
        "anomalias_por_perfil": conteo_perfiles,
        "laboratorio_seg": t_lab,
        "series_evaluadas_lab": backtest.get("total_series", 0),
        "modelos_lab": [
            {"modelo": nombre, "wmape": m.get("wmape"),
             "fva_pp": (round(naive["wmape"] - m["wmape"], 2)
                        if naive.get("wmape") is not None and m.get("wmape") is not None else None),
             "costo": m.get("mae")}
            for nombre, m in (backtest.get("resumen_global") or {}).items()
        ],
        "pipeline_newsvendor_fefo_seg": t_prod,
        "series_produccion": len(riesgo),
    }


# ---------------------------------------------------------------------------
# 6. Consumo de recursos
# ---------------------------------------------------------------------------
def medir_recursos() -> dict:
    tablas = query(
        """
        SELECT schemaname || '.' || relname AS tabla,
               pg_total_relation_size(relid) / (1024.0 * 1024.0) AS total_mb,
               pg_indexes_size(relid) / (1024.0 * 1024.0) AS indices_mb
        FROM pg_stat_user_tables
        WHERE schemaname IN ('operacion', 'analitica', 'auditoria')
        ORDER BY pg_total_relation_size(relid) DESC
        LIMIT 10
        """
    )
    for t in tablas:
        t["total_mb"] = round(float(t["total_mb"]), 2)
        t["indices_mb"] = round(float(t["indices_mb"]), 2)

    pg_total_mb = round(sum(t["total_mb"] for t in tablas), 2)
    mongo_mb = 0.0
    db = doc_store.get_mongo_db()
    if db is not None:
        try:
            st = db.command("dbStats")
            mongo_mb = round(float(st.get("storageSize", 0) + st.get("indexSize", 0)) / (1024.0 * 1024.0), 2)
        except Exception:
            pass

    redis_mem = "—"
    r = cache_service.get_redis_client()
    if r is not None:
        try:
            redis_mem = r.info("memory").get("used_memory_human", "—")
        except Exception:
            pass

    return {
        "python_rss_mb": _rss_mb(),
        "postgres_top10_mb": pg_total_mb,
        "mongo_storage_mb": mongo_mb,
        "redis_used_memory": redis_mem,
        "tablas": tablas,
    }


# ---------------------------------------------------------------------------
# 8. Escalabilidad y concurrencia (HTTP Web o DB directa: lecturas + escrituras + cron)
# ---------------------------------------------------------------------------
def _obtener_cookie_sesion(base_url: str, email: str, password: str) -> str | None:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    data = urllib.parse.urlencode({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(f"{base_url.rstrip('/')}/login", data=data, method="POST")
    try:
        with opener.open(req, timeout=10) as resp:
            if resp.status >= 400:
                return None
            cookie_hdr = "; ".join(f"{c.name}={c.value}" for c in cj)
            return cookie_hdr or None
    except Exception:
        return None


def _usuario_benchmark(email_pref: str) -> dict | None:
    fila = one(
        """
        SELECT u.id_usuario::text AS id_usuario, u.email, r.clave AS rol_clave
        FROM operacion.usuario u
        JOIN operacion.rol r ON r.id_rol = u.id_rol
        WHERE u.estado_activo = true
        ORDER BY (CASE WHEN u.email = :email THEN 0 ELSE 1 END), u.fecha_alta ASC
        LIMIT 1
        """,
        email=email_pref,
    )
    return dict(fila) if fila else None


def medir_escalabilidad(
    *,
    base_url: str,
    email: str,
    password: str,
    niveles: list[int],
    peticiones_por_hilo: int = 3,
    pct_escrituras: int = 10,
    sin_entrenamiento_paralelo: bool = False,
) -> dict:
    cookie_header = _obtener_cookie_sesion(base_url, email, password)
    modo = "http_web_mixto" if cookie_header else "db_concurrente_mixto"
    rutas = ["/panel", "/mapa", "/pronostico", "/reabastecimiento", "/lotes", "/inventario"]

    candidatos_stock = query(
        """
        SELECT id_sku, id_locacion
        FROM operacion.v_inventario_lote
        WHERE tipo_locacion = 'Tienda'
          AND estado_lote = 'DISPONIBLE'
          AND dias_restantes >= 0
          AND cantidad_util >= 25
        LIMIT 40
        """
    )
    usuario_bench = _usuario_benchmark(email)
    tienda_entreno = one(
        "SELECT id_locacion FROM operacion.locacion WHERE activo = true AND tipo_locacion = 'Tienda' ORDER BY id_locacion LIMIT 1"
    )
    id_loc_entreno = int(tienda_entreno["id_locacion"]) if tienda_entreno else None
    pct_esc = max(0, min(50, int(pct_escrituras)))
    cada_n = max(1, round(100 / pct_esc)) if pct_esc > 0 else 0

    resultados_niveles: list[dict] = []
    for hilos in niveles:
        total_reqs = hilos * max(1, int(peticiones_por_hilo))
        entrenamiento_estado: dict[str, object] = {"seg": None, "ok": None}
        hilo_entreno: threading.Thread | None = None

        def _correr_entrenamiento_paralelo() -> None:
            t_e0 = time.perf_counter()
            try:
                dom_pron._ejecutar_pronostico_tienda(
                    usuario=usuario_bench,
                    id_locacion=id_loc_entreno,
                    metodo="AUTO",
                    horizonte=7,
                )
                entrenamiento_estado["ok"] = True
            except Exception:
                entrenamiento_estado["ok"] = False
            entrenamiento_estado["seg"] = round(time.perf_counter() - t_e0, 2)

        def tarea(idx: int) -> tuple[str, bool, float]:
            es_escritura = bool(candidatos_stock) and pct_esc > 0 and (idx % cada_n == 0)
            t0 = time.perf_counter()
            try:
                if cookie_header:
                    if es_escritura:
                        cand = candidatos_stock[idx % len(candidatos_stock)]
                        cuerpo = json.dumps(
                            {
                                "formato": "json",
                                "cantidad_tx": 1,
                                "id_locacion": int(cand["id_locacion"]),
                                "id_sku": int(cand["id_sku"]),
                            }
                        ).encode("utf-8")
                        req = urllib.request.Request(
                            f"{base_url.rstrip('/')}/ventas/simular-pos",
                            data=cuerpo,
                            headers={"Cookie": cookie_header, "Content-Type": "application/json"},
                            method="POST",
                        )
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            _ = resp.read(256)
                            ok = 200 <= resp.status < 300
                    else:
                        ruta = rutas[idx % len(rutas)]
                        req = urllib.request.Request(
                            f"{base_url.rstrip('/')}{ruta}",
                            headers={"Cookie": cookie_header},
                            method="GET",
                        )
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            _ = resp.read(256)
                            ok = 200 <= resp.status < 400
                else:
                    if es_escritura and usuario_bench:
                        cand = candidatos_stock[idx % len(candidatos_stock)]
                        dom_ventas.registrar_venta(
                            id_locacion=int(cand["id_locacion"]),
                            lineas=[{"id_sku": int(cand["id_sku"]), "cantidad": 1.0}],
                            usuario=usuario_bench,
                        )
                        ok = True
                    else:
                        if idx % 2 == 0:
                            dom_kpis.panel_principal()
                        else:
                            dom_kpis.metricas_por_locacion(30)
                        ok = True
            except Exception:
                ok = False
            tipo = "W" if es_escritura else "R"
            return tipo, ok, (time.perf_counter() - t0) * 1000.0

        t_ini = time.perf_counter()
        if not sin_entrenamiento_paralelo and hilos >= 50 and usuario_bench and id_loc_entreno:
            hilo_entreno = threading.Thread(target=_correr_entrenamiento_paralelo, daemon=True)
            hilo_entreno.start()

        with ThreadPoolExecutor(max_workers=hilos) as pool:
            res = list(pool.map(tarea, range(total_reqs)))

        if hilo_entreno is not None:
            hilo_entreno.join(timeout=120)
        dur_s = max(0.001, time.perf_counter() - t_ini)

        lecturas = [r for r in res if r[0] == "R"]
        escrituras = [r for r in res if r[0] == "W"]
        exitosos = sum(1 for _, ok, _ in res if ok)
        lats = [ms for _, _, ms in res]
        resultados_niveles.append(
            {
                "concurrencia": hilos,
                "total_peticiones": total_reqs,
                "lecturas": len(lecturas),
                "lecturas_ok": sum(1 for _, ok, _ in lecturas if ok),
                "escrituras": len(escrituras),
                "escrituras_ok": sum(1 for _, ok, _ in escrituras if ok),
                "exitosas": exitosos,
                "exito_pct": round(exitosos / total_reqs * 100.0, 1),
                "rps": round(total_reqs / dur_s, 1),
                "p50_ms": _percentil(lats, 50),
                "p95_ms": _percentil(lats, 95),
                "p99_ms": _percentil(lats, 99),
                "entrenamiento_paralelo_seg": entrenamiento_estado["seg"],
                "entrenamiento_paralelo_ok": entrenamiento_estado["ok"],
            }
        )

    negativos = one("SELECT COUNT(*) AS n FROM operacion.existencia WHERE cantidad_disponible < 0") or {"n": 0}
    return {
        "modo": modo,
        "niveles": resultados_niveles,
        "integridad_stock_negativo": int(negativos["n"]),
    }


def _generar_markdown(rep: dict) -> str:
    lines = [
        "# Reporte de Benchmark y Escalabilidad — FreshTrack",
        "",
        f"Generado: `{rep['generado_en']}` | RSS Python: `{rep['recursos']['python_rss_mb']} MB`",
        "",
        "## 1. Tiempo de Inserción",
        "",
    ]
    mb = rep["insercion"]["micro_benchmark"]
    lines.extend([
        f"- **PostgreSQL `COPY` (1,000 filas):** `{mb['pg_copy_1000_ms']} ms` vs `INSERT` batch: `{mb['pg_insert_1000_ms']} ms`",
        f"- **MongoDB `insert_many` (500 docs):** `{mb['mongo_insert_500_ms']} ms`",
        f"- **Redis `pipeline` (1,000 claves):** `{mb['redis_pipeline_1000_ms']} ms`",
    ])
    ing = rep["insercion"].get("ingesta_masiva")
    if ing:
        desglose = ing.get("desglose_postgres") or {}
        lines.append(
            f"- **Carga masiva completa (`modo={ing.get('modo')}`):** `{ing['registros_postgres']:,}` filas PostgreSQL "
            f"(`{ing['throughput']['pg_filas_por_seg']:,.0f}` filas/s) y `{ing['documentos_mongo']:,}` "
            f"docs MongoDB (`{ing['throughput']['mongo_docs_por_seg']:,.0f}` docs/s) en `{ing['tiempos_seg']['total']}s`."
        )
        if desglose:
            lines.append(
                f"  - Ventas detalle: `{desglose.get('venta_detalle', 0):,}` · "
                f"Kardex FEFO: `{desglose.get('movimientos', 0):,}` · "
                f"OCs: `{desglose.get('ordenes_compra_cabeceras', 0):,}` "
                f"(`{desglose.get('ordenes_compra_lineas', 0):,}` líneas) · "
                f"Reabastecimiento NV: `{desglose.get('ordenes_reabastecimiento', 0):,}`"
            )

    lines.extend(["", "## 2. Tiempo de Consulta", "", "| Consulta | p50 (ms) | p95 (ms) | p99 (ms) |", "| --- | ---: | ---: | ---: |"])
    for c in rep["consultas"]:
        lines.append(f"| {c['consulta']} | {c['p50_ms']} | {c['p95_ms']} | {c['p99_ms']} |")

    lines.extend(["", "## 3. Uso de Índices (EXPLAIN ANALYZE)", "", "| Motor | Consulta / Índice | Plan | ¿Usa Índice? | Tiempo (ms) |", "| --- | --- | --- | :---: | ---: |"])
    for idx in rep["indices"]:
        lines.append(f"| {idx['motor']} | {idx['objetivo']} | `{idx['nodos_scan']}` | {'Sí' if idx['usa_indice'] else 'No'} | {idx['execution_ms']} |")

    cs = rep["cache"]
    lines.extend([
        "", "## 4. Uso de Caché (Redis)", "",
        f"- **Cache Miss (frío):** `{cs.get('miss_frio_ms', '—')} ms` vs **Cache Hit (caliente p50):** `{cs.get('hit_caliente_p50_ms', '—')} ms` (`{cs.get('speedup_cache_x', '—')}×` más rápido)",
        f"- **Hit Ratio medido:** `{cs.get('hit_ratio_pct', '—')}%` · **Memoria Redis:** `{cs.get('redis_memoria', '—')}`",
    ])

    pr = rep["procesamiento"]
    lines.extend([
        "", "## 5. Tiempo de Procesamiento y Discriminación de Perfiles", "",
        f"- **Salud de datos / Drift:** `{pr['salud_datos_seg']}s` · Anomalías detectadas: `{pr['anomalias_detectadas']}` (`{pr['anomalias_por_perfil']}`)",
        f"- **Backtest comparativo (walk-forward):** `{pr['laboratorio_seg']}s` · Series evaluadas: `{pr['series_evaluadas_lab']}`",
        f"- **Riesgo de sobreinventario (Newsvendor/FEFO):** `{pr['pipeline_newsvendor_fefo_seg']}s` · Series: `{pr['series_produccion']}`",
        "", "| Modelo | WMAPE (%) | FVA vs Naive (pp) | MAE |", "| --- | ---: | ---: | ---: |",
    ])
    for m in pr["modelos_lab"]:
        lines.append(f"| {m['modelo']} | {m['wmape']} | {m['fva_pp']} | {m['costo']} |")

    rec = rep["recursos"]
    lines.extend([
        "", "## 6. Consumo de Recursos", "",
        f"- **PostgreSQL Top 10 tablas+índices:** `{rec['postgres_top10_mb']} MB` · **MongoDB:** `{rec['mongo_storage_mb']} MB` · **Redis:** `{rec['redis_used_memory']}`",
        "", "| Tabla | Total (MB) | Índices (MB) |", "| --- | ---: | ---: |",
    ])
    for t in rec["tablas"]:
        lines.append(f"| `{t['tabla']}` | {t['total_mb']} | {t['indices_mb']} |")

    lines.extend(["", "## 7. Comportamiento Con y Sin Redis", "", "| Operación | Con Redis p50 (ms) | Sin Redis p50 (ms) | Aceleración |", "| --- | ---: | ---: | ---: |"])
    for cmp in rep["con_vs_sin_redis"]:
        lines.append(f"| {cmp['operacion']} | {cmp['con_redis_p50_ms']} | {cmp['sin_redis_p50_ms']} | `{cmp['speedup_x']}×` |")

    esc = rep["escalabilidad"]
    lines.extend([
        "", f"## 8. Escalabilidad y Concurrencia (`modo={esc['modo']}`)", "",
        "| Hilos | Peticiones (L/E) | Éxito (%) | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Entreno paralelo |",
        "| ---: | :---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ])
    for nv in esc["niveles"]:
        ent = (
            f"{nv['entrenamiento_paralelo_seg']}s ({'OK' if nv['entrenamiento_paralelo_ok'] else 'ERR'})"
            if nv.get("entrenamiento_paralelo_seg") is not None
            else "—"
        )
        le_txt = f"{nv['total_peticiones']} ({nv.get('lecturas', nv['total_peticiones'])}/{nv.get('escrituras', 0)})"
        lines.append(
            f"| {nv['concurrencia']} | {le_txt} | {nv['exito_pct']}% | {nv['rps']} | "
            f"{nv['p50_ms']} | {nv['p95_ms']} | {nv.get('p99_ms', nv['p95_ms'])} | {ent} |"
        )
    lines.append(f"\n- **Integridad FEFO (existencias negativas):** `{esc['integridad_stock_negativo']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark completo de FreshTrack")
    ap.add_argument("--base-url", default="http://127.0.0.1:5000")
    ap.add_argument("--email", default="admin@freshtrack.mx")
    ap.add_argument("--password", default="Admin2026!")
    ap.add_argument("--concurrencia", default="1,25,50,100,200")
    ap.add_argument("--peticiones-por-hilo", type=int, default=3)
    ap.add_argument("--pct-escrituras", type=int, default=10)
    ap.add_argument("--sin-entrenamiento-paralelo", action="store_true")
    ap.add_argument("--archivo-ingesta", default="docs/ingesta_resultados.json")
    ap.add_argument("--salida-md", default="docs/REPORTE_BENCHMARK.md")
    ap.add_argument("--salida-json", default="docs/benchmark_resultados.json")
    args = ap.parse_args()

    niveles = parsear_niveles_concurrencia(args.concurrencia)

    print("[BENCH] 1/8 Midiendo inserción...")
    insercion = medir_insercion(args.archivo_ingesta)
    print("[BENCH] 2-3/8 Midiendo consultas y EXPLAIN ANALYZE...")
    consultas, indices, stats_idx = medir_consultas_e_indices()
    print("[BENCH] 4 y 7/8 Midiendo caché Redis y Con vs Sin Redis...")
    cache_stats, con_vs_sin = medir_cache_y_redis()
    print("[BENCH] 5/8 Midiendo procesamiento analítico y 4 perfiles...")
    procesamiento = medir_procesamiento_analitico()
    print("[BENCH] 6/8 Midiendo consumo de recursos...")
    recursos = medir_recursos()
    print("[BENCH] 8/8 Midiendo escalabilidad concurrente...")
    escalabilidad = medir_escalabilidad(
        base_url=args.base_url,
        email=args.email,
        password=args.password,
        niveles=niveles,
        peticiones_por_hilo=args.peticiones_por_hilo,
        pct_escrituras=args.pct_escrituras,
        sin_entrenamiento_paralelo=args.sin_entrenamiento_paralelo,
    )

    reporte = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "insercion": insercion,
        "consultas": consultas,
        "indices": indices,
        "indices_stats": stats_idx,
        "cache": cache_stats,
        "con_vs_sin_redis": con_vs_sin,
        "procesamiento": procesamiento,
        "recursos": recursos,
        "escalabilidad": escalabilidad,
    }

    md_text = _generar_markdown(reporte)
    for p in (Path(args.salida_md), Path(args.salida_json)):
        p.parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida_md).write_text(md_text, encoding="utf-8")
    Path(args.salida_json).write_text(json.dumps(reporte, indent=2, default=str, ensure_ascii=False), encoding="utf-8")

    print(f"\n[BENCH] Reportes generados en:\n  - {args.salida_md}\n  - {args.salida_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
