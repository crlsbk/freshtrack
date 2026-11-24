package mx.freshtrack.mobile

import android.app.Application
import mx.freshtrack.mobile.data.api.ApiClient
import mx.freshtrack.mobile.data.offline.EncryptedFileQueueStore
import mx.freshtrack.mobile.data.offline.OfflineQueue
import mx.freshtrack.mobile.data.repo.FreshTrackRepository
import mx.freshtrack.mobile.session.SessionManager
import mx.freshtrack.mobile.work.AlertNotifier
import mx.freshtrack.mobile.work.AlertWorker
import mx.freshtrack.mobile.work.SyncWorker

/** Contenedor de dependencias simple (Service Locator) para no agregar Hilt al proyecto. */
class FreshTrackApp : Application() {

    lateinit var session: SessionManager
        private set
    lateinit var apiClient: ApiClient
        private set
    lateinit var repository: FreshTrackRepository
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        session = SessionManager(this)
        apiClient = ApiClient(session)
        repository = FreshTrackRepository(
            apiClient, session, OfflineQueue(EncryptedFileQueueStore(this), apiClient.gson),
        ) { SyncWorker.enqueue(this) }
        AlertNotifier.createChannels(this)
        if (session.isLoggedIn && session.notificationsEnabled) AlertWorker.schedule(this)
        // Sincronización posterior de lo capturado sin conexión (espera a que haya red).
        if (session.isLoggedIn && repository.offlineQueue.count.value > 0) SyncWorker.enqueue(this)
    }

    companion object {
        lateinit var instance: FreshTrackApp
            private set
    }
}
