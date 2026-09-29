"""
ui/catalog_screen.py
Catalogo de libros: semaforo de salud de los dos microservicios,
buscador y tabla (Treeview) con crear (POST), editar (PUT), editar
parcial (PATCH) y eliminar (DELETE). Solo se llega aqui desde
LoginScreen tras autenticarse; las escrituras viajan con el JWT.
"""
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import api_client
from api_client import ApiError
from ui import theme
from ui.book_form import BookForm
from utils import run_async

INTERVALO_SEMAFORO_MS = 8000

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
        self._semaforo_iniciado = False

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_barra_superior()
        self._construir_barra_acciones()
        self._construir_tabla()

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

        semaforo = ttk.Frame(barra)
        semaforo.grid(row=0, column=4, sticky="e", padx=12)
        ttk.Label(semaforo, text="Login").pack(side="left")
        self.luz_login = ttk.Label(semaforo, text="●", font=(theme.FAMILIA, 14))
        self.luz_login.pack(side="left", padx=(2, 10))
        ttk.Label(semaforo, text="Libros").pack(side="left")
        self.luz_books = ttk.Label(semaforo, text="●", font=(theme.FAMILIA, 14))
        self.luz_books.pack(side="left", padx=(2, 0))

        ttk.Button(barra, text="Configuración", command=lambda: self.app.mostrar("config")).grid(
            row=0, column=5, padx=3)
        ttk.Button(barra, text="Cerrar sesión", command=self.app.cerrar_sesion).grid(
            row=0, column=6, padx=(3, 0))

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

        scroll_y = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        scroll_x = ttk.Scrollbar(marco, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")

    # ---------------------------------------------------------- ciclo de vida
    def on_show(self):
        self._cargar_libros()
        if not self._semaforo_iniciado:
            self._semaforo_iniciado = True
            self._actualizar_semaforo()

    # ---------------------------------------------------------- semaforo
    def _actualizar_semaforo(self):
        def hacer():
            return (
                api_client.is_healthy(self.app.config_data["login_base_url"]),
                api_client.is_healthy(self.app.config_data["books_base_url"]),
            )

        def ok(resultado):
            login_ok, books_ok = resultado
            self._pintar_luz(self.luz_login, login_ok)
            self._pintar_luz(self.luz_books, books_ok)
            self.after(INTERVALO_SEMAFORO_MS, self._actualizar_semaforo)

        def error(_e):
            self._pintar_luz(self.luz_login, False)
            self._pintar_luz(self.luz_books, False)
            self.after(INTERVALO_SEMAFORO_MS, self._actualizar_semaforo)

        run_async(self, hacer, ok, error)

    @staticmethod
    def _pintar_luz(etiqueta, activo):
        etiqueta.configure(foreground=theme.COLOR_EXITO if activo else theme.COLOR_PELIGRO)

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
