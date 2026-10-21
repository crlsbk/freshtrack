# Guion de demostración — Comprador y Planeador

Guion paso a paso para exponer el flujo de los roles **Comprador** (`buyer`) y
**Planeador** (`planner`). Todo lo que se indica aquí existe en el código: los
permisos salen de `app/navegacion.py` y las pantallas y acciones de
`app/blueprints/`. No hace falta escribir código ni cargar datos nuevos: con la
base inicializada (`make bootstrap` + `make etl`) hay material de sobra.

> Referencia rápida: permisos `app/navegacion.py:96-138`; pantallas analíticas
> `app/blueprints/analitica.py`; operación `app/blueprints/operacion.py`;
> catálogos `app/blueprints/catalogo.py`; tablero y alertas
> `app/blueprints/panel.py`; nombres de eventos `app/auditoria.py:18-50`.

---

## 1. Cuentas

| Rol | Correo | Contraseña | Pantalla inicial |
|---|---|---|---|
| Comprador | `buyer@freshtrack.mx` | `Compras2026!` | **Reabastecimiento** |
| Planeador | `planner@freshtrack.mx` | `Plan2026!` | **Pronósticos** |

Las contraseñas viven en `sql/07_seed_base.sql` y **deben cambiarse** antes de
cualquier despliegue real. La pantalla de acceso lista las cuentas y rellena el
formulario con un clic: sirve para arrancar la demo sin teclear.

### Qué ve cada rol

| Sección | Comprador | Planeador |
|---|---|---|
| Principal | Panel de Control, Alertas | Panel de  Control, Alertas |
| Catálogos | Productos, **Proveedores** | Productos |
| Operación | Lotes y Recepción, Inventario, Trazabilidad | Lotes y Recepción, Inventario, **Ventas**, Trazabilidad |
| Analítica | Pronósticos, **Reabastecimiento** | Pronósticos, Reabastecimiento, **Transferencias**, **Descuentos** |
| Desperdicio | — | Desperdicio Evitado, Sostenibilidad |

En negrita, lo que hace diferente a cada rol: el Comprador domina catálogo de
proveedores y compras; el Planeador domina pronóstico, transferencias entre
tiendas y descuentos.

---

## 2. Preparación (5 minutos)

1. **Base y aplicación en pie.**

   ```bash
   make bootstrap      # idempotente
   make etl            # 180 días de historia, si aún no la cargaste
   make app            # Flask en http://127.0.0.1:5000
   ```

2. **Dos sesiones a la vez.** La sesión web es una cookie firmada con
   `SECRET_KEY`, así que en el mismo navegador la segunda cuenta reemplaza a la
   primera. Abre **una ventana normal para el Comprador** y **una ventana de
   incógnito para el Planeador**: alternas de rol sin cerrar sesión a mitad de la
   exposición.

3. **Una terminal con `psql` a la vista**, para responder «¿y eso dónde quedó?»:

   ```bash
   PGPASSWORD=999 psql -h 127.0.0.1 -U postgres -d retail_perecederos
   ```

4. **Datos frescos (opcional).**

   ```bash
   .venv/bin/python scripts/ETL.py --reset   # recarga la historia; no toca catálogos ni usuarios
   ```

> ⚠️ **No uses `scripts/demo_avance2.py --escenario` para esta demo.** Está escrito
> para el rol **admin** (inicia sesión como `admin@freshtrack.mx`) y arranca
> borrando los datos de su propio escenario. Los flujos de Comprador y Planeador se
> recorren en el navegador; §7 explica la alternativa por API.

---

## 3. Estado de partida (referencia)

Números observados en la base de trabajo cuando se escribió este guion:

| Dato | Cantidad |
|---|---|
| Productos / Proveedores / Locaciones | 13 / 7 / 8 |
| Lotes / Ventas | 4 206 / 10 862 |
| Corridas de pronóstico | 5 |
| Alertas abiertas | 109 |
| Órdenes de reabastecimiento | 52 PENDIENTE · 5 APROBADA · 2 RECHAZADA |
| Transferencias | 3 SUGERIDA · 1 APROBADA · 1 EJECUTADA |
| Descuentos | 17 SUGERIDO · 5 APROBADO |

Para recontar antes de exponer (por si tu base cambió):

```sql
SELECT estado, count(*) FROM analitica.orden_reabastecimiento GROUP BY estado;
SELECT estado, count(*) FROM analitica.transferencia        GROUP BY estado;
SELECT estado, count(*) FROM analitica.descuento            GROUP BY estado;
SELECT count(*) FROM analitica.alerta WHERE estado = 'ABIERTA';
SELECT count(*) FROM analitica.forecast_run;
```

Si algún contador está en cero, el guion indica en qué paso se genera: no hay que
preparar nada a mano.

## 4. Guion del Comprador — «comprar sin sobreinventar» (~10 min)

