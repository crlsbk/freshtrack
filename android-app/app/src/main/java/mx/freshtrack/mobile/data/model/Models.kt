package mx.freshtrack.mobile.data.model

import com.google.gson.annotations.SerializedName

/*
 * Contratos JSON de los microservicios FreshTrack (vía API Gateway Caddy).
 * Los nombres de campo replican exactamente las respuestas reales de los servicios.
 * Todos los campos numéricos que el backend puede omitir son anulables.
 */

// ---------------------------------------------------------------- svc-auth
data class LoginRequest(val email: String, val password: String)

data class Usuario(
    @SerializedName("id_usuario") val idUsuario: String,
    val email: String,
    val nombre: String?,
    val rol: String,
    @SerializedName("id_locacion") val idLocacion: Int?,
)

data class LoginResponse(
    val token: String,
    val jti: String,
    @SerializedName("token_type") val tokenType: String?,
    @SerializedName("expira_en_segundos") val expiraEnSegundos: Long?,
    /** Refresh token opaco (256 bits); cada uso lo rota. Ausente en servidores antiguos. */
    @SerializedName("refresh_token") val refreshToken: String? = null,
    /** Fin ABSOLUTO de la sesión: rotar no lo extiende. */
    @SerializedName("refresh_expira_en_segundos") val refreshExpiraEnSegundos: Long? = null,
    val usuario: Usuario,
)

data class LogoutResponse(val status: String?, val jti: String?)

data class ApiErrorBody(
    val error: String?,
    val mensaje: String?,
    val status: Int?,
    @SerializedName("correlation_id") val correlationId: String?,
)

// ---------------------------------------------------------------- comunes
data class Paginacion(
    val pagina: Int,
    @SerializedName("por_pagina") val porPagina: Int,
    val total: Int,
    @SerializedName("total_paginas") val totalPaginas: Int,
)

// ---------------------------------------------------------------- svc-catalog
data class Locacion(
    @SerializedName("id_locacion") val idLocacion: Int,
    @SerializedName("tipo_locacion") val tipo: String?,
    val nombre: String,
    val ciudad: String?,
    val activo: Boolean?,
)

data class LocacionesResponse(val total: Int?, val locaciones: List<Locacion>)

data class Producto(
    @SerializedName("id_sku") val idSku: Int,
    @SerializedName("codigo_gtin") val codigoGtin: String?,
    val nombre: String,
    val categoria: String?,
    @SerializedName("unidad_medida") val unidadMedida: String?,
    @SerializedName("vida_util_estandar") val vidaUtil: Int?,
    @SerializedName("precio_venta") val precioVenta: Double?,
    @SerializedName("precio_costo") val precioCosto: Double?,
)

data class ProductosResponse(val paginacion: Paginacion?, val productos: List<Producto>)

// ---------------------------------------------------------------- svc-inventory
data class Existencia(
    @SerializedName("id_existencia") val idExistencia: String,
    @SerializedName("id_locacion") val idLocacion: Int,
    val locacion: String?,
    @SerializedName("id_lote") val idLote: String,
    @SerializedName("id_sku") val idSku: Int,
    val producto: String,
    @SerializedName("codigo_lote_prov") val codigoLote: String?,
    @SerializedName("estado_lote") val estadoLote: String?,
    @SerializedName("fecha_caducidad") val fechaCaducidad: String?,
    @SerializedName("dias_restantes") val diasRestantes: Int?,
    @SerializedName("cantidad_disponible") val disponible: Double,
    @SerializedName("cantidad_reservada") val reservada: Double?,
    @SerializedName("disponible_neto") val disponibleNeto: Double?,
)

data class StockResponse(val paginacion: Paginacion?, val existencias: List<Existencia>)

data class LoteFefo(
    @SerializedName("id_existencia") val idExistencia: String?,
    @SerializedName("id_lote") val idLote: String,
    @SerializedName("codigo_lote_prov") val codigoLote: String?,
    val estado: String?,
    @SerializedName("cantidad_disponible") val disponible: Double,
    @SerializedName("cantidad_reservada") val reservada: Double?,
    @SerializedName("fecha_caducidad") val fechaCaducidad: String?,
    @SerializedName("dias_restantes") val diasRestantes: Int?,
    @SerializedName("costo_unitario") val costoUnitario: Double?,
)

data class FefoResponse(
    @SerializedName("id_sku") val idSku: Int,
    @SerializedName("id_locacion") val idLocacion: Int,
    @SerializedName("total_lotes") val totalLotes: Int,
    @SerializedName("lotes_fefo") val lotes: List<LoteFefo>,
)

