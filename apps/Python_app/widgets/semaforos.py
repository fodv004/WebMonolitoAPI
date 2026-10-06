"""
widgets/semaforos.py
Panel de semaforos, siempre visible: una luz por microservicio (login,
books, users, authors, pedidos, pagos).

  Verde  -> GET /health respondio 200 con status "ok".
  Rojo   -> cualquier otro caso (sin respuesta, timeout, 503, status distinto).
  Gris   -> todavia no se ha revisado.

Cada revision corre en su propio hilo y el resultado regresa al hilo de
Tkinter con after(): la ventana nunca se congela. El ciclo se repite con
root.after() cada `semaforo_intervalo_s` (10 s por defecto) y el boton
"Revisar ahora" lo adelanta. Al pasar el mouse sobre una luz se muestra el
detalle: db, redis, tiempo de respuesta y ultima revision.
"""
import tkinter as tk
from tkinter import ttk

from api import health
from config.settings import ETIQUETAS, SERVICIOS
from utils import run_async
from widgets import theme
from widgets.tooltip import Tooltip

_DIAMETRO = 14


class SemaforoPanel(tk.Frame):
    def __init__(self, parent, config):
        super().__init__(parent, background=theme.COLOR_SUPERFICIE, padx=14, pady=6,
                         highlightthickness=1, highlightbackground=theme.COLOR_BORDE)
        self.config_app = config
        self.resultados = {}          # servicio -> ultimo resultado de health.revisar
        self._en_curso = set()        # servicios con una revision todavia sin responder
        self._after_id = None
        self._luces = {}
        self._oyentes = []            # funciones(servicio, ok) avisadas tras cada revision

        tk.Label(self, text="Servicios", font=theme.FUENTE_NEGRITA, background=theme.COLOR_SUPERFICIE,
                 foreground=theme.COLOR_TEXTO).pack(side="left", padx=(0, 14))

        for servicio in SERVICIOS:
            marco = tk.Frame(self, background=theme.COLOR_SUPERFICIE)
            marco.pack(side="left", padx=(0, 16))
            lienzo = tk.Canvas(marco, width=_DIAMETRO + 2, height=_DIAMETRO + 2, highlightthickness=0,
                               background=theme.COLOR_SUPERFICIE)
            luz = lienzo.create_oval(1, 1, _DIAMETRO + 1, _DIAMETRO + 1, fill=theme.COLOR_BORDE, outline="")
            lienzo.pack(side="left")
            etiqueta = tk.Label(marco, text=ETIQUETAS[servicio], font=theme.FUENTE_NORMAL,
                                background=theme.COLOR_SUPERFICIE, foreground=theme.COLOR_TEXTO)
            etiqueta.pack(side="left", padx=(5, 0))
            self._luces[servicio] = (lienzo, luz)
            for widget in (marco, lienzo, etiqueta):
                Tooltip(widget, lambda s=servicio: self._detalle(s))

        ttk.Button(self, text="Revisar ahora", command=self.revisar_ahora).pack(side="right")
        self._ultima_var = tk.StringVar(value="Sin revisar")
        tk.Label(self, textvariable=self._ultima_var, font=theme.FUENTE_PEQUENA,
                 background=theme.COLOR_SUPERFICIE, foreground=theme.COLOR_TEXTO_SUAVE).pack(side="right", padx=10)

    # ------------------------------------------------------------ estado para las pantallas
    def al_cambiar(self, funcion):
        """Registra funcion(servicio, ok): se llama (en el hilo de Tk) tras cada revision."""
        self._oyentes.append(funcion)

    def en_rojo(self, servicio):
        """True solo si la ultima revision de ese servicio fallo (sin revisar todavia = False)."""
        resultado = self.resultados.get(servicio)
        return resultado is not None and not resultado["ok"]

    # ------------------------------------------------------------ ciclo
    def iniciar(self):
        self.revisar_ahora()

    def revisar_ahora(self):
        """Revisa los 6 servicios ya y reprograma el siguiente ciclo (tambien tras cambiar la configuracion)."""
        if self._after_id is not None:
            self.after_cancel(self._after_id)
        self._ciclo()

    def _ciclo(self):
        timeout = self.config_app["semaforo_timeout_s"]
        for servicio in SERVICIOS:
            if servicio in self._en_curso:
                continue                      # la revision anterior aun no responde
            self._en_curso.add(servicio)
            run_async(self, lambda s=servicio: health.revisar(self.config_app, s, timeout),
                      self._recibir, lambda _e, s=servicio: self._en_curso.discard(s))
        self._after_id = self.after(self.config_app["semaforo_intervalo_s"] * 1000, self._ciclo)

    def _recibir(self, resultado):
        servicio = resultado["servicio"]
        self._en_curso.discard(servicio)
        self.resultados[servicio] = resultado
        lienzo, luz = self._luces[servicio]
        lienzo.itemconfigure(luz, fill=theme.COLOR_EXITO if resultado["ok"] else theme.COLOR_PELIGRO)
        self._ultima_var.set(f"Última revisión: {resultado['hora']:%H:%M:%S}")
        for oyente in self._oyentes:
            oyente(servicio, resultado["ok"])

    # ------------------------------------------------------------ detalle
    def _detalle(self, servicio):
        r = self.resultados.get(servicio)
        if r is None:
            return f"{ETIQUETAS[servicio]} ({servicio})\nTodavía sin revisar."
        if r["ok"]:
            estado = "Funcional"
        elif r["status"] is not None:
            estado = f"No funcional (HTTP {r['status']})"
        else:
            estado = f"No funcional ({r['error']})"
        return "\n".join([
            f"{ETIQUETAS[servicio]} ({servicio})",
            r["url"],
            f"Estado: {estado}",
            f"Base de datos: {r['db'] or '—'}",
            f"Redis: {r['redis'] or '—'}",
            f"Tiempo de respuesta: {r['ms']} ms",
            f"Última revisión: {r['hora']:%H:%M:%S}",
        ])
