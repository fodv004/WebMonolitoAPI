"""
services/pedidos_service.py
Reglas de negocio de los pedidos (sin Flask).

Estados (cualquier otra transicion -> 409 TRANSICION_INVALIDA):
    PENDIENTE_PAGO -> PAGADO | CANCELADO | EXPIRADO
    PAGADO         -> ENVIADO | CANCELADO
    ENVIADO        -> ENTREGADO

Stock (tabla inventario), siempre dentro de la transaccion y con las filas
bloqueadas (SELECT ... FOR UPDATE):
    crear / agregar unidades      disponible -= n, reservado += n   (409 si no alcanza)
    cancelar o expirar PENDIENTE  disponible += n, reservado -= n
    PENDIENTE_PAGO -> PAGADO      reservado  -= n                   (venta confirmada)
    PAGADO -> CANCELADO           disponible += n                   (las unidades regresan)

PostgreSQL es la fuente de verdad. La clave de Redis pedido:reserva:<id>
(TTL = minutos de reserva) es solo un espejo de la reserva: escribirla o
borrarla nunca hace fallar una operacion.
"""
from decimal import Decimal
from math import ceil

from common import redis_client, redis_keys
from common.auth import ADMIN_ROLE_ID
from common.errors import ApiError
from config import settings as cfg
from db import repository
from services import clientes_http, validators

PENDIENTE, PAGADO, ENVIADO, ENTREGADO, CANCELADO, EXPIRADO = validators.ESTADOS

TRANSICIONES = {
    PENDIENTE: {PAGADO, CANCELADO, EXPIRADO},
    PAGADO: {ENVIADO, CANCELADO},
    ENVIADO: {ENTREGADO},
}
ACTOR_EXPIRACION = "sistema:expiracion"
ACTOR_PAGOS = "servicio:pagos"


class Actor:
    """Quien hace la peticion, segun su JWT."""

    def __init__(self, payload):
        self.user_id = payload["user_id"]
        self.es_admin = payload["role_id"] == ADMIN_ROLE_ID

    @property
    def etiqueta(self):
        return f"{'admin' if self.es_admin else 'user'}:{self.user_id}"


# ------------------------------------------------------------------ salida
def _fecha(valor):
    return valor.isoformat(timespec="seconds") if valor is not None else None


def _resumen(pedido):
    datos = {
        "id": pedido["id"],
        "user_id": pedido["user_id"],
        "estado": pedido["estado"],
        "total": float(pedido["total"]),
        "created_at": _fecha(pedido["created_at"]),
        "updated_at": _fecha(pedido["updated_at"]),
        "expira_en": _fecha(pedido["expira_en"]),
    }
    if "articulos" in pedido:
        datos["articulos"] = int(pedido["articulos"])
    return datos


def _completo(repo, pedido_id):
    """Pedido con sus lineas y su historial, leido de nuevo tras cualquier cambio."""
    pedido = repo.pedido_get(pedido_id)
    datos = _resumen(pedido)
    datos["lineas"] = [{"isbn": l["isbn"], "titulo": l["titulo"], "cantidad": l["cantidad"],
                        "precio_unitario": float(l["precio_unitario"]), "subtotal": float(l["subtotal"])}
                       for l in repo.lineas_get(pedido_id)]
    datos["articulos"] = sum(l["cantidad"] for l in datos["lineas"])
    datos["historial"] = [{"estado_anterior": h["estado_anterior"], "estado_nuevo": h["estado_nuevo"],
                           "actor": h["actor"], "fecha": _fecha(h["fecha"])} for h in repo.historial_get(pedido_id)]
    return datos


# ------------------------------------------------------------------ errores
def _no_encontrado():
    return ApiError(404, "PEDIDO_NO_ENCONTRADO", "No existe el pedido indicado.")


def _prohibido(mensaje):
    return ApiError(403, "ROL_INSUFICIENTE", mensaje)


def _transicion_invalida(actual, nuevo):
    return ApiError(409, "TRANSICION_INVALIDA", f"Un pedido en estado {actual} no puede pasar a {nuevo}.")


def _no_disponible(servicio):
    codigo = {"books": "BOOKS_NO_DISPONIBLE", "users": "USERS_NO_DISPONIBLE"}[servicio]
    return ApiError(503, codigo, f"El servicio {servicio} no responde: no se puede validar el pedido. "
                                 "Intenta mas tarde.")


