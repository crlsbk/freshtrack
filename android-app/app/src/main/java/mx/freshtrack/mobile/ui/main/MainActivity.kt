package mx.freshtrack.mobile.ui.main

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.fragment.app.Fragment
import androidx.fragment.app.commitNow
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.R
import mx.freshtrack.mobile.databinding.ActivityMainBinding
import mx.freshtrack.mobile.ui.alerts.AlertsFragment
import mx.freshtrack.mobile.ui.common.BaseActivity
import mx.freshtrack.mobile.ui.home.HomeFragment
import mx.freshtrack.mobile.ui.inventory.FefoActivity
import mx.freshtrack.mobile.ui.inventory.InventoryFragment
import mx.freshtrack.mobile.ui.receive.ReceiveActivity
import mx.freshtrack.mobile.ui.scan.ScannerActivity
import mx.freshtrack.mobile.util.LabelParser
import mx.freshtrack.mobile.work.AlertNotifier
import mx.freshtrack.mobile.work.AlertWorker

/**
 * Contenedor principal con navegación inferior. El botón "Escanear" abre la cámara y
 * enruta según lo leído: etiqueta logística (FT1 / FTL / GS1) → Recepción;
 * código de producto (GTIN) → Cola FEFO de ese producto en la tienda.
 */
class MainActivity : BaseActivity() {

    private lateinit var b: ActivityMainBinding

    private val scan = registerForActivityResult(ScannerActivity.Contract()) { raw ->
        if (raw != null) route(raw)
    }

    private val notifPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!session.isLoggedIn) return
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)
        ViewCompat.setOnApplyWindowInsetsListener(b.statusScrim) { v, insets ->
            v.layoutParams = v.layoutParams.apply { height = insets.getInsets(WindowInsetsCompat.Type.statusBars()).top }
            insets
        }
        ViewCompat.setOnApplyWindowInsetsListener(b.bottomNav) { v, insets ->
            v.updatePadding(bottom = insets.getInsets(WindowInsetsCompat.Type.systemBars()).bottom)
            insets
        }

        b.bottomNav.setOnItemSelectedListener { item ->
            show(item.itemId); true
        }
        b.fabScan.setOnClickListener { openScanner() }

        // Badge en «Más» con lo capturado sin conexión que falta sincronizar.
        lifecycleScope.launch {
            repo.offlineQueue.count.collect { n ->
                b.bottomNav.getOrCreateBadge(R.id.nav_more).apply {
                    isVisible = n > 0
                    number = n
                }
            }
        }

        if (savedInstanceState == null) {
            val tab = intent.getIntExtra(EXTRA_TAB, R.id.nav_home)
            // Si la pestaña ya está seleccionada el listener no se dispara: se muestra a mano.
            // Si no, el listener la muestra (evita agregar el fragment dos veces).
            if (b.bottomNav.selectedItemId == tab) show(tab) else b.bottomNav.selectedItemId = tab
        } else {
            setLightStatusBar(b.bottomNav.selectedItemId != R.id.nav_home)
        }

        if (savedInstanceState == null && session.notificationsEnabled) {
            AlertWorker.schedule(this)
            AlertWorker.runNow(this)
        }

        if (Build.VERSION.SDK_INT >= 33 && !AlertNotifier.canNotify(this)) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val tab = intent.getIntExtra(EXTRA_TAB, 0)
        if (tab != 0) b.bottomNav.selectedItemId = tab
    }

    fun selectTab(id: Int) { b.bottomNav.selectedItemId = id }

    fun openScanner() = scan.launch(ScannerActivity.Request("Escanea una etiqueta de lote o el código del producto"))

    private fun show(itemId: Int) {
        val tag = "tab_$itemId"
        val fm = supportFragmentManager
        val existing = fm.findFragmentByTag(tag)
        // commitNow: el fragment queda registrado de inmediato y findFragmentByTag lo encuentra la próxima vez.
        fm.commitNow {
            setReorderingAllowed(true)
            fm.fragments.forEach { hide(it) }
            if (existing != null) show(existing) else add(R.id.container, create(itemId), tag)
        }
        if (itemId == R.id.nav_home || itemId == R.id.nav_inventory) b.fabScan.show() else b.fabScan.hide()
        setLightStatusBar(itemId != R.id.nav_home)
        b.statusScrim.visibility = if (itemId == R.id.nav_home) android.view.View.VISIBLE else android.view.View.GONE
    }

    private fun create(itemId: Int): Fragment = when (itemId) {
        R.id.nav_inventory -> InventoryFragment()
        R.id.nav_alerts -> AlertsFragment()
        R.id.nav_more -> MoreFragment()
        else -> HomeFragment()
    }

    private fun route(raw: String) {
        when (val p = LabelParser.parse(raw)) {
            is LabelParser.Parsed.Gtin -> startActivity(FefoActivity.forGtin(this, p.gtin))
            else -> startActivity(ReceiveActivity.intent(this, raw))
        }
    }

    companion object {
        const val EXTRA_TAB = "tab"
        val TAB_ALERTS = R.id.nav_alerts
    }
}
