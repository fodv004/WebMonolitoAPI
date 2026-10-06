"""
db/repository.py
Acceso a datos del microservicio authors (psycopg 3, consultas
parametrizadas). Tablas propias: `authors` y `author_books`.

author_books.isbn no tiene llave foranea: que el libro exista lo valida
services/authors_service.py contra el microservicio books.
"""
from contextlib import contextmanager

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from common.db import get_conn

_COLUMNAS = "a.id, a.nombre, a.apellido, a.nacionalidad, a.fecha_nacimiento, a.biografia, a.created_at, a.updated_at"
_CON_TOTAL = f"{_COLUMNAS}, (SELECT COUNT(*) FROM author_books ab WHERE ab.author_id = a.id) AS total_libros"
_EDITABLES = {"nombre", "apellido", "nacionalidad", "fecha_nacimiento", "biografia"}


class RelacionDuplicada(Exception):
    pass


def _like(texto):
    """Patron ILIKE que busca `texto` literal (escapa % y _)."""
    return "%" + texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class AuthorRepository:
    def __init__(self, conn):
        self.conn = conn

    def _cur(self):
        return self.conn.cursor(row_factory=dict_row)

    # ------------------------------------------------------------ autores
    def get(self, author_id, bloquear=False):
        sql = f"SELECT {_CON_TOTAL} FROM authors a WHERE a.id = %s" + (" FOR UPDATE OF a" if bloquear else "")
        return self._cur().execute(sql, (author_id,)).fetchone()

    def list(self, q=None, nacionalidad=None, limit=20, offset=0):
        """(filas, total) ordenadas por apellido y nombre."""
        condiciones, valores = [], []
        if q:
            condiciones.append("(a.nombre ILIKE %s OR a.apellido ILIKE %s "
                               "OR (a.nombre || ' ' || COALESCE(a.apellido, '')) ILIKE %s)")
            valores += [_like(q)] * 3
        if nacionalidad:
            condiciones.append("lower(a.nacionalidad) = lower(%s)")
            valores.append(nacionalidad)
        where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

        total = self.conn.execute(f"SELECT COUNT(*) FROM authors a{where}", valores).fetchone()[0]
        filas = self._cur().execute(
            f"SELECT {_CON_TOTAL} FROM authors a{where} "
            "ORDER BY lower(COALESCE(a.apellido, a.nombre)), lower(a.nombre), a.id LIMIT %s OFFSET %s",
            valores + [limit, offset],
        ).fetchall()
        return filas, total

    def insert(self, **campos):
        columnas = [c for c in campos if c in _EDITABLES]
        fila = self.conn.execute(
            f"INSERT INTO authors ({', '.join(columnas)}) VALUES ({', '.join(['%s'] * len(columnas))}) RETURNING id",
            [campos[c] for c in columnas],
        ).fetchone()
        return self.get(fila[0])

    def update(self, author_id, **campos):
        desconocidas = set(campos) - _EDITABLES
        if desconocidas:
            raise ValueError(f"Columnas no editables: {sorted(desconocidas)}")
        asignaciones = "".join(f"{columna} = %s, " for columna in campos)
        self.conn.execute(f"UPDATE authors SET {asignaciones}updated_at = NOW() WHERE id = %s",
                          list(campos.values()) + [author_id])
        return self.get(author_id)

    def delete(self, author_id):
        """Borra el autor (y, por ON DELETE CASCADE, sus relaciones). True si existia."""
        return self.conn.execute("DELETE FROM authors WHERE id = %s", (author_id,)).rowcount > 0

    # ------------------------------------------------------------ relaciones
    def books_of(self, author_id):
        """[{isbn, orden}] de un autor."""
        return self._cur().execute(
            "SELECT isbn, orden FROM author_books WHERE author_id = %s ORDER BY isbn", (author_id,)).fetchall()

    def authors_of(self, isbn):
        """Autores de un libro, en su orden de aparicion."""
        return self._cur().execute(
            f"SELECT {_CON_TOTAL}, ab.orden FROM author_books ab JOIN authors a ON a.id = ab.author_id "
            "WHERE ab.isbn = %s ORDER BY ab.orden, a.id", (isbn,)).fetchall()

    def next_orden(self, isbn):
        return self.conn.execute(
            "SELECT COALESCE(MAX(orden), 0) + 1 FROM author_books WHERE isbn = %s", (isbn,)).fetchone()[0]

    def add_book(self, author_id, isbn, orden):
        try:
            self.conn.execute("INSERT INTO author_books (author_id, isbn, orden) VALUES (%s, %s, %s)",
                              (author_id, isbn, orden))
        except pg_errors.UniqueViolation:
            raise RelacionDuplicada()
        return {"isbn": isbn, "orden": orden}

    def remove_book(self, author_id, isbn):
        return self.conn.execute("DELETE FROM author_books WHERE author_id = %s AND isbn = %s",
                                 (author_id, isbn)).rowcount > 0


@contextmanager
def unit_of_work():
    """Una transaccion: COMMIT si el bloque termina bien, ROLLBACK si lanza."""
    with get_conn() as conn:
        yield AuthorRepository(conn)
