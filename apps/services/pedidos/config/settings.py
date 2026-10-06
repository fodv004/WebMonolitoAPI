"""
config/settings.py
Constantes propias del microservicio pedidos. Lo comun a todos los
servicios (PORT, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, BOOKS_URL,
USERS_URL...) se lee en common/config.py.

Variables de entorno propias (todas opcionales):
  RESERVA_MINUTOS          minutos que un pedido PENDIENTE_PAGO conserva su
                           stock reservado antes de expirar (default 15).
                           Para probar la expiracion: RESERVA_MINUTOS=1
  EXPIRACION_AUTOMATICA    0 = no arrancar la tarea en segundo plano (pruebas)
"""
import os

from common import redis_keys

SERVICE_NAME = "pedidos"
DEFAULT_PORT = 5004
VERSION = "1.0.0"


def _entero(nombre, defecto, minimo):
    try:
        return max(int(os.getenv(nombre, "").strip() or defecto), minimo)
    except ValueError:
        return defecto


RESERVA_MINUTOS = _entero("RESERVA_MINUTOS", redis_keys.STOCK_RESERVATION_TTL // 60, 1)
RESERVA_SEGUNDOS = RESERVA_MINUTOS * 60

EXPIRACION_AUTOMATICA = os.getenv("EXPIRACION_AUTOMATICA", "1").strip() != "0"
EXPIRACION_INTERVALO_SEGUNDOS = 60      # la tarea revisa cada minuto
