Como referencia, se establece un conjunto de entre seis y diez microservicios, de acuerdo con la complejidad y el alcance aprobado del proyecto. Cada microservicio deberá incluir:

    Responsabilidad funcional claramente definida.
    Diseño desacoplado y modular.
    Ejecución en su propio contenedor Docker.
    Endpoints REST versionados, por ejemplo /api/v1/....
    Métodos HTTP apropiados: GET, POST, PUT, PATCH y DELETE, cuando correspondan.
    Recepción y validación de parámetros.
    Autenticación mediante JWT.
    Autorización según roles y permisos.
    Soporte de respuestas JSON.
    Soporte de respuestas XML de acuerdo con los contratos definidos.
    Manejo estandarizado de errores HTTP.
    Registro de actividad y operaciones relevantes.
    Endpoint de salud, por ejemplo /health.
    Documentación OpenAPI/Swagger.
    Integración con PostgreSQL, MongoDB y Redis, según su responsabilidad.
    Pruebas unitarias y de integración.


Los microservicios deberán representar responsabilidades reales y diferenciadas, evitando la fragmentación artificial de funcionalidades únicamente para alcanzar una cantidad determinada. Documentación individual obligatoria de cada microservicio Para cada microservicio se deberá presentar:

Elemento
	

Información requerida

Identificación
	

Nombre, propósito y responsabilidad

Justificación
	

Relación con los requerimientos del proyecto

Diseño
	

Arquitectura interna y componentes

Tecnología
	

Lenguaje, framework, bibliotecas y dependencias

Endpoints
	

Rutas, métodos HTTP y versiones

Entrada
	

Parámetros, headers y estructura del request

Salida
	

Estructura del response y códigos HTTP

Seguridad
	

JWT, roles y validaciones

Persistencia
	

Tablas, colecciones, claves y relaciones

Integración
	

Otros servicios o componentes con los que interactúa

Despliegue
	

Dockerfile, configuración y puerto

Evidencias
	

Solicitudes y respuestas reales, exitosas y con error

Pruebas
	

Casos ejecutados y resultados

