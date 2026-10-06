"""
Pruebas contra un PostgreSQL REAL: migracion, carga inicial, consultas del
repositorio y la API completa. Solo corren si se define TEST_DATABASE_URL
(si no, se omiten):

    TEST_DATABASE_URL=postgresql://usuario:clave@localhost:5432/base_de_pruebas pytest tests/test_integracion_pg.py

Usa una base DESECHABLE, nunca la de la aplicacion. Cada prueba trabaja en
un esquema propio (test_authors_<aleatorio>) creado con el esquema real del
monolito (WebMonolito/db/01_schema.sql) y lo borra al terminar.
"""
import os
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from conftest import ALEPH, CIEN
from db import repository
from db.repository import AuthorRepository, RelacionDuplicada

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="define TEST_DATABASE_URL (base desechable) para estas pruebas")

APPS = Path(__file__).resolve().parents[3]                      # apps/
SQL_MONOLITO = APPS / "WebMonolito" / "db" / "01_schema.sql"
SQL_AUTHORS = APPS / "services" / "authors" / "sql" / "001_authors.sql"


class Base:
    def __init__(self, esquema):
        self.esquema = esquema

    def conectar(self, autocommit=False):
        import psycopg

        return psycopg.connect(URL, autocommit=autocommit, options=f"-c search_path={self.esquema}")

    def ejecutar_archivo(self, ruta):
        with self.conectar(autocommit=True) as conn:
            conn.execute(ruta.read_text(encoding="utf-8"))

    def sql(self, consulta, parametros=None):
        with self.conectar() as conn:
            cur = conn.execute(consulta, parametros)
            return cur.fetchall() if cur.description else None

    @contextmanager
    def unit_of_work(self):
        conn = self.conectar()
        try:
            yield AuthorRepository(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def _esquema_nuevo():
    import psycopg

    esquema = f"test_authors_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {esquema}")
    return Base(esquema)


def _borrar(db):
    import psycopg

    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {db.esquema} CASCADE")


@pytest.fixture
def monolito():
    """Base con las tablas del monolito y datos en autores / libro_autor, ANTES de la Parte 3."""
    db = _esquema_nuevo()
    try:
        db.ejecutar_archivo(SQL_MONOLITO)
        db.sql("INSERT INTO formatos (nombre) VALUES ('Tapa dura')")
        db.sql("INSERT INTO libros (isbn, titulo, anio_publicacion, precio, stock, id_formato) VALUES "
               "(%s, 'Cien años de soledad', 1967, 300, 5, 1), (%s, 'El Aleph', 1949, 250, 3, 1)", (CIEN, ALEPH))
        db.sql("INSERT INTO autores (id_autor, nombre, nacionalidad) VALUES "
               "(5, 'Gabriel García Márquez', 'Colombiana'), (9, ' Jorge Luis Borges ', ''), (12, 'Coautora', NULL)")
        db.sql("INSERT INTO libro_autor (isbn, id_autor) VALUES (%s, 5), (%s, 12), (%s, 9)", (CIEN, CIEN, ALEPH))
        yield db
    finally:
        _borrar(db)


@pytest.fixture
def migrada(monolito):
    monolito.ejecutar_archivo(SQL_AUTHORS)
    return monolito


# ------------------------------------------------------------------ migracion
def test_migracion_crea_las_tablas_y_copia_los_datos_del_monolito(migrada):
    assert migrada.sql("SELECT id, nombre, apellido, nacionalidad FROM authors ORDER BY id") == [
        (5, "Gabriel García Márquez", None, "Colombiana"), (9, "Jorge Luis Borges", None, None), (12, "Coautora", None, None)]
    # orden = posicion del autor dentro de cada libro
    assert migrada.sql("SELECT author_id, isbn, orden FROM author_books ORDER BY isbn, orden") == [
        (5, CIEN, 1), (12, CIEN, 2), (9, ALEPH, 1)]
    # los ids nuevos continuan despues de los copiados
    assert migrada.sql("INSERT INTO authors (nombre) VALUES ('Nuevo') RETURNING id") == [(13,)]
    # las tablas del monolito quedan intactas
    assert migrada.sql("SELECT COUNT(*) FROM autores") == [(3,)] and migrada.sql("SELECT COUNT(*) FROM libro_autor") == [(3,)]
    assert ("005_authors",) in migrada.sql("SELECT version FROM schema_migraciones")


def test_migracion_idempotente_no_repite_la_carga_inicial(migrada):
    migrada.sql("DELETE FROM authors WHERE id = 12")                       # el admin borro un autor copiado
    migrada.sql("UPDATE authors SET nombre = 'Gabriel', apellido = 'García Márquez' WHERE id = 5")
    antes = migrada.sql("SELECT * FROM authors ORDER BY id"), migrada.sql("SELECT * FROM author_books ORDER BY 1, 2")
    migrada.ejecutar_archivo(SQL_AUTHORS)
    migrada.ejecutar_archivo(SQL_AUTHORS)
    assert (migrada.sql("SELECT * FROM authors ORDER BY id"), migrada.sql("SELECT * FROM author_books ORDER BY 1, 2")) == antes


def test_migracion_en_una_base_sin_las_tablas_del_monolito():
    db = _esquema_nuevo()
    try:
        db.ejecutar_archivo(SQL_AUTHORS)
        assert db.sql("SELECT COUNT(*) FROM authors") == [(0,)]
        assert db.sql("INSERT INTO authors (nombre) VALUES ('Primera') RETURNING id") == [(1,)]
    finally:
        _borrar(db)


