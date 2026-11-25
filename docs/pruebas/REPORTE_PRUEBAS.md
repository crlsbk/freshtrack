# Reporte de pruebas unitarias y de integración

Generado automáticamente por `scripts/generar_reporte_pruebas.py` el 2026-11-24 23:43. El resultado obtenido y el estado de cada caso salen de la ejecución real de pytest, no se escriben a mano.

## Entorno de ejecución

- **Python:** 3.14.10 (Linux)
- **PostgreSQL:** PostgreSQL 17.11 on x86_64-pc-linux-musl
- **Redis:** real (contenedor)
- **MongoDB:** real (contenedor)
- **Comando:** `python -m pytest tests -v --junitxml=docs/pruebas/resultado_pytest.xml`

## Resumen

| Tipo | Ejecutadas | Pasaron | Fallaron | Omitidas |
|---|---:|---:|---:|---:|
| Unitaria | 380 | 380 | 0 | 0 |
| Integración | 27 | 27 | 0 | 0 |
| **Total** | **407** | **407** | **0** | **0** |

Tiempo total: 3.79 s. Las pruebas de integración corren contra el PostgreSQL real con el seed de FreshTrack y levantan los 8 microservicios en el mismo proceso, compartiendo Redis y MongoDB igual que en docker compose.

## Unitaria: `tests/unit/test_app_movil.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-01 | `test_tipo_real_por_magic_bytes` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-02 | `test_url_firmada_v4` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-03 | `test_url_firmada_usa_endpoint_publico` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-04 | `test_conteo_ok_pasa_idempotency_key` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.009 s |
| PU-05 | `test_conteo_otra_sucursal_403` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-06 | `test_conteo_sin_lineas_400` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-07 | `test_conteo_cantidad_negativa_400` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-08 | `test_conteo_xml_valida_xsd` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.011 s |
| PU-09 | `test_conteo_comprador_403` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-10 | `test_solicitar_transferencia_201` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-11 | `test_solicitar_transferencia_regla_409` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.007 s |
| PU-12 | `test_solicitar_transferencia_desde_otra_sucursal_403` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-13 | `test_subir_evidencia_jpeg` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-14 | `test_evidencia_rechaza_archivo_que_no_es_imagen` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-15 | `test_evidencia_demasiado_grande_413` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-16 | `test_evidencia_bucket_caido_503` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-17 | `test_listar_y_url_evidencia` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-18 | `test_url_evidencia_de_otra_sucursal_403` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-19 | `test_foto_de_6mb_cabe_bajo_el_limite_global` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.021 s |
| PU-20 | `test_cuerpo_excesivo_responde_413_en_espanol` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.015 s |

## Unitaria: `tests/unit/test_auth_refresh.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-21 | `test_refresh_con_refresh_token_en_el_cuerpo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-22 | `test_refresh_en_xml_valida_contrato` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.008 s |
| PU-23 | `test_refresh_compatible_con_bearer_vigente` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-24 | `test_refresh_sin_credenciales_o_rechazado_401` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |

## Unitaria: `tests/unit/test_contratos_json_xml.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-25 | `test_respuesta_json_por_omision` | Verificar que sin cabecera Accept la respuesta sea JSON. | `render_response({'a': 1}, status=201)` sin `Accept`. | HTTP 201, `application/json`, cuerpo `{"a": 1}`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-26 | `test_respuesta_xml_con_accept` | Verificar la negociación de contenido hacia XML. | `Accept: application/xml`, `text/xml` y `application/xml;q=0.9`; dict con objeto anidado y lista. | `application/xml` con declaración UTF-8; objeto anidado como elementos y lista como `<item>`. | Se cumplieron todas las aserciones en las 3 variantes. | **PASÓ** | 0.003 s |
| PU-27 | `test_respuesta_xml_con_parametro_formato` | Permitir elegir XML por parámetro de consulta. | `GET /?formato=xml`. | Respuesta `application/xml`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-28 | `test_dict_a_xml_sanea_etiquetas_invalidas` | Generar XML válido aunque las claves no sean nombres XML válidos. | Claves `1campo`, `con espacio`, `_id`. | Etiquetas `<_1campo>` y `<con_espacio>`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-29 | `test_xml_a_dict_ida_y_vuelta` | Comprobar que la conversión dict→XML→dict no pierde datos. | `checkout_request` con `id_locacion` y una lista de líneas. | El dict reconstruido es idéntico al original. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-30 | `test_xml_a_dict_un_solo_item_sigue_siendo_lista` | Evitar que una lista de un solo elemento se lea como objeto. | `<lineas>` con un único `<item>`. | `lineas` es una lista de un elemento. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-31 | `test_xml_mal_formado_da_400` | Rechazar de forma controlada un XML mal formado. | `<r><sin_cerrar></r>`. | `ErrorApi` 400 con código `xml_mal_formado`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-32 | `test_xsd_acepta_documento_valido` | Validar un ASN correcto contra su XSD. | `asn_request` con folio, proveedor y un `item_carga` completo. | Validación sin excepción. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-33 | `test_xsd_rechaza_tipos_y_campos_faltantes` | Rechazar XML que no cumple el contrato (tipo incorrecto y campo obligatorio faltante). | `checkout_request` sin `id_locacion` y con `id_sku=abc`. | 400 `xml_no_cumple_contrato` con detalles del XSD. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-34 | `test_todos_los_xsd_compilan` | Asegurar que todos los esquemas XSD del contrato son válidos. | Todos los archivos `contracts/xsd/*.xsd`. | Al menos 9 esquemas y todos compilan. | Se cumplieron todas las aserciones. | **PASÓ** | 0.221 s |
| PU-35 | `test_leer_cuerpo_json_y_xml` | Leer el cuerpo de la petición en JSON o XML con la misma función. | POST JSON `{"a":1}` y POST XML `login_request`. | Ambos se convierten al mismo tipo de dict. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-36 | `test_leer_cuerpo_json_invalido_y_vacio` | Manejar JSON inválido y cuerpo vacío obligatorio. | `{malo` con `application/json`; POST sin cuerpo con `requerido=True`. | `json_mal_formado` y 400 respectivamente. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-37 | `test_error_response_cumple_su_xsd` | Comprobar que el error XML estándar cumple `error_response.xsd` y propaga el correlation id. | Error 404 con `Accept: application/xml` y `X-Correlation-Id: abc123`. | HTTP 404, XML válido contra el XSD, `<correlation_id>abc123</correlation_id>`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-38 | `test_error_response_json_estructura` | Verificar la estructura estándar del error JSON. | Error 409 `conflicto`. | Campos exactos `error`, `mensaje`, `status`, `correlation_id`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-39 | `test_paginacion_por_defecto_y_limites` | Validar los parámetros de paginación y sus límites. | Sin parámetros; `pagina=3&por_pagina=500`; `pagina=0`. | (1,20,0); `por_pagina` topado a 100; error en página 0; metadatos con `total_paginas=5`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |

