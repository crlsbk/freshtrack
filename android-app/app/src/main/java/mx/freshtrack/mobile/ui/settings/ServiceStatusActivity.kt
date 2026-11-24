package mx.freshtrack.mobile.ui.settings

import android.os.Bundle
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.RecyclerView
import com.google.gson.Gson
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.ApiErrorBody
import mx.freshtrack.mobile.data.model.HealthResponse
import mx.freshtrack.mobile.databinding.ActivityServiceStatusBinding
import mx.freshtrack.mobile.databinding.ItemServiceBinding
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.common.app
import java.net.SocketTimeoutException
import java.text.DateFormat
import java.util.Date

/**
 * Monitoreo desde el cliente: sondea cada microservicio a través del API Gateway y clasifica
 *  - ARRIBA: responde (aunque sea 401/403: el servicio está vivo y protegido)
 *  - DEGRADADO: responde 503 porque una dependencia (MongoDB/Redis/bucket) no está disponible
 *  - CAÍDO: el gateway responde 502/504 (contenedor detenido) o no hay conexión
 *  - TIMEOUT: excede el tiempo máximo del cliente (5 s)
 * Si el gateway expone /health/<servicio>, se muestran además sus dependencias y versión.
 */
class ServiceStatusActivity : BaseActivity() {

    enum class Status(val label: String, val color: Int, val dot: Int) {
        UP("Arriba", R.color.status_up, R.drawable.dot_up),
        DEGRADED("Degradado", R.color.status_degraded, R.drawable.dot_degraded),
        DOWN("Caído", R.color.status_down, R.drawable.dot_down),
        TIMEOUT("Timeout", R.color.status_down, R.drawable.dot_down),
    }

    data class Probe(val name: String, val key: String, val path: String)
    data class Result(val probe: Probe, val status: Status, val ms: Long, val detail: String)

    private val probes = listOf(
        Probe("Sistema web", "web", "health"),
        Probe("svc-auth", "auth", "api/v1/auth/me"),
        Probe("svc-catalog", "catalog", "api/v1/catalog/locations"),
        Probe("svc-inventory", "inventory", "api/v1/inventory/stock?por_pagina=1"),
        Probe("svc-commercial", "commercial", "api/v1/commercial/sales?por_pagina=1"),
        Probe("svc-asn", "asn", "api/v1/asn?por_pagina=1"),
        Probe("svc-planning", "planning", "api/v1/planning/transfers?limite=1"),
        Probe("svc-alerts", "alerts", "api/v1/alerts/active?limite=1"),
        Probe("svc-audit", "audit", "api/v1/audit/events?por_pagina=1"),
    )

    private lateinit var b: ActivityServiceStatusBinding
    private val adapter = Adapter()
    private val gson = Gson()
    private val probeApi by lazy { app.apiClient.build(session.baseUrl, timeoutSeconds = 5) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityServiceStatusBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setupToolbar(b.toolbar, "Estado de servicios", session.baseUrl.removePrefix("https://").trimEnd('/'))
        b.list.adapter = adapter
        b.swipe.setOnRefreshListener { run() }
        b.swipe.setColorSchemeResources(R.color.brand_primary)
        run()
    }

    private fun run() {
        b.swipe.isRefreshing = true
        lifecycleScope.launch {
            val results = probes.map { p -> async { check(p) } }.awaitAll()
            adapter.items = results
            val up = results.count { it.status == Status.UP }
            val deg = results.count { it.status == Status.DEGRADED }
            val down = results.size - up - deg
            b.textOverall.text = when {
                down == 0 && deg == 0 -> "Todos los servicios operando"
                down == 0 -> "$deg servicio(s) degradado(s)"
                else -> "$down servicio(s) sin respuesta"
            }
            b.textOverall.setTextColor(ContextCompat.getColor(this@ServiceStatusActivity,
                if (down > 0) R.color.status_down else if (deg > 0) R.color.status_degraded else R.color.status_up))
            b.textChecked.text = "Última verificación ${DateFormat.getTimeInstance().format(Date())} · " +
                "promedio ${results.filter { it.status != Status.TIMEOUT }.map { it.ms }.average().toLong()} ms"
            b.swipe.isRefreshing = false
        }
    }

