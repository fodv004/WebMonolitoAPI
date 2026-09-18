"""
security.py
Hash de contrasenas y tokens de confirmacion.

* Contrasenas: bcrypt (12 rondas). Es el MISMO formato que usa el monolito
  Node (paquete `bcrypt`), asi una cuenta creada aqui puede iniciar sesion en
  el monolito y viceversa. Solo se guarda el hash; nunca la contrasena.
* Tokens: 256 bits aleatorios (secrets). En BD solo se guarda su SHA-256, de
  modo que una fuga de la tabla no permite confirmar cuentas.
"""
import hashlib
import secrets

import bcrypt

BCRYPT_ROUNDS = 12
# bcrypt solo considera los primeros 72 bytes de la contrasena.
BCRYPT_MAX_BYTES = 72

# Hash de una contrasena inventada: se verifica contra el cuando el correo no
# existe, para que "correo desconocido" y "contrasena incorrecta" tarden igual.
_HASH_SENUELO = bcrypt.hashpw(b"senuelo-sin-uso", bcrypt.gensalt(BCRYPT_ROUNDS))


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8")[:BCRYPT_MAX_BYTES], bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password, stored_hash):
    """True solo si `stored_hash` es un hash bcrypt valido que corresponde a `password`.

    Un valor que no sea bcrypt (p. ej. las contrasenas de demo en texto plano
    del seed del monolito) nunca se acepta aqui.
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:BCRYPT_MAX_BYTES], stored_hash.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        return False


def burn_password_check(password):
    """Gasta el mismo tiempo que una verificacion real (usuario inexistente)."""
    bcrypt.checkpw(password.encode("utf-8")[:BCRYPT_MAX_BYTES], _HASH_SENUELO)


def new_token():
    return secrets.token_urlsafe(32)


def token_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
