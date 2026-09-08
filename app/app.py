from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps
from data.repository import (
    USUARIOS, ROLE_KEY_MAP, ROLE_KEYS, ROLE_VIEWS, ROLE_DEFAULT_VIEW,
    ROLE_ACCENT, NAV_SECTIONS, LOCACIONES, PROVEEDORES, PRODUCTOS,
    LOTES, EXISTENCIAS, VENTAS, MERMAS, CAUSA_MERMA_OPTS, BITACORA,
    REPLENISHMENT, TRANSFERS, ALERTS, DISCOUNTS, FORECAST_DATA,
    SALES_MONTHLY, CATEGORY_WASTE, SAVINGS_DATA, MICROSERVICES,
    get_login_users, get_products_catalog, get_inventory_report, get_sales_report,
)

app = Flask(__name__)
app.secret_key = "freshtrack-dev-2026-secret"


# ── Auth helpers ────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(view_id):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            allowed = ROLE_VIEWS.get(session.get("role", ""), [])
            if view_id not in allowed:
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Context processor (inject nav data into every template) ─────────────────

NAV_ICONS = {
    "dashboard":      '<path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zm0 8a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zm6-6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zm0 8a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/>',
    "alerts":         '<path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zm0 16a2 2 0 01-2-2h4a2 2 0 01-2 2z"/>',
    "products":       '<path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"/>',
    "stores":         '<path d="M2 5a2 2 0 012-2h12a2 2 0 012 2v2a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm14 6a2 2 0 012 2v3a2 2 0 01-2 2H4a2 2 0 01-2-2v-3a2 2 0 012-2h12z"/>',
    "suppliers":      '<path d="M8 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm7 0a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM3 4a1 1 0 00-1 1v9a1 1 0 001 1h.5a2.5 2.5 0 014.95 0h3.1a2.5 2.5 0 014.95 0H17a1 1 0 001-1v-5l-3-4H3z"/>',
    "batches":        '<path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd"/>',
    "inventory":      '<path d="M10 3.5L2.5 8 10 12.5 17.5 8 10 3.5zm-7.5 7L10 15l7.5-4.5L10 16.5 2.5 10.5z"/>',
    "sales":          '<path fill-rule="evenodd" d="M3 3a1 1 0 000 2v8a2 2 0 002 2h2.586l-1.293 1.293a1 1 0 101.414 1.414L10 15.414l2.293 2.293a1 1 0 001.414-1.414L12.414 15H15a2 2 0 002-2V5a1 1 0 100-2H3zm11 4a1 1 0 10-2 0v4a1 1 0 102 0V7zm-3 1a1 1 0 10-2 0v3a1 1 0 102 0V8zM8 9a1 1 0 00-2 0v2a1 1 0 102 0V9z" clip-rule="evenodd"/>',
    "fefo":           '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/>',
    "forecast":       '<path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z"/><path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z"/>',
    "replenishment":  '<path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>',
    "transfers":      '<path d="M8 5a1 1 0 100 2h5.586l-1.293 1.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L13.586 5H8zm-5 10a1 1 0 100-2H2.414l1.293-1.293a1 1 0 10-1.414-1.414l-3 3a1 1 0 000 1.414l3 3a1 1 0 001.414-1.414L2.414 15H3z"/>',
    "discounts":      '<path fill-rule="evenodd" d="M17.707 9.293a1 1 0 010 1.414l-7 7a1 1 0 01-1.414 0l-7-7A.997.997 0 012 10V5a3 3 0 013-3h5c.256 0 .512.098.707.293l7 7zM5 6a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>',
    "shrinkage":      '<path fill-rule="evenodd" d="M3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd"/>',
    "savings":        '<path fill-rule="evenodd" d="M3.172 5.172a4 4 0 015.656 0L10 6.343l1.172-1.171a4 4 0 115.656 5.656L10 17.657l-6.828-6.829a4 4 0 010-5.656z" clip-rule="evenodd"/>',
    "sustainability": '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z" clip-rule="evenodd"/>',
    "users":          '<path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zm8 0a3 3 0 11-6 0 3 3 0 016 0zm-4.07 11c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>',
    "audit":          '<path fill-rule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>',
    "settings":       '<path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>',
}


