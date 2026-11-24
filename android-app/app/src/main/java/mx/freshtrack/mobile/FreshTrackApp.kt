package mx.freshtrack.mobile

import android.app.Application
import mx.freshtrack.mobile.data.api.ApiClient
import mx.freshtrack.mobile.data.repo.FreshTrackRepository
import mx.freshtrack.mobile.session.SessionManager
import mx.freshtrack.mobile.work.AlertNotifier
import mx.freshtrack.mobile.work.AlertWorker

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
        repository = FreshTrackRepository(apiClient, session)
        AlertNotifier.createChannels(this)
        if (session.isLoggedIn && session.notificationsEnabled) AlertWorker.schedule(this)
    }

    companion object {
        lateinit var instance: FreshTrackApp
            private set
    }
}
