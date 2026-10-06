"""
main.py
Punto de entrada de la app de escritorio (Tkinter + ttk): cliente de los
6 microservicios de la librería (login, books, users, authors, pedidos,
pagos), que corren en la VM.

  api/       cliente HTTP base y un cliente por microservicio
  screens/   pantallas (login, registro, inicio, libros, configuracion...)
  widgets/   tema, menu lateral, panel de semaforos y tooltip
  config/    configuracion persistente (config.json)
  session.py JWT y refresh token, solo en memoria

El JWT dura 20 minutos: se renueva solo a los 17 y, ante un 401, el
cliente HTTP intenta un refresh antes de regresar al login. Todo el
trafico HTTP se imprime en la consola (sin tokens ni contraseñas): lanzar
desde una terminal para verlo.

Ejecutar:  python main.py
"""
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from api.auth_client import AuthClient
from api.authors_client import AuthorsClient
from api.books_client import BooksClient
from api.pagos_client import PagosClient
from api.pedidos_client import PedidosClient
from api.users_client import UsersClient
from config.settings import AppConfig
from screens.authors_screen import AuthorsScreen
from screens.catalog_screen import CatalogScreen
from screens.config_screen import ConfigScreen
from screens.home_screen import HomeScreen
from screens.login_screen import LoginScreen
from screens.pedidos_screen import PedidosScreen
from screens.placeholder_screen import PlaceholderScreen
from screens.register_screen import RegisterScreen
from screens.users_screen import UsersScreen
from session import Session
from utils import run_async
from widgets import theme
from widgets.semaforos import SemaforoPanel
from widgets.sidebar import Sidebar

_COLORES_ESTADO = {
    "ok": theme.COLOR_EXITO,
    "error": theme.COLOR_PELIGRO,
    "info": theme.COLOR_TEXTO_SUAVE,
}

