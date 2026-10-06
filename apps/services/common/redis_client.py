"""
common/redis_client.py
Cliente Redis compartido (redis-py) con timeouts de 2 segundos.

Dos formas de usarlo, segun lo que este en juego:

* Cache (cache_get / cache_set / cache_invalidate): Redis es OPCIONAL.
  Si falla se registra en el log, se cuenta en /metrics y se continua
  con PostgreSQL. Nunca lanzan.
* Sesion, revocacion y autorizacion (get_client() directo): Redis es
  OBLIGATORIO. El redis.RedisError se propaga y quien llama responde 503.
"""
import json
import logging

import redis

from common import metrics
from common.config import settings

log = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 2

_client = None


def get_client():
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_timeout=TIMEOUT_SEGUNDOS,
            socket_connect_timeout=TIMEOUT_SEGUNDOS,
            decode_responses=True,
        )
    return _client


def set_client(client):
    """Sustituye el cliente (pruebas con fakeredis)."""
    global _client
    _client = client


def _fallo(operacion, clave, error):
    metrics.inc("redis_errors")
    log.warning("Redis no disponible en %s (%s): %s", operacion, clave, error)


def ping():
    try:
        return bool(get_client().ping())
    except redis.RedisError as e:
        _fallo("ping", "-", e)
        return False


def cache_get(key):
    """Valor cacheado (ya deserializado) o None si no existe o Redis fallo."""
    try:
        crudo = get_client().get(key)
    except redis.RedisError as e:
        _fallo("cache_get", key, e)
        return None
    if crudo is None:
        metrics.inc("cache_misses")
        return None
    try:
        valor = json.loads(crudo)
    except ValueError:
        metrics.inc("cache_misses")
        return None
    metrics.inc("cache_hits")
    return valor


def cache_set(key, value, ttl):
    try:
        get_client().set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
        return True
    except redis.RedisError as e:
        _fallo("cache_set", key, e)
        return False


def cache_delete(*keys):
    try:
        return get_client().delete(*keys) if keys else 0
    except redis.RedisError as e:
        _fallo("cache_delete", ",".join(keys), e)
        return 0


def cache_invalidate(pattern):
    """Borra las claves que cumplen el patron recorriendolas con SCAN (nunca KEYS)."""
    borradas = 0
    try:
        cliente = get_client()
        lote = []
        for clave in cliente.scan_iter(match=pattern, count=200):
            lote.append(clave)
            if len(lote) >= 200:
                borradas += cliente.delete(*lote)
                lote = []
        if lote:
            borradas += cliente.delete(*lote)
    except redis.RedisError as e:
        _fallo("cache_invalidate", pattern, e)
    return borradas
