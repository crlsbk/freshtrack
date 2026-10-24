#!/usr/bin/env python3
"""
Genera docs/pruebas/REPORTE_PRUEBAS.md ejecutando la suite REAL de pytest.

Por cada caso se documenta: objetivo, entradas, resultado esperado, resultado
obtenido (salido de la ejecución, no escrito a mano), estado y duración. La salida
completa de pytest y el JUnit XML quedan junto al reporte como evidencia.

Uso:
    docker compose up -d --wait        # PostgreSQL, Redis y MongoDB reales
    python scripts/generar_reporte_pruebas.py
"""

from __future__ import annotations

import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "docs" / "pruebas"

# Catálogo de casos: nombre de la función de prueba -> (objetivo, entradas, esperado).
# El resultado obtenido y el estado se toman de la ejecución.
CASOS: dict[str, tuple[str, str, str]] = {
    # --- Contratos JSON/XML -------------------------------------------------------
    "test_respuesta_json_por_omision": (
        "Verificar que sin cabecera Accept la respuesta sea JSON.",
        "`render_response({'a': 1}, status=201)` sin `Accept`.",
        "HTTP 201, `application/json`, cuerpo `{\"a\": 1}`.",
    ),
    "test_respuesta_xml_con_accept": (
        "Verificar la negociación de contenido hacia XML.",
        "`Accept: application/xml`, `text/xml` y `application/xml;q=0.9`; dict con objeto anidado y lista.",
        "`application/xml` con declaración UTF-8; objeto anidado como elementos y lista como `<item>`.",
    ),
    "test_respuesta_xml_con_parametro_formato": (
        "Permitir elegir XML por parámetro de consulta.",
        "`GET /?formato=xml`.",
        "Respuesta `application/xml`.",
    ),
    "test_dict_a_xml_sanea_etiquetas_invalidas": (
        "Generar XML válido aunque las claves no sean nombres XML válidos.",
        "Claves `1campo`, `con espacio`, `_id`.",
        "Etiquetas `<_1campo>` y `<con_espacio>`.",
    ),
    "test_xml_a_dict_ida_y_vuelta": (
        "Comprobar que la conversión dict→XML→dict no pierde datos.",
        "`checkout_request` con `id_locacion` y una lista de líneas.",
        "El dict reconstruido es idéntico al original.",
    ),
    "test_xml_a_dict_un_solo_item_sigue_siendo_lista": (
        "Evitar que una lista de un solo elemento se lea como objeto.",
        "`<lineas>` con un único `<item>`.",
        "`lineas` es una lista de un elemento.",
    ),
    "test_xml_mal_formado_da_400": (
        "Rechazar de forma controlada un XML mal formado.",
        "`<r><sin_cerrar></r>`.",
        "`ErrorApi` 400 con código `xml_mal_formado`.",
    ),
    "test_xsd_acepta_documento_valido": (
        "Validar un ASN correcto contra su XSD.",
        "`asn_request` con folio, proveedor y un `item_carga` completo.",
        "Validación sin excepción.",
    ),
    "test_xsd_rechaza_tipos_y_campos_faltantes": (
        "Rechazar XML que no cumple el contrato (tipo incorrecto y campo obligatorio faltante).",
        "`checkout_request` sin `id_locacion` y con `id_sku=abc`.",
        "400 `xml_no_cumple_contrato` con detalles del XSD.",
    ),
    "test_todos_los_xsd_compilan": (
        "Asegurar que todos los esquemas XSD del contrato son válidos.",
        "Todos los archivos `contracts/xsd/*.xsd`.",
        "Al menos 9 esquemas y todos compilan.",
    ),
    "test_leer_cuerpo_json_y_xml": (
        "Leer el cuerpo de la petición en JSON o XML con la misma función.",
        "POST JSON `{\"a\":1}` y POST XML `login_request`.",
        "Ambos se convierten al mismo tipo de dict.",
    ),
    "test_leer_cuerpo_json_invalido_y_vacio": (
        "Manejar JSON inválido y cuerpo vacío obligatorio.",
        "`{malo` con `application/json`; POST sin cuerpo con `requerido=True`.",
        "`json_mal_formado` y 400 respectivamente.",
    ),
    "test_error_response_cumple_su_xsd": (
        "Comprobar que el error XML estándar cumple `error_response.xsd` y propaga el correlation id.",
        "Error 404 con `Accept: application/xml` y `X-Correlation-Id: abc123`.",
        "HTTP 404, XML válido contra el XSD, `<correlation_id>abc123</correlation_id>`.",
    ),
    "test_error_response_json_estructura": (
        "Verificar la estructura estándar del error JSON.",
        "Error 409 `conflicto`.",
        "Campos exactos `error`, `mensaje`, `status`, `correlation_id`.",
    ),
    "test_paginacion_por_defecto_y_limites": (
        "Validar los parámetros de paginación y sus límites.",
        "Sin parámetros; `pagina=3&por_pagina=500`; `pagina=0`.",
        "(1,20,0); `por_pagina` topado a 100; error en página 0; metadatos con `total_paginas=5`.",
    ),
    # --- Mapa de tiendas -----------------------------------------------------------
    "test_coordenadas_vacias_son_opcionales": (
        "Permitir locaciones sin coordenadas.",
        "Dict vacío y latitud/longitud en blanco.",
        "`(None, None)`.",
    ),
    "test_coordenadas_validas_se_convierten_a_numero": (
        "Convertir coordenadas de texto a número.",
        "`latitud=25.6575`, `longitud=-100.402`.",
        "`(25.6575, -100.402)`.",
    ),
    "test_coordenadas_invalidas_se_rechazan": (
        "Validar coordenadas incompletas, no numéricas o fuera de rango.",
        "Solo latitud, solo longitud, `norte`, latitud 95, longitud -181.",
        "`ValueError` con el mensaje correspondiente.",
    ),
    "test_vista_del_mapa_registrada_y_sin_acceso_para_proveedor": (
        "Verificar permisos de la vista del mapa por rol.",
        "Matriz `VISTAS_POR_ROL`.",
        "Proveedor sin acceso; los otros 6 roles con acceso.",
    ),
    # --- OpenAPI -----------------------------------------------------------------
    "test_rutas_versionadas_y_health": (
        "Verificar que cada microservicio expone `/health` y rutas versionadas.",
        "`GET /api/v1/openapi.json` y `/api/v1/docs` de cada servicio.",
        "Swagger responde 200; todas las rutas de negocio empiezan con `/api/v1/`.",
    ),
    "test_endpoints_protegidos_declaran_jwt_y_errores": (
        "Comprobar que la documentación declara seguridad JWT y errores.",
        "Todas las operaciones del OpenAPI de cada servicio.",
        "Cada operación tiene resumen y 500; las protegidas documentan 401.",
    ),
    "test_cuerpos_con_ejemplo_json_y_xml": (
        "Comprobar ejemplos de request en ambos formatos.",
        "Operaciones con `requestBody`.",
        "Ejemplo JSON y ejemplo XML (con `<?xml`).",
    ),
    "test_respuestas_en_json_y_xml": (
        "Comprobar que cada respuesta documentada ofrece JSON y XML.",
        "Todas las respuestas del OpenAPI.",
        "`application/json` y `application/xml` en cada respuesta.",
    ),
    "test_usa_metodos_http_variados": (
        "Verificar el uso de los métodos HTTP apropiados.",
        "Reglas de URL de los 8 servicios.",
        "Aparecen GET, POST, PUT, PATCH y DELETE.",
    ),
    # --- Redis ---------------------------------------------------------------------
    "test_sesion_con_ttl_e_indice_por_usuario": (
        "Gestionar sesiones en Redis con TTL e índice por usuario.",
        "Sesión `s1` del usuario `u1` con TTL de 120 s.",
        "Sesión activa, TTL ≤ 120, listada en `user:sessions:u1`; inactiva tras eliminarla.",
    ),
    "test_denylist_jwt": (
        "Revocar un JWT por su `jti`.",
        "`revocar_jwt('j1', 300)`.",
        "`jwt:denylist:j1` existe con TTL; contador de revocados = 1.",
    ),
    "test_cache_aside_e_invalidacion_por_patron": (
        "Probar el patrón Cache-Aside y la invalidación por patrón con SCAN.",
        "3 claves de caché; `invalidar_patron('catalog:products:*')`.",
        "Se eliminan 2 claves; la de locaciones se conserva.",
    ),
    "test_contadores_de_operacion": (
        "Contar operaciones de forma atómica con INCRBY.",
        "Dos incrementos de `inventory/reserve_success`.",
        "Contador del día = 2.",
    ),
    "test_temporal_se_consume_una_sola_vez": (
        "Guardar datos temporales con TTL y consumirlos una sola vez.",
        "Carrito `c1` con TTL de 900 s.",
        "TTL ≤ 900; el primer consumo devuelve el carrito y el segundo `None`.",
    ),
    "test_bloqueo_distribuido_exclusivo": (
        "Garantizar exclusión mutua con bloqueo distribuido (SET NX EX + Lua).",
        "Bloqueo `inv:loc:1`; segundo intento; liberar con token ajeno y con el propio.",
        "Segundo intento falla; el token ajeno no libera; el propio sí.",
    ),
    "test_rate_limit_ventana_fija": (
        "Limitar la tasa de peticiones con ventana fija.",
        "4 peticiones con límite 3 en 60 s.",
        "Permitidas, permitidas, permitidas, rechazada; restante 0 en la tercera.",
    ),
    "test_sin_redis_no_reintenta_en_cada_llamada": (
        "Degradar de forma controlada si Redis no responde.",
        "Redis apuntando a un puerto cerrado; 20 llamadas seguidas.",
        "Sin excepciones y sin pagar el timeout en cada llamada (< 0.1 s en total).",
    ),
    # --- Reglas de negocio -------------------------------------------------------
    "test_fefo_consume_primero_el_lote_mas_proximo_a_caducar": (
        "Aplicar FEFO: primero el lote que caduca antes.",
        "Lote que vence hoy (3 u.) y lote que vence mañana (10 u.); pedido de 5.",
        "Se toman 3 del primero y 2 del segundo.",
    ),
    "test_fefo_respeta_lo_ya_reservado": (
        "No consumir cantidades ya reservadas.",
        "Lote A con 5 disponibles y 4 reservadas, lote B con 5; pedido de 3.",
        "1 de A y 2 de B.",
    ),
    "test_fefo_stock_insuficiente_cubre_lo_posible": (
        "Repartir solo lo existente cuando no alcanza el stock.",
        "Un lote de 2 u.; pedido de 5.",
        "Total consumido = 2.",
    ),
    "test_fefo_omite_lotes_sin_disponible": (
        "Omitir lotes sin disponibilidad real.",
        "Lote totalmente reservado y lote en 0.",
        "Ningún consumo.",
    ),
    "test_medias_moviles": (
        "Calcular media móvil simple y ponderada.",
        "`[1,2,3,4]` ventana 2; `[2,4,6]` ventana 3 ponderada.",
        "3.5 y 28/6.",
    ),
    "test_suavizacion_exponencial_converge_al_ultimo_valor_con_alpha_alto": (
        "Validar la suavización exponencial.",
        "`[10,10,10,50]` con α=0.99; serie vacía.",
        "≈49.6 y 0.0.",
    ),
    "test_metodo_desconocido_lanza_error": (
        "Rechazar métodos de pronóstico inexistentes.",
        "Método `MAGIA`.",
        "`ValueError`.",
    ),
    "test_metricas_de_error": (
        "Calcular MAE y WMAPE del pronóstico.",
        "Real `[10,20]`, pronóstico `[12,18]`.",
        "MAE 2, n 2, WMAPE 13.33 %, suma_real 30.",
    ),
    "test_pronosticar_serie_horizonte_y_no_negativo": (
        "Pronosticar con el horizonte pedido y sin valores negativos.",
        "Serie de 60 días, suavización exponencial, horizonte 7.",
        "7 valores ≥ 0; métricas sobre los días de backtest.",
    ),
    # --- Seguridad JWT (unitarias) -----------------------------------------------
    "test_sin_token_401": (
        "Rechazar peticiones protegidas sin token.",
        "`GET /libre` sin `Authorization`.",
        "401 `token_requerido`.",
    ),
    "test_token_manipulado_401": (
        "Rechazar tokens con firma alterada.",
        "JWT con los últimos 3 caracteres cambiados.",
        "401 `token_invalido`.",
    ),
    "test_token_expirado_401": (
        "Rechazar tokens expirados.",
        "JWT con `exp=1`.",
        "401.",
    ),
    "test_token_valido_200": (
        "Aceptar un token válido con sesión activa.",
        "JWT firmado y sesión en Redis.",
        "200 con el email del usuario y cabecera `X-Correlation-Id`.",
    ),
    "test_token_revocado_en_denylist_401": (
        "Rechazar tokens revocados en Redis.",
        "JWT cuyo `jti` está en la denylist.",
        "401 `token_revocado`.",
    ),
    "test_sesion_inexistente_en_redis_401": (
        "Exigir sesión viva en Redis.",
        "JWT válido sin sesión registrada.",
        "401 `sesion_inexistente`.",
    ),
    "test_cerrar_sesiones_usuario_invalida_tokens": (
        "Cerrar todas las sesiones de un usuario.",
        "`cerrar_sesiones_usuario('u-1')`.",
        "1 sesión cerrada, `jti` revocado y siguiente petición 401.",
    ),
    "test_rol_no_permitido_403": (
        "Aplicar RBAC: rol sin permiso.",
        "Rol `store_manager` en endpoint solo para `auditor`.",
        "403 con los roles permitidos en el detalle.",
    ),
    "test_rol_permitido_y_admin_200": (
        "Aplicar RBAC: rol permitido y administrador.",
        "Roles `auditor` y `admin`.",
        "200.",
    ),
    "test_rate_limit_429_con_cabeceras": (
        "Limitar tasa por endpoint con cabeceras RFC.",
        "3 peticiones con límite 2/60 s.",
        "`X-RateLimit-Remaining: 0`, luego 429 `limite_excedido` con `Retry-After`.",
    ),
    "test_errores_http_estandarizados": (
        "Estandarizar 404 y 405.",
        "Ruta inexistente con `Accept: application/xml`; POST a ruta GET.",
        "404 con `<error_response>` y 405.",
    ),
    "test_error_no_controlado_no_expone_traza": (
        "No filtrar información interna en errores 500.",
        "Endpoint que lanza `RuntimeError('detalle interno secreto')`.",
        "500 `error_interno` sin el texto del error.",
    ),
    "test_health_reporta_dependencias": (
        "Reportar el estado de dependencias en `/health`.",
        "`GET /health` con Redis disponible.",
        "200 con `dependencies: {redis: true}`.",
    ),
    # --- Integración: mapa ---------------------------------------------------------
    "test_metricas_por_locacion_traen_coordenadas_y_cuadran_con_postgres": (
        "Verificar que las métricas del mapa cuadran con PostgreSQL.",
        "Métricas de 30 días de la tienda 3 contra `operacion.v_inventario_lote`.",
        "Coordenadas válidas; valor y número de lotes iguales a la consulta SQL.",
    ),
    "test_metricas_por_locacion_solo_incluye_activas": (
        "Mostrar solo locaciones activas.",
        "Métricas de 7 días.",
        "Tantas filas como locaciones activas en PostgreSQL.",
    ),
    # --- Integración: procesos de negocio ----------------------------------------
    "test_crud_de_producto_con_xml_y_cache": (
        "Recorrer el CRUD de producto en svc-catalog con XML, reglas de negocio y RBAC.",
        "POST XML (buyer), GET, PATCH, PUT incompleto, PATCH precio < costo, DELETE (buyer y admin), GET de id inexistente.",
        "201 XML, 200, 200, 400, 409, 403, 200 con `activo=false` en PostgreSQL, 404.",
    ),
    "test_listado_paginado_usa_cache_redis": (
        "Comprobar Cache-Aside en el listado paginado.",
        "Dos `GET /api/v1/catalog/products` idénticos.",
        "Primera desde `postgres`, segunda desde `redis_cache`; metadatos de paginación.",
    ),
    "test_saga_de_venta_descuenta_inventario_fefo": (
        "Ejecutar la saga de venta entre svc-commercial y svc-inventory.",
        "Lote nuevo de 50 u.; `POST /commercial/checkout` de 2 u. del SKU 1 en la tienda 3.",
        "Cola FEFO ordenada; 201; disponible total baja exactamente 2; la venta aparece en el historial.",
    ),
    "test_saga_rechaza_stock_insuficiente_sin_dejar_reservas": (
        "Compensar la saga cuando no hay stock.",
        "Checkout de 10 000 000 u.",
        "409 `venta_rechazada` y la cantidad reservada queda igual que antes.",
    ),
    "test_checkout_valida_entrada": (
        "Validar la entrada del checkout en JSON y XML.",
        "Cantidad -1 (JSON); `checkout_request` sin líneas (XML).",
        "400 y 400 `xml_no_cumple_contrato`.",
    ),
    "test_reserva_y_compensacion_por_saga_id": (
        "Reservar FEFO y cancelar la reserva por `saga_id`.",
        "`reserve-fefo` de todo el disponible; `cancel-reservation` dos veces.",
        "Reserva sube y se guarda en Redis; al cancelar vuelve al valor inicial; segunda cancelación 404.",
    ),
    "test_merma_descuenta_y_valida_causa": (
        "Registrar merma con validación de causa y cantidad.",
        "Merma de 1 u. `DANO`; causa `INVENTADA`; 999 999 u.",
        "201 y disponible -1; 400; 409.",
    ),
    "test_carrito_temporal_con_ttl": (
        "Gestionar el carrito POS temporal en Redis.",
        "PUT, GET, DELETE y GET del carrito.",
        "200, TTL ≤ 900, 200, 404.",
    ),
    "test_ciclo_de_vida_asn_en_mongodb": (
        "Recorrer el ciclo de vida de un ASN en MongoDB.",
        "POST XML con 2 partidas, POST duplicado, GET, transición inválida, transición válida, inspección, filtro por SKU, folio inexistente.",
        "201, 409, estado `ANUNCIADO` con 2 partidas, 409, 200, 201 (`$push`), aparece en el filtro anidado, 404.",
    ),
    "test_asn_valida_contra_postgres": (
        "Validar el ASN contra el catálogo de PostgreSQL.",
        "ASN JSON con SKU 99999999.",
        "409 con `skus_inexistentes: [99999999]`.",
    ),
    "test_escaneo_y_atencion_de_alertas": (
        "Escanear riesgo de caducidad y atender alertas.",
        "Escaneo de 30 días en la tienda 3; resolver una alerta; id inválido; criticidad inválida.",
        "200; 200 al resolver; 400; 400.",
    ),
    "test_planeacion_ordenes_y_contexto_hibrido": (
        "Consultar planeación y el contexto PostgreSQL + MongoDB.",
        "Listado de órdenes, aprobar orden inexistente, contexto del SKU 1, pronóstico con método inexistente.",
        "200 paginado, 404, contexto con `producto_postgres` y `contexto_mongo`, 400.",
    ),
    "test_auditoria_registra_con_identidad_del_jwt": (
        "Registrar en la bitácora con la identidad del JWT, no con la de cabeceras.",
        "POST de auditoría como auditor con `X-User-Email: suplantado@x.mx`.",
        "201 y en PostgreSQL `usuario_email = auditor@freshtrack.mx`.",
    ),
    "test_trazabilidad_de_lote": (
        "Obtener la trazabilidad de un lote.",
        "`GET /audit/traceability/{id_lote}` de un lote recién recibido.",
        "200 y primer movimiento del kardex `RECEPCION`.",
    ),
    "test_health_de_los_ocho_servicios": (
        "Verificar `/health` de los 8 microservicios.",
        "`GET /health` en cada servicio.",
        "200 o 503 con el estado de su base de datos principal.",
    ),
    # --- Integración: seguridad distribuida --------------------------------------
    "test_login_json_entrega_jwt_y_crea_sesion_en_redis": (
        "Iniciar sesión, emitir JWT y registrar la sesión.",
        "Login JSON del usuario de almacén.",
        "JWT con rol e `iss`; sesión en Redis con TTL; fila no revocada en `operacion.sesion_usuario`.",
    ),
    "test_login_xml_con_respuesta_xml": (
        "Iniciar sesión en XML y recibir XML.",
        "`login_request` XML con `Accept: application/xml`.",
        "200 `application/xml` con `<auth_response>` y `<token>`.",
    ),
    "test_login_errores_controlados": (
        "Manejar errores de login de forma controlada.",
        "Contraseña incorrecta, falta password, XML que no cumple el XSD, usuario inactivo.",
        "401 `credenciales_invalidas`, 400 con faltantes, 400 `xml_no_cumple_contrato`, 401.",
    ),
    "test_rate_limit_de_login": (
        "Limitar intentos de login (fuerza bruta).",
        "11 intentos con credenciales inválidas.",
        "10 × 401 y el 11.º 429.",
    ),
    "test_token_de_auth_funciona_en_otros_servicios": (
        "Usar el token de svc-auth en otros servicios.",
        "Token de almacén en svc-inventory, svc-commercial y `/auth/verify`.",
        "200, 200 y `valido: true`.",
    ),
    "test_rbac_entre_servicios": (
        "Aplicar RBAC entre servicios.",
        "Auditor lee bitácora, crea producto, vende; gerente lee bitácora; admin lista usuarios.",
        "200, 403 `acceso_denegado`, 403, 403, 200.",
    ),
    "test_tokens_invalidos_y_expirados": (
        "Rechazar tokens manipulados, expirados, de otro emisor o ausentes.",
        "4 variantes contra `GET /catalog/suppliers`.",
        "401 en los 4 casos.",
    ),
    "test_logout_revoca_en_todos_los_servicios": (
        "Revocar el token en todos los servicios al cerrar sesión.",
        "Login de gerente, petición OK, `POST /auth/logout`, peticiones a 3 servicios.",
        "Denylist en Redis, sesión inactiva, `revocado=true` en PostgreSQL y 401 `token_revocado` en los 3.",
    ),
    "test_admin_cierra_sesiones_de_otro_usuario": (
        "Cierre forzado de sesiones por el administrador.",
        "Login de planner; admin lista y elimina sus sesiones.",
        "≥ 1 sesión activa, ≥ 1 cerrada y el token del planner da 401 en svc-planning.",
    ),
    "test_ids_invalidos_dan_400_no_500": (
        "Validar identificadores de ruta.",
        "UUID inválido en sesiones y trazabilidad.",
        "400 en ambos (no 500).",
    ),
}

