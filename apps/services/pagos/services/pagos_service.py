"""
services/pagos_service.py
Reglas de negocio de los pagos (sin Flask). El pago es SIMULADO: no hay
pasarela real; una tarjeta terminada en 0000 se rechaza y todo lo demas
se aprueba.

Barreras contra el doble cobro, de afuera hacia adentro:
  1. Idempotency-Key: pago:idem:<key> en Redis (24 h) y, como respaldo,
     la columna UNIQUE idempotency_key. Reenviar la misma llave devuelve
     el mismo pago sin cobrar otra vez.
  2. Lock pago:lock:<pedido_id> (SET NX EX 30) durante todo el proceso:
     dos pagos del mismo pedido no avanzan a la vez.
  3. Indice unico en la base: un pedido no puede tener dos pagos APROBADO.

Redis es obligatorio para pagar y reembolsar: cualquier redis.RedisError
se propaga y la respuesta es 503 (common/errors.py).

El monto sale SIEMPRE del pedido (GET /pedidos/internal/{id}); lo que
mande el cliente se ignora. Del numero de tarjeta solo se conservan los
ultimos 4 digitos; el CVV no se conserva.
"""
import logging
import secrets
import uuid
from datetime import datetime
from decimal import Decimal
from math import ceil

from common import redis_keys
from common.auth import ADMIN_ROLE_ID
from common.errors import ApiError
from common.redis_client import get_client
from db import repository
from services import pedidos_client, validators

log = logging.getLogger(__name__)

APROBADO, RECHAZADO, REEMBOLSADO = validators.ESTADOS

# Estados del pedido tal como los define el microservicio pedidos.
PEDIDO_PENDIENTE, PEDIDO_PAGADO, PEDIDO_CANCELADO = "PENDIENTE_PAGO", "PAGADO", "CANCELADO"
PEDIDO_YA_COBRADO = ("PAGADO", "ENVIADO", "ENTREGADO")          # pedidos ya tomo nota del pago
PEDIDO_SIN_ENTREGA = ("CANCELADO", "EXPIRADO")                  # ya no hay nada que cancelar

TERMINACION_RECHAZADA = "0000"


class Actor:
    """Quien hace la peticion, segun su JWT."""

    def __init__(self, payload):
        self.user_id = payload["user_id"]
        self.es_admin = payload["role_id"] == ADMIN_ROLE_ID


# ------------------------------------------------------------------ salida
def _fecha(valor):
    return valor.isoformat(timespec="seconds") if valor is not None else None


def publico(pago):
    """Representacion de un pago en la API (sin la llave de idempotencia)."""
    return {
        "id": pago["id"],
        "pedido_id": pago["pedido_id"],
        "user_id": pago["user_id"],
        "monto": float(pago["monto"]),
        "metodo": pago["metodo"],
        "estado": pago["estado"],
        "referencia": pago["referencia"],
        "ultimos4": pago["ultimos4"],
        "sincronizado": pago["sincronizado"],
        "notas": pago["notas"],
        "created_at": _fecha(pago["created_at"]),
        "updated_at": _fecha(pago["updated_at"]),
    }


# ------------------------------------------------------------------ errores
def _no_encontrado():
    return ApiError(404, "PAGO_NO_ENCONTRADO", "No existe el pago indicado.")


def _prohibido(mensaje):
    return ApiError(403, "ROL_INSUFICIENTE", mensaje)


def _pedidos_no_disponible():
    return ApiError(503, "PEDIDOS_NO_DISPONIBLE",
                    "El servicio de pedidos no responde: no se pudo completar la operacion. Intenta mas tarde.")


def _en_proceso():
    return ApiError(409, "PAGO_EN_PROCESO",
                    "Ya hay una operacion de pago en curso para ese pedido. Espera unos segundos y reintenta "
                    "con la misma Idempotency-Key.")


# ------------------------------------------------------------------ apoyo
def _actualizar(pago_id, **campos):
    with repository.unit_of_work() as repo:
        return repo.update(pago_id, **campos)


def _tomar_lock(cliente, pedido_id):
    """Token del lock pago:lock:<pedido_id> (SET NX EX 30), o None si otro proceso lo tiene."""
    token = uuid.uuid4().hex
    tomado = cliente.set(redis_keys.pago_lock(pedido_id), token, nx=True, ex=redis_keys.LOCK_TTL)
    return token if tomado else None


