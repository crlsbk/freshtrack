package mx.freshtrack.mobile.session

import com.google.gson.Gson
import mx.freshtrack.mobile.data.model.ApiErrorBody
import mx.freshtrack.mobile.data.model.LoginResponse
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** Lo mínimo que necesita el renovador; SessionManager lo implementa (y las pruebas usan un falso). */
interface TokenStore {
    val token: String?
    val refreshToken: String?
    val expiresAtMillis: Long
    val baseUrl: String
    fun save(login: LoginResponse)
    fun onUnauthorized(code: String?)
}

/**
 * Renovación de la sesión con refresh token rotatorio (svc-auth POST /api/v1/auth/refresh):
 *
 *  - El access token dura 15 min; el refresh token, la sesión completa (8 h, tope absoluto).
 *  - Se renueva cuando al access le quedan menos de [windowMillis] (60 s) o ya venció.
 *  - Cada uso ROTA el par: el refresh anterior deja de servir, así que se guarda el nuevo
 *    antes de cualquier otra petición. Si se reutilizara uno viejo, el servidor revoca la sesión.
 *  - Sincronizado: con varias peticiones a la vez, solo una rota y las demás usan el par nuevo.
 *  - 401 del servidor = sesión revocada o vencida → se cierra la sesión local.
 *  - Sin red no hace nada: se reintenta en la siguiente petición.
 *  - Servidor sin refresh_token (versión anterior): renueva con el access token vigente.
 */
class TokenRefresher(
    private val store: TokenStore,
    private val http: OkHttpClient,
    private val gson: Gson = Gson(),
    private val windowMillis: Long = 60 * 1000L,
    private val now: () -> Long = System::currentTimeMillis,
) {
    @Volatile var lastRotation: Pair<String?, String>? = null
        private set

    fun needsRefresh(): Boolean {
        if (store.token == null) return false
        val remaining = store.expiresAtMillis - now()
        if (remaining >= windowMillis) return false
        // Vencido: solo se puede renovar con refresh token.
        return remaining > 0 || store.refreshToken != null
    }

    /** Renueva solo si hace falta (o si [force]). Devuelve true si hubo rotación. */
    fun refreshIfNeeded(force: Boolean = false): Boolean = synchronized(this) {
        if (!force && !needsRefresh()) return false
        rotate()
    }

    /**
     * Tras un 401 de una petición hecha con [failedToken]: si otro hilo ya rotó el token,
     * basta con reintentar; si no, se rota ahora. Devuelve true si hay un token nuevo que usar.
     */
    fun refreshAfterUnauthorized(failedToken: String?): Boolean = synchronized(this) {
        val current = store.token ?: return false
        if (failedToken != null && current != failedToken) return true
        if (store.refreshToken == null) return false
        rotate()
    }

    private fun rotate(): Boolean {
        val current = store.token ?: return false
        val refresh = store.refreshToken
        val builder = Request.Builder()
            .url(store.baseUrl + "api/v1/auth/refresh")
            .header("Accept", "application/json")
        if (refresh != null) {
            builder.post(gson.toJson(mapOf("refresh_token" to refresh)).toRequestBody("application/json".toMediaType()))
        } else {
            builder.header("Authorization", "Bearer $current")
                .post("{}".toRequestBody("application/json".toMediaType()))
        }
        return try {
            http.newCall(builder.build()).execute().use { resp ->
                val body = resp.body?.string().orEmpty()
                when {
                    resp.isSuccessful -> {
                        val login = gson.fromJson(body, LoginResponse::class.java)
                        val oldJti = runCatching { jwtJti(current) }.getOrNull()
                        store.save(login)
                        lastRotation = oldJti to login.jti
                        true
                    }
                    resp.code == 401 -> {
                        store.onUnauthorized(runCatching { gson.fromJson(body, ApiErrorBody::class.java)?.error }.getOrNull())
                        false
                    }
                    else -> false
                }
            }
        } catch (e: java.io.IOException) {
            false
        }
    }

    private fun jwtJti(token: String): String? {
        val payload = token.split(".").getOrNull(1) ?: return null
        val json = String(java.util.Base64.getUrlDecoder().decode(payload.padEnd((payload.length + 3) / 4 * 4, '=')))
        return gson.fromJson(json, Map::class.java)["jti"] as? String
    }
}
