"""
screens/catalog_screen.py
Catalogo de libros: buscador y tabla (Treeview) con crear (POST), editar
(PUT), editar parcial (PATCH) y eliminar (DELETE). Solo se llega aqui con
sesion iniciada; las escrituras viajan con el JWT y requieren rol admin.
El semaforo, Configuración y Cerrar sesión viven en la ventana principal.

Al seleccionar un libro, la franja de detalle bajo la tabla muestra sus
datos y sus autores segun el microservicio authors (GET /authors/by-book).
"""
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from api.http_base import ApiError
from screens.book_form import BookForm
from utils import run_async
from widgets import theme

_COLUMNAS = [
    # (clave, encabezado, ancho, ancla)
    ("isbn", "ISBN", 120, "w"),
    ("titulo", "Título", 240, "w"),
    ("autor", "Autor", 160, "w"),
    ("genero", "Género", 110, "w"),
    ("anio", "Año", 60, "center"),
    ("precio", "Precio", 80, "e"),
    ("stock", "Stock", 60, "center"),
    ("formato", "Formato", 100, "w"),
]


class CatalogScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(18, 14))
        self.app = app
        self._todos_libros = []
        self._libros_por_iid = {}
        self._peticion_autores = 0     # ultima consulta de autores pedida (las respuestas viejas se descartan)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_barra_superior()
        self._construir_barra_acciones()
        self._construir_tabla()
        self._construir_detalle()

    # ---------------------------------------------------------- UI
    def _construir_barra_superior(self):
        barra = ttk.Frame(self)
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        barra.grid_columnconfigure(4, weight=1)

        self.busqueda_var = tk.StringVar()
        entrada = ttk.Entry(barra, textvariable=self.busqueda_var, width=32)
        entrada.grid(row=0, column=0, padx=(0, 6))
        entrada.bind("<Return>", lambda e: self._buscar())

        ttk.Button(barra, text="Buscar", style="Primary.TButton", command=self._buscar).grid(
            row=0, column=1, padx=3)
        ttk.Button(barra, text="Mostrar todos", command=self._mostrar_todos).grid(row=0, column=2, padx=3)
        ttk.Button(barra, text="Actualizar catálogo", command=self._cargar_libros).grid(row=0, column=3, padx=3)

    def _construir_barra_acciones(self):
        barra = ttk.Frame(self)
        barra.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        barra.grid_columnconfigure(5, weight=1)

        acciones = [
            ("+ Crear libro", "Crear.TButton", self._insertar),
            ("Editar (PUT)", "Editar.TButton", self._editar_seleccion),
            ("Editar parcial (PATCH)", "Patch.TButton", self._patch_seleccion),
            ("Eliminar", "Eliminar.TButton", self._eliminar_seleccion),
            ("Ver portada", "TButton", self._ver_portada),
        ]
        for col, (texto, estilo, comando) in enumerate(acciones):
            ttk.Button(barra, text=texto, style=estilo, command=comando).grid(
                row=0, column=col, padx=(0 if col == 0 else 6, 0))

        self.conteo_var = tk.StringVar()
        ttk.Label(barra, textvariable=self.conteo_var, style="Info.TLabel").grid(row=0, column=5, sticky="e")

    def _construir_tabla(self):
        marco = tk.Frame(self, background=theme.COLOR_SUPERFICIE,
                         highlightthickness=1, highlightbackground=theme.COLOR_BORDE)
        marco.grid(row=2, column=0, sticky="nsew")
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)

        self.tabla = ttk.Treeview(marco, columns=[c[0] for c in _COLUMNAS], show="headings",
                                  selectmode="browse")
        for clave, encabezado, ancho, ancla in _COLUMNAS:
            self.tabla.heading(clave, text=encabezado, anchor=ancla)
            self.tabla.column(clave, width=ancho, minwidth=50, anchor=ancla, stretch=clave in ("titulo", "autor"))
        self.tabla.tag_configure("par", background=theme.COLOR_SUPERFICIE)
        self.tabla.tag_configure("impar", background=theme.COLOR_FILA_ALTERNA)
        self.tabla.tag_configure("vacio", foreground=theme.COLOR_TEXTO_SUAVE)
        self.tabla.bind("<Double-1>", lambda e: self._editar_seleccion())
        self.tabla.bind("<Delete>", lambda e: self._eliminar_seleccion())
        self.tabla.bind("<<TreeviewSelect>>", lambda e: self._mostrar_detalle())

        scroll_y = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        scroll_x = ttk.Scrollbar(marco, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    def _construir_detalle(self):
        """Franja bajo la tabla con el detalle del libro seleccionado y sus autores."""
        franja = ttk.Frame(self, style="Card.TFrame", padding=(14, 10))
        franja.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        franja.grid_columnconfigure(1, weight=1)
        ttk.Label(franja, text="Detalle", style="Subtitulo.TLabel").grid(row=0, column=0, sticky="nw", padx=(0, 12))
        self.detalle_var = tk.StringVar(value="Selecciona un libro para ver su detalle y sus autores.")
        ttk.Label(franja, textvariable=self.detalle_var, style="Card.TLabel", justify="left").grid(
            row=0, column=1, sticky="w")
        ttk.Label(franja, text="Autores", style="Subtitulo.TLabel").grid(row=1, column=0, sticky="nw", padx=(0, 12),
                                                                          pady=(4, 0))
        self.autores_var = tk.StringVar(value="—")
        self._autores_label = ttk.Label(franja, textvariable=self.autores_var, style="Card.TLabel", justify="left",
                                        wraplength=760)
        self._autores_label.grid(row=1, column=1, sticky="w", pady=(4, 0))

    def _mostrar_detalle(self):
        seleccion = self.tabla.selection()
        libro = self._libros_por_iid.get(seleccion[0]) if seleccion else None
        self._peticion_autores += 1
        if libro is None:
            self.detalle_var.set("Selecciona un libro para ver su detalle y sus autores.")
            self.autores_var.set("—")
            return
        precio = libro.get("precio")
        self.detalle_var.set(
            f"{libro.get('titulo')}  ·  ISBN {libro.get('isbn')}  ·  {libro.get('anio') or '—'}  ·  "
            f"{libro.get('formato') or '—'}  ·  {'$' + format(float(precio), ',.2f') if precio is not None else '—'}"
            f"  ·  stock {libro.get('stock') if libro.get('stock') is not None else '—'}")
        self.autores_var.set("Consultando el servicio de autores...")
        numero, isbn = self._peticion_autores, libro.get("isbn")

        def ok(datos):
            if numero != self._peticion_autores:
                return
            autores = datos.get("authors", [])
            self.autores_var.set(
                "  ·  ".join(f"{a['orden']}. {a['nombre_completo']}" + (f" ({a['nacionalidad']})" if a.get("nacionalidad") else "")
                             for a in autores)
                if autores else "Sin autores relacionados en el servicio de autores.")

        def error(e):
            if numero == self._peticion_autores:
                self.autores_var.set("No disponible: el servicio de autores no responde "
                                     f"({e.mensaje if isinstance(e, ApiError) else e}).")

        run_async(self, lambda: self.app.authors.by_book(isbn), ok, error)

    # ---------------------------------------------------------- ciclo de vida
    def on_show(self):
        self._cargar_libros()

    # ---------------------------------------------------------- datos
    def _cargar_libros(self):
        self.conteo_var.set("Cargando catálogo...")

        def hacer():
            return self.app.books.list_books()

        def ok(libros):
            self._todos_libros = libros if isinstance(libros, list) else []
            self._aplicar_busqueda()

        def error(e):
            self._todos_libros = []
            mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
            self.conteo_var.set("")
            self.app.set_estado(f"{getattr(e, 'status', None) or '—'} No se pudo cargar el catálogo: {mensaje}",
                                "error")
            self._renderizar([])

        run_async(self, hacer, ok, error)

    def _buscar(self):
        self._aplicar_busqueda()

    def _mostrar_todos(self):
        self.busqueda_var.set("")
        self._aplicar_busqueda()

    def _aplicar_busqueda(self):
        termino = self.busqueda_var.get().strip().lower()
        if not termino:
            filtrados = self._todos_libros
        else:
            filtrados = [
                libro for libro in self._todos_libros
                if termino in " ".join(
                    str(libro.get(campo) or "") for campo in ("isbn", "titulo", "autor", "genero")
                ).lower()
            ]
        self.conteo_var.set(f"{len(filtrados)} libro(s) de {len(self._todos_libros)}")
        self._renderizar(filtrados)

    # ---------------------------------------------------------- tabla
    def _renderizar(self, libros):
        self.tabla.delete(*self.tabla.get_children())
        self._libros_por_iid = {}

        self._mostrar_detalle()        # la seleccion se pierde al repintar
        if not libros:
            self.tabla.insert("", "end", values=("", "No hay libros que mostrar."), tags=("vacio",))
            return

        for i, libro in enumerate(libros):
            valores = []
            for clave, *_ in _COLUMNAS:
                valor = libro.get(clave)
                if clave == "precio" and valor is not None:
                    valor = f"${float(valor):,.2f}"
                valores.append("—" if valor in (None, "") else valor)
            iid = self.tabla.insert("", "end", values=valores, tags=("par" if i % 2 == 0 else "impar",))
            self._libros_por_iid[iid] = libro

    def _libro_seleccionado(self):
        seleccion = self.tabla.selection()
        libro = self._libros_por_iid.get(seleccion[0]) if seleccion else None
        if libro is None:
            self.app.set_estado("Selecciona un libro de la tabla primero.", "info")
        return libro

    # ---------------------------------------------------------- acciones
    def _al_guardar(self, mensaje):
        self.app.set_estado(mensaje, "ok")
        self._cargar_libros()

    def _insertar(self):
        BookForm(self.app, modo="crear", on_guardado=self._al_guardar)

    def _editar(self, libro):
        BookForm(self.app, modo="editar", on_guardado=self._al_guardar, libro=libro)

    def _editar_seleccion(self):
        libro = self._libro_seleccionado()
        if libro:
            self._editar(libro)

    def _patch_seleccion(self):
        libro = self._libro_seleccionado()
        if libro:
            BookForm(self.app, modo="patch", on_guardado=self._al_guardar, libro=libro)

    def _ver_portada(self):
        libro = self._libro_seleccionado()
        if not libro:
            return
        portada = libro.get("portada") or libro.get("image_url")
        if portada:
            webbrowser.open(portada)
        else:
            self.app.set_estado(f"El libro {libro.get('isbn')} no tiene portada.", "info")

    def _eliminar_seleccion(self):
        libro = self._libro_seleccionado()
        if libro:
            self._eliminar(libro)

    def _eliminar(self, libro):
        isbn = libro.get("isbn")
        if not messagebox.askyesno("Eliminar libro", f"¿Eliminar el libro {isbn} — {libro.get('titulo')}?",
                                   parent=self.app):
            return

        def hacer():
            respuesta = self.app.books.delete_book(isbn)
            return self.app.books.ultimo_status, respuesta

        def ok(resultado):
            status, _respuesta = resultado
            self._al_guardar(f"{status} Libro {isbn} eliminado")

        def error(e):
            if isinstance(e, ApiError) and e.es_sesion_invalida:
                self.app.sesion_invalida(e)
                return
            mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
            self.app.set_estado(f"{getattr(e, 'status', None) or '—'} {mensaje}", "error")
            messagebox.showerror("No se pudo eliminar", mensaje, parent=self.app)

        run_async(self, hacer, ok, error)
