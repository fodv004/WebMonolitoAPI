"""
common/health.py
GET /health publico. HTTP 200 solo si PostgreSQL y Redis responden;
503 en cualquier otro caso.

    {"service": "users", "status": "ok", "db": "ok", "redis": "ok", "version": "1.0.0"}
"""
import logging

from flask import jsonify

from common import redis_client

log = logging.getLogger(__name__)


def init_health(app, service_name, db_check, version="1.0.0"):
    """`db_check` es una funcion sin argumentos que devuelve True si PostgreSQL responde."""

    @app.get("/health")
    def health():
        try:
            db_ok = bool(db_check())
        except Exception as e:
            log.error("Health check: PostgreSQL no responde: %s", e)
            db_ok = False
        redis_ok = redis_client.ping()

        todo_ok = db_ok and redis_ok
        return jsonify({
            "service": service_name,
            "status": "ok" if todo_ok else "error",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
            "version": version,
        }), 200 if todo_ok else 503
