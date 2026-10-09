"""
db/repository.py
Acceso a datos del microservicio authors (psycopg 3, consultas
parametrizadas). Usa las tablas que ya existen en la base `library`:

    autores      (id_autor, nombre, nacionalidad)
    libro_autor  (isbn, id_autor)     id_autor con ON DELETE RESTRICT

Que el libro exista lo valida services/authors_service.py contra el
microservicio books antes de relacionarlo.
"""
from contextlib import contextmanager

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from common.db import get_conn

_COLUMNAS = "a.id_autor, a.nombre, a.nacionalidad"
_CON_TOTAL = f"{_COLUMNAS}, (SELECT COUNT(*) FROM libro_autor la WHERE la.id_autor = a.id_autor) AS total_libros"
_EDITABLES = {"nombre", "nacionalidad"}


class RelacionDuplicada(Exception):
    pass


class LibroInexistente(Exception):
    """libro_autor.isbn tiene llave foranea a libros: el ISBN no existe."""


def _like(texto):
    """Patron ILIKE que busca `texto` literal (escapa % y _)."""
    return "%" + texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class AuthorRepository:
    def __init__(self, conn):
        self.conn = conn

    def _cur(self):
        return self.conn.cursor(row_factory=dict_row)

    # ------------------------------------------------------------ autores
    def get(self, id_autor, bloquear=False):
        sql = f"SELECT {_CON_TOTAL} FROM autores a WHERE a.id_autor = %s" + (" FOR UPDATE OF a" if bloquear else "")
        return self._cur().execute(sql, (id_autor,)).fetchone()

    def list(self, q=None, nacionalidad=None, limit=20, offset=0):
        """(filas, total) ordenadas por nombre."""
        condiciones, valores = [], []
        if q:
            condiciones.append("a.nombre ILIKE %s")
            valores.append(_like(q))
        if nacionalidad:
            condiciones.append("lower(a.nacionalidad) = lower(%s)")
            valores.append(nacionalidad)
        where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

        total = self.conn.execute(f"SELECT COUNT(*) FROM autores a{where}", valores).fetchone()[0]
        filas = self._cur().execute(
            f"SELECT {_CON_TOTAL} FROM autores a{where} ORDER BY lower(a.nombre), a.id_autor LIMIT %s OFFSET %s",
            valores + [limit, offset],
        ).fetchall()
        return filas, total

    def insert(self, nombre, nacionalidad):
        fila = self.conn.execute(
            "INSERT INTO autores (nombre, nacionalidad) VALUES (%s, %s) RETURNING id_autor",
            (nombre, nacionalidad)).fetchone()
        return self.get(fila[0])

    def update(self, id_autor, **campos):
        desconocidas = set(campos) - _EDITABLES
        if desconocidas:
            raise ValueError(f"Columnas no editables: {sorted(desconocidas)}")
        asignaciones = ", ".join(f"{columna} = %s" for columna in campos)
        self.conn.execute(f"UPDATE autores SET {asignaciones} WHERE id_autor = %s",
                          list(campos.values()) + [id_autor])
        return self.get(id_autor)

    def delete(self, id_autor):
        """Borra el autor. Primero sus relaciones: libro_autor.id_autor es ON DELETE RESTRICT."""
        self.conn.execute("DELETE FROM libro_autor WHERE id_autor = %s", (id_autor,))
        return self.conn.execute("DELETE FROM autores WHERE id_autor = %s", (id_autor,)).rowcount > 0

    # ------------------------------------------------------------ relaciones
    def books_of(self, id_autor):
        """[{isbn}] de un autor."""
        return self._cur().execute(
            "SELECT isbn FROM libro_autor WHERE id_autor = %s ORDER BY isbn", (id_autor,)).fetchall()

    def authors_of(self, isbn):
        """Autores de un libro."""
        return self._cur().execute(
            f"SELECT {_CON_TOTAL} FROM libro_autor la2 JOIN autores a ON a.id_autor = la2.id_autor "
            "WHERE la2.isbn = %s ORDER BY lower(a.nombre), a.id_autor", (isbn,)).fetchall()

    def add_book(self, id_autor, isbn):
        try:
            self.conn.execute("INSERT INTO libro_autor (isbn, id_autor) VALUES (%s, %s)", (isbn, id_autor))
        except pg_errors.UniqueViolation:
            raise RelacionDuplicada()
        except pg_errors.ForeignKeyViolation:
            raise LibroInexistente()
        return {"isbn": isbn}

    def remove_book(self, id_autor, isbn):
        return self.conn.execute("DELETE FROM libro_autor WHERE id_autor = %s AND isbn = %s",
                                 (id_autor, isbn)).rowcount > 0


@contextmanager
def unit_of_work():
    """Una transaccion: COMMIT si el bloque termina bien, ROLLBACK si lanza."""
    with get_conn() as conn:
        yield AuthorRepository(conn)
