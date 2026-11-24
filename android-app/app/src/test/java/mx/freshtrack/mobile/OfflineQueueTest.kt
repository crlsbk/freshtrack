package mx.freshtrack.mobile

import kotlinx.coroutines.test.runTest
import mx.freshtrack.mobile.data.model.MermaRequest
import mx.freshtrack.mobile.data.offline.OfflineQueue
import mx.freshtrack.mobile.data.offline.OfflineSync
import mx.freshtrack.mobile.data.offline.QueueStore
import mx.freshtrack.mobile.data.offline.SendOutcome
import mx.freshtrack.mobile.data.repo.AppError
import org.junit.Assert.*
import org.junit.Test

/** Trabajo sin conexión y sincronización posterior (lógica JVM pura, sin Android). */
class OfflineQueueTest {

    private class MemoryStore : QueueStore {
        var json: String? = null
        override fun read() = json
        override fun write(json: String) { this.json = json }
    }

    private var clock = 1_000L
    private fun queue(store: QueueStore = MemoryStore()) = OfflineQueue(store, now = { clock++ })
    private fun merma(id: String) = MermaRequest(id, 3, 1.0, "DANO", null)

    @Test fun `encola en orden, persiste y cuenta para el badge`() {
        val store = MemoryStore()
        val q = queue(store)
        q.enqueue(OfflineQueue.Type.MERMA, merma("l1"), "k1", "u1", "Merma 1")
        q.enqueue(OfflineQueue.Type.CONTEO, mapOf("id_locacion" to 3), "k2", "u1", "Conteo")
        assertEquals(2, q.count.value)
        // Otra instancia (la app se reinició) lee lo mismo del almacenamiento.
        val q2 = queue(store)
        assertEquals(listOf("k1", "k2"), q2.pending().map { it.id })
        assertEquals(OfflineQueue.Type.CONTEO, q2.pending()[1].type)
        assertTrue(q2.pending()[0].payloadJson.contains("\"id_lote\":\"l1\""))
    }

    @Test fun `la misma llave no se encola dos veces`() {
        val q = queue()
        q.enqueue(OfflineQueue.Type.MERMA, merma("l1"), "k1", "u1", "Merma")
        q.enqueue(OfflineQueue.Type.MERMA, merma("l1"), "k1", "u1", "Merma")
        assertEquals(1, q.count.value)
    }

    @Test fun `sincroniza en orden y quita lo enviado`() = runTest {
        val q = queue()
        listOf("k1", "k2", "k3").forEach { q.enqueue(OfflineQueue.Type.MERMA, merma(it), it, "u1", it) }
        val enviados = mutableListOf<String>()
        val r = OfflineSync(q) { op -> enviados += op.id; SendOutcome.Sent }.run("u1")
        assertEquals(listOf("k1", "k2", "k3"), enviados)
        assertEquals(OfflineSync.Result(3, 0, 0, false), r)
        assertEquals(0, q.count.value)
    }

    @Test fun `sin red se detiene, conserva el orden y pide reintento`() = runTest {
        val q = queue()
        listOf("k1", "k2", "k3").forEach { q.enqueue(OfflineQueue.Type.MERMA, merma(it), it, "u1", it) }
        val r = OfflineSync(q) { op ->
            if (op.id == "k2") SendOutcome.Retry("Sin conexión") else SendOutcome.Sent
        }.run("u1")
        assertTrue(r.needsRetry)
        assertEquals(listOf("k2", "k3"), q.pending().map { it.id })
        assertEquals(1, q.pending()[0].attempts)
        assertEquals("Sin conexión", q.pending()[0].lastError)
    }

    @Test fun `un 4xx se saca de la cola y queda registrado para el usuario`() = runTest {
        val q = queue()
        listOf("k1", "k2").forEach { q.enqueue(OfflineQueue.Type.MERMA, merma(it), it, "u1", it) }
        val r = OfflineSync(q) { op ->
            if (op.id == "k1") SendOutcome.Drop("No alcanza la existencia") else SendOutcome.Sent
        }.run("u1")
        assertEquals(OfflineSync.Result(1, 1, 0, false), r)
        assertEquals("No alcanza la existencia", q.failures().single().message)
        assertEquals("k1", q.failures().single().op.id)
        q.clearFailures()
        assertTrue(q.failures().isEmpty())
    }

    @Test fun `solo envia lo del usuario de la sesion`() = runTest {
        val q = queue()
        q.enqueue(OfflineQueue.Type.MERMA, merma("a"), "ka", "u1", "a")
        q.enqueue(OfflineQueue.Type.MERMA, merma("b"), "kb", "u2", "b")
        val enviados = mutableListOf<String>()
        OfflineSync(q) { op -> enviados += op.id; SendOutcome.Sent }.run("u2")
        assertEquals(listOf("kb"), enviados)
        assertEquals(listOf("ka"), q.pending().map { it.id })
    }

    @Test fun `clasificacion de errores`() {
        fun e(k: AppError.Kind) = AppError(k, "m")
        listOf(AppError.Kind.NETWORK, AppError.Kind.TIMEOUT, AppError.Kind.SERVER, AppError.Kind.SERVICE_DOWN,
            AppError.Kind.RATE_LIMIT, AppError.Kind.UNAUTHORIZED).forEach {
            assertTrue(it.name, SendOutcome.from(e(it)) is SendOutcome.Retry)
        }
        listOf(AppError.Kind.VALIDATION, AppError.Kind.CONFLICT, AppError.Kind.FORBIDDEN, AppError.Kind.NOT_FOUND).forEach {
            assertTrue(it.name, SendOutcome.from(e(it)) is SendOutcome.Drop)
        }
        assertTrue(SendOutcome.isOffline(e(AppError.Kind.NETWORK)))
        assertFalse(SendOutcome.isOffline(e(AppError.Kind.CONFLICT)))
    }

    @Test fun `almacenamiento corrupto arranca con cola vacia`() {
        val store = MemoryStore().apply { json = "{no es json" }
        assertEquals(0, queue(store).count.value)
        val vacio = MemoryStore().apply { json = "{}" }
        assertEquals(0, queue(vacio).count.value)
    }
}
