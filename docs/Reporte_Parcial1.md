**PROYECTO IAC**

# **Reporte Técnico FreshTrack · Avance 2**

Sistema de gestión de inventario y reducción de desperdicio para retail
de productos perecederos

Equipo 05 · Proyecto FreshTrack

Avance 2 --- operación con datos reales en PostgreSQL

PostgreSQL 17 · esquemas operacion, analitica, auditoria

Flask 3 · SQLAlchemy 2 · psycopg 3

28 de septiembre de 2026

**Índice**

1.  [[1. Resumen ejecutivo]{.underline}](#resumen-ejecutivo)

2.  [[2. Introducción y
    objetivos]{.underline}](#introducción-y-objetivos)

3.  [[3. Alcance del Avance 2 y criterios de
    aceptación]{.underline}](#alcance-del-avance-2-y-criterios-de-aceptación)

4.  [[4. Arquitectura de la
    solución]{.underline}](#arquitectura-de-la-solución)

5.  [[5. Modelo de datos en
    PostgreSQL]{.underline}](#modelo-de-datos-en-postgresql)

6.  [[6. Seguridad y
    autenticación]{.underline}](#seguridad-y-autenticación)

7.  [[7. Catálogos maestros: CRUD
    reales]{.underline}](#catálogos-maestros-crud-reales)

8.  [[8. Gestión de lotes, vida útil residual y clasificación de
    riesgo]{.underline}](#gestión-de-lotes-vida-útil-residual-y-clasificación-de-riesgo)

9.  [[9. Inventario, consumo FEFO y
    trazabilidad]{.underline}](#inventario-consumo-fefo-y-trazabilidad)

10. [[10. Ventas y mermas]{.underline}](#ventas-y-mermas)

11. [[11. Pronóstico de demanda y medición del
    error]{.underline}](#pronóstico-de-demanda-y-medición-del-error)

12. [[12. Reabastecimiento, transferencias y descuentos con aprobación
    humana]{.underline}](#reabastecimiento-transferencias-y-descuentos-con-aprobación-humana)

13. [[13. Motor de alertas]{.underline}](#motor-de-alertas)

14. [[14. Panel de negocio, desperdicio evitado y
    auditoría]{.underline}](#panel-de-negocio-desperdicio-evitado-y-auditoría)

15. [[15. Evidencia de
    funcionamiento]{.underline}](#evidencia-de-funcionamiento)

16. [[16. Conclusiones, limitaciones y trabajo
    pendiente]{.underline}](#conclusiones-limitaciones-y-trabajo-pendiente)

17. [[Anexo A --- Cómo
    reproducir]{.underline}](#anexo-a-cómo-reproducir)

18. [[Anexo B --- Cuentas de
    demostración]{.underline}](#anexo-b-cuentas-de-demostración)

19. [[Anexo C --- Estructura del
    repositorio]{.underline}](#anexo-c-estructura-del-repositorio)

**Resumen ejecutivo en cifras**

  -----------------------------------------------------------------------
  **Indicador**                                                 **Valor**
  ----------------------------------- -----------------------------------
  Pasos de demostración ejecutados                                 **20**

  Comprobaciones del escenario                                     **61**

  Comprobaciones sin fallos (total)                               **139**

  Pantallas verificadas por rol                                    **73**

  Tablas en PostgreSQL                                             **22**

  Disparadores de auditoría                                        **41**

  Eventos de auditoría registrados                              **8 245**

  Tipos de alerta activos                                           **7**
  -----------------------------------------------------------------------

El flujo principal opera íntegramente contra PostgreSQL: se eliminó el
archivo de datos simulados y toda la operación pasa por la base. La
autenticación valida la contraseña dentro del motor con crypt(), el
consumo de inventario es FEFO y transaccional, el pronóstico se mide con
MAE 6.3049 y WMAPE 11.4650 %, y la persistencia se demuestra reiniciando
la aplicación.

**Reporte Técnico --- FreshTrack · Avance 2**

**Proyecto IAC · Equipo 05**

Sistema de gestión de inventario y reducción de desperdicio para retail
de productos perecederos.

## **1. Resumen ejecutivo**

FreshTrack es una aplicación web que administra inventario perecedero
por lote, consume existencias en orden FEFO, pronostica demanda y
propone reabastecimiento, transferencias y descuentos para reducir
mermas. Este reporte documenta el **Avance 2**, cuyo requisito central
es que **todo lo que se presente como funcional opere con datos reales
almacenados en PostgreSQL**, sin mock_data.py como fuente del flujo
principal.

El resultado del avance se resume en cinco hechos verificables:

1.  **No queda ningún dato simulado en el camino principal.** Los
    catálogos, lotes, existencias, ventas, mermas, alertas, pronósticos,
    órdenes de reabastecimiento y transferencias se leen y escriben en
    PostgreSQL. El archivo app/data/mock_data.py fue eliminado del
    repositorio.

2.  **La autenticación es real.** El login valida la contraseña **dentro
    de PostgreSQL** con crypt(), emite cookie de sesión y token JWT,
    resuelve permisos desde operacion.rol y deja registro en la
    bitácora. La raíz / es una landing pública que no redirige al login.

3.  **La operación es transaccional.** La venta consume lotes con SELECT
    ... FOR UPDATE, descuenta existencias y escribe el kardex en una
    sola transacción. Una merma mayor a la existencia se rechaza sin
    escribir nada.

4.  **La analítica se mide, no se afirma.** El pronóstico se ejecutó
    sobre 60 series producto-tienda con un error **MAE de 6.3049, RMSE
    de 8.9633 y WMAPE de 11.4650 %**, y el error queda persistido en
    analitica.forecast_result.

5.  **La persistencia se demuestra.** El escenario extremo a extremo
    recorre **20 pasos y 61 comprobaciones** a través de la capa HTTP
    real y, en un proceso nuevo, la verificación confirma que toda la
    información sigue existiendo con la aplicación reiniciada. Sumando
    las tres herramientas de verificación, se ejecutaron **139
    comprobaciones sin un solo fallo**.

Como resultado colateral del trabajo se encontró y corrigió un **defecto
de fondo** que hacía que ninguna acción de la aplicación quedara
registrada en la bitácora de auditoría: SQLAlchemy 2.x revierte la
transacción al cerrar un bloque connect(), de modo que las escrituras
lanzadas por esa vía se perdían en silencio. El detalle está en la
sección 15.2.

## **2. Introducción y objetivos**

Este apartado explica por qué el problema importa, qué se propuso el
equipo y qué objetivos concretos persigue el avance.

### **2.1 Contexto**

El desperdicio en retail de perecederos ocurre sobre todo por dos causas
evitables: no consumir primero lo que caduca antes, y no dimensionar las
compras a la demanda real. Ambas son problemas de información: si el
sistema no sabe cuánto queda de cada lote, cuándo vence y cuánto se
vende, no puede decidir.

FreshTrack ataca esas dos causas con un principio de diseño: **la fecha
de caducidad y la vida útil residual son atributos calculados por la
base de datos, no valores precargados**. Todo lo demás --- clasificación
de riesgo, cola FEFO, alertas, pronóstico y reabastecimiento --- se
deriva de ahí.

### **2.2 Objetivo general**

Construir una aplicación web cuyo flujo principal opere íntegramente
contra PostgreSQL, con autenticación real, operación transaccional,
analítica medible y auditoría automática, de modo que la información
sobreviva al reinicio del proceso.

### **2.3 Objetivos específicos**

1.  Sustituir toda fuente de datos simulada por consultas a PostgreSQL.

2.  Implementar autenticación con hash de contraseña, sesión, JWT, roles
    y permisos por pantalla.

3.  Implementar los CRUD reales de productos, proveedores y
    tiendas/CEDIS, con activación y desactivación.

4.  Calcular automáticamente la vida útil residual y clasificar el
    riesgo por lote con umbrales configurables por tipo de producto.

5.  Ejecutar el consumo de inventario en orden FEFO dentro de una
    transacción.

6.  Registrar mermas con causa, validación, descuento de existencia y
    auditoría.

7.  Pronosticar demanda por tienda y por producto sin LSTM, **midiendo
    el error**.

8.  Calcular el reabastecimiento considerando inventario físico, en
    riesgo y útil proyectado, más tiempo de entrega y compra mínima.

9.  Someter reabastecimiento, transferencias y descuentos a aprobación
    humana.

10. Generar alertas a partir de reglas sobre los datos y mantener una
    bitácora de auditoría poblada por disparadores.

### **2.4 Audiencia**

El documento está dirigido al profesor del curso y sirve simultáneamente
como manual de operación para el equipo: cada afirmación incluye el
objeto de base de datos o el comando que permite reproducirla.

## **3. Alcance del Avance 2 y criterios de aceptación**

Antes de describir la solución conviene fijar qué entra y qué no en este
avance, y contra qué criterios se evaluó el resultado.

### **3.1 Alcance**

El Avance 2 comprende la aplicación completa: capa web, capa de dominio,
capa de acceso a datos, esquema de base de datos, carga inicial, motor
analítico y las herramientas de demostración y verificación.

Queda fuera del alcance de este avance el despliegue en infraestructura
de producción, la integración con sistemas de punto de venta reales y el
entrenamiento de modelos de aprendizaje profundo, que se sustituyen
deliberadamente por métodos estadísticos simples y medibles.

### **3.2 Criterios de aceptación y estado**

  ----------------------------------------------------------------------------------------------
  **\#**            **Criterio          **Estado**        **Evidencia**
                    exigido**                             
  ----------------- ------------------- ----------------- --------------------------------------
  1                 Todo el flujo       Cumplido          app/data/mock_data.py eliminado; 22
                    principal opera con                   tablas y 7 vistas en uso
                    datos de PostgreSQL                   

  2                 Login contra        Cumplido          app/security.py ,
                    PostgreSQL con                        operacion.sesion_usuario ,
                    hash, sesión, JWT y                   auditoria.bitacora_eventos
                    roles                                 

  3                 Landing público en  Cumplido          scripts/smoke_rutas.py valida HTTP 200
                    / sin redirección                     y ausencia de campo password
                    al login                              

  4                 CRUD reales de      Cumplido          app/repos/catalogo.py ; pasos 02--04 y
                    productos,                            05 del guion de demostración
                    proveedores y                         
                    tiendas/CEDIS                         

  5                 Inventario          Cumplido          operacion.v_inventario_lote , pantalla
                    consultable                           /inventario
                    producto → tienda →                   
                    lote → caducidad                      

  6                 Vida útil residual  Cumplido          operacion.fn_vida_util_pct() y
                    calculada por el                      v_inventario_lote.dias_restantes
                    sistema                               

  7                 Clasificación de    Cumplido          operacion.regla_riesgo con 7 reglas
                    riesgo con umbrales                   por categoría y por defecto
                    configurables                         

  8                 Inventario real por Cumplido          operacion.existencia ,
                    lote y FEFO                           app/domain/ventas.py con FOR UPDATE
                    transaccional                         

  9                 Registro de merma   Cumplido          operacion.merma , 7 causas en CHECK ,
                    con causa,                            REGISTER_SHRINKAGE en bitácora
                    descuento y                           
                    auditoría                             

  10                Pronóstico contra   Cumplido          analitica.forecast_run /
                    PostgreSQL con                        forecast_result ; MAE 6.3049
                    error medido                          

  11                Pronóstico por      Cumplido          60 series producto-tienda en la última
                    tienda y por                          corrida
                    producto                              

  12                Reabastecimiento    Cumplido          app/domain/reabastecimiento.py ,
                    con stock de                          analitica.orden_reabastecimiento
                    seguridad, útil                       
                    proyectado, lead                      
                    time y MOQ                            

  13                Transferencias con  Cumplido          analitica.transferencia.validaciones
                    4 validaciones                        (jsonb)

  14                Aprobación humana   Cumplido          APPROVE\_ / REJECT\_ en bitácora
                    de                                    
                    reabastecimiento,                     
                    transferencias y                      
                    descuentos                            

  15                7 tipos de alerta   Cumplido          app/domain/alertas.py ; los 7
                    generados por                         verificados en el paso 17 del guion
                    reglas                                

  16                Auditoría real por  Cumplido          41 disparadores; 49 acciones distintas
                    disparadores y                        registradas
                    pantalla de                           
                    bitácora                              

  17                Trazabilidad        Cumplido          analitica.v_trazabilidad_lote , paso
                    completa del lote                     19 del guion

  18                Demostración con    Cumplido          scripts/demo_avance2.py \--verificar
                    reinicio de Flask                     

  19                Reporte técnico     Cumplido          Este documento
                    consolidado                           

  20                Cinco diagramas de  Cumplido          docs/diagramas/ , generados por
                    arquitectura                          scripts/generar_diagramas.py
  ----------------------------------------------------------------------------------------------

## **4. Arquitectura de la solución**

La aplicación sigue el patrón **factoría de aplicación + blueprints** de
Flask, con una separación estricta en cuatro capas: presentación,
dominio, acceso a datos y persistencia. Ninguna plantilla ejecuta SQL y
ningún modelo de dominio conoce el motor HTTP.

### **4.1 Vista de componentes**

![](media/image1.png){width="10.657893700787401in"
height="8.5894728783902in"}

Diagrama de componentes de FreshTrack

La capa de presentación expone la interfaz por blueprints (publico,
auth, catalogo, operacion, analitica, panel, api) y renderiza con Jinja2
apoyándose en un archivo de macros compartido.

La capa de dominio contiene las reglas de negocio puras ---ventas,
inventario, mermas, pronóstico, reabastecimiento, transferencias,
descuentos, alertas y KPIs--- y no importa nada de Flask. La capa de
acceso a datos concentra el motor SQLAlchemy, el repositorio de
catálogos y el módulo de auditoría. La persistencia es PostgreSQL 17 con
tres esquemas.

La regla de dependencia es unidireccional: presentación → dominio →
acceso a datos → persistencia. Esto permite que las herramientas de
línea de comandos (carga inicial, ETL, demostración) reutilicen el mismo
dominio sin levantar el servidor web.

### **4.2 Vista de red y despliegue**

![](media/image2.png){width="10.657893700787401in"
height="6.821052055993001in"}

Diagrama de red y despliegue

En el entorno de desarrollo la aplicación escucha en 127.0.0.1:5000 y
PostgreSQL en el puerto **5433** ---puerto elegido para no colisionar
con una instalación previa en el 5432---. La base se llama
retail_perecederos y tiene la extensión pgcrypto habilitada, que es la
que permite verificar contraseñas dentro del motor.

Para el despliegue con contenedores, el archivo docker-compose.yml
define dos servicios sobre una red bridge interna: freshtrack_app y
freshtrack_db. El servicio de base de datos publica un *healthcheck* con
pg_isready, del que depende el arranque de la aplicación (depends_on:
condition: service_healthy), de modo que la aplicación no intenta
conectarse antes de que el motor acepte conexiones. Los secretos se
inyectan por env_file; **no hay credenciales dentro de la imagen**.

### **4.3 Comunicación entre aplicaciones**

![](media/image3.png){width="10.657893700787401in" height="7.6in"}

Diagrama de comunicación entre aplicaciones

El sistema expone dos vías de acceso sobre los mismos datos:

- **Flujo web con formularios.** El navegador hace GET / o POST /login;
  el servidor consulta PostgreSQL con crypt(:password, u.password_hash)
  = u.password_hash, devuelve una fila de operacion.usuario unida con
  operacion.rol, inserta el identificador del token en
  operacion.sesion_usuario y escribe los eventos de auditoría. Después
  entrega la cookie de sesión, el JWT y la redirección al panel.

- **Vía API JSON.** El cliente solicita un token en POST /api/auth/token
  y luego consume /api/kpis, /api/inventario, /api/alertas y
  /api/pronostico con el encabezado Authorization: Bearer \<JWT\>. La
  API decodifica el token, verifica que su identificador no esté
  revocado y devuelve JSON con los Decimal convertidos a número.

Los procesos por lote ---la carga inicial del esquema, el ETL y el guion
de demostración--- no abren conexiones privilegiadas:
**scripts/demo_avance2.py usa el cliente de pruebas de Flask**, es
decir, atraviesa la capa HTTP real, con las mismas validaciones y los
mismos permisos que un usuario humano.

### **4.4 Autenticación y control de acceso**

![](media/image4.png){width="10.657893700787401in"
height="7.9105260279965in"}

Diagrama de autenticación y control de acceso

El flujo de autenticación aplica las validaciones en un orden
deliberado: primero que el usuario exista, después que no esté
bloqueado, luego que la contraseña coincida y finalmente que
estado_activo sea verdadero. Si alguna falla, se incrementa
intentos_fallidos y al llegar al máximo configurado la cuenta se bloquea
por 15 minutos, dejando registro como LOGIN_FALLIDO.

Cuando las validaciones pasan, el sistema emite **dos credenciales**:
una cookie de sesión firmada con SECRET_KEY y un token **JWT HS256** con
sujeto, rol, identificador y expiración. El identificador del token se
persiste en operacion.sesion_usuario, lo que permite revocarlo antes de
que expire. Los permisos se resuelven en ese momento leyendo
operacion.rol.clave y traduciéndolo a la lista de pantallas permitidas,
con la que se construye el menú y se decide la pantalla inicial.

Cada petición posterior queda protegida por decoradores encadenables:

  -----------------------------------------------------------------------
  **Decorador**                       **Efecto**
  ----------------------------------- -----------------------------------
  login_required                      Exige sesión; sin ella redirige a
                                      /login?next=...

  requiere_vista(\"ventas\")          Exige que el rol tenga esa pantalla
                                      habilitada

  requiere_rol(\"admin\")             Exige uno de los roles indicados

  token_requerido                     Exige Authorization: Bearer \<JWT\>
                                      y valida firma, expiración y
                                      revocación

  rol_en_token(\"admin\")             Restringe las escrituras de la API
                                      por rol
  -----------------------------------------------------------------------

El cierre de sesión ejecuta UPDATE operacion.sesion_usuario SET revocado
= true y registra LOGOUT; a partir de ese momento el token deja de ser
válido aunque no haya expirado.

### **4.5 Almacenamiento de datos**

![](media/image5.png){width="10.657893700787401in"
height="8.5894728783902in"}

Diagrama de almacenamiento de datos

La base se organiza en tres esquemas con responsabilidades disjuntas:

- **operacion** --- el núcleo transaccional: catálogos, lotes,
  existencias, kardex, ventas, mermas y sesiones.

- **analitica** --- los resultados derivados: pronósticos, órdenes de
  reabastecimiento, transferencias, descuentos, alertas, desperdicio
  evitado y configuración.

- **auditoria** --- la bitácora de eventos, inmutable por diseño.

Separar la analítica de la operación evita que un recálculo de
pronóstico bloquee una venta, y permite reconstruir los resultados
analíticos en cualquier momento a partir de los datos operativos, que
son la única fuente de verdad.

## **5. Modelo de datos en PostgreSQL**

El modelo de datos es la pieza sobre la que se apoyan todas las demás,
así que conviene empezar por su tamaño y su organización.

### **5.1 Dimensiones del esquema**

  -----------------------------------------------------------------------
  **Objeto**                          **Cantidad**
  ----------------------------------- -----------------------------------
  Tablas base                         22

  Vistas                              7

  Esquemas                            3

  Restricciones declaradas            290

  Índices                             72

  Disparadores                        41

  Funciones y procedimientos          9
  -----------------------------------------------------------------------

El desglose por esquema es: operacion con 13 tablas y 2 vistas,
analitica con 8 tablas y 4 vistas, y auditoria con 1 tabla y 1 vista.

### **5.2 Inventario de tablas**

  ------------------------------------------------------------------------
  **Esquema**             **Tabla**                **Contenido**
  ----------------------- ------------------------ -----------------------
  operacion               rol                      Los 7 perfiles del
                                                   sistema y su clave

  operacion               usuario                  Credenciales, hash,
                                                   estado activo e
                                                   intentos fallidos

  operacion               sesion_usuario           Identificador de token,
                                                   expiración y revocación

  operacion               producto                 SKU, GTIN, categoría,
                                                   vida útil estándar y
                                                   stock de seguridad

  operacion               proveedor                RFC, razón social,
                                                   tiempo de entrega y
                                                   compra mínima

  operacion               locacion                 Tiendas y CEDIS, con
                                                   bandera de activo

  operacion               lote                     Fechas de producción,
                                                   recepción y caducidad,
                                                   costo y estado

  operacion               existencia               Inventario disponible
                                                   por combinación lote ×
                                                   locación

  operacion               movimiento_inventario    Kardex: recepción,
                                                   venta, merma y
                                                   transferencia

  operacion               venta / venta_detalle    Venta con una línea por
                                                   lote consumido

  operacion               merma                    Causa, cantidad, valor
                                                   calculado y responsable

  operacion               regla_riesgo             Umbrales de
                                                   clasificación por SKU,
                                                   categoría o por defecto

  analitica               forecast_run /           Corrida de pronóstico y
                          forecast_result          su error por serie

  analitica               orden_reabastecimiento   Demanda, stock de
                                                   seguridad, útil y
                                                   necesidad neta

  analitica               transferencia            Origen, destino,
                                                   cantidad y las cuatro
                                                   validaciones

  analitica               descuento                Sugerencia, decisión
                                                   humana y precio
                                                   resultante

  analitica               alerta                   Tipo, severidad,
                                                   mensaje, detalle y
                                                   huella

  analitica               desperdicio_evitado      Ahorro estimado con su
                                                   metodología

  analitica               configuracion            12 parámetros de
                                                   negocio

  auditoria               bitacora_eventos         Acción, tabla,
                                                   registro, usuario,
                                                   estado anterior y nuevo
  ------------------------------------------------------------------------

### **5.3 Restricciones, índices y disparadores**

La integridad se delega al motor siempre que es posible. Las decisiones
relevantes son:

1.  **Identificadores UUID** generados con gen_random_uuid() en las
    entidades que se referencian desde varias tablas, lo que permite
    construir registros completos antes de persistirlos.

2.  **Restricciones CHECK** sobre fechas, cantidades positivas y las
    siete causas de merma válidas, de modo que un valor imposible no
    llegue nunca a la tabla.

3.  **Claves foráneas con ON DELETE RESTRICT** donde la integridad
    importa: no se puede borrar una locación con ventas asociadas, ni un
    lote con existencias.

4.  **Índices para las series de pronóstico** sobre (id_sku,
    id_locacion, fecha) y **para la cola FEFO** sobre (id_sku,
    fecha_caducidad).

5.  **Índices únicos parciales** sobre regla_riesgo que garantizan que
    exista como máximo una regla por categoría, una por SKU y una por
    defecto. Sin ellos, volver a ejecutar la carga inicial duplicaba las
    reglas: el ON CONFLICT DO NOTHING no tenía índice contra el que
    resolver el conflicto.

6.  **Disparadores de auditoría por fila** que escriben en la bitácora
    el estado anterior y el posterior en formato jsonb.

### **5.4 Vistas de negocio**

  -----------------------------------------------------------------------
  **Vista**                           **Propósito**
  ----------------------------------- -----------------------------------
  operacion.v_inventario_lote         Inventario por lote con días
                                      restantes, porcentaje de vida útil
                                      y clasificación

  operacion.v_lote_riesgo             Lote con su proveedor, categoría y
                                      clasificación de riesgo

  analitica.v_demanda_diaria          Serie histórica de demanda agregada
                                      por día, insumo del pronóstico

  analitica.v_merma_agregada          Merma agregada por producto, tienda
                                      y causa

  analitica.v_alerta_abierta          Alertas vigentes con su severidad y
                                      antigüedad

  analitica.v_trazabilidad_lote       Recorrido completo del lote:
                                      recepción, movimientos, ventas y
                                      mermas

  auditoria.v_bitacora                Bitácora con nombres legibles en
                                      lugar de identificadores
  -----------------------------------------------------------------------

## **6. Seguridad y autenticación**

La seguridad se resolvió en dos frentes: dónde se verifica la contraseña
y de dónde salen los permisos de cada usuario.

### **6.1 Verificación de contraseñas dentro del motor**

La contraseña en claro **nunca se compara en Python**. La consulta de
login delega la comparación a PostgreSQL:

crypt(:password, u.password_hash) = u.password_hash

El hash se almacena con crypt() y gen_salt(\'bf\') de pgcrypto. Esta
decisión tiene tres consecuencias favorables: el hash no sale del motor,
no existe una ruta en la aplicación capaz de comparar contraseñas, y
cualquier intento de autenticación queda inevitablemente asociado a una
consulta SQL auditable.

### **6.2 Credenciales fuera del código**

El módulo app/config.py declara DATABASE_URL, SECRET_KEY y
JWT_SECRET_KEY como **variables obligatorias**: si alguna falta, la
aplicación falla al arrancar con un mensaje explícito en lugar de caer a
un valor por defecto embebido. El archivo env.example documenta cada
variable e indica generar los secretos con secrets.token_hex(32).

El script scripts/ETL.py también fue corregido: antes contenía una
cadena de conexión con contraseña embebida como valor por defecto. Ahora
exige que ETL_DATABASE_URL o DATABASE_URL estén definidas y aborta con
un error si no lo están.

### **6.3 Roles de base de datos**

  -----------------------------------------------------------------------
  **Rol**                             **Uso**
  ----------------------------------- -----------------------------------
  postgres                            Administración y creación del
                                      esquema

  app_backend                         Rol de la aplicación: lectura y
                                      escritura sobre los tres esquemas

  app_auditor                         Rol de solo lectura para consulta
                                      de bitácora y mermas

  app_etl                             Rol de la carga masiva, con permiso
                                      para desactivar disparadores
  -----------------------------------------------------------------------

La separación permite que la aplicación web no necesite privilegios de
administración, y que la carga masiva ---que desactiva los disparadores
de auditoría para no generar decenas de miles de eventos de inserción---
use un rol distinto del que sirve las peticiones de los usuarios.

### **6.4 Matriz de permisos**

El sistema define **7 roles** y **20 pantallas**. La matriz se declara
en app/navegacion.py y se aplica en cada petición.

  -----------------------------------------------------------------------
  **Rol**                             **Alcance**
  ----------------------------------- -----------------------------------
  admin                               Todo el sistema: las 20 pantallas

  buyer                               Catálogos, lotes, inventario,
                                      reabastecimiento y trazabilidad

  planner                             Pronóstico, transferencias,
                                      descuentos y analítica de
                                      sostenibilidad

  store_manager                       Operación de la tienda y
                                      **aprobación** de reabastecimiento,
                                      transferencias y descuentos

  warehouse                           Lotes, inventario, cola FEFO y
                                      mermas

  supplier                            Consulta de sus productos y lotes

  auditor                             Bitácora, mermas y desperdicio
                                      evitado, en solo lectura
  -----------------------------------------------------------------------

Las cuentas de demostración se listan en la propia pantalla de login
para facilitar la evaluación, e incluyen un usuario **inactivo** que
sirve para demostrar que el sistema rechaza el acceso de cuentas
deshabilitadas.

## **7. Catálogos maestros: CRUD reales**

Los tres catálogos maestros comparten la misma lógica de alta, edición y
desactivación, con diferencias puntuales que se detallan a continuación.

### **7.1 Productos**

La pantalla /productos permite crear, consultar, editar, desactivar y
reactivar productos. El formulario escribe en operacion.producto y cada
operación deja su evento en la bitácora (CREATE_PRODUCT, UPDATE_PRODUCT,
ACTIVATE_PRODUCT, DEACTIVATE_PRODUCT).

Dos decisiones merecen mención porque corrigen defectos detectados
durante las pruebas:

- **Normalización del GTIN.** El código original truncaba y rellenaba el
  GTIN con ceros a la derecha, de modo que 7503000000001 se convertía en
  75030000000010, alterando el identificador. La corrección usa
  zfill(14), que rellena **por la izquierda** como corresponde a un
  GTIN-14. Cuando el usuario no captura código, el sistema genera uno
  automáticamente.

- **Normalización del RFC.** El código original recortaba a 13
  caracteres y rellenaba con X, transformando DEM260101ABC en
  DEM260101ABCX. Ahora el RFC se valida contra el formato oficial y se
  rechaza si no lo cumple, en lugar de alterarlo en silencio.

### **7.2 Proveedores**

La pantalla /proveedores administra razón social, RFC, correo de
contacto, teléfono y dos atributos que el motor de reabastecimiento
necesita: **tiempo de entrega en días** (lead_time_dias) y **compra
mínima** (moq). Sin ellos, la necesidad neta calculada por el sistema no
sería ejecutable.

### **7.3 Tiendas y CEDIS**

La pantalla /tiendas administra locaciones con bandera de activo. La
distinción entre tienda y CEDIS es relevante porque las transferencias
se proponen entre locaciones y porque la demanda se analiza por tienda.

### **7.4 Desactivación en lugar de borrado**

Los catálogos se desactivan, no se borran. Un producto con historial de
ventas no puede eliminarse sin destruir la trazabilidad, y una locación
con existencias no puede eliminarse por la restricción ON DELETE
RESTRICT. La bandera activo permite retirar un elemento de circulación
preservando el histórico.

## **8. Gestión de lotes, vida útil residual y clasificación de riesgo**

El lote es la unidad de trabajo del sistema: casi todas las decisiones
posteriores dependen de su fecha de caducidad y de la vida útil que le
queda.

### **8.1 Recepción de lotes**

La pantalla /lotes registra una recepción completa: producto, proveedor,
locación de destino, código de lote del proveedor, fechas de producción,
recepción y caducidad, cantidad y costo unitario. El alta escribe en una
sola transacción el lote, su existencia inicial y el movimiento de
kardex correspondiente, y deja tres eventos en la bitácora:
CREATE_BATCH, CREATE_INVENTORY y RECEIVE_INVENTORY.

El sistema valida antes de escribir: la cantidad debe ser mayor que
cero, la caducidad debe ser posterior a la recepción y la producción no
puede ser posterior a la recepción.

### **8.2 Vida útil residual calculada**

La vida útil residual **no se almacena**: se calcula. La vista
operacion.v_inventario_lote expone dias_restantes como fecha_caducidad -
CURRENT_DATE y vida_util_pct mediante la función
operacion.fn_vida_util_pct(), que relaciona los días restantes con la
vida útil total del lote ---desde producción hasta caducidad--- o con la
vida útil estándar del producto cuando no se registró fecha de
producción.

Que sea un valor calculado es lo que hace que el sistema sea correcto:
un lote no cambia de estado por una actualización programada, sino
porque el paso del tiempo cambia el resultado de la resta.

### **8.3 Clasificación automática de riesgo**

La función operacion.fn_clasificar_riesgo() traduce los días restantes y
el porcentaje de vida útil a cuatro estados:

  -----------------------------------------------------------------------
  **Estado**              **Significado**         **Acción esperada**
  ----------------------- ----------------------- -----------------------
  NORMAL                  Vida útil suficiente    Sin acción

  VIGILANCIA              Se acerca al umbral     Vigilar rotación

  CRITICO                 Riesgo inminente de     Descuento o
                          merma                   transferencia

  VENCIDO                 Ya caducó               Baja del inventario
  -----------------------------------------------------------------------

Los umbrales **no están en el código**: viven en operacion.regla_riesgo
y se resuelven por especificidad decreciente ---primero por SKU, luego
por categoría, finalmente la regla por defecto---. La tabla cargada
contiene siete reglas:

  ---------------------------------------------------------------------------
  **Categoría**   **Días para    **Días para    **% de vida    **% de vida
                  vigilancia**   crítico**      para           para crítico**
                                                vigilancia**   
  --------------- -------------- -------------- -------------- --------------
  Carnes          2              1              40 %           20 %

  Panadería       2              1              40 %           20 %

  Lácteos         4              2              25 %           10 %

  Frutas          3              1              25 %           10 %

  Verduras        3              1              30 %           15 %

  Abarrotes       15             5              20 %           5 %

  Por defecto     5              2              30 %           10 %
  ---------------------------------------------------------------------------

La consecuencia práctica es que un mismo número de días restantes
produce clasificaciones distintas según el producto: dos días son
críticos para un cárnico y normales para un abarrote. Eso es exactamente
lo que la rúbrica pedía al exigir umbrales configurables por tipo de
producto.

## **9. Inventario, consumo FEFO y trazabilidad**

Una vez que el sistema sabe cuánto queda de cada lote y cuándo vence,
puede decidir en qué orden consumirlo y cómo reconstruir su historia.

### **9.1 Inventario consultable en cuatro niveles**

La pantalla /inventario permite recorrer la jerarquía **producto →
tienda → lote → fecha de caducidad**, con los días restantes y la
clasificación de riesgo de cada lote. La consulta se resuelve contra
operacion.v_inventario_lote, que une lote, producto, locación y
existencia.

### **9.2 Descomposición del inventario en tres valores**

El motor analítico distingue tres lecturas del mismo inventario, y la
distinción es la base de todo el cálculo de reabastecimiento:

- **Inventario físico** --- la suma de existencia.cantidad_disponible.
  Es lo que hay en el anaquel.

- **Inventario en riesgo** --- la parte que probablemente no se venda
  antes de caducar. Se estima por lote como el excedente sobre cinco
  días de demanda diaria.

- **Inventario útil proyectado** --- la diferencia entre los dos
  anteriores. Es lo que realmente puede satisfacer demanda futura.

Un sistema que reabastece usando el inventario físico compra de más
justo cuando ya tiene producto en riesgo de vencerse. Esa es la razón de
separar los tres valores.

### **9.3 Consumo FEFO transaccional**

La venta consume primero el lote que caduca antes. La operación abre una
transacción y bloquea las filas con SELECT ... FOR UPDATE antes de
decidir cuánto tomar de cada lote, lo que evita que dos ventas
simultáneas descuenten la misma existencia.

La secuencia dentro de una sola transacción es: seleccionar los lotes
ordenados por fecha de caducidad con bloqueo de fila, descontar la
cantidad de cada lote hasta cubrir la venta, insertar una línea de
detalle por cada lote consumido y escribir el movimiento de kardex. Si
algo falla, todo se revierte.

El guion de demostración comprueba este comportamiento de forma
explícita: se reciben dos lotes del mismo producto ---uno que caduca en
cinco días y otro en veinte--- y luego se vende una cantidad que cabe en
el primero. El sistema debe consumir el lote próximo a vencer y dejar
intacto el otro.

### **9.4 Trazabilidad del lote**

La pantalla /trazabilidad reconstruye la vida completa de un lote a
partir de analitica.v_trazabilidad_lote y del kardex: proveedor de
origen, recepción, locación, existencia actual, ventas FEFO que lo
consumieron, transferencias en las que participó, mermas registradas y
estado final. La verificación del guion comprueba que el kardex
reconstruye la aritmética del lote: lo recibido menos lo vendido menos
lo mermado es igual a lo que queda.

## **10. Ventas y mermas**

Las ventas y las mermas son las dos únicas operaciones que reducen
inventario, y por eso ambas están sujetas a las mismas garantías
transaccionales.

### **10.1 Registro de ventas**

La pantalla /ventas registra una venta por locación y producto. El
sistema resuelve internamente qué lotes consumir aplicando FEFO y deja
el rastro completo: cabecera de venta, una línea por lote, movimientos
de kardex y evento REGISTER_SALE en la bitácora.

### **10.2 Registro de mermas**

La pantalla /mermas registra una merma indicando locación, lote,
cantidad, causa y observación. El flujo exigido ---validar, registrar,
descontar y auditar--- se cumple íntegramente:

1.  **Validar.** El sistema comprueba que exista la cantidad suficiente
    en ese lote y esa locación. Si la merma excede la existencia, la
    operación se rechaza y **no se escribe nada**.

2.  **Registrar.** Se inserta la fila en operacion.merma con la causa,
    la cantidad y el usuario responsable.

3.  **Descontar.** Se reduce existencia.cantidad_disponible y se escribe
    el movimiento de kardex.

4.  **Auditar.** Los disparadores y el módulo de auditoría dejan
    CREATE_SHRINKAGE y REGISTER_SHRINKAGE en la bitácora.

El **valor de la merma no se captura**: la base lo calcula a partir del
costo unitario del lote, de modo que no puede declararse un valor
distinto al que corresponde.

Las siete causas admitidas, restringidas por una restricción CHECK, son:
CADUCIDAD, DAÑO, CALIDAD, CADENA_DE_FRÍO, MANIPULACIÓN, DEVOLUCIÓN y
OTRA.

### **10.3 Por qué el mensaje de confirmación importa**

Un mensaje que dice «merma registrada correctamente» sin que exista la
fila correspondiente es peor que un error: produce confianza falsa. Por
eso el guion de demostración no se conforma con leer el mensaje en
pantalla ---consulta la base después de cada acción y compara la
existencia antes y después. En el paso correspondiente se verifica que
la merma descuente exactamente la cantidad registrada y que un intento
de merma imposible deje el conteo de filas inalterado.

## **11. Pronóstico de demanda y medición del error**

Pronosticar bien no consiste en elegir el modelo más sofisticado, sino
en poder demostrar cuánto se equivoca el que se eligió.

### **11.1 Decisión metodológica**

El primer pronóstico **no usa LSTM**. Usa métodos estadísticos simples,
por tres razones: son explicables ante el profesor, son auditables
---cada número se puede recalcular a mano---, y sobre todo **se pueden
medir**. Un modelo complejo que no se mide es un pasivo, no un activo.

Los métodos disponibles son media móvil, media móvil ponderada y
suavización exponencial. El método por defecto es
SUAVIZACION_EXPONENCIAL con factor alpha = 0.30, ambos parámetros
configurables desde analitica.configuracion.

### **11.2 Cómo se construye el pronóstico**

El pronóstico **desestacionaliza por día de la semana** antes de
promediar, porque la demanda de perecederos tiene un patrón semanal
marcado y promediar sin corregirlo produce un sesgo sistemático.

El cálculo es obligatoriamente **por tienda y por producto**: cada serie
es una combinación (id_sku, id_locacion). Una serie necesita al menos 14
días con ventas para ser pronosticable, umbral también configurable.

Cada corrida persiste en dos tablas: analitica.forecast_run con el
método, los parámetros, el periodo, el horizonte, el usuario y las
métricas globales, y analitica.forecast_result con el valor
pronosticado, el valor real y el error absoluto de cada serie y cada día
del horizonte.

### **11.3 Medición del error**

El sistema calcula tres métricas mediante validación hacia adelante:
**MAE** (error absoluto medio), **RMSE** (raíz del error cuadrático
medio) y **WMAPE** (error porcentual absoluto ponderado por volumen).

La última corrida verificada produjo:

  -----------------------------------------------------------------------
  **Métrica**                         **Valor**
  ----------------------------------- -----------------------------------
  Método                              SUAVIZACION_EXPONENCIAL

  Series pronosticadas                60

  Horizonte                           7 días

  Periodo de historia                 2026-05-31 a 2026-09-28

  MAE                                 6.3049

  RMSE                                8.9633

  WMAPE                               11.4650 %

  Duración                            161 ms
  -----------------------------------------------------------------------

Leído en términos operativos, un WMAPE de 11.4650 % significa que por
cada 100 unidades que se venderán, el pronóstico se desvía del orden de
11 unidades. Ese margen es la referencia para dimensionar el stock de
seguridad: un colchón de dos días de demanda solo es suficiente si
absorbe ese nivel de desviación.

El número no es una calificación decorativa ---es el insumo que permite
decidir si el colchón alcanza--- y queda almacenado junto con la corrida
que lo produjo, de modo que cualquier afirmación posterior sobre la
calidad del pronóstico se pueda contrastar contra la corrida que la
respalda.

## **12. Reabastecimiento, transferencias y descuentos con aprobación humana**

El reabastecimiento, las transferencias y los descuentos son las tres
decisiones donde el sistema propone y una persona dispone.

### **12.1 Cálculo de la necesidad neta**

El motor de reabastecimiento no responde a la pregunta «¿cuánto vendí?»
sino a «¿cuánto me falta para cubrir la demanda futura sin comprar de
más?». La fórmula implementada es:

necesidad_neta = demanda_pronosticada + stock_seguridad\
− inventario_útil − entradas_confirmadas

Cada término tiene una razón de ser:

- **Demanda pronosticada** --- el consumo esperado durante el horizonte,
  tomado de analitica.forecast_result.

- **Stock de seguridad** --- un colchón de dos días de demanda,
  configurable.

- **Inventario útil** --- el inventario físico menos el que está en
  riesgo de vencerse, no el inventario físico completo.

- **Entradas confirmadas** --- lo que ya está pedido y por llegar.
  Omitirlo es el error clásico que hace que el sistema compre dos veces
  lo mismo.

Cuando la necesidad neta es positiva, el sistema la ajusta a la **compra
mínima del proveedor** (moq) y la redondea hacia arriba; cuando es
negativa o nula, no genera orden.

El sistema reporta además el **tiempo de entrega** (lead_time_dias) del
proveedor, porque una necesidad que se cubre después de que el producto
se agote no resuelve el problema.

Ambos atributos viven en operacion.proveedor y varían por proveedor. Los
valores cargados en la base de referencia son:

  -----------------------------------------------------------------------
  **Proveedor**           **Tiempo de entrega**   **Compra mínima**
  ----------------------- ----------------------- -----------------------
  Frutas del Bajío        1 día                   100 unidades

  Verduras Frescas del    1 día                   80 unidades
  Rancho                                          

  Panificadora Artesanal  1 día                   60 unidades

  Distribuidora Demo      2 días                  60 unidades
  Avance 2                                        

  Lácteos del Norte       3 días                  50 unidades

  Carnes Refrigeradas del 3 días                  40 unidades
  Norte                                           

  Abarrotes del Centro    5 días                  200 unidades
  -----------------------------------------------------------------------

La diferencia entre proveedores es la que obliga a que el cálculo sea
por proveedor y no global: una necesidad de 55 unidades se convierte en
un pedido de 100 si el proveedor es Frutas del Bajío, y en uno de 60 si
es la Distribuidora Demo. Para el producto de demostración ---cuya
compra mínima es de 60 unidades y cuyo tiempo de entrega es de 2 días---
una necesidad neta de 55 unidades se redondea a 60, y la orden solo
tiene sentido si el producto no se agota en esos dos días.

La pantalla /reabastecimiento muestra el desglose completo de cada orden
---demanda, stock de seguridad, inventario útil, entradas confirmadas y
necesidad neta--- de modo que el gerente que aprueba puede ver de dónde
sale el número en lugar de aceptarlo por autoridad del sistema.

### **12.2 Detección de sobreinventario y riesgo por lote**

Dos análisis complementan al reabastecimiento y son, para este proyecto,
más importantes que cualquier modelo de aprendizaje profundo:

- **Sobreinventario.** Cuando la cobertura del inventario útil supera el
  umbral configurado ---21 días por defecto--- el sistema advierte que
  el producto dura menos de lo que tardaría en venderse, y por tanto que
  parte se va a vencer.

- **Riesgo por lote.** Para cada lote con existencia, el motor estima
  cuánto probablemente no alcance a venderse antes de su caducidad. Es
  el insumo directo de las alertas de riesgo de merma y de las
  sugerencias de descuento y transferencia.

### **12.3 Transferencias entre tiendas**

Una transferencia mueve producto de donde sobra a donde falta. El motor
de detección no aplica una regla simple: somete cada par origen-destino
candidato a **cuatro validaciones**, y solo propone la transferencia si
las cuatro se cumplen.

  -----------------------------------------------------------------------
  **\#**                  **Validación**          **Pregunta**
  ----------------------- ----------------------- -----------------------
  1                       Existencia en origen    ¿La tienda de origen
                                                  tiene suficiente
                                                  excedente?

  2                       Necesidad en destino    ¿La tienda de destino
                                                  realmente lo necesita?

  3                       Vida útil suficiente    ¿El producto llega
                                                  antes de caducar?

  4                       Capacidad de consumo    ¿El destino alcanza a
                                                  venderlo antes de que
                                                  venza?
  -----------------------------------------------------------------------

El resultado de las cuatro validaciones se guarda en la columna
validaciones de tipo jsonb, lo que permite ver por qué se propuso ---o
por qué se descartó--- cada par. La transferencia no se ejecuta sola:
queda en estado pendiente hasta que una persona la aprueba, y solo
entonces se descuentan existencias del origen e incrementan en el
destino.

Un hallazgo relevante de las pruebas: al principio el motor no proponía
ninguna transferencia. La causa no era un defecto de la detección sino
de los datos de prueba.

El cálculo de excedente descuenta cinco días de demanda por lote, de
modo que **una sola recepción nunca produce excedente**; y si la tienda
de origen no vende el producto, todo su inventario cuenta como riesgo y
su inventario útil es cero. La condición real para que exista un
excedente transferible es que la tienda de origen venda el producto y
tenga varias recepciones.

### **12.4 Descuentos**

Para lotes clasificados como VIGILANCIA o CRITICO, el sistema sugiere un
descuento con un porcentaje configurable ---15 % y 30 %
respectivamente--- y calcula el ingreso potencial de venderlo con
descuento frente a perderlo completo. La sugerencia **no se aplica
automáticamente**: requiere aprobación humana, y la aprobación queda
auditada como APPROVE_DISCOUNT.

### **12.5 Por qué la aprobación humana es un requisito y no una formalidad**

Las tres decisiones ---reabastecer, transferir y descontar--- mueven
dinero. El sistema propone porque puede procesar más información que una
persona; la persona decide porque responde por el resultado. La
separación se implementa en los hechos: el estado de una orden, una
transferencia o un descuento no cambia sin un evento de aprobación
registrado con el usuario que lo autorizó.

## **13. Motor de alertas**

El motor de alertas no almacena avisos: los deriva cada vez que se
ejecuta, a partir del estado real de los datos.

### **13.1 Las alertas se derivan, no se capturan**

No existe una pantalla para crear alertas. El motor las recalcula cada
vez que alguien entra a la pantalla o pulsa «Regenerar», aplicando
reglas sobre el inventario, el pronóstico y las órdenes pendientes. Cada
alerta lleva una **huella** única y un índice único parcial sobre la
huella mientras la alerta esté abierta, lo que impide duplicados sin
impedir que una misma causa vuelva a alertar después de haberse cerrado.

### **13.2 Los siete tipos**

  ----------------------------------------------------------------------------
  **Tipo**                     **Se dispara cuando**   **Severidad**
  ---------------------------- ----------------------- -----------------------
  LOTE_POR_VENCER              Un lote con existencia  Alta o media
                               está en vigilancia o    
                               crítico                 

  LOTE_VENCIDO                 Un lote con existencia  Crítica
                               ya caducó               

  RIESGO_DE_MERMA              Se estima que parte de  Alta
                               un lote no alcanzará a  
                               venderse                

  SOBREINVENTARIO              La cobertura útil       Media
                               supera el umbral de     
                               días                    

  RIESGO_DE_FALTANTE           La cobertura cae por    Alta
                               debajo del stock de     
                               seguridad               

  REABASTECIMIENTO_REQUERIDO   Existe una orden con    Media
                               necesidad neta positiva 

  TRANSFERENCIA_SUGERIDA       Existe una              Media
                               transferencia propuesta 
                               y no decidida           
  ----------------------------------------------------------------------------

### **13.3 Un caso que obligó a revisar los datos de prueba**

Durante la validación se detectó que solo cinco de los siete tipos
llegaban a generarse. La revisión del motor descartó un defecto de
implementación: los siete estaban correctamente programados y admitidos
por la restricción de la tabla. La causa era la naturaleza de los datos.

Un almacén bien administrado no tiene lotes caducados con existencia, y
por definición no tiene sobreinventario. LOTE_VENCIDO exige un lote cuya
fecha de caducidad ya pasó y que todavía conserva unidades;
SOBREINVENTARIO exige una cobertura que supera el umbral. Ninguna de las
dos condiciones se cumple en una operación sana, y ninguna se puede
provocar creando una recepción nueva, porque el sistema
---correctamente--- impide recibir mercancía ya caducada.

La solución adoptada fue incorporar al guion de demostración un paso que
carga los dos casos extremos mediante **recepciones históricas reales**:
un lote recibido hace veinte días y caducado hace tres, y tres
recepciones adicionales en una tienda con demanda insuficiente para
absorberlas. Las alertas no se inyectan: las deriva el motor a partir de
esos datos. El paso 17 del guion verifica que los siete tipos aparezcan,
y en la corrida de referencia se generaron 108 alertas abiertas.

## **14. Panel de negocio, desperdicio evitado y auditoría**

El panel reúne los indicadores que resumen la operación, y la auditoría
registra quién hizo qué para llegar a ellos.

### **14.1 Panel de control**

La pantalla /panel presenta los indicadores de negocio calculados contra
PostgreSQL. En la última verificación mostraba:

  -----------------------------------------------------------------------
  **Indicador**                       **Valor**
  ----------------------------------- -----------------------------------
  Unidades de inventario              12 116.86

  Unidades vendidas (histórico)       530 183.39

  Unidades mermadas (histórico)       7 924.54

  Órdenes de reabastecimiento         75

  Transferencias ejecutadas           6

  Alertas abiertas                    108

  Corridas de pronóstico completadas  19
  -----------------------------------------------------------------------

Las cifras anteriores se obtuvieron por consulta directa a PostgreSQL el
28 de septiembre de 2026, al cierre del escenario de demostración; no
son valores de referencia escritos a mano. Crecen con cada ejecución del
guion, de modo que un lector que reproduzca los comandos verá números
iguales o mayores.

Complementan al panel las pantallas de sostenibilidad y de desperdicio
evitado, y la pantalla de configuración, que expone los 12 parámetros de
negocio:

  ----------------------------------------------------------------------------------
  **Parámetro**                    **Valor**                 **Efecto**
  -------------------------------- ------------------------- -----------------------
  metodo_pronostico_default        SUAVIZACION_EXPONENCIAL   Método usado si no se
                                                             especifica otro

  alpha_suavizacion                0.30                      Peso del dato más
                                                             reciente

  ventana_media_movil              28                        Días de historia de la
                                                             media móvil

  horizonte_pronostico_dias        7                         Días que se pronostican

  min_dias_historia_pronostico     14                        Mínimo de días con
                                                             ventas para pronosticar

  dias_ventana_riesgo_lote         5                         Días de demanda que se
                                                             consideran seguros por
                                                             lote

  umbral_sobreinventario_dias      21                        Cobertura a partir de
                                                             la cual hay
                                                             sobreinventario

  cobertura_stock_seguridad_dias   2                         Días que cubre el stock
                                                             de seguridad

  descuento_pct_vigilancia         15                        Descuento sugerido en
                                                             vigilancia

  descuento_pct_critico            30                        Descuento sugerido en
                                                             crítico

  max_intentos_login               5                         Intentos antes de
                                                             bloquear la cuenta

  jwt_horas_vigencia               8                         Vigencia del token
  ----------------------------------------------------------------------------------

### **14.2 Desperdicio evitado y su metodología**

El indicador de desperdicio evitado registra el valor del producto que
**no** se perdió gracias a una acción del sistema: una transferencia que
colocó el excedente donde había demanda, o un descuento que liquidó un
lote antes de que caducara.

La parte crítica no es el número sino la metodología, que queda
almacenada junto al registro. Cada entrada documenta qué acción la
originó, qué cantidad se movió, a qué precio y con qué supuesto de
venta. Un ahorro sin metodología explícita es una cifra decorativa; con
metodología, es una afirmación que el profesor puede refutar.

### **14.3 Auditoría**

La bitácora auditoria.bitacora_eventos se puebla por dos vías
complementarias: **disparadores por fila** que registran el estado
anterior y el nuevo en formato jsonb para los cambios de datos, y el
**módulo de auditoría de la aplicación** para las acciones que no
corresponden a una fila única ---un inicio de sesión, una ejecución de
pronóstico, una aprobación---.

La bitácora es **inmutable por diseño**: un disparador
trg_proteger_bitacora bloquea cualquier UPDATE o DELETE. La única forma
de escribir en ella es insertar.

Las acciones exigidas por la rúbrica están todas presentes, con estos
conteos en la base de referencia:

  --------------------------------------------------------------------------------
  **Acción**           **Registros**     **Acción**              **Registros**
  -------------------- ----------------- ----------------------- -----------------
  LOGIN                194               CREATE_TRANSFER         24

  LOGOUT               170               APPROVE_TRANSFER        12

  LOGIN_FALLIDO        2                 EXECUTE_TRANSFER        11

  CREATE_PRODUCT       47                CREATE_DISCOUNT         50

  UPDATE_PRODUCT       52                APPROVE_DISCOUNT        13

  ACTIVATE_PRODUCT     13                RUN_FORECAST            17

  DEACTIVATE_PRODUCT   13                RUN_ALERTS              51

  CREATE_SUPPLIER      41                CREATE_REPLENISHMENT    88

  CREATE_LOCATION      42                APPROVE_REPLENISHMENT   13

  CREATE_BATCH         63                REJECT_REPLENISHMENT    13

  RECEIVE_INVENTORY    63                REGISTER_SALE           22

  REGISTER_SHRINKAGE   17                CREATE_USER             9
  --------------------------------------------------------------------------------

En total la bitácora contiene **8 245 eventos** y **49 acciones
distintas**.

La pantalla /auditoria consulta esa tabla y permite filtrar por acción,
usuario y fecha, de modo que la auditoría no es solo un mecanismo de
escritura sino una capacidad de consulta verificable.

## **15. Evidencia de funcionamiento**

Esta sección reúne las herramientas con las que se comprobó el sistema,
y el defecto de fondo que esa comprobación reveló.

### **15.1 Guion de demostración extremo a extremo**

El script scripts/demo_avance2.py recorre el sistema completo **a través
de la capa HTTP real**, usando el cliente de pruebas de Flask. No
manipula la base directamente: inicia sesión, envía formularios y sigue
redirecciones, exactamente como lo haría un usuario. Tras cada paso,
**consulta la base y compara**; si un paso no escribe lo que debía, el
script lo reporta como fallo y termina con código de salida distinto de
cero.

El guion consta de **20 pasos**:

  -----------------------------------------------------------------------
  **\#**                  **Paso**                **Qué comprueba**
  ----------------------- ----------------------- -----------------------
  01                      El administrador inicia Login contra PostgreSQL
                          sesión                  y evento LOGIN en la
                                                  bitácora

  02                      Alta de un proveedor    Inserción real en
                                                  operacion.proveedor

  03                      Alta de un producto     Inserción real y
                          ligado al proveedor     generación de GTIN

  04                      Edición, desactivación  CRUD completo y
                          y reactivación del      UPDATE_PRODUCT auditado
                          producto                

  05                      Alta de una tienda      Inserción real en
                                                  operacion.locacion

  06                      Dos recepciones del     Lote, existencia y
                          mismo producto          kardex

  07                      Cálculo de vida útil y  Lote crítico y lote
                          clasificación de riesgo normal, con umbrales de
                                                  la tabla

  08                      Venta de 70 unidades    FEFO consume primero el
                                                  lote que caduca antes

  09                      Ejecución del           Corrida persistida con
                          pronóstico              sus métricas de error

  10                      Cálculo del             La necesidad neta
                          reabastecimiento        cuadra con la fórmula

  11                      Aprobación y rechazo de Decisión humana
                          órdenes                 auditada

  12                      Transferencia entre     Cuatro validaciones y
                          tiendas                 ejecución con descuento
                                                  e incremento

  13                      Aprobación y ejecución  Movimiento real de
                          de la transferencia     existencias

  14                      Descuento con           Precio resultante y
                          aprobación              APPROVE_DISCOUNT

  15                      Registro de una merma   Descuento de existencia
                                                  y rechazo de la merma
                                                  imposible

  16                      Carga de los casos      Lote vencido y
                          extremos                sobreinventario

  17                      Generación de alertas   Los siete tipos
                                                  presentes

  18                      Panel de control        Indicadores contra la
                                                  base

  19                      Trazabilidad del lote   Kardex reconstruye la
                                                  aritmética del lote

  20                      API JSON con JWT        Cuatro endpoints con
                                                  token y rechazo sin
                                                  token
  -----------------------------------------------------------------------

Resultado de la última ejecución completa: **20 pasos, 61
comprobaciones, 0 fallos**. El script termina con código de salida cero
solo si ninguna comprobación falla.

A esas 61 comprobaciones se suman las de las otras dos herramientas de
verificación:

  -----------------------------------------------------------------------
  **Herramienta**         **Comprobaciones**      **Resultado**
  ----------------------- ----------------------- -----------------------
  demo_avance2.py         61                      0 fallos
  \--escenario                                    

  demo_avance2.py         5                       0 fallos
  \--verificar                                    

  smoke_rutas.py          73 pantallas            0 fallos
  -----------------------------------------------------------------------

En total, **139 comprobaciones ejecutadas sin fallos** sobre la misma
base de datos.

### **15.2 El defecto de fondo que se encontró y corrigió**

La revisión de la bitácora mostró un dato imposible: **6 308 eventos
registrados y ni un solo LOGIN**. Las acciones de aplicación no se
estaban guardando.

La causa se localizó con una prueba directa. Se ejecutó la función de
registro a través del ayudante escalar() y se midió el conteo de filas
antes y después:

antes: 6308 → después: 6308

La función devolvía un identificador válido pero **la fila no existía**.
El motivo es una semántica de SQLAlchemy 2.x que es fácil pasar por
alto: al cerrar un bloque engine.connect(), la transacción se
**revierte**. El ayudante usado hasta entonces para escribir abría la
conexión con connect(), de modo que cada escritura se deshacía
silenciosamente al salir del bloque ---sin excepción, sin advertencia,
sin error---.

La corrección consistió en añadir un ayudante explícito que abre la
transacción con engine.begin(), que sí confirma, y en migrar a él todo
el código de escritura:

  -----------------------------------------------------------------------
  **Ayudante**      **Apertura**      **Semántica**     **Uso**
  ----------------- ----------------- ----------------- -----------------
  query / one /     connect()         Revierte al salir Solo lectura
  escalar                                               

  escribir          begin()           Confirma al salir Toda escritura
  -----------------------------------------------------------------------

El mismo defecto afectaba a la limpieza del guion de demostración, que
borraba registros sin borrar nada y dejaba residuos entre corridas, y a
la verificación del alta de mermas. Corregido el ayudante, la
verificación pasó de antes: 0 → después: 1 y la bitácora empezó a
registrar las acciones de aplicación.

Este hallazgo es, en la práctica, el resultado más formativo del avance:
**una operación que no falla y no escribe es más peligrosa que una que
falla**, porque produce la apariencia de funcionar. Fue el contraste
entre el número devuelto y el número de filas lo que lo reveló.

### **15.3 Verificación de persistencia con Flask reiniciado**

El requisito de la demostración es cerrar Flask, volver a iniciarlo y
comprobar que la información sigue existiendo. El script lo resuelve con
una segunda orden que se ejecuta **en un proceso nuevo**, después de que
el primero terminó:

python scripts/demo_avance2.py \--verificar

La verificación relee todo desde PostgreSQL sin Flask en memoria y
confirma:

- Los conteos de cada tabla (productos, lotes, existencias, movimientos,
  ventas, mermas, pronósticos, órdenes, transferencias, alertas y
  eventos de auditoría).

- La presencia del producto, el proveedor y los lotes del escenario de
  demostración.

- La última corrida de pronóstico con su MAE y su WMAPE.

- Los últimos eventos de la bitácora, con marca de tiempo.

- Que las rutas privadas sigan protegidas: GET /inventario sin sesión
  devuelve **HTTP 302** hacia /login?next=/inventario.

- Que las rutas privadas respondan con datos después del reinicio:
  /panel, /inventario y /lotes devuelven **HTTP 200**, y el producto de
  la demostración aparece en el inventario.

### **15.4 Prueba de humo de todas las pantallas**

El script scripts/smoke_rutas.py inicia sesión con cada uno de los 7
roles y solicita **todas las pantallas que ese rol tiene permitidas**:
73 peticiones en total.

El resultado es que las 73 pantallas responden **HTTP 200** con el rol
que tiene permiso, la landing pública responde 200 sin exponer un campo
de contraseña, y las rutas privadas devuelven 302 para un visitante
anónimo. Esto comprueba simultáneamente que las plantillas renderizan
sin error con datos reales y que la matriz de permisos no tiene
agujeros.

### **15.5 Construcción desde cero e idempotencia**

El script scripts/bootstrap_db.py crea la base de datos si no existe,
crea o actualiza los cuatro roles de conexión y ejecuta en orden los
siete archivos SQL del esquema, verificando al final la existencia de 16
objetos clave.

La carga inicial de datos se realiza con scripts/ETL.py, que en una base
nueva deja **746 lotes, 1 860 ventas, 2 424 líneas de venta, 96 mermas y
3 266 movimientos de kardex**.

Ambos scripts son idempotentes. La idempotencia del esquema exigió
añadir los tres índices únicos parciales sobre regla_riesgo: sin ellos,
volver a ejecutar la carga duplicaba las reglas de riesgo ---de 7 a
13---. Con los índices, tres ejecuciones consecutivas dejan el conteo
estable en 7.

### **15.6 Trazabilidad de la infraestructura**

El archivo docker-compose.yml fue reescrito para dejar únicamente los
dos servicios que el sistema realmente usa. Los servicios de MongoDB y
Redis que contenía fueron eliminados tras comprobar por búsqueda en el
código que **no había una sola referencia** a ninguno de los dos.

De forma análoga, tres archivos SQL que eran volcados de un esquema
obsoleto se movieron a sql/legacy/: al estar en el directorio de
inicialización de PostgreSQL, su orden de ejecución rompía la creación
del esquema desde cero en un contenedor nuevo.

## **16. Conclusiones, limitaciones y trabajo pendiente**

El cierre del avance separa lo que quedó demostrado de lo que todavía
no, y deja por escrito lo que falta.

### **16.1 Conclusiones**

1.  **El requisito central está cumplido y es verificable.** El flujo
    principal no usa datos simulados. El archivo de datos de ejemplo fue
    eliminado y las 22 tablas se pueblan por operaciones reales a través
    de la capa HTTP.

<!-- -->

1.  **La decisión de calcular la vida útil en la base y no almacenarla**
    resultó ser la que sostiene todo lo demás. Clasificación de riesgo,
    alertas, riesgo por lote, FEFO y reabastecimiento son consecuencias
    de ese cálculo, no módulos independientes.

<!-- -->

1.  **Separar el inventario en físico, en riesgo y útil** cambió el
    comportamiento del reabastecimiento. Es la diferencia entre reponer
    por lo que hay y reponer por lo que sirve.

<!-- -->

1.  **Medir el error del pronóstico** fue más valioso que mejorar el
    método. Un MAE de 6.3049 y un WMAPE de 11.4650 % permiten afirmar
    que el pronóstico es aceptable; sin esas métricas, cualquier
    afirmación sería una opinión.

<!-- -->

1.  **La aprobación humana se implementó en los hechos**, no en la
    interfaz: el estado de una orden, una transferencia o un descuento
    no cambia sin un evento de aprobación registrado con responsable.

<!-- -->

1.  **El hallazgo más importante fue un defecto silencioso.** Una
    escritura que se revertía sin error dejó la bitácora de acciones
    vacía. Solo se detectó contrastando el valor devuelto con el conteo
    real de filas.

### **16.2 Limitaciones**

- **El pronóstico no incorpora promociones ni quiebres de stock.**
  Cuando un producto se agota, la venta registrada deja de reflejar la
  demanda real: la demanda observada es demanda satisfecha. El sistema
  no distingue ambas, y eso sesga el pronóstico a la baja en productos
  con faltantes recurrentes.

- **El cálculo de inventario en riesgo es una heurística**, no un
  modelo. Usa un horizonte fijo de cinco días de demanda por lote. Un
  producto con demanda muy estacional quedaría mal estimado.

- **La desestacionalización es semanal.** No captura efectos mensuales,
  quincenales ni de temporada alta.

- **La bitácora es inmutable por diseño**, lo que impide corregir
  registros de diagnóstico. Durante el desarrollo quedaron dos filas
  sintéticas (TEST_AUDITORIA y PRUEBA_DIRECTA) producto de las pruebas
  del mecanismo de auditoría. No es un defecto ---la inmutabilidad es
  intencional--- pero conviene saberlo antes de revisar la bitácora.

- **La aplicación no se ha probado con concurrencia real.** El bloqueo
  FOR UPDATE está implementado y es correcto, pero no se ha sometido a
  prueba de carga con ventas simultáneas.

### **16.3 Trabajo pendiente**

1.  **Rotar las credenciales** que circularon en texto plano durante el
    desarrollo: las claves de los roles de base de datos y la contraseña
    del servidor. La corrección de config.py y ETL.py evita que vuelvan
    a quedar embebidas, pero no invalida las que ya se expusieron.

2.  Incorporar **promociones y quiebres de stock** como variables del
    pronóstico.

3.  Añadir una **prueba de concurrencia** sobre el consumo FEFO.

4.  Evaluar la **media móvil ponderada** contra la suavización
    exponencial con las métricas ya implementadas, y elegir el método
    por error medido y no por preferencia.

5.  Incorporar **caducidad escalonada** en la sugerencia de descuento,
    para no descontar al mismo porcentaje un lote que vence en un día y
    otro que vence en cinco.

### **16.4 Cierre**

El Avance 2 no se sostiene en una lista de pantallas sino en un conjunto
de mediciones: **139 comprobaciones ejecutadas sin fallos** ---61 en el
escenario, 5 en la verificación de persistencia y 73 en la prueba de
humo de pantallas---, 108 alertas derivadas de reglas, 8 245 eventos de
auditoría y un pronóstico con error declarado y almacenado. Cada una de
esas cifras se puede reproducir ejecutando el comando correspondiente, y
ninguna se escribió a mano en este documento.

## **Anexo A --- Cómo reproducir**

Todos los comandos se ejecutan desde la raíz del proyecto, con el
entorno virtual activo.

  -----------------------------------------------------------------------
  **Objetivo**                        **Comando**
  ----------------------------------- -----------------------------------
  Crear el esquema desde cero         python scripts/bootstrap_db.py

  Solo verificar objetos existentes   python scripts/bootstrap_db.py
                                      \--solo-verificar

  Cargar datos históricos             python scripts/ETL.py

  Levantar la aplicación              python run.py

  Ejecutar el guion completo          python scripts/demo_avance2.py
                                      \--escenario

  Verificar persistencia              python scripts/demo_avance2.py
                                      \--verificar

  Probar todas las pantallas          python scripts/smoke_rutas.py

  Regenerar los diagramas             python scripts/generar_diagramas.py
  -----------------------------------------------------------------------

Los archivos Makefile y README.md agrupan estos comandos en objetivos
abreviados, e incluyen la variante con contenedores.

## **Anexo B --- Cuentas de demostración**

  -------------------------------------------------------------------------
  **Rol**                 **Correo**                **Estado**
  ----------------------- ------------------------- -----------------------
  Administrador           admin@freshtrack.mx       Activo

  Compras                 buyer@freshtrack.mx       Activo

  Planeación              planner@freshtrack.mx     Activo

  Gerente de tienda       gerente@freshtrack.mx     Activo

  Almacén                 almacen@freshtrack.mx     Activo

  Proveedor               proveedor@freshtrack.mx   Activo

  Auditor                 auditor@freshtrack.mx     Activo

  Usuario deshabilitado   inactivo@freshtrack.mx    **Inactivo**
  -------------------------------------------------------------------------

Las contraseñas se encuentran en la pantalla de login, que las lista
para facilitar la evaluación, y en la tabla de cuentas del README.md. El
usuario inactivo@freshtrack.mx existe para demostrar que el sistema
rechaza el acceso de cuentas deshabilitadas: sus credenciales son
válidas, pero estado_activo = false impide el acceso.

## **Anexo C --- Estructura del repositorio**

ProyectoIAC/\
├── app/\
│ ├── \_\_init\_\_.py factoría de la aplicación\
│ ├── config.py variables obligatorias del entorno\
│ ├── db.py motor, lectura y escritura\
│ ├── security.py login, JWT, decoradores de permisos\
│ ├── navegacion.py menú y matriz de permisos por rol\
│ ├── auditoria.py registro de acciones de aplicación\
│ ├── blueprints/ publico, auth, catalogo, operacion,\
│ │ analitica, panel, api\
│ ├── domain/ ventas, inventario, mermas, pronostico,\
│ │ reabastecimiento, transferencias,\
│ │ descuentos, alertas, kpis\
│ ├── repos/ catalogo.py\
│ ├── templates/ Jinja2, con \_macros.html compartido\
│ └── static/css/ hoja de estilos\
├── sql/\
│ ├── 01...07 esquema, en orden de ejecución\
│ └── legacy/ volcados obsoletos, fuera del arranque\
├── scripts/\
│ ├── bootstrap_db.py creación e idempotencia del esquema\
│ ├── ETL.py carga masiva\
│ ├── demo_avance2.py guion y verificación\
│ ├── smoke_rutas.py prueba de humo de las 73 pantallas\
│ └── generar_diagramas.py los cinco diagramas de este reporte\
├── docs/diagramas/ diagramas en PNG\
├── docker-compose.yml dos servicios con healthcheck\
├── Dockerfile\
├── Makefile\
├── env.example\
└── README.md
