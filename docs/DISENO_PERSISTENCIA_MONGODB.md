# FreshTrack — Diseño y Especificación de Persistencia en MongoDB

> **Integración de Aplicaciones Computacionales**  
> **Arquitectura de Persistencia Políglota — FreshTrack**  
> **Motor Documental**: MongoDB 7.0 (Alpine Container `freshtrack_mongo`)  
> **Fuente de Verdad Transaccional**: PostgreSQL 17  
> **Capa de Conectividad**: Python 3.14 con `pymongo >= 4.6.0`

---

## 1. Justificación Arquitectónica: ¿Por qué MongoDB?

En el diseño original ([`docs/BD_Diseño.docx`](../docs/BD_Diseño.docx)), PostgreSQL fue establecido como la **única fuente de verdad para el negocio transaccional** (catálogos de usuarios, productos, locaciones, transacciones de venta, deducciones de inventario FEFO y bitácora de auditoría inmutable regulada).

Sin embargo, los entornos modernos de comercio minorista y logística de perecederos enfrentan tres desafíos que degradan severamente a un motor relacional puro si se fuerza su almacenamiento en tablas rígidas:

1. **Variabilidad de Formatos de Entrada de Proveedores Externos (Avisos ASN)**:  
   Cada proveedor o transportista utiliza variantes de estándares EDIFACT, GS1 XML o JSON con jerarquías anidadas impredecibles (detalles de pallets, bultos, múltiples lecturas de temperatura en tránsito y observaciones de calidad). En PostgreSQL, modelar esto requeriría múltiples tablas con decenas de columnas nulas o continuas migraciones DDL (`ALTER TABLE`). En **MongoDB**, los manifiestos se almacenan como documentos BSON nativos con arreglos embebidos (`detalle_carga`, `inspecciones`).
2. **Series Temporales y Percentiles de Demanda Proyectada (`pronosticos_demanda`)**:  
   Los algoritmos de predicción estadística (Media Móvil, Suavización Exponencial, Prophet) generan curvas temporales completas con intervalos de confianza y percentiles (P10, P50, P90). Guardar cada punto diario como una fila individual en PostgreSQL causaría un crecimiento explosivo de tablas (>500,000 filas por corrida) con alta sobrecarga de índices B-tree. En **MongoDB**, toda la corrida se encapsula en un único documento inmutable autónomo, garantizando linaje algorítmico y lectura en $O(1)$.
3. **Eventos y Alertas Operativas de Alta Frecuencia con Ciclo de Vida Efímero (`alertas_operativas`)**:  
   Los sensores de cámaras frigoríficas y los escaneos pre-merma emiten cientos de advertencias diarias. En un motor transaccional, estas alertas saturan la base y obligan a crear procesos de purga (`cron jobs` con `DELETE FROM`), generando fragmentación de tablas y problemas de bloat (VACUUM). En **MongoDB**, se utiliza la característica nativa de **Índices TTL (Time-To-Live)**, donde el motor purga automáticamente los documentos tras 180 días a nivel de disco sin consumo de CPU de la aplicación.

---

## 2. Relación y Coordinación entre MongoDB y PostgreSQL

> [!IMPORTANT] Principio de Segregación de Responsabilidades
> - **PostgreSQL**: Conserva el control transaccional estricto (ACID), inventario en piso, balances contables y auditoría trigger-level.
> - **MongoDB**: Conserva proyecciones documentales, historiales algorítmicos, evidencias de inspección y eventos de monitoreo.
> - **Redis**: Sincroniza ambos motores mediante mensajería reactiva en Redis Streams (`freshtrack:events`).

### 2.1 Modelo Conceptual de Relación Lógica
MongoDB **no duplica** los datos maestros de PostgreSQL; en su lugar, utiliza **identificadores foráneos lógicos** que coinciden exactamente con las claves primarias relacionales:

