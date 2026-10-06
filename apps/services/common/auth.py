"""
common/auth.py
Validacion del JWT de acceso que emite el microservicio de login.

Orden de las comprobaciones:
  1. Sin header "Authorization: Bearer <token>"            -> 401
  2. jwt.decode con algorithms=["HS256"] fijo (firma, exp)  -> 401
  3. Faltan claims (sub, user_id, role_id, jti, iat, exp,
     type="access")                                         -> 401
  4. Existe jwt:revoked:<jti> en Redis                      -> 401
     Redis caido (no se puede saber si esta revocado)       -> 503
  5. Rol insuficiente                                       -> 403

Decoradores: @require_auth, @require_role(ADMIN_ROLE_ID) (ya incluye la
autenticacion) y @require_internal_key (llamadas entre servicios).
El payload validado queda en flask.g.jwt_payload.
"""
import hmac
import logging
from functools import wraps

import jwt
import redis
from flask import g, request

from common import redis_client, redis_keys
from common.config import JWT_ALGORITHM, settings
from common.errors import error_response

log = logging.getLogger(__name__)

ADMIN_ROLE_ID = 1
CLIENTE_ROLE_ID = 2
ROLES = {ADMIN_ROLE_ID: "admin", CLIENTE_ROLE_ID: "cliente"}

CLAIMS_REQUERIDOS = ("sub", "user_id", "role_id", "jti", "iat", "exp", "type")
INTERNAL_KEY_HEADER = "X-Internal-Key"


def _token_del_header():
    partes = request.headers.get("Authorization", "").split()
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    return partes[1]


def _autenticar():
    """Devuelve (payload, None) o (None, respuesta_de_error)."""
    token = _token_del_header()
    if token is None:
        return None, error_response(401, "TOKEN_AUSENTE", "Envia el header 'Authorization: Bearer <token>'.")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM],
                             options={"require": ["exp", "iat"]})
    except jwt.ExpiredSignatureError:
        return None, error_response(401, "TOKEN_EXPIRADO", "El token expiro. Renuevalo o inicia sesion de nuevo.")
    except jwt.InvalidTokenError:
        return None, error_response(401, "TOKEN_INVALIDO", "El token no es valido.")

    if any(payload.get(claim) is None for claim in CLAIMS_REQUERIDOS) or payload["type"] != "access":
        return None, error_response(401, "TOKEN_INVALIDO", "El token no contiene los claims requeridos.")

    try:
        revocado = redis_client.get_client().exists(redis_keys.jwt_revoked(payload["jti"]))
    except redis.RedisError as e:
        log.error("No se pudo consultar la lista de revocacion: %s", e)
        return None, error_response(503, "REDIS_NO_DISPONIBLE",
                                    "No se puede verificar la sesion en este momento. Intenta mas tarde.")
    if revocado:
        return None, error_response(401, "TOKEN_REVOCADO", "La sesion fue cerrada. Inicia sesion de nuevo.")

    return payload, None


def require_auth(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        payload, error = _autenticar()
        if error is not None:
            return error
        g.jwt_payload = payload
        return vista(*args, **kwargs)

    return envoltura


def require_role(*roles_permitidos):
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            payload, error = _autenticar()
            if error is not None:
                return error
            if payload["role_id"] not in roles_permitidos:
                return error_response(403, "ROL_INSUFICIENTE", "No tienes permisos para esta operacion.")
            g.jwt_payload = payload
            return vista(*args, **kwargs)

        return envoltura

    return decorador


def require_internal_key(vista):
    """Llamadas entre microservicios: header X-Internal-Key == INTERNAL_API_KEY."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        recibida = request.headers.get(INTERNAL_KEY_HEADER, "")
        esperada = settings.INTERNAL_API_KEY
        if not esperada or not recibida or not hmac.compare_digest(recibida.encode(), esperada.encode()):
            return error_response(401, "CLAVE_INTERNA_INVALIDA", "Llamada interna no autorizada.")
        return vista(*args, **kwargs)

    return envoltura
