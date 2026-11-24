package mx.freshtrack.mobile.data.repo

import android.os.Build
import mx.freshtrack.mobile.BuildConfig
import mx.freshtrack.mobile.data.api.ApiClient
import mx.freshtrack.mobile.data.model.*
import mx.freshtrack.mobile.data.offline.OfflineQueue
import mx.freshtrack.mobile.data.offline.SendOutcome
import mx.freshtrack.mobile.session.SessionManager
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.util.UUID

/** Único punto de acceso a los microservicios desde los ViewModels. */
class FreshTrackRepository(
    private val client: ApiClient,
    private val session: SessionManager,
    val offlineQueue: OfflineQueue,
    private val onQueued: () -> Unit = {},
) {

    private val api get() = client.api
    private val store get() = session.storeId

    // ---------------- auth
    suspend fun login(email: String, password: String): ApiResult<LoginResponse> {
        val r = safeCall { api.login(LoginRequest(email.trim(), password)) }
        if (r is ApiResult.Ok) {
            session.save(r.data)
            // Registro seguro del dispositivo: si el administrador lo revocó, no se entra.
            val d = registerDevice()
            if (d is ApiResult.Fail && d.error.code == "dispositivo_revocado") {
                safeCall { api.logout() }
                session.clear()
                return ApiResult.Fail(
                    d.error.copy(message = "Este dispositivo fue revocado por un administrador. Pide que lo habiliten de nuevo.")
                )
            }
            // Lo que este usuario dejó pendiente sin conexión se envía en cuanto haya red.
            if (offlineQueue.pendingFor(r.data.usuario.idUsuario).isNotEmpty()) onQueued()
        }
        return r
    }

    /**
     * POST /auth/devices con el UUID del teléfono, modelo y versiones. Cualquier otro
     * fallo (sin red, backend anterior sin el endpoint) no impide trabajar.
     */
    suspend fun registerDevice(): ApiResult<DispositivoResponse> = safeCall {
        api.registerDevice(
            DispositivoRequest(
                idDispositivo = session.deviceId,
                modelo = "${Build.MANUFACTURER} ${Build.MODEL}".trim().take(120),
                versionSo = "${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})",
                versionApp = BuildConfig.VERSION_NAME,
            )
        )
    }

    /** Revoca el jti en el backend (denylist Redis + PostgreSQL) y limpia la sesión local siempre. */
    suspend fun logout(): ApiResult<LogoutResponse> {
        val r = safeCall { api.logout() }
        session.clear()
        return r
    }

    suspend fun me() = safeCall { api.me() }

    /** Renovación manual (botón en Más): rota el token aunque no esté por vencer. */
    suspend fun refreshSession(): Boolean = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
        client.refresher.refreshIfNeeded(force = true)
    }

    val lastRotation get() = client.refresher.lastRotation

    // ---------------- catálogo
    suspend fun locations() = safeCall { api.locations() }
    suspend fun searchProducts(q: String?) = safeCall { api.products(q?.takeIf { it.isNotBlank() }) }

    // ---------------- inventario
    suspend fun stock(diasMax: Int? = null, idSku: Int? = null) =
        safeCall { api.stock(store, idSku, diasMax) }

    suspend fun fefo(idSku: Int, idLocacion: Int = store ?: 0) = safeCall { api.fefoQueue(idSku, idLocacion) }

    suspend fun label(code: String) = safeCall { api.label(code, store) }

    suspend fun receive(req: ReceiveScanRequest, idempotencyKey: String) =
        safeCall { api.receiveScan(idempotencyKey, req) }

    suspend fun changeBatchStatus(idLote: String, estado: String, motivo: String?) =
        safeCall { api.batchStatus(idLote, BatchStatusRequest(estado, motivo, store)) }

    fun countRequest(idSku: Int?, lineas: List<ConteoLinea>, observacion: String?) =
        ConteoRequest(store ?: 0, idSku, lineas, observacion)

    suspend fun cycleCount(req: ConteoRequest, idempotencyKey: String) =
        safeCall { api.cycleCount(idempotencyKey, req) }

    // ---------------- comercial
    fun shrinkageRequest(idLote: String, cantidad: Double, causa: String, obs: String?, idEvidencia: String?) =
        MermaRequest(idLote, store ?: 0, cantidad, causa, obs, idEvidencia)

    suspend fun shrinkage(req: MermaRequest, idempotencyKey: String) =
        safeCall { api.shrinkage(idempotencyKey, req) }

    // ---------------- trabajo sin conexión
    /** Guarda la operación para la sincronización posterior y programa el envío al volver la red. */
    fun saveOffline(type: OfflineQueue.Type, payload: Any, idempotencyKey: String, summary: String) {
        offlineQueue.enqueue(type, payload, idempotencyKey, session.user?.idUsuario, summary)
        onQueued()
    }

    /** Reenvía una operación guardada con su Idempotency-Key original. */
    suspend fun replay(op: OfflineQueue.PendingOp): SendOutcome {
        val r: ApiResult<*> = when (op.type) {
            OfflineQueue.Type.MERMA -> shrinkage(client.gson.fromJson(op.payloadJson, MermaRequest::class.java), op.id)
            OfflineQueue.Type.CONTEO -> cycleCount(client.gson.fromJson(op.payloadJson, ConteoRequest::class.java), op.id)
        }
        return when (r) {
            is ApiResult.Ok -> SendOutcome.Sent
            is ApiResult.Fail -> SendOutcome.from(r.error)
        }
    }

    suspend fun uploadEvidence(
        file: File, tipo: String, refTipo: String?, refId: String?, descripcion: String?,
    ): ApiResult<Evidencia> {
        val text = "text/plain".toMediaType()
        val part = MultipartBody.Part.createFormData(
            "archivo", file.name, file.asRequestBody("image/jpeg".toMediaType())
        )
        return safeCall {
            api.uploadEvidence(
                part,
                tipo.toRequestBody(text),
                refTipo?.toRequestBody(text),
                refId?.toRequestBody(text),
                descripcion?.toRequestBody(text),
                store?.toString()?.toRequestBody(text),
            )
        }
    }

    suspend fun evidences() = safeCall { api.evidences(store) }
    suspend fun evidenceUrl(id: String) = safeCall { api.evidenceUrl(id) }

    // ---------------- transferencias
    suspend fun transfers(estado: String?) = safeCall { api.transfers(estado) }
    suspend fun requestTransfer(idLote: String, destino: Int, cantidad: Double, motivo: String?) =
        safeCall { api.requestTransfer(SolicitudTransferenciaRequest(idLote, store ?: 0, destino, cantidad, motivo)) }
    suspend fun detectTransfers(horizonte: Int = 7) = safeCall { api.detectTransfers(HorizonteBody(horizonte)) }
    suspend fun approveTransfer(id: String, cantidad: Double?) = safeCall { api.approveTransfer(id, CantidadBody(cantidad)) }
    suspend fun rejectTransfer(id: String) = safeCall { api.rejectTransfer(id) }
    suspend fun executeTransfer(id: String) = safeCall { api.executeTransfer(id) }

    // ---------------- descuentos
    suspend fun discounts(estado: String?) = safeCall { api.discounts(estado) }
    suspend fun generateDiscounts(diasHasta: Int = 5) = safeCall { api.generateDiscounts(DiasHastaBody(diasHasta)) }
    suspend fun approveDiscount(id: String) = safeCall { api.approveDiscount(id) }
    suspend fun rejectDiscount(id: String) = safeCall { api.rejectDiscount(id) }

    // ---------------- alertas
    suspend fun alerts(criticidad: String? = null) = safeCall { api.activeAlerts(store, criticidad) }
    suspend fun scanAlerts(dias: Int = 3) = safeCall { api.scanAlerts(store, dias) }
    suspend fun resolveAlert(id: String) = safeCall { api.resolveAlert(id) }
    suspend fun esg() = safeCall { api.esg() }

    fun newIdempotencyKey(): String = UUID.randomUUID().toString()
}
