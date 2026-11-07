"""
services/pedidos_client.py
Llamadas al microservicio pedidos (tracking no lee ni escribe sus tablas).
Timeout de 3 segundos.

  GET   {PEDIDOS_URL}/pedidos/{id}                   -> obtener_como_usuario(id, authorization)
        reenvia el MISMO header Authorization del usuario: pedidos decide si
        el pedido es suyo (403) o si existe (404).
  GET   {PEDIDOS_URL}/pedidos/internal/{id}          -> obtener_interno(id)          X-Internal-Key
  PATCH {PEDIDOS_URL}/pedidos/internal/{id}/estado   -> cambiar_estado(id, estado)   X-Internal-Key
        estado = "ENVIADO" (solo desde PAGADO) | "ENTREGADO" (solo desde ENVIADO)

Excepciones:
  PedidosNoDisponible   pedidos no responde o responde con un error inesperado
  TransicionRechazada   pedidos respondio 409 al cambiar el estado
"""
import logging

import requests

from common.auth import INTERNAL_KEY_HEADER
from common.config import settings
from common.errors import ApiError

log = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 3
_ERRORES_DEL_USUARIO = (400, 401, 403, 404)


class PedidosNoDisponible(Exception):
    pass


class TransicionRechazada(Exception):
    pass


def _llamar(metodo, ruta, cuerpo=None, headers=None):
    try:
        return requests.request(metodo, f"{settings.PEDIDOS_URL}{ruta}", json=cuerpo, timeout=TIMEOUT_SEGUNDOS,
                                headers={"Accept": "application/json", **(headers or {})})
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


def _interno():
    return {INTERNAL_KEY_HEADER: settings.INTERNAL_API_KEY}


def obtener_como_usuario(pedido_id, authorization):
    """Pedido completo visto por el usuario del token. Si pedidos responde 400/401/403/404 se
    devuelve ese mismo error ({"error","message"}); si no responde, 503 PEDIDOS_NO_DISPONIBLE."""
    try:
        resp = _llamar("GET", f"/pedidos/{int(pedido_id)}", headers={"Authorization": authorization or ""})
    except PedidosNoDisponible:
        raise ApiError(503, "PEDIDOS_NO_DISPONIBLE", "El servicio de pedidos no responde. Intenta mas tarde.")
    if resp.status_code == 200:
        try:
            return _json(resp)
        except PedidosNoDisponible:
            raise ApiError(503, "PEDIDOS_NO_DISPONIBLE", "Respuesta invalida del servicio de pedidos.")
    if resp.status_code in _ERRORES_DEL_USUARIO:
        try:
            cuerpo = resp.json()
        except ValueError:
            cuerpo = {}
        cuerpo = cuerpo if isinstance(cuerpo, dict) else {}
        raise ApiError(resp.status_code, cuerpo.get("error") or f"HTTP_{resp.status_code}",
                       cuerpo.get("message") or "pedidos rechazo la consulta del pedido.")
    log.warning("pedidos respondio HTTP %s al consultar un pedido", resp.status_code)
    raise ApiError(503, "PEDIDOS_NO_DISPONIBLE", "El servicio de pedidos no responde. Intenta mas tarde.")


def obtener_interno(pedido_id):
    """Pedido completo, o None si no existe."""
    resp = _llamar("GET", f"/pedidos/internal/{int(pedido_id)}", headers=_interno())
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        log.warning("pedidos respondio HTTP %s al consultar un pedido (interno)", resp.status_code)
        raise PedidosNoDisponible()
    return _json(resp)


def cambiar_estado(pedido_id, estado):
    """Devuelve el pedido actualizado. TransicionRechazada si pedidos responde 409."""
    resp = _llamar("PATCH", f"/pedidos/internal/{int(pedido_id)}/estado", {"estado": estado}, headers=_interno())
    if resp.status_code == 409:
        raise TransicionRechazada()
    if resp.status_code != 200:
        log.warning("pedidos respondio HTTP %s al cambiar el estado de un pedido", resp.status_code)
        raise PedidosNoDisponible()
    return _json(resp)
