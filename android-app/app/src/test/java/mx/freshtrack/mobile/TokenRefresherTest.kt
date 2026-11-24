package mx.freshtrack.mobile

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

/** Rotación del JWT contra un svc-auth simulado. */
class TokenRefresherTest {

    private class FakeStore(override val baseUrl: String, var expires: Long) : TokenStore {
        override var token: String? = jwt("jti-viejo")
        override val expiresAtMillis get() = expires
        var unauthorizedCode: String? = null
        override fun save(login: LoginResponse) { token = login.token; expires = Long.MAX_VALUE }
        override fun onUnauthorized(code: String?) { unauthorizedCode = code; token = null }
    }

    private lateinit var server: MockWebServer
    private val now = 1_000_000L

    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() = server.shutdown()

    private fun okBody(jti: String) =
        """{"token":"${jwt(jti)}","jti":"$jti","token_type":"Bearer","expira_en_segundos":28800,
           "usuario":{"id_usuario":"u","email":"g@freshtrack.mx","nombre":"G","rol":"store_manager","id_locacion":3}}"""

    private fun refresher(store: FakeStore) = TokenRefresher(store, OkHttpClient(), now = { now })

    @Test fun `no renueva si faltan mas de 30 min`() {
        val store = FakeStore(server.url("/").toString(), now + 60 * 60 * 1000)
        assertFalse(refresher(store).refreshIfNeeded())
        assertEquals(0, server.requestCount)
    }

    @Test fun `renueva cerca de expirar, manda el token vigente y guarda el nuevo`() {
        server.enqueue(MockResponse().setBody(okBody("jti-nuevo")))
        val store = FakeStore(server.url("/").toString(), now + 5 * 60 * 1000)
        val r = refresher(store)
        assertTrue(r.refreshIfNeeded())
        val req = server.takeRequest()
        assertEquals("/api/v1/auth/refresh", req.path)
        assertEquals("Bearer ${jwt("jti-viejo")}", req.getHeader("Authorization"))
        assertEquals(jwt("jti-nuevo"), store.token)
        assertEquals("jti-viejo" to "jti-nuevo", r.lastRotation)
    }

    @Test fun `token revocado en el servidor cierra la sesion`() {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"token_revocado","mensaje":"x","status":401}"""))
        val store = FakeStore(server.url("/").toString(), now + 60_000)
        assertFalse(refresher(store).refreshIfNeeded())
        assertEquals("token_revocado", store.unauthorizedCode)
        assertNull(store.token)
    }

    @Test fun `sin red conserva la sesion actual`() {
        val store = FakeStore("http://127.0.0.1:1/", now + 60_000)
        assertFalse(refresher(store).refreshIfNeeded())
        assertNotNull(store.token)
    }

    @Test fun `peticiones simultaneas rotan el token una sola vez`() {
        server.enqueue(MockResponse().setBody(okBody("jti-nuevo")).setBodyDelay(200, TimeUnit.MILLISECONDS))
        server.enqueue(MockResponse().setBody(okBody("jti-otro")))
        val store = FakeStore(server.url("/").toString(), now + 60_000)
        val r = refresher(store)
        val pool = Executors.newFixedThreadPool(5)
        val done = CountDownLatch(5)
        repeat(5) { pool.execute { r.refreshIfNeeded(); done.countDown() } }
        assertTrue(done.await(5, TimeUnit.SECONDS))
        assertEquals(1, server.requestCount)
        assertEquals(jwt("jti-nuevo"), store.token)
    }

    companion object {
        fun jwt(jti: String): String {
            val enc = java.util.Base64.getUrlEncoder().withoutPadding()
            return enc.encodeToString("""{"alg":"HS256"}""".toByteArray()) + "." +
                enc.encodeToString("""{"jti":"$jti"}""".toByteArray()) + ".firma"
        }
    }
}
