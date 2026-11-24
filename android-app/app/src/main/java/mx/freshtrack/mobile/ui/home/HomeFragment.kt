package mx.freshtrack.mobile.ui.home

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.isVisible
import androidx.core.view.updatePadding
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.FreshTrackApp
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.EsgResponse
import mx.freshtrack.mobile.data.model.Existencia
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.FragmentHomeBinding
import mx.freshtrack.mobile.databinding.ViewActionBinding
import mx.freshtrack.mobile.databinding.ViewKpiBinding
import mx.freshtrack.mobile.ui.common.launchWhenStarted
import mx.freshtrack.mobile.ui.count.CountActivity
import mx.freshtrack.mobile.ui.discount.DiscountsActivity
import mx.freshtrack.mobile.ui.evidence.EvidenceActivity
import mx.freshtrack.mobile.ui.inventory.FefoActivity
import mx.freshtrack.mobile.ui.inventory.StockAdapter
import mx.freshtrack.mobile.ui.main.MainActivity
import mx.freshtrack.mobile.ui.receive.ReceiveActivity
import mx.freshtrack.mobile.ui.shrink.ShrinkageActivity
import mx.freshtrack.mobile.ui.transfer.TransfersActivity
import mx.freshtrack.mobile.util.Fmt
import java.time.LocalTime

/** Cada indicador se carga de forma independiente: si un microservicio cae, solo su tarjeta se degrada. */
data class Kpi(val value: String?, val ok: Boolean)

data class HomeState(
    val loading: Boolean = true,
    val atRisk: Kpi = Kpi(null, true),
    val alerts: Kpi = Kpi(null, true),
    val transfers: Kpi = Kpi(null, true),
    val discounts: Kpi = Kpi(null, true),
    val esg: EsgResponse? = null,
    val esgOk: Boolean = true,
    val expiring: List<Existencia> = emptyList(),
    val degraded: List<String> = emptyList(),
)

class HomeViewModel : ViewModel() {
    private val repo = FreshTrackApp.instance.repository
    private val session = FreshTrackApp.instance.session
    private val _state = MutableStateFlow(HomeState())
    val state: StateFlow<HomeState> = _state

    init { load() }

    fun load() = viewModelScope.launch {
        _state.value = _state.value.copy(loading = true)
        val store = session.storeId
        // Llamadas en paralelo a 4 microservicios distintos.
        val risk = async { repo.stock(diasMax = 2) }
        val alerts = async { repo.alerts() }
        val tr = async { repo.transfers("SUGERIDA") }
        val ds = async { repo.discounts("SUGERIDO") }
        val esg = async { repo.esg() }

        val degraded = mutableListOf<String>()
        val riskR = risk.await()
        val atRisk = when (riskR) {
            is ApiResult.Ok -> Kpi((riskR.data.paginacion?.total ?: riskR.data.existencias.size).toString(), true)
            is ApiResult.Fail -> { degraded += "Inventario"; Kpi(null, false) }
        }
        val alertsK = when (val r = alerts.await()) {
            is ApiResult.Ok -> Kpi(r.data.total.toString(), true)
            is ApiResult.Fail -> { degraded += "Alertas"; Kpi(null, false) }
        }
        val trK = when (val r = tr.await()) {
            is ApiResult.Ok -> Kpi(r.data.transferencias.count { store == null || it.idOrigen == store || it.idDestino == store }.toString(), true)
            is ApiResult.Fail -> { if (r.error.httpStatus != 403) degraded += "Planeación"; Kpi(null, false) }
        }
        val dsK = when (val r = ds.await()) {
            is ApiResult.Ok -> Kpi(r.data.descuentos.count { store == null || it.idLocacion == store }.toString(), true)
            is ApiResult.Fail -> { if (r.error.httpStatus != 403 && "Planeación" !in degraded) degraded += "Planeación"; Kpi(null, false) }
        }
        val esgR = esg.await()
        _state.value = HomeState(
            loading = false,
            atRisk = atRisk, alerts = alertsK, transfers = trK, discounts = dsK,
            esg = (esgR as? ApiResult.Ok)?.data, esgOk = esgR is ApiResult.Ok,
            expiring = (riskR as? ApiResult.Ok)?.data?.existencias?.take(5).orEmpty(),
            degraded = degraded,
        )
    }
}

class HomeFragment : Fragment() {

