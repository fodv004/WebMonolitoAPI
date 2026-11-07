"""Simulador de envios (sin ventana) para el microservicio tracking.

Cada CONSULTA_SEGUNDOS pide a tracking los envios activos:

    GET {TRACKING_URL}/envios/internal/activos        header X-Internal-Key

y por cada envio nuevo arranca un hilo que recorre los puntos de SU ruta (la
manda tracking, que es la fuente de verdad de rutas.json) enviando posiciones a

    {TRACKING_WS_URL}   (ws://.../ws?role=gps, header X-Internal-Key)
    {"vehicle_id": "<codigo>", "latitude", "longitude", "speed", "heading"}

y en el ultimo punto de la ruta agrega "final": true (tracking lo marca
ENTREGADO solo si esa posicion queda a menos de 30 m del destino).

Configuracion en tools/gps_simulator/.env (ver .env.example). Uso:

    python simulador_envios.py

El modo de prueba local de siempre (main.py + servidor_prueba.py) no cambia.
"""
import bisect
import json
import logging
import math
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import websocket  # paquete websocket-client
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

TRACKING_URL = os.getenv("TRACKING_URL", "http://127.0.0.1:5900").rstrip("/")
TRACKING_WS_URL = os.getenv("TRACKING_WS_URL", "ws://127.0.0.1:5900/ws?role=gps")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "").strip()
CONSULTA_SEGUNDOS = float(os.getenv("CONSULTA_SEGUNDOS", "5"))
DURACION_RUTA_SEGUNDOS = float(os.getenv("DURACION_RUTA_SEGUNDOS", "150"))   # 2.5 min por ruta en la demo
ENVIO_SEGUNDOS = float(os.getenv("ENVIO_SEGUNDOS", "1"))                     # una posicion por segundo
TIMEOUT_HTTP_S = 5
ERRORES_DEFINITIVOS = {"ENVIO_NO_ENCONTRADO", "ENVIO_NO_ACTIVO", "CLAVE_INTERNA_INVALIDA", "VALIDACION"}
RADIO_TIERRA_M = 6_371_000

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(threadName)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("simulador")


# ---------------------------------------------------------------- geometria
def distancia_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(min(1.0, h)))


def rumbo_grados(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    x = math.sin(lon2 - lon1) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


class Trazo:
    """Puntos de la ruta con distancia acumulada, para interpolar la posicion a X metros del inicio."""

    def __init__(self, puntos):
        self.puntos = [(float(p[0]), float(p[1])) for p in puntos]
        self.acumulada = [0.0]
        for a, b in zip(self.puntos, self.puntos[1:]):
            self.acumulada.append(self.acumulada[-1] + distancia_m(a, b))
        self.total = self.acumulada[-1]

    def en(self, metros):
        """(lat, lon, rumbo) a `metros` del inicio."""
        metros = max(0.0, min(self.total, metros))
        i = max(0, min(len(self.puntos) - 2, bisect.bisect_right(self.acumulada, metros) - 1))
        a, b = self.puntos[i], self.puntos[i + 1]
        tramo = self.acumulada[i + 1] - self.acumulada[i]
        t = 0.0 if tramo == 0 else (metros - self.acumulada[i]) / tramo
        return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]), rumbo_grados(a, b)


