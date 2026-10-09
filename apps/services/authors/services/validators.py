"""
services/validators.py
Validacion de los datos de entrada del microservicio authors. Cada funcion
devuelve el valor limpio o lanza ApiError 400 VALIDACION.
"""
import re

from common.errors import ApiError

PER_PAGE_DEFECTO = 20
PER_PAGE_MAXIMO = 100
Q_MAXIMO = 100

# campo -> (etiqueta, longitud maxima de la columna)
_TEXTOS = {
    "nombre": ("El nombre", 150),             # autores.nombre VARCHAR(150)
    "nacionalidad": ("La nacionalidad", 80),  # autores.nacionalidad VARCHAR(80)
}
# Misma forma que libros.isbn en books: hasta 13 caracteres, digitos, letras o guiones.
_ISBN_RE = re.compile(r"[0-9A-Za-z\-]{1,13}")


def invalido(mensaje):
    return ApiError(400, "VALIDACION", mensaje)


def texto(campo, valor, obligatorio=False):
    """Texto limpio, o None si es opcional y viene vacio."""
    etiqueta, maximo = _TEXTOS[campo]
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        raise invalido(f"{etiqueta} debe ser texto.")
    valor = " ".join(valor.split())
    if not valor:
        if obligatorio:
            raise invalido(f"{etiqueta} es obligatorio.")
        return None
    if len(valor) > maximo:
        raise invalido(f"{etiqueta} no puede exceder {maximo} caracteres.")
    if "<" in valor or ">" in valor:
        raise invalido(f"{etiqueta} contiene caracteres no permitidos.")
    return valor


def isbn(valor):
    if not isinstance(valor, str) or not _ISBN_RE.fullmatch(valor.strip()):
        raise invalido("'isbn' es obligatorio: hasta 13 caracteres (digitos, letras o guiones).")
    return valor.strip()


def _entero_query(args, campo, defecto, minimo, maximo=None):
    crudo = args.get(campo)
    if crudo is None or crudo == "":
        return defecto
    try:
        numero = int(crudo)
    except ValueError:
        raise invalido(f"'{campo}' debe ser un numero entero.")
    if numero < minimo:
        raise invalido(f"'{campo}' debe ser mayor o igual a {minimo}.")
    return min(numero, maximo) if maximo else numero


def filtros_de_lista(args):
    """?q=&nacionalidad=&page=&per_page=  ->  dict normalizado (tambien sirve de clave de cache)."""
    return {
        "q": " ".join((args.get("q") or "").split())[:Q_MAXIMO] or None,
        "nacionalidad": " ".join((args.get("nacionalidad") or "").split())[:80] or None,
        "page": _entero_query(args, "page", 1, 1),
        "per_page": _entero_query(args, "per_page", PER_PAGE_DEFECTO, 1, PER_PAGE_MAXIMO),
    }
