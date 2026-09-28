# FreshTrack — Gestión de inventario perecedero con FEFO, pronóstico y control de merma

Sistema web para tiendas y CEDIS que trabaja **exclusivamente contra PostgreSQL**.
No hay datos simulados en el flujo principal: todo lo que la interfaz muestra —catálogos,
lotes, existencias, ventas, mermas, pronósticos, alertas y bitácora— se lee y se escribe
en la base de datos.

> **Avance 2 · Equipo 05 · Proyecto IAC**
> Entrega: todo lo presentado como funcional opera con datos reales almacenados en
> PostgreSQL. El módulo `mock_data.py` fue eliminado del repositorio.

---

## 1. Puesta en marcha

### 1.1 Sin Docker (recomendado para desarrollo)

```bash
# 1. Variables de entorno
cp env.example .env          # y ajusta las claves

# 2. Entorno virtual
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip

# 3. Base de datos: base + roles + esquemas + datos base (idempotente)
python scripts/bootstrap_db.py

# 4. Historia operativa (180 días de ventas, lotes, mermas y kardex)
python scripts/ETL.py

# 5. Aplicación
python run.py                # http://127.0.0.1:5000
```

Con `make`:

```bash
make setup venv bootstrap etl app
```

### 1.2 Con Docker

```bash
cp env.example .env
make up          # levanta PostgreSQL, MongoDB, Redis y la aplicación
```

Al crear el volumen por primera vez, cada motor ejecuta sus scripts de inicialización
(`docker-entrypoint-initdb.d`): PostgreSQL los de `sql/`, MongoDB los de `mongo/`.

**Los tres motores están desplegados; solo uno es fuente de datos.** Vale la pena ser
explícito porque es fácil confundir "desplegado" con "funcional":

| Motor | Puerto | Papel hoy |
|---|---|---|
| PostgreSQL 17 | 5432 | **Única fuente de verdad.** Todo el flujo funcional vive aquí. |
| MongoDB 7 | 27017 | Desplegado con sus colecciones e índices creados. Aún sin flujo que lo consuma. |
| Redis 7 | 6379 | Desplegado. Aún sin flujo que lo consuma. |

MongoDB y Redis corresponden a la arquitectura políglota ya diseñada en
`docs/Documento_Analitico_FreshTrack.pdf` (pronósticos y alertas como documentos;
sesiones, denylist de JWT, caché de catálogos y bloqueos distribuidos en memoria) y se
activan en las siguientes parciales. La aplicación **no** depende de ellos para arrancar:
su único `depends_on` es PostgreSQL.

El ETL se corre aparte con `make etl`.

---

## 2. Cuentas de demostración

Todas las cuentas usan el patrón `usuario@freshtrack.mx`. La pantalla de acceso las
lista y permite rellenar el formulario con un clic.

| Rol | Correo | Contraseña | Qué ve |
|---|---|---|---|
| Administrador | `admin@freshtrack.mx` | `Admin2026!` | Todo |
| Comprador | `buyer@freshtrack.mx` | `Compras2026!` | Catálogos, lotes, reabastecimiento |
| Planeador | `planner@freshtrack.mx` | `Plan2026!` | Pronóstico, reabastecimiento, transferencias |
| Gerente de tienda | `gerente@freshtrack.mx` | `Tienda2026!` | Operación de tienda **y aprobaciones** |
| Almacén | `almacen@freshtrack.mx` | `Almacen2026!` | Lotes, inventario, FEFO, mermas |
| Proveedor | `proveedor@freshtrack.mx` | `Proveedor2026!` | Sus productos y lotes |
| Auditor | `auditor@freshtrack.mx` | `Auditor2026!` | Bitácora, mermas, desperdicio evitado |
| *(inactivo)* | `inactivo@freshtrack.mx` | `Inactivo2026!` | — el sistema debe rechazarlo |

> Las contraseñas de demostración viven en `sql/07_seed_base.sql` y **deben cambiarse**
> antes de cualquier despliegue real.

---

## 3. Arquitectura

### 3.1 Esquemas de PostgreSQL