```
[ POSTGRESQL (ACID) ]                         [ MONGODB (Document Store) ]
=====================                         ============================
operacion.producto (id_sku) ------------+---> pronosticos_demanda.id_sku
                                        |---> alertas_operativas.id_sku
                                        +---> avisos_asn.detalle_carga[].id_sku

operacion.locacion (id_locacion) -------+---> pronosticos_demanda.id_locacion
                                        +---> alertas_operativas.id_locacion

operacion.proveedor (id_proveedor) ------> avisos_asn.id_proveedor

operacion.lote (id_lote) ----------------> alertas_operativas.id_lote
```

---

## 3. Catálogo de Colecciones y Validación de Esquema

MongoDB implementa validadores a nivel de colección mediante `$jsonSchema` (`validationLevel: "moderate"`, `validationAction: "error"`) configurados en [`mongo/01_init_freshtrack.js`](../mongo/01_init_freshtrack.js) y asegurados por [`app/services/doc_store.py`](../app/services/doc_store.py):

### 3.1 Colección: `avisos_asn`
Almacena avisos anticipados de despacho enviados por proveedores antes del arribo al CEDIS.
```json
{
  "_id": ObjectId("..."),
  "folio_asn": "ASN-2026-00891",
  "id_proveedor": 1,
  "fecha_embarque": ISODate("2026-10-21T08:00:00Z"),
  "fecha_arribo_estimada": ISODate("2026-10-23T12:00:00Z"),
  "estado": "ANUNCIADO",
  "detalle_carga": [
    {
      "id_sku": 1,
      "cantidad_declarada": 500.0,
      "lote_proveedor": "L-FRESAS-09",
      "rango_temperatura_controlada": "2C a 6C"
    }
  ],
  "inspecciones": [
    {
      "id_inspeccion": "6ad93...",
      "fecha": ISODate("2026-10-21T15:30:00Z"),
      "inspector": "auditor_cedis",
      "resultado": "CONFORME",
      "temperatura_registrada": 4.1,
      "observaciones": "Cadena de frío respetada"
    }
  ],
  "version_esquema": 1
}
```

### 3.2 Colección: `pronosticos_demanda`
Almacena la serie proyectada para los siguientes $T+7$ días con intervalos de confianza y percentiles.
```json
{
  "_id": ObjectId("..."),
  "id_sku": 1,
  "id_locacion": 3,
  "fecha_calculo": ISODate("2026-10-21T10:00:00Z"),
  "horizonte_proyeccion": {
    "fecha_inicio": ISODate("2026-10-22T00:00:00Z"),
    "fecha_fin": ISODate("2026-10-28T00:00:00Z"),
    "dias": 7
  },
  "modelo": "SUAVIZACION_EXPONENCIAL",
  "version_modelo": "1.0",
  "linaje": { "generado_por": "planificador@freshtrack.local", "id_run": "run_01" },
  "metricas": { "mae": 7.307, "rmse": 8.75 },
  "puntos": [
    { "fecha": ISODate("2026-10-22T00:00:00Z"), "demanda_pronosticada": 25.4, "intervalo_inferior": 21.5, "intervalo_superior": 29.2, "percentil": 50 }
  ],
  "version_esquema": 1
}
```

### 3.3 Colección: `alertas_operativas`
Almacena incidentes de pre-merma y desviación térmica.
```json
{
  "_id": ObjectId("..."),
  "tipo": "RIESGO_PRE_MERMA",
  "criticidad": "CRITICAL",
  "id_sku": 1,
  "id_locacion": 1,
  "id_lote": 105,
  "mensaje": "Lote de fresas a 1 día de caducidad en cámara fría",
  "generada_en": ISODate("2026-10-21T14:00:00Z"),
  "atendida": false,
  "contexto": { "dias_restantes": 1, "temperatura_sensor": 7.2 },
  "version_esquema": 1
}
```

---

## 4. Demostración y Validación de las 7 Operaciones Requeridas

La suite automatizada [`scripts/verify_mongo.py`](../scripts/verify_mongo.py) (ejecutable vía `make verify-mongo`) comprueba punto por punto las 7 operaciones:

### 1. Inserción de Documentos
- **Individual**: `doc_store.registrar_aviso_asn(...)` utiliza `db.avisos_asn.insert_one(documento)` respetando el validador JSON Schema.
- **Masiva**: `doc_store.guardar_alertas_lote(lote_alertas)` utiliza `db.alertas_operativas.insert_many(docs)` para procesar ráfagas de alertas de escaneo en un solo viaje de red (*round-trip*).

