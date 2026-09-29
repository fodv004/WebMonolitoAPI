"""
api_client.py
Cliente HTTP (libreria `requests`) para los dos microservicios:
  - login  (apps/services/login, puerto 5000 por defecto)
  - books  (apps/services/library_soap_service, puerto 5001 por defecto)

Todas las peticiones pasan por _HttpClient._request, que imprime en la
consola cada peticion saliente (metodo, URL, headers con el Bearer
visible y body) y cada respuesta (status, headers y body).

Ambos servicios responden JSON con ?format=json. La cookie de sesion
del login (auth_session) se conserva en la requests.Session. El JWT que
devuelve POST /login se guarda en memoria en BooksClient.token y se
adjunta como "Authorization: Bearer <token>" en POST, PUT, PATCH y
DELETE hacia el servicio de libros (los GET van sin token).
"""
import json
import threading
import time
import urllib.parse
from datetime import datetime

import requests

TIMEOUT = 6

# El semaforo consulta /health cada 8 s en ambos servicios; registrar esas
# llamadas llenaria la consola. Poner en True para verlas tambien.
LOG_HEALTH_CHECKS = False

# Los bodies muy largos (p. ej. el catalogo completo) se recortan en consola.
MAX_BODY_LOG = 4000

_CAMPOS_OCULTOS = {"password"}
_SEPARADOR = "=" * 78
_SUBSEPARADOR = "-" * 78
_METODOS_CON_TOKEN = {"POST", "PUT", "PATCH", "DELETE"}
_lock_consola = threading.Lock()


class ApiError(Exception):
    def __init__(self, mensaje, status=None, code=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.code = code

    @property
    def es_sesion_invalida(self):
        return self.status in (401, 403)


# ------------------------------------------------------------------ logging
def _formatear_body(body):
    if body is None or body == b"" or body == "":
        return "(vacio)"
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    try:
        datos = json.loads(body)
    except (TypeError, ValueError):
        texto = str(body)
    else:
        if isinstance(datos, dict):
            datos = {k: ("********" if k in _CAMPOS_OCULTOS else v) for k, v in datos.items()}
        texto = json.dumps(datos, indent=2, ensure_ascii=False)
    if len(texto) > MAX_BODY_LOG:
        texto = f"{texto[:MAX_BODY_LOG]}\n... ({len(texto) - MAX_BODY_LOG} caracteres mas, recortado)"
    return texto


def _formatear_headers(headers):
    return "\n".join(f"  {k}: {v}" for k, v in headers.items()) or "  (ninguno)"


def _log_peticion(prep):
    with _lock_consola:
        print(_SEPARADOR)
        print(f">>> PETICION   [{datetime.now():%Y-%m-%d %H:%M:%S}]")
        print(f"{prep.method} {prep.url}")
        print("--- Headers ---")
        print(_formatear_headers(prep.headers))
        print("--- Body ---")
        print(_formatear_body(prep.body))
        print(_SUBSEPARADOR, flush=True)


def _log_respuesta(resp, inicio):
    ms = (time.perf_counter() - inicio) * 1000
    with _lock_consola:
        print(f"<<< RESPUESTA  ({ms:.0f} ms)")
        print(f"Status: {resp.status_code} {resp.reason}")
        print("--- Headers ---")
        print(_formatear_headers(resp.headers))
        print("--- Body ---")
        print(_formatear_body(resp.text))
        print(_SEPARADOR + "\n", flush=True)


def _log_sin_respuesta(error, inicio):
    ms = (time.perf_counter() - inicio) * 1000
    with _lock_consola:
        print(f"<<< SIN RESPUESTA  ({ms:.0f} ms)")
        print(f"Error de conexion: {error}")
        print(_SEPARADOR + "\n", flush=True)


# ------------------------------------------------------------------ cliente base
class _HttpClient:
    """Unico punto por el que sale cualquier peticion HTTP de la app."""

    def __init__(self):
        self._session = requests.Session()
        self._local = threading.local()
        self.token = None  # JWT en memoria; nunca se escribe a disco

    @property
    def ultimo_status(self):
        """Status de la ultima respuesta recibida en ESTE hilo."""
        return getattr(self._local, "status", None)

    def _request(self, method, url, data=None, registrar=True):
        headers = {"Accept": "application/json"}
        if self.token and method in _METODOS_CON_TOKEN:
            headers["Authorization"] = f"Bearer {self.token}"

        req = requests.Request(method, url, params={"format": "json"}, json=data, headers=headers)
        prep = self._session.prepare_request(req)

        if registrar:
            _log_peticion(prep)
        inicio = time.perf_counter()
        try:
            resp = self._session.send(prep, timeout=TIMEOUT)
        except requests.RequestException as e:
            if registrar:
                _log_sin_respuesta(e, inicio)
            raise ApiError(f"No se pudo conectar con {url}: {e}") from e
        if registrar:
            _log_respuesta(resp, inicio)

        self._local.status = resp.status_code
        try:
            payload = resp.json() if resp.content else {}
        except ValueError:
            payload = None

        if resp.status_code >= 400:
            datos = payload if isinstance(payload, dict) else {}
            mensaje = datos.get("message") or datos.get("mensaje") or f"Error HTTP {resp.status_code}."
            codigo = datos.get("code") or datos.get("error")
            raise ApiError(mensaje, status=resp.status_code, code=codigo)
        return payload if payload is not None else {}

    def get(self, url, registrar=True):
        return self._request("GET", url, registrar=registrar)

    def post(self, url, data):
        return self._request("POST", url, data)

    def put(self, url, data):
        return self._request("PUT", url, data)

    def patch(self, url, data):
        return self._request("PATCH", url, data)

    def delete(self, url):
        return self._request("DELETE", url)


def is_healthy(base_url):
    """True/False; nunca lanza. Se usa para el semaforo del catalogo."""
    try:
        _HttpClient().get(f"{base_url.rstrip('/')}/health", registrar=LOG_HEALTH_CHECKS)
        return True
    except Exception:
        return False


class AuthClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self._http = _HttpClient()

    def register(self, nombre, apellido_paterno, apellido_materno, email, password):
        return self._http.post(f"{self.base_url}/register", {
            "nombre": nombre,
            "apellido_paterno": apellido_paterno,
            "apellido_materno": apellido_materno,
            "email": email,
            "password": password,
        })

    def login(self, email, password):
        return self._http.post(f"{self.base_url}/login", {"email": email, "password": password})

    def logout(self):
        return self._http.post(f"{self.base_url}/logout", {})

    def session(self):
        return self._http.get(f"{self.base_url}/session")


class BooksClient:
    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self._http = _HttpClient()
        self._http.token = token

    @property
    def token(self):
        return self._http.token

    @token.setter
    def token(self, valor):
        self._http.token = valor

    @property
    def ultimo_status(self):
        return self._http.ultimo_status

    def _url_libro(self, isbn):
        return f"{self.base_url}/books/{urllib.parse.quote(isbn, safe='')}"

    def list_books(self):
        return self._http.get(f"{self.base_url}/books")

    def list_formats(self):
        return self._http.get(f"{self.base_url}/formats")

    def create_book(self, **campos):
        return self._http.post(f"{self.base_url}/books", campos)

    def update_book(self, isbn, **campos):
        return self._http.put(self._url_libro(isbn), campos)

    def patch_book(self, isbn, **campos):
        return self._http.patch(self._url_libro(isbn), campos)

    def delete_book(self, isbn):
        return self._http.delete(self._url_libro(isbn))
