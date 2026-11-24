"""
Operaciones que pide la app Android (personal de tienda) y que no tenía el backend:

  * Conteo cíclico: compara lo contado contra la existencia, ajusta la diferencia
    con movimiento AJUSTE en el kardex y guarda la exactitud. Idempotente por
    Idempotency-Key (reintentar con mala señal no ajusta dos veces).
  * Solicitud manual de transferencia: crea una propuesta SUGERIDA con las mismas
    validaciones que la detección automática (stock en origen y que llegue antes de vencer).
  * Evidencia fotográfica: imagen al bucket privado, metadatos y SHA-256 en
    PostgreSQL, y acceso solo con URL firmada de vida corta.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, one, query, transaccion
from app.domain.cache_web import invalida
from app.domain.transferencias import DIAS_TRANSITO
from app.services import object_storage

TIPOS_EVIDENCIA = ("ANAQUEL", "MERMA", "RECEPCION", "TEMPERATURA", "OTRO")
URL_EXPIRA_SEG = 900
TOLERANCIA = 0.005


def tipo_imagen(contenido: bytes) -> str:
    """Tipo real del archivo por sus primeros bytes; el Content-Type del cliente no se cree."""
    if contenido[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if contenido[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("El archivo no es una imagen JPEG, PNG o WebP.")


# ---------------------------------------------------------------------------
# Conteo cíclico
# ---------------------------------------------------------------------------
def _resultado_conteo(fila: dict) -> dict:
    ajustes = fila["ajustes"]
    if isinstance(ajustes, str):
        ajustes = json.loads(ajustes)
    return {
        "id_conteo": fila["id_conteo"],
        "lineas_contadas": a_int(fila["lineas_contadas"]),
        "lineas_con_diferencia": a_int(fila["lineas_con_diferencia"]),
        "exactitud_pct": a_float(fila["exactitud_pct"]),
        "ajustes": ajustes,
    }


@invalida("web:triaje:*")
def registrar_conteo(
    *,
    id_locacion: int,
    id_sku: int | None,
    lineas: list[dict],
    observacion: str | None,
    usuario: dict,
    idempotency_key: str | None = None,
) -> dict:
    """Ajusta la existencia de cada lote contado y devuelve las diferencias encontradas."""
    if not lineas:
        raise ValueError("El conteo no tiene líneas.")
    clave = str(idempotency_key).strip()[:80] if idempotency_key else None
    if clave:
        previo = one(
            "SELECT id_conteo::text, lineas_contadas, lineas_con_diferencia, exactitud_pct, ajustes "
            "FROM operacion.conteo_ciclico WHERE idempotency_key = :k",
            k=clave,
        )
        if previo:
            return {**_resultado_conteo(previo), "repetido": True}

    id_conteo = str(uuid.uuid4())
    ajustes: list[dict] = []
    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        for linea in lineas:
            ex = conn.execute(
                text(
                    """
                    SELECT e.cantidad_disponible, e.cantidad_reservada, l.codigo_lote_prov,
                           l.costo_unitario, l.id_sku
                    FROM operacion.existencia e
                    JOIN operacion.lote l ON l.id_lote = e.id_lote
                    WHERE e.id_lote = CAST(:lote AS uuid) AND e.id_locacion = :loc
                    FOR UPDATE OF e
                    """
                ),
                {"lote": linea["id_lote"], "loc": id_locacion},
            ).mappings().first()
            if ex is None:
                raise ValueError(f"El lote {linea['id_lote']} no tiene existencia en esta tienda.")
            if id_sku and a_int(ex["id_sku"]) != int(id_sku):
                raise ValueError(f"El lote {ex['codigo_lote_prov']} no es del producto contado.")

            sistema = a_float(ex["cantidad_disponible"])
            contado = round(a_float(linea["cantidad_contada"]), 2)
            diferencia = round(contado - sistema, 2)
            if abs(diferencia) < TOLERANCIA:
                continue
            if contado < a_float(ex["cantidad_reservada"]):
                raise ValueError(
                    f"El lote {ex['codigo_lote_prov']} tiene {a_float(ex['cantidad_reservada']):g} unidades "
                    f"reservadas; no puede contarse por debajo de eso."
                )
            conn.execute(
                text(
                    "UPDATE operacion.existencia SET cantidad_disponible = :c, actualizado_en = now() "
                    "WHERE id_lote = CAST(:lote AS uuid) AND id_locacion = :loc"
                ),
                {"c": contado, "lote": linea["id_lote"], "loc": id_locacion},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO operacion.movimiento_inventario
                        (id_lote, id_locacion, tipo, cantidad, cantidad_resultante, costo_unitario,
                         referencia_tipo, referencia_id, id_usuario)
                    VALUES (CAST(:lote AS uuid), :loc, 'AJUSTE', :dif, :res, :costo,
                            'CONTEO', CAST(:ref AS uuid), CAST(:uid AS uuid))
                    """
                ),
                {"lote": linea["id_lote"], "loc": id_locacion, "dif": diferencia, "res": contado,
                 "costo": a_float(ex["costo_unitario"]), "ref": id_conteo, "uid": usuario["id_usuario"]},
            )
            ajustes.append({"id_lote": linea["id_lote"], "codigo_lote_prov": ex["codigo_lote_prov"],
                            "sistema": sistema, "contado": contado, "diferencia": diferencia})

        exactitud = round(100.0 * (len(lineas) - len(ajustes)) / len(lineas), 2)
        conn.execute(
            text(
                """
                INSERT INTO operacion.conteo_ciclico
                    (id_conteo, id_locacion, id_sku, idempotency_key, lineas_contadas,
                     lineas_con_diferencia, exactitud_pct, ajustes, observacion, id_usuario)
                VALUES (CAST(:id AS uuid), :loc, :sku, :k, :n, :nd, :ex, CAST(:aj AS jsonb), :obs, CAST(:uid AS uuid))
                """
            ),
            {"id": id_conteo, "loc": id_locacion, "sku": id_sku, "k": clave, "n": len(lineas),
             "nd": len(ajustes), "ex": exactitud, "aj": json.dumps(ajustes), "obs": observacion,
             "uid": usuario["id_usuario"]},
        )

    auditoria.registrar(
        "CYCLE_COUNT",
        tabla="conteo_ciclico",
        id_registro=id_conteo,
        descripcion=f"Conteo de {len(lineas)} lote(s) en la locación {id_locacion}: {len(ajustes)} con diferencia",
        estado_nuevo={"exactitud_pct": exactitud, "ajustes": ajustes},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_conteo": id_conteo, "lineas_contadas": len(lineas), "lineas_con_diferencia": len(ajustes),
            "exactitud_pct": exactitud, "ajustes": ajustes}


