"""
Motor de reabastecimiento.

Lo que distingue a FreshTrack de un sistema de inventarios normal es que aquí
el inventario **no** es un número: se separa en tres.

    Inventario físico            lo que hay en el anaquel
    Inventario en riesgo         lo que va a vencer antes de poder venderse
    Inventario útil proyectado   físico − en riesgo

La fórmula de la necesidad neta es:

    Necesidad = Demanda del horizonte
              + Stock de seguridad
              − Inventario útil proyectado
              − Entradas confirmadas

Y la recomendación considera además:

    * Lead time del proveedor → hay que cubrir la demanda de esos días
    * MOQ (pedido mínimo)     → si la necesidad es menor, se advierte del exceso
    * Caducidad               → no se pide lo que no se podrá vender a tiempo

Cada recomendación se guarda con su explicación completa para que un humano
pueda revisarla y aprobarla o rechazarla. El sistema nunca decide solo.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, config_valor, one, query, transaccion
from app.domain import pronostico


# ---------------------------------------------------------------------------
# Demanda proyectada
# ---------------------------------------------------------------------------
def demanda_proyectada(id_sku: int, id_locacion: int, dias: int) -> tuple[float, str]:
    """
    Demanda esperada para los próximos `dias`.

    Usa el pronóstico vigente si existe; si no, cae al promedio diario de los
    últimos 28 días. Devuelve (cantidad, origen) para poder explicarlo.
    """
    fila = one(
        """
        SELECT COALESCE(SUM(demanda_pronosticada), 0) AS total, COUNT(*) AS dias
        FROM analitica.forecast_result
        WHERE id_sku = :sku AND id_locacion = :loc
          AND id_run = (
              SELECT id_run FROM analitica.forecast_run
              WHERE estado = 'COMPLETADO' ORDER BY fecha_ejecucion DESC LIMIT 1
          )
          AND horizonte_dia <= :dias
        """,
        sku=id_sku,
        loc=id_locacion,
        dias=dias,
    )
    if fila and fila["dias"]:
        return a_float(fila["total"]), "pronostico"
    promedio = pronostico.demanda_diaria_promedio(id_sku, id_locacion, 28)
    return round(promedio * dias, 2), "promedio_28d"


# ---------------------------------------------------------------------------
# Riesgo de desperdicio por lote
# ---------------------------------------------------------------------------
def riesgo_por_lote(
    id_sku: int, id_locacion: int, dias_ventana: int | None = None
) -> list[dict]:
    """
    Para cada lote con existencia estima cuántas unidades van a sobrar:

        unidades_en_riesgo = cantidad_disponible − demanda esperada antes de caducar

    Es el cálculo que hace útil el módulo: 80 unidades que vencen en 3 días no
    equivalen a 80 unidades utilizables si en 3 días solo se van a vender 47.
    """
    if dias_ventana is None:
        dias_ventana = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)

    promedio_diario = pronostico.demanda_diaria_promedio(id_sku, id_locacion, 28)

    lotes = query(
        """
        SELECT id_lote::text, codigo_lote_prov, cantidad_disponible,
               fecha_caducidad, (fecha_caducidad - CURRENT_DATE) AS dias_restantes,
               clasificacion, vida_util_pct, costo_unitario, unidad_medida
        FROM operacion.v_inventario_lote
        WHERE id_sku = :sku AND id_locacion = :loc AND cantidad_disponible > 0
        ORDER BY fecha_caducidad ASC
        """,
        sku=id_sku,
        loc=id_locacion,
    )

    salida = []
    for lote in lotes:
        dias = a_int(lote["dias_restantes"], 0)
        disponible = a_float(lote["cantidad_disponible"])
        if dias < 0:
            demanda_antes = 0.0
        else:
            dias_utiles = min(dias, dias_ventana)
            demanda_antes = round(promedio_diario * dias_utiles, 2)

        en_riesgo = max(0.0, round(disponible - demanda_antes, 2))
        salida.append(
            {
                **lote,
                "cantidad_disponible": round(disponible, 2),
                "demanda_antes_caducidad": demanda_antes,
                "unidades_en_riesgo": en_riesgo,
                "valor_en_riesgo": round(en_riesgo * a_float(lote["costo_unitario"]), 2),
            }
        )
    return salida


# ---------------------------------------------------------------------------
# Análisis de un par producto + tienda
# ---------------------------------------------------------------------------
def analizar_sku_locacion(
    id_sku: int, id_locacion: int, horizonte: int | None = None
) -> dict:
    """
    Calcula la situación completa de un producto en una tienda y, si hace
    falta, la recomendación de reabastecimiento con su explicación.
    """
    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)
    umbral_sobreinventario = a_int(config_valor("umbral_sobreinventario_dias", "21"), 21)
    dias_ventana_riesgo = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)

    producto = one(
        """
        SELECT p.id_sku, p.nombre, p.categoria, p.unidad_medida, p.precio_costo,
               p.precio_venta, p.stock_seguridad, p.punto_reorden, p.vida_util_estandar,
               p.id_proveedor, pr.razon_social AS proveedor,
               COALESCE(pr.lead_time_dias, 3) AS lead_time_dias,
               COALESCE(pr.moq, 1)            AS moq
        FROM operacion.producto p
        LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        WHERE p.id_sku = :sku
        """,
        sku=id_sku,
    )
    if producto is None:
        raise ValueError(f"El producto {id_sku} no existe.")

    locacion = one(
        "SELECT id_locacion, nombre, tipo_locacion FROM operacion.locacion WHERE id_locacion = :l",
        l=id_locacion,
    )
    if locacion is None:
        raise ValueError(f"La locación {id_locacion} no existe.")

    # --- Inventario desglosado
    lotes = riesgo_por_lote(id_sku, id_locacion, dias_ventana_riesgo)
    inventario_fisico = round(sum(l["cantidad_disponible"] for l in lotes), 2)
    inventario_riesgo = round(sum(l["unidades_en_riesgo"] for l in lotes), 2)
    inventario_util = round(inventario_fisico - inventario_riesgo, 2)

    # --- Demanda
    demanda_horizonte, origen_demanda = demanda_proyectada(id_sku, id_locacion, horizonte)
    lead_time = a_int(producto["lead_time_dias"], 3)
    demanda_lead_time, _ = demanda_proyectada(id_sku, id_locacion, lead_time)
    demanda_diaria = round(demanda_horizonte / horizonte, 2) if horizonte else 0.0

    stock_seguridad = a_float(producto["stock_seguridad"])

    # --- Entradas confirmadas (órdenes aprobadas y todavía no recibidas)
    entradas = a_float(
        one(
            """
            SELECT COALESCE(SUM(COALESCE(cantidad_aprobada, cantidad_sugerida)), 0) AS total
            FROM analitica.orden_reabastecimiento
            WHERE id_sku = :sku AND id_locacion = :loc
              AND estado IN ('PENDIENTE', 'APROBADA')
            """,
            sku=id_sku,
            loc=id_locacion,
        )["total"]
    )

    necesidad = round(
        demanda_horizonte + stock_seguridad - inventario_util - entradas, 2
    )

    moq = a_float(producto["moq"])
    advertencias: list[str] = []
    cantidad_sugerida = 0.0

    if necesidad <= 0:
        cantidad_sugerida = 0.0
        if inventario_util > demanda_horizonte + stock_seguridad and demanda_diaria > 0:
            cobertura = round(inventario_util / demanda_diaria, 1)
            if cobertura > umbral_sobreinventario:
                advertencias.append(
                    f"Sobreinventario: hay {inventario_util:g} unidades útiles, "
                    f"suficientes para {cobertura:g} días de demanda "
                    f"(el umbral es {umbral_sobreinventario} días). No conviene pedir más."
                )
    else:
        if necesidad < moq:
            cantidad_sugerida = moq
            advertencias.append(
                f"El proveedor tiene un pedido mínimo (MOQ) de {moq:g} unidades y la "
                f"necesidad calculada es de {necesidad:g}. Se sugiere comprar {moq:g}, "
                f"es decir {round(moq - necesidad, 2):g} unidades por encima de lo necesario."
            )
        else:
            # Se redondea hacia arriba al múltiplo de MOQ más cercano
            cantidad_sugerida = round(necesidad)
            if moq > 1:
                multiplos = round(necesidad / moq)
                if multiplos * moq >= necesidad:
                    cantidad_sugerida = multiplos * moq

        # ¿El exceso del MOQ generaría sobreinventario?
        exceso = round(cantidad_sugerida - necesidad, 2)
        if exceso > 0:
            cobertura_post = (
                round((inventario_util + cantidad_sugerida) / demanda_diaria, 1)
                if demanda_diaria > 0
                else 0
            )
            if demanda_diaria > 0 and cobertura_post > umbral_sobreinventario:
                advertencias.append(
                    f"Advertencia: si se compran {cantidad_sugerida:g} unidades, la "
                    f"cobertura subiría a {cobertura_post:g} días "
                    f"(umbral de sobreinventario: {umbral_sobreinventario} días). "
                    f"Revisa si conviene ajustar la cantidad."
                )

        # Riesgo de vencimiento del inventario pedido
        vida_util = a_int(producto["vida_util_estandar"], 15)
        if demanda_diaria > 0:
            dias_para_vender = round((inventario_util + cantidad_sugerida) / demanda_diaria, 1)
            if dias_para_vender > vida_util:
                advertencias.append(
                    f"Riesgo de vencimiento: con {inventario_util + cantidad_sugerida:g} "
                    f"unidades se tardarían {dias_para_vender:g} días en venderse, pero el "
                    f"producto dura {vida_util} días. Parte del pedido podría caducar."
                )

    if inventario_riesgo > 0:
        advertencias.append(
            f"{inventario_riesgo:g} unidades del inventario actual están en riesgo de "
            f"vencer antes de poder venderse; no se contaron como inventario útil."
        )

    if lead_time > 0 and demanda_diaria > 0:
        cobertura_actual = round(inventario_util / demanda_diaria, 1)
        if cobertura_actual < lead_time:
            advertencias.append(
                f"El inventario útil cubre {cobertura_actual:g} días y el proveedor tarda "
                f"{lead_time} días en surtir: hay riesgo de faltante si no se pide ahora."
            )

    prioridad = "BAJA"
    if cantidad_sugerida > 0:
        cobertura_actual = (
            inventario_util / demanda_diaria if demanda_diaria > 0 else 999
        )
        if cobertura_actual <= max(1, lead_time):
            prioridad = "ALTA"
        elif cobertura_actual <= horizonte:
            prioridad = "MEDIA"

    return {
        "producto": producto,
        "locacion": locacion,
        "horizonte": horizonte,
        "lead_time_dias": lead_time,
        "moq": moq,
        "demanda_horizonte": demanda_horizonte,
        "demanda_lead_time": demanda_lead_time,
        "demanda_diaria": demanda_diaria,
        "origen_demanda": origen_demanda,
        "inventario_fisico": inventario_fisico,
        "inventario_riesgo": inventario_riesgo,
        "inventario_util": inventario_util,
        "entradas_confirmadas": round(entradas, 2),
        "stock_seguridad": stock_seguridad,
        "necesidad_neta": necesidad,
        "cantidad_sugerida": round(cantidad_sugerida, 2),
        "prioridad": prioridad,
        "advertencias": advertencias,
        "lotes": lotes,
        "lotes_en_riesgo": [l for l in lotes if l["unidades_en_riesgo"] > 0],
    }


def explicar(analisis: dict) -> str:
    """Texto legible con el desglose completo de la recomendación."""
    p = analisis["producto"]
    loc = analisis["locacion"]
    lineas = [
        f"Producto: {p['nombre']}",
        f"Tienda: {loc['nombre']}",
        "",
        f"Demanda prevista {analisis['horizonte']} días     {analisis['demanda_horizonte']:>10,.2f}",
        f"Inventario físico                  {analisis['inventario_fisico']:>10,.2f}",
        f"Inventario próximo a vencer        {analisis['inventario_riesgo']:>10,.2f}",
        f"Inventario útil                    {analisis['inventario_util']:>10,.2f}",
        f"Stock de seguridad                 {analisis['stock_seguridad']:>10,.2f}",
        f"Entradas confirmadas               {analisis['entradas_confirmadas']:>10,.2f}",
        f"Lead time                          {analisis['lead_time_dias']:>10} días",
        f"MOQ                                {analisis['moq']:>10,.2f}",
        "",
        f"Necesidad neta                     {analisis['necesidad_neta']:>10,.2f}",
        "",
        f"Recomendación: ordenar {analisis['cantidad_sugerida']:,.0f} {p['unidad_medida']}"
        if analisis["cantidad_sugerida"] > 0
        else "Recomendación: no ordenar. El inventario útil cubre la demanda.",
    ]
    if analisis["advertencias"]:
        lineas.append("")
        lineas.append("Advertencias:")
        lineas.extend(f"  · {a}" for a in analisis["advertencias"])
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Generación de órdenes
# ---------------------------------------------------------------------------
def generar_recomendaciones(
    *, usuario: dict, horizonte: int | None = None, solo_con_necesidad: bool = True
) -> dict:
    """
    Recorre todos los pares producto + tienda con historia y genera órdenes
    de reabastecimiento para los que lo necesitan. Evita duplicar órdenes
    que ya están pendientes.
    """
    from app.domain.ventas import pares_con_historia

    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)

    pares = pares_con_historia(min_dias=14)
    generadas = []
    revisadas = 0

    for par in pares:
        id_sku, id_locacion = par["id_sku"], par["id_locacion"]
        try:
            analisis = analizar_sku_locacion(id_sku, id_locacion, horizonte)
        except ValueError:
            continue
        revisadas += 1

        if solo_con_necesidad and analisis["cantidad_sugerida"] <= 0:
            continue

        pendiente = one(
            """
            SELECT id_orden::text FROM analitica.orden_reabastecimiento
            WHERE id_sku = :sku AND id_locacion = :loc AND estado = 'PENDIENTE'
            LIMIT 1
            """,
            sku=id_sku,
            loc=id_locacion,
        )
        if pendiente:
            continue

        with transaccion(
            id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
        ) as conn:
            id_orden = conn.execute(
                text(
                    """
                    INSERT INTO analitica.orden_reabastecimiento
                        (id_sku, id_locacion, id_proveedor, id_run,
                         demanda_pronosticada, inventario_fisico, inventario_riesgo,
                         inventario_util, entradas_confirmadas, stock_seguridad,
                         lead_time_dias, moq,
                         necesidad_neta, cantidad_sugerida, prioridad, estado,
                         explicacion, advertencias, id_usuario_solicita)
                    VALUES
                        (:sku, :loc, :prov,
                         (SELECT id_run FROM analitica.forecast_run
                          WHERE estado='COMPLETADO' ORDER BY fecha_ejecucion DESC LIMIT 1),
                         :demanda, :fisico, :riesgo, :util, :entradas, :seguridad,
                         :lead, :moq,
                         :necesidad, :sugerida, :prioridad, 'PENDIENTE',
                         :explicacion, CAST(:advertencias AS jsonb), CAST(:uid AS uuid))
                    RETURNING id_orden::text
                    """
                ),
                {
                    "sku": id_sku,
                    "loc": id_locacion,
                    "prov": analisis["producto"]["id_proveedor"],
                    "demanda": analisis["demanda_horizonte"],
                    "fisico": analisis["inventario_fisico"],
                    "riesgo": analisis["inventario_riesgo"],
                    "util": analisis["inventario_util"],
                    "entradas": analisis["entradas_confirmadas"],
                    "seguridad": analisis["stock_seguridad"],
                    "lead": analisis["lead_time_dias"],
                    "moq": analisis["moq"],
                    "necesidad": analisis["necesidad_neta"],
                    "sugerida": analisis["cantidad_sugerida"],
                    "prioridad": analisis["prioridad"],
                    "explicacion": explicar(analisis),
                    "advertencias": _json(analisis["advertencias"]),
                    "uid": usuario["id_usuario"],
                },
            ).scalar()

        generadas.append(
            {
                "id_orden": id_orden,
                "producto": analisis["producto"]["nombre"],
                "locacion": analisis["locacion"]["nombre"],
                "cantidad_sugerida": analisis["cantidad_sugerida"],
                "prioridad": analisis["prioridad"],
                "necesidad_neta": analisis["necesidad_neta"],
            }
        )

        auditoria.registrar(
            "CREATE_REPLENISHMENT",
            tabla="orden_reabastecimiento",
            id_registro=id_orden,
            descripcion=(
                f"Orden sugerida: {analisis['cantidad_sugerida']:g} "
                f"{analisis['producto']['unidad_medida']} de "
                f"{analisis['producto']['nombre']} para {analisis['locacion']['nombre']} "
                f"(prioridad {analisis['prioridad']})"
            ),
            estado_nuevo={
                "necesidad_neta": analisis["necesidad_neta"],
                "cantidad_sugerida": analisis["cantidad_sugerida"],
                "inventario_util": analisis["inventario_util"],
                "inventario_riesgo": analisis["inventario_riesgo"],
            },
            id_usuario=usuario["id_usuario"],
            usuario_email=usuario["email"],
        )

    return {"generadas": generadas, "total": len(generadas), "revisadas": revisadas}


def _json(valor) -> str:
    import json

    return json.dumps(valor, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Consultas y flujo de aprobación
# ---------------------------------------------------------------------------
def listar_ordenes(estado: str | None = None, limite: int = 100) -> list[dict]:
    filtro = "WHERE o.estado = :estado" if estado else ""
    params = {"estado": estado, "limite": limite} if estado else {"limite": limite}
    return query(
        f"""
        SELECT o.id_orden::text, o.estado, o.prioridad, o.fecha_creacion, o.fecha_decision,
               o.demanda_pronosticada, o.inventario_fisico, o.inventario_riesgo,
               o.inventario_util, o.entradas_confirmadas, o.stock_seguridad,
               o.lead_time_dias, o.moq,
               o.necesidad_neta, o.cantidad_sugerida, o.cantidad_aprobada,
               o.explicacion, o.advertencias,
               p.nombre AS producto, p.id_sku, p.unidad_medida, p.precio_costo,
               loc.nombre AS locacion, loc.id_locacion,
               pr.razon_social AS proveedor,
               us.nombre_completo AS solicita,
               ua.nombre_completo AS aprueba
        FROM analitica.orden_reabastecimiento o
        JOIN operacion.producto  p   ON p.id_sku = o.id_sku
        JOIN operacion.locacion  loc ON loc.id_locacion = o.id_locacion
        LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = o.id_proveedor
        LEFT JOIN operacion.usuario   us ON us.id_usuario = o.id_usuario_solicita
        LEFT JOIN operacion.usuario   ua ON ua.id_usuario = o.id_usuario_aprueba
        {filtro}
        ORDER BY
            CASE o.prioridad WHEN 'ALTA' THEN 1 WHEN 'MEDIA' THEN 2 ELSE 3 END,
            o.fecha_creacion DESC
        LIMIT :limite
        """,
        **params,
    )


def decidir_orden(
    id_orden: str, *, aprobar: bool, usuario: dict, cantidad: float | None = None
) -> dict:
    """Aprueba o rechaza una orden. Registra la decisión con quién y cuándo."""
    orden = one(
        """
        SELECT o.id_orden::text, o.estado, o.cantidad_sugerida, o.id_sku, o.id_locacion,
               p.nombre AS producto, loc.nombre AS locacion
        FROM analitica.orden_reabastecimiento o
        JOIN operacion.producto p   ON p.id_sku = o.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = o.id_locacion
        WHERE o.id_orden = CAST(:id AS uuid)
        """,
        id=id_orden,
    )
    if orden is None:
        raise ValueError("La orden no existe.")
    if orden["estado"] != "PENDIENTE":
        raise ValueError(f"La orden ya está en estado {orden['estado']}.")

    aprobada = a_float(cantidad) if cantidad is not None else a_float(orden["cantidad_sugerida"])
    nuevo_estado = "APROBADA" if aprobar else "RECHAZADA"

    with transaccion(
        id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
    ) as conn:
        conn.execute(
            text(
                """
                UPDATE analitica.orden_reabastecimiento
                   SET estado = :estado,
                       cantidad_aprobada = :cantidad,
                       id_usuario_aprueba = CAST(:uid AS uuid),
                       fecha_decision = now()
                 WHERE id_orden = CAST(:id AS uuid)
                """
            ),
            {
                "estado": nuevo_estado,
                "cantidad": aprobada if aprobar else None,
                "uid": usuario["id_usuario"],
                "id": id_orden,
            },
        )

    auditoria.registrar(
        "APPROVE_REPLENISHMENT" if aprobar else "REJECT_REPLENISHMENT",
        tabla="orden_reabastecimiento",
        id_registro=id_orden,
        descripcion=(
            f"{'Aprobada' if aprobar else 'Rechazada'} la orden de "
            f"{orden['producto']} para {orden['locacion']}"
            + (f" por {aprobada:g} unidades" if aprobar else "")
        ),
        estado_anterior={"estado": "PENDIENTE"},
        estado_nuevo={"estado": nuevo_estado, "cantidad_aprobada": aprobada if aprobar else None},
        id_usuario=usuario["id_usuario"],
        usuario_email=usuario["email"],
    )
    return {"id_orden": id_orden, "estado": nuevo_estado, "cantidad": aprobada}


def resumen_ordenes() -> dict:
    fila = one(
        """
        SELECT COUNT(*) FILTER (WHERE estado = 'PENDIENTE')  AS pendientes,
               COUNT(*) FILTER (WHERE estado = 'APROBADA')   AS aprobadas,
               COUNT(*) FILTER (WHERE estado = 'RECHAZADA')  AS rechazadas,
               COUNT(*) FILTER (WHERE estado = 'PENDIENTE' AND prioridad = 'ALTA') AS urgentes,
               COALESCE(SUM(CASE WHEN estado = 'PENDIENTE'
                                 THEN cantidad_sugerida * (SELECT AVG(precio_costo)
                                                           FROM operacion.producto) END), 0) AS valor_estimado
        FROM analitica.orden_reabastecimiento
        """
    ) or {}
    return fila


def sobreinventario(horizonte: int | None = None, limite: int = 50) -> list[dict]:
    """Productos donde el inventario útil supera la demanda esperada."""
    if horizonte is None:
        horizonte = a_int(config_valor("umbral_sobreinventario_dias", "21"), 21)

    filas = query(
        """
        WITH inventario AS (
            SELECT id_sku, id_locacion,
                   SUM(cantidad_disponible) AS fisico,
                   SUM(CASE WHEN clasificacion IN ('CRITICO','VENCIDO')
                            THEN cantidad_disponible ELSE 0 END) AS en_riesgo
            FROM operacion.v_inventario_lote
            WHERE cantidad_disponible > 0
            GROUP BY id_sku, id_locacion
        ),
        demanda AS (
            SELECT id_sku, id_locacion, AVG(cantidad) AS diaria
            FROM analitica.v_demanda_diaria
            WHERE fecha >= CURRENT_DATE - 28
            GROUP BY id_sku, id_locacion
        )
        SELECT p.nombre AS producto, p.id_sku, p.unidad_medida, p.vida_util_estandar,
               loc.nombre AS locacion, loc.id_locacion,
               i.fisico, i.en_riesgo, (i.fisico - i.en_riesgo) AS util,
               COALESCE(d.diaria, 0) AS demanda_diaria,
               CASE WHEN COALESCE(d.diaria, 0) > 0
                    THEN ROUND((i.fisico - i.en_riesgo) / d.diaria, 1)
                    ELSE NULL END AS dias_cobertura
        FROM inventario i
        JOIN operacion.producto p   ON p.id_sku = i.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = i.id_locacion
        LEFT JOIN demanda d ON d.id_sku = i.id_sku AND d.id_locacion = i.id_locacion
        WHERE COALESCE(d.diaria, 0) > 0
          AND (i.fisico - i.en_riesgo) / d.diaria > :umbral
        ORDER BY dias_cobertura DESC
        LIMIT :limite
        """,
        umbral=horizonte,
        limite=limite,
    )
    for fila in filas:
        fila["fisico"] = a_float(fila["fisico"])
        fila["en_riesgo"] = a_float(fila["en_riesgo"])
        fila["util"] = a_float(fila["util"])
    return filas


def demanda_por_vencer(id_sku: int, id_locacion: int) -> float:
    """Demanda esperada dentro de la ventana de riesgo configurada."""
    dias = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)
    valor, _ = demanda_proyectada(id_sku, id_locacion, dias)
    return valor