| Esquema | Contenido |
|---|---|
| `operacion` | Catálogos (rol, usuario, locación, proveedor, producto, regla de riesgo) y el núcleo transaccional (lote, existencia, movimiento de inventario, venta, merma, sesión) |
| `analitica` | Pronóstico (`forecast_run`, `forecast_result`), reabastecimiento, transferencias, descuentos, alertas, desperdicio evitado y configuración |
| `auditoria` | `bitacora_eventos`, inmutable por disparador, más las vistas de consulta |

Vistas principales: `operacion.v_inventario_lote`, `operacion.v_lote_riesgo`,
`analitica.v_demanda_diaria`, `analitica.v_merma_agregada`, `analitica.v_alerta_abierta`,
`analitica.v_trazabilidad_lote`, `auditoria.v_bitacora`.

**Persistencia políglota.** La arquitectura completa contempla tres motores (ver §1.2 y
`docs/Documento_Analitico_FreshTrack.pdf`): PostgreSQL como fuente transaccional,
MongoDB para pronósticos y alertas como documentos, y Redis para sesiones, denylist de
JWT, caché y bloqueos distribuidos. En esta entrega **solo PostgreSQL está en uso**: es
el único motor que el sistema consulta y el único del que dependen los resultados que se
presentan como funcionales.

### 3.2 Capas de la aplicación

```
app/
├── config.py          Configuración: todo desde el entorno, sin credenciales en código
├── db.py              Acceso a PostgreSQL (lecturas, transacciones con usuario fijado)
├── security.py        Login, bcrypt en PostgreSQL, JWT, decoradores de permisos
├── navegacion.py      Menú y permisos por rol
├── auditoria.py       Eventos de aplicación → auditoria.fn_registrar_accion()
├── domain/            Reglas de negocio (FEFO, mermas, pronóstico, reabastecimiento…)
├── repos/             CRUD de catálogos
├── blueprints/        Rutas HTTP (publico, auth, catalogo, operacion, analitica, panel, api)
├── templates/         Jinja2
└── static/            Hojas de estilo
```

### 3.3 Flujo de autenticación

```
Login → PostgreSQL valida con crypt(password, password_hash)  (pgcrypto / bcrypt)
      → sesión web firmada + JWT HS256 persistido en operacion.sesion_usuario
      → resolución de rol → permisos → menú correspondiente
      → logout revoca el jti
```

Los decoradores `login_required`, `requiere_vista`, `requiere_rol`, `token_requerido`
y `rol_en_token` protegen las rutas. `SECRET_KEY` y `JWT_SECRET_KEY` se leen del entorno;
la aplicación **no arranca** si faltan.

---

## 4. Funcionalidad

### 4.1 Catálogos (CRUD real)

Productos, proveedores (con **lead time** y **MOQ**) y tiendas/CEDIS: alta, consulta,
edición y activar/desactivar. Cada operación escribe en PostgreSQL y queda auditada.

### 4.2 Lotes, vida útil y clasificación de riesgo

La **vida útil restante** la calcula el sistema (`operacion.fn_vida_util_pct`) a partir de
la fecha de caducidad, la de producción y la vida útil estándar del producto.
La **clasificación** (`NORMAL` / `VIGILANCIA` / `CRITICO` / `VENCIDO`) sale de
`operacion.fn_clasificar_riesgo`, que resuelve los umbrales en este orden:

1. regla por **SKU** → 2. regla por **categoría** → 3. regla **por defecto**

Los umbrales son datos (`operacion.regla_riesgo`) y se editan desde **Configuración**,
no están en el código.

### 4.3 Inventario y FEFO transaccional

Inventario real por lote y ubicación (`operacion.existencia`) con kardex completo
(`operacion.movimiento_inventario`). La venta consume lotes en orden de caducidad con
`SELECT … FOR UPDATE`, dentro de una sola transacción: si no alcanza el inventario, no se
escribe nada. La pantalla de ventas previsualiza el reparto FEFO antes de confirmar.

### 4.4 Mermas

Siete causas: `CADUCIDAD`, `DANO`, `CALIDAD`, `CADENA_DE_FRIO`, `MANIPULACION`,
`DEVOLUCION`, `OTRA`. Se valida que el lote exista y tenga existencia suficiente, se
registra la merma, se descuenta el inventario y se escribe el evento
`REGISTER_SHRINKAGE`. Nunca se confirma un mensaje sin un INSERT real.

