"""
ui/config_screen.py
Pantalla de configuracion: URLs de los microservicios (login y books).
Se guardan en local_storage.json (equivalente de escritorio al
localStorage del navegador) y sobreviven a cerrar y volver a abrir la
app.
"""
import tkinter as tk
from tkinter import ttk

import api_client
import storage
from utils import run_async


class ConfigScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=24)
        self.app = app

        ttk.Label(self, text="Configuración", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 16))

        ttk.Label(self, text="URL del servicio de login").grid(row=1, column=0, sticky="e", pady=4)
        self.login_url_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.login_url_var, width=36).grid(row=1, column=1, pady=4)

        ttk.Label(self, text="URL del servicio de libros").grid(row=2, column=0, sticky="e", pady=4)
        self.books_url_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.books_url_var, width=36).grid(row=2, column=1, pady=4)

        self.estado_var = tk.StringVar()
        ttk.Label(self, textvariable=self.estado_var, wraplength=360).grid(
            row=3, column=0, columnspan=2, pady=(8, 0))

        botones = ttk.Frame(self)
        botones.grid(row=4, column=0, columnspan=2, pady=16)
        ttk.Button(botones, text="Probar conexión", command=self._probar).grid(row=0, column=0, padx=4)
        ttk.Button(botones, text="Guardar", command=self._guardar).grid(row=0, column=1, padx=4)
        ttk.Button(botones, text="Volver", command=lambda: app.volver()).grid(row=0, column=2, padx=4)

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
