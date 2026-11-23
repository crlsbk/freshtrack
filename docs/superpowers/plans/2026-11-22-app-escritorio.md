# App de escritorio FreshTrack — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App de escritorio PySide6 instalable para compradores y planeadores que consume solo XML (validado con XSD) de los microservicios.

**Architecture:** Paquete `desktop/freshtrack_desktop` totalmente independiente de `app/`. Un núcleo (config, códec XML, cliente HTTP, sesión, bitácora) y una ventana con barra lateral de páginas; cada página recibe un `AppContext` y llama al backend en hilos de `QThreadPool`. Dos endpoints nuevos en el backend (refresh de JWT e importación de ventas).

**Tech Stack:** Python 3.14, PySide6 6.12 (QtWidgets, QtCharts, QtPrintSupport), requests, lxml, pytest + pytest-qt, PyInstaller. Backend: Flask existente.

**Spec:** `docs/superpowers/specs/2026-11-22-app-escritorio-design.md`

## Global Constraints
- `desktop/` NUNCA importa `app.*` ni habla con PostgreSQL/Mongo/Redis.
- Toda petición de la app lleva `Accept: application/xml`; los cuerpos van en XML (`Content-Type: application/xml; charset=utf-8`). Nada de JSON.
- Cada petición lleva `X-Correlation-Id` (uuid4 hex) y `User-Agent: FreshTrack-Desktop/1.0`.
- Roles que pueden iniciar sesión en la app: `buyer`, `planner`, `admin`. Otro rol → mensaje "Esta aplicación es para compradores y planeadores" y logout.
- URLs por defecto: auth 5001, catalog 5002, inventory 5003, commercial 5004, asn 5005, planning 5006, alerts 5007, audit 5008 en `http://localhost`. Modo gateway: si `FRESHTRACK_GATEWAY_URL` está definido, todos los servicios usan esa base (el Caddyfile enruta por prefijo `/api/v1/<svc>`).
- Textos de la UI en español.
- Pruebas: `.venv/bin/python -m pytest desktop/tests` (Qt con `QT_QPA_PLATFORM=offscreen`).
- Dependencias de la app en `desktop/requirements.txt`: `PySide6>=6.8`, `requests>=2.32`, `lxml>=5.3`; dev: `pytest-qt>=4.4`, `pyinstaller>=6.11` (ya instaladas en `.venv`).

## Review Focus
1. Respuesta de lista con 0 o 1 elemento (`<ordenes/>` o un solo `<item>`): las tablas deben mostrar 0/1 filas, no romper → `as_list` probado en Task 3.
2. Servicio apagado o timeout: la UI muestra "Servicio X no disponible" y no se congela ni cierra → prueba en Task 3 (ServiceUnavailable) y Task 4 (diálogo de error).
3. Token revocado desde otro cliente: 401 → un intento de refresh → si falla, vuelve al login → Task 3.
4. Respuesta que no es XML (HTML de error de proxy, JSON): error `XmlContractError` claro, no excepción cruda → Task 3.
5. CSV de importación con filas inválidas (sku no numérico, cantidad ≤ 0, fecha mal): se reportan por fila sin enviar nada inválido → Task 7.

---

### Task 1: Backend — `POST /api/v1/auth/refresh`
**Files:** Modify `app/services/auth_service/app.py`; Test `tests/unit/test_auth_refresh.py`
**Interfaces:** Produces `POST /api/v1/auth/refresh` (Bearer requerido) → 200 `auth_response` con los mismos campos que login (`token, jti, token_type, expira_en_segundos, usuario`) y revoca el jti anterior (`revocar_token`).
- [ ] Test: con token válido y sesión en fakeredis (monkeypatch `crear_token`, `revocar_token` y `decodificar_token` como en `tests/unit/test_seguridad_jwt.py`), `POST` devuelve 200 con `token` nuevo y se llamó `revocar_token(jti_viejo)`; sin token → 401 `token_requerido`; con `Accept: application/xml` la raíz es `<auth_response>`.
- [ ] Implementar con `@requiere_auth()`, `@documentar(...)` y `@limite_tasa(limite=30, ventana_segundos=60)`; construir el dict usuario desde `g.usuario_actual` (`id_usuario=sub, email, nombre_completo=nombre, rol_clave=rol, id_locacion`).
- [ ] `pytest tests/unit/test_auth_refresh.py -v` pasa; `pytest tests/unit -q` sin regresiones. Commit.

