"""Creacion con reserva, falta de stock, transiciones, cancelacion, expiracion, permisos y concurrencia basica."""
import threading

import pytest

from common import redis_client, redis_keys
from conftest import (ADMIN_ID, ALEPH, ANA_ID, CIEN, INTERNA, RAYUELA, SIN_INVENTARIO, TOTAL_2_CIEN_1_ALEPH,
                      RedisCaido, token)
from services import expiracion, pedidos_service


def _error(resp):
    return resp.get_json()["error"]


def _estado(client, cabecera, pedido_id):
    return client.get(f"/pedidos/{pedido_id}", headers=cabecera).get_json()["estado"]


def _pagar(client, pedido_id):
    return client.patch(f"/pedidos/internal/{pedido_id}/estado", headers=INTERNA, json={"estado": "PAGADO"})


# ------------------------------------------------------------------ crear con reserva
def test_crear_pedido_reserva_el_stock(client, repo, servicios, fake_redis, ana, pedir):
    resp = pedir(ana, {CIEN: 2, ALEPH: 1})
    assert resp.status_code == 201
    pedido = resp.get_json()
    assert pedido["estado"] == "PENDIENTE_PAGO" and pedido["user_id"] == ANA_ID      # el user_id sale del token
    assert pedido["total"] == TOTAL_2_CIEN_1_ALEPH == 850.5 and pedido["articulos"] == 3
    assert pedido["lineas"] == [                                                     # titulo y precio copiados de books
        {"isbn": CIEN, "titulo": "Cien años de soledad", "cantidad": 2, "precio_unitario": 300.0, "subtotal": 600.0},
        {"isbn": ALEPH, "titulo": "El Aleph", "cantidad": 1, "precio_unitario": 250.5, "subtotal": 250.5}]
    assert [(h["estado_anterior"], h["estado_nuevo"], h["actor"]) for h in pedido["historial"]] == [
        (None, "PENDIENTE_PAGO", f"user:{ANA_ID}")]

    assert repo.stock(CIEN) == (3, 2) and repo.stock(ALEPH) == (1, 1) and repo.stock(RAYUELA) == (10, 0)
    assert ("usuario", ANA_ID) in servicios.llamadas and ("libro", CIEN) in servicios.llamadas

    clave = redis_keys.pedido_reserva(pedido["id"])                                  # espejo en Redis, 15 minutos
    assert fake_redis.exists(clave) and 890 <= fake_redis.ttl(clave) <= 900


def test_el_precio_copiado_no_cambia_si_despues_cambia_el_libro(client, servicios, ana, pedir):
    pedido = pedir(ana, {CIEN: 1}).get_json()
    servicios.libros[CIEN] = ("Titulo nuevo", 999.0)
    linea = client.get(f"/pedidos/{pedido['id']}", headers=ana).get_json()["lineas"][0]
    assert linea["titulo"] == "Cien años de soledad" and linea["precio_unitario"] == 300.0


@pytest.mark.parametrize("cuerpo", [
    None, {}, {"lineas": []}, {"lineas": "x"}, {"lineas": ["x"]}, {"lineas": [{"isbn": CIEN}]},
    {"lineas": [{"isbn": CIEN, "cantidad": 0}]}, {"lineas": [{"isbn": CIEN, "cantidad": -1}]},
    {"lineas": [{"isbn": CIEN, "cantidad": "2"}]}, {"lineas": [{"isbn": CIEN, "cantidad": 1.5}]},
    {"lineas": [{"isbn": CIEN, "cantidad": 1000}]}, {"lineas": [{"isbn": "", "cantidad": 1}]},
    {"lineas": [{"isbn": CIEN, "cantidad": 1}, {"isbn": CIEN, "cantidad": 2}]},
])
def test_crear_con_datos_invalidos_400(client, repo, ana, cuerpo):
    resp = client.post("/pedidos", json=cuerpo, headers=ana)
    assert resp.status_code == 400 and _error(resp) == "VALIDACION"
    assert repo.pedidos == {} and repo.stock(CIEN) == (5, 0)


