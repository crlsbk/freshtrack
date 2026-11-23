"""Pruebas unitarias de los motores nuevos y seguridad Fail-Closed."""

from __future__ import annotations

from datetime import date, timedelta

from app import security
from app.domain import pronostico as p
from app.domain.reabastecimiento import optimizar_newsvendor
from app.domain.triaje import decidir_ruta_lote
from app.domain.ventas import repartir_fefo
from app.services import cache_service


def test_fefo_excluye_lotes_bloqueados_cuarentena_y_caducados():
    lotes = [
        {"id_lote": "bloqueado", "cantidad_disponible": 20, "cantidad_reservada": 0, "costo_unitario": 10, "estado": "BLOQUEADO", "dias_restantes": 2},
        {"id_lote": "cuarentena", "cantidad_disponible": 20, "cantidad_reservada": 0, "costo_unitario": 10, "estado": "CUARENTENA", "dias_restantes": 2},
        {"id_lote": "vencido", "cantidad_disponible": 20, "cantidad_reservada": 0, "costo_unitario": 10, "estado": "DISPONIBLE", "dias_restantes": -1},
        {"id_lote": "elegible", "cantidad_disponible": 15, "cantidad_reservada": 5, "costo_unitario": 10, "estado": "DISPONIBLE", "dias_restantes": 3},
    ]
    consumos = repartir_fefo(lotes, 10)
    assert [(c["id_lote"], c["consumido"]) for c in consumos] == [("elegible", 10)]


def test_newsvendor_optimiza_costo_y_respeta_caducidad():
    nv = optimizar_newsvendor(
        precio_venta=50.0,
        precio_costo=20.0,
        demanda_media=100.0,
        desviacion_estandar=20.0,
        vida_util_dias=7,
        demanda_diaria=15.0,
        stock_util=20.0,
        entradas=0.0,
        stock_seguridad_simple=10.0,
    )
    assert nv["costo_faltante"] == 30.0
    assert nv["costo_excedente"] > 0
    assert 0.5 < nv["fractil_critico"] < 1.0
    # Vida útil 7 días * 15/día = 105 max stock objetivo -> 105 - 20 = 85 max pedido
    assert nv["stock_objetivo_newsvendor"] <= 105.0
    assert nv["costo_esperado_newsvendor"] <= nv["costo_esperado_simple"] + 1e-6


def test_triaje_elige_traslado_descuento_y_merma():
    # 1. Caducado -> MERMA
    m = decidir_ruta_lote(
        estado_lote="DISPONIBLE",
        dias_restantes=-1,
        cantidad_disponible=10,
        demanda_diaria_origen=2,
        precio_venta=50,
        precio_costo=30,
    )
    assert m["accion"] == "MERMA"

    # 2. Exceso con tienda destino deficitaria y tiempo suficiente -> TRASLADO
    t = decidir_ruta_lote(
        estado_lote="DISPONIBLE",
        dias_restantes=4,
        cantidad_disponible=40,
        demanda_diaria_origen=2,
        precio_venta=60,
        precio_costo=30,
        mejor_destino={"id_locacion": 4, "nombre": "Tienda Cumbres", "faltante": 30, "demanda_diaria": 10},
    )
    assert t["accion"] == "TRASLADO"
    assert t["valor_traslado_neto"] >= t["valor_descuento_neto"]

    # 3. Riesgo urgente (vence en 1 día, no llega traslado) -> DESCUENTO local
    d = decidir_ruta_lote(
        estado_lote="DISPONIBLE",
        dias_restantes=1,
        cantidad_disponible=20,
        demanda_diaria_origen=4,
        precio_venta=60,
        precio_costo=30,
        mejor_destino={"id_locacion": 4, "nombre": "Tienda Cumbres", "faltante": 30, "demanda_diaria": 10},
    )
    assert d["accion"] == "DESCUENTO"
    assert d["valor_descuento_neto"] > 0


def test_pronostico_calcula_sesgo_y_naive():
    m = p._metricas([10, 0, 20, 0], [12, 2, 22, 2])
    assert m["sesgo"] == 2.0  # sobreestima por +2
    assert m["demanda_intermitente"] is True

    base = date(2026, 10, 1)
    serie = [(base + timedelta(days=i), float(10 + (i % 7))) for i in range(60)]
    res = p.pronosticar_serie(serie, "SUAVIZACION_EXPONENCIAL", horizonte=7, ventana=28, alpha=0.3, fecha_base=serie[-1][0])
    assert "metricas_naive" in res
    assert res["metricas"]["sesgo"] is not None


def test_seguridad_fail_closed_sin_redis_ni_postgres(monkeypatch):
    monkeypatch.setattr(cache_service, "_client", None)
    monkeypatch.setattr(cache_service, "_ultimo_fallo", 10**12)  # evita intentar conectar

    def _bd_caida(*args, **kwargs):
        raise RuntimeError("PostgreSQL unreachable")

    monkeypatch.setattr(security, "one", _bd_caida)
    assert security.verificar_sesion_respaldo_bd("jti-cualquiera") is False