## Unitaria: `tests/unit/test_contratos_respuesta_xsd.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-40 | `test_cada_raiz_tiene_xsd_que_compila` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 21 variantes. | **PASÓ** | 0.237 s |
| PU-41 | `test_cada_xsd_tiene_comentario_de_endpoint` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 21 variantes. | **PASÓ** | 0.001 s |
| PU-42 | `test_hay_una_muestra_por_cada_raiz` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.009 s |
| PU-43 | `test_muestra_real_valida_contra_su_xsd` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 26 variantes. | **PASÓ** | 0.234 s |
| PU-44 | `test_valor_con_tipo_invalido_no_valida` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 10 variantes. | **PASÓ** | 0.104 s |
| PU-45 | `test_valores_vacios_y_campos_nuevos_siguen_siendo_validos` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-46 | `test_un_campo_escalar_con_hijos_no_valida` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |

## Unitaria: `tests/unit/test_csrf.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-47 | `test_inyecta_token_en_cada_form_post_y_meta` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-48 | `test_post_sin_token_o_con_token_ajeno_400` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-49 | `test_post_con_token_en_campo_o_cabecera_pasa` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-50 | `test_clientes_bearer_exentos` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-51 | `test_token_de_otra_sesion_no_sirve` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-52 | `test_logout_por_get_desde_otro_sitio_no_cierra_sesion` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.052 s |

## Unitaria: `tests/unit/test_dependencias_caidas.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-53 | `test_redis_cacheado_que_cae_devuelve_none` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-54 | `test_redis_caido_no_reintenta_en_cada_llamada` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-55 | `test_redis_sano_no_hace_ping_en_cada_llamada` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-56 | `test_mongo_cacheado_que_cae_devuelve_none` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-57 | `test_alertas_responden_503_si_mongo_cae_despues_del_arranque` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-58 | `test_postgres_caido_responde_503_no_401` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-59 | `test_token_manipulado_sigue_siendo_401` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |

## Unitaria: `tests/unit/test_dispositivos_y_merma_idempotente.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-60 | `test_registrar_dispositivo_ligado_al_usuario_del_jwt` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-61 | `test_registrar_dispositivo_existente_200` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-62 | `test_dispositivo_revocado_403` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-63 | `test_dispositivo_id_invalido_400_y_sin_token_401` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-64 | `test_dispositivo_xml_valida_xsd` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.008 s |
| PU-65 | `test_listar_dispositivos_propios_o_admin` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-66 | `test_revocar_solo_admin` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-67 | `test_texto_de_dispositivo_se_sanea` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-68 | `test_sql_13_idempotente_y_en_bootstrap` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-69 | `test_merma_pasa_idempotency_key_y_201` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-70 | `test_merma_repetida_devuelve_200_sin_volver_a_ligar` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-71 | `test_merma_envio_simultaneo_unique_devuelve_la_previa` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-72 | `test_dominio_merma_repetida_no_toca_inventario` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |

