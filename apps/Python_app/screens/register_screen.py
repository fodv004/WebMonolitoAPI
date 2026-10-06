"""
screens/register_screen.py
Pantalla de registro: crea la cuenta contra el microservicio de login
(POST /register), que valida el dominio del correo (MX) y envia el
correo de confirmacion (Mailpit o Gmail, segun MAIL_MODE).
"""
import tkinter as tk
from tkinter import ttk

from api.http_base import ApiError
from widgets import theme
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
        super().__init__(parent)
        self.app = app

        tarjeta = theme.tarjeta_centrada(self, "Crear cuenta", "Te enviaremos un correo para confirmarla")

        self.vars = {}
        for i, (clave, etiqueta) in enumerate(_CAMPOS, start=3):
            var = tk.StringVar()
            theme.campo(tarjeta, i, etiqueta, var, show="•" if clave == "password" else "")
            self.vars[clave] = var

        fila = 3 + len(_CAMPOS)
        self.estado_var = tk.StringVar()
        self._estado_label = ttk.Label(tarjeta, textvariable=self.estado_var, style="Error.TLabel", wraplength=360)
        self._estado_label.grid(row=fila, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.boton_registrar = ttk.Button(tarjeta, text="Registrar", style="Primary.TButton",
                                          command=self._registrar)
        self.boton_registrar.grid(row=fila + 1, column=0, columnspan=2, sticky="ew", pady=(14, 8))
        ttk.Button(tarjeta, text="Volver a iniciar sesión", command=lambda: app.mostrar("login")).grid(
            row=fila + 2, column=0, columnspan=2, sticky="ew")

    def on_show(self):
        self.estado_var.set("")
        for var in self.vars.values():
            var.set("")

    def _registrar(self):
        datos = {clave: var.get().strip() if clave != "password" else var.get()
                 for clave, var in self.vars.items()}
        if not all(datos.values()):
            self._estado_label.configure(style="Error.TLabel")
            self.estado_var.set("Todos los campos son obligatorios.")
            return

        self.boton_registrar.state(["disabled"])
        self.estado_var.set("Registrando...")

        def hacer():
            return self.app.auth.register(**datos)

        def ok(respuesta):
            self.boton_registrar.state(["!disabled"])
            mensaje = respuesta.get("message", "Cuenta creada. Revisa tu correo para confirmarla.")
            self._estado_label.configure(style="Subtitulo.TLabel")
            self.estado_var.set(mensaje)
            self.app.set_estado(f"201 {mensaje}", "ok")
            self.after(1800, lambda: self.app.mostrar("login"))

        def error(e):
            self.boton_registrar.state(["!disabled"])
            self._estado_label.configure(style="Error.TLabel")
            mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
            self.estado_var.set(mensaje)
            if isinstance(e, ApiError):
                self.app.set_estado(f"{e.status or '—'} {mensaje}", "error")

        run_async(self, hacer, ok, error)
