package mx.freshtrack.mobile.session

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit
import com.google.gson.Gson
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import mx.freshtrack.mobile.BuildConfig
import mx.freshtrack.mobile.data.model.LoginResponse
import mx.freshtrack.mobile.data.model.Usuario

/**
 * Sesión del usuario en el dispositivo.
 * - JWT cifrado con [TokenCipher] (Android Keystore).
 * - Expiración local: se calcula con 'expira_en_segundos' del login para no mandar
 *   peticiones con un token que ya sabemos vencido.
 * - [events]: canal global que avisa a la UI cuando el backend revoca la sesión (401).
 */
class SessionManager(context: Context) : TokenStore {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("freshtrack_session", Context.MODE_PRIVATE)
    private val gson = Gson()

    @Volatile private var cachedToken: String? = null
    @Volatile private var cachedRefresh: String? = null

    sealed class Event {
        data class Expired(val reason: String) : Event()
    }

    private val _events = MutableSharedFlow<Event>(extraBufferCapacity = 4)
    val events: SharedFlow<Event> = _events.asSharedFlow()

    override var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, null) ?: BuildConfig.DEFAULT_BASE_URL
        set(value) {
            val normalized = value.trim().let { if (it.endsWith("/")) it else "$it/" }
            prefs.edit { putString(KEY_BASE_URL, normalized) }
        }

    var notificationsEnabled: Boolean
        get() = prefs.getBoolean(KEY_NOTIF, true)
        set(value) = prefs.edit { putBoolean(KEY_NOTIF, value) }

    var lastEmail: String?
        get() = prefs.getString(KEY_LAST_EMAIL, null)
        set(value) = prefs.edit { putString(KEY_LAST_EMAIL, value) }

    override val token: String?
        get() {
            cachedToken?.let { return it }
            val enc = prefs.getString(KEY_TOKEN, null) ?: return null
            return TokenCipher.decrypt(enc).also { cachedToken = it }
        }

    val user: Usuario?
        get() = prefs.getString(KEY_USER, null)?.let { runCatching { gson.fromJson(it, Usuario::class.java) }.getOrNull() }

    /** Vencimiento del ACCESS token (15 min en el servidor actual). */
    override val expiresAtMillis: Long get() = prefs.getLong(KEY_EXPIRES, 0L)

    /** Refresh token, cifrado igual que el access token. */
    override val refreshToken: String?
        get() {
            cachedRefresh?.let { return it }
            val enc = prefs.getString(KEY_REFRESH, null) ?: return null
            return TokenCipher.decrypt(enc).also { cachedRefresh = it }
        }

    /** Fin de la SESIÓN: el del refresh token si existe; si no, el del access token. */
    val sessionExpiresAtMillis: Long
        get() = maxOf(expiresAtMillis, prefs.getLong(KEY_REFRESH_EXPIRES, 0L))

    /** Hay sesión mientras el refresh siga vigente aunque el access ya haya vencido: se renueva solo. */
    val isLoggedIn: Boolean
        get() = token != null && user != null && System.currentTimeMillis() < sessionExpiresAtMillis

    /** Tienda asignada al usuario en su JWT (gerente/almacén están acotados a su sucursal). */
    val storeId: Int? get() = user?.idLocacion

    var storeName: String?
        get() = prefs.getString(KEY_STORE_NAME, null)
        set(value) = prefs.edit { putString(KEY_STORE_NAME, value) }

    val role: Role get() = Role.from(user?.rol)

    val jti: String? get() = prefs.getString(KEY_JTI, null)

    /**
     * Identificador aleatorio del teléfono para el registro seguro del dispositivo
     * (POST /auth/devices). Se genera una sola vez y sobrevive al cierre de sesión;
     * no usa IMEI ni ANDROID_ID (no identifica al hardware fuera de FreshTrack).
     */
    val deviceId: String
        get() = prefs.getString(KEY_DEVICE_ID, null) ?: synchronized(this) {
            prefs.getString(KEY_DEVICE_ID, null) ?: java.util.UUID.randomUUID().toString().also {
                prefs.edit(commit = true) { putString(KEY_DEVICE_ID, it) }
            }
        }

    override fun save(login: LoginResponse) {
        val ahora = System.currentTimeMillis()
        val ttl = (login.expiraEnSegundos ?: 8 * 3600L).coerceAtLeast(30)
        cachedToken = login.token
        login.refreshToken?.let { cachedRefresh = it }
        prefs.edit {
            putString(KEY_TOKEN, TokenCipher.encrypt(login.token))
            // Rotación: el refresh nuevo reemplaza al anterior, que el servidor ya invalidó.
            login.refreshToken?.let { putString(KEY_REFRESH, TokenCipher.encrypt(it)) }
            login.refreshExpiraEnSegundos?.let { putLong(KEY_REFRESH_EXPIRES, ahora + it * 1000) }
            putString(KEY_JTI, login.jti)
            putString(KEY_USER, gson.toJson(login.usuario))
            putLong(KEY_EXPIRES, ahora + ttl * 1000)
            putString(KEY_LAST_EMAIL, login.usuario.email)
        }
    }

    fun clear() {
        cachedToken = null
        cachedRefresh = null
        prefs.edit {
            remove(KEY_TOKEN); remove(KEY_JTI); remove(KEY_USER); remove(KEY_EXPIRES); remove(KEY_STORE_NAME)
            remove(KEY_REFRESH); remove(KEY_REFRESH_EXPIRES)
        }
    }

    /** Lo llama el interceptor HTTP cuando el backend contesta 401 a una petición autenticada. */
    override fun onUnauthorized(code: String?) {
        if (token == null) return
        clear()
        val reason = when (code) {
            "token_revocado" -> "Tu sesión fue revocada por un administrador."
            "sesion_inexistente" -> "Tu sesión expiró en el servidor."
            "sesion_no_verificable" -> "No se pudo verificar tu sesión (Redis no disponible). Inicia sesión de nuevo."
            else -> "Tu sesión ya no es válida. Inicia sesión de nuevo."
        }
        _events.tryEmit(Event.Expired(reason))
    }

    companion object {
        private const val KEY_TOKEN = "jwt_enc"
        private const val KEY_JTI = "jti"
        private const val KEY_USER = "user"
        private const val KEY_EXPIRES = "expires_at"
        private const val KEY_REFRESH = "refresh_enc"
        private const val KEY_REFRESH_EXPIRES = "refresh_expires_at"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_NOTIF = "notif"
        private const val KEY_LAST_EMAIL = "last_email"
        private const val KEY_STORE_NAME = "store_name"
        private const val KEY_DEVICE_ID = "device_id"
    }
}
