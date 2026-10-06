"""
session.py
Sesion del usuario EN MEMORIA: JWT de acceso, refresh token y datos del
usuario. Nada de esto se escribe a disco; se pierde al cerrar sesion o
la app.

El JWT dura 20 minutos. La app lo renueva de forma proactiva a los 17
(main.py programa el temporizador con `segundos_para_renovar`) y, si un
servicio responde 401, el cliente HTTP intenta UNA renovacion antes de
regresar al login.
"""
import threading

MARGEN_RENOVACION_S = 180   # renovar 3 minutos antes de que caduque (20 min -> minuto 17)
ADMIN_ROLE_ID = 1


class Session:
    def __init__(self):
        self._lock = threading.Lock()
        self._refrescar = None        # funcion(refresh_token) -> datos; la registra main.py
        self.token = None
        self.refresh_token = None
        self.usuario = None
        self.expires_in = 0

    def conectar_refresh(self, funcion):
        self._refrescar = funcion

    # ------------------------------------------------------------ estado
    @property
    def activa(self):
        return bool(self.token)

    @property
    def es_admin(self):
        return (self.usuario or {}).get("role_id") == ADMIN_ROLE_ID

    def segundos_para_renovar(self):
        return max(self.expires_in - MARGEN_RENOVACION_S, 30)

    def iniciar(self, datos):
        """`datos` es el campo data de POST /login o POST /refresh."""
        self.token = datos["token"]
        self.refresh_token = datos.get("refresh_token")
        self.expires_in = int(datos.get("expires_in") or 0)
        if datos.get("user"):
            self.usuario = datos["user"]

    def limpiar(self):
        self.token = None
        self.refresh_token = None
        self.usuario = None
        self.expires_in = 0

    # ------------------------------------------------------------ renovacion
    def renovar(self, token_usado=None):
        """Cambia el refresh token por un JWT nuevo. True si la sesion quedo con un token vigente.

        `token_usado` es el JWT con el que fallo la peticion: si otro hilo ya lo
        renovo no se vuelve a llamar a /refresh (el refresh token es de un solo uso).
        Si el servidor rechaza el refresh token la sesion se limpia.
        """
        from api.http_base import ApiError

        with self._lock:
            if token_usado is not None and self.token and self.token != token_usado:
                return True
            if not self.refresh_token or self._refrescar is None:
                return False
            try:
                respuesta = self._refrescar(self.refresh_token)
            except ApiError as e:
                if e.status in (400, 401):
                    self.limpiar()
                return False
            datos = (respuesta or {}).get("data") or {}
            if not datos.get("token"):
                return False
            self.iniciar(datos)
            return True