    private suspend fun check(p: Probe): Result {
        // 1) Health detallado si el gateway lo enruta (/health/<svc>)
        if (p.key != "web") {
            val t0 = System.nanoTime()
            val h = runCatching { probeApi.probe("health/${p.key}") }.getOrNull()
            val ms = (System.nanoTime() - t0) / 1_000_000
            if (h != null && h.code() in listOf(200, 503)) {
                val body = h.body()?.string() ?: h.errorBody()?.string()
                val health = runCatching { gson.fromJson(body, HealthResponse::class.java) }.getOrNull()
                if (health?.service != null) {
                    val deps = health.dependencies.orEmpty().entries.joinToString(" · ") { (k, v) ->
                        val ok = when (v) { is Boolean -> v; is Map<*, *> -> v["ok"] == true || v["status"] == "UP"; else -> v.toString().contains("true", true) }
                        "$k ${if (ok) "✓" else "✗"}"
                    }
                    val st = if (health.status.equals("HEALTHY", true) || health.status.equals("UP", true)) Status.UP else Status.DEGRADED
                    return Result(p, st, ms, listOfNotNull(deps, health.version?.let { "v$it" }).joinToString("\n"))
                }
            }
        }
        // 2) Sondeo de un endpoint real del servicio
        val t0 = System.nanoTime()
        return try {
            val r = probeApi.probe(p.path)
            val ms = (System.nanoTime() - t0) / 1_000_000
            val code = r.code()
            val err = if (!r.isSuccessful) runCatching { gson.fromJson(r.errorBody()?.string(), ApiErrorBody::class.java) }.getOrNull() else null
            when {
                code in 200..299 -> {
                    if (p.key == "web") {
                        val h = runCatching { gson.fromJson(r.body()?.string(), HealthResponse::class.java) }.getOrNull()
                        Result(p, if (h?.status.equals("HEALTHY", true)) Status.UP else Status.DEGRADED, ms,
                            h?.dependencies?.entries?.joinToString(" · ") { "${it.key} ${if (it.value == true) "✓" else "✗"}" } ?: "HTTP 200")
                    } else Result(p, Status.UP, ms, "HTTP $code · responde")
                }
                code == 401 || code == 403 || code == 404 || code == 409 || code == 429 ->
                    Result(p, Status.UP, ms, "HTTP $code · vivo y protegido (${err?.error ?: "sin permiso"})")
                code == 503 -> Result(p, Status.DEGRADED, ms, "Dependencia no disponible: ${err?.error ?: err?.mensaje ?: "503"}")
                code == 502 || code == 504 -> Result(p, Status.DOWN, ms, "Gateway no alcanza el contenedor (HTTP $code)")
                else -> Result(p, Status.DEGRADED, ms, "HTTP $code ${err?.error ?: ""}")
            }
        } catch (e: SocketTimeoutException) {
            Result(p, Status.TIMEOUT, 5000, "Excedió 5 s de espera")
        } catch (e: Exception) {
            Result(p, Status.DOWN, (System.nanoTime() - t0) / 1_000_000, e.message ?: "Sin conexión")
        }
    }

    class Adapter : RecyclerView.Adapter<Adapter.VH>() {
        var items: List<Result> = emptyList()
            set(v) { field = v; notifyDataSetChanged() }

        class VH(val b: ItemServiceBinding) : RecyclerView.ViewHolder(b.root)

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
            VH(ItemServiceBinding.inflate(LayoutInflater.from(parent.context), parent, false))

        override fun getItemCount() = items.size

        override fun onBindViewHolder(h: VH, position: Int) {
            val r = items[position]
            val ctx = h.itemView.context
            h.b.dot.setBackgroundResource(r.status.dot)
            h.b.textName.text = r.probe.name
            h.b.textStatus.text = r.status.label
            h.b.textStatus.setTextColor(ContextCompat.getColor(ctx, r.status.color))
            h.b.textLatency.text = "${r.ms} ms"
            h.b.textDetail.text = r.detail
            h.b.textDetail.isVisible = r.detail.isNotBlank()
        }
    }
}