## Unitaria: `tests/unit/test_generador_perfiles.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-73 | `test_catalogo_200_skus_cumple_proporciones_y_vida_util` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-74 | `test_cuatro_perfiles_discriminan_en_pronostico_y_drift` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-75 | `test_simulacion_fefo_consume_lote_mas_viejo_y_nunca_vencido` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-76 | `test_cache_web_en_kpis_y_degradacion_sin_redis` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-77 | `test_generar_locaciones_gps_50_tiendas` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-78 | `test_modos_config_rubrica_cumple_objetivos` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-79 | `test_simulacion_fefo_acota_kardex_sin_perder_historial_ventas` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-80 | `test_benchmark_parsear_niveles_concurrencia` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.011 s |

## Unitaria: `tests/unit/test_locust_suite.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-81 | `test_clasificar` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 10 variantes. | **PASÓ** | 0.000 s |
| PU-82 | `test_timeout_es_fallo_real` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-83 | `test_percentil_rango_mas_cercano` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-84 | `test_curva_por_defecto` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-85 | `test_parsear_fases` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-86 | `test_colector_agrega_por_fase_endpoint_y_errores` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-87 | `test_sin_saturacion_cuando_escala_lineal` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-88 | `test_satura_por_throughput_plano` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-89 | `test_satura_por_latencia_o_errores` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-90 | `test_recuperacion_mide_segundos_hasta_volver_a_la_base` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-91 | `test_no_recuperado` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-92 | `test_top_lentos_ordena_por_p95_y_descarta_muestras_pequenas` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-93 | `test_importador_lee_carpeta_de_corrida` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.010 s |
| PU-94 | `test_sql_11_define_esquema_pruebas` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_mailer.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-95 | `test_sin_smtp_host_solo_registra` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-96 | `test_envia_pdf_adjunto_a_mailpit_sin_tls` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-97 | `test_smtp_externo_usa_starttls_y_login` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-98 | `test_correo_invalido_lanza_valueerror` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-99 | `test_fallo_del_servidor_lanza_errorcorreo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-100 | `test_endpoint_envia_hoja_qr_en_xml` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.010 s |
| PU-101 | `test_endpoint_rechaza_correo_invalido_por_xsd` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-102 | `test_endpoint_smtp_caido_responde_502` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-103 | `test_endpoint_rol_sin_permiso_403` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-104 | `test_puerto_587_siempre_usa_starttls_aunque_smtp_tls_sea_false` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-105 | `test_mailpit_1025_sin_tls` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_mapa_tiendas.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-106 | `test_coordenadas_vacias_son_opcionales` | Permitir locaciones sin coordenadas. | Dict vacío y latitud/longitud en blanco. | `(None, None)`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-107 | `test_coordenadas_validas_se_convierten_a_numero` | Convertir coordenadas de texto a número. | `latitud=25.6575`, `longitud=-100.402`. | `(25.6575, -100.402)`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-108 | `test_coordenadas_invalidas_se_rechazan` | Validar coordenadas incompletas, no numéricas o fuera de rango. | Solo latitud, solo longitud, `norte`, latitud 95, longitud -181. | `ValueError` con el mensaje correspondiente. | Se cumplieron todas las aserciones en las 5 variantes. | **PASÓ** | 0.000 s |
| PU-109 | `test_vista_del_mapa_registrada_y_sin_acceso_para_proveedor` | Verificar permisos de la vista del mapa por rol. | Matriz `VISTAS_POR_ROL`. | Proveedor sin acceso; los otros 6 roles con acceso. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_monitoreo.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-110 | `test_health_incluye_proceso_dependencias_latencia_y_version_json_y_xml` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-111 | `test_health_degradado_si_falla_bucket_o_mongo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-112 | `test_todos_los_microservicios_declaran_las_cuatro_dependencias` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-113 | `test_xsd_service_health_valido_y_compatible` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.009 s |
| PU-114 | `test_verificar_plataforma_consolida_degradados_caidas_errores_e_historial` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-115 | `test_panel_oculto_protegido_y_sin_enlaces_en_sitio` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.076 s |

## Unitaria: `tests/unit/test_notificaciones.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-116 | `test_filtra_por_rol_y_tienda` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-117 | `test_no_se_notifica_lo_que_hizo_uno_mismo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-118 | `test_proveedor_solo_ve_sus_ordenes` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-119 | `test_rol_sin_alertas_no_consulta_mongo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-120 | `test_orden_mas_reciente_primero` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-121 | `test_marcar_una_y_todas_y_conteo_cacheado` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-122 | `test_mongo_caido_muestra_el_resto` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-123 | `test_postgres_caido_no_rompe` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-124 | `test_redis_caido_muestra_alertas_y_no_guarda` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-125 | `test_alertas_postgres_se_incluyen` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-126 | `test_vista_lista_y_marca` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.071 s |

