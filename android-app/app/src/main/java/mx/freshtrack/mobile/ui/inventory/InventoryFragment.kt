package mx.freshtrack.mobile.ui.inventory

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.isVisible
import androidx.core.view.updatePadding
import androidx.core.widget.doAfterTextChanged
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.FreshTrackApp
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.Existencia
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.FragmentInventoryBinding
import mx.freshtrack.mobile.ui.common.UiState
import mx.freshtrack.mobile.ui.common.launchWhenStarted
import mx.freshtrack.mobile.ui.common.showError
import mx.freshtrack.mobile.util.Fmt

class InventoryViewModel : ViewModel() {
    private val repo = FreshTrackApp.instance.repository
    private val _state = MutableStateFlow<UiState<List<Existencia>>>(UiState.Loading)
    val state: StateFlow<UiState<List<Existencia>>> = _state
    var diasMax: Int? = null
        private set

    init { load() }

    fun setFilter(dias: Int?) { diasMax = dias; load() }

    fun load() = viewModelScope.launch {
        _state.value = UiState.Loading
        _state.value = when (val r = repo.stock(diasMax = diasMax)) {
            is ApiResult.Ok -> UiState.Success(r.data.existencias)
            is ApiResult.Fail -> UiState.Error(r.error)
        }
    }
}

/** Existencias de la tienda ordenadas FEFO (caducidad más próxima primero) con búsqueda local. */
class InventoryFragment : Fragment() {

    private var _b: FragmentInventoryBinding? = null
    private val b get() = _b!!
    private val vm: InventoryViewModel by viewModels()
    private var all: List<Existencia> = emptyList()
    private lateinit var adapter: StockAdapter

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, s: Bundle?): View {
        _b = FragmentInventoryBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        ViewCompat.setOnApplyWindowInsetsListener(b.appBar) { v, insets ->
            v.updatePadding(top = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top)
            insets
        }
        b.toolbar.subtitle = FreshTrackApp.instance.session.storeName
        adapter = StockAdapter { e -> startActivity(FefoActivity.forSku(requireContext(), e.idSku, e.producto)) }
        b.list.adapter = adapter
        b.swipe.setOnRefreshListener { vm.load() }
        b.swipe.setColorSchemeResources(R.color.brand_primary)
        b.inputSearch.doAfterTextChanged { applyFilter() }
        b.chips.setOnCheckedStateChangeListener { _, ids ->
            vm.setFilter(
                when (ids.firstOrNull()) {
                    R.id.chipExpired -> 0
                    R.id.chipCritical -> 2
                    R.id.chipWatch -> 5
                    else -> null
                }
            )
        }

        viewLifecycleOwner.launchWhenStarted {
            vm.state.collect { st ->
                b.swipe.isRefreshing = st is UiState.Loading
                when (st) {
                    is UiState.Success -> { all = st.data; applyFilter() }
                    is UiState.Error -> {
                        all = emptyList(); applyFilter()
                        b.textEmpty.text = st.error.message
                        b.root.showError(st.error) { vm.load() }
                    }
                    else -> Unit
                }
            }
        }
    }

    private fun applyFilter() {
        val q = b.inputSearch.text?.toString()?.trim()?.lowercase().orEmpty()
        val list = if (q.isEmpty()) all else all.filter {
            it.producto.lowercase().contains(q) || (it.codigoLote?.lowercase()?.contains(q) == true)
        }
        adapter.submitList(list)
        val total = list.sumOf { it.disponibleNeto ?: it.disponible }
        b.textSummary.text = "${list.size} lotes · ${Fmt.qty(total)} unidades"
        b.textEmpty.isVisible = list.isEmpty() && vm.state.value !is UiState.Loading
        if (list.isEmpty() && vm.state.value is UiState.Success) b.textEmpty.text = getString(R.string.empty_generic)
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
