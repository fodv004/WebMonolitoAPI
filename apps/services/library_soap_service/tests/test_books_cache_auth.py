"""Cache de GET /books y GET /books/<isbn>, JWT + admin en las escrituras, /health y /metrics."""
import pytest

from api import rest
from conftest import ConexionNula

ISBN = "9780000000001"


def _metricas(client):
    return client.get("/metrics").get_json()


# ------------------------------------------------------------------ cache
def test_lista_se_cachea_60s_y_hay_cache_hit_en_metrics(client, catalogo, fake_redis):
    primera = client.get("/books?format=json")
    segunda = client.get("/books?format=json")
    assert primera.status_code == 200 and primera.get_json() == segunda.get_json()
    assert primera.get_json()[0]["precio"] == 499.90 and primera.get_json()[0]["isbn"] == ISBN
    assert catalogo.consultas == 1                      # la segunda no toco PostgreSQL

    assert 0 < fake_redis.ttl("books:list:format=json") <= 60
    datos = _metricas(client)
    assert datos["cache_misses"] == 1 and datos["cache_hits"] == 1


def test_lista_xml_y_json_usan_claves_distintas(client, catalogo, fake_redis):
    xml = client.get("/books")
    assert xml.status_code == 200 and b"<price>499.90</price>" in xml.data and b'model="IaaS"' in xml.data
    client.get("/books?format=JSON")
    assert set(fake_redis.scan_iter("books:list:*")) == {"books:list:format=xml", "books:list:format=json"}
    assert client.get("/books").data == xml.data        # servido desde cache, identico


def test_detalle_se_cachea_en_books_isbn(client, catalogo, fake_redis):
    primera = client.get(f"/books/{ISBN}?format=json")
    segunda = client.get(f"/books/{ISBN}?format=json")
    assert primera.status_code == 200 and primera.get_json() == segunda.get_json()
    assert primera.get_json()["portada"] == f"http://img.test/{ISBN}.png"
    assert catalogo.consultas == 1
    assert 0 < fake_redis.ttl(f"books:{ISBN}") <= 60
    # el mismo dato cacheado sirve la version xml
    assert b"<title>Cloud Native</title>" in client.get(f"/books/{ISBN}").data and catalogo.consultas == 1


def test_libro_inexistente_404_no_se_cachea(client, catalogo, fake_redis):
    assert client.get("/books/000?format=json").status_code == 404
    assert not fake_redis.exists("books:000")


def test_lectura_con_redis_caido_continua_con_postgresql(client, catalogo, redis_caido):
    assert client.get("/books?format=json").status_code == 200
    assert client.get(f"/books/{ISBN}?format=json").status_code == 200
    assert catalogo.consultas == 2
    assert _metricas(client)["redis_errors"] >= 2


# ------------------------------------------------------------------ escrituras
@pytest.mark.parametrize("metodo, ruta", [("post", "/books"), ("put", f"/books/{ISBN}"),
                                          ("patch", f"/books/{ISBN}"), ("delete", f"/books/{ISBN}")])
def test_escrituras_sin_token_401(client, fake_redis, metodo, ruta):
    resp = getattr(client, metodo)(ruta, json={"titulo": "x"})
    assert resp.status_code == 401 and resp.get_json()["error"] == "TOKEN_AUSENTE"


def test_escritura_con_rol_cliente_403(client, fake_redis, token):
    resp = client.patch(f"/books/{ISBN}", json={"stock": 9}, headers=token(role_id=2))
    assert resp.status_code == 403 and resp.get_json()["error"] == "ROL_INSUFICIENTE"


def test_escritura_con_redis_caido_503(client, redis_caido, token):
    resp = client.patch(f"/books/{ISBN}", json={"stock": 9}, headers=token())
    assert resp.status_code == 503 and resp.get_json()["error"] == "REDIS_NO_DISPONIBLE"


def test_escritura_de_admin_invalida_la_cache(client, catalogo, fake_redis, token, monkeypatch):
    monkeypatch.setattr(rest, "get_connection", lambda: ConexionNula())
    monkeypatch.setattr(rest, "_fetch_libro_card", lambda isbn: catalogo.todos()[0])

    client.get("/books?format=json")
    client.get("/books")
    client.get(f"/books/{ISBN}?format=json")
    client.get("/books/9780000000002?format=json")
    assert fake_redis.dbsize() == 4

    resp = client.patch(f"/books/{ISBN}?format=json", json={"stock": 9}, headers=token())
    assert resp.status_code == 200
    # se borran las listas y el libro modificado; el otro libro sigue cacheado
    assert set(fake_redis.scan_iter("*")) == {"books:9780000000002"}


# ------------------------------------------------------------------ modulo comun y SOAP
def test_health_y_metrics(client, fake_redis):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"service": "books", "status": "ok", "db": "ok", "redis": "ok", "version": "2.0.0"}
    assert _metricas(client)["service"] == "books"


def test_health_con_redis_caido_503(client, redis_caido):
    assert client.get("/health").status_code == 503


def test_soap_sigue_respondiendo(client, fake_redis):
    resp = client.post("/soap", data=b"esto no es xml", content_type="text/xml")
    assert resp.status_code == 400 and b"XML_INVALIDO" in resp.data
