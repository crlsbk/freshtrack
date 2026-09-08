# Retail Perecederos - Data Infrastructure & IaC

Infraestructura como código (IaC) estandarizada y reproducible para el proyecto de base de datos de retail (PostgreSQL), incluyendo esquemas transaccionales, auditoría con disparadores JSONB y despliegue automatizado mediante contenedores.

## Estructura del Repositorio

```text
├── .env.example
├── .gitattributes
├── Makefile
├── docker-compose.yml
├── sql/
│   ├── 01_init_roles_schemas.sh
│   ├── 02_ddl_operacion.sql
│   └── 03_ddl_auditoria.sql
└── README.md

## Requisitos Previos
- Docker y Docker Compose V2
- Python 3.10+ (para la capa de ETL opcional)

## Configuración y Despliegue Rápido

**1. Clonar el repositorio:**
```bash
git clone [https://github.com/tu-usuario/iac-proyecto.git](https://github.com/tu-usuario/iac-proyecto.git)
cd iac-proyecto
```

**2. Inicializar entorno de variables:**
```bash
make setup
```

**3. Restaurar respaldo de datos (si aplica):**
Si cuentas con un archivo de respaldo en formato SQL plano comprimido (dump_perecederos.sql.gz), cárgalo directamente al contenedor con:

```bash
gunzip -c dump_perecederos.sql.gz | docker exec -i retail_db psql -U postgres -d retail_pereceder
```

### Comandos Útiles (Makefile)
- `make up`: Despliega el contenedor en segundo plano.
- `make down`: Detiene los contenedores preservando el volumen de datos.
- `make clean`: Destruye los contenedores y limpia por completo el volumen de la base de datos para un reinicio limpio.
- `make populate`: Configura el entorno virtual de Python e instala las dependencias del ETL.

### Arquitectura de Base de Datos
Esquema operacion: Contiene catálogos maestros (rol, locacion, proveedor, producto) y el núcleo transaccional (usuario, lote, existencia, venta_detalle, merma) con tipado estricto en UUIDs y restricciones de integridad.  

### Esquema auditoria 
Almacena la bitácora centralizada de eventos mediante estructuras JSONB y funciones PL/pgSQL que capturan de manera dinámica los cambios (INSERT, UPDATE, DELETE) junto con disparadores de protección contra modificaciones indebidas.