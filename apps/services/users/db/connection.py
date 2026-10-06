"""
db/connection.py
Conexion a PostgreSQL del microservicio users (psycopg 3, DATABASE_URL).
Este servicio solo escribe en sus propias tablas; lo que necesite de otro
servicio lo pide por HTTP (timeout de 3 s, header X-Internal-Key).
"""
from common.db import get_conn, ping

__all__ = ["get_conn", "ping"]
