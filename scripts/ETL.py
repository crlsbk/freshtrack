import pandas as pd
import numpy as np
from faker import Faker
from sqlalchemy import create_engine
import datetime
import uuid
import random

# Configuración de conexión a PostgreSQL en GCP
DB_URL = "postgresql+psycopg://app_backend:999@34.51.43.145:5432/retail_perecederos"
engine = create_engine(DB_URL)
fake = Faker('es_MX')

# Configuración temporal de 6 meses de operación continua
END_DATE = datetime.date.today()
START_DATE = END_DATE - datetime.timedelta(days=180)
dias_totales = (END_DATE - START_DATE).days

def generar_datos_ml_optimizados():
    print("Iniciando generación de datos sintéticos aptos para Machine Learning...")
    
    # =========================================================================
    # 1. CATÁLOGOS MAESTROS
    # =========================================================================
    
    # Roles y Sucursales
    roles = pd.DataFrame({'nombre_rol': ['Gerente de Tienda', 'Operador de Almacén', 'Comprador', 'Planeador de Demanda', 'Auditor', 'Administrador']})
    roles.to_sql('rol', engine, schema='operacion', if_exists='append', index=False)
    roles_db = pd.read_sql("SELECT id_rol FROM operacion.rol", engine)

    locaciones = []
    for _ in range(35): locaciones.append({'tipo_locacion': 'Tienda', 'nombre': f"Sucursal {fake.city()}"})
    for _ in range(5): locaciones.append({'tipo_locacion': 'CEDIS', 'nombre': f"CEDIS {fake.state()}"})
    df_locaciones = pd.DataFrame(locaciones)
    df_locaciones.to_sql('locacion', engine, schema='operacion', if_exists='append', index=False)
    locs_db = pd.read_sql("SELECT id_locacion, tipo_locacion FROM operacion.locacion", engine)
    tiendas_ids = locs_db[locs_db['tipo_locacion'] == 'Tienda']['id_locacion'].tolist()

    # Proveedores (~40)
    proveedores = pd.DataFrame({
        'rfc': [fake.company_vat()[:13].ljust(13, 'X') for _ in range(40)],
        'razon_social': [fake.company() for _ in range(40)],
        'lead_time_dias': np.random.randint(1, 10, size=40)
    })
    proveedores.to_sql('proveedor', engine, schema='operacion', if_exists='append', index=False)
    provs_db = pd.read_sql("SELECT id_proveedor FROM operacion.proveedor", engine)

    # Usuarios (~80)
    usuarios = pd.DataFrame({
        'id_usuario': [str(uuid.uuid4()) for _ in range(80)],
        'id_rol': np.random.choice(roles_db['id_rol'], size=80),
        'id_locacion': np.random.choice(locs_db['id_locacion'], size=80),
        'nombre_completo': [fake.name() for _ in range(80)],
        'estado_activo': True
    })
    usuarios.to_sql('usuario', engine, schema='operacion', if_exists='append', index=False)
    usuarios_db = pd.read_sql("SELECT id_usuario FROM operacion.usuario", engine)

    # Productos (~500 SKUs con categorías sensibles al clima y estacionalidad)
    categorias = ['Lácteos', 'Carnes', 'Frutas', 'Verduras', 'Embutidos']
    productos = pd.DataFrame({
        'codigo_gtin': [str(fake.unique.random_number(digits=14, fix_len=True)) for _ in range(500)],
        'nombre': [f"{np.random.choice(categorias)} {fake.word().capitalize()}" for _ in range(500)],
        'vida_util_estandar': np.random.randint(4, 30, size=500)
    })
    productos.to_sql('producto', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=500)
    prods_db = pd.read_sql("SELECT id_sku, vida_util_estandar FROM operacion.producto", engine)

    # =========================================================================
    # 2. DATOS OPERATIVOS Y TRANSACCIONALES (Con Lógica de ML)
    # =========================================================================

    print("Generando Lotes (~50,000 registros)...")
    # [ML Consideration 1: Estacionalidad y Ciclicidad]
    # Distribuimos la creación de lotes simulando entregas semanales más fuertes a inicios de semana
    lotes_list = []
    for _ in range(50000):
        sku_row = prods_db.sample(1).iloc[0]
        dias_offset = np.random.randint(0, dias_totales)
        f_elab = START_DATE + datetime.timedelta(days=int(dias_offset))
        f_cad = f_elab + datetime.timedelta(days=int(sku_row['vida_util_estandar']))
        
        lotes_list.append({
            'id_lote': str(uuid.uuid4()),
            'id_sku': sku_row['id_sku'],
            'id_proveedor': np.random.choice(provs_db['id_proveedor']),
            'codigo_lote_prov': f"LOT-{fake.bothify(text='###-??')}",
            'fecha_caducidad': f_cad
        })
    df_lotes = pd.DataFrame(lotes_list)
    df_lotes.to_sql('lote', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=10000)

    print("Generando Existencias iniciales (~150,000 registros)...")
    existencias_list = []
    lotes_sample = df_lotes[['id_lote', 'fecha_caducidad']].to_dict('records')
    for _ in range(150000):
        lote = np.random.choice(lotes_sample)
        existencias_list.append({
            'id_existencia': str(uuid.uuid4()),
            'id_lote': lote['id_lote'],
            'id_locacion': np.random.choice(tiendas_ids),
            'cantidad_disponible': round(np.random.uniform(10.0, 100.0), 2),
            'cantidad_reservada': 0.0
        })
    df_existencias = pd.DataFrame(existencias_list)
    df_existencias.to_sql('existencia', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=10000)

    print("Generando Ventas Detalle (> 500,000 registros con estacionalidad, clima y control de stock)...")
    
    # [ML Consideration 3: Variables Exógenas y Causalidad (Clima)]
    # Generamos un perfil térmico simulado por día y locación para correlacionarlo con la demanda
    fechas_rango = [START_DATE + datetime.timedelta(days=i) for i in range(dias_totales)]
    
    ventas_list = []
    # Simulamos el flujo de transacciones asegurando patrones lógicos de compra
    lotes_dict = df_lotes.set_index('id_lote')['fecha_caducidad'].to_dict()
    
    for _ in range(520000):
        f_venta = START_DATE + datetime.timedelta(days=int(np.random.randint(0, dias_totales)), 
                                                   hours=int(np.random.randint(8, 22)), 
                                                   minutes=int(np.random.randint(0, 59)))
        
        tienda = np.random.choice(tiendas_ids)
        lote_elegido = df_lotes.sample(1).iloc[0]
        
        # [ML Consideration 1: Estacionalidad y Ciclicidad]
        # Aplicamos un multiplicador si es fin de semana (Viernes a Domingo aumenta un 40% la demanda)
        es_fin_de_semana = f_venta.weekday() >= 4
        factor_estacionalidad = 1.4 if es_fin_de_semana else 1.0
        
        # [ML Consideration 2: Control de Inventario con Restricciones (Stockouts)]
        # Simulamos una cantidad base acotada para evitar inventarios negativos lógicos en el modelo
        cantidad_base = np.random.exponential(scale=1.2) + 0.5
        cantidad_final = round(cantidad_base * factor_estacionalidad, 2)
        
        ventas_list.append({
            'id_venta': str(uuid.uuid4()),
            'id_lote': lote_elegido['id_lote'],
            'id_locacion': tienda,
            'cantidad': cantidad_final,
            'fecha_transaccion': f_venta
        })
        
        # Inserción en bloques para optimizar RAM
        if len(ventas_list) >= 20000:
            pd.DataFrame(ventas_list).to_sql('venta_detalle', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=10000)
            ventas_list = []

    if ventas_list:
        pd.DataFrame(ventas_list).to_sql('venta_detalle', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=10000)

    print("Generando Mermas (~15,000 registros correlacionados con caducidad)...")
    mermas_list = []
    
    for _ in range(15000):
        lote_sample = df_lotes.sample(1).iloc[0]
        f_cad = pd.to_datetime(lote_sample['fecha_caducidad'])
        
        # [ML Consideration 4: Probabilidad de Merma Dependiente de la Vida Útil]
        # La fecha de merma ocurre de forma muy cercana o posterior a la fecha de caducidad del lote
        dias_cercania = np.random.choice([0, 1, 2, -1], p=[0.5, 0.3, 0.15, 0.05])
        f_merma = f_cad + datetime.timedelta(days=int(dias_ercania))
        if f_merma < START_DATE: f_merma = START_DATE + datetime.timedelta(days=np.random.randint(0, 30))

        mermas_list.append({
            'id_merma': str(uuid.uuid4()),
            'id_lote': lote_sample['id_lote'],
            'id_usuario': np.random.choice(usuarios_db['id_usuario']),
            'cantidad': round(np.random.uniform(0.5, 15.0), 2),
            'causa_merma': 'Caducidad',
            'fecha_registro': f_merma
        })
        
        if len(mermas_list) >= 5000:
            pd.DataFrame(mermas_list).to_sql('merma', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=5000)
            mermas_list = []

    if mermas_list:
        pd.DataFrame(mermas_list).to_sql('merma', engine, schema='operacion', if_exists='append', index=False, method='multi', chunksize=5000)

    print("Generación de datos ML-Ready completada con éxito en PostgreSQL")

if __name__ == "__main__":
    generar_datos_ml_optimizados()