"""
Genera los 5 diagramas de arquitectura del reporte técnico (PNG, fondo blanco).

Cada diagrama se dibuja con matplotlib para que sea reproducible: si cambia el
diseño del sistema, se vuelve a correr este script y las figuras se regeneran.

Sistema de coordenadas: x de 0 a 10, y de 0 a 10 en todas las figuras; el
tamaño físico de la figura decide la proporción final.

Uso:
    python scripts/generar_diagramas.py            # salida en docs/diagramas/
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "diagramas"
DPI = 190

AZUL, AZUL_CLARO = "#1d4ed8", "#dbeafe"
VERDE, VERDE_CLARO = "#15803d", "#dcfce7"
AMBAR, AMBAR_CLARO = "#b45309", "#fef3c7"
MORADO, MORADO_CLARO = "#6d28d9", "#ede9fe"
ROJO, ROJO_CLARO = "#b91c1c", "#fee2e2"
CIAN, CIAN_CLARO = "#0e7490", "#cffafe"
GRIS, GRIS_CLARO = "#1f2937", "#f3f4f6"


# ---------------------------------------------------------------------------
# Primitivas
# ---------------------------------------------------------------------------
def caja(ax, x, y, w, h, titulo="", detalle="", borde=GRIS, fondo=GRIS_CLARO,
         tam=8.0, tam_titulo=None):
    """Rectángulo con título en negrita arriba y detalle debajo."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.015,rounding_size=0.08",
            linewidth=1.15, edgecolor=borde, facecolor=fondo, zorder=2,
        )
    )
    if titulo and detalle:
        ax.text(x + w / 2, y + h * 0.74, titulo, ha="center", va="center",
                fontsize=tam_titulo or tam, color=borde, fontweight="bold",
                zorder=3, linespacing=1.35)
        ax.text(x + w / 2, y + h * 0.31, detalle, ha="center", va="center",
                fontsize=tam - 0.5, color=GRIS, zorder=3, linespacing=1.45)
    else:
        ax.text(x + w / 2, y + h / 2, titulo or detalle, ha="center", va="center",
                fontsize=tam, color=GRIS, zorder=3, linespacing=1.5)


