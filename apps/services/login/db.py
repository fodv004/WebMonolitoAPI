"""
db.py
Conexion a PostgreSQL (psycopg2) con el rol auth_user, que solo tiene los
permisos que este servicio necesita (sql/auth_roles.sql). Una conexion por
peticion: el volumen de este servicio no justifica un pool.
"""
from contextlib import contextmanager

import psycopg2

from config import Config


@contextmanager
def get_conn():
    """Entrega una conexion; hace COMMIT si el bloque termina bien y ROLLBACK si falla."""
    conn = psycopg2.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        connect_timeout=5,
    )
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