### 2. Consultas y Recuperación con Proyección Selectiva
- **Búsqueda exacta**: `doc_store.detalle_asn(folio_asn)` ejecuta `find_one({"folio_asn": folio_asn})`.
- **Proyección selectiva de atributos**: `doc_store.obtener_resumen_pronostico(id_sku, id_locacion)` optimiza el tráfico de red trayendo metadatos sin descargar el arreglo completo de puntos:
  ```python
  db.pronosticos_demanda.find_one(
      {"id_sku": id_sku, "id_locacion": id_locacion},
      projection={"_id": 1, "modelo": 1, "metricas": 1, "horizonte_proyeccion": 1}
  )
  ```

### 3. Actualización de Documentos ($set, $push)
- **Operador `$set`**: `doc_store.marcar_alerta_atendida(id_mongo)` actualiza el estado y fecha de atención atómicamente:
  ```python
  db.alertas_operativas.update_one({"_id": ObjectId(id_mongo)}, {"$set": {"atendida": True, "atendida_en": ahora}})
  ```
- **Operador `$push`**: `doc_store.agregar_inspeccion_asn(...)` añade un registro de inspección de calidad y temperatura dentro del arreglo embebido `inspecciones`:
  ```python
  db.avisos_asn.update_one({"folio_asn": folio_asn}, {"$push": {"inspecciones": nueva_inspeccion}})
  ```

### 4. Filtrado por Criterios Combinados ($in, $gte, $lte)
- `doc_store.buscar_alertas_avanzado(...)` combina:
  - `$in`: `{"criticidad": {"$in": ["CRITICAL", "WARNING"]}}`
  - `$lte` sobre campo anidado: `{"contexto.dias_restantes": {"$lte": 5}}`
  - `$gte` / `$lte` sobre rangos de fecha de emisión `generada_en`.

### 5. Agregaciones Mediante Pipelines (`aggregate`)
FreshTrack implementa 3 pipelines analíticos de valor operativo:
1. **Pipeline de Alertas por Locación y Criticidad**:
   ```javascript
   db.alertas_operativas.aggregate([
     { $match: { atendida: false } },
     { $group: {
         _id: { id_locacion: "$id_locacion", criticidad: "$criticidad" },
         total_alertas: { $sum: 1 },
         promedio_dias_restantes: { $avg: "$contexto.dias_restantes" }
     }},
     { $project: { _id: 0, id_locacion: "$_id.id_locacion", criticidad: "$_id.criticidad", total_alertas: 1, promedio_dias_restantes: { $round: ["$promedio_dias_restantes", 1] } }},
     { $sort: { total_alertas: -1 } }
   ]);
   ```
2. **Pipeline de Consolidación de Carga ASN por Proveedor y SKU** (`$unwind` + `$group`):
   Desenrolla el arreglo de detalle para totalizar volumen proyectado por proveedor:
   ```javascript
   db.avisos_asn.aggregate([
     { $unwind: "$detalle_carga" },
     { $group: {
         _id: { id_proveedor: "$id_proveedor", id_sku: "$detalle_carga.id_sku" },
         piezas_totales: { $sum: "$detalle_carga.cantidad_declarada" },
         despachos_asociados: { $sum: 1 }
     }},
     { $sort: { piezas_totales: -1 } }
   ]);
   ```
3. **Pipeline de Rendimiento Algorítmico de Pronósticos**:
   Agrupa corridas históricas calculando el error medio absoluto (MAE) y cuadrático (RMSE) por modelo.

### 6. Creación y Uso de Índices con Verificación `explain()`
FreshTrack asegura de forma idempotente 9 índices clave:
- **Índice Único**: `uq_asn_folio` en `avisos_asn` sobre `{"folio_asn": 1}`.
- **Índice Compuesto**: `idx_pronostico_sku_locacion_fecha` en `pronosticos_demanda` sobre `{"id_sku": 1, "id_locacion": 1, "fecha_calculo": -1}`.
- **Índice TTL (Time-To-Live)**: `idx_alerta_retencion_ttl` en `alertas_operativas` sobre `{"generada_en": 1}` con `expireAfterSeconds: 15552000` (180 días).

