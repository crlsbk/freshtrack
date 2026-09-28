// =============================================================================
// FreshTrack — inicialización de MongoDB
//
// Se ejecuta una sola vez, cuando el contenedor crea el volumen por primera vez.
// Crea las tres colecciones que define el diseño (docs/Documento_Analitico_FreshTrack.pdf)
// con su validador de esquema y sus índices.
//
// Colecciones:
//   pronosticos_demanda  — series de tiempo con esquema variable (intervalos de
//                          confianza, percentiles). Linaje algorítmico inmutable.
//   avisos_asn           — avisos anticipados de embarque del proveedor (ASN),
//                          con detalle_carga anidado.
//   alertas_operativas   — alertas pre-merma con criticidad, para tableros.
//
// Nota: este aviso NO es fuente de datos del flujo funcional del avance actual.
// El sistema opera contra PostgreSQL. Estas colecciones quedan listas para las
// siguientes parciales.
// =============================================================================

const ESQUEMA_VERSION = 1;
const DIAS_RETENCION_ALERTAS = 180;

// --- pronosticos_demanda -----------------------------------------------------
// RN-ML-03: todo pronóstico es inmutable. Se guarda el linaje (modelo, versión y
// hash de la entrada) para poder auditar con qué datos se generó cada corrida.
db.createCollection("pronosticos_demanda", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["id_sku", "id_locacion", "fecha_calculo", "horizonte_proyeccion", "modelo", "version_esquema"],
      properties: {
        id_sku: { bsonType: ["int", "long"], description: "FK lógica a operacion.producto" },
        id_locacion: { bsonType: ["int", "long"], description: "FK lógica a operacion.locacion (tienda o CEDIS)" },
        fecha_calculo: { bsonType: "date" },
        // RN-ML-01: el horizonte debe cubrir al menos 7 días naturales (T+7).
        horizonte_proyeccion: {
          bsonType: "object",
          required: ["fecha_inicio", "fecha_fin", "dias"],
          properties: {
            fecha_inicio: { bsonType: "date" },
            fecha_fin: { bsonType: "date" },
            dias: { bsonType: ["int", "long"], minimum: 7 }
          }
        },
        modelo: { bsonType: "string", description: "p. ej. SUAVIZACION_EXPONENCIAL, MEDIA_MOVIL, PROPHET, XGBOOST" },
        version_modelo: { bsonType: "string" },
        linaje: {
          bsonType: "object",
          properties: {
            hash_entrada: { bsonType: "string" },
            ventana_entrenamiento_dias: { bsonType: ["int", "long"] },
            generado_por: { bsonType: "string" }
          }
        },
        metricas: {
          bsonType: "object",
          properties: {
            mae: { bsonType: ["double", "decimal", "int", "long"] },
            rmse: { bsonType: ["double", "decimal", "int", "long"] },
            wmape: { bsonType: ["double", "decimal", "int", "long"] }
          }
        },
        puntos: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["fecha", "demanda_pronosticada"],
            properties: {
              fecha: { bsonType: "date" },
              demanda_pronosticada: { bsonType: ["double", "decimal", "int", "long"], minimum: 0 },
              intervalo_inferior: { bsonType: ["double", "decimal", "int", "long"] },
              intervalo_superior: { bsonType: ["double", "decimal", "int", "long"] },
              percentil: { bsonType: ["int", "long"] }
            }
          }
        },
        version_esquema: { bsonType: ["int", "long"] }
      }
    }
  },
  validationLevel: "moderate",
  validationAction: "error"
});

// Una corrida por producto, tienda y momento de cálculo.
db.pronosticos_demanda.createIndex(
  { id_sku: 1, id_locacion: 1, fecha_calculo: -1 },
  { name: "idx_pronostico_sku_locacion_fecha" }
);
// Consultas por horizonte: "¿qué se proyectó para tal fecha?"
db.pronosticos_demanda.createIndex(
  { "horizonte_proyeccion.fecha_fin": 1, id_locacion: 1 },
  { name: "idx_pronostico_horizonte_locacion" }
);
db.pronosticos_demanda.createIndex(
  { modelo: 1, version_modelo: 1, fecha_calculo: -1 },
  { name: "idx_pronostico_modelo_version" }
);

