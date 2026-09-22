"""
ui/register_screen.py
Pantalla de registro: crea la cuenta contra el microservicio de login
(POST /register), que valida el dominio del correo (MX) y envia el
correo de confirmacion (Mailpit o Gmail, segun MAIL_MODE).
"""
import tkinter as tk
from tkinter import ttk

from api_client import ApiError
from utils import run_async

_CAMPOS = [
    ("nombre", "Nombre"),
    ("apellido_paterno", "Apellido paterno"),
    ("apellido_materno", "Apellido materno"),
    ("email", "Correo"),
    ("password", "Contraseña"),
]


class RegisterScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=24)
        self.app = app

        ttk.Label(self, text="Crear cuenta", font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 16))

        self.vars = {}
        for i, (clave, etiqueta) in enumerate(_CAMPOS, start=1):
            ttk.Label(self, text=etiqueta).grid(row=i, column=0, sticky="e", pady=4)
            var = tk.StringVar()
            mostrar = "*" if clave == "password" else ""
            ttk.Entry(self, textvariable=var, width=32, show=mostrar).grid(row=i, column=1, pady=4)
            self.vars[clave] = var

        self.estado_var = tk.StringVar()
        ttk.Label(self, textvariable=self.estado_var, foreground="#b91c1c", wraplength=340).grid(
            row=len(_CAMPOS) + 1, column=0, columnspan=2, pady=(8, 0))

        botones = ttk.Frame(self)
        botones.grid(row=len(_CAMPOS) + 2, column=0, columnspan=2, pady=16)
        self.boton_registrar = ttk.Button(botones, text="Registrar", command=self._registrar)
        self.boton_registrar.grid(row=0, column=0, padx=4)
        ttk.Button(botones, text="Volver a iniciar sesión", command=lambda: app.mostrar("login")).grid(
            row=0, column=1, padx=4)

    def on_show(self):
        self.estado_var.set("")
        for var in self.vars.values():
            var.set("")

    def _registrar(self):
        datos = {clave: var.get().strip() if clave != "password" else var.get()
                 for clave, var in self.vars.items()}
        if not all(datos.values()):
            self.estado_var.set("Todos los campos son obligatorios.")
            return

        self.boton_registrar.state(["disabled"])
        self.estado_var.set("Registrando...")

        def hacer():
            return self.app.auth.register(**datos)

        def ok(respuesta):
            self.boton_registrar.state(["!disabled"])
            self.estado_var.set(respuesta.get("message", "Cuenta creada. Revisa tu correo para confirmarla."))
            self.after(1800, lambda: self.app.mostrar("login"))

        def error(e):
            self.boton_registrar.state(["!disabled"])
            self.estado_var.set(e.mensaje if isinstance(e, ApiError) else str(e))

        run_async(self, hacer, ok, error)