Entra con `buyer@freshtrack.mx` / `Compras2026!`. Aterriza directo en
**Analítica › Reabastecimiento** (`app/navegacion.py:132`: es su vista inicial).

| # | Pantalla | Acción | Qué se demuestra |
|---|---|---|---|
| 1 | Menú lateral | Recorrerlo | El RBAC de verdad: el Comprador **no ve** Ventas, FEFO, Mermas, Transferencias, Descuentos, Usuarios ni Bitácora. |
| 2 | Analítica › Reabastecimiento | Leer los KPIs: **Órdenes pendientes**, **Urgentes**, **Aprobadas**, **Valor estimado pendiente** | El Comprador abre en una bandeja de trabajo, no en una pantalla decorativa: ve pendientes y dinero comprometido. |
| 3 | Misma pantalla, abajo | Bloque **Sobreinventario detectado** | El motor también le dice dónde **no** debe comprar (cobertura por encima del umbral o producto que caduca antes de venderse). |
| 4 | Selector «Horizonte» = `7 días` → **Generar recomendaciones** | Ejecutar | Aviso: *«Se generaron N recomendaciones… cada una incluye su explicación y queda pendiente de aprobación»*. Aclarar: las combinaciones producto + tienda que **ya** tienen una orden PENDIENTE no se duplican. |
| 5 | Una tarjeta de orden | Abrir el detalle | El argumento central: la fórmula del encabezado hecha números — *demanda pronosticada + stock de seguridad − inventario útil − entradas confirmadas* — con **inventario útil** separado del **inventario en riesgo** (lo que está por vencer no cubre demanda), más **lead time** y **MOQ** del proveedor. |
| 6 | Misma tarjeta | Bajar a **Explicación guardada** | El texto quedó escrito en la orden (`analitica.orden_reabastecimiento.explicacion`), no se recalcula al vuelo: se puede auditar después. |
| 7 | Botón **Aprobar** (campo «Cantidad a aprobar») | Aprobar dejando la cantidad sugerida y luego repetir con otra cantidad | El sistema **sugiere**, el humano **decide**: sale *«Orden aprobada por X unidades. La encuentras con el filtro «APROBADA»»*. |
| 8 | KPI **Aprobadas** (es un enlace) | Clic | La lista de aprobadas, cada tarjeta con la línea **«Decidió: <nombre>»** y la fecha. Trazabilidad de la decisión humana. |
| 9 | Filtro **Estado** | Elegir `RECHAZADA` → **Filtrar** | Y a continuación **Rechazar** una orden de prioridad baja (el botón está en el filtro `PENDIENTE`). La orden aparece después en `RECHAZADA`. Los estados disponibles son `PENDIENTE`, `APROBADA`, `RECHAZADA`, `EJECUTADA`, `CANCELADA` y `TODAS`. |
| 10 | Catálogos › **Proveedores** | Abrir uno y editar **lead time** y **MOQ** (p. ej. lead 1→5, MOQ 80→150) | Los parámetros del proveedor alimentan el motor: la propia pantalla lo advierte («El lead time y el MOQ alimentan el motor de reabastecimiento»). |
| 11 | Analítica › Reabastecimiento | **Generar recomendaciones** otra vez y comparar | El cambio se ve en la cantidad sugerida y en las advertencias. ⚠️ **Tip:** si ese producto + tienda ya tiene una orden `PENDIENTE`, el motor no crea otra (evita duplicados). Decide primero esa orden (apruébala o recházala) y vuelve a generar. |
| 12 | Principal › **Alertas** | **Recalcular alertas desde PostgreSQL** y **Marcar atendida** una | El Comprador también opera su parte del motor de alertas. |
| 13 | Operación › **Lotes y Recepción** | Registrar la recepción de un lote del proveedor que editó | Cierra el ciclo físico: *compré → llegó → entró al inventario* (evento `RECEIVE_INVENTORY`). |

### Frases que funcionan bien en este guion

- «El Comprador no adivina: la cantidad sugerida es una resta verificable, y el
  sistema guarda la explicación junto con la orden.»
- «El **MOQ** es lo que obliga a comprar más de lo que la fórmula pedía; el
  sistema lo advierte y el humano asume la decisión.»
- «Al aprobar no desaparece nada: la orden se queda en la base con **quién**,
  **cuándo** y **por cuánto** — mira el filtro `APROBADA`.»
- «Lo que está por vencer **no** cuenta como inventario disponible: por eso el
  inventario útil es menor que el físico.»

### Lo que el Comprador **no** puede hacer (para no perder tiempo)

No ve ni puede entrar a: Tiendas y CEDIS, Ventas, Cola FEFO, Mermas,
Transferencias, Descuentos, Usuarios y Roles, Bitácora ni Configuración. Si
intentas abrir esas URL con su sesión, la aplicación te devuelve a su vista
inicial: eso también es demostrable.

<!-- PENDIENTE: guion planeador -->

