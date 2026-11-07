"""Codigo de rastreo, permisos, estados por tiempo, posiciones, entrega a < 30 m y aviso a pedidos."""
import re
from datetime import datetime

from conftest import (ADMIN_ID, ANA_ID, INTERNA, PEDIDO_ANA, PEDIDO_ANA_2, PEDIDO_INEXISTENTE, PEDIDO_LUIS,
                      PEDIDO_PENDIENTE)
from config import settings as cfg
from services import envios_service, rutas, tareas


def _error(resp):
    return resp.get_json()["error"]


def _posicion(codigo, punto, final=None, speed=40.0, heading=90.0):
    datos = {"vehicle_id": codigo, "latitude": punto[0], "longitude": punto[1], "speed": speed, "heading": heading}
    if final is not None:
        datos["final"] = final
    return envios_service.registrar_posicion(envios_service.validar_posicion(datos))


def _enviado(client, repo, cabecera, pedido_id, sin_esperas=True):
    """Crea el envio y lo deja en ENVIADO con una vuelta de la tarea."""
    codigo = client.post("/envios", json={"pedido_id": pedido_id}, headers=cabecera).get_json()["codigo"]
    tareas.ejecutar_una_vez(sincronizar=False)
    assert repo.envio(codigo)["estado"] == "ENVIADO"
    return codigo


# ------------------------------------------------------------------ POST /envios
def test_crear_envio_de_pedido_pagado(client, repo, pedidos, ana, crear_envio):
    resp = crear_envio(ana, PEDIDO_ANA)
    assert resp.status_code == 201
    envio = resp.get_json()
    assert envio["codigo"] == f"LIB-MTY-{datetime.now().year}-{PEDIDO_ANA:06d}"
    assert re.fullmatch(r"LIB-MTY-\d{4}-\d{6}", envio["codigo"])
    assert envio["estado"] == "CONFIRMADO" and envio["progreso"] == 0 and envio["posicion"] is None
    assert envio["user_id"] == ANA_ID and envio["pedido_id"] == PEDIDO_ANA
    assert envio["ruta"]["id"] == envio["ruta_id"] and len(envio["ruta"]["puntos"]) > 2 and envio["recorrido"] == []
    # se reenvia el mismo Authorization del usuario a pedidos
    assert pedidos.llamadas[0] == ("obtener_como_usuario", PEDIDO_ANA, ana["Authorization"])


def test_crear_dos_veces_devuelve_el_mismo_envio(client, repo, ana, admin, crear_envio):
    primero = crear_envio(ana, PEDIDO_ANA).get_json()
    otra_vez = crear_envio(ana, PEDIDO_ANA)
    assert otra_vez.status_code == 200 and otra_vez.get_json()["codigo"] == primero["codigo"]
    assert crear_envio(admin, PEDIDO_ANA).status_code == 200            # el admin tampoco duplica
    assert len(repo.envios) == 1


def test_pedido_no_pagado_409(client, repo, ana, crear_envio):
    resp = crear_envio(ana, PEDIDO_PENDIENTE)
    assert resp.status_code == 409 and _error(resp) == "PEDIDO_NO_PAGADO" and not repo.envios


def test_errores_de_pedidos_se_regresan_tal_cual(client, repo, pedidos, ana, crear_envio):
    resp = crear_envio(ana, PEDIDO_LUIS)                                 # pedido ajeno
    assert resp.status_code == 403 and _error(resp) == "ROL_INSUFICIENTE"
    resp = crear_envio(ana, PEDIDO_INEXISTENTE)
    assert resp.status_code == 404 and _error(resp) == "PEDIDO_NO_ENCONTRADO"
    pedidos.caido = True
    resp = crear_envio(ana, PEDIDO_ANA)
    assert resp.status_code == 503 and _error(resp) == "PEDIDOS_NO_DISPONIBLE"
    assert not repo.envios


def test_crear_requiere_jwt_y_pedido_id_valido(client, ana):
    assert client.post("/envios", json={"pedido_id": PEDIDO_ANA}).status_code == 401
    for cuerpo in ({}, {"pedido_id": "abc"}, {"pedido_id": 0}, {"pedido_id": True}, None):
        resp = client.post("/envios", json=cuerpo, headers=ana)
        assert resp.status_code == 400 and set(resp.get_json()) == {"error", "message"}


