"""
screens/pagos_screen.py
Pantalla Pagos (microservicio pagos), tipo caja o checkout. El pago es
SIMULADO: no hay pasarela real.

  Izquierda (caja): pedido pendiente a pagar, monto en grande (solo
    lectura: lo fija el servidor), metodo de pago, datos de tarjeta
    enmascarados (solo con TARJETA_SIMULADA), boton Pagar y comprobante.
  Derecha: historial de pagos con filtros. El admin ademas puede
    reembolsar, corregir referencia y notas, y eliminar pagos rechazados.

Idempotencia: cada intento de pago lleva un Idempotency-Key (uuid4). Si se
reintenta EL MISMO pago (mismo pedido, metodo y tarjeta) -por un doble
clic o porque la respuesta no llego- se reutiliza la misma llave y el
servidor devuelve el mismo pago sin cobrar otra vez.

El numero de tarjeta y el CVV solo existen en los campos del formulario
mientras se escribe; se borran al recibir la respuesta y no se guardan.

Si el semaforo de pagos esta en rojo la pantalla se cubre con un aviso.
"""
import hashlib
import tkinter as tk
import uuid
from tkinter import messagebox, ttk

from api.http_base import ApiError
from api.pagos_client import ESTADOS, METODOS
from screens.pedidos_screen import _detalle, _escribir, _fecha, _tabla, dinero
from utils import run_async
from widgets import theme
from widgets.dialogs import Campo, FormDialog

NOMBRES_METODO = {"TARJETA_SIMULADA": "Tarjeta (simulada)", "TRANSFERENCIA": "Transferencia", "EFECTIVO": "Efectivo"}
# estado del pago -> (color del texto, fondo): verde, rojo y gris
COLORES_PAGO = {
    "APROBADO": ("#166534", "#bbf7d0"),
    "RECHAZADO": ("#991b1b", "#fecaca"),
    "REEMBOLSADO": ("#374151", "#e5e7eb"),
}
SIN_PEDIDOS = "No tienes pedidos pendientes de pago"


def solo_digitos(texto):
    return texto.replace(" ", "").replace("-", "")


def firma_del_intento(pedido_id, metodo, tarjeta, cvv):
    """Huella del intento de pago: mismos datos -> misma huella -> misma Idempotency-Key.
    Es un hash: la app no conserva el numero de tarjeta para poder comparar."""
    crudo = f"{pedido_id}|{metodo}|{solo_digitos(tarjeta)}|{cvv.strip()}"
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def texto_del_comprobante(pago):
    lineas = [
        "COMPROBANTE DE PAGO (simulado)",
        "",
        f"  Estado:      {pago['estado']}",
        f"  Referencia:  {pago['referencia']}",
        f"  Pedido:      #{pago['pedido_id']}",
        f"  Monto:       {dinero(pago['monto'])}",
        f"  Método:      {NOMBRES_METODO.get(pago['metodo'], pago['metodo'])}",
    ]
    if pago.get("ultimos4"):
        lineas.append(f"  Tarjeta:     •••• •••• •••• {pago['ultimos4']}")
    lineas.append(f"  Fecha:       {_fecha(pago.get('created_at'))}")
    if pago.get("notas"):
        lineas.append(f"  Notas:       {pago['notas']}")
    if pago["estado"] == "RECHAZADO":
        lineas += ["", "El pago fue rechazado: el pedido sigue pendiente. Intenta con otro método o tarjeta."]
    elif pago["estado"] == "APROBADO" and not pago.get("sincronizado", True):
        lineas += ["", "Pago aprobado. El pedido se marcará como PAGADO en cuanto el servicio de pedidos responda."]
    if pago.get("repetido"):
        lineas += ["", "(Reenvío del mismo pago: no se cobró otra vez.)"]
    return "\n".join(lineas)


class PagosScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=(14, 12))
        self.app = app
        self.pendientes = []           # pedidos PENDIENTE_PAGO del usuario
        self._preseleccion = None      # pedido con el que se abrio la pantalla desde "Ir a pagar"
        self._intento = None           # (huella, Idempotency-Key) del ultimo intento de pago
        self._pagos = {}               # iid de la tabla -> pago
        self._peticion = 0             # ultima carga del historial pedida (las viejas se descartan)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._construir_caja()
        self._construir_historial()
        self.aviso = self._construir_aviso()
        app.semaforos.al_cambiar(self._semaforo_cambio)

    # ------------------------------------------------------------ caja
    def _construir_caja(self):
        caja = ttk.Frame(self, style="Card.TFrame", padding=(18, 14), width=370)
        caja.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        caja.pack_propagate(False)

        ttk.Label(caja, text="Caja", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(caja, text="Pedido a pagar", style="Subtitulo.TLabel").pack(anchor="w", pady=(8, 2))
        fila = ttk.Frame(caja, style="CardInner.TFrame")
        fila.pack(fill="x")
        fila.grid_columnconfigure(0, weight=1)
        self.pedido_var = tk.StringVar()
        self.combo = ttk.Combobox(fila, textvariable=self.pedido_var, state="readonly")
        self.combo.grid(row=0, column=0, sticky="ew")
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self._pedido_elegido())
        ttk.Button(fila, text="Actualizar", command=self._cargar_pendientes).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(caja, text="Total a pagar", style="Subtitulo.TLabel").pack(anchor="w", pady=(12, 0))
        self.monto_var = tk.StringVar(value="$0.00")
        ttk.Label(caja, textvariable=self.monto_var, style="Card.TLabel", font=(theme.FAMILIA, 30, "bold"),
                  foreground=theme.COLOR_PRINCIPAL).pack(anchor="w")
        self.info_var = tk.StringVar()
        ttk.Label(caja, textvariable=self.info_var, style="Subtitulo.TLabel", wraplength=330,
                  justify="left").pack(anchor="w")

        ttk.Label(caja, text="Método de pago", style="Subtitulo.TLabel").pack(anchor="w", pady=(12, 2))
        self.metodo_var = tk.StringVar(value=METODOS[0])
        for metodo in METODOS:
            ttk.Radiobutton(caja, text=NOMBRES_METODO[metodo], value=metodo, variable=self.metodo_var,
                            style="Card.TRadiobutton", command=self._metodo_elegido).pack(anchor="w")

        # Datos de tarjeta: solo visibles con TARJETA_SIMULADA; se escriben enmascarados.
        self.marco_tarjeta = ttk.Frame(caja, style="CardInner.TFrame")
        self.marco_tarjeta.grid_columnconfigure(1, weight=1)
        ttk.Label(self.marco_tarjeta, text="Número", style="Card.TLabel").grid(row=0, column=0, sticky="e", padx=(0, 8),
                                                                              pady=3)
        self.tarjeta_var = tk.StringVar()
        ttk.Entry(self.marco_tarjeta, textvariable=self.tarjeta_var, show="•").grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(self.marco_tarjeta, text="CVV", style="Card.TLabel").grid(row=1, column=0, sticky="e", padx=(0, 8),
                                                                           pady=3)
        self.cvv_var = tk.StringVar()
        ttk.Entry(self.marco_tarjeta, textvariable=self.cvv_var, show="•", width=6).grid(row=1, column=1, sticky="w",
                                                                                          pady=3)
        ttk.Label(self.marco_tarjeta, style="Subtitulo.TLabel", wraplength=330, justify="left",
                  text="Pago simulado: no uses una tarjeta real. Una tarjeta terminada en 0000 se rechaza.").grid(
            row=2, column=0, columnspan=2, sticky="w")

        self.boton_pagar = ttk.Button(caja, text="Pagar", style="Crear.TButton", command=self._pagar)
        self.estado_var = tk.StringVar()
        self.etiqueta_estado = ttk.Label(caja, textvariable=self.estado_var, style="Error.TLabel", wraplength=330,
                                         justify="left")
        self.comprobante = _detalle(caja, 10)
        # El orden de empaquetado final lo decide _acomodar (el marco de tarjeta aparece y desaparece).
        self._acomodar()
        _escribir(self.comprobante, "Aquí aparecerá el comprobante del pago.")

    def _acomodar(self):
        """Coloca (o quita) el marco de tarjeta y, debajo, el boton, el mensaje y el comprobante."""
        for widget in (self.marco_tarjeta, self.boton_pagar, self.etiqueta_estado, self.comprobante):
            widget.pack_forget()
        if self.metodo_var.get() == "TARJETA_SIMULADA":
            self.marco_tarjeta.pack(fill="x", pady=(6, 0))
        self.boton_pagar.pack(fill="x", pady=(12, 4))
        self.etiqueta_estado.pack(anchor="w")
        self.comprobante.pack(fill="both", expand=True, pady=(6, 0))

    # ------------------------------------------------------------ historial
    def _construir_historial(self):
        lado = ttk.Frame(self)
        lado.grid(row=0, column=1, sticky="nsew")
        lado.grid_rowconfigure(2, weight=1)
        lado.grid_columnconfigure(0, weight=1)
        ttk.Label(lado, text="Historial de pagos", font=theme.FUENTE_SUBTITULO).grid(row=0, column=0, sticky="w")

        barra = ttk.Frame(lado)
        barra.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        ttk.Label(barra, text="Estado").pack(side="left")
        self.filtro_estado = tk.StringVar(value="Todos")
        combo = ttk.Combobox(barra, textvariable=self.filtro_estado, values=("Todos",) + ESTADOS, state="readonly",
                             width=13)
        combo.pack(side="left", padx=(6, 10))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._cargar_historial())
        ttk.Label(barra, text="Método").pack(side="left")
        self.filtro_metodo = tk.StringVar(value="Todos")
        combo = ttk.Combobox(barra, textvariable=self.filtro_metodo, values=("Todos",) + METODOS, state="readonly",
                             width=18)
        combo.pack(side="left", padx=(6, 10))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._cargar_historial())
        # Solo admin: filtrar por usuario.
        self.filtro_admin = ttk.Frame(barra)
        ttk.Label(self.filtro_admin, text="ID usuario").pack(side="left")
        self.filtro_usuario = tk.StringVar()
        entrada = ttk.Entry(self.filtro_admin, textvariable=self.filtro_usuario, width=7)
        entrada.pack(side="left", padx=(6, 10))
        entrada.bind("<Return>", lambda _e: self._cargar_historial())
        ttk.Button(barra, text="Filtrar", style="Primary.TButton", command=self._cargar_historial).pack(side="right")

        marco, self.tabla = _tabla(lado, [
            ("id", "#", 36, "center", False), ("pedido", "Pedido", 52, "center", False),
            ("monto", "Monto", 80, "e", False), ("metodo", "Método", 110, "w", False),
            ("estado", "Estado", 100, "w", False), ("referencia", "Referencia", 150, "w", True),
            ("tarjeta", "Tarjeta", 60, "center", False), ("fecha", "Fecha", 110, "w", False)])
        marco.grid(row=2, column=0, sticky="nsew")
        for estado, (texto, fondo) in COLORES_PAGO.items():
            self.tabla.tag_configure(estado, foreground=texto, background=fondo)
        self.tabla.bind("<<TreeviewSelect>>", lambda _e: self._pago_seleccionado())

        pie = ttk.Frame(lado)
        pie.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        self.total_var = tk.StringVar()
        ttk.Label(pie, textvariable=self.total_var, style="Info.TLabel").pack(side="left")
        # Solo admin: acciones sobre el pago seleccionado.
        self.acciones_admin = ttk.Frame(pie)
        self.botones = {
            "eliminar": ttk.Button(self.acciones_admin, text="Eliminar rechazado", command=self._eliminar),
            "corregir": ttk.Button(self.acciones_admin, text="Corregir referencia / notas", style="Editar.TButton",
                                   command=self._corregir),
            "reembolsar": ttk.Button(self.acciones_admin, text="Reembolsar", style="Eliminar.TButton",
                                     command=self._reembolsar),
        }
        for boton in self.botones.values():
            boton.pack(side="right", padx=(6, 0))
        self._botones_admin()

    # ------------------------------------------------------------ servicio caido
    def _construir_aviso(self):
        aviso = tk.Frame(self, background=theme.COLOR_FONDO)
        tarjeta = ttk.Frame(aviso, style="Card.TFrame", padding=(36, 28))
        tarjeta.place(relx=0.5, rely=0.5, anchor="center")
        ttk.Label(tarjeta, text="Servicio de pagos no disponible", style="Titulo.TLabel",
                  foreground=theme.COLOR_PELIGRO).pack(anchor="w")
        ttk.Label(tarjeta, style="Card.TLabel", justify="left", wraplength=420,
                  text="El semáforo de Pagos está en rojo: el microservicio no responde o no está funcional, así "
                       "que no se puede cobrar ni consultar pagos.\n\n"
                       "La pantalla se habilitará sola en cuanto el semáforo vuelva a verde.").pack(anchor="w",
                                                                                                  pady=(10, 16))
        ttk.Button(tarjeta, text="Revisar ahora", style="Primary.TButton",
                   command=self.app.semaforos.revisar_ahora).pack(anchor="w")
        return aviso

    def _semaforo_cambio(self, servicio, ok):
        if servicio != "pagos":
            return
        estaba_caido = bool(self.aviso.winfo_manager())
        self._aplicar_disponibilidad()
        if ok and estaba_caido and self.app.pantalla_actual == "pagos":
            self._recargar()                         # volvio el servicio: datos frescos

    def _aplicar_disponibilidad(self):
        if self.app.semaforos.en_rojo("pagos"):
            self.aviso.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.aviso.lift()
        else:
            self.aviso.place_forget()

    # ------------------------------------------------------------ ciclo de vida
    def preseleccionar(self, pedido_id):
        """Lo llama "Ir a pagar" de la pantalla Pedidos antes de mostrar esta pantalla."""
        self._preseleccion = pedido_id

    def on_show(self):
        # Otro usuario pudo iniciar sesion: nada del anterior debe quedar en pantalla.
        self._intento = None
        self._limpiar_tarjeta()
        self.estado_var.set("")
        _escribir(self.comprobante, "Aquí aparecerá el comprobante del pago.")
        if self.app.sesion.es_admin:
            self.filtro_admin.pack(side="left")
            self.acciones_admin.pack(side="right")
        else:
            self.filtro_admin.pack_forget()
            self.acciones_admin.pack_forget()
            self.filtro_usuario.set("")
        self._aplicar_disponibilidad()
        if not self.app.semaforos.en_rojo("pagos"):
            self._recargar()

    def _recargar(self):
        self._cargar_pendientes()
        self._cargar_historial()

    def _error(self, e, titulo="No se pudo completar la operación"):
        if isinstance(e, ApiError) and e.es_sesion_invalida:
            self.app.sesion_invalida(e)
            return
        mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
        self.app.set_estado(f"{getattr(e, 'status', None) or '—'} {mensaje}", "error")
        messagebox.showerror(titulo, mensaje, parent=self.app)

    # ------------------------------------------------------------ pedido y metodo
    def _cargar_pendientes(self):
        user_id = (self.app.sesion.usuario or {}).get("id_usuario")
        run_async(self, lambda: self.app.pedidos.list(estado="PENDIENTE_PAGO", user_id=user_id, per_page=50),
                  self._recibir_pendientes, lambda e: self._error(e, "No se pudieron cargar tus pedidos pendientes"))

    def _recibir_pendientes(self, datos):
        self.pendientes = datos.get("items", [])
        self.combo.configure(values=[f"#{p['id']} — {p.get('articulos', '?')} artículo(s) — {dinero(p['total'])}"
                                     for p in self.pendientes])
        elegido = 0
        if self._preseleccion is not None:
            elegido = next((i for i, p in enumerate(self.pendientes) if p["id"] == self._preseleccion), None)
            if elegido is None:
                self.app.set_estado(f"El pedido #{self._preseleccion} ya no está pendiente de pago.", "info")
                elegido = 0
            self._preseleccion = None
        if self.pendientes:
            self.combo.current(elegido)
        else:
            self.pedido_var.set(SIN_PEDIDOS)
        self._pedido_elegido()

    def _pedido(self):
        """Pedido elegido en el selector, o None."""
        indice = self.combo.current()
        return self.pendientes[indice] if 0 <= indice < len(self.pendientes) else None

    def _pedido_elegido(self):
        pedido = self._pedido()
        if pedido is None:
            self.monto_var.set("$0.00")
            self.info_var.set("Crea un pedido en la pantalla Pedidos para poder pagarlo.")
            self.boton_pagar.state(["disabled"])
            return
        self.monto_var.set(dinero(pedido["total"]))             # solo lectura: lo fija el servidor
        self.info_var.set(f"Pedido #{pedido['id']} · la reserva de stock vence {_fecha(pedido.get('expira_en'))}")
        self.boton_pagar.state(["!disabled"])
        self.estado_var.set("")

    def _metodo_elegido(self):
        if self.metodo_var.get() != "TARJETA_SIMULADA":
            self._limpiar_tarjeta()
        self._acomodar()

    def _limpiar_tarjeta(self):
        self.tarjeta_var.set("")
        self.cvv_var.set("")

    # ------------------------------------------------------------ pagar
    def _pagar(self):
        pedido = self._pedido()
        if pedido is None:
            return
        metodo = self.metodo_var.get()
        tarjeta, cvv = self.tarjeta_var.get(), self.cvv_var.get()
        if metodo == "TARJETA_SIMULADA":
            numero = solo_digitos(tarjeta)
            if not numero.isdigit() or not 13 <= len(numero) <= 19:
                self.estado_var.set("Escribe el número de tarjeta: de 13 a 19 dígitos.")
                return
            if not cvv.strip().isdigit() or len(cvv.strip()) not in (3, 4):
                self.estado_var.set("Escribe el CVV: 3 o 4 dígitos.")
                return
        else:
            tarjeta, cvv = "", ""

        # Mismo pago que el intento anterior -> misma llave (el servidor no cobra dos veces).
        huella = firma_del_intento(pedido["id"], metodo, tarjeta, cvv)
        if self._intento is None or self._intento[0] != huella:
            self._intento = (huella, str(uuid.uuid4()))
        llave = self._intento[1]

        self.boton_pagar.state(["disabled"])
        self.estado_var.set("Procesando el pago...")

        def ok(pago):
            self._limpiar_tarjeta()                             # los datos de tarjeta no se conservan
            self.estado_var.set("")
            _escribir(self.comprobante, texto_del_comprobante(pago))
            if pago["estado"] == "APROBADO":
                self.app.set_estado(f"{200 if pago.get('repetido') else 201} Pago aprobado: pedido "
                                    f"#{pago['pedido_id']}, referencia {pago['referencia']}", "ok")
            else:
                self.app.set_estado(f"Pago {pago['estado']} (referencia {pago['referencia']})", "error")
            self._recargar()                                    # el pedido pagado sale del selector

        def error(e):
            self.boton_pagar.state(["!disabled"])
            if isinstance(e, ApiError) and e.es_sesion_invalida:
                self.app.sesion_invalida(e)
                return
            mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
            # La llave se conserva: si vuelves a pulsar Pagar con los mismos datos es el MISMO intento.
            self.estado_var.set(f"{mensaje}\nPuedes reintentar: no se cobrará dos veces.")
            self.app.set_estado(f"{getattr(e, 'status', None) or '—'} {mensaje}", "error")

        run_async(self, lambda: self.app.pagos.pay(pedido["id"], metodo, llave,
                                                   tarjeta=solo_digitos(tarjeta) or None, cvv=cvv.strip() or None),
                  ok, error)

    # ------------------------------------------------------------ historial
    def _cargar_historial(self):
        usuario = self.filtro_usuario.get().strip()
        if usuario and not usuario.isdigit():
            self.app.set_estado("El ID de usuario debe ser un número.", "error")
            return
        estado = None if self.filtro_estado.get() == "Todos" else self.filtro_estado.get()
        metodo = None if self.filtro_metodo.get() == "Todos" else self.filtro_metodo.get()
        self._peticion += 1
        numero = self._peticion
        run_async(self, lambda: self.app.pagos.list(estado=estado, metodo=metodo,
                                                    user_id=int(usuario) if usuario else None),
                  lambda datos: numero == self._peticion and self._pintar_historial(datos),
                  lambda e: numero == self._peticion and self._error(e, "No se pudo cargar el historial de pagos"))

    def _pintar_historial(self, datos):
        seleccion = self.tabla.selection()
        self.tabla.delete(*self.tabla.get_children())
        self._pagos = {}
        for pago in datos.get("items", []):
            iid = str(pago["id"])
            self._pagos[iid] = pago
            self.tabla.insert("", "end", iid=iid, tags=(pago["estado"],), values=(
                pago["id"], f"#{pago['pedido_id']}", dinero(pago["monto"]),
                NOMBRES_METODO.get(pago["metodo"], pago["metodo"]), pago["estado"], pago["referencia"],
                f"•••• {pago['ultimos4']}" if pago.get("ultimos4") else "—", _fecha(pago.get("created_at"))))
        self.total_var.set(f"{datos.get('total', 0)} pago(s)")
        if seleccion and self.tabla.exists(seleccion[0]):
            self.tabla.selection_set(seleccion[0])
        self._botones_admin()

    def _seleccionado(self):
        seleccion = self.tabla.selection()
        return self._pagos.get(seleccion[0]) if seleccion else None

    def _pago_seleccionado(self):
        pago = self._seleccionado()
        if pago is not None:
            _escribir(self.comprobante, texto_del_comprobante(pago))
        self._botones_admin()

    def _botones_admin(self):
        pago = self._seleccionado()
        estado = pago["estado"] if pago else None
        habilitados = {"reembolsar": estado == "APROBADO", "corregir": pago is not None,
                       "eliminar": estado == "RECHAZADO"}
        for clave, boton in self.botones.items():
            boton.state(["!disabled"] if habilitados[clave] else ["disabled"])

    def _hecho(self, mensaje):
        self.app.set_estado(mensaje, "ok")
        self._recargar()

    # ------------------------------------------------------------ admin
    def _reembolsar(self):
        pago = self._seleccionado()
        if pago is None:
            return
        if not messagebox.askyesno(
                "Reembolsar pago",
                f"¿Reembolsar el pago #{pago['id']} ({dinero(pago['monto'])}, referencia {pago['referencia']})?\n\n"
                f"El pedido #{pago['pedido_id']} pasará a CANCELADO y su stock se liberará. No se puede deshacer.",
                parent=self.app, icon="warning"):
            return

        def ok(actualizado):
            _escribir(self.comprobante, texto_del_comprobante(actualizado))
            self._hecho(f"200 Pago #{pago['id']} reembolsado: pedido #{pago['pedido_id']} cancelado")

        run_async(self, lambda: self.app.pagos.refund(pago["id"]), ok, self._error)

    def _corregir(self):
        pago = self._seleccionado()
        if pago is None:
            return

        def accion(valores):
            if not valores["referencia"].strip():
                raise ValueError("La referencia no puede quedar vacía.")
            return self.app.pagos.update(pago["id"], referencia=valores["referencia"].strip(),
                                         notas=valores["notas"].strip())

        FormDialog(self.app, "Corregir pago",
                   f"PATCH /pagos/{pago['id']} — solo referencia y notas. El monto ({dinero(pago['monto'])}) "
                   "no se puede modificar.",
                   [Campo("referencia", "Referencia", valor=pago["referencia"]),
                    Campo("notas", "Notas", valor=pago.get("notas") or "")],
                   accion, lambda p: self._hecho(f"200 Pago #{p['id']} corregido"), estilo_boton="Editar.TButton")

    def _eliminar(self):
        pago = self._seleccionado()
        if pago is None:
            return
        if not messagebox.askyesno("Eliminar pago rechazado",
                                   f"¿Eliminar del historial el pago rechazado #{pago['id']}?",
                                   parent=self.app, icon="warning"):
            return
        run_async(self, lambda: self.app.pagos.delete(pago["id"]),
                  lambda _r: self._hecho(f"200 Pago #{pago['id']} eliminado"), self._error)
