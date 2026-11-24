package mx.freshtrack.mobile.ui.alerts

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.isVisible
import androidx.core.view.updatePadding
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.FreshTrackApp
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.Alerta
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.FragmentAlertsBinding
import mx.freshtrack.mobile.ui.common.StateColors
import mx.freshtrack.mobile.ui.common.TaskAdapter
import mx.freshtrack.mobile.ui.common.TaskItem
import mx.freshtrack.mobile.ui.common.setupFilters
import mx.freshtrack.mobile.ui.common.showError
import mx.freshtrack.mobile.ui.common.snack
import mx.freshtrack.mobile.ui.inventory.FefoActivity
import mx.freshtrack.mobile.work.AlertNotifier

/**
 * Alertas operativas guardadas en MongoDB (svc-alerts). El botón "Escanear ahora" pide a
 * svc-alerts revisar los lotes de la tienda (con bloqueo distribuido en Redis para no
 * duplicar) y las nuevas alertas también llegan como notificación push local.
 */
class AlertsFragment : Fragment() {

    private var _b: FragmentAlertsBinding? = null
    private val b get() = _b!!
    private val adapter = TaskAdapter()
    private var criticidad: String? = null
    private val app get() = FreshTrackApp.instance

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, s: Bundle?): View {
        _b = FragmentAlertsBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        ViewCompat.setOnApplyWindowInsetsListener(b.toolbar) { v, insets ->
            v.updatePadding(top = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top)
            insets
        }
        b.toolbar.subtitle = app.session.storeName
        b.list.adapter = adapter
        b.swipe.setOnRefreshListener { load() }
        b.swipe.setColorSchemeResources(R.color.brand_primary)
        b.chips.setupFilters(listOf(null to "Todas", "CRITICAL" to "Críticas", "WARNING" to "Advertencia", "INFO" to "Info"), null) {
            criticidad = it; load()
        }
        b.btnScan.isVisible = app.session.role.canResolveAlert
        b.btnScan.setOnClickListener { scanNow() }
        load()
    }

    override fun onHiddenChanged(hidden: Boolean) {
        super.onHiddenChanged(hidden)
        if (!hidden && _b != null) load()
    }

    private fun load() {
        b.swipe.isRefreshing = true
        viewLifecycleOwner.lifecycleScope.launch {
            when (val r = app.repository.alerts(criticidad)) {
                is ApiResult.Ok -> {
                    adapter.items = r.data.alertas.map { toItem(it) }
                    b.textEmpty.isVisible = r.data.alertas.isEmpty()
                    b.textEmpty.text = "Sin alertas abiertas. ¡Todo en orden!"
                    AlertNotifier.notifyNew(requireContext().applicationContext, emptyList()) // solo mantiene el registro
                }
                is ApiResult.Fail -> {
                    adapter.items = emptyList()
                    b.textEmpty.isVisible = true
                    b.textEmpty.text = r.error.message
                    b.root.showError(r.error) { load() }
                }
            }
            _b?.swipe?.isRefreshing = false
        }
    }

    private fun toItem(a: Alerta): TaskItem {
        val (c, bg) = StateColors.of(a.criticidad)
        val ctx = a.contexto.orEmpty()
        val sku = a.idSku
        val canResolve = app.session.role.canResolveAlert && a.id != null
        return TaskItem(
            id = a.id ?: a.hashCode().toString(),
            title = (ctx["producto"] as? String) ?: a.tipo?.replace('_', ' ')?.lowercase()?.replaceFirstChar { it.uppercase() } ?: "Alerta",
            subtitle = a.tipo?.replace('_', ' '),
            highlight = null,
            body = a.mensaje,
            badge = when (a.criticidad) { "CRITICAL" -> "CRÍTICA"; "WARNING" -> "AVISO"; else -> a.criticidad ?: "INFO" },
            badgeColor = c, badgeBg = bg,
            primary = if (sku != null) "Ver FEFO" to { startActivity(FefoActivity.forSku(requireContext(), sku, ctx["producto"] as? String)) } else null,
            secondary = if (canResolve) "Atendida" to { resolve(a) } else null,
        )
    }

    private fun resolve(a: Alerta) {
        val id = a.id ?: return
        viewLifecycleOwner.lifecycleScope.launch {
            when (val r = app.repository.resolveAlert(id)) {
                is ApiResult.Ok -> { b.root.snack("Alerta marcada como atendida"); load() }
                is ApiResult.Fail -> b.root.showError(r.error)
            }
        }
    }

    private fun scanNow() {
        b.btnScan.isEnabled = false
        viewLifecycleOwner.lifecycleScope.launch {
            when (val r = app.repository.scanAlerts(3)) {
                is ApiResult.Ok -> {
                    b.root.snack("Escaneados ${r.data.totalEscaneados ?: 0} lotes · ${r.data.alertasEmitidas ?: 0} alertas nuevas")
                    (app.repository.alerts() as? ApiResult.Ok)?.let { AlertNotifier.notifyNew(requireContext().applicationContext, it.data.alertas) }
                    load()
                }
                is ApiResult.Fail -> b.root.showError(r.error)
            }
            _b?.btnScan?.isEnabled = true
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
