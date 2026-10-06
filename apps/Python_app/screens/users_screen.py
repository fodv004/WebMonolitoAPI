"""
screens/users_screen.py
Pantalla Usuarios (microservicio users). Tiene dos vistas segun el rol:

  * Admin  -> panel de administracion: filtros (busqueda, rol, estado),
    tabla paginada y, a la derecha, el detalle del usuario seleccionado con
    sus acciones (editar, cambiar rol, restablecer contraseña, cambiar
    correo, desactivar/reactivar). Las acciones destructivas piden confirmar.
  * Cliente -> "Mi perfil": editar su nombre, cambiar su contraseña (con la
    actual) y cambiar su correo.

Si el semaforo de users esta en rojo, la pantalla se cubre con un aviso y
no deja operar hasta que el servicio vuelva.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from api.http_base import ApiError
from utils import run_async
from widgets import theme
from widgets.dialogs import Campo, FormDialog

POR_PAGINA = 15
PASSWORD_MIN = 8

_COLUMNAS = [
    # (clave, encabezado, ancho, ancla)
    ("id_usuario", "ID", 50, "center"),
    ("nombre", "Nombre", 190, "w"),
    ("email", "Correo", 210, "w"),
    ("role", "Rol", 80, "center"),
    ("estado", "Estado", 80, "center"),
    ("verificado", "Correo verificado", 120, "center"),
]
_ESTADOS = {"Todos": None, "Activos": True, "Inactivos": False}
_CAMPOS_NOMBRE = [("nombre", "Nombre"), ("apellido_paterno", "Apellido paterno"),
                  ("apellido_materno", "Apellido materno")]


def nombre_completo(usuario):
    return " ".join(p for p in (usuario.get("nombre"), usuario.get("apellido_paterno"),
                                usuario.get("apellido_materno")) if p)


def _validar_password_nueva(valores):
    if len(valores["password_nueva"]) < PASSWORD_MIN:
        raise ValueError(f"La contraseña nueva debe tener al menos {PASSWORD_MIN} caracteres.")
    if valores["password_nueva"] != valores["confirmacion"]:
        raise ValueError("La contraseña nueva y su confirmación no coinciden.")


class UsersScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.admin = AdminView(self, app)
        self.perfil = PerfilView(self, app)
        for vista in (self.admin, self.perfil):
            vista.grid(row=0, column=0, sticky="nsew")

        self.aviso = self._construir_aviso()
        app.semaforos.al_cambiar(self._semaforo_cambio)

    # ------------------------------------------------------------ servicio caido
    def _construir_aviso(self):
        aviso = tk.Frame(self, background=theme.COLOR_FONDO)
        tarjeta = ttk.Frame(aviso, style="Card.TFrame", padding=(36, 28))
        tarjeta.place(relx=0.5, rely=0.5, anchor="center")
        ttk.Label(tarjeta, text="Servicio de usuarios no disponible", style="Titulo.TLabel",
                  foreground=theme.COLOR_PELIGRO).pack(anchor="w")
        ttk.Label(tarjeta, style="Card.TLabel", justify="left", wraplength=420,
                  text="El semáforo de Usuarios está en rojo: el microservicio no responde o no está "
                       "funcional, así que esta pantalla queda deshabilitada.\n\n"
                       "Se habilitará sola en cuanto el semáforo vuelva a verde.").pack(anchor="w", pady=(10, 16))
        ttk.Button(tarjeta, text="Revisar ahora", style="Primary.TButton",
                   command=self.app.semaforos.revisar_ahora).pack(anchor="w")
        return aviso

    def _semaforo_cambio(self, servicio, ok):
        if servicio != "users":
            return
        estaba_caido = bool(self.aviso.winfo_manager())
        self._aplicar_disponibilidad()
        if ok and estaba_caido and self.app.pantalla_actual == "users":
            self._vista_actual().recargar()          # volvio el servicio: datos frescos

    def _aplicar_disponibilidad(self):
        if self.app.semaforos.en_rojo("users"):
            self.aviso.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.aviso.lift()
        else:
            self.aviso.place_forget()

    # ------------------------------------------------------------ ciclo de vida
    def _vista_actual(self):
        return self.admin if self.app.sesion.es_admin else self.perfil

    def on_show(self):
        vista = self._vista_actual()
        vista.tkraise()
        self._aplicar_disponibilidad()
        if not self.app.semaforos.en_rojo("users"):
            vista.recargar()


class _Vista(ttk.Frame):
    """Lo comun a las dos vistas: manejo de errores y dialogos de contraseña y correo."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=(18, 14))
        self.app = app

    def _error(self, e, titulo="No se pudo completar la operación"):
        if isinstance(e, ApiError) and e.es_sesion_invalida:
            self.app.sesion_invalida(e)
            return
        mensaje = e.mensaje if isinstance(e, ApiError) else str(e)
        self.app.set_estado(f"{getattr(e, 'status', None) or '—'} {mensaje}", "error")
        messagebox.showerror(titulo, mensaje, parent=self.app)

    def _es_propia(self, usuario):
        return usuario["id_usuario"] == (self.app.sesion.usuario or {}).get("id_usuario")

    def _dialogo_password(self, usuario, al_terminar):
        """Propia: pide la actual. De otro usuario (solo admin): la restablece sin ella."""
        propia = self._es_propia(usuario)
        campos = [Campo("password_actual", "Contraseña actual", secreto=True)] if propia else []
        campos += [Campo("password_nueva", "Contraseña nueva", secreto=True),
                   Campo("confirmacion", "Repite la nueva", secreto=True)]

        def accion(valores):
            if propia and not valores["password_actual"]:
                raise ValueError("Escribe tu contraseña actual.")
            _validar_password_nueva(valores)
            return self.app.users.change_password(usuario["id_usuario"], valores["password_nueva"],
                                                  valores["password_actual"] if propia else None)

        FormDialog(
            self.app, "Cambiar mi contraseña" if propia else "Restablecer contraseña",
            ("Al guardarla se cerrarán todas tus sesiones y tendrás que iniciar sesión de nuevo." if propia else
             f"Nueva contraseña para {usuario['email']}. Se cerrarán todas sus sesiones abiertas."),
            campos, accion, al_terminar,
            texto_boton="Cambiar contraseña" if propia else "Restablecer", estilo_boton="Patch.TButton")

    def _dialogo_email(self, usuario, al_terminar):
        def accion(valores):
            email = valores["email"].strip()
            if not email or "@" not in email:
                raise ValueError("Escribe un correo válido.")
            return self.app.users.change_email(usuario["id_usuario"], email)

        FormDialog(
            self.app, "Cambiar correo",
            f"Correo actual: {usuario['email']}\n"
            "El nuevo queda SIN verificar: se envía un enlace de confirmación y la cuenta no podrá "
            "iniciar sesión hasta abrirlo.",
            [Campo("email", "Correo nuevo")], accion, al_terminar, texto_boton="Cambiar correo",
            estilo_boton="Patch.TButton")


