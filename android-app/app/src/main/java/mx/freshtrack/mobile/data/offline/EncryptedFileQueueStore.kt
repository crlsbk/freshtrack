package mx.freshtrack.mobile.data.offline

import android.content.Context
import android.util.AtomicFile
import mx.freshtrack.mobile.session.TokenCipher
import java.io.File

/**
 * Guarda la cola en el almacenamiento privado de la app (`files/offline_queue.bin`),
 * cifrada con AES-256/GCM y la llave no exportable del Android Keystore (la misma
 * que protege el JWT). AtomicFile evita dejar el archivo a medias si la app muere
 * mientras escribe. El directorio no se respalda en la nube (allowBackup=false).
 */
class EncryptedFileQueueStore(context: Context) : QueueStore {

    private val file = AtomicFile(File(context.filesDir, "offline_queue.bin"))

    override fun read(): String? = runCatching {
        if (!file.baseFile.exists()) null else TokenCipher.decrypt(String(file.readFully(), Charsets.UTF_8))
    }.getOrNull()

    override fun write(json: String) {
        val out = file.startWrite()
        try {
            out.write(TokenCipher.encrypt(json).toByteArray(Charsets.UTF_8))
            file.finishWrite(out)
        } catch (e: Exception) {
            file.failWrite(out)
        }
    }
}
