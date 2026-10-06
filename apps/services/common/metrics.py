"""
common/metrics.py
Contadores en memoria del proceso y endpoint GET /metrics.

Son por proceso: las unidades systemd lanzan gunicorn con 1 worker (y
varios hilos) para que /metrics refleje todo el trafico del servicio.
"""
import threading
import time

from flask import jsonify, request

_lock = threading.Lock()
_inicio = time.time()

_CONTADORES = ("requests_total", "errors_4xx", "errors_5xx", "responses_401", "responses_403",
               "cache_hits", "cache_misses", "redis_errors")
_valores = dict.fromkeys(_CONTADORES, 0)


def inc(nombre, cantidad=1):
    with _lock:
        _valores[nombre] += cantidad


def snapshot():
    with _lock:
        return dict(_valores)


def reset():
    """Solo para pruebas."""
    with _lock:
        for nombre in _CONTADORES:
            _valores[nombre] = 0


def init_metrics(app, service_name):
    @app.after_request
    def _contar(resp):
        if request.path != "/metrics":
            inc("requests_total")
            if 400 <= resp.status_code < 500:
                inc("errors_4xx")
            elif resp.status_code >= 500:
                inc("errors_5xx")
            if resp.status_code == 401:
                inc("responses_401")
            elif resp.status_code == 403:
                inc("responses_403")
        return resp

    @app.get("/metrics")
    def metrics():
        datos = {"service": service_name, "uptime_seconds": int(time.time() - _inicio)}
        datos.update(snapshot())
        return jsonify(datos), 200
