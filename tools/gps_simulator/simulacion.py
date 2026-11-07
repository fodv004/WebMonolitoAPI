"""Movimiento simple de un camión sobre una Ruta.

Avanza a la velocidad base elegida (con una pequeña variación aleatoria), frena un
poco antes de las vueltas cerradas y, al llegar al destino, regresa por la misma ruta.
De aquí salen latitude, longitude, speed y heading.
"""

import bisect
import math
import random

VELOCIDADES_KMH = {"lenta": 30, "normal": 50, "rapida": 70}

ACELERACION = 0.8       # m/s²
FRENADO = 1.5           # m/s²
SUBPASO_S = 0.2
DT_MAX_S = 5.0
PAUSA_DESTINO_S = 2.0   # se detiene un momento antes de dar la vuelta


class SimuladorCamion:
    def __init__(self, ruta, velocidad="normal", rng=None):
        self.ruta = ruta
        self.rng = rng or random.Random()
        self.velocidad = velocidad
        self.s = 0.0          # metros recorridos desde el inicio de la ruta
        self.dir = 1          # 1 = hacia el destino, -1 = de regreso
        self.v = 0.0          # m/s
        self.variacion = 1.0  # cambia poco a poco entre 0.92 y 1.06
        self.pausa = 0.0

    @property
    def v_base(self):
        return VELOCIDADES_KMH[self.velocidad] / 3.6

    def _v_permitida(self, v_obj):
        """Velocidad máxima ahora para poder frenar a tiempo en vueltas y al final."""
        ruta = self.ruta
        v = v_obj
        d_fin = ruta.largo - self.s if self.dir > 0 else self.s
        v = min(v, math.sqrt(2 * FRENADO * d_fin) + 0.5)
        alcance = v_obj ** 2 / (2 * FRENADO) + 20
        lo, hi = (self.s, self.s + alcance) if self.dir > 0 else (self.s - alcance, self.s)
        i, j = bisect.bisect_left(ruta.vueltas_s, lo), bisect.bisect_right(ruta.vueltas_s, hi)
        for s_v, angulo in ruta.vueltas[i:j]:
            # Vuelta de 90° o más: a la mitad de la velocidad base; menos cerrada, menos freno.
            v_vuelta = v_obj * (1 - 0.5 * min(angulo, 90) / 90)
            v = min(v, math.sqrt(v_vuelta ** 2 + 2 * FRENADO * abs(s_v - self.s)))
        return v

    def _paso(self, h):
        if self.pausa > 0:
            self.pausa -= h
            self.v = 0.0
            return
        self.variacion = min(1.06, max(0.92, self.variacion + self.rng.gauss(0, 0.015) * math.sqrt(h)))
        v_perm = self._v_permitida(self.v_base * self.variacion)
        if self.v < v_perm:
            self.v = min(v_perm, self.v + ACELERACION * h)
        else:
            self.v = max(v_perm, self.v - FRENADO * h)

        self.s += self.dir * self.v * h
        if not 0.0 < self.s < self.ruta.largo:  # llegó a un extremo: da la vuelta
            self.s = min(self.ruta.largo, max(0.0, self.s))
            self.dir = -self.dir
            self.v = 0.0
            self.pausa = PAUSA_DESTINO_S

    def avanzar(self, dt):
        """Avanza dt segundos y devuelve latitude, longitude, speed (km/h) y heading."""
        dt = min(max(dt, 0.0), DT_MAX_S)
        pasos = max(1, math.ceil(dt / SUBPASO_S))
        for _ in range(pasos):
            self._paso(dt / pasos)
        lat, lng = self.ruta.punto(self.s)
        return {
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
            "speed": round(self.v * 3.6, 1),
            "heading": round(self.ruta.rumbo(self.s, self.dir), 1) % 360,
        }
