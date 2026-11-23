# App de escritorio FreshTrack — diseño

Aprobado por el equipo el 2026-11-22. Entrega final IAC, Proyecto 12 (Equipo 05), fecha límite 2026-11-24.

## Intención
La entrega final exige una **app de escritorio instalable** para **compradores y planeadores** que
consuma **exclusivamente XML** de los microservicios (validado con XSD), desacoplada de la web, y que
se pueda demostrar en vivo (incluyendo token revocado, permisos insuficientes y servicio caído).
Cada integrante debe poder defenderla, así que se usa el mismo lenguaje del backend.

## Objetivos
- Funciones de Blackboard: autenticación, importar ventas, ejecutar pronósticos, revisar
  recomendaciones, ajustar parámetros, aprobar órdenes, planear transferencias, comparar modelos,
  analizar mermas, generar reportes, exportar órdenes de compra.
- Requisitos generales: JWT, sesión validada en Redis (lo hace el microservicio), control de permisos,
  conversión y validación XML, manejo de errores, reportes, exportación, impresión, registro de
  actividades, operación desacoplada de la web.

## No-objetivos / anti-objetivos
- No accede a PostgreSQL/Mongo/Redis ni importa nada de `app/`. Si lo hiciera, falla el requisito.
- No consume JSON. Toda llamada lleva `Accept: application/xml`.
- No replica lógica de negocio del backend (pronóstico, newsvendor, FEFO se calculan en servicios).

## Enfoques considerados
| Enfoque | Trade-off | Decisión |
|---|---|---|
| **Python + PySide6 (Qt) + PyInstaller** | Mismo lenguaje que el equipo; Qt da tablas, impresión (QPrinter) y PDF nativos | **Elegido** |
| Electron | UI web fácil, pero segundo lenguaje/runtime y no aporta impresión mejor | Descartado |
| C#/.NET o JavaFX | Bueno para escritorio, pero el equipo tendría que defender otro stack | Descartado |

## Diseño
- Código en `desktop/` (paquete `freshtrack_desktop`), con su propio `requirements.txt`, pruebas en
  `desktop/tests/` y spec de PyInstaller. Rama `feat/app-escritorio`.
- **Núcleo**
  - `config`: URLs de los 8 servicios (por defecto `http://localhost:5001..5008`, configurable por
    archivo/env y desde la pantalla de login).
  - `api_client`: `requests` con `Accept: application/xml`, `Authorization: Bearer`, `X-Correlation-Id`
    por petición, timeout; cuerpos XML (`Content-Type: application/xml`).
  - `xml_codec`: XML → dict/list (listas `<item>`), dict → XML; validación con `lxml` contra
    `contracts/xsd/*.xsd` (empaquetados con la app). Si el XML no es válido o no está bien formado
    se registra y se muestra error.
  - Errores: `<error_response>` → excepción con `error, mensaje, status, correlation_id`.
    401 → intenta refresh una vez; si falla, cierra sesión y vuelve al login. 403 → aviso de permisos.
    Conexión/timeout → "servicio no disponible" sin crash.
  - `session`: token en memoria, datos de usuario; permisos por rol (buyer, planner, admin) que
    habilitan/deshabilitan pantallas y botones.
  - `activity_log`: archivo local rotativo + `POST /api/v1/audit/log` (best effort).
  - Panel "XML crudo" con la última respuesta recibida (evidencia para la demo).
- **Pantallas** (barra lateral): Tablero (KPIs), Pronósticos (ejecutar + comparar modelos/backtest +
  drift), Newsvendor, Reabastecimiento (generar/aprobar/rechazar), Transferencias
  (detectar/aprobar/rechazar/ejecutar), Descuentos (generar/aprobar/rechazar), Mermas y desperdicio,
  Órdenes de compra (listar/detalle/crear/PDF/exportar CSV/imprimir), Importar ventas (CSV → XML),
  Estado de servicios (/health de los 8).
- **Backend mínimo**
  - `POST /api/v1/auth/refresh` en svc-auth: emite nuevo JWT y revoca el anterior.
  - `POST /api/v1/commercial/sales/import` en svc-commercial (roles buyer, planner, admin) con XSD
    `sales_import_request.xsd`; inserta ventas de forma idempotente y auditada.
  - XSD de respuestas usadas por la app (`error_response` ya existe).

## Lo que queda al constructor
Estilo visual (sobrio, denso, legible, modo claro/oscuro del sistema), gráficas (QtCharts),
formato exacto de reportes impresos.