### Task 2: Backend — `POST /api/v1/commercial/sales/import`
**Files:** Modify `app/services/commercial_service/app.py`; Create `contracts/xsd/sales_import_request.xsd`; Test `tests/unit/test_sales_import.py`
**Interfaces:** Body raíz `<sales_import_request>` con `<id_locacion>` (positiveInteger) y `<tickets>` con 1..500 `<ticket>`; cada ticket: `<folio_externo>` (string 1..60), `<canal>` opcional (TIENDA|ONLINE|MAYOREO), `<lineas>` con 1..100 `<linea>` de `<id_sku>` positiveInteger y `<cantidad>` decimal > 0. Roles `buyer`, `planner` (admin pasa siempre). Respuesta 200 raíz `sales_import_result`: `{importados:int, duplicados:int, errores:int, resultados:[{folio_externo, estado: IMPORTADO|DUPLICADO|ERROR, id_venta?, folio?, mensaje?}]}`.
- Ojo: en XML las listas se leen con `xml_a_dict`; la etiqueta `ticket` no está en `_ETIQUETAS_LISTA` → agregar `"ticket"` a ese set en `app/services/common/response.py` (y `linea` ya está).
- Idempotencia: `SET importacion:venta:{id_locacion}:{folio_externo} NX EX 30d` en Redis; si Redis no responde → 503 `redis_no_disponible` (no se importa nada para no duplicar). Cada ticket se registra con `app.domain.ventas.registrar_venta(id_locacion=..., lineas=..., usuario=usuario_desde_token(), canal=...)`; si falla (ValueError/inventario insuficiente) se libera la clave y el ticket queda `ERROR` con el mensaje; los demás siguen.
- [ ] Tests (fakeredis, `registrar_venta` monkeypatched): XML válido con 2 tickets → 2 IMPORTADO; reenviar el mismo → 2 DUPLICADO; XML que viola el XSD (cantidad 0) → 400 `xml_no_cumple_contrato`; rol `warehouse` → 403; un ticket que lanza ValueError → ERROR y el otro IMPORTADO; `test_todos_los_xsd_compilan` sigue pasando.
- [ ] Implementar; `pytest tests/unit -q` pasa. Commit.

