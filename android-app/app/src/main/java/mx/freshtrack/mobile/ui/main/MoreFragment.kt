package mx.freshtrack.mobile.ui.main

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.BuildConfig
import mx.freshtrack.mobile.FreshTrackApp
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.databinding.FragmentMoreBinding
import mx.freshtrack.mobile.databinding.ItemMenuBinding
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.count.CountActivity
import mx.freshtrack.mobile.ui.discount.DiscountsActivity
import mx.freshtrack.mobile.ui.evidence.EvidenceActivity
import mx.freshtrack.mobile.ui.receive.ReceiveActivity
import mx.freshtrack.mobile.ui.settings.ServiceStatusActivity
import mx.freshtrack.mobile.ui.settings.SettingsActivity
import mx.freshtrack.mobile.ui.shrink.ShrinkageActivity
import mx.freshtrack.mobile.ui.transfer.TransfersActivity
import mx.freshtrack.mobile.work.AlertWorker
import java.text.DateFormat
import java.util.Date

class MoreFragment : Fragment() {

    private var _b: FragmentMoreBinding? = null
    private val b get() = _b!!
    private val app get() = FreshTrackApp.instance

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, s: Bundle?): View {
        _b = FragmentMoreBinding.inflate(inflater, container, false)
        return b.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        ViewCompat.setOnApplyWindowInsetsListener(b.root) { v, insets ->
            v.updatePadding(top = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top)
            insets
        }
        val s = app.session
        val u = s.user
        b.textName.text = u?.nombre ?: "—"
        b.textEmail.text = u?.email
        b.textRole.text = "${s.role.label} · ${s.storeName ?: "Tienda ${u?.idLocacion ?: "—"}"}"
        renderSession()

        item(b.mReceive, R.drawable.ic_truck, "Recibir mercancía", "Escanear etiqueta QR del ASN") { start(ReceiveActivity.intent(requireContext(), null)) }
        item(b.mShrink, R.drawable.ic_trash, "Registrar merma", "Baja justificada con evidencia") { start(Intent(requireContext(), ShrinkageActivity::class.java)) }
        item(b.mCount, R.drawable.ic_count, "Conteo cíclico", "Ajustes y exactitud de inventario") { start(Intent(requireContext(), CountActivity::class.java)) }
        item(b.mTransfers, R.drawable.ic_transfer, "Transferencias", "Solicitar, aprobar y ejecutar") { start(Intent(requireContext(), TransfersActivity::class.java)) }
        item(b.mDiscounts, R.drawable.ic_discount, "Descuentos por vencimiento", "Autorizar rebajas sugeridas") { start(Intent(requireContext(), DiscountsActivity::class.java)) }
        item(b.mEvidence, R.drawable.ic_image, "Evidencias", "Fotos en Cloud Storage (URL firmada)") { start(Intent(requireContext(), EvidenceActivity::class.java)) }
        item(b.mStatus, R.drawable.ic_server, "Estado de servicios", "Salud de los 8 microservicios") { start(Intent(requireContext(), ServiceStatusActivity::class.java)) }
        item(b.mRefresh, R.drawable.ic_refresh, "Renovar sesión", "Rota el token (refresh) y revoca el anterior") { refresh() }
        item(b.mSettings, R.drawable.ic_tune, "Ajustes", "Servidor, notificaciones") { start(Intent(requireContext(), SettingsActivity::class.java)) }
        item(b.mLogout, R.drawable.ic_logout, "Cerrar sesión", "Revoca el token en el servidor") { logout() }
        b.textVersion.text = "FreshTrack Mobile v${BuildConfig.VERSION_NAME} · Equipo 05"
    }

    private fun start(i: Intent) = startActivity(i)

    private fun item(v: ItemMenuBinding, icon: Int, title: String, sub: String, onClick: () -> Unit) {
        v.menuIcon.setImageResource(icon)
        v.menuTitle.text = title
        v.menuSubtitle.text = sub
        v.root.setOnClickListener { onClick() }
    }

    private fun renderSession() {
        val s = app.session
        b.textSession.text = "Sesión válida hasta ${DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(s.expiresAtMillis))} · " +
            "se renueva sola 30 min antes · token cifrado en Keystore"
    }

    private fun refresh() {
        lifecycleScope.launch {
            val ok = app.repository.refreshSession()
            if (!isAdded) return@launch
            val rot = app.repository.lastRotation
            renderSession()
            MaterialAlertDialogBuilder(requireContext())
                .setTitle(if (ok) "Sesión renovada" else "No se pudo renovar")
                .setMessage(
                    if (ok) "Token anterior (revocado): ${rot?.first?.take(12) ?: "—"}…\n" +
                        "Token nuevo: ${rot?.second?.take(12)}…\n\n" +
                        "Vigente hasta ${DateFormat.getTimeInstance(DateFormat.SHORT).format(Date(app.session.expiresAtMillis))}."
                    else "Revisa tu conexión. Tu sesión actual sigue siendo válida."
                )
                .setPositiveButton("Cerrar", null).show()
        }
    }

    private fun logout() {
        MaterialAlertDialogBuilder(requireContext()).setTitle("¿Cerrar sesión?")
            .setMessage("El token se revocará en el servidor (denylist en Redis) y no podrá reutilizarse.")
            .setPositiveButton("Cerrar sesión") { _, _ ->
                lifecycleScope.launch {
                    app.repository.logout()
                    AlertWorker.cancel(requireContext())
                    (activity as? BaseActivity)?.goToLogin(null)
                }
            }
            .setNegativeButton("Cancelar", null).show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
