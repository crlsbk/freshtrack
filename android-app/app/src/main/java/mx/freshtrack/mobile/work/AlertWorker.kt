package mx.freshtrack.mobile.work

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import androidx.work.*
import mx.freshtrack.mobile.FreshTrackApp
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.Alerta
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.ui.main.MainActivity
import java.util.concurrent.TimeUnit

/**
 * Cada 15 min (mínimo de WorkManager) consulta svc-alerts por alertas abiertas de la tienda
 * y notifica solo las nuevas (deduplicadas por id de MongoDB). Solo corre con red.
 */
class AlertWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as FreshTrackApp
        if (!app.session.isLoggedIn || !app.session.notificationsEnabled) return Result.success()
        return when (val r = app.repository.alerts()) {
            is ApiResult.Ok -> {
                AlertNotifier.notifyNew(applicationContext, r.data.alertas)
                Result.success()
            }
            is ApiResult.Fail -> Result.retry()
        }
    }

    companion object {
        private const val NAME = "freshtrack_alert_poll"

        fun schedule(context: Context) {
            val req = PeriodicWorkRequestBuilder<AlertWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 1, TimeUnit.MINUTES)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.KEEP, req)
        }

        fun cancel(context: Context) = WorkManager.getInstance(context).cancelUniqueWork(NAME)

        /**
         * Revisión inmediata (al abrir la app / iniciar sesión / botón «Revisar ahora»).
         * El trabajo periódico tarda hasta 15 min en su primera ejecución; este no espera.
         */
        fun runNow(context: Context) {
            val req = OneTimeWorkRequestBuilder<AlertWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork("${NAME}_now", ExistingWorkPolicy.REPLACE, req)
        }
    }
}

object AlertNotifier {
    const val CHANNEL_CRITICAL = "alerts_critical"
    const val CHANNEL_GENERAL = "alerts_general"
    private const val PREFS = "freshtrack_alerts_seen"

    fun createChannels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_CRITICAL, "Alertas críticas de caducidad", NotificationManager.IMPORTANCE_HIGH)
                .apply { description = "Lotes que vencen hoy o mañana" }
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_GENERAL, "Alertas de inventario", NotificationManager.IMPORTANCE_DEFAULT)
                .apply { description = "Lotes en vigilancia, transferencias y descuentos" }
        )
    }

    fun canNotify(context: Context): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /** Notifica las alertas que el dispositivo aún no ha mostrado. Devuelve cuántas eran nuevas. */
    fun notifyNew(context: Context, alertas: List<Alerta>): Int {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val seen = prefs.getStringSet("ids", emptySet())!!.toMutableSet()
        val nuevas = alertas.filter { it.id != null && it.id !in seen }
        if (nuevas.isEmpty() || !canNotify(context)) {
            prefs.edit { putStringSet("ids", seen + nuevas.mapNotNull { it.id }) }
            return nuevas.size
        }
        val intent = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).putExtra(MainActivity.EXTRA_TAB, MainActivity.TAB_ALERTS)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val nm = NotificationManagerCompat.from(context)
        nuevas.take(5).forEach { a ->
            val critical = a.criticidad == "CRITICAL"
            val n = NotificationCompat.Builder(context, if (critical) CHANNEL_CRITICAL else CHANNEL_GENERAL)
                .setSmallIcon(R.drawable.ic_notification)
                .setColor(ContextCompat.getColor(context, if (critical) R.color.risk_critical else R.color.brand_primary))
                .setContentTitle(if (critical) "Alerta crítica de caducidad" else "Alerta de inventario")
                .setContentText(a.mensaje ?: a.tipo)
                .setStyle(NotificationCompat.BigTextStyle().bigText(a.mensaje ?: a.tipo))
                .setPriority(if (critical) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
                .setContentIntent(intent)
                .setAutoCancel(true)
                .setGroup("freshtrack_alerts")
                .build()
            try { nm.notify(a.id.hashCode(), n) } catch (_: SecurityException) { }
        }
        if (nuevas.size > 5) {
            val summary = NotificationCompat.Builder(context, CHANNEL_GENERAL)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle("${nuevas.size} alertas nuevas en tu tienda")
                .setGroup("freshtrack_alerts").setGroupSummary(true)
                .setContentIntent(intent).setAutoCancel(true).build()
            try { nm.notify(0xF7, summary) } catch (_: SecurityException) { }
        }
        // Se conserva un historial acotado para no crecer indefinidamente.
        val updated = (seen + nuevas.mapNotNull { it.id }).toList().takeLast(500).toSet()
        prefs.edit { putStringSet("ids", updated) }
        return nuevas.size
    }
}