/** Respuesta de GET /api/v1/asn/labels?codigo=... (vista previa antes de recibir). */
data class EtiquetaInfo(
    @SerializedName("codigo_etiqueta") val codigoEtiqueta: String,
    @SerializedName("firma_valida") val firmaValida: Boolean?,
    @SerializedName("folio_asn") val folioAsn: String?,
    @SerializedName("folio_oc") val folioOc: String?,
    val proveedor: String?,
    @SerializedName("id_sku") val idSku: Int,
    val producto: String?,
    @SerializedName("codigo_gtin") val codigoGtin: String?,
    @SerializedName("unidad_medida") val unidadMedida: String?,
    @SerializedName("id_locacion_destino") val idLocacionDestino: Int?,
    @SerializedName("locacion_destino") val locacionDestino: String?,
    @SerializedName("lote_proveedor") val loteProveedor: String?,
    @SerializedName("fecha_produccion") val fechaProduccion: String?,
    @SerializedName("fecha_caducidad") val fechaCaducidad: String?,
    @SerializedName("cantidad_declarada") val cantidadDeclarada: Double?,
    @SerializedName("rango_temperatura_controlada") val rangoTemperatura: String?,
    @SerializedName("dias_restantes") val diasRestantes: Int?,
    @SerializedName("vida_util_pct") val vidaUtilPct: Double?,
    @SerializedName("alerta_vida_util_baja") val alertaVidaUtilBaja: Boolean?,
    @SerializedName("alerta_destino_incorrecto") val alertaDestinoIncorrecto: Boolean?,
    @SerializedName("ya_recibida") val yaRecibida: Boolean?,
)

data class ReceiveScanRequest(
    @SerializedName("codigo_qr_crudo") val codigoQrCrudo: String,
    @SerializedName("id_locacion_recepcion") val idLocacion: Int,
    @SerializedName("cantidad_recibida") val cantidadRecibida: Double,
    @SerializedName("fecha_caducidad_verificada") val fechaCaducidadVerificada: String?,
    @SerializedName("temperatura_registrada_c") val temperatura: Double?,
    @SerializedName("resultado_inspeccion") val resultadoInspeccion: String,
    @SerializedName("accion_calidad") val accionCalidad: String,
    @SerializedName("medio_lectura") val medioLectura: String = "QR",
    val observaciones: String?,
)

data class ReceiveScanResponse(
    @SerializedName("codigo_etiqueta") val codigoEtiqueta: String?,
    @SerializedName("folio_asn") val folioAsn: String?,
    @SerializedName("folio_oc") val folioOc: String?,
    @SerializedName("id_lote") val idLote: String?,
    val producto: String?,
    @SerializedName("unidad_medida") val unidadMedida: String?,
    @SerializedName("cantidad_esperada") val esperada: Double?,
    @SerializedName("cantidad_recibida") val recibida: Double?,
    @SerializedName("accion_calidad") val accionCalidad: String?,
    @SerializedName("elegible_fefo") val elegibleFefo: Boolean?,
    @SerializedName("estado_orden_compra") val estadoOc: String?,
    val idempotente: Boolean?,
)

data class BatchStatusRequest(val estado: String, val motivo: String?, @SerializedName("id_locacion") val idLocacion: Int?)
data class BatchStatusResponse(
    @SerializedName("id_lote") val idLote: String?,
    @SerializedName("estado_anterior") val estadoAnterior: String?,
    val estado: String?,
    @SerializedName("elegible_fefo") val elegibleFefo: Boolean?,
)

/** Conteo cíclico: POST /api/v1/inventory/counts */
data class ConteoLinea(
    @SerializedName("id_lote") val idLote: String,
    @SerializedName("cantidad_contada") val cantidadContada: Double,
)

data class ConteoRequest(
    @SerializedName("id_locacion") val idLocacion: Int,
    @SerializedName("id_sku") val idSku: Int?,
    val lineas: List<ConteoLinea>,
    val observacion: String?,
)

data class ConteoAjuste(
    @SerializedName("id_lote") val idLote: String,
    @SerializedName("codigo_lote_prov") val codigoLote: String?,
    val sistema: Double,
    val contado: Double,
    val diferencia: Double,
)

data class ConteoResponse(
    @SerializedName("id_conteo") val idConteo: String?,
    @SerializedName("lineas_contadas") val lineasContadas: Int?,
    @SerializedName("lineas_con_diferencia") val lineasConDiferencia: Int?,
    @SerializedName("exactitud_pct") val exactitudPct: Double?,
    val ajustes: List<ConteoAjuste>?,
)

// ---------------------------------------------------------------- svc-commercial
data class MermaRequest(
    @SerializedName("id_lote") val idLote: String,
    @SerializedName("id_locacion") val idLocacion: Int,
    val cantidad: Double,
    val causa: String,
    val observacion: String?,
    @SerializedName("id_evidencia") val idEvidencia: String? = null,
)

data class MermaResponse(
    @SerializedName("id_merma") val idMerma: String?,
    val cantidad: Double?,
    val causa: String?,
    @SerializedName("causa_etiqueta") val causaEtiqueta: String?,
    @SerializedName("valor_merma") val valorMerma: Double?,
    val producto: String?,
    @SerializedName("codigo_lote_prov") val codigoLote: String?,
    @SerializedName("existencia_restante") val existenciaRestante: Double?,
    @SerializedName("unidad_medida") val unidadMedida: String?,
)

