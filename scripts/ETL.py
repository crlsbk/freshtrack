import pandas as pd
import numpy as np
from faker import Faker
from sqlalchemy import create_engine
import datetime
import uuid

# 1. Configuración y Conexión
# Reemplazar con credenciales reales de la instancia en GCP
DB_URL = "postgresql+psycopg2://app_backend:999@34.51.43.145:5432/retail_perecederos"
engine = create_engine(DB_URL)
fake = Faker('es_MX')

# Configuración de horizonte temporal (6 meses de operación)
END_DATE = datetime.date.today()
START_DATE = END_DATE - datetime.timedelta(days=180)

def poblar_catalogos_maestros():
    print("Generando Catálogos Maestros...")
    
    # 1. ROLES (Inclusión estricta de la matriz de perfiles definida)
    roles = pd.DataFrame({
        'nombre_rol': [
            'Usuario del Portal Público',
            'Operador de Almacén',
            'Proveedor',
            'Gerente de Tienda',
            'Planeador de Demanda',
            'Comprador',
            'Auditor',
            'Administrador del Sistema'
        ]
    })
    roles.to_sql('rol', engine, schema='operacion', if_exists='append', index=False)
    roles_db = pd.read_sql("SELECT id_rol, nombre_rol FROM operacion.rol", engine)

    # 2. LOCACIONES (~45 tiendas, 3 CEDIS y 2 Sedes Administrativas/Virtuales para perfiles corporativos y externos)
    locaciones = [
        {'tipo_locacion': 'CEDIS', 'nombre': 'Oficinas Corporativas Centrales'},
        {'tipo_locacion': 'CEDIS', 'nombre': 'Portal Externo B2B / Público'}
    ]
    for _ in range(45):
        locaciones.append({'tipo_locacion': 'Tienda', 'nombre': f"Sucursal {fake.city()}"})
    for _ in range(3):
        locaciones.append({'tipo_locacion': 'CEDIS', 'nombre': f"Macro CEDIS {fake.state()}"})
    
    df_locaciones = pd.DataFrame(locaciones)
    df_locaciones.to_sql('locacion', engine, schema='operacion', if_exists='append', index=False)
    locs_db = pd.read_sql("SELECT id_locacion, tipo_locacion, nombre FROM operacion.locacion", engine)

    # 3. PROVEEDORES (~40)
    proveedores = []
    for _ in range(40):
        proveedores.append({
            'rfc': fake.company_vat()[:13].ljust(13, 'X'),
            'razon_social': fake.company(),
            'lead_time_dias': np.random.randint(1, 15)
        })
    df_proveedores = pd.DataFrame(proveedores)
    df_proveedores.to_sql('proveedor', engine, schema='operacion', if_exists='append', index=False)
    provs_db = pd.read_sql("SELECT id_proveedor FROM operacion.proveedor", engine)

    # 4. USUARIOS (~90 perfiles distribuidos lógicamente)
    usuarios = []
    
    # Función auxiliar para asignar locación lógica según el rol
    def asignar_locacion(nombre_rol):
        if nombre_rol in ['Administrador del Sistema', 'Comprador', 'Planeador de Demanda', 'Auditor']:
            return locs_db[locs_db['nombre'] == 'Oficinas Corporativas Centrales']['id_locacion'].values[0]
        elif nombre_rol in ['Proveedor', 'Usuario del Portal Público']:
            return locs_db[locs_db['nombre'] == 'Portal Externo B2B / Público']['id_locacion'].values[0]
        elif nombre_rol == 'Operador de Almacén':
            return np.random.choice(locs_db[locs_db['tipo_locacion'] == 'CEDIS']['id_locacion'].values)
        else: # Gerente de Tienda
            return np.random.choice(locs_db[locs_db['tipo_locacion'] == 'Tienda']['id_locacion'].values)

    for _, rol in roles_db.iterrows():
        # Generar entre 5 y 15 usuarios por cada rol para tener una muestra balanceada (aprox 80-90 total)
        num_usuarios_rol = np.random.randint(5, 15)
        for _ in range(num_usuarios_rol):
            usuarios.append({
                'id_usuario': str(uuid.uuid4()),
                'id_rol': rol['id_rol'],
                'id_locacion': asignar_locacion(rol['nombre_rol']),
                'nombre_completo': fake.name(),
                'estado_activo': True
            })
            
    df_usuarios = pd.DataFrame(usuarios)
    df_usuarios.to_sql('usuario', engine, schema='operacion', if_exists='append', index=False)
    print(f"Catálogos Maestros poblados: {len(df_usuarios)} usuarios generados.")
    return locs_db, provs_db, df_usuarios

