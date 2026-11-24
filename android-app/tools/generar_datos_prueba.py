"""
Genera android-app/datos_prueba/hoja_pruebas.html: hoja para probar la app móvil escaneando
desde la pantalla de la PC. Lee datos REALES del gateway (solo lectura, no escribe nada):

  - Cuentas de prueba y qué puede hacer cada rol.
  - QR con el GTIN de productos que tienen existencias en la tienda del gerente, con el
    orden FEFO esperado (para comparar contra la app).
  - Etiquetas QR FT1 de ASN pendientes de recibir en esa tienda (si existen).
  - Casos de prueba (incluye los de seguridad y tolerancia a fallos).

Uso:
    python android-app/tools/generar_datos_prueba.py [--base https://34.51.41.80.nip.io/]
Requiere: segno (ya está en requirements.txt del backend).
"""

from __future__ import annotations

import argparse
import html
import io
import json
import urllib.request
from datetime import datetime
from pathlib import Path

import segno

CUENTAS = [
    ("Gerente de tienda", "gerente@freshtrack.mx", "Tienda2026!", "Todo: recibir, merma, conteo, FEFO, aprobar transferencias y autorizar descuentos"),
    ("Operador de almacén", "almacen@freshtrack.mx", "Almacen2026!", "Recibir, merma, conteo, FEFO, ejecutar transferencias. NO autoriza descuentos"),
    ("Administrador", "admin@freshtrack.mx", "Admin2026!", "Todo (sin restricción de sucursal)"),
    ("Comprador", "buyer@freshtrack.mx", "Compras2026!", "DEBE SER RECHAZADO por la app móvil (prueba de roles)"),
    ("Inactivo", "inactivo@freshtrack.mx", "Inactivo2026!", "DEBE SER RECHAZADO por el servidor (usuario desactivado)"),
]


