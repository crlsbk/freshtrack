package mx.freshtrack.mobile.ui.receive

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import com.google.android.material.datepicker.MaterialDatePicker
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.EtiquetaInfo
import mx.freshtrack.mobile.data.model.ReceiveScanRequest
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.ActivityReceiveBinding
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.common.errorDialog
import mx.freshtrack.mobile.ui.common.hideKeyboard
import mx.freshtrack.mobile.ui.common.showError
import mx.freshtrack.mobile.ui.common.snack
import mx.freshtrack.mobile.ui.evidence.EvidenceCapture
import mx.freshtrack.mobile.ui.scan.ScannerActivity
import mx.freshtrack.mobile.util.Fmt
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

/**
 * Recepción en muelle de tienda:
 *  1. Escanear la etiqueta del ASN (QR FT1 firmado con HMAC, GS1-128 o folio FTL).
 *  2. svc-asn valida firma y destino y devuelve lo declarado por el proveedor.
 *  3. El operador captura cantidad real, caducidad verificada, temperatura e inspección.
 *  4. svc-inventory crea el lote/existencia de forma idempotente (Idempotency-Key),
 *     actualiza la OC y deja todo en la bitácora de auditoría.
 */
class ReceiveActivity : BaseActivity() {

    private lateinit var b: ActivityReceiveBinding
    private var raw: String? = null
    private var label: EtiquetaInfo? = null
    private var expiry: LocalDate? = null
    private var photo: File? = null
    /** Se conserva durante toda la pantalla: si el usuario reintenta, el backend no duplica la recepción. */
    private val idempotencyKey by lazy { repo.newIdempotencyKey() }

    private val scan = registerForActivityResult(ScannerActivity.Contract()) { code ->
        if (code != null) lookup(code) else if (raw == null) finish()
    }
    private lateinit var camera: EvidenceCapture

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityReceiveBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setupToolbar(b.toolbar, "Recepción de mercancía", session.storeName)
        camera = EvidenceCapture(this) { f -> photo = f; renderPhoto() }

        b.btnRescan.setOnClickListener { openScanner() }
        b.inputExpiry.setOnClickListener { pickDate() }
        b.btnPhoto.setOnClickListener { camera.launch() }
        b.btnSubmit.setOnClickListener { submit() }
        b.chipsAction.setOnCheckedStateChangeListener { _, _ -> updateQtyRequirement() }

        if (!session.role.canReceive) {
            b.btnSubmit.isEnabled = false
            b.btnSubmit.text = "Tu rol no puede recibir mercancía"
        }

