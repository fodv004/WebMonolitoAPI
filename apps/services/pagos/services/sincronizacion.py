"""
services/sincronizacion.py
Tarea en segundo plano: cada minuto reintenta avisar a pedidos de los
pagos APROBADO que quedaron con sincronizado = false (pedidos no
respondio cuando se pago).

  * Antes de cada vuelta toma el lock de Redis lock:pagos:sync
    (SET NX EX 30). Si otro proceso lo tiene, esta vuelta no hace nada.
  * Si Redis no responde no se puede tomar el lock y la vuelta se salta.
  * Es un hilo daemon dentro del proceso del servicio (gunicorn corre con
    1 worker): no necesita cron ni otro servicio.
"""
import logging
import threading
import uuid

import redis

from common import redis_keys
from common.redis_client import get_client
from config import settings as cfg
from services import pagos_service

log = logging.getLogger(__name__)

_hilo = None
_detener = threading.Event()


def ejecutar_una_vez():
    """Una vuelta de la tarea. Devuelve los ids sincronizados, o None si no se tomo el lock."""
    try:
        tomado = get_client().set(redis_keys.LOCK_SYNC_PAGOS, uuid.uuid4().hex, nx=True, ex=redis_keys.LOCK_TTL)
        if not tomado:
            return None
        ids = pagos_service.sincronizar_pendientes()
    except redis.RedisError as e:
        log.warning("Sincronizacion de pagos: Redis no disponible, se salta esta vuelta (%s)", type(e).__name__)
        return None
    if ids:
        log.info("Pagos sincronizados con pedidos: %s", ids)
    return ids


def _bucle():
    while not _detener.wait(cfg.SINCRONIZACION_INTERVALO_SEGUNDOS):
        try:
            ejecutar_una_vez()
        except Exception:
            log.exception("Fallo la sincronizacion de pagos; se reintenta en la siguiente vuelta")


def iniciar():
    """Arranca el hilo (una sola vez por proceso)."""
    global _hilo
    if _hilo is None or not _hilo.is_alive():
        _detener.clear()
        _hilo = threading.Thread(target=_bucle, name="sincronizar-pagos", daemon=True)
        _hilo.start()
        log.info("Tarea de sincronizacion de pagos iniciada (cada %s s)", cfg.SINCRONIZACION_INTERVALO_SEGUNDOS)
