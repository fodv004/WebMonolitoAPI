"""
main.py
Punto de entrada de la app de escritorio (Tkinter + ttk). Login y
registro contra el microservicio de auth (puerto 5000) y catalogo de
libros con CRUD contra el microservicio de libros (puerto 5001). Las
URLs de ambos servicios son configurables desde la pantalla de
Configuración y se guardan en local_storage.json.

El JWT que devuelve POST /login vive solo en memoria (self.token) y se
pierde al cerrar sesión o la app. Todo el trafico HTTP se imprime en la
consola: lanzar desde una terminal para verlo.

Ejecutar:  python main.py
(ver instrucciones.txt en la raiz del proyecto)
"""
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import api_client
import storage
from ui import theme
from ui.catalog_screen import CatalogScreen
from ui.config_screen import ConfigScreen
from ui.login_screen import LoginScreen
from ui.register_screen import RegisterScreen

_COLORES_ESTADO = {
    "ok": theme.COLOR_EXITO,
    "error": theme.COLOR_PELIGRO,
    "info": theme.COLOR_TEXTO_SUAVE,
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Librería en línea — Python/Tk")
        self.geometry("1040x660")
        self.minsize(820, 520)
        theme.aplicar(self)

        self.config_data = storage.cargar()
        self.usuario_actual = None
        self.token = None
        self.auth = api_client.AuthClient(self.config_data["login_base_url"])
        self.books = api_client.BooksClient(self.config_data["books_base_url"])

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._construir_barra_superior()
        self._construir_barra_estado()

        contenedor = ttk.Frame(self)
        contenedor.grid(row=1, column=0, sticky="nsew")
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
        self.actualizar_indicador_sesion()
        self.mostrar("login")

    # ---------------------------------------------------------- barras
    def _construir_barra_superior(self):
        barra = tk.Frame(self, background=theme.COLOR_PRINCIPAL, padx=18, pady=10)
        barra.grid(row=0, column=0, sticky="ew")
        barra.grid_columnconfigure(1, weight=1)

        tk.Label(barra, text="Librería en línea", font=theme.FUENTE_SUBTITULO,
                 background=theme.COLOR_PRINCIPAL, foreground=theme.COLOR_TEXTO_CLARO).grid(
            row=0, column=0, sticky="w")
        self._sesion_label = tk.Label(barra, font=theme.FUENTE_NORMAL,
                                      background=theme.COLOR_PRINCIPAL, foreground=theme.COLOR_TEXTO_CLARO)
        self._sesion_label.grid(row=0, column=1, sticky="e")

    def _construir_barra_estado(self):
        barra = tk.Frame(self, background=theme.COLOR_SUPERFICIE, padx=14, pady=5,
                         highlightthickness=1, highlightbackground=theme.COLOR_BORDE)
        barra.grid(row=2, column=0, sticky="ew")
        self._punto_estado = tk.Label(barra, text="●", font=theme.FUENTE_NORMAL,
                                      background=theme.COLOR_SUPERFICIE, foreground=theme.COLOR_TEXTO_SUAVE)
        self._punto_estado.pack(side="left")
        self._estado_label = tk.Label(barra, text="Listo.", font=theme.FUENTE_NORMAL, anchor="w",
                                      background=theme.COLOR_SUPERFICIE, foreground=theme.COLOR_TEXTO_SUAVE)
        self._estado_label.pack(side="left", padx=(6, 0), fill="x", expand=True)

    def set_estado(self, texto, tipo="info"):
        """Último resultado en la barra inferior. tipo: ok (verde) | error (rojo) | info."""
        color = _COLORES_ESTADO.get(tipo, theme.COLOR_TEXTO_SUAVE)
        self._estado_label.configure(text=texto, foreground=color)
        self._punto_estado.configure(foreground=color)

    def actualizar_indicador_sesion(self):
        email = (self.usuario_actual or {}).get("email")
        self._sesion_label.configure(text=f"● Sesión iniciada como {email}" if email else "○ Sin sesión")

    # ---------------------------------------------------------- sesion
    def iniciar_sesion(self, usuario, token):
        self.usuario_actual = usuario
        self.token = token
        self.books.token = token
        self.actualizar_indicador_sesion()

    def _limpiar_sesion(self):
        self.usuario_actual = None
        self.token = None
        self.books.token = None
        self.actualizar_indicador_sesion()

    def sesion_invalida(self, error):
        """401/403 del servicio de libros: avisa, limpia el token y vuelve al login."""
        if error.status == 401:
            estado = "401 Sesión no válida: falta el token o su formato es incorrecto"
        else:
            estado = f"403 Sesión expirada o token inválido ({error.mensaje})"
        self.set_estado(estado, "error")
        messagebox.showerror(
            f"Sesión no válida ({error.status})",
            "Tu sesión no es válida o ya expiró.\n\n"
            f"Detalle del servidor: {error.mensaje}\n\n"
            "Inicia sesión de nuevo para continuar.",
            parent=self,
        )
        self._limpiar_sesion()
        self.mostrar("login")

    # ---------------------------------------------------------- navegacion
    def reconectar_clientes(self):
        """Reconstruye los clientes HTTP tras cambiar las URLs en Configuración."""
        self.auth = api_client.AuthClient(self.config_data["login_base_url"])
        self.books = api_client.BooksClient(self.config_data["books_base_url"], token=self.token)

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
        self._limpiar_sesion()
        self.set_estado("Sesión cerrada.", "info")
        self.mostrar("login")


if __name__ == "__main__":
    App().mainloop()
