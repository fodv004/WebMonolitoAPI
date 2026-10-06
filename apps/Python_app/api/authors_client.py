"""
api/authors_client.py
Cliente del microservicio authors (apps/services/authors, puerto 5003):
autores y su relacion con los libros. Las lecturas son publicas; las
escrituras exigen JWT de un usuario con rol admin.
"""
import urllib.parse

from api.http_base import ServiceClient


class AuthorsClient(ServiceClient):
    SERVICIO = "authors"

    @staticmethod
    def _isbn(isbn):
        return urllib.parse.quote(isbn, safe="")

    # ------------------------------------------------------------ lecturas
    def list(self, q=None, nacionalidad=None, page=1, per_page=20):
        """{"items": [...], "page", "per_page", "total", "pages"}."""
        return self._http.get("/authors", params={"q": q, "nacionalidad": nacionalidad,
                                                  "page": page, "per_page": per_page})

    def get(self, author_id):
        return self._http.get(f"/authors/{author_id}")

    def books(self, author_id):
        """{"author_id", "enriquecido", "books": [{"isbn", "orden", "titulo"}]}."""
        return self._http.get(f"/authors/{author_id}/books")

    def by_book(self, isbn):
        """{"isbn", "authors": [...]} con los autores de un libro, en su orden."""
        return self._http.get(f"/authors/by-book/{self._isbn(isbn)}")

    # ------------------------------------------------------------ escrituras (admin)
    def create(self, **campos):
        return self._http.post("/authors", campos)

    def update(self, author_id, **campos):
        """PUT: reemplaza todos los campos del autor."""
        return self._http.put(f"/authors/{author_id}", campos)

    def patch(self, author_id, **campos):
        return self._http.patch(f"/authors/{author_id}", campos)

    def delete(self, author_id, force=False):
        """Con libros relacionados el servicio responde 409, salvo force=True."""
        return self._http.delete(f"/authors/{author_id}", params={"force": "true"} if force else None)

    def add_book(self, author_id, isbn, orden=None):
        cuerpo = {"isbn": isbn}
        if orden is not None:
            cuerpo["orden"] = orden
        return self._http.post(f"/authors/{author_id}/books", cuerpo)

    def remove_book(self, author_id, isbn):
        return self._http.delete(f"/authors/{author_id}/books/{self._isbn(isbn)}")
