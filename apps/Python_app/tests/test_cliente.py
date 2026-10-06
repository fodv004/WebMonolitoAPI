"""
Pruebas de la app de escritorio que no necesitan ventana: configuracion,
cliente HTTP base, sesion y revision de /health. Ejecutar desde
apps/Python_app:

    pytest
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # apps/Python_app

import pytest  # noqa: E402
import requests  # noqa: E402

from api import health  # noqa: E402
from api.auth_client import AuthClient  # noqa: E402
from api.books_client import BooksClient  # noqa: E402
from api.http_base import ApiError  # noqa: E402
from config import settings  # noqa: E402
from config.settings import AppConfig  # noqa: E402
from session import Session  # noqa: E402


def _respuesta(status, cuerpo=None):
    resp = requests.Response()
    resp.status_code = status
    resp.reason = "PRUEBA"
    resp._content = json.dumps(cuerpo if cuerpo is not None else {}).encode()
    resp.headers["Content-Type"] = "application/json"
    return resp


class Servidor:
    """Sustituye requests.Session.send: responde con lo que se le encole y guarda lo recibido."""

    def __init__(self, monkeypatch):
        self.recibidas = []
        self.cola = []
        monkeypatch.setattr(requests.Session, "send", self._send)

    def _send(self, prep, **kwargs):
        self.recibidas.append((prep, kwargs))
        siguiente = self.cola.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


@pytest.fixture
def servidor(monkeypatch):
    return Servidor(monkeypatch)


@pytest.fixture
def config():
    return AppConfig({"host": "34.51.58.130"})


def _sesion_iniciada(config):
    sesion = Session()
    sesion.conectar_refresh(AuthClient(config).refresh)
    sesion.iniciar({"token": "jwt-viejo", "refresh_token": "rt-viejo", "expires_in": 1200,
                    "user": {"email": "ana@correo.com", "role_id": 2}})
    return sesion


# ------------------------------------------------------------------ configuracion
def test_http_por_defecto_y_urls():
    config = AppConfig()
    assert config["protocolo"] == "http" and config["host"] == "127.0.0.1"
    assert config.base_url("login") == "http://127.0.0.1:5000"
    assert config.base_url("pagos") == "http://127.0.0.1:5005"
    assert config["semaforo_intervalo_s"] == 10 and settings.TIMEOUT_HTTP == 5


def test_https_usa_api_servicio_y_verify():
    config = AppConfig({"host": "34.51.58.130", "protocolo": "https"})
    assert config.base_url("books") == "https://34.51.58.130/api/books"
    assert config.verify() is True
    config.aplicar({**config.datos, "certificado": "C:/certs/vm.crt"})
    assert config.verify() == "C:/certs/vm.crt"
    config.aplicar({**config.datos, "verificar_certificado": False})
    assert config.verify() is False


def test_validacion_de_la_configuracion():
    assert AppConfig({"host": " http://10.0.0.5:5000/ "})["host"] == "10.0.0.5"
    for datos in ({"host": ""}, {"host": "a b"}, {"host": "x", "protocolo": "ftp"},
                  {"host": "x", "puertos": {"login": "abc"}}, {"host": "x", "puertos": {"login": 70000}},
                  {"host": "x", "semaforo_intervalo_s": 0}, {"host": "x", "semaforo_timeout_s": "nunca"}):
        with pytest.raises(ValueError):
            AppConfig(datos)


def test_guardar_y_cargar_sin_tokens(tmp_path):
    archivo = tmp_path / "config.json"
    config = AppConfig({"host": "10.0.0.5", "protocolo": "https", "puertos": {"users": 6002}})
    config.datos["token"] = "no-debe-guardarse"
    config.guardar(archivo)

    guardado = json.loads(archivo.read_text(encoding="utf-8"))
    assert set(guardado) == set(settings.VALORES_POR_DEFECTO) and "token" not in archivo.read_text(encoding="utf-8")
    cargada = AppConfig.cargar(archivo)
    assert cargada["host"] == "10.0.0.5" and cargada["puertos"]["users"] == 6002 and cargada["puertos"]["login"] == 5000


def test_config_corrupta_vuelve_a_los_valores_por_defecto(tmp_path):
    archivo = tmp_path / "config.json"
    archivo.write_text("{esto no es json", encoding="utf-8")
    assert AppConfig.cargar(archivo).datos == settings.VALORES_POR_DEFECTO


def test_primera_ejecucion_hereda_la_ip_de_local_storage(tmp_path, monkeypatch):
    anterior = tmp_path / "local_storage.json"
    anterior.write_text(json.dumps({"login_base_url": "http://34.51.58.130:5000"}), encoding="utf-8")
    monkeypatch.setattr(settings, "_ARCHIVO_ANTERIOR", anterior)
    assert AppConfig.cargar(tmp_path / "config.json")["host"] == "34.51.58.130"


# ------------------------------------------------------------------ cliente HTTP
def test_authorization_automatico_timeout_y_verify(servidor, config):
    books = BooksClient(config, _sesion_iniciada(config))
    servidor.cola.append(_respuesta(200, []))
    assert books.list_books() == []

    prep, kwargs = servidor.recibidas[0]
    assert prep.url == "http://34.51.58.130:5001/books?format=json"
    assert prep.headers["Authorization"] == "Bearer jwt-viejo"
    assert kwargs["timeout"] == 5 and kwargs["verify"] is True


def test_login_va_sin_authorization_y_su_401_no_dispara_refresh(servidor, config):
    servidor.cola.append(_respuesta(401, {"status": "error", "code": "CREDENCIALES_INVALIDAS",
                                           "message": "Email o contraseña incorrectos."}))
    with pytest.raises(ApiError) as error:
        AuthClient(config).login("ana@correo.com", "mala")
    assert "Authorization" not in servidor.recibidas[0][0].headers
    assert error.value.mensaje == "Email o contraseña incorrectos." and not error.value.es_sesion_invalida
    assert len(servidor.recibidas) == 1


def test_401_renueva_el_token_una_vez_y_repite_la_peticion(servidor, config):
    sesion = _sesion_iniciada(config)
    books = BooksClient(config, sesion)
    servidor.cola += [
        _respuesta(401, {"error": "TOKEN_EXPIRADO", "message": "El token expiro."}),
        _respuesta(200, {"data": {"token": "jwt-nuevo", "refresh_token": "rt-nuevo", "expires_in": 1200}}),
        _respuesta(200, {"isbn": "1"}),
    ]
    assert books.patch_book("1", stock=3) == {"isbn": "1"}

    rutas = [prep.url.split("?")[0].rsplit("/", 1)[-1] for prep, _ in servidor.recibidas]
    assert rutas == ["1", "refresh", "1"]
    assert json.loads(servidor.recibidas[1][0].body) == {"refresh_token": "rt-viejo"}
    assert servidor.recibidas[2][0].headers["Authorization"] == "Bearer jwt-nuevo"
    assert sesion.token == "jwt-nuevo" and sesion.refresh_token == "rt-nuevo"
    assert sesion.usuario["email"] == "ana@correo.com"          # el refresh no borra al usuario


def test_401_sin_poder_renovar_marca_sesion_invalida_y_limpia(servidor, config):
    sesion = _sesion_iniciada(config)
    servidor.cola += [
        _respuesta(401, {"error": "TOKEN_REVOCADO", "message": "La sesion fue cerrada."}),
        _respuesta(401, {"status": "error", "code": "REFRESH_INVALIDO", "message": "El refresh token no es válido."}),
    ]
    with pytest.raises(ApiError) as error:
        BooksClient(config, sesion).delete_book("1")
    assert error.value.status == 401 and error.value.es_sesion_invalida
    assert "Inicia sesión de nuevo" in error.value.mensaje
    assert len(servidor.recibidas) == 2 and not sesion.activa     # un solo intento de refresh


def test_segundo_401_tras_renovar_no_entra_en_bucle(servidor, config):
    sesion = _sesion_iniciada(config)
    servidor.cola += [
        _respuesta(401, {"error": "TOKEN_EXPIRADO", "message": "x"}),
        _respuesta(200, {"data": {"token": "jwt-nuevo", "refresh_token": "rt-nuevo", "expires_in": 1200}}),
        _respuesta(401, {"error": "TOKEN_INVALIDO", "message": "x"}),
    ]
    with pytest.raises(ApiError) as error:
        BooksClient(config, sesion).delete_book("1")
    assert error.value.es_sesion_invalida and len(servidor.recibidas) == 3


def test_renovar_no_repite_el_refresh_si_otro_hilo_ya_lo_hizo(servidor, config):
    sesion = _sesion_iniciada(config)
    sesion.token = "jwt-que-ya-renovo-otro-hilo"
    assert sesion.renovar("jwt-viejo") is True and servidor.recibidas == []


def test_fallo_de_red_al_renovar_conserva_la_sesion(servidor, config):
    sesion = _sesion_iniciada(config)
    servidor.cola.append(requests.ConnectionError("sin red"))
    assert sesion.renovar("jwt-viejo") is False and sesion.activa


@pytest.mark.parametrize("status, cuerpo, esperado", [
    (403, {"error": "ROL_INSUFICIENTE", "message": "No tienes permisos para esta operacion."}, "No tienes permisos"),
    (409, {"error": "ISBN_DUPLICADO", "mensaje": "Ya existe un libro con ISBN 1."}, "Conflicto"),
    (503, {"error": "REDIS_NO_DISPONIBLE", "message": "Intenta mas tarde."}, "no está disponible"),
])
def test_mensajes_claros_y_403_no_cierra_la_sesion(servidor, config, status, cuerpo, esperado):
    sesion = _sesion_iniciada(config)
    servidor.cola.append(_respuesta(status, cuerpo))
    with pytest.raises(ApiError) as error:
        BooksClient(config, sesion).create_book(isbn="1")
    assert esperado in error.value.mensaje and error.value.status == status
    assert not error.value.es_sesion_invalida and sesion.activa and len(servidor.recibidas) == 1


def test_servicio_caido_da_un_mensaje_claro(servidor, config):
    servidor.cola.append(requests.ConnectionError("conexion rechazada"))
    with pytest.raises(ApiError) as error:
        BooksClient(config, Session()).list_books()
    assert "No se pudo conectar" in error.value.mensaje and error.value.status is None


def test_logout_envia_el_token_y_el_refresh(servidor, config):
    servidor.cola.append(_respuesta(200, {"data": {"authenticated": False}}))
    AuthClient(config).logout("jwt-viejo", "rt-viejo")
    prep, _ = servidor.recibidas[0]
    assert prep.headers["Authorization"] == "Bearer jwt-viejo"
    assert json.loads(prep.body) == {"refresh_token": "rt-viejo"}


def test_el_log_de_consola_no_muestra_tokens_ni_passwords(servidor, config, capsys):
    servidor.cola.append(_respuesta(200, {"data": {"token": "JWT-SECRETO", "refresh_token": "RT-SECRETO",
                                                  "user": {"email": "ana@correo.com"}}}))
    AuthClient(config).login("ana@correo.com", "PASSWORD-SECRETO")
    servidor.cola.append(_respuesta(200, []))
    BooksClient(config, _sesion_iniciada(config)).list_books()

    consola = capsys.readouterr().out
    for secreto in ("PASSWORD-SECRETO", "JWT-SECRETO", "RT-SECRETO", "jwt-viejo"):
        assert secreto not in consola
    assert "POST http://34.51.58.130:5000/login" in consola and "ana@correo.com" in consola
    assert "Authorization: Bearer ********" in consola


def test_renovacion_proactiva_a_los_17_minutos(config):
    assert _sesion_iniciada(config).segundos_para_renovar() == 17 * 60


# ------------------------------------------------------------------ semaforo
class _Health:
    def __init__(self, monkeypatch, respuesta):
        self.llamadas = []
        monkeypatch.setattr(requests, "get", self._get)
        self.respuesta = respuesta

    def _get(self, url, **kwargs):
        self.llamadas.append((url, kwargs))
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta


def test_semaforo_verde_solo_con_200_y_status_ok(monkeypatch, config):
    falso = _Health(monkeypatch, _respuesta(200, {"service": "users", "status": "ok", "db": "ok", "redis": "ok"}))
    r = health.revisar(config, "users", 3)
    assert r["ok"] and r["db"] == "ok" and r["redis"] == "ok" and r["ms"] is not None and r["hora"] is not None
    assert falso.llamadas[0][0] == "http://34.51.58.130:5002/health" and falso.llamadas[0][1]["timeout"] == 3


@pytest.mark.parametrize("respuesta", [
    _respuesta(503, {"service": "users", "status": "error", "db": "ok", "redis": "error"}),
    _respuesta(200, {"status": "error"}),
    _respuesta(200, {"otra": "cosa"}),
    requests.ConnectionError("rechazada"),
    requests.Timeout("lento"),
])
def test_semaforo_rojo_en_cualquier_otro_caso(monkeypatch, config, respuesta):
    _Health(monkeypatch, respuesta)
    assert health.revisar(config, "users", 3)["ok"] is False


# ------------------------------------------------------------------ cliente de users
def test_users_list_envia_filtros_y_paginacion(servidor, config):
    from api.users_client import UsersClient

    users = UsersClient(config, _sesion_iniciada(config))
    servidor.cola += [_respuesta(200, {"items": [], "page": 2, "per_page": 15, "total": 0, "pages": 0})] * 2
    users.list(q="ana", role_id=2, activo=False, page=2, per_page=15)
    users.list()

    con_filtros, sin_filtros = (prep.url for prep, _ in servidor.recibidas)
    assert con_filtros.startswith("http://34.51.58.130:5002/users?")
    for parte in ("q=ana", "role_id=2", "activo=false", "page=2", "per_page=15", "format=json"):
        assert parte in con_filtros
    assert "q=" not in sin_filtros and "role_id" not in sin_filtros and "activo" not in sin_filtros


def test_users_rutas_y_cuerpos(servidor, config):
    from api.users_client import UsersClient

    users = UsersClient(config, _sesion_iniciada(config))
    servidor.cola += [_respuesta(200, {})] * 9
    users.me()
    users.create(nombre="Ana", email="ana@correo.com", password="ClaveNueva123", role_id=2)
    users.update(31, nombre="Ana")
    users.patch(31, activo=True)
    users.deactivate(31)
    users.change_password(31, "Nueva12345", "Actual12345")
    users.change_password(32, "Nueva12345")
    users.change_email(31, "nueva@correo.com")
    users.change_role(31, 1)

    vistas = [(prep.method, prep.url.split("?")[0].split(":5002")[1], json.loads(prep.body) if prep.body else None)
              for prep, _ in servidor.recibidas]
    assert vistas == [
        ("GET", "/users/me", None),
        ("POST", "/users", {"nombre": "Ana", "email": "ana@correo.com", "password": "ClaveNueva123", "role_id": 2}),
        ("PUT", "/users/31", {"nombre": "Ana"}),
        ("PATCH", "/users/31", {"activo": True}),
        ("DELETE", "/users/31", None),
        ("PATCH", "/users/31/password", {"password_nueva": "Nueva12345", "password_actual": "Actual12345"}),
        ("PATCH", "/users/32/password", {"password_nueva": "Nueva12345"}),      # el admin no envia la actual
        ("PATCH", "/users/31/email", {"email": "nueva@correo.com"}),
        ("PATCH", "/users/31/role", {"role_id": 1}),
    ]
    assert all(prep.headers["Authorization"] == "Bearer jwt-viejo" for prep, _ in servidor.recibidas)


def test_el_log_oculta_las_contraseñas_al_cambiarlas(servidor, config, capsys):
    from api.users_client import UsersClient

    servidor.cola.append(_respuesta(200, {"status": "ok"}))
    UsersClient(config, _sesion_iniciada(config)).change_password(31, "NUEVA-SECRETA-1", "ACTUAL-SECRETA-1")
    consola = capsys.readouterr().out
    assert "NUEVA-SECRETA-1" not in consola and "ACTUAL-SECRETA-1" not in consola
    assert "PATCH http://34.51.58.130:5002/users/31/password" in consola


# ------------------------------------------------------------------ cliente de authors
def test_authors_rutas_filtros_y_cuerpos(servidor, config):
    from api.authors_client import AuthorsClient

    authors = AuthorsClient(config, _sesion_iniciada(config))
    servidor.cola += [_respuesta(200, {})] * 11
    authors.list(q="borges", nacionalidad="Argentina", page=2, per_page=15)
    authors.list()
    authors.get(3)
    authors.books(3)
    authors.by_book("978-0000000001")
    authors.create(nombre="Juan", apellido="Rulfo")
    authors.update(3, nombre="Jorge Luis")
    authors.delete(3)
    authors.delete(3, force=True)
    authors.add_book(3, "9780000000003")
    authors.add_book(3, "9780000000003", orden=2)

    vistas = [(prep.method, prep.url.split(":5003")[1], json.loads(prep.body) if prep.body else None)
              for prep, _ in servidor.recibidas]
    lista = vistas[0][1]
    assert lista.startswith("/authors?") and all(p in lista for p in ("q=borges", "nacionalidad=Argentina", "page=2", "per_page=15"))
    assert "q=" not in vistas[1][1] and "nacionalidad" not in vistas[1][1]
    assert vistas[2:] == [
        ("GET", "/authors/3?format=json", None),
        ("GET", "/authors/3/books?format=json", None),
        ("GET", "/authors/by-book/978-0000000001?format=json", None),
        ("POST", "/authors?format=json", {"nombre": "Juan", "apellido": "Rulfo"}),
        ("PUT", "/authors/3?format=json", {"nombre": "Jorge Luis"}),
        ("DELETE", "/authors/3?format=json", None),
        ("DELETE", "/authors/3?format=json&force=true", None),
        ("POST", "/authors/3/books?format=json", {"isbn": "9780000000003"}),
        ("POST", "/authors/3/books?format=json", {"isbn": "9780000000003", "orden": 2}),
    ]


def test_authors_quitar_relacion_y_error_de_isbn_inexistente(servidor, config):
    from api.authors_client import AuthorsClient

    authors = AuthorsClient(config, _sesion_iniciada(config))
    servidor.cola += [_respuesta(200, {}), _respuesta(404, {"error": "LIBRO_NO_ENCONTRADO",
                                                             "message": "No existe un libro con ISBN 999 en el catalogo."}),
                      _respuesta(503, {"error": "BOOKS_NO_DISPONIBLE", "message": "El servicio de libros no responde."})]
    authors.remove_book(3, "9780000000003")
    assert servidor.recibidas[0][0].method == "DELETE" and "/authors/3/books/9780000000003" in servidor.recibidas[0][0].url
    with pytest.raises(ApiError) as error:
        authors.add_book(3, "999")
    assert error.value.status == 404 and error.value.code == "LIBRO_NO_ENCONTRADO" and "999" in error.value.mensaje
    with pytest.raises(ApiError) as error:
        authors.add_book(3, "9780000000003")
    assert error.value.status == 503 and "no está disponible" in error.value.mensaje


# ------------------------------------------------------------------ cliente de pedidos
def test_pedidos_rutas_y_cuerpos(servidor, config):
    from api.pedidos_client import PedidosClient

    pedidos = PedidosClient(config, _sesion_iniciada(config))
    servidor.cola += [_respuesta(200, {"items": [{"isbn": "1", "stock_disponible": 5}]})] + [_respuesta(200, {})] * 11
    assert pedidos.inventory() == [{"isbn": "1", "stock_disponible": 5}]
    pedidos.create({"9780000000001": 2, "9780000000003": 1})
    pedidos.list(estado="PAGADO", user_id=31, per_page=50)
    pedidos.get(7)
    pedidos.replace_lines(7, {"9780000000001": 4})
    pedidos.patch_lines(7, {"9780000000003": 0})
    pedidos.cancel(7)
    pedidos.set_state(7, "ENVIADO")
    pedidos.delete(7)
    pedidos.inventory_add("9780000000004", 10)
    pedidos.inventory_set("9780000000004", 3)
    pedidos.inventory_remove("9780000000004")

    vistas = [(prep.method, prep.url.split(":5004")[1].split("?")[0], json.loads(prep.body) if prep.body else None)
              for prep, _ in servidor.recibidas]
    assert vistas == [
        ("GET", "/inventario", None),
        ("POST", "/pedidos", {"lineas": [{"isbn": "9780000000001", "cantidad": 2}, {"isbn": "9780000000003", "cantidad": 1}]}),
        ("GET", "/pedidos", None),
        ("GET", "/pedidos/7", None),
        ("PUT", "/pedidos/7", {"lineas": [{"isbn": "9780000000001", "cantidad": 4}]}),
        ("PATCH", "/pedidos/7/lineas", {"lineas": [{"isbn": "9780000000003", "cantidad": 0}]}),
        ("PATCH", "/pedidos/7/cancelar", {}),
        ("PATCH", "/pedidos/7/estado", {"estado": "ENVIADO"}),
        ("DELETE", "/pedidos/7", None),
        ("POST", "/inventario", {"isbn": "9780000000004", "stock_disponible": 10}),
        ("PUT", "/inventario/9780000000004", {"stock_disponible": 3}),
        ("DELETE", "/inventario/9780000000004", None),
    ]
    assert "Authorization" not in servidor.recibidas[0][0].headers          # el inventario se consulta sin token
    assert all(p in servidor.recibidas[2][0].url for p in ("estado=PAGADO", "user_id=31", "per_page=50"))


def test_pedidos_falta_de_stock_es_un_conflicto_que_no_cierra_la_sesion(servidor, config):
    from api.pedidos_client import PedidosClient

    sesion = _sesion_iniciada(config)
    servidor.cola.append(_respuesta(409, {"error": "STOCK_INSUFICIENTE", "message":
                                           "Stock insuficiente para el ISBN 9780000000003: disponible 1, solicitado 5."}))
    with pytest.raises(ApiError) as error:
        PedidosClient(config, sesion).create({"9780000000003": 5})
    assert error.value.status == 409 and error.value.code == "STOCK_INSUFICIENTE"
    assert "9780000000003" in error.value.mensaje and sesion.activa


def test_texto_del_pedido_muestra_lineas_vencimiento_e_historial():
    from screens.pedidos_screen import COLORES_ESTADO, ESTADOS, texto_del_pedido

    pedido = {"id": 7, "user_id": 31, "estado": "PENDIENTE_PAGO", "total": 850.5, "expira_en": "2026-10-06T12:15:00",
              "lineas": [{"isbn": "9780000000001", "titulo": "Cien años de soledad", "cantidad": 2,
                          "precio_unitario": 300.0, "subtotal": 600.0}],
              "historial": [{"estado_anterior": None, "estado_nuevo": "PENDIENTE_PAGO", "actor": "user:31",
                             "fecha": "2026-10-06T12:00:00"}]}
    texto = texto_del_pedido(pedido)
    for parte in ("Pedido #7", "2 × Cien años de soledad", "$600.00", "TOTAL: $850.50", "vence: 2026-10-06 12:15",
                  "creado → PENDIENTE_PAGO  (user:31)"):
        assert parte in texto
    assert "vence" not in texto_del_pedido({**pedido, "estado": "PAGADO"})
    assert set(COLORES_ESTADO) == set(ESTADOS)                              # cada estado tiene su color
    assert COLORES_ESTADO["CANCELADO"] == COLORES_ESTADO["EXPIRADO"]
