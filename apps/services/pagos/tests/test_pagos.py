"""
Pago aprobado y rechazado, idempotencia, monto manipulado, pedido ajeno,
lock concurrente, pedidos caido con sincronizacion posterior, reembolso,
permisos (401 y 403) y que ningun log contenga numeros de tarjeta.
"""
import json
import logging
import threading

import pytest

from common import redis_client, redis_keys
from conftest import (ANA_ID, LUIS_ID, PEDIDO_ANA, PEDIDO_INEXISTENTE, PEDIDO_LUIS, PEDIDO_PAGADO, TARJETA_BUENA,
                      TARJETA_RECHAZADA, RedisCaido, RedisQueFallaAlPagar, nueva_llave, token)
from services import pagos_service, sincronizacion

NUMERO_BUENO = TARJETA_BUENA.replace(" ", "")
NUMERO_RECHAZADO = TARJETA_RECHAZADA.replace("-", "")
CAMPOS_DE_UN_PAGO = {"id", "pedido_id", "user_id", "monto", "metodo", "estado", "referencia", "ultimos4",
                     "sincronizado", "notas", "created_at", "updated_at"}


def _error(resp):
    return resp.get_json()["error"]


# ------------------------------------------------------------------ pago aprobado
def test_pago_aprobado_deja_el_pedido_en_pagado(client, repo, pedidos, fake_redis, ana, pagar):
    llave = nueva_llave()
    resp = pagar(ana, PEDIDO_ANA, llave=llave)
    assert resp.status_code == 201
    pago = resp.get_json()
    assert set(pago) == CAMPOS_DE_UN_PAGO | {"repetido"} and pago["repetido"] is False
    assert pago["estado"] == "APROBADO" and pago["metodo"] == "TARJETA_SIMULADA"
    assert pago["pedido_id"] == PEDIDO_ANA and pago["user_id"] == ANA_ID            # el usuario sale del token
    assert pago["monto"] == 850.5                                                   # el monto sale del pedido
    assert pago["ultimos4"] == "1111" and pago["referencia"].startswith("PAG-")
    assert pago["sincronizado"] is True

    assert pedidos.estado(PEDIDO_ANA) == "PAGADO"
    assert pedidos.cambios() == [("cambiar_estado", PEDIDO_ANA, "PAGADO")]

    clave = redis_keys.pago_idem(llave)                                             # idempotencia: 24 horas
    assert fake_redis.get(clave) == str(pago["id"]) and 86390 <= fake_redis.ttl(clave) <= 86400
    assert not fake_redis.exists(redis_keys.pago_lock(PEDIDO_ANA))                  # el lock se libero


@pytest.mark.parametrize("metodo", ["TRANSFERENCIA", "EFECTIVO", "efectivo"])
def test_pago_sin_tarjeta(client, repo, pedidos, ana, pagar, metodo):
    resp = pagar(ana, PEDIDO_ANA, metodo=metodo)
    assert resp.status_code == 201
    assert resp.get_json()["estado"] == "APROBADO" and resp.get_json()["metodo"] == metodo.upper()
    assert resp.get_json()["ultimos4"] is None and pedidos.estado(PEDIDO_ANA) == "PAGADO"


# ------------------------------------------------------------------ pago rechazado
def test_tarjeta_terminada_en_0000_se_rechaza_y_el_pedido_sigue_pendiente(client, repo, pedidos, ana, pagar):
    resp = pagar(ana, PEDIDO_ANA, tarjeta=TARJETA_RECHAZADA)
    assert resp.status_code == 201                              # el intento queda registrado...
    pago = resp.get_json()
    assert pago["estado"] == "RECHAZADO" and pago["ultimos4"] == "0000" and pago["monto"] == 850.5
    assert pago["sincronizado"] is True                         # ...y no hay nada que avisar a pedidos
    assert pedidos.estado(PEDIDO_ANA) == "PENDIENTE_PAGO" and pedidos.cambios() == []


def test_tras_un_rechazo_se_puede_pagar_con_otra_tarjeta_y_otra_llave(client, repo, pedidos, ana, pagar):
    assert pagar(ana, PEDIDO_ANA, tarjeta=TARJETA_RECHAZADA).get_json()["estado"] == "RECHAZADO"
    segundo = pagar(ana, PEDIDO_ANA)
    assert segundo.status_code == 201 and segundo.get_json()["estado"] == "APROBADO"
    assert pedidos.estado(PEDIDO_ANA) == "PAGADO"
    assert [p["estado"] for p in client.get(f"/pagos/pedido/{PEDIDO_ANA}", headers=ana).get_json()["items"]] == [
        "APROBADO", "RECHAZADO"]


