package mx.freshtrack.mobile.ui.count

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.ConteoLinea
import mx.freshtrack.mobile.data.model.LoteFefo
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.ActivityCountBinding
import mx.freshtrack.mobile.databinding.ItemCountLotBinding
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.common.ProductSelector
import mx.freshtrack.mobile.ui.common.hideKeyboard
import mx.freshtrack.mobile.ui.common.showError
import mx.freshtrack.mobile.util.Fmt
import kotlin.math.abs

/**
 * Conteo cíclico por producto: el operador captura lo que hay físicamente en cada lote.
 * svc-inventory compara contra el sistema, genera movimientos de AJUSTE en el kardex
 * para las diferencias y calcula la exactitud del inventario (IRA).
 */
class CountActivity : BaseActivity() {

    private lateinit var b: ActivityCountBinding
    private lateinit var selector: ProductSelector
    private val adapter = CountAdapter { updateSummary() }
    private var sku: Int? = null
    private var unit: String? = null
    private var idempotencyKey = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityCountBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setupToolbar(b.toolbar, "Conteo cíclico", session.storeName)
        b.list.adapter = adapter
        selector = ProductSelector(this, b.selector) { id, _, u -> sku = id; unit = u; load() }
        b.btnSubmit.setOnClickListener { submit() }
        b.btnSubmit.isEnabled = false
        if (!session.role.canCount) b.btnSubmit.text = "Tu rol no puede ajustar inventario"
    }

    private fun load() {
        val id = sku ?: return
        b.progress.isVisible = true
        idempotencyKey = repo.newIdempotencyKey()
        lifecycleScope.launch {
            when (val r = repo.fefo(id)) {
                is ApiResult.Ok -> {
                    adapter.unit = unit
                    adapter.set(r.data.lotes)
                    b.textEmpty.isVisible = r.data.lotes.isEmpty()
                    updateSummary()
                }
                is ApiResult.Fail -> b.root.showError(r.error) { load() }
            }
            b.progress.isVisible = false
        }
    }

    private fun updateSummary() {
        val counted = adapter.counted()
        val diffs = adapter.items.filter { l -> counted[l.idLote]?.let { abs(it - l.disponible) > 1e-6 } == true }
        b.textSummary.isVisible = adapter.items.isNotEmpty()
        b.textSummary.text = "Contados ${counted.size}/${adapter.items.size} lotes · ${diffs.size} con diferencia"
        b.btnSubmit.isEnabled = session.role.canCount && counted.isNotEmpty()
    }

    private fun submit() {
        hideKeyboard()
        val counted = adapter.counted()
        if (counted.isEmpty()) return
        val lines = counted.map { (lote, qty) -> ConteoLinea(lote, qty) }
        val diffs = adapter.items.mapNotNull { l ->
            counted[l.idLote]?.let { c -> if (abs(c - l.disponible) > 1e-6) "${l.codigoLote ?: l.idLote.take(8)}: ${Fmt.qty(l.disponible)} → ${Fmt.qty(c)}" else null }
        }
        MaterialAlertDialogBuilder(this)
            .setTitle("¿Enviar conteo?")
            .setMessage(
                if (diffs.isEmpty()) "Todo coincide con el sistema. Se registrará el conteo sin ajustes."
                else "Se generarán ajustes de inventario:\n\n" + diffs.joinToString("\n")
            )
            .setPositiveButton("Enviar") { _, _ -> send(lines) }
            .setNegativeButton("Revisar", null).show()
    }

    private fun send(lines: List<ConteoLinea>) {
        b.progress.isVisible = true
        b.btnSubmit.isEnabled = false
        lifecycleScope.launch {
            val obs = b.inputNotes.text?.toString()?.takeIf { it.isNotBlank() }
            when (val r = repo.cycleCount(sku, lines, obs, idempotencyKey)) {
                is ApiResult.Ok -> {
                    val c = r.data
                    MaterialAlertDialogBuilder(this@CountActivity)
                        .setTitle("Conteo registrado")
                        .setMessage(
                            "Exactitud del inventario: ${c.exactitudPct?.let { "%.1f %%".format(it) } ?: "—"}\n" +
                                "Lotes contados: ${c.lineasContadas ?: lines.size}\n" +
                                "Ajustes aplicados: ${c.lineasConDiferencia ?: 0}" +
                                (c.ajustes?.takeIf { it.isNotEmpty() }?.joinToString("\n", prefix = "\n\n") {
                                    "${it.codigoLote ?: it.idLote.take(8)}: ${if (it.diferencia >= 0) "+" else ""}${Fmt.qty(it.diferencia)}"
                                } ?: "")
                        )
                        .setPositiveButton("Listo") { _, _ -> load() }.show()
                }
                is ApiResult.Fail -> { b.btnSubmit.isEnabled = true; b.root.showError(r.error) }
            }
            b.progress.isVisible = false
        }
    }

    class CountAdapter(private val onChange: () -> Unit) : RecyclerView.Adapter<CountAdapter.VH>() {
        var unit: String? = null
        var items: List<LoteFefo> = emptyList()
            private set
        private val values = mutableMapOf<String, Double>()

        fun set(list: List<LoteFefo>) { items = list; values.clear(); notifyDataSetChanged() }
        fun counted(): Map<String, Double> = values.toMap()

        class VH(val b: ItemCountLotBinding) : RecyclerView.ViewHolder(b.root) { var watcher: TextWatcher? = null }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
            VH(ItemCountLotBinding.inflate(LayoutInflater.from(parent.context), parent, false))

        override fun getItemCount() = items.size

        override fun onBindViewHolder(h: VH, position: Int) {
            val l = items[position]
            h.b.textLot.text = "Lote ${l.codigoLote ?: l.idLote.take(8)}"
            h.b.textSystem.text = "Sistema: ${Fmt.qty(l.disponible, unit)} · ${Fmt.days(l.diasRestantes)}"
            h.watcher?.let { h.b.inputCount.removeTextChangedListener(it) }
            h.b.inputCount.setText(values[l.idLote]?.let { Fmt.qty(it).replace(",", "") } ?: "")
            renderDiff(h, l)
            h.b.btnMatch.setOnClickListener {
                h.b.inputCount.setText(Fmt.qty(l.disponible).replace(",", ""))
            }
            h.watcher = object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, c: Int, d: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, c: Int, d: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    val v = s?.toString()?.replace(",", ".")?.toDoubleOrNull()
                    if (v != null && v >= 0) values[l.idLote] = v else values.remove(l.idLote)
                    renderDiff(h, l); onChange()
                }
            }
            h.b.inputCount.addTextChangedListener(h.watcher)
        }

        private fun renderDiff(h: VH, l: LoteFefo) {
            val ctx = h.itemView.context
            val v = values[l.idLote]
            if (v == null) { h.b.textDiff.text = "Sin contar"; h.b.textDiff.setTextColor(ContextCompat.getColor(ctx, R.color.on_surface_muted)); return }
            val d = v - l.disponible
            h.b.textDiff.text = when {
                abs(d) < 1e-6 -> "Coincide"
                d > 0 -> "Sobrante +${Fmt.qty(d)}"
                else -> "Faltante ${Fmt.qty(d)}"
            }
            h.b.textDiff.setTextColor(ContextCompat.getColor(ctx, if (abs(d) < 1e-6) R.color.risk_ok else R.color.risk_critical))
        }
    }
}
