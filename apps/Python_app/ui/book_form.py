"""
ui/book_form.py
Ventana emergente (modal) para insertar, editar o editar parcialmente
un libro:
  crear  -> POST  /books          (todos los campos obligatorios)
  editar -> PUT   /books/<isbn>   (envia todos los campos)
  patch  -> PATCH /books/<isbn>   (envia SOLO los campos que cambiaste)
Las tres viajan con Authorization: Bearer <token>. Un 401/403 cierra el
formulario y pide iniciar sesion de nuevo.
"""
import tkinter as tk
from tkinter import ttk

from api_client import ApiError
from ui import theme
from utils import run_async

_CAMPOS = [
    ("isbn", "ISBN"),
    ("titulo", "Título"),
    ("anio", "Año"),
    ("precio", "Precio"),
    ("stock", "Stock"),
    ("formato", "Formato"),
    ("autor", "Autor"),
    ("genero", "Género"),
    ("portada", "URL de portada"),
]

_MODOS = {
    # modo: (titulo, subtitulo, texto del boton, estilo del boton)
    "crear": ("Crear libro", "POST /books — todos los campos marcados son obligatorios",
              "Crear", "Crear.TButton"),
    "editar": ("Editar libro (PUT)", "PUT /books/{isbn} — se envían todos los campos",
               "Guardar (PUT)", "Editar.TButton"),
    "patch": ("Editar parcial (PATCH)", "PATCH /books/{isbn} — solo se envían los campos que cambies",
              "Guardar cambios (PATCH)", "Patch.TButton"),
}

_ENTEROS = ("anio", "stock")


def _texto_original(libro, clave):
    valor = libro.get(clave)
    return "" if valor is None else str(valor)


class BookForm(tk.Toplevel):
    def __init__(self, app, modo, on_guardado, libro=None):
        super().__init__(app)
        self.app = app
        self.modo = modo  # "crear" | "editar" | "patch"
        self.on_guardado = on_guardado
        self.libro = libro or {}

        titulo, subtitulo, texto_boton, estilo_boton = _MODOS[modo]
        isbn = self.libro.get("isbn", "")
        self.title(titulo if modo == "crear" else f"{titulo} — {isbn}")
        self.configure(background=theme.COLOR_FONDO, padx=16, pady=16)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()

        tarjeta = ttk.Frame(self, style="Card.TFrame", padding=(28, 22))
        tarjeta.pack(fill="both", expand=True)
        tarjeta.grid_columnconfigure(1, weight=1)
        ttk.Label(tarjeta, text=titulo, style="Titulo.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(tarjeta, text=subtitulo.replace("{isbn}", isbn or "{isbn}"), style="Subtitulo.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 12))

        self.vars = {}
        for i, (clave, etiqueta) in enumerate(_CAMPOS, start=2):
            var = tk.StringVar(value=_texto_original(self.libro, clave))
            entrada = theme.campo(tarjeta, i, etiqueta, var)
            if clave == "isbn" and modo != "crear":
                entrada.state(["disabled"])
            self.vars[clave] = var

        fila = 2 + len(_CAMPOS)
        self.estado_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.estado_var, style="Error.TLabel", wraplength=380).grid(
            row=fila, column=0, columnspan=2, sticky="w", pady=(8, 0))

        botones = ttk.Frame(tarjeta, style="CardInner.TFrame")
        botones.grid(row=fila + 1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        botones.grid_columnconfigure((0, 1), weight=1, uniform="bf")
        self.boton_guardar = ttk.Button(botones, text=texto_boton, style=estilo_boton, command=self._guardar)
        self.boton_guardar.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(botones, text="Cancelar", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    # ---------------------------------------------------------- construir body
    def _campos_completos(self, datos):
        """crear/editar: mismas validaciones que antes (todos los campos)."""
        if self.modo == "crear" and not datos["isbn"]:
            raise ValueError("El ISBN es obligatorio.")
        if not datos["titulo"] or not datos["formato"]:
            raise ValueError("Título y formato son obligatorios.")
        try:
            anio = int(datos["anio"])
            precio = float(datos["precio"])
            stock = int(datos["stock"])
        except ValueError:
            raise ValueError("Año y stock deben ser enteros; precio, un número.")
        return {
            "titulo": datos["titulo"],
            "anio": anio,
            "precio": precio,
            "stock": stock,
            "formato": datos["formato"],
            "autor": datos["autor"] or None,
            "genero": datos["genero"] or None,
            "portada": datos["portada"] or None,
        }

    def _campos_modificados(self, datos):
        """patch: solo los campos cuyo valor cambió respecto al libro original."""
        campos = {}
        for clave, _ in _CAMPOS:
            if clave == "isbn" or datos[clave] == _texto_original(self.libro, clave):
                continue
            valor = datos[clave]
            if not valor:
                raise ValueError(f"El campo '{clave}' no puede quedar vacío en una actualización parcial.")
            try:
                if clave in _ENTEROS:
                    valor = int(valor)
                elif clave == "precio":
                    valor = float(valor)
            except ValueError:
                raise ValueError("Año y stock deben ser enteros; precio, un número.")
            campos[clave] = valor
        if not campos:
            raise ValueError("No modificaste ningún campo.")
        return campos

    # ---------------------------------------------------------- guardar
    def _guardar(self):
        datos = {clave: var.get().strip() for clave, var in self.vars.items()}
        try:
            campos = self._campos_modificados(datos) if self.modo == "patch" else self._campos_completos(datos)
        except ValueError as e:
            self.estado_var.set(str(e))
            return

        self.boton_guardar.state(["disabled"])
        self.estado_var.set("Guardando...")
        books = self.app.books

        def hacer():
            if self.modo == "crear":
                books.create_book(isbn=datos["isbn"], **campos)
            elif self.modo == "editar":
                books.update_book(self.libro["isbn"], **campos)
            else:
                books.patch_book(self.libro["isbn"], **campos)
            return books.ultimo_status

        def ok(status):
            isbn = datos["isbn"] if self.modo == "crear" else self.libro["isbn"]
            mensajes = {
                "crear": f"{status} Libro creado ({isbn})",
                "editar": f"{status} Libro actualizado con PUT ({isbn})",
                "patch": f"{status} Libro actualizado parcialmente con PATCH ({isbn}): {', '.join(campos)}",
            }
            self.destroy()
            self.on_guardado(mensajes[self.modo])

        def error(e):
            if isinstance(e, ApiError) and e.es_sesion_invalida:
                self.destroy()
                self.app.sesion_invalida(e)
                return
            self.boton_guardar.state(["!disabled"])
            mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
            self.estado_var.set(mensaje)
            self.app.set_estado(f"{getattr(e, 'status', None) or '—'} {mensaje}", "error")

        run_async(self, hacer, ok, error)
