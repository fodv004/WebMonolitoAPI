"""
ui/config_screen.py
Pantalla de configuracion: URLs de los microservicios (login y books).
Se guardan en local_storage.json (equivalente de escritorio al
localStorage del navegador) y sobreviven a cerrar y volver a abrir la
app. El JWT nunca se guarda aqui: vive solo en memoria.
"""
import tkinter as tk
from tkinter import ttk

import api_client
import storage
from ui import theme
from utils import run_async


class ConfigScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        tarjeta = theme.tarjeta_centrada(self, "Configuración", "URLs base de los microservicios")

        self.login_url_var = tk.StringVar()
        theme.campo(tarjeta, 3, "Servicio de login", self.login_url_var)
        self.books_url_var = tk.StringVar()
        theme.campo(tarjeta, 4, "Servicio de libros", self.books_url_var)

        self.estado_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.estado_var, style="Subtitulo.TLabel", wraplength=380).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))

        botones = ttk.Frame(tarjeta, style="CardInner.TFrame")
        botones.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        botones.grid_columnconfigure((0, 1, 2), weight=1, uniform="cfg")
        ttk.Button(botones, text="Probar conexión", command=self._probar).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(botones, text="Guardar", style="Primary.TButton", command=self._guardar).grid(
            row=0, column=1, sticky="ew", padx=4)
        ttk.Button(botones, text="Volver", command=lambda: app.volver()).grid(
            row=0, column=2, sticky="ew", padx=(4, 0))

    def on_show(self):
        self.login_url_var.set(self.app.config_data["login_base_url"])
        self.books_url_var.set(self.app.config_data["books_base_url"])
        self.estado_var.set("")

    def _probar(self):
        login_url = self.login_url_var.get().strip().rstrip("/")
        books_url = self.books_url_var.get().strip().rstrip("/")
        self.estado_var.set("Probando...")

        def hacer():
            return api_client.is_healthy(login_url), api_client.is_healthy(books_url)

        def ok(resultado):
            login_ok, books_ok = resultado
            self.estado_var.set(
                f"Login: {'OK' if login_ok else 'sin respuesta'}   ·   "
                f"Libros: {'OK' if books_ok else 'sin respuesta'}"
            )
            self.app.set_estado(self.estado_var.get(), "ok" if login_ok and books_ok else "error")

        run_async(self, hacer, ok, lambda e: self.estado_var.set(str(e)))

    def _guardar(self):
        login_url = self.login_url_var.get().strip().rstrip("/")
        books_url = self.books_url_var.get().strip().rstrip("/")
        if not login_url or not books_url:
            self.estado_var.set("Ambas URL son obligatorias.")
            return
        self.app.config_data["login_base_url"] = login_url
        self.app.config_data["books_base_url"] = books_url
        storage.guardar(self.app.config_data)
        self.app.reconectar_clientes()
        self.estado_var.set("Configuración guardada.")
        self.app.set_estado("Configuración guardada.", "ok")