## Unitaria: `tests/unit/test_nuevos_motores.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-127 | `test_fefo_excluye_lotes_bloqueados_cuarentena_y_caducados` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-128 | `test_newsvendor_optimiza_costo_y_respeta_caducidad` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-129 | `test_triaje_elige_traslado_descuento_y_merma` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-130 | `test_pronostico_calcula_sesgo_y_naive` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-131 | `test_seguridad_fail_closed_sin_redis_ni_postgres` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-132 | `test_pronostico_auto_selecciona_mejor_estrategia` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-133 | `test_detectar_drift_serie_estable_vigilancia_y_anomalia` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-134 | `test_newsvendor_descuenta_traslados_entrantes` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-135 | `test_generar_pdf_orden_compra_valido_y_multipagina` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-136 | `test_object_storage_firma_y_fallback_local` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-137 | `test_rbac_comprador_y_proveedor` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-138 | `test_object_storage_gcs_put_directo_y_creacion_404` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-139 | `test_proxy_fix_y_cookie_secure_produccion` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.053 s |
| PU-140 | `test_qr_firma_hmac_y_parseo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-141 | `test_generar_pdf_hoja_asn_con_qr_vectorial` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.022 s |
| PU-142 | `test_recepcion_escaneo_validacion_tienda_e_idempotencia` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |

## Unitaria: `tests/unit/test_openapi_microservicios.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-143 | `test_rutas_versionadas_y_health` | Verificar que cada microservicio expone `/health` y rutas versionadas. | `GET /api/v1/openapi.json` y `/api/v1/docs` de cada servicio. | Swagger responde 200; todas las rutas de negocio empiezan con `/api/v1/`. | Se cumplieron todas las aserciones en las 8 variantes. | **PASÓ** | 0.061 s |
| PU-144 | `test_endpoints_protegidos_declaran_jwt_y_errores` | Comprobar que la documentación declara seguridad JWT y errores. | Todas las operaciones del OpenAPI de cada servicio. | Cada operación tiene resumen y 500; las protegidas documentan 401. | Se cumplieron todas las aserciones en las 8 variantes. | **PASÓ** | 0.001 s |
| PU-145 | `test_cuerpos_con_ejemplo_json_y_xml` | Comprobar ejemplos de request en ambos formatos. | Operaciones con `requestBody`. | Ejemplo JSON y ejemplo XML (con `<?xml`). | Se cumplieron todas las aserciones en las 8 variantes. | **PASÓ** | 0.001 s |
| PU-146 | `test_respuestas_en_json_y_xml` | Comprobar que cada respuesta documentada ofrece JSON y XML. | Todas las respuestas del OpenAPI. | `application/json` y `application/xml` en cada respuesta. | Se cumplieron todas las aserciones en las 8 variantes. | **PASÓ** | 0.000 s |
| PU-147 | `test_usa_metodos_http_variados` | Verificar el uso de los métodos HTTP apropiados. | Reglas de URL de los 8 servicios. | Aparecen GET, POST, PUT, PATCH y DELETE. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-148 | `test_importacion_de_ventas_documenta_503_por_redis` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |

## Unitaria: `tests/unit/test_optimizacion_rendimiento.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-149 | `test_vistas_sql_no_invocan_fn_clasificar_riesgo_por_fila` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-150 | `test_bloquear_lotes_vencidos_usa_throttle_redis_y_skip_locked` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-151 | `test_cache_aside_en_pronostico_alertas_y_ventas` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-152 | `test_listar_usuarios_aplica_limit_por_defecto` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-153 | `test_simulacion_fefo_marca_lotes_agotados_en_memoria` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |

## Unitaria: `tests/unit/test_optimizacion_vistas.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-154 | `test_08_conserva_columnas_y_usa_historico_materializado` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-155 | `test_08_indices_y_refresco` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-156 | `test_06_no_pisa_la_vista_materializada` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-157 | `test_con_cache_web_hit_miss_y_desactivable` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-158 | `test_con_lock_espera_al_otro_worker` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-159 | `test_decorador_invalida` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-160 | `test_contar_cacheado_ignora_paginacion` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-161 | `test_demandas_en_lote_cae_al_promedio` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-162 | `test_situaciones_en_lote_equivale_a_calculo_por_par` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_por_recibir.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-163 | `test_completo_es_recibido_aunque_haya_pasado_la_fecha` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-164 | `test_fecha_vencida_sin_completar_es_atrasado` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-165 | `test_parcial_en_camino_y_por_enviar` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-166 | `test_agrupa_por_orden_y_tienda_y_ordena_lo_urgente_primero` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-167 | `test_sin_mongo_la_vista_sigue` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-168 | `test_vista_visible_para_gerente_y_almacen_no_para_proveedor` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_proveedor_alcance.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-169 | `test_supplier_no_modifica_producto_ajeno` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 2 variantes. | **PASÓ** | 0.007 s |
| PU-170 | `test_supplier_sin_proveedor_asignado_no_opera` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-171 | `test_supplier_no_regala_su_producto_a_otro_proveedor` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-172 | `test_listado_de_supplier_filtra_por_su_proveedor` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-173 | `test_otros_roles_no_se_restringen_por_proveedor` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-174 | `test_usuario_supplier_requiere_proveedor` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_recuperacion_password.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-175 | `test_correo_desconocido_no_genera_token_ni_correo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-176 | `test_token_se_guarda_hasheado_con_ttl` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-177 | `test_restablecer_es_de_un_solo_uso_y_revoca_sesiones` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-178 | `test_politica_y_confirmacion_no_gastan_el_token` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-179 | `test_token_inventado_o_vencido` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-180 | `test_limite_por_correo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-181 | `test_sin_redis_falla_cerrado` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-182 | `test_login_muestra_enlace_de_recuperacion` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.032 s |
| PU-183 | `test_vista_responde_igual_exista_o_no_la_cuenta` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.029 s |
| PU-184 | `test_vista_exige_csrf` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.031 s |
| PU-185 | `test_vista_restablecer_flujo_completo` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.034 s |
| PU-186 | `test_vista_sin_redis_mensaje_amable` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.029 s |

