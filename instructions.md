**Vamos a fortalecer varios aspectos funcionales del proyecto.**

1. En primer lugar, **es necesario implementar y validar explícitamente el modelo newsvendor**, demostrando que las cantidades recomendadas consideran demanda incierta, costos de excedentes y faltantes, tiempos de suministro y vida útil restante, asimismo, las funcionalidades de transferencias y descuentos preventivos aparecen implementadas en el dominio web, pero deben integrarse de manera uniforme con los microservicios para que puedan ser consumidas por Android y escritorio.

2. **Se deben reforzar las pruebas de concurrencia FEFO, recuperación de transacciones, seguridad JWT y funcionamiento ante fallas de Redis, para la siguiente etapa desarrollaremos una aplicación móvil Android orientada a recepción, escaneo y control de lotes, así como una aplicación de escritorio destinada a planeación de demanda, reabastecimiento, transferencias, descuentos y análisis de resultados.** Se exigirá una demostración integrada que comience con el registro y recepción de mercancía, continúe con inventario FEFO y ventas y concluya con pronósticos, decisiones preventivas y cuantificación verificable de mermas y desperdicio evitado. (**POR LO PRONTO NOS ENFOCAMOS ESTRÍCTAMENTE EN LA PÁGINA WEB, SOLO HAY QUE TENER EN MENTE LA APLICACIÓN DE ESCRITORIO Y LA MÓVIL**)

3. El catálogo de ocho APIs no contempla operaciones REST equivalentes claramente diferenciadas para ambas capacidades, **esto significa que la funcionalidad web existente no necesariamente estará disponible para los futuros clientes Android y escritorio**. Hay que convertir transferencias y descuentos preventivos en operaciones de negocio accesibles desde microservicios, manteniendo las mismas reglas de aprobación, permisos, persistencia y auditoría. No es obligatorio crear dos contenedores nuevos: pueden incorporarse al servicio de planeación o de inventario si se justifica la propiedad de los datos.

4. **Falta demostrar newsvendor como optimizador específico, el proyecto asignado solicita un servicio newsvendor**. El código contiene funciones de pronóstico y recomendaciones de reabastecimiento, pero no basta con utilizar una media móvil o calcular demanda esperada. El modelo newsvendor debe demostrar cómo se selecciona una cantidad de pedido que equilibre el costo de quedarse sin producto y el costo de excedentes que puedan caducar. Hay que documentar formalmente los costos de faltante y excedente, la distribución de demanda, la vida útil, la política de reposición y el tratamiento de pedidos mínimos. Se debe comparar la política propuesta contra alternativas simples y verificar que reduzca el costo esperado o el desperdicio bajo condiciones equivalentes.

5. El proyecto documenta medias móviles y suavización exponencial. El código contiene funciones para series, factores semanales y métricas, sin embargo, para probar utilidad es necesario demostrar calidad predictiva con conjuntos de datos separados cronológicamente. Hay que medir MAE, WAPE y sesgo, utilizar validación temporal o backtesting, comparar con una predicción ingenua y documentar errores por producto y tienda. En productos de demanda intermitente deben considerar que un porcentaje de error puede resultar inestable o poco interpretable.

6. La fecha de vencimiento es un criterio central, pero no suficiente por sí sola para determinar que un producto debe venderse, el sistema debe distinguir productos disponibles, reservados, bloqueados, dañados, retirados, en cuarentena o caducados. Hay que demostrar que FEFO solo selecciona lotes elegibles y que no utiliza productos inmovilizados por calidad o por restricciones comerciales.

7. **Veo bloqueos Redis frente a consistencia transaccional, documentan bloqueos distribuidos Redlock, scripts Lua y compensaciones Saga, la presencia de estos mecanismos no elimina automáticamente las condiciones de carrera**. Hay que ejecutar ventas concurrentes sobre pocas unidades disponibles, interrupciones entre reserva y confirmación, reintentos duplicados y reinicios de workers. Las invariantes críticas deben protegerse también mediante transacciones y restricciones PostgreSQL.

8. **Veo problemas de seguridad ante fallos de Redis. el módulo compartido de autenticación comprueba la denylist y la sesión activa mediante funciones de Redis.** Su documentación menciona además un mecanismo de respaldo hacia PostgreSQL cuando Redis no está disponible. Esto exige probar que una falla de Redis no provoque la aceptación accidental de tokens revocados. Hay que demostrar los comportamientos exactos frente a Redis indisponible, sesión vencida, logout, revocación administrativa y token inválido. Si el respaldo no puede determinar con certeza el estado de la sesión, debe rechazar las operaciones protegidas.