def test_no_se_puede_pedir_a_nombre_de_otro(client, repo, ana):
    resp = client.post("/pedidos", headers=ana, json={"user_id": 999, "lineas": [{"isbn": CIEN, "cantidad": 1}]})
    assert resp.status_code == 201 and resp.get_json()["user_id"] == ANA_ID


# ------------------------------------------------------------------ falta de stock
def test_sin_stock_suficiente_409_indicando_el_isbn(client, repo, fake_redis, ana, pedir):
    resp = pedir(ana, {CIEN: 1, ALEPH: 3})                      # de El Aleph solo hay 2
    assert resp.status_code == 409 and _error(resp) == "STOCK_INSUFICIENTE"
    mensaje = resp.get_json()["message"]
    assert ALEPH in mensaje and "disponible 2" in mensaje and "solicitado 3" in mensaje
    # nada se reservo: ni siquiera el ISBN que si alcanzaba
    assert repo.stock(CIEN) == (5, 0) and repo.stock(ALEPH) == (2, 0) and repo.pedidos == {}
    assert list(fake_redis.scan_iter("pedido:reserva:*")) == []


def test_isbn_sin_fila_de_inventario_409(client, repo, ana, pedir):
    resp = pedir(ana, {SIN_INVENTARIO: 1})
    assert resp.status_code == 409 and SIN_INVENTARIO in resp.get_json()["message"]


def test_el_stock_reservado_por_otro_pedido_ya_no_esta_disponible(client, repo, ana, luis, pedir):
    assert pedir(ana, {ALEPH: 2}).status_code == 201
    assert pedir(luis, {ALEPH: 1}).status_code == 409
    assert repo.stock(ALEPH) == (0, 2)


# ------------------------------------------------------------------ validacion contra books y users
def test_libro_inexistente_404(client, repo, ana, pedir):
    resp = pedir(ana, {CIEN: 1, "9789999999999": 1})
    assert resp.status_code == 404 and _error(resp) == "LIBRO_NO_ENCONTRADO" and "9789999999999" in resp.get_json()["message"]
    assert repo.stock(CIEN) == (5, 0)


@pytest.mark.parametrize("servicio, codigo", [("books", "BOOKS_NO_DISPONIBLE"), ("users", "USERS_NO_DISPONIBLE")])
def test_books_o_users_caidos_503(client, repo, servicios, ana, pedir, servicio, codigo):
    servicios.caidos.add(servicio)
    resp = pedir(ana, {CIEN: 1})
    assert resp.status_code == 503 and _error(resp) == codigo and repo.stock(CIEN) == (5, 0)


def test_usuario_inexistente_o_inactivo_403(client, repo, servicios, ana, pedir):
    servicios.usuarios[ANA_ID] = False
    resp = pedir(ana, {CIEN: 1})
    assert resp.status_code == 403 and _error(resp) == "USUARIO_NO_VALIDO"
    del servicios.usuarios[ANA_ID]
    assert pedir(ana, {CIEN: 1}).status_code == 403 and repo.pedidos == {}


# ------------------------------------------------------------------ consultas y permisos
@pytest.mark.parametrize("metodo, ruta", [
    ("post", "/pedidos"), ("get", "/pedidos"), ("get", "/pedidos/1"), ("put", "/pedidos/1"),
    ("patch", "/pedidos/1/lineas"), ("patch", "/pedidos/1/cancelar"), ("patch", "/pedidos/1/estado"),
    ("delete", "/pedidos/1"), ("post", "/inventario"), ("put", f"/inventario/{CIEN}"), ("delete", f"/inventario/{CIEN}"),
])
def test_sin_token_401(client, metodo, ruta):
    resp = getattr(client, metodo)(ruta, json={})
    assert resp.status_code == 401 and _error(resp) == "TOKEN_AUSENTE"