def test_pronostico_auto_selecciona_mejor_estrategia():
    base = date(2026, 9, 1)
    # Serie semanal clara + cambio gradual en nivel
    serie = [(base + timedelta(days=i), float(12 + (i % 7) * 2 + i * 0.15)) for i in range(60)]
    auto_res = p.pronosticar_serie(
        serie, "AUTO", horizonte=7, ventana=28, alpha=0.3, fecha_base=serie[-1][0]
    )
    assert auto_res["metodo_ganador"] in p.METODOS_BASE
    assert len(auto_res["pronostico"]) == 7
    assert all(pt["valor"] >= 0 for pt in auto_res["pronostico"])

    # Ningún algoritmo base con hiperparámetros por defecto debe vencer al seleccionado por WMAPE
    maes_fijos = [
        p.pronosticar_serie(serie, m, horizonte=7, ventana=28, alpha=0.3, fecha_base=serie[-1][0])["metricas"]["wmape"]
        for m in p.METODOS_BASE
    ]
    assert auto_res["metricas"]["wmape"] <= max(maes_fijos) + 1e-6


def test_detectar_drift_serie_estable_vigilancia_y_anomalia():
    base = date(2026, 8, 1)
    # 1. Serie estable -> CONFIABLE
    serie_estable = [(base + timedelta(days=i), float(15 + (i % 7))) for i in range(70)]
    d_ok = p.detectar_drift_serie(
        serie_estable,
        metricas_modelo={"wmape": 8.0, "mae": 1.1, "sesgo": 0.1},
        metricas_naive={"mae": 2.0},
    )
    assert d_ok["estado"] == "CONFIABLE"
    assert d_ok["requiere_reemplazo"] is False

    # 2. Serie con caída abrupta / exceso de ceros en últimos 14 días -> NO_CONFIABLE
    serie_drift = [(base + timedelta(days=i), float(22 + (i % 5))) for i in range(50)] + [
        (base + timedelta(days=50 + j), 0.0 if j % 2 == 0 else 1.0) for j in range(14)
    ]
    d_bad = p.detectar_drift_serie(serie_drift)
    assert d_bad["estado"] == "NO_CONFIABLE"
    assert d_bad["requiere_reemplazo"] is True
    assert d_bad["psi"] >= 0.25 or abs(d_bad["z_nivel"]) >= 2.8

    # 3. Degradación severa del modelo frente a Naive -> NO_CONFIABLE
    d_deg = p.detectar_drift_serie(
        serie_estable,
        metricas_modelo={"wmape": 55.0, "mae": 6.0, "sesgo": 0.2},
        metricas_naive={"mae": 2.0},
    )
    assert d_deg["estado"] == "NO_CONFIABLE"
    assert d_deg["requiere_reemplazo"] is True
    assert d_deg["mejora_vs_naive_pct"] is not None and d_deg["mejora_vs_naive_pct"] < -10.0


def test_newsvendor_descuenta_traslados_entrantes(monkeypatch):
    from app.domain import reabastecimiento as reab

    estado_mock = {"traslados_in": 0.0, "descuentos": 0.0}

    def fake_config(clave, defecto=""):
        return {"horizonte_pronostico_dias": "7", "umbral_sobreinventario_dias": "21", "dias_ventana_riesgo_lote": "5"}.get(clave, defecto)

    def fake_one(sql, **params):
        if "FROM operacion.producto" in sql:
            return {
                "id_sku": 1, "nombre": "Fresa Orgánica", "categoria": "Fruta",
                "unidad_medida": "kg", "precio_costo": 20.0, "precio_venta": 60.0,
                "stock_seguridad": 5.0, "punto_reorden": 10.0, "vida_util_estandar": 15,
                "id_proveedor": 1, "proveedor": "Prov Demo", "lead_time_dias": 2, "moq": 1.0,
            }
        if "FROM operacion.locacion" in sql:
            return {"id_locacion": 4, "nombre": "Tienda Cumbres", "tipo_locacion": "Tienda"}
        if "FROM analitica.orden_reabastecimiento" in sql:
            return {"total": 0.0}
        if "id_locacion_destino" in sql:
            return {"total": estado_mock["traslados_in"]}
        if "FROM analitica.descuento" in sql:
            return {"total": estado_mock["descuentos"]}
        if "id_locacion_origen" in sql:
            return {"total": 0.0}
        return {"total": 0.0}

    monkeypatch.setattr(reab, "config_valor", fake_config)
    monkeypatch.setattr(reab, "one", fake_one)
    monkeypatch.setattr(reab, "riesgo_por_lote", lambda sku, loc, d: [{"cantidad_disponible": 20.0, "unidades_en_riesgo": 0.0}])
    monkeypatch.setattr(reab, "demanda_proyectada", lambda sku, loc, d: (70.0 if d == 7 else 20.0, "pronostico"))
    monkeypatch.setattr(reab, "_desviacion_diaria", lambda sku, loc, d=28: 3.0)

    sin_traslado = reab.analizar_sku_locacion(1, 4, horizonte=7)
    estado_mock["traslados_in"] = 25.0
    con_traslado = reab.analizar_sku_locacion(1, 4, horizonte=7)

    assert con_traslado["entradas_traslados"] == 25.0
    assert con_traslado["entradas_confirmadas"] == 25.0
    assert round(sin_traslado["necesidad_neta"] - con_traslado["necesidad_neta"], 2) == 25.0
    assert con_traslado["cantidad_sugerida"] < sin_traslado["cantidad_sugerida"]

    # Descuento activo en tienda con cobertura >= lead_time (20 / 10 = 2 días >= 2 días) frena compra
    estado_mock["traslados_in"] = 0.0
    estado_mock["descuentos"] = 10.0
    con_descuento = reab.analizar_sku_locacion(1, 4, horizonte=7)
    assert con_descuento["cantidad_sugerida"] == 0.0
    assert any("Compra detenida por triaje local" in a for a in con_descuento["advertencias"])