**Medición del desperdicio evitado, esto es una prioridad crítica del proyecto, el servicio de alertas calcula indicadores de sostenibilidad y el portal muestra reportes de desperdicio evitado, no obstante, es necesario distinguir entre:**

*Indicador y significado:*

- Producto en riesgo: Existencia con probabilidad de caducar

- Desperdicio proyectado: cantidad estimada que podría perderse

- Producto recuperado: Unidades efectivamente vendidas o aprovechadas mediante una intervención registrada

- Desperdicio evitado estimado: Diferencia estimada frente a un escenario comparable sin intervención

- Reducción observada de merma: Cambio comprobado en pérdidas registradas

- CO₂e evitado estimado: Conversión basada en factores ambientales y supuestos documentados

**No se debe reportar todo producto vendido con descuento como desperdicio efectivamente evitado. Sin una línea base o contrafactual apropiado, el resultado constituye una estimación, no una medición causal demostrada.**


PRÓXIMA ENTREGA

Deben evolucionar FreshTrack hasta convertirlo en un sistema inteligente de gestión de productos perecederos, que permita anticipar la demanda, controlar inventarios por lote y caducidad, recomendar cantidades óptimas de compra y ejecutar acciones preventivas para disminuir desperdicios. 

En la segunda entrega identificamos ocho microservicios, una aplicación web Flask que consume APIs, PostgreSQL, MongoDB, Redis, autenticación JWT, contratos JSON/XML, Docker y pruebas de integración. No considero necesario rehacer esa arquitectura. Lo que hace falta es completar los procesos de negocio y comprobar su efectividad.

**La solución final deberá contar con tres aplicaciones:**

## Aplicación, función principal y comunicación

- Web empresarial: Administración de productos, proveedores, tiendas, inventario, alertas, indicadores y auditoría APIs REST. (NOSOTROS NOS ENFOCAMOS EXCLUSÍVAMENTE EN ESTO.)

- Android: Recepción de mercancía, escaneo de lotes, verificación FEFO, conteos, mermas y operaciones en tienda JSON. 
- Aplicación de escritorio: Pronósticos, optimización newsvendor, reabastecimiento, transferencias, descuentos y análisis de desperdicio XML validado mediante XSD. 

**Deben de completar y fortalecer los microservicios actuales con:**

1.- svc-auth 5001 JWT, renovación y revocación, sesiones Redis, permisos por rol y sucursal, acceso desde web, Android y escritorio, y manejo seguro de fallos.

2.- svc-catalog 5002 CRUD de productos, categorías, tiendas y proveedores; unidades, presentación, conservación, vida útil, tiempos de suministro y mínimos de compra.

3.- svc-inventory 5003 Existencias por lote y tienda; caducidad, FEFO, movimientos, reservas, conteos, ubicaciones, cuarentena, bloqueos y prevención de inventario negativo.

4.- svc-commercial 5004 Ventas POS, devoluciones, descuentos autorizados, mermas, transacciones idempotentes, compensaciones y registros financieros operativos.

5.- svc-asn 5005 Recepción de avisos anticipados de embarque, validación XML/XSD, inspecciones, diferencias de recepción y vinculación con lotes reales.

6.- svc-planning 5006 Pronósticos por SKU/tienda, evaluación de modelos, cantidades newsvendor, propuestas de compra, transferencias, descuentos preventivos y aprobaciones.

7.- svc-alerts 5007 Alertas de vencimiento, lotes de alto riesgo, desviaciones de stock, propuestas preventivas, seguimiento de acciones y métricas ambientales.

8.- svc-audit 5008 Historial de operaciones, usuarios, decisiones, versiones de algoritmos, cambios de inventario, autorizaciones y reconstrucción de eventos.

Cada servicio deberá disponer de rutas REST versionadas, seguridad JWT y autorización por roles, solicitudes/respuestas JSON y XML, contratos XSD cuando correspondan, Swagger/OpenAPI, validación de datos, errores consistentes, /health, contenedor Docker, trazabilidad mediante correlation_id y pruebas de integración. Además, las decisiones críticas deberán conservar qué datos se utilizaron, qué versión del algoritmo calculó el resultado, qué usuario lo aprobó y qué efecto tuvo sobre el inventario y el desperdicio.