### 4.5 Pronóstico

Sin LSTM: media móvil, media móvil ponderada y suavización exponencial, con
desestacionalización por día de la semana. **Siempre por producto y tienda** (nunca un
pronóstico global). Cada corrida persiste en `analitica.forecast_run` con su
**error medido** por *walk-forward*: MAE, RMSE y WMAPE, y el detalle en
`analitica.forecast_result`. Un pronóstico nunca se declara «bueno» sin medirlo.

### 4.6 Reabastecimiento

```
necesidad_neta = demanda_pronosticada + stock_seguridad − inventario_útil − entradas_confirmadas
cantidad_sugerida = redondeo al alza al MOQ del proveedor
```

Se distingue **inventario físico / en riesgo / útil proyectado**, se respeta el **lead
time** y se advierte cuando el MOQ genera sobreinventario o riesgo de caducidad.
Cada orden guarda su **explicación completa** y queda pendiente de aprobación humana.

### 4.7 Transferencias entre tiendas

Cuatro validaciones guardadas en la propia fila: ¿el origen tiene suficiente?,
¿el destino lo necesita?, ¿llega antes de vencer?, ¿el destino alcanza a consumirlo?
Una transferencia solo se propone si las cuatro pasan.

### 4.8 Aprobación humana

Reabastecimiento, transferencias y descuentos siguen el mismo flujo:
**el sistema recomienda → la persona revisa → aprueba o rechaza → el sistema registra
la decisión y quién la tomó** (`APPROVE_*` / `REJECT_*` en la bitácora).

### 4.9 Alertas

Se derivan de los datos, con huella única para no duplicar mientras siguen abiertas:
`LOTE_POR_VENCER`, `LOTE_VENCIDO`, `RIESGO_DE_MERMA`, `SOBREINVENTARIO`,
`RIESGO_DE_FALTANTE`, `REABASTECIMIENTO_REQUERIDO`, `TRANSFERENCIA_SUGERIDA`.

### 4.10 Merma y desperdicio evitado

Panel de mermas en pesos, por tienda, SKU, causa y caducidad. El **desperdicio evitado**
usa una metodología explícita y auditable, guardada en cada registro:

1. riesgo estimado inicial → 2. intervención aprobada → 3. unidades recuperadas →
4. merma residual

`desperdicio_evitado = cantidad_recuperada`, con `tasa_recuperacion = recuperada / en_riesgo`.

### 4.11 Auditoría

La bitácora es **inmutable**: un disparador bloquea cualquier `UPDATE` o `DELETE`.
Se llena por dos vías: disparadores de fila sobre las tablas de operación y eventos de
aplicación vía `auditoria.fn_registrar_accion(...)`.

Acciones registradas: `LOGIN`, `LOGOUT`, `LOGIN_FALLIDO`, `CREATE_PRODUCT`,
`UPDATE_PRODUCT`, `ACTIVATE_/DEACTIVATE_PRODUCT`, `CREATE_SUPPLIER`, `CREATE_LOCATION`,
`CREATE_BATCH`, `RECEIVE_INVENTORY`, `REGISTER_SALE`, `REGISTER_SHRINKAGE`,
`RUN_FORECAST`, `RUN_ALERTS`, `CREATE_REPLENISHMENT`, `APPROVE_/REJECT_REPLENISHMENT`,
`CREATE_TRANSFER`, `APPROVE_/REJECT_/EXECUTE_TRANSFER`, `CREATE_DISCOUNT`,
`APPROVE_DISCOUNT`, `CREATE_USER`, `UPDATE_USER`, `ACTIVATE_/DEACTIVATE_USER`.

El usuario responsable viaja en la variable de sesión `app.current_user_id`, que la
aplicación fija al abrir cada transacción (`app/db.py`).

### 4.12 Trazabilidad

Proveedor → recepción → tienda/CEDIS → inventario → ventas FEFO → transferencias →
mermas → estado final, reconstruida desde `analitica.v_trazabilidad_lote` y el kardex.

