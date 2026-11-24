package mx.freshtrack.mobile.ui.settings

import android.os.Bundle
import android.util.Patterns
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.BuildConfig
import mx.freshtrack.mobile.databinding.ActivitySettingsBinding
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.common.app
import mx.freshtrack.mobile.ui.common.hideKeyboard
import mx.freshtrack.mobile.ui.common.snack
import mx.freshtrack.mobile.work.AlertWorker

/** Ajustes: URL del gateway (GCP o local), prueba de conexión y notificaciones. */
class SettingsActivity : BaseActivity() {

    override val requiresSession = false
    private lateinit var b: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setupToolbar(b.toolbar, "Ajustes")

        b.inputUrl.setText(session.baseUrl)
        b.btnTest.setOnClickListener { test() }
        b.btnSave.setOnClickListener { save() }
        b.btnGcp.setOnClickListener { b.inputUrl.setText(BuildConfig.DEFAULT_BASE_URL) }

        b.switchNotif.isChecked = session.notificationsEnabled
        b.switchNotif.isEnabled = session.isLoggedIn
        b.switchNotif.setOnCheckedChangeListener { _, on ->
            session.notificationsEnabled = on
            if (on) AlertWorker.schedule(this) else AlertWorker.cancel(this)
        }
        b.btnCheckAlerts.isVisible = session.isLoggedIn
        b.btnCheckAlerts.setOnClickListener { AlertWorker.runNow(this); b.root.snack("Revisando alertas en segundo plano…") }
        b.textAbout.text = "Versión ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE}) · ${if (BuildConfig.DEBUG) "debug" else "release"}"
    }

    private fun normalized(): String? {
        val raw = b.inputUrl.text.toString().trim()
        val url = if (raw.endsWith("/")) raw else "$raw/"
        return url.takeIf { Patterns.WEB_URL.matcher(it).matches() && (it.startsWith("https://") || it.startsWith("http://")) }
    }

    private fun test() {
        hideKeyboard()
        val url = normalized() ?: run { b.layoutUrl.error = "URL inválida"; return }
        b.layoutUrl.error = null
        b.textTest.isVisible = true
        b.textTest.text = "Probando…"
        lifecycleScope.launch {
            val api = app.apiClient.build(url, timeoutSeconds = 6)
            val t0 = System.nanoTime()
            val res = runCatching { api.probe("health") }
            val ms = (System.nanoTime() - t0) / 1_000_000
            b.textTest.text = res.fold(
                onSuccess = { r -> if (r.isSuccessful) "✓ Conectado en $ms ms · ${r.body()?.string()?.take(120)}" else "✗ HTTP ${r.code()}" },
                onFailure = { e -> "✗ ${e.javaClass.simpleName}: ${e.message}" },
            )
        }
    }

    private fun save() {
        val url = normalized() ?: run { b.layoutUrl.error = "URL inválida"; return }
        if (url != session.baseUrl && session.isLoggedIn) {
            // Un token emitido por otro servidor no sirve: se cierra la sesión local.
            session.clear()
        }
        session.baseUrl = url
        b.root.snack("Servidor guardado")
        finish()
    }
}
