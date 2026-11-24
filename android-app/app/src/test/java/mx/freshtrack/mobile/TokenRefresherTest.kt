package mx.freshtrack.mobile

import com.google.gson.Gson
import mx.freshtrack.mobile.data.model.LoginResponse
import mx.freshtrack.mobile.session.TokenRefresher
import mx.freshtrack.mobile.session.TokenStore
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Renovación con refresh token rotatorio contra un svc-auth simulado (access 15 min, sesión 8 h). */
class TokenRefresherTest {

    private class FakeStore(
        override val baseUrl: String,
        var expires: Long,
        override var refreshToken: String? = "rt-viejo",
    ) : TokenStore {
        override var token: String? = jwt("jti-viejo")
        override val expiresAtMillis get() = expires
        var unauthorizedCode: String? = null
        override fun save(login: LoginResponse) {
            token = login.token
            login.refreshToken?.let { refreshToken = it }
            expires = Long.MAX_VALUE
        }
        override fun onUnauthorized(code: String?) { unauthorizedCode = code; token = null; refreshToken = null }
    }

    private lateinit var server: MockWebServer
    private val now = 1_000_000_000L

    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() = server.shutdown()

    private fun okBody(jti: String, refresh: String? = "rt-$jti") =
        """{"token":"${jwt(jti)}","jti":"$jti","token_type":"Bearer","expira_en_segundos":900,
           ${if (refresh != null) "\"refresh_token\":\"$refresh\",\"refresh_expira_en_segundos\":27000," else ""}
           "usuario":{"id_usuario":"u","email":"g@freshtrack.mx","nombre":"G","rol":"store_manager","id_locacion":3}}"""

    private fun refresher(store: FakeStore) = TokenRefresher(store, OkHttpClient(), now = { now })
    private fun store(expiresInMs: Long, refresh: String? = "rt-viejo") = FakeStore(server.url("/").toString(), now + expiresInMs, refresh)

    @Test fun `no renueva si al access le queda mas de un minuto`() {
        assertFalse(refresher(store(10 * 60_000)).refreshIfNeeded())
        assertEquals(0, server.requestCount)
    }

    @Test fun `renueva en el ultimo minuto enviando el refresh token y guarda el par nuevo`() {
        server.enqueue(MockResponse().setBody(okBody("jti-nuevo")))
        val s = store(30_000)
        val r = refresher(s)
        assertTrue(r.refreshIfNeeded())
        val req = server.takeRequest()
        assertEquals("/api/v1/auth/refresh", req.path)
        assertEquals("rt-viejo", Gson().fromJson(req.body.readUtf8(), Map::class.java)["refresh_token"])
        assertNull("con refresh token no se manda el access", req.getHeader("Authorization"))
        assertEquals(jwt("jti-nuevo"), s.token)
        assertEquals("rt-jti-nuevo", s.refreshToken)
        assertEquals("jti-viejo" to "jti-nuevo", r.lastRotation)
    }

    @Test fun `access vencido se renueva con el refresh token`() {
        server.enqueue(MockResponse().setBody(okBody("jti-nuevo")))
        val s = store(-5 * 60_000)
        assertTrue(refresher(s).refreshIfNeeded())
        assertEquals(jwt("jti-nuevo"), s.token)
    }

    @Test fun `access vencido sin refresh token no intenta renovar`() {
        assertFalse(refresher(store(-60_000, refresh = null)).refreshIfNeeded())
        assertEquals(0, server.requestCount)
    }

    @Test fun `servidor sin refresh token usa el access vigente`() {
        server.enqueue(MockResponse().setBody(okBody("jti-nuevo", refresh = null)))
        val s = store(30_000, refresh = null)
        assertTrue(refresher(s).refreshIfNeeded())
        assertEquals("Bearer ${jwt("jti-viejo")}", server.takeRequest().getHeader("Authorization"))
    }

    @Test fun `refresh revocado cierra la sesion`() {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"refresh_invalido","mensaje":"x","status":401}"""))
        val s = store(30_000)
        assertFalse(refresher(s).refreshIfNeeded())
        assertEquals("refresh_invalido", s.unauthorizedCode)
        assertNull(s.token)
    }

    @Test fun `sin red conserva la sesion`() {
        val s = FakeStore("http://127.0.0.1:1/", now + 30_000)
        assertFalse(refresher(s).refreshIfNeeded())
        assertNotNull(s.token)
    }

    @Test fun `peticiones simultaneas rotan una sola vez`() {
        server.enqueue(MockResponse().setBody(okBody("jti-nuevo")).setBodyDelay(200, TimeUnit.MILLISECONDS))
        server.enqueue(MockResponse().setBody(okBody("jti-otro")))
        val s = store(30_000)
        val r = refresher(s)
        val pool = Executors.newFixedThreadPool(5)
        val done = CountDownLatch(5)
        repeat(5) { pool.execute { r.refreshIfNeeded(); done.countDown() } }
        assertTrue(done.await(5, TimeUnit.SECONDS))
        assertEquals(1, server.requestCount)
        assertEquals("rt-jti-nuevo", s.refreshToken)
    }

    @Test fun `401 cuando otro hilo ya roto el token solo pide reintentar`() {
        val s = store(10 * 60_000)
        s.token = jwt("jti-ya-rotado")
        assertTrue(refresher(s).refreshAfterUnauthorized(jwt("jti-viejo")))
        assertEquals(0, server.requestCount)
    }

    @Test fun `401 con el token actual rota y entrega uno nuevo`() {
        server.enqueue(MockResponse().setBody(okBody("jti-nuevo")))
        val s = store(10 * 60_000)
        assertTrue(refresher(s).refreshAfterUnauthorized(jwt("jti-viejo")))
        assertEquals(jwt("jti-nuevo"), s.token)
    }

    companion object {
        fun jwt(jti: String): String {
            val enc = java.util.Base64.getUrlEncoder().withoutPadding()
            return enc.encodeToString("""{"alg":"HS256"}""".toByteArray()) + "." +
                enc.encodeToString("""{"jti":"$jti"}""".toByteArray()) + ".firma"
        }
    }
}
