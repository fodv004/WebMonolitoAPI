"""
common/logging_utils.py
Log HTTP en consola (metodo, ruta, status, tiempo) y filtro que oculta
datos sensibles en CUALQUIER linea de log: Authorization, password,
password_actual, password_nueva, refresh_token, token, tarjeta y cvv.

Del request solo se registra la ruta (nunca el query string ni el body):
/confirm?token=... no debe quedar en el log.
"""
import logging
import re
import time

from flask import g, request

OCULTO = "***"
CAMPOS_SENSIBLES = ("authorization", "password", "password_actual", "password_nueva",
                    "refresh_token", "token", "tarjeta", "cvv")

# clave (con o sin comillas) + ":" o "=" + valor (entre comillas, "Bearer xxx" o hasta el separador)
_PAR_SENSIBLE = re.compile(
    r"""(?ix)
    ( ["']? (?:authorization | \w*password\w* | \w*token | tarjeta\w* | cvv) ["']? \s* [:=] \s* )
    ( "[^"]*" | '[^']*' | (?:bearer\s+)? [^\s,&;}'"]+ )
    """
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.=+/]+")

log_http = logging.getLogger("http")


def redact(texto):
    texto = _PAR_SENSIBLE.sub(lambda m: m.group(1) + OCULTO, texto)
    return _BEARER.sub("Bearer " + OCULTO, texto)


def mask(datos):
    """Copia de un dict/list con los campos sensibles ocultos (para registrar bodies)."""
    if isinstance(datos, dict):
        return {k: OCULTO if str(k).lower() in CAMPOS_SENSIBLES else mask(v) for k, v in datos.items()}
    if isinstance(datos, (list, tuple)):
        return [mask(v) for v in datos]
    return datos


class SensitiveFilter(logging.Filter):
    def filter(self, record):
        try:
            mensaje = record.getMessage()
        except Exception:
            return True
        record.msg = redact(mensaje)
        record.args = ()
        return True


def init_logging(app):
    raiz = logging.getLogger()
    if not raiz.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # El filtro va en los handlers: asi cubre tambien los loggers hijos.
    for handler in raiz.handlers:
        if not any(isinstance(f, SensitiveFilter) for f in handler.filters):
            handler.addFilter(SensitiveFilter())

    @app.before_request
    def _inicio():
        g._inicio_peticion = time.perf_counter()

    @app.after_request
    def _registrar(resp):
        inicio = getattr(g, "_inicio_peticion", None)
        ms = (time.perf_counter() - inicio) * 1000 if inicio else 0
        log_http.info("%s %s %s %.0fms", request.method, request.path, resp.status_code, ms)
        return resp