def banda(ax, x, y, w, h, titulo, color):
    """Marco punteado con su etiqueta ENCIMA, para no tapar el contenido."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.015,rounding_size=0.1",
            linewidth=1.5, edgecolor=color, facecolor="none",
            linestyle=(0, (6, 3)), zorder=1,
        )
    )
    ax.text(x + 0.06, y + h + 0.13, titulo, ha="left", va="bottom",
            fontsize=9.5, color=color, fontweight="bold", zorder=3)


def flecha(ax, x1, y1, x2, y2, texto="", color=GRIS, estilo="-|>", tam=7.6,
           rad=0.0, dy=0.12, dx=0.0):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1), (x2, y2), arrowstyle=estilo, mutation_scale=12,
            linewidth=1.35, color=color, zorder=1,
            connectionstyle=f"arc3,rad={rad}",
        )
    )
    if texto:
        ax.text((x1 + x2) / 2 + dx, (y1 + y2) / 2 + dy, texto, ha="center",
                va="bottom", fontsize=tam, color=color, zorder=4,
                bbox=dict(boxstyle="round,pad=0.24", fc="white", ec="none", alpha=0.95))


def lienzo(titulo, ancho=13.5, alto=10.0):
    fig, ax = plt.subplots(figsize=(ancho, alto))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_title(titulo, fontsize=13.5, fontweight="bold", color=GRIS, pad=12)
    return fig, ax


def guardar(fig, nombre):
    SALIDA.mkdir(parents=True, exist_ok=True)
    fig.savefig(SALIDA / nombre, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  docs/diagramas/{nombre}")


# ===========================================================================
# 1. Componentes
# ===========================================================================
def diagrama_componentes():
    fig, ax = lienzo("Diagrama de componentes — FreshTrack", 13.5, 10.5)

    banda(ax, 0.15, 8.05, 9.7, 1.35, "1 · Presentación", AZUL)
    caja(ax, 0.4, 8.25, 2.5, 0.95, "Navegador", "HTML + CSS + JS", AZUL, AZUL_CLARO, 8)
    caja(ax, 3.05, 8.25, 4.2, 0.95, "Blueprints Flask",
         "publico · auth · catalogo\noperacion · analitica · panel · api", AZUL, AZUL_CLARO, 8)
    caja(ax, 7.4, 8.25, 2.2, 0.95, "Vistas Jinja2",
         "base.html + _macros\nstatic/freshtrack.css", AZUL, AZUL_CLARO, 8)

    banda(ax, 0.15, 5.55, 9.7, 2.2, "2 · Dominio — reglas de negocio", VERDE)
    dominios = [
        ("ventas.py", "FEFO transaccional\ncon FOR UPDATE"),
        ("inventario.py", "existencias\ny kardex"),
        ("mermas.py", "7 causas\nvalidación previa"),
        ("pronostico.py", "MM · MMP\nsuavizado exponencial"),
        ("reabastecimiento.py", "demanda + SS\n− útil − entradas"),
    ]
    for i, (t, d) in enumerate(dominios):
        caja(ax, 0.38 + i * 1.93, 6.85, 1.8, 0.72, t, d, VERDE, VERDE_CLARO, 7.4)
    dominios2 = [
        ("transferencias.py", "4 validaciones\nguardadas en la fila"),
        ("descuentos.py", "lotes por vencer\ncon aprobación"),
        ("alertas.py", "7 tipos\ncon huella única"),
        ("kpis.py", "indicadores\ndel panel"),
        ("seguridad", "security.py · navegacion.py\nsesión · JWT · permisos"),
    ]
    for i, (t, d) in enumerate(dominios2):
        caja(ax, 0.38 + i * 1.93, 5.78, 1.8, 0.72, t, d, VERDE, VERDE_CLARO, 7.4)

    banda(ax, 0.15, 3.85, 9.7, 1.5, "3 · Acceso a datos", CIAN)
    caja(ax, 0.4, 4.05, 2.9, 1.1, "db.py",
         "SQLAlchemy 2.x Core + psycopg 3\nquery · escalar · escribir\ntransaccion()", CIAN, CIAN_CLARO, 7.6)
    caja(ax, 3.55, 4.05, 2.9, 1.1, "repos/catalogo.py",
         "CRUD de productos, proveedores\ny tiendas/CEDIS", CIAN, CIAN_CLARO, 7.6)
    caja(ax, 6.7, 4.05, 2.9, 1.1, "auditoria.py",
         "eventos de aplicación vía\nfn_registrar_accion()", CIAN, CIAN_CLARO, 7.6)

    banda(ax, 0.15, 2.15, 9.7, 1.5, "4 · Persistencia — PostgreSQL 17", MORADO)
    caja(ax, 0.4, 2.35, 3.0, 1.1, "esquema operacion",
         "catálogos, lotes, existencias,\nventas, mermas, kardex", MORADO, MORADO_CLARO, 7.8)
    caja(ax, 3.65, 2.35, 3.0, 1.1, "esquema analitica",
         "pronóstico, reabastecimiento,\ntransferencias, alertas", MORADO, MORADO_CLARO, 7.8)
    caja(ax, 6.9, 2.35, 2.7, 1.1, "esquema auditoria",
         "bitacora_eventos\n(inmutable por disparador)", MORADO, MORADO_CLARO, 7.8)

    banda(ax, 0.15, 0.35, 9.7, 1.5, "5 · Procesos por lote, fuera de la aplicación web", AMBAR)
    caja(ax, 0.4, 0.55, 3.0, 1.1, "bootstrap_db.py",
         "base + roles + esquemas\n+ datos base (idempotente)", AMBAR, AMBAR_CLARO, 7.8)
    caja(ax, 3.65, 0.55, 3.0, 1.1, "ETL.py",
         "historia operativa:\nlotes, ventas, mermas, kardex", AMBAR, AMBAR_CLARO, 7.8)
    caja(ax, 6.9, 0.55, 2.7, 1.1, "demo_avance2.py",
         "escenario extremo a extremo\ny verificación", AMBAR, AMBAR_CLARO, 7.8)

    flecha(ax, 5.0, 7.9, 5.0, 7.75, color=AZUL)
    flecha(ax, 5.0, 5.4, 5.0, 5.25, color=VERDE)
    flecha(ax, 5.0, 3.7, 5.0, 3.55, color=MORADO)
    ax.text(5.12, 7.83, "invoca", fontsize=7.4, color=AZUL, va="center")
    ax.text(5.12, 5.33, "usa", fontsize=7.4, color=VERDE, va="center")
    ax.text(5.12, 3.63, "SQL", fontsize=7.4, color=MORADO, va="center")

    guardar(fig, "01_componentes.png")


# ===========================================================================
# 2. Red
# ===========================================================================
def diagrama_red():
    fig, ax = lienzo("Diagrama de red y despliegue", 13.5, 8.2)

    banda(ax, 0.15, 6.15, 2.8, 2.9, "Zona cliente", AZUL)
    caja(ax, 0.4, 7.75, 2.3, 1.05, "Estación de trabajo",
         "navegador web\nChrome · Edge · Firefox", AZUL, AZUL_CLARO, 8)
    caja(ax, 0.4, 6.4, 2.3, 1.15, "Cliente de API",
         "curl · Postman\no aplicación móvil", AZUL, AZUL_CLARO, 8)

    banda(ax, 3.15, 6.15, 3.2, 2.9, "Servidor de aplicación", VERDE)
    caja(ax, 3.4, 7.55, 2.7, 1.25, "Proceso Flask",
         "run.py → create_app()\n\n127.0.0.1 : 5000\nAPP_HOST / APP_PORT", VERDE, VERDE_CLARO, 8)
    caja(ax, 3.4, 6.4, 2.7, 0.95, "Credenciales de sesión",
         "cookie firmada con SECRET_KEY\ntoken JWT HS256 (JWT_SECRET_KEY)", ROJO, ROJO_CLARO, 7.6)

    banda(ax, 6.55, 6.15, 3.3, 2.9, "Servidor de base de datos", MORADO)
    caja(ax, 6.8, 7.55, 2.8, 1.25, "PostgreSQL 17",
         "localhost : 5433\nbase retail_perecederos\nextensiones pgcrypto", MORADO, MORADO_CLARO, 8)
    caja(ax, 6.8, 6.4, 2.8, 0.95, "Roles de conexión",
         "postgres (administración)\napp_backend · app_auditor · app_etl", MORADO, MORADO_CLARO, 7.6)

    flecha(ax, 2.7, 8.3, 3.4, 8.3, "HTTP/HTTPS · 5000", AZUL, dy=0.1)
    flecha(ax, 3.4, 7.85, 2.7, 7.85, "HTML / JSON", AZUL, dy=-0.42)
    flecha(ax, 2.7, 7.0, 3.4, 7.0, "Bearer <JWT>", ROJO, dy=0.1)
    flecha(ax, 6.1, 8.3, 6.8, 8.3, "TCP 5432/5433", MORADO, dy=0.1)
    flecha(ax, 6.8, 7.85, 6.1, 7.85, "resultset", MORADO, dy=-0.42)

    banda(ax, 0.15, 2.2, 9.7, 3.5, "Despliegue con contenedores (docker compose)", AMBAR)
    caja(ax, 0.4, 4.35, 4.4, 1.1, "Contenedor freshtrack_app",
         "Dockerfile sobre python:3.13-slim\npublica ${APP_PORT}:5000 · volumen . → /app",
         AMBAR, AMBAR_CLARO, 8)
    caja(ax, 5.2, 4.35, 4.4, 1.1, "Contenedor freshtrack_db",
         "imagen postgres:17-alpine\npublica ${POSTGRES_PORT}:5432 · volumen postgres_data",
         AMBAR, AMBAR_CLARO, 8)
    caja(ax, 0.4, 2.45, 9.2, 1.65, "Detalles de la red",
         "Red bridge interna: los servicios se resuelven por nombre (app, postgres).\n"
         "El contenedor de base de datos ejecuta ./sql la primera vez que se crea el volumen\n"
         "y publica un healthcheck con pg_isready del que depende el arranque de la aplicación.\n"
         "Los secretos llegan por env_file (.env): no hay credenciales dentro de la imagen.",
         GRIS, "white", 8)
    flecha(ax, 4.85, 4.9, 5.15, 4.9, color=AMBAR)

    caja(ax, 0.15, 0.35, 9.7, 1.5, "Puertos y protocolos",
         "5000  →  interfaz web de la aplicación (HTTP/HTTPS)\n"
         "5433  →  PostgreSQL en el entorno local  ·  5432 dentro del contenedor\n"
         "El cliente de API usa el mismo puerto 5000 con el encabezado Authorization.",
         GRIS, GRIS_CLARO, 8)

    guardar(fig, "02_red.png")


# ===========================================================================
# 3. Comunicación entre aplicaciones
# ===========================================================================
def diagrama_comunicacion():
    fig, ax = lienzo("Diagrama de comunicación entre aplicaciones", 13.5, 9.2)

    actores = ["Navegador\n(usuario)", "Flask\n(aplicación web)", "PostgreSQL\n(base de datos)",
               "Scripts\n(ETL · demo)"]
    xs = [1.25, 4.0, 6.75, 9.1]
    for x, a in zip(xs, actores):
        caja(ax, x - 1.0, 9.0, 2.0, 0.75, detalle=a, borde=AZUL, fondo=AZUL_CLARO, tam=8.6)
        ax.plot([x, x], [0.9, 9.0], color="#cbd5e1", linewidth=1.1,
                linestyle=(0, (4, 4)), zorder=0)

    def msj(y, i, j, texto, color=GRIS, dy=0.1):
        flecha(ax, xs[i], y, xs[j], y, color=color, dy=dy)
        ax.text((xs[i] + xs[j]) / 2, y + 0.08, texto, ha="center", va="bottom",
                fontsize=8, color=color, zorder=4,
                bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.95))

    ax.text(0.1, 8.6, "Flujo web (formularios)", fontsize=9.5, fontweight="bold", color=AZUL)
    msj(8.35, 0, 1, "1. GET /  ·  POST /login  (correo y contraseña)")
    msj(7.75, 1, 2, "2. SELECT con crypt(:password, password_hash)")
    msj(7.15, 2, 1, "3. fila de operacion.usuario unida con operacion.rol", GRIS, -0.45)
    msj(6.55, 1, 2, "4. INSERT del jti en sesion_usuario y de los eventos de auditoría")
    msj(5.95, 1, 0, "5. cookie de sesión + JWT y redirección al panel", GRIS, -0.45)
    msj(5.35, 0, 1, "6. GET /inventario  ·  POST /ventas  (consumo FEFO)")
    msj(4.75, 1, 2, "7. SELECT … FOR UPDATE, UPDATE de existencias e INSERT del kardex")
    msj(4.15, 2, 1, "8. commit o rollback: todo ocurre en una sola transacción", GRIS, -0.45)

    ax.text(0.1, 3.72, "Vía API (JSON)", fontsize=9.5, fontweight="bold", color=CIAN)
    msj(3.45, 0, 1, "9. GET /api/kpis con Authorization: Bearer <JWT>", CIAN)
    msj(2.85, 1, 2, "10. decodifica el JWT, verifica el jti y consulta", CIAN)
    msj(2.25, 1, 0, "11. JSON con los Decimal convertidos a número", CIAN, -0.45)

    ax.text(0.1, 1.82, "Procesos por lote", fontsize=9.5, fontweight="bold", color=AMBAR)
    flecha(ax, xs[3], 1.5, xs[2], 1.5, color=AMBAR, dy=0.1)
    ax.text((xs[3] + xs[2]) / 2, 1.58, "12. carga masiva con los disparadores de auditoría desactivados",
            ha="center", va="bottom", fontsize=8, color=AMBAR, zorder=4,
            bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.95))
    flecha(ax, xs[3], 0.75, xs[1], 0.75, color=AMBAR)
    ax.text(6.55, 0.83, "13. demo_avance2.py usa el cliente de pruebas de Flask (capa HTTP real)",
            ha="center", va="bottom", fontsize=8, color=AMBAR, zorder=4,
            bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.95))

    guardar(fig, "03_comunicacion.png")


# ===========================================================================
# 4. Autenticación
# ===========================================================================
def diagrama_autenticacion():
    fig, ax = lienzo("Diagrama de autenticación y control de acceso", 13.5, 9.6)

    caja(ax, 0.3, 8.9, 2.4, 0.75, "1 · Usuario", "correo + contraseña", AZUL, AZUL_CLARO, 8.2)
    caja(ax, 3.0, 8.9, 2.6, 0.75, "2 · POST /login", "auth.login", AZUL, AZUL_CLARO, 8.2)
    caja(ax, 5.9, 8.9, 3.8, 0.75, "3 · PostgreSQL",
         "crypt(:password, u.password_hash) = u.password_hash", MORADO, MORADO_CLARO, 8)

    caja(ax, 0.3, 7.4, 4.5, 1.15, "4 · Validaciones, en este orden",
         "el usuario existe · no está bloqueado\nla contraseña coincide · estado_activo = true",
         ROJO, ROJO_CLARO, 8.2)
    caja(ax, 5.2, 7.4, 4.5, 1.15, "Si alguna falla",
         "se incrementa intentos_fallidos y al llegar al máximo\n"
         "se bloquea 15 minutos. Se registra LOGIN_FALLIDO.", ROJO, ROJO_CLARO, 8.2)

    caja(ax, 0.3, 5.75, 4.5, 1.35, "5 · Se emiten dos credenciales",
         "cookie de sesión firmada con SECRET_KEY\nJWT HS256 con sub, rol, jti y exp\n"
         "el jti se guarda en operacion.sesion_usuario", VERDE, VERDE_CLARO, 8.2)
    caja(ax, 5.2, 5.75, 4.5, 1.35, "6 · Se resuelven los permisos",
         "operacion.rol.clave → VISTAS_POR_ROL\nse construye el menú y la pantalla inicial\n"
         "se registra LOGIN en la bitácora", VERDE, VERDE_CLARO, 8.2)

    caja(ax, 0.3, 3.7, 9.4, 1.75, "7 · Protección de cada petición — decoradores",
         "login_required            exige sesión; sin ella redirige a /login?next=…\n"
         "requiere_vista(\"ventas\")    exige que el rol tenga esa pantalla\n"
         "requiere_rol(\"admin\")       exige uno de los roles indicados\n"
         "token_requerido           exige Authorization: Bearer <JWT> y valida firma, expiración y jti\n"
         "rol_en_token(\"admin\")       restringe las escrituras de la API",
         GRIS, GRIS_CLARO, 8.0)

    caja(ax, 0.3, 2.35, 4.5, 1.1, "8 · Cierre de sesión y revocación",
         "logout → UPDATE sesion_usuario SET revocado = true\n"
         "se registra LOGOUT y el token deja de ser válido", AMBAR, AMBAR_CLARO, 8.2)
    caja(ax, 5.2, 2.35, 4.5, 1.1, "9 · Propiedad de seguridad",
         "crypt() se evalúa DENTRO de PostgreSQL: la contraseña\n"
         "en claro nunca se compara en Python.", AMBAR, AMBAR_CLARO, 8.2)

    caja(ax, 0.3, 0.35, 9.4, 1.65, "10 · Roles del sistema y su alcance",
         "admin          todo el sistema\n"
         "buyer          catálogos, lotes y reabastecimiento\n"
         "planner        pronóstico, transferencias y analítica\n"
         "store_manager  operación de la tienda y aprobaciones de reabastecimiento,\n"
         "               transferencias y descuentos\n"
         "warehouse      lotes, inventario, FEFO y mermas        supplier  sus productos y lotes\n"
         "auditor        bitácora, mermas y desperdicio evitado (solo lectura)",
         AZUL, AZUL_CLARO, 8.0)

    flecha(ax, 2.7, 9.28, 3.0, 9.28, color=AZUL)
    flecha(ax, 5.6, 9.28, 5.9, 9.28, color=MORADO)
    flecha(ax, 7.8, 8.88, 2.55, 8.57, color=MORADO, rad=0.1)
    flecha(ax, 2.55, 7.38, 2.55, 7.12, color=VERDE)
    flecha(ax, 4.82, 6.42, 5.18, 6.42, color=VERDE)
    flecha(ax, 5.0, 5.73, 5.0, 5.47, color=GRIS)
    flecha(ax, 2.55, 3.68, 2.55, 3.47, color=GRIS)

    guardar(fig, "04_autenticacion.png")


# ===========================================================================
# 5. Almacenamiento de datos
# ===========================================================================
def diagrama_almacenamiento():
    fig, ax = lienzo("Diagrama de almacenamiento de datos — PostgreSQL 17", 13.5, 10.5)

    banda(ax, 0.15, 5.15, 9.7, 4.25, "esquema  operacion  —  transaccional", AZUL)
    catalogo = [
        (0.4, 7.75, "rol", "clave · nombre_rol"),
        (2.85, 7.75, "usuario", "email · password_hash\nestado_activo · intentos"),
        (5.3, 7.75, "locacion", "Tienda o CEDIS\nactivo"),
        (7.75, 7.75, "proveedor", "rfc · lead_time_dias\nmoq · activo"),
        (0.4, 6.55, "producto", "codigo_gtin · categoria\nvida_util_estandar\nstock_seguridad"),
        (2.85, 6.55, "regla_riesgo", "por SKU, por categoría\no por defecto"),
        (5.3, 6.55, "lote", "fechas · cantidad_recibida\ncosto_unitario · estado"),
        (7.75, 6.55, "sesion_usuario", "jti · expira_en\nrevocado"),
        (0.4, 5.3, "existencia", "lote × locación\ncantidad_disponible"),
        (2.85, 5.3, "movimiento_inventario", "kardex: RECEPCION, VENTA\nMERMA, TRANSFERENCIA"),
        (5.3, 5.3, "venta y venta_detalle", "folio · línea por lote\n(FEFO)"),
        (7.75, 5.3, "merma", "7 causas · valor_merma\ncalculado por la base"),
    ]
    for x, y, t, d in catalogo:
        caja(ax, x, y, 2.25, 1.05, t, d, AZUL, AZUL_CLARO, 7.6)

    banda(ax, 0.15, 2.10, 4.75, 2.55, "esquema  analitica", VERDE)
    for y, t, d in (
        (4.05, "forecast_run y forecast_result", "MAE · RMSE · WMAPE por producto y tienda"),
        (3.45, "orden_reabastecimiento", "demanda · útil · entradas → necesidad_neta"),
        (2.85, "transferencia y descuento", "validaciones jsonb · estado y decisión"),
        (2.25, "alerta y desperdicio_evitado", "huella única · metodología explícita"),
    ):
        caja(ax, 0.4, y, 4.25, 0.52, t, d, VERDE, VERDE_CLARO, 7.4)

    banda(ax, 5.1, 2.10, 4.75, 2.55, "esquema  auditoria", ROJO)
    caja(ax, 5.35, 3.4, 4.25, 1.1, "bitacora_eventos",
         "accion · tipo_operacion · nombre_tabla\nid_registro · id_usuario_app · usuario_email\n"
         "estado_anterior y estado_nuevo (jsonb) · ip · fecha_evento",
         ROJO, ROJO_CLARO, 7.4)
    caja(ax, 5.35, 2.4, 4.25, 0.9, "Inmutable por diseño",
         "el disparador trg_proteger_bitacora bloquea\ncualquier UPDATE o DELETE sobre la bitácora",
         ROJO, "white", 7.4)

    caja(ax, 0.15, 0.30, 9.7, 1.65, "Claves, garantías y vistas",
         "Identificadores UUID con gen_random_uuid()  ·  catálogos con columna activo  ·  restricciones\n"
         "CHECK en fechas, cantidades y causas de merma  ·  claves foráneas con ON DELETE RESTRICT\n"
         "donde la integridad importa  ·  índices para las series de pronóstico (id_sku, id_locacion, fecha)\n"
         "y para la cola FEFO (id_sku, fecha_caducidad).\n"
         "Vistas: v_inventario_lote · v_lote_riesgo · v_demanda_diaria · v_merma_agregada · "
         "v_alerta_abierta · v_trazabilidad_lote",
         GRIS, GRIS_CLARO, 7.8)

    guardar(fig, "05_almacenamiento.png")


if __name__ == "__main__":
    print("Generando diagramas en docs/diagramas/…")
    diagrama_componentes()
    diagrama_red()
    diagrama_comunicacion()
    diagrama_autenticacion()
    diagrama_almacenamiento()
    print("Listo.")