def test_cliente_solo_ve_sus_pedidos_y_admin_todos(client, ana, luis, admin, pedir):
    de_ana = pedir(ana, {CIEN: 1}).get_json()["id"]
    de_luis = pedir(luis, {RAYUELA: 2}).get_json()["id"]

    lista = client.get("/pedidos", headers=ana).get_json()
    assert [p["id"] for p in lista["items"]] == [de_ana] and lista["total"] == 1
    assert lista["items"][0]["articulos"] == 1 and "lineas" not in lista["items"][0]
    # un cliente no puede pedir los de otro con el filtro user_id
    assert [p["id"] for p in client.get(f"/pedidos?user_id={LUIS}", headers=ana).get_json()["items"]] == [de_ana]

    assert [p["id"] for p in client.get("/pedidos", headers=admin).get_json()["items"]] == [de_luis, de_ana]
    assert [p["id"] for p in client.get(f"/pedidos?user_id={LUIS}", headers=admin).get_json()["items"]] == [de_luis]
    assert client.get("/pedidos?estado=PAGADO", headers=admin).get_json()["total"] == 0
    assert client.get("/pedidos?estado=pendiente_pago", headers=admin).get_json()["total"] == 2
    assert client.get("/pedidos?estado=INVENTADO", headers=admin).status_code == 400

    assert client.get(f"/pedidos/{de_luis}", headers=ana).status_code == 403
    assert client.get(f"/pedidos/{de_luis}", headers=admin).status_code == 200
    assert client.get("/pedidos/999", headers=ana).status_code == 404


LUIS = 32


def test_acciones_de_admin_403_para_el_cliente(client, repo, ana, pedir):
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    for metodo, ruta, cuerpo in (("patch", f"/pedidos/{pedido}/estado", {"estado": "ENVIADO"}),
                                 ("delete", f"/pedidos/{pedido}", None),
                                 ("post", "/inventario", {"isbn": SIN_INVENTARIO, "stock_disponible": 5}),
                                 ("put", f"/inventario/{CIEN}", {"stock_disponible": 99}),
                                 ("delete", f"/inventario/{RAYUELA}", None)):
        resp = getattr(client, metodo)(ruta, json=cuerpo, headers=ana)
        assert resp.status_code == 403 and _error(resp) == "ROL_INSUFICIENTE"
    assert repo.stock(CIEN) == (4, 1) and RAYUELA in repo.inventario


def test_solo_el_dueno_edita_o_cancela(client, repo, ana, luis, admin, pedir):
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    cuerpo = {"lineas": [{"isbn": CIEN, "cantidad": 3}]}
    for cabecera in (luis, admin):                              # ni otro cliente ni el admin editan pedidos ajenos
        assert client.put(f"/pedidos/{pedido}", json=cuerpo, headers=cabecera).status_code == 403
        assert client.patch(f"/pedidos/{pedido}/lineas", json=cuerpo, headers=cabecera).status_code == 403
    assert client.patch(f"/pedidos/{pedido}/cancelar", headers=luis).status_code == 403
    assert repo.stock(CIEN) == (4, 1) and _estado(client, ana, pedido) == "PENDIENTE_PAGO"


def test_endpoints_internos_exigen_la_clave(client, ana, admin, pedir):
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    assert client.get(f"/pedidos/internal/{pedido}").status_code == 401
    assert client.get(f"/pedidos/internal/{pedido}", headers=admin).status_code == 401       # un JWT no basta
    assert client.patch(f"/pedidos/internal/{pedido}/estado", json={"estado": "PAGADO"}, headers=admin).status_code == 401
    interno = client.get(f"/pedidos/internal/{pedido}", headers=INTERNA)
    assert interno.status_code == 200 and interno.get_json()["total"] == 300.0 and interno.get_json()["user_id"] == ANA_ID
    assert client.get("/pedidos/internal/999", headers=INTERNA).status_code == 404


