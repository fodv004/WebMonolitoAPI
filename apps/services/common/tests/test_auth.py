import base64
import json

import jwt
import pytest

from common import redis_keys
from common.auth import ADMIN_ROLE_ID, CLIENTE_ROLE_ID
from conftest import bearer


def _error(resp):
    return resp.get_json()["error"]


def test_sin_token_401(client, fake_redis):
    resp = client.post("/privado")
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "TOKEN_AUSENTE",
                               "message": "Envia el header 'Authorization: Bearer <token>'."}


@pytest.mark.parametrize("header", ["Basic abc", "Bearer", "Bearer a b", "token-suelto"])
def test_header_mal_formado_401(client, fake_redis, header):
    resp = client.post("/privado", headers={"Authorization": header})
    assert resp.status_code == 401 and _error(resp) == "TOKEN_AUSENTE"


def test_token_valido_200(client, fake_redis, make_token):
    resp = client.post("/privado", headers=bearer(make_token()))
    assert resp.status_code == 200 and resp.get_json() == {"user_id": 7}


def test_mal_firmado_401(client, fake_redis, make_token):
    token = make_token(secret="otro-secreto-distinto-con-mas-de-32-bytes-abcdefghij")
    resp = client.post("/privado", headers=bearer(token))
    assert resp.status_code == 401 and _error(resp) == "TOKEN_INVALIDO"


def test_algoritmo_distinto_401(client, fake_redis, make_token):
    # Mismo secreto pero HS512: solo se acepta HS256.
    resp = client.post("/privado", headers=bearer(make_token(algorithm="HS512")))
    assert resp.status_code == 401 and _error(resp) == "TOKEN_INVALIDO"


def test_algoritmo_none_401(client, fake_redis, make_token):
    payload = jwt.decode(make_token(), options={"verify_signature": False})

    def b64(datos):
        return base64.urlsafe_b64encode(json.dumps(datos).encode()).rstrip(b"=").decode()

    token = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(payload)}."
    resp = client.post("/privado", headers=bearer(token))
    assert resp.status_code == 401 and _error(resp) == "TOKEN_INVALIDO"


def test_expirado_401(client, fake_redis, make_token):
    resp = client.post("/privado", headers=bearer(make_token(exp_delta=-5)))
    assert resp.status_code == 401 and _error(resp) == "TOKEN_EXPIRADO"


@pytest.mark.parametrize("claim", ["sub", "user_id", "role_id", "jti", "iat", "exp", "type"])
def test_sin_claim_401(client, fake_redis, make_token, claim):
    resp = client.post("/privado", headers=bearer(make_token(omit=(claim,))))
    assert resp.status_code == 401 and _error(resp) == "TOKEN_INVALIDO"


def test_type_distinto_de_access_401(client, fake_redis, make_token):
    resp = client.post("/privado", headers=bearer(make_token(type="refresh")))
    assert resp.status_code == 401 and _error(resp) == "TOKEN_INVALIDO"


def test_revocado_401(client, fake_redis, make_token):
    token = make_token()
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    fake_redis.set(redis_keys.jwt_revoked(jti), "1", ex=60)
    resp = client.post("/privado", headers=bearer(token))
    assert resp.status_code == 401 and _error(resp) == "TOKEN_REVOCADO"


def test_redis_caido_503(client, redis_caido, make_token):
    resp = client.post("/privado", headers=bearer(make_token()))
    assert resp.status_code == 503 and _error(resp) == "REDIS_NO_DISPONIBLE"


def test_redis_caido_sin_token_sigue_siendo_401(client, redis_caido):
    assert client.post("/privado").status_code == 401


def test_rol_insuficiente_403(client, fake_redis, make_token):
    resp = client.delete("/admin", headers=bearer(make_token(role_id=CLIENTE_ROLE_ID)))
    assert resp.status_code == 403
    assert resp.get_json() == {"error": "ROL_INSUFICIENTE", "message": "No tienes permisos para esta operacion."}


def test_rol_admin_200(client, fake_redis, make_token):
    assert client.delete("/admin", headers=bearer(make_token(role_id=ADMIN_ROLE_ID))).status_code == 200


def test_require_role_sin_token_401(client, fake_redis):
    assert client.delete("/admin").status_code == 401


def test_require_role_revocado_es_401_no_403(client, fake_redis, make_token):
    token = make_token(role_id=CLIENTE_ROLE_ID)
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    fake_redis.set(redis_keys.jwt_revoked(jti), "1", ex=60)
    assert client.delete("/admin", headers=bearer(token)).status_code == 401


def test_clave_interna(client, fake_redis):
    assert client.get("/interno").status_code == 401
    assert client.get("/interno", headers={"X-Internal-Key": "incorrecta"}).status_code == 401
    assert client.get("/interno", headers={"X-Internal-Key": "clave-interna-de-pruebas"}).status_code == 200
