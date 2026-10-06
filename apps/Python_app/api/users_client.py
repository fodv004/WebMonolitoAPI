"""
api/users_client.py
Cliente del microservicio users (apps/services/users, puerto 5002):
usuarios, roles, correos y contraseñas.

Parte 1: el servicio solo expone /health y /metrics; los metodos del CRUD
se agregan aqui cuando existan sus endpoints.
"""
from api.http_base import ServiceClient


class UsersClient(ServiceClient):
    SERVICIO = "users"