# ------------------------------------------------------------------ editar lineas
def test_put_reemplaza_las_lineas_y_reajusta_la_reserva(client, repo, servicios, ana, pedir):
    pedido = pedir(ana, {CIEN: 2, ALEPH: 1}).get_json()["id"]
    servicios.libros[CIEN] = ("Otro titulo", 999.0)             # el precio de una linea existente no cambia
    resp = client.put(f"/pedidos/{pedido}", headers=ana, json={"lineas": [{"isbn": CIEN, "cantidad": 4},
                                                                           {"isbn": RAYUELA, "cantidad": 2}]})
    assert resp.status_code == 200
    datos = resp.get_json()
    assert {l["isbn"]: (l["cantidad"], l["precio_unitario"]) for l in datos["lineas"]} == {
        CIEN: (4, 300.0), RAYUELA: (2, 199.99)}
    assert datos["total"] == 1599.98 and datos["estado"] == "PENDIENTE_PAGO"
    assert repo.stock(CIEN) == (1, 4) and repo.stock(ALEPH) == (2, 0) and repo.stock(RAYUELA) == (8, 2)


def test_patch_lineas_cambia_agrega_y_quita(client, repo, ana, pedir):
    pedido = pedir(ana, {CIEN: 2, ALEPH: 1}).get_json()["id"]
    resp = client.patch(f"/pedidos/{pedido}/lineas", headers=ana, json={"lineas": [
        {"isbn": CIEN, "cantidad": 1}, {"isbn": ALEPH, "cantidad": 0}, {"isbn": RAYUELA, "cantidad": 3}]})
    assert resp.status_code == 200
    assert {l["isbn"]: l["cantidad"] for l in resp.get_json()["lineas"]} == {CIEN: 1, RAYUELA: 3}
    assert resp.get_json()["total"] == 899.97
    assert repo.stock(CIEN) == (4, 1) and repo.stock(ALEPH) == (2, 0) and repo.stock(RAYUELA) == (7, 3)


def test_editar_sin_stock_409_y_no_cambia_nada(client, repo, ana, pedir):
    pedido = pedir(ana, {CIEN: 2}).get_json()["id"]
    resp = client.patch(f"/pedidos/{pedido}/lineas", headers=ana,
                        json={"lineas": [{"isbn": CIEN, "cantidad": 6}, {"isbn": RAYUELA, "cantidad": 1}]})
    assert resp.status_code == 409 and _error(resp) == "STOCK_INSUFICIENTE" and CIEN in resp.get_json()["message"]
    assert repo.stock(CIEN) == (3, 2) and repo.stock(RAYUELA) == (10, 0)
    assert client.get(f"/pedidos/{pedido}", headers=ana).get_json()["lineas"][0]["cantidad"] == 2
    # 5 si alcanza: las 2 que ya tenia reservadas cuentan
    assert client.patch(f"/pedidos/{pedido}/lineas", headers=ana,
                        json={"lineas": [{"isbn": CIEN, "cantidad": 5}]}).status_code == 200
    assert repo.stock(CIEN) == (0, 5)


def test_un_pedido_no_puede_quedar_sin_lineas(client, repo, ana, pedir):
    pedido = pedir(ana, {CIEN: 2}).get_json()["id"]
    resp = client.patch(f"/pedidos/{pedido}/lineas", headers=ana, json={"lineas": [{"isbn": CIEN, "cantidad": 0}]})
    assert resp.status_code == 400 and repo.stock(CIEN) == (3, 2)
    assert client.put(f"/pedidos/{pedido}", headers=ana, json={"lineas": [{"isbn": CIEN, "cantidad": 0}]}).status_code == 400


