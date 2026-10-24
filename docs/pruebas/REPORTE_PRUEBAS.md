# Reporte de pruebas unitarias y de integración

Generado automáticamente por `scripts/generar_reporte_pruebas.py` el 2026-10-23 23:38. El resultado obtenido y el estado de cada caso salen de la ejecución real de pytest, no se escriben a mano.

## Entorno de ejecución

- **Python:** 3.14.8 (Linux)
- **PostgreSQL:** PostgreSQL 17.11 on x86_64-pc-linux-musl
- **Redis:** real (contenedor)
- **MongoDB:** real (contenedor)
- **Comando:** `python -m pytest tests -v --junitxml=docs/pruebas/resultado_pytest.xml`

## Resumen

| Tipo | Ejecutadas | Pasaron | Fallaron | Omitidas |
|---|---:|---:|---:|---:|
| Unitaria | 89 | 89 | 0 | 0 |
| Integración | 27 | 27 | 0 | 0 |
| **Total** | **116** | **116** | **0** | **0** |

Tiempo total: 2.94 s. Las pruebas de integración corren contra el PostgreSQL real con el seed de FreshTrack y levantan los 8 microservicios en el mismo proceso, compartiendo Redis y MongoDB igual que en docker compose.

## Unitaria: `tests/unit/test_contratos_json_xml.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-01 | `test_respuesta_json_por_omision` | Verificar que sin cabecera Accept la respuesta sea JSON. | `render_response({'a': 1}, status=201)` sin `Accept`. | HTTP 201, `application/json`, cuerpo `{"a": 1}`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-02 | `test_respuesta_xml_con_accept` | Verificar la negociación de contenido hacia XML. | `Accept: application/xml`, `text/xml` y `application/xml;q=0.9`; dict con objeto anidado y lista. | `application/xml` con declaración UTF-8; objeto anidado como elementos y lista como `<item>`. | Se cumplieron todas las aserciones en las 3 variantes. | **PASÓ** | 0.005 s |
| PU-03 | `test_respuesta_xml_con_parametro_formato` | Permitir elegir XML por parámetro de consulta. | `GET /?formato=xml`. | Respuesta `application/xml`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-04 | `test_dict_a_xml_sanea_etiquetas_invalidas` | Generar XML válido aunque las claves no sean nombres XML válidos. | Claves `1campo`, `con espacio`, `_id`. | Etiquetas `<_1campo>` y `<con_espacio>`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-05 | `test_xml_a_dict_ida_y_vuelta` | Comprobar que la conversión dict→XML→dict no pierde datos. | `checkout_request` con `id_locacion` y una lista de líneas. | El dict reconstruido es idéntico al original. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-06 | `test_xml_a_dict_un_solo_item_sigue_siendo_lista` | Evitar que una lista de un solo elemento se lea como objeto. | `<lineas>` con un único `<item>`. | `lineas` es una lista de un elemento. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-07 | `test_xml_mal_formado_da_400` | Rechazar de forma controlada un XML mal formado. | `<r><sin_cerrar></r>`. | `ErrorApi` 400 con código `xml_mal_formado`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-08 | `test_xsd_acepta_documento_valido` | Validar un ASN correcto contra su XSD. | `asn_request` con folio, proveedor y un `item_carga` completo. | Validación sin excepción. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-09 | `test_xsd_rechaza_tipos_y_campos_faltantes` | Rechazar XML que no cumple el contrato (tipo incorrecto y campo obligatorio faltante). | `checkout_request` sin `id_locacion` y con `id_sku=abc`. | 400 `xml_no_cumple_contrato` con detalles del XSD. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-10 | `test_todos_los_xsd_compilan` | Asegurar que todos los esquemas XSD del contrato son válidos. | Todos los archivos `contracts/xsd/*.xsd`. | Al menos 9 esquemas y todos compilan. | Se cumplieron todas las aserciones. | **PASÓ** | 0.056 s |
| PU-11 | `test_leer_cuerpo_json_y_xml` | Leer el cuerpo de la petición en JSON o XML con la misma función. | POST JSON `{"a":1}` y POST XML `login_request`. | Ambos se convierten al mismo tipo de dict. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-12 | `test_leer_cuerpo_json_invalido_y_vacio` | Manejar JSON inválido y cuerpo vacío obligatorio. | `{malo` con `application/json`; POST sin cuerpo con `requerido=True`. | `json_mal_formado` y 400 respectivamente. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-13 | `test_error_response_cumple_su_xsd` | Comprobar que el error XML estándar cumple `error_response.xsd` y propaga el correlation id. | Error 404 con `Accept: application/xml` y `X-Correlation-Id: abc123`. | HTTP 404, XML válido contra el XSD, `<correlation_id>abc123</correlation_id>`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-14 | `test_error_response_json_estructura` | Verificar la estructura estándar del error JSON. | Error 409 `conflicto`. | Campos exactos `error`, `mensaje`, `status`, `correlation_id`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-15 | `test_paginacion_por_defecto_y_limites` | Validar los parámetros de paginación y sus límites. | Sin parámetros; `pagina=3&por_pagina=500`; `pagina=0`. | (1,20,0); `por_pagina` topado a 100; error en página 0; metadatos con `total_paginas=5`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |

## Unitaria: `tests/unit/test_mapa_tiendas.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-16 | `test_coordenadas_vacias_son_opcionales` | Permitir locaciones sin coordenadas. | Dict vacío y latitud/longitud en blanco. | `(None, None)`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-17 | `test_coordenadas_validas_se_convierten_a_numero` | Convertir coordenadas de texto a número. | `latitud=25.6575`, `longitud=-100.402`. | `(25.6575, -100.402)`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-18 | `test_coordenadas_invalidas_se_rechazan` | Validar coordenadas incompletas, no numéricas o fuera de rango. | Solo latitud, solo longitud, `norte`, latitud 95, longitud -181. | `ValueError` con el mensaje correspondiente. | Se cumplieron todas las aserciones en las 5 variantes. | **PASÓ** | 0.003 s |
| PU-19 | `test_vista_del_mapa_registrada_y_sin_acceso_para_proveedor` | Verificar permisos de la vista del mapa por rol. | Matriz `VISTAS_POR_ROL`. | Proveedor sin acceso; los otros 6 roles con acceso. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_openapi_microservicios.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-20 | `test_rutas_versionadas_y_health` | Verificar que cada microservicio expone `/health` y rutas versionadas. | `GET /api/v1/openapi.json` y `/api/v1/docs` de cada servicio. | Swagger responde 200; todas las rutas de negocio empiezan con `/api/v1/`. | Se cumplieron todas las aserciones en las 8 variantes. | **PASÓ** | 0.055 s |
| PU-21 | `test_endpoints_protegidos_declaran_jwt_y_errores` | Comprobar que la documentación declara seguridad JWT y errores. | Todas las operaciones del OpenAPI de cada servicio. | Cada operación tiene resumen y 500; las protegidas documentan 401. | Se cumplieron todas las aserciones en las 8 variantes. | **PASÓ** | 0.001 s |
| PU-22 | `test_cuerpos_con_ejemplo_json_y_xml` | Comprobar ejemplos de request en ambos formatos. | Operaciones con `requestBody`. | Ejemplo JSON y ejemplo XML (con `<?xml`). | Se cumplieron todas las aserciones en las 8 variantes. | **PASÓ** | 0.000 s |
| PU-23 | `test_respuestas_en_json_y_xml` | Comprobar que cada respuesta documentada ofrece JSON y XML. | Todas las respuestas del OpenAPI. | `application/json` y `application/xml` en cada respuesta. | Se cumplieron todas las aserciones en las 8 variantes. | **PASÓ** | 0.000 s |
| PU-24 | `test_usa_metodos_http_variados` | Verificar el uso de los métodos HTTP apropiados. | Reglas de URL de los 8 servicios. | Aparecen GET, POST, PUT, PATCH y DELETE. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_redis_cache_service.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-25 | `test_sesion_con_ttl_e_indice_por_usuario` | Gestionar sesiones en Redis con TTL e índice por usuario. | Sesión `s1` del usuario `u1` con TTL de 120 s. | Sesión activa, TTL ≤ 120, listada en `user:sessions:u1`; inactiva tras eliminarla. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-26 | `test_denylist_jwt` | Revocar un JWT por su `jti`. | `revocar_jwt('j1', 300)`. | `jwt:denylist:j1` existe con TTL; contador de revocados = 1. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-27 | `test_cache_aside_e_invalidacion_por_patron` | Probar el patrón Cache-Aside y la invalidación por patrón con SCAN. | 3 claves de caché; `invalidar_patron('catalog:products:*')`. | Se eliminan 2 claves; la de locaciones se conserva. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-28 | `test_contadores_de_operacion` | Contar operaciones de forma atómica con INCRBY. | Dos incrementos de `inventory/reserve_success`. | Contador del día = 2. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-29 | `test_temporal_se_consume_una_sola_vez` | Guardar datos temporales con TTL y consumirlos una sola vez. | Carrito `c1` con TTL de 900 s. | TTL ≤ 900; el primer consumo devuelve el carrito y el segundo `None`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-30 | `test_bloqueo_distribuido_exclusivo` | Garantizar exclusión mutua con bloqueo distribuido (SET NX EX + Lua). | Bloqueo `inv:loc:1`; segundo intento; liberar con token ajeno y con el propio. | Segundo intento falla; el token ajeno no libera; el propio sí. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-31 | `test_rate_limit_ventana_fija` | Limitar la tasa de peticiones con ventana fija. | 4 peticiones con límite 3 en 60 s. | Permitidas, permitidas, permitidas, rechazada; restante 0 en la tercera. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-32 | `test_sin_redis_no_reintenta_en_cada_llamada` | Degradar de forma controlada si Redis no responde. | Redis apuntando a un puerto cerrado; 20 llamadas seguidas. | Sin excepciones y sin pagar el timeout en cada llamada (< 0.1 s en total). | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |

