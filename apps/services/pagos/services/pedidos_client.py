"""
services/pedidos_client.py
Llamadas al microservicio pedidos por sus endpoints internos (los pedidos
y el stock son suyos; pagos no lee ni escribe sus tablas). Timeout de 3
segundos y header X-Internal-Key.

  GET   {PEDIDOS_URL}/pedidos/internal/{id}           -> obtener(id)
  PATCH {PEDIDOS_URL}/pedidos/internal/{id}/estado    -> cambiar_estado(id, "PAGADO" | "CANCELADO")

Al pasar a CANCELADO, pedidos libera el stock por su cuenta.

Excepciones:
  PedidosNoDisponible   pedidos no responde o responde con un error inesperado
  TransicionRechazada   pedidos respondio 409: el pedido no puede pasar a ese estado
"""
import logging

import requests

from common.auth import INTERNAL_KEY_HEADER
from common.config import settings

log = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 3


class PedidosNoDisponible(Exception):
    pass


class TransicionRechazada(Exception):
    pass


def _llamar(metodo, ruta, cuerpo=None):
    try:
        return requests.request(
            metodo, f"{settings.PEDIDOS_URL}{ruta}", json=cuerpo, timeout=TIMEOUT_SEGUNDOS,
            headers={INTERNAL_KEY_HEADER: settings.INTERNAL_API_KEY, "Accept": "application/json"})
    except requests.RequestException as e:
        log.warning("pedidos no responde (%s %s): %s", metodo, ruta, type(e).__name__)
        raise PedidosNoDisponible()


def _json(resp):
    try:
        datos = resp.json()
    except ValueError:
        raise PedidosNoDisponible()
    if not isinstance(datos, dict):
        raise PedidosNoDisponible()
    return datos


def obtener(pedido_id):
    """Pedido completo (id, user_id, estado, total, lineas...), o None si no existe."""
    resp = _llamar("GET", f"/pedidos/internal/{int(pedido_id)}")
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        log.warning("pedidos respondio HTTP %s al consultar un pedido", resp.status_code)
        raise PedidosNoDisponible()
    return _json(resp)


def cambiar_estado(pedido_id, estado):
    """Devuelve el pedido actualizado. TransicionRechazada si pedidos responde 409."""
    resp = _llamar("PATCH", f"/pedidos/internal/{int(pedido_id)}/estado", {"estado": estado})
    if resp.status_code == 409:
        raise TransicionRechazada()
    if resp.status_code != 200:
        log.warning("pedidos respondio HTTP %s al cambiar el estado de un pedido", resp.status_code)
        raise PedidosNoDisponible()
    return _json(resp)
