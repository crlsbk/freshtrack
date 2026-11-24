package mx.freshtrack.mobile.work

import android.content.Context
import androidx.work.*
import mx.freshtrack.mobile.FreshTrackApp
import mx.freshtrack.mobile.data.offline.OfflineSync
import java.util.concurrent.TimeUnit

/**
 * Sincronización posterior: cuando hay red, reenvía en orden las mermas y conteos guardados
 * sin conexión (cada uno con su Idempotency-Key original, así que repetir no duplica nada).
 *  - 2xx → se quita de la cola.
 *  - 400/403/404/409 → se quita y queda en «No se pudieron enviar» para que el usuario lo revise.
 *  - Sin red / 5xx / 429 / sesión vencida → se conserva y WorkManager reintenta con backoff.
 * Se encola al guardar algo sin conexión, al abrir la app y al iniciar sesión.
 */
class SyncWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as FreshTrackApp
        val session = app.session
        // Sin sesión no se puede enviar a nombre de nadie: se espera al próximo login.
        if (!session.isLoggedIn) return Result.success()
        val repo = app.repository
        val r = OfflineSync(repo.offlineQueue) { op -> repo.replay(op) }.run(session.user?.idUsuario)
        return if (r.needsRetry) Result.retry() else Result.success()
    }

    companion object {
        private const val NAME = "freshtrack_offline_sync"

        fun enqueue(context: Context) {
            val req = OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            // APPEND_OR_REPLACE: si una sincronización ya está corriendo, esta va después y
            // recoge lo que se guardó mientras tanto (reenviar de más es inocuo: idempotente).
            WorkManager.getInstance(context).enqueueUniqueWork(NAME, ExistingWorkPolicy.APPEND_OR_REPLACE, req)
        }
    }
}
