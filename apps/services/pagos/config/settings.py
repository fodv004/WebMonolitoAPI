"""
config/settings.py
Constantes propias del microservicio pagos. Lo comun a todos los
servicios (PORT, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, PEDIDOS_URL,
INTERNAL_API_KEY...) se lee en common/config.py.

Variables de entorno propias (opcionales):
  SINCRONIZACION_AUTOMATICA   0 = no arrancar la tarea en segundo plano (pruebas)
"""
import os

SERVICE_NAME = "pagos"
DEFAULT_PORT = 5005
VERSION = "1.0.0"

SINCRONIZACION_AUTOMATICA = os.getenv("SINCRONIZACION_AUTOMATICA", "1").strip() != "0"
SINCRONIZACION_INTERVALO_SEGUNDOS = 60      # la tarea reintenta cada minuto
