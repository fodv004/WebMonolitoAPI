"""
ui/login_screen.py
Pantalla de inicio de sesion: pide correo/contraseña al microservicio
de login (POST /login) y, si son correctos, guarda en memoria el JWT de
data.token y pasa al catalogo.
"""
import tkinter as tk
from tkinter import ttk

from api_client import ApiError
from ui import theme
from utils import run_async


class LoginScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        tarjeta = theme.tarjeta_centrada(self, "Iniciar sesión", "Accede al catálogo de la librería")

        self.email_var = tk.StringVar()
        entrada_email = theme.campo(tarjeta, 3, "Correo", self.email_var)
        entrada_email.bind("<Return>", lambda e: self._login())

        self.password_var = tk.StringVar()
        entrada_password = theme.campo(tarjeta, 4, "Contraseña", self.password_var, show="•")
        entrada_password.bind("<Return>", lambda e: self._login())

        self.estado_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.estado_var, style="Error.TLabel", wraplength=340).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.boton_login = ttk.Button(tarjeta, text="Iniciar sesión", style="Primary.TButton", command=self._login)
        self.boton_login.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 8))

        secundarios = ttk.Frame(tarjeta, style="CardInner.TFrame")
        secundarios.grid(row=7, column=0, columnspan=2, sticky="ew")
        secundarios.grid_columnconfigure((0, 1), weight=1, uniform="sec")
        ttk.Button(secundarios, text="Crear cuenta", command=lambda: app.mostrar("register")).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(secundarios, text="Configuración", command=lambda: app.mostrar("config")).grid(
            row=0, column=1, sticky="ew", padx=(4, 0))

    def on_show(self):
        self.estado_var.set("")

    def _login(self):
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not email or not password:
            self.estado_var.set("Ingresa correo y contraseña.")
            return
        self.estado_var.set("Conectando...")
        self.boton_login.state(["disabled"])

        def hacer():
            return self.app.auth.login(email, password)

        def ok(respuesta):
            self.boton_login.state(["!disabled"])
            datos = respuesta.get("data") or {}
            if not datos.get("authenticated") or not datos.get("token"):
                self.estado_var.set(respuesta.get("message", "No se pudo iniciar sesión."))
                return
            self.app.iniciar_sesion(datos.get("user"), datos["token"])
            self.app.set_estado("200 Sesión iniciada (token JWT recibido)", "ok")
            self.password_var.set("")
            self.estado_var.set("")
            self.app.mostrar("catalog")

        def error(e):
            self.boton_login.state(["!disabled"])
            if isinstance(e, ApiError):
                self.estado_var.set(e.mensaje)
                self.app.set_estado(f"{e.status or '—'} {e.mensaje}", "error")
            else:
                self.estado_var.set(str(e))

        run_async(self, hacer, ok, error)
