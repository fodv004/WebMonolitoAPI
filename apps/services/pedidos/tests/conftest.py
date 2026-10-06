"""
Pruebas del microservicio pedidos (pytest + fakeredis). Ejecutar desde
apps/services/pedidos:

    pytest

PostgreSQL se sustituye por FakeRepo (misma interfaz que db/repository.py,
con ROLLBACK simulado y un candado que hace de "FOR UPDATE") y los
servicios books y users por FakeServicios. El SQL real, los bloqueos y la
concurrencia de verdad se prueban en test_integracion_pg.py, que solo
corre si se define TEST_DATABASE_URL apuntando a una base DESECHABLE.
"""
import copy
import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

os.environ["JWT_SECRET_KEY"] = "secreto-de-pruebas-con-mas-de-32-bytes-0123456789"
os.environ["INTERNAL_API_KEY"] = "clave-interna-de-pruebas"
os.environ["EXPIRACION_AUTOMATICA"] = "0"          # la tarea se ejecuta a mano en las pruebas
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/services/pedidos

import fakeredis  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402

import app as app_module  # noqa: E402
from common import redis_client  # noqa: E402
from common.config import settings  # noqa: E402
from db import connection, repository  # noqa: E402
from services import clientes_http  # noqa: E402

ADMIN_ID, ANA_ID, LUIS_ID = 1, 31, 32
CIEN, ALEPH, RAYUELA, SIN_INVENTARIO = "9780000000001", "9780000000003", "9780000000004", "9780000000009"
INTERNA = {"X-Internal-Key": "clave-interna-de-pruebas"}


class FakeRepo:
    """Sustituye a PedidosRepository guardando todo en memoria."""

    def __init__(self):
        self.inventario = {CIEN: self._inv(CIEN, 5), ALEPH: self._inv(ALEPH, 2), RAYUELA: self._inv(RAYUELA, 10)}
        self.pedidos, self.lineas, self.historial = {}, {}, {}
        self._candado = threading.RLock()

    @staticmethod
    def _inv(isbn, disponible, reservado=0):
        return {"isbn": isbn, "stock_disponible": disponible, "stock_reservado": reservado,
                "updated_at": datetime(2026, 9, 1, 10, 0, 0)}

    def ahora(self):
        return datetime.now()

    # ---- inventario
    def inventario_get(self, isbn):
        fila = self.inventario.get(isbn)
        return dict(fila) if fila else None

    def inventario_list(self, limit=100, offset=0):
        filas = [dict(self.inventario[i]) for i in sorted(self.inventario)]
        return filas[offset:offset + limit], len(filas)

    def inventario_bloquear(self, isbns):
        return {i: dict(self.inventario[i]) for i in sorted(set(isbns)) if i in self.inventario}

    def inventario_ajustar(self, isbn, disponible=0, reservado=0):
        fila = self.inventario[isbn]
        fila["stock_disponible"] += disponible
        fila["stock_reservado"] += reservado
        assert fila["stock_disponible"] >= 0 and fila["stock_reservado"] >= 0, "CHECK del inventario violado"
        fila["updated_at"] = datetime.now()

    def inventario_insert(self, isbn, stock_disponible):
        if isbn in self.inventario:
            raise repository.InventarioDuplicado()
        self.inventario[isbn] = self._inv(isbn, stock_disponible)
        return dict(self.inventario[isbn])

    def inventario_fijar_disponible(self, isbn, stock_disponible):
        self.inventario[isbn]["stock_disponible"] = stock_disponible
        return dict(self.inventario[isbn])

    def inventario_delete(self, isbn):
        return self.inventario.pop(isbn, None) is not None

    # ---- pedidos
    def pedido_insert(self, user_id, total, minutos_de_reserva):
        nuevo_id = max(self.pedidos, default=0) + 1
        ahora = datetime.now()
        self.pedidos[nuevo_id] = {"id": nuevo_id, "user_id": user_id, "estado": "PENDIENTE_PAGO", "total": total,
                                  "created_at": ahora, "updated_at": ahora,
                                  "expira_en": ahora + timedelta(minutes=minutos_de_reserva), "eliminado_en": None}
        self.lineas[nuevo_id], self.historial[nuevo_id] = [], []
        return self.pedido_get(nuevo_id)

    def pedido_get(self, pedido_id, bloquear=False):
        pedido = self.pedidos.get(pedido_id)
        if pedido is None or pedido["eliminado_en"] is not None:
            return None
        return {k: v for k, v in pedido.items() if k != "eliminado_en"}

    def pedido_list(self, user_id=None, estado=None, limit=20, offset=0):
        filas = [p for p in sorted(self.pedidos.values(), key=lambda p: -p["id"]) if p["eliminado_en"] is None
                 and (user_id is None or p["user_id"] == user_id) and (estado is None or p["estado"] == estado)]
        return [{**self.pedido_get(p["id"]), "articulos": sum(l["cantidad"] for l in self.lineas[p["id"]])}
                for p in filas[offset:offset + limit]], len(filas)

    def pedido_cambiar_estado(self, pedido_id, estado):
        self.pedidos[pedido_id].update(estado=estado, updated_at=datetime.now())

    def pedido_fijar_total(self, pedido_id, total):
        self.pedidos[pedido_id].update(total=total, updated_at=datetime.now())

    def pedido_eliminar(self, pedido_id):
        self.pedidos[pedido_id]["eliminado_en"] = datetime.now()

    def pedidos_vencidos(self, limite=100):
        ahora = datetime.now()
        return [p["id"] for p in self.pedidos.values()
                if p["estado"] == "PENDIENTE_PAGO" and p["expira_en"] <= ahora][:limite]

    # ---- lineas e historial
    def lineas_get(self, pedido_id):
        return [dict(l) for l in self.lineas[pedido_id]]

    def lineas_reemplazar(self, pedido_id, lineas):
        self.lineas[pedido_id] = [dict(l) for l in lineas]

    def historial_insert(self, pedido_id, estado_anterior, estado_nuevo, actor):
        self.historial[pedido_id].append({"estado_anterior": estado_anterior, "estado_nuevo": estado_nuevo,
                                          "actor": actor, "fecha": datetime.now()})

    def historial_get(self, pedido_id):
        return [dict(h) for h in self.historial[pedido_id]]

    # ---- transaccion
    @contextmanager
    def unit_of_work(self):
        with self._candado:                     # una transaccion a la vez: hace de SELECT ... FOR UPDATE
            respaldo = copy.deepcopy((self.inventario, self.pedidos, self.lineas, self.historial))
            try:
                yield self
            except BaseException:
                self.inventario, self.pedidos, self.lineas, self.historial = respaldo       # ROLLBACK
                raise

    # ---- atajos para las pruebas
    def stock(self, isbn):
        fila = self.inventario[isbn]
        return fila["stock_disponible"], fila["stock_reservado"]

    def vencer(self, pedido_id):
        self.pedidos[pedido_id]["expira_en"] = datetime.now() - timedelta(seconds=1)