**Recomiendo incorporar los siguientes microservicios y capacidades:**

9.- svc-newsvendor 5009 Calcular cantidades óptimas de pedido considerando demanda incierta, costo de faltante, costo de excedente, vida útil, precio, valor de recuperación y restricciones comerciales.

10.- vc-transfers 5010 Proponer transferencias entre tiendas; comprobar stock disponible, demanda del destino, vida útil residual, tiempos, costos y aprobación; registrar salida, tránsito y recepción.

11.- svc-markdowns 5011 Proponer descuentos preventivos por lote; calcular precio, margen, demanda esperada, fecha de vigencia, aprobación y resultado real.

12.- svc-expiration 5012 Evaluar caducidad y vida útil, detectar lotes críticos, bloquear productos vencidos y clasificar riesgo por fecha, temperatura y condiciones cuando se disponga de datos.

13.- svc-waste 5013 Registrar mermas, motivos, cantidades, costos, destino, evidencias y resultados por producto, tienda, periodo y proveedor.

14.- svc-demand-validation 5014 Ejecutar backtesting de pronósticos, comparar modelos, medir MAE, WAPE, sesgo y comportamiento por producto y tienda.

15.- svc-supplier-orders 5015 Administrar órdenes de compra, mínimos, múltiplos de empaque, fechas prometidas, cantidades recibidas, incumplimientos y modificaciones.

16.- svc-quality-coldchain 5016 Registrar inspecciones, temperaturas cuando existan mediciones, rupturas de cadena de frío, cuarentena, rechazos y liberación autorizada.

17.- svc-sustainability 5017 Medir merma observada, estimaciones de desperdicio evitado, recuperación de valor, costos y CO₂e estimado con fuentes y factores documentados.

18.- svc-sync-notifications 5018 Sincronización offline Android, eventos pendientes, notificaciones por tienda, reintentos, prevención de duplicados y resolución de conflictos.


**Los servicios que considera indispensable son:**

- Newsvendor y reabastecimiento: Determinar cuánto comprar y no solamente cuánto se espera vender. Debe considerar el costo de quedarse sin producto, el costo del excedente y la caducidad.

- Transferencias entre tiendas: Detectar una tienda con exceso y otra con demanda, evaluar si el producto llegará con vida útil suficiente y determinar si el ahorro supera el costo logístico.

- Descuentos preventivos: Proponer rebajas únicamente cuando sean comercialmente justificables, respetando margen, inventario, vencimiento y autorizaciones.

- Medición del desperdicio: Distinguir pérdidas reales, pérdidas proyectadas, unidades recuperadas y reducción estimada frente a una línea base comparable.

## Pruebas de aceptación y usabilidad: 

- ASN y recepción: Registrar un aviso de embarque y recibir mercancía desde Android.

- Identidad de lotes: Conservar producto, tienda, lote, caducidad y estado de calidad.

- FEFO: Seleccionar el lote elegible que vence primero.

- Producto bloqueado: Impedir utilizar producto caducado o inmovilizado.

- Venta concurrente: Ejecutar dos ventas simultáneas sin generar inventario negativo.

F- allo y compensación: Interrumpir una transacción y recuperar reservas sin duplicaciones.

- Pronóstico: Calcular demanda por producto/tienda y mostrar métricas verificables.

- Newsvendor: Comparar cantidad propuesta contra un cálculo de referencia.

- Transferencia: Evaluar un lote crítico y decidir si conviene trasladarlo.

- Descuento: Simular y aprobar una rebaja preventiva con margen y vigencia.

- Merma: Registrar cantidad, motivo, costo y evidencia.

- Sostenibilidad: Separar merma observada, proyección e impacto estimado.

.- Integración XML/JSON: Android registra mediante JSON y escritorio consulta mediante XML/XSD.

- Autorización: Un usuario de otra sucursal no puede modificar datos sin permiso.

- Modo offline: Sincronizar capturas pendientes sin duplicar movimientos.

- Auditoría: Reconstruir movimientos y decisiones desde ASN hasta venta o merma.

- La reducción de merma, la precisión del pronóstico y los beneficios económicos deben evaluarse frente a una línea base medida. No recomendaría imponer un porcentaje universal de mejora sin conocer datos históricos y condiciones de operación.