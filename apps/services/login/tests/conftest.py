"""
Pruebas unitarias del login (pytest + fakeredis; PostgreSQL simulado).
Ejecutar desde apps/services/login:

    pytest

(tests/validar_endpoints.py es aparte: valida un servicio YA levantado.)
"""
import os
import sys
from contextlib import contextmanager
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
os.environ["SECRET_KEY"] = "cookie-de-pruebas"
os.environ["INTERNAL_API_KEY"] = "clave-interna-de-pruebas"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/services/login

import bcrypt  # noqa: E402
import fakeredis  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402
from psycopg2 import errors as pg_errors  # noqa: E402

import app as app_module  # noqa: E402
import routes  # noqa: E402
from common import metrics, redis_client  # noqa: E402

PASSWORD = "MiClaveSegura123"
_HASH = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(4)).decode()


def _usuario(id_usuario, correo, role_id, activo=True, estado="confirmado"):
    # mismas columnas que routes.USER_COLS
    return [id_usuario, "Ana", "Pérez", "Ruiz", correo, role_id == 1, activo, estado, role_id]


class FakeDB:
    """Sustituye a PostgreSQL: solo entiende las consultas de login, refresh y health."""

    def __init__(self):
        self.tokens = []          # (id_usuario, token_hash) insertados en tokens_confirmacion
        self.usuarios = {
            "admin@correo.com": _usuario(1, "admin@correo.com", 1),
            "ana@correo.com": _usuario(31, "ana@correo.com", 2),
        }

    def por_id(self, id_usuario):
        return next((u for u in self.usuarios.values() if u[0] == id_usuario), None)

    @contextmanager
    def get_conn(self):
        yield _Conexion(self)


class _Conexion:
    def __init__(self, db):
        self._db = db

    def cursor(self):
        return _Cursor(self._db)


class _Cursor:
    def __init__(self, db):
        self._db = db
        self._fila = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        if sql == "SELECT 1":
            self._fila = (1,)
        elif "WHERE correo = %s" in sql:
            usuario = self._db.usuarios.get(params[0])
            self._fila = tuple(usuario) + (_HASH,) if usuario else None
        elif "INSERT INTO tokens_confirmacion" in sql:
            if self._db.por_id(params[0]) is None:
                raise pg_errors.ForeignKeyViolation()
            self._db.tokens.append((params[0], params[1]))
        elif "WHERE id_usuario = %s" in sql:
            usuario = self._db.por_id(params[0])
            self._fila = tuple(usuario) if usuario and usuario[6] and usuario[7] == "confirmado" else None
        else:
            raise AssertionError(f"Consulta no esperada en las pruebas: {sql}")

    def fetchone(self):
        return self._fila


class RedisCaido:
    def __getattr__(self, nombre):
        def falla(*args, **kwargs):
            raise redis.ConnectionError("Redis caido (prueba)")

        return falla


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(routes, "get_conn", fake.get_conn)
    monkeypatch.setattr(app_module, "get_conn", fake.get_conn)   # /health
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
    yield
    redis_client.set_client(None)


@pytest.fixture
def client(db):
    return app_module.app.test_client()


@pytest.fixture
def login(client):
    def _login(email="ana@correo.com", password=PASSWORD):
        return client.post("/login?format=json", json={"email": email, "password": password})

    return _login
