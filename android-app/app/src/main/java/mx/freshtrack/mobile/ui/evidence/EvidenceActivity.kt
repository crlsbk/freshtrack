package mx.freshtrack.mobile.ui.evidence

import android.graphics.BitmapFactory
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.ImageView
import androidx.core.view.isVisible
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.data.model.Evidencia
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.ActivityListBinding
import mx.freshtrack.mobile.databinding.DialogEvidenceBinding
import mx.freshtrack.mobile.ui.common.*
import mx.freshtrack.mobile.util.Fmt
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Evidencias fotográficas en Google Cloud Storage.
 * La BD solo guarda metadatos (ruta, tipo, tamaño, hash SHA-256, propietario, fecha);
 * el archivo vive en un bucket privado y se ve con una URL firmada V4 de vida corta.
 * La descarga usa un cliente HTTP SIN el JWT: la URL firmada ya es la autorización.
 */
class EvidenceActivity : BaseActivity() {

    private lateinit var b: ActivityListBinding
    private val adapter = TaskAdapter()
    private lateinit var camera: EvidenceCapture
    private val plainHttp by lazy { OkHttpClient.Builder().callTimeout(30, TimeUnit.SECONDS).build() }

    private val tipos = linkedMapOf("ANAQUEL" to "Anaquel / exhibición", "MERMA" to "Merma", "RECEPCION" to "Recepción", "TEMPERATURA" to "Temperatura", "OTRO" to "Otro")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityListBinding.inflate(layoutInflater)
        setContentView(b.root)
        applyInsets(b.root, b.toolbar)
        setupToolbar(b.toolbar, "Evidencias", session.storeName)
        b.list.adapter = adapter
        b.swipe.setOnRefreshListener { load() }
        b.swipe.setColorSchemeResources(R.color.brand_primary)
        b.textSummary.isVisible = true
        b.textSummary.text = "Las fotos se guardan en un bucket privado de Cloud Storage. Al abrirlas se genera una URL firmada que expira en minutos."
        camera = EvidenceCapture(this) { f -> askMetadata(f) }
        b.fab.isVisible = true
        b.fab.text = "Nueva evidencia"
        b.fab.setIconResource(R.drawable.ic_camera)
        b.fab.setOnClickListener { camera.launch() }
        load()
    }

    private fun load() {
        b.swipe.isRefreshing = true
        lifecycleScope.launch {
            when (val r = repo.evidences()) {
                is ApiResult.Ok -> {
                    adapter.items = r.data.evidencias.map { toItem(it) }
                    b.textEmpty.isVisible = r.data.evidencias.isEmpty()
                    b.textEmpty.text = "Aún no hay evidencias de tu tienda"
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

    private fun toItem(e: Evidencia): TaskItem = TaskItem(
        id = e.idEvidencia,
        title = e.descripcion ?: tipos[e.tipo] ?: e.tipo ?: "Evidencia",
        subtitle = listOfNotNull(e.referenciaTipo?.let { "$it ${e.referenciaId?.take(8) ?: ""}" }, e.creadoEn?.let { Fmt.date(it) }).joinToString(" · "),
        highlight = null,
        body = "${(e.tamanoBytes ?: 0) / 1024} KB · ${e.contentType ?: "image/jpeg"}\nSHA-256 ${e.sha256?.take(16) ?: "—"}…\ngs://${e.bucket ?: "?"}/${e.objectKey ?: ""}",
        badge = e.tipo ?: "FOTO", badgeColor = R.color.brand_primary, badgeBg = R.color.brand_primary_container,
        primary = "Ver" to { view(e) },
    )

    private fun view(e: Evidencia) {
        lifecycleScope.launch {
            when (val r = repo.evidenceUrl(e.idEvidencia)) {
                is ApiResult.Ok -> {
                    val url = r.data.urlFirmada ?: return@launch b.root.snack("El servidor no devolvió URL firmada")
                    val bmp = withContext(Dispatchers.IO) {
                        runCatching {
                            plainHttp.newCall(Request.Builder().url(url).build()).execute().use { resp ->
                                if (!resp.isSuccessful) null else resp.body?.bytes()?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
                            }
                        }.getOrNull()
                    }
                    if (bmp == null) { b.root.snack("No se pudo descargar la imagen (¿URL expirada?)"); return@launch }
                    val iv = ImageView(this@EvidenceActivity).apply { setImageBitmap(bmp); adjustViewBounds = true; setPadding(24, 24, 24, 0) }
                    MaterialAlertDialogBuilder(this@EvidenceActivity)
                        .setTitle(e.descripcion ?: "Evidencia")
                        .setMessage("URL firmada válida por ${r.data.urlExpiraEn?.let { "${it / 60} min" } ?: "poco tiempo"}")
                        .setView(iv).setPositiveButton("Cerrar", null).show()
                }
                is ApiResult.Fail -> b.root.showError(r.error)
            }
        }
    }

    private fun askMetadata(f: File) {
        val d = DialogEvidenceBinding.inflate(layoutInflater)
        d.imagePreview.setImageBitmap(BitmapFactory.decodeFile(f.path))
        d.dropdownType.setAdapter(ArrayAdapter(this, android.R.layout.simple_list_item_1, tipos.values.toList()))
        d.dropdownType.setText(tipos.values.first(), false)
        d.textSize.text = "${f.length() / 1024} KB · JPEG comprimido en el dispositivo"
        MaterialAlertDialogBuilder(this).setTitle("Subir evidencia").setView(d.root)
            .setPositiveButton("Subir") { _, _ ->
                val tipo = tipos.entries.firstOrNull { it.value == d.dropdownType.text.toString() }?.key ?: "OTRO"
                upload(f, tipo, d.inputDesc.text?.toString()?.takeIf { it.isNotBlank() })
            }
            .setNegativeButton("Descartar") { _, _ -> f.delete() }.show()
    }

    private fun upload(f: File, tipo: String, desc: String?) {
        b.swipe.isRefreshing = true
        lifecycleScope.launch {
            when (val r = repo.uploadEvidence(f, tipo, "TIENDA", session.storeId?.toString(), desc)) {
                is ApiResult.Ok -> { b.root.snack("Evidencia guardada en el bucket"); f.delete(); load() }
                is ApiResult.Fail -> { b.swipe.isRefreshing = false; b.root.showError(r.error) { upload(f, tipo, desc) } }
            }
        }
    }
}