def test_solo_se_edita_en_pendiente_de_pago_y_sin_vencer(client, repo, ana, pedir):
    cuerpo = {"lineas": [{"isbn": CIEN, "cantidad": 1}]}
    pagado = pedir(ana, {CIEN: 2}).get_json()["id"]
    _pagar(client, pagado)
    resp = client.put(f"/pedidos/{pagado}", headers=ana, json=cuerpo)
    assert resp.status_code == 409 and _error(resp) == "PEDIDO_NO_EDITABLE"

    vencido = pedir(ana, {RAYUELA: 2}).get_json()["id"]
    repo.vencer(vencido)
    resp = client.patch(f"/pedidos/{vencido}/lineas", headers=ana, json={"lineas": [{"isbn": RAYUELA, "cantidad": 5}]})
    assert resp.status_code == 409 and _error(resp) == "PEDIDO_EXPIRADO" and repo.stock(RAYUELA) == (8, 2)


# ------------------------------------------------------------------ cancelacion con liberacion de stock
def test_el_dueno_cancela_y_el_stock_regresa(client, repo, fake_redis, ana, pedir):
    pedido = pedir(ana, {CIEN: 2, ALEPH: 1}).get_json()["id"]
    assert repo.stock(CIEN) == (3, 2)
    resp = client.patch(f"/pedidos/{pedido}/cancelar", headers=ana)
    assert resp.status_code == 200 and resp.get_json()["estado"] == "CANCELADO"
    assert resp.get_json()["historial"][-1]["estado_anterior"] == "PENDIENTE_PAGO"
    assert resp.get_json()["historial"][-1]["actor"] == f"user:{ANA_ID}"
    assert repo.stock(CIEN) == (5, 0) and repo.stock(ALEPH) == (2, 0)                # todo regreso
    assert not fake_redis.exists(redis_keys.pedido_reserva(pedido))

    otra = client.patch(f"/pedidos/{pedido}/cancelar", headers=ana)                  # no se libera dos veces
    assert otra.status_code == 409 and _error(otra) == "TRANSICION_INVALIDA" and repo.stock(CIEN) == (5, 0)


def test_cancelar_un_pedido_pagado_solo_el_admin_y_devuelve_las_unidades(client, repo, ana, admin, pedir):
    pedido = pedir(ana, {CIEN: 2}).get_json()["id"]
    assert _pagar(client, pedido).status_code == 200
    assert repo.stock(CIEN) == (3, 0)                                                # venta confirmada: ya no esta reservado

    resp = client.patch(f"/pedidos/{pedido}/cancelar", headers=ana)
    assert resp.status_code == 403 and repo.stock(CIEN) == (3, 0)
    resp = client.patch(f"/pedidos/{pedido}/cancelar", headers=admin)
    assert resp.status_code == 200 and resp.get_json()["estado"] == "CANCELADO"
    assert resp.get_json()["historial"][-1]["actor"] == f"admin:{ADMIN_ID}"
    assert repo.stock(CIEN) == (5, 0)


# ------------------------------------------------------------------ transiciones
def test_flujo_completo_de_estados(client, repo, ana, admin, pedir):
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    pago = _pagar(client, pedido)
    assert pago.status_code == 200 and pago.get_json()["estado"] == "PAGADO"
    assert pago.get_json()["historial"][-1]["actor"] == "servicio:pagos"
    for estado in ("ENVIADO", "ENTREGADO"):
        resp = client.patch(f"/pedidos/{pedido}/estado", json={"estado": estado}, headers=admin)
        assert resp.status_code == 200 and resp.get_json()["estado"] == estado
    historial = client.get(f"/pedidos/{pedido}", headers=ana).get_json()["historial"]
    assert [h["estado_nuevo"] for h in historial] == ["PENDIENTE_PAGO", "PAGADO", "ENVIADO", "ENTREGADO"]
    assert repo.stock(CIEN) == (4, 0)


