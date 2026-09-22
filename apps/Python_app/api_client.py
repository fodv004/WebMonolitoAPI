"""
api_client.py
Cliente HTTP (solo libreria estandar, sin dependencias externas) para
los dos microservicios:
  - login  (apps/services/login, puerto 5000 por defecto)
  - books  (apps/services/library_soap_service, puerto 5001 por defecto)

Ambos responden JSON con ?format=json. Las cookies de sesion del
microservicio de login (cookie auth_session) se conservan entre
llamadas de un mismo AuthClient gracias a un CookieJar.
"""
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 6


class ApiError(Exception):
    def __init__(self, mensaje, status=None, code=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.code = code


def _parse_json(texto):
    try:
        return json.loads(texto) if texto else {}
    except json.JSONDecodeError:
        return None


class _HttpClient:
    """Envuelve urllib con cookies, JSON y manejo de errores uniforme."""

    def __init__(self):
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))

    def _request(self, method, url, data=None):
        body = None
        headers = {"Accept": "application/json"}
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        separador = "&" if "?" in url else "?"
        req = urllib.request.Request(f"{url}{separador}format=json", data=body, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=TIMEOUT) as resp:
                crudo = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            crudo = e.read().decode("utf-8")
            payload = _parse_json(crudo) or {}
            mensaje = payload.get("message") or payload.get("mensaje") or f"Error HTTP {e.code}."
            codigo = payload.get("code") or payload.get("error")
            raise ApiError(mensaje, status=e.code, code=codigo) from e
        except urllib.error.URLError as e:
            raise ApiError(f"No se pudo conectar con {url}: {e.reason}") from e

        return _parse_json(crudo) or {}

    def get(self, url):
        return self._request("GET", url)

    def post(self, url, data):
        return self._request("POST", url, data)

    def put(self, url, data):
        return self._request("PUT", url, data)

    def delete(self, url):
        return self._request("DELETE", url)


def is_healthy(base_url):
    """True/False; nunca lanza. Se usa para el semaforo del catalogo."""
    try:
        req = urllib.request.Request(f"{base_url}/health?format=json", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
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
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self._http = _HttpClient()

    def list_books(self):
        return self._http.get(f"{self.base_url}/books")

    def list_formats(self):
        return self._http.get(f"{self.base_url}/formats")

    def create_book(self, **campos):
        return self._http.post(f"{self.base_url}/books", campos)

    def update_book(self, isbn, **campos):
        return self._http.put(f"{self.base_url}/books/{urllib.parse.quote(isbn, safe='')}", campos)

    def delete_book(self, isbn):
        return self._http.delete(f"{self.base_url}/books/{urllib.parse.quote(isbn, safe='')}")
