"""
services/clientes_http.py
Llamadas a otros microservicios. Pedidos no lee ni escribe sus tablas:
les pregunta por HTTP con timeout de 3 segundos y el header X-Internal-Key.

  libro(isbn)      books -> dict del libro (titulo, precio...), None si no existe (404)
  usuario(id)      users -> datos minimos del usuario, None si no existe (404)

ServicioNoDisponible si el otro servicio no responde o responde con error.
"""
import logging
from urllib.parse import quote

import requests

from common.auth import INTERNAL_KEY_HEADER
from common.config import settings

log = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 3


class ServicioNoDisponible(Exception):
    def __init__(self, servicio):
        super().__init__(servicio)
        self.servicio = servicio


def _get(servicio, url):
    """JSON (dict) de la respuesta, o None si fue 404."""
    try:
        resp = requests.get(
            url, params={"format": "json"}, timeout=TIMEOUT_SEGUNDOS,
            headers={INTERNAL_KEY_HEADER: settings.INTERNAL_API_KEY, "Accept": "application/json"})
    except requests.RequestException as e:
        log.warning("%s no responde: %s", servicio, type(e).__name__)
        raise ServicioNoDisponible(servicio)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        log.warning("%s respondio HTTP %s", servicio, resp.status_code)
        raise ServicioNoDisponible(servicio)
    try:
        datos = resp.json()
    except ValueError:
        raise ServicioNoDisponible(servicio)
    if not isinstance(datos, dict):
        raise ServicioNoDisponible(servicio)
    return datos


def libro(isbn):
    return _get("books", f"{settings.BOOKS_URL}/books/{quote(isbn, safe='')}")


def usuario(user_id):
    return _get("users", f"{settings.USERS_URL}/users/internal/{int(user_id)}")