**Evidencia de Uso (Plan de Consulta con Explain)**:
Al ejecutar `db.avisos_asn.find({"folio_asn": "..."}).explain()`, el planificador resuelve la consulta mediante **`IXSCAN`** / **`FETCH`** utilizando el índice `uq_asn_folio`, descartando escaneos completos de colección (`COLLSCAN`).

### 7. Recuperación Mediante Identificadores del Sistema (Cruce PostgreSQL ↔ MongoDB)
Demostrado en `doc_store.obtener_contexto_documental_sku(id_sku, id_locacion)`:
1. La aplicación consulta los datos maestros de producto (`nombre`, `categoría`, `precio`) en PostgreSQL (`operacion.producto`).
2. Mediante el `id_sku` y el `id_locacion`, consulta a MongoDB para adjuntar el último pronóstico algorítmico y las alertas pre-merma abiertas.
3. Se devuelve una respuesta compuesta que unifica la consistencia relacional con el detalle documental sin acoplamiento de esquemas.

---

## 5. Exposición en Microservicios y Endpoints

| Microservicio | Puerto | Endpoint | Método | Operación Demostrada |
|---|---|---|---|---|
| `svc-asn` | 5005 | `/api/v1/asn` | POST / GET | Inserción y listado de manifiestos ASN |
| `svc-asn` | 5005 | `/api/v1/asn/<folio_asn>/inspection` | POST | **$push**: Registro atómico de inspección de frío |
| `svc-asn` | 5005 | `/api/v1/asn/analytics/summary` | GET | **Pipeline**: Carga ASN por proveedor ($unwind+$group) |
| `svc-alerts` | 5007 | `/api/v1/alerts/active` | GET | **Filtrado**: Alertas abiertas por criticidad y locación |
| `svc-alerts` | 5007 | `/api/v1/alerts/<id_mongo>/resolve` | PATCH | **$set**: Atención de alerta |
| `svc-alerts` | 5007 | `/api/v1/alerts/analytics/kpis` | GET | **Pipeline**: KPIs de alertas por sucursal |
| `svc-planning` | 5006 | `/api/v1/planning/forecast/latest/<sku>/<loc>` | GET | **Proyección**: Última corrida de pronóstico |
| `svc-planning` | 5006 | `/api/v1/planning/forecast/analytics/kpis` | GET | **Pipeline**: Precisión estadística de modelos |
| `svc-planning` | 5006 | `/api/v1/planning/sku/<sku>/full-context` | GET | **Cruce Híbrido**: PostgreSQL ↔ MongoDB |

---

## 6. Métodos de Demostración y Prueba

### 6.1 Prueba Automatizada por Consola
Para ejecutar la comprobación de todas las operaciones en 3 segundos:
```bash
make verify-mongo
```
O dentro de la suite completa de verificación:
```bash
make test
```

### 6.2 Demostración Visual e Interactiva
1. **Tablero Web Unificado de FreshTrack**:
   - Iniciar la aplicación: `make app`
   - Abrir en el navegador: [http://127.0.0.1:5000](http://127.0.0.1:5000)
   - Iniciar sesión con cualquier rol (ej. `admin@freshtrack.local` / `admin123`).
   - Hacer clic en el menú lateral en **Analítica › MongoDB Políglota** (o navegar directamente a [http://127.0.0.1:5000/mongo](http://127.0.0.1:5000/mongo)).
   - Se mostrarán las tarjetas de estado, los 3 pipelines de agregación en tiempo real y el listado de índices activos.
2. **Swagger UI Interactivo de Microservicios**:
   - Abrir en el navegador:
     - `http://127.0.0.1:5005/api/v1/docs` (Microservicio ASN)
     - `http://127.0.0.1:5006/api/v1/docs` (Microservicio Planning)
     - `http://127.0.0.1:5007/api/v1/docs` (Microservicio Alerts)
