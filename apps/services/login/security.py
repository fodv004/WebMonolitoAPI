"""
security.py
Hash de contrasenas y tokens de confirmacion.

* Contrasenas: bcrypt (12 rondas). Es el MISMO formato que usa el monolito
  Node (paquete `bcrypt`), asi una cuenta creada aqui puede iniciar sesion en
  el monolito y viceversa. Solo se guarda el hash; nunca la contrasena.
* Tokens: 256 bits aleatorios (secrets). En BD solo se guarda su SHA-256, de
  modo que una fuga de la tabla no permite confirmar cuentas.
* JWT de acceso: HS256 firmado con JWT_SECRET_KEY (PyJWT), 20 minutos.
  Claims sub, user_id, role_id, role, jti, iat, exp, type="access" (mas
  email y sid, el id de la sesion en Redis). Lo validan todos los
  microservicios con common/auth.py.
* Refresh token: 256 bits aleatorios; en Redis solo se guarda su SHA-256.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import Config
from common.auth import ROLES

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


def create_access_token(user_id, email, role_id, session_id):
    """Devuelve (token, jti, exp). `exp` es el instante de expiracion (epoch, segundos)."""
    ahora = datetime.now(timezone.utc)
    expira = ahora + timedelta(seconds=Config.JWT_EXPIRATION_SECONDS)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "role_id": role_id,
        "role": ROLES.get(role_id, "cliente"),
        "email": email,
        "sid": session_id,
        "jti": jti,
        "iat": ahora,
        "exp": expira,
        "type": "access",
    }
    token = jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)
    return token, jti, int(expira.timestamp())


def decode_own_token(token):
    """Payload de un JWT firmado por este servicio, aunque ya haya expirado
    (logout debe poder cerrar la sesion de un token vencido). None si no es valido."""
    try:
        return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM],
                          options={"verify_exp": False})
    except jwt.InvalidTokenError:
        return None
