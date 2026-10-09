"""
screens/authors_screen.py
Pantalla Autores (microservicio authors).

  Izquierda: buscador y tabla paginada de autores.
  Derecha:   panel con los libros del autor seleccionado.

Cualquier usuario puede consultar. Las acciones de administracion (alta,
edicion y baja de autores; relacionar un libro buscandolo por ISBN o
titulo; quitar una relacion) solo se muestran al rol admin.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from api.http_base import ApiError
from utils import run_async
from widgets import theme
from widgets.dialogs import Campo, FormDialog

POR_PAGINA = 15
MAX_RESULTADOS = 30

_COLUMNAS = [
    # (clave, encabezado, ancho, ancla)
    ("id_autor", "ID", 45, "center"),
    ("autor", "Autor", 240, "w"),
    ("nacionalidad", "Nacionalidad", 130, "w"),
    ("libros", "Libros", 55, "center"),
]
# Columnas de la tabla autores (id_autor, nombre, nacionalidad).
_CAMPOS = [("nombre", "Nombre"), ("nacionalidad", "Nacionalidad")]


class AuthorsScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(18, 14))
        self.app = app
        self.pagina = 1
        self.paginas = 0
        self._por_iid = {}
        self._seleccion_id = None
        self._peticion = 0             # ultima carga de la tabla pedida (las respuestas viejas se descartan)
        self._peticion_libros = 0      # idem para el panel de libros
        self._libros = []              # libros del autor seleccionado
        self._catalogo = None          # catalogo de books, para el buscador (se pide una vez por visita)
        self._resultados = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._construir_barra()
        self._construir_tabla()
        self._construir_panel()
        self._construir_paginacion()

    # ------------------------------------------------------------ UI
    def _construir_barra(self):
        barra = ttk.Frame(self)
        barra.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ttk.Label(barra, text="Buscar").pack(side="left")
        self.q_var = tk.StringVar()
        entrada = ttk.Entry(barra, textvariable=self.q_var, width=24)
        entrada.pack(side="left", padx=(6, 12))
        entrada.bind("<Return>", lambda _e: self._filtrar())
        ttk.Label(barra, text="Nacionalidad").pack(side="left")
        self.nacionalidad_var = tk.StringVar()
        entrada = ttk.Entry(barra, textvariable=self.nacionalidad_var, width=14)
        entrada.pack(side="left", padx=(6, 12))
        entrada.bind("<Return>", lambda _e: self._filtrar())
        ttk.Button(barra, text="Buscar", style="Primary.TButton", command=self._filtrar).pack(side="left", padx=3)
        ttk.Button(barra, text="Limpiar", command=self._limpiar).pack(side="left", padx=3)

        # Solo admin (se muestra u oculta en on_show segun el rol).
        self.acciones_admin = ttk.Frame(barra)
        ttk.Button(self.acciones_admin, text="Eliminar", style="Eliminar.TButton", command=self._eliminar).pack(
            side="right", padx=(6, 0))
        ttk.Button(self.acciones_admin, text="Editar", style="Editar.TButton", command=self._editar).pack(
            side="right", padx=(6, 0))
        ttk.Button(self.acciones_admin, text="+ Nuevo autor", style="Crear.TButton", command=self._crear).pack(
            side="right")

    def _construir_tabla(self):
        marco = tk.Frame(self, background=theme.COLOR_SUPERFICIE, highlightthickness=1,
                         highlightbackground=theme.COLOR_BORDE)
        marco.grid(row=1, column=0, sticky="nsew")
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)

        self.tabla = ttk.Treeview(marco, columns=[c[0] for c in _COLUMNAS], show="headings", selectmode="browse")
        for clave, encabezado, ancho, ancla in _COLUMNAS:
            self.tabla.heading(clave, text=encabezado, anchor=ancla)
            self.tabla.column(clave, width=ancho, minwidth=40, anchor=ancla, stretch=clave == "autor")
        self.tabla.tag_configure("par", background=theme.COLOR_SUPERFICIE)
        self.tabla.tag_configure("impar", background=theme.COLOR_FILA_ALTERNA)
        self.tabla.bind("<<TreeviewSelect>>", lambda _e: self._al_seleccionar())
        self.tabla.bind("<Double-1>", lambda _e: self._editar() if self.app.sesion.es_admin else None)

        scroll = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def _construir_panel(self):
        panel = ttk.Frame(self, style="Card.TFrame", padding=(14, 12), width=340)
        panel.grid(row=1, column=1, sticky="ns", padx=(10, 0))
        panel.pack_propagate(False)

        ttk.Label(panel, text="Libros del autor", style="Subtitulo.TLabel").pack(anchor="w")
        self.autor_var = tk.StringVar(value="—")
        ttk.Label(panel, textvariable=self.autor_var, style="Card.TLabel", font=theme.FUENTE_SUBTITULO,
                  wraplength=305, justify="left").pack(anchor="w", pady=(2, 0))
        self.datos_var = tk.StringVar(value="Selecciona un autor de la tabla.")
        ttk.Label(panel, textvariable=self.datos_var, style="Subtitulo.TLabel", wraplength=305,
                  justify="left").pack(anchor="w", pady=(2, 8))

        self.tabla_libros = ttk.Treeview(panel, columns=("isbn", "titulo"), show="headings",
                                         selectmode="browse", height=6)
        for clave, encabezado, ancho, ancla in (("isbn", "ISBN", 110, "w"), ("titulo", "Título", 185, "w")):
            self.tabla_libros.heading(clave, text=encabezado, anchor=ancla)
            self.tabla_libros.column(clave, width=ancho, minwidth=30, anchor=ancla, stretch=clave == "titulo")
        self.tabla_libros.pack(fill="x")
        self.libros_var = tk.StringVar()
        ttk.Label(panel, textvariable=self.libros_var, style="Subtitulo.TLabel", wraplength=305,
                  justify="left").pack(anchor="w", pady=(4, 0))

        # ---- solo admin: quitar relacion y relacionar un libro
        self.panel_admin = ttk.Frame(panel, style="CardInner.TFrame")
        self.boton_quitar = ttk.Button(self.panel_admin, text="Quitar relación", style="Eliminar.TButton",
                                       command=self._quitar)
        self.boton_quitar.pack(fill="x", pady=(6, 10))

        ttk.Label(self.panel_admin, text="Relacionar un libro", style="Card.TLabel",
                  font=theme.FUENTE_NEGRITA).pack(anchor="w")
        buscador = ttk.Frame(self.panel_admin, style="CardInner.TFrame")
        buscador.pack(fill="x", pady=(4, 4))
        buscador.grid_columnconfigure(0, weight=1)
        self.libro_var = tk.StringVar()
        entrada = ttk.Entry(buscador, textvariable=self.libro_var)
        entrada.grid(row=0, column=0, sticky="ew")
        entrada.bind("<Return>", lambda _e: self._buscar_libro())
        ttk.Button(buscador, text="Buscar", command=self._buscar_libro).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(self.panel_admin, text="Por ISBN o título (catálogo del servicio de libros)",
                  style="Subtitulo.TLabel").pack(anchor="w")

        self.lista_resultados = tk.Listbox(self.panel_admin, height=5, activestyle="none", exportselection=False,
                                           font=theme.FUENTE_PEQUENA, relief="solid", borderwidth=1,
                                           highlightthickness=0, selectbackground=theme.COLOR_SELECCION,
                                           selectforeground=theme.COLOR_TEXTO)
        self.lista_resultados.pack(fill="x", pady=(4, 6))
        pie = ttk.Frame(self.panel_admin, style="CardInner.TFrame")
        pie.pack(fill="x")
        self.boton_relacionar = ttk.Button(pie, text="Relacionar", style="Crear.TButton", command=self._relacionar)
        self.boton_relacionar.pack(side="left", fill="x", expand=True)

    def _construir_paginacion(self):
        barra = ttk.Frame(self)
        barra.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.boton_anterior = ttk.Button(barra, text="« Anterior", command=lambda: self._ir_a(self.pagina - 1))
        self.boton_anterior.pack(side="left")
        self.pagina_var = tk.StringVar()
        ttk.Label(barra, textvariable=self.pagina_var).pack(side="left", padx=12)
        self.boton_siguiente = ttk.Button(barra, text="Siguiente »", command=lambda: self._ir_a(self.pagina + 1))
        self.boton_siguiente.pack(side="left")
        self.total_var = tk.StringVar()
        ttk.Label(barra, textvariable=self.total_var, style="Info.TLabel").pack(side="left", padx=14)
        ttk.Button(barra, text="Actualizar", command=self._cargar).pack(side="right")

    # ------------------------------------------------------------ ciclo de vida
    def on_show(self):
        # Las acciones de admin se ocultan para el cliente.
        if self.app.sesion.es_admin:
            self.acciones_admin.pack(side="right")
            self.panel_admin.pack(fill="x")
        else:
            self.acciones_admin.pack_forget()
            self.panel_admin.pack_forget()
        self._catalogo = None
        self._cargar()

    def _error(self, e, titulo="No se pudo completar la operación"):
        if isinstance(e, ApiError) and e.es_sesion_invalida:
            self.app.sesion_invalida(e)
            return
        mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
        self.app.set_estado(f"{getattr(e, 'status', None) or '—'} {mensaje}", "error")
        messagebox.showerror(titulo, mensaje, parent=self.app)

    def _hecho(self, mensaje):
        self.app.set_estado(mensaje, "ok")
        self._cargar()

    # ------------------------------------------------------------ tabla de autores
    def _filtrar(self):
        self.pagina = 1
        self._cargar()

    def _limpiar(self):
        self.q_var.set("")
        self.nacionalidad_var.set("")
        self._filtrar()

    def _ir_a(self, pagina):
        if 1 <= pagina <= max(self.paginas, 1):
            self.pagina = pagina
            self._cargar()

    def _cargar(self):
        self.pagina_var.set("Cargando...")
        filtros = dict(q=self.q_var.get().strip(), nacionalidad=self.nacionalidad_var.get().strip(),
                       page=self.pagina, per_page=POR_PAGINA)
        self._peticion += 1
        numero = self._peticion
        run_async(self, lambda: self.app.authors.list(**filtros),
                  lambda datos: numero == self._peticion and self._recibir_pagina(datos),
                  lambda e: numero == self._peticion and self._error_de_carga(e))

    def _error_de_carga(self, e):
        self.pagina_var.set("")
        self._renderizar([])
        self._error(e, "No se pudo cargar la lista de autores")

    def _recibir_pagina(self, datos):
        self.paginas = datos.get("pages", 0)
        if self.pagina > max(self.paginas, 1):          # la ultima pagina se quedo vacia
            self.pagina = max(self.paginas, 1)
            self._cargar()
            return
        self.total_var.set(f"{datos.get('total', 0)} autor(es)")
        self.pagina_var.set(f"Página {self.pagina} de {max(self.paginas, 1)}")
        self.boton_anterior.state(["!disabled"] if self.pagina > 1 else ["disabled"])
        self.boton_siguiente.state(["!disabled"] if self.pagina < self.paginas else ["disabled"])
        self._renderizar(datos.get("items", []))

    def _renderizar(self, autores):
        self.tabla.delete(*self.tabla.get_children())
        self._por_iid = {}
        a_seleccionar = None
        for i, autor in enumerate(autores):
            iid = self.tabla.insert("", "end", tags=("par" if i % 2 == 0 else "impar",), values=(
                autor["id_autor"], autor["nombre"], autor.get("nacionalidad") or "—",
                autor.get("total_libros", 0)))
            self._por_iid[iid] = autor
            if autor["id_autor"] == self._seleccion_id:
                a_seleccionar = iid
        if a_seleccionar:
            self.tabla.selection_set(a_seleccionar)      # conserva la seleccion; dispara _al_seleccionar
        else:
            self._seleccion_id = None
            self._al_seleccionar()

    def _seleccionado(self):
        seleccion = self.tabla.selection()
        autor = self._por_iid.get(seleccion[0]) if seleccion else None
        if autor is None:
            self.app.set_estado("Selecciona un autor de la tabla primero.", "info")
        return autor

    # ------------------------------------------------------------ panel de libros
    def _al_seleccionar(self):
        seleccion = self.tabla.selection()
        autor = self._por_iid.get(seleccion[0]) if seleccion else None
        self._seleccion_id = autor["id_autor"] if autor else None
        self._peticion_libros += 1
        self._pintar_libros([])
        if autor is None:
            self.autor_var.set("—")
            self.datos_var.set("Selecciona un autor de la tabla.")
            self.libros_var.set("")
            return
        self.autor_var.set(autor["nombre"])
        self.datos_var.set(autor.get("nacionalidad") or "Nacionalidad sin registrar")
        self.libros_var.set("Cargando libros...")
        numero = self._peticion_libros
        run_async(self, lambda: self.app.authors.books(autor["id_autor"]),
                  lambda datos: numero == self._peticion_libros and self._recibir_libros(datos),
                  lambda e: numero == self._peticion_libros and self.libros_var.set(
                      f"No se pudieron cargar: {e.mensaje if isinstance(e, ApiError) else e}"))

    def _recibir_libros(self, datos):
        libros = datos.get("books", [])
        self._pintar_libros(libros)
        if not libros:
            self.libros_var.set("Sin libros relacionados.")
        elif not datos.get("enriquecido", True):
            self.libros_var.set("El servicio de libros no responde: se muestran solo los ISBN.")
        else:
            self.libros_var.set(f"{len(libros)} libro(s) relacionado(s).")

    def _pintar_libros(self, libros):
        self._libros = libros
        self.tabla_libros.delete(*self.tabla_libros.get_children())
        for libro in libros:
            self.tabla_libros.insert("", "end", iid=libro["isbn"],
                                     values=(libro["isbn"], libro.get("titulo") or "—"))

    # ------------------------------------------------------------ admin: autores
    def _valores_de_autor(self, valores):
        if not valores["nombre"].strip():
            raise ValueError("El nombre es obligatorio.")
        return {clave: (valor.strip() or None) for clave, valor in valores.items()}

    def _crear(self):
        FormDialog(self.app, "Nuevo autor", "POST /authors — solo el nombre es obligatorio.",
                   [Campo(clave, etiqueta) for clave, etiqueta in _CAMPOS],
                   lambda valores: self.app.authors.create(**self._valores_de_autor(valores)),
                   lambda a: self._hecho(f"201 Autor creado: {a['nombre']} (ID {a['id_autor']})"),
                   texto_boton="Crear", estilo_boton="Crear.TButton")

    def _editar(self):
        autor = self._seleccionado()
        if autor is None:
            return
        FormDialog(self.app, "Editar autor", f"PUT /authors/{autor['id_autor']} — {autor['nombre']}",
                   [Campo(clave, etiqueta, valor=autor.get(clave) or "") for clave, etiqueta in _CAMPOS],
                   lambda valores: self.app.authors.update(autor["id_autor"], **self._valores_de_autor(valores)),
                   lambda a: self._hecho(f"200 Autor {a['id_autor']} actualizado"), estilo_boton="Editar.TButton")

    def _eliminar(self):
        autor = self._seleccionado()
        if autor is None:
            return
        libros = autor.get("total_libros", 0)
        if libros:
            pregunta = (f"{autor['nombre']} tiene {libros} libro(s) relacionado(s).\n\n"
                        "¿Eliminar al autor JUNTO CON esas relaciones? (Los libros no se borran.)")
        else:
            pregunta = f"¿Eliminar a {autor['nombre']}?"
        if not messagebox.askyesno("Eliminar autor", pregunta, parent=self.app, icon="warning"):
            return
        run_async(self, lambda: self.app.authors.delete(autor["id_autor"], force=bool(libros)),
                  lambda _r: self._hecho(f"200 Autor {autor['nombre']} eliminado"), self._error)

    # ------------------------------------------------------------ admin: relaciones
    def _quitar(self):
        autor = self._seleccionado()
        seleccion = self.tabla_libros.selection()
        if autor is None:
            return
        if not seleccion:
            self.app.set_estado("Selecciona un libro del autor para quitar la relación.", "info")
            return
        isbn = seleccion[0]
        titulo = next((l.get("titulo") for l in self._libros if l["isbn"] == isbn), None) or isbn
        if not messagebox.askyesno("Quitar relación",
                                   f"¿Quitar «{titulo}» de los libros de {autor['nombre']}?\n\n"
                                   "El libro y el autor no se borran.", parent=self.app, icon="warning"):
            return
        run_async(self, lambda: self.app.authors.remove_book(autor["id_autor"], isbn),
                  lambda _r: self._hecho(f"200 Relación con {isbn} eliminada"), self._error)

    def _buscar_libro(self):
        termino = self.libro_var.get().strip().lower()
        if not termino:
            self.app.set_estado("Escribe un ISBN o parte del título.", "info")
            return

        def mostrar(catalogo):
            self._catalogo = catalogo if isinstance(catalogo, list) else []
            self._resultados = [l for l in self._catalogo
                                if termino in str(l.get("isbn", "")).lower()
                                or termino in str(l.get("titulo", "")).lower()][:MAX_RESULTADOS]
            self.lista_resultados.delete(0, "end")
            for libro in self._resultados:
                self.lista_resultados.insert("end", f"{libro.get('isbn')}  ·  {libro.get('titulo')}")
            if self._resultados:
                self.lista_resultados.selection_set(0)
            self.app.set_estado(f"{len(self._resultados)} libro(s) encontrados para «{termino}»",
                                "ok" if self._resultados else "info")

        if self._catalogo is not None:
            mostrar(self._catalogo)
        else:
            run_async(self, self.app.books.list_books, mostrar,
                      lambda e: self._error(e, "No se pudo consultar el catálogo de libros"))

    def _relacionar(self):
        autor = self._seleccionado()
        if autor is None:
            return
        seleccion = self.lista_resultados.curselection()
        if not seleccion:
            self.app.set_estado("Busca un libro y selecciónalo en la lista para relacionarlo.", "info")
            return
        libro = self._resultados[seleccion[0]]

        def ok(relacion):
            self._hecho(f"201 «{relacion.get('titulo') or relacion['isbn']}» relacionado con {autor['nombre']}")

        run_async(self, lambda: self.app.authors.add_book(autor["id_autor"], libro["isbn"]), ok, self._error)
