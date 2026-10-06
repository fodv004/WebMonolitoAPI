"""
Pruebas unitarias de la capa REST de books (pytest + fakeredis; PostgreSQL
simulado). Ejecutar desde apps/services/library_soap_service:

    pytest
"""
import os
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/services/library_soap_service

import fakeredis  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402

import app as app_module  # noqa: E402
from api import rest  # noqa: E402
from common import metrics, redis_client  # noqa: E402
from common.config import settings  # noqa: E402


class FakeCatalogo:
    """Sustituye las consultas de lectura de api/rest.py y cuenta cuantas veces se llega a 'PostgreSQL'."""

    def __init__(self):
        self.consultas = 0
        self.libros = {
            "9780000000001": ["9780000000001", "Cloud Native", 2020, Decimal("499.90"), 5, "Tapa blanda"],
            "9780000000002": ["9780000000002", "Redis en acción", 2021, Decimal("350.00"), 2, "Digital"],
        }

    def todos(self):
        self.consultas += 1
        return [tuple(l) + ("Autora Uno", "Tecnología", None) for l in self.libros.values()]

    def uno(self, isbn):
        self.consultas += 1
        libro = self.libros.get(isbn)
        return tuple(libro) if libro else None

    def portada(self, isbn):
        return f"http://img.test/{isbn}.png"

    def conceptos(self, isbn):
        return [(1, "Máquinas virtuales", "IaaS", 3)]


class ConexionNula:
    """Las escrituras y el /health de estas pruebas no llegan a PostgreSQL de verdad."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self

    def execute(self, *args, **kwargs):
        pass

    def close(self):
        pass


class RedisCaido:
    def __getattr__(self, nombre):
        def falla(*args, **kwargs):
            raise redis.ConnectionError("Redis caido (prueba)")

        return falla


@pytest.fixture
def catalogo(monkeypatch):
    fake = FakeCatalogo()
    monkeypatch.setattr(rest, "_fetch_todos_libros", fake.todos)
    monkeypatch.setattr(rest, "_fetch_libro", fake.uno)
    monkeypatch.setattr(rest, "_fetch_portada", fake.portada)
    monkeypatch.setattr(rest, "_fetch_conceptos_cloud_libro", fake.conceptos)
    monkeypatch.setattr(app_module, "get_connection", lambda: ConexionNula())   # /health
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
def client(catalogo):
    return app_module.app.test_client()


@pytest.fixture
def token():
    def _token(role_id=1):
        ahora = int(time.time())
        payload = {"sub": "1", "user_id": 1, "role_id": role_id, "role": "admin" if role_id == 1 else "cliente",
                   "jti": uuid.uuid4().hex, "iat": ahora, "exp": ahora + 1200, "type": "access"}
        return {"Authorization": "Bearer " + jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")}

    return _token
