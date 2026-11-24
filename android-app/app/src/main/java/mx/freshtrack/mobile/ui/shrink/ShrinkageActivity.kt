package mx.freshtrack.mobile.ui.shrink

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.ArrayAdapter
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import com.google.android.material.chip.Chip
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.data.model.LoteFefo
import mx.freshtrack.mobile.data.offline.OfflineQueue
import mx.freshtrack.mobile.data.offline.SendOutcome
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.ActivityShrinkageBinding
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.common.ProductSelector
import mx.freshtrack.mobile.ui.common.hideKeyboard
import mx.freshtrack.mobile.ui.common.showError
import mx.freshtrack.mobile.ui.evidence.EvidenceCapture
import mx.freshtrack.mobile.util.Fmt
import java.io.File

/**
 * Registro justificado de merma (svc-commercial POST /shrinkage):
 * descuenta la existencia del lote en la misma transacción, calcula el valor perdido
 * y queda en la bitácora. La foto se sube primero a Cloud Storage y su id se liga a la merma.
 */
class ShrinkageActivity : BaseActivity() {

    private lateinit var b: ActivityShrinkageBinding
    private lateinit var selector: ProductSelector
    private lateinit var camera: EvidenceCapture
    private var lots: List<LoteFefo> = emptyList()
    private var lot: LoteFefo? = null
    private var unit: String? = null
    private var photo: File? = null
    private var idempotencyKey: String? = null

    private val causes = linkedMapOf(
        "CADUCIDAD" to "Caducidad", "DANO" to "Daño", "CALIDAD" to "Calidad",
        "CADENA_DE_FRIO" to "Cadena de frío", "MANIPULACION" to "Manipulación",
        "DEVOLUCION" to "Devolución", "OTRA" to "Otra",
    )
    /** Causas en las que la política de la tienda pide evidencia fotográfica. */
    private val photoRecommended = setOf("DANO", "CALIDAD", "CADENA_DE_FRIO")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityShrinkageBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setupToolbar(b.toolbar, "Registrar merma", session.storeName)

        causes.forEach { (code, label) ->
            b.chipsCause.addView(Chip(this, null, com.google.android.material.R.attr.chipStyle).apply {
                text = label; tag = code; isCheckable = true
                setOnCheckedChangeListener { _, _ -> updatePhotoHint() }
            })
        }
        (b.chipsCause.getChildAt(0) as Chip).isChecked = true

        camera = EvidenceCapture(this) { f -> photo = f; updatePhotoHint() }
        b.btnPhoto.setOnClickListener { camera.launch() }
        b.btnSubmit.setOnClickListener { submit() }
        b.dropdownLot.setOnItemClickListener { _, _, pos, _ -> selectLot(lots[pos]) }

        selector = ProductSelector(this, b.selector) { id, nombre, u -> unit = u; loadLots(id, null) }

