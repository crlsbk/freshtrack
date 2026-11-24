package mx.freshtrack.mobile.ui.login

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import androidx.activity.viewModels
import androidx.core.view.isVisible
import androidx.lifecycle.ViewModel
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewModelScope
import com.google.android.material.chip.Chip
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.FreshTrackApp
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.LoginResponse
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.data.repo.AppError
import mx.freshtrack.mobile.databinding.ActivityLoginBinding
import mx.freshtrack.mobile.session.Role
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.common.UiState
import mx.freshtrack.mobile.ui.common.hideKeyboard
import mx.freshtrack.mobile.ui.common.launchWhenStarted
import mx.freshtrack.mobile.ui.main.MainActivity
import mx.freshtrack.mobile.ui.settings.SettingsActivity
import mx.freshtrack.mobile.work.AlertWorker

class LoginViewModel : ViewModel() {
    private val app = FreshTrackApp.instance
    private val _state = MutableStateFlow<UiState<LoginResponse>?>(null)
    val state: StateFlow<UiState<LoginResponse>?> = _state

    private val _gateway = MutableStateFlow<Boolean?>(null)
    val gateway: StateFlow<Boolean?> = _gateway

    fun checkGateway() = viewModelScope.launch {
        _gateway.value = null
        _gateway.value = runCatching { app.apiClient.api.probe("health").isSuccessful }.getOrDefault(false)
    }

    fun login(email: String, password: String) {
        if (email.isBlank() || password.isBlank()) {
            _state.value = UiState.Error(AppError(AppError.Kind.VALIDATION, "Escribe tu correo y contraseña."))
            return
        }
        _state.value = UiState.Loading
        viewModelScope.launch {
            when (val r = app.repository.login(email, password)) {
                is ApiResult.Ok -> {
                    val role = Role.from(r.data.usuario.rol)
                    if (!role.canUseMobile) {
                        // La app móvil es para personal de tienda; el resto usa web/escritorio.
                        app.repository.logout()
                        _state.value = UiState.Error(
                            AppError(
                                AppError.Kind.FORBIDDEN,
                                "El perfil ${role.label} no opera la app móvil. Usa el sistema web o la app de escritorio.",
                            )
                        )
                    } else {
                        // Nombre de la tienda para el encabezado (catálogo con caché Redis).
                        (app.repository.locations() as? ApiResult.Ok)?.data?.locaciones
                            ?.firstOrNull { it.idLocacion == r.data.usuario.idLocacion }
                            ?.let { app.session.storeName = it.nombre }
                        _state.value = UiState.Success(r.data)
                    }
                }
                is ApiResult.Fail -> _state.value = UiState.Error(r.error)
            }
        }
    }
}

class LoginActivity : BaseActivity() {

    override val requiresSession = false
    override val greenHeader = true
    private lateinit var b: ActivityLoginBinding
    private val vm: LoginViewModel by viewModels()

    private val demoAccounts = listOf(
        Triple("Gerente", "gerente@freshtrack.mx", "Tienda2026!"),
        Triple("Almacén", "almacen@freshtrack.mx", "Almacen2026!"),
        Triple("Admin", "admin@freshtrack.mx", "Admin2026!"),
        Triple("Comprador", "buyer@freshtrack.mx", "Compras2026!"),
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (session.isLoggedIn) {
            openMain(); return
        }
        b = ActivityLoginBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root)

        intent.getStringExtra(EXTRA_REASON)?.let { reason ->
            MaterialAlertDialogBuilder(this).setTitle("Sesión finalizada").setMessage(reason)
                .setIcon(R.drawable.ic_lock).setPositiveButton("Entendido", null).show()
        }

        session.lastEmail?.let { b.inputEmail.setText(it) }
        b.inputPassword.setOnEditorActionListener { _, id, _ ->
            if (id == EditorInfo.IME_ACTION_DONE) { submit(); true } else false
        }
        b.btnLogin.setOnClickListener { submit() }
        b.btnServer.setOnClickListener { startActivity(Intent(this, SettingsActivity::class.java)) }

        demoAccounts.forEach { (label, email, pass) ->
            val chip = Chip(this).apply {
                text = label
                isCheckable = false
                setOnClickListener {
                    b.inputEmail.setText(email); b.inputPassword.setText(pass)
                }
            }
            b.chipsDemo.addView(chip)
        }

        launchWhenStarted {
            vm.state.collect { st ->
                b.progress.isVisible = st is UiState.Loading
                b.btnLogin.isEnabled = st !is UiState.Loading
                b.textError.isVisible = st is UiState.Error
                when (st) {
                    is UiState.Error -> b.textError.text = st.error.message
                    is UiState.Success -> {
                        if (session.notificationsEnabled) AlertWorker.schedule(this@LoginActivity)
                        openMain()
                    }
                    else -> Unit
                }
            }
        }
        lifecycleScope.launch {
            vm.gateway.collect { ok ->
                b.textServer.text = session.baseUrl.removePrefix("https://").removePrefix("http://").trimEnd('/')
                b.dotServer.setBackgroundResource(
                    when (ok) {
                        true -> R.drawable.dot_up
                        false -> R.drawable.dot_down
                        null -> R.drawable.dot_unknown
                    }
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (::b.isInitialized) vm.checkGateway()
    }

    private fun submit() {
        hideKeyboard()
        vm.login(b.inputEmail.text.toString(), b.inputPassword.text.toString())
    }

    private fun openMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    companion object {
        const val EXTRA_REASON = "reason"
    }
}
