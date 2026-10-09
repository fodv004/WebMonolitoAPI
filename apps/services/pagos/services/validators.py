"""
services/validators.py
Validacion de entradas del microservicio pagos. Cada funcion devuelve el
valor limpio o lanza ApiError 400 VALIDACION.

Los mensajes de error NUNCA repiten el valor recibido en los campos de
tarjeta: un numero mal escrito no debe terminar en una respuesta ni en un log.
"""
import re

from common.errors import ApiError

METODOS = ("TARJETA_SIMULADA", "TRANSFERENCIA", "EFECTIVO")
ESTADOS = ("APROBADO", "RECHAZADO", "REEMBOLSADO")
TARJETA = METODOS[0]

REFERENCIA_MAXIMO = 40
NOTAS_MAXIMO = 500

_LLAVE_RE = re.compile(r"[A-Za-z0-9_\-]{8,100}")
_TARJETA_RE = re.compile(r"[0-9]{13,19}")
_CVV_RE = re.compile(r"[0-9]{3,4}")


def invalido(mensaje):
    return ApiError(400, "VALIDACION", mensaje)


def cuerpo(datos):
    if not isinstance(datos, dict):
        raise invalido("Envia el cuerpo como un objeto JSON (Content-Type: application/json).")
    return datos


def llave_de_idempotencia(valor):
    if not isinstance(valor, str) or not _LLAVE_RE.fullmatch(valor.strip()):
        raise invalido("Falta el header Idempotency-Key (8 a 100 caracteres: letras, digitos, '-' o '_'). "
                       "Genera uno por intento de pago, por ejemplo un UUID, y reutilizalo si reintentas.")
    return valor.strip()


def pedido_id(valor):
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise invalido("'pedido_id' es obligatorio y debe ser un numero entero.")
    return valor


def metodo(valor):
    if not isinstance(valor, str) or valor.strip().upper() not in METODOS:
        raise invalido(f"'metodo' debe ser uno de: {', '.join(METODOS)}.")
    return valor.strip().upper()


def ultimos4_de_tarjeta(datos):
    """Valida `tarjeta` y `cvv` y devuelve SOLO los ultimos 4 digitos: el numero completo y el
    CVV no salen de esta funcion (no se guardan, no se devuelven y no se registran)."""
    numero, cvv = datos.get("tarjeta"), datos.get("cvv")
    if not isinstance(numero, str) or not _TARJETA_RE.fullmatch(numero.replace(" ", "").replace("-", "")):
        raise invalido("'tarjeta' es obligatoria con TARJETA_SIMULADA: de 13 a 19 digitos.")
    if not isinstance(cvv, str) or not _CVV_RE.fullmatch(cvv.strip()):
        raise invalido("'cvv' es obligatorio con TARJETA_SIMULADA: 3 o 4 digitos.")
    return numero.replace(" ", "").replace("-", "")[-4:]


def texto(campo, valor, maximo, obligatorio=False):
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        raise invalido(f"'{campo}' debe ser texto.")
    valor = valor.strip()
    if not valor:
        if obligatorio:
            raise invalido(f"'{campo}' no puede quedar vacio.")
        return None
    if len(valor) > maximo:
        raise invalido(f"'{campo}' no puede exceder {maximo} caracteres.")
    return valor


def _opcion(args, campo, permitidos):
    crudo = (args.get(campo) or "").strip().upper()
    if crudo and crudo not in permitidos:
        raise invalido(f"'{campo}' debe ser uno de: {', '.join(permitidos)}.")
    return crudo or None


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
    """?estado=&metodo=&user_id=&page=&per_page=  ->  dict normalizado."""
    return {
        "estado": _opcion(args, "estado", ESTADOS),
        "metodo": _opcion(args, "metodo", METODOS),
        "user_id": _entero_query(args, "user_id", None, 1),
        "page": _entero_query(args, "page", 1, 1),
        "per_page": _entero_query(args, "per_page", 20, 1, 100),
    }
