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

import math
from datetime import date, timedelta
from statistics import NormalDist

from sqlalchemy import text

from app import auditoria
from app.db import a_float, a_int, config_valor, one, query, transaccion
from app.domain import pronostico


# ---------------------------------------------------------------------------
# Optimizador Newsvendor (cantidad óptima bajo demanda incierta y caducidad)
# ---------------------------------------------------------------------------
def _desviacion_diaria(id_sku: int, id_locacion: int, dias: int = 28) -> float:
    """Calcula la desviación estándar de la demanda diaria (incluyendo días en cero)."""
    filas = query(
        """
        SELECT fecha, SUM(cantidad) AS cantidad
        FROM analitica.v_demanda_diaria
        WHERE id_sku = :sku AND id_locacion = :loc
          AND fecha >= CURRENT_DATE - :dias
        GROUP BY fecha
        """,
        sku=id_sku,
        loc=id_locacion,
        dias=dias,
    )
    por_fecha = {f["fecha"]: a_float(f["cantidad"]) for f in filas}
    hoy = date.today()
    valores = [por_fecha.get(hoy - timedelta(days=i), 0.0) for i in range(dias)]
    if not valores:
        return 0.0
    media = sum(valores) / len(valores)
    var = sum((v - media) ** 2 for v in valores) / len(valores)
    return round(math.sqrt(var), 4)


def _costo_esperado_politica(
    nivel_objetivo: float,
    media: float,
    sigma: float,
    c_u: float,
    c_o: float,
    max_vida: float | None = None,
) -> float:
    """Costo esperado total E[C_u * (D - S)+ + C_o * (S - D)+] bajo demanda Normal."""
    penal_vida = (
        max(0.0, nivel_objetivo - max_vida) * c_o * 0.5
        if max_vida is not None and max_vida > 0
        else 0.0
    )
    if sigma <= 1e-6:
        faltante = max(0.0, media - nivel_objetivo)
        excedente = max(0.0, nivel_objetivo - media)
        return round(faltante * c_u + excedente * c_o + penal_vida, 2)

    norm = NormalDist(0.0, 1.0)
    z = (nivel_objetivo - media) / sigma
    esperado_exceso = max(0.0, sigma * (z * norm.cdf(z) + norm.pdf(z)))
    esperado_faltante = max(0.0, esperado_exceso + (media - nivel_objetivo))
    return round(esperado_faltante * c_u + esperado_exceso * c_o + penal_vida, 2)


def optimizar_newsvendor(
    *,
    precio_venta: float,
    precio_costo: float,
    demanda_media: float,
    desviacion_estandar: float,
    vida_util_dias: int,
    demanda_diaria: float,
    stock_util: float = 0.0,
    entradas: float = 0.0,
    stock_seguridad_simple: float = 0.0,
    valor_salvamento: float | None = None,
) -> dict:
    """
    Modelo Newsvendor para perecederos:
      - Costo de faltante (underage): C_u = max(0.01, P_venta - C_costo)
      - Costo de excedente (overage): C_o = max(0.01, C_costo - V_rescate)
      - Fractil crítico: F(Q*) = C_u / (C_u + C_o)
      - Inventario objetivo: S* = min(mu + z * sigma, demanda_diaria * vida_util_dias)
    """
    p_venta = max(0.0, a_float(precio_venta))
    p_costo = max(0.01, a_float(precio_costo))
    if valor_salvamento is None:
        # Recuperación parcial vía liquidación preventiva si vida útil > 3 días; si no, 0.
        valor_salvamento = round(p_costo * 0.25, 2) if vida_util_dias > 3 else 0.0

    c_u = round(max(0.01, p_venta - p_costo), 2)
    c_o = round(max(0.01, p_costo - valor_salvamento), 2)
    fractil = round(c_u / (c_u + c_o), 4)
    fractil_acotado = min(0.99, max(0.01, fractil))

    z_score = round(NormalDist(0.0, 1.0).inv_cdf(fractil_acotado), 4)
    sigma = max(0.0, a_float(desviacion_estandar))
    objetivo_raw = max(0.0, demanda_media + z_score * sigma)

    max_vida = (
        round(demanda_diaria * max(1, vida_util_dias), 2)
        if demanda_diaria > 0
        else None
    )
    acotado_por_caducidad = bool(max_vida is not None and objetivo_raw > max_vida)
    objetivo_nv = round(min(objetivo_raw, max_vida) if max_vida is not None else objetivo_raw, 2)

    necesidad_nv = round(max(0.0, objetivo_nv - stock_util - entradas), 2)
    objetivo_simple = round(max(0.0, demanda_media + stock_seguridad_simple), 2)
    necesidad_simple = round(max(0.0, objetivo_simple - stock_util - entradas), 2)

    costo_esp_nv = _costo_esperado_politica(
        objetivo_nv, demanda_media, sigma, c_u, c_o, max_vida
    )
    costo_esp_simple = _costo_esperado_politica(
        objetivo_simple, demanda_media, sigma, c_u, c_o, max_vida
    )
    ahorro = round(max(0.0, costo_esp_simple - costo_esp_nv), 2)

    return {
        "costo_faltante": c_u,
        "costo_excedente": c_o,
        "valor_salvamento": valor_salvamento,
        "fractil_critico": fractil,
        "z_score": z_score,
        "sigma_horizonte": round(sigma, 2),
        "stock_objetivo_newsvendor": objetivo_nv,
        "stock_objetivo_simple": objetivo_simple,
        "acotado_por_caducidad": acotado_por_caducidad,
        "cantidad_newsvendor": necesidad_nv,
        "cantidad_politica_simple": necesidad_simple,
        "costo_esperado_newsvendor": costo_esp_nv,
        "costo_esperado_simple": costo_esp_simple,
        "ahorro_esperado": ahorro,
    }