@pytest.mark.parametrize("previos, intento", [
    ([], "ENVIADO"),                                   # PENDIENTE_PAGO -> ENVIADO
    ([], "ENTREGADO"),
    (["PAGADO"], "ENTREGADO"),                         # PAGADO -> ENTREGADO (falta ENVIADO)
    (["PAGADO", "ENVIADO"], "ENVIADO"),
    (["PAGADO", "ENVIADO", "ENTREGADO"], "ENVIADO"),
])
def test_transiciones_invalidas_409(client, repo, ana, admin, pedir, previos, intento):
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    for estado in previos:
        if estado == "PAGADO":
            _pagar(client, pedido)
        else:
            client.patch(f"/pedidos/{pedido}/estado", json={"estado": estado}, headers=admin)
    antes = _estado(client, ana, pedido)
    resp = client.patch(f"/pedidos/{pedido}/estado", json={"estado": intento}, headers=admin)
    assert resp.status_code == 409 and _error(resp) == "TRANSICION_INVALIDA"
    assert antes in resp.get_json()["message"] and _estado(client, ana, pedido) == antes


def test_estados_finales_no_admiten_cambios(client, repo, ana, admin, pedir):
    cancelado = pedir(ana, {CIEN: 1}).get_json()["id"]
    client.patch(f"/pedidos/{cancelado}/cancelar", headers=ana)
    assert _pagar(client, cancelado).status_code == 409                              # no se paga un pedido cancelado
    assert client.patch(f"/pedidos/{cancelado}/estado", json={"estado": "ENVIADO"}, headers=admin).status_code == 409

    enviado = pedir(ana, {CIEN: 1}).get_json()["id"]
    _pagar(client, enviado)
    client.patch(f"/pedidos/{enviado}/estado", json={"estado": "ENVIADO"}, headers=admin)
    assert client.patch(f"/pedidos/{enviado}/cancelar", headers=admin).status_code == 409   # ENVIADO no es cancelable
    assert _pagar(client, enviado).status_code == 409 and repo.stock(CIEN) == (4, 0)


def test_el_admin_solo_marca_enviado_o_entregado_y_pagos_solo_pagado_o_cancelado(client, ana, admin, pedir):
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    for estado in ("PAGADO", "CANCELADO", "EXPIRADO", "PENDIENTE_PAGO", "otro", None):
        assert client.patch(f"/pedidos/{pedido}/estado", json={"estado": estado}, headers=admin).status_code == 400
    for estado in ("ENVIADO", "EXPIRADO", None):
        assert client.patch(f"/pedidos/internal/{pedido}/estado", json={"estado": estado}, headers=INTERNA).status_code == 400
    assert _estado(client, ana, pedido) == "PENDIENTE_PAGO"


def test_pagos_puede_cancelar_y_libera_el_stock(client, repo, ana, pedir):
    pedido = pedir(ana, {CIEN: 2}).get_json()["id"]
    resp = client.patch(f"/pedidos/internal/{pedido}/estado", json={"estado": "CANCELADO"}, headers=INTERNA)
    assert resp.status_code == 200 and repo.stock(CIEN) == (5, 0)


# ------------------------------------------------------------------ borrado logico
def test_delete_solo_cancelado_o_expirado_y_es_logico(client, repo, ana, admin, pedir):
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    resp = client.delete(f"/pedidos/{pedido}", headers=admin)
    assert resp.status_code == 409 and _error(resp) == "PEDIDO_NO_ELIMINABLE"

    client.patch(f"/pedidos/{pedido}/cancelar", headers=ana)
    assert client.delete(f"/pedidos/{pedido}", headers=admin).status_code == 200
    assert pedido in repo.pedidos and repo.pedidos[pedido]["eliminado_en"] is not None   # la fila sigue ahi
    assert client.get(f"/pedidos/{pedido}", headers=admin).status_code == 404
    assert client.get("/pedidos", headers=ana).get_json()["total"] == 0
    assert client.delete(f"/pedidos/{pedido}", headers=admin).status_code == 404


