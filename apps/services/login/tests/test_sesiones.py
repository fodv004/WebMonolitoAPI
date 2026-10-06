"""login, refresh con rotacion y logout con revocacion (Redis = fakeredis)."""
import json
import time

import jwt
import pytest
from flask import Flask, jsonify

from common import redis_keys
from common.auth import require_auth
import routes
from config import Config
from security import token_digest

SIETE_DIAS = 7 * 24 * 3600


def _claims(token):
    return jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])


@pytest.fixture
def servicio_protegido():
    """Otro microservicio cualquiera que valida el JWT con common/auth.py."""
    app = Flask("otro-servicio")

    @app.post("/escribir")
    @require_auth
    def escribir():
        return jsonify({"ok": True})

    return app.test_client()


# ------------------------------------------------------------------ login
def test_login_emite_jwt_con_los_claims(login, fake_redis):
    resp = login()
    assert resp.status_code == 200
    datos = resp.get_json()["data"]
    assert datos["token_type"] == "Bearer" and datos["expires_in"] == 20 * 60
    assert datos["user"]["role_id"] == 2 and datos["user"]["role"] == "cliente"

    claims = _claims(datos["token"])
    assert set(claims) >= {"sub", "user_id", "role_id", "role", "jti", "iat", "exp", "type"}
    assert claims["sub"] == "31" and claims["user_id"] == 31
    assert claims["role_id"] == 2 and claims["role"] == "cliente" and claims["type"] == "access"
    assert claims["exp"] - claims["iat"] == 20 * 60
    assert jwt.get_unverified_header(datos["token"])["alg"] == "HS256"


def test_login_admin_lleva_role_id_1(login, fake_redis):
    claims = _claims(login("admin@correo.com").get_json()["data"]["token"])
    assert claims["role_id"] == 1 and claims["role"] == "admin"


def test_login_guarda_sesion_refresh_y_set_en_redis(login, fake_redis):
    datos = login().get_json()["data"]
    claims = _claims(datos["token"])

    sesion = json.loads(fake_redis.get(redis_keys.session(claims["sid"])))
    assert sesion["user_id"] == 31 and sesion["jti"] == claims["jti"]       # jti vigente en la sesion

    clave_refresh = redis_keys.refresh(token_digest(datos["refresh_token"]))
    assert json.loads(fake_redis.get(clave_refresh)) == {"session_id": claims["sid"], "user_id": 31}
    assert fake_redis.smembers(redis_keys.user_sessions(31)) == {claims["sid"]}

    for clave in (redis_keys.session(claims["sid"]), clave_refresh, redis_keys.user_sessions(31)):
        assert SIETE_DIAS - 5 <= fake_redis.ttl(clave) <= SIETE_DIAS
    # el refresh token nunca se guarda en claro
    assert not any(datos["refresh_token"] in clave for clave in fake_redis.scan_iter())


def test_login_credenciales_invalidas_401_sin_tocar_redis(login, fake_redis):
    assert login(password="incorrecta").status_code == 401
    assert login(email="nadie@correo.com").status_code == 401
    assert fake_redis.dbsize() == 0


def test_login_con_redis_caido_503(login, redis_caido):
    resp = login()
    assert resp.status_code == 503 and resp.get_json()["code"] == "REDIS_NO_DISPONIBLE"
    assert "token" not in json.dumps(resp.get_json())