def _sin_stock(isbn, disponible, solicitado):
    return ApiError(409, "STOCK_INSUFICIENTE",
                    f"Stock insuficiente para el ISBN {isbn}: disponible {disponible}, solicitado {solicitado}.")


# ------------------------------------------------------------------ apoyo
def _pedido_bloqueado(repo, pedido_id):
    pedido = repo.pedido_get(pedido_id, bloquear=True)
    if pedido is None:
        raise _no_encontrado()
    return pedido


def _libros_de_books(isbns):
    """{isbn: (titulo, precio)} consultando books. 404 si alguno no existe; 503 si books no responde."""
    libros = {}
    for isbn in isbns:
        try:
            libro = clientes_http.libro(isbn)
        except clientes_http.ServicioNoDisponible as e:
            raise _no_disponible(e.servicio)
        if libro is None:
            raise ApiError(404, "LIBRO_NO_ENCONTRADO", f"No existe un libro con ISBN {isbn} en el catalogo.")
        try:
            precio = Decimal(str(libro["precio"])).quantize(Decimal("0.01"))
            titulo = str(libro["titulo"])[:255]
        except (KeyError, TypeError, ArithmeticError):
            raise _no_disponible("books")       # respuesta sin titulo o sin precio: no se puede cobrar
        libros[isbn] = (titulo, precio)
    return libros


def _reservar(repo, deltas):
    """Aplica al inventario el cambio de unidades reservadas por ISBN (positivo = reservar mas,
    negativo = devolver). Bloquea las filas en orden de isbn y falla con 409 si alguna no alcanza."""
    deltas = {isbn: d for isbn, d in deltas.items() if d}
    if not deltas:
        return
    inventario = repo.inventario_bloquear(deltas)
    for isbn in sorted(deltas):
        delta = deltas[isbn]
        disponible = inventario[isbn]["stock_disponible"] if isbn in inventario else 0
        if delta > 0 and disponible < delta:
            raise _sin_stock(isbn, disponible, delta)
        if isbn in inventario:
            repo.inventario_ajustar(isbn, disponible=-delta, reservado=delta)


def _cambiar_estado(repo, pedido, nuevo, actor):
    """Unico lugar donde un pedido cambia de estado: valida la transicion, mueve el stock y
    deja el rastro en el historial. `pedido` debe venir bloqueado."""
    actual = pedido["estado"]
    if nuevo not in TRANSICIONES.get(actual, ()):
        raise _transicion_invalida(actual, nuevo)

    cantidades = {l["isbn"]: l["cantidad"] for l in repo.lineas_get(pedido["id"])}
    inventario = repo.inventario_bloquear(cantidades)
    for isbn in sorted(cantidades):
        if isbn not in inventario:
            continue                    # el admin quito ese ISBN del inventario: no hay nada que mover
        n = cantidades[isbn]
        # min(): nunca se devuelve mas de lo que la fila dice tener reservado.
        reservado = min(n, inventario[isbn]["stock_reservado"])
        if actual == PENDIENTE and nuevo in (CANCELADO, EXPIRADO):
            repo.inventario_ajustar(isbn, disponible=n, reservado=-reservado)
        elif actual == PENDIENTE and nuevo == PAGADO:
            repo.inventario_ajustar(isbn, reservado=-reservado)
        elif actual == PAGADO and nuevo == CANCELADO:
            repo.inventario_ajustar(isbn, disponible=n)

    repo.pedido_cambiar_estado(pedido["id"], nuevo)
    repo.historial_insert(pedido["id"], actual, nuevo, actor)


def _olvidar_reserva(pedido_id):
    redis_client.cache_delete(redis_keys.pedido_reserva(pedido_id))