## Unitaria: `tests/unit/test_reglas_negocio.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-33 | `test_fefo_consume_primero_el_lote_mas_proximo_a_caducar` | Aplicar FEFO: primero el lote que caduca antes. | Lote que vence hoy (3 u.) y lote que vence mañana (10 u.); pedido de 5. | Se toman 3 del primero y 2 del segundo. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-34 | `test_fefo_respeta_lo_ya_reservado` | No consumir cantidades ya reservadas. | Lote A con 5 disponibles y 4 reservadas, lote B con 5; pedido de 3. | 1 de A y 2 de B. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-35 | `test_fefo_stock_insuficiente_cubre_lo_posible` | Repartir solo lo existente cuando no alcanza el stock. | Un lote de 2 u.; pedido de 5. | Total consumido = 2. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-36 | `test_fefo_omite_lotes_sin_disponible` | Omitir lotes sin disponibilidad real. | Lote totalmente reservado y lote en 0. | Ningún consumo. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-37 | `test_medias_moviles` | Calcular media móvil simple y ponderada. | `[1,2,3,4]` ventana 2; `[2,4,6]` ventana 3 ponderada. | 3.5 y 28/6. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-38 | `test_suavizacion_exponencial_converge_al_ultimo_valor_con_alpha_alto` | Validar la suavización exponencial. | `[10,10,10,50]` con α=0.99; serie vacía. | ≈49.6 y 0.0. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-39 | `test_metodo_desconocido_lanza_error` | Rechazar métodos de pronóstico inexistentes. | Método `MAGIA`. | `ValueError`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-40 | `test_metricas_de_error` | Calcular MAE y WMAPE del pronóstico. | Real `[10,20]`, pronóstico `[12,18]`. | MAE 2, n 2, WMAPE 13.33 %, suma_real 30. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-41 | `test_pronosticar_serie_horizonte_y_no_negativo` | Pronosticar con el horizonte pedido y sin valores negativos. | Serie de 60 días, suavización exponencial, horizonte 7. | 7 valores ≥ 0; métricas sobre los días de backtest. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |

