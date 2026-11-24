package mx.freshtrack.mobile.data.offline

import com.google.gson.Gson
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import mx.freshtrack.mobile.data.repo.AppError

/**
 * Trabajo temporal sin conexión: mermas y conteos que no se pudieron enviar por falta de red.
 *
 * Cada operación guarda el cuerpo JSON ya armado y la Idempotency-Key generada AL CAPTURAR,
 * así que reenviarla nunca duplica inventario (el backend devuelve lo ya registrado).
 * La lógica es JVM pura (probada en OfflineQueueTest); dónde y cómo se guarda lo decide
 * [QueueStore] (en el teléfono: archivo privado de la app cifrado con la llave del Keystore).
 */
class OfflineQueue(private val store: QueueStore, private val gson: Gson = Gson(), private val now: () -> Long = System::currentTimeMillis) {

    enum class Type { MERMA, CONTEO }

    data class PendingOp(
        val id: String,                 // = Idempotency-Key
        val type: Type,
        val payloadJson: String,
        val userId: String?,
        val summary: String,
        val createdAt: Long,
        val attempts: Int = 0,
        val lastError: String? = null,
    )

    /** Operación descartada por un error que no se arregla reintentando (se le muestra al usuario). */
    data class FailedOp(val op: PendingOp, val message: String, val failedAt: Long)

    private data class State(val pending: List<PendingOp> = emptyList(), val failed: List<FailedOp> = emptyList())

    private val lock = Any()
    private var state: State = load()
    private val _count = MutableStateFlow(state.pending.size)
    /** Pendientes de sincronizar (para el badge de la navegación). */
    val count: StateFlow<Int> = _count.asStateFlow()

    // Gson puede dejar en null las listas de un JSON incompleto aunque el tipo diga lo contrario.
    @Suppress("USELESS_ELVIS", "SENSELESS_COMPARISON")
    private fun load(): State {
        val s = store.read()?.let { runCatching { gson.fromJson(it, State::class.java) }.getOrNull() } ?: return State()
        return State(
            (s.pending ?: emptyList()).filter { it != null },
            (s.failed ?: emptyList()).filter { it != null },
        )
    }

    private fun update(f: (State) -> State) = synchronized(lock) {
        state = f(state)
        store.write(gson.toJson(state))
        _count.value = state.pending.size
    }

    fun enqueue(type: Type, payload: Any, idempotencyKey: String, userId: String?, summary: String): PendingOp {
        val op = PendingOp(idempotencyKey, type, gson.toJson(payload), userId, summary, now())
        update { s -> if (s.pending.any { it.id == op.id }) s else s.copy(pending = s.pending + op) }
        return op
    }

    fun pending(): List<PendingOp> = synchronized(lock) { state.pending.toList() }
    fun failures(): List<FailedOp> = synchronized(lock) { state.failed.toList() }
    fun pendingFor(userId: String?): List<PendingOp> = pending().filter { it.userId == userId }

    fun remove(id: String) = update { s -> s.copy(pending = s.pending.filterNot { it.id == id }) }

    fun markAttempt(id: String, error: String?) = update { s ->
        s.copy(pending = s.pending.map { if (it.id == id) it.copy(attempts = it.attempts + 1, lastError = error) else it })
    }

    fun recordFailure(op: PendingOp, message: String) = update { s ->
        s.copy(
            pending = s.pending.filterNot { it.id == op.id },
            failed = (s.failed + FailedOp(op, message, now())).takeLast(MAX_FAILED),
        )
    }

    fun clearFailures() = update { it.copy(failed = emptyList()) }

    companion object {
        const val MAX_FAILED = 20
    }
}

/** Dónde se persiste la cola (JSON). */
interface QueueStore {
    fun read(): String?
    fun write(json: String)
}

/** Resultado de intentar reenviar una operación. */
sealed class SendOutcome {
    object Sent : SendOutcome()
    /** Red, tiempo agotado, 5xx, 429 o sesión vencida: se conserva para el siguiente intento. */
    data class Retry(val message: String) : SendOutcome()
    /** 400/403/404/409…: reintentar no lo arregla; se saca de la cola y se avisa al usuario. */
    data class Drop(val message: String) : SendOutcome()

    companion object {
        fun from(error: AppError): SendOutcome = when (error.kind) {
            AppError.Kind.NETWORK, AppError.Kind.TIMEOUT, AppError.Kind.SERVICE_DOWN, AppError.Kind.SERVER,
            AppError.Kind.RATE_LIMIT, AppError.Kind.UNAUTHORIZED -> Retry(error.message)
            else -> Drop(error.message)
        }

        /** ¿Este fallo al capturar justifica guardar la operación sin conexión? */
        fun isOffline(error: AppError): Boolean =
            error.kind == AppError.Kind.NETWORK || error.kind == AppError.Kind.TIMEOUT
    }
}

/**
 * Sincronización posterior: reenvía en orden de captura las operaciones del usuario de la sesión.
 * Se detiene en el primer fallo reintentable (sin red no tiene caso seguir) para conservar el orden.
 */
class OfflineSync(private val queue: OfflineQueue, private val send: suspend (OfflineQueue.PendingOp) -> SendOutcome) {

    data class Result(val sent: Int, val dropped: Int, val remaining: Int, val needsRetry: Boolean)

    suspend fun run(userId: String?): Result {
        var sent = 0
        var dropped = 0
        var retry = false
        for (op in queue.pendingFor(userId)) {
            when (val r = send(op)) {
                is SendOutcome.Sent -> { queue.remove(op.id); sent++ }
                is SendOutcome.Drop -> { queue.recordFailure(op, r.message); dropped++ }
                is SendOutcome.Retry -> { queue.markAttempt(op.id, r.message); retry = true }
            }
            if (retry) break
        }
        return Result(sent, dropped, queue.pendingFor(userId).size, retry)
    }
}
