"""CRUD, relacion con libros (ISBN inexistente, books caido), cache e invalidacion, permisos."""
import pytest
import requests

from conftest import ALEPH, BORGES, CASA, CIEN, GABO, ISABEL
from services import books_client

NUEVO = {"nombre": "  Juan  ", "apellido": "Rulfo", "nacionalidad": "Mexicana", "fecha_nacimiento": "1917-05-16",
         "biografia": "Autor de Pedro Páramo."}


def _error(resp):
    return resp.get_json()["error"]


def _metricas(client):
    return client.get("/metrics").get_json()


# ------------------------------------------------------------------ lecturas publicas
def test_lista_publica_paginada_y_ordenada(client, fake_redis):
    resp = client.get("/authors?per_page=2")                 # sin token
    datos = resp.get_json()
    assert resp.status_code == 200
    assert [a["apellido"] for a in datos["items"]] == ["Allende", "Borges"]
    assert (datos["page"], datos["per_page"], datos["total"], datos["pages"]) == (1, 2, 3, 2)
    assert [a["id"] for a in client.get("/authors?per_page=2&page=2").get_json()["items"]] == [GABO]


def test_filtros_q_y_nacionalidad(client, fake_redis):
    ids = lambda q: [a["id"] for a in client.get(f"/authors?{q}").get_json()["items"]]   # noqa: E731
    assert ids("q=garc%C3%ADa") == [GABO]
    assert ids("q=jorge luis borges") == [BORGES]
    assert ids("nacionalidad=chilena") == [ISABEL]
    assert ids("q=o&nacionalidad=Argentina") == [BORGES]
    assert ids("q=nadie") == []


@pytest.mark.parametrize("query", ["page=0", "page=x", "per_page=0"])
def test_filtros_invalidos_400(client, fake_redis, query):
    resp = client.get(f"/authors?{query}")
    assert resp.status_code == 400 and _error(resp) == "VALIDACION"


def test_detalle_y_formato(client, fake_redis):
    resp = client.get(f"/authors/{GABO}")
    assert resp.status_code == 200
    assert resp.get_json() == {
        "id": GABO, "nombre": "Gabriel", "apellido": "García Márquez", "nombre_completo": "Gabriel García Márquez",
        "nacionalidad": "Colombiana", "fecha_nacimiento": "1927-03-06", "biografia": None, "total_libros": 1,
        "created_at": "2026-09-01T10:00:00", "updated_at": "2026-09-01T10:00:00",
    }
    resp = client.get("/authors/999")
    assert resp.status_code == 404 and _error(resp) == "AUTOR_NO_ENCONTRADO"


def test_libros_del_autor_enriquecidos_con_el_titulo(client, books, fake_redis):
    resp = client.get(f"/authors/{GABO}/books")
    assert resp.status_code == 200
    assert resp.get_json() == {"author_id": GABO, "enriquecido": True,
                               "books": [{"isbn": CIEN, "orden": 1, "titulo": "Cien años de soledad"}]}
    assert books.llamadas == [("titulos", None)]             # una sola llamada a books
    assert client.get("/authors/999/books").status_code == 404


def test_autor_sin_libros_no_llama_a_books(client, books, fake_redis):
    assert client.get(f"/authors/{BORGES}/books").get_json() == {"author_id": BORGES, "enriquecido": True, "books": []}
    assert books.llamadas == []


def test_si_books_falla_se_devuelven_solo_los_isbn_y_no_se_cachea(client, books, fake_redis):
    books.caido = True
    resp = client.get(f"/authors/{GABO}/books")
    assert resp.status_code == 200
    assert resp.get_json() == {"author_id": GABO, "enriquecido": False,
                               "books": [{"isbn": CIEN, "orden": 1, "titulo": None}]}
    assert not fake_redis.exists(f"authors:{GABO}:books")
    books.caido = False                                      # books vuelve: regresan los titulos de inmediato
    assert client.get(f"/authors/{GABO}/books").get_json()["books"][0]["titulo"] == "Cien años de soledad"