def pipeline_etl_operativo(locs_db, provs_db, df_usuarios):
    print("Iniciando ETL de Datos Operativos y Transaccionales (Procesamiento Vectorial)...")
    
    # 1. PRODUCTOS (500 SKUs)
    categorias_frescos = ['Lácteos', 'Carnes', 'Frutas', 'Verduras', 'Embutidos', 'Panadería', 'Pescados']
    productos = pd.DataFrame({
        'codigo_gtin': [str(fake.unique.random_number(digits=14, fix_len=True)) for _ in range(500)],
        'nombre': [f"{np.random.choice(categorias_frescos)} {fake.word().capitalize()}" for _ in range(500)],
        'vida_util_estandar': np.random.randint(3, 45, size=500)
    })
    productos.to_sql('producto', engine, schema='operacion', if_exists='append', index=False)
    prods_db = pd.read_sql("SELECT id_sku, vida_util_estandar FROM operacion.producto", engine)

    # 2. LOTES (~50,000 registros)
    dias_random = np.random.randint(0, 180, size=50000)
    fechas_elaboracion = pd.to_datetime(START_DATE) + pd.to_timedelta(dias_random, unit='D')
    
    lotes = pd.DataFrame({
        'id_lote': [str(uuid.uuid4()) for _ in range(50000)],
        'id_sku': np.random.choice(prods_db['id_sku'], size=50000),
        'id_proveedor': np.random.choice(provs_db['id_proveedor'], size=50000),
        'codigo_lote_prov': [f"LOT-{fake.bothify(text='???-####')}" for _ in range(50000)]
    })
    lotes = lotes.merge(prods_db, on='id_sku')
    lotes['fecha_caducidad'] = fechas_elaboracion + pd.to_timedelta(lotes['vida_util_estandar'], unit='D')
    lotes.drop(columns=['vida_util_estandar'], inplace=True)
    
    print("Insertando Lotes (50,000)...")
    lotes.to_sql('lote', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=10000)

    # 3. EXISTENCIAS (~150,000 intersecciones)
    existencias = pd.DataFrame({
        'id_existencia': [str(uuid.uuid4()) for _ in range(150000)],
        'id_lote': np.random.choice(lotes['id_lote'], size=150000),
        'id_locacion': np.random.choice(locs_db['id_locacion'], size=150000),
        'cantidad_disponible': np.random.uniform(5.0, 150.0, size=150000).round(2),
        'cantidad_reservada': 0.0
    })
    print("Insertando Existencias (150,000)...")
    existencias.to_sql('existencia', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=10000)

    # 4. VENTA DETALLE (> 500,000 registros)
    minutos_random = np.random.randint(0, 180 * 24 * 60, size=520000)
    fechas_venta = pd.to_datetime(START_DATE) + pd.to_timedelta(minutos_random, unit='m')
    
    ventas = pd.DataFrame({
        'id_venta': [str(uuid.uuid4()) for _ in range(520000)],
        'id_lote': np.random.choice(lotes['id_lote'], size=520000),
        'id_locacion': np.random.choice(locs_db[locs_db['tipo_locacion'] == 'Tienda']['id_locacion'], size=520000),
        'cantidad': np.random.exponential(scale=1.5, size=520000).clip(0.1).round(2),
        'fecha_transaccion': fechas_venta
    })
    print("Insertando Ventas Detalle (520,000)...")
    ventas.to_sql('venta_detalle', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=15000)

    # 5. MERMAS (~15,000 registros)
    # Filtrar solo usuarios con capacidad operativa de registrar merma (Gerentes y Operadores)
    usuarios_operativos = df_usuarios[df_usuarios['id_locacion'].isin(locs_db[locs_db['tipo_locacion'].isin(['Tienda', 'CEDIS'])]['id_locacion'])]
    
    dias_merma = np.random.randint(0, 180, size=15000)
    fechas_merma = pd.to_datetime(START_DATE) + pd.to_timedelta(dias_merma, unit='D')

    mermas = pd.DataFrame({
        'id_merma': [str(uuid.uuid4()) for _ in range(15000)],
        'id_lote': np.random.choice(lotes['id_lote'], size=15000),
        'id_usuario': np.random.choice(usuarios_operativos['id_usuario'], size=15000),
        'cantidad': np.random.uniform(1.0, 20.0, size=15000).round(2),
        'causa_merma': np.random.choice(['Caducidad', 'Cadena de Frío', 'Daño Empaque'], size=15000, p=[0.7, 0.2, 0.1]),
        'fecha_registro': fechas_merma
    })
    print("Insertando Mermas (15,000)...")
    mermas.to_sql('merma', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=5000)
    
    print("¡ETL finalizado con éxito! Datos distribuidos a lo largo de 6 meses operacionales con integridad referencial estricta.")

if __name__ == "__main__":
    locaciones_db, proveedores_db, usuarios_df = poblar_catalogos_maestros()
    pipeline_etl_operativo(locaciones_db, proveedores_db, usuarios_df)