TIPOS = {"unit": "Unitaria", "integration": "Integración"}


def _entorno() -> list[str]:
    sys.path.insert(0, str(RAIZ))
    from tests.conftest import _redis_real_disponible  # carga .env y defaults

    from app.services import doc_store

    try:
        from app.db import escalar

        pg = escalar("SELECT version()").split(",")[0]
    except Exception:
        pg = "no disponible (las de integración se omiten)"
    mongo = doc_store.get_mongo_db() is not None
    return [
        f"- **Python:** {platform.python_version()} ({platform.system()})",
        f"- **PostgreSQL:** {pg}",
        f"- **Redis:** {'real (contenedor)' if _redis_real_disponible() else 'fakeredis en memoria'}",
        f"- **MongoDB:** {'real (contenedor)' if mongo else 'mongomock en memoria'}",
    ]


def _ejecutar(junit: Path, log: Path) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-v", "-p", "no:cacheprovider", f"--junitxml={junit}"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    # Rutas relativas: la evidencia no debe depender de la máquina donde se generó.
    log.write_text((proc.stdout + proc.stderr).replace(str(RAIZ) + "/", "").replace(str(RAIZ), "."), encoding="utf-8")
    return proc.returncode


def _celda(texto: str) -> str:
    return " ".join(texto.split()).replace("|", "\\|")