@app.context_processor
def inject_nav():
    if "user_id" not in session:
        return {}
    role = session.get("role", "admin")
    allowed = ROLE_VIEWS.get(role, [])
    filtered_sections = [
        {"label": s["label"], "items": [i for i in s["items"] if i["id"] in allowed]}
        for s in NAV_SECTIONS
        if any(i["id"] in allowed for i in s["items"])
    ]
    role_info = next((r for r in ROLE_KEYS if r["key"] == role), {})
    return {
        "nav_sections": filtered_sections,
        "allowed_views": allowed,
        "current_role": role,
        "role_label": role_info.get("label", role),
        "role_accent": ROLE_ACCENT.get(role, "#4ade80"),
        "user_name": session.get("user_name", ""),
        "user_initials": "".join(w[0] for w in session.get("user_name", "U").split()[:2]).upper(),
        "notifications": 6,
        "nav_icons": NAV_ICONS,
    }


# ── Auth routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for(ROLE_DEFAULT_VIEW.get(session["role"], "dashboard")))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        users = get_login_users()
        if users is None:
            return render_template("login.html", error="No se pudo conectar a PostgreSQL para validar usuarios.", usuarios=[], role_keys=ROLE_KEYS)
        user = next((u for u in users if str(u.get("email", "")).lower() == email and str(u.get("password", "")) == password), None)
        if not user:
            error = "Correo o contraseña incorrectos."
        elif not user.get("estado_activo", True):
            error = "Esta cuenta está desactivada. Contacta al administrador."
        else:
            role = ROLE_KEY_MAP.get(user.get("id_rol"), "auditor")
            session["user_id"] = user.get("id_usuario")
            session["role"] = role
            session["user_name"] = user.get("nombre_completo")
            return redirect(url_for(ROLE_DEFAULT_VIEW.get(role, "dashboard")))
    return render_template("login.html", error=error, usuarios=get_login_users() or [], role_keys=ROLE_KEYS)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── View routes ─────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    from datetime import date
    today = date(2026, 9, 8)
    critical_lotes = []
    for lote in LOTES:
        if lote["status"] in ("critical", "expired"):
            prod = next((p for p in PRODUCTOS if p["id_sku"] == lote["id_sku"]), {})
            loc  = next((l for l in LOCACIONES if l["id_locacion"] == lote["id_locacion"]), {})
            from datetime import datetime
            exp = datetime.strptime(lote["fecha_caducidad"], "%Y-%m-%d").date()
            days = (exp - today).days
            critical_lotes.append({**lote, "producto": prod.get("nombre",""), "locacion": loc.get("nombre",""), "dias_restantes": days})
    urgent_repl = [r for r in REPLENISHMENT if r["prioridad"] == "alta"]
    return render_template("dashboard.html", active="dashboard",
        critical_lotes=critical_lotes, urgent_repl=urgent_repl,
        sales_monthly=SALES_MONTHLY, category_waste=CATEGORY_WASTE,
        forecast_data=FORECAST_DATA)


@app.route("/products")
@login_required
@role_required("products")
def products():
    catalog = get_products_catalog() or PRODUCTOS
    enriched = []
    for p in catalog:
        prov = next((pr for pr in PROVEEDORES if pr.get("id_proveedor") == p.get("id_proveedor")), {})
        row = dict(p)
        row["proveedor_nombre"] = p.get("proveedor_nombre") or prov.get("razon_social", "—")
        row["categoria"] = p.get("categoria", "")
        row["precio_costo"] = p.get("precio_costo", 0)
        row["precio_venta"] = p.get("precio_venta", 0)
        row["unidad"] = p.get("unidad", "")
        row["stock_min"] = p.get("stock_min", 0)
        row["punto_reorden"] = p.get("punto_reorden", 0)
        enriched.append(row)
    return render_template("products.html", active="products", productos=enriched)


@app.route("/stores")
@login_required
@role_required("stores")
def stores():
    return render_template("stores.html", active="stores", locaciones=LOCACIONES)


@app.route("/suppliers")
@login_required
@role_required("suppliers")
def suppliers():
    return render_template("suppliers.html", active="suppliers", proveedores=PROVEEDORES)


