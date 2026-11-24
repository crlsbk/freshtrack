package mx.freshtrack.mobile.ui.inventory

import android.content.Context
import android.content.Intent
import android.content.res.ColorStateList
import android.os.Bundle
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.LoteFefo
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.ActivityFefoBinding
import mx.freshtrack.mobile.databinding.ItemFefoLotBinding
import mx.freshtrack.mobile.databinding.SheetLotActionsBinding
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.common.ProductSelector
import mx.freshtrack.mobile.ui.common.showError
import mx.freshtrack.mobile.ui.common.snack
import mx.freshtrack.mobile.ui.shrink.ShrinkageActivity
import mx.freshtrack.mobile.ui.transfer.TransfersActivity
import mx.freshtrack.mobile.util.Fmt
import mx.freshtrack.mobile.util.Risk

/**
 * Consulta FEFO (First Expired, First Out): orden de surtido de los lotes de un producto
 * en la tienda, calculado por svc-inventory. El primer lote es el que debe salir primero.
 */
class FefoActivity : BaseActivity() {

    private lateinit var b: ActivityFefoBinding
    private lateinit var selector: ProductSelector
    private val adapter = LotAdapter { lot, index -> openLotActions(lot, index) }
    private var sku: Int? = null
    private var productName: String? = null
    private var unit: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityFefoBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setupToolbar(b.toolbar, "Consultar FEFO", session.storeName)
        b.list.adapter = adapter
        b.swipe.setOnRefreshListener { load() }
        b.swipe.setColorSchemeResources(R.color.brand_primary)

        selector = ProductSelector(this, b.selector) { id, nombre, u ->
            sku = id; productName = nombre; unit = u; load()
        }