def test_autores_por_libro_en_su_orden(client, repo, fake_redis):
    repo.relaciones[(BORGES, CIEN)] = 2
    datos = client.get(f"/authors/by-book/{CIEN}").get_json()
    assert datos["isbn"] == CIEN
    assert [(a["id"], a["orden"]) for a in datos["authors"]] == [(GABO, 1), (BORGES, 2)]
    assert datos["authors"][0]["nombre_completo"] == "Gabriel García Márquez"
    assert client.get("/authors/by-book/9789999999999").get_json() == {"isbn": "9789999999999", "authors": []}
    assert client.get("/authors/by-book/isbn%20con%20espacios").status_code == 400


# ------------------------------------------------------------------ cache
def test_segunda_consulta_es_cache_hit_en_metrics(client, repo, fake_redis):
    primera = client.get("/authors?q=Borges")
    segunda = client.get("/authors?q=borges")                # mismos filtros normalizados -> misma clave
    assert primera.get_json() == segunda.get_json() and repo.lecturas == 1
    datos = _metricas(client)
    assert datos["cache_misses"] == 1 and datos["cache_hits"] == 1


def test_las_cuatro_claves_de_cache_con_ttl_de_60s(client, repo, fake_redis):
    for ruta in ("/authors", f"/authors/{GABO}", f"/authors/{GABO}/books", f"/authors/by-book/{CIEN}"):
        primera, lecturas = client.get(ruta).get_json(), repo.lecturas
        assert client.get(ruta).get_json() == primera and repo.lecturas == lecturas     # servida desde Redis
    claves = set(fake_redis.scan_iter("*"))
    assert claves == {"authors:list:page=1&per_page=20", f"authors:{GABO}", f"authors:{GABO}:books",
                      f"authors:by-book:{CIEN}"}
    assert all(0 < fake_redis.ttl(clave) <= 60 for clave in claves)


@pytest.mark.parametrize("escritura", ["crear", "put", "patch", "eliminar", "relacionar", "quitar"])
def test_cada_escritura_invalida_la_cache_con_scan(client, repo, fake_redis, admin, monkeypatch, escritura):
    for ruta in ("/authors", f"/authors/{GABO}", f"/authors/{GABO}/books", f"/authors/by-book/{CIEN}"):
        client.get(ruta)
    fake_redis.set("books:list:format=json", "[]")           # cache de OTRO servicio: no se toca
    assert fake_redis.dbsize() == 5
    monkeypatch.setattr(fake_redis, "keys", lambda *a, **k: pytest.fail("no se debe usar KEYS"))

    resp = {
        "crear": lambda: client.post("/authors", json=NUEVO, headers=admin),
        "put": lambda: client.put(f"/authors/{GABO}", json={"nombre": "Gabo"}, headers=admin),
        "patch": lambda: client.patch(f"/authors/{GABO}", json={"nacionalidad": "Mexicana"}, headers=admin),
        "eliminar": lambda: client.delete(f"/authors/{BORGES}", headers=admin),
        "relacionar": lambda: client.post(f"/authors/{BORGES}/books", json={"isbn": ALEPH}, headers=admin),
        "quitar": lambda: client.delete(f"/authors/{GABO}/books/{CIEN}", headers=admin),
    }[escritura]()
    assert resp.status_code in (200, 201)
    assert set(fake_redis.scan_iter("*")) == {"books:list:format=json"}


def test_tras_escribir_la_lectura_devuelve_el_dato_nuevo(client, fake_redis, admin):
    assert client.get(f"/authors/{GABO}").get_json()["nacionalidad"] == "Colombiana"
    client.patch(f"/authors/{GABO}", json={"nacionalidad": "Mexicana"}, headers=admin)
    assert client.get(f"/authors/{GABO}").get_json()["nacionalidad"] == "Mexicana"
    assert client.get("/authors?nacionalidad=mexicana").get_json()["total"] == 1


def test_una_escritura_rechazada_no_invalida_la_cache(client, fake_redis, admin, cliente):
    client.get("/authors")
    client.post("/authors", json=NUEVO, headers=cliente)                 # 403
    client.post("/authors", json={"nombre": ""}, headers=admin)         # 400
    assert fake_redis.exists("authors:list:page=1&per_page=20")


