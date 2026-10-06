"""
api/pedidos_client.py
Cliente del microservicio pedidos (apps/services/pedidos, puerto 5004):
pedidos, líneas de pedido, stock y estados.

Parte 1: el servicio solo expone /health y /metrics; los metodos del CRUD
se agregan aqui cuando existan sus endpoints.
"""
from api.http_base import ServiceClient


class PedidosClient(ServiceClient):
    SERVICIO = "pedidos"
