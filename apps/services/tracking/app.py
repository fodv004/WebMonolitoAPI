"""Microservicio de rastreo GPS (Proyecto 2).

Recibe las posiciones de los camiones (GPSapp) y se las empuja a los mapas.

    python app.py      -> escucha en 0.0.0.0:5900

Solo expone:
    /ws?role=gps   camiones: mandan {"vehicle_id","latitude","longitude","speed","heading"}
                   y reciben {"type":"ack"} o {"type":"error","detail":"..."}
    /ws?role=map   mapas: reciben snapshot al conectar y luego update; pueden mandar config
    GET /health    {"status":"ok","vehicles":N,"active_vehicles":A,"map_clients":M}

No sirve páginas web ni HTML. Todo se guarda en memoria (sin base de datos).
"""

import itertools
import json
import logging
import math
import threading
import time
from collections import deque
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_sock import ConnectionClosed, Sock

HOST, PUERTO = "0.0.0.0", 5900
CAMPOS = ("vehicle_id", "latitude", "longitude", "speed", "heading")  # en el orden del contrato
HISTORIAL = 50                 # últimas posiciones guardadas por vehículo
INACTIVO_S = 15                # sin datos en este tiempo -> inactivo
OLVIDAR_S = 600                # inactivo por este tiempo -> se borra de memoria
INTERVALO_DEFECTO_S = 1.0
INTERVALO_MIN_S, INTERVALO_MAX_S = 0.1, 3600

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("microservicio")
logging.getLogger("werkzeug").setLevel(logging.WARNING)  # sin una línea por cada petición HTTP

app = Flask(__name__)
sock = Sock(app)


# ---------------------------------------------------------------- estado en memoria


class Flota:
    """Estado actual e historial de cada vehículo. Todo acceso pasa por el lock,
    porque cada conexión WebSocket corre en su propio hilo."""

    def __init__(self):
        self.lock = threading.Lock()
        self.vehiculos = {}      # vehicle_id -> dict (ver registrar)
        self.conexiones = {}     # vehicle_id -> ficha de la conexión gps que lo tiene
        self.mapas = 0
        self.fichas = itertools.count(1)

    def _activo(self, v, ahora):
        return v["conectado"] and ahora - v["ultimo"] <= INACTIVO_S

    def ligar(self, vehicle_id):
        """Liga una conexión gps nueva a vehicle_id. Devuelve su ficha o None si ya está ocupado.

        Si la conexión que lo tiene lleva más de INACTIVO_S sin mandar datos (por ejemplo
        una conexión que quedó colgada), la nueva la reemplaza.
        """
        with self.lock:
            ahora = time.monotonic()
            v = self.vehiculos.get(vehicle_id)
            if vehicle_id in self.conexiones and v is not None and self._activo(v, ahora):
                return None
            ficha = next(self.fichas)
            self.conexiones[vehicle_id] = ficha
            return ficha

    def soltar(self, vehicle_id, ficha):
        """La conexión se cerró: el vehículo queda inactivo (no se borra todavía)."""
        with self.lock:
            if self.conexiones.get(vehicle_id) != ficha:
                return False  # otra conexión ya lo había tomado
            del self.conexiones[vehicle_id]
            if vehicle_id in self.vehiculos:
                self.vehiculos[vehicle_id]["conectado"] = False
            return True

    def es_dueña(self, vehicle_id, ficha):
        with self.lock:
            return self.conexiones.get(vehicle_id) == ficha

    def registrar(self, datos):
        recibido = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        posicion = {**{c: datos[c] for c in CAMPOS}, "received_at": recibido}
        with self.lock:
            v = self.vehiculos.get(datos["vehicle_id"])
            nuevo = v is None
            if nuevo:
                v = self.vehiculos[datos["vehicle_id"]] = {"historial": deque(maxlen=HISTORIAL), "version": 0}
            v.update(actual=posicion, conectado=True, ultimo=time.monotonic(), version=v["version"] + 1)
            v["historial"].append(posicion)
        return nuevo

    def lista(self, max_vehiculos=None):
        """Primeros N vehículos ordenados por vehicle_id: (lista para el mapa, firma para detectar cambios)."""
        with self.lock:
            ahora = time.monotonic()
            ids = sorted(self.vehiculos)[:max_vehiculos]
            vehiculos, firma = [], []
            for vid in ids:
                v = self.vehiculos[vid]
                activo = self._activo(v, ahora)
                vehiculos.append({**v["actual"], "active": activo})
                firma.append((vid, v["version"], activo))
        return vehiculos, tuple(firma)

    def revisar(self):
        """Devuelve los vehículos que acaban de quedar inactivos y borra los olvidados."""
        nuevos_inactivos, olvidados = [], []
        with self.lock:
            ahora = time.monotonic()
            for vid, v in list(self.vehiculos.items()):
                activo = self._activo(v, ahora)
                if v.get("avisado_activo", True) and not activo:
                    nuevos_inactivos.append(vid)
                v["avisado_activo"] = activo
                if not activo and vid not in self.conexiones and ahora - v["ultimo"] > OLVIDAR_S:
                    del self.vehiculos[vid]
                    olvidados.append(vid)
        return nuevos_inactivos, olvidados

    def conteo(self):
        with self.lock:
            ahora = time.monotonic()
            activos = sum(self._activo(v, ahora) for v in self.vehiculos.values())
            return len(self.vehiculos), activos, self.mapas

    def cambiar_mapas(self, delta):
        with self.lock:
            self.mapas += delta
            return self.mapas