## Unitaria: `tests/unit/test_redis_cache_service.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-187 | `test_sesion_con_ttl_e_indice_por_usuario` | Gestionar sesiones en Redis con TTL e índice por usuario. | Sesión `s1` del usuario `u1` con TTL de 120 s. | Sesión activa, TTL ≤ 120, listada en `user:sessions:u1`; inactiva tras eliminarla. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-188 | `test_denylist_jwt` | Revocar un JWT por su `jti`. | `revocar_jwt('j1', 300)`. | `jwt:denylist:j1` existe con TTL; contador de revocados = 1. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-189 | `test_cache_aside_e_invalidacion_por_patron` | Probar el patrón Cache-Aside y la invalidación por patrón con SCAN. | 3 claves de caché; `invalidar_patron('catalog:products:*')`. | Se eliminan 2 claves; la de locaciones se conserva. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-190 | `test_contadores_de_operacion` | Contar operaciones de forma atómica con INCRBY. | Dos incrementos de `inventory/reserve_success`. | Contador del día = 2. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-191 | `test_temporal_se_consume_una_sola_vez` | Guardar datos temporales con TTL y consumirlos una sola vez. | Carrito `c1` con TTL de 900 s. | TTL ≤ 900; el primer consumo devuelve el carrito y el segundo `None`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-192 | `test_bloqueo_distribuido_exclusivo` | Garantizar exclusión mutua con bloqueo distribuido (SET NX EX + Lua). | Bloqueo `inv:loc:1`; segundo intento; liberar con token ajeno y con el propio. | Segundo intento falla; el token ajeno no libera; el propio sí. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-193 | `test_rate_limit_ventana_fija` | Limitar la tasa de peticiones con ventana fija. | 4 peticiones con límite 3 en 60 s. | Permitidas, permitidas, permitidas, rechazada; restante 0 en la tercera. | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-194 | `test_sin_redis_no_reintenta_en_cada_llamada` | Degradar de forma controlada si Redis no responde. | Redis apuntando a un puerto cerrado; 20 llamadas seguidas. | Sin excepciones y sin pagar el timeout en cada llamada (< 0.1 s en total). | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |

## Unitaria: `tests/unit/test_reglas_negocio.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-195 | `test_fefo_consume_primero_el_lote_mas_proximo_a_caducar` | Aplicar FEFO: primero el lote que caduca antes. | Lote que vence hoy (3 u.) y lote que vence mañana (10 u.); pedido de 5. | Se toman 3 del primero y 2 del segundo. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-196 | `test_fefo_respeta_lo_ya_reservado` | No consumir cantidades ya reservadas. | Lote A con 5 disponibles y 4 reservadas, lote B con 5; pedido de 3. | 1 de A y 2 de B. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-197 | `test_fefo_stock_insuficiente_cubre_lo_posible` | Repartir solo lo existente cuando no alcanza el stock. | Un lote de 2 u.; pedido de 5. | Total consumido = 2. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-198 | `test_fefo_omite_lotes_sin_disponible` | Omitir lotes sin disponibilidad real. | Lote totalmente reservado y lote en 0. | Ningún consumo. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-199 | `test_medias_moviles` | Calcular media móvil simple y ponderada. | `[1,2,3,4]` ventana 2; `[2,4,6]` ventana 3 ponderada. | 3.5 y 28/6. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-200 | `test_suavizacion_exponencial_converge_al_ultimo_valor_con_alpha_alto` | Validar la suavización exponencial. | `[10,10,10,50]` con α=0.99; serie vacía. | ≈49.6 y 0.0. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-201 | `test_metodo_desconocido_lanza_error` | Rechazar métodos de pronóstico inexistentes. | Método `MAGIA`. | `ValueError`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-202 | `test_metricas_de_error` | Calcular MAE y WMAPE del pronóstico. | Real `[10,20]`, pronóstico `[12,18]`. | MAE 2, n 2, WMAPE 13.33 %, suma_real 30. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-203 | `test_pronosticar_serie_horizonte_y_no_negativo` | Pronosticar con el horizonte pedido y sin valores negativos. | Serie de 60 días, suavización exponencial, horizonte 7. | 7 valores ≥ 0; métricas sobre los días de backtest. | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |

