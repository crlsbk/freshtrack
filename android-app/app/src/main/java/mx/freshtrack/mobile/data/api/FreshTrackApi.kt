package mx.freshtrack.mobile.data.api

import mx.freshtrack.mobile.data.model.*
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.*

/**
 * Contrato Retrofit contra el API Gateway (Caddy) que enruta por prefijo:
 *   /api/v1/auth*       → svc-auth       (5001)
 *   /api/v1/catalog*    → svc-catalog    (5002)
 *   /api/v1/inventory*  → svc-inventory  (5003)
 *   /api/v1/commercial* → svc-commercial (5004)
 *   /api/v1/asn*        → svc-asn        (5005)
 *   /api/v1/planning*   → svc-planning   (5006)
 *   /api/v1/alerts*     → svc-alerts     (5007)
 *   /api/v1/audit*      → svc-audit      (5008)
 */
interface FreshTrackApi {

    // ---------- svc-auth
    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): Response<LoginResponse>

    @POST("api/v1/auth/refresh")
    suspend fun refresh(@Body body: Map<String, String> = emptyMap()): Response<LoginResponse>

    @POST("api/v1/auth/logout")
    suspend fun logout(): Response<LogoutResponse>

    @GET("api/v1/auth/me")
    suspend fun me(): Response<Usuario>

    // ---------- svc-catalog
    @GET("api/v1/catalog/locations")
    suspend fun locations(): Response<LocacionesResponse>

    @GET("api/v1/catalog/products")
    suspend fun products(
        @Query("q") q: String? = null,
        @Query("por_pagina") porPagina: Int = 50,
    ): Response<ProductosResponse>

    // ---------- svc-inventory
    @GET("api/v1/inventory/stock")
    suspend fun stock(
        @Query("id_locacion") idLocacion: Int?,
        @Query("id_sku") idSku: Int? = null,
        @Query("dias_max") diasMax: Int? = null,
        @Query("pagina") pagina: Int = 1,
        @Query("por_pagina") porPagina: Int = 100,
    ): Response<StockResponse>

    @GET("api/v1/inventory/fefo-queue/{sku}/{loc}")
    suspend fun fefoQueue(@Path("sku") idSku: Int, @Path("loc") idLocacion: Int): Response<FefoResponse>

    @POST("api/v1/inventory/receive-scan")
    suspend fun receiveScan(
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body body: ReceiveScanRequest,
    ): Response<ReceiveScanResponse>

    @PATCH("api/v1/inventory/batches/{id}/status")
    suspend fun batchStatus(@Path("id") idLote: String, @Body body: BatchStatusRequest): Response<BatchStatusResponse>

    @POST("api/v1/inventory/counts")
    suspend fun cycleCount(
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body body: ConteoRequest,
    ): Response<ConteoResponse>

    // ---------- svc-asn (vista previa de etiqueta QR antes de recibir)
    @GET("api/v1/asn/labels")
    suspend fun label(@Query("codigo") codigo: String, @Query("id_locacion") idLocacion: Int?): Response<EtiquetaInfo>

    // ---------- svc-commercial
    @POST("api/v1/commercial/shrinkage")
    suspend fun shrinkage(@Body body: MermaRequest): Response<MermaResponse>

    @Multipart
    @POST("api/v1/commercial/evidence")
    suspend fun uploadEvidence(
        @Part archivo: MultipartBody.Part,
        @Part("tipo") tipo: RequestBody,
        @Part("referencia_tipo") referenciaTipo: RequestBody?,
        @Part("referencia_id") referenciaId: RequestBody?,
        @Part("descripcion") descripcion: RequestBody?,
        @Part("id_locacion") idLocacion: RequestBody?,
    ): Response<Evidencia>

    @GET("api/v1/commercial/evidence")
    suspend fun evidences(@Query("id_locacion") idLocacion: Int?, @Query("limite") limite: Int = 50): Response<EvidenciasResponse>

    @GET("api/v1/commercial/evidence/{id}/url")
    suspend fun evidenceUrl(@Path("id") id: String): Response<Evidencia>

    // ---------- svc-planning: transferencias
    @GET("api/v1/planning/transfers")
    suspend fun transfers(@Query("estado") estado: String?, @Query("limite") limite: Int = 100): Response<TransferenciasResponse>

    @POST("api/v1/planning/transfers")
    suspend fun requestTransfer(@Body body: SolicitudTransferenciaRequest): Response<Map<String, Any?>>

    @POST("api/v1/planning/transfers/detect")
    suspend fun detectTransfers(@Body body: HorizonteBody): Response<Map<String, Any?>>

    @POST("api/v1/planning/transfers/{id}/approve")
    suspend fun approveTransfer(@Path("id") id: String, @Body body: CantidadBody): Response<Map<String, Any?>>

    @POST("api/v1/planning/transfers/{id}/reject")
    suspend fun rejectTransfer(@Path("id") id: String, @Body body: Map<String, String> = emptyMap()): Response<Map<String, Any?>>

    @POST("api/v1/planning/transfers/{id}/execute")
    suspend fun executeTransfer(@Path("id") id: String, @Body body: Map<String, String> = emptyMap()): Response<Map<String, Any?>>

    // ---------- svc-planning: descuentos por vencimiento
    @GET("api/v1/planning/discounts")
    suspend fun discounts(@Query("estado") estado: String?, @Query("limite") limite: Int = 100): Response<DescuentosResponse>

    @POST("api/v1/planning/discounts/generate")
    suspend fun generateDiscounts(@Body body: DiasHastaBody): Response<Map<String, Any?>>

    @POST("api/v1/planning/discounts/{id}/approve")
    suspend fun approveDiscount(@Path("id") id: String, @Body body: Map<String, String> = emptyMap()): Response<Map<String, Any?>>

    @POST("api/v1/planning/discounts/{id}/reject")
    suspend fun rejectDiscount(@Path("id") id: String, @Body body: Map<String, String> = emptyMap()): Response<Map<String, Any?>>

    // ---------- svc-alerts
    @GET("api/v1/alerts/active")
    suspend fun activeAlerts(
        @Query("id_locacion") idLocacion: Int?,
        @Query("criticidad") criticidad: String? = null,
        @Query("limite") limite: Int = 100,
    ): Response<AlertasResponse>

    @POST("api/v1/alerts/scan")
    suspend fun scanAlerts(@Query("id_locacion") idLocacion: Int?, @Query("dias") dias: Int = 3): Response<ScanAlertasResponse>

    @PATCH("api/v1/alerts/{id}/resolve")
    suspend fun resolveAlert(@Path("id") id: String): Response<Map<String, Any?>>

    @GET("api/v1/alerts/esg/carbon-avoided")
    suspend fun esg(): Response<EsgResponse>

    // ---------- monitoreo: se usa @Url para sondear cualquier ruta del gateway
    @GET
    suspend fun probe(@Url url: String): Response<ResponseBody>
}