@app.route("/batches")
@login_required
@role_required("batches")
def batches():
    from datetime import datetime, date
    today = date(2026, 9, 8)
    enriched = []
    for lote in sorted(LOTES, key=lambda l: l["fecha_caducidad"]):
        prod = next((p for p in PRODUCTOS if p["id_sku"] == lote["id_sku"]), {})
        loc  = next((l for l in LOCACIONES if l["id_locacion"] == lote["id_locacion"]), {})
        exp  = datetime.strptime(lote["fecha_caducidad"], "%Y-%m-%d").date()
        dias = (exp - today).days
        pct  = max(0, min(100, int(dias / prod.get("vida_util_estandar", 15) * 100))) if prod else 0
        enriched.append({**lote, "producto": prod.get("nombre",""), "locacion": loc.get("nombre",""), "dias_restantes": dias, "pct_vida": pct})
    return render_template("batches.html", active="batches", lotes=enriched)


@app.route("/inventory")
@login_required
@role_required("inventory")
def inventory():
    enriched = []
    rows = get_inventory_report() or EXISTENCIAS
    for ex in rows:
        lote = next((l for l in LOTES if str(l.get("id_lote")) == str(ex.get("id_lote"))), {})
        prod = next((p for p in PRODUCTOS if p.get("id_sku") == lote.get("id_sku")), {})
        loc = next((l for l in LOCACIONES if l.get("id_locacion") == ex.get("id_locacion")), {})
        row = dict(ex)
        row["producto"] = ex.get("producto") or prod.get("nombre", "")
        row["lote_codigo"] = lote.get("codigo_lote_prov", "")
        row["locacion"] = ex.get("locacion") or loc.get("nombre", "")
        row["fecha_caducidad"] = ex.get("fecha_caducidad") or lote.get("fecha_caducidad", "")
        enriched.append(row)
    return render_template("inventory.html", active="inventory", existencias=enriched, locaciones=LOCACIONES)


@app.route("/sales")
@login_required
@role_required("sales")
def sales():
    rows = get_sales_report() or VENTAS
    enriched = []
    total_units = total_revenue = 0
    for v in rows:
        lote = next((l for l in LOTES if str(l.get("id_lote")) == str(v.get("id_lote"))), {})
        prod = next((p for p in PRODUCTOS if p.get("id_sku") == lote.get("id_sku")), {})
        loc = next((l for l in LOCACIONES if l.get("id_locacion") == v.get("id_locacion")), {})
        qty = float(v.get("cantidad", 0) or 0)
        unit_price = float(prod.get("precio_venta", 0) or 0)
        total = qty * unit_price
        total_units += qty
        total_revenue += total
        row = dict(v)
        row["producto"] = v.get("producto") or prod.get("nombre", "")
        row["lote_codigo"] = lote.get("codigo_lote_prov", "")
        row["locacion"] = v.get("locacion") or loc.get("nombre", "")
        row["precio_unit"] = unit_price
        row["total"] = total
        enriched.append(row)
    return render_template("sales.html", active="sales", ventas=enriched,
        total_units=total_units, total_revenue=total_revenue,
        ticket_prom=round(total_units/len(enriched),1) if enriched else 0,
        n_transacciones=len(enriched), sales_monthly=SALES_MONTHLY)


@app.route("/forecast")
@login_required
@role_required("forecast")
def forecast():
    return render_template("forecast.html", active="forecast", forecast_data=FORECAST_DATA, replenishment=REPLENISHMENT)


@app.route("/fefo")
@login_required
@role_required("fefo")
def fefo():
    from datetime import datetime, date
    today = date(2026, 9, 8)
    queue = []
    for lote in sorted(LOTES, key=lambda l: l["fecha_caducidad"]):
        if lote["status"] == "expired":
            continue
        prod = next((p for p in PRODUCTOS if p["id_sku"] == lote["id_sku"]), {})
        loc  = next((l for l in LOCACIONES if l["id_locacion"] == lote["id_locacion"]), {})
        ex   = next((e for e in EXISTENCIAS if e["id_lote"] == lote["id_lote"]), {})
        exp  = datetime.strptime(lote["fecha_caducidad"], "%Y-%m-%d").date()
        dias = (exp - today).days
        queue.append({**lote, "producto": prod.get("nombre",""), "locacion": loc.get("nombre",""), "dias_restantes": dias, "disponible": ex.get("cantidad_disponible",0)})
    return render_template("fefo.html", active="fefo", queue=queue)


