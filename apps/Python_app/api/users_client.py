"""
api/users_client.py
Cliente del microservicio users (apps/services/users, puerto 5002):
usuarios, roles, correos y contraseñas. Todas las rutas exigen JWT; las
de administracion (listar, crear, desactivar, cambiar rol) exigen rol admin.
"""
from api.http_base import ServiceClient


class UsersClient(ServiceClient):
    SERVICIO = "users"

    def list(self, q=None, role_id=None, activo=None, page=1, per_page=20):
        """{"items": [...], "page", "per_page", "total", "pages"}. `activo`: True, False o None (todos)."""
        return self._http.get("/users", params={
            "q": q, "role_id": role_id, "page": page, "per_page": per_page,
            "activo": None if activo is None else ("true" if activo else "false"),
        })

    def me(self):
        return self._http.get("/users/me")

    def get(self, user_id):
        return self._http.get(f"/users/{user_id}")

    def roles(self):
        return self._http.get("/roles")

    def create(self, **campos):
        return self._http.post("/users", campos)

    def update(self, user_id, **campos):
        """PUT: reemplaza nombre y apellidos."""
        return self._http.put(f"/users/{user_id}", campos)

    def patch(self, user_id, **campos):
        """PATCH: solo los campos enviados (el admin puede incluir activo y role_id)."""
        return self._http.patch(f"/users/{user_id}", campos)

    def deactivate(self, user_id):
        """Baja logica (activo = false)."""
        return self._http.delete(f"/users/{user_id}")

    def change_password(self, user_id, password_nueva, password_actual=None):
        cuerpo = {"password_nueva": password_nueva}
        if password_actual is not None:
            cuerpo["password_actual"] = password_actual
        return self._http.patch(f"/users/{user_id}/password", cuerpo)

    def change_email(self, user_id, email):
        return self._http.patch(f"/users/{user_id}/email", {"email": email})

    def change_role(self, user_id, role_id):
        return self._http.patch(f"/users/{user_id}/role", {"role_id": role_id})