# ---------------------------------------------------------------------------
# Demanda proyectada
# ---------------------------------------------------------------------------
def demanda_proyectada(id_sku: int, id_locacion: int, dias: int) -> tuple[float, str]:
    """
    Demanda esperada para los próximos `dias`.

    Usa el pronóstico vigente del modelo propio de la tienda si existe; si no,
    cae al promedio diario de los últimos 28 días. Devuelve (cantidad, origen).
    """
    fila = one(
        """
        SELECT COALESCE(SUM(demanda_pronosticada), 0) AS total, COUNT(*) AS dias
        FROM analitica.forecast_result
        WHERE id_sku = :sku AND id_locacion = :loc
          AND id_run = (
              SELECT r.id_run
              FROM analitica.forecast_run r
              WHERE r.estado = 'COMPLETADO'
                AND (r.id_locacion = :loc OR r.id_locacion IS NULL)
                AND EXISTS (
                    SELECT 1 FROM analitica.forecast_result fr2
                    WHERE fr2.id_run = r.id_run AND fr2.id_sku = :sku AND fr2.id_locacion = :loc
                )
              ORDER BY (CASE WHEN r.id_locacion = :loc THEN 0 ELSE 1 END),
                       r.fecha_ejecucion DESC
              LIMIT 1
          )
          AND horizonte_dia <= :dias
        """,
        sku=id_sku,
        loc=id_locacion,
        dias=dias,
    )
    if fila and fila["dias"]:
        total = a_float(fila["total"])
        dias_cubiertos = a_int(fila["dias"], 0)
        if dias_cubiertos < dias and dias_cubiertos > 0:
            total = round(total / dias_cubiertos * dias, 2)
        return total, "pronostico"
    promedio = pronostico.demanda_diaria_promedio(id_sku, id_locacion, 28)
    return round(promedio * dias, 2), "promedio_28d"