# ---------------------------------------------------------------- un envio
class Recorrido(threading.Thread):
    def __init__(self, envio):
        super().__init__(name=envio["codigo"], daemon=True)
        self.codigo = envio["codigo"]
        self.trazo = Trazo(envio["ruta"]["puntos"])
        # Si el simulador se reinicia, sigue donde iba (progreso que guardo tracking).
        self.metros = float(envio.get("progreso") or 0) * self.trazo.total
        self.velocidad_mps = self.trazo.total / max(DURACION_RUTA_SEGUNDOS, 1)
        self.ws = None
        self.terminado = False

    def _conectar(self):
        espera = 1
        while self.ws is None:
            try:
                self.ws = websocket.create_connection(TRACKING_WS_URL, header=[f"X-Internal-Key: {INTERNAL_API_KEY}"],
                                                      timeout=10)
            except Exception as e:
                log.warning("No se pudo conectar a %s (%s); reintento en %s s", TRACKING_WS_URL, type(e).__name__, espera)
                time.sleep(espera)
                espera = min(espera * 2, 10)

    def _mandar(self, lat, lon, speed, heading, final=False):
        """Manda una posicion y devuelve la respuesta de tracking (ack o error)."""
        mensaje = {"vehicle_id": self.codigo, "latitude": round(lat, 6), "longitude": round(lon, 6),
                   "speed": round(speed, 1), "heading": round(heading, 1)}
        if final:
            mensaje["final"] = True
        while True:
            self._conectar()
            try:
                self.ws.send(json.dumps(mensaje))
                return json.loads(self.ws.recv())
            except Exception as e:
                log.warning("Conexion perdida (%s); reconectando", type(e).__name__)
                try:
                    self.ws.close()
                except Exception:
                    pass
                self.ws = None

    def run(self):
        log.info("Inicia recorrido: %.0f m en ~%.0f s (desde %.0f%%)", self.trazo.total, DURACION_RUTA_SEGUNDOS,
                 100 * self.metros / self.trazo.total)
        try:
            while True:
                final = self.metros >= self.trazo.total
                lat, lon, rumbo = self.trazo.en(self.metros)
                speed_kmh = 0.0 if final else self.velocidad_mps * 3.6
                respuesta = self._mandar(lat, lon, speed_kmh, rumbo, final=final)
                if respuesta.get("type") == "error":
                    codigo_error = respuesta.get("error")
                    log.warning("tracking respondio %s: %s", codigo_error, respuesta.get("detail"))
                    if codigo_error in ERRORES_DEFINITIVOS:
                        return
                elif respuesta.get("estado") == "ENTREGADO":
                    log.info("ENTREGADO")
                    return
                elif final:
                    log.warning("Posicion final sin entrega: %s", respuesta.get("detail"))
                    return
                time.sleep(ENVIO_SEGUNDOS)
                self.metros += self.velocidad_mps * ENVIO_SEGUNDOS
        finally:
            self.terminado = True
            if self.ws is not None:
                try:
                    self.ws.close()
                except Exception:
                    pass


# ---------------------------------------------------------------- bucle principal
def consultar_activos():
    peticion = urllib.request.Request(f"{TRACKING_URL}/envios/internal/activos",
                                      headers={"X-Internal-Key": INTERNAL_API_KEY, "Accept": "application/json"})
    with urllib.request.urlopen(peticion, timeout=TIMEOUT_HTTP_S) as r:
        return json.loads(r.read().decode("utf-8"))["items"]


def main():
    if not INTERNAL_API_KEY:
        raise SystemExit("ERROR: define INTERNAL_API_KEY en tools/gps_simulator/.env (la misma que tracking).")
    log.info("Simulador de envios: %s (cada %s s), ruta en ~%s s", TRACKING_URL, CONSULTA_SEGUNDOS,
             DURACION_RUTA_SEGUNDOS)
    hilos = {}
    while True:
        try:
            envios = consultar_activos()
        except urllib.error.HTTPError as e:
            log.warning("GET /envios/internal/activos respondio HTTP %s", e.code)
            envios = []
        except Exception as e:
            log.warning("tracking no responde (%s)", type(e).__name__)
            envios = []
        for codigo in [c for c, hilo in hilos.items() if hilo.terminado]:
            del hilos[codigo]
        for envio in envios:
            if envio["codigo"] not in hilos and envio.get("ruta"):
                hilos[envio["codigo"]] = Recorrido(envio)
                hilos[envio["codigo"]].start()
        time.sleep(CONSULTA_SEGUNDOS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Simulador detenido")
