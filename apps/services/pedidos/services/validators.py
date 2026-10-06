"""
services/validators.py
Validacion de entradas del microservicio pedidos. Cada funcion devuelve el
valor limpio o lanza ApiError 400 VALIDACION.
"""
import re

from common.errors import ApiError

ESTADOS = ("PENDIENTE_PAGO", "PAGADO", "ENVIADO", "ENTREGADO", "CANCELADO", "EXPIRADO")
CANTIDAD_MAXIMA = 999
LINEAS_MAXIMAS = 50
STOCK_MAXIMO = 1_000_000

# Misma forma que libros.isbn en books: hasta 13 caracteres, digitos, letras o guiones.
_ISBN_RE = re.compile(r"[0-9A-Za-z\-]{1,13}")


def invalido(mensaje):
    return ApiError(400, "VALIDACION", mensaje)


def cuerpo(datos):
    if not isinstance(datos, dict):
        raise invalido("Envia el cuerpo como un objeto JSON (Content-Type: application/json).")
    return datos


def isbn(valor):
    if not isinstance(valor, str) or not _ISBN_RE.fullmatch(valor.strip()):
        raise invalido("'isbn' es obligatorio: hasta 13 caracteres (digitos, letras o guiones).")
    return valor.strip()


def _entero(campo, valor, minimo, maximo):
    if isinstance(valor, bool) or not isinstance(valor, int) or not minimo <= valor <= maximo:
        raise invalido(f"'{campo}' debe ser un numero entero entre {minimo} y {maximo}.")
    return valor


def stock(valor):
    return _entero("stock_disponible", valor, 0, STOCK_MAXIMO)


def lineas(datos, permitir_cero=False):
    """{"lineas": [{"isbn", "cantidad"}]}  ->  {isbn: cantidad}.
    Un ISBN repetido es un error. Con `permitir_cero`, cantidad 0 significa "quitar la linea"."""
    crudas = cuerpo(datos).get("lineas")
    if not isinstance(crudas, list) or not crudas:
        raise invalido("'lineas' debe ser una lista con al menos un elemento: [{\"isbn\", \"cantidad\"}].")
    if len(crudas) > LINEAS_MAXIMAS:
        raise invalido(f"Un pedido admite como maximo {LINEAS_MAXIMAS} lineas.")
    resultado = {}
    for linea in crudas:
        if not isinstance(linea, dict):
            raise invalido("Cada linea debe ser un objeto {\"isbn\", \"cantidad\"}.")
        clave = isbn(linea.get("isbn"))
        if clave in resultado:
            raise invalido(f"El ISBN {clave} aparece mas de una vez en 'lineas'.")
        resultado[clave] = _entero("cantidad", linea.get("cantidad"), 0 if permitir_cero else 1, CANTIDAD_MAXIMA)
    return resultado


def estado(valor, permitidos):
    if not isinstance(valor, str) or valor.strip().upper() not in permitidos:
        raise invalido(f"'estado' debe ser uno de: {', '.join(permitidos)}.")
    return valor.strip().upper()


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


def paginacion(args, defecto=20, maximo=100):
    return _entero_query(args, "page", 1, 1), _entero_query(args, "per_page", defecto, 1, maximo)


def filtros_de_pedidos(args):
    crudo = (args.get("estado") or "").strip().upper()
    if crudo and crudo not in ESTADOS:
        raise invalido(f"'estado' debe ser uno de: {', '.join(ESTADOS)}.")
    return crudo or None, _entero_query(args, "user_id", None, 1)
