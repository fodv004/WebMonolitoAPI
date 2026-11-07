"""
services/rutas.py
Rutas de Monterrey. La fuente de verdad es tracking/rutas.json (mismo
formato que tools/gps_simulator/rutas.json):

    {"Centro": {"inicio": [lat, lon], "destino": [lat, lon], "por_calles": true,
                "geometria": [[lat, lon], ...]}}

`ruta_id` es la clave del JSON ("Centro", "San Pedro"...). El destino real
de un envio es el ULTIMO punto de `geometria`.
"""
import bisect
import json
import math
from functools import lru_cache
from pathlib import Path

RUTAS_JSON = Path(__file__).resolve().parents[1] / "rutas.json"
RADIO_TIERRA_M = 6_371_000


def distancia_m(a, b):
    """Distancia haversine en metros entre dos puntos (lat, lon)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(min(1.0, h)))


class Ruta:
    def __init__(self, ruta_id, puntos):
        if len(puntos) < 2:
            raise ValueError(f"La ruta {ruta_id!r} necesita al menos 2 puntos")
        self.id = ruta_id
        self.puntos = [(float(p[0]), float(p[1])) for p in puntos]
        self.acumulada = [0.0]
        for a, b in zip(self.puntos, self.puntos[1:]):
            self.acumulada.append(self.acumulada[-1] + distancia_m(a, b))
        self.distancia_m = self.acumulada[-1]

    @property
    def destino(self):
        return self.puntos[-1]

    def a_dict(self):
        return {"id": self.id, "distancia_m": round(self.distancia_m, 1),
                "inicio": list(self.puntos[0]), "destino": list(self.destino),
                "puntos": [list(p) for p in self.puntos]}

    def proyectar(self, punto, desde_m=0.0, ventana_m=None):
        """Distancia recorrida (m) del punto de la ruta mas cercano a `punto`, buscando solo en los
        tramos entre `desde_m` y `desde_m + ventana_m` (para que una ruta que se cruza consigo misma
        no haga saltar el progreso)."""
        hasta_m = self.distancia_m if ventana_m is None else desde_m + ventana_m
        inicio = max(0, bisect.bisect_right(self.acumulada, desde_m) - 1)
        mejor_d, mejor_m = None, desde_m
        lat0 = math.radians(punto[0])
        for i in range(inicio, len(self.puntos) - 1):
            if self.acumulada[i] > hasta_m:
                break
            a, b = self.puntos[i], self.puntos[i + 1]
            # Proyeccion en un plano local (equirectangular): suficiente para tramos de calle.
            ax, ay = 0.0, 0.0
            bx, by = (b[1] - a[1]) * math.cos(lat0), b[0] - a[0]
            px, py = (punto[1] - a[1]) * math.cos(lat0), punto[0] - a[0]
            largo2 = bx * bx + by * by
            t = 0.0 if largo2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / largo2))
            cercano = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            d = distancia_m(punto, cercano)
            if mejor_d is None or d < mejor_d:
                mejor_d = d
                mejor_m = self.acumulada[i] + t * (self.acumulada[i + 1] - self.acumulada[i])
        return mejor_m


@lru_cache(maxsize=1)
def _cargar():
    datos = json.loads(RUTAS_JSON.read_text(encoding="utf-8"))
    return {ruta_id: Ruta(ruta_id, info["geometria"]) for ruta_id, info in datos.items()}


def todas():
    return _cargar()


def ids():
    """Ids en el orden del archivo (estable mientras rutas.json no cambie)."""
    return list(_cargar())


def obtener(ruta_id):
    return _cargar().get(ruta_id)


def para_pedido(pedido_id):
    """Ruta asignada a un pedido: pedidos consecutivos reciben rutas distintas."""
    lista = ids()
    return lista[int(pedido_id) % len(lista)]