class FakeServicios:
    """Sustituye a books y users (services/clientes_http.py)."""

    def __init__(self):
        self.libros = {CIEN: ("Cien años de soledad", 300.0), ALEPH: ("El Aleph", 250.5),
                       RAYUELA: ("Rayuela", 199.99), SIN_INVENTARIO: ("Libro sin inventario", 100.0)}
        self.usuarios = {ADMIN_ID: True, ANA_ID: True, LUIS_ID: True}       # id -> activo
        self.caidos = set()
        self.llamadas = []

    def libro(self, isbn):
        self.llamadas.append(("libro", isbn))
        if "books" in self.caidos:
            raise clientes_http.ServicioNoDisponible("books")
        if isbn not in self.libros:
            return None
        titulo, precio = self.libros[isbn]
        return {"isbn": isbn, "titulo": titulo, "precio": precio}

    def usuario(self, user_id):
        self.llamadas.append(("usuario", user_id))
        if "users" in self.caidos:
            raise clientes_http.ServicioNoDisponible("users")
        if user_id not in self.usuarios:
            return None
        return {"id_usuario": user_id, "activo": self.usuarios[user_id]}


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
def servicios(monkeypatch):
    fake = FakeServicios()
    monkeypatch.setattr(clientes_http, "libro", fake.libro)
    monkeypatch.setattr(clientes_http, "usuario", fake.usuario)
    return fake


@pytest.fixture
def fake_redis():
    cliente = fakeredis.FakeRedis(decode_responses=True)
    redis_client.set_client(cliente)
    yield cliente
    redis_client.set_client(None)


@pytest.fixture
def client(repo, servicios, fake_redis, monkeypatch):
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


@pytest.fixture
def pedir(client):
    """pedir(cabecera, {isbn: cantidad}) -> respuesta de POST /pedidos."""

    def _pedir(cabecera, cantidades):
        return client.post("/pedidos", headers=cabecera,
                           json={"lineas": [{"isbn": i, "cantidad": n} for i, n in cantidades.items()]})

    return _pedir


TOTAL_2_CIEN_1_ALEPH = float(Decimal("300.00") * 2 + Decimal("250.50"))
