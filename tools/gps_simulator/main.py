"""GPSapp: simula UN camión que envía su posición al microservicio por WebSocket.

    python main.py

Cada ventana es un camión independiente; para tener varios, abre main.py varias veces.
Todo se maneja desde la ventana: elegir o crear la ruta, la velocidad e Iniciar/Detener.
"""

import json
import socket
import sys
import threading
import time
import uuid

import webview
import websocket  # paquete websocket-client

from rutas import ErrorRuta, Ruta, calcular_camino, cargar_rutas, guardar_ruta
from simulacion import VELOCIDADES_KMH, SimuladorCamion

URL_SERVIDOR = "ws://localhost:5900/ws?role=gps"
INTERVALO_S = 1.0
TIMEOUT_S = 5
ESPERA_MAX_S = 10
PUERTO_IDS = 47100  # V001 ocupa 127.0.0.1:47101, V002 47102, ...


def log(vehicle_id, texto):
    print(f"[{time.strftime('%H:%M:%S')}] [{vehicle_id}] {texto}", flush=True)


def reservar_id():
    """Primer ID libre (V001, V002...) entre las ventanas abiertas en esta computadora.

    Cada ventana se queda con un puerto local mientras vive; el sistema lo libera solo
    al cerrarla (aunque se cierre a la fuerza), así el ID vuelve a quedar libre.
    """
    for n in range(1, 1000):
        candado = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            candado.bind(("127.0.0.1", PUERTO_IDS + n))
            return f"V{n:03d}", candado
        except OSError:
            candado.close()
    return f"V-{uuid.uuid4().hex[:6].upper()}", None


class Conexion:
    """WebSocket con reconexión automática y espera creciente entre intentos."""

    def __init__(self, url, vehicle_id):
        self.url = url
        self.vehicle_id = vehicle_id
        self.ws = None
        self.espera = 1
        self.proximo_intento = 0.0

    def conectada(self):
        """Intenta conectar si toca hacerlo. Devuelve True si hay conexión."""
        if self.ws is not None:
            return True
        if time.monotonic() < self.proximo_intento:
            return False
        try:
            self.ws = websocket.create_connection(self.url, timeout=TIMEOUT_S)
            log(self.vehicle_id, f"Conectado a {self.url}")
            self.espera = 1
            return True
        except Exception as e:
            log(self.vehicle_id, f"No se pudo conectar ({e.__class__.__name__}: {e})")
            self.fallo()
            return False

    def fallo(self):
        """Descarta la conexión actual y programa el siguiente intento."""
        self.cerrar()
        self.proximo_intento = time.monotonic() + self.espera
        log(self.vehicle_id, f"Reintentando conexión en {self.espera}s...")
        self.espera = min(self.espera * 2, ESPERA_MAX_S)

    def enviar(self, mensaje):
        """Envía el mensaje y devuelve la respuesta del servidor ya decodificada."""
        self.ws.send(json.dumps(mensaje))
        return json.loads(self.ws.recv())

    def cerrar(self):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None