def test_lecturas_con_redis_caido_se_sirven_desde_postgresql(client, repo, redis_caido):
    for ruta in ("/authors", f"/authors/{GABO}", f"/authors/{GABO}/books", f"/authors/by-book/{CIEN}"):
        assert client.get(ruta).status_code == 200
        assert client.get(ruta).status_code == 200
    assert repo.lecturas >= 8 and _metricas(client)["redis_errors"] >= 8


# ------------------------------------------------------------------ permisos
ESCRITURAS = [("post", "/authors", NUEVO), ("put", f"/authors/{GABO}", {"nombre": "X"}),
              ("patch", f"/authors/{GABO}", {"nombre": "X"}), ("delete", f"/authors/{BORGES}", None),
              ("post", f"/authors/{BORGES}/books", {"isbn": ALEPH}), ("delete", f"/authors/{GABO}/books/{CIEN}", None)]


@pytest.mark.parametrize("metodo, ruta, cuerpo", ESCRITURAS)
def test_escrituras_sin_token_401(client, repo, fake_redis, metodo, ruta, cuerpo):
    resp = getattr(client, metodo)(ruta, json=cuerpo)
    assert resp.status_code == 401 and _error(resp) == "TOKEN_AUSENTE"
    assert len(repo.autores) == 3 and len(repo.relaciones) == 2


@pytest.mark.parametrize("metodo, ruta, cuerpo", ESCRITURAS)
def test_escrituras_con_rol_cliente_403(client, repo, fake_redis, cliente, metodo, ruta, cuerpo):
    resp = getattr(client, metodo)(ruta, json=cuerpo, headers=cliente)
    assert resp.status_code == 403 and _error(resp) == "ROL_INSUFICIENTE"
    assert len(repo.autores) == 3 and len(repo.relaciones) == 2


def test_escritura_con_redis_caido_503(client, repo, redis_caido, admin):
    # Sin Redis no se puede comprobar si el token fue revocado: no se acepta (fallo seguro).
    resp = client.post("/authors", json=NUEVO, headers=admin)
    assert resp.status_code == 503 and _error(resp) == "REDIS_NO_DISPONIBLE" and len(repo.autores) == 3


# ------------------------------------------------------------------ CRUD
def test_crear_autor(client, repo, fake_redis, admin):
    resp = client.post("/authors", json=NUEVO, headers=admin)
    assert resp.status_code == 201
    creado = resp.get_json()
    assert creado["nombre"] == "Juan" and creado["nombre_completo"] == "Juan Rulfo"
    assert creado["fecha_nacimiento"] == "1917-05-16" and creado["total_libros"] == 0
    assert client.get(f"/authors/{creado['id']}").get_json()["biografia"] == "Autor de Pedro Páramo."


def test_crear_solo_con_nombre(client, fake_redis, admin):
    creado = client.post("/authors", json={"nombre": "Homero"}, headers=admin).get_json()
    assert creado["apellido"] is None and creado["nombre_completo"] == "Homero" and creado["fecha_nacimiento"] is None


@pytest.mark.parametrize("cambio", [
    {"nombre": ""}, {"nombre": None}, {"nombre": 5}, {"nombre": "x" * 151}, {"nombre": "<b>Juan</b>"},
    {"nacionalidad": "x" * 81}, {"fecha_nacimiento": "16/05/1917"}, {"fecha_nacimiento": "1917-02-30"},
    {"fecha_nacimiento": "2999-01-01"}, {"fecha_nacimiento": 1917}, {"biografia": "x" * 5001},
])
def test_crear_con_datos_invalidos_400(client, repo, fake_redis, admin, cambio):
    resp = client.post("/authors", json={**NUEVO, **cambio}, headers=admin)
    assert resp.status_code == 400 and _error(resp) == "VALIDACION" and len(repo.autores) == 3


def test_cuerpo_que_no_es_json_400(client, fake_redis, admin):
    assert client.post("/authors", data="hola", headers=admin).status_code == 400
    assert client.patch(f"/authors/{GABO}", json=["lista"], headers=admin).status_code == 400


