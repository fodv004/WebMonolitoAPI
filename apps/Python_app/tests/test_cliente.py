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