def _soltar_lock(cliente, pedido_id, token):
    """Libera el lock solo si sigue siendo nuestro. Nunca lanza: si Redis falla aqui, el lock
    caduca solo a los 30 segundos."""
    try:
        clave = redis_keys.pago_lock(pedido_id)
        if cliente.get(clave) == token:
            cliente.delete(clave)
    except Exception:
        log.warning("No se pudo liberar el lock de pago del pedido %s; caducara solo", pedido_id)


def _pago_de_la_llave(cliente, llave):
    """Pago ya registrado con esa Idempotency-Key: primero Redis, y la base como respaldo."""
    pago_id = cliente.get(redis_keys.pago_idem(llave))
    with repository.unit_of_work() as repo:
        pago = repo.get(int(pago_id)) if pago_id else None
        if pago is None or pago["idempotency_key"] != llave:
            pago = repo.get_by_key(llave)
    return pago


def _repetido(actor, pago, pedido_id):
    """Respuesta de un reenvio: el MISMO pago, siempre que la llave sea de este usuario y pedido."""
    if pago["user_id"] != actor.user_id or pago["pedido_id"] != pedido_id:
        raise ApiError(409, "LLAVE_YA_USADA",
                       "Esa Idempotency-Key ya se uso para otro pago. Genera una llave nueva para este intento.")
    return publico(pago)


def _referencia():
    return f"PAG-{datetime.now():%Y%m%d}-{secrets.token_hex(4).upper()}"


# ------------------------------------------------------------------ aviso a pedidos
def _resolver_conflicto(pago):
    """pedidos respondio 409 al marcar PAGADO: se consulta en que quedo el pedido."""
    try:
        pedido = pedidos_client.obtener(pago["pedido_id"])
    except pedidos_client.PedidosNoDisponible:
        return pago                                      # se reintenta en la siguiente vuelta
    estado = (pedido or {}).get("estado")
    if estado in PEDIDO_YA_COBRADO:
        return _actualizar(pago["id"], sincronizado=True)    # el aviso anterior si llego
    # El pedido se cancelo o expiro antes de poder confirmarle el pago: no se va a entregar,
    # asi que el pago (simulado) se reembolsa solo.
    log.warning("Pago %s reembolsado automaticamente: el pedido %s quedo en %s",
                pago["id"], pago["pedido_id"], estado or "inexistente")
    return _actualizar(pago["id"], estado=REEMBOLSADO, sincronizado=True,
                       notas=f"Reembolso automatico: el pedido estaba {estado or 'eliminado'} al confirmar el pago.")


def _avisar_a_pedidos(pago):
    """Marca el pedido como PAGADO. Si pedidos no responde, el pago queda con sincronizado = false
    y lo reintenta la tarea en segundo plano. Devuelve el pago como quedo."""
    try:
        pedidos_client.cambiar_estado(pago["pedido_id"], PEDIDO_PAGADO)
    except pedidos_client.PedidosNoDisponible:
        return pago
    except pedidos_client.TransicionRechazada:
        return _resolver_conflicto(pago)
    return _actualizar(pago["id"], sincronizado=True)


# ------------------------------------------------------------------ pagar
def _cobrar(actor, llave, pedido_id, metodo, ultimos4):
    """Con el lock del pedido tomado: valida el pedido, decide y registra el pago."""
    try:
        pedido = pedidos_client.obtener(pedido_id)
    except pedidos_client.PedidosNoDisponible:
        raise _pedidos_no_disponible()                   # sin pedido no hay monto: no se registra nada
    if pedido is None:
        raise ApiError(404, "PEDIDO_NO_ENCONTRADO", "No existe el pedido indicado.")
    if pedido.get("user_id") != actor.user_id:
        raise _prohibido("Solo el dueño del pedido puede pagarlo.")
    if pedido.get("estado") != PEDIDO_PENDIENTE:
        raise ApiError(409, "PEDIDO_NO_PAGABLE",
                       f"Solo se paga un pedido en PENDIENTE_PAGO (esta en {pedido.get('estado')}).")
    try:
        monto = Decimal(str(pedido["total"])).quantize(Decimal("0.01"))      # el monto sale del pedido
    except (KeyError, TypeError, ArithmeticError):
        raise _pedidos_no_disponible()

    aprobado = not (metodo == validators.TARJETA and ultimos4 == TERMINACION_RECHAZADA)
    ya_pagado = ApiError(409, "PEDIDO_YA_PAGADO", "El pedido ya tiene un pago aprobado.")
    try:
        with repository.unit_of_work() as repo:
            if repo.aprobado_de_pedido(pedido_id) is not None:
                raise ya_pagado
            # Un pago rechazado no tiene nada que avisar a pedidos: nace sincronizado.
            pago = repo.insert(pedido_id=pedido_id, user_id=actor.user_id, monto=monto, metodo=metodo,
                               estado=APROBADO if aprobado else RECHAZADO, referencia=_referencia(),
                               ultimos4=ultimos4, idempotency_key=llave, sincronizado=not aprobado)
    except repository.PedidoYaPagado:
        raise ya_pagado
    except repository.LlaveDuplicada:
        with repository.unit_of_work() as repo:          # otra peticion con la misma llave gano la carrera
            return repo.get_by_key(llave), False

    if aprobado:
        pago = _avisar_a_pedidos(pago)
    return pago, True


