"""
services/validators.py
Validacion de los datos de entrada. Las reglas de nombres y de correo
(formato + registro MX del dominio) son las MISMAS que aplica login en
POST /register (apps/services/login/validators.py): una cuenta valida en
un servicio lo es en el otro.

Cada funcion devuelve el valor limpio o lanza ApiError 400 VALIDACION.
"""
import re

import dns.exception
import dns.resolver
from email_validator import EmailNotValidError, validate_email

from common.errors import ApiError

# Cache en memoria del proceso: evita repetir la misma consulta MX.
_MX_CACHE = {}

# Nombres: empiezan con letra; despues letras (con acentos), espacios, ', . y -.
_NOMBRE_RE = re.compile(r"[^\W\d_](?:[^\W\d_]|[ '’.\-])*")

# campo -> (etiqueta, longitud maxima de la columna, obligatorio)
CAMPOS_NOMBRE = {
    "nombre": ("El nombre", 150, True),
    "apellido_paterno": ("El apellido paterno", 100, False),
    "apellido_materno": ("El apellido materno", 100, False),
}

PER_PAGE_DEFECTO = 20
PER_PAGE_MAXIMO = 100


def invalido(mensaje):
    return ApiError(400, "VALIDACION", mensaje)


def _dominio_recibe_correo(dominio):
    """Consulta MX (dnspython). Ante un problema de red/timeout no se bloquea (fail-open)."""
    if dominio in _MX_CACHE:
        return _MX_CACHE[dominio]
    try:
        resultado = bool(dns.resolver.resolve(dominio, "MX", lifetime=5))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        resultado = False
    except dns.exception.Timeout:
        resultado = True
    _MX_CACHE[dominio] = resultado
    return resultado


def email(valor):
    if not isinstance(valor, str) or not valor.strip():
        raise invalido("El email es obligatorio.")
    try:
        info = validate_email(valor.strip(), check_deliverability=False)
    except EmailNotValidError as e:
        raise invalido(f"El email no es valido: {e}")
    correo = info.normalized.lower()
    if len(correo) > 150:
        raise invalido("El email no puede exceder 150 caracteres.")
    if not _dominio_recibe_correo(info.domain):
        raise invalido("El dominio del email no recibe correo (sin registro MX).")
    return correo


def nombre(campo, valor):
    """Texto limpio, o None si el campo es opcional y viene vacio."""
    etiqueta, maximo, obligatorio = CAMPOS_NOMBRE[campo]
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        raise invalido(f"{etiqueta} debe ser texto.")
    valor = " ".join(valor.split())  # recorta y colapsa espacios
    if not valor:
        if obligatorio:
            raise invalido(f"{etiqueta} es obligatorio.")
        return None
    if len(valor) > maximo:
        raise invalido(f"{etiqueta} no puede exceder {maximo} caracteres.")
    if not _NOMBRE_RE.fullmatch(valor):
        raise invalido(f"{etiqueta} solo puede contener letras, espacios, apostrofes, puntos y guiones.")
    return valor


def booleano(campo, valor):
    if not isinstance(valor, bool):
        raise invalido(f"'{campo}' debe ser true o false.")
    return valor


def entero(campo, valor):
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise invalido(f"'{campo}' debe ser un numero entero.")
    return valor


# ------------------------------------------------------------------ query string
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
    """?q=&role_id=&activo=&page=&per_page=  ->  dict listo para el repositorio."""
    activo = args.get("activo")
    if activo is not None and activo != "":
        if activo.lower() not in ("true", "false", "1", "0"):
            raise invalido("'activo' debe ser true o false.")
        activo = activo.lower() in ("true", "1")
    else:
        activo = None
    return {
        "q": (args.get("q") or "").strip() or None,
        "role_id": _entero_query(args, "role_id", None, 1),
        "activo": activo,
        "page": _entero_query(args, "page", 1, 1),
        "per_page": _entero_query(args, "per_page", PER_PAGE_DEFECTO, 1, PER_PAGE_MAXIMO),
    }
