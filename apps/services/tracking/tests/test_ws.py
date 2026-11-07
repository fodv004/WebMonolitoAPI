"""WebSocket /ws con un servidor real (werkzeug en un hilo) y websocket-client."""
import json
import threading

import pytest
import websocket
from werkzeug.serving import make_server

import app as app_module
from conftest import ANA_ID, INTERNA, PEDIDO_ANA, token_crudo
from services import rutas, tareas


@pytest.fixture
def servidor(client):
    """URL ws:// de un servidor real con los mismos fakes que `client`."""
    srv = make_server("127.0.0.1", 0, app_module.app, threaded=True)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"ws://127.0.0.1:{srv.server_port}/ws"
    srv.shutdown()


def _conectar(url, headers=None):
    return websocket.create_connection(url, header=[f"{k}: {v}" for k, v in (headers or {}).items()], timeout=5)


def _recibir(ws):
    return json.loads(ws.recv())


def _envio_enviado(client, repo, cabecera, monkeypatch):
    from config import settings as cfg

    monkeypatch.setattr(cfg, "SEGUNDOS_CONFIRMADO", 0)
    monkeypatch.setattr(cfg, "SEGUNDOS_PREPARANDO", 0)
    codigo = client.post("/envios", json={"pedido_id": PEDIDO_ANA}, headers=cabecera).get_json()["codigo"]
    tareas.ejecutar_una_vez(sincronizar=False)
    return codigo


def test_gps_sin_clave_interna_se_rechaza(servidor):
    ws = _conectar(f"{servidor}?role=gps")
    assert _recibir(ws)["error"] == "CLAVE_INTERNA_INVALIDA"
    ws.close()


def test_cliente_recibe_snapshot_y_updates_de_su_codigo(servidor, client, repo, ana, monkeypatch):
    codigo = _envio_enviado(client, repo, ana, monkeypatch)
    ruta = rutas.obtener(repo.envio(codigo)["ruta_id"])

    cliente = _conectar(f"{servidor}?role=cliente&codigo={codigo}", ana)
    snapshot = _recibir(cliente)
    assert snapshot["type"] == "snapshot" and snapshot["codigo"] == codigo and snapshot["estado"] == "ENVIADO"
    assert snapshot["ruta"]["puntos"] and snapshot["recorrido"] == []

    gps = _conectar(f"{servidor}?role=gps", INTERNA)
    gps.send(json.dumps({"vehicle_id": codigo, "latitude": ruta.puntos[2][0], "longitude": ruta.puntos[2][1],
                         "speed": 50, "heading": 90}))
    ack = _recibir(gps)
    assert ack["type"] == "ack" and ack["estado"] == "EN_RUTA"

    update = _recibir(cliente)
    assert update["type"] == "update" and update["codigo"] == codigo and update["estado"] == "EN_RUTA"
    assert (update["latitude"], update["longitude"]) == tuple(ruta.puntos[2]) and update["received_at"]
    assert set(update) == {"type", "codigo", "estado", "progreso", "latitude", "longitude", "speed", "heading",
                           "received_at"}

    gps.send(json.dumps({"vehicle_id": codigo, "latitude": ruta.destino[0], "longitude": ruta.destino[1],
                         "speed": 0, "heading": 90, "final": True}))
    assert _recibir(gps)["estado"] == "ENTREGADO"
    assert _recibir(cliente)["estado"] == "ENTREGADO"

    gps.send(json.dumps({"vehicle_id": "LIB-MTY-2026-999999", "latitude": 25.6, "longitude": -100.3,
                         "speed": 0, "heading": 0}))
    assert _recibir(gps)["error"] == "ENVIO_NO_ENCONTRADO"
    gps.close()
    cliente.close()


def test_cliente_con_token_en_query_como_respaldo(servidor, client, repo, ana, monkeypatch):
    codigo = _envio_enviado(client, repo, ana, monkeypatch)
    ws = _conectar(f"{servidor}?role=cliente&codigo={codigo}&token={token_crudo(ANA_ID)}")
    assert _recibir(ws)["type"] == "snapshot"
    ws.close()


def test_cliente_sin_token_ajeno_o_revocado_se_rechaza(servidor, client, repo, fake_redis, ana, luis, monkeypatch):
    codigo = _envio_enviado(client, repo, ana, monkeypatch)
    url = f"{servidor}?role=cliente&codigo={codigo}"

    ws = _conectar(url)
    assert _recibir(ws)["error"] == "TOKEN_AUSENTE"
    ws.close()

    ws = _conectar(url, luis)
    assert _recibir(ws) == {"type": "error", "error": "ROL_INSUFICIENTE",
                            "message": "Solo puedes consultar el rastreo de tus propios pedidos."}
    ws.close()

    ws = _conectar(f"{servidor}?role=cliente&codigo=LIB-MTY-2026-999999", ana)
    assert _recibir(ws)["error"] == "ENVIO_NO_ENCONTRADO"
    ws.close()

    # Token revocado en Redis (logout): se rechaza igual que en REST.
    import jwt
    from common import redis_keys
    from common.config import settings

    crudo = token_crudo(ANA_ID)
    fake_redis.set(redis_keys.jwt_revoked(jwt.decode(crudo, settings.JWT_SECRET_KEY, algorithms=["HS256"])["jti"]), 1)
    ws = _conectar(f"{url}&token={crudo}")
    assert _recibir(ws)["error"] == "TOKEN_REVOCADO"
    ws.close()


def test_mapa_solo_admin(servidor, client, repo, ana, admin, monkeypatch):
    codigo = _envio_enviado(client, repo, ana, monkeypatch)
    ws = _conectar(f"{servidor}?role=map", ana)
    assert _recibir(ws)["error"] == "ROL_INSUFICIENTE"
    ws.close()
    ws = _conectar(f"{servidor}?role=map", admin)
    snapshot = _recibir(ws)
    assert snapshot["type"] == "snapshot" and [e["codigo"] for e in snapshot["envios"]] == [codigo]
    ws.close()