### Task 3: Núcleo de la app (sin Qt)
**Files:** Create `desktop/requirements.txt`, `desktop/freshtrack_desktop/__init__.py` (`__version__ = "1.0.0"`), `core/config.py`, `core/xml_codec.py`, `core/errors.py`, `core/session.py`, `core/api_client.py`, `core/activity_log.py`; Tests `desktop/tests/conftest.py`, `desktop/tests/test_xml_codec.py`, `desktop/tests/test_api_client.py`, `desktop/tests/test_activity_log.py`; `desktop/pytest.ini` (`testpaths = tests`, `qt_api = pyside6`).
**Interfaces (Produces):**
- `config.Settings` dataclass: `base_urls: dict[str,str]` (claves `auth, catalog, inventory, commercial, asn, planning, alerts, audit`), `timeout: float = 15`, `data_dir: Path` (`~/.freshtrack_desktop`), `Settings.load() -> Settings` (env `FRESHTRACK_GATEWAY_URL`, `FRESHTRACK_HOST`, archivo `data_dir/config.ini`), `save()`, `xsd_dir() -> Path` (env `FRESHTRACK_XSD_DIR` → `sys._MEIPASS/contracts/xsd` → `<repo>/contracts/xsd`).
- `errors`: `ApiError(Exception)` con `status:int, error:str, mensaje:str, correlation_id:str, detalles:Any`; `ServiceUnavailable(ApiError)` (status 0, error `servicio_no_disponible`, atributo `service`); `XmlContractError(ApiError)` (error `xml_invalido`, `detalles` = lista de motivos).
- `xml_codec`: `parse_xml(data: bytes|str) -> tuple[str, Any]` (raíz, valor; mismas reglas que `_valor_xml` del servidor, listas si las hijas comparten etiqueta y (>1 o etiqueta en {item, item_carga, linea, subitem, ticket})); `to_xml(data: dict, root: str) -> bytes` (listas → `<item>` salvo que la clave sea `tickets`→`ticket`, `lineas`→`linea`); `validate(xml: bytes, xsd_name: str) -> None` (lxml, cache de esquemas, lanza `XmlContractError` con hasta 10 motivos); `as_list(v) -> list`; `num(v, default=0.0) -> float`.
- `session.Session`: `token, jti, usuario: dict, expira_en: float`; `rol` property; `can(*roles) -> bool` (admin siempre True); `Session.DESKTOP_ROLES = {"buyer","planner","admin"}`.
- `api_client.Exchange` dataclass `method, url, status, request_xml: str, response_text: str, correlation_id, elapsed_ms`.
- `api_client.ApiClient(settings, *, on_unauthorized: Callable[[], None] = lambda: None)`: `session: Session|None`; `listeners: list[Callable[[Exchange], None]]`; `login(email, password) -> Session` (valida `login_request.xsd` antes de enviar); `logout()`; `refresh() -> bool`; `call(service, method, path, *, params=None, body=None, body_root=None, body_xsd=None, expect_root=None, response_xsd=None) -> Any`; `get_bytes(service, path, params=None) -> bytes` (PDF, `Accept: application/pdf`); `health(service) -> dict` (GET `/health` con XML; incluye `elapsed_ms`).
- Comportamiento: respuesta no-XML o mal formada → `XmlContractError`; raíz `error_response` (status ≥400) → `ApiError` con sus campos; `requests.ConnectionError/Timeout` → `ServiceUnavailable`; 401 en cualquier ruta que no sea `/auth/login` ni `/auth/refresh` → un `refresh()` y reintento; si vuelve a fallar → `session=None`, `on_unauthorized()` y se lanza el `ApiError`. Si `expect_root` no coincide → `XmlContractError`. Respuestas `error_response`, `auth_response`, `service_health` se validan contra su XSD cuando el archivo existe.
- `activity_log.ActivityLog(path: Path)`: `record(action: str, detail: str, ok: bool = True) -> None` (línea JSON con ts ISO, usuario, acción, detalle, ok; `RotatingFileHandler` 1 MB × 3); `set_user(email)`; `tail(n=200) -> list[dict]`; `sync_remote(api)` envía las acciones pendientes a `audit` `POST /api/v1/audit/log` (raíz `audit_log_request`, `accion` saneada a `[A-Za-z_]{3,40}` con prefijo `DESKTOP_`, `tabla="desktop"`, descripcion ≤500), sin propagar errores.
- Pruebas: servidor falso con `monkeypatch` sobre `requests.Session.request` (fixture `fake_http` en conftest que registra rutas → (status, body, headers)). Casos: parse de lista vacía/1 item/varios; ida y vuelta `to_xml→parse_xml`; validate rechaza login sin password; HTML como respuesta → XmlContractError; error_response 403 → ApiError(403, "acceso_denegado"); ConnectionError → ServiceUnavailable; 401 → refresh ok → reintento ok (2 llamadas al endpoint); 401 → refresh 401 → on_unauthorized llamado y session None; todas las peticiones llevan `Accept: application/xml` y `X-Correlation-Id`; login con rol `warehouse` sigue devolviendo Session (el bloqueo de rol es de la UI); activity_log escribe y `tail` lee.
- [ ] Tests primero (fallan), implementar, `pytest desktop/tests -q` pasa. Commit.

