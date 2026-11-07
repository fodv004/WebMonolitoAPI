"""Campo opcional `descripcion` de libros: lectura (JSON y XML) y escritura (POST, PUT, PATCH)."""
import xml.etree.ElementTree as ET

from api import rest
from conftest import ConexionNula

ISBN = "9780000000001"
TEXTO = "Guía práctica de arquitecturas nativas de la nube."


class ConexionQueAnota(ConexionNula):
    """Como ConexionNula, pero guarda cada (sql, parametros) que se ejecuta."""

    def __init__(self):
        self.sentencias = []

    def execute(self, sql, params=None):
        self.sentencias.append((" ".join(sql.split()), params))

    def fetchone(self):
        return (1,)       # _get_or_create_formato: el formato ya existe


def _con_descripcion(catalogo, monkeypatch):
    """El primer libro trae descripcion al final de la fila; el segundo no (fila previa a la columna)."""
    todos, uno = catalogo.todos, catalogo.uno
    monkeypatch.setattr(rest, "_fetch_todos_libros",
                        lambda: [fila + ((TEXTO,) if fila[0] == ISBN else ()) for fila in todos()])
    monkeypatch.setattr(rest, "_fetch_libro",
                        lambda isbn: (uno(isbn) + (TEXTO,)) if isbn == ISBN and uno(isbn) else uno(isbn))


def test_lista_json_incluye_descripcion(client, catalogo, fake_redis, monkeypatch):
    _con_descripcion(catalogo, monkeypatch)
    libros = {l["isbn"]: l for l in client.get("/books?format=json").get_json()}
    assert libros[ISBN]["descripcion"] == TEXTO
    assert libros["9780000000002"]["descripcion"] is None          # sin descripcion -> null
    assert {"isbn", "titulo", "precio", "stock", "portada"} <= set(libros[ISBN])   # lo demas no cambia


def test_detalle_json_y_xml_incluyen_descripcion(client, catalogo, fake_redis, monkeypatch):
    _con_descripcion(catalogo, monkeypatch)
    assert client.get(f"/books/{ISBN}?format=json").get_json()["descripcion"] == TEXTO
    raiz = ET.fromstring(client.get(f"/books/{ISBN}").data)
    assert raiz.findtext("description") == TEXTO and raiz.findtext("title") == "Cloud Native"
    lista = ET.fromstring(client.get("/books").data)
    assert lista.find(f"book[@isbn='{ISBN}']").findtext("description") == TEXTO


def test_filas_sin_descripcion_en_cache_siguen_funcionando(client, catalogo, fake_redis):
    # El FakeCatalogo original devuelve filas SIN descripcion (como la cache anterior a la migracion).
    assert client.get(f"/books/{ISBN}?format=json").get_json()["descripcion"] is None
    assert all(l["descripcion"] is None for l in client.get("/books?format=json").get_json())


def test_post_put_y_patch_guardan_la_descripcion(client, catalogo, fake_redis, token, monkeypatch):
    conexion = ConexionQueAnota()
    monkeypatch.setattr(rest, "get_connection", lambda: conexion)
    monkeypatch.setattr(rest, "_fetch_libro_card", lambda isbn: catalogo.todos()[0] + (TEXTO,))

    nuevo = {"isbn": "9780000000009", "titulo": "Nuevo", "anio": 2024, "precio": 100, "stock": 1,
             "formato": "Digital", "descripcion": TEXTO}
    resp = client.post("/books?format=json", json=nuevo, headers=token())
    assert resp.status_code == 201 and resp.get_json()["descripcion"] == TEXTO
    insert = next(p for sql, p in conexion.sentencias if sql.startswith("INSERT INTO libros"))
    assert insert[-1] == TEXTO

    for metodo in (client.put, client.patch):
        conexion.sentencias.clear()
        resp = metodo(f"/books/{ISBN}?format=json", json={"descripcion": "Otra"}, headers=token())
        assert resp.status_code == 200
        update = next((sql, p) for sql, p in conexion.sentencias if sql.startswith("UPDATE libros"))
        assert update == ("UPDATE libros SET descripcion = %s WHERE isbn = %s", ["Otra", ISBN])


def test_descripcion_debe_ser_texto(client, catalogo, fake_redis, token, monkeypatch):
    monkeypatch.setattr(rest, "get_connection", lambda: ConexionQueAnota())
    resp = client.patch(f"/books/{ISBN}?format=json", json={"descripcion": 123}, headers=token())
    assert resp.status_code == 400 and resp.get_json()["error"] == "VALIDACION"
