"""
validators.py
Validacion de los datos de entrada. Devuelve (datos_limpios, errores); cada
error es {"field": ..., "message": ...}.
"""
import re

import dns.exception
import dns.resolver
from email_validator import EmailNotValidError, validate_email

from security import BCRYPT_MAX_BYTES

PASSWORD_MIN = 8

# Cache en memoria del proceso: evita repetir la misma consulta MX en cada intento de registro.
_MX_CACHE = {}


def _dominio_recibe_correo(dominio):
    """Consulta MX (dnspython) para saber si el dominio puede recibir correo.
    Ante un problema de red/timeout no se bloquea el registro (fail-open)."""
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

# Nombres: empiezan con letra; despues letras (con acentos), espacios, ', . y -.
# Rechaza digitos, '<', '>' y demas simbolos.
_NOMBRE_RE = re.compile(r"[^\W\d_](?:[^\W\d_]|[ '’.\-])*")

# campo -> (etiqueta, longitud maxima segun la columna de la tabla usuarios)
CAMPOS_NOMBRE = {
    "nombre": ("El nombre", 150),
    "apellido_paterno": ("El apellido paterno", 100),
    "apellido_materno": ("El apellido materno", 100),
}


def _texto(data, campo):
    valor = data.get(campo)
    if valor is None:
        return None
    return valor if isinstance(valor, str) else False  # False = tipo incorrecto


def validar_email(valor):
    """Devuelve (email_normalizado, None) o (None, mensaje)."""
    if not valor or not valor.strip():
        return None, "El email es obligatorio."
    try:
        # Formato y dominio bien formado (sin la consulta DNS propia de la libreria: se hace abajo con dnspython).
        info = validate_email(valor.strip(), check_deliverability=False)
    except EmailNotValidError as e:
        return None, f"El email no es valido: {e}"
    correo = info.normalized.lower()
    if len(correo) > 150:
        return None, "El email no puede exceder 150 caracteres."
    if not _dominio_recibe_correo(info.domain):
        return None, "El dominio del email no recibe correo (sin registro MX)."
    return correo, None


def validar_registro(data):
    limpio, errores = {}, []

    for campo, (etiqueta, maximo) in CAMPOS_NOMBRE.items():
        valor = _texto(data, campo)
        if valor is False:
            errores.append({"field": campo, "message": f"{etiqueta} debe ser texto."})
            continue
        valor = " ".join((valor or "").split())  # recorta y colapsa espacios
        if not valor:
            errores.append({"field": campo, "message": f"{etiqueta} es obligatorio."})
        elif len(valor) > maximo:
            errores.append({"field": campo, "message": f"{etiqueta} no puede exceder {maximo} caracteres."})
        elif not _NOMBRE_RE.fullmatch(valor):
            errores.append({"field": campo, "message": f"{etiqueta} solo puede contener letras, espacios, apostrofes, puntos y guiones."})
        else:
            limpio[campo] = valor

    email = _texto(data, "email")
    if email is False:
        errores.append({"field": "email", "message": "El email debe ser texto."})
    else:
        correo, mensaje = validar_email(email)
        if mensaje:
            errores.append({"field": "email", "message": mensaje})
        else:
            limpio["email"] = correo

    password = _texto(data, "password")
    if password is False:
        errores.append({"field": "password", "message": "El password debe ser texto."})
    elif not password:
        errores.append({"field": "password", "message": "El password es obligatorio."})
    elif len(password) < PASSWORD_MIN:
        errores.append({"field": "password", "message": f"El password debe tener al menos {PASSWORD_MIN} caracteres."})
    elif len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        errores.append({"field": "password", "message": f"El password no puede exceder {BCRYPT_MAX_BYTES} bytes."})
    else:
        limpio["password"] = password

    return limpio, errores


def validar_credenciales(data):
    """Login: solo exige texto no vacio (no revela reglas de formato)."""
    email, password = data.get("email"), data.get("password")
    errores = []
    if not isinstance(email, str) or not email.strip():
        errores.append({"field": "email", "message": "El email es obligatorio."})
    if not isinstance(password, str) or not password:
        errores.append({"field": "password", "message": "El password es obligatorio."})
    if errores:
        return None, errores
    return {"email": email.strip().lower(), "password": password}, []