### Task 4: Shell Qt — ventana, login, contexto, widgets comunes, estado de servicios
**Files:** Create `desktop/freshtrack_desktop/__main__.py`, `app.py` (`main()`), `ui/theme.py`, `ui/context.py`, `ui/worker.py`, `ui/widgets.py`, `ui/login_dialog.py`, `ui/main_window.py`, `ui/xml_inspector.py`, `ui/pages/__init__.py`, `ui/pages/base.py`, `ui/pages/estado.py`, `ui/pages/actividad.py`; `desktop/run_desktop.py` (lanzador). Tests `desktop/tests/test_shell.py`.
**Interfaces (Produces):**
- `context.AppContext`: `settings, api: ApiClient, log: ActivityLog, window (QMainWindow|None)`; `run(fn, *args, on_ok=None, on_error=None, busy: QWidget|None=None)` ejecuta en `QThreadPool` vía `worker.Worker` y entrega resultado/excepción en el hilo de UI; `show_error(exc, parent)` (diálogo: mensaje según tipo — ServiceUnavailable: "El servicio {service} no está disponible", 403: "No tienes permiso para esta acción", XmlContractError: "La respuesta no cumple el contrato XML"; siempre muestra `correlation_id` y lo registra en ActivityLog); `notify(text)` (barra de estado).
- `pages.base.BasePage(QWidget)`: atributos de clase `title: str`, `icon: str` (nombre de QStyle.StandardPixmap o vacío), `roles: tuple[str,...]` (vacío = todos); `__init__(self, ctx: AppContext)`; `on_show()` (se llama al activar la página; por defecto `refresh()`); `refresh()`.
- `widgets`: `DataTable(QWidget)` con `set_columns(list[tuple[key, header]])`, `set_rows(list[dict])`, `selected_row() -> dict|None`, `rows() -> list[dict]`, filtro de texto, ordenable, `export_csv(path)`, `print_table(title, parent)` (QPrinter + QPrintDialog, renderiza HTML del contenido); `KpiCard(title)` con `set_value(text, sub="")`; `Toolbar(QHBoxLayout helper)`; `confirm(parent, text) -> bool`; `ask_text(parent, title, label) -> str|None`.
- `main_window.MainWindow(ctx)`: barra lateral (QListWidget) + QStackedWidget; `register_pages(list[type[BasePage]])` filtra por `ctx.api.session.can(*page.roles)`; menú Archivo (Cerrar sesión, Salir), Ver (Inspector XML F12, Actividad), Ayuda (Acerca de); barra de estado con usuario/rol y servicio de la última llamada. `on_unauthorized` → cierra la ventana y vuelve al login con mensaje "Tu sesión terminó o fue revocada".
- `login_dialog.LoginDialog(ctx)`: correo, contraseña, botón "Servidores…" (edita host/gateway y guarda `Settings`), atajos de cuentas demo buyer/planner; rechaza roles fuera de `DESKTOP_ROLES` (hace logout).
- `xml_inspector.XmlInspector(QDockWidget)`: se suscribe a `api.listeners`; lista de los últimos 50 `Exchange` y muestra petición/respuesta XML con indentación.
- `pages.estado.EstadoPage`: tabla de los 8 servicios con estado (OK/DEGRADADO/CAÍDO), dependencias, latencia, versión; botón Actualizar y auto-refresh cada 30 s mientras está visible.
- `pages.actividad.ActividadPage`: muestra `log.tail()`, botón "Sincronizar con auditoría".
- `ui/pages/__init__.py` expone `ALL_PAGES: list[type[BasePage]]` en orden: Tablero, Pronósticos, Newsvendor, Reabastecimiento, Transferencias, Descuentos, Mermas y desperdicio, Órdenes de compra, Importar ventas, Estado de servicios, Actividad. Tasks 5–7 agregan sus clases; esta task crea stubs importables para las que aún no existen (página que dice "En construcción").
- Estilo: `theme.apply(app)` — Fusion, paleta sobria (verde FreshTrack `#2E7D32` como acento), respeta modo oscuro del sistema; fuente del sistema; tablas con filas alternas.
- [ ] Tests con pytest-qt y `fake_http`: login exitoso como planner abre MainWindow con páginas permitidas (no "Órdenes de compra" si es buyer-only); login como warehouse muestra error y no abre; EstadoPage con un servicio caído muestra "CAÍDO"; inspector recibe un Exchange tras una llamada; `on_unauthorized` regresa al login.
- [ ] `QT_QPA_PLATFORM=offscreen pytest desktop/tests -q` pasa. Commit.