def api(base: str, path: str, tok: str | None = None, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(base + "api/v1/" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    for intento in range(3):  # el servidor puede tardar con la volumetría masiva: se reintenta
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        except (TimeoutError, urllib.error.URLError):
            if intento == 2:
                raise


def qr_svg(texto: str, escala: int = 8) -> str:
    buf = io.BytesIO()
    segno.make(texto, error="m", micro=False).save(  # micro=False: ML Kit no lee Micro QR
        buf, kind="svg", scale=escala, border=2, xmldecl=False, svgns=True)
    return buf.getvalue().decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://34.51.41.80.nip.io/")
    ap.add_argument("--max-productos", type=int, default=8)
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"

    st, login = api(base, "auth/login", method="POST", body={"email": "gerente@freshtrack.mx", "password": "Tienda2026!"})
    if st != 200:
        raise SystemExit(f"No se pudo iniciar sesión como gerente ({st}): {login}")
    tok, loc = login["token"], login["usuario"]["id_locacion"]

    # Catálogo completo (paginado) para obtener el GTIN de cada SKU
    productos, pag = {}, 1
    while True:
        _, d = api(base, f"catalog/products?por_pagina=100&pagina={pag}")
        for p in d.get("productos", []):
            productos[p["id_sku"]] = p
        if pag >= (d.get("paginacion") or {}).get("total_paginas", 1):
            break
        pag += 1
    _, locs = api(base, "catalog/locations")
    nombre_tienda = next((l["nombre"] for l in locs.get("locaciones", []) if l["id_locacion"] == loc), f"Tienda {loc}")

    # Existencias de la tienda
    filas, pag, aviso_stock = [], 1, ""
    try:
        while True:
            _, d = api(base, f"inventory/stock?id_locacion={loc}&por_pagina=100&pagina={pag}", tok)
            filas += d.get("existencias", [])
            if pag >= d["paginacion"]["total_paginas"] or pag >= 20:
                break
            pag += 1
    except (TimeoutError, urllib.error.URLError, KeyError) as exc:
        # svc-inventory no respondió: la hoja se genera igual con las etiquetas de recepción.
        aviso_stock = f"svc-inventory no respondió ({exc.__class__.__name__}); vuelve a generar la hoja más tarde."
        print("AVISO:", aviso_stock)
    por_sku: dict[int, list] = {}
    for f in filas:
        por_sku.setdefault(f["id_sku"], []).append(f)

    # Elegimos productos con GTIN y ≥2 lotes (para que FEFO tenga orden que verificar), priorizando los que vencen antes
    candidatos = [
        (sku, sorted(ls, key=lambda x: (x["fecha_caducidad"], x["codigo_lote_prov"] or "")))
        for sku, ls in por_sku.items()
        if productos.get(sku, {}).get("codigo_gtin") and len(ls) >= 2
    ]
    candidatos.sort(key=lambda kv: kv[1][0]["dias_restantes"])
    elegidos = candidatos[: args.max_productos]

    # Etiquetas de ASN pendientes para la tienda (si hay)
    etiquetas = []
    # Primero los ASN creados con crear_asn_prueba.py (registro local), luego los más recientes del servidor.
    reg = Path(__file__).resolve().parents[1] / "datos_prueba" / "asn_prueba.json"
    propios = [{"folio_asn": f} for f in reversed(json.loads(reg.read_text(encoding="utf-8")))] if reg.exists() else []
    _, asns = api(base, "asn?por_pagina=50", tok)
    for a in propios + (asns.get("avisos_asn") or asns.get("asns") or []):
        if a.get("estado") in ("RECIBIDO", "CANCELADO"):
            continue
        _, det = api(base, "asn/" + a["folio_asn"], tok)
        for e in det.get("etiquetas", []) or []:
            # Solo etiquetas de esta tienda que aún no se escanean en muelle
            if e.get("qr_payload") and e.get("id_locacion_destino") == loc and e.get("estado_escaneo", "PENDIENTE") == "PENDIENTE":
                etiquetas.append((a["folio_asn"], e))

    def dias(d):
        return "VENCIDO" if d < 0 else "vence HOY" if d == 0 else f"vence en {d} d"

    tarjetas = []
    for sku, ls in elegidos:
        p = productos[sku]
        orden = "".join(
            f"<li><b>{html.escape(l['codigo_lote_prov'] or l['id_lote'][:8])}</b> · {dias(l['dias_restantes'])} · {l['disponible_neto']:g} {html.escape(p.get('unidad_medida') or '')}</li>"
            for l in ls[:4]
        )
        tarjetas.append(f"""
        <div class="card">
          <div class="qr">{qr_svg(p['codigo_gtin'])}</div>
          <div>
            <h3>{html.escape(p['nombre'])}</h3>
            <p class="mono">GTIN {p['codigo_gtin']} · SKU {sku}</p>
            <p>Orden FEFO esperado en la app:</p><ol>{orden}</ol>
            <p class="hint">Úsalo en: Escanear (→ FEFO), Merma, Conteo y Transferir.</p>
          </div>
        </div>""")

    tarjetas_asn = "".join(
        f"""<div class="card"><div class="qr">{qr_svg(e["qr_payload"], 6)}</div><div>
            <h3>{html.escape(str(e.get('producto') or e.get('id_sku')))}</h3>
            <p class="mono">{html.escape(e.get('codigo_etiqueta', ''))} · ASN {html.escape(folio)}</p>
            <p>Declarado: {e.get('cantidad_declarada', '—')} · caduca {html.escape(str(e.get('fecha_caducidad', '—')))}</p></div></div>"""
        for folio, e in etiquetas[:8]
    ) or """<div class="warn">No hay ASN pendientes de recibir en esta tienda en el servidor.
        Para probar <b>Recibir</b> hay que crear una orden de compra (comprador) y su ASN con etiquetas hacia esta tienda,
        y volver a correr este script. Mientras tanto puedes probar la validación con el QR de abajo:
        es una etiqueta FT1 con <b>firma falsa</b> y la app debe rechazarla.</div>
        <div class="card"><div class="qr">""" + qr_svg("FT1|FTL-261124-FALSA1|OC-PRUEBA|L3|S63|0000000000000000", 3) + """</div>
        <div><h3>Etiqueta con firma inválida</h3><p class="mono">FT1|FTL-261124-FALSA1|…|firma falsa</p>
        <p>Resultado esperado: «Etiqueta no válida» (svc-asn valida la firma HMAC).</p></div></div>"""

    cuentas = "".join(
        f"<tr><td>{html.escape(r)}</td><td class='mono'>{e}</td><td class='mono'>{p}</td><td>{html.escape(d)}</td></tr>"
        for r, e, p, d in CUENTAS
    )

    casos = [
        ("Login y roles", "Entrar con Comprador → mensaje «no opera la app móvil». Entrar con Gerente → Inicio con KPIs de la tienda."),
        ("Escanear producto", "Botón naranja Escanear → apuntar a un QR de producto de esta hoja → abre FEFO con el orden de arriba."),
        ("FEFO", "El lote 1º debe ser el de caducidad más próxima (marcado «SURTIR PRIMERO»)."),
        ("Merma con evidencia", "FEFO → tocar el lote 1º → Registrar merma → 1 unidad, causa Caducidad, tomar foto → «Merma registrada» y baja la existencia."),
        ("Conteo", "Conteo → escanear producto → poner en un lote 1 menos que el sistema → Enviar → exactitud < 100 % y ajuste −1."),
        ("Transferencia", "FEFO → lote con ≥ 3 días → Solicitar transferencia → otra tienda, 2 unidades → aparece SUGERIDA → Aprobar → Ejecutar."),
        ("Descuentos", "Descuentos → menú «Generar sugerencias» → Autorizar uno (solo gerente; con almacén no aparece el botón)."),
        ("Alertas", "Alertas → «Escanear ahora» → aparecen alertas de lotes por vencer y llega notificación al teléfono."),
        ("Recepción", "Recibir → escanear etiqueta FT1 de un ASN → cantidad, caducidad, temperatura 4.0 → Registrar. Repetir: no se duplica."),
        ("Sesión", "Más → Renovar sesión → muestra jti anterior (revocado) y nuevo."),
        ("Token revocado", "Desde la web (admin) cerrar las sesiones del gerente → la app regresa sola al login con el motivo."),
        ("Microservicio caído", "En la VM: docker stop freshtrack_svc_planning → Inicio muestra «Servicio degradado» y Estado de servicios lo marca Caído. docker start lo recupera."),
        ("Sin red", "Modo avión → cualquier pantalla muestra «Sin conexión con el servidor» con Reintentar."),
    ]
    filas_casos = "".join(f"<tr><td><b>{html.escape(a)}</b></td><td>{html.escape(b)}</td><td class='chk'>☐</td></tr>" for a, b in casos)

    out = Path(__file__).resolve().parents[1] / "datos_prueba" / "hoja_pruebas.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FreshTrack · Datos de prueba app móvil</title>
<style>
body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:24px;color:#18201c;background:#f7faf8}}
h1{{color:#0f7b5f;margin-bottom:0}} .sub{{color:#5b6863;margin-top:4px}}
h2{{border-bottom:2px solid #c9f1e1;padding-bottom:4px;margin-top:32px}}
table{{border-collapse:collapse;width:100%;background:#fff}} td,th{{border:1px solid #dce5e0;padding:8px;text-align:left;vertical-align:top}}
th{{background:#c9f1e1}} .mono{{font-family:Consolas,monospace;font-size:13px}} .chk{{text-align:center;font-size:20px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:12px}}
.card{{display:flex;gap:16px;background:#fff;border:1px solid #dce5e0;border-radius:16px;padding:16px;break-inside:avoid}}
.card h3{{margin:0 0 4px}} .card p{{margin:4px 0}} .card ol{{margin:4px 0;padding-left:20px}} .qr svg{{width:240px;height:240px}}
.hint{{color:#5b6863;font-size:13px}} .warn{{background:#fff1d6;border-radius:12px;padding:12px;margin-bottom:12px}}
@media print{{body{{background:#fff}}}}
</style></head><body>
<h1>FreshTrack · Datos de prueba de la app móvil</h1>
<p class="sub">Servidor {html.escape(base)} · {html.escape(nombre_tienda)} (id {loc}) · generado {datetime.now():%d/%m/%Y %H:%M}.
Los lotes caducan día a día: vuelve a generar esta hoja antes de la demo.</p>

<h2>Cuentas</h2>
<table><tr><th>Rol</th><th>Correo</th><th>Contraseña</th><th>Qué debe pasar</th></tr>{cuentas}</table>

<h2>Productos para escanear ({len(elegidos)}) — {html.escape(nombre_tienda)}</h2>
<p class="hint">Abre esta hoja en la PC y escanea los QR desde la pantalla con el botón <b>Escanear</b> de la app.
También puedes escribir el GTIN en «Capturar manualmente».</p>
{f'<div class="warn">{html.escape(aviso_stock)}</div>' if aviso_stock else ''}
<div class="grid">{''.join(tarjetas)}</div>

<h2>Etiquetas de recepción (ASN)</h2>
<div class="grid">{tarjetas_asn}</div>

<h2>Casos de prueba</h2>
<table><tr><th>Caso</th><th>Pasos y resultado esperado</th><th>OK</th></tr>{filas_casos}</table>
</body></html>""", encoding="utf-8")
    print(f"Hoja generada: {out}")
    print(f"Tienda {loc}: {len(filas)} lotes · productos en hoja: {len(elegidos)} · etiquetas ASN: {len(etiquetas)}")


if __name__ == "__main__":
    main()
