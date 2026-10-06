"""
config/settings.py
Configuracion de la app (IP de la VM, puerto de cada microservicio,
protocolo y semaforo). Se guarda en config.json junto al programa y se
aplica sin reiniciar: los clientes HTTP leen este objeto en cada peticion.

Nunca se guardan tokens aqui: el JWT y el refresh token viven solo en
memoria (session.py).

URL de cada servicio:
  HTTP  (default) -> http://<IP>:<puerto>
  HTTPS           -> https://<IP>/api/<servicio>   (proxy inverso en la VM)
"""
import copy
import json
from pathlib import Path
from urllib.parse import urlparse

_RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = _RAIZ / "config.json"
_ARCHIVO_ANTERIOR = _RAIZ / "local_storage.json"   # formato viejo: solo se lee para heredar la IP

SERVICIOS = ("login", "books", "users", "authors", "pedidos", "pagos")
ETIQUETAS = {"login": "Login", "books": "Libros", "users": "Usuarios",
             "authors": "Autores", "pedidos": "Pedidos", "pagos": "Pagos"}

TIMEOUT_HTTP = 5  # segundos, para todas las peticiones a los microservicios

VALORES_POR_DEFECTO = {
    "host": "127.0.0.1",   # no "localhost": en Windows prueba antes IPv6 y cada peticion tarda ~2 s
    "protocolo": "http",
    "puertos": {"login": 5000, "books": 5001, "users": 5002, "authors": 5003, "pedidos": 5004, "pagos": 5005},
    "verificar_certificado": True,
    "certificado": "",
    "semaforo_intervalo_s": 10,
    "semaforo_timeout_s": 3,
}


def _entero(valor, nombre, minimo, maximo):
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{nombre} debe ser un número entero.")
    if not minimo <= numero <= maximo:
        raise ValueError(f"{nombre} debe estar entre {minimo} y {maximo}.")
    return numero


def validar(datos):
    """Devuelve una copia normalizada de `datos` o lanza ValueError con un mensaje para el usuario."""
    host = str(datos.get("host", "")).strip()
    if "://" in host:
        host = urlparse(host).hostname or ""
    host = host.strip("/")
    if not host or any(c in host for c in " /?#@"):
        raise ValueError("La IP o nombre de la VM no es válido (ejemplo: 34.51.58.130).")

    protocolo = str(datos.get("protocolo", "http")).lower()
    if protocolo not in ("http", "https"):
        raise ValueError("El protocolo debe ser HTTP o HTTPS.")

    puertos_recibidos = datos.get("puertos") or {}
    puertos = {s: _entero(puertos_recibidos.get(s, VALORES_POR_DEFECTO["puertos"][s]),
                          f"El puerto de {ETIQUETAS[s]}", 1, 65535) for s in SERVICIOS}

    return {
        "host": host,
        "protocolo": protocolo,
        "puertos": puertos,
        "verificar_certificado": bool(datos.get("verificar_certificado", True)),
        "certificado": str(datos.get("certificado") or "").strip(),
        "semaforo_intervalo_s": _entero(datos.get("semaforo_intervalo_s", 10), "El intervalo del semáforo", 2, 3600),
        "semaforo_timeout_s": _entero(datos.get("semaforo_timeout_s", 3), "El timeout del semáforo", 1, 60),
    }


def _host_anterior():
    """IP que el usuario ya habia configurado en local_storage.json (version anterior de la app)."""
    try:
        datos = json.loads(_ARCHIVO_ANTERIOR.read_text(encoding="utf-8"))
        return urlparse(datos.get("login_base_url", "")).hostname
    except (OSError, ValueError, AttributeError):
        return None


class AppConfig:
    def __init__(self, datos=None):
        self.datos = validar(datos) if datos else copy.deepcopy(VALORES_POR_DEFECTO)

    # ------------------------------------------------------------ disco
    @classmethod
    def cargar(cls, archivo=None):
        archivo = archivo or ARCHIVO
        base = copy.deepcopy(VALORES_POR_DEFECTO)
        try:
            guardado = json.loads(archivo.read_text(encoding="utf-8"))
        except FileNotFoundError:
            base["host"] = _host_anterior() or base["host"]
            return cls(base)
        except (OSError, ValueError):
            return cls()
        if not isinstance(guardado, dict):
            return cls()
        base.update({k: v for k, v in guardado.items() if k in base and k != "puertos"})
        if isinstance(guardado.get("puertos"), dict):
            base["puertos"].update({k: v for k, v in guardado["puertos"].items() if k in base["puertos"]})
        try:
            return cls(base)
        except ValueError:
            return cls()

    def guardar(self, archivo=None):
        # Solo las claves conocidas: aqui nunca llega un token.
        datos = {clave: self.datos[clave] for clave in VALORES_POR_DEFECTO}
        (archivo or ARCHIVO).write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")

    def aplicar(self, datos):
        """Valida y reemplaza la configuracion en caliente (los clientes la leen en cada peticion)."""
        self.datos = validar(datos)

    # ------------------------------------------------------------ lectura
    def __getitem__(self, clave):
        return self.datos[clave]

    @property
    def es_https(self):
        return self.datos["protocolo"] == "https"

    def base_url(self, servicio):
        if self.es_https:
            return f"https://{self.datos['host']}/api/{servicio}"
        return f"http://{self.datos['host']}:{self.datos['puertos'][servicio]}"

    def verify(self):
        """Valor del parametro `verify` de requests: False, la ruta del .crt o True (CAs del sistema)."""
        if not self.datos["verificar_certificado"]:
            return False
        return self.datos["certificado"] or True
