package mx.freshtrack.mobile.data.api

import com.google.gson.Gson
import com.google.gson.GsonBuilder
import mx.freshtrack.mobile.BuildConfig
import mx.freshtrack.mobile.data.model.ApiErrorBody
import mx.freshtrack.mobile.session.SessionManager
import mx.freshtrack.mobile.session.TokenRefresher
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Construye Retrofit/OkHttp. Se reconstruye cuando cambia la URL del servidor en Ajustes.
 *
 * Cadena de interceptores:
 *  1. [AuthInterceptor]   → Authorization: Bearer, X-Correlation-Id, X-Location-Id, User-Agent
 *  2. [UnauthorizedInterceptor] → si el gateway responde 401 se limpia la sesión y se avisa a la UI
 *  3. HttpLoggingInterceptor (solo debug; el header Authorization se redacta)
 */
class ApiClient(private val session: SessionManager) {

    val gson: Gson = GsonBuilder().create()

    /** Cliente sin interceptores para llamar /auth/refresh (evita recursión en el interceptor). */
    val refresher = TokenRefresher(
        session,
        OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).build(),
        gson,
    )

    @Volatile private var currentUrl: String? = null
    @Volatile private var cached: FreshTrackApi? = null

    val api: FreshTrackApi
        get() {
            val url = session.baseUrl
            val c = cached
            if (c != null && url == currentUrl) return c
            synchronized(this) {
                if (cached == null || url != currentUrl) {
                    cached = build(url)
                    currentUrl = url
                }
                return cached!!
            }
        }

    fun build(baseUrl: String, timeoutSeconds: Long = 20): FreshTrackApi {
        val logging = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.HTTP_LOGS) HttpLoggingInterceptor.Level.BODY else HttpLoggingInterceptor.Level.NONE
            redactHeader("Authorization")
        }
        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(timeoutSeconds, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS) // subida de fotos
            .callTimeout(90, TimeUnit.SECONDS)
            .addInterceptor(AuthInterceptor(session, refresher))
            .addInterceptor(UnauthorizedInterceptor(session, gson))
            .addInterceptor(logging)
            .build()
        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(FreshTrackApi::class.java)
    }
}

class AuthInterceptor(private val session: SessionManager, private val refresher: TokenRefresher) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val path = original.url.encodedPath
        // Renovación preventiva: si al token le quedan < 30 min se rota ANTES de usarlo.
        if (!path.endsWith("/auth/login") && !path.endsWith("/auth/refresh") && !path.endsWith("/auth/logout")) {
            refresher.refreshIfNeeded()
        }
        val b = original.newBuilder()
            .header("Accept", "application/json")
            .header("User-Agent", "FreshTrackMobile/${BuildConfig.VERSION_NAME} (Android)")
            // Mismo correlation_id viaja por todos los microservicios y queda en la bitácora.
            .header("X-Correlation-Id", UUID.randomUUID().toString().replace("-", ""))
        session.storeId?.let { b.header("X-Location-Id", it.toString()) }
        val isLogin = original.url.encodedPath.endsWith("/auth/login")
        if (!isLogin) session.token?.let { b.header("Authorization", "Bearer $it") }
        return chain.proceed(b.build())
    }
}

class UnauthorizedInterceptor(private val session: SessionManager, private val gson: Gson) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val response = chain.proceed(request)
        val isLogin = request.url.encodedPath.endsWith("/auth/login")
        if (response.code == 401 && !isLogin && request.header("Authorization") != null) {
            val code = runCatching {
                gson.fromJson(response.peekBody(4096).string(), ApiErrorBody::class.java)?.error
            }.getOrNull()
            session.onUnauthorized(code)
        }
        return response
    }
}
