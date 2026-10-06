"""
common/app_factory.py
Fabrica de la app Flask de un microservicio nuevo: logging con filtro,
CORS, /metrics, /health y errores con formato uniforme.
"""
from flask import Flask

from common import db
from common.cors import init_cors
from common.errors import register_error_handlers
from common.health import init_health
from common.logging_utils import init_logging
from common.metrics import init_metrics


def create_service_app(service_name, version="1.0.0", db_check=None):
    app = Flask(service_name)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    init_logging(app)
    init_cors(app)
    init_metrics(app, service_name)
    init_health(app, service_name, db_check or db.ping, version)
    register_error_handlers(app)
    return app
