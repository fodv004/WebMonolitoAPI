"""
Pruebas del microservicio users (pytest + fakeredis). Ejecutar desde
apps/services/users:

    pytest

PostgreSQL se sustituye por FakeRepo (misma interfaz que db/repository.py,
con ROLLBACK simulado). Las consultas SQL reales y las migraciones se
prueban aparte en test_integracion_pg.py, que solo corre si se define
TEST_DATABASE_URL apuntando a una base DESECHABLE.
"""
import copy
import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
os.environ["INTERNAL_API_KEY"] = "clave-interna-de-pruebas"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/services/users

import bcrypt  # noqa: E402
import fakeredis  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402

import app as app_module  # noqa: E402
from common import redis_client, redis_keys  # noqa: E402
from common.config import settings  # noqa: E402
from db import connection, repository  # noqa: E402
from services import login_client, passwords, validators  # noqa: E402

PASSWORD = "MiClaveSegura123"
ADMIN_ID, ANA_ID, LUIS_ID = 1, 31, 32


def hash_rapido(password):
    """bcrypt valido pero con pocas rondas, para que las pruebas no tarden."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(4)).decode()


def _fila(id_usuario, nombre, correo, role_id, activo=True, estado="confirmado", password_hash=None):
    return {"id_usuario": id_usuario, "nombre": nombre, "apellido_paterno": "Pérez", "apellido_materno": None,
            "correo": correo, "role_id": role_id, "es_admin": role_id == 1, "activo": activo,
            "estado_cuenta": estado, "fecha_registro": datetime(2026, 9, 1, 10, 0, 0),
            "updated_at": datetime(2026, 9, 1, 10, 0, 0), "password_hash": password_hash or hash_rapido(PASSWORD)}


class FakeRepo:
    """Sustituye a UserRepository guardando las filas en memoria."""

    ROLES = [{"role_id": 1, "nombre": "admin", "descripcion": "Administra"},
             {"role_id": 2, "nombre": "cliente", "descripcion": "Consulta"}]

    def __init__(self):
        compartido = hash_rapido(PASSWORD)
        self.filas = {
            ADMIN_ID: _fila(ADMIN_ID, "Admin", "admin@libreria.com", 1, password_hash=compartido),
            ANA_ID: _fila(ANA_ID, "Ana", "ana@correo.com", 2, password_hash=compartido),
            LUIS_ID: _fila(LUIS_ID, "Luis", "luis@correo.com", 2, password_hash=compartido),
        }
        self.commits = 0
        self.un_solo_admin = False     # True = con el indice unico del monolito sobre es_admin

    def _respetar_un_solo_admin(self, user_id, role_id):
        if self.un_solo_admin and role_id == 1 and any(
                f["role_id"] == 1 and f["id_usuario"] != user_id for f in self.filas.values()):
            raise repository.UnSoloAdmin()

    @staticmethod
    def _sin_hash(fila):
        return {k: v for k, v in fila.items() if k not in ("password_hash", "es_admin")} if fila else None

    def get(self, user_id, bloquear=False):
        return self._sin_hash(self.filas.get(user_id))

    def get_by_email(self, correo):
        return self._sin_hash(next((f for f in self.filas.values() if f["correo"] == correo), None))

    def password_hash(self, user_id):
        fila = self.filas.get(user_id)
        return fila["password_hash"] if fila else None

    def list(self, q=None, role_id=None, activo=None, limit=20, offset=0):
        filas = sorted(self.filas.values(), key=lambda f: f["id_usuario"])
        if q:
            filas = [f for f in filas if q.lower() in " ".join(
                str(f[c] or "") for c in ("nombre", "apellido_paterno", "apellido_materno", "correo")).lower()]
        if role_id is not None:
            filas = [f for f in filas if f["role_id"] == role_id]
        if activo is not None:
            filas = [f for f in filas if f["activo"] == activo]
        return [self._sin_hash(f) for f in filas[offset:offset + limit]], len(filas)

    def otros_admins_activos(self, user_id):
        return sum(1 for f in self.filas.values() if f["role_id"] == 1 and f["activo"] and f["id_usuario"] != user_id)

    def roles(self):
        return list(self.ROLES)

    def role(self, role_id):
        return next((r for r in self.ROLES if r["role_id"] == role_id), None)

    def _correo_libre(self, correo, excepto=None):
        if any(f["correo"] == correo and f["id_usuario"] != excepto for f in self.filas.values()):
            raise repository.EmailDuplicado()

    def insert(self, nombre, apellido_paterno, apellido_materno, correo, password_hash, role_id, activo,
               estado_cuenta):
        self._correo_libre(correo)
        self._respetar_un_solo_admin(None, role_id)
        nuevo_id = max(self.filas) + 1
        self.filas[nuevo_id] = {**_fila(nuevo_id, nombre, correo, role_id, activo, estado_cuenta, password_hash),
                                "apellido_paterno": apellido_paterno, "apellido_materno": apellido_materno}
        return self.get(nuevo_id)

    def update(self, user_id, **campos):
        if "correo" in campos:
            self._correo_libre(campos["correo"], excepto=user_id)
        if "role_id" in campos:
            self._respetar_un_solo_admin(user_id, campos["role_id"])
            campos["es_admin"] = campos["role_id"] == 1
        self.filas[user_id].update(campos, updated_at=datetime(2026, 10, 6, 12, 0, 0))
        return self.get(user_id)

    @contextmanager
    def unit_of_work(self):
        respaldo = copy.deepcopy(self.filas)
        try:
            yield self
        except BaseException:
            self.filas = respaldo          # ROLLBACK
            raise
        self.commits += 1


class RedisQueFallaAlRevocar:
    """Deja pasar la validacion del JWT (EXISTS) y falla al cerrar las sesiones."""

    def __init__(self, real):
        self._real = real

    def exists(self, *claves):
        return self._real.exists(*claves)

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
def fake_redis():
    cliente = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set_client(cliente)
    yield cliente
    redis_client.set_client(None)


@pytest.fixture(autouse=True)
def sin_red(monkeypatch):
    """Ninguna prueba sale a la red: MX siempre valido salvo 'sin-mx.test', y login simulado."""
    monkeypatch.setattr(validators, "_dominio_recibe_correo", lambda dominio: dominio != "sin-mx.test")
    monkeypatch.setattr(passwords, "BCRYPT_ROUNDS", 4)


@pytest.fixture
def confirmaciones(monkeypatch):
    """Correos de confirmacion que users le pidio a login."""
    pedidas = []
    monkeypatch.setattr(login_client, "enviar_confirmacion", lambda *args: pedidas.append(args))
    return pedidas


@pytest.fixture
def client(repo, monkeypatch):
    monkeypatch.setattr(connection, "ping", lambda: True)
    return app_module.app.test_client()


@pytest.fixture
def sesion(fake_redis):
    """Crea en Redis una sesion como la de login y devuelve el header Authorization de su JWT."""

    def _sesion(user_id, role_id):
        ahora = int(time.time())
        sid, jti, refresh_hash = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
        payload = {"sub": str(user_id), "user_id": user_id, "role_id": role_id, "sid": sid, "jti": jti,
                   "role": "admin" if role_id == 1 else "cliente", "iat": ahora, "exp": ahora + 1200, "type": "access"}
        fake_redis.set(redis_keys.session(sid), json.dumps(
            {"user_id": user_id, "jti": jti, "exp": payload["exp"], "refresh_hash": refresh_hash}), ex=3600)
        fake_redis.set(redis_keys.refresh(refresh_hash), json.dumps({"session_id": sid, "user_id": user_id}), ex=3600)
        fake_redis.sadd(redis_keys.user_sessions(user_id), sid)
        return {"Authorization": "Bearer " + jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")}

    return _sesion


@pytest.fixture
def admin(sesion):
    return sesion(ADMIN_ID, 1)


@pytest.fixture
def ana(sesion):
    return sesion(ANA_ID, 2)