class Api:
    """Métodos que la página llama con window.pywebview.api.<método>.

    Los atributos empiezan con "_" para que pywebview no los exponga a la página.
    """

    def __init__(self, vehicle_id):
        self._id_sugerido = vehicle_id
        self._ventana = None
        self._candado = threading.Lock()
        self._parar = threading.Event()
        self._hilo = None
        self._velocidad = "normal"
        self._estado = self._estado_vacio()

    @staticmethod
    def _estado_vacio():
        return {"andando": False, "conectado": False, "speed": None, "servidor": None,
                "posicion": None, "n": 0}

    # -- llamadas desde la página

    def inicio(self):
        return {"vehicle_id": self._id_sugerido, "rutas": cargar_rutas(), "velocidad": self._velocidad}

    def calcular_ruta(self, inicio, destino):
        geometria, por_calles = calcular_camino(inicio, destino)
        return {"geometria": geometria, "por_calles": por_calles}

    def guardar_ruta(self, nombre, inicio, destino, geometria, por_calles):
        try:
            rutas = guardar_ruta(nombre, inicio, destino, geometria, por_calles)
        except ErrorRuta as e:
            return {"ok": False, "mensaje": str(e)}
        return {"ok": True, "mensaje": f"Ruta '{nombre.strip()}' guardada.", "rutas": rutas}

    def cambiar_velocidad(self, velocidad):
        if velocidad in VELOCIDADES_KMH:
            self._velocidad = velocidad

    def iniciar(self, vehicle_id, nombre_ruta):
        vehicle_id = (vehicle_id or "").strip()
        if not vehicle_id:
            return {"ok": False, "mensaje": "Escribe el ID del camión."}
        if self._hilo is not None:
            return {"ok": False, "mensaje": "El camión ya está andando."}
        datos = cargar_rutas().get(nombre_ruta)
        if datos is None:
            return {"ok": False, "mensaje": "Elige una ruta guardada."}
        try:
            ruta = Ruta(nombre_ruta, datos["geometria"])
        except ErrorRuta as e:
            return {"ok": False, "mensaje": str(e)}

        with self._candado:
            self._estado = {**self._estado_vacio(), "andando": True}
        self._parar.clear()
        self._hilo = threading.Thread(target=self._correr, args=(vehicle_id, ruta), daemon=True)
        self._hilo.start()
        if self._ventana is not None:
            self._ventana.set_title(f"GPSapp - Camión {vehicle_id}")
        log(vehicle_id, f"Iniciado en la ruta '{ruta.nombre}' ({ruta.largo / 1000:.1f} km)")
        return {"ok": True}

    def detener(self):
        hilo, self._hilo = self._hilo, None
        if hilo is None:
            return
        self._parar.set()
        hilo.join(timeout=TIMEOUT_S + 2)
        with self._candado:
            self._estado.update(andando=False, conectado=False, speed=None)

    def estado(self):
        with self._candado:
            return dict(self._estado)

    # -- hilo del camión

    def _correr(self, vehicle_id, ruta):
        simulador = SimuladorCamion(ruta, self._velocidad)
        conexion = Conexion(URL_SERVIDOR, vehicle_id)
        ultimo = time.monotonic()
        try:
            while not self._parar.is_set():
                inicio = time.monotonic()
                simulador.velocidad = self._velocidad
                posicion = simulador.avanzar(inicio - ultimo)
                ultimo = inicio
                # Exactamente los 5 campos del contrato.
                mensaje = {"vehicle_id": vehicle_id, **posicion}

                servidor = None
                if conexion.conectada():
                    try:
                        respuesta = conexion.enviar(mensaje)
                        if respuesta.get("type") == "ack":
                            servidor = "ack"
                        elif respuesta.get("type") == "error":
                            servidor = f"error: {respuesta.get('detail', '')}"
                            log(vehicle_id, f"Enviado {json.dumps(mensaje)} -> {servidor}")
                        else:
                            servidor = "respuesta desconocida"
                            log(vehicle_id, f"Respuesta inesperada: {respuesta}")
                    except (websocket.WebSocketException, OSError, ValueError, AttributeError) as e:
                        log(vehicle_id, f"Conexión perdida ({e.__class__.__name__}: {e})")
                        conexion.fallo()

                with self._candado:
                    self._estado.update(conectado=conexion.ws is not None, speed=posicion["speed"],
                                        posicion=posicion, n=self._estado["n"] + 1)
                    if servidor:
                        self._estado["servidor"] = servidor

                self._parar.wait(max(0.0, INTERVALO_S - (time.monotonic() - inicio)))
        finally:
            conexion.cerrar()
            log(vehicle_id, "Detenido y desconectado.")


def main():
    vehicle_id, candado = reservar_id()
    api = Api(vehicle_id)
    api._ventana = webview.create_window(
        f"GPSapp - Camión {vehicle_id}", url="mapa.html", js_api=api,
        width=1200, height=760, min_size=(800, 520),
    )
    # http_server: la página se sirve por http://127.0.0.1 y no como file://; así los
    # tiles de OpenStreetMap reciben Referer y no responden "403 Access blocked".
    webview.start(http_server=True)
    api.detener()  # la ventana se cerró: detener y desconectar limpio
    if candado is not None:
        candado.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
