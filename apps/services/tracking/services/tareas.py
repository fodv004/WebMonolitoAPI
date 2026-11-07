"""
services/tareas.py
Hilo en segundo plano del microservicio tracking:

  * cada segundo: CONFIRMADO -> PREPARANDO -> ENVIADO por tiempo
  * cada SINCRONIZACION_SEGUNDOS: avisa a pedidos (ENVIADO / ENTREGADO)
    lo que no se le pudo avisar antes

Es un hilo daemon dentro del proceso (gunicorn corre con 1 worker). Un
fallo de PostgreSQL o de pedidos se registra en el log y se reintenta en la
siguiente vuelta: nunca tira el servicio.
"""
import logging
import threading
import time

from config import settings as cfg
from services import envios_service

log = logging.getLogger(__name__)

_hilo = None
_detener = threading.Event()


def ejecutar_una_vez(sincronizar=True):
    """Una vuelta de la tarea (las pruebas la llaman a mano)."""
    cambios = envios_service.avanzar_por_tiempo()
    hechos = envios_service.sincronizar_pendientes() if sincronizar else []
    return cambios, hechos


def _bucle():
    ultima_sync = 0.0
    ultimo_error = None
    while not _detener.wait(cfg.TAREAS_INTERVALO_SEGUNDOS):
        ahora = time.monotonic()
        sincronizar = ahora - ultima_sync >= cfg.SINCRONIZACION_SEGUNDOS
        try:
            ejecutar_una_vez(sincronizar)
            if sincronizar:
                ultima_sync = ahora
            ultimo_error = None
        except Exception as e:
            descripcion = f"{type(e).__name__}: {e}"
            if descripcion != ultimo_error:          # sin repetir la misma linea cada segundo
                log.warning("Tarea de tracking fallo; se reintenta (%s)", descripcion)
                ultimo_error = descripcion


def iniciar():
    """Arranca el hilo (una sola vez por proceso)."""
    global _hilo
    if _hilo is None or not _hilo.is_alive():
        _detener.clear()
        _hilo = threading.Thread(target=_bucle, name="tracking-tareas", daemon=True)
        _hilo.start()
        log.info("Tareas de tracking iniciadas (estados cada %s s, sincronizacion cada %s s)",
                 cfg.TAREAS_INTERVALO_SEGUNDOS, cfg.SINCRONIZACION_SEGUNDOS)


def detener():
    _detener.set()
