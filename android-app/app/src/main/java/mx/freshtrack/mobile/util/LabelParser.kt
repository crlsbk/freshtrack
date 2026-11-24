package mx.freshtrack.mobile.util

/**
 * Interpreta lo que lee la cámara antes de mandarlo al backend:
 *  - FT1|FTL-261123-ABC123|OC-...|L3|S5|<firma>  → etiqueta logística firmada (HMAC) de un ASN
 *  - (01)07501234560126(17)261130(10)LOTE        → GS1-128 / DataMatrix (GTIN + caducidad + lote)
 *  - FTL-261123-ABC123                            → folio corto de etiqueta
 *  - 7501234560126 (8/12/13/14 dígitos)           → código de barras del producto (GTIN)
 *
 * La firma NO se valida aquí (la llave vive solo en el servidor); el parser solo decide
 * a qué flujo mandar el código y muestra una vista previa inmediata.
 */
object LabelParser {

    sealed class Parsed(val raw: String) {
        class Ft1(raw: String, val codigoEtiqueta: String, val folioOc: String, val idLocacion: Int?, val idSku: Int?) : Parsed(raw)
        class Gs1(raw: String, val gtin: String?, val caducidad: String?, val lote: String?) : Parsed(raw)
        class ShortLabel(raw: String, val codigoEtiqueta: String) : Parsed(raw)
        class Gtin(raw: String, val gtin: String) : Parsed(raw)
        class Unknown(raw: String) : Parsed(raw)

        val isLogisticLabel get() = this is Ft1 || this is ShortLabel || this is Gs1
    }

    private val shortLabel = Regex("^FTL-\\d{6}-[A-Z0-9]{4,12}$", RegexOption.IGNORE_CASE)
    private val gtin = Regex("^\\d{8}$|^\\d{12,14}$")

    fun parse(text: String?): Parsed {
        val raw = text?.trim().orEmpty()
        if (raw.isEmpty()) return Parsed.Unknown(raw)
        if (raw.startsWith("FT1|")) {
            val p = raw.split("|")
            if (p.size >= 6) {
                return Parsed.Ft1(
                    raw, p[1], p[2],
                    p[3].removePrefix("L").toIntOrNull(),
                    p[4].removePrefix("S").toIntOrNull(),
                )
            }
            return Parsed.Unknown(raw)
        }
        if (raw.startsWith("(01)") || raw.startsWith("]C1") || raw.startsWith("]d2")) {
            return parseGs1(raw)
        }
        if (shortLabel.matches(raw)) return Parsed.ShortLabel(raw, raw.uppercase())
        if (gtin.matches(raw)) return Parsed.Gtin(raw, raw.padStart(14, '0'))
        return Parsed.Unknown(raw)
    }

    private fun parseGs1(raw: String): Parsed.Gs1 {
        val clean = raw.removePrefix("]C1").removePrefix("]d2")
        val ai = Regex("\\((\\d{2,4})\\)([^(]+)").findAll(clean).associate { it.groupValues[1] to it.groupValues[2] }
        val exp = ai["17"]?.takeIf { it.length == 6 }?.let { "20${it.substring(0, 2)}-${it.substring(2, 4)}-${it.substring(4, 6)}" }
        return Parsed.Gs1(raw, ai["01"], exp, ai["10"])
    }

    /** Las variantes de GTIN que pueden estar guardadas en el catálogo (13 o 14 dígitos). */
    fun gtinCandidates(gtin: String): List<String> {
        val digits = gtin.trimStart('0')
        return listOf(gtin, digits.padStart(13, '0'), digits.padStart(14, '0')).distinct()
    }
}