        val sku = intent.getIntExtra(EXTRA_SKU, 0)
        if (sku > 0) {
            selector.show(intent.getStringExtra(EXTRA_NAME), "SKU $sku")
            loadLots(sku, intent.getStringExtra(EXTRA_LOT))
        }
        if (!session.role.canRegisterShrinkage) {
            b.btnSubmit.isEnabled = false; b.btnSubmit.text = "Tu rol no puede registrar mermas"
        }
        updatePhotoHint()
    }

    private fun loadLots(sku: Int, preselect: String?) {
        b.progress.isVisible = true
        lifecycleScope.launch {
            when (val r = repo.fefo(sku)) {
                is ApiResult.Ok -> {
                    lots = r.data.lotes
                    b.layoutLot.isEnabled = lots.isNotEmpty()
                    b.layoutLot.helperText = if (lots.isEmpty()) "Sin existencias de este producto en tu tienda" else "Ordenados FEFO"
                    val labels = lots.map { "${it.codigoLote ?: it.idLote.take(8)} · ${Fmt.qty(it.disponible, unit)} · ${Fmt.days(it.diasRestantes)}" }
                    b.dropdownLot.setAdapter(ArrayAdapter(this@ShrinkageActivity, android.R.layout.simple_list_item_1, labels))
                    val pre = lots.indexOfFirst { it.idLote == preselect }.takeIf { it >= 0 } ?: if (lots.isNotEmpty()) 0 else -1
                    if (pre >= 0) { b.dropdownLot.setText(labels[pre], false); selectLot(lots[pre]) }
                }
                is ApiResult.Fail -> b.root.showError(r.error) { loadLots(sku, preselect) }
            }
            b.progress.isVisible = false
        }
    }

    private fun selectLot(l: LoteFefo) {
        lot = l
        b.layoutQty.suffixText = unit
        b.layoutQty.helperText = "Máximo ${Fmt.qty(l.disponible - (l.reservada ?: 0.0), unit)}"
        if ((l.diasRestantes ?: 1) < 0) (b.chipsCause.getChildAt(0) as Chip).isChecked = true
    }

    private fun cause(): String =
        (0 until b.chipsCause.childCount).map { b.chipsCause.getChildAt(it) as Chip }.firstOrNull { it.isChecked }?.tag as? String ?: "OTRA"

    private fun updatePhotoHint() {
        val needs = cause() in photoRecommended
        b.textPhoto.text = when {
            photo != null -> "Foto lista (${photo!!.length() / 1024} KB)"
            needs -> "Se recomienda evidencia fotográfica para esta causa"
            else -> "Evidencia fotográfica (opcional)"
        }
        b.btnPhoto.text = if (photo != null) "Repetir" else "Tomar foto"
    }

    private fun submit() {
        hideKeyboard()
        val l = lot ?: run { b.layoutLot.error = "Selecciona un lote"; return }
        b.layoutLot.error = null
        val qty = b.inputQty.text.toString().replace(",", ".").toDoubleOrNull()
        val max = l.disponible - (l.reservada ?: 0.0)
        if (qty == null || qty <= 0) { b.layoutQty.error = "Cantidad inválida"; return }
        if (qty > max + 1e-6) { b.layoutQty.error = "No puede exceder la existencia (${Fmt.qty(max)})"; return }
        b.layoutQty.error = null
        val c = cause()
        if (c == "OTRA" && b.inputNotes.text.isNullOrBlank()) { b.layoutNotes.error = "Describe la causa"; return }
        b.layoutNotes.error = null

        val value = qty * (l.costoUnitario ?: 0.0)
        MaterialAlertDialogBuilder(this)
            .setTitle("¿Registrar merma?")
            .setMessage("${Fmt.qty(qty, unit)} del lote ${l.codigoLote ?: ""}\nCausa: ${causes[c]}\nValor estimado: ${Fmt.money(value)}\n\nEsta acción descuenta inventario y no se puede deshacer.")
            .setPositiveButton("Registrar") { _, _ -> send(l, qty, c) }
            .setNegativeButton("Cancelar", null).show()
    }

    private fun send(l: LoteFefo, qty: Double, causa: String) {
        b.btnSubmit.isEnabled = false
        b.progress.isVisible = true
        // La Idempotency-Key nace al capturar: reintentar desde esta pantalla o reenviar
        // lo guardado sin conexión nunca registra la merma dos veces.
        val key = idempotencyKey ?: repo.newIdempotencyKey().also { idempotencyKey = it }
        lifecycleScope.launch {
            var evidenceId: String? = null
            var photoSkipped = false
            photo?.let { f ->
                when (val up = repo.uploadEvidence(f, "MERMA", "LOTE", l.idLote, "Merma $causa")) {
                    is ApiResult.Ok -> evidenceId = up.data.idEvidencia
                    is ApiResult.Fail -> {
                        if (SendOutcome.isOffline(up.error)) {
                            photoSkipped = true
                        } else {
                            b.root.showError(up.error)
                        }
                    }
                }
            }
            val obs = b.inputNotes.text?.toString()?.takeIf { it.isNotBlank() }
            val req = repo.shrinkageRequest(l.idLote, qty, causa, obs, evidenceId)
            when (val r = repo.shrinkage(req, key)) {
                is ApiResult.Fail -> if (SendOutcome.isOffline(r.error)) {
                    repo.saveOffline(
                        OfflineQueue.Type.MERMA, req, key,
                        "Merma ${Fmt.qty(qty, unit)} · lote ${l.codigoLote ?: l.idLote.take(8)} (${causes[causa]})",
                    )
                    MaterialAlertDialogBuilder(this@ShrinkageActivity)
                        .setTitle("Guardado sin conexión")
                        .setMessage(
                            "Guardado sin conexión; se enviará al recuperar la red." +
                                (if (photoSkipped) "\n\nLa foto no se pudo subir sin conexión; la merma se enviará sin evidencia." else "")
                        )
                        .setPositiveButton("Entendido") { _, _ -> finish() }
                        .setCancelable(false).show()
                } else {
                    // El servidor respondió (400/409/…): no se registró; la próxima captura lleva llave nueva.
                    idempotencyKey = null
                    b.btnSubmit.isEnabled = true
                    b.root.showError(r.error)
                }
                is ApiResult.Ok -> {
                    idempotencyKey = null
                    val m = r.data
                    MaterialAlertDialogBuilder(this@ShrinkageActivity)
                        .setTitle("Merma registrada")
                        .setMessage(
                            "${m.producto ?: ""} · ${Fmt.qty(m.cantidad, m.unidadMedida)} (${m.causaEtiqueta})\n" +
                                "Valor: ${Fmt.money(m.valorMerma)}\n" +
                                "Existencia restante del lote: ${Fmt.qty(m.existenciaRestante, m.unidadMedida)}" +
                                (if (evidenceId != null) "\nEvidencia ligada: ${evidenceId!!.take(8)}" else "")
                        )
                        .setPositiveButton("Listo") { _, _ -> finish() }
                        .setCancelable(false).show()
                }
            }
            b.progress.isVisible = false
        }
    }

    companion object {
        private const val EXTRA_SKU = "sku"
        private const val EXTRA_NAME = "name"
        private const val EXTRA_LOT = "lot"
        fun intent(ctx: Context, sku: Int, name: String?, idLote: String?, codigo: String?) =
            Intent(ctx, ShrinkageActivity::class.java).putExtra(EXTRA_SKU, sku).putExtra(EXTRA_NAME, name).putExtra(EXTRA_LOT, idLote)
    }
}