## Unitaria: `tests/unit/test_sales_import.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-204 | `test_dos_tickets_importados` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.010 s |
| PU-205 | `test_reenvio_es_duplicado` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.007 s |
| PU-206 | `test_xsd_violado_400` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-207 | `test_rol_no_permitido_403` | Aplicar RBAC: rol sin permiso. | Rol `store_manager` en endpoint solo para `auditor`. | 403 con los roles permitidos en el detalle. | Se cumplieron todas las aserciones en las 2 variantes. | **PASÓ** | 0.008 s |
| PU-208 | `test_error_en_un_ticket_no_detiene_los_demas` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-209 | `test_sin_redis_503` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-210 | `test_error_de_conexion_redis_503` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-211 | `test_excepcion_inesperada_libera_clave_y_permite_reintento` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.008 s |
| PU-212 | `test_folio_duplicado_en_el_mismo_lote` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |

## Unitaria: `tests/unit/test_seguridad_endurecimiento.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-213 | `test_jwt_valido_pasa` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-214 | `test_jwt_sin_claims_obligatorios_o_emisor_ajeno` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 4 variantes. | **PASÓ** | 0.004 s |
| PU-215 | `test_clave_jwt_no_es_la_de_la_cookie` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-216 | `test_sesion_web_sin_jti_o_revocada_no_vale` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-217 | `test_revocar_sesiones_usuario_llega_a_redis` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.002 s |
| PU-218 | `test_repo_usuarios_revoca_al_desactivar_y_al_cambiar_rol` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-219 | `test_destino_login` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 7 variantes. | **PASÓ** | 0.001 s |
| PU-220 | `test_ruta_log_oculta_tokens` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |
| PU-221 | `test_verify_rechaza_token_en_query` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.003 s |
| PU-222 | `test_sql_error_no_expone_detalles_internos` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-223 | `test_audit_log_no_permite_acciones_del_sistema` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.004 s |
| PU-224 | `test_kpis_ventana_rechaza_authorization_falso` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.027 s |
| PU-225 | `test_kpis_ventana_acota_dias` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.028 s |
| PU-226 | `test_triaje_accion_lote_respeta_rol_y_sucursal` | (sin descripción) | — | — | Se cumplieron todas las aserciones en las 6 variantes. | **PASÓ** | 0.180 s |

## Unitaria: `tests/unit/test_seguridad_jwt.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-227 | `test_sin_token_401` | Rechazar peticiones protegidas sin token. | `GET /libre` sin `Authorization`. | 401 `token_requerido`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-228 | `test_token_manipulado_401` | Rechazar tokens con firma alterada. | JWT con los últimos 3 caracteres cambiados. | 401 `token_invalido`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.010 s |
| PU-229 | `test_token_expirado_401` | Rechazar tokens expirados. | JWT con `exp=1`. | 401. | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-230 | `test_token_valido_200` | Aceptar un token válido con sesión activa. | JWT firmado y sesión en Redis. | 200 con el email del usuario y cabecera `X-Correlation-Id`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-231 | `test_token_revocado_en_denylist_401` | Rechazar tokens revocados en Redis. | JWT cuyo `jti` está en la denylist. | 401 `token_revocado`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-232 | `test_sesion_inexistente_en_redis_401` | Exigir sesión viva en Redis. | JWT válido sin sesión registrada. | 401 `sesion_inexistente`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-233 | `test_cerrar_sesiones_usuario_invalida_tokens` | Cerrar todas las sesiones de un usuario. | `cerrar_sesiones_usuario('u-1')`. | 1 sesión cerrada, `jti` revocado y siguiente petición 401. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-234 | `test_rol_permitido_y_admin_200` | Aplicar RBAC: rol permitido y administrador. | Roles `auditor` y `admin`. | 200. | Se cumplieron todas las aserciones en las 2 variantes. | **PASÓ** | 0.012 s |
| PU-235 | `test_rate_limit_429_con_cabeceras` | Limitar tasa por endpoint con cabeceras RFC. | 3 peticiones con límite 2/60 s. | `X-RateLimit-Remaining: 0`, luego 429 `limite_excedido` con `Retry-After`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.007 s |
| PU-236 | `test_errores_http_estandarizados` | Estandarizar 404 y 405. | Ruta inexistente con `Accept: application/xml`; POST a ruta GET. | 404 con `<error_response>` y 405. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-237 | `test_error_no_controlado_no_expone_traza` | No filtrar información interna en errores 500. | Endpoint que lanza `RuntimeError('detalle interno secreto')`. | 500 `error_interno` sin el texto del error. | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-238 | `test_health_reporta_dependencias` | Reportar el estado de dependencias en `/health`. | `GET /health` con Redis disponible. | 200 con `dependencies: {redis: true}`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.005 s |
| PU-239 | `test_health_tiene_alias_detras_del_gateway` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |

## Unitaria: `tests/unit/test_ultimo_error.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PU-240 | `test_error_no_controlado_queda_registrado_sin_detalles_internos` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-241 | `test_error_response_5xx_si_y_4xx_no` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-242 | `test_lista_acotada_y_repeticiones` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-243 | `test_sin_redis_sin_datos` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.000 s |
| PU-244 | `test_health_expone_last_error_en_json_y_xml_valido` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.015 s |
| PU-245 | `test_monitor_registra_health_fallido_y_lo_muestra` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PU-246 | `test_monitor_sin_redis_muestra_sin_datos` | (sin descripción) | — | — | Se cumplieron todas las aserciones. | **PASÓ** | 0.001 s |