    private var _b: FragmentHomeBinding? = null
    private val b get() = _b!!
    private val vm: HomeViewModel by viewModels()
    private val app get() = FreshTrackApp.instance

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, s: Bundle?): View {
        _b = FragmentHomeBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        ViewCompat.setOnApplyWindowInsetsListener(b.header) { v, insets ->
            v.updatePadding(top = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top + 16.dp)
            insets
        }
        val user = app.session.user
        val hour = LocalTime.now().hour
        val greet = when (hour) { in 5..11 -> "Buenos días"; in 12..18 -> "Buenas tardes"; else -> "Buenas noches" }
        b.textGreeting.text = "$greet, ${user?.nombre?.substringBefore(' ') ?: ""}"
        b.textStore.text = "${app.session.role.label} · ${app.session.storeName ?: "Tienda ${user?.idLocacion ?: "—"}"}"

        kpi(b.kpiRisk, R.drawable.ic_warning, "Lotes ≤ 2 días", R.color.risk_critical) {
            (activity as? MainActivity)?.selectTab(R.id.nav_inventory)
        }
        kpi(b.kpiAlerts, R.drawable.ic_bell, "Alertas abiertas", R.color.brand_secondary) {
            (activity as? MainActivity)?.selectTab(R.id.nav_alerts)
        }
        kpi(b.kpiTransfers, R.drawable.ic_transfer, "Transferencias", R.color.brand_primary) {
            startActivity(Intent(requireContext(), TransfersActivity::class.java))
        }
        kpi(b.kpiDiscounts, R.drawable.ic_discount, "Descuentos sugeridos", R.color.brand_primary) {
            startActivity(Intent(requireContext(), DiscountsActivity::class.java))
        }

        val role = app.session.role
        action(b.actReceive, R.drawable.ic_truck, "Recibir", role.canReceive) { startActivity(ReceiveActivity.intent(requireContext(), null)) }
        action(b.actShrink, R.drawable.ic_trash, "Merma", role.canRegisterShrinkage) { startActivity(Intent(requireContext(), ShrinkageActivity::class.java)) }
        action(b.actCount, R.drawable.ic_count, "Conteo", role.canCount) { startActivity(Intent(requireContext(), CountActivity::class.java)) }
        action(b.actFefo, R.drawable.ic_fefo, "FEFO", true) { startActivity(Intent(requireContext(), FefoActivity::class.java)) }
        action(b.actTransfer, R.drawable.ic_transfer, "Transferir", true) { startActivity(Intent(requireContext(), TransfersActivity::class.java)) }
        action(b.actDiscount, R.drawable.ic_discount, "Descuentos", true) { startActivity(Intent(requireContext(), DiscountsActivity::class.java)) }
        action(b.actEvidence, R.drawable.ic_camera, "Evidencias", true) { startActivity(Intent(requireContext(), EvidenceActivity::class.java)) }
        action(b.actScan, R.drawable.ic_scan, "Escanear", true) { (activity as? MainActivity)?.openScanner() }

        val adapter = StockAdapter { e -> startActivity(FefoActivity.forSku(requireContext(), e.idSku, e.producto)) }
        b.listExpiring.adapter = adapter
        b.swipe.setOnRefreshListener { vm.load() }
        b.swipe.setColorSchemeResources(R.color.brand_primary)

        viewLifecycleOwner.launchWhenStarted {
            vm.state.collect { st ->
                b.swipe.isRefreshing = st.loading
                setKpi(b.kpiRisk, st.atRisk); setKpi(b.kpiAlerts, st.alerts)
                setKpi(b.kpiTransfers, st.transfers); setKpi(b.kpiDiscounts, st.discounts)
                b.bannerDegraded.isVisible = st.degraded.isNotEmpty() && !st.loading
                b.textDegraded.text = "Servicio degradado: ${st.degraded.joinToString()}. Se muestran los datos disponibles."
                st.esg.let { e ->
                    b.textEsgWaste.text = if (e != null) Fmt.qty(e.evitadoNetoKg, "kg") else "—"
                    b.textEsgCo2.text = if (e != null) Fmt.qty(e.co2eKg, "kg CO₂e") else "—"
                    b.textEsgMoney.text = if (e != null) Fmt.money(e.ahorroMxn) else "—"
                }
                b.textEsgSource.text = when {
                    !st.esgOk -> "Servicio de métricas no disponible"
                    st.esg?.fuente == "redis_cache" -> "Últimos 30 días · desde caché Redis"
                    else -> "Últimos 30 días · PostgreSQL"
                }
                adapter.submitList(st.expiring)
                b.textExpiringEmpty.isVisible = !st.loading && st.expiring.isEmpty()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (!vm.state.value.loading) vm.load()
    }

    private fun kpi(v: ViewKpiBinding, icon: Int, label: String, tint: Int, onClick: () -> Unit) {
        v.kpiIcon.setImageResource(icon)
        v.kpiIcon.setColorFilter(ContextCompat.getColor(requireContext(), tint))
        v.kpiLabel.text = label
        v.root.setOnClickListener { onClick() }
    }

    private fun setKpi(v: ViewKpiBinding, k: Kpi) {
        v.kpiValue.text = k.value ?: if (k.ok) "…" else "—"
        v.kpiHint.isVisible = !k.ok
        v.kpiHint.text = "No disponible"
    }

    private fun action(v: ViewActionBinding, icon: Int, label: String, enabled: Boolean, onClick: () -> Unit) {
        v.actionIcon.setImageResource(icon)
        v.actionLabel.text = label
        v.root.alpha = if (enabled) 1f else 0.4f
        v.root.setOnClickListener {
            if (enabled) onClick()
            else com.google.android.material.snackbar.Snackbar.make(b.root, "Tu rol no puede realizar esta acción", 1500).show()
        }
    }

    private val Int.dp get() = (this * resources.displayMetrics.density).toInt()

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
