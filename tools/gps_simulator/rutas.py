"""Rutas del camión: geometría, rutas.json y cálculo del camino por calles con OSRM.

Formato de rutas.json (la clave es el nombre que se ve en la lista):

    {
      "Centro": {
        "inicio": [25.664466, -100.315131],
        "destino": [25.672804, -100.287269],
        "por_calles": true,
        "geometria": [[25.664466, -100.315131], ...]
      }
    }
"""

import bisect
import json
import math
import re
import urllib.request
from pathlib import Path

RUTAS_JSON = Path(__file__).with_name("rutas.json")
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/"
USER_AGENT = "GPSapp-simulador-camion/2.0"
TIMEOUT_OSRM_S = 10
RADIO_TIERRA_M = 6_371_000


class ErrorRuta(Exception):
    """Error con un mensaje pensado para mostrarse tal cual al usuario."""


# ---------------------------------------------------------------- geometría


def distancia_m(a, b):
    """Distancia haversine en metros entre dos puntos (lat, lng)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(math.sqrt(h))


def rumbo_grados(a, b):
    """Rumbo de a hacia b en grados [0, 360), 0 = norte, sentido horario."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def diferencia_angulo(a, b):
    """Diferencia absoluta entre dos rumbos, en [0, 180]."""
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


class Ruta:
    """Línea de la ruta con distancia acumulada y las vueltas cerradas que tiene."""

    VENTANA_VUELTA_M = 15.0   # mide el giro entre 15 m antes y 15 m después de cada vértice
    ANGULO_VUELTA = 35.0      # a partir de este giro se considera vuelta cerrada

    def __init__(self, nombre, geometria):
        self.nombre = nombre
        # Quita puntos repetidos y arma la distancia acumulada.
        self.geom, self.acum = [tuple(geometria[0])], [0.0]
        for p in geometria[1:]:
            d = distancia_m(self.geom[-1], p)
            if d >= 0.05:
                self.geom.append(tuple(p))
                self.acum.append(self.acum[-1] + d)
        if len(self.geom) < 2:
            raise ErrorRuta(f"La ruta '{nombre}' necesita un inicio y un destino distintos.")
        self.largo = self.acum[-1]
        self.rumbo_seg = [rumbo_grados(a, b) for a, b in zip(self.geom, self.geom[1:])]
        self.vueltas = self._vueltas()
        self.vueltas_s = [s for s, _ in self.vueltas]

    def segmento(self, s, direccion=1):
        """Índice del segmento en el que está s según el sentido de avance."""
        if direccion > 0:
            i = bisect.bisect_right(self.acum, s) - 1
        else:
            i = bisect.bisect_left(self.acum, s) - 1
        return max(0, min(len(self.acum) - 2, i))

    def punto(self, s):
        i = self.segmento(s)
        a, b = self.geom[i], self.geom[i + 1]
        f = (s - self.acum[i]) / (self.acum[i + 1] - self.acum[i])
        return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f

    def rumbo(self, s, direccion=1):
        r = self.rumbo_seg[self.segmento(s, direccion)]
        return r if direccion > 0 else (r + 180) % 360

    def _vueltas(self):
        """Lista (s, ángulo) de los vértices donde la ruta da una vuelta cerrada."""
        vueltas = []
        v = self.VENTANA_VUELTA_M
        for k in range(1, len(self.geom) - 1):
            s = self.acum[k]
            antes = self.rumbo_seg[self.segmento(max(0.0, s - v))]
            despues = self.rumbo_seg[self.segmento(min(self.largo, s + v))]
            angulo = diferencia_angulo(antes, despues)
            if angulo >= self.ANGULO_VUELTA and not (vueltas and s - vueltas[-1][0] < v):
                vueltas.append((s, angulo))
        return vueltas


# ---------------------------------------------------------------- OSRM


def calcular_camino(inicio, destino):
    """Camino por calles entre inicio y destino. Devuelve (geometría, por_calles).

    Si OSRM no responde o no encuentra camino, devuelve la línea recta y por_calles=False.
    """
    coords = f"{inicio[1]},{inicio[0]};{destino[1]},{destino[0]}"
    url = f"{OSRM_URL}{coords}?overview=full&geometries=geojson"
    try:
        peticion = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_OSRM_S) as r:
            datos = json.load(r)
        if datos.get("code") != "Ok" or not datos.get("routes"):
            raise ValueError(datos.get("code"))
        geometria = [[round(lat, 6), round(lng, 6)] for lng, lat in datos["routes"][0]["geometry"]["coordinates"]]
        if len(geometria) >= 2:
            return geometria, True
    except Exception as e:
        print(f"OSRM no respondió ({e.__class__.__name__}: {e}); se usa línea recta.", flush=True)
    return [list(inicio), list(destino)], False


# ---------------------------------------------------------------- archivo


def cargar_rutas(archivo=RUTAS_JSON):
    """Lee rutas.json. Devuelve {nombre: datos}; las rutas dañadas se omiten con aviso."""
    archivo = Path(archivo)
    if not archivo.exists():
        return {}
    try:
        crudas = json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"AVISO: no se pudo leer {archivo.name}: {e}", flush=True)
        return {}
    rutas = {}
    for nombre, datos in crudas.items() if isinstance(crudas, dict) else ():
        try:
            Ruta(nombre, datos["geometria"])
            rutas[nombre] = datos
        except (ErrorRuta, KeyError, TypeError, ValueError, IndexError):
            print(f"AVISO: la ruta '{nombre}' de {archivo.name} está dañada y se omitió.", flush=True)
    return rutas


def guardar_ruta(nombre, inicio, destino, geometria, por_calles, archivo=RUTAS_JSON):
    """Agrega una ruta a rutas.json (vuelve a leer el archivo por si otra ventana guardó)."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorRuta("Escribe un nombre para la ruta.")
    Ruta(nombre, geometria)  # valida
    rutas = cargar_rutas(archivo)
    if nombre in rutas:
        raise ErrorRuta(f"Ya existe una ruta llamada '{nombre}'. Usa otro nombre.")
    rutas[nombre] = {"inicio": list(inicio), "destino": list(destino),
                     "por_calles": bool(por_calles), "geometria": [list(p) for p in geometria]}
    texto = json.dumps(rutas, ensure_ascii=False, indent=2)
    texto = re.sub(r"\[\s+(-?[\d.]+),\s+(-?[\d.]+)\s+\]", r"[\1, \2]", texto)  # [lat, lng] en una línea
    Path(archivo).write_text(texto + "\n", encoding="utf-8")
    return rutas