# ---------------------------------------------------------------------------
# Solicitud manual de transferencia
# ---------------------------------------------------------------------------
@invalida("web:triaje:*")
def solicitar_transferencia(
    *,
    id_lote: str,
    id_locacion_origen: int,
    id_locacion_destino: int,
    cantidad: float,
    motivo: str | None,
    usuario: dict,
) -> dict:
    """Crea una transferencia SUGERIDA pedida desde la tienda; la aprobación sigue el flujo normal."""
    if id_locacion_origen == id_locacion_destino:
        raise ValueError("El origen y el destino deben ser tiendas distintas.")
    lote = one(
        """
        SELECT l.id_sku, l.codigo_lote_prov, l.fecha_caducidad, l.estado, p.nombre AS producto,
               COALESCE(e.cantidad_disponible - e.cantidad_reservada, 0) AS libre
        FROM operacion.lote l
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        LEFT JOIN operacion.existencia e ON e.id_lote = l.id_lote AND e.id_locacion = :origen
        WHERE l.id_lote = CAST(:lote AS uuid)
        """,
        lote=id_lote,
        origen=id_locacion_origen,
    )
    if lote is None:
        raise ValueError("El lote no existe.")
    destino = one(
        "SELECT nombre FROM operacion.locacion WHERE id_locacion = :d AND activo AND tipo_locacion = 'Tienda'",
        d=id_locacion_destino,
    )
    if destino is None:
        raise ValueError("La tienda destino no existe o no está activa.")
    origen = one("SELECT nombre FROM operacion.locacion WHERE id_locacion = :o", o=id_locacion_origen)

    libre = a_float(lote["libre"])
    dias = (lote["fecha_caducidad"] - date.today()).days
    validaciones = {
        "lote_disponible": {"pasa": lote["estado"] == "DISPONIBLE", "detalle": f"El lote está {lote['estado']}"},
        "origen_suficiente": {"pasa": libre >= cantidad,
                              "detalle": f"{origen['nombre'] if origen else id_locacion_origen} tiene {libre:g} unidades libres"},
        "llega_antes_de_vencer": {"pasa": dias > DIAS_TRANSITO,
                                  "detalle": f"El lote vence en {dias} días y el traslado toma {DIAS_TRANSITO} día(s)"},
    }
    fallas = [v["detalle"] for v in validaciones.values() if not v["pasa"]]
    if fallas:
        raise ValueError("No se puede solicitar: " + "; ".join(fallas) + ".")

    existente = one(
        """
        SELECT id_transferencia::text FROM analitica.transferencia
        WHERE id_lote = CAST(:lote AS uuid) AND id_locacion_origen = :o AND id_locacion_destino = :d
          AND estado IN ('SUGERIDA', 'APROBADA')
        LIMIT 1
        """,
        lote=id_lote, o=id_locacion_origen, d=id_locacion_destino,
    )
    if existente:
        raise ValueError(f"Ya hay una transferencia pendiente de este lote a esa tienda ({existente['id_transferencia']}).")

    texto_motivo = (motivo or "").strip()[:500] or "Solicitada desde la app móvil"
    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        id_tr = conn.execute(
            text(
                """
                INSERT INTO analitica.transferencia
                    (id_sku, id_lote, id_locacion_origen, id_locacion_destino, cantidad, motivo,
                     dias_para_vencer, validaciones, estado, id_usuario_solicita)
                VALUES (:sku, CAST(:lote AS uuid), :o, :d, :c, :m, :dias, CAST(:v AS jsonb),
                        'SUGERIDA', CAST(:uid AS uuid))
                RETURNING id_transferencia::text
                """
            ),
            {"sku": lote["id_sku"], "lote": id_lote, "o": id_locacion_origen, "d": id_locacion_destino,
             "c": cantidad, "m": texto_motivo, "dias": dias, "v": json.dumps(validaciones),
             "uid": usuario["id_usuario"]},
        ).scalar()

    auditoria.registrar(
        "REQUEST_TRANSFER",
        tabla="transferencia",
        id_registro=id_tr,
        descripcion=f"Solicitud de {cantidad:g} de {lote['producto']}: {origen['nombre'] if origen else id_locacion_origen} → {destino['nombre']}",
        estado_nuevo={"estado": "SUGERIDA", "cantidad": cantidad},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_transferencia": id_tr, "estado": "SUGERIDA", "cantidad": cantidad, "producto": lote["producto"],
            "origen": origen["nombre"] if origen else None, "destino": destino["nombre"],
            "dias_para_vencer": dias, "validaciones": validaciones}