def _leer_junit(junit: Path) -> list[dict]:
    casos = []
    for tc in ET.parse(junit).iter("testcase"):
        nombre = tc.get("name", "")
        funcion, _, parametro = nombre.partition("[")
        archivo = tc.get("classname", "").replace(".", "/") + ".py"
        estado, detalle = "PASÓ", ""
        for etiqueta, valor in (("failure", "FALLÓ"), ("error", "ERROR"), ("skipped", "OMITIDA")):
            nodo = tc.find(etiqueta)
            if nodo is not None:
                estado, detalle = valor, nodo.get("message", "")
                break
        casos.append({
            "funcion": funcion,
            "parametro": parametro.rstrip("]"),
            "archivo": archivo,
            "tipo": TIPOS["integration" if "/integration/" in archivo else "unit"],
            "estado": estado,
            "detalle": detalle,
            "segundos": float(tc.get("time", 0)),
        })
    return casos


def _obtenido(ejecuciones: list[dict]) -> str:
    malas = [e for e in ejecuciones if e["estado"] != "PASÓ"]
    if not malas:
        n = len(ejecuciones)
        variantes = f" en las {n} variantes" if n > 1 else ""
        return f"Se cumplieron todas las aserciones{variantes}."
    return "; ".join(f"{e['parametro'] or e['funcion']}: {e['estado']} — {e['detalle'][:200]}" for e in malas)


