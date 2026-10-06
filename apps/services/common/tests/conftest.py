"""
Pruebas del modulo comun. Ejecutar desde apps/services/common:

    pytest
"""
import os
import sys
import time
import uuid
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
os.environ["INTERNAL_API_KEY"] = "clave-interna-de-pruebas"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # apps/services

import fakeredis  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402
from flask import g, jsonify  # noqa: E402

from common import metrics, redis_client  # noqa: E402
from common.app_factory import create_service_app  # noqa: E402
from common.auth import ADMIN_ROLE_ID, CLIENTE_ROLE_ID, require_auth, require_internal_key, require_role  # noqa: E402
from common.config import settings  # noqa: E402


class RedisCaido:
    """Cliente cuyo servidor no responde: cualquier operacion lanza ConnectionError."""

    def __getattr__(self, nombre):
        def falla(*args, **kwargs):
            raise redis.ConnectionError("Redis caido (prueba)")

        return falla


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
def db_estado():
    return {"ok": True}


@pytest.fixture
def app(db_estado):
    def db_check():
        if not db_estado["ok"]:
            raise RuntimeError("PostgreSQL caido (prueba)")
        return True

    app = create_service_app("pruebas", version="9.9.9", db_check=db_check)

    @app.get("/publico")
    def publico():
        return jsonify({"ok": True})

    @app.post("/privado")
    @require_auth
    def privado():
        return jsonify({"user_id": g.jwt_payload["user_id"]})

    @app.delete("/admin")
    @require_role(ADMIN_ROLE_ID)
    def admin():
        return jsonify({"ok": True})

    @app.get("/interno")
    @require_internal_key
    def interno():
        return jsonify({"ok": True})

    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_token():
    def _make(role_id=CLIENTE_ROLE_ID, secret=None, algorithm="HS256", exp_delta=1200, omit=(), **extra):
        ahora = int(time.time())
        payload = {"sub": "7", "user_id": 7, "role_id": role_id, "role": "x", "jti": uuid.uuid4().hex,
                   "iat": ahora, "exp": ahora + exp_delta, "type": "access"}
        payload.update(extra)
        for claim in omit:
            payload.pop(claim, None)
        return jwt.encode(payload, secret or settings.JWT_SECRET_KEY, algorithm=algorithm)

    return _make


def bearer(token):
    return {"Authorization": f"Bearer {token}"}
