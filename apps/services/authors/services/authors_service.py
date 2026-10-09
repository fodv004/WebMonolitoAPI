"""
services/authors_service.py
Reglas de negocio del microservicio authors (sin Flask), sobre las tablas
`autores` (id_autor, nombre, nacionalidad) y `libro_autor` (isbn, id_autor).

  * Las lecturas son publicas y se cachean 60 s en Redis. Redis es opcional
    aqui: si falla, se consulta PostgreSQL (los cache_* nunca lanzan).
  * Cualquier escritura invalida toda la cache del servicio (authors:*) con SCAN.
  * Un libro solo se relaciona si existe en books; si books no responde -> 503.
  * Un autor con libros relacionados no se elimina (409) salvo ?force=true.
"""
from math import ceil
from urllib.parse import urlencode

from common import redis_client, redis_keys
from common.errors import ApiError
from db import repository
from services import books_client, validators

_CAMPOS = ("nombre", "nacionalidad")


# ------------------------------------------------------------------ salida
def publico(fila):
    """Representacion de un autor en la API."""
    return {
        "id_autor": fila["id_autor"],
        "nombre": fila["nombre"],
        "nacionalidad": fila["nacionalidad"],
        "total_libros": fila.get("total_libros", 0),
    }


# ------------------------------------------------------------------ errores
def _no_encontrado():
    return ApiError(404, "AUTOR_NO_ENCONTRADO", "No existe el autor indicado.")


def _libro_no_encontrado(isbn):
    return ApiError(404, "LIBRO_NO_ENCONTRADO", f"No existe un libro con ISBN {isbn} en el catalogo.")


def _books_no_disponible():
    return ApiError(503, "BOOKS_NO_DISPONIBLE",
                    "El servicio de libros no responde: no se puede validar el ISBN. Intenta mas tarde.")


def _cuerpo(datos):
    if not isinstance(datos, dict):
        raise validators.invalido("Envia el cuerpo como un objeto JSON (Content-Type: application/json).")
    return datos


def _invalidar_cache():
    redis_client.cache_invalidate(redis_keys.AUTHORS_PATTERN)


# ------------------------------------------------------------------ lecturas (cacheadas)
def listar(args):
    filtros = validators.filtros_de_lista(args)
    clave = redis_keys.authors_list(urlencode({k: (v.lower() if isinstance(v, str) else v)
                                               for k, v in filtros.items() if v is not None}))
    datos = redis_client.cache_get(clave)
    if datos is None:
        page, per_page = filtros["page"], filtros["per_page"]
        with repository.unit_of_work() as repo:
            filas, total = repo.list(q=filtros["q"], nacionalidad=filtros["nacionalidad"],
                                     limit=per_page, offset=(page - 1) * per_page)
        datos = {
            "items": [publico(fila) for fila in filas],
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": ceil(total / per_page) if total else 0,
        }
        redis_client.cache_set(clave, datos, redis_keys.CACHE_TTL)
    return datos


def obtener(id_autor):
    clave = redis_keys.author(id_autor)
    datos = redis_client.cache_get(clave)
    if datos is None:
        with repository.unit_of_work() as repo:
            fila = repo.get(id_autor)
        if fila is None:
            raise _no_encontrado()          # los 404 no se cachean
        datos = publico(fila)
        redis_client.cache_set(clave, datos, redis_keys.CACHE_TTL)
    return datos


def libros_de(id_autor):
    """Libros del autor con su titulo (de books). Si books falla: solo los ISBN, `enriquecido` = false."""
    clave = redis_keys.author_books(id_autor)
    datos = redis_client.cache_get(clave)
    if datos is not None:
        return datos

    with repository.unit_of_work() as repo:
        if repo.get(id_autor) is None:
            raise _no_encontrado()
        relaciones = repo.books_of(id_autor)

    libros = [{"isbn": r["isbn"], "titulo": None} for r in relaciones]
    enriquecido = True
    if libros:
        try:
            titulos = books_client.titulos()
        except books_client.BooksNoDisponible:
            enriquecido = False
        else:
            for libro in libros:
                libro["titulo"] = titulos.get(libro["isbn"])
    datos = {"id_autor": id_autor, "enriquecido": enriquecido, "books": libros}
    if enriquecido:
        # La respuesta degradada no se cachea: en cuanto books vuelva, vuelven los titulos.
        redis_client.cache_set(clave, datos, redis_keys.CACHE_TTL)
    return datos


