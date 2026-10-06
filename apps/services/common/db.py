"""
common/db.py
Conexion a PostgreSQL con psycopg (v3) a partir de DATABASE_URL, para los
servicios nuevos (users, authors, pedidos, pagos). login y books conservan
su propia conexion. Una conexion por peticion.
"""
from contextlib import contextmanager

from common.config import settings


@contextmanager
def get_conn():
    """Entrega una conexion; hace COMMIT si el bloque termina bien y ROLLBACK si falla."""
    import psycopg  # import tardio: login y books no lo instalan

    conn = psycopg.connect(settings.DATABASE_URL, connect_timeout=5)
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def ping():
    with get_conn() as conn:
        conn.execute("SELECT 1")
    return True
