"""
screens/placeholder_screen.py
Pantalla "En construcción" de los microservicios que en la Parte 1 solo
tienen su ambiente base (Autores, Usuarios, Pedidos y Pagos).
"""
import tkinter as tk
from tkinter import ttk

from config.settings import ETIQUETAS
from widgets import theme


class PlaceholderScreen(ttk.Frame):
    def __init__(self, parent, app, servicio, descripcion):
        super().__init__(parent)
        self.app = app
        self.servicio = servicio

        tarjeta = theme.tarjeta_centrada(self, ETIQUETAS[servicio], descripcion)
        ttk.Label(tarjeta, text="En construcción", style="Card.TLabel", font=theme.FUENTE_TITULO,
                  foreground=theme.COLOR_ADVERTENCIA).grid(row=3, column=0, columnspan=2, sticky="w")
        self.url_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.url_var, style="Subtitulo.TLabel", justify="left", wraplength=420).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def on_show(self):
        self.url_var.set(f"El microservicio ya responde /health y /metrics en\n"
                         f"{self.app.config_app.base_url(self.servicio)}\n"
                         "Su CRUD se agrega en las siguientes partes del proyecto.")