## Integración: `tests/integration/test_mapa_tiendas.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PI-247 | `test_metricas_por_locacion_traen_coordenadas_y_cuadran_con_postgres` | Verificar que las métricas del mapa cuadran con PostgreSQL. | Métricas de 30 días de la tienda 3 contra `operacion.v_inventario_lote`. | Coordenadas válidas; valor y número de lotes iguales a la consulta SQL. | Se cumplieron todas las aserciones. | **PASÓ** | 0.236 s |
| PI-248 | `test_metricas_por_locacion_solo_incluye_activas` | Mostrar solo locaciones activas. | Métricas de 7 días. | Tantas filas como locaciones activas en PostgreSQL. | Se cumplieron todas las aserciones. | **PASÓ** | 0.045 s |

## Integración: `tests/integration/test_procesos_negocio.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PI-249 | `test_crud_de_producto_con_xml_y_cache` | Recorrer el CRUD de producto en svc-catalog con XML, reglas de negocio y RBAC. | POST XML (buyer), GET, PATCH, PUT incompleto, PATCH precio < costo, DELETE (buyer y admin), GET de id inexistente. | 201 XML, 200, 200, 400, 409, 403, 200 con `activo=false` en PostgreSQL, 404. | Se cumplieron todas las aserciones. | **PASÓ** | 0.430 s |
| PI-250 | `test_listado_paginado_usa_cache_redis` | Comprobar Cache-Aside en el listado paginado. | Dos `GET /api/v1/catalog/products` idénticos. | Primera desde `postgres`, segunda desde `redis_cache`; metadatos de paginación. | Se cumplieron todas las aserciones. | **PASÓ** | 0.013 s |
| PI-251 | `test_saga_de_venta_descuenta_inventario_fefo` | Ejecutar la saga de venta entre svc-commercial y svc-inventory. | Lote nuevo de 50 u.; `POST /commercial/checkout` de 2 u. del SKU 1 en la tienda 3. | Cola FEFO ordenada; 201; disponible total baja exactamente 2; la venta aparece en el historial. | Se cumplieron todas las aserciones. | **PASÓ** | 0.107 s |
| PI-252 | `test_saga_rechaza_stock_insuficiente_sin_dejar_reservas` | Compensar la saga cuando no hay stock. | Checkout de 10 000 000 u. | 409 `venta_rechazada` y la cantidad reservada queda igual que antes. | Se cumplieron todas las aserciones. | **PASÓ** | 0.026 s |
| PI-253 | `test_checkout_valida_entrada` | Validar la entrada del checkout en JSON y XML. | Cantidad -1 (JSON); `checkout_request` sin líneas (XML). | 400 y 400 `xml_no_cumple_contrato`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.017 s |
| PI-254 | `test_reserva_y_compensacion_por_saga_id` | Reservar FEFO y cancelar la reserva por `saga_id`. | `reserve-fefo` de todo el disponible; `cancel-reservation` dos veces. | Reserva sube y se guarda en Redis; al cancelar vuelve al valor inicial; segunda cancelación 404. | Se cumplieron todas las aserciones. | **PASÓ** | 0.082 s |
| PI-255 | `test_merma_descuenta_y_valida_causa` | Registrar merma con validación de causa y cantidad. | Merma de 1 u. `DANO`; causa `INVENTADA`; 999 999 u. | 201 y disponible -1; 400; 409. | Se cumplieron todas las aserciones. | **PASÓ** | 0.039 s |
| PI-256 | `test_carrito_temporal_con_ttl` | Gestionar el carrito POS temporal en Redis. | PUT, GET, DELETE y GET del carrito. | 200, TTL ≤ 900, 200, 404. | Se cumplieron todas las aserciones. | **PASÓ** | 0.017 s |
| PI-257 | `test_ciclo_de_vida_asn_en_mongodb` | Recorrer el ciclo de vida de un ASN en MongoDB. | POST XML con 2 partidas, POST duplicado, GET, transición inválida, transición válida, inspección, filtro por SKU, folio inexistente. | 201, 409, estado `ANUNCIADO` con 2 partidas, 409, 200, 201 (`$push`), aparece en el filtro anidado, 404. | Se cumplieron todas las aserciones. | **PASÓ** | 0.098 s |
| PI-258 | `test_asn_valida_contra_postgres` | Validar el ASN contra el catálogo de PostgreSQL. | ASN JSON con SKU 99999999. | 409 con `skus_inexistentes: [99999999]`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.011 s |
| PI-259 | `test_escaneo_y_atencion_de_alertas` | Escanear riesgo de caducidad y atender alertas. | Escaneo de 30 días en la tienda 3; resolver una alerta; id inválido; criticidad inválida. | 200; 200 al resolver; 400; 400. | Se cumplieron todas las aserciones. | **PASÓ** | 0.072 s |
| PI-260 | `test_planeacion_ordenes_y_contexto_hibrido` | Consultar planeación y el contexto PostgreSQL + MongoDB. | Listado de órdenes, aprobar orden inexistente, contexto del SKU 1, pronóstico con método inexistente. | 200 paginado, 404, contexto con `producto_postgres` y `contexto_mongo`, 400. | Se cumplieron todas las aserciones. | **PASÓ** | 0.045 s |
| PI-261 | `test_auditoria_registra_con_identidad_del_jwt` | Registrar en la bitácora con la identidad del JWT, no con la de cabeceras. | POST de auditoría como auditor con `X-User-Email: suplantado@x.mx`. | 201 y en PostgreSQL `usuario_email = auditor@freshtrack.mx`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.046 s |
| PI-262 | `test_trazabilidad_de_lote` | Obtener la trazabilidad de un lote. | `GET /audit/traceability/{id_lote}` de un lote recién recibido. | 200 y primer movimiento del kardex `RECEPCION`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.024 s |
| PI-263 | `test_health_de_los_ocho_servicios` | Verificar `/health` de los 8 microservicios. | `GET /health` en cada servicio. | 200 o 503 con el estado de su base de datos principal. | Se cumplieron todas las aserciones. | **PASÓ** | 0.041 s |