def test_pedidos_distintos_reciben_rutas_distintas(client, ana, crear_envio):
    a = crear_envio(ana, PEDIDO_ANA).get_json()
    b = crear_envio(ana, PEDIDO_ANA_2).get_json()
    assert a["codigo"] != b["codigo"] and a["ruta_id"] != b["ruta_id"]
    assert a["ruta_id"] == rutas.para_pedido(PEDIDO_ANA)


# ------------------------------------------------------------------ GET /envios y /envios/<codigo>
def test_listar_cliente_solo_los_suyos_admin_todos(client, ana, luis, admin, crear_envio):
    crear_envio(ana, PEDIDO_ANA)
    crear_envio(luis, PEDIDO_LUIS)
    suyos = client.get("/envios", headers=ana).get_json()
    assert suyos["total"] == 1 and suyos["items"][0]["user_id"] == ANA_ID
    assert client.get(f"/envios?user_id={ANA_ID}", headers=luis).get_json()["total"] == 1   # se ignora el filtro
    assert client.get("/envios", headers=admin).get_json()["total"] == 2
    assert client.get(f"/envios?user_id={ANA_ID}", headers=admin).get_json()["total"] == 1
    assert client.get("/envios?estado=XYZ", headers=admin).status_code == 400


def test_consultar_por_codigo_solo_dueno_o_admin(client, ana, luis, admin, crear_envio):
    codigo = crear_envio(ana, PEDIDO_ANA).get_json()["codigo"]
    datos = client.get(f"/envios/{codigo}", headers=ana).get_json()
    assert {"estado", "progreso", "posicion", "ruta", "recorrido", "pedido_id"} <= set(datos)
    assert client.get(f"/envios/{codigo.lower()}", headers=ana).status_code == 200        # sin importar mayusculas
    resp = client.get(f"/envios/{codigo}", headers=luis)
    assert resp.status_code == 403 and _error(resp) == "ROL_INSUFICIENTE"
    assert client.get(f"/envios/{codigo}", headers=admin).status_code == 200
    resp = client.get("/envios/LIB-MTY-2026-999999", headers=ana)
    assert resp.status_code == 404 and _error(resp) == "ENVIO_NO_ENCONTRADO"
    assert client.get(f"/envios/{codigo}").status_code == 401


# ------------------------------------------------------------------ estados por tiempo
def test_estados_por_tiempo(client, repo, ana, crear_envio, monkeypatch):
    codigo = crear_envio(ana, PEDIDO_ANA).get_json()["codigo"]
    tareas.ejecutar_una_vez(sincronizar=False)
    assert repo.envio(codigo)["estado"] == "CONFIRMADO"              # aun no pasan SEGUNDOS_CONFIRMADO
    monkeypatch.setattr(cfg, "SEGUNDOS_CONFIRMADO", 0)
    tareas.ejecutar_una_vez(sincronizar=False)
    assert repo.envio(codigo)["estado"] == "PREPARANDO"
    monkeypatch.setattr(cfg, "SEGUNDOS_PREPARANDO", 0)
    tareas.ejecutar_una_vez(sincronizar=False)
    assert repo.envio(codigo)["estado"] == "ENVIADO"
    tareas.ejecutar_una_vez(sincronizar=False)
    assert repo.envio(codigo)["estado"] == "ENVIADO"                 # por tiempo nunca pasa de ENVIADO


# ------------------------------------------------------------------ activos (simulador)
def test_activos_internos(client, repo, ana, luis, sin_esperas, crear_envio):
    assert client.get("/envios/internal/activos").status_code == 401
    assert client.get("/envios/internal/activos", headers=ana).status_code == 401           # un JWT no basta
    codigo = _enviado(client, repo, ana, PEDIDO_ANA)
    repo.forzar_estado(crear_envio(luis, PEDIDO_LUIS).get_json()["codigo"], "CONFIRMADO")
    datos = client.get("/envios/internal/activos", headers=INTERNA).get_json()
    assert [e["codigo"] for e in datos["items"]] == [codigo]
    assert datos["items"][0]["ruta"]["puntos"] and datos["items"][0]["ruta_id"] == rutas.para_pedido(PEDIDO_ANA)


