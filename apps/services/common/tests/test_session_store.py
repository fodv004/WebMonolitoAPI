"""common/session_store.py: cierre de todas las sesiones de un usuario."""
import json
import time

import pytest
import redis

from common import redis_keys, session_store


def _sesion(fake_redis, user_id, sid, exp_delta=1200):
    jti, refresh_hash = f"jti-{sid}", f"hash-{sid}"
    fake_redis.set(redis_keys.session(sid), json.dumps(
        {"user_id": user_id, "jti": jti, "exp": int(time.time()) + exp_delta, "refresh_hash": refresh_hash}), ex=3600)
    fake_redis.set(redis_keys.refresh(refresh_hash), json.dumps({"session_id": sid, "user_id": user_id}), ex=3600)
    fake_redis.sadd(redis_keys.user_sessions(user_id), sid)
    return jti, refresh_hash


def test_cierra_todas_las_sesiones_del_usuario_y_solo_las_suyas(fake_redis):
    jti_a, hash_a = _sesion(fake_redis, 7, "a")
    jti_b, hash_b = _sesion(fake_redis, 7, "b")
    jti_otro, hash_otro = _sesion(fake_redis, 8, "c")

    assert session_store.revoke_user_sessions(7) == 2

    for jti in (jti_a, jti_b):
        clave = redis_keys.jwt_revoked(jti)
        assert fake_redis.exists(clave) and 1190 <= fake_redis.ttl(clave) <= 1200     # vida restante del JWT
    for sid, refresh_hash in (("a", hash_a), ("b", hash_b)):
        assert not fake_redis.exists(redis_keys.session(sid)) and not fake_redis.exists(redis_keys.refresh(refresh_hash))
    assert not fake_redis.exists(redis_keys.user_sessions(7))

    assert not fake_redis.exists(redis_keys.jwt_revoked(jti_otro))
    assert fake_redis.exists(redis_keys.session("c")) and fake_redis.exists(redis_keys.refresh(hash_otro))


def test_jwt_ya_expirado_no_se_agrega_a_la_lista(fake_redis):
    jti, _ = _sesion(fake_redis, 7, "vieja", exp_delta=-10)
    assert session_store.revoke_user_sessions(7) == 1
    assert not fake_redis.exists(redis_keys.jwt_revoked(jti)) and not fake_redis.exists(redis_keys.session("vieja"))


def test_sin_sesiones_y_sesion_ya_expirada(fake_redis):
    assert session_store.revoke_user_sessions(99) == 0
    fake_redis.sadd(redis_keys.user_sessions(7), "fantasma")          # el set apunta a una sesion que ya caduco
    assert session_store.revoke_user_sessions(7) == 1 and not fake_redis.exists(redis_keys.user_sessions(7))


def test_redis_caido_propaga_el_error(redis_caido):
    with pytest.raises(redis.RedisError):
        session_store.revoke_user_sessions(7)