# ------------------------------------------------------------------ idempotencia
def test_doble_envio_con_la_misma_llave_es_un_solo_pago(client, repo, pedidos, ana, pagar):
    llave = nueva_llave()
    primero = pagar(ana, PEDIDO_ANA, llave=llave)
    segundo = pagar(ana, PEDIDO_ANA, llave=llave)
    tercero = pagar(ana, PEDIDO_ANA, llave=llave)

    assert primero.status_code == 201 and segundo.status_code == 200 and tercero.status_code == 200
    assert segundo.get_json()["repetido"] is True
    sin_marca = lambda r: {k: v for k, v in r.get_json().items() if k != "repetido"}        # noqa: E731
    assert sin_marca(primero) == sin_marca(segundo) == sin_marca(tercero)                    # el MISMO pago
    assert len(repo.pagos) == 1                                                              # no se cobro otra vez
    assert pedidos.cambios() == [("cambiar_estado", PEDIDO_ANA, "PAGADO")]                   # ni se aviso otra vez


def test_idempotencia_con_la_base_como_respaldo_si_redis_perdio_la_llave(client, repo, fake_redis, ana, pagar):
    llave = nueva_llave()
    primero = pagar(ana, PEDIDO_ANA, llave=llave).get_json()
    fake_redis.delete(redis_keys.pago_idem(llave))              # la llave ya no esta en Redis
    segundo = pagar(ana, PEDIDO_ANA, llave=llave)
    assert segundo.status_code == 200 and segundo.get_json()["id"] == primero["id"] and len(repo.pagos) == 1


def test_un_rechazo_tambien_es_idempotente(client, repo, ana, pagar):
    llave = nueva_llave()
    primero = pagar(ana, PEDIDO_ANA, tarjeta=TARJETA_RECHAZADA, llave=llave)
    # reintentar con la MISMA llave no vuelve a evaluar la tarjeta: devuelve el rechazo ya registrado
    segundo = pagar(ana, PEDIDO_ANA, tarjeta=TARJETA_BUENA, llave=llave)
    assert segundo.status_code == 200 and segundo.get_json()["estado"] == "RECHAZADO"
    assert segundo.get_json()["id"] == primero.get_json()["id"] and len(repo.pagos) == 1


def test_la_llave_de_otro_pago_no_se_puede_reutilizar(client, repo, pedidos, ana, luis, pagar):
    llave = nueva_llave()
    assert pagar(ana, PEDIDO_ANA, llave=llave).status_code == 201
    de_otro_usuario = pagar(luis, PEDIDO_LUIS, llave=llave)
    assert de_otro_usuario.status_code == 409 and _error(de_otro_usuario) == "LLAVE_YA_USADA"
    assert "monto" not in json.dumps(de_otro_usuario.get_json())            # no se filtra el pago ajeno
    assert len(repo.pagos) == 1 and pedidos.estado(PEDIDO_LUIS) == "PENDIENTE_PAGO"


@pytest.mark.parametrize("cabeceras", [{}, {"Idempotency-Key": ""}, {"Idempotency-Key": "corta"},
                                       {"Idempotency-Key": "con espacios y simbolos !"},
                                       {"Idempotency-Key": "x" * 101}])
def test_sin_idempotency_key_valida_400(client, repo, pedidos, ana, cabeceras):
    resp = client.post("/pagos", headers={**ana, **cabeceras},
                       json={"pedido_id": PEDIDO_ANA, "metodo": "EFECTIVO"})
    assert resp.status_code == 400 and _error(resp) == "VALIDACION" and "Idempotency-Key" in resp.get_json()["message"]
    assert repo.pagos == {} and pedidos.llamadas == []


def test_un_pedido_pagado_no_se_paga_dos_veces_aunque_cambie_la_llave(client, repo, pedidos, ana, pagar):
    assert pagar(ana, PEDIDO_ANA).status_code == 201
    otra = pagar(ana, PEDIDO_ANA)                               # llave nueva
    assert otra.status_code == 409 and _error(otra) == "PEDIDO_NO_PAGABLE" and len(repo.pagos) == 1


# ------------------------------------------------------------------ monto manipulado
@pytest.mark.parametrize("extra", [{"monto": 1}, {"monto": 0.01, "total": 0.01}, {"monto": "1", "user_id": LUIS_ID},
                                   {"estado": "APROBADO", "monto": -5, "sincronizado": True}])
def test_el_monto_y_los_demas_campos_enviados_por_el_cliente_se_ignoran(client, repo, ana, pagar, extra):
    resp = pagar(ana, PEDIDO_ANA, **extra)
    assert resp.status_code == 201
    pago = resp.get_json()
    assert pago["monto"] == 850.5 and pago["user_id"] == ANA_ID and pago["estado"] == "APROBADO"
    assert float(repo.pagos[pago["id"]]["monto"]) == 850.5


