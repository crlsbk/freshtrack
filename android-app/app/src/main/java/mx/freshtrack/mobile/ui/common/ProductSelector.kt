package mx.freshtrack.mobile.ui.common

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import androidx.core.widget.doAfterTextChanged
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import mx.freshtrack.mobile.data.model.Producto
import mx.freshtrack.mobile.data.repo.ApiResult
import mx.freshtrack.mobile.databinding.DialogProductPickerBinding
import mx.freshtrack.mobile.databinding.ItemProductBinding
import mx.freshtrack.mobile.databinding.ViewProductSelectorBinding
import mx.freshtrack.mobile.ui.scan.ScannerActivity
import mx.freshtrack.mobile.util.LabelParser

/**
 * Selector de producto reutilizable (FEFO, merma, conteo):
 *  - "Escanear": lee el GTIN del empaque (o la etiqueta FT1, que trae el SKU) y lo resuelve en svc-catalog.
 *  - "Buscar": diálogo con búsqueda por nombre/GTIN contra GET /catalog/products?q=
 */
class ProductSelector(
    private val activity: BaseActivity,
    private val v: ViewProductSelectorBinding,
    private val onSelected: (id: Int, nombre: String, unidad: String?) -> Unit,
) {
    private val repo get() = activity.app.repository

    private val scan = activity.registerForActivityResult(ScannerActivity.Contract()) { raw ->
        if (raw != null) resolve(raw)
    }

    init {
        v.btnScanProduct.setOnClickListener {
            scan.launch(ScannerActivity.Request("Escanea el código de barras del producto"))
        }
        v.btnSearchProduct.setOnClickListener { openSearch() }
    }

    fun show(nombre: String?, detalle: String?) {
        v.textProductName.text = nombre ?: "Selecciona un producto"
        v.textProductDetail.text = detalle ?: "Escanea el empaque o búscalo en el catálogo"
    }

    fun select(p: Producto) {
        show(p.nombre, listOfNotNull(p.categoria, p.codigoGtin?.let { "GTIN $it" }).joinToString(" · "))
        onSelected(p.idSku, p.nombre, p.unidadMedida)
    }

    private fun resolve(raw: String) {
        activity.lifecycleScope.launch {
            v.progressProduct.isVisible = true
            when (val p = LabelParser.parse(raw)) {
                is LabelParser.Parsed.Ft1 -> p.idSku?.let { sku -> findBySku(sku) }
                is LabelParser.Parsed.Gs1 -> p.gtin?.let { findByGtin(it) }
                is LabelParser.Parsed.Gtin -> findByGtin(p.gtin)
                else -> v.root.snack("No es un código de producto. Usa Buscar.")
            }
            v.progressProduct.isVisible = false
        }
    }

    suspend fun findByGtin(gtin: String) {
        for (cand in LabelParser.gtinCandidates(gtin)) {
            val r = repo.searchProducts(cand)
            if (r is ApiResult.Fail) { v.root.showError(r.error); return }
            val hit = (r as ApiResult.Ok).data.productos.firstOrNull { it.codigoGtin?.trimStart('0') == cand.trimStart('0') }
            if (hit != null) { select(hit); return }
        }
        v.root.snack("GTIN $gtin no está en el catálogo")
    }

    suspend fun findBySku(sku: Int) {
        when (val r = repo.searchProducts(null)) {
            is ApiResult.Ok -> r.data.productos.firstOrNull { it.idSku == sku }?.let { select(it) }
                ?: v.root.snack("SKU $sku no encontrado")
            is ApiResult.Fail -> v.root.showError(r.error)
        }
    }

    private fun openSearch() {
        val d = DialogProductPickerBinding.inflate(activity.layoutInflater)
        val adapter = ProductAdapter()
        d.list.layoutManager = LinearLayoutManager(activity)
        d.list.adapter = adapter
        var dialog: AlertDialog? = null
        adapter.onClick = { p -> select(p); dialog?.dismiss() }
        var job: Job? = null
        fun search(q: String?) {
            job?.cancel()
            job = activity.lifecycleScope.launch {
                delay(250) // debounce
                d.progress.isVisible = true
                when (val r = repo.searchProducts(q)) {
                    is ApiResult.Ok -> { adapter.items = r.data.productos; d.textEmpty.isVisible = r.data.productos.isEmpty() }
                    is ApiResult.Fail -> { d.textEmpty.isVisible = true; d.textEmpty.text = r.error.message }
                }
                d.progress.isVisible = false
            }
        }
        d.inputQuery.doAfterTextChanged { search(it?.toString()) }
        search(null)
        dialog = MaterialAlertDialogBuilder(activity).setTitle("Buscar producto").setView(d.root)
            .setNegativeButton("Cerrar", null).show()
    }

    private class ProductAdapter : RecyclerView.Adapter<ProductAdapter.VH>() {
        var onClick: (Producto) -> Unit = {}
        var items: List<Producto> = emptyList()
            set(value) { field = value; notifyDataSetChanged() }

        class VH(val b: ItemProductBinding) : RecyclerView.ViewHolder(b.root)

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
            VH(ItemProductBinding.inflate(LayoutInflater.from(parent.context), parent, false))

        override fun getItemCount() = items.size

        override fun onBindViewHolder(h: VH, position: Int) {
            val p = items[position]
            h.b.textName.text = p.nombre
            h.b.textDetail.text = listOfNotNull(p.categoria, p.unidadMedida, p.codigoGtin).joinToString(" · ")
            h.itemView.setOnClickListener { onClick(p) }
        }
    }
}
