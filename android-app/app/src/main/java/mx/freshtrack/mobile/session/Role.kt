package mx.freshtrack.mobile.session

/**
 * Roles del backend (operacion.rol.clave) y qué puede hacer cada uno en la app móvil.
 * La app oculta acciones no permitidas, pero la autorización real la hace el backend
 * (decorador requiere_auth → 403 acceso_denegado), así que esto es solo UX.
 */
enum class Role(val key: String, val label: String) {
    ADMIN("admin", "Administrador"),
    STORE_MANAGER("store_manager", "Gerente de tienda"),
    WAREHOUSE("warehouse", "Operador de almacén"),
    BUYER("buyer", "Comprador"),
    PLANNER("planner", "Planeador"),
    SUPPLIER("supplier", "Proveedor"),
    AUDITOR("auditor", "Auditor"),
    UNKNOWN("", "Desconocido");

    /** La app móvil está dirigida al personal de tienda. */
    val canUseMobile get() = this == ADMIN || this == STORE_MANAGER || this == WAREHOUSE

    val canReceive get() = this == ADMIN || this == STORE_MANAGER || this == WAREHOUSE
    val canRegisterShrinkage get() = canReceive
    val canCount get() = canReceive
    val canApproveDiscount get() = this == ADMIN || this == STORE_MANAGER
    val canApproveTransfer get() = this == ADMIN || this == STORE_MANAGER
    val canExecuteTransfer get() = canReceive
    val canDetect get() = this == ADMIN || this == STORE_MANAGER
    val canResolveAlert get() = canReceive

    companion object {
        fun from(key: String?): Role = entries.firstOrNull { it.key == key?.lowercase() } ?: UNKNOWN
    }
}
