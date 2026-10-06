"""
widgets/tooltip.py
Globo de ayuda que aparece al pasar el mouse sobre un widget. El texto se
calcula al mostrarlo (texto_fn), asi siempre refleja el ultimo estado.
"""
import tkinter as tk

from widgets import theme

RETARDO_MS = 350


class Tooltip:
    def __init__(self, widget, texto_fn):
        self.widget = widget
        self.texto_fn = texto_fn
        self._ventana = None
        self._pendiente = None
        widget.bind("<Enter>", self._programar, add="+")
        widget.bind("<Leave>", self._ocultar, add="+")
        widget.bind("<ButtonPress>", self._ocultar, add="+")

    def _programar(self, _evento=None):
        self._cancelar()
        self._pendiente = self.widget.after(RETARDO_MS, self._mostrar)

    def _cancelar(self):
        if self._pendiente is not None:
            self.widget.after_cancel(self._pendiente)
            self._pendiente = None

    def _mostrar(self):
        self._pendiente = None
        texto = self.texto_fn()
        if not texto or self._ventana is not None:
            return
        self._ventana = tk.Toplevel(self.widget)
        self._ventana.wm_overrideredirect(True)
        self._ventana.wm_geometry(
            f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 6}")
        tk.Label(self._ventana, text=texto, justify="left", font=theme.FUENTE_PEQUENA,
                 background=theme.COLOR_TEXTO, foreground=theme.COLOR_TEXTO_CLARO, padx=10, pady=7).pack()

    def _ocultar(self, _evento=None):
        self._cancelar()
        if self._ventana is not None:
            self._ventana.destroy()
            self._ventana = None
