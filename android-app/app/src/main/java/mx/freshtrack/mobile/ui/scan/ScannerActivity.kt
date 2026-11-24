package mx.freshtrack.mobile.ui.scan

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.VibrationEffect
import android.os.Vibrator
import android.text.InputType
import android.widget.EditText
import android.widget.FrameLayout
import androidx.activity.result.contract.ActivityResultContract
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.OptIn
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.databinding.ActivityScannerBinding
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.util.LabelParser
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Lector de códigos con CameraX + ML Kit (modelo embebido, funciona sin internet).
 * Formatos: QR (etiquetas FT1 firmadas), DataMatrix y Code128 (GS1), EAN-13/8 y UPC (producto).
 * Devuelve el texto crudo; quien lo invoca decide el flujo.
 */
class ScannerActivity : BaseActivity() {

    data class Request(val hint: String, val manualHint: String = "Código de etiqueta o GTIN")

    class Contract : ActivityResultContract<Request, String?>() {
        override fun createIntent(context: Context, input: Request) =
            Intent(context, ScannerActivity::class.java)
                .putExtra(EXTRA_HINT, input.hint)
                .putExtra(EXTRA_MANUAL_HINT, input.manualHint)

        override fun parseResult(resultCode: Int, intent: Intent?): String? =
            if (resultCode == Activity.RESULT_OK) intent?.getStringExtra(EXTRA_RESULT) else null
    }

    private lateinit var b: ActivityScannerBinding
    private lateinit var executor: ExecutorService
    private var camera: Camera? = null
    private val delivered = AtomicBoolean(false)
    private var torchOn = false

    private val permission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startCamera() else {
            b.textHint.text = getString(R.string.permission_camera)
            manualEntry()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityScannerBinding.inflate(layoutInflater)
        setContentView(b.root)
        ViewCompat.setOnApplyWindowInsetsListener(b.root) { _, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            b.topBar.updatePadding(top = bars.top)
            b.bottomBar.updatePadding(bottom = bars.bottom + 16)
            insets
        }
        executor = Executors.newSingleThreadExecutor()
        b.textHint.text = intent.getStringExtra(EXTRA_HINT)
        b.btnClose.setOnClickListener { finish() }
        b.btnManual.setOnClickListener { manualEntry() }
        b.btnTorch.setOnClickListener {
            torchOn = !torchOn
            camera?.cameraControl?.enableTorch(torchOn)
            b.btnTorch.alpha = if (torchOn) 1f else 0.6f
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) startCamera()
        else permission.launch(Manifest.permission.CAMERA)
    }

    @OptIn(ExperimentalGetImage::class)
    private fun startCamera() {
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            val provider = providerFuture.get()
            val preview = Preview.Builder().build().also { it.surfaceProvider = b.preview.surfaceProvider }
            val scanner = BarcodeScanning.getClient(
                BarcodeScannerOptions.Builder().setBarcodeFormats(
                    Barcode.FORMAT_QR_CODE, Barcode.FORMAT_DATA_MATRIX, Barcode.FORMAT_CODE_128,
                    Barcode.FORMAT_EAN_13, Barcode.FORMAT_EAN_8, Barcode.FORMAT_UPC_A,
                ).build()
            )
            // 1280×720 (en vez del 640×480 por defecto): los QR pequeños o en pantalla necesitan resolución.
            val analysis = ImageAnalysis.Builder()
                .setResolutionSelector(
                    androidx.camera.core.resolutionselector.ResolutionSelector.Builder()
                        .setResolutionStrategy(
                            androidx.camera.core.resolutionselector.ResolutionStrategy(
                                android.util.Size(1280, 720),
                                androidx.camera.core.resolutionselector.ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER,
                            )
                        ).build()
                )
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
            analysis.setAnalyzer(executor) { proxy ->
                val media = proxy.image
                if (media == null || delivered.get()) { proxy.close(); return@setAnalyzer }
                val img = InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees)
                scanner.process(img)
                    .addOnSuccessListener { codes ->
                        codes.firstNotNullOfOrNull { it.rawValue?.takeIf { v -> v.isNotBlank() } }?.let { deliver(it) }
                    }
                    .addOnCompleteListener { proxy.close() }
            }
            try {
                provider.unbindAll()
                camera = provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                b.btnTorch.isEnabled = camera?.cameraInfo?.hasFlashUnit() == true
                // Tocar la vista enfoca en ese punto (útil al escanear una pantalla de cerca).
                b.preview.setOnTouchListener { v, ev ->
                    if (ev.action == android.view.MotionEvent.ACTION_UP) {
                        val point = b.preview.meteringPointFactory.createPoint(ev.x, ev.y)
                        camera?.cameraControl?.startFocusAndMetering(FocusMeteringAction.Builder(point).build())
                        v.performClick()
                    }
                    true
                }
            } catch (e: Exception) {
                b.textHint.text = "No se pudo abrir la cámara: ${e.message}"
            }
        }, ContextCompat.getMainExecutor(this))
    }

    private fun deliver(raw: String) {
        if (!delivered.compareAndSet(false, true)) return
        runOnUiThread {
            vibrate()
            val kind = when (LabelParser.parse(raw)) {
                is LabelParser.Parsed.Ft1 -> "Etiqueta FT1 firmada"
                is LabelParser.Parsed.Gs1 -> "Código GS1"
                is LabelParser.Parsed.ShortLabel -> "Folio de etiqueta"
                is LabelParser.Parsed.Gtin -> "Código de producto"
                else -> "Código"
            }
            b.textHint.text = "$kind detectado"
            setResult(Activity.RESULT_OK, Intent().putExtra(EXTRA_RESULT, raw))
            b.root.postDelayed({ finish() }, 250)
        }
    }

    private fun manualEntry() {
        val input = EditText(this).apply {
            hint = intent.getStringExtra(EXTRA_MANUAL_HINT)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            isSingleLine = true
        }
        val box = FrameLayout(this).apply { setPadding(56, 24, 56, 0); addView(input) }
        MaterialAlertDialogBuilder(this)
            .setTitle("Captura manual")
            .setView(box)
            .setPositiveButton("Usar") { _, _ ->
                input.text.toString().trim().takeIf { it.isNotEmpty() }?.let { deliver(it) }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun vibrate() {
        val v = getSystemService(Vibrator::class.java) ?: return
        if (Build.VERSION.SDK_INT >= 26) v.vibrate(VibrationEffect.createOneShot(60, VibrationEffect.DEFAULT_AMPLITUDE))
    }

    override fun onDestroy() {
        super.onDestroy()
        if (::executor.isInitialized) executor.shutdown()
    }

    companion object {
        private const val EXTRA_HINT = "hint"
        private const val EXTRA_MANUAL_HINT = "manual_hint"
        private const val EXTRA_RESULT = "result"
    }
}
