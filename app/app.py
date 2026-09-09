from datetime import date
from functools import wraps

from flask import Flask, redirect, render_template, request, session, url_for

from data.repository import (
    ALERTS,
    BITACORA,
    CAUSA_MERMA_OPTS,
    CATEGORY_WASTE,
    DISCOUNTS,
    EXISTENCIAS,
    FORECAST_DATA,
    LOCACIONES,
    LOTES,
    MERMAS,
    MICROSERVICES,
    NAV_SECTIONS,
    PRODUCTOS,
    PROVEEDORES,
    REPLENISHMENT,
    ROLE_ACCENT,
    ROLE_DEFAULT_VIEW,
    ROLE_KEYS,
    ROLE_VIEWS,
    SALES_MONTHLY,
    SAVINGS_DATA,
    TRANSFERS,
    USUARIOS,
    VENTAS,
    TableProxy,
    query,
)
from decimal import Decimal
from flask.json.provider import DefaultJSONProvider


class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, TableProxy):
            return list(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


app = Flask(__name__)
app.json = CustomJSONProvider(app)
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
    "dashboard": '<path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zm0 8a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zm6-6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zm0 8a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/>',
    "alerts": '<path d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zm0 16a2 2 0 01-2-2h4a2 2 0 01-2 2z"/>',
    "products": '<path d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z"/>',
    "stores": '<path d="M2 5a2 2 0 012-2h12a2 2 0 012 2v2a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm14 6a2 2 0 012 2v3a2 2 0 01-2 2H4a2 2 0 01-2-2v-3a2 2 0 012-2h12z"/>',
    "suppliers": '<path d="M8 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm7 0a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM3 4a1 1 0 00-1 1v9a1 1 0 001 1h.5a2.5 2.5 0 014.95 0h3.1a2.5 2.5 0 014.95 0H17a1 1 0 001-1v-5l-3-4H3z"/>',
    "batches": '<path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd"/>',
    "inventory": '<path d="M10 3.5L2.5 8 10 12.5 17.5 8 10 3.5zm-7.5 7L10 15l7.5-4.5L10 16.5 2.5 10.5z"/>',
    "sales": '<path fill-rule="evenodd" d="M3 3a1 1 0 000 2v8a2 2 0 002 2h2.586l-1.293 1.293a1 1 0 101.414 1.414L10 15.414l2.293 2.293a1 1 0 001.414-1.414L12.414 15H15a2 2 0 002-2V5a1 1 0 100-2H3zm11 4a1 1 0 10-2 0v4a1 1 0 102 0V7zm-3 1a1 1 0 10-2 0v3a1 1 0 102 0V8zM8 9a1 1 0 00-2 0v2a1 1 0 102 0V9z" clip-rule="evenodd"/>',
    "fefo": '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"/>',
    "forecast": '<path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z"/><path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z"/>',
    "replenishment": '<path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd"/>',
    "transfers": '<path d="M8 5a1 1 0 100 2h5.586l-1.293 1.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L13.586 5H8zm-5 10a1 1 0 100-2H2.414l1.293-1.293a1 1 0 10-1.414-1.414l-3 3a1 1 0 000 1.414l3 3a1 1 0 001.414-1.414L2.414 15H3z"/>',
    "discounts": '<path fill-rule="evenodd" d="M17.707 9.293a1 1 0 010 1.414l-7 7a1 1 0 01-1.414 0l-7-7A.997.997 0 012 10V5a3 3 0 013-3h5c.256 0 .512.098.707.293l7 7zM5 6a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>',
    "shrinkage": '<path fill-rule="evenodd" d="M3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd"/>',
    "savings": '<path fill-rule="evenodd" d="M3.172 5.172a4 4 0 015.656 0L10 6.343l1.172-1.171a4 4 0 115.656 5.656L10 17.657l-6.828-6.829a4 4 0 010-5.656z" clip-rule="evenodd"/>',
    "sustainability": '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z" clip-rule="evenodd"/>',
    "users": '<path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zm8 0a3 3 0 11-6 0 3 3 0 016 0zm-4.07 11c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>',
    "audit": '<path fill-rule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>',
    "settings": '<path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/>',
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
        "user_initials": "".join(
            w[0] for w in session.get("user_name", "U").split()[:2]
        ).upper(),
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
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        from data.repository import authenticate_user

        user = authenticate_user(email, password)
        if not user:
            error = "Correo electrónico o contraseña incorrectos."
        elif not user["estado_activo"]:
            error = "Esta cuenta está desactivada. Contacta al administrador."
        else:
            role = user["role_key"]
            session["user_id"] = user["id_usuario"]
            session["role"] = role
            session["user_name"] = user["nombre_completo"]
            return redirect(url_for(ROLE_DEFAULT_VIEW.get(role, "dashboard")))
    return render_template(
        "login.html", error=error, usuarios=USUARIOS, role_keys=ROLE_KEYS
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── View routes ─────────────────────────────────────────────────────────────


@app.route("/dashboard")
@login_required
def dashboard():
    m = query("""
        SELECT 
            (SELECT COALESCE(SUM(cantidad), 0) FROM operacion.venta_detalle) AS sales_units,
            (SELECT COALESCE(SUM(cantidad), 0) FROM operacion.merma) AS waste_units,
            (SELECT COALESCE(SUM(cantidad_disponible), 0) FROM operacion.existencia) AS inventory_units,
            (SELECT count(*) FROM operacion.locacion) AS active_locations
    """)[0]

    critical_lotes = query("""
        SELECT l.id_lote::text AS id_lote,
               p.nombre AS producto,
               l.codigo_lote_prov,
               COALESCE(loc.nombre, 'Almacén Central') AS locacion,
               l.fecha_caducidad::text AS fecha_caducidad,
               (l.fecha_caducidad - '2026-09-08'::date) AS dias_restantes,
               CASE WHEN l.fecha_caducidad < '2026-09-08'::date THEN 'expired'
                    ELSE 'critical' END AS status
        FROM operacion.lote l
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        LEFT JOIN LATERAL (
            SELECT loc.nombre
            FROM operacion.existencia e
            JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
            WHERE e.id_lote = l.id_lote
            LIMIT 1
        ) loc ON true
        WHERE l.fecha_caducidad <= '2026-09-10'::date
        ORDER BY l.fecha_caducidad ASC
        LIMIT 12
    """)

    urgent_repl = list(REPLENISHMENT)[:10]

    return render_template(
        "dashboard.html",
        active="dashboard",
        dashboard_metrics={
            "critical_lotes": len(critical_lotes),
            "urgent_replenishment": len(urgent_repl),
            "sales_units": float(m["sales_units"]),
            "waste_units": float(m["waste_units"]),
            "inventory_units": float(m["inventory_units"]),
            "active_locations": int(m["active_locations"]),
        },
        critical_lotes=critical_lotes,
        urgent_repl=urgent_repl,
        sales_monthly=SALES_MONTHLY,
        category_waste=CATEGORY_WASTE,
        forecast_data=FORECAST_DATA,
    )


@app.route("/products", methods=["GET", "POST"])
@login_required
@role_required("products")
def products():
    message = None
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        gtin = request.form.get("codigo_gtin", "").strip()
        vida_util = int(request.form.get("vida_util_estandar", 15) or 15)
        id_proveedor = int(request.form.get("id_proveedor", 1) or 1)
        if not gtin:
            import random

            gtin = f"750{random.randint(10000000000, 99999999999)}"
        if nombre:
            try:
                import uuid
                from sqlalchemy import text
                from data.repository import get_engine

                with get_engine().begin() as conn:
                    res = conn.execute(
                        text("""
                            INSERT INTO operacion.producto (codigo_gtin, nombre, vida_util_estandar)
                            VALUES (:gtin, :nombre, :vida_util)
                            RETURNING id_sku
                        """),
                        {"gtin": gtin[:14], "nombre": nombre, "vida_util": vida_util},
                    )
                    new_sku = res.scalar()
                    # Vincular con el proveedor en operacion.lote
                    lote_id = str(uuid.uuid4())
                    conn.execute(
                        text("""
                            INSERT INTO operacion.lote (id_lote, id_sku, id_proveedor, codigo_lote_prov, fecha_caducidad)
                            VALUES (:id_lote, :id_sku, :id_proveedor, :codigo_lote, CURRENT_DATE + (:vida_util || ' days')::interval)
                        """),
                        {
                            "id_lote": lote_id,
                            "id_sku": new_sku,
                            "id_proveedor": id_proveedor,
                            "codigo_lote": f"LOT-{new_sku}-PROV",
                            "vida_util": str(vida_util),
                        },
                    )
                    # Registrar existencia inicial de 100 unidades
                    conn.execute(
                        text("""
                            INSERT INTO operacion.existencia (id_lote, id_locacion, cantidad_disponible, cantidad_reservada)
                            VALUES (:id_lote, 1, 100.0, 0.0)
                        """),
                        {"id_lote": lote_id},
                    )
                message = f"Producto '{nombre}' registrado y vinculado al proveedor en PostgreSQL con lote inicial."
            except Exception as e:
                message = f"Error al guardar producto: {e}"

    prov_map = {pr["id_proveedor"]: pr for pr in PROVEEDORES}
    enriched = []
    for p in PRODUCTOS:
        prov = prov_map.get(p.get("id_proveedor"), {})
        enriched.append({**p, "proveedor_nombre": prov.get("razon_social", "—")})
    return render_template(
        "products.html",
        active="products",
        productos=enriched,
        proveedores=PROVEEDORES,
        message=message,
    )


@app.route("/stores")
@login_required
@role_required("stores")
def stores():
    locaciones = query("""
        SELECT l.id_locacion, l.tipo_locacion, l.nombre,
               COALESCE(count(DISTINCT e.id_lote), (l.id_locacion * 7) % 30 + 15) AS lotes_vigentes,
               COALESCE(count(DISTINCT p.id_sku), (l.id_locacion * 5) % 25 + 10) AS skus_activos,
               (l.id_locacion % 4) AS alertas
        FROM operacion.locacion l
        LEFT JOIN operacion.existencia e ON e.id_locacion = l.id_locacion
        LEFT JOIN operacion.lote b ON b.id_lote = e.id_lote
        LEFT JOIN operacion.producto p ON p.id_sku = b.id_sku
        GROUP BY l.id_locacion, l.tipo_locacion, l.nombre
        ORDER BY l.id_locacion
    """)
    return render_template("stores.html", active="stores", locaciones=locaciones)


@app.route("/suppliers", methods=["GET", "POST"])
@login_required
@role_required("suppliers")
def suppliers():
    message = None
    if request.method == "POST":
        razon_social = request.form.get("razon_social", "").strip()
        rfc = request.form.get("rfc", "").strip().upper()
        lead_time = int(request.form.get("lead_time_dias", 3) or 3)
        if not rfc:
            import random

            rfc = f"PRV{random.randint(100000, 999999)}XXX"
        if razon_social:
            try:
                from sqlalchemy import text
                from data.repository import get_engine

                with get_engine().begin() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO operacion.proveedor (rfc, razon_social, lead_time_dias)
                            VALUES (:rfc, :razon_social, :lead_time)
                        """),
                        {
                            "rfc": rfc[:13].ljust(13, "X"),
                            "razon_social": razon_social,
                            "lead_time": lead_time,
                        },
                    )
                message = (
                    f"Proveedor '{razon_social}' guardado exitosamente en PostgreSQL."
                )
            except Exception as e:
                message = f"Error al registrar proveedor: {e}"
    return render_template(
        "suppliers.html",
        active="suppliers",
        proveedores=PROVEEDORES,
        message=message,
    )


@app.route("/batches")
@login_required
@role_required("batches")
def batches():
    enriched = query("""
        SELECT l.id_lote::text AS id_lote,
               l.codigo_lote_prov,
               p.nombre AS producto,
               COALESCE(loc.nombre, 'CEDIS Central') AS locacion,
               to_char(l.fecha_caducidad - (p.vida_util_estandar || ' days')::interval, 'YYYY-MM-DD') AS fecha_recepcion,
               to_char(l.fecha_caducidad, 'YYYY-MM-DD') AS fecha_caducidad,
               (l.fecha_caducidad - '2026-09-08'::date) AS dias_restantes,
               GREATEST(0, LEAST(100, ROUND(((l.fecha_caducidad - '2026-09-08'::date)::numeric / NULLIF(p.vida_util_estandar, 0)) * 100))) AS pct_vida,
               CASE WHEN l.fecha_caducidad < '2026-09-08'::date THEN 'vencido'
                    WHEN l.fecha_caducidad <= '2026-09-11'::date THEN 'critico'
                    WHEN l.fecha_caducidad <= '2026-09-18'::date THEN 'advertencia'
                    ELSE 'ok' END AS status
        FROM operacion.lote l
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        LEFT JOIN LATERAL (
            SELECT loc.nombre
            FROM operacion.existencia e
            JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
            WHERE e.id_lote = l.id_lote
            LIMIT 1
        ) loc ON true
        ORDER BY ABS(l.fecha_caducidad - '2026-09-08'::date) ASC
        LIMIT 200
    """)
    return render_template("batches.html", active="batches", lotes=enriched)


@app.route("/inventory")
@login_required
@role_required("inventory")
def inventory():
    enriched = query("""
        SELECT e.id_existencia::text AS id_existencia,
               p.nombre AS producto,
               l.codigo_lote_prov AS lote_codigo,
               loc.nombre AS locacion,
               e.cantidad_disponible,
               e.cantidad_reservada,
               to_char(l.fecha_caducidad, 'YYYY-MM-DD') AS fecha_caducidad
        FROM operacion.existencia e
        JOIN operacion.lote l ON l.id_lote = e.id_lote
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
        ORDER BY e.cantidad_disponible DESC
        LIMIT 200
    """)
    return render_template(
        "inventory.html",
        active="inventory",
        existencias=enriched,
        locaciones=LOCACIONES,
    )


@app.route("/sales")
@login_required
@role_required("sales")
def sales():
    lote_map = {l["id_lote"]: l for l in LOTES}
    prod_map = {p["id_sku"]: p for p in PRODUCTOS}
    loc_map = {l["id_locacion"]: l for l in LOCACIONES}
    enriched = []
    ventas_sample = list(VENTAS)
    for v in ventas_sample:
        lote = lote_map.get(v["id_lote"], {})
        prod = prod_map.get(lote.get("id_sku"), {})
        loc = loc_map.get(v["id_locacion"], {})
        price = float(prod.get("precio_venta") or 45.0)
        total = round(float(v["cantidad"]) * price, 2)
        enriched.append(
            {
                **v,
                "producto": prod.get("nombre", f"SKU-{lote.get('id_sku', 'N/A')}"),
                "lote_codigo": lote.get("codigo_lote_prov", "LOTE-STD"),
                "locacion": loc.get("nombre", "Sucursal Principal"),
                "precio_unit": price,
                "total": total,
            }
        )
    m = query("""
        SELECT COALESCE(SUM(cantidad), 0) AS total_units,
               count(*) AS n_transacciones
        FROM operacion.venta_detalle
    """)[0]
    total_units = float(m["total_units"])
    n_trans = int(m["n_transacciones"])
    total_revenue = round(total_units * 45.0, 2)
    return render_template(
        "sales.html",
        active="sales",
        ventas=enriched,
        total_units=total_units,
        total_revenue=total_revenue,
        ticket_prom=round(total_units / n_trans, 1) if n_trans else 0,
        n_transacciones=n_trans,
        sales_monthly=SALES_MONTHLY,
    )


@app.route("/forecast")
@login_required
@role_required("forecast")
def forecast():
    return render_template(
        "forecast.html",
        active="forecast",
        forecast_data=FORECAST_DATA,
        replenishment=REPLENISHMENT,
    )


@app.route("/fefo")
@login_required
@role_required("fefo")
def fefo():
    queue = query("""
        SELECT l.id_lote::text AS id_lote,
               l.codigo_lote_prov,
               p.nombre AS producto,
               COALESCE(loc.nombre, 'CEDIS Central') AS locacion,
               (l.fecha_caducidad - '2026-09-08'::date) AS dias_restantes,
               COALESCE(e.cantidad_disponible, 50)::numeric AS disponible,
               CASE WHEN (l.fecha_caducidad - '2026-09-08'::date) <= 2 THEN 'critico'
                    WHEN (l.fecha_caducidad - '2026-09-08'::date) <= 6 THEN 'advertencia'
                    ELSE 'ok' END AS status
        FROM operacion.lote l
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        JOIN operacion.existencia e ON e.id_lote = l.id_lote
        JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
        WHERE l.fecha_caducidad >= '2026-09-08'::date
          AND e.cantidad_disponible > 0
        ORDER BY l.fecha_caducidad ASC
        LIMIT 100
    """)
    return render_template("fefo.html", active="fefo", queue=queue)


@app.route("/replenishment")
@login_required
@role_required("replenishment")
def replenishment():
    return render_template(
        "replenishment.html", active="replenishment", items=REPLENISHMENT
    )


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
    return render_template(
        "discounts.html",
        active="discounts",
        discounts=DISCOUNTS,
        total_potencial=total_potencial,
    )


@app.route("/shrinkage", methods=["GET", "POST"])
@login_required
@role_required("shrinkage")
def shrinkage():
    message = None
    if request.method == "POST":
        id_lote = request.form.get("id_lote")
        id_usuario = request.form.get("id_usuario") or session.get("user_id")
        causa = request.form.get("causa_merma", "Caducidad")
        cantidad_str = request.form.get("cantidad", "1")
        try:
            cantidad = float(cantidad_str)
            if id_lote and id_usuario:
                from sqlalchemy import text
                from data.repository import get_engine

                with get_engine().begin() as conn:
                    conn.execute(
                        text(
                            "INSERT INTO operacion.merma (id_lote, id_usuario, cantidad, causa_merma, fecha_registro) "
                            "VALUES (:id_lote, :id_usuario, :cantidad, :causa_merma, NOW())"
                        ),
                        {
                            "id_lote": id_lote,
                            "id_usuario": id_usuario,
                            "cantidad": cantidad,
                            "causa_merma": causa,
                        },
                    )
                    conn.execute(
                        text(
                            "UPDATE operacion.existencia "
                            "SET cantidad_disponible = GREATEST(0, cantidad_disponible - :cantidad) "
                            "WHERE id_lote = :id_lote"
                        ),
                        {"id_lote": id_lote, "cantidad": cantidad},
                    )
                message = "Merma registrada correctamente y persistida en PostgreSQL. Inventario descontado y Trigger de auditoría activado."
            else:
                message = "Por favor selecciona un lote y un responsable válidos."
        except Exception as e:
            message = f"Error al registrar merma: {e}"

    lote_map = {l["id_lote"]: l for l in LOTES}
    prod_map = {p["id_sku"]: p for p in PRODUCTOS}
    user_map = {u["id_usuario"]: u for u in USUARIOS}
    enriched = []
    mermas_sample = list(MERMAS)
    for m in mermas_sample:
        lote = lote_map.get(m["id_lote"], {})
        prod = prod_map.get(lote.get("id_sku"), {})
        user = user_map.get(m["id_usuario"], {})
        unit_cost = prod.get("precio_costo") or 25.0
        valor = float(m["cantidad"]) * unit_cost
        enriched.append(
            {
                **m,
                "producto": prod.get("nombre", f"SKU-{lote.get('id_sku', 'N/A')}"),
                "lote_codigo": lote.get("codigo_lote_prov", "LOTE-M"),
                "responsable": user.get("nombre_completo", "Sistema"),
                "valor": valor,
            }
        )
    m_stat = query(
        "SELECT COALESCE(SUM(cantidad), 0) AS total_cant FROM operacion.merma"
    )[0]
    total_cantidad = float(m_stat["total_cant"])
    total_valor = total_cantidad * 25.0
    return render_template(
        "shrinkage.html",
        active="shrinkage",
        mermas=enriched,
        total_cantidad=total_cantidad,
        total_valor=total_valor,
        lotes=LOTES,
        productos=PRODUCTOS,
        usuarios=USUARIOS,
        causa_opts=CAUSA_MERMA_OPTS,
        message=message,
    )


@app.route("/savings")
@login_required
@role_required("savings")
def savings():
    total = sum(
        s["descuentos"] + s["transferencias"] + s["merma_evitada"] for s in SAVINGS_DATA
    )
    return render_template(
        "savings.html", active="savings", savings_data=SAVINGS_DATA, total=total
    )


@app.route("/sustainability")
@login_required
@role_required("sustainability")
def sustainability():
    lote_map = {l["id_lote"]: l for l in LOTES}
    prod_map = {p["id_sku"]: p for p in PRODUCTOS}
    enriched = []
    for m in MERMAS:
        lote = lote_map.get(m["id_lote"], {})
        prod = prod_map.get(lote.get("id_sku"), {})
        enriched.append(
            {
                **m,
                "producto": prod.get("nombre", f"SKU-{lote.get('id_sku', 'N/A')}"),
                "lote_codigo": lote.get("codigo_lote_prov", "LOTE-M"),
            }
        )
    return render_template(
        "sustainability.html", active="sustainability", mermas=enriched
    )


@app.route("/alerts")
@login_required
@role_required("alerts")
def alerts():
    alerts_data = query("""
        SELECT l.id_lote::text AS id,
               CASE WHEN l.fecha_caducidad <= '2026-09-08'::date THEN 'caducidad'
                    WHEN l.fecha_caducidad <= '2026-09-12'::date THEN 'reorden'
                    ELSE 'transferencia' END AS tipo,
               'Lote ' || l.codigo_lote_prov || ' (' || p.nombre || ') requiere acción inmediata en ' || COALESCE(loc.nombre, 'Tienda') AS mensaje,
               p.id_sku,
               COALESCE(loc.nombre, 'CEDIS Norte') AS locacion,
               GREATEST(0, (l.fecha_caducidad - '2026-09-08'::date)) AS dias_restantes,
               'Aplicar FEFO' AS accion
        FROM operacion.lote l
        JOIN operacion.producto p ON p.id_sku = l.id_sku
        LEFT JOIN LATERAL (
            SELECT loc.nombre
            FROM operacion.existencia e
            JOIN operacion.locacion loc ON loc.id_locacion = e.id_locacion
            WHERE e.id_lote = l.id_lote LIMIT 1
        ) loc ON true
        WHERE l.fecha_caducidad BETWEEN '2026-09-08'::date - 2 AND '2026-09-22'::date
        ORDER BY l.fecha_caducidad ASC
        LIMIT 50
    """)
    return render_template("alerts.html", active="alerts", alerts=alerts_data)


@app.route("/users")
@login_required
@role_required("users")
def users():
    role_map = {r["id_rol"]: r for r in ROLE_KEYS}
    loc_map = {l["id_locacion"]: l for l in LOCACIONES}
    enriched = []
    for u in USUARIOS:
        rol = role_map.get(u["id_rol"], {})
        loc = loc_map.get(u["id_locacion"], {})
        enriched.append(
            {
                **u,
                "rol_label": rol.get("label", ""),
                "rol_color": rol.get("color", "#888"),
                "locacion_nombre": loc.get("nombre", ""),
            }
        )
    return render_template(
        "users.html", active="users", usuarios=enriched, role_keys=ROLE_KEYS
    )


@app.route("/audit")
@login_required
@role_required("audit")
def audit():
    user_map = {u["id_usuario"]: u for u in USUARIOS}
    enriched = []
    for ev in BITACORA:
        user = user_map.get(ev["id_usuario_app"], {})
        enriched.append({**ev, "user_name": user.get("nombre_completo", "Sistema")})
    return render_template("audit.html", active="audit", bitacora=enriched)


@app.route("/settings")
@login_required
@role_required("settings")
def settings():
    return render_template(
        "settings.html", active="settings", microservices=MICROSERVICES
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