# ---------------------------------------------------------------------------
# Riesgo de desperdicio por lote
# ---------------------------------------------------------------------------
def riesgo_por_lote(
    id_sku: int, id_locacion: int, dias_ventana: int | None = None
) -> list[dict]:
    """
    Simula consumo FEFO secuencial lote a lote (hoy → mañana → 2 días → ...)
    para estimar cuántas unidades caducarán antes de poder venderse:

        demanda_acumulada_hasta_caducidad = demanda_diaria * min(dias, dias_ventana)
        vendible_lote = min(disponible, max(0, demanda_acumulada - vendido_acumulado))
        unidades_en_riesgo = disponible - vendible_lote
    """
    if dias_ventana is None:
        dias_ventana = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)

    demanda_diaria = pronostico.demanda_diaria_vigente(id_sku, id_locacion)

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
    vendido_acumulado = 0.0
    for lote in lotes:
        dias = a_int(lote["dias_restantes"], 0)
        disponible = a_float(lote["cantidad_disponible"])
        if dias < 0:
            demanda_antes = 0.0
        else:
            dias_utiles = min(dias, dias_ventana)
            demanda_acum = demanda_diaria * dias_utiles
            demanda_antes = round(max(0.0, demanda_acum - vendido_acumulado), 2)
            vendible = min(disponible, demanda_antes)
            vendido_acumulado += vendible

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
    id_sku: int,
    id_locacion: int,
    horizonte: int | None = None,
    *,
    excluir_orden_id: str | None = None,
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
               COALESCE(p.moq_lote, pr.moq, 1) AS moq
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

    # --- Demanda e incertidumbre desacopladas del módulo de pronóstico
    fc = pronostico.pronostico_vigente_con_incertidumbre(id_sku, id_locacion, horizonte)
    demanda_horizonte = fc["demanda_media"]
    origen_demanda = fc["origen"]
    lead_time = a_int(producto["lead_time_dias"], 3)
    demanda_lead_time, _ = demanda_proyectada(id_sku, id_locacion, lead_time)
    demanda_diaria = round(demanda_horizonte / horizonte, 2) if horizonte else 0.0

    stock_seguridad = a_float(producto["stock_seguridad"])

    # --- Entradas confirmadas (órdenes pendientes/aprobadas + traslados entrantes de triaje)
    filtro_excl = "AND id_orden <> CAST(:excl AS uuid)" if excluir_orden_id else ""
    params_oc: dict = {"sku": id_sku, "loc": id_locacion}
    if excluir_orden_id:
        params_oc["excl"] = excluir_orden_id
    entradas_oc = a_float(
        (
            one(
                f"""
                SELECT COALESCE(SUM(COALESCE(cantidad_aprobada, cantidad_sugerida)), 0) AS total
                FROM analitica.orden_reabastecimiento
                WHERE id_sku = :sku AND id_locacion = :loc
                  AND estado IN ('PENDIENTE', 'APROBADA')
                  {filtro_excl}
                """,
                **params_oc,
            )
            or {}
        ).get("total")
    )
    entradas_traslados = a_float(
        (
            one(
                """
                SELECT COALESCE(SUM(cantidad), 0) AS total
                FROM analitica.transferencia
                WHERE id_sku = :sku AND id_locacion_destino = :loc
                  AND estado IN ('SUGERIDA', 'APROBADA')
                """,
                sku=id_sku,
                loc=id_locacion,
            )
            or {}
        ).get("total")
    )
    entradas = round(entradas_oc + entradas_traslados, 2)

    # Acciones preventivas locales vigentes (descuentos activos o traslados salientes)
    descuentos_activos = a_float(
        (
            one(
                """
                SELECT COALESCE(SUM(d.cantidad), 0) AS total
                FROM analitica.descuento d
                JOIN operacion.lote l ON l.id_lote = d.id_lote
                WHERE l.id_sku = :sku AND d.id_locacion = :loc
                  AND d.estado IN ('SUGERIDO', 'APROBADO')
                """,
                sku=id_sku,
                loc=id_locacion,
            )
            or {}
        ).get("total")
    )
    traslados_salientes = a_float(
        (
            one(
                """
                SELECT COALESCE(SUM(cantidad), 0) AS total
                FROM analitica.transferencia
                WHERE id_sku = :sku AND id_locacion_origen = :loc
                  AND estado IN ('SUGERIDA', 'APROBADA')
                """,
                sku=id_sku,
                loc=id_locacion,
            )
            or {}
        ).get("total")
    )

    necesidad_simple = round(
        demanda_horizonte + stock_seguridad - inventario_util - entradas, 2
    )
    vida_util = a_int(producto["vida_util_estandar"], 15)
    if fc.get("desviacion_std") is not None and fc["desviacion_std"] > 0:
        sigma_horizonte = max(float(fc["desviacion_std"]), demanda_horizonte * 0.10)
    else:
        sigma_diaria = _desviacion_diaria(id_sku, id_locacion, 28)
        sigma_horizonte = max(
            sigma_diaria * math.sqrt(max(1, horizonte)),
            demanda_horizonte * 0.10,
        )
    nv = optimizar_newsvendor(
        precio_venta=a_float(producto["precio_venta"]),
        precio_costo=a_float(producto["precio_costo"]),
        demanda_media=demanda_horizonte,
        desviacion_estandar=sigma_horizonte,
        vida_util_dias=vida_util,
        demanda_diaria=demanda_diaria,
        stock_util=inventario_util,
        entradas=entradas,
        stock_seguridad_simple=stock_seguridad,
    )
    # La necesidad neta recomendada usa la cantidad óptima Newsvendor
    necesidad = nv["cantidad_newsvendor"] if nv["cantidad_newsvendor"] > 0 else necesidad_simple

    moq = a_float(producto["moq"])
    advertencias: list[str] = []
    cantidad_sugerida = 0.0

    if nv["acotado_por_caducidad"]:
        advertencias.append(
            f"Restricción de caducidad Newsvendor: el nivel objetivo se acotó a {vida_util} días de vida útil para evitar merma futura."
        )

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

    if entradas_traslados > 0:
        advertencias.append(
            f"Triaje integrado: se descontaron {entradas_traslados:g} unidades en traslado entrante "
            f"desde otra tienda antes de calcular la compra."
        )

    if descuentos_activos > 0 or traslados_salientes > 0:
        acciones_prev: list[str] = []
        if descuentos_activos > 0:
            acciones_prev.append(f"{descuentos_activos:g} u. con descuento preventivo vigente")
        if traslados_salientes > 0:
            acciones_prev.append(f"{traslados_salientes:g} u. en traslado saliente")
        cobertura_util = (inventario_util / demanda_diaria) if demanda_diaria > 0 else 999.0
        if cantidad_sugerida > 0 and (demanda_diaria <= 0 or cobertura_util >= lead_time):
            cantidad_sugerida = 0.0
            advertencias.append(
                f"Compra detenida por triaje local ({' y '.join(acciones_prev)}): "
                f"la tienda cubre el tiempo de entrega mientras liquida o reubica su excedente."
            )
        else:
            advertencias.append(
                f"Triaje activo en esta tienda ({' y '.join(acciones_prev)}): "
                f"valida la reposición antes de autorizar la compra."
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
        "entradas_oc": round(entradas_oc, 2),
        "entradas_traslados": round(entradas_traslados, 2),
        "descuentos_activos": round(descuentos_activos, 2),
        "traslados_salientes": round(traslados_salientes, 2),
        "stock_seguridad": stock_seguridad,
        "necesidad_neta": necesidad,
        "necesidad_politica_simple": necesidad_simple,
        "desviacion_std": round(sigma_horizonte, 2),
        "cuantil_optimo": nv["stock_objetivo_newsvendor"],
        "modelo_aplicado": fc.get("modelo_aplicado"),
        "grupo_ab": fc.get("grupo_ab"),
        "newsvendor": nv,
        "cantidad_sugerida": round(cantidad_sugerida, 2),
        "prioridad": prioridad,
        "advertencias": advertencias,
        "lotes": lotes,
        "lotes_en_riesgo": [l for l in lotes if l["unidades_en_riesgo"] > 0],
    }


