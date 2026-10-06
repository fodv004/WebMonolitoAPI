"""
screens/config_screen.py
Pantalla de configuracion: IP de la VM, puerto de cada microservicio,
protocolo (HTTP por default / HTTPS) y semaforo. Se guarda en config.json
(sin tokens: el JWT vive solo en memoria) y se aplica sin reiniciar la app.

  HTTP  -> http://<IP>:<puerto>
  HTTPS -> https://<IP>/api/<servicio>, con la opcion de verificar el
           certificado contra un archivo .crt.
"""
import tkinter as tk
from tkinter import filedialog, ttk

from api import health
from config.settings import ETIQUETAS, SERVICIOS, VALORES_POR_DEFECTO, AppConfig, validar
from utils import run_async
from widgets import theme

_AVISO_SIN_VERIFICAR = ("⚠ Verificación del certificado DESACTIVADA: la conexión va cifrada, pero la app "
                        "no comprueba que el servidor sea realmente tu VM. Úsalo solo para pruebas.")


class ConfigScreen(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        tarjeta = theme.tarjeta_centrada(self, "Configuración", "Conexión con los microservicios de la VM")

        self.host_var = tk.StringVar()
        theme.campo(tarjeta, 3, "IP de la VM", self.host_var)

        # ---- protocolo
        ttk.Label(tarjeta, text="Protocolo", style="Card.TLabel").grid(row=4, column=0, sticky="e", padx=(0, 12), pady=6)
        self.protocolo_var = tk.StringVar(value="http")
        protocolos = ttk.Frame(tarjeta, style="CardInner.TFrame")
        protocolos.grid(row=4, column=1, sticky="w")
        ttk.Radiobutton(protocolos, text="HTTP (por defecto)", value="http", variable=self.protocolo_var,
                        style="Card.TRadiobutton", command=self._actualizar_estado_https).pack(side="left")
        ttk.Radiobutton(protocolos, text="HTTPS", value="https", variable=self.protocolo_var,
                        style="Card.TRadiobutton", command=self._actualizar_estado_https).pack(side="left", padx=(16, 0))

        # ---- puertos (3 columnas x 2 filas)
        ttk.Label(tarjeta, text="Puertos", style="Card.TLabel").grid(row=5, column=0, sticky="ne", padx=(0, 12), pady=8)
        puertos = ttk.Frame(tarjeta, style="CardInner.TFrame")
        puertos.grid(row=5, column=1, sticky="w", pady=4)
        self.puerto_vars = {}
        self._entradas_puerto = []
        for i, servicio in enumerate(SERVICIOS):
            fila, columna = divmod(i, 3)
            ttk.Label(puertos, text=ETIQUETAS[servicio], style="Card.TLabel").grid(
                row=fila, column=columna * 2, sticky="e", padx=(0 if columna == 0 else 14, 6), pady=3)
            self.puerto_vars[servicio] = tk.StringVar()
            entrada = ttk.Entry(puertos, textvariable=self.puerto_vars[servicio], width=7)
            entrada.grid(row=fila, column=columna * 2 + 1, pady=3)
            self._entradas_puerto.append(entrada)

        # ---- HTTPS
        self.verificar_var = tk.BooleanVar(value=True)
        self.check_verificar = ttk.Checkbutton(tarjeta, text="Verificar certificado", variable=self.verificar_var,
                                               style="Card.TCheckbutton", command=self._actualizar_estado_https)
        self.check_verificar.grid(row=6, column=1, sticky="w", pady=(6, 0))

        ttk.Label(tarjeta, text="Certificado (.crt)", style="Card.TLabel").grid(
            row=7, column=0, sticky="e", padx=(0, 12), pady=6)
        certificado = ttk.Frame(tarjeta, style="CardInner.TFrame")
        certificado.grid(row=7, column=1, sticky="ew")
        certificado.grid_columnconfigure(0, weight=1)
        self.certificado_var = tk.StringVar()
        self.entrada_certificado = ttk.Entry(certificado, textvariable=self.certificado_var)
        self.entrada_certificado.grid(row=0, column=0, sticky="ew")
        self.boton_certificado = ttk.Button(certificado, text="Examinar…", command=self._elegir_certificado)
        self.boton_certificado.grid(row=0, column=1, padx=(6, 0))

        self.aviso_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.aviso_var, style="Error.TLabel", wraplength=460, justify="left").grid(
            row=8, column=0, columnspan=2, sticky="w")

        # ---- semaforo
        ttk.Label(tarjeta, text="Semáforo", style="Card.TLabel").grid(row=9, column=0, sticky="e", padx=(0, 12), pady=6)
        semaforo = ttk.Frame(tarjeta, style="CardInner.TFrame")
        semaforo.grid(row=9, column=1, sticky="w")
        self.intervalo_var = tk.StringVar()
        self.timeout_var = tk.StringVar()
        ttk.Label(semaforo, text="Intervalo (s)", style="Card.TLabel").pack(side="left")
        ttk.Entry(semaforo, textvariable=self.intervalo_var, width=6).pack(side="left", padx=(6, 16))
        ttk.Label(semaforo, text="Timeout (s)", style="Card.TLabel").pack(side="left")
        ttk.Entry(semaforo, textvariable=self.timeout_var, width=6).pack(side="left", padx=(6, 0))

        self.estado_var = tk.StringVar()
        ttk.Label(tarjeta, textvariable=self.estado_var, style="Subtitulo.TLabel", wraplength=460, justify="left").grid(
            row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))

        botones = ttk.Frame(tarjeta, style="CardInner.TFrame")
        botones.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        botones.grid_columnconfigure((0, 1, 2, 3), weight=1)
        ttk.Button(botones, text="Probar conexión", command=self._probar).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(botones, text="Restaurar valores por defecto", command=self._restaurar).grid(
            row=0, column=1, sticky="ew", padx=4)
        ttk.Button(botones, text="Guardar", style="Primary.TButton", command=self._guardar).grid(
            row=0, column=2, sticky="ew", padx=4)
        ttk.Button(botones, text="Volver", command=lambda: app.volver()).grid(row=0, column=3, sticky="ew", padx=(4, 0))

    # ------------------------------------------------------------ formulario
    def on_show(self):
        self._llenar(self.app.config_app.datos)
        self.estado_var.set("")

    def _llenar(self, datos):
        self.host_var.set(datos["host"])
        self.protocolo_var.set(datos["protocolo"])
        for servicio in SERVICIOS:
            self.puerto_vars[servicio].set(str(datos["puertos"][servicio]))
        self.verificar_var.set(datos["verificar_certificado"])
        self.certificado_var.set(datos["certificado"])
        self.intervalo_var.set(str(datos["semaforo_intervalo_s"]))
        self.timeout_var.set(str(datos["semaforo_timeout_s"]))
        self._actualizar_estado_https()

    def _leer(self):
        """Datos del formulario ya validados (lanza ValueError con el mensaje para el usuario)."""
        return validar({
            "host": self.host_var.get(),
            "protocolo": self.protocolo_var.get(),
            "puertos": {servicio: var.get() for servicio, var in self.puerto_vars.items()},
            "verificar_certificado": self.verificar_var.get(),
            "certificado": self.certificado_var.get(),
            "semaforo_intervalo_s": self.intervalo_var.get(),
            "semaforo_timeout_s": self.timeout_var.get(),
        })

    def _actualizar_estado_https(self):
        https = self.protocolo_var.get() == "https"
        verificar = self.verificar_var.get()
        self.check_verificar.state(["!disabled"] if https else ["disabled"])
        estado_certificado = ["!disabled"] if https and verificar else ["disabled"]
        self.entrada_certificado.state(estado_certificado)
        self.boton_certificado.state(estado_certificado)
        # Con HTTPS los puertos no se usan: todo entra por https://<IP>/api/<servicio>.
        for entrada in self._entradas_puerto:
            entrada.state(["disabled"] if https else ["!disabled"])
        self.aviso_var.set(_AVISO_SIN_VERIFICAR if https and not verificar else "")

    def _elegir_certificado(self):
        ruta = filedialog.askopenfilename(
            parent=self, title="Certificado del servidor",
            filetypes=[("Certificados", "*.crt *.pem *.cer"), ("Todos los archivos", "*.*")])
        if ruta:
            self.certificado_var.set(ruta)

    # ------------------------------------------------------------ acciones
    def _probar(self):
        """Revisa /health de los 6 servicios con los valores del formulario (aunque no esten guardados)."""
        try:
            prueba = AppConfig(self._leer())
        except ValueError as e:
            self.estado_var.set(str(e))
            return
        self.estado_var.set("Probando conexión con los 6 servicios...")
        timeout = prueba["semaforo_timeout_s"]

        def hacer():
            return [health.revisar(prueba, servicio, timeout) for servicio in SERVICIOS]

        def ok(resultados):
            partes = []
            for r in resultados:
                detalle = f"OK ({r['ms']} ms)" if r["ok"] else (r["error"] or f"HTTP {r['status']}")
                partes.append(f"{ETIQUETAS[r['servicio']]}: {detalle}")
            funcionales = sum(r["ok"] for r in resultados)
            self.estado_var.set("   ·   ".join(partes))
            self.app.set_estado(f"Prueba de conexión: {funcionales} de {len(resultados)} servicios funcionales",
                                "ok" if funcionales == len(resultados) else "error")

        run_async(self, hacer, ok, lambda e: self.estado_var.set(str(e)))

    def _restaurar(self):
        self._llenar(VALORES_POR_DEFECTO)
        self.estado_var.set("Valores por defecto cargados en el formulario. Pulsa Guardar para aplicarlos.")

    def _guardar(self):
        try:
            datos = self._leer()
        except ValueError as e:
            self.estado_var.set(str(e))
            return
        try:
            self.app.aplicar_configuracion(datos)
        except OSError as e:
            self.estado_var.set(f"No se pudo escribir config.json: {e}")
            return
        self._llenar(datos)
        self.estado_var.set("Configuración guardada y aplicada.")
        self.app.set_estado("Configuración guardada y aplicada (sin reiniciar).", "ok")
