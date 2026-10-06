"""health, metrics, cache de Redis, CORS, errores, config y filtro de logs."""
import logging

import pytest

from common import metrics, redis_client
from common.config import Settings
from common.logging_utils import SensitiveFilter, mask, redact
from conftest import bearer


# ------------------------------------------------------------------ health
def test_health_ok(client, fake_redis):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"service": "pruebas", "status": "ok", "db": "ok", "redis": "ok", "version": "9.9.9"}


def test_health_redis_caido_503(client, redis_caido):
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.get_json()["redis"] == "error" and resp.get_json()["status"] == "error"


def test_health_db_caida_503(client, fake_redis, db_estado):
    db_estado["ok"] = False
    resp = client.get("/health")
    assert resp.status_code == 503
    assert resp.get_json()["db"] == "error" and resp.get_json()["redis"] == "ok"


# ------------------------------------------------------------------ metrics
def test_metrics_cuenta_peticiones_y_errores(client, fake_redis, make_token):
    client.get("/publico")
    client.post("/privado")                                   # 401
    client.delete("/admin", headers=bearer(make_token()))     # 403
    client.get("/no-existe")                                  # 404
    datos = client.get("/metrics").get_json()
    assert datos["service"] == "pruebas"
    assert datos["requests_total"] == 4
    assert datos["errors_4xx"] == 3 and datos["errors_5xx"] == 0
    assert datos["responses_401"] == 1 and datos["responses_403"] == 1


# ------------------------------------------------------------------ cache
def test_cache_hit_y_miss(fake_redis):
    assert redis_client.cache_get("books:1") is None
    assert redis_client.cache_set("books:1", {"titulo": "Ñandú"}, 60)
    assert redis_client.cache_get("books:1") == {"titulo": "Ñandú"}
    assert 0 < fake_redis.ttl("books:1") <= 60
    datos = metrics.snapshot()
    assert datos["cache_misses"] == 1 and datos["cache_hits"] == 1


def test_cache_invalidate_usa_scan_y_respeta_el_patron(fake_redis, monkeypatch):
    for i in range(450):
        fake_redis.set(f"books:list:{i}", "[]")
    fake_redis.set("books:123", "{}")
    fake_redis.set("session:abc", "{}")
    monkeypatch.setattr(fake_redis, "keys", lambda *a, **k: pytest.fail("no se debe usar KEYS"))

    assert redis_client.cache_invalidate("books:list:*") == 450
    assert fake_redis.exists("books:123") and fake_redis.exists("session:abc")
    assert fake_redis.dbsize() == 2


def test_cache_con_redis_caido_no_lanza(redis_caido):
    assert redis_client.cache_get("books:1") is None
    assert redis_client.cache_set("books:1", {"a": 1}, 60) is False
    assert redis_client.cache_invalidate("books:*") == 0
    assert redis_client.ping() is False
    assert metrics.snapshot()["redis_errors"] == 4


def test_timeouts_de_2_segundos():
    redis_client.set_client(None)
    kwargs = redis_client.get_client().connection_pool.connection_kwargs
    redis_client.set_client(None)
    assert kwargs["socket_timeout"] == 2 and kwargs["socket_connect_timeout"] == 2


# ------------------------------------------------------------------ errores y CORS
def test_formato_uniforme_de_error(client, fake_redis):
    resp = client.get("/no-existe")
    assert resp.status_code == 404
    assert set(resp.get_json()) == {"error", "message"} and resp.get_json()["error"] == "HTTP_404"


def test_cors_solo_origenes_permitidos(client, fake_redis):
    permitido = client.get("/publico", headers={"Origin": "http://localhost:3000"})
    assert permitido.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    ajeno = client.get("/publico", headers={"Origin": "http://evil.example"})
    assert "Access-Control-Allow-Origin" not in ajeno.headers


