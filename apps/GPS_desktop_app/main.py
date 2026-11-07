"""Mapa de la flota (Proyecto 3): todos los camiones en tiempo real.

    python main.py

La página (mapa.html) se conecta como cliente a ws://localhost:5900/ws?role=map y recibe
snapshot/update del microservicio. Python solo abre la ventana y consulta /health para
saber cuántos camiones hay conectados en total (la página no puede leer /health directo
porque el microservicio no manda cabeceras CORS).
"""

import json
import sys
import urllib.request

import webview

# 127.0.0.1 y no localhost: el microservicio escucha en IPv4 y en Windows "localhost"
# prueba primero IPv6, lo que añade ~2 s a cada consulta.
HEALTH_URL = "http://127.0.0.1:5900/health"


class Api:
    """Métodos que la página llama con window.pywebview.api.<método>."""

    def health(self):
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                return json.load(r)
        except Exception:
            return None


def main():
    webview.create_window("Mapa de la flota", url="mapa.html", js_api=Api(),
                          width=1280, height=800, min_size=(800, 520))
    # http_server: la página se sirve por http://127.0.0.1 y no como file://; así los
    # tiles de OpenStreetMap reciben Referer y no responden "403 Access blocked".
    webview.start(http_server=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