flota = Flota()


def vigilar():
    """Hilo de fondo: avisa en consola cuando un vehículo queda inactivo y borra los olvidados."""
    while True:
        time.sleep(1)
        inactivos, olvidados = flota.revisar()
        for vid in inactivos:
            log.info(f"[gps] {vid} inactivo (desconectado o sin datos en {INACTIVO_S} s)")
        for vid in olvidados:
            log.info(f"[gps] {vid} borrado de memoria tras {OLVIDAR_S} s inactivo")


# ---------------------------------------------------------------- validación


def es_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def validar(datos):
    """Devuelve None si el mensaje cumple el contrato, o el texto del error."""
    if not isinstance(datos, dict):
        return "el mensaje debe ser un objeto JSON"
    if set(datos) != set(CAMPOS):
        faltan = [c for c in CAMPOS if c not in datos]
        sobran = sorted(set(datos) - set(CAMPOS))
        return f"debe traer exactamente {list(CAMPOS)} (faltan: {faltan}, sobran: {sobran})"
    if not isinstance(datos["vehicle_id"], str) or not datos["vehicle_id"].strip():
        return "vehicle_id debe ser un texto no vacío"
    for campo in ("latitude", "longitude", "speed", "heading"):
        if not es_numero(datos[campo]):
            return f"{campo} debe ser un número"
    if not -90 <= datos["latitude"] <= 90:
        return "latitude debe estar entre -90 y 90"
    if not -180 <= datos["longitude"] <= 180:
        return "longitude debe estar entre -180 y 180"
    if datos["speed"] < 0:
        return "speed no puede ser negativa"
    if not 0 <= datos["heading"] <= 360:
        return "heading debe estar entre 0 y 360"
    return None


def validar_config(datos, max_vehiculos, intervalo):
    """Aplica un mensaje config. Devuelve (max_vehiculos, intervalo, error)."""
    if "max_vehicles" in datos:
        n = datos["max_vehicles"]
        if n is not None and (not isinstance(n, int) or isinstance(n, bool) or n < 0):
            return max_vehiculos, intervalo, "max_vehicles debe ser un entero >= 0 (o null para todos)"
        max_vehiculos = n
    if "interval" in datos:
        s = datos["interval"]
        if not es_numero(s) or not INTERVALO_MIN_S <= s <= INTERVALO_MAX_S:
            return max_vehiculos, intervalo, f"interval debe ser un número entre {INTERVALO_MIN_S} y {INTERVALO_MAX_S}"
        intervalo = float(s)
    return max_vehiculos, intervalo, None


def enviar(ws, datos):
    ws.send(json.dumps(datos, ensure_ascii=False))


# ---------------------------------------------------------------- rutas


@app.get("/health")
def health():
    vehiculos, activos, mapas = flota.conteo()
    return jsonify(status="ok", vehicles=vehiculos, active_vehicles=activos, map_clients=mapas)


@app.errorhandler(404)
@app.errorhandler(405)
def no_existe(e):
    return jsonify(error="solo existen /ws y /health"), e.code


@sock.route("/ws")
def ws(conexion):
    rol = request.args.get("role")
    cliente = f"{request.remote_addr}:{request.environ.get('REMOTE_PORT', '?')}"
    if rol == "gps":
        atender_gps(conexion, cliente)
    elif rol == "map":
        atender_mapa(conexion, cliente)
    else:
        log.info(f"Conexión rechazada de {cliente}: role={rol!r}")
        enviar(conexion, {"type": "error", "detail": "role debe ser 'gps' o 'map'"})