### Task 5: Páginas de análisis — Tablero, Pronósticos, Newsvendor
**Files:** Create `ui/pages/tablero.py`, `ui/pages/pronosticos.py`, `ui/pages/newsvendor.py`; Tests `desktop/tests/test_pages_analisis.py`.
**Interfaces:** Consumes `BasePage`, `AppContext.run`, `DataTable`, `KpiCard`, `ApiClient.call`. Leer los endpoints en `app/services/planning_service/app.py`, `alerts_service/app.py` para nombres exactos de campos.
- Tablero (`roles=()`): KPIs de `GET planning /api/v1/planning/forecast/analytics/kpis`, `GET alerts /api/v1/alerts/analytics/kpis`, `GET alerts /api/v1/alerts/waste-measurement`; tabla de alertas activas (`GET /api/v1/alerts/active`). Cada bloque falla de forma independiente (un servicio caído no vacía el resto).
- Pronósticos (`roles=("planner","buyer")`): formulario (tienda de `GET catalog /api/v1/catalog/locations`, SKU de `GET /api/v1/catalog/products`, método AUTO/MEDIA_MOVIL/MEDIA_MOVIL_PONDERADA/SUAVIZACION_EXPONENCIAL, horizonte, ventana, alpha, días de historia) → `POST /planning/forecast/run` con cuerpo raíz `forecast_request` validado con `forecast_request.xsd`; muestra resultado (tabla + gráfica QtCharts de la serie). Pestaña "Comparar modelos": `GET /planning/forecast/backtest` (MAE, WAPE, sesgo por modelo vs ingenuo) en tabla + gráfica de barras; pestaña "Drift": `GET /planning/forecast/drift`.
- Newsvendor (`roles=("planner","buyer")`): parámetros (SKU, tienda, costo faltante/excedente o precio/costo/valor de recuperación, nivel de servicio, según lo que acepte `POST /planning/newsvendor/evaluate`) → muestra cantidad óptima, ratio crítico, costo esperado y comparación contra políticas simples si el endpoint la devuelve.
- Exportar CSV e imprimir en las tablas de resultados.
- [ ] Tests con `fake_http`: cada página hace `refresh()` sin excepción con respuestas de ejemplo; el POST de pronóstico envía XML con raíz `forecast_request` y `Accept: application/xml`; Tablero con alerts caído sigue mostrando KPIs de planning.
- [ ] Pasa `pytest desktop/tests -q`. Commit.

