"""
common/errors.py
Formato uniforme de error de los microservicios:

    {"error": "<codigo>", "message": "<texto>"}
"""
import logging

import redis
from flask import jsonify
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class ApiError(Exception):
    """Error controlado: se convierte en una respuesta con el formato uniforme."""

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(status, code, message):
    respuesta = jsonify({"error": code, "message": message})
    respuesta.status_code = status
    if status == 401:
        respuesta.headers["WWW-Authenticate"] = "Bearer"
    return respuesta


def register_error_handlers(app):
    """Para los servicios nuevos. login y books conservan sus propios manejadores."""

    @app.errorhandler(ApiError)
    def _api_error(err):
        return error_response(err.status, err.code, err.message)

    @app.errorhandler(HTTPException)
    def _http_error(err):
        return error_response(err.code, f"HTTP_{err.code}", err.description or err.name)

    @app.errorhandler(redis.RedisError)
    def _redis_caido(err):
        # Sesion, revocacion y autorizacion dependen de Redis: se falla de forma segura.
        log.error("Redis no disponible: %s", err)
        return error_response(503, "REDIS_NO_DISPONIBLE",
                              "No se puede completar la operacion en este momento. Intenta mas tarde.")

    try:
        import psycopg
    except ImportError:      # el servicio no usa psycopg 3
        psycopg = None
    if psycopg is not None:
        @app.errorhandler(psycopg.OperationalError)
        def _db_caida(err):
            log.error("PostgreSQL no disponible: %s", err)
            return error_response(503, "BASE_DE_DATOS_NO_DISPONIBLE", "PostgreSQL no responde.")

    @app.errorhandler(Exception)
    def _inesperado(err):
        log.exception("Error inesperado")
        return error_response(500, "ERROR_INTERNO", "Ocurrio un error inesperado.")
