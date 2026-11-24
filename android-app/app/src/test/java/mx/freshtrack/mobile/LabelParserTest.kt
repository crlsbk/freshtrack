package mx.freshtrack.mobile

import mx.freshtrack.mobile.util.LabelParser
import mx.freshtrack.mobile.util.LabelParser.Parsed
import org.junit.Assert.*
import org.junit.Test

class LabelParserTest {

    @Test fun `FT1 firmado extrae etiqueta, OC, locacion y sku`() {
        val p = LabelParser.parse("FT1|FTL-261123-ABC123|OC-2026-0042|L3|S5|9f8e7d6c")
        assertTrue(p is Parsed.Ft1)
        p as Parsed.Ft1
        assertEquals("FTL-261123-ABC123", p.codigoEtiqueta)
        assertEquals("OC-2026-0042", p.folioOc)
        assertEquals(3, p.idLocacion)
        assertEquals(5, p.idSku)
        assertTrue(p.isLogisticLabel)
    }

    @Test fun `FT1 truncado no se acepta`() {
        assertTrue(LabelParser.parse("FT1|FTL-261123-ABC123|OC") is Parsed.Unknown)
    }

    @Test fun `GS1-128 con GTIN caducidad y lote`() {
        val p = LabelParser.parse("(01)07501234560126(17)261130(10)LOTE-77") as Parsed.Gs1
        assertEquals("07501234560126", p.gtin)
        assertEquals("2026-11-30", p.caducidad)
        assertEquals("LOTE-77", p.lote)
    }

    @Test fun `folio corto de etiqueta`() {
        val p = LabelParser.parse("ftl-261123-a1b2c3")
        assertTrue(p is Parsed.ShortLabel)
        assertEquals("FTL-261123-A1B2C3", (p as Parsed.ShortLabel).codigoEtiqueta)
    }

    @Test fun `EAN-13 se normaliza a GTIN-14`() {
        val p = LabelParser.parse("7501234560126") as Parsed.Gtin
        assertEquals("07501234560126", p.gtin)
        assertFalse(p.isLogisticLabel)
    }

    @Test fun `texto libre o vacio es desconocido`() {
        assertTrue(LabelParser.parse("hola mundo") is Parsed.Unknown)
        assertTrue(LabelParser.parse("") is Parsed.Unknown)
        assertTrue(LabelParser.parse(null) is Parsed.Unknown)
    }

    @Test fun `candidatos de GTIN cubren 13 y 14 digitos`() {
        val c = LabelParser.gtinCandidates("07501234560126")
        assertTrue("7501234560126" in c)
        assertTrue("07501234560126" in c)
    }
}
