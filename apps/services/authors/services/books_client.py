"""
services/books_client.py
Llamadas al microservicio books (los libros son suyos; authors no lee ni
escribe sus tablas). Timeout de 3 segundos y header X-Internal-Key.

  libro(isbn)   -> dict del libro, None si no existe (404); BooksNoDisponible si books falla
  titulos()     -> {isbn: titulo} de todo el catalogo; BooksNoDisponible si books falla
"""
import logging
from urllib.parse import quote

import requests

from common.auth import INTERNAL_KEY_HEADER
from common.config import settings

log = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 3


class BooksNoDisponible(Exception):
    pass


def _get(ruta):
    try:
        return requests.get(
            f"{settings.BOOKS_URL}{ruta}",
            params={"format": "json"},
            headers={INTERNAL_KEY_HEADER: settings.INTERNAL_API_KEY, "Accept": "application/json"},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as e:
        log.warning("books no responde (%s): %s", ruta, type(e).__name__)
        raise BooksNoDisponible()


def libro(isbn):
    resp = _get(f"/books/{quote(isbn, safe='')}")
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        log.warning("books respondio HTTP %s al consultar un libro", resp.status_code)
        raise BooksNoDisponible()
    try:
        datos = resp.json()
    except ValueError:
        raise BooksNoDisponible()
    return datos if isinstance(datos, dict) else {}


def titulos():
    """Una sola llamada (GET /books, que books cachea) en lugar de una por libro."""
    resp = _get("/books")
    if resp.status_code != 200:
        log.warning("books respondio HTTP %s al listar el catalogo", resp.status_code)
        raise BooksNoDisponible()
    try:
        libros = resp.json()
    except ValueError:
        raise BooksNoDisponible()
    if not isinstance(libros, list):
        raise BooksNoDisponible()
    return {l.get("isbn"): l.get("titulo") for l in libros if isinstance(l, dict)}