def test_generar_pdf_orden_compra_valido_y_multipagina():
    from app.domain.pdf_oc import generar_pdf_orden_compra

    lineas = [
        {
            "locacion_destino": f"Tienda {(i % 3) + 1}",
            "producto": f"Producto Orgánico #{i}",
            "unidad_medida": "kg",
            "cantidad_lotes": 2,
            "unidades_por_lote": 10.0,
            "cantidad_unidades": 20.0,
            "precio_unitario": 25.0,
            "subtotal": 500.0,
        }
        for i in range(1, 41)
    ]
    orden = {
        "folio": "OC-20261122-0001",
        "estado": "EMITIDA",
        "fecha_creacion": "2026-11-22T12:00:00",
        "fecha_entrega_estimada": "2026-11-25",
        "lead_time_dias": 3,
        "proveedor": "Lácteos Frescos de México S.A.",
        "rfc": "LFM190101XYZ",
        "contacto_email": "ventas@lacteos.mx",
        "telefono": "8110002200",
        "comprador": "Ana Compras",
        "comprador_email": "buyer@freshtrack.mx",
        "total_lotes": 80,
        "total_unidades": 800.0,
        "total": 20000.0,
        "observaciones": "Entregar en rampa refrigerada con temperatura controlada.",
        "resumen_tiendas": [
            {"locacion_destino": "Tienda 1", "lotes": 28, "unidades": 280.0, "subtotal": 7000.0},
            {"locacion_destino": "Tienda 2", "lotes": 26, "unidades": 260.0, "subtotal": 6500.0},
            {"locacion_destino": "Tienda 3", "lotes": 26, "unidades": 260.0, "subtotal": 6500.0},
        ],
        "lineas": lineas,
    }
    pdf = generar_pdf_orden_compra(orden)
    assert pdf.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf[-32:]
    assert b"OC-20261122-0001" in pdf
    assert b"/Type /Page" in pdf and b"/Count 2" in pdf


def test_object_storage_firma_y_fallback_local(monkeypatch):
    import tempfile
    from pathlib import Path
    from app.services import object_storage

    assert len(object_storage._signing_key("secret", "20261122", "us-east-1")) == 32

    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setattr(object_storage, "FALLBACK_DIR", Path(td))
        monkeypatch.setattr(object_storage, "_peticion_s3", lambda *a, **k: (0, b"", {}))

        meta = object_storage.subir_pdf("ordenes/demo.pdf", b"%PDF-1.4 demo-ok")
        assert meta["storage_provider"] == "local_fallback"
        assert meta["tamano_bytes"] == 16
        assert len(meta["sha256"]) == 64
        recuperado = object_storage.descargar_pdf("ordenes/demo.pdf", bucket=meta["bucket"], storage_provider="local_fallback")
        assert recuperado == b"%PDF-1.4 demo-ok"

        # Simular S3 disponible
        monkeypatch.setattr(
            object_storage,
            "_peticion_s3",
            lambda metodo, ruta, **k: (200, b"%PDF-1.4 s3-ok", {"etag": '"etag123"'}),
        )
        meta_s3 = object_storage.subir_pdf("ordenes/s3.pdf", b"%PDF-1.4 s3-ok")
        assert meta_s3["storage_provider"] == "s3"
        assert meta_s3["etag"] == "etag123"
        assert object_storage.descargar_pdf("ordenes/s3.pdf", bucket=meta_s3["bucket"], storage_provider="s3") == b"%PDF-1.4 s3-ok"


def test_rbac_comprador_y_proveedor():
    from app.navegacion import VISTAS_POR_ROL, VISTA_INICIAL

    assert VISTA_INICIAL["buyer"] == "suppliers"
    assert "suppliers" in VISTAS_POR_ROL["buyer"]
    assert "products" not in VISTAS_POR_ROL["buyer"]
    assert "products" in VISTAS_POR_ROL["supplier"]
    assert VISTA_INICIAL["supplier"] == "replenishment"