        val initial = intent.getStringExtra(EXTRA_CODE)
        if (initial != null) lookup(initial) else if (savedInstanceState == null) openScanner()
    }

    private fun openScanner() = scan.launch(ScannerActivity.Request("Escanea la etiqueta QR del lote (ASN)", "FTL-AAMMDD-XXXXXX"))

    private fun lookup(code: String) {
        raw = code
        b.progress.isVisible = true
        b.cardLabel.isVisible = false
        b.formCard.isVisible = false
        b.cardResult.isVisible = false
        lifecycleScope.launch {
            when (val r = repo.label(code)) {
                is ApiResult.Ok -> showLabel(r.data)
                is ApiResult.Fail -> {
                    b.textScanState.isVisible = true
                    b.textScanState.text = r.error.message
                    errorDialog("Etiqueta no válida", r.error) { lookup(code) }
                }
            }
            b.progress.isVisible = false
        }
    }

    private fun showLabel(l: EtiquetaInfo) {
        label = l
        b.textScanState.isVisible = false
        b.cardLabel.isVisible = true
        b.formCard.isVisible = true
        b.textLabelProduct.text = l.producto ?: "SKU ${l.idSku}"
        b.textLabelCode.text = l.codigoEtiqueta
        b.textLabelOc.text = listOfNotNull(l.folioOc?.let { "OC $it" }, l.folioAsn?.let { "ASN $it" }).joinToString(" · ")
        b.textLabelSupplier.text = l.proveedor ?: "—"
        b.textLabelLot.text = l.loteProveedor ?: "—"
        b.textLabelDeclared.text = Fmt.qty(l.cantidadDeclarada, l.unidadMedida)
        b.textLabelExpiry.text = "${Fmt.date(l.fechaCaducidad)} (${Fmt.days(l.diasRestantes).lowercase()})"
        b.textLabelTemp.text = l.rangoTemperatura ?: "—"
        b.textLabelSignature.text = if (l.firmaValida == true) "Firma HMAC verificada" else "Sin firma (folio/GS1)"
        b.textLabelSignature.setCompoundDrawablesRelativeWithIntrinsicBounds(
            if (l.firmaValida == true) R.drawable.ic_shield else R.drawable.ic_warning, 0, 0, 0
        )

        val warnings = buildList {
            if (l.yaRecibida == true) add("Esta etiqueta ya se recibió. Reenviar no duplicará el inventario.")
            if (l.alertaDestinoIncorrecto == true) add("El lote está destinado a ${l.locacionDestino ?: "otra sucursal"}, no a tu tienda.")
            if (l.alertaVidaUtilBaja == true) add("Vida útil restante baja (${l.vidaUtilPct?.toInt() ?: 0}%). Considera cuarentena o rechazo.")
        }
        b.boxWarnings.isVisible = warnings.isNotEmpty()
        b.textWarnings.text = warnings.joinToString("\n• ", prefix = "• ")

        b.inputQty.setText(l.cantidadDeclarada?.let { Fmt.qty(it).replace(",", "") } ?: "")
        b.layoutQty.suffixText = l.unidadMedida
        expiry = l.fechaCaducidad?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() }
        b.inputExpiry.setText(expiry?.toString() ?: "")
        b.layoutTemp.helperText = "Rango esperado: ${l.rangoTemperatura ?: "2C a 6C"}"
    }

    private fun pickDate() {
        val sel = (expiry ?: LocalDate.now()).atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli()
        val picker = MaterialDatePicker.Builder.datePicker()
            .setTitleText("Caducidad impresa en el empaque")
            .setSelection(sel).build()
        picker.addOnPositiveButtonClickListener { ms ->
            expiry = Instant.ofEpochMilli(ms).atZone(ZoneOffset.UTC).toLocalDate()
            b.inputExpiry.setText(expiry.toString())
            val declared = label?.fechaCaducidad?.take(10)
            b.layoutExpiry.helperText =
                if (declared != null && declared != expiry.toString()) "Difiere de lo declarado ($declared): se registrará la verificada"
                else null
        }
        picker.show(supportFragmentManager, "date")
    }

    private fun accion(): String = when (b.chipsAction.checkedChipId) {
        R.id.chipQuarantine -> "ACEPTAR_CUARENTENA"
        R.id.chipReject -> "RECHAZAR_MUELLE"
        else -> "ACEPTAR_DISPONIBLE"
    }

    private fun inspeccion(): String = when (b.chipsInspection.checkedChipId) {
        R.id.chipNonConform -> "NO_CONFORME"
        R.id.chipObservations -> "CONFORME_CON_OBSERVACIONES"
        else -> "CONFORME"
    }

    private fun updateQtyRequirement() {
        b.layoutQty.helperText = if (accion() == "RECHAZAR_MUELLE") "Rechazo total en muelle: la cantidad puede ser 0" else null
    }

    private fun renderPhoto() {
        b.textPhoto.text = photo?.let { "Foto lista (${it.length() / 1024} KB) · se subirá al bucket al confirmar" } ?: "Opcional: foto del producto o del termómetro"
        b.btnPhoto.text = if (photo != null) "Repetir foto" else "Tomar foto"
    }

    private fun submit() {
        hideKeyboard()
        val l = label ?: return
        val code = raw ?: return
        val qty = b.inputQty.text.toString().replace(",", ".").toDoubleOrNull()
        val acc = accion()
        if (qty == null || qty < 0 || (qty == 0.0 && acc != "RECHAZAR_MUELLE")) {
            b.layoutQty.error = "Cantidad inválida"; return
        }
        b.layoutQty.error = null
        val temp = b.inputTemp.text.toString().replace(",", ".").takeIf { it.isNotBlank() }?.toDoubleOrNull()
        if (b.inputTemp.text?.isNotBlank() == true && temp == null) { b.layoutTemp.error = "Temperatura inválida"; return }
        b.layoutTemp.error = null
        val store = session.storeId ?: run { b.root.snack("Tu usuario no tiene tienda asignada"); return }

        val req = ReceiveScanRequest(
            codigoQrCrudo = code,
            idLocacion = store,
            cantidadRecibida = qty,
            fechaCaducidadVerificada = expiry?.toString(),
            temperatura = temp,
            resultadoInspeccion = inspeccion(),
            accionCalidad = acc,
            medioLectura = if (code.startsWith("FT1|")) "QR" else "MANUAL",
            observaciones = b.inputNotes.text?.toString()?.takeIf { it.isNotBlank() },
        )
        val diff = (l.cantidadDeclarada ?: qty) - qty
        val confirmMsg = buildString {
            append("${Fmt.qty(qty, l.unidadMedida)} de ${l.producto}\n")
            append("Acción: ${acc.replace('_', ' ').lowercase()}\n")
            if (diff > 0.001) append("\nFaltante vs. declarado: ${Fmt.qty(diff, l.unidadMedida)} (se notificará discrepancia al comprador)")
        }
        MaterialAlertDialogBuilder(this).setTitle("¿Confirmar recepción?").setMessage(confirmMsg)
            .setPositiveButton("Recibir") { _, _ -> send(req) }
            .setNegativeButton("Revisar", null).show()
    }

    private fun send(req: ReceiveScanRequest) {
        b.btnSubmit.isEnabled = false
        b.progress.isVisible = true
        lifecycleScope.launch {
            when (val r = repo.receive(req, idempotencyKey)) {
                is ApiResult.Ok -> {
                    val res = r.data
                    var evidenceMsg = ""
                    photo?.let { f ->
                        evidenceMsg = when (val up = repo.uploadEvidence(f, "RECEPCION", "LOTE", res.idLote, "Recepción ${res.codigoEtiqueta}")) {
                            is ApiResult.Ok -> "\nEvidencia guardada en el bucket (${up.data.idEvidencia.take(8)})."
                            is ApiResult.Fail -> "\nLa recepción se guardó, pero la foto no se pudo subir: ${up.error.message}"
                        }
                    }
                    b.formCard.isVisible = false
                    b.cardResult.isVisible = true
                    b.textResultTitle.text = if (res.idempotente == true) "Recepción ya registrada" else "Recepción registrada"
                    b.textResultBody.text = buildString {
                        append("${res.producto} · ${Fmt.qty(res.recibida, res.unidadMedida)} de ${Fmt.qty(res.esperada, res.unidadMedida)}\n")
                        append("Lote ${res.idLote?.take(8) ?: "—"} · ${if (res.elegibleFefo == true) "disponible en FEFO" else "fuera de FEFO (${res.accionCalidad})"}\n")
                        res.estadoOc?.let { append("Orden de compra: $it") }
                        append(evidenceMsg)
                    }
                    b.btnNext.setOnClickListener { recreateForNext() }
                    b.btnDone.setOnClickListener { finish() }
                }
                is ApiResult.Fail -> {
                    b.btnSubmit.isEnabled = true
                    b.root.showError(r.error) { send(req) }
                }
            }
            b.progress.isVisible = false
        }
    }

    private fun recreateForNext() {
        startActivity(intent(this, null)); finish()
    }

    companion object {
        private const val EXTRA_CODE = "code"
        fun intent(ctx: Context, code: String?) = Intent(ctx, ReceiveActivity::class.java).putExtra(EXTRA_CODE, code)
    }
}