@app.route("/replenishment")
@login_required
@role_required("replenishment")
def replenishment():
    return render_template("replenishment.html", active="replenishment", items=REPLENISHMENT)


@app.route("/transfers")
@login_required
@role_required("transfers")
def transfers():
    return render_template("transfers.html", active="transfers", transfers=TRANSFERS)


@app.route("/discounts")
@login_required
@role_required("discounts")
def discounts():
    total_potencial = sum(d["ingreso_potencial"] for d in DISCOUNTS)
    return render_template("discounts.html", active="discounts", discounts=DISCOUNTS, total_potencial=total_potencial)


@app.route("/shrinkage", methods=["GET", "POST"])
@login_required
@role_required("shrinkage")
def shrinkage():
    message = None
    if request.method == "POST":
        message = "Merma registrada correctamente en operacion.merma"
    enriched = []
    for m in MERMAS:
        lote = next((l for l in LOTES if l["id_lote"] == m["id_lote"]), {})
        prod = next((p for p in PRODUCTOS if p["id_sku"] == lote.get("id_sku")), {})
        user = next((u for u in USUARIOS if u["id_usuario"] == m["id_usuario"]), {})
        valor = m["cantidad"] * prod.get("precio_costo", 0)
        enriched.append({**m, "producto": prod.get("nombre",""), "lote_codigo": lote.get("codigo_lote_prov",""), "responsable": user.get("nombre_completo","Sistema"), "valor": valor})
    total_valor = sum(e["valor"] for e in enriched)
    return render_template("shrinkage.html", active="shrinkage", mermas=enriched,
        total_cantidad=sum(m["cantidad"] for m in MERMAS),
        total_valor=total_valor, lotes=LOTES, productos=PRODUCTOS,
        usuarios=USUARIOS, causa_opts=CAUSA_MERMA_OPTS, message=message)


@app.route("/savings")
@login_required
@role_required("savings")
def savings():
    total = sum(s["descuentos"] + s["transferencias"] + s["merma_evitada"] for s in SAVINGS_DATA)
    return render_template("savings.html", active="savings", savings_data=SAVINGS_DATA, total=total)


@app.route("/sustainability")
@login_required
@role_required("sustainability")
def sustainability():
    enriched = []
    for m in MERMAS:
        lote = next((l for l in LOTES if l["id_lote"] == m["id_lote"]), {})
        prod = next((p for p in PRODUCTOS if p["id_sku"] == lote.get("id_sku")), {})
        enriched.append({**m, "producto": prod.get("nombre",""), "lote_codigo": lote.get("codigo_lote_prov","")})
    return render_template("sustainability.html", active="sustainability", mermas=enriched)


@app.route("/alerts")
@login_required
@role_required("alerts")
def alerts():
    return render_template("alerts.html", active="alerts", alerts=ALERTS)


@app.route("/users")
@login_required
@role_required("users")
def users():
    enriched = []
    for u in USUARIOS:
        rol  = next((r for r in ROLE_KEYS if r["id_rol"] == u["id_rol"]), {})
        loc  = next((l for l in LOCACIONES if l["id_locacion"] == u["id_locacion"]), {})
        enriched.append({**u, "rol_label": rol.get("label",""), "rol_color": rol.get("color","#888"), "locacion_nombre": loc.get("nombre","")})
    return render_template("users.html", active="users", usuarios=enriched, role_keys=ROLE_KEYS)


@app.route("/audit")
@login_required
@role_required("audit")
def audit():
    enriched = []
    for ev in BITACORA:
        user = next((u for u in USUARIOS if u["id_usuario"] == ev["id_usuario_app"]), {})
        enriched.append({**ev, "user_name": user.get("nombre_completo","Sistema")})
    return render_template("audit.html", active="audit", bitacora=enriched)


@app.route("/settings")
@login_required
@role_required("settings")
def settings():
    return render_template("settings.html", active="settings", microservices=MICROSERVICES)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
