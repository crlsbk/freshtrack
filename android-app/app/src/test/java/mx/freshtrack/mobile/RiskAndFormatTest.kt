package mx.freshtrack.mobile

import mx.freshtrack.mobile.session.Role
import mx.freshtrack.mobile.util.Fmt
import mx.freshtrack.mobile.util.Risk
import org.junit.Assert.*
import org.junit.Test

class RiskAndFormatTest {

    @Test fun `clasificacion de riesgo igual a fn_clasificar_riesgo`() {
        assertEquals(Risk.VENCIDO, Risk.of(-1))
        assertEquals(Risk.CRITICO, Risk.of(0))
        assertEquals(Risk.CRITICO, Risk.of(2))
        assertEquals(Risk.VIGILANCIA, Risk.of(3))
        assertEquals(Risk.VIGILANCIA, Risk.of(5))
        assertEquals(Risk.NORMAL, Risk.of(6))
        assertEquals(Risk.NORMAL, Risk.of(null))
    }

    @Test fun `texto de dias restantes`() {
        assertEquals("Vence hoy", Fmt.days(0))
        assertEquals("Vence mañana", Fmt.days(1))
        assertEquals("Vence en 4 días", Fmt.days(4))
        assertEquals("Venció hace 2 d", Fmt.days(-2))
    }

    @Test fun `cantidades enteras sin decimales`() {
        assertEquals("12", Fmt.qty(12.0))
        assertEquals("28.17 kg", Fmt.qty(28.17, "kg"))
    }

    @Test fun `solo personal de tienda usa la app movil`() {
        assertTrue(Role.from("store_manager").canUseMobile)
        assertTrue(Role.from("warehouse").canUseMobile)
        assertTrue(Role.from("ADMIN").canUseMobile)
        assertFalse(Role.from("buyer").canUseMobile)
        assertFalse(Role.from("auditor").canUseMobile)
        assertFalse(Role.from(null).canUseMobile)
    }

    @Test fun `permisos por rol`() {
        val wh = Role.WAREHOUSE
        assertTrue(wh.canReceive && wh.canRegisterShrinkage && wh.canExecuteTransfer)
        assertFalse(wh.canApproveDiscount)
        assertFalse(wh.canApproveTransfer)
        assertTrue(Role.STORE_MANAGER.canApproveDiscount)
    }
}