# ------------------------------------------------------------------ expiracion
def test_expiracion_pasa_a_expirado_y_libera_el_stock(client, repo, fake_redis, ana, luis, pedir):
    vencido = pedir(ana, {CIEN: 2, ALEPH: 1}).get_json()["id"]
    vigente = pedir(luis, {CIEN: 1}).get_json()["id"]
    pagado = pedir(ana, {RAYUELA: 1}).get_json()["id"]
    _pagar(client, pagado)
    repo.vencer(vencido)
    repo.vencer(pagado)                                         # un pedido pagado nunca expira

    assert expiracion.ejecutar_una_vez() == [vencido]

    datos = client.get(f"/pedidos/{vencido}", headers=ana).get_json()
    assert datos["estado"] == "EXPIRADO"
    assert (datos["historial"][-1]["estado_anterior"], datos["historial"][-1]["actor"]) == ("PENDIENTE_PAGO", "sistema:expiracion")
    assert repo.stock(CIEN) == (4, 1) and repo.stock(ALEPH) == (2, 0)                # solo queda lo de Luis
    assert _estado(client, luis, vigente) == "PENDIENTE_PAGO" and _estado(client, ana, pagado) == "PAGADO"
    assert not fake_redis.exists(redis_keys.pedido_reserva(vencido))
    assert fake_redis.exists(redis_keys.pedido_reserva(vigente))

    assert _pagar(client, vencido).status_code == 409           # ya no se puede pagar
    assert client.patch(f"/pedidos/{vencido}/cancelar", headers=ana).status_code == 409


def test_la_expiracion_usa_el_lock_de_redis(client, repo, fake_redis, ana, pedir):
    pedido = pedir(ana, {CIEN: 1}).get_json()["id"]
    repo.vencer(pedido)

    fake_redis.set(redis_keys.LOCK_EXPIRAR_PEDIDOS, "otro-proceso", ex=30)
    assert expiracion.ejecutar_una_vez() is None                # otro proceso tiene el lock: no hace nada
    assert _estado(client, ana, pedido) == "PENDIENTE_PAGO"

    fake_redis.delete(redis_keys.LOCK_EXPIRAR_PEDIDOS)
    assert expiracion.ejecutar_una_vez() == [pedido]
    assert 0 < fake_redis.ttl(redis_keys.LOCK_EXPIRAR_PEDIDOS) <= 30     # SET NX EX 30
    assert expiracion.ejecutar_una_vez() is None                # el lock sigue tomado hasta que caduque


def test_postgresql_es_la_fuente_de_verdad_de_la_expiracion(client, repo, fake_redis, ana, pedir):
    vigente = pedir(ana, {CIEN: 1}).get_json()["id"]
    vencido = pedir(ana, {CIEN: 1}).get_json()["id"]
    repo.vencer(vencido)
    fake_redis.delete(redis_keys.pedido_reserva(vigente))       # se perdio la clave de Redis del vigente...
    assert expiracion.ejecutar_una_vez() == [vencido]           # ...y aun asi decide expira_en de la base
    assert _estado(client, ana, vigente) == "PENDIENTE_PAGO"


def test_con_redis_caido_la_expiracion_se_salta_la_vuelta(repo, servicios):
    redis_client.set_client(RedisCaido())
    try:
        assert expiracion.ejecutar_una_vez() is None
    finally:
        redis_client.set_client(None)


def test_la_reserva_dura_lo_que_diga_RESERVA_MINUTOS(client, repo, fake_redis, ana, pedir, monkeypatch):
    monkeypatch.setattr(pedidos_service.cfg, "RESERVA_MINUTOS", 1)
    monkeypatch.setattr(pedidos_service.cfg, "RESERVA_SEGUNDOS", 60)
    pedido = pedir(ana, {CIEN: 1}).get_json()
    segundos = (repo.pedidos[pedido["id"]]["expira_en"] - repo.pedidos[pedido["id"]]["created_at"]).total_seconds()
    assert 59 <= segundos <= 61 and 50 <= fake_redis.ttl(redis_keys.pedido_reserva(pedido["id"])) <= 60