def test_put_reemplaza_y_patch_solo_lo_enviado(client, fake_redis, admin):
    parcial = client.patch(f"/authors/{GABO}", json={"biografia": "Nobel 1982"}, headers=admin).get_json()
    assert parcial["biografia"] == "Nobel 1982" and parcial["apellido"] == "García Márquez"
    assert parcial["updated_at"] != "2026-09-01T10:00:00"

    completo = client.put(f"/authors/{GABO}", json={"nombre": "Gabo"}, headers=admin).get_json()
    assert completo["nombre"] == "Gabo" and completo["apellido"] is None and completo["biografia"] is None
    assert completo["total_libros"] == 1                                  # las relaciones no se tocan

    assert client.put(f"/authors/{GABO}", json={"apellido": "Sin nombre"}, headers=admin).status_code == 400
    assert client.patch(f"/authors/{GABO}", json={}, headers=admin).status_code == 400
    assert client.patch("/authors/999", json={"nombre": "X"}, headers=admin).status_code == 404


def test_eliminar_autor_sin_libros(client, repo, fake_redis, admin):
    resp = client.delete(f"/authors/{BORGES}", headers=admin)
    assert resp.status_code == 200 and BORGES not in repo.autores
    assert client.delete(f"/authors/{BORGES}", headers=admin).status_code == 404


def test_eliminar_autor_con_libros_409_salvo_force(client, repo, fake_redis, admin):
    resp = client.delete(f"/authors/{GABO}", headers=admin)
    assert resp.status_code == 409 and _error(resp) == "AUTOR_CON_LIBROS" and "force=true" in resp.get_json()["message"]
    assert GABO in repo.autores and (GABO, CIEN) in repo.relaciones
    assert client.delete(f"/authors/{GABO}?force=false", headers=admin).status_code == 409

    forzado = client.delete(f"/authors/{GABO}?force=true", headers=admin)
    assert forzado.status_code == 200 and forzado.get_json()["relaciones_eliminadas"] == 1
    assert GABO not in repo.autores and (GABO, CIEN) not in repo.relaciones
    assert client.get(f"/authors/by-book/{CIEN}").get_json()["authors"] == []


# ------------------------------------------------------------------ relacion con libros
def test_relacionar_un_libro_existente(client, repo, books, fake_redis, admin):
    resp = client.post(f"/authors/{BORGES}/books", json={"isbn": ALEPH, "orden": 1}, headers=admin)
    assert resp.status_code == 201
    assert resp.get_json() == {"author_id": BORGES, "isbn": ALEPH, "orden": 1, "titulo": "El Aleph"}
    assert books.llamadas == [("libro", ALEPH)]                           # se valido contra books
    assert client.get(f"/authors/{BORGES}/books").get_json()["books"] == [{"isbn": ALEPH, "orden": 1, "titulo": "El Aleph"}]
    assert client.get(f"/authors/by-book/{ALEPH}").get_json()["authors"][0]["id"] == BORGES
    assert client.get(f"/authors/{BORGES}").get_json()["total_libros"] == 1


def test_sin_orden_se_asigna_el_siguiente_del_libro(client, repo, fake_redis, admin):
    resp = client.post(f"/authors/{BORGES}/books", json={"isbn": CIEN}, headers=admin)
    assert resp.status_code == 201 and resp.get_json()["orden"] == 2      # Gabo ya es el 1 de ese libro
    assert [a["id"] for a in client.get(f"/authors/by-book/{CIEN}").get_json()["authors"]] == [GABO, BORGES]


def test_relacionar_un_isbn_inexistente_404(client, repo, books, fake_redis, admin):
    resp = client.post(f"/authors/{BORGES}/books", json={"isbn": "9789999999999"}, headers=admin)
    assert resp.status_code == 404 and _error(resp) == "LIBRO_NO_ENCONTRADO"
    assert "9789999999999" in resp.get_json()["message"] and len(repo.relaciones) == 2


def test_relacionar_con_books_caido_503(client, repo, books, fake_redis, admin):
    books.caido = True
    resp = client.post(f"/authors/{BORGES}/books", json={"isbn": ALEPH}, headers=admin)
    assert resp.status_code == 503 and _error(resp) == "BOOKS_NO_DISPONIBLE" and len(repo.relaciones) == 2


