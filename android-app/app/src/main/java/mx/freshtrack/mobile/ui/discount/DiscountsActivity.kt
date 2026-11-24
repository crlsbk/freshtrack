package mx.freshtrack.mobile.ui.discount

import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.Descuento
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.ActivityListBinding
import mx.freshtrack.mobile.ui.common.*
import mx.freshtrack.mobile.util.Fmt

/**
 * Descuentos preventivos por vencimiento (svc-planning). El motor propone un % que respeta
 * el costo piso; el gerente lo autoriza en piso de venta ("aplicar descuento autorizado").
 * Al aprobarse se da de alta el seguimiento en analitica.desperdicio_evitado.
 */
class DiscountsActivity : BaseActivity() {

    private lateinit var b: ActivityListBinding
    private val adapter = TaskAdapter()
    private var filter: String? = "SUGERIDO"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityListBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setSupportActionBar(b.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        setupToolbar(b.toolbar, "Descuentos por vencimiento", session.storeName)
        b.list.adapter = adapter
        b.swipe.setOnRefreshListener { load() }
        b.swipe.setColorSchemeResources(R.color.brand_primary)
        b.chips.setupFilters(
            listOf("SUGERIDO" to "Por autorizar", "APROBADO" to "Autorizados", "RECHAZADO" to "Rechazados", null to "Todos"),
            filter,
        ) { filter = it; load() }
        load()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        if (session.role.canDetect) menu.add(0, 1, 0, "Generar sugerencias").setIcon(R.drawable.ic_refresh)
            .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == 1) { generate(); return true }
        if (item.itemId == android.R.id.home) { finish(); return true }
        return super.onOptionsItemSelected(item)
    }

    private fun load() {
        b.swipe.isRefreshing = true
        lifecycleScope.launch {
            when (val r = repo.discounts(filter)) {
                is ApiResult.Ok -> {
                    val store = session.storeId
                    val mine = r.data.descuentos.filter { store == null || it.idLocacion == store }
                    adapter.items = mine.map { toItem(it) }
                    b.textEmpty.isVisible = mine.isEmpty()
                    b.textEmpty.text = "No hay descuentos ${filter?.lowercase() ?: ""} en tu tienda"
                    val pot = mine.sumOf { it.ingresoPotencial ?: 0.0 }
                    b.textSummary.isVisible = mine.isNotEmpty()
                    b.textSummary.text = "${mine.size} descuentos · ingreso recuperable ${Fmt.money(pot)} · ${Fmt.qty(mine.sumOf { it.cantidad ?: 0.0 })} u. que no se tirarán"
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

    private fun toItem(d: Descuento): TaskItem {
        val (c, bg) = StateColors.of(d.estado)
        val canDecide = session.role.canApproveDiscount && d.estado == "SUGERIDO"
        return TaskItem(
            id = d.id,
            title = d.producto ?: "Producto",
            subtitle = listOfNotNull(d.codigoLote?.let { "Lote $it" }, Fmt.days(d.diasRestantes)).joinToString(" · "),
            highlight = "-${d.descuentoPct?.let { "%.0f".format(it) } ?: "?"}%  ${Fmt.money(d.precioNuevo)}",
            body = "Antes ${Fmt.money(d.precioNormal)} · ${Fmt.qty(d.cantidad, d.unidadMedida)} · recupera ${Fmt.money(d.ingresoPotencial)}" +
                (d.aprueba?.let { "\nAutorizó: $it" } ?: ""),
            badge = d.estado, badgeColor = c, badgeBg = bg,
            primary = if (canDecide) "Autorizar" to { decide(d, true) } else null,
            secondary = if (canDecide) "Rechazar" to { decide(d, false) } else null,
        )
    }

    private fun decide(d: Descuento, approve: Boolean) {
        MaterialAlertDialogBuilder(this)
            .setTitle(if (approve) "¿Autorizar descuento?" else "¿Rechazar descuento?")
            .setMessage(
                if (approve) "${d.producto}: ${Fmt.money(d.precioNormal)} → ${Fmt.money(d.precioNuevo)}\nCambia la etiqueta de precio en anaquel después de autorizar."
                else "El lote seguirá a precio normal y podría terminar en merma."
            )
            .setPositiveButton(if (approve) "Autorizar" else "Rechazar") { _, _ ->
                lifecycleScope.launch {
                    val r = if (approve) repo.approveDiscount(d.id) else repo.rejectDiscount(d.id)
                    when (r) {
                        is ApiResult.Ok -> { b.root.snack(if (approve) "Descuento autorizado" else "Descuento rechazado"); load() }
                        is ApiResult.Fail -> b.root.showError(r.error)
                    }
                }
            }
            .setNegativeButton("Cancelar", null).show()
    }

    private fun generate() {
        b.swipe.isRefreshing = true
        lifecycleScope.launch {
            when (val r = repo.generateDiscounts(5)) {
                is ApiResult.Ok -> { b.root.snack("Sugerencias generadas: ${(r.data["total"] as? Number)?.toInt() ?: 0}"); filter = "SUGERIDO"; load() }
                is ApiResult.Fail -> { b.swipe.isRefreshing = false; b.root.showError(r.error) }
            }
        }
    }
}
