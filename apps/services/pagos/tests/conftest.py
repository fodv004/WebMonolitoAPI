"""
Pruebas del microservicio pagos (pytest + fakeredis). Ejecutar desde
apps/services/pagos:

    pytest

PostgreSQL se sustituye por FakeRepo (misma interfaz que db/repository.py,
con ROLLBACK simulado y los dos indices unicos de la tabla) y el
microservicio pedidos por FakePedidos (services/pedidos_client.py). No se
necesita PostgreSQL, Redis ni ningun otro servicio levantado.
"""
import copy
import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
os.environ["INTERNAL_API_KEY"] = "clave-interna-de-pruebas"
os.environ["SINCRONIZACION_AUTOMATICA"] = "0"      # la tarea se ejecuta a mano en las pruebas
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/services/pagos

import fakeredis  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402

import app as app_module  # noqa: E402
from common import redis_client  # noqa: E402
from common.config import settings  # noqa: E402
from db import connection, repository  # noqa: E402
from services import pedidos_client  # noqa: E402

ADMIN_ID, ANA_ID, LUIS_ID = 1, 31, 32
PEDIDO_ANA, PEDIDO_LUIS, PEDIDO_PAGADO, PEDIDO_INEXISTENTE = 7, 8, 9, 999

TARJETA_BUENA = "4111 1111 1111 1111"
TARJETA_RECHAZADA = "4000-0000-0000-0000"          # termina en 0000 -> rechazada
CVV = "987"


class FakeRepo:
    """Sustituye a PagosRepository guardando las filas en memoria."""

    def __init__(self):
        self.pagos = {}
        self._candado = threading.RLock()

    def get(self, pago_id, bloquear=False):
        pago = self.pagos.get(pago_id)
        return dict(pago) if pago and pago["activo"] else None

    def get_by_key(self, idempotency_key):
        return next((dict(p) for p in self.pagos.values() if p["idempotency_key"] == idempotency_key), None)

    def aprobado_de_pedido(self, pedido_id):
        return next((dict(p) for p in self.pagos.values()
                     if p["pedido_id"] == pedido_id and p["estado"] == "APROBADO" and p["activo"]), None)

    def de_pedido(self, pedido_id):
        return [dict(p) for p in sorted(self.pagos.values(), key=lambda p: -p["id"])
                if p["pedido_id"] == pedido_id and p["activo"]]

    def list(self, user_id=None, estado=None, metodo=None, limit=20, offset=0):
        filas = [dict(p) for p in sorted(self.pagos.values(), key=lambda p: -p["id"]) if p["activo"]
                 and (user_id is None or p["user_id"] == user_id) and (estado is None or p["estado"] == estado)
                 and (metodo is None or p["metodo"] == metodo)]
        return filas[offset:offset + limit], len(filas)

    def pendientes_de_sincronizar(self, limite=50):
        return [dict(p) for p in sorted(self.pagos.values(), key=lambda p: p["id"])
                if not p["sincronizado"] and p["estado"] == "APROBADO" and p["activo"]][:limite]

    def insert(self, pedido_id, user_id, monto, metodo, estado, referencia, ultimos4, idempotency_key,
               sincronizado):
        if any(p["idempotency_key"] == idempotency_key for p in self.pagos.values()):
            raise repository.LlaveDuplicada()                    # columna UNIQUE
        if estado == "APROBADO" and any(p["pedido_id"] == pedido_id and p["estado"] == "APROBADO"
                                        for p in self.pagos.values()):
            raise repository.PedidoYaPagado()                    # indice unico uq_pagos_pedido_aprobado
        nuevo_id = max(self.pagos, default=0) + 1
        ahora = datetime.now()
        self.pagos[nuevo_id] = {
            "id": nuevo_id, "pedido_id": pedido_id, "user_id": user_id, "monto": monto, "metodo": metodo,
            "estado": estado, "referencia": referencia, "ultimos4": ultimos4, "idempotency_key": idempotency_key,
            "sincronizado": sincronizado, "notas": None, "activo": True, "created_at": ahora, "updated_at": ahora}
        return dict(self.pagos[nuevo_id])

    def update(self, pago_id, **campos):
        assert "monto" not in campos, "el monto nunca se edita"
        self.pagos[pago_id].update(campos, updated_at=datetime.now())
        return dict(self.pagos[pago_id])

    @contextmanager
    def unit_of_work(self):
        with self._candado:
            respaldo = copy.deepcopy(self.pagos)
            try:
                yield self
            except BaseException:
                self.pagos = respaldo          # ROLLBACK
                raise


