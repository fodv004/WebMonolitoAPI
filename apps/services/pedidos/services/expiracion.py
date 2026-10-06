"""
services/expiracion.py
Tarea en segundo plano: cada minuto pasa a EXPIRADO los pedidos
PENDIENTE_PAGO cuya reserva vencio y libera su stock.

  * Antes de cada vuelta toma el lock de Redis lock:pedidos:expirar
    (SET NX EX 30). Si otro proceso lo tiene, esta vuelta no hace nada:
    asi dos procesos del servicio nunca expiran lo mismo a la vez.
  * Que pedidos vencieron lo decide PostgreSQL (pedidos.expira_en), no
    Redis. Si Redis no responde no se puede tomar el lock y la vuelta se
    salta; los pedidos se expiraran en cuanto vuelva.
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
from services import pedidos_service

log = logging.getLogger(__name__)

_hilo = None
_detener = threading.Event()


def ejecutar_una_vez():
    """Una vuelta de la tarea. Devuelve los ids expirados, o None si no se tomo el lock."""
    try:
        tomado = get_client().set(redis_keys.LOCK_EXPIRAR_PEDIDOS, uuid.uuid4().hex, nx=True, ex=redis_keys.LOCK_TTL)
    except redis.RedisError as e:
        log.warning("Expiracion de pedidos: Redis no disponible, se salta esta vuelta (%s)", type(e).__name__)
        return None
    if not tomado:
        return None
    ids = pedidos_service.expirar_vencidos()
    if ids:
        log.info("Pedidos expirados por reserva vencida: %s", ids)
    return ids


def _bucle():
    while not _detener.wait(cfg.EXPIRACION_INTERVALO_SEGUNDOS):
        try:
            ejecutar_una_vez()
        except Exception:
            log.exception("Fallo la expiracion de pedidos; se reintenta en la siguiente vuelta")


def iniciar():
    """Arranca el hilo (una sola vez por proceso)."""
    global _hilo
    if _hilo is None or not _hilo.is_alive():
        _detener.clear()
        _hilo = threading.Thread(target=_bucle, name="expirar-pedidos", daemon=True)
        _hilo.start()
        log.info("Tarea de expiracion de pedidos iniciada (cada %s s, reserva de %s min)",
                 cfg.EXPIRACION_INTERVALO_SEGUNDOS, cfg.RESERVA_MINUTOS)
