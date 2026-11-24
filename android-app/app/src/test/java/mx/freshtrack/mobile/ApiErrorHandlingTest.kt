package mx.freshtrack.mobile

import kotlinx.coroutines.test.runTest
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.data.repo.AppError
import mx.freshtrack.mobile.data.repo.safeCall
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import java.util.concurrent.TimeUnit

/** Contrato de errores {error, mensaje, status, correlation_id} → AppError, con un servidor simulado. */
class ApiErrorHandlingTest {

    data class Ping(val status: String)
    interface TestApi { @GET("ping") suspend fun ping(): Response<Ping> }

    private lateinit var server: MockWebServer
    private lateinit var api: TestApi

    @Before fun setUp() {
        server = MockWebServer().apply { start() }
        api = Retrofit.Builder().baseUrl(server.url("/"))
            .client(OkHttpClient.Builder().readTimeout(1, TimeUnit.SECONDS).build())
            .addConverterFactory(GsonConverterFactory.create()).build().create(TestApi::class.java)
    }

    @After fun tearDown() = server.shutdown()

    private fun err(status: Int, code: String, msg: String) = MockResponse().setResponseCode(status)
        .setBody("""{"error":"$code","mensaje":"$msg","status":$status,"correlation_id":"abc123"}""")

    @Test fun `200 devuelve datos`() = runTest {
        server.enqueue(MockResponse().setBody("""{"status":"ok"}"""))
        val r = safeCall { api.ping() }
        assertEquals("ok", (r as ApiResult.Ok).data.status)
    }

    @Test fun `403 conserva mensaje y correlation id`() = runTest {
        server.enqueue(err(403, "acceso_denegado", "El rol 'warehouse' no tiene permiso"))
        val e = (safeCall { api.ping() } as ApiResult.Fail).error
        assertEquals(AppError.Kind.FORBIDDEN, e.kind)
        assertEquals("acceso_denegado", e.code)
        assertEquals("abc123", e.correlationId)
        assertTrue(e.message.contains("warehouse"))
    }

    @Test fun `409 stock insuficiente es conflicto`() = runTest {
        server.enqueue(err(409, "stock_insuficiente", "Stock insuficiente para el SKU 5."))
        assertEquals(AppError.Kind.CONFLICT, (safeCall { api.ping() } as ApiResult.Fail).error.kind)
    }

    @Test fun `429 rate limit`() = runTest {
        server.enqueue(err(429, "limite_excedido", "Demasiadas solicitudes"))
        assertEquals(AppError.Kind.RATE_LIMIT, (safeCall { api.ping() } as ApiResult.Fail).error.kind)
    }

    @Test fun `500 no expone el mensaje interno`() = runTest {
        server.enqueue(err(500, "error_interno", "psycopg.OperationalError: connection refused at 10.0.0.5"))
        val e = (safeCall { api.ping() } as ApiResult.Fail).error
        assertEquals(AppError.Kind.SERVER, e.kind)
        assertFalse(e.message.contains("psycopg"))
    }

    @Test fun `502 del gateway es servicio caido`() = runTest {
        server.enqueue(MockResponse().setResponseCode(502).setBody("Bad Gateway"))
        assertEquals(AppError.Kind.SERVICE_DOWN, (safeCall { api.ping() } as ApiResult.Fail).error.kind)
    }

    @Test fun `timeout se reporta como tal`() = runTest {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        assertEquals(AppError.Kind.TIMEOUT, (safeCall { api.ping() } as ApiResult.Fail).error.kind)
    }

    @Test fun `respuesta no JSON en error no truena`() = runTest {
        server.enqueue(MockResponse().setResponseCode(404).setBody("<html>not found</html>"))
        val e = (safeCall { api.ping() } as ApiResult.Fail).error
        assertEquals(AppError.Kind.NOT_FOUND, e.kind)
        assertNull(e.correlationId)
    }
}