def pagar(actor, llave, datos):
    """POST /pagos. Devuelve (pago, creado): creado = False cuando es el reenvio de una llave ya usada."""
    llave = validators.llave_de_idempotencia(llave)
    datos = validators.cuerpo(datos)
    pedido_id = validators.pedido_id(datos.get("pedido_id"))
    metodo = validators.metodo(datos.get("metodo"))
    # De aqui en adelante el numero de tarjeta y el CVV ya no existen: solo los ultimos 4 digitos.
    ultimos4 = validators.ultimos4_de_tarjeta(datos) if metodo == validators.TARJETA else None

    cliente = get_client()                               # Redis caido -> RedisError -> 503

    previo = _pago_de_la_llave(cliente, llave)           # 1. idempotencia
    if previo is not None:
        return _repetido(actor, previo, pedido_id), False

    token = _tomar_lock(cliente, pedido_id)              # 5. lock durante todo el proceso
    if token is None:
        raise _en_proceso()
    try:
        with repository.unit_of_work() as repo:          # pudo terminar otra peticion igual mientras tanto
            previo = repo.get_by_key(llave)
        if previo is not None:
            return _repetido(actor, previo, pedido_id), False

        pago, creado = _cobrar(actor, llave, pedido_id, metodo, ultimos4)       # 2, 3 y 4
        if not creado:
            return _repetido(actor, pago, pedido_id), False
        cliente.set(redis_keys.pago_idem(llave), pago["id"], ex=redis_keys.PAYMENT_IDEMPOTENCY_TTL)
        return publico(pago), True
    finally:
        _soltar_lock(cliente, pedido_id, token)


# ------------------------------------------------------------------ consultas
def listar(actor, args):
    filtros = validators.filtros_de_lista(args)
    page, per_page = filtros.pop("page"), filtros.pop("per_page")
    if not actor.es_admin:
        filtros["user_id"] = actor.user_id               # un cliente solo ve los suyos
    with repository.unit_of_work() as repo:
        filas, total = repo.list(limit=per_page, offset=(page - 1) * per_page, **filtros)
    return {"items": [publico(fila) for fila in filas], "page": page, "per_page": per_page, "total": total,
            "pages": ceil(total / per_page) if total else 0}


def obtener(actor, pago_id):
    with repository.unit_of_work() as repo:
        pago = repo.get(pago_id)
    if pago is None:
        raise _no_encontrado()
    if not actor.es_admin and pago["user_id"] != actor.user_id:
        raise _prohibido("Solo puedes consultar tus propios pagos.")
    return publico(pago)


def de_pedido(actor, pedido_id):
    """Pagos de un pedido (el mas reciente primero)."""
    with repository.unit_of_work() as repo:
        pagos = repo.de_pedido(pedido_id)
    if not actor.es_admin and any(pago["user_id"] != actor.user_id for pago in pagos):
        raise _prohibido("Solo puedes consultar los pagos de tus propios pedidos.")
    return {"pedido_id": pedido_id, "items": [publico(pago) for pago in pagos]}


