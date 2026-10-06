"""
widgets/sidebar.py
Menu lateral de la ventana principal (solo visible con sesion iniciada):
Inicio, Libros, Autores, Usuarios, Pedidos, Pagos, Configuración y
Cerrar sesión. Resalta la pantalla actual.
"""
import tkinter as tk

from widgets import theme

# (texto, nombre de la pantalla en App)
OPCIONES = [
    ("Inicio", "home"),
    ("Libros", "catalog"),
    ("Autores", "authors"),
    ("Usuarios", "users"),
    ("Pedidos", "pedidos"),
    ("Pagos", "pagos"),
    ("Configuración", "config"),
]


class Sidebar(tk.Frame):
    def __init__(self, parent, on_navegar, on_cerrar_sesion):
        super().__init__(parent, background=theme.COLOR_PRINCIPAL, width=170)
        self.pack_propagate(False)
        self._botones = {}

        tk.Label(self, text="MENÚ", font=theme.FUENTE_PEQUENA, background=theme.COLOR_PRINCIPAL,
                 foreground=theme.COLOR_SELECCION, anchor="w", padx=18).pack(fill="x", pady=(16, 6))
        for texto, pantalla in OPCIONES:
            self._botones[pantalla] = self._boton(texto, lambda p=pantalla: on_navegar(p))
            self._botones[pantalla].pack(fill="x")

        self._boton("Cerrar sesión", on_cerrar_sesion).pack(fill="x", side="bottom", pady=(0, 12))

    def _boton(self, texto, comando):
        return tk.Button(self, text=texto, command=comando, anchor="w", padx=18, pady=9, relief="flat",
                         borderwidth=0, cursor="hand2", font=theme.FUENTE_NORMAL,
                         background=theme.COLOR_PRINCIPAL, foreground=theme.COLOR_TEXTO_CLARO,
                         activebackground=theme.COLOR_PRINCIPAL_HOVER, activeforeground=theme.COLOR_TEXTO_CLARO)

    def marcar(self, pantalla):
        for nombre, boton in self._botones.items():
            activo = nombre == pantalla
            boton.configure(background=theme.COLOR_INFO if activo else theme.COLOR_PRINCIPAL,
                            font=theme.FUENTE_NEGRITA if activo else theme.FUENTE_NORMAL)