def explicar(analisis: dict) -> str:
    """Texto legible con el desglose completo de la recomendación y Newsvendor."""
    p = analisis["producto"]
    loc = analisis["locacion"]
    nv = analisis.get("newsvendor") or {}
    lineas = [
        f"Producto: {p['nombre']}",
        f"Tienda: {loc['nombre']}",
        "",
        f"Demanda prevista {analisis['horizonte']} días     {analisis['demanda_horizonte']:>10,.2f}",
        f"Inventario físico                  {analisis['inventario_fisico']:>10,.2f}",
        f"Inventario próximo a vencer        {analisis['inventario_riesgo']:>10,.2f}",
        f"Inventario útil                    {analisis['inventario_util']:>10,.2f}",
        f"Stock de seguridad                 {analisis['stock_seguridad']:>10,.2f}",
        f"Entradas confirmadas (total)       {analisis['entradas_confirmadas']:>10,.2f}",
        f"  · Órdenes en curso               {analisis.get('entradas_oc', analisis['entradas_confirmadas']):>10,.2f}",
        f"  · Traslados entrantes (triaje)   {analisis.get('entradas_traslados', 0.0):>10,.2f}",
        f"Lead time                          {analisis['lead_time_dias']:>10} días",
        f"MOQ                                {analisis['moq']:>10,.2f}",
        "",
        f"Necesidad neta (Newsvendor)        {analisis['necesidad_neta']:>10,.2f}",
    ]
    if nv:
        lineas.extend([
            "",
            "Modelo Newsvendor:",
            f"  Costo de faltante (Cu)           ${nv['costo_faltante']:>9,.2f}",
            f"  Costo de excedente (Co)          ${nv['costo_excedente']:>9,.2f}",
            f"  Fractil crítico Cu/(Cu+Co)       {nv['fractil_critico']:>10.4f}",
            f"  Cantidad óptima Newsvendor       {nv['cantidad_newsvendor']:>10,.2f}",
            f"  Política simple (referencia)     {nv['cantidad_politica_simple']:>10,.2f}",
            f"  Ahorro esperado en costo         ${nv['ahorro_esperado']:>9,.2f}",
        ])
    lineas.extend([
        "",
        f"Recomendación: ordenar {analisis['cantidad_sugerida']:,.0f} {p['unidad_medida']}"
        if analisis["cantidad_sugerida"] > 0
        else "Recomendación: no ordenar. El inventario útil cubre la demanda.",
    ])
    if analisis["advertencias"]:
        lineas.append("")
        lineas.append("Advertencias:")
        lineas.extend(f"  · {a}" for a in analisis["advertencias"])
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Generación de órdenes
# ---------------------------------------------------------------------------
def generar_recomendaciones(
    *,
    usuario: dict,
    horizonte: int | None = None,
    solo_con_necesidad: bool = True,
    id_locacion: int | None = None,
) -> dict:
    """
    Recorre todos los pares producto + tienda con historia y genera órdenes
    de reabastecimiento netas (descontando traslados entrantes de triaje).
    Evita duplicar órdenes que ya están pendientes.
    """
    from app.domain.ventas import pares_con_historia

    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)

    pares = pares_con_historia(min_dias=14)
    if id_locacion:
        pares = [p for p in pares if p["id_locacion"] == id_locacion]
    generadas = []
    actualizadas = 0
    revisadas = 0

    for par in pares:
        id_sku, id_loc = par["id_sku"], par["id_locacion"]
        pendiente = one(
            """
            SELECT id_orden::text, entradas_traslados, cantidad_sugerida
            FROM analitica.orden_reabastecimiento
            WHERE id_sku = :sku AND id_locacion = :loc AND estado = 'PENDIENTE'
            LIMIT 1
            """,
            sku=id_sku,
            loc=id_loc,
        )
        try:
            analisis = analizar_sku_locacion(
                id_sku,
                id_loc,
                horizonte,
                excluir_orden_id=pendiente["id_orden"] if pendiente else None,
            )
        except ValueError:
            continue
        revisadas += 1

        if pendiente:
            if abs(analisis["entradas_traslados"] - a_float(pendiente["entradas_traslados"])) > 1e-6:
                with transaccion(
                    id_usuario=usuario["id_usuario"], usuario_email=usuario["email"]
                ) as conn:
                    if analisis["cantidad_sugerida"] <= 0:
                        conn.execute(
                            text(
                                """
                                UPDATE analitica.orden_reabastecimiento
                                   SET estado = 'CANCELADA',
                                       entradas_confirmadas = :entradas,
                                       entradas_traslados = :traslados,
                                       necesidad_neta = :necesidad,
                                       cantidad_sugerida = 0,
                                       explicacion = :explicacion,
                                       advertencias = CAST(:advertencias AS jsonb),
                                       fecha_decision = now()
                                 WHERE id_orden = CAST(:id AS uuid)
                                """
                            ),
                            {
                                "entradas": analisis["entradas_confirmadas"],
                                "traslados": analisis["entradas_traslados"],
                                "necesidad": analisis["necesidad_neta"],
                                "explicacion": explicar(analisis),
                                "advertencias": _json(analisis["advertencias"]),
                                "id": pendiente["id_orden"],
                            },
                        )
                    else:
                        conn.execute(
                            text(
                                """
                                UPDATE analitica.orden_reabastecimiento
                                   SET id_run = (
                                           SELECT r.id_run FROM analitica.forecast_run r
                                           WHERE r.estado = 'COMPLETADO'
                                             AND (r.id_locacion = :loc OR r.id_locacion IS NULL)
                                           ORDER BY (CASE WHEN r.id_locacion = :loc THEN 0 ELSE 1 END),
                                                    r.fecha_ejecucion DESC
                                           LIMIT 1
                                       ),
                                       demanda_pronosticada = :demanda,
                                       inventario_fisico = :fisico,
                                       inventario_riesgo = :riesgo,
                                       inventario_util = :util,
                                       entradas_confirmadas = :entradas,
                                       entradas_traslados = :traslados,
                                       necesidad_neta = :necesidad,
                                       cantidad_sugerida = :sugerida,
                                       cantidad_newsvendor = :cant_nv,
                                       cantidad_politica_simple = :cant_simple,
                                       ahorro_esperado = :ahorro_esp,
                                       prioridad = :prioridad,
                                       explicacion = :explicacion,
                                       advertencias = CAST(:advertencias AS jsonb)
                                 WHERE id_orden = CAST(:id AS uuid)
                                """
                            ),
                            {
                                "loc": id_loc,
                                "demanda": analisis["demanda_horizonte"],
                                "fisico": analisis["inventario_fisico"],
                                "riesgo": analisis["inventario_riesgo"],
                                "util": analisis["inventario_util"],
                                "entradas": analisis["entradas_confirmadas"],
                                "traslados": analisis["entradas_traslados"],
                                "necesidad": analisis["necesidad_neta"],
                                "sugerida": analisis["cantidad_sugerida"],
                                "cant_nv": analisis["newsvendor"]["cantidad_newsvendor"],
                                "cant_simple": analisis["newsvendor"]["cantidad_politica_simple"],
                                "ahorro_esp": analisis["newsvendor"]["ahorro_esperado"],
                                "prioridad": analisis["prioridad"],
                                "explicacion": explicar(analisis),
                                "advertencias": _json(analisis["advertencias"]),
                                "id": pendiente["id_orden"],
                            },
                        )
                actualizadas += 1
            continue

        if solo_con_necesidad and analisis["cantidad_sugerida"] <= 0:
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
                         inventario_util, entradas_confirmadas, entradas_traslados,
                         stock_seguridad, lead_time_dias, moq,
                         necesidad_neta, cantidad_sugerida,
                         costo_faltante, costo_excedente, fractil_critico,
                         cantidad_newsvendor, cantidad_politica_simple, ahorro_esperado,
                         prioridad, estado,
                         explicacion, advertencias, id_usuario_solicita)
                    VALUES
                        (:sku, :loc, :prov,
                         (SELECT r.id_run FROM analitica.forecast_run r
                          WHERE r.estado = 'COMPLETADO'
                            AND (r.id_locacion = :loc OR r.id_locacion IS NULL)
                          ORDER BY (CASE WHEN r.id_locacion = :loc THEN 0 ELSE 1 END),
                                   r.fecha_ejecucion DESC
                          LIMIT 1),
                         :demanda, :fisico, :riesgo, :util, :entradas, :traslados,
                         :seguridad, :lead, :moq,
                         :necesidad, :sugerida,
                         :cu, :co, :fractil, :cant_nv, :cant_simple, :ahorro_esp,
                         :prioridad, 'PENDIENTE',
                         :explicacion, CAST(:advertencias AS jsonb), CAST(:uid AS uuid))
                    RETURNING id_orden::text
                    """
                ),
                {
                    "sku": id_sku,
                    "loc": id_loc,
                    "prov": analisis["producto"]["id_proveedor"],
                    "demanda": analisis["demanda_horizonte"],
                    "fisico": analisis["inventario_fisico"],
                    "riesgo": analisis["inventario_riesgo"],
                    "util": analisis["inventario_util"],
                    "entradas": analisis["entradas_confirmadas"],
                    "traslados": analisis["entradas_traslados"],
                    "seguridad": analisis["stock_seguridad"],
                    "lead": analisis["lead_time_dias"],
                    "moq": analisis["moq"],
                    "necesidad": analisis["necesidad_neta"],
                    "sugerida": analisis["cantidad_sugerida"],
                    "cu": analisis["newsvendor"]["costo_faltante"],
                    "co": analisis["newsvendor"]["costo_excedente"],
                    "fractil": analisis["newsvendor"]["fractil_critico"],
                    "cant_nv": analisis["newsvendor"]["cantidad_newsvendor"],
                    "cant_simple": analisis["newsvendor"]["cantidad_politica_simple"],
                    "ahorro_esp": analisis["newsvendor"]["ahorro_esperado"],
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

    return {
        "generadas": generadas,
        "actualizadas": actualizadas,
        "total": len(generadas),
        "revisadas": revisadas,
    }


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
               o.inventario_util, o.entradas_confirmadas, o.entradas_traslados, o.stock_seguridad,
               o.lead_time_dias, o.moq,
               o.necesidad_neta, o.cantidad_sugerida, o.cantidad_aprobada,
               o.costo_faltante, o.costo_excedente, o.fractil_critico,
               o.cantidad_newsvendor, o.cantidad_politica_simple, o.ahorro_esperado,
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


# ---------------------------------------------------------------------------
# Etapa 4: Pipeline desacoplado Pronóstico (μ, σ) → Inventario FEFO → Newsvendor
# ---------------------------------------------------------------------------
def pipeline_produccion_newsvendor_fefo(
    id_locacion: int | None = None,
    horizonte: int | None = None,
    limite: int = 120,
) -> dict:
    """
    Orquesta en solo lectura la vista integrada de Etapa 4:
      1. Tabla estándar del módulo Pronóstico: (fecha, tienda, producto, media, desviacion_std).
      2. Stock FEFO por fecha de caducidad desde `inventario.desglose_inventario_fefo`.
      3. Cruce Newsvendor FEFO: cuantil óptimo Q*, inventario útil descontando riesgo y orden sugerida.
    """
    from app.domain import inventario as dom_inv

    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)
    dias_ventana_riesgo = a_int(config_valor("dias_ventana_riesgo_lote", "5"), 5)

    tabla_fc = pronostico.tabla_pronostico_estandar(id_locacion=id_locacion, limite=limite)
    if not tabla_fc:
        return {
            "horizonte": horizonte,
            "resumen": {
                "total_series": 0,
                "con_orden_sugerida": 0,
                "unidades_sugeridas": 0.0,
                "inventario_en_riesgo": 0.0,
                "ahorro_esperado": 0.0,
            },
            "filas": [],
        }

    fefo_map = dom_inv.desglose_inventario_fefo(id_locacion=id_locacion)

    prods = query(
        """
        SELECT p.id_sku, p.precio_venta, p.precio_costo, p.vida_util_estandar,
               p.stock_seguridad, COALESCE(p.moq_lote, pr.moq, 1) AS moq,
               COALESCE(pr.lead_time_dias, 3) AS lead_time_dias
        FROM operacion.producto p
        LEFT JOIN operacion.proveedor pr ON pr.id_proveedor = p.id_proveedor
        WHERE p.activo = true
        """
    )
    prod_map = {p["id_sku"]: p for p in prods}

    entradas_rows = query(
        """
        SELECT id_sku, id_locacion,
               COALESCE(SUM(COALESCE(cantidad_aprobada, cantidad_sugerida)), 0) AS total
        FROM analitica.orden_reabastecimiento
        WHERE estado IN ('PENDIENTE', 'APROBADA')
        GROUP BY id_sku, id_locacion
        """
    )
    entradas_map = {
        (r["id_sku"], r["id_locacion"]): a_float(r["total"])
        for r in entradas_rows
    }

    filas_out: list[dict] = []
    con_orden = 0
    total_sugerido = 0.0
    total_riesgo = 0.0
    total_ahorro = 0.0

    for fc in tabla_fc:
        sku = fc["id_sku"]
        loc = fc["id_locacion"]
        p_info = prod_map.get(sku) or {}
        fefo = fefo_map.get((loc, sku)) or {
            "caduca_hoy": 0.0,
            "caduca_manana": 0.0,
            "caduca_2_dias": 0.0,
            "caduca_3_5_dias": 0.0,
            "caduca_mas_5_dias": 0.0,
            "stock_fisico": 0.0,
            "lotes": [],
        }

        demanda_diaria = a_float(fc["media_diaria"])
        media_h = a_float(fc["media_horizonte"])
        sigma_h = max(a_float(fc["desviacion_std_horizonte"]), media_h * 0.10)

        # Riesgo FEFO secuencial sobre lotes próximos a caducar dentro de la ventana
        vendido_acum = 0.0
        riesgo_fefo = 0.0
        for lote in fefo.get("lotes", []):
            d_rest = a_int(lote.get("dias_restantes"), 0)
            cant = a_float(lote.get("cantidad"))
            if d_rest < 0:
                riesgo_fefo += cant
            else:
                d_util = min(d_rest, dias_ventana_riesgo)
                dem_acum = demanda_diaria * d_util
                disponible_vender = max(0.0, dem_acum - vendido_acum)
                vendible = min(cant, disponible_vender)
                vendido_acum += vendible
                riesgo_fefo += max(0.0, cant - vendible)

        riesgo_fefo = round(riesgo_fefo, 2)
        stock_fisico = round(a_float(fefo["stock_fisico"]), 2)
        inv_util = round(max(0.0, stock_fisico - riesgo_fefo), 2)
        entradas = round(entradas_map.get((sku, loc), 0.0), 2)

        nv = optimizar_newsvendor(
            precio_venta=a_float(p_info.get("precio_venta")) or 20.0,
            precio_costo=a_float(p_info.get("precio_costo")) or 10.0,
            demanda_media=media_h,
            desviacion_estandar=sigma_h,
            vida_util_dias=a_int(p_info.get("vida_util_estandar"), 15),
            demanda_diaria=demanda_diaria,
            stock_util=inv_util,
            entradas=entradas,
            stock_seguridad_simple=a_float(p_info.get("stock_seguridad")),
        )
        necesidad = nv["cantidad_newsvendor"]
        moq = max(1.0, a_float(p_info.get("moq")) or 1.0)
        if necesidad <= 0:
            sugerida = 0.0
        elif necesidad < moq:
            sugerida = moq
        else:
            sugerida = round(necesidad)
            if moq > 1:
                mult = round(necesidad / moq)
                if mult * moq >= necesidad:
                    sugerida = mult * moq

        lead_time = a_int(p_info.get("lead_time_dias"), 3)
        cobertura = (inv_util / demanda_diaria) if demanda_diaria > 0 else 999.0
        prioridad = "BAJA"
        if sugerida > 0:
            if cobertura <= max(1, lead_time):
                prioridad = "ALTA"
            elif cobertura <= max(1, a_int(fc.get("horizonte_dias"), horizonte)):
                prioridad = "MEDIA"
            con_orden += 1
            total_sugerido += sugerida

        total_riesgo += riesgo_fefo
        total_ahorro += nv["ahorro_esperado"]

        filas_out.append(
            {
                "id_sku": sku,
                "producto": fc["producto"],
                "categoria": fc.get("categoria"),
                "unidad_medida": fc["unidad_medida"],
                "id_locacion": loc,
                "locacion": fc["locacion"],
                "desde": fc["desde"],
                "hasta": fc["hasta"],
                "modelo_aplicado": fc.get("modelo_aplicado"),
                "grupo_ab": fc.get("grupo_ab"),
                "media": media_h,
                "media_diaria": demanda_diaria,
                "desviacion_std": round(sigma_h, 2),
                "fractil_critico": nv["fractil_critico"],
                "cuantil_optimo": nv["stock_objetivo_newsvendor"],
                "caduca_hoy": fefo["caduca_hoy"],
                "caduca_manana": fefo["caduca_manana"],
                "caduca_2_dias": fefo["caduca_2_dias"],
                "caduca_3_5_dias": fefo["caduca_3_5_dias"],
                "caduca_mas_5_dias": fefo["caduca_mas_5_dias"],
                "stock_fisico": stock_fisico,
                "inventario_riesgo": riesgo_fefo,
                "inventario_util": inv_util,
                "entradas_confirmadas": entradas,
                "orden_sugerida": round(sugerida, 2),
                "prioridad": prioridad,
                "ahorro_esperado": nv["ahorro_esperado"],
            }
        )

    filas_out.sort(
        key=lambda x: (
            0 if x["prioridad"] == "ALTA" else (1 if x["prioridad"] == "MEDIA" else 2),
            -x["orden_sugerida"],
            x["locacion"],
            x["producto"],
        )
    )

    return {
        "horizonte": horizonte,
        "resumen": {
            "total_series": len(filas_out),
            "con_orden_sugerida": con_orden,
            "unidades_sugeridas": round(total_sugerido, 2),
            "inventario_en_riesgo": round(total_riesgo, 2),
            "ahorro_esperado": round(total_ahorro, 2),
        },
        "filas": filas_out,
    }


def ejecutar_pipeline_produccion(
    *,
    usuario: dict,
    id_locacion: int | None = None,
    horizonte: int | None = None,
) -> dict:
    """
    Ejecuta en cadena el pipeline completo de Producción:
      1. Inferencia por tienda respetando Campeón vigente o experimento A/B activo.
      2. Si hay A/B Test activo, consolida la bitácora contra ventas/mermas reales.
      3. Cruza distribución (media, sigma) contra inventario FEFO → órdenes Newsvendor.
    """
    from app.domain import experimentos_ab as dom_ab

    if horizonte is None:
        horizonte = a_int(config_valor("horizonte_pronostico_dias", "7"), 7)

    if id_locacion:
        locaciones = [{"id_locacion": id_locacion}]
    else:
        locaciones = query(
            """
            SELECT DISTINCT v.id_locacion
            FROM analitica.v_demanda_diaria v
            JOIN operacion.locacion l ON l.id_locacion = v.id_locacion
            WHERE l.activo = true
            ORDER BY v.id_locacion
            """
        )

    tiendas_inferidas = 0
    series_inferidas = 0
    for t in locaciones:
        loc_id = t["id_locacion"]
        cfg = dom_ab.modelo_activo_para_tienda(loc_id)
        res_t = pronostico._ejecutar_pronostico_tienda(
            usuario=usuario,
            id_locacion=loc_id,
            metodo=cfg["metodo"],
            horizonte=horizonte,
            proposito=cfg["proposito"],
            id_experimento=cfg["id_experimento"],
            grupo_ab=cfg["grupo_ab"],
        )
        if res_t.get("id_run"):
            tiendas_inferidas += 1
            series_inferidas += res_t.get("series", 0)

    exp_activo = dom_ab.obtener_experimento_activo()
    if exp_activo:
        try:
            dom_ab.consolidar_experimento_ab(exp_activo["id_experimento"], usuario=usuario)
        except Exception:
            pass

    res_reab = generar_recomendaciones(
        usuario=usuario,
        horizonte=horizonte,
        id_locacion=id_locacion,
    )

    return {
        "horizonte": horizonte,
        "tiendas_inferidas": tiendas_inferidas,
        "series_inferidas": series_inferidas,
        "ordenes_generadas": res_reab["total"],
        "ordenes_actualizadas": res_reab["actualizadas"],
        "revisadas": res_reab["revisadas"],
        "experimento_activo": exp_activo["nombre"] if exp_activo else None,
    }