# ------------------------------------------------------------------ config
def test_sin_jwt_secret_key_no_arranca(monkeypatch):
    for nombre in ("JWT_SECRET_KEY", "JWT_SECRET", "SECRET_KEY"):
        monkeypatch.delenv(nombre, raising=False)
    with pytest.raises(SystemExit) as error:
        Settings()
    assert "JWT_SECRET_KEY" in str(error.value)


def test_secret_key_solo_como_respaldo(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY")
    monkeypatch.setenv("SECRET_KEY", "respaldo")
    assert Settings().JWT_SECRET_KEY == "respaldo"
    monkeypatch.setenv("JWT_SECRET_KEY", "principal")
    assert Settings().JWT_SECRET_KEY == "principal"


def test_cors_nunca_comodin_y_algoritmo_fijo(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*, http://a.test ,http://b.test")
    assert Settings().CORS_ALLOWED_ORIGINS == ["http://a.test", "http://b.test"]
    monkeypatch.setenv("JWT_ALGORITHM", "none")
    with pytest.raises(SystemExit):
        Settings()


def test_database_url_desde_variables_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for nombre, valor in {"DB_HOST": "localhost", "DB_PORT": "5432", "DB_NAME": "library_db",
                          "DB_USER": "library_user", "DB_PASSWORD": "p@ss/word"}.items():
        monkeypatch.setenv(nombre, valor)
    assert Settings().DATABASE_URL == "postgresql://library_user:p%40ss%2Fword@localhost:5432/library_db"


# ------------------------------------------------------------------ filtro de logs
@pytest.mark.parametrize("linea, secreto", [
    ("Authorization: Bearer eyJhbGciOi.abc.def", "eyJhbGciOi.abc.def"),
    ('body={"email": "a@b.c", "password": "hunter2"}', "hunter2"),
    ("password_actual=vieja123&password_nueva=nueva456", "vieja123"),
    ("password_actual=vieja123&password_nueva=nueva456", "nueva456"),
    ("{'refresh_token': 'rt-secreto-1'}", "rt-secreto-1"),
    ("GET /confirm?token=tok-secreto-2 200", "tok-secreto-2"),
    ('{"tarjeta": "4111111111111111"}', "4111111111111111"),
    ("tarjeta=4111-1111-1111-1111", "4111-1111-1111-1111"),
    ("reintentando con Bearer abc.def.ghi", "abc.def.ghi"),
])
def test_redact_oculta_datos_sensibles(linea, secreto):
    limpio = redact(linea)
    assert secreto not in limpio and "***" in limpio


def test_redact_conserva_lo_no_sensible():
    assert redact('POST /login 200 12ms email="a@b.c"') == 'POST /login 200 12ms email="a@b.c"'


def test_mask_recursivo():
    datos = {"email": "a@b.c", "password": "x", "pago": {"tarjeta": "4111", "monto": 10},
             "items": [{"token": "t"}], "Authorization": "Bearer z"}
    assert mask(datos) == {"email": "a@b.c", "password": "***", "pago": {"tarjeta": "***", "monto": 10},
                           "items": [{"token": "***"}], "Authorization": "***"}


def test_filtro_en_el_logger(caplog):
    logger = logging.getLogger("prueba.filtro")
    caplog.handler.addFilter(SensitiveFilter())
    with caplog.at_level(logging.INFO):
        logger.info("login de %s con password=%s y header Authorization: Bearer %s", "ana", "hunter2", "aaa.bbb.ccc")
    assert "hunter2" not in caplog.text and "aaa.bbb.ccc" not in caplog.text
    assert "ana" in caplog.text


def test_log_http_registra_solo_la_ruta(client, fake_redis, caplog):
    with caplog.at_level(logging.INFO, logger="http"):
        client.get("/publico?token=secreto-en-query")
    lineas = [r.getMessage() for r in caplog.records if r.name == "http"]
    assert any(linea.startswith("GET /publico 200") for linea in lineas)
    assert not any("secreto-en-query" in linea for linea in lineas)