## Unitaria: `tests/unit/test_seguridad_jwt.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-42 | `test_sin_token_401` | Rechazar peticiones protegidas sin token. | `GET /libre` sin `Authorization`. | 401 `token_requerido`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-43 | `test_token_manipulado_401` | Rechazar tokens con firma alterada. | JWT con los últimos 3 caracteres cambiados. | 401 `token_invalido`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.007 s |
| PU-44 | `test_token_expirado_401` | Rechazar tokens expirados. | JWT con `exp=1`. | 401. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-45 | `test_token_valido_200` | Aceptar un token válido con sesión activa. | JWT firmado y sesión en Redis. | 200 con el email del usuario y cabecera `X-Correlation-Id`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.007 s |
| PU-46 | `test_token_revocado_en_denylist_401` | Rechazar tokens revocados en Redis. | JWT cuyo `jti` está en la denylist. | 401 `token_revocado`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-47 | `test_sesion_inexistente_en_redis_401` | Exigir sesión viva en Redis. | JWT válido sin sesión registrada. | 401 `sesion_inexistente`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-48 | `test_cerrar_sesiones_usuario_invalida_tokens` | Cerrar todas las sesiones de un usuario. | `cerrar_sesiones_usuario('u-1')`. | 1 sesión cerrada, `jti` revocado y siguiente petición 401. | Se cumplieron todas las aserciones. | **PASÓ** | 0.008 s |
| PU-49 | `test_rol_no_permitido_403` | Aplicar RBAC: rol sin permiso. | Rol `store_manager` en endpoint solo para `auditor`. | 403 con los roles permitidos en el detalle. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-50 | `test_rol_permitido_y_admin_200` | Aplicar RBAC: rol permitido y administrador. | Roles `auditor` y `admin`. | 200. | Se cumplieron todas las aserciones en las 2 variantes. | **PASÓ** | 0.016 s |
| PU-51 | `test_rate_limit_429_con_cabeceras` | Limitar tasa por endpoint con cabeceras RFC. | 3 peticiones con límite 2/60 s. | `X-RateLimit-Remaining: 0`, luego 429 `limite_excedido` con `Retry-After`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.010 s |
| PU-52 | `test_errores_http_estandarizados` | Estandarizar 404 y 405. | Ruta inexistente con `Accept: application/xml`; POST a ruta GET. | 404 con `<error_response>` y 405. | Se cumplieron todas las aserciones. | **PASÓ** | 0.007 s |
| PU-53 | `test_error_no_controlado_no_expone_traza` | No filtrar información interna en errores 500. | Endpoint que lanza `RuntimeError('detalle interno secreto')`. | 500 `error_interno` sin el texto del error. | Se cumplieron todas las aserciones. | **PASÓ** | 0.009 s |
| PU-54 | `test_health_reporta_dependencias` | Reportar el estado de dependencias en `/health`. | `GET /health` con Redis disponible. | 200 con `dependencies: {redis: true}`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |

## Integración: `tests/integration/test_mapa_tiendas.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PI-55 | `test_metricas_por_locacion_traen_coordenadas_y_cuadran_con_postgres` | Verificar que las métricas del mapa cuadran con PostgreSQL. | Métricas de 30 días de la tienda 3 contra `operacion.v_inventario_lote`. | Coordenadas válidas; valor y número de lotes iguales a la consulta SQL. | Se cumplieron todas las aserciones. | **PASÓ** | 0.294 s |
| PI-56 | `test_metricas_por_locacion_solo_incluye_activas` | Mostrar solo locaciones activas. | Métricas de 7 días. | Tantas filas como locaciones activas en PostgreSQL. | Se cumplieron todas las aserciones. | **PASÓ** | 0.061 s |

