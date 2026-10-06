"""
api/auth_client.py
Cliente del microservicio de login (apps/services/login, puerto 5000).
register, login y refresh van SIN header Authorization: un 401 ahi
significa credenciales o refresh token invalidos, no sesion expirada.
"""
from api.http_base import ServiceClient


class AuthClient(ServiceClient):
    SERVICIO = "login"

    def register(self, nombre, apellido_paterno, apellido_materno, email, password):
        return self._http.post("/register", {
            "nombre": nombre,
            "apellido_paterno": apellido_paterno,
            "apellido_materno": apellido_materno,
            "email": email,
            "password": password,
        }, auth=False)

    def login(self, email, password):
        return self._http.post("/login", {"email": email, "password": password}, auth=False)

    def refresh(self, refresh_token):
        return self._http.post("/refresh", {"refresh_token": refresh_token}, auth=False)

    def logout(self, token, refresh_token=None):
        """Revoca el JWT y borra la sesion en el servidor. Recibe los tokens de forma
        explicita porque se llama despues de limpiar la sesion local."""
        return self._http.post("/logout", {"refresh_token": refresh_token} if refresh_token else {}, token=token)

    def session(self):
        return self._http.get("/session")
