"""
ui/login_screen.py
Pantalla de inicio de sesion: pide correo/contraseña al microservicio
de login (POST /login) y, si son correctos, pasa al catalogo.
"""
import tkinter as tk
from tkinter import ttk

from api_client import ApiError
from utils import run_async


class LoginScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=24)
        self.app = app

        ttk.Label(self, text="Librería en línea", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 16))

        ttk.Label(self, text="Correo").grid(row=1, column=0, sticky="e", pady=4)
        self.email_var = tk.StringVar()
        entrada_email = ttk.Entry(self, textvariable=self.email_var, width=32)
        entrada_email.grid(row=1, column=1, pady=4)

        ttk.Label(self, text="Contraseña").grid(row=2, column=0, sticky="e", pady=4)
        self.password_var = tk.StringVar()
        entrada_password = ttk.Entry(self, textvariable=self.password_var, width=32, show="*")
        entrada_password.grid(row=2, column=1, pady=4)
        entrada_password.bind("<Return>", lambda e: self._login())

        self.estado_var = tk.StringVar()
        ttk.Label(self, textvariable=self.estado_var, foreground="#b91c1c", wraplength=320).grid(
            row=3, column=0, columnspan=2, pady=(8, 0))

        botones = ttk.Frame(self)
        botones.grid(row=4, column=0, columnspan=2, pady=(16, 0))
        self.boton_login = ttk.Button(botones, text="Iniciar sesión", command=self._login)
        self.boton_login.grid(row=0, column=0, padx=4)
        ttk.Button(botones, text="Crear cuenta", command=lambda: app.mostrar("register")).grid(
            row=0, column=1, padx=4)
        ttk.Button(botones, text="Configuración", command=lambda: app.mostrar("config")).grid(
            row=0, column=2, padx=4)

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
            if not datos.get("authenticated"):
                self.estado_var.set(respuesta.get("message", "No se pudo iniciar sesión."))
                return
            self.app.usuario_actual = datos.get("user")
            self.password_var.set("")
            self.estado_var.set("")
            self.app.mostrar("catalog")

        def error(e):
            self.boton_login.state(["!disabled"])
            self.estado_var.set(e.mensaje if isinstance(e, ApiError) else str(e))

        run_async(self, hacer, ok, error)
