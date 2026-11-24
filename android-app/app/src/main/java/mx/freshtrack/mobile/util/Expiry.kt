package mx.freshtrack.mobile.util

import androidx.annotation.ColorRes
import mx.freshtrack.mobile.R

/**
 * Clasificación de riesgo de vencimiento en el cliente, alineada con
 * operacion.fn_clasificar_riesgo (NORMAL / VIGILANCIA / CRITICO / VENCIDO).
 * Umbrales por defecto del backend: crítico ≤ 2 días, vigilancia ≤ 5 días.
 */
enum class Risk(val label: String, @ColorRes val color: Int, @ColorRes val container: Int) {
    VENCIDO("Vencido", R.color.risk_expired, R.color.risk_expired_bg),
    CRITICO("Crítico", R.color.risk_critical, R.color.risk_critical_bg),
    VIGILANCIA("Vigilancia", R.color.risk_watch, R.color.risk_watch_bg),
    NORMAL("Normal", R.color.risk_ok, R.color.risk_ok_bg);

    companion object {
        const val CRITICAL_DAYS = 2
        const val WATCH_DAYS = 5

        fun of(diasRestantes: Int?): Risk = when {
            diasRestantes == null -> NORMAL
            diasRestantes < 0 -> VENCIDO
            diasRestantes <= CRITICAL_DAYS -> CRITICO
            diasRestantes <= WATCH_DAYS -> VIGILANCIA
            else -> NORMAL
        }
    }
}

object Fmt {
    private val es = java.util.Locale("es", "MX")

    fun qty(v: Double?, unit: String? = null): String {
        if (v == null) return "—"
        val s = if (v % 1.0 == 0.0) String.format(es, "%,.0f", v) else String.format(es, "%,.2f", v)
        return if (unit.isNullOrBlank()) s else "$s $unit"
    }

    fun money(v: Double?): String = if (v == null) "—" else String.format(es, "$%,.2f", v)

    fun days(d: Int?): String = when {
        d == null -> "—"
        d < 0 -> "Venció hace ${-d} d"
        d == 0 -> "Vence hoy"
        d == 1 -> "Vence mañana"
        else -> "Vence en $d días"
    }

    fun date(iso: String?): String {
        if (iso.isNullOrBlank()) return "—"
        return runCatching {
            val d = java.time.LocalDate.parse(iso.take(10))
            d.format(java.time.format.DateTimeFormatter.ofPattern("d MMM yyyy", es))
        }.getOrDefault(iso)
    }
}
