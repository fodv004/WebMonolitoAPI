"""
config/settings.py
Constantes propias del microservicio tracking. Lo comun a todos los
servicios (PORT, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, PEDIDOS_URL,
INTERNAL_API_KEY...) se lee en common/config.py.

Variables de entorno propias (opcionales):
  SEGUNDOS_CONFIRMADO        segundos en CONFIRMADO antes de pasar a PREPARANDO (default 15)
  SEGUNDOS_PREPARANDO        segundos en PREPARANDO antes de pasar a ENVIADO    (default 15)
  SINCRONIZACION_SEGUNDOS    cada cuanto se reintenta avisar a pedidos          (default 5)
  TAREAS_AUTOMATICAS         0 = no arrancar el hilo de fondo (pruebas)
"""
import os

SERVICE_NAME = "tracking"
DEFAULT_PORT = 5900
VERSION = "2.0.0"


def _entero(nombre, defecto, minimo=0):
    try:
        return max(minimo, int(os.getenv(nombre, str(defecto)).strip()))
    except ValueError:
        return defecto


SEGUNDOS_CONFIRMADO = _entero("SEGUNDOS_CONFIRMADO", 15)
SEGUNDOS_PREPARANDO = _entero("SEGUNDOS_PREPARANDO", 15)
SINCRONIZACION_SEGUNDOS = _entero("SINCRONIZACION_SEGUNDOS", 5, 1)
TAREAS_AUTOMATICAS = os.getenv("TAREAS_AUTOMATICAS", "1").strip() != "0"
TAREAS_INTERVALO_SEGUNDOS = 1          # el hilo revisa los cambios por tiempo cada segundo

CODIGO_PREFIJO = "LIB-MTY"             # LIB-MTY-<año>-<pedido_id con 6 digitos>
DISTANCIA_ENTREGA_M = 30               # la posicion final debe quedar a menos de esto del ultimo punto
MAX_POSICIONES = 500                   # posiciones recorridas que se guardan por envio
VENTANA_PROYECCION_M = 1500            # el progreso solo avanza dentro de esta distancia (rutas que se cruzan)
