"""
screens/config_screen.py
Pantalla de configuracion: URL base del API Gateway y semaforo. Se guarda
en config.json (sin tokens: el JWT vive solo en memoria) y se aplica sin
reiniciar la app.

  Gateway -> http://IP_EXTERNA:8080/catalogo/api  (todas las peticiones)
  Si la URL es https://, se puede verificar el certificado contra un .crt.
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

        tarjeta = theme.tarjeta_centrada(self, "Configuración", "Conexión con los microservicios (API Gateway)")

        self.gateway_var = tk.StringVar()
        theme.campo(tarjeta, 3, "URL del gateway", self.gateway_var)
        self.gateway_var.trace_add("write", lambda *_: self._actualizar_estado_https())
        ttk.Label(tarjeta, text="Ejemplo: http://IP_EXTERNA:8080/catalogo/api", style="Subtitulo.TLabel").grid(
            row=4, column=1, sticky="w")

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
        self.gateway_var.set(datos["gateway_url"])
        self.verificar_var.set(datos["verificar_certificado"])
        self.certificado_var.set(datos["certificado"])
        self.intervalo_var.set(str(datos["semaforo_intervalo_s"]))
        self.timeout_var.set(str(datos["semaforo_timeout_s"]))
        self._actualizar_estado_https()

    def _leer(self):
        """Datos del formulario ya validados (lanza ValueError con el mensaje para el usuario)."""
        return validar({
            "gateway_url": self.gateway_var.get(),
            "verificar_certificado": self.verificar_var.get(),
            "certificado": self.certificado_var.get(),
            "semaforo_intervalo_s": self.intervalo_var.get(),
            "semaforo_timeout_s": self.timeout_var.get(),
        })

    def _actualizar_estado_https(self):
        if not hasattr(self, "aviso_var"):
            return                    # el trace de la URL se dispara antes de crear el resto del formulario
        https = self.gateway_var.get().strip().lower().startswith("https://")
        verificar = self.verificar_var.get()
        self.check_verificar.state(["!disabled"] if https else ["disabled"])
        estado_certificado = ["!disabled"] if https and verificar else ["disabled"]
        self.entrada_certificado.state(estado_certificado)
        self.boton_certificado.state(estado_certificado)
        self.aviso_var.set(_AVISO_SIN_VERIFICAR if https and not verificar else "")

    def _elegir_certificado(self):
        ruta = filedialog.askopenfilename(
            parent=self, title="Certificado del servidor",
            filetypes=[("Certificados", "*.crt *.pem *.cer"), ("Todos los archivos", "*.*")])
        if ruta:
            self.certificado_var.set(ruta)

    # ------------------------------------------------------------ acciones
    def _probar(self):
        """Sondea los 6 servicios por el gateway con los valores del formulario (aunque no esten guardados)."""
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
