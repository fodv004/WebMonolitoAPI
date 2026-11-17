"""
config/settings.py
Configuracion de la app: URL base del API Gateway, certificado (si el
gateway es HTTPS) y semaforo. Se guarda en config.json junto al programa y
se aplica sin reiniciar: los clientes HTTP leen este objeto en cada peticion.

Nunca se guardan tokens aqui: el JWT y el refresh token viven solo en
memoria (session.py).

Todas las peticiones pasan por el API Gateway (nginx) con UNA sola URL base:
  http://IP_EXTERNA:8080/catalogo/api
y el gateway enruta por prefijo a cada microservicio (/login, /books,
/users, /authors, /pedidos, /pagos, /envios, /ws...).

La variable de entorno EG4_GATEWAY_URL, si existe, tiene prioridad sobre
config.json.
"""
import copy
import json
import os
from pathlib import Path
from urllib.parse import urlparse

_RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = _RAIZ / "config.json"
_ARCHIVO_ANTERIOR = _RAIZ / "local_storage.json"   # formato viejo: solo se lee para heredar la IP

ENV_GATEWAY_URL = "EG4_GATEWAY_URL"
GATEWAY_PUERTO = 8080
GATEWAY_PREFIJO = "/catalogo/api"

SERVICIOS = ("login", "books", "users", "authors", "pedidos", "pagos")
ETIQUETAS = {"login": "Login", "books": "Libros", "users": "Usuarios",
             "authors": "Autores", "pedidos": "Pedidos", "pagos": "Pagos"}

TIMEOUT_HTTP = 5  # segundos, para todas las peticiones a los microservicios


def gateway_de_host(host):
    """URL del gateway para una IP/nombre: http://<host>:8080/catalogo/api."""
    return f"http://{host}:{GATEWAY_PUERTO}{GATEWAY_PREFIJO}"


VALORES_POR_DEFECTO = {
    # 127.0.0.1 y no "localhost": en Windows prueba antes IPv6 y cada peticion tarda ~2 s
    "gateway_url": gateway_de_host("127.0.0.1"),
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


def normalizar_gateway_url(valor):
    """Valida la URL del gateway y la devuelve sin "/" final (lanza ValueError)."""
    url = str(valor or "").strip().rstrip("/")
    partes = urlparse(url)
    if partes.scheme not in ("http", "https") or not partes.hostname or any(c in url for c in " ?#@"):
        raise ValueError("La URL del gateway no es válida "
                         "(ejemplo: http://34.51.58.130:8080/catalogo/api).")
    try:
        partes.port
    except ValueError:
        raise ValueError("El puerto de la URL del gateway no es válido.")
    return url


def validar(datos):
    """Devuelve una copia normalizada de `datos` o lanza ValueError con un mensaje para el usuario."""
    return {
        "gateway_url": normalizar_gateway_url(datos.get("gateway_url")),
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
        config = cls._cargar_archivo(archivo or ARCHIVO)
        desde_entorno = os.environ.get(ENV_GATEWAY_URL, "").strip()
        if desde_entorno:
            try:
                config.datos["gateway_url"] = normalizar_gateway_url(desde_entorno)
            except ValueError:
                print(f"[config] {ENV_GATEWAY_URL} no es una URL válida; se ignora: {desde_entorno}", flush=True)
        return config

    @classmethod
    def _cargar_archivo(cls, archivo):
        base = copy.deepcopy(VALORES_POR_DEFECTO)
        try:
            guardado = json.loads(archivo.read_text(encoding="utf-8"))
        except FileNotFoundError:
            host = _host_anterior()
            if host:
                base["gateway_url"] = gateway_de_host(host)
            return cls(base)
        except (OSError, ValueError):
            return cls()
        if not isinstance(guardado, dict):
            return cls()
        base.update({k: v for k, v in guardado.items() if k in base})
        if "gateway_url" not in guardado and guardado.get("host"):
            # config.json de la version anterior (IP + puerto por servicio): se pasa al gateway.
            base["gateway_url"] = gateway_de_host(str(guardado["host"]).strip())
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
        return self.datos["gateway_url"].startswith("https://")

    def base_url(self, servicio=None):
        """URL base de cualquier servicio: siempre la del gateway. Cada cliente agrega
        su prefijo (/login, /books, /users, ...) y el gateway enruta."""
        return self.datos["gateway_url"]

    def verify(self):
        """Valor del parametro `verify` de requests: False, la ruta del .crt o True (CAs del sistema)."""
        if not self.datos["verificar_certificado"]:
            return False
        return self.datos["certificado"] or True
