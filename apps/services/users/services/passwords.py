"""
services/passwords.py
Hash de contraseñas con EXACTAMENTE el mismo algoritmo que login
(apps/services/login/security.py): bcrypt, 12 rondas, sobre los primeros
72 bytes de la contraseña en UTF-8. Asi una contraseña puesta desde users
sirve para iniciar sesion en login (y en el monolito).

Solo se guarda el hash; la contraseña nunca se registra ni se devuelve.
"""
import bcrypt

BCRYPT_ROUNDS = 12
# bcrypt solo considera los primeros 72 bytes de la contrasena.
BCRYPT_MAX_BYTES = 72
PASSWORD_MIN = 8

# Valores de relleno de los seeds del monolito: no son hashes de nada.
HASHES_DE_EJEMPLO = ("hash_de_ejemplo", "CAMBIAR_POR_HASH_BCRYPT_REAL")


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8")[:BCRYPT_MAX_BYTES], bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password, stored_hash):
    """True solo si `stored_hash` es un hash bcrypt valido que corresponde a `password`."""
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:BCRYPT_MAX_BYTES], stored_hash.encode("ascii"))
    except (ValueError, TypeError, UnicodeError, AttributeError):
        return False


def es_hash_bcrypt(valor):
    return isinstance(valor, str) and valor.startswith(("$2a$", "$2b$", "$2y$")) and len(valor) == 60


def error_de_password(password, campo="El password"):
    """Mensaje si la contraseña no cumple las reglas de login; None si es valida."""
    if not isinstance(password, str) or not password:
        return f"{campo} es obligatorio."
    if len(password) < PASSWORD_MIN:
        return f"{campo} debe tener al menos {PASSWORD_MIN} caracteres."
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        return f"{campo} no puede exceder {BCRYPT_MAX_BYTES} bytes."
    return None
