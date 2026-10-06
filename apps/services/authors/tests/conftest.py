"""
Pruebas del microservicio authors (pytest + fakeredis; PostgreSQL simulado).
Ejecutar desde apps/services/authors:

    pytest
"""
import os
import sys
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/services/authors

import fakeredis  # noqa: E402
import pytest  # noqa: E402

import app as app_module  # noqa: E402
from common import redis_client  # noqa: E402
from db import connection  # noqa: E402


@pytest.fixture
def fake_redis():
    cliente = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set_client(cliente)
    yield cliente
    redis_client.set_client(None)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(connection, "ping", lambda: True)
    return app_module.app.test_client()
