package mx.freshtrack.mobile.ui.common

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import android.content.res.Configuration
import androidx.core.view.updatePadding
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.snackbar.Snackbar
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.FreshTrackApp
import mx.freshtrack.mobile.data.repo.AppError
import mx.freshtrack.mobile.session.SessionManager
import mx.freshtrack.mobile.ui.login.LoginActivity

/** Estado de una pantalla que carga datos remotos. */
sealed class UiState<out T> {
    data object Loading : UiState<Nothing>()
    data class Success<T>(val data: T) : UiState<T>()
    data class Error(val error: AppError) : UiState<Nothing>()
}

val Context.app: FreshTrackApp get() = applicationContext as FreshTrackApp

/**
 * Actividad base de las pantallas autenticadas:
 *  - Si no hay sesión válida, regresa al login.
 *  - Escucha el canal global de sesión: si cualquier microservicio responde 401
 *    (token revocado, sesión expirada en Redis), cierra todo y vuelve al login con el motivo.
 *  - Edge-to-edge con insets aplicados a la raíz.
 */
abstract class BaseActivity : AppCompatActivity() {

    protected val session: SessionManager get() = app.session
    protected val repo get() = app.repository
    protected open val requiresSession: Boolean = true
    /** Pantallas con encabezado verde: iconos claros en la barra de estado. */
    protected open val greenHeader: Boolean = false

    private val isNight: Boolean
        get() = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES

    /** Iconos oscuros sobre fondo claro; en modo oscuro siempre claros. */
    fun setLightStatusBar(lightBackground: Boolean) {
        WindowInsetsControllerCompat(window, window.decorView).isAppearanceLightStatusBars = lightBackground && !isNight
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setLightStatusBar(!greenHeader)
        if (requiresSession && !session.isLoggedIn) {
            goToLogin(null)
            return
        }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                session.events.collect { ev ->
                    if (ev is SessionManager.Event.Expired && requiresSession) goToLogin(ev.reason)
                }
            }
        }
    }

    protected fun applyInsets(root: View, toolbar: View? = null) {
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            toolbar?.updatePadding(top = bars.top) ?: v.updatePadding(top = bars.top)
            v.updatePadding(bottom = bars.bottom, left = bars.left, right = bars.right)
            insets
        }
    }

    protected fun setupToolbar(toolbar: MaterialToolbar, title: String, subtitle: String? = null) {
        toolbar.title = title
        toolbar.subtitle = subtitle
        toolbar.setNavigationOnClickListener { onBackPressedDispatcher.onBackPressed() }
    }

    fun goToLogin(reason: String?) {
        startActivity(
            Intent(this, LoginActivity::class.java)
                .putExtra(LoginActivity.EXTRA_REASON, reason)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        )
        finish()
    }
}

fun Activity.hideKeyboard() {
    val imm = getSystemService(InputMethodManager::class.java)
    currentFocus?.let { imm.hideSoftInputFromWindow(it.windowToken, 0) }
}

fun View.showError(error: AppError, retry: (() -> Unit)? = null) {
    val sb = Snackbar.make(this, error.message, if (retry != null) Snackbar.LENGTH_LONG else Snackbar.LENGTH_LONG)
    if (retry != null) sb.setAction("Reintentar") { retry() }
    else if (error.correlationId != null || error.code != null) sb.setAction("Detalle") {
        MaterialAlertDialogBuilder(context).setTitle("Detalle del error").setMessage(error.detail)
            .setPositiveButton("Cerrar", null).show()
    }
    sb.show()
}

fun View.snack(msg: String) = Snackbar.make(this, msg, Snackbar.LENGTH_SHORT).show()

fun Context.toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

fun Context.errorDialog(title: String, error: AppError, onRetry: (() -> Unit)? = null) {
    val b = MaterialAlertDialogBuilder(this).setTitle(title).setMessage(error.detail)
        .setPositiveButton("Cerrar", null)
    if (onRetry != null) b.setNeutralButton("Reintentar") { _, _ -> onRetry() }
    b.show()
}

fun LifecycleOwner.launchWhenStarted(block: suspend () -> Unit) {
    lifecycleScope.launch { repeatOnLifecycle(Lifecycle.State.STARTED) { block() } }
}