# ------------------------------------------------------------------ administracion
def editar(pago_id, datos):
    """PATCH /pagos/{id}: solo `referencia` y `notas`. El monto y todo lo demas no se tocan."""
    datos = validators.cuerpo(datos)
    ajenos = sorted(set(datos) - {"referencia", "notas"})
    if ajenos:
        raise validators.invalido(f"Solo se pueden corregir 'referencia' y 'notas' (no: {', '.join(ajenos)}).")
    cambios = {}
    if "referencia" in datos:
        cambios["referencia"] = validators.texto("referencia", datos["referencia"], validators.REFERENCIA_MAXIMO,
                                                 obligatorio=True)
    if "notas" in datos:
        cambios["notas"] = validators.texto("notas", datos["notas"], validators.NOTAS_MAXIMO)
    if not cambios:
        raise validators.invalido("Envia 'referencia' y/o 'notas'.")
    with repository.unit_of_work() as repo:
        if repo.get(pago_id, bloquear=True) is None:
            raise _no_encontrado()
        return publico(repo.update(pago_id, **cambios))


def reembolsar(pago_id, datos):
    """POST /pagos/{id}/reembolso: el pedido pasa a CANCELADO (pedidos libera el stock) y el pago
    a REEMBOLSADO. Si pedidos no responde no se cambia nada (503): el admin reintenta."""
    notas = validators.texto("notas", datos.get("notas") if isinstance(datos, dict) else None,
                             validators.NOTAS_MAXIMO)
    with repository.unit_of_work() as repo:
        pago = repo.get(pago_id)
    if pago is None:
        raise _no_encontrado()
    no_reembolsable = ApiError(409, "PAGO_NO_REEMBOLSABLE", "Solo se reembolsa un pago APROBADO.")
    if pago["estado"] != APROBADO:
        raise no_reembolsable

    cliente = get_client()                               # Redis caido -> 503
    token = _tomar_lock(cliente, pago["pedido_id"])
    if token is None:
        raise _en_proceso()
    try:
        try:
            pedidos_client.cambiar_estado(pago["pedido_id"], PEDIDO_CANCELADO)
        except pedidos_client.PedidosNoDisponible:
            raise _pedidos_no_disponible()
        except pedidos_client.TransicionRechazada:
            try:
                pedido = pedidos_client.obtener(pago["pedido_id"])
            except pedidos_client.PedidosNoDisponible:
                raise _pedidos_no_disponible()
            estado = (pedido or {}).get("estado")
            if pedido is not None and estado not in PEDIDO_SIN_ENTREGA:
                raise ApiError(409, "PEDIDO_NO_CANCELABLE",
                               f"El pedido esta en {estado} y ya no se puede cancelar: no se reembolsa.")

        with repository.unit_of_work() as repo:
            actual = repo.get(pago_id, bloquear=True)
            if actual is None:
                raise _no_encontrado()
            if actual["estado"] != APROBADO:
                raise no_reembolsable
            return publico(repo.update(pago_id, estado=REEMBOLSADO, sincronizado=True,
                                       notas=notas if notas is not None else actual["notas"]))
    finally:
        _soltar_lock(cliente, pago["pedido_id"], token)


def eliminar(pago_id):
    """Borrado logico (activo = false); solo pagos RECHAZADO."""
    with repository.unit_of_work() as repo:
        pago = repo.get(pago_id, bloquear=True)
        if pago is None:
            raise _no_encontrado()
        if pago["estado"] != RECHAZADO:
            raise ApiError(409, "PAGO_NO_ELIMINABLE",
                           f"Solo se eliminan pagos RECHAZADO (este esta {pago['estado']}).")
        repo.update(pago_id, activo=False)
    return {"status": "ok", "id": pago_id, "message": "Pago eliminado."}


# ------------------------------------------------------------------ sincronizacion
def sincronizar_pendientes():
    """Reintenta avisar a pedidos de los pagos APROBADO que quedaron con sincronizado = false.
    Devuelve los ids que quedaron resueltos en esta vuelta."""
    with repository.unit_of_work() as repo:
        pendientes = repo.pendientes_de_sincronizar()
    resueltos = []
    cliente = get_client()
    for pendiente in pendientes:
        token = _tomar_lock(cliente, pendiente["pedido_id"])
        if token is None:
            continue                                     # hay un pago o reembolso en curso para ese pedido
        try:
            with repository.unit_of_work() as repo:
                pago = repo.get(pendiente["id"])         # releido con el lock tomado
            if pago is None or pago["sincronizado"] or pago["estado"] != APROBADO:
                continue
            if _avisar_a_pedidos(pago)["sincronizado"]:
                resueltos.append(pago["id"])
        finally:
            _soltar_lock(cliente, pendiente["pedido_id"], token)
    return resueltos