def test_relacion_duplicada_409_y_autor_inexistente_404(client, repo, books, fake_redis, admin):
    resp = client.post(f"/authors/{GABO}/books", json={"isbn": CIEN}, headers=admin)
    assert resp.status_code == 409 and _error(resp) == "RELACION_DUPLICADA"
    resp = client.post("/authors/999/books", json={"isbn": CIEN}, headers=admin)
    assert resp.status_code == 404 and _error(resp) == "AUTOR_NO_ENCONTRADO"
    assert ("libro", CIEN) not in books.llamadas[1:]                       # sin autor no se molesta a books


@pytest.mark.parametrize("cuerpo", [{}, {"isbn": ""}, {"isbn": 9780000000003}, {"isbn": "x" * 14},
                                    {"isbn": ALEPH, "orden": 0}, {"isbn": ALEPH, "orden": "1"},
                                    {"isbn": ALEPH, "orden": True}])
def test_relacion_con_datos_invalidos_400(client, repo, books, fake_redis, admin, cuerpo):
    resp = client.post(f"/authors/{BORGES}/books", json=cuerpo, headers=admin)
    assert resp.status_code == 400 and _error(resp) == "VALIDACION"
    assert books.llamadas == [] and len(repo.relaciones) == 2


def test_quitar_relacion(client, repo, fake_redis, admin):
    resp = client.delete(f"/authors/{GABO}/books/{CIEN}", headers=admin)
    assert resp.status_code == 200 and (GABO, CIEN) not in repo.relaciones and GABO in repo.autores
    otra = client.delete(f"/authors/{GABO}/books/{CIEN}", headers=admin)
    assert otra.status_code == 404 and _error(otra) == "RELACION_NO_ENCONTRADA"


# ------------------------------------------------------------------ cliente HTTP de books
class _Respuesta:
    def __init__(self, status, cuerpo=None):
        self.status_code = status
        self._cuerpo = cuerpo

    def json(self):
        if self._cuerpo is None:
            raise ValueError("no es json")
        return self._cuerpo


def test_books_client_consulta_el_isbn_con_timeout_de_3s(monkeypatch):
    llamadas = []
    monkeypatch.setattr(books_client.requests, "get",
                        lambda url, **k: llamadas.append((url, k)) or _Respuesta(200, {"isbn": ALEPH, "titulo": "El Aleph"}))
    assert books_client.libro(ALEPH)["titulo"] == "El Aleph"
    url, kwargs = llamadas[0]
    assert url == f"http://127.0.0.1:5001/books/{ALEPH}" and kwargs["timeout"] == 3
    assert kwargs["params"] == {"format": "json"} and kwargs["headers"]["X-Internal-Key"] == "clave-interna-de-pruebas"


@pytest.mark.parametrize("respuesta, esperado", [
    (_Respuesta(404, {"error": "LIBRO_NO_ENCONTRADO"}), None),
    (_Respuesta(500), books_client.BooksNoDisponible),
    (_Respuesta(503, {"status": "error"}), books_client.BooksNoDisponible),
    (_Respuesta(200), books_client.BooksNoDisponible),
    (requests.ConnectionError("rechazada"), books_client.BooksNoDisponible),
    (requests.Timeout("lento"), books_client.BooksNoDisponible),
])
def test_books_client_distingue_inexistente_de_caido(monkeypatch, respuesta, esperado):
    def falso(url, **kwargs):
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(books_client.requests, "get", falso)
    if esperado is None:
        assert books_client.libro(ALEPH) is None
    else:
        with pytest.raises(esperado):
            books_client.libro(ALEPH)
        with pytest.raises(esperado):
            books_client.titulos()


def test_books_client_titulos(monkeypatch):
    monkeypatch.setattr(books_client.requests, "get", lambda url, **k: _Respuesta(
        200, [{"isbn": CIEN, "titulo": "Cien años de soledad"}, {"isbn": CASA, "titulo": "La casa"}]))
    assert books_client.titulos() == {CIEN: "Cien años de soledad", CASA: "La casa"}
