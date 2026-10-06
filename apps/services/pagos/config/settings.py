"""
config/settings.py
Constantes propias del microservicio pagos. Todo lo que viene de
variables de entorno (PORT, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY...)
se lee en common/config.py.
"""
SERVICE_NAME = "pagos"
DEFAULT_PORT = 5005
VERSION = "0.1.0"