## Integración: `tests/integration/test_procesos_negocio.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PI-57 | `test_crud_de_producto_con_xml_y_cache` | Recorrer el CRUD de producto en svc-catalog con XML, reglas de negocio y RBAC. | POST XML (buyer), GET, PATCH, PUT incompleto, PATCH precio < costo, DELETE (buyer y admin), GET de id inexistente. | 201 XML, 200, 200, 400, 409, 403, 200 con `activo=false` en PostgreSQL, 404. | Se cumplieron todas las aserciones. | **PASÓ** | 0.562 s |
| PI-58 | `test_listado_paginado_usa_cache_redis` | Comprobar Cache-Aside en el listado paginado. | Dos `GET /api/v1/catalog/products` idénticos. | Primera desde `postgres`, segunda desde `redis_cache`; metadatos de paginación. | Se cumplieron todas las aserciones. | **PASÓ** | 0.018 s |
| PI-59 | `test_saga_de_venta_descuenta_inventario_fefo` | Ejecutar la saga de venta entre svc-commercial y svc-inventory. | Lote nuevo de 50 u.; `POST /commercial/checkout` de 2 u. del SKU 1 en la tienda 3. | Cola FEFO ordenada; 201; disponible total baja exactamente 2; la venta aparece en el historial. | Se cumplieron todas las aserciones. | **PASÓ** | 0.147 s |
| PI-60 | `test_saga_rechaza_stock_insuficiente_sin_dejar_reservas` | Compensar la saga cuando no hay stock. | Checkout de 10 000 000 u. | 409 `venta_rechazada` y la cantidad reservada queda igual que antes. | Se cumplieron todas las aserciones. | **PASÓ** | 0.043 s |
| PI-61 | `test_checkout_valida_entrada` | Validar la entrada del checkout en JSON y XML. | Cantidad -1 (JSON); `checkout_request` sin líneas (XML). | 400 y 400 `xml_no_cumple_contrato`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.026 s |
| PI-62 | `test_reserva_y_compensacion_por_saga_id` | Reservar FEFO y cancelar la reserva por `saga_id`. | `reserve-fefo` de todo el disponible; `cancel-reservation` dos veces. | Reserva sube y se guarda en Redis; al cancelar vuelve al valor inicial; segunda cancelación 404. | Se cumplieron todas las aserciones. | **PASÓ** | 0.157 s |
| PI-63 | `test_merma_descuenta_y_valida_causa` | Registrar merma con validación de causa y cantidad. | Merma de 1 u. `DANO`; causa `INVENTADA`; 999 999 u. | 201 y disponible -1; 400; 409. | Se cumplieron todas las aserciones. | **PASÓ** | 0.070 s |
| PI-64 | `test_carrito_temporal_con_ttl` | Gestionar el carrito POS temporal en Redis. | PUT, GET, DELETE y GET del carrito. | 200, TTL ≤ 900, 200, 404. | Se cumplieron todas las aserciones. | **PASÓ** | 0.047 s |
| PI-65 | `test_ciclo_de_vida_asn_en_mongodb` | Recorrer el ciclo de vida de un ASN en MongoDB. | POST XML con 2 partidas, POST duplicado, GET, transición inválida, transición válida, inspección, filtro por SKU, folio inexistente. | 201, 409, estado `ANUNCIADO` con 2 partidas, 409, 200, 201 (`$push`), aparece en el filtro anidado, 404. | Se cumplieron todas las aserciones. | **PASÓ** | 0.123 s |
| PI-66 | `test_asn_valida_contra_postgres` | Validar el ASN contra el catálogo de PostgreSQL. | ASN JSON con SKU 99999999. | 409 con `skus_inexistentes: [99999999]`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.017 s |
| PI-67 | `test_escaneo_y_atencion_de_alertas` | Escanear riesgo de caducidad y atender alertas. | Escaneo de 30 días en la tienda 3; resolver una alerta; id inválido; criticidad inválida. | 200; 200 al resolver; 400; 400. | Se cumplieron todas las aserciones. | **PASÓ** | 0.206 s |
| PI-68 | `test_planeacion_ordenes_y_contexto_hibrido` | Consultar planeación y el contexto PostgreSQL + MongoDB. | Listado de órdenes, aprobar orden inexistente, contexto del SKU 1, pronóstico con método inexistente. | 200 paginado, 404, contexto con `producto_postgres` y `contexto_mongo`, 400. | Se cumplieron todas las aserciones. | **PASÓ** | 0.055 s |
| PI-69 | `test_auditoria_registra_con_identidad_del_jwt` | Registrar en la bitácora con la identidad del JWT, no con la de cabeceras. | POST de auditoría como auditor con `X-User-Email: suplantado@x.mx`. | 201 y en PostgreSQL `usuario_email = auditor@freshtrack.mx`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.034 s |
| PI-70 | `test_trazabilidad_de_lote` | Obtener la trazabilidad de un lote. | `GET /audit/traceability/{id_lote}` de un lote recién recibido. | 200 y primer movimiento del kardex `RECEPCION`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.042 s |
| PI-71 | `test_health_de_los_ocho_servicios` | Verificar `/health` de los 8 microservicios. | `GET /health` en cada servicio. | 200 o 503 con el estado de su base de datos principal. | Se cumplieron todas las aserciones. | **PASÓ** | 0.049 s |

