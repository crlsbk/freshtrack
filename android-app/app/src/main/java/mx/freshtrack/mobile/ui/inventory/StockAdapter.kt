package mx.freshtrack.mobile.ui.inventory

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import mx.freshtrack.mobile.data.model.Existencia
import mx.freshtrack.mobile.databinding.ItemStockBinding
import mx.freshtrack.mobile.util.Fmt
import mx.freshtrack.mobile.util.Risk

class StockAdapter(private val onClick: (Existencia) -> Unit) :
    ListAdapter<Existencia, StockAdapter.VH>(DIFF) {

    class VH(val b: ItemStockBinding) : RecyclerView.ViewHolder(b.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
        VH(ItemStockBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun onBindViewHolder(h: VH, position: Int) {
        val e = getItem(position)
        val ctx = h.itemView.context
        val risk = Risk.of(e.diasRestantes)
        h.b.textProduct.text = e.producto
        h.b.textLot.text = "Lote ${e.codigoLote ?: e.idLote.take(8)} · ${Fmt.date(e.fechaCaducidad)}"
        h.b.textQty.text = Fmt.qty(e.disponibleNeto ?: e.disponible)
        h.b.textQtyLabel.text = if ((e.reservada ?: 0.0) > 0) "disp. (${Fmt.qty(e.reservada)} res.)" else "disponible"
        h.b.textDays.text = Fmt.days(e.diasRestantes)
        h.b.textDays.setTextColor(ContextCompat.getColor(ctx, risk.color))
        h.b.textDays.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(ctx, risk.container))
        h.b.riskBar.setBackgroundColor(ContextCompat.getColor(ctx, risk.color))
        val blocked = e.estadoLote != null && e.estadoLote != "DISPONIBLE"
        h.b.textStatus.isVisible = blocked
        h.b.textStatus.text = e.estadoLote
        h.itemView.setOnClickListener { onClick(e) }
    }

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<Existencia>() {
            override fun areItemsTheSame(a: Existencia, b: Existencia) = a.idExistencia == b.idExistencia
            override fun areContentsTheSame(a: Existencia, b: Existencia) = a == b
        }
    }
}