# ------------------------------------------------------------------ Redis caido
def test_con_redis_caido_no_se_aceptan_pedidos(client, repo, ana, pedir):
    redis_client.set_client(RedisCaido())           # sin Redis no se puede validar el JWT: 503 (fallo seguro)
    resp = pedir(ana, {CIEN: 1})
    assert resp.status_code == 503 and _error(resp) == "REDIS_NO_DISPONIBLE" and repo.stock(CIEN) == (5, 0)
    assert client.get("/inventario").status_code == 200         # las lecturas publicas siguen


# ------------------------------------------------------------------ inventario
def test_inventario_publico(client):
    lista = client.get("/inventario").get_json()                # sin token
    assert lista["total"] == 3 and [i["isbn"] for i in lista["items"]] == [CIEN, ALEPH, RAYUELA]
    assert client.get(f"/inventario/{CIEN}").get_json()["stock_disponible"] == 5
    assert set(client.get(f"/inventario/{CIEN}").get_json()) == {"isbn", "stock_disponible", "stock_reservado", "updated_at"}
    assert client.get("/inventario/9789999999999").status_code == 404


def test_admin_carga_actualiza_y_elimina_stock(client, repo, servicios, admin):
    alta = client.post("/inventario", json={"isbn": SIN_INVENTARIO, "stock_disponible": 7}, headers=admin)
    assert alta.status_code == 201 and alta.get_json()["stock_disponible"] == 7 and alta.get_json()["stock_reservado"] == 0
    assert client.post("/inventario", json={"isbn": SIN_INVENTARIO, "stock_disponible": 1}, headers=admin).status_code == 409
    assert client.post("/inventario", json={"isbn": "9789999999999", "stock_disponible": 1}, headers=admin).status_code == 404

    cambio = client.put(f"/inventario/{SIN_INVENTARIO}", json={"stock_disponible": 20}, headers=admin)
    assert cambio.status_code == 200 and repo.stock(SIN_INVENTARIO) == (20, 0)
    assert client.put("/inventario/9789999999999", json={"stock_disponible": 1}, headers=admin).status_code == 404
    for malo in (-1, "5", 1.5, None, True):
        assert client.put(f"/inventario/{SIN_INVENTARIO}", json={"stock_disponible": malo}, headers=admin).status_code == 400

    assert client.delete(f"/inventario/{SIN_INVENTARIO}", headers=admin).status_code == 200
    assert client.delete(f"/inventario/{SIN_INVENTARIO}", headers=admin).status_code == 404

    servicios.caidos.add("books")
    assert client.post("/inventario", json={"isbn": SIN_INVENTARIO, "stock_disponible": 1}, headers=admin).status_code == 503


def test_fijar_el_disponible_no_toca_lo_reservado_y_no_se_borra_con_reservas(client, repo, ana, admin, pedir):
    pedir(ana, {CIEN: 2})
    assert client.put(f"/inventario/{CIEN}", json={"stock_disponible": 50}, headers=admin).status_code == 200
    assert repo.stock(CIEN) == (50, 2)
    resp = client.delete(f"/inventario/{CIEN}", headers=admin)
    assert resp.status_code == 409 and _error(resp) == "INVENTARIO_CON_RESERVAS" and CIEN in repo.inventario


# ------------------------------------------------------------------ concurrencia basica
def test_concurrencia_sobre_el_mismo_isbn_nunca_sobrevende(client, repo, pedir):
    """10 clientes piden a la vez 1 unidad de un libro con 3 en stock: exactamente 3 lo consiguen."""
    repo.inventario[ALEPH].update(stock_disponible=3, stock_reservado=0)
    resultados, arranque = [], threading.Barrier(10)

    def comprar(user_id):
        cliente = client.application.test_client()
        arranque.wait()
        resp = cliente.post("/pedidos", headers=token(user_id), json={"lineas": [{"isbn": ALEPH, "cantidad": 1}]})
        resultados.append(resp.status_code)

    hilos = [threading.Thread(target=comprar, args=(ANA_ID,)) for _ in range(10)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == [201] * 3 + [409] * 7
    assert repo.stock(ALEPH) == (0, 3) and len(repo.pedidos) == 3
