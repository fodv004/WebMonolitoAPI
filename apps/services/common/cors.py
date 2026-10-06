"""
common/cors.py
CORS con flask-cors usando UNICAMENTE la lista de CORS_ALLOWED_ORIGINS
(separada por comas). Nunca "*": si la lista esta vacia no se envia
ningun header CORS y solo funcionan los clientes que no son navegador
(la app Tk, curl, llamadas entre servicios).
"""
import logging

from flask_cors import CORS

from common.config import settings

log = logging.getLogger(__name__)


def init_cors(app):
    origenes = settings.CORS_ALLOWED_ORIGINS
    if not origenes:
        log.info("CORS_ALLOWED_ORIGINS vacio: CORS deshabilitado.")
        return
    CORS(app, origins=origenes, allow_headers=["Authorization", "Content-Type"],
         methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