def atender_gps(conexion, cliente):
    """Un camión. Solo recibe ack o error: NUNCA posiciones de otros camiones."""
    log.info(f"[gps] Conectado {cliente}")
    vehicle_id, ficha = None, None
    try:
        while True:
            crudo = conexion.receive()
            try:
                datos = json.loads(crudo)
            except (TypeError, ValueError):
                datos = None
                error = "JSON inválido"
            else:
                error = validar(datos)
            if error:
                log.warning(f"[gps] {vehicle_id or cliente}: mensaje inválido ({error}): {str(crudo)[:200]}")
                enviar(conexion, {"type": "error", "detail": error})
                continue

            if vehicle_id is None:
                # La conexión queda ligada al vehicle_id de su primer mensaje válido.
                ficha = flota.ligar(datos["vehicle_id"])
                if ficha is None:
                    detalle = f"vehicle_id '{datos['vehicle_id']}' ya está conectado desde otra GPSapp"
                    log.warning(f"[gps] {cliente} rechazado: {detalle}")
                    enviar(conexion, {"type": "error", "detail": detalle})
                    return
                vehicle_id = datos["vehicle_id"]
                log.info(f"[gps] {cliente} es el vehículo {vehicle_id}")
            elif datos["vehicle_id"] != vehicle_id:
                detalle = f"esta conexión pertenece a '{vehicle_id}', no puede mandar datos de '{datos['vehicle_id']}'"
                log.warning(f"[gps] {vehicle_id}: {detalle}")
                enviar(conexion, {"type": "error", "detail": detalle})
                continue
            elif not flota.es_dueña(vehicle_id, ficha):
                detalle = f"otra conexión tomó el vehicle_id '{vehicle_id}'"
                log.warning(f"[gps] {cliente}: {detalle}; se cierra esta conexión")
                enviar(conexion, {"type": "error", "detail": detalle})
                return

            if flota.registrar(datos):
                log.info(f"[gps] Vehículo nuevo: {vehicle_id}")
            enviar(conexion, {"type": "ack"})
    except ConnectionClosed:
        pass
    except Exception as e:  # una conexión rota nunca debe tumbar el servidor
        log.warning(f"[gps] {vehicle_id or cliente}: error en la conexión ({e.__class__.__name__}: {e})")
    finally:
        if vehicle_id is not None:
            flota.soltar(vehicle_id, ficha)
        log.info(f"[gps] Desconectado {vehicle_id or cliente}")


def atender_mapa(conexion, cliente):
    """Un mapa. Usamos WebSocket y no REST porque así el servidor EMPUJA las posiciones en
    cuanto toca enviarlas; con REST el mapa tendría que preguntar una y otra vez (polling)."""
    total = flota.cambiar_mapas(+1)
    log.info(f"[map] Conectado {cliente} ({total} mapas)")
    max_vehiculos, intervalo = None, INTERVALO_DEFECTO_S   # por defecto: todos, cada 1 s
    try:
        vehiculos, enviada = flota.lista(max_vehiculos)
        enviar(conexion, {"type": "snapshot", "vehicles": vehiculos})
        proximo = time.monotonic() + intervalo
        while True:
            # Espera mensajes del mapa hasta que toque mandar el siguiente update.
            crudo = conexion.receive(timeout=max(0.0, proximo - time.monotonic()))
            if crudo is not None:
                try:
                    datos = json.loads(crudo)
                    if not isinstance(datos, dict) or datos.get("type") != "config":
                        raise ValueError("se esperaba {\"type\":\"config\",...}")
                except ValueError as e:
                    log.warning(f"[map] {cliente}: mensaje inválido ({e})")
                    enviar(conexion, {"type": "error", "detail": str(e)})
                    continue
                max_vehiculos, intervalo, error = validar_config(datos, max_vehiculos, intervalo)
                if error:
                    log.warning(f"[map] {cliente}: config inválida ({error})")
                    enviar(conexion, {"type": "error", "detail": error})
                    continue
                log.info(f"[map] {cliente}: config max_vehicles={max_vehiculos if max_vehiculos is not None else 'todos'}, "
                         f"interval={intervalo} s")
                proximo = time.monotonic()  # aplicar ya la nueva config
                continue
            if time.monotonic() < proximo:
                continue
            # Agrupa todos los cambios del intervalo en un solo update (solo si hubo cambios).
            vehiculos, firma = flota.lista(max_vehiculos)
            if firma != enviada:
                enviar(conexion, {"type": "update", "vehicles": vehiculos})
                enviada = firma
            proximo = time.monotonic() + intervalo
    except ConnectionClosed:
        pass
    except Exception as e:
        log.warning(f"[map] {cliente}: error en la conexión ({e.__class__.__name__}: {e})")
    finally:
        total = flota.cambiar_mapas(-1)
        log.info(f"[map] Desconectado {cliente} ({total} mapas)")


threading.Thread(target=vigilar, daemon=True).start()

if __name__ == "__main__":
    log.info(f"Microservicio en ws://{HOST}:{PUERTO}/ws (health: http://localhost:{PUERTO}/health)")
    app.run(host=HOST, port=PUERTO, threaded=True)
