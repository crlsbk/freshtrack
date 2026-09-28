"""
Escenario de demostración extremo a extremo (Avance 2).

Recorre, a través de la capa HTTP real de la aplicación, el guion que pide la
rúbrica: alta de catálogos, recepción de lotes, cálculo de vida útil, venta con
FEFO, pronóstico, reabastecimiento, transferencia con aprobación humana, merma,
alertas, panel y trazabilidad.

Todo lo que imprime son valores medidos contra PostgreSQL. No hay ningún dato
simulado: si un paso no escribe en la base, el script lo reporta como fallo.

Uso:

    python scripts/demo_avance2.py --escenario    # ejecuta el guion completo
    python scripts/demo_avance2.py --verificar    # relee todo desde PostgreSQL
                                                  # en un proceso nuevo

La segunda orden demuestra la persistencia: se ejecuta en un proceso distinto,
después de que el primero terminó, y toda la información sigue ahí porque vive
en PostgreSQL y no en memoria de Flask.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
os.chdir(RAIZ)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app import create_app  # noqa: E402
from app.db import escribir, escalar, one, query  # noqa: E402
from app.domain.alertas import TIPOS as TIPOS_ALERTA  # noqa: E402

# ---------------------------------------------------------------------------
# Presentación
# ---------------------------------------------------------------------------
_ANCHO = 78
_fallos: list[str] = []


def titulo(texto: str) -> None:
    print("\n" + "=" * _ANCHO)
    print(texto)
    print("=" * _ANCHO)


_paso_actual = 0


def paso(texto: str) -> None:
    """Numera los pasos solo: así se pueden insertar sin renumerar a mano."""
    global _paso_actual
    _paso_actual += 1
    print(f"\n[{_paso_actual:02d}] {texto}")
    print("-" * _ANCHO)


def dato(etiqueta: str, valor) -> None:
    print(f"     {etiqueta:<38} {valor}")


def comprobar(condicion: bool, descripcion: str, detalle: str = "") -> bool:
    marca = "OK  " if condicion else "FALLO"
    print(f"     [{marca}] {descripcion}" + (f" — {detalle}" if detalle else ""))
    if not condicion:
        _fallos.append(descripcion)
    return condicion


def entrada(cliente, ruta: str, datos: dict):
    """POST a una ruta de formulario, siguiendo la redirección."""
    return cliente.post(ruta, data=datos, follow_redirects=True)


# ---------------------------------------------------------------------------
# Utilidades de consulta
# ---------------------------------------------------------------------------
def id_sku_por_nombre(nombre: str) -> int | None:
    return escalar("SELECT id_sku FROM operacion.producto WHERE nombre = :n", n=nombre)


def id_locacion_por_nombre(nombre: str) -> int | None:
    return escalar("SELECT id_locacion FROM operacion.locacion WHERE nombre = :n", n=nombre)


def id_proveedor_por_rfc(rfc: str) -> int | None:
    return escalar("SELECT id_proveedor FROM operacion.proveedor WHERE rfc = :r", r=rfc)


def existencia(id_lote: str, id_locacion: int) -> float:
    valor = escalar(
        "SELECT COALESCE(cantidad_disponible, 0) FROM operacion.existencia "
        "WHERE id_lote = CAST(:l AS uuid) AND id_locacion = :loc",
        l=id_lote,
        loc=id_locacion,
    )
    return float(valor or 0)


def lote_por_codigo(codigo: str) -> dict | None:
    return one(
        """
        SELECT id_lote::text, codigo_lote_prov, cantidad_recibida, fecha_caducidad,
               dias_restantes, vida_util_pct, clasificacion
        FROM operacion.v_lote_riesgo
        WHERE codigo_lote_prov = :c
        LIMIT 1
        """,
        c=codigo,
    )


# ---------------------------------------------------------------------------
# Limpieza acotada al escenario
# ---------------------------------------------------------------------------
NOMBRE_SKU_DEMO = "Yogur Demostración 1kg"
TIENDA_DEMO = "Tienda Demostración"
RFC_DEMO = "DEM260101ABC"


def _borrar_por_sku(borrar, sku: int) -> None:
    """Borra, en orden inverso a las dependencias, todo lo del SKU de demo."""
    # Analítica
    borrar(
        "analitica.desperdicio_evitado",
        "SELECT de.ctid FROM analitica.desperdicio_evitado de "
        "JOIN analitica.transferencia t ON t.id_transferencia = de.id_transferencia "
        "JOIN operacion.lote l ON l.id_lote = t.id_lote WHERE l.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "analitica.transferencia",
        "SELECT t.ctid FROM analitica.transferencia t "
        "JOIN operacion.lote l ON l.id_lote = t.id_lote WHERE l.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "analitica.alerta",
        "SELECT a.ctid FROM analitica.alerta a WHERE a.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "analitica.descuento",
        "SELECT d.ctid FROM analitica.descuento d "
        "JOIN operacion.lote l ON l.id_lote = d.id_lote WHERE l.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "analitica.orden_reabastecimiento",
        "SELECT o.ctid FROM analitica.orden_reabastecimiento o WHERE o.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "analitica.forecast_result",
        "SELECT fr.ctid FROM analitica.forecast_result fr WHERE fr.id_sku = :sku",
        sku=sku,
    )
    # Operación
    borrar(
        "operacion.movimiento_inventario",
        "SELECT mi.ctid FROM operacion.movimiento_inventario mi "
        "JOIN operacion.lote l ON l.id_lote = mi.id_lote WHERE l.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "operacion.venta_detalle",
        "SELECT vd.ctid FROM operacion.venta_detalle vd WHERE vd.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "operacion.merma",
        "SELECT m.ctid FROM operacion.merma m "
        "JOIN operacion.lote l ON l.id_lote = m.id_lote WHERE l.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "operacion.existencia",
        "SELECT e.ctid FROM operacion.existencia e "
        "JOIN operacion.lote l ON l.id_lote = e.id_lote WHERE l.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "operacion.lote",
        "SELECT l.ctid FROM operacion.lote l WHERE l.id_sku = :sku",
        sku=sku,
    )
    borrar(
        "operacion.producto",
        "SELECT p.ctid FROM operacion.producto p WHERE p.id_sku = :sku",
        sku=sku,
    )


def _borrar_por_locacion(borrar, loc: int) -> None:
    """
    Borra todo lo que apunta a la tienda de demostración.

    Hace falta además del filtro por SKU: el pronóstico se ejecuta para todas
    las series producto + tienda, así que deja filas en forecast_result que
    apuntan a la tienda de demo con otros productos. Si no se borran, la clave
    foránea impide eliminar la locación y la limpieza queda a medias.
    """
    borrar(
        "analitica.desperdicio_evitado",
        "SELECT de.ctid FROM analitica.desperdicio_evitado de WHERE de.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "analitica.transferencia",
        "SELECT t.ctid FROM analitica.transferencia t "
        "WHERE t.id_locacion_origen = :loc OR t.id_locacion_destino = :loc",
        loc=loc,
    )
    borrar(
        "analitica.descuento",
        "SELECT d.ctid FROM analitica.descuento d WHERE d.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "analitica.alerta",
        "SELECT a.ctid FROM analitica.alerta a WHERE a.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "analitica.orden_reabastecimiento",
        "SELECT o.ctid FROM analitica.orden_reabastecimiento o WHERE o.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "analitica.forecast_result",
        "SELECT fr.ctid FROM analitica.forecast_result fr WHERE fr.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "operacion.movimiento_inventario",
        "SELECT mi.ctid FROM operacion.movimiento_inventario mi WHERE mi.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "operacion.venta",
        "SELECT v.ctid FROM operacion.venta v WHERE v.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "operacion.merma",
        "SELECT m.ctid FROM operacion.merma m WHERE m.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "operacion.existencia",
        "SELECT e.ctid FROM operacion.existencia e WHERE e.id_locacion = :loc",
        loc=loc,
    )
    borrar(
        "operacion.lote",
        "SELECT l.ctid FROM operacion.lote l WHERE l.id_locacion_recepcion = :loc",
        loc=loc,
    )


def limpiar_demo() -> None:
    """
    Borra únicamente los datos que genera este escenario, para poder repetirlo.

    No toca el historial del ETL ni la bitácora (que es inmutable por diseño:
    un disparador de PostgreSQL impide modificarla).
    """
    sku = id_sku_por_nombre(NOMBRE_SKU_DEMO)

    print("     Limpiando restos de una ejecución anterior del escenario…")
    borrados = {}

    def borrar(etiqueta: str, sql: str, **params) -> None:
        n = escalar(f"SELECT COUNT(*) FROM ({sql}) AS t", **params)
        if n:
            # OJO: `escribir`, no `escalar`. SQLAlchemy 2.x revierte la
            # transacción al cerrar un connect(), así que un DELETE lanzado con
            # `escalar` no borraba nada y los restos de la corrida anterior
            # hacían fallar el escenario (p. ej. RFC duplicado).
            escribir(f"DELETE FROM {etiqueta} WHERE ctid IN (SELECT ctid FROM ({sql}) AS t)",
                     **params)
            borrados[etiqueta] = borrados.get(etiqueta, 0) + int(n)

    # Todo lo que cuelga del producto de demostración. Si una corrida anterior
    # se cortó a medias puede no existir el producto pero sí la tienda o el
    # proveedor, así que cada bloque es independiente.
    if sku:
        _borrar_por_sku(borrar, sku)

    # Las ventas que se quedaron sin líneas se borran ANTES que la tienda: si no,
    # la clave foránea venta.id_locacion → locacion impide borrar la locación.
    escribir("DELETE FROM operacion.venta v WHERE NOT EXISTS "
             "(SELECT 1 FROM operacion.venta_detalle vd WHERE vd.id_venta = v.id_venta)")

    # La tienda y el proveedor de demostración
    loc = id_locacion_por_nombre(TIENDA_DEMO)
    if loc:
        _borrar_por_locacion(borrar, loc)
        borrar(
            "operacion.locacion",
            "SELECT l.ctid FROM operacion.locacion l WHERE l.id_locacion = :i",
            i=loc,
        )
    prov = id_proveedor_por_rfc(RFC_DEMO)
    if prov:
        borrar(
            "operacion.proveedor",
            "SELECT pr.ctid FROM operacion.proveedor pr WHERE pr.id_proveedor = :i",
            i=prov,
        )

    for tabla, n in borrados.items():
        print(f"       {tabla}: {n} registros")
    print("     Limpieza terminada. La bitácora no se toca: es inmutable por diseño.")


# ===========================================================================
# ESCENARIO
# ===========================================================================
def escenario() -> None:
    app = create_app()
    app.config["TESTING"] = True

    hoy = date.today()
    SKU = NOMBRE_SKU_DEMO
    TIENDA = TIENDA_DEMO
    TIENDA_ORIGEN = "Tienda Cumbres"
    RFC = RFC_DEMO
    LOTE_A = "DEMO-A-001"
    LOTE_B = "DEMO-B-001"
    LOTE_EXCESO = "DEMO-EXC-001"
    LOTE_VENCIDO = "DEMO-VENC-001"
    LOTE_SOBRE = "DEMO-SOB-001"

    titulo("ESCENARIO EXTREMO A EXTREMO — FRESHTRACK (AVANCE 2)")
    print("Cada paso pasa por la capa HTTP real y escribe en PostgreSQL.")
    print("Los valores que se imprimen son consultados a la base después de cada acción.\n")
    limpiar_demo()

    with app.test_client() as c:
        # ------------------------------------------------------------------
        paso("El administrador inicia sesión contra PostgreSQL")
        r = c.post(
            "/login",
            data={"email": "admin@freshtrack.mx", "password": "Admin2026!"},
            follow_redirects=False,
        )
        comprobar(r.status_code == 302, "Login aceptado y sesión abierta",
                  f"redirige a {r.headers.get('Location')}")
        comprobar(
            escalar(
                "SELECT COUNT(*) FROM auditoria.bitacora_eventos "
                "WHERE accion = 'LOGIN' AND fecha_evento > now() - interval '2 minutes'"
            ) > 0,
            "El acceso quedó registrado en auditoria.bitacora_eventos",
        )

        # ------------------------------------------------------------------
        paso("Alta de un proveedor nuevo (CRUD real)")
        entrada(c, "/proveedores", {
            "razon_social": "Distribuidora Demo Avance 2, S.A. de C.V.",
            "rfc": RFC,
            "lead_time_dias": "2",
            "moq": "60",
            "contacto_email": "ventas@demo-avance2.mx",
            "telefono": "81 0000 0000",
        })
        id_prov = id_proveedor_por_rfc(RFC)
        comprobar(bool(id_prov), "Proveedor insertado en operacion.proveedor",
                  f"id_proveedor={id_prov}")

        # ------------------------------------------------------------------
        paso("Alta de un producto nuevo, ligado al proveedor anterior")
        entrada(c, "/productos", {
            "nombre": SKU,
            "codigo_gtin": "7503000000001",
            "categoria": "Lácteos",
            "id_proveedor": str(id_prov),
            "vida_util_estandar": "21",
            "unidad_medida": "Pieza",
            "precio_costo": "20",
            "precio_venta": "32",
            "stock_seguridad": "40",
            "punto_reorden": "60",
            "perecedero": "1",
        })
        sku = id_sku_por_nombre(SKU)
        comprobar(bool(sku), "Producto insertado en operacion.producto", f"id_sku={sku}")

        # ------------------------------------------------------------------
        paso("El producto se edita y se desactiva / reactiva (CRUD completo)")
        entrada(c, f"/productos/{sku}/editar", {
            "nombre": SKU,
            "categoria": "Lácteos",
            "id_proveedor": str(id_prov),
            "vida_util_estandar": "21",
            "unidad_medida": "Pieza",
            "precio_costo": "20",
            "precio_venta": "34.50",          # antes 32
            "stock_seguridad": "40",
            "punto_reorden": "60",
            "perecedero": "1",
        })
        editado = one(
            "SELECT precio_venta FROM operacion.producto WHERE id_sku = :s", s=sku
        )
        comprobar(float(editado["precio_venta"]) == 34.50,
                  "La edición cambió el precio en la base",
                  f"precio_venta={float(editado['precio_venta']):.2f}")

        entrada(c, f"/productos/{sku}/estado", {"activo": "0"})
        comprobar(
            escalar("SELECT NOT activo FROM operacion.producto WHERE id_sku = :s", s=sku),
            "El producto quedó desactivado en la base",
        )
        entrada(c, f"/productos/{sku}/estado", {"activo": "1"})
        comprobar(
            escalar("SELECT activo FROM operacion.producto WHERE id_sku = :s", s=sku),
            "El producto quedó reactivado en la base",
        )
        comprobar(
            escalar(
                "SELECT COUNT(*) FROM auditoria.bitacora_eventos "
                "WHERE accion = 'UPDATE_PRODUCT' AND id_registro = :s",
                s=str(sku),
            ) > 0,
            "La edición quedó auditada como UPDATE_PRODUCT",
        )

        # ------------------------------------------------------------------
        paso("Alta de una tienda nueva")
        entrada(c, "/tiendas", {
            "nombre": TIENDA,
            "tipo_locacion": "Tienda",
            "ciudad": "Monterrey",
            "direccion": "Av. Demostración 100",
        })
        id_tienda = id_locacion_por_nombre(TIENDA)
        comprobar(bool(id_tienda), "Tienda insertada en operacion.locacion",
                  f"id_locacion={id_tienda}")

        id_san_pedro = id_locacion_por_nombre("Tienda San Pedro")
        id_cumbres = id_locacion_por_nombre(TIENDA_ORIGEN)

        # ------------------------------------------------------------------
        paso("El operador de almacén entra y registra dos recepciones del mismo producto")
        c.get("/logout")
        c.post("/login", data={"email": "almacen@freshtrack.mx", "password": "Almacen2026!"})

        # Lote A: 100 unidades que caducan en 5 días (producto de 21 días de vida útil)
        entrada(c, "/lotes", {
            "id_sku": str(sku),
            "id_proveedor": str(id_prov),
            "id_locacion": str(id_tienda),
            "codigo_lote_prov": LOTE_A,
            "fecha_produccion": (hoy - timedelta(days=16)).isoformat(),
            "fecha_recepcion": hoy.isoformat(),
            "fecha_caducidad": (hoy + timedelta(days=5)).isoformat(),
            "cantidad": "100",
            "costo_unitario": "20",
            "observaciones": "Lote cercano a su caducidad",
        })
        # Lote B: 150 unidades que caducan en 20 días
        entrada(c, "/lotes", {
            "id_sku": str(sku),
            "id_proveedor": str(id_prov),
            "id_locacion": str(id_tienda),
            "codigo_lote_prov": LOTE_B,
            "fecha_produccion": (hoy - timedelta(days=1)).isoformat(),
            "fecha_recepcion": hoy.isoformat(),
            "fecha_caducidad": (hoy + timedelta(days=20)).isoformat(),
            "cantidad": "150",
            "costo_unitario": "20",
            "observaciones": "Lote con vida útil amplia",
        })

        la, lb = lote_por_codigo(LOTE_A), lote_por_codigo(LOTE_B)
        comprobar(bool(la and lb), "Ambos lotes existen en la base de datos")
        comprobar(existencia(la["id_lote"], id_tienda) == 100,
                  "Lote A: 100 unidades en existencia", f"{existencia(la['id_lote'], id_tienda)}")
        comprobar(existencia(lb["id_lote"], id_tienda) == 150,
                  "Lote B: 150 unidades en existencia", f"{existencia(lb['id_lote'], id_tienda)}")
        movs = escalar(
            "SELECT COUNT(*) FROM operacion.movimiento_inventario "
            "WHERE id_lote IN (CAST(:a AS uuid), CAST(:b AS uuid))",
            a=la["id_lote"], b=lb["id_lote"],
        )
        comprobar(movs >= 2, "Kardex: se escribieron los movimientos de entrada",
                  f"{movs} movimientos")

        # ------------------------------------------------------------------
        paso("El sistema calcula la vida útil restante y clasifica el riesgo")
        print()
        dato("Lote", "días restantes / vida útil / clasificación")
        dato(LOTE_A, f"{la['dias_restantes']} d / {float(la['vida_util_pct']):.0f}% / {la['clasificacion']}")
        dato(LOTE_B, f"{lb['dias_restantes']} d / {float(lb['vida_util_pct']):.0f}% / {lb['clasificacion']}")
        comprobar(la["clasificacion"] in ("CRITICO", "VIGILANCIA"),
                  "El lote A se clasifica como crítico o en vigilancia",
                  f"clasificación = {la['clasificacion']}")
        comprobar(lb["clasificacion"] == "NORMAL",
                  "El lote B se clasifica como normal", f"clasificación = {lb['clasificacion']}")
        comprobar(escalar("SELECT COUNT(*) FROM operacion.regla_riesgo") > 0,
                  "Los umbrales salen de operacion.regla_riesgo, no del código")

        # ------------------------------------------------------------------
        paso("Venta de 70 unidades: FEFO debe consumir primero el lote A")
        # La venta la registra el gerente de tienda: el rol de almacén no tiene
        # permiso sobre la pantalla de ventas y la petición sería rechazada.
        c.get("/logout")
        c.post("/login", data={"email": "gerente@freshtrack.mx", "password": "Tienda2026!"})
        entrada(c, "/ventas", {
            "id_locacion": str(id_tienda),
            "id_sku": str(sku),
            "cantidad": "70",
        })
        a_despues = existencia(la["id_lote"], id_tienda)
        b_despues = existencia(lb["id_lote"], id_tienda)
        comprobar(a_despues == 30, "Lote A descontado de 100 a 30 unidades", f"queda {a_despues}")
        comprobar(b_despues == 150, "Lote B intacto en 150 unidades", f"queda {b_despues}")

        lineas = query(
            """
            SELECT vd.cantidad, vd.id_lote::text, l.codigo_lote_prov
            FROM operacion.venta_detalle vd
            JOIN operacion.lote l ON l.id_lote = vd.id_lote
            WHERE vd.id_sku = :sku AND vd.id_locacion = :loc
            ORDER BY vd.fecha_transaccion DESC
            LIMIT 3
            """,
            sku=sku, loc=id_tienda,
        )
        print()
        for li in lineas:
            dato(f"Línea de venta sobre {li['codigo_lote_prov']}", f"{float(li['cantidad']):.2f} unidades")
        comprobar(
            any(li["codigo_lote_prov"] == LOTE_A for li in lineas),
            "La venta quedó registrada en venta_detalle sobre el lote A",
        )
        comprobar(
            escalar(
                "SELECT COUNT(*) FROM operacion.venta WHERE fecha_venta::date = CURRENT_DATE"
            ) > 0,
            "Se generó el encabezado de venta con su folio",
        )

        # ------------------------------------------------------------------
        paso("El planeador ejecuta el pronóstico de demanda")
        c.get("/logout")
        c.post("/login", data={"email": "planner@freshtrack.mx", "password": "Plan2026!"})
        entrada(c, "/pronostico/ejecutar", {
            "metodo": "SUAVIZACION_EXPONENCIAL",
            "horizonte": "7",
            "ventana": "28",
            "alpha": "0.30",
            "dias_historia": "120",
            "id_locacion": "",
        })
        corrida = one(
            """
            SELECT id_run::text, metodo, n_series, mae, rmse, wmape, horizonte_dias
            FROM analitica.forecast_run
            WHERE estado = 'COMPLETADO'
            ORDER BY fecha_ejecucion DESC LIMIT 1
            """
        )
        comprobar(bool(corrida), "La corrida de pronóstico se guardó en forecast_run")
        if corrida:
            dato("Método", corrida["metodo"])
            dato("Series producto + tienda", corrida["n_series"])
            dato("Horizonte", f"{corrida['horizonte_dias']} días")
            dato("MAE", f"{float(corrida['mae']):.4f}")
            dato("RMSE", f"{float(corrida['rmse']):.4f}")
            dato("WMAPE", f"{float(corrida['wmape']):.4f} %")
            comprobar(corrida["n_series"] > 0,
                      "El pronóstico se calculó por producto y tienda, no de forma global")
            comprobar(
                escalar(
                    "SELECT COUNT(*) FROM analitica.forecast_result WHERE id_run = CAST(:r AS uuid)",
                    r=corrida["id_run"],
                ) > 0,
                "Los resultados quedaron persistidos en forecast_result",
            )
            comprobar(corrida["mae"] is not None,
                      "El error del pronóstico está medido, no supuesto")

        # ------------------------------------------------------------------
        paso("Reabastecimiento: el motor calcula la necesidad real")
        entrada(c, "/reabastecimiento/generar", {"horizonte": "7"})
        total_ordenes = escalar("SELECT COUNT(*) FROM analitica.orden_reabastecimiento")
        comprobar(total_ordenes > 0, "Se generaron órdenes de reabastecimiento",
                  f"{total_ordenes} en total")

        orden = one(
            """
            SELECT o.id_orden::text, o.demanda_pronosticada, o.inventario_fisico,
                   o.inventario_riesgo, o.inventario_util, o.entradas_confirmadas,
                   o.stock_seguridad, o.necesidad_neta, o.cantidad_sugerida,
                   o.lead_time_dias, o.moq, o.prioridad, o.explicacion,
                   p.nombre AS producto, loc.nombre AS locacion
            FROM analitica.orden_reabastecimiento o
            JOIN operacion.producto p   ON p.id_sku = o.id_sku
            JOIN operacion.locacion loc ON loc.id_locacion = o.id_locacion
            ORDER BY CASE o.prioridad WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 ELSE 3 END,
                     o.fecha_creacion DESC
            LIMIT 1
            """
        )
        if orden:
            print()
            dato("Producto / tienda", f"{orden['producto']} / {orden['locacion']}")
            dato("Demanda pronosticada", f"{float(orden['demanda_pronosticada']):.2f}")
            dato("Inventario físico", f"{float(orden['inventario_fisico']):.2f}")
            dato("Inventario en riesgo", f"{float(orden['inventario_riesgo']):.2f}")
            dato("Inventario útil", f"{float(orden['inventario_util']):.2f}")
            dato("Entradas confirmadas", f"{float(orden['entradas_confirmadas']):.2f}")
            dato("Stock de seguridad", f"{float(orden['stock_seguridad']):.2f}")
            dato("Necesidad neta", f"{float(orden['necesidad_neta']):.2f}")
            dato("Cantidad sugerida", f"{float(orden['cantidad_sugerida']):.2f}")
            dato("Lead time / MOQ", f"{orden['lead_time_dias']} d / {float(orden['moq']):.0f}")
            print("\n     Explicación guardada con la orden:")
            for linea in (orden["explicacion"] or "").splitlines():
                print(f"       {linea}")
            # La fórmula completa que usa el motor:
            #   necesidad = demanda + stock de seguridad − inventario útil − entradas confirmadas
            esperado = (
                float(orden["demanda_pronosticada"])
                + float(orden["stock_seguridad"])
                - float(orden["inventario_util"])
                - float(orden["entradas_confirmadas"])
            )
            comprobar(
                abs(float(orden["necesidad_neta"]) - esperado) < 1.0,
                "La necesidad neta cuadra con demanda + seguridad − útil − entradas confirmadas",
                f"calculado {esperado:.2f} vs guardado "
                f"{float(orden['necesidad_neta']):.2f}",
            )

        # ------------------------------------------------------------------
        paso("El gerente de tienda aprueba una orden de reabastecimiento")
        c.get("/logout")
        c.post("/login", data={"email": "gerente@freshtrack.mx", "password": "Tienda2026!"})

        pendiente = one(
            """
            SELECT id_orden::text, cantidad_sugerida, prioridad
            FROM analitica.orden_reabastecimiento
            WHERE estado = 'PENDIENTE'
            ORDER BY CASE prioridad WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 ELSE 3 END
            LIMIT 1
            """
        )
        comprobar(bool(pendiente), "Hay órdenes pendientes de decisión humana")
        if pendiente:
            entrada(c, f"/reabastecimiento/{pendiente['id_orden']}/decidir", {
                "decision": "aprobar",
                "cantidad": f"{float(pendiente['cantidad_sugerida']):.2f}",
            })
            estado_orden = escalar(
                "SELECT estado FROM analitica.orden_reabastecimiento WHERE id_orden = CAST(:o AS uuid)",
                o=pendiente["id_orden"],
            )
            dato("Orden de reabastecimiento", f"{pendiente['id_orden'][:8]}… ({pendiente['prioridad']})")
            dato("Estado tras la decisión", estado_orden)
            comprobar(estado_orden == "APROBADA",
                      "La orden quedó aprobada por una persona", f"estado = {estado_orden}")
            comprobar(
                escalar(
                    "SELECT COUNT(*) FROM auditoria.bitacora_eventos "
                    "WHERE accion = 'APPROVE_REPLENISHMENT' AND id_registro = :o",
                    o=pendiente["id_orden"],
                ) > 0,
                "La decisión quedó auditada como APPROVE_REPLENISHMENT",
            )

            # Una segunda orden se rechaza: la decisión humana se registra igual.
            otra = one(
                """
                SELECT id_orden::text FROM analitica.orden_reabastecimiento
                WHERE estado = 'PENDIENTE' ORDER BY fecha_creacion DESC LIMIT 1
                """
            )
            if otra:
                entrada(c, f"/reabastecimiento/{otra['id_orden']}/decidir", {"decision": "rechazar"})
                comprobar(
                    escalar(
                        "SELECT estado FROM analitica.orden_reabastecimiento "
                        "WHERE id_orden = CAST(:o AS uuid)",
                        o=otra["id_orden"],
                    ) == "RECHAZADA",
                    "Una orden rechazada queda marcada como RECHAZADA y auditada",
                )

        # ------------------------------------------------------------------
        paso("Transferencia entre tiendas: exceso en una, faltante en otra")
        print("     El motor decide el par origen→destino; el guion solo prepara")
        print("     las condiciones. Para que exista exceso en una tienda hacen falta")
        print("     dos cosas: que esa tienda VENDA el producto (si no lo vende, todo")
        print("     su inventario cuenta como riesgo) y que tenga varias recepciones.")
        # 1) Recepciones en la tienda origen, con vida útil suficiente para que
        #    pase la validación «llega antes de vencer».
        for n_lote, dias in enumerate((12, 14, 16), start=1):
            entrada(c, "/lotes", {
                "id_sku": str(sku),
                "id_proveedor": str(id_prov),
                "id_locacion": str(id_cumbres),
                "codigo_lote_prov": f"{LOTE_EXCESO}-{n_lote}",
                "fecha_produccion": (hoy - timedelta(days=6)).isoformat(),
                "fecha_recepcion": hoy.isoformat(),
                "fecha_caducidad": (hoy + timedelta(days=dias)).isoformat(),
                "cantidad": "400",
                "costo_unitario": "20",
                "observaciones": f"Exceso {n_lote} en una tienda que otra puede vender",
            })
        exc = lote_por_codigo(f"{LOTE_EXCESO}-1")
        comprobar(bool(exc), "Tres recepciones de exceso en Tienda Cumbres",
                  f"{existencia(exc['id_lote'], id_cumbres) if exc else 0} unidades en el primero")

        # 2) Demanda del producto en la tienda origen: la venta pasa por FEFO.
        entrada(c, "/ventas", {
            "id_locacion": str(id_cumbres),
            "id_sku": str(sku),
            "cantidad": "70",
        })

        entrada(c, "/transferencias/detectar", {})
        transferencias = query(
            """
            SELECT t.id_transferencia::text, t.cantidad, t.exceso_origen,
                   t.faltante_destino, t.dias_para_vencer, t.validaciones,
                   t.estado, o.nombre AS origen, d.nombre AS destino,
                   p.nombre AS producto
            FROM analitica.transferencia t
            JOIN operacion.locacion o ON o.id_locacion = t.id_locacion_origen
            JOIN operacion.locacion d ON d.id_locacion = t.id_locacion_destino
            JOIN operacion.producto p ON p.id_sku = t.id_sku
            WHERE t.estado = 'SUGERIDA'
            ORDER BY t.fecha_creacion DESC
            """
        )
        comprobar(len(transferencias) > 0, "Se detectaron oportunidades de transferencia",
                  f"{len(transferencias)} sugerencias")
        if transferencias:
            # Se prefiere una sugerencia del producto de la demostración, para
            # que el movimiento de inventario se pueda comprobar contra un lote
            # conocido; si no la hay, se toma la primera.
            t = next((x for x in transferencias if x["producto"] == SKU), transferencias[0])
            print()
            dato("Producto", t["producto"])
            dato("Ruta sugerida", f"{t['origen']} → {t['destino']}")
            dato("Cantidad", f"{float(t['cantidad']):.2f}")
            dato("Exceso en el origen", f"{float(t['exceso_origen']):.2f}")
            dato("Faltante en el destino", f"{float(t['faltante_destino']):.2f}")
            dato("Días para vencer", t["dias_para_vencer"])
            print("\n     Validaciones guardadas:")
            for clave, v in (t["validaciones"] or {}).items():
                print(f"       [{'PASA' if v['pasa'] else 'NO PASA'}] {clave}: {v['detalle']}")
            comprobar(
                all(v["pasa"] for v in (t["validaciones"] or {}).values()),
                "Las cuatro validaciones están guardadas y pasan",
            )

            # --------------------------------------------------------------
            paso("El gerente de tienda aprueba y ejecuta la transferencia")
            c.get("/logout")
            c.post("/login", data={"email": "gerente@freshtrack.mx", "password": "Tienda2026!"})

            id_tr = t["id_transferencia"]
            entrada(c, f"/transferencias/{id_tr}/decidir",
                    {"decision": "aprobar", "cantidad": f"{float(t['cantidad']):.2f}"})
            estado = escalar(
                "SELECT estado FROM analitica.transferencia WHERE id_transferencia = CAST(:i AS uuid)",
                i=id_tr,
            )
            comprobar(estado == "APROBADA", "La transferencia quedó aprobada", f"estado = {estado}")
            comprobar(
                escalar(
                    "SELECT COUNT(*) FROM auditoria.bitacora_eventos "
                    "WHERE accion = 'APPROVE_TRANSFER' AND id_registro = :i",
                    i=id_tr,
                ) > 0,
                "La aprobación quedó en la bitácora con el usuario que decidió",
            )

            lote_tr = escalar(
                "SELECT id_lote::text FROM analitica.transferencia WHERE id_transferencia = CAST(:i AS uuid)",
                i=id_tr,
            )
            id_origen = escalar(
                "SELECT id_locacion_origen FROM analitica.transferencia WHERE id_transferencia = CAST(:i AS uuid)",
                i=id_tr,
            )
            id_destino = escalar(
                "SELECT id_locacion_destino FROM analitica.transferencia WHERE id_transferencia = CAST(:i AS uuid)",
                i=id_tr,
            )
            o_antes = existencia(lote_tr, id_origen)
            d_antes = existencia(lote_tr, id_destino)

            entrada(c, f"/transferencias/{id_tr}/ejecutar", {})
            o_despues = existencia(lote_tr, id_origen)
            d_despues = existencia(lote_tr, id_destino)
            cantidad = float(t["cantidad"])

            dato("Existencia en el origen", f"{o_antes:.2f} → {o_despues:.2f}")
            dato("Existencia en el destino", f"{d_antes:.2f} → {d_despues:.2f}")
            comprobar(abs((o_antes - o_despues) - cantidad) < 0.01,
                      "El origen se descontó exactamente la cantidad transferida")
            comprobar(abs((d_despues - d_antes) - cantidad) < 0.01,
                      "El destino se incrementó exactamente la cantidad transferida")
            comprobar(
                escalar(
                    "SELECT COUNT(*) FROM analitica.transferencia "
                    "WHERE id_transferencia = CAST(:i AS uuid) AND estado = 'EJECUTADA'",
                    i=id_tr,
                ) == 1,
                "La transferencia quedó marcada como ejecutada",
            )
            comprobar(
                escalar(
                    "SELECT COUNT(*) FROM analitica.desperdicio_evitado "
                    "WHERE id_transferencia = CAST(:i AS uuid)",
                    i=id_tr,
                ) == 1,
                "Se registró el desperdicio evitado con su metodología",
            )

        # ------------------------------------------------------------------
        paso("Descuento sugerido para un lote por vencer, con aprobación humana")
        # El gerente sigue con la sesión abierta desde el paso anterior.
        entrada(c, "/descuentos/generar", {})
        desc = one(
            """
            SELECT d.id_descuento::text, d.descuento_pct, d.precio_normal,
                   d.precio_nuevo, d.cantidad, d.dias_restantes, d.ingreso_potencial,
                   l.codigo_lote_prov
            FROM analitica.descuento d
            JOIN operacion.lote l ON l.id_lote = d.id_lote
            WHERE d.estado = 'SUGERIDO'
            ORDER BY d.descuento_pct DESC
            LIMIT 1
            """
        )
        comprobar(bool(desc), "El motor sugirió al menos un descuento")
        if desc:
            dato("Lote", desc["codigo_lote_prov"])
            dato("Días para vencer", desc["dias_restantes"])
            dato("Descuento", f"{float(desc['descuento_pct']):.1f}%")
            dato("Precio", f"{float(desc['precio_normal']):.2f} → "
                           f"{float(desc['precio_nuevo']):.2f}")
            dato("Ingreso potencial", f"{float(desc['ingreso_potencial']):.2f}")
            comprobar(
                float(desc["precio_nuevo"]) < float(desc["precio_normal"]),
                "El precio con descuento es menor que el precio normal",
            )
            entrada(c, f"/descuentos/{desc['id_descuento']}/decidir", {"decision": "aprobar"})
            comprobar(
                escalar(
                    "SELECT estado FROM analitica.descuento "
                    "WHERE id_descuento = CAST(:d AS uuid)",
                    d=desc["id_descuento"],
                ) == "APROBADO",
                "El descuento quedó aprobado por una persona",
            )
            comprobar(
                escalar(
                    "SELECT COUNT(*) FROM auditoria.bitacora_eventos "
                    "WHERE accion = 'APPROVE_DISCOUNT' AND id_registro = :d",
                    d=desc["id_descuento"],
                ) > 0,
                "La aprobación quedó auditada como APPROVE_DISCOUNT",
            )

        # ------------------------------------------------------------------
        paso("El operador registra una merma sobre el lote A")
        c.get("/logout")
        c.post("/login", data={"email": "almacen@freshtrack.mx", "password": "Almacen2026!"})

        antes_merma = existencia(la["id_lote"], id_tienda)
        entrada(c, "/mermas", {
            "id_locacion": str(id_tienda),
            "id_lote": la["id_lote"],
            "cantidad": "12",
            "causa_merma": "CADUCIDAD",
            "observacion": "Producto vencido detectado en anaquel",
        })
        despues_merma = existencia(la["id_lote"], id_tienda)
        dato("Existencia del lote A", f"{antes_merma:.2f} → {despues_merma:.2f}")
        comprobar(despues_merma == antes_merma - 12,
                  "La merma descontó el inventario real", f"quedan {despues_merma}")

        merma = one(
            """
            SELECT m.cantidad, m.causa_merma, m.valor_merma, u.nombre_completo AS responsable
            FROM operacion.merma m
            JOIN operacion.usuario u ON u.id_usuario = m.id_usuario
            WHERE m.id_lote = CAST(:l AS uuid)
            ORDER BY m.fecha_registro DESC LIMIT 1
            """,
            l=la["id_lote"],
        )
        if merma:
            dato("Merma registrada", f"{float(merma['cantidad']):.2f} por {merma['causa_merma']}")
            dato("Valor de la merma", f"{float(merma['valor_merma']):.2f}")
            dato("Responsable", merma["responsable"])
        comprobar(
            escalar(
                "SELECT COUNT(*) FROM auditoria.bitacora_eventos "
                "WHERE accion = 'REGISTER_SHRINKAGE' AND fecha_evento > now() - interval '2 minutes'"
            ) > 0,
            "La merma quedó en la bitácora (REGISTER_SHRINKAGE)",
        )

        # Se intenta una merma imposible: no debe escribir nada.
        mermas_antes = escalar("SELECT COUNT(*) FROM operacion.merma")
        entrada(c, "/mermas", {
            "id_locacion": str(id_tienda),
            "id_lote": la["id_lote"],
            "cantidad": "999999",
            "causa_merma": "DAÑO",
            "observacion": "Prueba de validación",
        })
        mermas_despues = escalar("SELECT COUNT(*) FROM operacion.merma")
        comprobar(mermas_antes == mermas_despues,
                  "Una merma mayor a la existencia se rechaza sin escribir nada",
                  f"{mermas_antes} → {mermas_despues} registros")

        # ------------------------------------------------------------------
        paso("Se cargan los dos casos extremos que faltaban: lote vencido y sobreinventario")
        # Los siete tipos de alerta están implementados, pero con un almacén
        # "bien administrado" dos de ellos nunca se disparan: hace falta un lote
        # que ya haya caducado con existencia, y una tienda con cobertura muy
        # por encima del umbral. Se cargan aquí, con recepciones históricas
        # reales (no se inyectan filas de alerta: las derivará el motor).
        c.get("/logout")
        c.post("/login", data={"email": "almacen@freshtrack.mx", "password": "Almacen2026!"})

        # Recepción de hace 20 días, caducada hace 3: el almacén la tiene en
        # anaquel todavía, que es exactamente lo que el motor debe detectar.
        entrada(c, "/lotes", {
            "id_sku": str(sku),
            "id_proveedor": str(id_prov),
            "id_locacion": str(id_tienda),
            "codigo_lote_prov": LOTE_VENCIDO,
            "fecha_produccion": (hoy - timedelta(days=30)).isoformat(),
            "fecha_recepcion": (hoy - timedelta(days=20)).isoformat(),
            "fecha_caducidad": (hoy - timedelta(days=3)).isoformat(),
            "cantidad": "40",
            "costo_unitario": "20",
            "observaciones": "Recepción antigua que ya caducó en anaquel",
        })
        lv = lote_por_codigo(LOTE_VENCIDO)
        comprobar(bool(lv), "El lote vencido existe y conserva existencia",
                  f"id_lote={lv['id_lote'] if lv else None}")
        if lv:
            comprobar(int(lv["dias_restantes"]) < 0,
                      "El sistema calcula días restantes negativos desde la fecha de caducidad",
                      f"{lv['dias_restantes']} días")
            comprobar(existencia(lv["id_lote"], id_tienda) == 40,
                      "Quedan 40 unidades del lote caducado en la tienda",
                      f"{existencia(lv['id_lote'], id_tienda):.2f}")

        # Cobertura excesiva: el motor marca SOBREINVENTARIO cuando el inventario
        # útil supera el umbral de días de demanda de la configuración.
        for i, dias in enumerate((18, 20, 22), start=1):
            entrada(c, "/lotes", {
                "id_sku": str(sku),
                "id_proveedor": str(id_prov),
                "id_locacion": str(id_cumbres),
                "codigo_lote_prov": f"{LOTE_SOBRE}-{i}",
                "fecha_produccion": (hoy - timedelta(days=11)).isoformat(),
                "fecha_recepcion": (hoy - timedelta(days=10)).isoformat(),
                "fecha_caducidad": (hoy + timedelta(days=dias)).isoformat(),
                "cantidad": "400",
                "costo_unitario": "20",
                "observaciones": "Compra de volumen sin demanda que la respalde",
            })

        # ------------------------------------------------------------------
        paso("Las alertas se derivan de los datos, no se capturan a mano")
        c.get("/logout")
        c.post("/login", data={"email": "admin@freshtrack.mx", "password": "Admin2026!"})
        entrada(c, "/alertas/regenerar", {})

        por_tipo = query(
            "SELECT tipo, COUNT(*) AS n FROM analitica.alerta "
            "WHERE estado = 'ABIERTA' GROUP BY tipo ORDER BY n DESC"
        )
        comprobar(len(por_tipo) > 0, "Hay alertas abiertas derivadas de reglas",
                  f"{sum(int(f['n']) for f in por_tipo)} alertas")
        print()
        for f in por_tipo:
            dato(f["tipo"], f["n"])
        comprobar(
            escalar("SELECT COUNT(*) FROM analitica.alerta WHERE huella IS NOT NULL") > 0,
            "Cada alerta lleva su huella, lo que evita duplicados mientras siga abierta",
        )
        # La rúbrica nombra siete tipos: se comprueba que el motor cubre los siete.
        presentes = {f["tipo"] for f in por_tipo}
        faltan = set(TIPOS_ALERTA) - presentes
        comprobar(not faltan, "Los siete tipos de alerta de la rúbrica se generaron",
                  "todos presentes" if not faltan else f"faltan: {sorted(faltan)}")

        # ------------------------------------------------------------------
        paso("El panel de control se alimenta de todo lo anterior")
        r = c.get("/panel")
        comprobar(r.status_code == 200, "El panel responde con las métricas reales")
        print()
        dato("Unidades de inventario",
             f"{float(escalar('SELECT COALESCE(SUM(cantidad_disponible),0) FROM operacion.v_inventario_lote')):.2f}")
        dato("Unidades vendidas (histórico)",
             f"{float(escalar('SELECT COALESCE(SUM(cantidad),0) FROM operacion.venta_detalle')):.2f}")
        dato("Unidades mermadas (histórico)",
             f"{float(escalar('SELECT COALESCE(SUM(cantidad),0) FROM operacion.merma')):.2f}")
        dato("Órdenes de reabastecimiento",
             escalar("SELECT COUNT(*) FROM analitica.orden_reabastecimiento"))
        dato("Transferencias ejecutadas",
             escalar("SELECT COUNT(*) FROM analitica.transferencia WHERE estado = 'EJECUTADA'"))
        dato("Alertas abiertas",
             escalar("SELECT COUNT(*) FROM analitica.alerta WHERE estado = 'ABIERTA'"))
        dato("Corridas de pronóstico",
             escalar("SELECT COUNT(*) FROM analitica.forecast_run WHERE estado = 'COMPLETADO'"))

        # ------------------------------------------------------------------
        paso("El auditor consulta la trazabilidad del lote A")
        c.get("/logout")
        c.post("/login", data={"email": "auditor@freshtrack.mx", "password": "Auditor2026!"})
        r = c.get(f"/trazabilidad?lote={la['id_lote']}")
        comprobar(r.status_code == 200, "La pantalla de trazabilidad responde")

        recibido = float(la["cantidad_recibida"])
        vendido = float(escalar(
            "SELECT COALESCE(SUM(cantidad),0) FROM operacion.venta_detalle "
            "WHERE id_lote = CAST(:l AS uuid)", l=la["id_lote"]) or 0)
        mermado = float(escalar(
            "SELECT COALESCE(SUM(cantidad),0) FROM operacion.merma "
            "WHERE id_lote = CAST(:l AS uuid)", l=la["id_lote"]) or 0)
        print()
        dato("Lote A — recibido", f"{recibido:.2f}")
        dato("Lote A — vendido (FEFO)", f"{vendido:.2f}")
        dato("Lote A — mermado", f"{mermado:.2f}")
        dato("Lote A — en existencia hoy",
             f"{sum(existencia(la['id_lote'], l) for l in [id_tienda, id_cumbres, id_san_pedro]):.2f}")
        comprobar(
            escalar(
                "SELECT COUNT(*) FROM operacion.movimiento_inventario "
                "WHERE id_lote = CAST(:l AS uuid)", l=la["id_lote"],
            ) >= 3,
            "El kardex reconstruye la vida del lote: entrada, ventas y merma",
        )

        # ------------------------------------------------------------------
        paso("La API JSON con JWT también opera sobre los mismos datos")
        c.get("/logout")
        tok = c.post("/api/auth/token",
                     json={"email": "planner@freshtrack.mx", "password": "Plan2026!"})
        comprobar(tok.status_code == 200, "La API emite un token JWT")
        token = tok.get_json().get("token") if tok.status_code == 200 else None
        if token:
            cab = {"Authorization": f"Bearer {token}"}
            for ruta in ["/api/kpis", "/api/inventario", "/api/alertas", "/api/pronostico"]:
                rr = c.get(ruta, headers=cab)
                comprobar(rr.status_code == 200, f"{ruta} responde con el token", f"{rr.status_code}")
            sin_token = c.get("/api/kpis")
            comprobar(sin_token.status_code == 401,
                      "Sin token, la API rechaza la petición", f"{sin_token.status_code}")

    # ----------------------------------------------------------------------
    titulo("RESUMEN DEL ESCENARIO")
    if _fallos:
        print(f"Comprobaciones fallidas: {len(_fallos)}")
        for f in _fallos:
            print(f"  - {f}")
    else:
        print("Todas las comprobaciones pasaron.")
    print("\nLos datos siguen en PostgreSQL. Ejecuta:")
    print("    python scripts/demo_avance2.py --verificar")
    print("para comprobarlo desde un proceso nuevo, sin Flask en memoria.")


# ===========================================================================
# VERIFICACIÓN DE PERSISTENCIA (proceso independiente)
# ===========================================================================
def verificar() -> None:
    app = create_app()
    app.config["TESTING"] = True

    titulo("VERIFICACIÓN DE PERSISTENCIA")
    print("Este proceso acaba de arrancar. No compartió memoria con el escenario.")
    print("Todo lo que sigue se lee de PostgreSQL.\n")

    tablas = [
        ("operacion.producto", "Productos"),
        ("operacion.proveedor", "Proveedores"),
        ("operacion.locacion", "Tiendas y CEDIS"),
        ("operacion.usuario", "Usuarios"),
        ("operacion.lote", "Lotes"),
        ("operacion.existencia", "Existencias por lote y ubicación"),
        ("operacion.movimiento_inventario", "Movimientos de kardex"),
        ("operacion.venta", "Ventas"),
        ("operacion.venta_detalle", "Líneas de venta"),
        ("operacion.merma", "Mermas"),
        ("analitica.forecast_run", "Corridas de pronóstico"),
        ("analitica.forecast_result", "Resultados de pronóstico"),
        ("analitica.orden_reabastecimiento", "Órdenes de reabastecimiento"),
        ("analitica.transferencia", "Transferencias"),
        ("analitica.alerta", "Alertas"),
        ("analitica.desperdicio_evitado", "Registros de desperdicio evitado"),
        ("auditoria.bitacora_eventos", "Eventos de auditoría"),
    ]
    print(f"     {'Tabla':<38} {'Registros':>10}")
    print("     " + "-" * 50)
    for tabla, etiqueta in tablas:
        n = escalar(f"SELECT COUNT(*) FROM {tabla}")
        print(f"     {etiqueta:<38} {n:>10}")

    print("\n     Escenario de demostración encontrado en la base:")
    demo = one(
        """
        SELECT p.nombre AS producto, pr.razon_social AS proveedor,
               p.id_sku, p.vida_util_estandar
        FROM operacion.producto p
        LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        WHERE p.nombre = :n
        """,
        n=NOMBRE_SKU_DEMO,
    )
    if demo:
        print(f"       Producto: {demo['producto']} (SKU {demo['id_sku']}) · "
              f"proveedor {demo['proveedor']}")
    tienda_demo = id_locacion_por_nombre("Tienda Demostración")
    if tienda_demo:
        print(f"       Tienda de demostración: id_locacion={tienda_demo}")

    for codigo in ("DEMO-A-001", "DEMO-B-001", "DEMO-EXC-001"):
        lote = lote_por_codigo(codigo)
        if lote:
            print(f"       Lote {codigo}: {float(lote['cantidad_recibida']):.0f} recibidas, "
                  f"{lote['dias_restantes']} días restantes, {lote['clasificacion']}")

    print("\n     Última corrida de pronóstico:")
    corrida = one(
        "SELECT metodo, n_series, mae, rmse, wmape, fecha_ejecucion "
        "FROM analitica.forecast_run WHERE estado='COMPLETADO' "
        "ORDER BY fecha_ejecucion DESC LIMIT 1"
    )
    if corrida:
        print(f"       {corrida['metodo']} · {corrida['n_series']} series · "
              f"MAE {float(corrida['mae']):.4f} · WMAPE {float(corrida['wmape']):.4f}% · "
              f"{corrida['fecha_ejecucion']}")
    else:
        print("       (no hay corridas)")

    print("\n     Últimos eventos de la bitácora:")
    for e in query(
        "SELECT accion, nombre_tabla, descripcion, fecha_evento "
        "FROM auditoria.bitacora_eventos ORDER BY fecha_evento DESC LIMIT 8"
    ):
        print(f"       {e['fecha_evento']}  {e['accion']:<26} {e['nombre_tabla']}")

    print("\n     Comprobación con la aplicación web ya reiniciada:")
    with app.test_client() as c:
        # Sin sesión, una ruta privada debe mandar al login (protección real).
        r = c.get("/inventario")
        print(f"       GET /inventario sin sesión → HTTP {r.status_code} "
              f"(redirige a {r.headers.get('Location')})")
        comprobar(r.status_code == 302, "Las rutas privadas siguen protegidas tras reiniciar")

        # Con sesión de administrador se leen las mismas filas de PostgreSQL.
        c.post("/login", data={"email": "admin@freshtrack.mx", "password": "Admin2026!"})
        for ruta in ("/panel", "/inventario", "/lotes"):
            r = c.get(ruta)
            print(f"       GET {ruta} tras reiniciar → HTTP {r.status_code}")
            comprobar(r.status_code == 200, f"{ruta} responde con datos persistidos")

        # Y el producto de la demostración sigue apareciendo en el inventario.
        ruta_inv = f"/inventario?locacion={tienda_demo}" if tienda_demo else "/inventario"
        html = c.get(ruta_inv).get_data(as_text=True)
        comprobar(
            NOMBRE_SKU_DEMO in html,
            "El producto de la demostración se ve en el inventario tras reiniciar",
        )
    print("\nLa información continúa existiendo porque está almacenada en PostgreSQL,")
    print("no en la memoria del proceso de Flask.")

    print()
    if _fallos:
        print(f"Comprobaciones fallidas: {len(_fallos)}")
        for f in _fallos:
            print(f"  - {f}")
    else:
        print("Persistencia verificada: todas las comprobaciones pasaron.")


def main() -> None:
    p = argparse.ArgumentParser(description="Demostración extremo a extremo de FreshTrack")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--escenario", action="store_true", help="Ejecuta el guion completo")
    g.add_argument("--verificar", action="store_true", help="Relee todo desde PostgreSQL")
    args = p.parse_args()

    if args.escenario:
        escenario()
    else:
        verificar()


if __name__ == "__main__":
    main()
