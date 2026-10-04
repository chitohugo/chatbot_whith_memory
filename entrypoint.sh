#!/bin/sh
set -e

echo "Esperando a que PostgreSQL esté disponible..."

python -c "
import time, os, psycopg2
db_url = os.getenv('DATABASE_URL')
for _ in range(30):
    try:
        conn = psycopg2.connect(db_url)
        conn.close()
        print('PostgreSQL está listo.')
        break
    except Exception:
        time.sleep(1)
else:
    raise TimeoutError('No se pudo conectar a PostgreSQL')
"

echo "Ejecutando script de inicialización de la base de datos (init.sql)..."
python -c "
import os, psycopg2
db_url = os.getenv('DATABASE_URL')
conn = psycopg2.connect(db_url)
with conn.cursor() as cur:
    with open('init.sql', 'r') as f:
        cur.execute(f.read())
conn.commit()
conn.close()
print('Tablas y extensiones verificadas/creadas correctamente.')
"

# Ejecutar Streamlit en lugar de main.py
exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501