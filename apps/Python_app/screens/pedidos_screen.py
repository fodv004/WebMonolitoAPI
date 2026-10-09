"""
screens/pedidos_screen.py
Pantalla Pedidos (microservicio pedidos), tipo carrito y seguimiento.

Pestaña "Comprar" (todos):
  izquierda  catalogo con el stock disponible y boton para agregar
  centro     carrito con cantidades editables y total
  derecha    "Mis pedidos" con el estado en color, detalle (lineas e
             historial) y botones editar, cancelar e "Ir a pagar"

Pestañas solo para el admin:
  "Gestión"     cambiar el estado de cualquier pedido
  "Inventario"  editar el stock de cada libro (PATCH /books/<isbn>)

El stock es el de books (libros.stock): pedidos lo reserva al crear un
pedido y lo libera al cancelarlo o expirar.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from api.http_base import ApiError
from utils import run_async
from widgets import theme
from widgets.tooltip import Tooltip

ESTADOS = ("PENDIENTE_PAGO", "PAGADO", "ENVIADO", "ENTREGADO", "CANCELADO", "EXPIRADO")
# estado -> (color del texto, fondo): amarillo, verde, azul, gris y rojo
COLORES_ESTADO = {
    "PENDIENTE_PAGO": ("#854d0e", "#fef08a"),
    "PAGADO": ("#166534", "#bbf7d0"),
    "ENVIADO": ("#1e40af", "#bfdbfe"),
    "ENTREGADO": ("#374151", "#e5e7eb"),
    "CANCELADO": ("#991b1b", "#fecaca"),
    "EXPIRADO": ("#991b1b", "#fecaca"),
}
CANTIDAD_MAXIMA = 999


def dinero(valor):
    return f"${float(valor):,.2f}"


def _fecha(texto):
    return (texto or "—").replace("T", " ")[:16]


def texto_del_pedido(pedido):
    """Detalle legible de un pedido: lineas, total, vencimiento de la reserva e historial."""
    lineas = [f"Pedido #{pedido['id']} — {pedido['estado']}   (usuario {pedido['user_id']})", ""]
    for l in pedido.get("lineas", []):
        lineas.append(f"  {l['cantidad']} × {l['titulo']}")
        lineas.append(f"      {l['isbn']}   {dinero(l['precio_unitario'])} c/u   = {dinero(l['subtotal'])}")
    lineas += ["", f"  TOTAL: {dinero(pedido['total'])}"]
    if pedido["estado"] == "PENDIENTE_PAGO":
        lineas.append(f"  La reserva de stock vence: {_fecha(pedido.get('expira_en'))}")
    lineas += ["", "Historial:"]
    for h in pedido.get("historial", []):
        lineas.append(f"  {_fecha(h['fecha'])}  {h['estado_anterior'] or 'creado'} → {h['estado_nuevo']}  ({h['actor']})")
    return "\n".join(lineas)


def _tabla(parent, columnas, alto=None):
    """Treeview con scroll dentro de un marco. columnas: (clave, encabezado, ancho, ancla, estira)."""
    marco = tk.Frame(parent, background=theme.COLOR_SUPERFICIE, highlightthickness=1,
                     highlightbackground=theme.COLOR_BORDE)
    marco.grid_rowconfigure(0, weight=1)
    marco.grid_columnconfigure(0, weight=1)
    opciones = {"height": alto} if alto else {}
    tabla = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings", selectmode="browse", **opciones)
    for clave, encabezado, ancho, ancla, estira in columnas:
        tabla.heading(clave, text=encabezado, anchor=ancla)
        tabla.column(clave, width=ancho, minwidth=30, anchor=ancla, stretch=estira)
    for estado, (texto, fondo) in COLORES_ESTADO.items():
        tabla.tag_configure(estado, foreground=texto, background=fondo)
    scroll = ttk.Scrollbar(marco, orient="vertical", command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    tabla.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    return marco, tabla


def _detalle(parent, alto):
    texto = tk.Text(parent, height=alto, wrap="word", font=theme.FUENTE_PEQUENA, relief="solid", borderwidth=1,
                    background=theme.COLOR_SUPERFICIE, foreground=theme.COLOR_TEXTO, state="disabled",
                    highlightthickness=0, padx=8, pady=6)
    return texto


def _escribir(texto, contenido):
    texto.configure(state="normal")
    texto.delete("1.0", "end")
    texto.insert("1.0", contenido)
    texto.configure(state="disabled")


class _Base(ttk.Frame):
    def __init__(self, parent, pantalla):
        super().__init__(parent, padding=(10, 10))
        self.pantalla = pantalla
        self.app = pantalla.app

    def _error(self, e, titulo="No se pudo completar la operación"):
        if isinstance(e, ApiError) and e.es_sesion_invalida:
            self.app.sesion_invalida(e)
            return
        mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
        self.app.set_estado(f"{getattr(e, 'status', None) or '—'} {mensaje}", "error")
        messagebox.showerror(titulo, mensaje, parent=self.app)


class PedidosScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(12, 10))
        self.app = app
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.pestanas = ttk.Notebook(self)
        self.pestanas.grid(row=0, column=0, sticky="nsew")
        self.comprar = ComprarTab(self.pestanas, self)
        self.gestion = GestionTab(self.pestanas, self)
        self.inventario = InventarioTab(self.pestanas, self)
        self.pestanas.add(self.comprar, text="  Comprar  ")
        self.pestanas.bind("<<NotebookTabChanged>>", lambda _e: self._al_cambiar_de_pestana())

    def _pestana_actual(self):
        return self.pestanas.nametowidget(self.pestanas.select())

    def _al_cambiar_de_pestana(self):
        # El Notebook tambien lanza este evento al construirse: solo se cargan datos con la
        # pantalla visible y con sesion.
        if self.app.sesion.activa and getattr(self.app, "pantalla_actual", None) == "pedidos":
            self._pestana_actual().recargar()

    def on_show(self):
        # Las pestañas de administracion solo existen para el admin.
        visibles = set(self.pestanas.tabs())
        for pestana, titulo in ((self.gestion, "  Gestión  "), (self.inventario, "  Inventario  ")):
            if self.app.sesion.es_admin and str(pestana) not in visibles:
                self.pestanas.add(pestana, text=titulo)
            elif not self.app.sesion.es_admin and str(pestana) in visibles:
                self.pestanas.forget(pestana)
        if not self.app.sesion.es_admin:
            self.pestanas.select(self.comprar)
        self.comprar.reiniciar()
        self._pestana_actual().recargar()

    def catalogo_con_stock(self):
        """Libros de books con su stock (libros.stock). Se llama desde un hilo."""
        libros = self.app.books.list_books()
        return [{"isbn": l.get("isbn"), "titulo": l.get("titulo") or "—", "precio": float(l.get("precio") or 0),
                 "disponible": int(l.get("stock") or 0)}
                for l in (libros if isinstance(libros, list) else [])]


# ====================================================================== COMPRAR
class ComprarTab(_Base):
    def __init__(self, parent, pantalla):
        super().__init__(parent, pantalla)
        self.catalogo = []
        self._visibles = {}            # iid del catalogo -> libro
        self.carrito = {}              # isbn -> {"titulo", "precio", "cantidad"}
        self.editando = None           # id del pedido que se esta editando (None = pedido nuevo)
        self.pedido = None             # pedido seleccionado en "Mis pedidos" (con lineas e historial)
        self._peticion_detalle = 0

        self.grid_rowconfigure(0, weight=1)
        for columna, peso in enumerate((5, 4, 5)):
            self.grid_columnconfigure(columna, weight=peso, uniform="comprar")
        self._construir_catalogo()
        self._construir_carrito()
        self._construir_mis_pedidos()

    # ------------------------------------------------------------ UI
    def _construir_catalogo(self):
        col = ttk.Frame(self)
        col.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        col.grid_rowconfigure(2, weight=1)
        col.grid_columnconfigure(0, weight=1)
        ttk.Label(col, text="Catálogo", font=theme.FUENTE_SUBTITULO).grid(row=0, column=0, sticky="w")
        self.buscar_var = tk.StringVar()
        entrada = ttk.Entry(col, textvariable=self.buscar_var)
        entrada.grid(row=1, column=0, sticky="ew", pady=(4, 6))
        self.buscar_var.trace_add("write", lambda *_: self._pintar_catalogo())
        marco, self.tabla_catalogo = _tabla(col, [("titulo", "Título", 150, "w", True), ("precio", "Precio", 68, "e", False),
                                                  ("disp", "Disp.", 44, "center", False)])
        marco.grid(row=2, column=0, sticky="nsew")
        self.tabla_catalogo.tag_configure("agotado", foreground=theme.COLOR_TEXTO_SUAVE)
        self.tabla_catalogo.bind("<Double-1>", lambda _e: self._agregar())
        ttk.Button(col, text="Agregar al carrito →", style="Crear.TButton", command=self._agregar).grid(
            row=3, column=0, sticky="ew", pady=(6, 0))

    def _construir_carrito(self):
        col = ttk.Frame(self)
        col.grid(row=0, column=1, sticky="nsew", padx=4)
        col.grid_rowconfigure(1, weight=1)
        col.grid_columnconfigure(0, weight=1)
        self.titulo_carrito = tk.StringVar(value="Carrito")
        ttk.Label(col, textvariable=self.titulo_carrito, font=theme.FUENTE_SUBTITULO).grid(row=0, column=0, sticky="w",
                                                                                           pady=(0, 4))
        marco, self.tabla_carrito = _tabla(col, [("titulo", "Título", 120, "w", True), ("cant", "Cant.", 44, "center", False),
                                                 ("subtotal", "Subtotal", 76, "e", False)])
        marco.grid(row=1, column=0, sticky="nsew")
        self.tabla_carrito.bind("<<TreeviewSelect>>", lambda _e: self._linea_seleccionada())

        editor = ttk.Frame(col)
        editor.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(editor, text="Cantidad").pack(side="left")
        self.cantidad_var = tk.StringVar(value="1")
        self.spin = ttk.Spinbox(editor, from_=1, to=CANTIDAD_MAXIMA, textvariable=self.cantidad_var, width=5,
                                command=self._aplicar_cantidad)
        self.spin.pack(side="left", padx=(6, 6))
        self.spin.bind("<Return>", lambda _e: self._aplicar_cantidad())
        self.spin.bind("<FocusOut>", lambda _e: self._aplicar_cantidad())
        ttk.Button(editor, text="Quitar", command=self._quitar).pack(side="left")

        self.total_var = tk.StringVar(value="Total: $0.00")
        ttk.Label(col, textvariable=self.total_var, font=theme.FUENTE_SUBTITULO).grid(row=3, column=0, sticky="e",
                                                                                      pady=(8, 4))
        botones = ttk.Frame(col)
        botones.grid(row=4, column=0, sticky="ew")
        botones.grid_columnconfigure((0, 1), weight=1, uniform="carrito")
        self.boton_confirmar = ttk.Button(botones, text="Crear pedido", style="Primary.TButton", command=self._confirmar)
        self.boton_confirmar.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.boton_vaciar = ttk.Button(botones, text="Vaciar", command=self._vaciar)
        self.boton_vaciar.grid(row=0, column=1, sticky="ew", padx=(3, 0))

    def _construir_mis_pedidos(self):
        col = ttk.Frame(self)
        col.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        col.grid_rowconfigure(1, weight=2)
        col.grid_rowconfigure(2, weight=3)
        col.grid_columnconfigure(0, weight=1)
        ttk.Label(col, text="Mis pedidos", font=theme.FUENTE_SUBTITULO).grid(row=0, column=0, sticky="w", pady=(0, 4))
        marco, self.tabla_pedidos = _tabla(col, [("id", "#", 34, "center", False), ("estado", "Estado", 110, "w", True),
                                                 ("total", "Total", 74, "e", False), ("fecha", "Creado", 100, "w", False)],
                                           alto=6)
        marco.grid(row=1, column=0, sticky="nsew")
        self.tabla_pedidos.bind("<<TreeviewSelect>>", lambda _e: self._pedido_seleccionado())
        self.detalle = _detalle(col, 9)
        self.detalle.grid(row=2, column=0, sticky="nsew", pady=(6, 6))

        botones = ttk.Frame(col)
        botones.grid(row=3, column=0, sticky="ew")
        botones.grid_columnconfigure((0, 1, 2), weight=1, uniform="pedidos")
        self.boton_editar = ttk.Button(botones, text="Editar", style="Editar.TButton", command=self._editar)
        self.boton_editar.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.boton_cancelar = ttk.Button(botones, text="Cancelar", style="Eliminar.TButton", command=self._cancelar)
        self.boton_cancelar.grid(row=0, column=1, sticky="ew", padx=3)
        self.boton_pagar = ttk.Button(botones, text="Ir a pagar", style="Crear.TButton", command=self._ir_a_pagar)
        self.boton_pagar.grid(row=0, column=2, sticky="ew", padx=(3, 0))
        Tooltip(self.boton_pagar, lambda: "Abre la pantalla Pagos con este pedido (solo pedidos pendientes de pago).")
        self._botones_de_pedido()

    # ------------------------------------------------------------ datos
    def reiniciar(self):
        """Al entrar a la pantalla (puede ser otro usuario): carrito vacio y sin edicion en curso."""
        self.carrito, self.editando, self.pedido = {}, None, None
        self._pintar_carrito()

    def recargar(self):
        self._cargar_catalogo()
        self._cargar_pedidos()

    def _cargar_catalogo(self):
        def ok(catalogo):
            self.catalogo = catalogo
            self._pintar_catalogo()

        run_async(self, self.pantalla.catalogo_con_stock, ok,
                  lambda e: self._error(e, "No se pudo cargar el catálogo"))

    def _pintar_catalogo(self):
        termino = self.buscar_var.get().strip().lower()
        self.tabla_catalogo.delete(*self.tabla_catalogo.get_children())
        self._visibles = {}
        for libro in self.catalogo:
            if termino and termino not in f"{libro['titulo']} {libro['isbn']}".lower():
                continue
            iid = self.tabla_catalogo.insert("", "end", tags=() if libro["disponible"] else ("agotado",), values=(
                libro["titulo"], dinero(libro["precio"]), libro["disponible"]))
            self._visibles[iid] = libro

    def _cargar_pedidos(self):
        user_id = (self.app.sesion.usuario or {}).get("id_usuario")
        run_async(self, lambda: self.app.pedidos.list(user_id=user_id, per_page=50), self._pintar_pedidos,
                  lambda e: self._error(e, "No se pudieron cargar tus pedidos"))

    def _pintar_pedidos(self, datos):
        seleccionado = self.pedido["id"] if self.pedido else None
        self.tabla_pedidos.delete(*self.tabla_pedidos.get_children())
        for pedido in datos.get("items", []):
            self.tabla_pedidos.insert("", "end", iid=str(pedido["id"]), tags=(pedido["estado"],), values=(
                pedido["id"], pedido["estado"].replace("_", " "), dinero(pedido["total"]), _fecha(pedido["created_at"])))
        if seleccionado is not None and self.tabla_pedidos.exists(str(seleccionado)):
            self.tabla_pedidos.selection_set(str(seleccionado))
        else:
            self.pedido = None
            _escribir(self.detalle, "Selecciona un pedido para ver sus líneas y su historial.")
            self._botones_de_pedido()

    # ------------------------------------------------------------ carrito
    def _agregar(self):
        seleccion = self.tabla_catalogo.selection()
        libro = self._visibles.get(seleccion[0]) if seleccion else None
        if libro is None:
            self.app.set_estado("Selecciona un libro del catálogo.", "info")
            return
        en_carrito = self.carrito.get(libro["isbn"], {}).get("cantidad", 0)
        if en_carrito + 1 > libro["disponible"] + self._ya_reservado(libro["isbn"]):
            self.app.set_estado(f"No hay más unidades disponibles de «{libro['titulo']}».", "error")
            return
        self.carrito.setdefault(libro["isbn"], {"titulo": libro["titulo"], "precio": libro["precio"], "cantidad": 0})
        self.carrito[libro["isbn"]]["cantidad"] += 1
        self._pintar_carrito(seleccionar=libro["isbn"])

    def _ya_reservado(self, isbn):
        """Unidades que el pedido en edicion ya tiene reservadas de ese ISBN (cuentan como disponibles para el)."""
        if self.editando is None or self.pedido is None:
            return 0
        return next((l["cantidad"] for l in self.pedido.get("lineas", []) if l["isbn"] == isbn), 0)

    def _pintar_carrito(self, seleccionar=None):
        self.tabla_carrito.delete(*self.tabla_carrito.get_children())
        total = 0
        for isbn, linea in self.carrito.items():
            subtotal = linea["precio"] * linea["cantidad"]
            total += subtotal
            self.tabla_carrito.insert("", "end", iid=isbn, values=(linea["titulo"], linea["cantidad"], dinero(subtotal)))
        self.total_var.set(f"Total: {dinero(total)}")
        if self.editando is None:
            self.titulo_carrito.set("Carrito")
            self.boton_confirmar.configure(text="Crear pedido")
            self.boton_vaciar.configure(text="Vaciar")
        else:
            self.titulo_carrito.set(f"Editando pedido #{self.editando}")
            self.boton_confirmar.configure(text="Guardar cambios")
            self.boton_vaciar.configure(text="Cancelar edición")
        self.boton_confirmar.state(["!disabled"] if self.carrito else ["disabled"])
        if seleccionar and self.tabla_carrito.exists(seleccionar):
            self.tabla_carrito.selection_set(seleccionar)

    def _linea_seleccionada(self):
        seleccion = self.tabla_carrito.selection()
        if seleccion:
            self.cantidad_var.set(str(self.carrito[seleccion[0]]["cantidad"]))

    def _aplicar_cantidad(self):
        seleccion = self.tabla_carrito.selection()
        if not seleccion:
            return
        isbn = seleccion[0]
        try:
            cantidad = int(self.cantidad_var.get())
        except ValueError:
            cantidad = 0
        if not 1 <= cantidad <= CANTIDAD_MAXIMA:
            self.cantidad_var.set(str(self.carrito[isbn]["cantidad"]))
            self.app.set_estado(f"La cantidad debe ser un entero entre 1 y {CANTIDAD_MAXIMA}.", "error")
            return
        if cantidad != self.carrito[isbn]["cantidad"]:
            self.carrito[isbn]["cantidad"] = cantidad
            self._pintar_carrito(seleccionar=isbn)

    def _quitar(self):
        seleccion = self.tabla_carrito.selection()
        if seleccion:
            del self.carrito[seleccion[0]]
            self._pintar_carrito()

    def _vaciar(self):
        self.carrito, self.editando = {}, None
        self._pintar_carrito()

    def _confirmar(self):
        if not self.carrito:
            return
        cantidades = {isbn: linea["cantidad"] for isbn, linea in self.carrito.items()}
        editando = self.editando
        self.boton_confirmar.state(["disabled"])

        def ok(pedido):
            self.carrito, self.editando, self.pedido = {}, None, pedido
            self._pintar_carrito()
            self.app.set_estado(
                f"200 Pedido #{pedido['id']} actualizado: {dinero(pedido['total'])}" if editando else
                f"201 Pedido #{pedido['id']} creado por {dinero(pedido['total'])}: stock reservado hasta "
                f"{_fecha(pedido['expira_en'])}", "ok")
            self.recargar()

        def error(e):
            self.boton_confirmar.state(["!disabled"])
            self._error(e, "No se pudo guardar el pedido")
            self._cargar_catalogo()                 # el stock pudo cambiar (409 por falta de stock)

        run_async(self, (lambda: self.app.pedidos.replace_lines(editando, cantidades)) if editando else
                  (lambda: self.app.pedidos.create(cantidades)), ok, error)

    # ------------------------------------------------------------ mis pedidos
    def _pedido_seleccionado(self):
        seleccion = self.tabla_pedidos.selection()
        if not seleccion:
            return
        self._peticion_detalle += 1
        numero, pedido_id = self._peticion_detalle, int(seleccion[0])

        def ok(pedido):
            if numero == self._peticion_detalle:
                self.pedido = pedido
                _escribir(self.detalle, texto_del_pedido(pedido))
                self._botones_de_pedido()

        run_async(self, lambda: self.app.pedidos.get(pedido_id), ok,
                  lambda e: numero == self._peticion_detalle and self._error(e, "No se pudo cargar el pedido"))

    def _botones_de_pedido(self):
        pendiente = self.pedido is not None and self.pedido["estado"] == "PENDIENTE_PAGO"
        for boton in (self.boton_editar, self.boton_cancelar, self.boton_pagar):
            boton.state(["!disabled"] if pendiente else ["disabled"])

    def _ir_a_pagar(self):
        """Abre la pantalla Pagos con el pedido seleccionado listo para pagar."""
        if self.pedido is not None and self.pedido["estado"] == "PENDIENTE_PAGO":
            self.app.ir_a_pagar(self.pedido["id"])

    def _editar(self):
        """Carga el pedido en el carrito; "Guardar cambios" reajusta la reserva de stock."""
        if self.pedido is None or self.pedido["estado"] != "PENDIENTE_PAGO":
            return
        self.editando = self.pedido["id"]
        self.carrito = {l["isbn"]: {"titulo": l["titulo"], "precio": l["precio_unitario"], "cantidad": l["cantidad"]}
                        for l in self.pedido["lineas"]}
        self._pintar_carrito()
        self.app.set_estado(f"Editando el pedido #{self.editando}: cambia el carrito y pulsa Guardar cambios.", "info")

    def _cancelar(self):
        if self.pedido is None:
            return
        pedido_id = self.pedido["id"]
        if not messagebox.askyesno("Cancelar pedido", f"¿Cancelar el pedido #{pedido_id}?\n\n"
                                   "Se liberará el stock reservado. No se puede deshacer.",
                                   parent=self.app, icon="warning"):
            return

        def ok(pedido):
            if self.editando == pedido_id:
                self._vaciar()
            self.pedido = pedido
            self.app.set_estado(f"200 Pedido #{pedido_id} cancelado: el stock quedó liberado", "ok")
            self.recargar()

        run_async(self, lambda: self.app.pedidos.cancel(pedido_id), ok, self._error)


# ====================================================================== GESTION (admin)
class GestionTab(_Base):
    def __init__(self, parent, pantalla):
        super().__init__(parent, pantalla)
        self.pedido = None
        self._peticion = 0
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)

        barra = ttk.Frame(self)
        barra.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(barra, text="Estado").pack(side="left")
        self.estado_var = tk.StringVar(value="Todos")
        combo = ttk.Combobox(barra, textvariable=self.estado_var, values=("Todos",) + ESTADOS, state="readonly", width=16)
        combo.pack(side="left", padx=(6, 12))
        combo.bind("<<ComboboxSelected>>", lambda _e: self.recargar())
        ttk.Label(barra, text="ID de usuario").pack(side="left")
        self.usuario_var = tk.StringVar()
        entrada = ttk.Entry(barra, textvariable=self.usuario_var, width=8)
        entrada.pack(side="left", padx=(6, 12))
        entrada.bind("<Return>", lambda _e: self.recargar())
        ttk.Button(barra, text="Filtrar", style="Primary.TButton", command=self.recargar).pack(side="left", padx=3)
        self.total_var = tk.StringVar()
        ttk.Label(barra, textvariable=self.total_var, style="Info.TLabel").pack(side="left", padx=12)

        marco, self.tabla = _tabla(self, [("id", "#", 40, "center", False), ("usuario", "Usuario", 60, "center", False),
                                          ("estado", "Estado", 120, "w", True), ("total", "Total", 80, "e", False),
                                          ("articulos", "Art.", 40, "center", False),
                                          ("fecha", "Creado", 110, "w", False)])
        marco.grid(row=1, column=0, sticky="nsew")
        self.tabla.bind("<<TreeviewSelect>>", lambda _e: self._seleccionado())

        lado = ttk.Frame(self)
        lado.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        lado.grid_rowconfigure(0, weight=1)
        lado.grid_columnconfigure(0, weight=1)
        self.detalle = _detalle(lado, 12)
        self.detalle.grid(row=0, column=0, sticky="nsew")
        botones = ttk.Frame(lado)
        botones.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        botones.grid_columnconfigure((0, 1), weight=1, uniform="gestion")
        self.botones = {
            "ENVIADO": ttk.Button(botones, text="Marcar ENVIADO", style="Editar.TButton",
                                  command=lambda: self._cambiar("ENVIADO")),
            "ENTREGADO": ttk.Button(botones, text="Marcar ENTREGADO", style="Editar.TButton",
                                    command=lambda: self._cambiar("ENTREGADO")),
            "cancelar": ttk.Button(botones, text="Cancelar pedido", style="Eliminar.TButton", command=self._cancelar),
            "eliminar": ttk.Button(botones, text="Eliminar", command=self._eliminar),
        }
        for i, boton in enumerate(self.botones.values()):
            boton.grid(row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        self._botones()

    def recargar(self):
        usuario = self.usuario_var.get().strip()
        if usuario and not usuario.isdigit():
            self.app.set_estado("El ID de usuario debe ser un número.", "error")
            return
        estado = None if self.estado_var.get() == "Todos" else self.estado_var.get()
        self._peticion += 1
        numero = self._peticion
        run_async(self, lambda: self.app.pedidos.list(estado=estado, user_id=int(usuario) if usuario else None,
                                                      per_page=100),
                  lambda datos: numero == self._peticion and self._pintar(datos),
                  lambda e: numero == self._peticion and self._error(e, "No se pudieron cargar los pedidos"))

    def _pintar(self, datos):
        seleccionado = self.pedido["id"] if self.pedido else None
        self.tabla.delete(*self.tabla.get_children())
        for p in datos.get("items", []):
            self.tabla.insert("", "end", iid=str(p["id"]), tags=(p["estado"],), values=(
                p["id"], p["user_id"], p["estado"].replace("_", " "), dinero(p["total"]), p.get("articulos", ""),
                _fecha(p["created_at"])))
        self.total_var.set(f"{datos.get('total', 0)} pedido(s)")
        if seleccionado is not None and self.tabla.exists(str(seleccionado)):
            self.tabla.selection_set(str(seleccionado))
        else:
            self.pedido = None
            _escribir(self.detalle, "Selecciona un pedido para ver su detalle y cambiar su estado.")
            self._botones()

    def _seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        pedido_id = int(seleccion[0])

        def ok(pedido):
            if self.tabla.selection() == (str(pedido_id),):
                self.pedido = pedido
                _escribir(self.detalle, texto_del_pedido(pedido))
                self._botones()

        run_async(self, lambda: self.app.pedidos.get(pedido_id), ok, self._error)

    def _botones(self):
        estado = self.pedido["estado"] if self.pedido else None
        habilitados = {"ENVIADO": estado == "PAGADO", "ENTREGADO": estado == "ENVIADO",
                       "cancelar": estado in ("PENDIENTE_PAGO", "PAGADO"), "eliminar": estado in ("CANCELADO", "EXPIRADO")}
        for clave, boton in self.botones.items():
            boton.state(["!disabled"] if habilitados[clave] else ["disabled"])

    def _hecho(self, pedido, mensaje):
        self.pedido = pedido
        self.app.set_estado(mensaje, "ok")
        self.recargar()

    def _cambiar(self, estado):
        pedido_id = self.pedido["id"]
        run_async(self, lambda: self.app.pedidos.set_state(pedido_id, estado),
                  lambda p: self._hecho(p, f"200 Pedido #{pedido_id} marcado como {estado}"), self._error)

    def _cancelar(self):
        pedido_id, estado = self.pedido["id"], self.pedido["estado"]
        if not messagebox.askyesno("Cancelar pedido", f"¿Cancelar el pedido #{pedido_id} (está {estado})?\n\n"
                                   "Sus unidades regresan al stock disponible. No se puede deshacer.",
                                   parent=self.app, icon="warning"):
            return
        run_async(self, lambda: self.app.pedidos.cancel(pedido_id),
                  lambda p: self._hecho(p, f"200 Pedido #{pedido_id} cancelado"), self._error)

    def _eliminar(self):
        pedido_id = self.pedido["id"]
        if not messagebox.askyesno("Eliminar pedido", f"¿Eliminar el pedido #{pedido_id} de las listas?",
                                   parent=self.app, icon="warning"):
            return
        run_async(self, lambda: self.app.pedidos.delete(pedido_id),
                  lambda _r: self._hecho(None, f"200 Pedido #{pedido_id} eliminado"), self._error)


# ====================================================================== INVENTARIO (admin)
class InventarioTab(_Base):
    """Stock de cada libro. Es libros.stock, en books: se edita con PATCH /books/<isbn>."""

    def __init__(self, parent, pantalla):
        super().__init__(parent, pantalla)
        self._filas = {}
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        marco, self.tabla = _tabla(self, [("isbn", "ISBN", 130, "w", False), ("titulo", "Título", 320, "w", True),
                                          ("precio", "Precio", 90, "e", False),
                                          ("stock", "Stock", 80, "center", False)])
        marco.grid(row=0, column=0, sticky="nsew")
        self.tabla.tag_configure("agotado", foreground=theme.COLOR_PELIGRO)
        self.tabla.bind("<<TreeviewSelect>>", lambda _e: self._seleccionado())

        barra = ttk.Frame(self)
        barra.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(barra, text="ISBN").pack(side="left")
        self.isbn_var = tk.StringVar()
        ttk.Entry(barra, textvariable=self.isbn_var, width=16, state="readonly").pack(side="left", padx=(6, 12))
        ttk.Label(barra, text="Stock").pack(side="left")
        self.stock_var = tk.StringVar()
        entrada = ttk.Entry(barra, textvariable=self.stock_var, width=8)
        entrada.pack(side="left", padx=(6, 12))
        entrada.bind("<Return>", lambda _e: self._guardar())
        ttk.Button(barra, text="Guardar stock", style="Crear.TButton", command=self._guardar).pack(side="left", padx=3)
        ttk.Button(barra, text="Actualizar", command=self.recargar).pack(side="right")
        ttk.Label(self, style="Info.TLabel", justify="left",
                  text="Selecciona un libro, escribe su stock y pulsa Guardar stock (PATCH /books/<isbn>). Crear un "
                       "pedido resta de este stock; cancelarlo o dejarlo expirar lo devuelve."
                  ).grid(row=2, column=0, sticky="w", pady=(6, 0))

    def recargar(self):
        def ok(catalogo):
            seleccion = self.tabla.selection()
            self.tabla.delete(*self.tabla.get_children())
            self._filas = {}
            for libro in catalogo:
                self._filas[libro["isbn"]] = libro
                self.tabla.insert("", "end", iid=libro["isbn"], tags=() if libro["disponible"] else ("agotado",),
                                  values=(libro["isbn"], libro["titulo"], dinero(libro["precio"]), libro["disponible"]))
            if seleccion and self.tabla.exists(seleccion[0]):
                self.tabla.selection_set(seleccion[0])

        run_async(self, self.pantalla.catalogo_con_stock, ok, lambda e: self._error(e, "No se pudo cargar el inventario"))

    def _seleccionado(self):
        seleccion = self.tabla.selection()
        if seleccion:
            libro = self._filas[seleccion[0]]
            self.isbn_var.set(libro["isbn"])
            self.stock_var.set(str(libro["disponible"]))

    def _guardar(self):
        isbn, stock = self.isbn_var.get().strip(), self.stock_var.get().strip()
        if not isbn or not stock.isdigit():
            self.app.set_estado("Selecciona un libro y escribe un stock entero (0 o mayor).", "error")
            return

        def ok(_libro):
            self.app.set_estado(f"200 Stock de {isbn} actualizado a {int(stock)}", "ok")
            self.recargar()

        run_async(self, lambda: self.app.books.patch_book(isbn, stock=int(stock)), ok, self._error)
