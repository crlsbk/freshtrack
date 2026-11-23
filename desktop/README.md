# FreshTrack Desktop

App de escritorio (PySide6 / Qt) para **compradores y planeadores**. Es un cliente de los 8 microservicios
de FreshTrack que habla **solo XML** (`Accept: application/xml`, cuerpos `application/xml`), valida cada
mensaje contra los XSD de `contracts/xsd/` y está desacoplada de la web: no importa `app/` ni toca
PostgreSQL, MongoDB ni Redis. Diseño: [`docs/superpowers/specs/2026-11-22-app-escritorio-design.md`](../docs/superpowers/specs/2026-11-22-app-escritorio-design.md).

## 1. Instalación y ejecución

Requiere Python 3.11+ (probado con 3.14) y los microservicios arriba (`docker compose up -d --build --wait`).

### Linux / macOS
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r desktop/requirements.txt
python desktop/run_desktop.py        # o: make desktop
```

### Windows (PowerShell)
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r desktop\requirements.txt
python desktop\run_desktop.py
```

### Pruebas y ejecutable
```bash
make desktop-test                    # QT_QPA_PLATFORM=offscreen pytest desktop/tests
make desktop-build                   # PyInstaller onedir -> desktop/dist/FreshTrackDesktop/FreshTrackDesktop
QT_QPA_PLATFORM=offscreen desktop/dist/FreshTrackDesktop/FreshTrackDesktop --smoke   # código 0 = arranca y encuentra los XSD
```
El spec (`desktop/freshtrack_desktop.spec`) empaqueta `contracts/xsd` en `contracts/xsd` dentro del bundle.
En Windows se genera `FreshTrackDesktop.exe` ejecutando el mismo comando de PyInstaller desde Windows
(no se puede compilar cruzado). Para entregar, comprime la carpeta `desktop/dist/FreshTrackDesktop/`.

## 2. Servidores

En el login, el botón **«Servidores…»** abre el diálogo de conexión; se guarda en
`~/.freshtrack_desktop/config.ini`.

| Escenario | Qué poner |
|---|---|
| Local (docker compose) | Host `http://localhost` (por defecto): usa los puertos 5001..5008 (auth, catalog, inventory, commercial, asn, planning, alerts, audit) |
| Gateway | Campo «Gateway»: una sola URL (p. ej. `http://gateway:8080`) para los 8 servicios |
| GCP | Host = IP o dominio de la VM (p. ej. `http://34.x.x.x`) o, si hay Caddy delante, la URL del gateway |

También por variables de entorno (tienen prioridad): `FRESHTRACK_HOST`, `FRESHTRACK_GATEWAY_URL`,
`FRESHTRACK_XSD_DIR` (carpeta de XSD alterna). El pie de la ventana muestra el último servicio llamado.

## 3. Cuentas demo

| Rol | Correo | Contraseña | Pantallas |
|---|---|---|---|
| Planeador | `planner@freshtrack.mx` | `Plan2026!` | Pronósticos, Newsvendor, Reabastecimiento, Transferencias, Descuentos, Mermas, Importar ventas |
| Comprador | `buyer@freshtrack.mx` | `Compras2026!` | Pronósticos, Newsvendor, Reabastecimiento, Mermas, **Órdenes de compra**, Importar ventas |
| Administrador | `admin@freshtrack.mx` | `Admin2026!` | Todas |

Tablero, Mermas y desperdicio, Estado de servicios y Actividad están disponibles para todos los roles.
Capturas reales de ambos roles en [`docs/capturas/`](docs/capturas/) (se regeneran con `desktop/scripts/capturas.py`).

## 4. Requisito de Blackboard → dónde está en la app

### Funciones del Proyecto 12 (escritorio)
| Requisito | Dónde |
|---|---|
| Autenticación | Diálogo de login (`POST /auth/login`, XML); «Cerrar sesión» en Archivo |
| Importar ventas | Página **Importar ventas**: CSV → vista previa con validación por fila → XML → `POST /commercial/sales/import` en bloques de 500 (idempotente) |
| Ejecutar pronósticos | **Pronósticos** → pestaña Pronóstico (método, horizonte, ventana, alpha) → «Generar pronóstico» |
| Revisar recomendaciones | **Reabastecimiento** (órdenes sugeridas) y **Newsvendor** (cantidad óptima vs. política simple) |
| Ajustar parámetros | Parámetros de Pronósticos (horizonte, ventana, alpha, historia) y de Newsvendor (costos de faltante y excedente) |
| Aprobar órdenes | **Reabastecimiento**: aprobar / rechazar con motivo (planner y buyer) |
| Planear transferencias | **Transferencias**: detectar, aprobar, rechazar, ejecutar (planner) |
| Comparar modelos | **Pronósticos** → «Comparar modelos» (backtest contra el ingenuo) y «Drift» |
| Analizar mermas | **Mermas y desperdicio**: producto en riesgo, desperdicio proyectado/recuperado/evitado, CO₂e; **Descuentos** para lotes por caducar |
| Generar reportes | Reporte PDF de cada orden de compra (servicio) y tablas/gráficas exportables en Tablero y Mermas |
| Exportar órdenes de compra | **Órdenes de compra** → «Exportar CSV» y «Descargar PDF» |