# Pantallas que se pueden ver sin sesion; las demas regresan al login.
_PANTALLAS_PUBLICAS = {"login", "register", "config"}
_REINTENTO_RENOVACION_MS = 30_000


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Librería en línea — Python/Tk")
        self.geometry("1180x760")
        self.minsize(1000, 680)
        theme.aplicar(self)

        self.config_app = AppConfig.cargar()
        self.sesion = Session()
        self.auth = AuthClient(self.config_app)                      # login/registro/refresh van sin token
        self.books = BooksClient(self.config_app, self.sesion)
        self.users = UsersClient(self.config_app, self.sesion)
        self.authors = AuthorsClient(self.config_app, self.sesion)
        self.pedidos = PedidosClient(self.config_app, self.sesion)
        self.pagos = PagosClient(self.config_app, self.sesion)
        self.sesion.conectar_refresh(self.auth.refresh)
        self._renovacion_id = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._construir_barra_superior()
        self.semaforos = SemaforoPanel(self, self.config_app)
        self.semaforos.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.sidebar = Sidebar(self, self.mostrar, self.cerrar_sesion)
        self.sidebar.grid(row=2, column=0, sticky="ns")
        self._construir_barra_estado()

        contenedor = ttk.Frame(self)
        contenedor.grid(row=2, column=1, sticky="nsew")
        contenedor.grid_rowconfigure(0, weight=1)
        contenedor.grid_columnconfigure(0, weight=1)

        self._pantallas = {
            "login": LoginScreen(contenedor, self),
            "register": RegisterScreen(contenedor, self),
            "config": ConfigScreen(contenedor, self),
            "home": HomeScreen(contenedor, self),
            "catalog": CatalogScreen(contenedor, self),
            "authors": AuthorsScreen(contenedor, self),
            "users": UsersScreen(contenedor, self),
            "pedidos": PedidosScreen(contenedor, self),
            "pagos": PlaceholderScreen(contenedor, self, "pagos", "Pagos y estado de los pedidos"),
        }
        for pantalla in self._pantallas.values():
            pantalla.grid(row=0, column=0, sticky="nsew")

        self.pantalla_actual = None
        self.pantalla_anterior = "login"
        self._actualizar_sesion_visible()
        self.mostrar("login")
        self.semaforos.iniciar()

    # ---------------------------------------------------------- barras
    def _construir_barra_superior(self):
        barra = tk.Frame(self, background=theme.COLOR_PRINCIPAL, padx=18, pady=10)
        barra.grid(row=0, column=0, columnspan=2, sticky="ew")
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
        barra.grid(row=3, column=0, columnspan=2, sticky="ew")
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

    def _actualizar_sesion_visible(self):
        """Indicador de la barra superior y menu lateral (solo con sesion)."""
        usuario = self.sesion.usuario or {}
        if self.sesion.activa:
            self._sesion_label.configure(
                text=f"● Sesión iniciada como {usuario.get('email', '—')} ({usuario.get('role', 'sin rol')})")
            self.sidebar.grid()
        else:
            self._sesion_label.configure(text="○ Sin sesión")
            self.sidebar.grid_remove()

    # ---------------------------------------------------------- sesion
    def iniciar_sesion(self, datos):
        """`datos` = campo data de POST /login (token, refresh_token, expires_in, user)."""
        self.sesion.iniciar(datos)
        self._actualizar_sesion_visible()
        self._programar_renovacion()

    def _limpiar_sesion(self):
        self._cancelar_renovacion()
        self.sesion.limpiar()
        self._actualizar_sesion_visible()

    def actualizar_usuario(self, usuario):
        """Refresca los datos visibles del usuario en sesion (p. ej. tras editar su nombre)."""
        self.sesion.usuario = {**(self.sesion.usuario or {}), **usuario}
        self._actualizar_sesion_visible()

    def terminar_sesion(self, motivo):
        """El servidor ya cerro las sesiones del usuario (cambio su contraseña, su correo o su
        rol): limpia la sesion local y regresa al login explicando por que."""
        self._limpiar_sesion()
        self.set_estado(motivo, "ok")
        self.mostrar("login")
        messagebox.showinfo("Inicia sesión de nuevo", motivo, parent=self)

    def sesion_invalida(self, error):
        """401 que no se pudo resolver renovando el token: avisa, limpia la sesion y vuelve al login."""
        if not self.sesion.activa and self.pantalla_actual == "login":
            return                      # otra peticion ya nos trajo al login
        self.set_estado("401 Sesión no válida o expirada", "error")
        self._limpiar_sesion()
        self.mostrar("login")
        messagebox.showerror(
            "Sesión no válida (401)",
            "Tu sesión no es válida o ya expiró y no se pudo renovar.\n\n"
            f"Detalle: {getattr(error, 'mensaje', error)}\n\n"
            "Inicia sesión de nuevo para continuar.",
            parent=self,
        )

    # ---------------------------------------------------------- renovacion del JWT
    def _cancelar_renovacion(self):
        if self._renovacion_id is not None:
            self.after_cancel(self._renovacion_id)
            self._renovacion_id = None

    def _programar_renovacion(self, milisegundos=None):
        """Renovacion proactiva: 3 minutos antes de que caduque el JWT (minuto 17 de 20)."""
        self._cancelar_renovacion()
        if milisegundos is None:
            milisegundos = self.sesion.segundos_para_renovar() * 1000
        self._renovacion_id = self.after(milisegundos, self._renovar_token)

    def _renovar_token(self):
        self._renovacion_id = None
        if not self.sesion.activa:
            return
        token_actual = self.sesion.token

        def terminado(renovado):
            if renovado:
                self.set_estado("Token renovado automáticamente.", "info")
                self._programar_renovacion()
            elif not self.sesion.activa:
                self.sesion_invalida("el servidor rechazó el refresh token")
            else:
                # Sin red o servicio caido: el token actual sigue vivo unos minutos; se reintenta.
                self._programar_renovacion(_REINTENTO_RENOVACION_MS)

        run_async(self, lambda: self.sesion.renovar(token_actual), terminado, lambda _e: terminado(False))

    # ---------------------------------------------------------- configuracion
    def aplicar_configuracion(self, datos):
        """Guarda config.json y aplica los cambios sin reiniciar (los clientes leen config_app en vivo)."""
        self.config_app.aplicar(datos)
        self.config_app.guardar()
        self.semaforos.revisar_ahora()

    # ---------------------------------------------------------- navegacion
    def mostrar(self, nombre):
        if nombre not in _PANTALLAS_PUBLICAS and not self.sesion.activa:
            nombre = "login"
        if self.pantalla_actual and self.pantalla_actual != nombre:
            self.pantalla_anterior = self.pantalla_actual
        pantalla = self._pantallas[nombre]
        pantalla.tkraise()
        self.pantalla_actual = nombre
        self.sidebar.marcar(nombre)
        if hasattr(pantalla, "on_show"):
            pantalla.on_show()

    def volver(self):
        self.mostrar(self.pantalla_anterior)

    def cerrar_sesion(self):
        token, refresh_token = self.sesion.token, self.sesion.refresh_token

        def hacer():
            try:
                self.auth.logout(token, refresh_token)     # revoca el JWT en el servidor
            except Exception:
                pass  # cerrar sesion localmente aunque el servicio no responda

        if token:
            threading.Thread(target=hacer, daemon=True).start()
        self._limpiar_sesion()
        self.set_estado("Sesión cerrada.", "info")
        self.mostrar("login")


if __name__ == "__main__":
    App().mainloop()
