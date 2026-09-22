"""
main.py
Punto de entrada de la app de escritorio (Tkinter puro, sin
dependencias externas). Login y registro contra el microservicio de
auth (puerto 5000) y catalogo de libros con CRUD contra el
microservicio de libros (puerto 5001). Las URLs de ambos servicios son
configurables desde la pantalla de Configuración y se guardan en
local_storage.json.

Ejecutar:  python main.py
(ver instrucciones.txt en esta misma carpeta)
"""
import threading
import tkinter as tk

import api_client
import storage
from ui.catalog_screen import CatalogScreen
from ui.config_screen import ConfigScreen
from ui.login_screen import LoginScreen
from ui.register_screen import RegisterScreen


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Librería en línea — Python/Tk")
        self.geometry("860x620")
        self.minsize(720, 480)

        self.config_data = storage.cargar()
        self.usuario_actual = None
        self.auth = api_client.AuthClient(self.config_data["login_base_url"])
        self.books = api_client.BooksClient(self.config_data["books_base_url"])

        contenedor = tk.Frame(self)
        contenedor.pack(fill="both", expand=True)
        contenedor.grid_rowconfigure(0, weight=1)
        contenedor.grid_columnconfigure(0, weight=1)

        self._pantallas = {
            "login": LoginScreen(contenedor, self),
            "register": RegisterScreen(contenedor, self),
            "config": ConfigScreen(contenedor, self),
            "catalog": CatalogScreen(contenedor, self),
        }
        for pantalla in self._pantallas.values():
            pantalla.grid(row=0, column=0, sticky="nsew")

        self.pantalla_actual = None
        self.pantalla_anterior = "login"
        self.mostrar("login")

    def reconectar_clientes(self):
        """Reconstruye los clientes HTTP tras cambiar las URLs en Configuración."""
        self.auth = api_client.AuthClient(self.config_data["login_base_url"])
        self.books = api_client.BooksClient(self.config_data["books_base_url"])

    def mostrar(self, nombre):
        if self.pantalla_actual and self.pantalla_actual != nombre:
            self.pantalla_anterior = self.pantalla_actual
        pantalla = self._pantallas[nombre]
        pantalla.tkraise()
        if hasattr(pantalla, "on_show"):
            pantalla.on_show()
        self.pantalla_actual = nombre

    def volver(self):
        self.mostrar(self.pantalla_anterior)

    def cerrar_sesion(self):
        auth_actual = self.auth

        def hacer():
            try:
                auth_actual.logout()
            except Exception:
                pass  # cerrar sesion localmente aunque el servicio no responda

        threading.Thread(target=hacer, daemon=True).start()
        self.usuario_actual = None
        self.mostrar("login")


if __name__ == "__main__":
    App().mainloop()