### 4.13 API JSON con JWT

`/api/kpis`, `/api/inventario`, `/api/inventario/fefo`, `/api/alertas`, `/api/pronostico`,
`/api/reabastecimiento`, `/api/transferencias`, `/api/mermas`,
`/api/trazabilidad/<id_lote>`, `POST /api/ventas`, `POST /api/mermas`,
`POST /api/pronostico/ejecutar`. Exige `Authorization: Bearer <token>`; las escrituras
además comprueban el rol.

---

## 5. Demostración

### 5.1 Escenario extremo a extremo

```bash
python scripts/demo_avance2.py --escenario
```

Recorre, **a través de la capa HTTP real** (cliente de pruebas de Flask), el guion
completo: login auditado, alta de proveedor/producto/tienda, edición y
activar-desactivar, dos recepciones con distinta caducidad, cálculo de vida útil y
clasificación de riesgo, venta con FEFO demostrado, pronóstico con error medido,
reabastecimiento con explicación, aprobación de la orden, transferencia con sus cuatro
validaciones, aprobación y ejecución, descuento aprobado, merma, rechazo de una merma
imposible, alertas, panel, trazabilidad y API con JWT. Cada paso imprime el valor
consultado a PostgreSQL y marca `OK`/`FALLO`.

### 5.2 Persistencia

```bash
python scripts/demo_avance2.py --verificar
```

Proceso **nuevo**: relee todas las tablas, encuentra el escenario, y vuelve a pedir
`/panel`, `/inventario` y `/lotes` con la aplicación recién arrancada. Demuestra que la
información sigue ahí porque vive en PostgreSQL, no en la memoria de Flask.

### 5.3 Pantallas y permisos

```bash
python scripts/smoke_rutas.py
```

Recorre las 73 pantallas con los 7 roles y comprueba que cada una responde 200 con el
rol que tiene permiso, que la landing pública no exige sesión y que las rutas privadas
sí.

---

## 6. Estructura del repositorio

```text
├── app/                      Aplicación Flask (factory + blueprints)
├── docs/                     Documentos de diseño y reporte técnico
├── scripts/
│   ├── bootstrap_db.py       Crea base, roles, esquemas y datos base
│   ├── ETL.py                Carga la historia operativa
│   ├── demo_avance2.py       Escenario extremo a extremo + verificación
│   └── smoke_rutas.py        Prueba de humo de todas las pantallas
├── sql/
│   ├── 00_init_roles.sh      Roles transaccionales
│   ├── 01_init_schemas.sql   Extensiones y esquemas
│   ├── 02_ddl_auditoria.sql  Bitácora inmutable y funciones de auditoría
│   ├── 03_ddl_operacion.sql  Esquema transaccional
│   ├── 04_ddl_analitica.sql  Pronóstico, alertas, transferencias, desperdicio
│   ├── 05_funciones_negocio.sql  Vida útil, riesgo, folios, configuración
│   ├── 06_views.sql          Vistas de consulta
│   ├── 07_seed_base.sql      Roles de negocio, catálogos y usuarios
│   └── legacy/               Volcados de una versión anterior (no se ejecutan)
├── mongo/
│   └── 01_init_freshtrack.js Colecciones, validadores e índices de MongoDB
├── Dockerfile
├── docker-compose.yml        PostgreSQL + MongoDB + Redis + aplicación
├── env.example
├── Makefile
├── requirements.txt
└── run.py                    Punto de entrada (comprueba la conexión antes de servir)
```

---

## 7. Notas de seguridad

- Ninguna credencial vive en el código. `SECRET_KEY` y `DATABASE_URL` son obligatorias:
  la aplicación falla al arrancar si faltan, en vez de caer a un valor por defecto.
- Las contraseñas se verifican **dentro de PostgreSQL** con `crypt()` (pgcrypto); el texto
  en claro nunca se compara en Python.
- Hay bloqueo temporal tras varios intentos fallidos y los usuarios inactivos se rechazan.
- La bitácora de auditoría es inmutable por disparador.
- `.env` está en `.gitignore`. Las claves de demostración deben rotarse antes de publicar.
