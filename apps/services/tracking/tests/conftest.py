"""
Pruebas del microservicio tracking (pytest + fakeredis). Ejecutar desde
apps/services/tracking:

    pytest

PostgreSQL se sustituye por FakeRepo (misma interfaz que db/repository.py,
con ROLLBACK simulado y los indices unicos de la tabla) y el microservicio
pedidos por FakePedidos (services/pedidos_client.py). No se necesita
PostgreSQL, Redis ni ningun otro servicio levantado.
"""
import copy
import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
os.environ["INTERNAL_API_KEY"] = "clave-interna-de-pruebas"
os.environ["TAREAS_AUTOMATICAS"] = "0"             # la tarea se ejecuta a mano en las pruebas
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/services/tracking

import fakeredis  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402

import app as app_module  # noqa: E402
from common import redis_client  # noqa: E402
from common.config import settings  # noqa: E402
from common.errors import ApiError  # noqa: E402
from config import settings as cfg  # noqa: E402
from db import connection, repository  # noqa: E402
from db.repository import AHORA  # noqa: E402
from services import pedidos_client  # noqa: E402

ADMIN_ID, ANA_ID, LUIS_ID = 1, 31, 32
PEDIDO_ANA, PEDIDO_LUIS, PEDIDO_PENDIENTE, PEDIDO_ANA_2, PEDIDO_INEXISTENTE = 7, 8, 9, 10, 999
INTERNA = {"X-Internal-Key": "clave-interna-de-pruebas"}


class FakeRepo:
    """Sustituye a TrackingRepository guardando las filas en memoria."""

    def __init__(self):
        self.envios = {}
        self.posiciones_por_envio = {}
        self._candado = threading.RLock()

    @staticmethod
    def _valor(valor):
        return datetime.now() if valor is AHORA else valor

    def get_by_codigo(self, codigo, bloquear=False):
        return next((dict(e) for e in self.envios.values() if e["codigo"] == codigo), None)

    def get_by_pedido(self, pedido_id):
        return next((dict(e) for e in self.envios.values() if e["pedido_id"] == pedido_id), None)

    def list(self, user_id=None, estado=None, limit=20, offset=0):
        filas = [dict(e) for e in sorted(self.envios.values(), key=lambda e: -e["id"])
                 if (user_id is None or e["user_id"] == user_id) and (estado is None or e["estado"] == estado)]
        return filas[offset:offset + limit], len(filas)

    def con_estado(self, estados):
        return [dict(e) for e in sorted(self.envios.values(), key=lambda e: e["id"]) if e["estado"] in estados]

    def vencidos(self, estado, segundos):
        limite = datetime.now() - timedelta(seconds=segundos)
        return [dict(e) for e in sorted(self.envios.values(), key=lambda e: e["id"])
                if e["estado"] == estado and e["estado_desde"] <= limite]

    def pendientes_de_sincronizar(self, limite=50):
        return [dict(e) for e in sorted(self.envios.values(), key=lambda e: e["id"])
                if e["sync_error"] is None and (
                    (e["estado"] in ("ENVIADO", "EN_RUTA") and e["pedido_estado_sync"] is None)
                    or (e["estado"] == "ENTREGADO" and e["pedido_estado_sync"] != "ENTREGADO"))][:limite]

    def posiciones(self, envio_id, limite):
        return [dict(p) for p in self.posiciones_por_envio.get(envio_id, [])[-limite:]]

    def insert(self, codigo, pedido_id, user_id, ruta_id):
        if any(e["pedido_id"] == pedido_id or e["codigo"] == codigo for e in self.envios.values()):
            raise repository.EnvioDuplicado()
        nuevo_id = max(self.envios, default=0) + 1
        ahora = datetime.now()
        self.envios[nuevo_id] = {
            "id": nuevo_id, "codigo": codigo, "pedido_id": pedido_id, "user_id": user_id, "ruta_id": ruta_id,
            "estado": "CONFIRMADO", "progreso": 0, "ultima_lat": None, "ultima_lon": None,
            "ultima_velocidad": None, "ultimo_rumbo": None, "ultima_posicion_en": None, "estado_desde": ahora,
            "pedido_estado_sync": None, "sync_error": None, "created_at": ahora, "updated_at": ahora,
            "entregado_en": None}
        return dict(self.envios[nuevo_id])

    def update(self, envio_id, **campos):
        desconocidas = set(campos) - repository._EDITABLES
        assert not desconocidas, desconocidas
        self.envios[envio_id].update({c: self._valor(v) for c, v in campos.items()}, updated_at=datetime.now())
        return dict(self.envios[envio_id])

    def posicion_insert(self, envio_id, latitude, longitude, speed, heading, progreso, maximo):
        fila = {"latitude": latitude, "longitude": longitude, "speed": speed, "heading": heading,
                "progreso": progreso, "received_at": datetime.now()}
        lista = self.posiciones_por_envio.setdefault(envio_id, [])
        lista.append(fila)
        del lista[:-maximo]                                   # se conservan las ultimas `maximo`
        return dict(fila)

    # ---- utilidades de las pruebas
    def envio(self, codigo):
        return self.get_by_codigo(codigo)

    def forzar_estado(self, codigo, estado):
        envio = next(e for e in self.envios.values() if e["codigo"] == codigo)
        envio.update(estado=estado, estado_desde=datetime.now())

    @contextmanager
    def unit_of_work(self):
        with self._candado:
            respaldo = copy.deepcopy((self.envios, self.posiciones_por_envio))
            try:
                yield self
            except BaseException:
                self.envios, self.posiciones_por_envio = respaldo          # ROLLBACK
                raise


