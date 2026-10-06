"""
services/validators.py
Validacion de los datos de entrada del microservicio authors. Cada funcion
devuelve el valor limpio o lanza ApiError 400 VALIDACION.
"""
import re
from datetime import date

from common.errors import ApiError

PER_PAGE_DEFECTO = 20
PER_PAGE_MAXIMO = 100
BIOGRAFIA_MAXIMO = 5000
Q_MAXIMO = 100

# campo -> (etiqueta, longitud maxima de la columna)
_TEXTOS = {
    "nombre": ("El nombre", 150),
    "apellido": ("El apellido", 150),
    "nacionalidad": ("La nacionalidad", 80),
    "biografia": ("La biografia", BIOGRAFIA_MAXIMO),
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
    valor = valor.strip() if campo == "biografia" else " ".join(valor.split())
    if not valor:
        if obligatorio:
            raise invalido(f"{etiqueta} es obligatorio.")
        return None
    if len(valor) > maximo:
        raise invalido(f"{etiqueta} no puede exceder {maximo} caracteres.")
    if campo != "biografia" and ("<" in valor or ">" in valor):
        raise invalido(f"{etiqueta} contiene caracteres no permitidos.")
    return valor


def fecha(valor):
    """date a partir de 'AAAA-MM-DD', o None si viene vacia."""
    if valor is None or valor == "":
        return None
    if not isinstance(valor, str):
        raise invalido("'fecha_nacimiento' debe ser texto con formato AAAA-MM-DD.")
    try:
        resultado = date.fromisoformat(valor.strip())
    except ValueError:
        raise invalido("'fecha_nacimiento' debe tener formato AAAA-MM-DD y ser una fecha real.")
    if resultado > date.today():
        raise invalido("'fecha_nacimiento' no puede ser una fecha futura.")
    return resultado


def isbn(valor):
    if not isinstance(valor, str) or not _ISBN_RE.fullmatch(valor.strip()):
        raise invalido("'isbn' es obligatorio: hasta 13 caracteres (digitos, letras o guiones).")
    return valor.strip()


def orden(valor):
    """Entero >= 1, o None si no se envio (se asigna el siguiente)."""
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise invalido("'orden' debe ser un numero entero mayor o igual a 1.")
    return valor


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