class FakePedidos:
    """Sustituye al microservicio pedidos: sus dos endpoints internos y su maquina de estados."""

    TRANSICIONES = {"PENDIENTE_PAGO": {"PAGADO", "CANCELADO"}, "PAGADO": {"CANCELADO"}}

    def __init__(self):
        self.pedidos = {
            PEDIDO_ANA: {"id": PEDIDO_ANA, "user_id": ANA_ID, "estado": "PENDIENTE_PAGO", "total": 850.5},
            PEDIDO_LUIS: {"id": PEDIDO_LUIS, "user_id": LUIS_ID, "estado": "PENDIENTE_PAGO", "total": 199.99},
            PEDIDO_PAGADO: {"id": PEDIDO_PAGADO, "user_id": ANA_ID, "estado": "PAGADO", "total": 300.0},
        }
        self.caido = False                 # pedidos no responde a nada
        self.caido_al_cambiar = False      # responde al GET pero no al PATCH (se cae a mitad del pago)
        self.llamadas = []
        self.al_obtener = None             # funcion que se ejecuta dentro del GET (para probar el lock)

    def obtener(self, pedido_id):
        self.llamadas.append(("obtener", pedido_id))
        if self.caido:
            raise pedidos_client.PedidosNoDisponible()
        if self.al_obtener is not None:
            self.al_obtener()
        pedido = self.pedidos.get(pedido_id)
        return dict(pedido) if pedido else None

    def cambiar_estado(self, pedido_id, estado):
        self.llamadas.append(("cambiar_estado", pedido_id, estado))
        if self.caido or self.caido_al_cambiar:
            raise pedidos_client.PedidosNoDisponible()
        pedido = self.pedidos[pedido_id]
        if estado not in self.TRANSICIONES.get(pedido["estado"], ()):
            raise pedidos_client.TransicionRechazada()
        pedido["estado"] = estado
        return dict(pedido)

    def estado(self, pedido_id):
        return self.pedidos[pedido_id]["estado"]

    def cambios(self):
        return [llamada for llamada in self.llamadas if llamada[0] == "cambiar_estado"]


class RedisCaido:
    def __getattr__(self, nombre):
        def falla(*args, **kwargs):
            raise redis.ConnectionError("Redis caido (prueba)")

        return falla


class RedisQueFallaAlPagar:
    """Deja pasar la validacion del JWT (EXISTS) y falla en todo lo demas."""

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
def pedidos(monkeypatch):
    fake = FakePedidos()
    monkeypatch.setattr(pedidos_client, "obtener", fake.obtener)
    monkeypatch.setattr(pedidos_client, "cambiar_estado", fake.cambiar_estado)
    return fake


@pytest.fixture
def fake_redis():
    cliente = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set_client(cliente)
    yield cliente
    redis_client.set_client(None)


@pytest.fixture
def client(repo, pedidos, fake_redis, monkeypatch):
    monkeypatch.setattr(connection, "ping", lambda: True)
    return app_module.app.test_client()


def token(user_id, role_id=2):
    ahora = int(time.time())
    payload = {"sub": str(user_id), "user_id": user_id, "role_id": role_id, "jti": uuid.uuid4().hex,
               "role": "admin" if role_id == 1 else "cliente", "iat": ahora, "exp": ahora + 1200, "type": "access"}
    return {"Authorization": "Bearer " + jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")}


@pytest.fixture
def admin():
    return token(ADMIN_ID, 1)


@pytest.fixture
def ana():
    return token(ANA_ID)


@pytest.fixture
def luis():
    return token(LUIS_ID)


def nueva_llave():
    return str(uuid.uuid4())


@pytest.fixture
def pagar(client):
    """pagar(cabecera, pedido_id, ...) -> respuesta de POST /pagos. Sin `llave` genera una nueva."""

    def _pagar(cabecera, pedido_id, metodo="TARJETA_SIMULADA", tarjeta=TARJETA_BUENA, llave=None, **extra):
        cuerpo = {"pedido_id": pedido_id, "metodo": metodo, **extra}
        if metodo == "TARJETA_SIMULADA":
            cuerpo.update(tarjeta=tarjeta, cvv=CVV)
        return client.post("/pagos", json=cuerpo, headers={**cabecera, "Idempotency-Key": llave or nueva_llave()})

    return _pagar