class FakePedidos:
    """Sustituye al microservicio pedidos: GET /pedidos/<id> con el JWT del usuario y sus endpoints internos."""

    TRANSICIONES = {"PAGADO": {"ENVIADO", "CANCELADO"}, "ENVIADO": {"ENTREGADO"}}

    def __init__(self):
        self.pedidos = {
            PEDIDO_ANA: {"id": PEDIDO_ANA, "user_id": ANA_ID, "estado": "PAGADO"},
            PEDIDO_ANA_2: {"id": PEDIDO_ANA_2, "user_id": ANA_ID, "estado": "PAGADO"},
            PEDIDO_LUIS: {"id": PEDIDO_LUIS, "user_id": LUIS_ID, "estado": "PAGADO"},
            PEDIDO_PENDIENTE: {"id": PEDIDO_PENDIENTE, "user_id": ANA_ID, "estado": "PENDIENTE_PAGO"},
        }
        self.caido = False
        self.llamadas = []

    def obtener_como_usuario(self, pedido_id, authorization):
        self.llamadas.append(("obtener_como_usuario", pedido_id, authorization))
        if self.caido:
            raise ApiError(503, "PEDIDOS_NO_DISPONIBLE", "El servicio de pedidos no responde.")
        payload = jwt.decode(authorization.split()[1], settings.JWT_SECRET_KEY, algorithms=["HS256"])
        pedido = self.pedidos.get(pedido_id)
        if pedido is None:
            raise ApiError(404, "PEDIDO_NO_ENCONTRADO", "No existe el pedido indicado.")
        if payload["role_id"] != 1 and pedido["user_id"] != payload["user_id"]:
            raise ApiError(403, "ROL_INSUFICIENTE", "Solo puedes consultar tus propios pedidos.")
        return dict(pedido)

    def obtener_interno(self, pedido_id):
        if self.caido:
            raise pedidos_client.PedidosNoDisponible()
        pedido = self.pedidos.get(pedido_id)
        return dict(pedido) if pedido else None

    def cambiar_estado(self, pedido_id, estado):
        self.llamadas.append(("cambiar_estado", pedido_id, estado))
        if self.caido:
            raise pedidos_client.PedidosNoDisponible()
        pedido = self.pedidos[pedido_id]
        if estado not in self.TRANSICIONES.get(pedido["estado"], ()):
            raise pedidos_client.TransicionRechazada()
        pedido["estado"] = estado
        return dict(pedido)

    def cambios(self):
        return [llamada[1:] for llamada in self.llamadas if llamada[0] == "cambiar_estado"]


@pytest.fixture
def repo(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(repository, "unit_of_work", fake.unit_of_work)
    return fake


@pytest.fixture
def pedidos(monkeypatch):
    fake = FakePedidos()
    monkeypatch.setattr(pedidos_client, "obtener_como_usuario", fake.obtener_como_usuario)
    monkeypatch.setattr(pedidos_client, "obtener_interno", fake.obtener_interno)
    monkeypatch.setattr(pedidos_client, "cambiar_estado", fake.cambiar_estado)
    return fake


@pytest.fixture
def fake_redis():
    cliente = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set_client(cliente)
    yield cliente
    redis_client.set_client(None)


@pytest.fixture
def sin_esperas(monkeypatch):
    """CONFIRMADO -> PREPARANDO -> ENVIADO en la primera vuelta de la tarea."""
    monkeypatch.setattr(cfg, "SEGUNDOS_CONFIRMADO", 0)
    monkeypatch.setattr(cfg, "SEGUNDOS_PREPARANDO", 0)


@pytest.fixture
def client(repo, pedidos, fake_redis, monkeypatch):
    monkeypatch.setattr(connection, "ping", lambda: True)
    return app_module.app.test_client()


def token_crudo(user_id, role_id=2):
    ahora = int(time.time())
    payload = {"sub": str(user_id), "user_id": user_id, "role_id": role_id, "jti": uuid.uuid4().hex,
               "role": "admin" if role_id == 1 else "cliente", "iat": ahora, "exp": ahora + 1200, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def token(user_id, role_id=2):
    return {"Authorization": "Bearer " + token_crudo(user_id, role_id)}


@pytest.fixture
def admin():
    return token(ADMIN_ID, 1)


@pytest.fixture
def ana():
    return token(ANA_ID)


@pytest.fixture
def luis():
    return token(LUIS_ID)


@pytest.fixture
def crear_envio(client):
    """crear_envio(cabecera, pedido_id) -> respuesta de POST /envios."""

    def _crear(cabecera, pedido_id):
        return client.post("/envios", json={"pedido_id": pedido_id}, headers=cabecera)

    return _crear
