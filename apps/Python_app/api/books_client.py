"""
api/books_client.py
Cliente del microservicio de libros (apps/services/library_soap_service,
puerto 5001). Las lecturas son publicas; POST, PUT, PATCH y DELETE exigen
JWT de un usuario con rol admin (401 sin token valido, 403 sin permisos).
"""
import urllib.parse

from api.http_base import ServiceClient


class BooksClient(ServiceClient):
    SERVICIO = "books"

    @staticmethod
    def _ruta_libro(isbn):
        return f"/books/{urllib.parse.quote(isbn, safe='')}"

    def list_books(self):
        return self._http.get("/books")

    def list_formats(self):
        return self._http.get("/formats")

    def create_book(self, **campos):
        return self._http.post("/books", campos)

    def update_book(self, isbn, **campos):
        return self._http.put(self._ruta_libro(isbn), campos)

    def patch_book(self, isbn, **campos):
        return self._http.patch(self._ruta_libro(isbn), campos)

    def delete_book(self, isbn):
        return self._http.delete(self._ruta_libro(isbn))
