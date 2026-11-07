"""Servidor WebSocket MÍNIMO de prueba (sustituto temporal del microservicio).

Respeta el contrato: Flask + Flask-Sock en 0.0.0.0:5900, /ws?role=gps|map y GET /health.
Solo imprime lo que recibe de cada camión y responde {"type":"ack"} o
{"type":"error","detail":"..."}. No reenvía nada al mapa.

    python servidor_prueba.py
"""

import json
import time

from flask import Flask, jsonify, request
from flask_sock import ConnectionClosed, Sock

app = Flask(__name__)
sock = Sock(app)

CAMPOS = {"vehicle_id", "latitude", "longitude", "speed", "heading"}


def log(texto):
    print(f"[{time.strftime('%H:%M:%S')}] {texto}", flush=True)


def es_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def validar(datos):
    """Devuelve None si el mensaje es válido o un texto con el error."""
    if not isinstance(datos, dict):
        return "el mensaje debe ser un objeto JSON"
    if set(datos) != CAMPOS:
        faltan = CAMPOS - set(datos)
        sobran = set(datos) - CAMPOS
        return f"campos incorrectos (faltan: {sorted(faltan)}, sobran: {sorted(sobran)})"
    if not isinstance(datos["vehicle_id"], str) or not datos["vehicle_id"]:
        return "vehicle_id debe ser un texto no vacío"
    for campo in ("latitude", "longitude", "speed", "heading"):
        if not es_numero(datos[campo]):
            return f"{campo} debe ser numérico"
    if not -90 <= datos["latitude"] <= 90:
        return "latitude fuera de rango"
    if not -180 <= datos["longitude"] <= 180:
        return "longitude fuera de rango"
    if datos["speed"] < 0:
        return "speed no puede ser negativa"
    if not 0 <= datos["heading"] < 360:
        return "heading debe estar en [0, 360)"
    return None


@app.get("/health")
def health():
    return jsonify(status="ok")


@sock.route("/ws")
def ws(conexion):
    rol = request.args.get("role")
    cliente = request.remote_addr
    if rol not in ("gps", "map"):
        conexion.send(json.dumps({"type": "error", "detail": "role debe ser 'gps' o 'map'"}))
        return

    log(f"Conectado {cliente} con role={rol}")
    try:
        while True:
            crudo = conexion.receive()
            if rol == "map":
                continue  # el servidor de prueba no envía nada al mapa
            log(f"Recibido: {crudo}")
            try:
                datos = json.loads(crudo)
            except (TypeError, ValueError):
                conexion.send(json.dumps({"type": "error", "detail": "JSON inválido"}))
                continue
            error = validar(datos)
            if error:
                log(f"  -> error: {error}")
                conexion.send(json.dumps({"type": "error", "detail": error}))
            else:
                conexion.send(json.dumps({"type": "ack"}))
    except ConnectionClosed:
        log(f"Desconectado {cliente} (role={rol})")


if __name__ == "__main__":
    log("Servidor de prueba en ws://0.0.0.0:5900/ws  (health: http://localhost:5900/health)")
    app.run(host="0.0.0.0", port=5900, threaded=True)
