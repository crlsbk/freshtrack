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

En modo gateway, **Estado de servicios** mide el `/health` del gateway (una sola URL para los 8), no el de
cada contenedor; si el proxy manda `/health` a la web, los 8 salen «fuera de contrato». Para la demo de
servicio caído usa el modo local (puertos 5001..5008).

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
| Ajustar parámetros | Parámetros de Pronósticos (método, horizonte, ventana, alpha, historia) y de Newsvendor (SKU, tienda y horizonte; los costos de faltante y excedente no se capturan: el servidor los deriva del catálogo y la app los muestra) |
| Aprobar órdenes | **Reabastecimiento**: aprobar / rechazar con motivo (planner y buyer). El motivo queda en la bitácora local y en svc-audit; el backend de planning no lo guarda (el diálogo lo avisa) |
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
| Permisos | `BasePage.roles` + `session`: la barra lateral solo muestra lo que el rol permite; el servidor tiene la última palabra (p. ej. buyer → «Ejecutar ciclo de planeación» → 403 «No tienes permiso para esta acción») |
| Conversión y validación XML | `core/xml_codec.py`: XML ↔ dict/list, validación `lxml` contra `contracts/xsd/*.xsd`: toda petición contra `<raíz>.xsd` antes de enviarla y toda respuesta cuya raíz tenga contrato |
| Manejo de errores | `core/errors.py`: `<error_response>` → excepción con error, mensaje, status y correlation id; sin conexión/timeout → «servicio no disponible», sin crash |
| Reportes | PDF de órdenes de compra; vistas de Tablero, Pronósticos y Mermas |
| Exportación | CSV de órdenes de compra; PDF descargable |
| Impresión | **Órdenes de compra** → «Imprimir PDF» (diálogo de impresión de Qt) |
| Registro de actividades | `core/activity_log.py`: archivo rotativo local + `POST /audit/log` (mejor esfuerzo, solo las acciones del usuario de la sesión vigente, porque svc-audit toma el usuario del JWT); página **Actividad** |
| Operación desacoplada | Solo HTTP+XML contra los servicios; sin imports de `app/` ni acceso a bases de datos (el spec excluye `app` del bundle) |

## 5. Guion de la demo de fallas

Probado el 2026-11-23 contra el stack local (puertos 5001..5008). Usa dos terminales: una con la app y otra
para provocar la falla. El Inspector XML (F12) puede quedar abierto todo el tiempo.

1. **Token revocado (sesión validada en Redis).**
   1. Inicia sesión como planner (`planner@freshtrack.mx` / `Plan2026!`) y abre **Reabastecimiento**
      (o quédate en **Tablero**: ambas páginas llaman endpoints autenticados de planning y alerts).
   2. En otra terminal, revoca todas las sesiones del planner con la revocación administrativa
      (`DELETE /api/v1/auth/sessions/<id_usuario>`, solo admin). El token no se puede copiar del inspector
      porque sale enmascarado, por eso se usa la cuenta admin:
      ```bash
      ADMIN=$(curl -s -X POST http://localhost:5001/api/v1/auth/login -H 'Content-Type: application/xml' \
        -H 'Accept: application/xml' \
        -d '<login_request><email>admin@freshtrack.mx</email><password>Admin2026!</password></login_request>' \
        | sed -n 's:.*<token>\([^<]*\)</token>.*:\1:p')
      ID=$(curl -s "http://localhost:5001/api/v1/auth/users?q=planner@freshtrack.mx" -H "Authorization: Bearer $ADMIN" \
        -H 'Accept: application/xml' | sed -n 's:.*<id_usuario>\([^<]*\)</id_usuario>.*:\1:p')
      curl -s -X DELETE "http://localhost:5001/api/v1/auth/sessions/$ID" -H "Authorization: Bearer $ADMIN" \
        -H 'Accept: application/xml'      # → <sessions_revoked>…<sesiones_cerradas>N</sesiones_cerradas>
      ```
   3. En la app pulsa «Actualizar» (o Ver → Actualizar página, **Ctrl+R**).
   Resultado: el servicio responde 401, la app intenta un refresh (también 401) y vuelve al login con
   «**Tu sesión terminó o fue revocada**». En el inspector se ven los 401 de planning y de `/auth/refresh`.
2. **Sin permisos (403 decidido por el servidor).** Entra como buyer (`buyer@freshtrack.mx` / `Compras2026!`):
   no aparecen Transferencias ni Descuentos. Abre **Reabastecimiento** y pulsa «**Ejecutar ciclo de
   planeación**» (el botón está habilitado a propósito; su tooltip dice «Requiere rol planificador») y
   confirma. svc-planning responde 403 y la app muestra «**No tienes permiso para esta acción**» con
   `HTTP 403 · correlation_id: …` (seleccionable; cruzarlo con `docker logs freshtrack_svc_planning`).
   No se crea nada.
3. **Servicio caído.** `docker stop freshtrack_svc_planning`. En **Reabastecimiento** pulsa «Actualizar»:
   diálogo «**El servicio planning no está disponible**» (sin respuesta HTTP), la app sigue viva. **Estado de
   servicios** marca planning como **CAÍDO** y el resto OK (en Tablero aparece «Bloques sin datos:
   Pronósticos (…)»). Recupera con `docker start freshtrack_svc_planning`, espera a que esté *healthy*
   (`docker ps`) y pulsa «Actualizar»: vuelven las órdenes y planning sale OK.
4. **XML inválido.**
   - *Cliente (petición)*: toda petición se valida antes de enviarse contra `contracts/xsd/<raíz>.xsd`.
     Copia los contratos y endurece uno, por ejemplo el horizonte de `replenishment_request.xsd`:
     ```bash
     cp -r contracts/xsd /tmp/xsd_demo
     sed -i 's/<xs:maxInclusive value="90"\/>/<xs:maxInclusive value="3"\/>/' /tmp/xsd_demo/replenishment_request.xsd
     FRESHTRACK_XSD_DIR=/tmp/xsd_demo python desktop/run_desktop.py
     ```
     Como planner, en **Reabastecimiento** deja el horizonte en 7 y pulsa «Generar órdenes»: «**El XML enviado
     no cumple su contrato: El XML no cumple el contrato replenishment_request.xsd.**» y en «Detalles» el
     motivo (`maxInclusive … '7' … ('3')`). La petición no sale a la red (no aparece en el inspector).
   - *Cliente (CSV)*: en **Importar ventas** un CSV con filas malas (cantidad negativa o texto, sin `id_sku`)
     marca esas filas en la vista previa y no las envía.
   - *Servidor*: svc-commercial valida contra `sales_import_request.xsd` y responde 400
     `xml_no_cumple_contrato` con los motivos:
     ```bash
     curl -s -X POST http://localhost:5004/api/v1/commercial/sales/import -H "Authorization: Bearer <token buyer>" \
       -H 'Content-Type: application/xml' -H 'Accept: application/xml' \
       -d '<sales_import_request><id_locacion>tres</id_locacion><tickets/></sales_import_request>'
     ```
     (el token del buyer se obtiene con el mismo `curl … /auth/login` del paso 1 usando su cuenta).
   - Una *respuesta* que no cumple su XSD se rechaza con «La respuesta no cumple el contrato XML» y hasta
     10 motivos en «Detalles».
5. **Inspector XML (F12).** Ver → Inspector XML abre el panel con cada petición y respuesta en XML crudo,
   estado, servicio, duración y `X-Correlation-Id`. La contraseña del login y el `<token>` de las respuestas
   de login/refresh se muestran como `***`. Sirve para enseñar que no hay JSON y cruzar el id con los logs.

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
