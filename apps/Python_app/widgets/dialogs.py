"""
widgets/dialogs.py
Ventana emergente (modal) con un formulario generico: campos de texto,
contraseñas y listas desplegables. La accion (una llamada de red) corre en
un hilo; si falla, el error se muestra dentro del dialogo sin cerrarlo.
"""
import tkinter as tk
from tkinter import ttk

from api.http_base import ApiError
from utils import run_async
from widgets import theme


class Campo:
    def __init__(self, clave, etiqueta, valor="", secreto=False, opciones=None):
        self.clave = clave
        self.etiqueta = etiqueta
        self.valor = valor
        self.secreto = secreto          # se muestra con puntos
        self.opciones = opciones        # lista de textos -> Combobox de solo lectura


class FormDialog(tk.Toplevel):
    def __init__(self, app, titulo, subtitulo, campos, accion, al_terminar, texto_boton="Guardar",
                 estilo_boton="Primary.TButton", antes=None):
        """`accion(valores)` se ejecuta en un hilo y devuelve el resultado; `al_terminar(resultado)`
        se llama en el hilo de Tk cuando termina bien. `accion` puede lanzar ValueError (validacion
        local) o ApiError.

        `antes(valores, dialogo)` (opcional) corre en el hilo de Tk antes de lanzar la accion, para
        validar o pedir confirmacion: devuelve None para continuar o un texto (puede ser vacio)
        para no enviar y mostrarlo en el dialogo."""
        super().__init__(app)
        self.app = app
        self.accion = accion
        self.al_terminar = al_terminar
        self.antes = antes

        self.title(titulo)
        self.configure(background=theme.COLOR_FONDO, padx=16, pady=16)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()

        tarjeta = ttk.Frame(self, style="Card.TFrame", padding=(28, 22))
        tarjeta.pack(fill="both", expand=True)
        tarjeta.grid_columnconfigure(1, weight=1)
        ttk.Label(tarjeta, text=titulo, style="Titulo.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(tarjeta, text=subtitulo, style="Subtitulo.TLabel", wraplength=400, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 12))

        self.vars = {}
        primera = None
        for fila, campo in enumerate(campos, start=2):
            var = tk.StringVar(value=campo.valor)
            self.vars[campo.clave] = var
            if campo.opciones:
                ttk.Label(tarjeta, text=campo.etiqueta, style="Card.TLabel").grid(
                    row=fila, column=0, sticky="e", padx=(0, 12), pady=6)
                entrada = ttk.Combobox(tarjeta, textvariable=var, values=campo.opciones, state="readonly",
                                       width=theme.ANCHO_CAMPO - 2)
                entrada.grid(row=fila, column=1, sticky="ew", pady=6)
            else:
                entrada = theme.campo(tarjeta, fila, campo.etiqueta, var, show="•" if campo.secreto else "")
                entrada.bind("<Return>", lambda _e: self._enviar())
            primera = primera or entrada

        fila = 2 + len(campos)
        self.estado_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.estado_var, style="Error.TLabel", wraplength=400, justify="left").grid(
            row=fila, column=0, columnspan=2, sticky="w", pady=(8, 0))

        botones = ttk.Frame(tarjeta, style="CardInner.TFrame")
        botones.grid(row=fila + 1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        botones.grid_columnconfigure((0, 1), weight=1, uniform="dlg")
        self.boton = ttk.Button(botones, text=texto_boton, style=estilo_boton, command=self._enviar)
        self.boton.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(botones, text="Cancelar", command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        if primera is not None:
            primera.focus_set()

    def _enviar(self):
        valores = {clave: var.get() for clave, var in self.vars.items()}
        if self.antes is not None:
            motivo = self.antes(valores, self)
            if motivo is not None:
                self.estado_var.set(motivo)
                return
        self.boton.state(["disabled"])
        self.estado_var.set("Guardando...")

        def ok(resultado):
            self.destroy()
            self.al_terminar(resultado)

        def error(e):
            if isinstance(e, ApiError) and e.es_sesion_invalida:
                self.destroy()
                self.app.sesion_invalida(e)
                return
            self.boton.state(["!disabled"])
            self.estado_var.set(e.mensaje if isinstance(e, ApiError) else str(e))

        run_async(self, lambda: self.accion(valores), ok, error)