## Integración: `tests/integration/test_seguridad_distribuida.py`

| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |
|---|---|---|---|---|---|---|---:|
| PI-264 | `test_login_json_entrega_jwt_y_crea_sesion_en_redis` | Iniciar sesión, emitir JWT y registrar la sesión. | Login JSON del usuario de almacén. | JWT con rol e `iss`; sesión en Redis con TTL; fila no revocada en `operacion.sesion_usuario`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.022 s |
| PI-265 | `test_login_xml_con_respuesta_xml` | Iniciar sesión en XML y recibir XML. | `login_request` XML con `Accept: application/xml`. | 200 `application/xml` con `<auth_response>` y `<token>`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.028 s |
| PI-266 | `test_login_errores_controlados` | Manejar errores de login de forma controlada. | Contraseña incorrecta, falta password, XML que no cumple el XSD, usuario inactivo. | 401 `credenciales_invalidas`, 400 con faltantes, 400 `xml_no_cumple_contrato`, 401. | Se cumplieron todas las aserciones. | **PASÓ** | 0.033 s |
| PI-267 | `test_rate_limit_de_login` | Limitar intentos de login (fuerza bruta). | 11 intentos con credenciales inválidas. | 10 × 401 y el 11.º 429. | Se cumplieron todas las aserciones. | **PASÓ** | 0.080 s |
| PI-268 | `test_token_de_auth_funciona_en_otros_servicios` | Usar el token de svc-auth en otros servicios. | Token de almacén en svc-inventory, svc-commercial y `/auth/verify`. | 200, 200 y `valido: true`. | Se cumplieron todas las aserciones. | **PASÓ** | 0.031 s |
| PI-269 | `test_rbac_entre_servicios` | Aplicar RBAC entre servicios. | Auditor lee bitácora, crea producto, vende; gerente lee bitácora; admin lista usuarios. | 200, 403 `acceso_denegado`, 403, 403, 200. | Se cumplieron todas las aserciones. | **PASÓ** | 0.047 s |
| PI-270 | `test_tokens_invalidos_y_expirados` | Rechazar tokens manipulados, expirados, de otro emisor o ausentes. | 4 variantes contra `GET /catalog/suppliers`. | 401 en los 4 casos. | Se cumplieron todas las aserciones. | **PASÓ** | 0.006 s |
| PI-271 | `test_logout_revoca_en_todos_los_servicios` | Revocar el token en todos los servicios al cerrar sesión. | Login de gerente, petición OK, `POST /auth/logout`, peticiones a 3 servicios. | Denylist en Redis, sesión inactiva, `revocado=true` en PostgreSQL y 401 `token_revocado` en los 3. | Se cumplieron todas las aserciones. | **PASÓ** | 0.051 s |
| PI-272 | `test_admin_cierra_sesiones_de_otro_usuario` | Cierre forzado de sesiones por el administrador. | Login de planner; admin lista y elimina sus sesiones. | ≥ 1 sesión activa, ≥ 1 cerrada y el token del planner da 401 en svc-planning. | Se cumplieron todas las aserciones. | **PASÓ** | 0.035 s |
| PI-273 | `test_ids_invalidos_dan_400_no_500` | Validar identificadores de ruta. | UUID inválido en sesiones y trazabilidad. | 400 en ambos (no 500). | Se cumplieron todas las aserciones. | **PASÓ** | 0.010 s |

## Evidencia de ejecución

- Salida completa de pytest: [`salida_pytest.txt`](salida_pytest.txt)
- Resultado en formato JUnit (lo leen GitHub Actions y otras herramientas de CI): [`resultado_pytest.xml`](resultado_pytest.xml)

Fragmento final de la salida:

```text
====================== 407 passed, 136 warnings in 5.21s =======================
```

Para reproducirlo:

```bash
docker compose up -d --wait
python scripts/generar_reporte_pruebas.py
```
