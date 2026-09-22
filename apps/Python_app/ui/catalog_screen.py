"""
ui/catalog_screen.py
Catalogo de libros: semaforo de salud de los dos microservicios,
buscador y tarjetas con insertar/editar/eliminar. Solo se llega aqui
desde LoginScreen tras autenticarse.
"""
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import api_client
from api_client import ApiError
from ui.book_form import BookForm
from utils import run_async

INTERVALO_SEMAFORO_MS = 8000


class CatalogScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(16, 12))
        self.app = app
        self._todos_libros = []
        self._semaforo_iniciado = False

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._construir_barra_superior()
        self._construir_barra_busqueda()

        self.estado_var = tk.StringVar()
        ttk.Label(self, textvariable=self.estado_var).grid(row=2, column=0, sticky="w", pady=(4, 4))

        self._construir_lista()

    # ---------------------------------------------------------- UI
    def _construir_barra_superior(self):
        barra = ttk.Frame(self)
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        barra.grid_columnconfigure(4, weight=1)

        ttk.Label(barra, text="Login:").grid(row=0, column=0, padx=(0, 2))
        self.luz_login = ttk.Label(barra, text="●", font=("Segoe UI", 14))
        self.luz_login.grid(row=0, column=1, padx=(0, 12))

        ttk.Label(barra, text="Libros:").grid(row=0, column=2, padx=(0, 2))
        self.luz_books = ttk.Label(barra, text="●", font=("Segoe UI", 14))
        self.luz_books.grid(row=0, column=3, padx=(0, 12))

        self.usuario_var = tk.StringVar()
        ttk.Label(barra, textvariable=self.usuario_var).grid(row=0, column=4, sticky="e", padx=8)
        ttk.Button(barra, text="Configuración", command=lambda: self.app.mostrar("config")).grid(
            row=0, column=5, padx=4)
        ttk.Button(barra, text="Cerrar sesión", command=self.app.cerrar_sesion).grid(
            row=0, column=6, padx=4)

    def _construir_barra_busqueda(self):
        barra = ttk.Frame(self)
        barra.grid(row=1, column=0, sticky="ew", pady=(0, 4))

        self.busqueda_var = tk.StringVar()
        entrada = ttk.Entry(barra, textvariable=self.busqueda_var, width=32)
        entrada.grid(row=0, column=0, padx=(0, 4))
        entrada.bind("<Return>", lambda e: self._buscar())

        ttk.Button(barra, text="Buscar", command=self._buscar).grid(row=0, column=1, padx=4)
        ttk.Button(barra, text="Mostrar todos", command=self._mostrar_todos).grid(row=0, column=2, padx=4)
        ttk.Button(barra, text="+ Insertar libro", command=self._insertar).grid(row=0, column=3, padx=(16, 4))
        ttk.Button(barra, text="Actualizar catálogo", command=self._cargar_libros).grid(row=0, column=4, padx=4)

    def _construir_lista(self):
        contenedor = ttk.Frame(self)
        contenedor.grid(row=3, column=0, sticky="nsew")
        contenedor.grid_rowconfigure(0, weight=1)
        contenedor.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(contenedor, highlightthickness=0)
        scrollbar = ttk.Scrollbar(contenedor, orient="vertical", command=self._canvas.yview)
        self._lista_frame = ttk.Frame(self._canvas)

        self._lista_frame.bind(
            "<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        )
        self._canvas.create_window((0, 0), window=self._lista_frame, anchor="nw")
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._canvas.bind_all("<MouseWheel>", self._sobre_rueda)

    def _sobre_rueda(self, evento):
        if self.app.pantalla_actual == "catalog":
            self._canvas.yview_scroll(int(-1 * (evento.delta / 120)), "units")

    # ---------------------------------------------------------- ciclo de vida
    def on_show(self):
        usuario = self.app.usuario_actual or {}
        nombre = " ".join(filter(None, [usuario.get("nombre"), usuario.get("apellido_paterno")]))
        self.usuario_var.set(f"Sesión: {nombre}" if nombre else "")
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
        etiqueta.configure(foreground="#16a34a" if activo else "#dc2626")

    # ---------------------------------------------------------- datos
    def _cargar_libros(self):
        self.estado_var.set("Cargando catálogo...")

        def hacer():
            return self.app.books.list_books()

        def ok(libros):
            self._todos_libros = libros if isinstance(libros, list) else []
            self._aplicar_busqueda()

        def error(e):
            self._todos_libros = []
            self.estado_var.set(e.mensaje if isinstance(e, ApiError) else str(e))
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
        self.estado_var.set(f"{len(filtrados)} libro(s) de {len(self._todos_libros)}.")
        self._renderizar(filtrados)

    # ---------------------------------------------------------- tarjetas
    def _renderizar(self, libros):
        for hijo in self._lista_frame.winfo_children():
            hijo.destroy()

        if not libros:
            ttk.Label(self._lista_frame, text="No hay libros que mostrar.").grid(row=0, column=0, pady=16)
            return

        self._lista_frame.grid_columnconfigure(0, weight=1)
        for fila, libro in enumerate(libros):
            self._crear_tarjeta(libro).grid(row=fila, column=0, sticky="ew", pady=4, padx=2)

    def _crear_tarjeta(self, libro):
        tarjeta = ttk.LabelFrame(self._lista_frame, text=libro.get("titulo") or "(sin título)")
        tarjeta.grid_columnconfigure(0, weight=1)

        info = (
            f"ISBN: {libro.get('isbn')}    Autor: {libro.get('autor') or '—'}    "
            f"Género: {libro.get('genero') or '—'}\n"
            f"Año: {libro.get('anio')}    Precio: ${libro.get('precio')}    "
            f"Stock: {libro.get('stock')}    Formato: {libro.get('formato')}"
        )
        ttk.Label(tarjeta, text=info, justify="left").grid(row=0, column=0, sticky="w", padx=8, pady=6)

        botones = ttk.Frame(tarjeta)
        botones.grid(row=0, column=1, sticky="e", padx=8)
        portada = libro.get("portada") or libro.get("image_url")
        if portada:
            ttk.Button(botones, text="Ver portada", command=lambda u=portada: webbrowser.open(u)).grid(
                row=0, column=0, padx=2)
        ttk.Button(botones, text="Editar", command=lambda l=libro: self._editar(l)).grid(row=0, column=1, padx=2)
        ttk.Button(botones, text="Eliminar", command=lambda l=libro: self._eliminar(l)).grid(row=0, column=2, padx=2)
        return tarjeta

    # ---------------------------------------------------------- acciones
    def _insertar(self):
        BookForm(self.app, modo="crear", on_guardado=self._cargar_libros)

    def _editar(self, libro):
        BookForm(self.app, modo="editar", on_guardado=self._cargar_libros, libro=libro)

    def _eliminar(self, libro):
        isbn = libro.get("isbn")
        if not messagebox.askyesno("Eliminar libro", f"¿Eliminar el libro {isbn} — {libro.get('titulo')}?"):
            return

        def hacer():
            return self.app.books.delete_book(isbn)

        def ok(_resultado):
            self._cargar_libros()

        def error(e):
            messagebox.showerror("No se pudo eliminar", e.mensaje if isinstance(e, ApiError) else str(e))

        run_async(self, hacer, ok, error)
