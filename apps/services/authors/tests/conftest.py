"""
Pruebas del microservicio authors (pytest + fakeredis). Ejecutar desde
apps/services/authors:

    pytest

PostgreSQL se sustituye por FakeRepo (misma interfaz que db/repository.py)
y el microservicio books por FakeBooks. Las consultas SQL reales y la
migracion se prueban en test_integracion_pg.py, que solo corre si se
define TEST_DATABASE_URL apuntando a una base DESECHABLE.
"""
import copy
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
os.environ["INTERNAL_API_KEY"] = "clave-interna-de-pruebas"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/services/authors

import fakeredis  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402

import app as app_module  # noqa: E402
from common import metrics, redis_client  # noqa: E402
from common.config import settings  # noqa: E402
from db import connection, repository  # noqa: E402
from services import books_client  # noqa: E402

GABO, ISABEL, BORGES = 1, 2, 3
CIEN, CASA, ALEPH = "9780000000001", "9780000000002", "9780000000003"


def _autor(id_, nombre, apellido, nacionalidad, nacimiento=None):
    return {"id": id_, "nombre": nombre, "apellido": apellido, "nacionalidad": nacionalidad,
            "fecha_nacimiento": nacimiento, "biografia": None,
            "created_at": datetime(2026, 9, 1, 10, 0, 0), "updated_at": datetime(2026, 9, 1, 10, 0, 0)}


class FakeRepo:
    """Sustituye a AuthorRepository guardando todo en memoria; cuenta las lecturas a 'PostgreSQL'."""

    def __init__(self):
        self.autores = {
            GABO: _autor(GABO, "Gabriel", "García Márquez", "Colombiana", date(1927, 3, 6)),
            ISABEL: _autor(ISABEL, "Isabel", "Allende", "Chilena"),
            BORGES: _autor(BORGES, "Jorge Luis", "Borges", "Argentina"),
        }
        self.relaciones = {(GABO, CIEN): 1, (ISABEL, CASA): 1}     # (author_id, isbn) -> orden
        self.lecturas = 0

    def _fila(self, autor):
        total = sum(1 for (a, _i) in self.relaciones if a == autor["id"])
        return {**autor, "total_libros": total}

    def get(self, author_id, bloquear=False):
        self.lecturas += 1
        autor = self.autores.get(author_id)
        return self._fila(autor) if autor else None

    def list(self, q=None, nacionalidad=None, limit=20, offset=0):
        self.lecturas += 1
        filas = sorted(self.autores.values(), key=lambda a: ((a["apellido"] or a["nombre"]).lower(), a["id"]))
        if q:
            filas = [a for a in filas if q.lower() in f"{a['nombre']} {a['apellido'] or ''}".lower()]
        if nacionalidad:
            filas = [a for a in filas if (a["nacionalidad"] or "").lower() == nacionalidad.lower()]
        return [self._fila(a) for a in filas[offset:offset + limit]], len(filas)

    def insert(self, **campos):
        nuevo_id = max(self.autores, default=0) + 1
        self.autores[nuevo_id] = {**_autor(nuevo_id, None, None, None), **campos}
        return self._fila(self.autores[nuevo_id])

    def update(self, author_id, **campos):
        self.autores[author_id].update(campos, updated_at=datetime(2026, 10, 6, 12, 0, 0))
        return self._fila(self.autores[author_id])

    def delete(self, author_id):
        self.relaciones = {k: v for k, v in self.relaciones.items() if k[0] != author_id}
        return self.autores.pop(author_id, None) is not None

    def books_of(self, author_id):
        self.lecturas += 1
        return sorted(({"isbn": i, "orden": o} for (a, i), o in self.relaciones.items() if a == author_id),
                      key=lambda r: r["isbn"])

    def authors_of(self, isbn):
        self.lecturas += 1
        filas = [{**self._fila(self.autores[a]), "orden": o} for (a, i), o in self.relaciones.items() if i == isbn]
        return sorted(filas, key=lambda f: (f["orden"], f["id"]))

    def next_orden(self, isbn):
        return max((o for (_a, i), o in self.relaciones.items() if i == isbn), default=0) + 1

    def add_book(self, author_id, isbn, orden):
        if (author_id, isbn) in self.relaciones:
            raise repository.RelacionDuplicada()
        self.relaciones[(author_id, isbn)] = orden
        return {"isbn": isbn, "orden": orden}

    def remove_book(self, author_id, isbn):
        return self.relaciones.pop((author_id, isbn), None) is not None

    @contextmanager
    def unit_of_work(self):
        respaldo = copy.deepcopy((self.autores, self.relaciones))
        try:
            yield self
        except BaseException:
            self.autores, self.relaciones = respaldo          # ROLLBACK
            raise


class FakeBooks:
    """Sustituye al microservicio books (services/books_client.py)."""

    def __init__(self):
        self.catalogo = {CIEN: "Cien años de soledad", CASA: "La casa de los espíritus", ALEPH: "El Aleph"}
        self.caido = False
        self.llamadas = []

    def libro(self, isbn):
        self.llamadas.append(("libro", isbn))
        if self.caido:
            raise books_client.BooksNoDisponible()
        return {"isbn": isbn, "titulo": self.catalogo[isbn]} if isbn in self.catalogo else None

    def titulos(self):
        self.llamadas.append(("titulos", None))
        if self.caido:
            raise books_client.BooksNoDisponible()
        return dict(self.catalogo)


class RedisCaido:
    def __getattr__(self, nombre):
        def falla(*args, **kwargs):
            raise redis.ConnectionError("Redis caido (prueba)")

        return falla


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(repository, "unit_of_work", fake.unit_of_work)
    return fake


@pytest.fixture
def books(monkeypatch):
    fake = FakeBooks()
    monkeypatch.setattr(books_client, "libro", fake.libro)
    monkeypatch.setattr(books_client, "titulos", fake.titulos)
    return fake


@pytest.fixture
def fake_redis():
    cliente = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set_client(cliente)
    metrics.reset()
    yield cliente
    redis_client.set_client(None)


@pytest.fixture
def redis_caido():
    redis_client.set_client(RedisCaido())
    metrics.reset()
    yield
    redis_client.set_client(None)


@pytest.fixture
def client(repo, books, monkeypatch):
    monkeypatch.setattr(connection, "ping", lambda: True)
    return app_module.app.test_client()


def _token(role_id):
    ahora = int(time.time())
    payload = {"sub": "1", "user_id": 1, "role_id": role_id, "role": "admin" if role_id == 1 else "cliente",
               "jti": uuid.uuid4().hex, "iat": ahora, "exp": ahora + 1200, "type": "access"}
    return {"Authorization": "Bearer " + jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")}


@pytest.fixture
def admin():
    return _token(1)


@pytest.fixture
def cliente():
    return _token(2)
