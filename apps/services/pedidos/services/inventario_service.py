"""
services/inventario_service.py
Inventario: stock disponible y reservado por ISBN. Las lecturas son
publicas; altas, cambios y bajas son del admin.

El admin fija el stock DISPONIBLE. El reservado lo mueven solo los
pedidos (services/pedidos_service.py), nunca este modulo.
"""
from math import ceil

from common.errors import ApiError
from db import repository
from services import clientes_http, validators


def _publico(fila):
    return {"isbn": fila["isbn"], "stock_disponible": fila["stock_disponible"],
            "stock_reservado": fila["stock_reservado"],
            "updated_at": fila["updated_at"].isoformat(timespec="seconds")}


def _no_encontrado(isbn):
    return ApiError(404, "INVENTARIO_NO_ENCONTRADO", f"El ISBN {isbn} no esta en el inventario.")


def listar(args):
    page, per_page = validators.paginacion(args, defecto=100, maximo=500)
    with repository.unit_of_work() as repo:
        filas, total = repo.inventario_list(limit=per_page, offset=(page - 1) * per_page)
    return {"items": [_publico(fila) for fila in filas], "page": page, "per_page": per_page, "total": total,
            "pages": ceil(total / per_page) if total else 0}


def obtener(isbn):
    isbn = validators.isbn(isbn)
    with repository.unit_of_work() as repo:
        fila = repo.inventario_get(isbn)
    if fila is None:
        raise _no_encontrado(isbn)
    return _publico(fila)


def crear(datos):
    """Alta de un ISBN en el inventario; el libro debe existir en books."""
    datos = validators.cuerpo(datos)
    isbn = validators.isbn(datos.get("isbn"))
    stock = validators.stock(datos.get("stock_disponible"))
    try:
        libro = clientes_http.libro(isbn)
    except clientes_http.ServicioNoDisponible:
        raise ApiError(503, "BOOKS_NO_DISPONIBLE", "El servicio books no responde: no se puede validar el ISBN.")
    if libro is None:
        raise ApiError(404, "LIBRO_NO_ENCONTRADO", f"No existe un libro con ISBN {isbn} en el catalogo.")
    with repository.unit_of_work() as repo:
        try:
            return _publico(repo.inventario_insert(isbn, stock))
        except repository.InventarioDuplicado:
            raise ApiError(409, "INVENTARIO_DUPLICADO",
                           f"El ISBN {isbn} ya esta en el inventario: usa PUT /inventario/{isbn}.")


def actualizar(isbn, datos):
    """Fija el stock disponible (el reservado no se toca)."""
    isbn = validators.isbn(isbn)
    stock = validators.stock(validators.cuerpo(datos).get("stock_disponible"))
    with repository.unit_of_work() as repo:
        if not repo.inventario_bloquear([isbn]):
            raise _no_encontrado(isbn)
        return _publico(repo.inventario_fijar_disponible(isbn, stock))


def eliminar(isbn):
    isbn = validators.isbn(isbn)
    with repository.unit_of_work() as repo:
        fila = repo.inventario_bloquear([isbn]).get(isbn)
        if fila is None:
            raise _no_encontrado(isbn)
        if fila["stock_reservado"] > 0:
            raise ApiError(409, "INVENTARIO_CON_RESERVAS",
                           f"El ISBN {isbn} tiene {fila['stock_reservado']} unidad(es) reservadas por pedidos "
                           "pendientes de pago: no se puede eliminar.")
        repo.inventario_delete(isbn)
    return {"status": "ok", "isbn": isbn, "message": "ISBN eliminado del inventario."}