data class Evidencia(
    @SerializedName("id_evidencia") val idEvidencia: String,
    val tipo: String?,
    @SerializedName("referencia_tipo") val referenciaTipo: String?,
    @SerializedName("referencia_id") val referenciaId: String?,
    @SerializedName("content_type") val contentType: String?,
    @SerializedName("tamano_bytes") val tamanoBytes: Long?,
    val sha256: String?,
    val bucket: String?,
    @SerializedName("object_key") val objectKey: String?,
    @SerializedName("url_firmada") val urlFirmada: String?,
    @SerializedName("url_expira_en_segundos") val urlExpiraEn: Int?,
    @SerializedName("creado_en") val creadoEn: String?,
    val descripcion: String?,
)

data class EvidenciasResponse(val total: Int?, val evidencias: List<Evidencia>)

// ---------------------------------------------------------------- svc-planning
data class Transferencia(
    @SerializedName("id_transferencia") val id: String,
    val estado: String,
    val cantidad: Double?,
    val motivo: String?,
    @SerializedName("dias_para_vencer") val diasParaVencer: Int?,
    @SerializedName("fecha_creacion") val fechaCreacion: String?,
    val producto: String?,
    @SerializedName("id_sku") val idSku: Int?,
    @SerializedName("unidad_medida") val unidadMedida: String?,
    val origen: String?,
    @SerializedName("id_origen") val idOrigen: Int?,
    val destino: String?,
    @SerializedName("id_destino") val idDestino: Int?,
    val solicita: String?,
    val aprueba: String?,
)

data class ResumenTransferencias(
    val sugeridas: Int?, val aprobadas: Int?, val ejecutadas: Int?, val rechazadas: Int?,
    @SerializedName("unidades_movidas") val unidadesMovidas: Double?,
)

data class TransferenciasResponse(
    val total: Int?,
    val resumen: ResumenTransferencias?,
    val transferencias: List<Transferencia>,
)

data class SolicitudTransferenciaRequest(
    @SerializedName("id_lote") val idLote: String,
    @SerializedName("id_locacion_origen") val idOrigen: Int,
    @SerializedName("id_locacion_destino") val idDestino: Int,
    val cantidad: Double,
    val motivo: String?,
)

data class CantidadBody(val cantidad: Double?)
data class HorizonteBody(val horizonte: Int)
data class DiasHastaBody(@SerializedName("dias_hasta") val diasHasta: Int)

data class Descuento(
    @SerializedName("id_descuento") val id: String,
    val estado: String,
    @SerializedName("descuento_pct") val descuentoPct: Double?,
    @SerializedName("precio_normal") val precioNormal: Double?,
    @SerializedName("precio_nuevo") val precioNuevo: Double?,
    val cantidad: Double?,
    @SerializedName("dias_restantes") val diasRestantes: Int?,
    @SerializedName("ingreso_potencial") val ingresoPotencial: Double?,
    val producto: String?,
    @SerializedName("unidad_medida") val unidadMedida: String?,
    val locacion: String?,
    @SerializedName("id_locacion") val idLocacion: Int?,
    @SerializedName("codigo_lote_prov") val codigoLote: String?,
    val aprueba: String?,
)

data class ResumenDescuentos(
    val sugeridos: Int?, val aprobados: Int?, val rechazados: Int?,
    @SerializedName("ingreso_potencial") val ingresoPotencial: Double?,
    val unidades: Double?,
)

data class DescuentosResponse(val total: Int?, val resumen: ResumenDescuentos?, val descuentos: List<Descuento>)

/** Respuestas de decisiones/ejecuciones: se muestran de forma genérica. */
typealias Decision = Map<String, Any?>

// ---------------------------------------------------------------- svc-alerts
data class Alerta(
    @SerializedName(value = "id_mongo", alternate = ["_id", "id"]) val id: String?,
    val tipo: String?,
    val criticidad: String?,
    val mensaje: String?,
    @SerializedName("id_sku") val idSku: Int?,
    @SerializedName("id_locacion") val idLocacion: Int?,
    @SerializedName(value = "generada_en", alternate = ["creada_en"]) val creadaEn: String?,
    val contexto: Map<String, Any?>?,
)

data class AlertasResponse(val total: Int, val alertas: List<Alerta>)

data class ScanAlertasResponse(
    val status: String?,
    @SerializedName("ventana_dias") val ventanaDias: Int?,
    @SerializedName("total_escaneados") val totalEscaneados: Int?,
    @SerializedName("alertas_emitidas") val alertasEmitidas: Int?,
)

data class EsgResponse(
    @SerializedName("alimento_recuperado_kg") val recuperadoKg: Double?,
    @SerializedName("desperdicio_evitado_neto_kg") val evitadoNetoKg: Double?,
    @SerializedName("ahorro_financiero_mxn") val ahorroMxn: Double?,
    @SerializedName("co2e_evitado_kg") val co2eKg: Double?,
    val fuente: String?,
)

// ---------------------------------------------------------------- monitoreo
data class HealthResponse(
    val status: String?,
    val service: String?,
    val version: String?,
    val dependencies: Map<String, Any?>?,
)