# ------------------------------------------------------------------ validacion del pedido
def test_pagar_un_pedido_ajeno_403(client, repo, pedidos, ana, pagar):
    resp = pagar(ana, PEDIDO_LUIS)
    assert resp.status_code == 403 and _error(resp) == "ROL_INSUFICIENTE"
    assert repo.pagos == {} and pedidos.estado(PEDIDO_LUIS) == "PENDIENTE_PAGO"


def test_ni_el_admin_paga_un_pedido_ajeno(client, repo, admin, pagar):
    assert pagar(admin, PEDIDO_ANA).status_code == 403 and repo.pagos == {}


def test_pedido_inexistente_404_y_pedido_que_no_esta_pendiente_409(client, repo, ana, pagar):
    inexistente = pagar(ana, PEDIDO_INEXISTENTE)
    assert inexistente.status_code == 404 and _error(inexistente) == "PEDIDO_NO_ENCONTRADO"
    ya_pagado = pagar(ana, PEDIDO_PAGADO)
    assert ya_pagado.status_code == 409 and _error(ya_pagado) == "PEDIDO_NO_PAGABLE"
    assert "PAGADO" in ya_pagado.get_json()["message"] and repo.pagos == {}


@pytest.mark.parametrize("cuerpo", [
    None, {}, {"metodo": "EFECTIVO"}, {"pedido_id": "7", "metodo": "EFECTIVO"}, {"pedido_id": 0, "metodo": "EFECTIVO"},
    {"pedido_id": 7}, {"pedido_id": 7, "metodo": "BITCOIN"},
    {"pedido_id": 7, "metodo": "TARJETA_SIMULADA"},                                     # sin tarjeta
    {"pedido_id": 7, "metodo": "TARJETA_SIMULADA", "tarjeta": "4111111111111111"},      # sin cvv
    {"pedido_id": 7, "metodo": "TARJETA_SIMULADA", "tarjeta": "1234", "cvv": "123"},
    {"pedido_id": 7, "metodo": "TARJETA_SIMULADA", "tarjeta": "4111-1111-1111-111X", "cvv": "123"},
    {"pedido_id": 7, "metodo": "TARJETA_SIMULADA", "tarjeta": 4111111111111111, "cvv": "123"},
    {"pedido_id": 7, "metodo": "TARJETA_SIMULADA", "tarjeta": "4111111111111111", "cvv": "12"},
    {"pedido_id": 7, "metodo": "TARJETA_SIMULADA", "tarjeta": "4111111111111111", "cvv": 123},
])
def test_datos_invalidos_400_sin_tocar_nada(client, repo, pedidos, ana, cuerpo):
    resp = client.post("/pagos", json=cuerpo, headers={**ana, "Idempotency-Key": nueva_llave()})
    assert resp.status_code == 400 and _error(resp) == "VALIDACION"
    assert repo.pagos == {} and pedidos.llamadas == []
    assert "4111" not in resp.get_data(as_text=True)            # el error no repite el numero recibido


# ------------------------------------------------------------------ lock concurrente
def test_lock_tomado_por_otro_proceso_409(client, repo, pedidos, fake_redis, ana, pagar):
    fake_redis.set(redis_keys.pago_lock(PEDIDO_ANA), "otro-proceso", ex=30)
    resp = pagar(ana, PEDIDO_ANA)
    assert resp.status_code == 409 and _error(resp) == "PAGO_EN_PROCESO"
    assert repo.pagos == {} and pedidos.llamadas == []
    assert fake_redis.get(redis_keys.pago_lock(PEDIDO_ANA)) == "otro-proceso"       # no se libera un lock ajeno

    fake_redis.delete(redis_keys.pago_lock(PEDIDO_ANA))
    assert pagar(ana, PEDIDO_ANA).status_code == 201


def test_el_lock_dura_todo_el_proceso_y_se_toma_con_set_nx_ex_30(client, pedidos, fake_redis, ana, pagar):
    visto = {}

    def mirar_el_lock():
        clave = redis_keys.pago_lock(PEDIDO_ANA)
        visto["tomado"], visto["ttl"] = fake_redis.exists(clave), fake_redis.ttl(clave)

    pedidos.al_obtener = mirar_el_lock                          # se ejecuta a mitad del pago
    assert pagar(ana, PEDIDO_ANA).status_code == 201
    assert visto["tomado"] == 1 and 0 < visto["ttl"] <= 30
    assert not fake_redis.exists(redis_keys.pago_lock(PEDIDO_ANA))


def test_el_lock_se_libera_aunque_el_pago_falle(client, pedidos, fake_redis, ana, pagar):
    assert pagar(ana, PEDIDO_LUIS).status_code == 403
    pedidos.caido = True
    assert pagar(ana, PEDIDO_ANA).status_code == 503
    assert list(fake_redis.scan_iter("pago:lock:*")) == []


