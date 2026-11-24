package mx.freshtrack.mobile.ui.common

import android.content.res.ColorStateList
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.annotation.ColorRes
import androidx.core.content.ContextCompat
import androidx.core.view.isVisible
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.chip.Chip
import com.google.android.material.chip.ChipGroup
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.databinding.ItemTaskBinding

/** Tarjeta genérica de "tarea" (transferencia, descuento, alerta) con hasta dos acciones. */
data class TaskItem(
    val id: String,
    val title: String,
    val subtitle: String?,
    val highlight: String?,
    val body: String?,
    val badge: String,
    @ColorRes val badgeColor: Int,
    @ColorRes val badgeBg: Int,
    val primary: Pair<String, () -> Unit>? = null,
    val secondary: Pair<String, () -> Unit>? = null,
)

class TaskAdapter : RecyclerView.Adapter<TaskAdapter.VH>() {
    var items: List<TaskItem> = emptyList()
        set(v) { field = v; notifyDataSetChanged() }

    class VH(val b: ItemTaskBinding) : RecyclerView.ViewHolder(b.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
        VH(ItemTaskBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun getItemCount() = items.size

    override fun onBindViewHolder(h: VH, position: Int) {
        val t = items[position]
        val ctx = h.itemView.context
        h.b.textTitle.text = t.title
        h.b.textSubtitle.text = t.subtitle
        h.b.textSubtitle.isVisible = !t.subtitle.isNullOrBlank()
        h.b.textHighlight.text = t.highlight
        h.b.textHighlight.isVisible = !t.highlight.isNullOrBlank()
        h.b.textBody.text = t.body
        h.b.textBody.isVisible = !t.body.isNullOrBlank()
        h.b.textBadge.text = t.badge
        h.b.textBadge.setTextColor(ContextCompat.getColor(ctx, t.badgeColor))
        h.b.textBadge.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(ctx, t.badgeBg))
        h.b.btnPrimary.isVisible = t.primary != null
        h.b.btnSecondary.isVisible = t.secondary != null
        h.b.actions.isVisible = t.primary != null || t.secondary != null
        t.primary?.let { (label, fn) -> h.b.btnPrimary.text = label; h.b.btnPrimary.setOnClickListener { fn() } }
        t.secondary?.let { (label, fn) -> h.b.btnSecondary.text = label; h.b.btnSecondary.setOnClickListener { fn() } }
    }
}

fun ChipGroup.setupFilters(options: List<Pair<String?, String>>, selected: String?, onSelect: (String?) -> Unit) {
    removeAllViews()
    options.forEach { (value, label) ->
        val chip = Chip(context, null, com.google.android.material.R.attr.chipStyle).apply {
            text = label; isCheckable = true; tag = value ?: ""
            isChecked = value == selected
        }
        addView(chip)
    }
    setOnCheckedStateChangeListener { group, ids ->
        val c = ids.firstOrNull()?.let { group.findViewById<Chip>(it) } ?: return@setOnCheckedStateChangeListener
        onSelect((c.tag as String).ifEmpty { null })
    }
}

object StateColors {
    fun of(estado: String?): Pair<Int, Int> = when (estado?.uppercase()) {
        "SUGERIDA", "SUGERIDO", "WARNING" -> R.color.risk_watch to R.color.risk_watch_bg
        "APROBADA", "APROBADO", "INFO" -> R.color.brand_primary to R.color.brand_primary_container
        "EJECUTADA", "APLICADO" -> R.color.risk_ok to R.color.risk_ok_bg
        "RECHAZADA", "RECHAZADO", "CANCELADA", "CRITICAL" -> R.color.risk_critical to R.color.risk_critical_bg
        else -> R.color.on_surface_muted to R.color.outline
    }
}
