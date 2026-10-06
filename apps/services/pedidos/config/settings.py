"""
config/settings.py
Constantes propias del microservicio pedidos. Todo lo que viene de
variables de entorno (PORT, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY...)
se lee en common/config.py.
"""
SERVICE_NAME = "pedidos"
DEFAULT_PORT = 5004
VERSION = "0.1.0"
