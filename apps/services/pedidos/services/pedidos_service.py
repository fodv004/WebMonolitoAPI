"""
services/pedidos_service.py
Reglas de negocio de los pedidos (sin Flask).

Estados (cualquier otra transicion -> 409 TRANSICION_INVALIDA):
    PENDIENTE_PAGO -> PAGADO | CANCELADO | EXPIRADO
    PAGADO         -> ENVIADO | CANCELADO
    ENVIADO        -> ENTREGADO

Stock: el stock real es libros.stock y lo mueve el microservicio books por sus
endpoints internos (una transaccion con SELECT ... FOR UPDATE del lado de books):
    crear / agregar unidades          POST /books/internal/stock/reservar   (409 si no alcanza)
    cancelar, expirar o quitar unid.  POST /books/internal/stock/liberar
    pagar                             no mueve stock (ya se resto al reservar)
Si books no responde al liberar, el cambio de estado NO se aplica (503) y se reintenta.

PostgreSQL es la fuente de verdad. La clave de Redis pedido:reserva:<id>
(TTL = minutos de reserva) es solo un espejo de la reserva: escribirla o
borrarla nunca hace fallar una operacion.
"""
import logging
from decimal import Decimal
from math import ceil

from common import redis_client, redis_keys
from common.auth import ADMIN_ROLE_ID
from common.errors import ApiError
from config import settings as cfg
from db import repository
from services import clientes_http, validators

log = logging.getLogger(__name__)

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


def _items(cantidades):
    return [{"isbn": isbn, "cantidad": n} for isbn, n in sorted(cantidades.items()) if n > 0]


def _reservar_en_books(cantidades):
    """Resta de libros.stock (books lo hace todo o nada). 409 indicando el ISBN si no alcanza."""
    items = _items(cantidades)
    if not items:
        return
    try:
        clientes_http.reservar_stock(items)
    except clientes_http.StockInsuficiente as e:
        raise ApiError(409, "STOCK_INSUFICIENTE", e.mensaje)
    except clientes_http.LibroNoEncontrado as e:
        raise ApiError(404, "LIBRO_NO_ENCONTRADO", e.mensaje)
    except clientes_http.ServicioNoDisponible as e:
        raise _no_disponible(e.servicio)


def _liberar_en_books(cantidades):
    """Devuelve unidades a libros.stock. 503 si books no responde (quien llama no aplica su cambio)."""
    items = _items(cantidades)
    if not items:
        return
    try:
        clientes_http.liberar_stock(items)
    except clientes_http.LibroNoEncontrado:
        log.warning("Al liberar stock, books ya no tiene alguno de los libros: %s", [i["isbn"] for i in items])
    except (clientes_http.ServicioNoDisponible, clientes_http.StockInsuficiente):
        raise _no_disponible("books")


def _compensar(cantidades):
    """Devuelve lo recien reservado cuando el paso siguiente fallo. Nunca lanza."""
    try:
        _liberar_en_books(cantidades)
    except Exception:
        log.error("No se pudo devolver a books el stock reservado: %s", _items(cantidades))


def _cambiar_estado(repo, pedido, nuevo, actor):
    """Unico lugar donde un pedido cambia de estado: valida la transicion, devuelve el stock a
    books si el pedido se cancela o expira, y deja el rastro en el historial. `pedido` debe venir
    bloqueado. Si books no responde, lanza 503 y la transaccion se deshace."""
    actual = pedido["estado"]
    if nuevo not in TRANSICIONES.get(actual, ()):
        raise _transicion_invalida(actual, nuevo)

    repo.pedido_cambiar_estado(pedido["id"], nuevo)
    repo.historial_insert(pedido["id"], actual, nuevo, actor)
    if nuevo in (CANCELADO, EXPIRADO):
        # Lo ultimo: si esto falla, lo anterior se deshace con la transaccion.
        _liberar_en_books({l["isbn"]: l["cantidad"] for l in repo.lineas_get(pedido["id"])})


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

    _reservar_en_books(cantidades)                               # resta de libros.stock; 409 si no alcanza
    try:
        with repository.unit_of_work() as repo:
            pedido = repo.pedido_insert(actor.user_id, total, cfg.RESERVA_MINUTOS)
            repo.lineas_reemplazar(pedido["id"], lineas)
            repo.historial_insert(pedido["id"], None, PENDIENTE, actor.etiqueta)
            resultado = _completo(repo, pedido["id"])
    except BaseException:
        _compensar(cantidades)                                   # el pedido no se guardo: se devuelve el stock
        raise

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

        deltas = {isbn: finales.get(isbn, 0) - (actuales[isbn]["cantidad"] if isbn in actuales else 0)
                  for isbn in set(finales) | set(actuales)}
        de_mas = {isbn: d for isbn, d in deltas.items() if d > 0}        # unidades que se agregan
        de_menos = {isbn: -d for isbn, d in deltas.items() if d < 0}     # unidades que se quitan

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
        _reservar_en_books(de_mas)                               # 409 si no alcanza: nada cambio todavia
        try:
            repo.lineas_reemplazar(pedido_id, lineas)
            repo.pedido_fijar_total(pedido_id, sum(l["subtotal"] for l in lineas))
            resultado = _completo(repo, pedido_id)
            _liberar_en_books(de_menos)
        except BaseException:
            _compensar(de_mas)
            raise
        return resultado


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
    """Pasa a EXPIRADO los pedidos PENDIENTE_PAGO cuya reserva vencio y devuelve su stock a books.
    Decide con los datos de PostgreSQL (expira_en), no con Redis. Cada pedido va en su propia
    transaccion: si books no responde, ese pedido se queda pendiente y se reintenta en la
    siguiente vuelta. Devuelve los ids expirados."""
    with repository.unit_of_work() as repo:
        candidatos = repo.pedidos_vencidos()
    expirados = []
    for pedido_id in candidatos:
        try:
            with repository.unit_of_work() as repo:
                pedido = repo.pedido_get(pedido_id, bloquear=True)
                if pedido is None or pedido["estado"] != PENDIENTE or pedido["expira_en"] > repo.ahora():
                    continue                             # lo pagaron o cancelaron mientras tanto
                _cambiar_estado(repo, pedido, EXPIRADO, ACTOR_EXPIRACION)
        except ApiError as e:
            log.warning("No se pudo expirar el pedido %s (%s); se reintenta en la siguiente vuelta",
                        pedido_id, e.code)
            continue
        expirados.append(pedido_id)
        _olvidar_reserva(pedido_id)
    return expirados
