# FreshTrack Mobile — App Android para personal de tienda

App nativa (Kotlin) para **gerentes de tienda** y **operadores de almacén**. Consume los
8 microservicios de FreshTrack a través del API Gateway (Caddy + HTTPS) desplegado en
Google Compute Engine: `https://34.51.41.80.nip.io`.

| | |
|---|---|
| Lenguaje / UI | Kotlin 2.2 · Views + ViewBinding · Material 3 (claro/oscuro) |
| Arquitectura | MVVM (ViewModel + StateFlow) + Repository + Service Locator (`FreshTrackApp`) |
| Red | Retrofit 2.11 + OkHttp 4.12 (interceptores JWT, correlation id, 401 global) |
| Cámara / escaneo | CameraX 1.4 + ML Kit Barcode (QR FT1, GS1-128/DataMatrix, EAN-13/8, UPC) |
| Segundo plano | WorkManager (sondeo de alertas cada 15 min → notificaciones) |
| Seguridad local | JWT cifrado AES-256-GCM con llave del **Android Keystore**; sin backup en la nube |
| SDK | minSdk 26 · target/compile 36 · AGP 9.2.1 · Gradle 9.4.1 · JDK 17+ |

## Cómo compilar e instalar

```bash
cd android-app
./gradlew assembleDebug            # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease          # APK minificado (R8) firmado con la llave debug para la demo
./gradlew testDebugUnitTest        # pruebas unitarias JVM
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

En Android Studio: **File → Open → `freshtrack/android-app`** y ▶ Run.
La URL del servidor se cambia en la app: *Login → (icono de ajustes) → Servidor*.

Cuentas de prueba (botones en el login): `gerente@freshtrack.mx`, `almacen@freshtrack.mx`, `admin@freshtrack.mx`.
El botón **Comprador** existe a propósito: demuestra que un perfil que no es de tienda es rechazado.

## Requisitos del proyecto → dónde están

| Función pedida (app móvil) | Pantalla | Microservicio / endpoint |
|---|---|---|
| Autenticación de usuarios | `LoginActivity` | svc-auth `POST /auth/login`, `POST /auth/logout` (revoca jti en Redis) |
| Escanear productos | `ScannerActivity` (botón naranja *Escanear*) | — (ML Kit en el dispositivo) → enruta a Recepción o FEFO |
| Registrar recepción | `ReceiveActivity` | svc-asn `GET /asn/labels?codigo=` → svc-inventory `POST /inventory/receive-scan` (Idempotency-Key) |
| Capturar caducidad | `ReceiveActivity` (fecha verificada) | `fecha_caducidad_verificada` en receive-scan |
| Ejecutar conteo | `CountActivity` | svc-inventory `POST /inventory/counts` **(nuevo)** |
| Consultar FEFO | `FefoActivity`, pestaña *Inventario* | svc-inventory `GET /inventory/fefo-queue/{sku}/{loc}`, `GET /inventory/stock` |
| Registrar merma | `ShrinkageActivity` | svc-commercial `POST /commercial/shrinkage` |
| Solicitar transferencia | `FefoActivity → lote → Solicitar`, `TransfersActivity` | svc-planning `POST /planning/transfers` **(nuevo)**, approve/reject/execute |
| Aplicar descuento autorizado | `DiscountsActivity` | svc-planning `GET /planning/discounts`, `POST …/{id}/approve` |
| Tomar evidencia | `EvidenceActivity`, adjunto en Recepción y Merma | svc-commercial `POST /commercial/evidence` **(nuevo)** → Cloud Storage; `GET …/{id}/url` (URL firmada) |
| Recibir alertas | pestaña *Alertas* + notificaciones (`AlertWorker`) | svc-alerts `GET /alerts/active`, `POST /alerts/scan`, `PATCH /alerts/{id}/resolve` |
| Monitoreo (extra) | `ServiceStatusActivity` | `/health` + sondeo de los 8 servicios vía gateway |

## Procesos integrales que pasan por la app

1. **Recepción de mercancía:** gerente escanea el QR firmado (HMAC) de la etiqueta del ASN → svc-asn valida firma y destino → captura cantidad real, caducidad, temperatura e inspección → svc-inventory crea lote/existencia (PostgreSQL), actualiza la OC, publica evento (Redis Streams) y audita → foto de evidencia al bucket → aparece en FEFO.
2. **Merma con evidencia:** foto (bucket privado + SHA-256 + metadatos en PostgreSQL) → merma (descuenta existencia, kardex, bitácora) → la evidencia queda ligada a la merma → visible con URL firmada.
3. **Rescate de lote por vencer:** alerta (MongoDB) notificada al teléfono → FEFO del producto → *Solicitar transferencia* (valida stock y que llegue antes de vencer) o el gerente autoriza un descuento sugerido → al ejecutar se registra desperdicio evitado (ESG en el Inicio).

## Seguridad

- **JWT** solo en memoria y en `SharedPreferences` **cifrado** (AES-GCM, llave no exportable en Android Keystore). `allowBackup=false` + reglas de extracción excluyen la sesión.
- **401 global:** si cualquier servicio responde `token_revocado`/`sesion_inexistente`, el `UnauthorizedInterceptor` borra la sesión y todas las pantallas regresan al login con el motivo. *(Demo: revocar el token desde la web → la app se cierra sola.)*
- **Roles:** la app solo admite `store_manager`, `warehouse` y `admin`, y oculta acciones no permitidas; la autorización real la hace el backend (403). Gerente/almacén están **acotados a su sucursal** (`sucursal_no_autorizada`).
- **HTTPS obligatorio** (`network_security_config`: sin tráfico en claro salvo `10.0.2.2` para desarrollo).
- **Idempotency-Key** en recepción y conteo: reintentar por mala señal no duplica inventario.
- **Errores seguros:** en 5xx no se muestra el mensaje interno; sí el `correlation_id` para buscarlo en los logs.
- **URLs firmadas:** la imagen se descarga con un cliente HTTP **sin** el JWT; la firma V4 (15 min) es la única autorización.
- Fotos comprimidas en el dispositivo (≤1600 px, JPEG 82 %); el backend valida el tipo real por *magic bytes* y el tamaño (≤ 8 MB).

## Tolerancia a fallos (para la demostración)

| Se provoca… | La app… |
|---|---|
| `docker stop freshtrack_svc_planning` | Inicio muestra *"Servicio degradado: Planeación"* y el resto sigue funcionando; *Estado de servicios* lo marca **Caído (502)** |
| Redis detenido | El backend verifica la sesión contra PostgreSQL (respaldo) y la app sigue operando sin caché; si tampoco puede verificarla aplica *fail-closed* (`sesion_no_verificable`) y la app regresa al login con ese motivo |
| MongoDB detenido | Pestaña Alertas muestra *"MongoDB no está disponible"* (503); Inventario/FEFO siguen funcionando |
| Bucket no disponible | Subir evidencia → 503 *almacenamiento_no_disponible*; la merma puede registrarse sin foto |
| Petición > tiempo máximo | OkHttp corta a los 20 s (5 s en el monitor) → *"La petición excedió el tiempo máximo"* |
| Token revocado | Diálogo *"Tu sesión fue revocada por un administrador"* |
| Rol sin permiso | Comprador no entra; un almacenista no ve *Autorizar descuento*; si se fuerza, 403 con detalle |
| Sin red | *"Sin conexión con el servidor"* + botón *Reintentar* |

## Pruebas

- `./gradlew testDebugUnitTest` — 20 pruebas JVM: parser de etiquetas (FT1/GS1/GTIN), semáforo de caducidad
  (igual a `fn_clasificar_riesgo`), permisos por rol y manejo de errores HTTP con **MockWebServer**
  (403/409/429/500/502/timeout/respuesta no JSON).
- Backend: `tests/unit/test_app_movil.py` — 21 pruebas de los endpoints nuevos (validación por magic bytes,
  URL firmada, 401/403/sucursal, XSD, bucket caído → 503, health extendido).

## Estructura

```
app/src/main/java/mx/freshtrack/mobile/
├── FreshTrackApp.kt            contenedor de dependencias, canales de notificación
├── data/api/                   Retrofit (FreshTrackApi) + OkHttp e interceptores
├── data/model/Models.kt        contratos JSON (mismos nombres que el backend)
├── data/repo/                  Repository + ApiResult/AppError (mapeo de errores)
├── session/                    SessionManager, TokenCipher (Keystore), Role
├── ui/login · main · home · inventory · scan · receive · shrink · count
├── ui/transfer · discount · alerts · evidence · settings · common
├── util/                       LabelParser (QR FT1/GS1/GTIN), Expiry (riesgo), formato
└── work/AlertWorker.kt         WorkManager + notificaciones
```