def por_libro(isbn):
    """Autores de un libro. No consulta a books: un ISBN sin relaciones devuelve lista vacia."""
    isbn = validators.isbn(isbn)
    clave = redis_keys.authors_by_book(isbn)
    datos = redis_client.cache_get(clave)
    if datos is None:
        with repository.unit_of_work() as repo:
            filas = repo.authors_of(isbn)
        datos = {"isbn": isbn, "authors": [publico(fila) for fila in filas]}
        redis_client.cache_set(clave, datos, redis_keys.CACHE_TTL)
    return datos


# ------------------------------------------------------------------ escrituras
def _campos_validados(datos, parcial):
    cambios = {}
    for campo in _CAMPOS:
        if campo not in datos and parcial:
            continue
        cambios[campo] = validators.texto(campo, datos.get(campo), obligatorio=campo == "nombre")
    return cambios


def crear(datos):
    campos = _campos_validados(_cuerpo(datos), parcial=False)
    with repository.unit_of_work() as repo:
        fila = repo.insert(**campos)
    _invalidar_cache()
    return publico(fila)


def actualizar(id_autor, datos, parcial):
    """PUT (parcial=False: reemplaza nombre y nacionalidad) y PATCH (solo los enviados)."""
    cambios = _campos_validados(_cuerpo(datos), parcial)
    if not cambios:
        raise validators.invalido("No enviaste ningun campo para modificar.")
    with repository.unit_of_work() as repo:
        if repo.get(id_autor, bloquear=True) is None:
            raise _no_encontrado()
        fila = repo.update(id_autor, **cambios)
    _invalidar_cache()
    return publico(fila)


def eliminar(id_autor, forzar):
    with repository.unit_of_work() as repo:
        fila = repo.get(id_autor, bloquear=True)
        if fila is None:
            raise _no_encontrado()
        if fila["total_libros"] and not forzar:
            raise ApiError(409, "AUTOR_CON_LIBROS",
                           f"El autor tiene {fila['total_libros']} libro(s) relacionado(s). Quita las relaciones "
                           "o repite la peticion con ?force=true para eliminarlo junto con ellas.")
        repo.delete(id_autor)               # borra antes sus filas de libro_autor (ON DELETE RESTRICT)
    _invalidar_cache()
    return {"status": "ok", "id_autor": id_autor, "relaciones_eliminadas": fila["total_libros"],
            "message": "Autor eliminado."}


def relacionar(id_autor, datos):
    datos = _cuerpo(datos)
    isbn = validators.isbn(datos.get("isbn"))

    with repository.unit_of_work() as repo:
        if repo.get(id_autor) is None:
            raise _no_encontrado()
    # La consulta a books va fuera de la transaccion: no se retiene una conexion durante la llamada.
    try:
        libro = books_client.libro(isbn)
    except books_client.BooksNoDisponible:
        raise _books_no_disponible()
    if libro is None:
        raise _libro_no_encontrado(isbn)

    with repository.unit_of_work() as repo:
        if repo.get(id_autor, bloquear=True) is None:
            raise _no_encontrado()
        try:
            relacion = repo.add_book(id_autor, isbn)
        except repository.RelacionDuplicada:
            raise ApiError(409, "RELACION_DUPLICADA", "Ese libro ya esta relacionado con el autor.")
        except repository.LibroInexistente:
            raise _libro_no_encontrado(isbn)
    _invalidar_cache()
    return {"id_autor": id_autor, **relacion, "titulo": libro.get("titulo")}


def quitar_relacion(id_autor, isbn):
    isbn = validators.isbn(isbn)
    with repository.unit_of_work() as repo:
        if not repo.remove_book(id_autor, isbn):
            raise ApiError(404, "RELACION_NO_ENCONTRADA", "El autor no tiene relacionado ese libro.")
    _invalidar_cache()
    return {"status": "ok", "id_autor": id_autor, "isbn": isbn, "message": "Relacion eliminada."}
