"""
sessions.py
Sesiones y refresh tokens en Redis (PostgreSQL sigue siendo la fuente de
los usuarios). Claves y TTL en common/redis_keys.py:

  session:<session_id>     JSON {user_id, email, role_id, jti, exp, refresh_hash, created_at}  7 dias
  refresh:<sha256(token)>  JSON {session_id, user_id}                                          7 dias
  user:sessions:<user_id>  SET de session_id                                                   7 dias
  jwt:revoked:<jti>        "1"                                             vida restante del JWT

Aqui Redis es obligatorio: cualquier redis.RedisError se propaga y app.py
lo convierte en 503.
"""
import json
import time
import uuid

from config import Config  # primero: agrega apps/services al path (modulo `common`)
from common import redis_keys
from common.redis_client import get_client
from security import create_access_token, new_token, token_digest


def _guardar(pipe, session_id, user_id, email, role_id, created_at=None):
    """Emite access + refresh token nuevos y los encola en `pipe`. Devuelve los datos para el cliente."""
    token, jti, exp = create_access_token(user_id, email, role_id, session_id)
    refresh_token = new_token()
    refresh_hash = token_digest(refresh_token)

    sesion = {"user_id": user_id, "email": email, "role_id": role_id, "jti": jti, "exp": exp,
              "refresh_hash": refresh_hash, "created_at": created_at or int(time.time())}
    pipe.set(redis_keys.session(session_id), json.dumps(sesion), ex=redis_keys.SESSION_TTL)
    pipe.set(redis_keys.refresh(refresh_hash), json.dumps({"session_id": session_id, "user_id": user_id}),
             ex=redis_keys.SESSION_TTL)
    pipe.sadd(redis_keys.user_sessions(user_id), session_id)
    pipe.expire(redis_keys.user_sessions(user_id), redis_keys.SESSION_TTL)

    return {
        "token": token,
        "token_type": "Bearer",
        "expires_in": Config.JWT_EXPIRATION_SECONDS,
        "refresh_token": refresh_token,
        "refresh_expires_in": redis_keys.SESSION_TTL,
    }


def crear(user_id, email, role_id):
    pipe = get_client().pipeline()
    datos = _guardar(pipe, uuid.uuid4().hex, user_id, email, role_id)
    pipe.execute()
    return datos


def buscar_refresh(refresh_token):
    """{session_id, user_id} del refresh token, o None si no existe o ya expiro."""
    crudo = get_client().get(redis_keys.refresh(token_digest(refresh_token)))
    return json.loads(crudo) if crudo else None


def rotar(refresh_token, email, role_id):
    """Consume el refresh token (un solo uso) y emite access + refresh nuevos para
    la misma sesion. None si otro proceso ya lo uso o la sesion ya no existe."""
    cliente = get_client()
    crudo = cliente.getdel(redis_keys.refresh(token_digest(refresh_token)))
    if not crudo:
        return None
    referencia = json.loads(crudo)
    session_id, user_id = referencia["session_id"], referencia["user_id"]

    crudo_sesion = cliente.get(redis_keys.session(session_id))
    if not crudo_sesion:
        return None
    anterior = json.loads(crudo_sesion)

    pipe = cliente.pipeline()
    # El JWT anterior deja de servir al renovarlo: asi la sesion nunca tiene mas de un
    # token vivo y cerrar sus sesiones (common/session_store.py) los revoca todos.
    restante = int(anterior.get("exp", 0)) - int(time.time())
    if anterior.get("jti") and restante > 0:
        pipe.set(redis_keys.jwt_revoked(anterior["jti"]), "1", ex=restante)
    datos = _guardar(pipe, session_id, user_id, email, role_id, anterior.get("created_at"))
    pipe.execute()
    return datos


def revocar_jti(jti, exp):
    """Agrega el JWT a la lista de revocacion hasta que expire por si solo."""
    restante = int(exp) - int(time.time())
    if jti and restante > 0:
        get_client().set(redis_keys.jwt_revoked(jti), "1", ex=restante)


def cerrar(session_id, user_id=None):
    """Borra la sesion y su refresh token, y revoca el JWT vigente de la sesion."""
    if not session_id:
        return False
    cliente = get_client()
    crudo = cliente.get(redis_keys.session(session_id))
    sesion = json.loads(crudo) if crudo else {}
    user_id = sesion.get("user_id", user_id)

    if sesion.get("jti"):
        revocar_jti(sesion["jti"], sesion.get("exp", 0))
    pipe = cliente.pipeline()
    if sesion.get("refresh_hash"):
        pipe.delete(redis_keys.refresh(sesion["refresh_hash"]))
    pipe.delete(redis_keys.session(session_id))
    if user_id is not None:
        pipe.srem(redis_keys.user_sessions(user_id), session_id)
    pipe.execute()
    return bool(crudo)
