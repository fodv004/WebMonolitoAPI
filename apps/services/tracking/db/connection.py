"""
db/connection.py
Conexion a PostgreSQL del microservicio tracking (psycopg 3, DATABASE_URL).
Este servicio solo escribe en sus propias tablas (envios, envio_posiciones);
lo que necesite de pedidos lo pide por HTTP.
"""
from common.db import get_conn, ping

__all__ = ["get_conn", "ping"]