        val preSku = intent.getIntExtra(EXTRA_SKU, 0).takeIf { it > 0 }
        val gtin = intent.getStringExtra(EXTRA_GTIN)
        when {
            preSku != null -> {
                sku = preSku; productName = intent.getStringExtra(EXTRA_NAME)
                selector.show(productName, "SKU $preSku"); load()
            }
            gtin != null -> lifecycleScope.launch { selector.findByGtin(gtin) }
            else -> b.textEmpty.apply { isVisible = true; text = "Escanea o busca un producto para ver su orden FEFO" }
        }
    }

    private fun load() {
        val id = sku ?: return
        b.swipe.isRefreshing = true
        lifecycleScope.launch {
            when (val r = repo.fefo(id)) {
                is ApiResult.Ok -> {
                    val lots = r.data.lotes
                    adapter.items = lots; adapter.unit = unit
                    val total = lots.sumOf { it.disponible - (it.reservada ?: 0.0) }
                    b.textSummary.isVisible = true
                    b.textSummary.text = "${lots.size} lotes · ${Fmt.qty(total, unit)} disponibles"
                    b.textEmpty.isVisible = lots.isEmpty()
                    b.textEmpty.text = "No hay existencias de este producto en tu tienda"
                }
                is ApiResult.Fail -> {
                    adapter.items = emptyList()
                    b.textEmpty.isVisible = true; b.textEmpty.text = r.error.message
                    b.root.showError(r.error) { load() }
                }
            }
            b.swipe.isRefreshing = false
        }
    }

    private fun openLotActions(lot: LoteFefo, index: Int) {
        val sheet = BottomSheetDialog(this)
        val s = SheetLotActionsBinding.inflate(layoutInflater)
        s.textTitle.text = "Lote ${lot.codigoLote ?: lot.idLote.take(8)}"
        s.textSubtitle.text = "${productName ?: ""} · ${Fmt.qty(lot.disponible, unit)} · ${Fmt.days(lot.diasRestantes)}"
        val role = session.role
        s.actShrink.isVisible = role.canRegisterShrinkage
        s.actQuarantine.isVisible = role.canReceive && lot.estado == "DISPONIBLE"
        s.actRelease.isVisible = role.canReceive && lot.estado != "DISPONIBLE"
        s.actShrink.setOnClickListener {
            sheet.dismiss()
            startActivity(ShrinkageActivity.intent(this, sku!!, productName, lot.idLote, lot.codigoLote))
        }
        s.actTransfer.setOnClickListener {
            sheet.dismiss()
            startActivity(TransfersActivity.requestIntent(this, lot.idLote, productName, lot.codigoLote, lot.disponible))
        }
        s.actQuarantine.setOnClickListener { sheet.dismiss(); changeStatus(lot, "CUARENTENA") }
        s.actRelease.setOnClickListener { sheet.dismiss(); changeStatus(lot, "DISPONIBLE") }
        sheet.setContentView(s.root)
        sheet.show()
    }

    private fun changeStatus(lot: LoteFefo, estado: String) {
        MaterialAlertDialogBuilder(this)
            .setTitle(if (estado == "CUARENTENA") "¿Poner en cuarentena?" else "¿Liberar lote?")
            .setMessage(
                if (estado == "CUARENTENA") "El lote dejará de surtirse en FEFO hasta que se libere."
                else "El lote volverá a la cola FEFO."
            )
            .setPositiveButton("Confirmar") { _, _ ->
                lifecycleScope.launch {
                    when (val r = repo.changeBatchStatus(lot.idLote, estado, "Cambio desde app móvil")) {
                        is ApiResult.Ok -> { b.root.snack("Lote ${r.data.estadoAnterior} → ${r.data.estado}"); load() }
                        is ApiResult.Fail -> b.root.showError(r.error)
                    }
                }
            }
            .setNegativeButton("Cancelar", null).show()
    }

    class LotAdapter(private val onClick: (LoteFefo, Int) -> Unit) : RecyclerView.Adapter<LotAdapter.VH>() {
        var unit: String? = null
        var items: List<LoteFefo> = emptyList()
            set(v) { field = v; notifyDataSetChanged() }

        class VH(val b: ItemFefoLotBinding) : RecyclerView.ViewHolder(b.root)

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
            VH(ItemFefoLotBinding.inflate(LayoutInflater.from(parent.context), parent, false))

        override fun getItemCount() = items.size

        override fun onBindViewHolder(h: VH, i: Int) {
            val l = items[i]
            val ctx = h.itemView.context
            val risk = Risk.of(l.diasRestantes)
            h.b.textOrder.text = "${i + 1}º"
            h.b.textOrder.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(ctx, if (i == 0) R.color.brand_primary else R.color.outline))
            h.b.textOrder.setTextColor(ContextCompat.getColor(ctx, if (i == 0) R.color.brand_on_primary else R.color.on_surface))
            h.b.textLot.text = "Lote ${l.codigoLote ?: l.idLote.take(8)}"
            h.b.textExpiry.text = "Caduca ${Fmt.date(l.fechaCaducidad)}"
            h.b.textDays.text = Fmt.days(l.diasRestantes)
            h.b.textDays.setTextColor(ContextCompat.getColor(ctx, risk.color))
            h.b.textDays.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(ctx, risk.container))
            h.b.textQty.text = Fmt.qty(l.disponible - (l.reservada ?: 0.0), unit)
            h.b.textFirst.isVisible = i == 0
            h.b.textState.isVisible = l.estado != null && l.estado != "DISPONIBLE"
            h.b.textState.text = l.estado
            h.itemView.setOnClickListener { onClick(l, i) }
        }
    }

    companion object {
        private const val EXTRA_SKU = "sku"
        private const val EXTRA_NAME = "name"
        private const val EXTRA_GTIN = "gtin"
        fun forSku(ctx: Context, sku: Int, name: String?) =
            Intent(ctx, FefoActivity::class.java).putExtra(EXTRA_SKU, sku).putExtra(EXTRA_NAME, name)
        fun forGtin(ctx: Context, gtin: String) = Intent(ctx, FefoActivity::class.java).putExtra(EXTRA_GTIN, gtin)
    }
}
