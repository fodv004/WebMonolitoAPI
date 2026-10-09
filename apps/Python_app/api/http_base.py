"""
api/http_base.py
Cliente HTTP base (libreria `requests`) por el que sale CUALQUIER peticion
de la app hacia los microservicios.

  * URL segun la configuracion: http://<IP>:<puerto> (default) o
    https://<IP>/api/<servicio>.
  * Timeout de 5 segundos y header "Authorization: Bearer <JWT>" automatico
    cuando hay sesion.
  * Ante un 401 intenta UNA renovacion del token (POST /refresh) y repite
    la peticion; si no se puede, el error sale marcado como sesion invalida
    y la interfaz regresa al login.
  * Log de cada peticion y respuesta en consola, SIN tokens ni contraseñas.
  * Mensajes claros para 401, 403, 409 y 503.
"""
import json
import threading
import time
from datetime import datetime

import requests
import urllib3

from config.settings import TIMEOUT_HTTP

# Los bodies muy largos (p. ej. el catalogo completo) se recortan en consola.
MAX_BODY_LOG = 4000

OCULTO = "********"
_CAMPOS_OCULTOS = {"password", "password_actual", "password_nueva", "refresh_token", "token", "tarjeta", "cvv"}
_HEADERS_OCULTOS = {"authorization", "cookie", "set-cookie", "x-internal-key"}
_SEPARADOR = "=" * 78
_SUBSEPARADOR = "-" * 78
_lock_consola = threading.Lock()

# Con "Verificar certificado" desactivado requests avisa en cada peticion;
# la advertencia ya se muestra de forma permanente en Configuracion.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ApiError(Exception):
    def __init__(self, mensaje, status=None, code=None, sesion_invalida=False):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.code = code
        self.sesion_invalida = sesion_invalida

    @property
    def es_sesion_invalida(self):
        """True cuando hay que volver al login (401 que no se pudo resolver renovando el token)."""
        return self.sesion_invalida


# ------------------------------------------------------------------ logging
def ocultar(datos):
    """Copia de un JSON con contraseñas, tokens y tarjetas ocultos (a cualquier profundidad)."""
    if isinstance(datos, dict):
        return {k: OCULTO if str(k).lower() in _CAMPOS_OCULTOS else ocultar(v) for k, v in datos.items()}
    if isinstance(datos, list):
        return [ocultar(v) for v in datos]
    return datos


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
        texto = json.dumps(ocultar(datos), indent=2, ensure_ascii=False)
    if len(texto) > MAX_BODY_LOG:
        texto = f"{texto[:MAX_BODY_LOG]}\n... ({len(texto) - MAX_BODY_LOG} caracteres mas, recortado)"
    return texto


def _formatear_headers(headers):
    lineas = []
    for clave, valor in headers.items():
        if clave.lower() in _HEADERS_OCULTOS:
            valor = f"Bearer {OCULTO}" if str(valor).lower().startswith("bearer ") else OCULTO
        lineas.append(f"  {clave}: {valor}")
    return "\n".join(lineas) or "  (ninguno)"


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


# ------------------------------------------------------------------ mensajes
def _mensaje_de_error(status, detalle, con_sesion):
    """Texto para el usuario. `detalle` es el mensaje que envio el servidor (puede venir vacio)."""
    sufijo = f" ({detalle})" if detalle else ""
    if status == 401 and con_sesion:
        return f"Tu sesión no es válida o ya expiró. Inicia sesión de nuevo.{sufijo}"
    if status == 403 and con_sesion:
        return f"No tienes permisos para realizar esta operación.{sufijo}"
    if status == 409:
        return f"Conflicto con el estado actual de los datos: {detalle}" if detalle else \
            "Conflicto con el estado actual de los datos."
    if status == 503:
        return f"El servicio no está disponible en este momento. Intenta de nuevo en unos minutos.{sufijo}"
    return detalle or f"Error HTTP {status}."


# ------------------------------------------------------------------ cliente base
class HttpClient:
    def __init__(self, servicio, config, sesion=None):
        self.servicio = servicio
        self.config = config          # config.settings.AppConfig (se lee en cada peticion)
        self.sesion = sesion          # session.Session o None
        self._session = requests.Session()
        self._local = threading.local()

    @property
    def base_url(self):
        return self.config.base_url(self.servicio)

    @property
    def ultimo_status(self):
        """Status de la ultima respuesta recibida en ESTE hilo."""
        return getattr(self._local, "status", None)

    def request(self, method, path, data=None, auth=True, registrar=True, timeout=None, token=None,
                params=None, headers=None, _reintento=False):
        """`auth=False` no envia Authorization. `token` envia ese JWT en lugar del de la
        sesion (y entonces un 401 no dispara la renovacion). `params` son parametros de
        consulta adicionales (los None se omiten) y `headers`, cabeceras adicionales
        (p. ej. Idempotency-Key)."""
        url = f"{self.base_url}{path}"
        extra = headers or {}
        headers = {"Accept": "application/json", **extra}
        renovable = token is None and not _reintento
        if token is None and auth and self.sesion is not None:
            token = self.sesion.token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        consulta = {"format": "json"}
        consulta.update({k: v for k, v in (params or {}).items() if v is not None and v != ""})
        req = requests.Request(method, url, params=consulta, json=data, headers=headers)
        prep = self._session.prepare_request(req)

        if registrar:
            _log_peticion(prep)
        inicio = time.perf_counter()
        try:
            resp = self._session.send(prep, timeout=timeout or TIMEOUT_HTTP, verify=self.config.verify())
        except requests.exceptions.SSLError as e:
            if registrar:
                _log_sin_respuesta(e, inicio)
            raise ApiError(f"No se pudo verificar el certificado HTTPS de {url}. "
                           "Revisa el archivo .crt en Configuración.") from e
        except requests.RequestException as e:
            if registrar:
                _log_sin_respuesta(e, inicio)
            raise ApiError(f"No se pudo conectar con {url}. Revisa el semáforo y la Configuración.") from e
        if registrar:
            _log_respuesta(resp, inicio)

        self._local.status = resp.status_code
        try:
            payload = resp.json() if resp.content else {}
        except ValueError:
            payload = None

        if resp.status_code == 401 and token and renovable:
            # Un solo intento de renovacion; si funciona se repite la peticion con el token nuevo.
            if self.sesion.renovar(token):
                return self.request(method, path, data, auth=auth, registrar=registrar,
                                    timeout=timeout, params=params, headers=extra, _reintento=True)

        if resp.status_code >= 400:
            datos = payload if isinstance(payload, dict) else {}
            detalle = datos.get("message") or datos.get("mensaje") or ""
            codigo = datos.get("code") or datos.get("error")
            raise ApiError(_mensaje_de_error(resp.status_code, detalle, con_sesion=bool(token)),
                           status=resp.status_code, code=codigo,
                           sesion_invalida=resp.status_code == 401 and bool(token))
        return payload if payload is not None else {}

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, data=None, **kwargs):
        return self.request("POST", path, data, **kwargs)

    def put(self, path, data=None, **kwargs):
        return self.request("PUT", path, data, **kwargs)

    def patch(self, path, data=None, **kwargs):
        return self.request("PATCH", path, data, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)


class ServiceClient:
    """Base de los clientes por microservicio."""

    SERVICIO = None

    def __init__(self, config, sesion=None):
        self._http = HttpClient(self.SERVICIO, config, sesion)

    @property
    def base_url(self):
        return self._http.base_url

    @property
    def ultimo_status(self):
        return self._http.ultimo_status