# ------------------------------------------------------------------ posiciones y entrega
def test_posiciones_en_ruta_progreso_y_entrega(client, repo, ana, sin_esperas):
    codigo = _enviado(client, repo, ana, PEDIDO_ANA)
    ruta = rutas.obtener(repo.envio(codigo)["ruta_id"])
    medio = ruta.puntos[len(ruta.puntos) // 2]

    ack = _posicion(codigo, ruta.puntos[1])
    assert ack["type"] == "ack" and ack["estado"] == "EN_RUTA"
    ack = _posicion(codigo, medio)
    assert 0 < ack["progreso"] < 1 and ack["estado"] == "EN_RUTA"
    progreso_medio = ack["progreso"]

    # Llegar al ultimo punto SIN "final" no entrega, ni con final=false.
    assert _posicion(codigo, ruta.destino)["estado"] == "EN_RUTA"
    assert _posicion(codigo, ruta.destino, final=False)["estado"] == "EN_RUTA"
    assert repo.envio(codigo)["progreso"] < 1

    ack = _posicion(codigo, ruta.destino, final=True)
    assert ack["estado"] == "ENTREGADO" and ack["progreso"] == 1.0
    envio = client.get(f"/envios/{codigo}", headers=ana).get_json()
    assert envio["estado"] == "ENTREGADO" and envio["entregado_en"] is not None
    assert len(envio["recorrido"]) == 5 and envio["recorrido"][1]["progreso"] == progreso_medio
    assert envio["posicion"]["latitude"] == ruta.destino[0]


def test_final_lejos_del_destino_no_entrega(client, repo, ana, sin_esperas):
    codigo = _enviado(client, repo, ana, PEDIDO_ANA)
    ruta = rutas.obtener(repo.envio(codigo)["ruta_id"])
    lejos = (ruta.destino[0] + 0.001, ruta.destino[1])                   # ~111 m al norte
    ack = _posicion(codigo, lejos, final=True)
    assert ack["estado"] == "EN_RUTA" and "maximo 30 m" in ack["detail"]
    cerca = (ruta.destino[0] + 0.0001, ruta.destino[1])                  # ~11 m
    assert _posicion(codigo, cerca, final=True)["estado"] == "ENTREGADO"


def test_rechaza_codigos_inexistentes_o_no_activos(client, repo, ana, crear_envio):
    codigo = crear_envio(ana, PEDIDO_ANA).get_json()["codigo"]            # CONFIRMADO
    ruta = rutas.obtener(repo.envio(codigo)["ruta_id"])
    for codigo_malo, error in ((codigo, "ENVIO_NO_ACTIVO"), ("LIB-MTY-2026-999999", "ENVIO_NO_ENCONTRADO")):
        try:
            _posicion(codigo_malo, ruta.puntos[0])
            raise AssertionError("debio rechazarse")
        except envios_service.ApiError as e:
            assert e.code == error
    assert repo.envio(codigo)["estado"] == "CONFIRMADO" and not repo.posiciones(repo.envio(codigo)["id"], 500)
    repo.forzar_estado(codigo, "ENTREGADO")
    try:
        _posicion(codigo, ruta.puntos[0])
        raise AssertionError("un envio ENTREGADO no recibe posiciones")
    except envios_service.ApiError as e:
        assert e.code == "ENVIO_NO_ACTIVO"


def test_mensaje_gps_invalido():
    for datos in ({}, {"vehicle_id": "X", "latitude": 1, "longitude": 1, "speed": 1, "heading": 1, "extra": 1},
                  {"vehicle_id": "X", "latitude": 91, "longitude": 1, "speed": 1, "heading": 1},
                  {"vehicle_id": "X", "latitude": 1, "longitude": 1, "speed": -1, "heading": 1},
                  {"vehicle_id": "X", "latitude": 1, "longitude": 1, "speed": 1, "heading": 1, "final": "si"}):
        try:
            envios_service.validar_posicion(datos)
            raise AssertionError(f"debio rechazarse: {datos}")
        except envios_service.ApiError as e:
            assert e.status == 400


def test_recorrido_guarda_solo_las_ultimas(client, repo, ana, sin_esperas, monkeypatch):
    monkeypatch.setattr(cfg, "MAX_POSICIONES", 3)
    codigo = _enviado(client, repo, ana, PEDIDO_ANA)
    ruta = rutas.obtener(repo.envio(codigo)["ruta_id"])
    for punto in ruta.puntos[:6]:
        _posicion(codigo, punto)
    recorrido = client.get(f"/envios/{codigo}", headers=ana).get_json()["recorrido"]
    assert [(p["latitude"], p["longitude"]) for p in recorrido] == [tuple(p) for p in ruta.puntos[3:6]]


# ------------------------------------------------------------------ aviso a pedidos
def test_sincroniza_enviado_y_entregado_con_pedidos(client, repo, pedidos, ana, sin_esperas):
    codigo = _enviado(client, repo, ana, PEDIDO_ANA)
    tareas.ejecutar_una_vez()
    assert pedidos.cambios() == [(PEDIDO_ANA, "ENVIADO")] and pedidos.pedidos[PEDIDO_ANA]["estado"] == "ENVIADO"
    ruta = rutas.obtener(repo.envio(codigo)["ruta_id"])
    _posicion(codigo, ruta.destino, final=True)
    tareas.ejecutar_una_vez()
    assert pedidos.cambios()[-1] == (PEDIDO_ANA, "ENTREGADO") and pedidos.pedidos[PEDIDO_ANA]["estado"] == "ENTREGADO"
    assert repo.envio(codigo)["pedido_estado_sync"] == "ENTREGADO"
    tareas.ejecutar_una_vez()
    assert len(pedidos.cambios()) == 2                                       # nada pendiente: no se repite


def test_si_pedidos_falla_se_reintenta_sin_tirar_tracking(client, repo, pedidos, ana, sin_esperas):
    codigo = _enviado(client, repo, ana, PEDIDO_ANA)
    ruta = rutas.obtener(repo.envio(codigo)["ruta_id"])
    pedidos.caido = True
    tareas.ejecutar_una_vez()
    assert repo.envio(codigo)["pedido_estado_sync"] is None
    # el envio sigue su curso aunque pedidos este caido
    assert _posicion(codigo, ruta.destino, final=True)["estado"] == "ENTREGADO"
    tareas.ejecutar_una_vez()
    pedidos.caido = False
    tareas.ejecutar_una_vez()                                                # manda ENVIADO y luego ENTREGADO
    assert [c for c in pedidos.cambios()][-2:] == [(PEDIDO_ANA, "ENVIADO"), (PEDIDO_ANA, "ENTREGADO")]
    assert pedidos.pedidos[PEDIDO_ANA]["estado"] == "ENTREGADO"


def test_pedido_cancelado_no_se_reintenta_para_siempre(client, repo, pedidos, ana, sin_esperas):
    codigo = _enviado(client, repo, ana, PEDIDO_ANA)
    pedidos.pedidos[PEDIDO_ANA]["estado"] = "CANCELADO"
    tareas.ejecutar_una_vez()
    envio = repo.envio(codigo)
    assert envio["pedido_estado_sync"] is None and "CANCELADO" in envio["sync_error"]
    tareas.ejecutar_una_vez()
    assert len(pedidos.cambios()) == 1


def test_pedido_ya_enviado_cuenta_como_sincronizado(client, repo, pedidos, ana, sin_esperas):
    codigo = _enviado(client, repo, ana, PEDIDO_ANA)
    pedidos.pedidos[PEDIDO_ANA]["estado"] = "ENVIADO"                       # p. ej. lo marco el admin a mano
    tareas.ejecutar_una_vez()
    assert repo.envio(codigo)["pedido_estado_sync"] == "ENVIADO" and repo.envio(codigo)["sync_error"] is None


def test_admin_puede_crear_envio_de_otro_y_el_dueno_es_el_del_pedido(client, repo, admin, crear_envio):
    envio = crear_envio(admin, PEDIDO_ANA).get_json()
    assert envio["user_id"] == ANA_ID != ADMIN_ID