### Requisitos generales
| Requisito | Dónde |
|---|---|
| JWT | `core/api_client.py`: `Authorization: Bearer`, token solo en memoria (`core/session.py`) |
| Sesión validada con Redis | La valida cada microservicio en cada llamada; la app lo evidencia: un token revocado devuelve 401 y la app vuelve al login (refresh una vez antes) |
| Permisos | `BasePage.roles` + `session`: la barra lateral solo muestra lo que el rol permite; un 403 del servicio se muestra como aviso de permisos |
| Conversión y validación XML | `core/xml_codec.py`: XML ↔ dict/list, validación `lxml` contra `contracts/xsd/*.xsd` en peticiones y respuestas |
| Manejo de errores | `core/errors.py`: `<error_response>` → excepción con error, mensaje, status y correlation id; sin conexión/timeout → «servicio no disponible», sin crash |
| Reportes | PDF de órdenes de compra; vistas de Tablero, Pronósticos y Mermas |
| Exportación | CSV de órdenes de compra; PDF descargable |
| Impresión | **Órdenes de compra** → «Imprimir PDF» (diálogo de impresión de Qt) |
| Registro de actividades | `core/activity_log.py`: archivo rotativo local + `POST /audit/log` (mejor esfuerzo); página **Actividad** |
| Operación desacoplada | Solo HTTP+XML contra los servicios; sin imports de `app/` ni acceso a bases de datos (el spec excluye `app` del bundle) |

## 5. Guion de la demo de fallas

1. **Token revocado.** Inicia sesión como planner y entra a Pronósticos. Revoca la sesión desde otra
   terminal (`POST /api/v1/auth/logout` con ese token, o inicia sesión en la web con la misma cuenta
   si cierra sesiones previas) y pulsa «Actualizar» (Ctrl+R). Resultado: 401, la app intenta refrescar
   una vez, falla y regresa al login con el mensaje «sesión expirada». Se aprecia en **Actividad**.
2. **Rol sin permisos.** Entra como buyer: no aparecen Transferencias ni Descuentos en la barra
   lateral; las acciones no permitidas devuelven 403 y la app muestra un aviso de permisos, no un error.
3. **Servicio caído.** `docker stop freshtrack_svc_planning`; abre Pronósticos o Tablero. Muestra
   «servicio no disponible» sin cerrar la app; **Estado de servicios** marca planning en rojo. Recupera con
   `docker start freshtrack_svc_planning`.
4. **XML inválido.** En **Importar ventas** carga un CSV con filas malas (cantidad negativa o texto, falta
   `id_sku`): la vista previa las marca y no se envían. Con `FRESHTRACK_XSD_DIR` apuntando a una carpeta
   sin XSD, el cliente reporta «No existe el contrato XSD …» en vez de enviar. Una respuesta que no cumple
   su XSD se rechaza con la lista de motivos (hasta 10).
5. **Inspector XML (F12).** En cualquier momento, F12 (Ver → Inspector XML) abre el panel con la última
   petición y respuesta en XML crudo, estado, servicio, duración y `X-Correlation-Id`. Útil para
   enseñar que no hay JSON y cruzar el id con los logs del servicio.

## 6. Arquitectura

```
desktop/
├── run_desktop.py            entrada (también la del ejecutable)
├── freshtrack_desktop.spec   PyInstaller onedir (+ contracts/xsd)
├── scripts/capturas.py       PNG de cada página contra el stack real
├── tests/                    pytest-qt (offscreen) con servidor HTTP falso
└── freshtrack_desktop/
    ├── app.py                QApplication, tema, flujo login -> ventana, --smoke
    ├── core/   (sin Qt-UI)   config · api_client · xml_codec · errors · session · activity_log
    └── ui/     (Qt)          context · login_dialog · main_window · xml_inspector · widgets · worker · theme · pages/*
```

```
 Página (ui/pages)          ctx.run(...) -> QThreadPool (ui/worker)
       |                              |
       v                              v
   AppContext  ------------>  core.api_client  --HTTP+XML-->  svc-auth/catalog/.../audit (5001..5008)
       |                         |      |
       |                         |      +-- core.xml_codec (dict <-> XML, validación XSD con lxml)
       |                         +-- core.session (JWT en memoria, rol)   core.errors (error_response)
       +-- core.activity_log (archivo + /audit/log)        MainWindow <- listeners (Inspector XML F12)
```
`core/` no importa Qt de interfaz; `ui/` nunca hace HTTP directo: siempre pasa por `ApiClient`.