# ====================================================================== ADMIN
class AdminView(_Vista):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.pagina = 1
        self.paginas = 0
        self.roles = []                # [{"role_id", "nombre"}], de GET /roles
        self._por_iid = {}
        self._seleccion_id = None
        self._peticion = 0             # numero de la ultima carga pedida (las respuestas viejas se descartan)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._construir_encabezado()
        self._construir_filtros()
        self._construir_tabla()
        self._construir_detalle()
        self._construir_paginacion()

    # ------------------------------------------------------------ UI
    def _construir_encabezado(self):
        barra = tk.Frame(self, background=theme.COLOR_PRINCIPAL, padx=16, pady=10)
        barra.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        tk.Label(barra, text="Administración de usuarios", font=theme.FUENTE_SUBTITULO,
                 background=theme.COLOR_PRINCIPAL, foreground=theme.COLOR_TEXTO_CLARO).pack(side="left")
        self.total_var = tk.StringVar()
        tk.Label(barra, textvariable=self.total_var, font=theme.FUENTE_NORMAL,
                 background=theme.COLOR_PRINCIPAL, foreground=theme.COLOR_SELECCION).pack(side="left", padx=14)
        ttk.Button(barra, text="+ Nuevo usuario", style="Crear.TButton", command=self._crear).pack(side="right")

    def _construir_filtros(self):
        barra = ttk.Frame(self)
        barra.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ttk.Label(barra, text="Buscar").pack(side="left")
        self.q_var = tk.StringVar()
        entrada = ttk.Entry(barra, textvariable=self.q_var, width=26)
        entrada.pack(side="left", padx=(6, 12))
        entrada.bind("<Return>", lambda _e: self._filtrar())

        ttk.Label(barra, text="Rol").pack(side="left")
        self.rol_var = tk.StringVar(value="Todos")
        self.combo_rol = ttk.Combobox(barra, textvariable=self.rol_var, values=["Todos"], state="readonly", width=10)
        self.combo_rol.pack(side="left", padx=(6, 12))
        self.combo_rol.bind("<<ComboboxSelected>>", lambda _e: self._filtrar())

        ttk.Label(barra, text="Estado").pack(side="left")
        self.estado_var = tk.StringVar(value="Todos")
        combo_estado = ttk.Combobox(barra, textvariable=self.estado_var, values=list(_ESTADOS), state="readonly",
                                    width=10)
        combo_estado.pack(side="left", padx=(6, 12))
        combo_estado.bind("<<ComboboxSelected>>", lambda _e: self._filtrar())

        ttk.Button(barra, text="Buscar", style="Primary.TButton", command=self._filtrar).pack(side="left", padx=3)
        ttk.Button(barra, text="Limpiar", command=self._limpiar).pack(side="left", padx=3)

    def _construir_tabla(self):
        marco = tk.Frame(self, background=theme.COLOR_SUPERFICIE, highlightthickness=1,
                         highlightbackground=theme.COLOR_BORDE)
        marco.grid(row=2, column=0, sticky="nsew")
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)

        self.tabla = ttk.Treeview(marco, columns=[c[0] for c in _COLUMNAS], show="headings", selectmode="browse")
        for clave, encabezado, ancho, ancla in _COLUMNAS:
            self.tabla.heading(clave, text=encabezado, anchor=ancla)
            self.tabla.column(clave, width=ancho, minwidth=40, anchor=ancla, stretch=clave in ("nombre", "email"))
        self.tabla.tag_configure("par", background=theme.COLOR_SUPERFICIE)
        self.tabla.tag_configure("impar", background=theme.COLOR_FILA_ALTERNA)
        self.tabla.tag_configure("inactivo", foreground=theme.COLOR_TEXTO_SUAVE)
        self.tabla.bind("<<TreeviewSelect>>", lambda _e: self._al_seleccionar())
        self.tabla.bind("<Double-1>", lambda _e: self._editar())

        scroll = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=scroll.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

    def _construir_detalle(self):
        panel = ttk.Frame(self, style="Card.TFrame", padding=(16, 14), width=250)
        panel.grid(row=2, column=1, sticky="ns", padx=(10, 0))
        panel.pack_propagate(False)

        ttk.Label(panel, text="Usuario seleccionado", style="Subtitulo.TLabel").pack(anchor="w")
        self.detalle_nombre = tk.StringVar(value="—")
        ttk.Label(panel, textvariable=self.detalle_nombre, style="Card.TLabel", font=theme.FUENTE_SUBTITULO,
                  wraplength=215, justify="left").pack(anchor="w", pady=(2, 0))
        self.detalle_datos = tk.StringVar(value="Selecciona un usuario de la tabla.")
        ttk.Label(panel, textvariable=self.detalle_datos, style="Card.TLabel", wraplength=215,
                  justify="left").pack(anchor="w", pady=(6, 12))

        self.botones = {}
        for clave, texto, estilo, comando in (
            ("editar", "Editar datos", "Editar.TButton", self._editar),
            ("rol", "Cambiar rol", "Editar.TButton", self._cambiar_rol),
            ("password", "Restablecer contraseña", "Patch.TButton", self._password),
            ("email", "Cambiar correo", "Patch.TButton", self._email),
            ("estado", "Desactivar", "Eliminar.TButton", self._alternar_estado),
        ):
            boton = ttk.Button(panel, text=texto, style=estilo, command=comando)
            boton.pack(fill="x", pady=3)
            self.botones[clave] = boton
        self._actualizar_detalle()

    def _construir_paginacion(self):
        barra = ttk.Frame(self)
        barra.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.boton_anterior = ttk.Button(barra, text="« Anterior", command=lambda: self._ir_a(self.pagina - 1))
        self.boton_anterior.pack(side="left")
        self.pagina_var = tk.StringVar()
        ttk.Label(barra, textvariable=self.pagina_var).pack(side="left", padx=12)
        self.boton_siguiente = ttk.Button(barra, text="Siguiente »", command=lambda: self._ir_a(self.pagina + 1))
        self.boton_siguiente.pack(side="left")
        ttk.Button(barra, text="Actualizar", command=self.recargar).pack(side="right")

    # ------------------------------------------------------------ datos
    def recargar(self):
        if not self.roles:
            run_async(self, self.app.users.roles, self._recibir_roles, lambda _e: None)
        self._cargar()

    def _recibir_roles(self, roles):
        self.roles = roles if isinstance(roles, list) else []
        self.combo_rol.configure(values=["Todos"] + [r["nombre"] for r in self.roles])

    def _role_id(self, nombre):
        return next((r["role_id"] for r in self.roles if r["nombre"] == nombre), None)

    def _filtrar(self):
        self.pagina = 1
        self._cargar()

    def _limpiar(self):
        self.q_var.set("")
        self.rol_var.set("Todos")
        self.estado_var.set("Todos")
        self._filtrar()

    def _ir_a(self, pagina):
        if 1 <= pagina <= max(self.paginas, 1):
            self.pagina = pagina
            self._cargar()

    def _cargar(self):
        self.pagina_var.set("Cargando...")
        filtros = dict(q=self.q_var.get().strip(), role_id=self._role_id(self.rol_var.get()),
                       activo=_ESTADOS[self.estado_var.get()], page=self.pagina, per_page=POR_PAGINA)
        # Dos cargas seguidas (p. ej. Limpiar y enseguida otro filtro) pueden responder en
        # desorden: solo se pinta la respuesta de la ultima peticion.
        self._peticion += 1
        numero = self._peticion
        run_async(self, lambda: self.app.users.list(**filtros),
                  lambda datos: numero == self._peticion and self._recibir_pagina(datos),
                  lambda e: numero == self._peticion and self._error_de_carga(e))

    def _error_de_carga(self, e):
        self.pagina_var.set("")
        self._renderizar([])
        self._error(e, "No se pudo cargar la lista de usuarios")

    def _recibir_pagina(self, datos):
        self.paginas = datos.get("pages", 0)
        if self.pagina > max(self.paginas, 1):          # la ultima pagina se quedo vacia
            self.pagina = max(self.paginas, 1)
            self._cargar()
            return
        total = datos.get("total", 0)
        self.total_var.set(f"{total} usuario(s)")
        self.pagina_var.set(f"Página {self.pagina} de {max(self.paginas, 1)}")
        self.boton_anterior.state(["!disabled"] if self.pagina > 1 else ["disabled"])
        self.boton_siguiente.state(["!disabled"] if self.pagina < self.paginas else ["disabled"])
        self._renderizar(datos.get("items", []))

    def _renderizar(self, usuarios):
        self.tabla.delete(*self.tabla.get_children())
        self._por_iid = {}
        a_seleccionar = None
        for i, usuario in enumerate(usuarios):
            etiquetas = ["par" if i % 2 == 0 else "impar"] + ([] if usuario["activo"] else ["inactivo"])
            iid = self.tabla.insert("", "end", tags=etiquetas, values=(
                usuario["id_usuario"], nombre_completo(usuario), usuario["email"], usuario["role"],
                "Activo" if usuario["activo"] else "Inactivo", "Sí" if usuario["email_verificado"] else "Pendiente"))
            self._por_iid[iid] = usuario
            if usuario["id_usuario"] == self._seleccion_id:
                a_seleccionar = iid
        if a_seleccionar:
            self.tabla.selection_set(a_seleccionar)      # conserva la seleccion tras recargar
        else:
            self._seleccion_id = None
        self._actualizar_detalle()

    # ------------------------------------------------------------ seleccion
    def _seleccionado(self):
        seleccion = self.tabla.selection()
        return self._por_iid.get(seleccion[0]) if seleccion else None

    def _al_seleccionar(self):
        usuario = self._seleccionado()
        self._seleccion_id = usuario["id_usuario"] if usuario else None
        self._actualizar_detalle()

    def _actualizar_detalle(self):
        usuario = self._seleccionado()
        for boton in self.botones.values():
            boton.state(["!disabled"] if usuario else ["disabled"])
        if usuario is None:
            self.detalle_nombre.set("—")
            self.detalle_datos.set("Selecciona un usuario de la tabla.")
            return
        self.detalle_nombre.set(nombre_completo(usuario))
        self.detalle_datos.set(
            f"{usuario['email']}\n"
            f"ID {usuario['id_usuario']} · rol {usuario['role']}\n"
            f"{'Activo' if usuario['activo'] else 'INACTIVO'} · correo "
            f"{'verificado' if usuario['email_verificado'] else 'sin verificar'}\n"
            f"Alta: {(usuario.get('created_at') or '—')[:10]}\n"
            f"Modificado: {(usuario.get('updated_at') or '—').replace('T', ' ')}")
        self.botones["estado"].configure(text="Desactivar" if usuario["activo"] else "Reactivar",
                                         style="Eliminar.TButton" if usuario["activo"] else "Crear.TButton")
        self.botones["password"].configure(
            text="Cambiar mi contraseña" if self._es_propia(usuario) else "Restablecer contraseña")

    def _hecho(self, mensaje):
        self.app.set_estado(mensaje, "ok")
        self._cargar()

    def _si_cambie_mi_cuenta(self, usuario, motivo):
        """Cambios que cierran la sesion del propio admin: se le regresa al login con una explicacion."""
        if self._es_propia(usuario):
            self.app.terminar_sesion(motivo)
            return True
        return False

    # ------------------------------------------------------------ acciones
    def _crear(self):
        nombres_de_rol = [r["nombre"] for r in self.roles] or ["cliente"]
        campos = [Campo(clave, etiqueta) for clave, etiqueta in _CAMPOS_NOMBRE]
        campos += [Campo("email", "Correo"), Campo("password", "Contraseña", secreto=True),
                   Campo("rol", "Rol", valor="cliente" if "cliente" in nombres_de_rol else nombres_de_rol[0],
                         opciones=nombres_de_rol)]

        def accion(valores):
            if not valores["nombre"].strip() or not valores["email"].strip():
                raise ValueError("Nombre y correo son obligatorios.")
            if len(valores["password"]) < PASSWORD_MIN:
                raise ValueError(f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres.")
            return self.app.users.create(
                nombre=valores["nombre"], apellido_paterno=valores["apellido_paterno"],
                apellido_materno=valores["apellido_materno"], email=valores["email"].strip(),
                password=valores["password"], role_id=self._role_id(valores["rol"]) or 2)

        FormDialog(self.app, "Nuevo usuario", "POST /users — la cuenta nace activa y con el correo verificado.",
                   campos, accion, lambda u: self._hecho(f"201 Usuario creado: {u['email']} (ID {u['id_usuario']})"),
                   texto_boton="Crear", estilo_boton="Crear.TButton")

    def _editar(self):
        usuario = self._seleccionado()
        if usuario is None:
            return
        campos = [Campo(clave, etiqueta, valor=usuario.get(clave) or "") for clave, etiqueta in _CAMPOS_NOMBRE]

        def accion(valores):
            if not valores["nombre"].strip():
                raise ValueError("El nombre es obligatorio.")
            return self.app.users.update(usuario["id_usuario"], **valores)

        FormDialog(self.app, "Editar usuario", f"PUT /users/{usuario['id_usuario']} — {usuario['email']}",
                   campos, accion, lambda u: self._hecho(f"200 Usuario {u['id_usuario']} actualizado"),
                   estilo_boton="Editar.TButton")

    def _cambiar_rol(self):
        usuario = self._seleccionado()
        if usuario is None or not self.roles:
            return

        def confirmar(valores, dialogo):
            if valores["rol"] == usuario["role"]:
                return "El usuario ya tiene ese rol."
            if not messagebox.askyesno(
                    "Confirmar cambio de rol",
                    f"¿Cambiar el rol de {usuario['email']} de «{usuario['role']}» a «{valores['rol']}»?\n\n"
                    "Se cerrarán todas sus sesiones abiertas.", parent=dialogo, icon="warning"):
                return ""
            return None

        def terminado(actualizado):
            if not self._si_cambie_mi_cuenta(usuario, "Cambiaste tu propio rol: inicia sesión de nuevo."):
                self._hecho(f"200 Rol de {actualizado['email']} cambiado a {actualizado['role']}")

        FormDialog(self.app, "Cambiar rol", f"PATCH /users/{usuario['id_usuario']}/role — {usuario['email']}",
                   [Campo("rol", "Rol", valor=usuario["role"], opciones=[r["nombre"] for r in self.roles])],
                   lambda valores: self.app.users.change_role(usuario["id_usuario"], self._role_id(valores["rol"])),
                   terminado, texto_boton="Cambiar rol", estilo_boton="Editar.TButton", antes=confirmar)

    def _password(self):
        usuario = self._seleccionado()
        if usuario is None:
            return

        def terminado(_respuesta):
            if not self._si_cambie_mi_cuenta(usuario, "Contraseña actualizada: inicia sesión con la nueva."):
                self._hecho(f"200 Contraseña de {usuario['email']} restablecida (sus sesiones se cerraron)")

        self._dialogo_password(usuario, terminado)

    def _email(self):
        usuario = self._seleccionado()
        if usuario is None:
            return

        def terminado(respuesta):
            nuevo = respuesta["user"]["email"]
            if not self._si_cambie_mi_cuenta(
                    usuario, f"Correo cambiado a {nuevo}. Abre el enlace de confirmación que se envió y vuelve a "
                             "iniciar sesión."):
                self._hecho(f"200 Correo cambiado a {nuevo} (pendiente de verificar)")

        self._dialogo_email(usuario, terminado)

    def _alternar_estado(self):
        usuario = self._seleccionado()
        if usuario is None:
            return
        if usuario["activo"]:
            if not messagebox.askyesno(
                    "Desactivar usuario",
                    f"¿Desactivar a {nombre_completo(usuario)} ({usuario['email']})?\n\n"
                    "No podrá iniciar sesión y se cerrarán sus sesiones abiertas. "
                    "Es una baja lógica: puedes reactivarlo después.", parent=self.app, icon="warning"):
                return
            accion = lambda: self.app.users.deactivate(usuario["id_usuario"])          # noqa: E731
            mensaje = f"200 Usuario {usuario['email']} desactivado"
        else:
            if not messagebox.askyesno("Reactivar usuario", f"¿Reactivar a {usuario['email']}?", parent=self.app):
                return
            accion = lambda: self.app.users.patch(usuario["id_usuario"], activo=True)  # noqa: E731
            mensaje = f"200 Usuario {usuario['email']} reactivado"
        run_async(self, accion, lambda _u: self._hecho(mensaje), self._error)


# ====================================================================== CLIENTE
class PerfilView(_Vista):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.usuario = None

        tarjeta = theme.tarjeta_centrada(self, "Mi perfil", "Tus datos en la librería")
        self.vars = {}
        for fila, (clave, etiqueta) in enumerate(_CAMPOS_NOMBRE, start=3):
            self.vars[clave] = tk.StringVar()
            theme.campo(tarjeta, fila, etiqueta, self.vars[clave])

        self.datos_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.datos_var, style="Card.TLabel", justify="left", wraplength=380).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.estado_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.estado_var, style="Error.TLabel", wraplength=380, justify="left").grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.boton_guardar = ttk.Button(tarjeta, text="Guardar mi nombre", style="Primary.TButton",
                                        command=self._guardar)
        self.boton_guardar.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 6))
        secundarios = ttk.Frame(tarjeta, style="CardInner.TFrame")
        secundarios.grid(row=9, column=0, columnspan=2, sticky="ew")
        secundarios.grid_columnconfigure((0, 1), weight=1, uniform="perfil")
        self.boton_password = ttk.Button(secundarios, text="Cambiar contraseña", style="Patch.TButton",
                                         command=self._password)
        self.boton_password.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.boton_email = ttk.Button(secundarios, text="Cambiar correo", style="Patch.TButton", command=self._email)
        self.boton_email.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self._habilitar(False)

    def _habilitar(self, habilitado):
        for boton in (self.boton_guardar, self.boton_password, self.boton_email):
            boton.state(["!disabled"] if habilitado else ["disabled"])

    def recargar(self):
        self.estado_var.set("")
        run_async(self, self.app.users.me, self._recibir, self._error_de_carga)

    def _error_de_carga(self, e):
        self._habilitar(False)
        self._error(e, "No se pudo cargar tu perfil")

    def _recibir(self, usuario):
        self.usuario = usuario
        for clave, var in self.vars.items():
            var.set(usuario.get(clave) or "")
        self.datos_var.set(
            f"Correo: {usuario['email']} ({'verificado' if usuario['email_verificado'] else 'sin verificar'})\n"
            f"Rol: {usuario['role']}   ·   Cuenta creada: {(usuario.get('created_at') or '—')[:10]}")
        self._habilitar(True)

    def _guardar(self):
        valores = {clave: var.get() for clave, var in self.vars.items()}
        if not valores["nombre"].strip():
            self.estado_var.set("El nombre es obligatorio.")
            return
        self.estado_var.set("")
        self.boton_guardar.state(["disabled"])

        def ok(usuario):
            self._recibir(usuario)
            self.app.actualizar_usuario(usuario)
            self.app.set_estado("200 Perfil actualizado", "ok")

        def error(e):
            self.boton_guardar.state(["!disabled"])
            if isinstance(e, ApiError) and not e.es_sesion_invalida:
                self.estado_var.set(e.mensaje)
                self.app.set_estado(f"{e.status or '—'} {e.mensaje}", "error")
            else:
                self._error(e)

        run_async(self, lambda: self.app.users.update(self.usuario["id_usuario"], **valores), ok, error)

    def _password(self):
        self._dialogo_password(self.usuario, lambda _r: self.app.terminar_sesion(
            "Contraseña actualizada: inicia sesión con la nueva."))

    def _email(self):
        self._dialogo_email(self.usuario, lambda r: self.app.terminar_sesion(
            f"Correo cambiado a {r['user']['email']}. Abre el enlace de confirmación que se envió y vuelve a "
            "iniciar sesión."))
