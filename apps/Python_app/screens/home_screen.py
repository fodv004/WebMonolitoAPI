"""
screens/home_screen.py
Pantalla de inicio tras autenticarse: quien inicio sesion, con que rol y
que puede hacer con el.
"""
import tkinter as tk
from tkinter import ttk

from widgets import theme


class HomeScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        tarjeta = theme.tarjeta_centrada(self, "Librería en línea", "Panel de administración de los microservicios")
        self.saludo_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.saludo_var, style="Card.TLabel", font=theme.FUENTE_SUBTITULO).grid(
            row=3, column=0, columnspan=2, sticky="w")
        self.detalle_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.detalle_var, style="Card.TLabel", justify="left", wraplength=420).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(tarjeta, style="Subtitulo.TLabel", justify="left", wraplength=420,
                  text="Usa el menú lateral para navegar. El panel superior muestra el estado de los "
                       "6 servicios (verde = funcional, rojo = no funcional).").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(14, 0))

    def on_show(self):
        usuario = self.app.sesion.usuario or {}
        self.saludo_var.set(f"Hola, {usuario.get('nombre') or 'usuario'}")
        permisos = ("Puedes consultar y modificar el catálogo." if self.app.sesion.es_admin
                    else "Puedes consultar el catálogo; modificarlo requiere rol admin.")
        self.detalle_var.set(f"Correo: {usuario.get('email', '—')}\n"
                             f"Rol: {usuario.get('role', '—')} (role_id {usuario.get('role_id', '—')})\n"
                             f"{permisos}")
