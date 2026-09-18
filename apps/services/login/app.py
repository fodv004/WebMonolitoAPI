"""
app.py
Entrypoint del microservicio de autenticacion (Flask, puerto 5000).

Rutas propias: /register /login /logout /session /health /confirm /confirmed
y la documentacion Swagger en /apidocs/. No comparte ninguna ruta con el
microservicio de libros (puerto 5001: /books, /books/<isbn>, /books/gallery,
/cloud-concepts, /soap) ni con el monolito (puerto 3000).
"""
import logging

import psycopg2
from flask import Flask, redirect, request
from flasgger import Swagger
from werkzeug.exceptions import HTTPException

from config import Config
from responses import ApiError, failure
from routes import bp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("auth")

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "Microservicio de Autenticación",
        "version": "1.0.0",
        "description": (
            "Registro, inicio de sesión y sesión de usuarios de la librería en línea.\n\n"
            "**Formato de las respuestas:** todos los endpoints responden **XML por defecto** "
            "y **JSON** con `?format=json` (`?format=xml` es equivalente a omitirlo). "
            "Los errores usan el mismo sobre (`status`, `code`, `message`) en el formato pedido.\n\n"
            "**Sesión:** `POST /login` entrega la cookie `auth_session` (sesión de Flask); "
            "el navegador la reenvía sola en `/session` y `/logout`.\n\n"
            "**Confirmación:** `POST /register` envía un correo (Mailpit, "
            "interfaz web en http://localhost:8025) con el enlace `/confirm?token=...`."
        ),
    },
    "schemes": ["http"],
    "tags": [
        {"name": "Autenticación", "description": "Registro, login, logout, sesión y confirmación de cuenta"},
        {"name": "Salud", "description": "Estado del servicio y de PostgreSQL"},
    ],
    "parameters": {
        "formatParam": {
            "name": "format",
            "in": "query",
            "type": "string",
            "enum": ["xml", "json"],
            "default": "xml",
            "required": False,
            "description": "Formato de la respuesta. Por omisión: `xml`.",
        }
    },
    "definitions": {
        "RegistroRequest": {
            "type": "object",
            "required": ["nombre", "apellido_paterno", "apellido_materno", "email", "password"],
            "properties": {
                "nombre": {"type": "string", "maxLength": 150, "example": "Ana"},
                "apellido_paterno": {"type": "string", "maxLength": 100, "example": "Pérez"},
                "apellido_materno": {"type": "string", "maxLength": 100, "example": "Ruiz"},
                "email": {"type": "string", "format": "email", "example": "ana@correo.com"},
                "password": {"type": "string", "format": "password", "minLength": 8, "maxLength": 72,
                             "example": "MiClaveSegura123"},
            },
        },
        "LoginRequest": {
            "type": "object",
            "required": ["email", "password"],
            "properties": {
                "email": {"type": "string", "format": "email", "example": "ana@correo.com"},
                "password": {"type": "string", "format": "password", "example": "MiClaveSegura123"},
            },
        },
        "Respuesta": {
            "type": "object",
            "description": "Sobre común. En XML el elemento raíz es `<response>` con los mismos campos.",
            "properties": {
                "status": {"type": "string", "enum": ["ok", "error"]},
                "code": {"type": "string", "example": "USUARIO_REGISTRADO"},
                "message": {"type": "string"},
                "data": {"type": "object"},
                "errors": {
                    "type": "array",
                    "description": "Solo en errores de validación.",
                    "items": {
                        "type": "object",
                        "properties": {"field": {"type": "string"}, "message": {"type": "string"}},
                    },
                },
            },
        },
    },
}

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [{"endpoint": "apispec_1", "route": "/apispec_1.json",
               "rule_filter": lambda rule: True, "model_filter": lambda tag: True}],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}

_MENSAJES_HTTP = {
    404: "Recurso no encontrado.",
    405: "Metodo no permitido para este recurso.",
    413: "El cuerpo de la peticion es demasiado grande.",
    415: "Tipo de contenido no soportado.",
}


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    app.register_blueprint(bp)
    Swagger(app, template=SWAGGER_TEMPLATE, config=SWAGGER_CONFIG)

    @app.get("/")
    def raiz():
        return redirect("/apidocs/")

    @app.errorhandler(ApiError)
    def _api_error(err):
        return failure(err)

    @app.errorhandler(HTTPException)
    def _http_error(err):
        mensaje = _MENSAJES_HTTP.get(err.code, err.description or err.name)
        return failure(ApiError(err.code, f"HTTP_{err.code}", mensaje))

    @app.errorhandler(psycopg2.OperationalError)
    def _db_down(err):
        log.error("PostgreSQL no disponible: %s", err)
        return failure(ApiError(503, "BASE_DE_DATOS_NO_DISPONIBLE", "PostgreSQL no responde."))

    @app.errorhandler(Exception)
    def _unexpected(err):
        log.exception("Error inesperado")
        return failure(ApiError(500, "ERROR_INTERNO", "Ocurrio un error inesperado."))

    @app.after_request
    def _no_cache(resp):
        # Las respuestas dependen de la sesion: nunca deben quedar en cache.
        if not request.path.startswith(("/apidocs", "/flasgger_static", "/apispec")):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=False)