def generar() -> int:
    SALIDA.mkdir(parents=True, exist_ok=True)
    junit, log = SALIDA / "resultado_pytest.xml", SALIDA / "salida_pytest.txt"
    entorno = _entorno()
    inicio = datetime.now()
    codigo = _ejecutar(junit, log)
    casos = _leer_junit(junit)

    agrupados: dict[str, list[dict]] = defaultdict(list)
    for c in casos:
        agrupados[c["funcion"]].append(c)

    conteo = defaultdict(lambda: defaultdict(int))
    for c in casos:
        conteo[c["tipo"]][c["estado"]] += 1
    sin_catalogo = sorted(f for f in agrupados if f not in CASOS)

    lineas = [
        "# Reporte de pruebas unitarias y de integración",
        "",
        f"Generado automáticamente por `scripts/generar_reporte_pruebas.py` el "
        f"{inicio:%Y-%m-%d %H:%M}. El resultado obtenido y el estado de cada caso salen de la "
        "ejecución real de pytest, no se escriben a mano.",
        "",
        "## Entorno de ejecución",
        "",
        *entorno,
        f"- **Comando:** `python -m pytest tests -v --junitxml=docs/pruebas/resultado_pytest.xml`",
        "",
        "## Resumen",
        "",
        "| Tipo | Ejecutadas | Pasaron | Fallaron | Omitidas |",
        "|---|---:|---:|---:|---:|",
    ]
    for tipo in ("Unitaria", "Integración"):
        e = conteo[tipo]
        total = sum(e.values())
        lineas.append(f"| {tipo} | {total} | {e['PASÓ']} | {e['FALLÓ'] + e['ERROR']} | {e['OMITIDA']} |")
    total = len(casos)
    pasaron = sum(1 for c in casos if c["estado"] == "PASÓ")
    lineas += [
        f"| **Total** | **{total}** | **{pasaron}** | **{sum(1 for c in casos if c['estado'] in ('FALLÓ', 'ERROR'))}** "
        f"| **{sum(1 for c in casos if c['estado'] == 'OMITIDA')}** |",
        "",
        f"Tiempo total: {sum(c['segundos'] for c in casos):.2f} s. "
        "Las pruebas de integración corren contra el PostgreSQL real con el seed de FreshTrack y "
        "levantan los 8 microservicios en el mismo proceso, compartiendo Redis y MongoDB igual que en docker compose.",
        "",
    ]

    por_archivo: dict[str, list[str]] = defaultdict(list)
    for funcion, ejecuciones in agrupados.items():
        por_archivo[ejecuciones[0]["archivo"]].append(funcion)

    n = 0
    for archivo in sorted(por_archivo, key=lambda a: ("integration" in a, a)):
        tipo = agrupados[por_archivo[archivo][0]][0]["tipo"]
        lineas += [
            f"## {tipo}: `{archivo}`",
            "",
            "| ID | Caso | Objetivo | Entradas | Resultado esperado | Resultado obtenido | Estado | Tiempo |",
            "|---|---|---|---|---|---|---|---:|",
        ]
        for funcion in por_archivo[archivo]:
            n += 1
            ejecuciones = agrupados[funcion]
            objetivo, entradas, esperado = CASOS.get(funcion, ("(sin descripción)", "—", "—"))
            estados = {e["estado"] for e in ejecuciones}
            estado = "PASÓ" if estados == {"PASÓ"} else " / ".join(sorted(estados))
            segundos = sum(e["segundos"] for e in ejecuciones)
            prefijo = "PI" if tipo == "Integración" else "PU"
            lineas.append(
                f"| {prefijo}-{n:02d} | `{funcion}` | {_celda(objetivo)} | {_celda(entradas)} | "
                f"{_celda(esperado)} | {_celda(_obtenido(ejecuciones))} | **{estado}** | {segundos:.3f} s |"
            )
        lineas.append("")

    lineas += [
        "## Evidencia de ejecución",
        "",
        "- Salida completa de pytest: [`salida_pytest.txt`](salida_pytest.txt)",
        "- Resultado en formato JUnit (lo leen GitHub Actions y otras herramientas de CI): "
        "[`resultado_pytest.xml`](resultado_pytest.xml)",
        "",
        "Fragmento final de la salida:",
        "",
        "```text",
        *[l for l in log.read_text(encoding="utf-8").splitlines() if " passed" in l or " failed" in l][-1:],
        "```",
        "",
        "Para reproducirlo:",
        "",
        "```bash",
        "docker compose up -d --wait",
        "python scripts/generar_reporte_pruebas.py",
        "```",
        "",
    ]
    (SALIDA / "REPORTE_PRUEBAS.md").write_text("\n".join(lineas), encoding="utf-8")

    print(f"[reporte] {pasaron}/{total} pruebas pasaron → {SALIDA / 'REPORTE_PRUEBAS.md'}")
    if sin_catalogo:
        print(f"[reporte] Casos sin descripción en CASOS: {', '.join(sin_catalogo)}", file=sys.stderr)
    return codigo


if __name__ == "__main__":
    sys.exit(generar())
