package mx.freshtrack.mobile.ui.transfer

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.widget.ArrayAdapter
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.Locacion
import mx.freshtrack.mobile.data.model.Transferencia
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.ActivityListBinding
import mx.freshtrack.mobile.databinding.DialogTransferRequestBinding
import mx.freshtrack.mobile.ui.common.*
import mx.freshtrack.mobile.ui.inventory.FefoActivity
import mx.freshtrack.mobile.util.Fmt

/**
 * Transferencias entre tiendas (svc-planning):
 *  - Ver sugerencias del motor (excesos que vencen vs. faltantes en otra tienda).
 *  - Solicitar una transferencia manual de un lote (desde FEFO).
 *  - Gerente: aprobar (ajustando cantidad) o rechazar. Gerente/almacén: ejecutar la aprobada,
 *    lo que mueve el inventario y registra el desperdicio evitado.
 */
class TransfersActivity : BaseActivity() {

    private lateinit var b: ActivityListBinding
    private val adapter = TaskAdapter()
    private var filter: String? = "SUGERIDA"
    private var locations: List<Locacion> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityListBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setSupportActionBar(b.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        setupToolbar(b.toolbar, "Transferencias", session.storeName)
        b.list.adapter = adapter
        b.swipe.setOnRefreshListener { load() }
        b.swipe.setColorSchemeResources(R.color.brand_primary)
        b.chips.setupFilters(
            listOf("SUGERIDA" to "Sugeridas", "APROBADA" to "Aprobadas", "EJECUTADA" to "Ejecutadas", "RECHAZADA" to "Rechazadas", null to "Todas"),
            filter,
        ) { filter = it; load() }

        b.fab.isVisible = true
        b.fab.text = "Solicitar"
        b.fab.setIconResource(R.drawable.ic_add)
        b.fab.setOnClickListener {
            MaterialAlertDialogBuilder(this).setTitle("Solicitar transferencia")
                .setMessage("Elige el producto y el lote que quieres enviar a otra tienda en la pantalla FEFO, y toca \"Solicitar transferencia\".")
                .setPositiveButton("Ir a FEFO") { _, _ -> startActivity(Intent(this, FefoActivity::class.java)) }
                .setNegativeButton("Cancelar", null).show()
        }

        lifecycleScope.launch {
            (repo.locations() as? ApiResult.Ok)?.let { locations = it.data.locaciones }
            intent.getStringExtra(EXTRA_LOT)?.let { openRequestDialog(it) }
        }
        load()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        if (session.role.canDetect) menu.add(0, 1, 0, "Detectar oportunidades").setIcon(R.drawable.ic_refresh)
            .setShowAsAction(MenuItem.SHOW_AS_ACTION_IF_ROOM)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == 1) { detect(); return true }
        if (item.itemId == android.R.id.home) { finish(); return true }
        return super.onOptionsItemSelected(item)
    }

    private fun load() {
        b.swipe.isRefreshing = true
        lifecycleScope.launch {
            when (val r = repo.transfers(filter)) {
                is ApiResult.Ok -> {
                    val store = session.storeId
                    val mine = r.data.transferencias.filter { store == null || it.idOrigen == store || it.idDestino == store }
                    adapter.items = mine.map { toItem(it) }
                    b.textEmpty.isVisible = mine.isEmpty()
                    b.textEmpty.text = "No hay transferencias ${filter?.lowercase() ?: ""} para tu tienda"
                    r.data.resumen?.let { s ->
                        b.textSummary.isVisible = true
                        b.textSummary.text = "Red: ${s.sugeridas ?: 0} sugeridas · ${s.aprobadas ?: 0} aprobadas · ${s.ejecutadas ?: 0} ejecutadas · ${Fmt.qty(s.unidadesMovidas)} u. movidas"
                    }
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

    private fun toItem(t: Transferencia): TaskItem {
        val (c, bg) = StateColors.of(t.estado)
        val store = session.storeId
        val outgoing = t.idOrigen == store
        val role = session.role
        var primary: Pair<String, () -> Unit>? = null
        var secondary: Pair<String, () -> Unit>? = null
        when (t.estado) {
            "SUGERIDA" -> if (role.canApproveTransfer && (outgoing || store == null)) {
                primary = "Aprobar" to { approve(t) }
                secondary = "Rechazar" to { decide(t, false) }
            }
            "APROBADA" -> if (role.canExecuteTransfer && (outgoing || store == null)) {
                primary = "Ejecutar envío" to { execute(t) }
            }
        }
        return TaskItem(
            id = t.id,
            title = t.producto ?: "SKU ${t.idSku}",
            subtitle = "${t.origen} → ${t.destino}" + if (outgoing) " · salida" else " · entrada",
            highlight = Fmt.qty(t.cantidad, t.unidadMedida),
            body = listOfNotNull(
                t.motivo,
                t.diasParaVencer?.let { Fmt.days(it) },
                t.solicita?.let { "Solicita: $it" },
                t.aprueba?.let { "Aprueba: $it" },
                t.fechaCreacion?.let { "Creada ${Fmt.date(it)}" },
            ).joinToString("\n"),
            badge = t.estado, badgeColor = c, badgeBg = bg,
            primary = primary, secondary = secondary,
        )
    }

    private fun approve(t: Transferencia) {
        val input = com.google.android.material.textfield.TextInputEditText(this).apply {
            setText(Fmt.qty(t.cantidad).replace(",", ""))
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
        }
        val box = com.google.android.material.textfield.TextInputLayout(this).apply {
            hint = "Cantidad a enviar"; suffixText = t.unidadMedida; setPadding(48, 16, 48, 0); addView(input)
        }
        MaterialAlertDialogBuilder(this).setTitle("Aprobar transferencia")
            .setMessage("${t.producto}: ${t.origen} → ${t.destino}")
            .setView(box)
            .setPositiveButton("Aprobar") { _, _ ->
                val q = input.text.toString().replace(",", ".").toDoubleOrNull()
                if (q == null || q <= 0) b.root.snack("Cantidad inválida") else decide(t, true, q)
            }
            .setNegativeButton("Cancelar", null).show()
    }

    private fun decide(t: Transferencia, approve: Boolean, qty: Double? = null) {
        lifecycleScope.launch {
            val r = if (approve) repo.approveTransfer(t.id, qty) else repo.rejectTransfer(t.id)
            when (r) {
                is ApiResult.Ok -> { b.root.snack(if (approve) "Transferencia aprobada" else "Transferencia rechazada"); load() }
                is ApiResult.Fail -> b.root.showError(r.error)
            }
        }
    }

    private fun execute(t: Transferencia) {
        MaterialAlertDialogBuilder(this).setTitle("¿Ejecutar envío?")
            .setMessage("Se descontarán ${Fmt.qty(t.cantidad, t.unidadMedida)} de ${t.origen} y se sumarán a ${t.destino}.")
            .setPositiveButton("Ejecutar") { _, _ ->
                lifecycleScope.launch {
                    when (val r = repo.executeTransfer(t.id)) {
                        is ApiResult.Ok -> { b.root.snack("Inventario movido · desperdicio evitado registrado"); load() }
                        is ApiResult.Fail -> b.root.showError(r.error)
                    }
                }
            }.setNegativeButton("Cancelar", null).show()
    }

    private fun detect() {
        b.swipe.isRefreshing = true
        lifecycleScope.launch {
            when (val r = repo.detectTransfers(7)) {
                is ApiResult.Ok -> {
                    val total = (r.data["total"] as? Number)?.toInt() ?: 0
                    b.root.snack("Motor de transferencias: $total oportunidades nuevas")
                    filter = "SUGERIDA"; load()
                }
                is ApiResult.Fail -> { b.swipe.isRefreshing = false; b.root.showError(r.error) }
            }
        }
    }

    private fun openRequestDialog(idLote: String) {
        val d = DialogTransferRequestBinding.inflate(layoutInflater)
        val product = intent.getStringExtra(EXTRA_PRODUCT)
        val lotCode = intent.getStringExtra(EXTRA_LOT_CODE)
        val max = intent.getDoubleExtra(EXTRA_MAX, 0.0)
        d.textLot.text = "$product · lote ${lotCode ?: idLote.take(8)} · disponible ${Fmt.qty(max)}"
        val targets = locations.filter { it.idLocacion != session.storeId && it.activo != false }
        d.dropdownDest.setAdapter(ArrayAdapter(this, android.R.layout.simple_list_item_1, targets.map { "${it.nombre} (${it.tipo})" }))
        var dest: Locacion? = null
        d.dropdownDest.setOnItemClickListener { _, _, pos, _ -> dest = targets[pos] }
        MaterialAlertDialogBuilder(this).setTitle("Solicitar transferencia").setView(d.root)
            .setPositiveButton("Enviar solicitud") { _, _ ->
                val q = d.inputQty.text.toString().replace(",", ".").toDoubleOrNull()
                val to = dest
                when {
                    to == null -> b.root.snack("Elige la tienda destino")
                    q == null || q <= 0 || (max > 0 && q > max) -> b.root.snack("Cantidad inválida (máx. ${Fmt.qty(max)})")
                    else -> lifecycleScope.launch {
                        when (val r = repo.requestTransfer(idLote, to.idLocacion, q, d.inputReason.text?.toString())) {
                            is ApiResult.Ok -> { b.root.snack("Solicitud enviada a ${to.nombre}"); filter = "SUGERIDA"; load() }
                            is ApiResult.Fail -> b.root.showError(r.error)
                        }
                    }
                }
            }
            .setNegativeButton("Cancelar", null).show()
    }

    companion object {
        private const val EXTRA_LOT = "lot"
        private const val EXTRA_PRODUCT = "product"
        private const val EXTRA_LOT_CODE = "lot_code"
        private const val EXTRA_MAX = "max"
        fun requestIntent(ctx: Context, idLote: String, product: String?, lotCode: String?, max: Double) =
            Intent(ctx, TransfersActivity::class.java).putExtra(EXTRA_LOT, idLote).putExtra(EXTRA_PRODUCT, product)
                .putExtra(EXTRA_LOT_CODE, lotCode).putExtra(EXTRA_MAX, max)
    }
}
