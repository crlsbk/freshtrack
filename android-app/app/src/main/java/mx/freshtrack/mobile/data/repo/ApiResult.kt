package mx.freshtrack.mobile.data.repo

import com.google.gson.Gson
import mx.freshtrack.mobile.data.model.ApiErrorBody
import retrofit2.Response
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException

/** Resultado de una llamada: éxito con datos o fallo ya traducido a un mensaje para el usuario. */
sealed class ApiResult<out T> {
    data class Ok<T>(val data: T) : ApiResult<T>()
    data class Fail(val error: AppError) : ApiResult<Nothing>()
}

/**
 * Error normalizado. Conserva el código y el correlation_id del backend para poder
 * buscar el mismo request en los logs / bitácora durante la demostración de fallos.
 */
data class AppError(
    val kind: Kind,
    val message: String,
    val httpStatus: Int? = null,
    val code: String? = null,
    val correlationId: String? = null,
) {
    enum class Kind { NETWORK, TIMEOUT, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT, VALIDATION, RATE_LIMIT, SERVICE_DOWN, SERVER, UNKNOWN }

    val detail: String
        get() = buildString {
            append(message)
            if (code != null || httpStatus != null) append("\n[${httpStatus ?: "-"} · ${code ?: "-"}]")
            if (correlationId != null) append("\nID de rastreo: $correlationId")
        }
}

object ErrorMapper {
    private val gson = Gson()

    fun <T> fromResponse(resp: Response<T>): AppError {
        val raw = runCatching { resp.errorBody()?.string() }.getOrNull()
        val body = raw?.let { runCatching { gson.fromJson(it, ApiErrorBody::class.java) }.getOrNull() }
        return fromHttp(resp.code(), body)
    }

    fun fromHttp(status: Int, body: ApiErrorBody?): AppError {
        val serverMsg = body?.mensaje?.takeIf { it.isNotBlank() }
        val kind = when (status) {
            400, 415, 422 -> AppError.Kind.VALIDATION
            401 -> AppError.Kind.UNAUTHORIZED
            403 -> AppError.Kind.FORBIDDEN
            404 -> AppError.Kind.NOT_FOUND
            409 -> AppError.Kind.CONFLICT
            429 -> AppError.Kind.RATE_LIMIT
            502, 503, 504 -> AppError.Kind.SERVICE_DOWN
            in 500..599 -> AppError.Kind.SERVER
            else -> AppError.Kind.UNKNOWN
        }
        val fallback = when (kind) {
            AppError.Kind.UNAUTHORIZED -> "Credenciales inválidas o sesión vencida."
            AppError.Kind.FORBIDDEN -> "Tu rol no tiene permiso para esta operación."
            AppError.Kind.NOT_FOUND -> "El recurso no existe."
            AppError.Kind.CONFLICT -> "La operación entra en conflicto con el estado actual."
            AppError.Kind.RATE_LIMIT -> "Demasiadas solicitudes. Espera unos segundos e intenta de nuevo."
            AppError.Kind.SERVICE_DOWN -> "El microservicio no está disponible en este momento. Intenta más tarde."
            AppError.Kind.SERVER -> "Error interno del servidor."
            AppError.Kind.VALIDATION -> "Datos inválidos."
            else -> "Error inesperado ($status)."
        }
        // En 5xx no se muestra el mensaje crudo del servidor (manejo seguro de errores).
        val msg = if (kind == AppError.Kind.SERVER || kind == AppError.Kind.SERVICE_DOWN) fallback else serverMsg ?: fallback
        return AppError(kind, msg, status, body?.error, body?.correlationId)
    }

    fun fromThrowable(t: Throwable): AppError = when (t) {
        is SocketTimeoutException -> AppError(AppError.Kind.TIMEOUT, "La petición excedió el tiempo máximo de espera.")
        is UnknownHostException, is ConnectException ->
            AppError(AppError.Kind.NETWORK, "Sin conexión con el servidor. Revisa tu red o la URL en Ajustes.")
        is SSLException -> AppError(AppError.Kind.NETWORK, "No se pudo establecer una conexión segura (HTTPS).")
        is IOException -> AppError(AppError.Kind.NETWORK, "Error de red: ${t.message ?: "conexión interrumpida"}")
        else -> AppError(AppError.Kind.UNKNOWN, t.message ?: "Error inesperado")
    }
}

suspend fun <T> safeCall(block: suspend () -> Response<T>): ApiResult<T> = try {
    val resp = block()
    val body = resp.body()
    if (resp.isSuccessful && body != null) ApiResult.Ok(body)
    else if (resp.isSuccessful) ApiResult.Fail(AppError(AppError.Kind.UNKNOWN, "Respuesta vacía del servidor", resp.code()))
    else ApiResult.Fail(ErrorMapper.fromResponse(resp))
} catch (e: kotlinx.coroutines.CancellationException) {
    throw e
} catch (t: Throwable) {
    ApiResult.Fail(ErrorMapper.fromThrowable(t))
}
