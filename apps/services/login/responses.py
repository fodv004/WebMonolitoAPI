"""
responses.py
Negociacion de formato y serializacion de TODAS las respuestas del servicio.

Cada endpoint responde XML por defecto o JSON con ?format=json. Los errores
usan exactamente el mismo sobre que los exitos, en el formato pedido:

  JSON: {"status": "ok"|"error", "code": "...", "message": "...", "data": {...}}
  XML : <response><status>..</status><code>..</code><message>..</message><data>..</data></response>
"""
import xml.etree.ElementTree as ET

from flask import Response, jsonify, request

FORMATOS_VALIDOS = ("xml", "json")
FORMATO_POR_DEFECTO = "xml"


class ApiError(Exception):
    """Error controlado: se convierte en una respuesta con el mismo sobre."""

    def __init__(self, http_status, code, message, errors=None):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message
        self.errors = errors


def resolve_format():
    """Devuelve 'xml' o 'json'. Sin parametro -> xml. Valor desconocido -> 400."""
    raw = request.args.get("format")
    if raw is None:
        return FORMATO_POR_DEFECTO
    formato = raw.strip().lower()
    if formato not in FORMATOS_VALIDOS:
        raise ApiError(
            400,
            "FORMATO_INVALIDO",
            f"El valor de 'format' no es valido. Valores permitidos: {', '.join(FORMATOS_VALIDOS)}.",
        )
    return formato


def _safe_format():
    """Formato para responder un error, aunque el propio 'format' sea invalido."""
    try:
        return resolve_format()
    except ApiError:
        return FORMATO_POR_DEFECTO


def _singular(clave):
    return clave[:-1] if clave.endswith("s") and len(clave) > 1 else "item"


def _texto(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)


def _agregar(padre, clave, valor):
    elemento = ET.SubElement(padre, clave)
    if isinstance(valor, dict):
        for k, v in valor.items():
            _agregar(elemento, k, v)
    elif isinstance(valor, (list, tuple)):
        hijo = _singular(clave)
        for item in valor:
            _agregar(elemento, hijo, item)
    else:
        elemento.text = _texto(valor)


def _serializar(formato, http_status, payload):
    if formato == "json":
        respuesta = jsonify(payload)
    else:
        raiz = ET.Element("response")
        for clave, valor in payload.items():
            _agregar(raiz, clave, valor)
        cuerpo = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(raiz, encoding="unicode")
        respuesta = Response(cuerpo, mimetype="application/xml")
    respuesta.status_code = http_status
    return respuesta


def success(formato, http_status, code, message, data=None):
    payload = {"status": "ok", "code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return _serializar(formato, http_status, payload)


def failure(err):
    """Respuesta de error para una ApiError, en el formato solicitado (xml por defecto)."""
    payload = {"status": "error", "code": err.code, "message": err.message}
    if err.errors:
        payload["errors"] = err.errors
    return _serializar(_safe_format(), err.http_status, payload)
