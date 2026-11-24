"""
Dominio de Abastecimiento por Proveedor y Órdenes de Compra por Lotes.

Consolida la vista del comprador:
- Catálogo de productos ofrecidos por cada proveedor con su MOQ de lote definido
  por el proveedor en el producto (moq_lote).
- Integración directa con reabastecimiento inteligente (Newsvendor + Triaje neto)
  enrutando lotes sugeridos hacia cada tienda destino.
- Registro transaccional de Órdenes de Compra formales, generación de PDF almacenado
  en Cloud Object Storage con metadatos en PostgreSQL (operacion.reporte_documento)
  y envío por correo electrónico al proveedor.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, config_valor, one, query, transaccion
from app.domain import pdf_oc, reabastecimiento
from app.domain.cache_web import con_cache_web, invalidar
from app.events.dispatcher import publicar_evento
from app.services import mailer, object_storage

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _json(valor) -> str:
    return json.dumps(valor, default=str, ensure_ascii=False)


def resumen_necesidad_por_proveedor() -> dict[int, dict]:
    """Devuelve métricas rápidas de necesidad de compra pendiente por proveedor (cache 60 s)."""
    datos = con_cache_web("web:reab:necesidad_proveedor", 60, _resumen_necesidad_por_proveedor_db)
    # JSON convierte las llaves int en str: restaurarlas.
    return {int(k): v for k, v in datos.items()}


def _resumen_necesidad_por_proveedor_db() -> dict[int, dict]:
    filas = query(
        """
        SELECT pr.id_proveedor,
               COUNT(DISTINCT p.id_sku) FILTER (WHERE p.activo) AS productos_activos,
               COUNT(DISTINCT o.id_orden) FILTER (WHERE o.estado = 'PENDIENTE') AS ordenes_pendientes,
               COUNT(DISTINCT o.id_orden) FILTER (WHERE o.estado = 'PENDIENTE' AND o.prioridad = 'ALTA') AS urgentes,
               COALESCE(SUM(CASE WHEN o.estado = 'PENDIENTE' THEN o.cantidad_sugerida ELSE 0 END), 0) AS unidades_sugeridas
        FROM operacion.proveedor pr
        LEFT JOIN operacion.producto p ON p.id_proveedor = pr.id_proveedor
        LEFT JOIN analitica.orden_reabastecimiento o ON o.id_sku = p.id_sku AND o.estado = 'PENDIENTE'
        GROUP BY pr.id_proveedor
        """
    )
    return {
        f["id_proveedor"]: {
            "productos_activos": int(f["productos_activos"] or 0),
            "ordenes_pendientes": int(f["ordenes_pendientes"] or 0),
            "urgentes": int(f["urgentes"] or 0),
            "unidades_sugeridas": round(a_float(f["unidades_sugeridas"]), 2),
        }
        for f in filas
    }


def catalogo_compra_proveedor(id_proveedor: int, horizonte: int | None = None) -> dict:
    """
    Construye el catálogo de compra por lotes para un proveedor integrando el análisis
    inteligente Newsvendor + Triaje para cada producto y tienda activa.

    Es el cálculo más caro de la plataforma (producto × tienda × ~13 consultas),
    así que se cachea 5 min por proveedor con protección anti-estampida y se
    invalida al emitir una orden de compra o cambiar órdenes de reabastecimiento.
    """
    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)
    return con_cache_web(
        f"web:reab:catalogo_compra:{int(id_proveedor)}:{int(horizonte)}",
        300,
        lambda: _catalogo_compra_proveedor_db(id_proveedor, horizonte),
        con_lock=True,
        espera_max_seg=25.0,
    )


def _catalogo_compra_proveedor_db(id_proveedor: int, horizonte: int) -> dict:
    prov = one(
        """
        SELECT id_proveedor, rfc, razon_social, lead_time_dias, moq,
               contacto_email, telefono, activo
        FROM operacion.proveedor
        WHERE id_proveedor = :p
        """,
        p=id_proveedor,
    )
    if prov is None:
        raise ValueError(f"El proveedor {id_proveedor} no existe.")
    prov_out = {**prov, "moq": a_float(prov["moq"])}

    tiendas = query(
        """
        SELECT id_locacion, nombre, ciudad
        FROM operacion.locacion
        WHERE activo AND tipo_locacion = 'Tienda'
        ORDER BY nombre
        """
    )

    productos = query(
        """
        SELECT p.id_sku, p.codigo_gtin, p.nombre, p.categoria, p.unidad_medida,
               p.vida_util_estandar, p.precio_costo, p.precio_venta,
               p.stock_seguridad, p.punto_reorden,
               COALESCE(p.moq_lote, pr.moq, 1) AS moq_lote_efectivo,
               p.moq_lote
        FROM operacion.producto p
        JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        WHERE p.id_proveedor = :p AND p.activo = true
        ORDER BY p.nombre
        """,
        p=id_proveedor,
    )

    pendientes_rows = query(
        """
        SELECT o.id_orden::text, o.id_sku, o.id_locacion, o.prioridad, o.cantidad_sugerida
        FROM analitica.orden_reabastecimiento o
        JOIN operacion.producto p ON p.id_sku = o.id_sku
        WHERE p.id_proveedor = :p AND o.estado = 'PENDIENTE'
        """,
        p=id_proveedor,
    )
    pendientes_map = {(r["id_sku"], r["id_locacion"]): r for r in pendientes_rows}

    prioridad_orden = {"ALTA": 3, "MEDIA": 2, "BAJA": 1}
    productos_out: list[dict] = []
    total_lotes_sugeridos = 0
    total_unidades_sugeridas = 0.0
    monto_sugerido = 0.0

    for prod in productos:
        moq_lote = max(1.0, round(a_float(prod["moq_lote_efectivo"]) or 1.0, 2))
        precio_costo = round(a_float(prod["precio_costo"]), 2)
        precio_venta = round(a_float(prod["precio_venta"]), 2)
        celdas_tienda: list[dict] = []
        lotes_prod_sug = 0
        unidades_prod_sug = 0.0
        prio_max = "BAJA"

        for t in tiendas:
            try:
                an = reabastecimiento.analizar_sku_locacion(prod["id_sku"], t["id_locacion"], horizonte)
            except ValueError:
                continue

            sug_u = max(0.0, round(a_float(an["cantidad_sugerida"]), 2))
            lotes_sug = int(math.ceil(sug_u / moq_lote)) if sug_u > 0 else 0
            unid_lotes = round(lotes_sug * moq_lote, 2)
            sub_sug = round(unid_lotes * precio_costo, 2)
            prio = an["prioridad"]
            if lotes_sug > 0 and prioridad_orden.get(prio, 0) > prioridad_orden.get(prio_max, 0):
                prio_max = prio

            pend = pendientes_map.get((prod["id_sku"], t["id_locacion"]))
            celdas_tienda.append(
                {
                    "id_locacion": t["id_locacion"],
                    "locacion": t["nombre"],
                    "inventario_util": an["inventario_util"],
                    "inventario_riesgo": an["inventario_riesgo"],
                    "demanda_horizonte": an["demanda_horizonte"],
                    "entradas_confirmadas": an["entradas_confirmadas"],
                    "entradas_traslados": an["entradas_traslados"],
                    "necesidad_neta": an["necesidad_neta"],
                    "cantidad_sugerida": sug_u,
                    "lotes_sugeridos": lotes_sug,
                    "unidades_sugeridas_lote": unid_lotes,
                    "subtotal_sugerido": sub_sug,
                    "prioridad": prio,
                    "advertencias": an["advertencias"],
                    "id_orden_pendiente": pend["id_orden"] if pend else None,
                }
            )
            lotes_prod_sug += lotes_sug
            unidades_prod_sug += unid_lotes
            monto_sugerido += sub_sug

        total_lotes_sugeridos += lotes_prod_sug
        total_unidades_sugeridas += unidades_prod_sug
        productos_out.append(
            {
                "id_sku": prod["id_sku"],
                "codigo_gtin": prod["codigo_gtin"],
                "nombre": prod["nombre"],
                "categoria": prod["categoria"],
                "unidad_medida": prod["unidad_medida"],
                "vida_util_estandar": int(prod["vida_util_estandar"]),
                "precio_costo": precio_costo,
                "precio_venta": precio_venta,
                "moq_lote": moq_lote,
                "costo_por_lote": round(moq_lote * precio_costo, 2),
                "total_lotes_sugeridos": lotes_prod_sug,
                "total_unidades_sugeridas": round(unidades_prod_sug, 2),
                "prioridad_max": prio_max,
                "tiendas": celdas_tienda,
            }
        )

    # Ordenar productos con necesidad sugerida primero
    productos_out.sort(key=lambda p: (-int(p["total_lotes_sugeridos"] > 0), -prioridad_orden.get(p["prioridad_max"], 0), p["nombre"]))

    return {
        "proveedor": prov_out,
        "horizonte": horizonte,
        "tiendas": tiendas,
        "productos": productos_out,
        "resumen": {
            "total_productos": len(productos_out),
            "total_lotes_sugeridos": total_lotes_sugeridos,
            "total_unidades_sugeridas": round(total_unidades_sugeridas, 2),
            "monto_sugerido": round(monto_sugerido, 2),
        },
    }


def _siguiente_folio_oc(conn) -> str:
    hoy = date.today()
    prefijo = f"OC-{hoy:%Y%m%d}-"
    ultimo = conn.execute(
        text(
            "SELECT folio FROM operacion.orden_compra "
            "WHERE folio LIKE :pref ORDER BY folio DESC LIMIT 1"
        ),
        {"pref": prefijo + "%"},
    ).scalar()
    if ultimo and ultimo.startswith(prefijo):
        try:
            seq = int(ultimo.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefijo}{seq:04d}"


def registrar_orden_compra(
    *,
    id_proveedor: int,
    lineas: list[dict],
    usuario: dict,
    observaciones: str | None = None,
) -> dict:
    """
    Registra una Orden de Compra multi-tienda por lotes (usando el moq_lote definido
    por el proveedor en cada producto), sincroniza recomendaciones de reabastecimiento
    y genera el PDF en Cloud Object Storage con metadatos persistidos en PostgreSQL.
    """
    prov = one(
        "SELECT id_proveedor, razon_social, lead_time_dias, moq, activo "
        "FROM operacion.proveedor WHERE id_proveedor = :p",
        p=id_proveedor,
    )
    if prov is None:
        raise ValueError("El proveedor seleccionado no existe.")
    if not prov["activo"]:
        raise ValueError("No se pueden emitir órdenes de compra a un proveedor inactivo.")

    if not lineas:
        raise ValueError("Debes seleccionar al menos 1 lote para emitir la orden de compra.")

    prods_prov = {
        r["id_sku"]: r
        for r in query(
            """
            SELECT p.id_sku, p.nombre, p.precio_costo, p.unidad_medida,
                   COALESCE(p.moq_lote, pr.moq, 1) AS moq_lote_efectivo
            FROM operacion.producto p
            JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
            WHERE p.id_proveedor = :p AND p.activo = true
            """,
            p=id_proveedor,
        )
    }
    tiendas_act = {
        r["id_locacion"]: r["nombre"]
        for r in query("SELECT id_locacion, nombre FROM operacion.locacion WHERE activo = true")
    }

    agrupadas: dict[tuple[int, int], int] = {}
    for item in lineas:
        try:
            sku = int(item["id_sku"])
            loc = int(item["id_locacion_destino"])
            lotes = int(item["cantidad_lotes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Cada línea debe indicar producto, tienda destino y número entero de lotes.") from exc
        if lotes <= 0:
            continue
        if sku not in prods_prov:
            raise ValueError(f"El producto {sku} no está activo o no pertenece al proveedor seleccionado.")
        if loc not in tiendas_act:
            raise ValueError(f"La tienda destino {loc} no existe o está inactiva.")
        key = (sku, loc)
        agrupadas[key] = agrupadas.get(key, 0) + lotes

    if not agrupadas:
        raise ValueError("Debes asignar al menos 1 lote en alguna tienda destino.")

    # Buscar recomendaciones PENDIENTE para enlazarlas y aprobarlas automáticamente
    pend_rows = query(
        """
        SELECT o.id_orden::text, o.id_sku, o.id_locacion, o.cantidad_sugerida
        FROM analitica.orden_reabastecimiento o
        JOIN operacion.producto p ON p.id_sku = o.id_sku
        WHERE p.id_proveedor = :p AND o.estado = 'PENDIENTE'
        """,
        p=id_proveedor,
    )
    pend_map = {(r["id_sku"], r["id_locacion"]): r for r in pend_rows}

    detalle_limpio: list[dict] = []
    total_lotes = 0
    total_unidades = 0.0
    subtotal_orden = 0.0

    for (sku, loc), lotes in sorted(agrupadas.items(), key=lambda kv: (tiendas_act[kv[0][1]], prods_prov[kv[0][0]]["nombre"])):
        prod = prods_prov[sku]
        unid_por_lote = max(1.0, round(a_float(prod["moq_lote_efectivo"]) or 1.0, 2))
        cant_unidades = round(lotes * unid_por_lote, 2)
        costo_u = round(a_float(prod["precio_costo"]), 2)
        sub = round(cant_unidades * costo_u, 2)
        pend = pend_map.get((sku, loc))

        detalle_limpio.append(
            {
                "id_sku": sku,
                "id_locacion_destino": loc,
                "cantidad_lotes": lotes,
                "unidades_por_lote": unid_por_lote,
                "cantidad_unidades": cant_unidades,
                "precio_unitario": costo_u,
                "subtotal": sub,
                "sugerencia_newsvendor": round(a_float(pend["cantidad_sugerida"]), 2) if pend else None,
                "id_orden_reabastecimiento": pend["id_orden"] if pend else None,
            }
        )
        total_lotes += lotes
        total_unidades = round(total_unidades + cant_unidades, 2)
        subtotal_orden = round(subtotal_orden + sub, 2)

    lead_time = a_int(prov["lead_time_dias"], 3)
    fecha_entrega = date.today() + timedelta(days=lead_time)
    obs = (observaciones or "").strip() or None

    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        folio = _siguiente_folio_oc(conn)
        id_oc = conn.execute(
            text(
                """
                INSERT INTO operacion.orden_compra
                    (folio, id_proveedor, id_usuario, estado,
                     total_lotes, total_unidades, subtotal, total,
                     fecha_entrega_estimada, observaciones)
                VALUES
                    (:folio, :prov, CAST(:uid AS uuid), 'EMITIDA',
                     :lotes, :unidades, :sub, :tot, :entrega, :obs)
                RETURNING id_oc::text
                """
            ),
            {
                "folio": folio,
                "prov": id_proveedor,
                "uid": usuario["id_usuario"],
                "lotes": total_lotes,
                "unidades": total_unidades,
                "sub": subtotal_orden,
                "tot": subtotal_orden,
                "entrega": fecha_entrega,
                "obs": obs,
            },
        ).scalar()

        for det in detalle_limpio:
            conn.execute(
                text(
                    """
                    INSERT INTO operacion.orden_compra_detalle
                        (id_oc, id_sku, id_locacion_destino, cantidad_lotes,
                         unidades_por_lote, cantidad_unidades, precio_unitario,
                         subtotal, sugerencia_newsvendor, id_orden_reabastecimiento)
                    VALUES
                        (CAST(:oc AS uuid), :sku, :loc, :lotes, :moq, :cant, :precio,
                         :sub, :sug, CAST(:id_or AS uuid))
                    """
                ),
                {
                    "oc": id_oc,
                    "sku": det["id_sku"],
                    "loc": det["id_locacion_destino"],
                    "lotes": det["cantidad_lotes"],
                    "moq": det["unidades_por_lote"],
                    "cant": det["cantidad_unidades"],
                    "precio": det["precio_unitario"],
                    "sub": det["subtotal"],
                    "sug": det["sugerencia_newsvendor"],
                    "id_or": det["id_orden_reabastecimiento"],
                },
            )
            if det["id_orden_reabastecimiento"]:
                conn.execute(
                    text(
                        """
                        UPDATE analitica.orden_reabastecimiento
                           SET estado = 'APROBADA',
                               cantidad_aprobada = :cant,
                               id_usuario_aprueba = CAST(:uid AS uuid),
                               fecha_decision = now()
                         WHERE id_orden = CAST(:id_or AS uuid)
                           AND estado = 'PENDIENTE'
                        """
                    ),
                    {
                        "cant": det["cantidad_unidades"],
                        "uid": usuario["id_usuario"],
                        "id_or": det["id_orden_reabastecimiento"],
                    },
                )

    orden = obtener_orden_compra(id_oc)
    assert orden is not None
    _generar_y_guardar_pdf(orden, usuario=usuario)
    orden = obtener_orden_compra(id_oc)
    assert orden is not None

    auditoria.registrar(
        "CREATE_PURCHASE_ORDER",
        tabla="orden_compra",
        id_registro=id_oc,
        descripcion=(
            f"Orden de compra {folio} a {prov['razon_social']}: "
            f"{total_lotes} lote(s) ({total_unidades:g} u.) por ${subtotal_orden:,.2f}"
        ),
        estado_nuevo={
            "folio": folio,
            "id_proveedor": id_proveedor,
            "total_lotes": total_lotes,
            "total_unidades": total_unidades,
            "total": subtotal_orden,
        },
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    publicar_evento(
        "ORDEN_COMPRA_EMITIDA",
        {
            "id_oc": id_oc,
            "folio": folio,
            "id_proveedor": id_proveedor,
            "total_lotes": total_lotes,
            "total_unidades": total_unidades,
            "total": subtotal_orden,
        },
        contexto={
            "user_id": usuario.get("id_usuario"),
            "user_role": usuario.get("rol_clave"),
            "correlation_id": id_oc,
        },
    )
    # La OC aprueba órdenes de reabastecimiento y cambia las entradas confirmadas.
    invalidar("web:reab:*")
    return orden


def _generar_y_guardar_pdf(orden: dict, *, usuario: dict) -> dict:
    """Genera el PDF de la OC, lo sube a Cloud Object Storage y persiste metadatos en SQL."""
    pdf_bytes = pdf_oc.generar_pdf_orden_compra(orden)
    hoy = date.today()
    folio = orden["folio"]
    nombre_archivo = f"{folio}.pdf"
    object_key = f"ordenes-compra/{hoy:%Y/%m}/{nombre_archivo}"
    meta_storage = object_storage.subir_pdf(object_key, pdf_bytes)

    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        id_doc = conn.execute(
            text(
                """
                INSERT INTO operacion.reporte_documento
                    (tipo_reporte, referencia_tipo, referencia_id, folio, nombre_archivo,
                     content_type, storage_provider, bucket, object_key, etag, sha256,
                     tamano_bytes, id_usuario, metadatos)
                VALUES
                    ('ORDEN_COMPRA_PDF', 'ORDEN_COMPRA', CAST(:ref AS uuid), :folio, :nombre,
                     'application/pdf', :prov_alm, :bucket, :obj_key, :etag, :sha256,
                     :tamano, CAST(:uid AS uuid), CAST(:meta AS jsonb))
                RETURNING id_documento::text
                """
            ),
            {
                "ref": orden["id_oc"],
                "folio": folio,
                "nombre": nombre_archivo,
                "prov_alm": meta_storage["storage_provider"],
                "bucket": meta_storage["bucket"],
                "obj_key": meta_storage["object_key"],
                "etag": meta_storage["etag"],
                "sha256": meta_storage["sha256"],
                "tamano": meta_storage["tamano_bytes"],
                "uid": usuario["id_usuario"],
                "meta": _json(
                    {
                        "id_proveedor": orden["id_proveedor"],
                        "proveedor": orden["proveedor"],
                        "total_lotes": orden["total_lotes"],
                        "total": orden["total"],
                    }
                ),
            },
        ).scalar()
        conn.execute(
            text(
                "UPDATE operacion.orden_compra SET id_documento_pdf = CAST(:doc AS uuid) "
                "WHERE id_oc = CAST(:oc AS uuid)"
            ),
            {"doc": id_doc, "oc": orden["id_oc"]},
        )

    return {"id_documento": id_doc, "pdf_bytes": pdf_bytes, **meta_storage, "nombre_archivo": nombre_archivo}


def obtener_orden_compra(id_oc: str) -> dict | None:
    cab = one(
        """
        SELECT oc.id_oc::text, oc.folio, oc.id_proveedor, oc.id_usuario::text,
               oc.id_documento_pdf::text, oc.estado, oc.total_lotes, oc.total_unidades,
               oc.subtotal, oc.total, oc.fecha_entrega_estimada, oc.correo_envio,
               oc.fecha_envio_correo, oc.estado_envio_correo, oc.observaciones,
               oc.fecha_creacion,
               pr.razon_social AS proveedor, pr.rfc, pr.lead_time_dias,
               pr.contacto_email, pr.telefono,
               u.nombre_completo AS comprador, u.email AS comprador_email,
               doc.nombre_archivo, doc.bucket, doc.object_key, doc.storage_provider,
               doc.sha256, doc.tamano_bytes, doc.etag, doc.creado_en AS documento_creado_en
        FROM operacion.orden_compra oc
        JOIN operacion.proveedor pr ON pr.id_proveedor = oc.id_proveedor
        JOIN operacion.usuario u    ON u.id_usuario = oc.id_usuario
        LEFT JOIN operacion.reporte_documento doc ON doc.id_documento = oc.id_documento_pdf
        WHERE oc.id_oc = CAST(:id AS uuid)
        """,
        id=id_oc,
    )
    if cab is None:
        return None

    lineas_raw = query(
        """
        SELECT d.id_detalle::text, d.id_sku, p.nombre AS producto, p.codigo_gtin,
               p.unidad_medida, d.id_locacion_destino, loc.nombre AS locacion_destino,
               d.cantidad_lotes, d.unidades_por_lote, d.cantidad_unidades,
               COALESCE(d.cantidad_recibida, 0) AS cantidad_recibida,
               d.precio_unitario, d.subtotal, d.sugerencia_newsvendor,
               d.id_orden_reabastecimiento::text
        FROM operacion.orden_compra_detalle d
        JOIN operacion.producto p   ON p.id_sku = d.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = d.id_locacion_destino
        WHERE d.id_oc = CAST(:id AS uuid)
        ORDER BY loc.nombre, p.nombre
        """,
        id=id_oc,
    )

    lineas = []
    resumen_map: dict[int, dict] = {}
    for l in lineas_raw:
        item = {
            **l,
            "cantidad_lotes": int(l["cantidad_lotes"]),
            "unidades_por_lote": a_float(l["unidades_por_lote"]),
            "cantidad_unidades": a_float(l["cantidad_unidades"]),
            "cantidad_recibida": a_float(l.get("cantidad_recibida")),
            "precio_unitario": a_float(l["precio_unitario"]),
            "subtotal": a_float(l["subtotal"]),
            "sugerencia_newsvendor": a_float(l["sugerencia_newsvendor"]) if l["sugerencia_newsvendor"] is not None else None,
        }
        lineas.append(item)
        loc_id = item["id_locacion_destino"]
        rt = resumen_map.setdefault(
            loc_id,
            {"id_locacion_destino": loc_id, "locacion_destino": item["locacion_destino"], "lotes": 0, "unidades": 0.0, "subtotal": 0.0},
        )
        rt["lotes"] += item["cantidad_lotes"]
        rt["unidades"] = round(rt["unidades"] + item["cantidad_unidades"], 2)
        rt["subtotal"] = round(rt["subtotal"] + item["subtotal"], 2)

    documento_pdf = None
    if cab.get("id_documento_pdf"):
        documento_pdf = {
            "id_documento": cab["id_documento_pdf"],
            "nombre_archivo": cab["nombre_archivo"],
            "bucket": cab["bucket"],
            "object_key": cab["object_key"],
            "storage_provider": cab["storage_provider"],
            "sha256": cab["sha256"],
            "tamano_bytes": int(cab["tamano_bytes"] or 0),
            "etag": cab["etag"],
            "creado_en": cab["documento_creado_en"].isoformat() if cab.get("documento_creado_en") else None,
        }

    from app.services import doc_store

    return {
        "id_oc": cab["id_oc"],
        "folio": cab["folio"],
        "id_proveedor": cab["id_proveedor"],
        "proveedor": cab["proveedor"],
        "rfc": cab["rfc"],
        "lead_time_dias": int(cab["lead_time_dias"]),
        "contacto_email": cab["contacto_email"],
        "telefono": cab["telefono"],
        "comprador": cab["comprador"],
        "comprador_email": cab["comprador_email"],
        "estado": cab["estado"],
        "total_lotes": int(cab["total_lotes"]),
        "total_unidades": a_float(cab["total_unidades"]),
        "subtotal": a_float(cab["subtotal"]),
        "total": a_float(cab["total"]),
        "fecha_entrega_estimada": str(cab["fecha_entrega_estimada"]) if cab["fecha_entrega_estimada"] else None,
        "correo_envio": cab["correo_envio"],
        "fecha_envio_correo": cab["fecha_envio_correo"].isoformat() if cab.get("fecha_envio_correo") else None,
        "estado_envio_correo": cab["estado_envio_correo"],
        "observaciones": cab["observaciones"],
        "fecha_creacion": cab["fecha_creacion"].isoformat() if cab.get("fecha_creacion") else None,
        "id_documento_pdf": cab["id_documento_pdf"],
        "documento_pdf": documento_pdf,
        "lineas": lineas,
        "resumen_tiendas": sorted(resumen_map.values(), key=lambda x: x["locacion_destino"]),
        "despachos_asn": doc_store.listar_asns_por_oc(cab["folio"]),
    }


def listar_ordenes_compra(
    id_proveedor: int | None = None,
    estado: str | None = None,
    limite: int = 50,
) -> list[dict]:
    condiciones = []
    params: dict = {"lim": limite}
    if id_proveedor:
        condiciones.append("oc.id_proveedor = :prov")
        params["prov"] = id_proveedor
    if estado:
        condiciones.append("oc.estado = :est")
        params["est"] = estado
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    filas = query(
        f"""
        SELECT oc.id_oc::text, oc.folio, oc.id_proveedor, pr.razon_social AS proveedor,
               pr.contacto_email, oc.estado, oc.total_lotes, oc.total_unidades,
               oc.total, oc.fecha_entrega_estimada, oc.correo_envio, oc.estado_envio_correo,
               oc.fecha_creacion, u.nombre_completo AS comprador,
               oc.id_documento_pdf::text, doc.nombre_archivo, doc.tamano_bytes,
               doc.storage_provider, doc.bucket, doc.object_key, doc.sha256,
               (SELECT COUNT(DISTINCT d.id_locacion_destino)
                  FROM operacion.orden_compra_detalle d WHERE d.id_oc = oc.id_oc) AS n_tiendas
        FROM operacion.orden_compra oc
        JOIN operacion.proveedor pr ON pr.id_proveedor = oc.id_proveedor
        JOIN operacion.usuario u    ON u.id_usuario = oc.id_usuario
        LEFT JOIN operacion.reporte_documento doc ON doc.id_documento = oc.id_documento_pdf
        {where}
        ORDER BY oc.fecha_creacion DESC
        LIMIT :lim
        """,
        **params,
    )
    for f in filas:
        f["total_lotes"] = int(f["total_lotes"] or 0)
        f["total_unidades"] = a_float(f["total_unidades"])
        f["total"] = a_float(f["total"])
        f["tamano_bytes"] = int(f["tamano_bytes"] or 0) if f.get("tamano_bytes") is not None else None
        f["n_tiendas"] = int(f["n_tiendas"] or 0)
        if f.get("fecha_entrega_estimada"):
            f["fecha_entrega_estimada"] = str(f["fecha_entrega_estimada"])
        if f.get("fecha_creacion"):
            f["fecha_creacion"] = f["fecha_creacion"].isoformat()
    return filas


def obtener_pdf_orden_compra(id_oc: str, usuario: dict | None = None) -> tuple[bytes, dict]:
    """Obtiene los bytes del PDF desde Cloud Object Storage (o lo regenera si faltara)."""
    orden = obtener_orden_compra(id_oc)
    if orden is None:
        raise ValueError("La orden de compra solicitada no existe.")
    doc = orden.get("documento_pdf")
    if doc and doc.get("object_key"):
        contenido = object_storage.descargar_pdf(
            doc["object_key"],
            bucket=doc.get("bucket"),
            storage_provider=doc.get("storage_provider") or "s3",
        )
        if contenido:
            return contenido, orden

    # Recuperación idempotente si el objeto fue borrado o migrado
    u_fallback = usuario or {"id_usuario": orden["id_oc"], "email": orden.get("comprador_email") or "sistema@freshtrack.mx"}
    if not usuario:
        u_row = one("SELECT id_usuario::text, email FROM operacion.orden_compra oc JOIN operacion.usuario u ON u.id_usuario = oc.id_usuario WHERE oc.id_oc = CAST(:id AS uuid)", id=id_oc)
        if u_row:
            u_fallback = u_row
    res_pdf = _generar_y_guardar_pdf(orden, usuario=u_fallback)
    return res_pdf["pdf_bytes"], (obtener_orden_compra(id_oc) or orden)


def enviar_orden_compra_correo(
    *,
    id_oc: str,
    correo_destino: str,
    usuario: dict,
    mensaje_extra: str | None = None,
) -> dict:
    """
    Envía la Orden de Compra con su PDF adjunto al correo indicado.
    Si hay un servidor SMTP configurado envía el correo real; en caso contrario
    registra el envío en modo demostración con trazabilidad completa en bitácora.
    """
    destino = (correo_destino or "").strip()
    if not _EMAIL_RE.match(destino):
        raise ValueError("Ingresa un correo electrónico válido.")

    pdf_bytes, orden = obtener_pdf_orden_compra(id_oc, usuario=usuario)
    folio = orden["folio"]
    nombre_archivo = (orden.get("documento_pdf") or {}).get("nombre_archivo") or f"{folio}.pdf"

    cuerpo = (
        f"Estimado equipo de {orden['proveedor']},\n\n"
        f"Adjuntamos la Orden de Compra {folio} por {orden['total_lotes']} lote(s) "
        f"({orden['total_unidades']:g} unidades) con un monto total de ${orden['total']:,.2f}.\n"
        f"Fecha estimada de entrega: {orden.get('fecha_entrega_estimada') or '-'}.\n"
    )
    if mensaje_extra and mensaje_extra.strip():
        cuerpo += f"\nNota adicional del comprador:\n{mensaje_extra.strip()}\n"
    cuerpo += "\nSaludos,\nFreshTrack Compras"

    estado_correo = mailer.enviar_correo(
        destino,
        f"Orden de Compra {folio} - FreshTrack",
        cuerpo,
        [(pdf_bytes, nombre_archivo, "application/pdf")],
    )

    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        conn.execute(
            text(
                """
                UPDATE operacion.orden_compra
                   SET estado = CASE WHEN estado = 'EMITIDA' THEN 'ENVIADA' ELSE estado END,
                       correo_envio = :correo,
                       fecha_envio_correo = now(),
                       estado_envio_correo = :estado_correo
                 WHERE id_oc = CAST(:id AS uuid)
                """
            ),
            {"correo": destino, "estado_correo": estado_correo, "id": id_oc},
        )

    auditoria.registrar(
        "SEND_PURCHASE_ORDER_EMAIL",
        tabla="orden_compra",
        id_registro=id_oc,
        descripcion=f"Envío de OC {folio} al correo {destino} ({estado_correo})",
        estado_nuevo={"correo_envio": destino, "estado_envio_correo": estado_correo},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )

    publicar_evento(
        "ORDEN_COMPRA_ENVIADA",
        {"id_oc": id_oc, "folio": folio, "correo_envio": destino, "modo": estado_correo},
        contexto={"user_id": usuario.get("id_usuario"), "correlation_id": id_oc},
    )

    return {
        "id_oc": id_oc,
        "folio": folio,
        "correo_envio": destino,
        "estado_envio_correo": estado_correo,
        "enviado_real": estado_correo == "ENVIADO_SMTP",
    }