# ------------------------------------------------------------------ crear
def crear(actor, datos):
    cantidades = validators.lineas(datos)

    # Validaciones contra otros servicios ANTES de abrir la transaccion.
    try:
        usuario = clientes_http.usuario(actor.user_id)
    except clientes_http.ServicioNoDisponible as e:
        raise _no_disponible(e.servicio)
    if usuario is None or not usuario.get("activo"):
        raise ApiError(403, "USUARIO_NO_VALIDO", "Tu cuenta no existe o esta desactivada: no puedes crear pedidos.")
    libros = _libros_de_books(cantidades)

    lineas = [{"isbn": isbn, "titulo": libros[isbn][0], "cantidad": n, "precio_unitario": libros[isbn][1],
               "subtotal": libros[isbn][1] * n} for isbn, n in cantidades.items()]
    total = sum(l["subtotal"] for l in lineas)

    with repository.unit_of_work() as repo:
        _reservar(repo, cantidades)                              # SELECT ... FOR UPDATE + 409 si no alcanza
        pedido = repo.pedido_insert(actor.user_id, total, cfg.RESERVA_MINUTOS)
        repo.lineas_reemplazar(pedido["id"], lineas)
        repo.historial_insert(pedido["id"], None, PENDIENTE, actor.etiqueta)
        resultado = _completo(repo, pedido["id"])

    redis_client.cache_set(redis_keys.pedido_reserva(pedido["id"]),
                           {"user_id": actor.user_id, "expira_en": resultado["expira_en"]}, cfg.RESERVA_SEGUNDOS)
    return resultado


# ------------------------------------------------------------------ consultar
def listar(actor, args):
    estado, user_id = validators.filtros_de_pedidos(args)
    page, per_page = validators.paginacion(args)
    if not actor.es_admin:
        user_id = actor.user_id                                  # un cliente solo ve los suyos
    with repository.unit_of_work() as repo:
        filas, total = repo.pedido_list(user_id=user_id, estado=estado, limit=per_page,
                                        offset=(page - 1) * per_page)
    return {"items": [_resumen(fila) for fila in filas], "page": page, "per_page": per_page, "total": total,
            "pages": ceil(total / per_page) if total else 0}


def obtener(actor, pedido_id):
    with repository.unit_of_work() as repo:
        pedido = repo.pedido_get(pedido_id)
        if pedido is None:
            raise _no_encontrado()
        if not actor.es_admin and pedido["user_id"] != actor.user_id:
            raise _prohibido("Solo puedes consultar tus propios pedidos.")
        return _completo(repo, pedido_id)


def obtener_interno(pedido_id):
    with repository.unit_of_work() as repo:
        if repo.pedido_get(pedido_id) is None:
            raise _no_encontrado()
        return _completo(repo, pedido_id)


# ------------------------------------------------------------------ editar lineas
def editar_lineas(actor, pedido_id, datos, reemplazar):
    """PUT /pedidos/{id} (reemplazar=True: las lineas enviadas son el pedido completo) y
    PATCH /pedidos/{id}/lineas (solo cambia las enviadas; cantidad 0 quita la linea).
    Solo el dueño y solo en PENDIENTE_PAGO; la reserva de stock se reajusta por diferencia."""
    cambios = validators.lineas(datos, permitir_cero=not reemplazar)

    # Lectura previa sin bloqueo: para saber que ISBN son nuevos y pedir su titulo y precio a
    # books fuera de la transaccion. Todo se vuelve a comprobar despues con el pedido bloqueado.
    with repository.unit_of_work() as repo:
        pedido = repo.pedido_get(pedido_id)
        if pedido is None:
            raise _no_encontrado()
        if pedido["user_id"] != actor.user_id:
            raise _prohibido("Solo el dueño del pedido puede modificarlo.")
        conocidos = {l["isbn"] for l in repo.lineas_get(pedido_id)}
    nuevos = _libros_de_books([isbn for isbn, n in cambios.items() if n > 0 and isbn not in conocidos])

    with repository.unit_of_work() as repo:
        pedido = _pedido_bloqueado(repo, pedido_id)
        if pedido["estado"] != PENDIENTE:
            raise ApiError(409, "PEDIDO_NO_EDITABLE",
                           f"Solo se puede modificar un pedido en PENDIENTE_PAGO (esta en {pedido['estado']}).")
        if pedido["expira_en"] <= repo.ahora():
            raise ApiError(409, "PEDIDO_EXPIRADO", "La reserva del pedido ya vencio: no se puede modificar.")

        actuales = {l["isbn"]: l for l in repo.lineas_get(pedido_id)}
        finales = {} if reemplazar else {isbn: l["cantidad"] for isbn, l in actuales.items()}
        finales.update(cambios)
        finales = {isbn: n for isbn, n in finales.items() if n > 0}
        if not finales:
            raise validators.invalido("El pedido no puede quedar sin lineas: para eso, cancelalo.")

        _reservar(repo, {isbn: finales.get(isbn, 0) - (actuales[isbn]["cantidad"] if isbn in actuales else 0)
                         for isbn in set(finales) | set(actuales)})

        lineas = []
        for isbn, n in finales.items():
            if isbn in actuales:                                 # conserva el titulo y el precio ya copiados
                titulo, precio = actuales[isbn]["titulo"], actuales[isbn]["precio_unitario"]
            elif isbn in nuevos:
                titulo, precio = nuevos[isbn]
            else:                                                # aparecio entre las dos lecturas: reintentar
                raise ApiError(409, "PEDIDO_MODIFICADO", "El pedido cambio mientras se editaba. Intenta de nuevo.")
            lineas.append({"isbn": isbn, "titulo": titulo, "cantidad": n, "precio_unitario": precio,
                           "subtotal": precio * n})
        repo.lineas_reemplazar(pedido_id, lineas)
        repo.pedido_fijar_total(pedido_id, sum(l["subtotal"] for l in lineas))
        return _completo(repo, pedido_id)