# ---------------------------------------------------------------------------
# Evidencia fotográfica
# ---------------------------------------------------------------------------
_COLUMNAS_EV = """
    id_evidencia::text, tipo, referencia_tipo, referencia_id, id_locacion, content_type,
    tamano_bytes, sha256, storage_provider, bucket, object_key, descripcion, creado_en
"""


def _con_url(fila: dict) -> dict:
    ev = dict(fila)
    ev["url_firmada"] = object_storage.url_firmada(ev["object_key"], bucket=ev["bucket"], expira_segundos=URL_EXPIRA_SEG)
    ev["url_expira_en_segundos"] = URL_EXPIRA_SEG
    return ev


def guardar_evidencia(
    *,
    contenido: bytes,
    content_type: str,
    tipo: str,
    referencia_tipo: str | None,
    referencia_id: str | None,
    descripcion: str | None,
    id_locacion: int | None,
    usuario: dict,
) -> dict:
    """Sube la foto al bucket privado y registra sus metadatos. Lanza AlmacenamientoNoDisponible si el bucket falla."""
    id_ev = str(uuid.uuid4())
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]
    key = f"evidencias/{id_locacion or 'general'}/{date.today():%Y/%m}/{id_ev}.{ext}"
    meta = object_storage.subir_objeto(key, contenido, content_type)
    with transaccion(id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]) as conn:
        fila = conn.execute(
            text(
                f"""
                INSERT INTO operacion.evidencia
                    (id_evidencia, tipo, referencia_tipo, referencia_id, id_locacion, content_type,
                     tamano_bytes, sha256, storage_provider, bucket, object_key, descripcion, id_usuario)
                VALUES (CAST(:id AS uuid), :tipo, :rt, :rid, :loc, :ct, :tam, :sha, :prov, :bkt, :key, :desc,
                        CAST(:uid AS uuid))
                RETURNING {_COLUMNAS_EV}
                """
            ),
            {"id": id_ev, "tipo": tipo, "rt": referencia_tipo, "rid": referencia_id, "loc": id_locacion,
             "ct": content_type, "tam": meta["tamano_bytes"], "sha": meta["sha256"],
             "prov": meta["storage_provider"], "bkt": meta["bucket"], "key": meta["object_key"],
             "desc": descripcion, "uid": usuario["id_usuario"]},
        ).mappings().first()
    auditoria.registrar(
        "UPLOAD_EVIDENCE",
        tabla="evidencia",
        id_registro=id_ev,
        descripcion=f"Evidencia {tipo} ({meta['tamano_bytes'] // 1024} KB) en gs://{meta['bucket']}/{meta['object_key']}",
        estado_nuevo={"sha256": meta["sha256"], "referencia_tipo": referencia_tipo, "referencia_id": referencia_id},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return _con_url(fila)


def listar_evidencias(id_locacion: int | None, limite: int = 50) -> list[dict]:
    return query(
        f"""
        SELECT {_COLUMNAS_EV} FROM operacion.evidencia
        WHERE (CAST(:loc AS integer) IS NULL OR id_locacion = :loc)
        ORDER BY creado_en DESC
        LIMIT :lim
        """,
        loc=id_locacion,
        lim=limite,
    )


def evidencia_con_url(id_evidencia: str) -> dict | None:
    fila = one(f"SELECT {_COLUMNAS_EV} FROM operacion.evidencia WHERE id_evidencia = CAST(:id AS uuid)", id=id_evidencia)
    return _con_url(fila) if fila else None


def ligar_evidencia_a_merma(id_evidencia: str, id_merma: str) -> None:
    """Liga la foto con la merma registrada (la app sube la foto antes de registrar la merma)."""
    with transaccion() as conn:
        conn.execute(
            text("UPDATE operacion.merma SET id_evidencia = CAST(:ev AS uuid) WHERE id_merma = CAST(:m AS uuid)"),
            {"ev": id_evidencia, "m": id_merma},
        )
        conn.execute(
            text(
                "UPDATE operacion.evidencia SET referencia_tipo = 'MERMA', referencia_id = :m "
                "WHERE id_evidencia = CAST(:ev AS uuid)"
            ),
            {"ev": id_evidencia, "m": id_merma},
        )
