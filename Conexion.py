import psycopg2

# Configuración de la base de datos
DATABASE_CONFIG = {
    'dbname': 'postgres',
    'user': 'postgres',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

# Conexion
def conectar_db():
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        return conn
    except Exception as e:
        print("Error al conectar a la base de datos:", e)
        return None