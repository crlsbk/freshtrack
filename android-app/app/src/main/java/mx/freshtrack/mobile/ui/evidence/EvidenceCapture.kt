package mx.freshtrack.mobile.ui.evidence

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.FileProvider
import androidx.exifinterface.media.ExifInterface
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mx.freshtrack.mobile.ui.common.BaseActivity
import java.io.File
import java.io.FileOutputStream

/**
 * Toma una foto con la cámara del sistema y la deja lista para subir:
 *  - Se guarda en cache/evidencias (FileProvider, no requiere permisos de almacenamiento).
 *  - Se corrige la orientación EXIF, se reduce a ≤1600 px y se comprime JPEG 82 %
 *    (una foto de 4 MB queda en ~250 KB → subida rápida en red móvil).
 * El backend vuelve a validar tipo, tamaño y calcula el SHA-256 antes de guardarla en el bucket.
 */
class EvidenceCapture(private val activity: BaseActivity, private val onReady: (File) -> Unit) {

    private var pending: File? = null

    private val take = activity.registerForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val f = pending
        if (ok && f != null && f.length() > 0) {
            activity.lifecycleScope.launch { onReady(compress(f)) }
        }
    }

    fun launch() {
        val dir = File(activity.cacheDir, "evidencias").apply { mkdirs() }
        val f = File(dir, "evid_${System.currentTimeMillis()}.jpg")
        pending = f
        val uri: Uri = FileProvider.getUriForFile(activity, "${activity.packageName}.fileprovider", f)
        take.launch(uri)
    }

    private suspend fun compress(src: File): File = withContext(Dispatchers.IO) {
        val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(src.path, opts)
        var sample = 1
        while (opts.outWidth / sample > 3200 || opts.outHeight / sample > 3200) sample *= 2
        val raw = BitmapFactory.decodeFile(src.path, BitmapFactory.Options().apply { inSampleSize = sample })
            ?: return@withContext src
        val rotation = when (ExifInterface(src.path).getAttributeInt(ExifInterface.TAG_ORIENTATION, 1)) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90f
            ExifInterface.ORIENTATION_ROTATE_180 -> 180f
            ExifInterface.ORIENTATION_ROTATE_270 -> 270f
            else -> 0f
        }
        val scale = minOf(1f, 1600f / maxOf(raw.width, raw.height))
        val m = Matrix().apply { postRotate(rotation); postScale(scale, scale) }
        val out = Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, m, true)
        val dst = File(src.parentFile, src.nameWithoutExtension + "_c.jpg")
        FileOutputStream(dst).use { out.compress(Bitmap.CompressFormat.JPEG, 82, it) }
        if (out != raw) out.recycle()
        raw.recycle()
        src.delete()
        dst
    }
}
