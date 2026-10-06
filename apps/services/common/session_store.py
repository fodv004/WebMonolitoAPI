"""
common/session_store.py
Cierre de TODAS las sesiones de un usuario desde cualquier servicio (las
sesiones las crea login; ver login/sessions.py para el formato).

Se usa cuando cambia algo que invalida lo que dice el JWT: contraseña,
rol o baja del usuario. Recorre user:sessions:<user_id> y, por cada sesion,
revoca su jti vigente (jwt:revoked:<jti>, TTL = vida restante) y borra la
sesion y su refresh token.

Aqui Redis es obligatorio: el redis.RedisError se propaga para que quien
llama responda 503 SIN aplicar el cambio (revocar antes del COMMIT).
"""
import json
import time

from common import redis_keys
from common.redis_client import get_client


def revoke_user_sessions(user_id):
    """Devuelve cuantas sesiones se cerraron."""
    cliente = get_client()
    clave_set = redis_keys.user_sessions(user_id)
    session_ids = cliente.smembers(clave_set)
    ahora = int(time.time())

    pipe = cliente.pipeline()
    for session_id in session_ids:
        crudo = cliente.get(redis_keys.session(session_id))
        if crudo:
            sesion = json.loads(crudo)
            restante = int(sesion.get("exp", 0)) - ahora
            if sesion.get("jti") and restante > 0:
                pipe.set(redis_keys.jwt_revoked(sesion["jti"]), "1", ex=restante)
            if sesion.get("refresh_hash"):
                pipe.delete(redis_keys.refresh(sesion["refresh_hash"]))
        pipe.delete(redis_keys.session(session_id))
    pipe.delete(clave_set)
    pipe.execute()
    return len(session_ids)
