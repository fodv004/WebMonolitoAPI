"""
ui/book_form.py
Ventana emergente (modal) para insertar o editar un libro. Llama a
POST /books o PUT /books/<isbn> del microservicio de libros.
"""
import tkinter as tk
from tkinter import ttk

from api_client import ApiError
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


class BookForm(tk.Toplevel):
    def __init__(self, app, modo, on_guardado, libro=None):
        super().__init__(app)
        self.app = app
        self.modo = modo  # "crear" | "editar"
        self.on_guardado = on_guardado
        self.libro = libro or {}

        self.title("Insertar libro" if modo == "crear" else f"Editar libro {self.libro.get('isbn', '')}")
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()

        self.vars = {}
        for i, (clave, etiqueta) in enumerate(_CAMPOS):
            ttk.Label(self, text=etiqueta).grid(row=i, column=0, sticky="e", padx=8, pady=4)
            var = tk.StringVar(value=str(self.libro.get(clave, "") or ""))
            entrada = ttk.Entry(self, textvariable=var, width=36)
            entrada.grid(row=i, column=1, padx=8, pady=4)
            if clave == "isbn" and modo == "editar":
                entrada.state(["disabled"])
            self.vars[clave] = var

        self.estado_var = tk.StringVar()
        ttk.Label(self, textvariable=self.estado_var, foreground="#b91c1c", wraplength=320).grid(
            row=len(_CAMPOS), column=0, columnspan=2, pady=(4, 0))

        botones = ttk.Frame(self)
        botones.grid(row=len(_CAMPOS) + 1, column=0, columnspan=2, pady=12)
        self.boton_guardar = ttk.Button(botones, text="Guardar", command=self._guardar)
        self.boton_guardar.grid(row=0, column=0, padx=4)
        ttk.Button(botones, text="Cancelar", command=self.destroy).grid(row=0, column=1, padx=4)

    def _guardar(self):
        datos = {clave: var.get().strip() for clave, var in self.vars.items()}

        if self.modo == "crear" and not datos["isbn"]:
            self.estado_var.set("El ISBN es obligatorio.")
            return
        if not datos["titulo"] or not datos["formato"]:
            self.estado_var.set("Título y formato son obligatorios.")
            return
        try:
            anio = int(datos["anio"])
            precio = float(datos["precio"])
            stock = int(datos["stock"])
        except ValueError:
            self.estado_var.set("Año y stock deben ser enteros; precio, un número.")
            return

        campos = {
            "titulo": datos["titulo"],
            "anio": anio,
            "precio": precio,
            "stock": stock,
            "formato": datos["formato"],
            "autor": datos["autor"] or None,
            "genero": datos["genero"] or None,
            "portada": datos["portada"] or None,
        }

        self.boton_guardar.state(["disabled"])
        self.estado_var.set("Guardando...")

        def hacer():
            if self.modo == "crear":
                return self.app.books.create_book(isbn=datos["isbn"], **campos)
            return self.app.books.update_book(self.libro["isbn"], **campos)

        def ok(_resultado):
            self.on_guardado()
            self.destroy()

        def error(e):
            self.boton_guardar.state(["!disabled"])
            self.estado_var.set(e.mensaje if isinstance(e, ApiError) else str(e))

        run_async(self, hacer, ok, error)
