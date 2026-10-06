"""
api/authors_client.py
Cliente del microservicio authors (apps/services/authors, puerto 5003):
autores y sus relaciones con libros.

Parte 1: el servicio solo expone /health y /metrics; los metodos del CRUD
se agregan aqui cuando existan sus endpoints.
"""
from api.http_base import ServiceClient


class AuthorsClient(ServiceClient):
    SERVICIO = "authors"