def test_author_books_no_tiene_llave_foranea_al_isbn(migrada):
    migrada.sql("INSERT INTO author_books (author_id, isbn, orden) VALUES (5, 'NO-EXISTE-1', 1)")   # la base lo permite
    foraneas = migrada.sql(
        "SELECT ccu.table_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu USING (constraint_schema, constraint_name) "
        "WHERE tc.table_schema = current_schema() AND tc.table_name = 'author_books' AND tc.constraint_type = 'FOREIGN KEY'")
    assert foraneas == [("authors",)]
    pk = migrada.sql(
        "SELECT kcu.column_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu USING (constraint_schema, constraint_name) "
        "WHERE tc.table_schema = current_schema() AND tc.table_name = 'author_books' "
        "AND tc.constraint_type = 'PRIMARY KEY' ORDER BY kcu.ordinal_position")
    assert pk == [("author_id",), ("isbn",)]                                # PK compuesta


# ------------------------------------------------------------------ repositorio
def test_repositorio_crud_y_lista(migrada):
    with migrada.unit_of_work() as repo:
        nuevo = repo.insert(nombre="Isabel", apellido="Allende", nacionalidad="Chilena",
                            fecha_nacimiento=date(1942, 8, 2), biografia=None)
        assert nuevo["id"] == 13 and nuevo["total_libros"] == 0 and nuevo["fecha_nacimiento"] == date(1942, 8, 2)

        todos, total = repo.list()
        assert total == 4 and [a["id"] for a in todos] == [13, 12, 5, 9]     # por apellido (o nombre si no hay)
        assert [a["id"] for a in repo.list(q="allende")[0]] == [13]
        assert [a["id"] for a in repo.list(q="isabel all")[0]] == [13]       # nombre + apellido
        assert [a["id"] for a in repo.list(nacionalidad="COLOMBIANA")[0]] == [5]
        assert repo.list(q="%")[1] == 0 and repo.list(q="_")[1] == 0         # % y _ son literales
        pagina, total = repo.list(limit=2, offset=2)
        assert total == 4 and [a["id"] for a in pagina] == [5, 9]

        actualizado = repo.update(13, apellido=None, biografia="Bio")
        assert actualizado["apellido"] is None and actualizado["updated_at"] >= actualizado["created_at"]
        assert repo.get(5)["total_libros"] == 1 and repo.get(999) is None
        with pytest.raises(ValueError):
            repo.update(13, id=7)


def test_repositorio_relaciones(migrada):
    with migrada.unit_of_work() as repo:
        assert repo.books_of(5) == [{"isbn": CIEN, "orden": 1}]
        assert [(a["id"], a["orden"]) for a in repo.authors_of(CIEN)] == [(5, 1), (12, 2)]
        assert repo.next_orden(CIEN) == 3 and repo.next_orden("SIN-RELACION") == 1
        assert repo.add_book(9, CIEN, 3) == {"isbn": CIEN, "orden": 3}
    with pytest.raises(RelacionDuplicada):
        with migrada.unit_of_work() as repo:
            repo.add_book(9, CIEN, 4)
    with migrada.unit_of_work() as repo:
        assert repo.remove_book(9, CIEN) is True and repo.remove_book(9, CIEN) is False
        assert repo.delete(5) is True and repo.delete(5) is False            # borra tambien sus relaciones
    assert migrada.sql("SELECT author_id FROM author_books WHERE isbn = %s", (CIEN,)) == [(12,)]


# ------------------------------------------------------------------ API completa sobre PostgreSQL
def test_api_flujo_completo_sobre_postgresql(migrada, monkeypatch, client, books, fake_redis, admin):
    monkeypatch.setattr(repository, "unit_of_work", migrada.unit_of_work)
    books.catalogo = {CIEN: "Cien años de soledad", ALEPH: "El Aleph"}

    creado = client.post("/authors", headers=admin, json={"nombre": "Juan", "apellido": "Rulfo",
                                                           "fecha_nacimiento": "1917-05-16"})
    assert creado.status_code == 201
    nuevo = creado.get_json()["id"]

    assert client.post(f"/authors/{nuevo}/books", json={"isbn": ALEPH}, headers=admin).get_json()["orden"] == 2
    assert client.post(f"/authors/{nuevo}/books", json={"isbn": ALEPH}, headers=admin).status_code == 409
    assert client.post(f"/authors/{nuevo}/books", json={"isbn": "9789999999999"}, headers=admin).status_code == 404

    assert client.get(f"/authors/{nuevo}/books").get_json()["books"] == [{"isbn": ALEPH, "orden": 2, "titulo": "El Aleph"}]
    assert [a["nombre_completo"] for a in client.get(f"/authors/by-book/{ALEPH}").get_json()["authors"]] == [
        "Jorge Luis Borges", "Juan Rulfo"]
    assert client.get("/authors?q=rulfo").get_json()["items"][0]["total_libros"] == 1
    assert client.get("/authors?q=rulfo").get_json()["total"] == 1           # desde cache
    assert client.get("/metrics").get_json()["cache_hits"] >= 1

    assert client.delete(f"/authors/{nuevo}", headers=admin).status_code == 409
    assert client.delete(f"/authors/{nuevo}/books/{ALEPH}", headers=admin).status_code == 200
    assert client.delete(f"/authors/{nuevo}", headers=admin).status_code == 200
    assert client.get(f"/authors/{nuevo}").status_code == 404
    assert client.delete("/authors/5?force=true", headers=admin).get_json()["relaciones_eliminadas"] == 1
    assert migrada.sql("SELECT COUNT(*) FROM author_books WHERE author_id = 5") == [(0,)]
    assert migrada.sql("SELECT COUNT(*) FROM libro_autor") == [(3,)]         # el monolito no se toca