### Task 6: Páginas de decisión — Reabastecimiento, Transferencias, Descuentos
**Files:** Create `ui/pages/reabastecimiento.py`, `ui/pages/transferencias.py`, `ui/pages/descuentos.py`; Tests `desktop/tests/test_pages_decisiones.py`.
- Reabastecimiento (`roles=("planner","buyer")`): filtros estado/tienda; `GET /planning/replenishment/orders`; botones Generar (`POST /replenishment/generate`), Aprobar/Rechazar seleccionadas (`POST .../orders/{id}/approve|reject`, con motivo vía `ask_text` al rechazar), detalle con `GET /planning/sku/{id}/full-context`. Aprobación en lote: itera seleccionadas y reporta éxitos/errores al final.
- Transferencias (`roles=("planner",)`): `GET /planning/transfers`, Detectar (`POST /transfers/detect`), Aprobar/Rechazar/Ejecutar.
- Descuentos (`roles=("planner",)`): `GET /planning/discounts`, Generar, Aprobar/Rechazar; muestra precio, margen, vigencia.
- Todas: exportar CSV, imprimir, registro en ActivityLog de cada decisión (`APROBAR_ORDEN`, etc.).
- [ ] Tests: aprobar llama a la ruta correcta con POST y registra actividad; un 403 en aprobar muestra error sin romper; refresh con lista vacía muestra 0 filas.
- [ ] Pasa `pytest desktop/tests -q`. Commit.

### Task 7: Páginas operativas — Mermas y desperdicio, Órdenes de compra, Importar ventas
**Files:** Create `ui/pages/mermas.py`, `ui/pages/ordenes_compra.py`, `ui/pages/importar_ventas.py`; Tests `desktop/tests/test_pages_operativas.py`.
- Mermas y desperdicio (`roles=()`): `GET /alerts/waste-measurement` (distinguir producto en riesgo, desperdicio proyectado, recuperado, evitado estimado, reducción observada, CO₂e), `GET /alerts/esg/carbon-avoided`, `GET /planning/triage`; gráfica de barras; exportar/imprimir reporte.
- Órdenes de compra (`roles=("buyer",)`): `GET /planning/purchase-orders`, detalle `GET /planning/purchase-orders/{id}`, Nueva OC (proveedor de `GET /planning/procurement/suppliers`, catálogo `GET .../suppliers/{id}/catalog`, cantidades → `POST /planning/purchase-orders`), Descargar PDF (`get_bytes .../pdf` → QFileDialog), Imprimir PDF (QPdfDocument si disponible, si no abre con `QDesktopServices`), Exportar CSV de las órdenes seleccionadas con sus líneas, Enviar por correo (`POST .../send-email`, confirmación previa).
- Importar ventas (`roles=("buyer","planner")`): elegir CSV (columnas `folio_externo,id_locacion,id_sku,cantidad[,canal]`, agrupa por folio), vista previa con validación por fila (errores en rojo, no se envían), envío en bloques de 500 tickets a `POST commercial /api/v1/commercial/sales/import` con raíz `sales_import_request` validada por `sales_import_request.xsd` (de Task 2); tabla de resultados IMPORTADO/DUPLICADO/ERROR; plantilla CSV descargable.
- [ ] Tests: parseo de CSV con filas inválidas reporta errores por fila y no las incluye; el XML generado valida contra el XSD; resultado DUPLICADO se muestra; PDF se guarda en ruta temporal (monkeypatch del diálogo).
- [ ] Pasa `pytest desktop/tests -q`. Commit.

### Task 8: Empaquetado, documentación y verificación
**Files:** Create `desktop/freshtrack_desktop.spec` (PyInstaller, onedir, incluye `contracts/xsd` como datos en `contracts/xsd`, nombre `FreshTrackDesktop`), `desktop/README.md` (instalación, ejecución, configuración de servidores, cuentas demo, cómo cumple cada requisito de Blackboard, demo de fallas), `desktop/scripts/capturas.py` (abre cada página offscreen con `fake_http` y guarda PNG en `desktop/docs/capturas/`); Modify `Makefile` (targets `desktop`, `desktop-test`, `desktop-build`), `README.md` (sección App de escritorio).
- [ ] `pyinstaller desktop/freshtrack_desktop.spec` genera `dist/FreshTrackDesktop/FreshTrackDesktop`; arrancarlo con `QT_QPA_PLATFORM=offscreen` y `--smoke` (flag que abre la ventana de login y sale con código 0) funciona.
- [ ] Commit.
