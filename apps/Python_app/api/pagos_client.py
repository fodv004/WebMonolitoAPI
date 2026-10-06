"""
api/pagos_client.py
Cliente del microservicio pagos (apps/services/pagos, puerto 5005):
pagos y estado de los pedidos.

Parte 1: el servicio solo expone /health y /metrics; los metodos del CRUD
se agregan aqui cuando existan sus endpoints.
"""
from api.http_base import ServiceClient


class PagosClient(ServiceClient):
    SERVICIO = "pagos"