# ------------------------------------------------------------------ cambios de estado
def cancelar(actor, pedido_id):
    """El dueño cancela en PENDIENTE_PAGO; el admin, en cualquier estado cancelable. Libera el stock."""
    with repository.unit_of_work() as repo:
        pedido = _pedido_bloqueado(repo, pedido_id)
        if not actor.es_admin:
            if pedido["user_id"] != actor.user_id:
                raise _prohibido("Solo puedes cancelar tus propios pedidos.")
            if pedido["estado"] == PAGADO:
                raise _prohibido("Un pedido ya pagado solo lo puede cancelar un administrador.")
        _cambiar_estado(repo, pedido, CANCELADO, actor.etiqueta)
        resultado = _completo(repo, pedido_id)
    _olvidar_reserva(pedido_id)
    return resultado


def cambiar_estado_admin(actor, pedido_id, datos):
    """PATCH /pedidos/{id}/estado: el admin marca ENVIADO o ENTREGADO."""
    nuevo = validators.estado(validators.cuerpo(datos).get("estado"), (ENVIADO, ENTREGADO))
    with repository.unit_of_work() as repo:
        _cambiar_estado(repo, _pedido_bloqueado(repo, pedido_id), nuevo, actor.etiqueta)
        return _completo(repo, pedido_id)


def cambiar_estado_interno(pedido_id, datos):
    """PATCH /pedidos/internal/{id}/estado: el servicio pagos marca PAGADO (o CANCELADO si reembolsa)."""
    nuevo = validators.estado(validators.cuerpo(datos).get("estado"), (PAGADO, CANCELADO))
    with repository.unit_of_work() as repo:
        _cambiar_estado(repo, _pedido_bloqueado(repo, pedido_id), nuevo, ACTOR_PAGOS)
        resultado = _completo(repo, pedido_id)
    _olvidar_reserva(pedido_id)
    return resultado


def eliminar(pedido_id):
    """Borrado logico; solo pedidos CANCELADO o EXPIRADO."""
    with repository.unit_of_work() as repo:
        pedido = _pedido_bloqueado(repo, pedido_id)
        if pedido["estado"] not in (CANCELADO, EXPIRADO):
            raise ApiError(409, "PEDIDO_NO_ELIMINABLE",
                           f"Solo se eliminan pedidos CANCELADO o EXPIRADO (esta en {pedido['estado']}).")
        repo.pedido_eliminar(pedido_id)
    return {"status": "ok", "id": pedido_id, "message": "Pedido eliminado."}


# ------------------------------------------------------------------ expiracion
def expirar_vencidos():
    """Pasa a EXPIRADO los pedidos PENDIENTE_PAGO cuya reserva vencio y libera su stock.
    Decide con los datos de PostgreSQL (expira_en), no con Redis. Devuelve los ids expirados."""
    with repository.unit_of_work() as repo:
        ids = repo.pedidos_vencidos()
        for pedido_id in ids:
            _cambiar_estado(repo, repo.pedido_get(pedido_id), EXPIRADO, ACTOR_EXPIRACION)
    for pedido_id in ids:
        _olvidar_reserva(pedido_id)
    return ids