## Integración: `tests/integration/test_seguridad_distribuida.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PI-72 | `test_login_json_entrega_jwt_y_crea_sesion_en_redis` | Iniciar sesión, emitir JWT y registrar la sesión. | Login JSON del usuario de almacén. | JWT con rol e `iss`; sesión en Redis con TTL; fila no revocada en `operacion.sesion_usuario`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.042 s |
| PI-73 | `test_login_xml_con_respuesta_xml` | Iniciar sesión en XML y recibir XML. | `login_request` XML con `Accept: application/xml`. | 200 `application/xml` con `<auth_response>` y `<token>`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.050 s |
| PI-74 | `test_login_errores_controlados` | Manejar errores de login de forma controlada. | Contraseña incorrecta, falta password, XML que no cumple el XSD, usuario inactivo. | 401 `credenciales_invalidas`, 400 con faltantes, 400 `xml_no_cumple_contrato`, 401. | Se cumplieron todas las aserciones. | **PASÓ** | 0.098 s |
| PI-75 | `test_rate_limit_de_login` | Limitar intentos de login (fuerza bruta). | 11 intentos con credenciales inválidas. | 10 × 401 y el 11.º 429. | Se cumplieron todas las aserciones. | **PASÓ** | 0.171 s |
| PI-76 | `test_token_de_auth_funciona_en_otros_servicios` | Usar el token de svc-auth en otros servicios. | Token de almacén en svc-inventory, svc-commercial y `/auth/verify`. | 200, 200 y `valido: true`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.077 s |
| PI-77 | `test_rbac_entre_servicios` | Aplicar RBAC entre servicios. | Auditor lee bitácora, crea producto, vende; gerente lee bitácora; admin lista usuarios. | 200, 403 `acceso_denegado`, 403, 403, 200. | Se cumplieron todas las aserciones. | **PASÓ** | 0.060 s |
| PI-78 | `test_tokens_invalidos_y_expirados` | Rechazar tokens manipulados, expirados, de otro emisor o ausentes. | 4 variantes contra `GET /catalog/suppliers`. | 401 en los 4 casos. | Se cumplieron todas las aserciones. | **PASÓ** | 0.014 s |
| PI-79 | `test_logout_revoca_en_todos_los_servicios` | Revocar el token en todos los servicios al cerrar sesión. | Login de gerente, petición OK, `POST /auth/logout`, peticiones a 3 servicios. | Denylist en Redis, sesión inactiva, `revocado=true` en PostgreSQL y 401 `token_revocado` en los 3. | Se cumplieron todas las aserciones. | **PASÓ** | 0.085 s |
| PI-80 | `test_admin_cierra_sesiones_de_otro_usuario` | Cierre forzado de sesiones por el administrador. | Login de planner; admin lista y elimina sus sesiones. | ≥ 1 sesión activa, ≥ 1 cerrada y el token del planner da 401 en svc-planning. | Se cumplieron todas las aserciones. | **PASÓ** | 0.109 s |
| PI-81 | `test_ids_invalidos_dan_400_no_500` | Validar identificadores de ruta. | UUID inválido en sesiones y trazabilidad. | 400 en ambos (no 500). | Se cumplieron todas las aserciones. | **PASÓ** | 0.025 s |

## Evidencia de ejecución

- Salida completa de pytest: [`salida_pytest.txt`](salida_pytest.txt)
- Resultado en formato JUnit (lo leen GitHub Actions y otras herramientas de CI): [`resultado_pytest.xml`](resultado_pytest.xml)

Fragmento final de la salida:

```text
======================= 116 passed, 41 warnings in 3.70s =======================
```

Para reproducirlo:

```bash
docker compose up -d --wait
python scripts/generar_reporte_pruebas.py
```