# ------------------------------------------------------------------ refresh
def test_refresh_rota_el_refresh_token(client, login, fake_redis):
    inicial = login().get_json()["data"]
    time.sleep(1.1)  # para que iat/exp del token nuevo difieran

    resp = client.post("/refresh?format=json", json={"refresh_token": inicial["refresh_token"]})
    assert resp.status_code == 200 and resp.get_json()["code"] == "TOKEN_RENOVADO"
    nuevo = resp.get_json()["data"]
    assert nuevo["token"] != inicial["token"] and nuevo["refresh_token"] != inicial["refresh_token"]

    antes, despues = _claims(inicial["token"]), _claims(nuevo["token"])
    assert despues["sid"] == antes["sid"] and despues["jti"] != antes["jti"]
    assert despues["user_id"] == 31 and despues["type"] == "access"

    # la sesion apunta al jti nuevo y el refresh viejo ya no existe
    assert json.loads(fake_redis.get(redis_keys.session(antes["sid"])))["jti"] == despues["jti"]
    assert not fake_redis.exists(redis_keys.refresh(token_digest(inicial["refresh_token"])))
    assert fake_redis.exists(redis_keys.refresh(token_digest(nuevo["refresh_token"])))

    # el JWT anterior queda revocado: la sesion nunca tiene dos tokens vivos
    assert fake_redis.exists(redis_keys.jwt_revoked(antes["jti"]))
    assert not fake_redis.exists(redis_keys.jwt_revoked(despues["jti"]))

    # un refresh token es de un solo uso
    reuso = client.post("/refresh?format=json", json={"refresh_token": inicial["refresh_token"]})
    assert reuso.status_code == 401 and reuso.get_json()["code"] == "REFRESH_INVALIDO"
    # ...y el nuevo si funciona
    assert client.post("/refresh?format=json", json={"refresh_token": nuevo["refresh_token"]}).status_code == 200


def test_refresh_invalido_401(client, fake_redis):
    resp = client.post("/refresh?format=json", json={"refresh_token": "inventado"})
    assert resp.status_code == 401 and resp.get_json()["code"] == "REFRESH_INVALIDO"


def test_refresh_sin_token_400(client, fake_redis):
    assert client.post("/refresh?format=json", json={}).status_code == 400


def test_refresh_relee_el_rol_de_la_base(client, login, fake_redis, db):
    inicial = login().get_json()["data"]
    db.usuarios["ana@correo.com"][8] = 1          # la promovieron a admin
    nuevo = client.post("/refresh?format=json", json={"refresh_token": inicial["refresh_token"]}).get_json()["data"]
    assert _claims(nuevo["token"])["role_id"] == 1


def test_refresh_de_cuenta_desactivada_401_y_cierra_la_sesion(client, login, fake_redis, db):
    inicial = login().get_json()["data"]
    sid = _claims(inicial["token"])["sid"]
    db.usuarios["ana@correo.com"][6] = False      # activo = false

    resp = client.post("/refresh?format=json", json={"refresh_token": inicial["refresh_token"]})
    assert resp.status_code == 401
    assert not fake_redis.exists(redis_keys.session(sid))
    assert not fake_redis.exists(redis_keys.refresh(token_digest(inicial["refresh_token"])))


def test_refresh_con_redis_caido_503(client, redis_caido):
    resp = client.post("/refresh?format=json", json={"refresh_token": "x"})
    assert resp.status_code == 503 and resp.get_json()["code"] == "REDIS_NO_DISPONIBLE"


# ------------------------------------------------------------------ logout
def test_logout_revoca_el_jwt_y_borra_la_sesion(client, login, fake_redis, servicio_protegido):
    datos = login().get_json()["data"]
    claims = _claims(datos["token"])
    cabecera = {"Authorization": f"Bearer {datos['token']}"}
    assert servicio_protegido.post("/escribir", headers=cabecera).status_code == 200

    resp = client.post("/logout?format=json", headers=cabecera)
    assert resp.status_code == 200 and resp.get_json()["code"] == "LOGOUT_EXITOSO"

    clave = redis_keys.jwt_revoked(claims["jti"])
    assert fake_redis.exists(clave)
    restante = claims["exp"] - int(time.time())
    assert restante - 5 <= fake_redis.ttl(clave) <= restante          # TTL = vida restante del JWT
    assert not fake_redis.exists(redis_keys.session(claims["sid"]))
    assert not fake_redis.exists(redis_keys.refresh(token_digest(datos["refresh_token"])))
    assert fake_redis.smembers(redis_keys.user_sessions(31)) == set()

    # el token anterior ya no sirve en ningun microservicio, ni su refresh token
    rechazo = servicio_protegido.post("/escribir", headers=cabecera)
    assert rechazo.status_code == 401 and rechazo.get_json()["error"] == "TOKEN_REVOCADO"
    assert client.post("/refresh?format=json", json={"refresh_token": datos["refresh_token"]}).status_code == 401