// --- avisos_asn --------------------------------------------------------------
db.createCollection("avisos_asn", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["folio_asn", "id_proveedor", "detalle_carga", "estado", "version_esquema"],
      properties: {
        folio_asn: { bsonType: "string", description: "Identificador del aviso anticipado de embarque" },
        id_proveedor: { bsonType: ["int", "long"] },
        fecha_embarque: { bsonType: "date" },
        fecha_arribo_estimada: { bsonType: "date" },
        estado: {
          enum: ["ANUNCIADO", "EN_TRANSITO", "RECIBIDO", "REVISION_CALIDAD", "CANCELADO"]
        },
        // Documentos embebidos: el detalle viaja con el aviso, no en una colección aparte.
        detalle_carga: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["id_sku", "cantidad_declarada"],
            properties: {
              id_sku: { bsonType: ["int", "long"] },
              cantidad_declarada: { bsonType: ["double", "decimal", "int", "long"], minimum: 0 },
              lote_proveedor: { bsonType: "string" },
              fecha_caducidad: { bsonType: "date" },
              // RN-LOG-03: se vigila la ruptura de cadena de frío.
              rango_temperatura_controlada: { bsonType: "string" }
            }
          }
        },
        version_esquema: { bsonType: ["int", "long"] }
      }
    }
  },
  validationLevel: "moderate",
  validationAction: "error"
});

db.avisos_asn.createIndex({ folio_asn: 1 }, { name: "uq_asn_folio", unique: true });
db.avisos_asn.createIndex(
  { id_proveedor: 1, fecha_embarque: -1 },
  { name: "idx_asn_proveedor_fecha" }
);
db.avisos_asn.createIndex({ estado: 1 }, { name: "idx_asn_estado" });

// --- alertas_operativas ------------------------------------------------------
db.createCollection("alertas_operativas", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tipo", "criticidad", "generada_en", "atendida", "version_esquema"],
      properties: {
        tipo: {
          enum: [
            "RIESGO_PRE_MERMA",
            "RUPTURA_CADENA_FRIO",
            "DISCREPANCIA_ASN",
            "EXCESO_COBERTURA"
          ]
        },
        criticidad: { enum: ["INFO", "WARNING", "CRITICAL"] },
        id_sku: { bsonType: ["int", "long"] },
        id_locacion: { bsonType: ["int", "long"] },
        id_lote: { bsonType: ["int", "long"] },
        mensaje: { bsonType: "string" },
        contexto: { bsonType: "object" },
        generada_en: { bsonType: "date" },
        atendida: { bsonType: "bool" },
        atendida_en: { bsonType: "date" },
        version_esquema: { bsonType: ["int", "long"] }
      }
    }
  },
  validationLevel: "moderate",
  validationAction: "error"
});

// Tableros: "alertas abiertas por criticidad, más recientes primero".
db.alertas_operativas.createIndex(
  { atendida: 1, criticidad: 1, generada_en: -1 },
  { name: "idx_alerta_abierta_criticidad" }
);
db.alertas_operativas.createIndex(
  { id_locacion: 1, tipo: 1, generada_en: -1 },
  { name: "idx_alerta_locacion_tipo" }
);
// Estrategia de crecimiento: las alertas atendidas caducan solas a los 180 días.
db.alertas_operativas.createIndex(
  { generada_en: 1 },
  { name: "idx_alerta_retencion_ttl", expireAfterSeconds: DIAS_RETENCION_ALERTAS * 86400 }
);

// --- Marca de versión del esquema -------------------------------------------
db.getCollection("_esquema").insertOne({
  version: ESQUEMA_VERSION,
  aplicado_en: new Date(),
  descripcion: "Estructura inicial de FreshTrack: pronosticos_demanda, avisos_asn, alertas_operativas",
  retencion_alertas_dias: DIAS_RETENCION_ALERTAS
});

print("[freshtrack] MongoDB inicializado: 3 colecciones, validadores e índices creados.");