def test_dos_pagos_simultaneos_del_mismo_pedido_cobran_una_sola_vez(client, repo, pedidos, ana):
    """8 peticiones a la vez, cada una con SU llave, por el mismo pedido: solo una lo paga."""
    resultados, arranque = [], threading.Barrier(8)

    def intentar():
        cliente = client.application.test_client()
        arranque.wait()
        resp = cliente.post("/pagos", headers={**token(ANA_ID), "Idempotency-Key": nueva_llave()},
                            json={"pedido_id": PEDIDO_ANA, "metodo": "EFECTIVO"})
        resultados.append(resp.status_code)

    hilos = [threading.Thread(target=intentar) for _ in range(8)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert resultados.count(201) == 1 and set(resultados) <= {201, 409}, resultados
    aprobados = [p for p in repo.pagos.values() if p["estado"] == "APROBADO"]
    assert len(aprobados) == 1 and pedidos.cambios() == [("cambiar_estado", PEDIDO_ANA, "PAGADO")]


def test_doble_clic_simultaneo_con_la_misma_llave_es_un_solo_pago(client, repo, pedidos, ana):
    llave, resultados, arranque = nueva_llave(), [], threading.Barrier(6)

    def intentar():
        cliente = client.application.test_client()
        arranque.wait()
        resp = cliente.post("/pagos", headers={**token(ANA_ID), "Idempotency-Key": llave},
                            json={"pedido_id": PEDIDO_ANA, "metodo": "EFECTIVO"})
        resultados.append((resp.status_code, resp.get_json().get("id")))

    hilos = [threading.Thread(target=intentar) for _ in range(6)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert len(repo.pagos) == 1 and pedidos.cambios() == [("cambiar_estado", PEDIDO_ANA, "PAGADO")]
    assert [codigo for codigo, _ in resultados].count(201) == 1
    assert {codigo for codigo, _ in resultados} <= {201, 200, 409}          # el mismo pago, o "en proceso"
    assert {pago_id for codigo, pago_id in resultados if codigo in (200, 201)} == {1}


# ------------------------------------------------------------------ Redis caido
def test_redis_caido_503_y_no_se_cobra(client, repo, pedidos, fake_redis, ana, pagar):
    redis_client.set_client(RedisQueFallaAlPagar(fake_redis))   # el JWT pasa; falla al revisar la llave
    resp = pagar(ana, PEDIDO_ANA)
    assert resp.status_code == 503 and _error(resp) == "REDIS_NO_DISPONIBLE"
    assert repo.pagos == {} and pedidos.llamadas == []


def test_redis_totalmente_caido_503(client, repo, pedidos, ana, pagar):
    redis_client.set_client(RedisCaido())
    assert pagar(ana, PEDIDO_ANA).status_code == 503
    assert client.get("/pagos", headers=ana).status_code == 503
    assert repo.pagos == {} and pedidos.llamadas == []


# ------------------------------------------------------------------ pedidos caido y sincronizacion
def test_pedidos_caido_antes_de_cobrar_503_sin_registrar_pago(client, repo, pedidos, fake_redis, ana, pagar):
    pedidos.caido = True
    llave = nueva_llave()
    resp = pagar(ana, PEDIDO_ANA, llave=llave)
    assert resp.status_code == 503 and _error(resp) == "PEDIDOS_NO_DISPONIBLE"
    assert repo.pagos == {} and not fake_redis.exists(redis_keys.pago_idem(llave))
    pedidos.caido = False                                       # con la misma llave se puede reintentar
    assert pagar(ana, PEDIDO_ANA, llave=llave).status_code == 201


def test_pedidos_se_cae_tras_aprobar_el_pago_queda_sin_sincronizar_y_la_tarea_lo_reintenta(
        client, repo, pedidos, fake_redis, ana, pagar):
    pedidos.caido_al_cambiar = True                             # responde el GET pero no el PATCH a PAGADO
    llave = nueva_llave()
    resp = pagar(ana, PEDIDO_ANA, llave=llave)
    assert resp.status_code == 201
    pago = resp.get_json()
    assert pago["estado"] == "APROBADO" and pago["sincronizado"] is False
    assert pedidos.estado(PEDIDO_ANA) == "PENDIENTE_PAGO"

    # mientras tanto: el reenvio devuelve el mismo pago y una llave nueva no cobra otra vez
    assert pagar(ana, PEDIDO_ANA, llave=llave).get_json()["id"] == pago["id"]
    otra = pagar(ana, PEDIDO_ANA)
    assert otra.status_code == 409 and _error(otra) == "PEDIDO_YA_PAGADO" and len(repo.pagos) == 1

    assert sincronizacion.ejecutar_una_vez() == []              # pedidos sigue caido: nada resuelto
    assert repo.pagos[pago["id"]]["sincronizado"] is False
    assert 0 < fake_redis.ttl(redis_keys.LOCK_SYNC_PAGOS) <= 30 # lock:pagos:sync con SET NX EX 30
    assert sincronizacion.ejecutar_una_vez() is None            # el lock sigue tomado: esta vuelta no hace nada

    pedidos.caido_al_cambiar = False                            # pedidos vuelve
    fake_redis.delete(redis_keys.LOCK_SYNC_PAGOS)
    assert sincronizacion.ejecutar_una_vez() == [pago["id"]]
    assert pedidos.estado(PEDIDO_ANA) == "PAGADO"
    assert client.get(f"/pagos/{pago['id']}", headers=ana).get_json()["sincronizado"] is True
    assert list(fake_redis.scan_iter("pago:lock:*")) == []

    fake_redis.delete(redis_keys.LOCK_SYNC_PAGOS)
    assert sincronizacion.ejecutar_una_vez() == []              # ya no queda nada pendiente


def test_la_sincronizacion_reconoce_un_aviso_que_si_habia_llegado(client, repo, pedidos, fake_redis, ana, pagar):
    pedidos.caido_al_cambiar = True
    pago = pagar(ana, PEDIDO_ANA).get_json()
    pedidos.caido_al_cambiar = False
    pedidos.pedidos[PEDIDO_ANA]["estado"] = "PAGADO"            # el PATCH llego pero se perdio su respuesta
    assert sincronizacion.ejecutar_una_vez() == [pago["id"]]
    assert repo.pagos[pago["id"]]["estado"] == "APROBADO" and repo.pagos[pago["id"]]["sincronizado"] is True


def test_si_el_pedido_expiro_antes_de_sincronizar_el_pago_se_reembolsa_solo(client, repo, pedidos, fake_redis, ana, pagar):
    pedidos.caido_al_cambiar = True
    pago = pagar(ana, PEDIDO_ANA).get_json()
    pedidos.caido_al_cambiar = False
    pedidos.pedidos[PEDIDO_ANA]["estado"] = "EXPIRADO"          # la reserva vencio mientras pedidos estaba caido
    assert sincronizacion.ejecutar_una_vez() == [pago["id"]]
    fila = repo.pagos[pago["id"]]
    assert fila["estado"] == "REEMBOLSADO" and fila["sincronizado"] is True and "EXPIRADO" in fila["notas"]


def test_la_sincronizacion_respeta_el_lock_del_pedido_y_se_salta_con_redis_caido(client, repo, pedidos, fake_redis, ana, pagar):
    pedidos.caido_al_cambiar = True
    pago = pagar(ana, PEDIDO_ANA).get_json()
    pedidos.caido_al_cambiar = False

    fake_redis.set(redis_keys.pago_lock(PEDIDO_ANA), "reembolso-en-curso", ex=30)
    assert sincronizacion.ejecutar_una_vez() == [] and repo.pagos[pago["id"]]["sincronizado"] is False

    redis_client.set_client(RedisCaido())
    assert sincronizacion.ejecutar_una_vez() is None            # sin Redis no hay lock: no hace nada
    assert repo.pagos[pago["id"]]["sincronizado"] is False


# ------------------------------------------------------------------ consultas
def test_cliente_solo_ve_sus_pagos_y_admin_todos_con_filtros(client, repo, ana, luis, admin, pagar):
    de_ana = pagar(ana, PEDIDO_ANA, tarjeta=TARJETA_RECHAZADA).get_json()["id"]
    de_luis = pagar(luis, PEDIDO_LUIS, metodo="EFECTIVO").get_json()["id"]

    lista = client.get("/pagos", headers=ana).get_json()
    assert [p["id"] for p in lista["items"]] == [de_ana] and lista["total"] == 1
    assert set(lista["items"][0]) == CAMPOS_DE_UN_PAGO
    assert [p["id"] for p in client.get(f"/pagos?user_id={LUIS_ID}", headers=ana).get_json()["items"]] == [de_ana]

    ids = lambda q: [p["id"] for p in client.get(f"/pagos?{q}", headers=admin).get_json()["items"]]   # noqa: E731
    assert ids("") == [de_luis, de_ana]
    assert ids("estado=RECHAZADO") == [de_ana] and ids("estado=aprobado") == [de_luis]
    assert ids("metodo=EFECTIVO") == [de_luis] and ids(f"user_id={ANA_ID}") == [de_ana]
    assert ids("estado=APROBADO&metodo=TARJETA_SIMULADA") == []
    assert client.get("/pagos?per_page=1", headers=admin).get_json()["pages"] == 2
    for malo in ("estado=OTRO", "metodo=BITCOIN", "user_id=x", "page=0"):
        assert client.get(f"/pagos?{malo}", headers=admin).status_code == 400

    assert client.get(f"/pagos/{de_luis}", headers=ana).status_code == 403
    assert client.get(f"/pagos/{de_luis}", headers=luis).status_code == 200
    assert client.get(f"/pagos/{de_luis}", headers=admin).status_code == 200
    assert client.get("/pagos/999", headers=admin).status_code == 404

    assert client.get(f"/pagos/pedido/{PEDIDO_LUIS}", headers=ana).status_code == 403
    assert [p["id"] for p in client.get(f"/pagos/pedido/{PEDIDO_LUIS}", headers=luis).get_json()["items"]] == [de_luis]
    assert client.get(f"/pagos/pedido/{PEDIDO_LUIS}", headers=admin).get_json()["pedido_id"] == PEDIDO_LUIS
    assert client.get(f"/pagos/pedido/{PEDIDO_INEXISTENTE}", headers=ana).get_json()["items"] == []


# ------------------------------------------------------------------ permisos 401 y 403
@pytest.mark.parametrize("metodo, ruta", [
    ("post", "/pagos"), ("get", "/pagos"), ("get", "/pagos/1"), ("get", f"/pagos/pedido/{PEDIDO_ANA}"),
    ("patch", "/pagos/1"), ("post", "/pagos/1/reembolso"), ("delete", "/pagos/1"),
])
def test_sin_token_401(client, repo, metodo, ruta):
    resp = getattr(client, metodo)(ruta, json={}, headers={"Idempotency-Key": nueva_llave()})
    assert resp.status_code == 401 and _error(resp) == "TOKEN_AUSENTE" and repo.pagos == {}


def test_acciones_de_admin_403_para_el_cliente(client, repo, pedidos, ana, pagar):
    pago = pagar(ana, PEDIDO_ANA).get_json()["id"]
    antes = dict(repo.pagos[pago])
    for metodo, ruta, cuerpo in (("patch", f"/pagos/{pago}", {"referencia": "X", "notas": "y"}),
                                 ("post", f"/pagos/{pago}/reembolso", {}),
                                 ("delete", f"/pagos/{pago}", None)):
        resp = getattr(client, metodo)(ruta, json=cuerpo, headers=ana)
        assert resp.status_code == 403 and _error(resp) == "ROL_INSUFICIENTE"
    assert repo.pagos[pago] == antes and pedidos.estado(PEDIDO_ANA) == "PAGADO"


# ------------------------------------------------------------------ admin: corregir y eliminar
def test_admin_corrige_solo_referencia_y_notas_nunca_el_monto(client, repo, ana, admin, pagar):
    pago = pagar(ana, PEDIDO_ANA).get_json()
    resp = client.patch(f"/pagos/{pago['id']}", headers=admin, json={"referencia": " REF-MANUAL-1 ", "notas": "Conciliado"})
    assert resp.status_code == 200
    assert resp.get_json()["referencia"] == "REF-MANUAL-1" and resp.get_json()["notas"] == "Conciliado"
    assert resp.get_json()["monto"] == 850.5 and resp.get_json()["estado"] == "APROBADO"

    for cuerpo in ({"monto": 1}, {"referencia": "R", "monto": 1}, {"estado": "REEMBOLSADO"}, {"user_id": 5},
                   {"sincronizado": False}, {"referencia": ""}, {"referencia": "x" * 41}, {"notas": "x" * 501},
                   {"referencia": 5}, {}, None):
        assert client.patch(f"/pagos/{pago['id']}", headers=admin, json=cuerpo).status_code == 400
    assert float(repo.pagos[pago["id"]]["monto"]) == 850.5 and repo.pagos[pago["id"]]["referencia"] == "REF-MANUAL-1"

    assert client.patch(f"/pagos/{pago['id']}", headers=admin, json={"notas": ""}).get_json()["notas"] is None
    assert client.patch("/pagos/999", headers=admin, json={"notas": "x"}).status_code == 404


def test_delete_solo_rechazados_y_es_borrado_logico(client, repo, ana, admin, pagar):
    rechazado = pagar(ana, PEDIDO_ANA, tarjeta=TARJETA_RECHAZADA).get_json()["id"]
    aprobado = pagar(ana, PEDIDO_ANA).get_json()["id"]

    resp = client.delete(f"/pagos/{aprobado}", headers=admin)
    assert resp.status_code == 409 and _error(resp) == "PAGO_NO_ELIMINABLE" and repo.pagos[aprobado]["activo"] is True

    assert client.delete(f"/pagos/{rechazado}", headers=admin).status_code == 200
    assert rechazado in repo.pagos and repo.pagos[rechazado]["activo"] is False     # la fila sigue en la tabla
    assert client.get(f"/pagos/{rechazado}", headers=admin).status_code == 404
    assert [p["id"] for p in client.get("/pagos", headers=admin).get_json()["items"]] == [aprobado]
    assert client.delete(f"/pagos/{rechazado}", headers=admin).status_code == 404


# ------------------------------------------------------------------ reembolso
def test_reembolso_deja_el_pago_reembolsado_y_el_pedido_cancelado(client, repo, pedidos, fake_redis, ana, admin, pagar):
    pago = pagar(ana, PEDIDO_ANA).get_json()
    resp = client.post(f"/pagos/{pago['id']}/reembolso", headers=admin, json={"notas": "Devolución solicitada"})
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "REEMBOLSADO" and resp.get_json()["notas"] == "Devolución solicitada"
    assert resp.get_json()["monto"] == 850.5 and resp.get_json()["sincronizado"] is True
    # pedidos recibe CANCELADO por su endpoint interno: ahi es donde se libera el stock
    assert pedidos.estado(PEDIDO_ANA) == "CANCELADO"
    assert pedidos.cambios() == [("cambiar_estado", PEDIDO_ANA, "PAGADO"), ("cambiar_estado", PEDIDO_ANA, "CANCELADO")]
    assert list(fake_redis.scan_iter("pago:lock:*")) == []

    otra = client.post(f"/pagos/{pago['id']}/reembolso", headers=admin)             # no se reembolsa dos veces
    assert otra.status_code == 409 and _error(otra) == "PAGO_NO_REEMBOLSABLE"
    assert len(pedidos.cambios()) == 2


def test_reembolso_sin_cuerpo_y_de_un_pago_rechazado(client, repo, pedidos, ana, admin, pagar):
    rechazado = pagar(ana, PEDIDO_ANA, tarjeta=TARJETA_RECHAZADA).get_json()["id"]
    resp = client.post(f"/pagos/{rechazado}/reembolso", headers=admin)
    assert resp.status_code == 409 and _error(resp) == "PAGO_NO_REEMBOLSABLE"
    aprobado = pagar(ana, PEDIDO_ANA).get_json()["id"]
    assert client.post(f"/pagos/{aprobado}/reembolso", headers=admin).get_json()["estado"] == "REEMBOLSADO"
    assert client.post("/pagos/999/reembolso", headers=admin).status_code == 404


def test_reembolso_con_pedidos_caido_503_y_no_cambia_nada(client, repo, pedidos, fake_redis, ana, admin, pagar):
    pago = pagar(ana, PEDIDO_ANA).get_json()["id"]
    pedidos.caido = True
    resp = client.post(f"/pagos/{pago}/reembolso", headers=admin)
    assert resp.status_code == 503 and _error(resp) == "PEDIDOS_NO_DISPONIBLE"
    assert repo.pagos[pago]["estado"] == "APROBADO" and pedidos.estado(PEDIDO_ANA) == "PAGADO"
    assert list(fake_redis.scan_iter("pago:lock:*")) == []
    pedidos.caido = False                                       # el admin reintenta
    assert client.post(f"/pagos/{pago}/reembolso", headers=admin).status_code == 200


def test_no_se_reembolsa_un_pedido_ya_enviado(client, repo, pedidos, ana, admin, pagar):
    pago = pagar(ana, PEDIDO_ANA).get_json()["id"]
    pedidos.pedidos[PEDIDO_ANA]["estado"] = "ENVIADO"           # pedidos ya no permite cancelarlo
    resp = client.post(f"/pagos/{pago}/reembolso", headers=admin)
    assert resp.status_code == 409 and _error(resp) == "PEDIDO_NO_CANCELABLE" and "ENVIADO" in resp.get_json()["message"]
    assert repo.pagos[pago]["estado"] == "APROBADO"


def test_reembolso_de_un_pedido_que_ya_estaba_cancelado(client, repo, pedidos, ana, admin, pagar):
    pago = pagar(ana, PEDIDO_ANA).get_json()["id"]
    pedidos.pedidos[PEDIDO_ANA]["estado"] = "CANCELADO"         # un admin lo cancelo desde Pedidos
    resp = client.post(f"/pagos/{pago}/reembolso", headers=admin)
    assert resp.status_code == 200 and resp.get_json()["estado"] == "REEMBOLSADO"


def test_reembolso_con_lock_tomado_o_redis_caido(client, repo, pedidos, fake_redis, ana, admin, pagar):
    pago = pagar(ana, PEDIDO_ANA).get_json()["id"]
    fake_redis.set(redis_keys.pago_lock(PEDIDO_ANA), "otro-proceso", ex=30)
    resp = client.post(f"/pagos/{pago}/reembolso", headers=admin)
    assert resp.status_code == 409 and _error(resp) == "PAGO_EN_PROCESO"
    fake_redis.delete(redis_keys.pago_lock(PEDIDO_ANA))

    redis_client.set_client(RedisQueFallaAlPagar(fake_redis))
    resp = client.post(f"/pagos/{pago}/reembolso", headers=admin)
    assert resp.status_code == 503 and _error(resp) == "REDIS_NO_DISPONIBLE"
    assert repo.pagos[pago]["estado"] == "APROBADO" and pedidos.estado(PEDIDO_ANA) == "PAGADO"


# ------------------------------------------------------------------ datos de tarjeta
def test_ningun_log_respuesta_ni_almacen_contiene_el_numero_de_tarjeta_ni_el_cvv(
        client, repo, pedidos, fake_redis, ana, admin, caplog, monkeypatch):
    # Referencia y llaves fijas: asi ningun valor aleatorio puede contener por casualidad los digitos del CVV.
    monkeypatch.setattr(pagos_service, "_referencia", lambda: "PAG-PRUEBA-REF")
    cvv_distintivo = "7391"
    secretos = (NUMERO_BUENO, TARJETA_BUENA, NUMERO_RECHAZADO, TARJETA_RECHAZADA, "4111111111111", cvv_distintivo)
    respuestas = []

    def enviar(llave, pedido_id, tarjeta):
        respuestas.append(client.post(
            "/pagos", headers={**ana, "Idempotency-Key": llave},
            json={"pedido_id": pedido_id, "metodo": "TARJETA_SIMULADA", "tarjeta": tarjeta, "cvv": cvv_distintivo}))

    with caplog.at_level(logging.DEBUG):                        # todos los loggers, incluso en DEBUG
        enviar("llave-prueba-a", PEDIDO_ANA, TARJETA_BUENA)             # 201 aprobado
        enviar("llave-prueba-a", PEDIDO_ANA, TARJETA_BUENA)             # 200 reenvio
        enviar("llave-prueba-b", PEDIDO_ANA, TARJETA_RECHAZADA)         # 409 el pedido ya esta pagado
        enviar("llave-prueba-c", PEDIDO_ANA, NUMERO_BUENO + "X")        # 400 tarjeta mal escrita
        enviar("llave-prueba-d", PEDIDO_LUIS, NUMERO_BUENO)             # 403 pedido ajeno
        pedidos.caido = True
        enviar("llave-prueba-e", PEDIDO_LUIS, NUMERO_BUENO)             # 503 pedidos caido
        pedidos.caido = False
        respuestas.append(client.get("/pagos", headers=admin))
        respuestas.append(client.post("/pagos/1/reembolso", headers=admin))
        sincronizacion.ejecutar_una_vez()

    assert [r.status_code for r in respuestas] == [201, 200, 409, 400, 403, 503, 200, 200]
    assert len(caplog.records) > 0                              # si hubo logs que revisar

    lugares = {
        "logs": caplog.text + " ".join(str(r.args) for r in caplog.records),
        "respuestas": " ".join(r.get_data(as_text=True) for r in respuestas),
        # sin las fechas: sus microsegundos son digitos al azar
        "base de datos": " ".join(f"{columna}={valor}" for pago in repo.pagos.values()
                                  for columna, valor in pago.items() if columna not in ("created_at", "updated_at")),
        # sin los locks: su valor es un token aleatorio
        "redis": " ".join(f"{clave}={fake_redis.get(clave)}" for clave in fake_redis.scan_iter("pago:*")),
        "llamadas a pedidos": repr(pedidos.llamadas),
    }
    for lugar, contenido in lugares.items():
        for secreto in secretos:
            assert secreto not in contenido, f"un dato de tarjeta aparece en: {lugar}"
    # lo unico que se conserva de la tarjeta son los ultimos 4 digitos
    assert {p["ultimos4"] for p in repo.pagos.values()} == {"1111"}
    assert all("cvv" not in pago and "tarjeta" not in pago for pago in repo.pagos.values())


def test_la_tabla_no_tiene_columnas_para_el_numero_ni_el_cvv():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "sql" / "001_pagos.sql").read_text(encoding="utf-8").lower()
    tabla = sql[sql.index("create table if not exists pagos"):sql.index("create index")]
    assert "ultimos4" in tabla and "idempotency_key" in tabla and "unique" in tabla
    for prohibida in ("cvv", "numero_tarjeta", "tarjeta "):
        assert prohibida not in tabla


def test_health_y_metrics(client):
    assert client.get("/health").get_json() == {"service": "pagos", "status": "ok", "db": "ok", "redis": "ok",
                                                "version": "1.0.0"}
    assert client.get("/metrics").get_json()["service"] == "pagos"