def test_logout_solo_con_refresh_token_tambien_revoca(client, login, fake_redis, servicio_protegido):
    datos = login().get_json()["data"]
    assert client.post("/logout?format=json", json={"refresh_token": datos["refresh_token"]}).status_code == 200
    rechazo = servicio_protegido.post("/escribir", headers={"Authorization": f"Bearer {datos['token']}"})
    assert rechazo.status_code == 401


def test_logout_no_afecta_a_otras_sesiones(client, login, fake_redis, servicio_protegido):
    una, otra = login().get_json()["data"], login().get_json()["data"]
    client.post("/logout?format=json", headers={"Authorization": f"Bearer {una['token']}"})
    assert servicio_protegido.post("/escribir", headers={"Authorization": f"Bearer {otra['token']}"}).status_code == 200


def test_logout_sin_sesion_es_idempotente(client, fake_redis):
    resp = client.post("/logout?format=json")
    assert resp.status_code == 200 and resp.get_json()["data"] == {"authenticated": False}
    assert client.post("/logout?format=json", headers={"Authorization": "Bearer basura"}).status_code == 200


def test_logout_con_redis_caido_503(client, redis_caido):
    resp = client.post("/logout?format=json")
    assert resp.status_code == 503 and resp.get_json()["code"] == "REDIS_NO_DISPONIBLE"


# ------------------------------------------------------------------ modulo comun en login
def test_health_y_metrics(client, fake_redis):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"service": "login", "status": "ok", "db": "ok", "redis": "ok", "version": "2.0.0"}
    assert client.get("/metrics").get_json()["service"] == "login"


def test_health_con_redis_caido_503(client, redis_caido):
    resp = client.get("/health")
    assert resp.status_code == 503 and resp.get_json()["redis"] == "error"


# ------------------------------------------------------------------ confirmacion para users
INTERNA = {"X-Internal-Key": "clave-interna-de-pruebas"}


@pytest.fixture
def correos(monkeypatch):
    enviados = []
    monkeypatch.setattr(routes, "send_confirmation_email", lambda *args: enviados.append(args))
    return enviados


def test_confirmacion_interna_crea_token_y_envia_correo(client, db, correos):
    resp = client.post("/internal/confirmation", headers=INTERNA,
                       json={"user_id": 31, "email": "Nueva@Correo.com", "nombre": "Ana"})
    assert resp.status_code == 202 and resp.get_json()["code"] == "CORREO_ENVIADO"
    destinatario, nombre, token = correos[0]
    assert destinatario == "nueva@correo.com" and nombre == "Ana"
    assert db.tokens == [(31, token_digest(token))]         # en la base solo vive el hash


def test_confirmacion_interna_exige_la_clave(client, db, correos):
    cuerpo = {"user_id": 31, "email": "nueva@correo.com"}
    assert client.post("/internal/confirmation", json=cuerpo).status_code == 401
    assert client.post("/internal/confirmation", json=cuerpo, headers={"X-Internal-Key": "otra"}).status_code == 401
    assert correos == [] and db.tokens == []


def test_confirmacion_interna_valida_y_404(client, db, correos):
    assert client.post("/internal/confirmation?format=json", headers=INTERNA, json={"email": "a@b.c"}).status_code == 400
    resp = client.post("/internal/confirmation?format=json", headers=INTERNA,
                       json={"user_id": 999, "email": "a@b.c"})
    assert resp.status_code == 404 and correos == []


def test_confirmacion_interna_503_si_el_correo_no_sale(client, db, monkeypatch):
    def falla(*args):
        raise routes.MailError("smtp caido")

    monkeypatch.setattr(routes, "send_confirmation_email", falla)
    resp = client.post("/internal/confirmation?format=json", headers=INTERNA,
                       json={"user_id": 31, "email": "nueva@correo.com"})
    assert resp.status_code == 503 and resp.get_json()["code"] == "CORREO_NO_ENVIADO"
