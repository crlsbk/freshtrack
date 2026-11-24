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
    val expiresAtMillis: Long
    val baseUrl: String
    fun save(login: LoginResponse)
    fun onUnauthorized(code: String?)
}

/**
 * Renovación del JWT con rotación (svc-auth POST /api/v1/auth/refresh):
 * con el token VIGENTE se obtiene uno nuevo y el servidor revoca el anterior (denylist en Redis).
 *
 *  - Se renueva cuando faltan menos de [windowMillis] (30 min) para que expire.
 *  - Es sincronizado: si varias peticiones llegan a la vez, solo una rota el token y las demás
 *    usan el nuevo (si dos rotaran, la segunda usaría un jti ya revocado → 401).
 *  - Si el servidor responde 401 (token ya revocado), se cierra la sesión.
 *  - Si no hay red, no hace nada: el token actual sigue siendo válido hasta su expiración.
 */
class TokenRefresher(
    private val store: TokenStore,
    private val http: OkHttpClient,
    private val gson: Gson = Gson(),
    private val windowMillis: Long = 30 * 60 * 1000L,
    private val now: () -> Long = System::currentTimeMillis,
) {
    @Volatile var lastRotation: Pair<String?, String>? = null
        private set

    fun needsRefresh(): Boolean {
        if (store.token == null) return false
        val remaining = store.expiresAtMillis - now()
        return remaining in 1 until windowMillis
    }

    /** Renueva solo si hace falta (o si [force]). Devuelve true si hubo rotación. */
    fun refreshIfNeeded(force: Boolean = false): Boolean = synchronized(this) {
        if (!force && !needsRefresh()) return false
        val current = store.token ?: return false
        val req = Request.Builder()
            .url(store.baseUrl + "api/v1/auth/refresh")
            .header("Authorization", "Bearer $current")
            .header("Accept", "application/json")
            .post("{}".toRequestBody("application/json".toMediaType()))
            .build()
        return try {
            http.newCall(req).execute().use { resp ->
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
