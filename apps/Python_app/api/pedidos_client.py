"""
api/pedidos_client.py
Cliente del microservicio pedidos (apps/services/pedidos, puerto 5004):
pedidos, lineas, estados e inventario. Todo lo de pedidos exige JWT; el
inventario se consulta sin token y lo modifica solo el admin.
"""
import urllib.parse

from api.http_base import ServiceClient


def _lineas(cantidades):
    """{isbn: cantidad} -> cuerpo {"lineas": [{"isbn", "cantidad"}]}."""
    return {"lineas": [{"isbn": isbn, "cantidad": cantidad} for isbn, cantidad in cantidades.items()]}


class PedidosClient(ServiceClient):
    SERVICIO = "pedidos"

    # ------------------------------------------------------------ pedidos
    def create(self, cantidades):
        """Crea el pedido y reserva el stock. 409 si no alcanza (el mensaje indica el ISBN)."""
        return self._http.post("/pedidos", _lineas(cantidades))

    def list(self, estado=None, user_id=None, page=1, per_page=20):
        """Cliente: sus pedidos. Admin: todos, con filtros. {"items", "page", "per_page", "total", "pages"}."""
        return self._http.get("/pedidos", params={"estado": estado, "user_id": user_id,
                                                  "page": page, "per_page": per_page})

    def get(self, pedido_id):
        """Pedido con lineas e historial."""
        return self._http.get(f"/pedidos/{pedido_id}")

    def replace_lines(self, pedido_id, cantidades):
        """PUT: las lineas enviadas pasan a ser el pedido completo (solo PENDIENTE_PAGO)."""
        return self._http.put(f"/pedidos/{pedido_id}", _lineas(cantidades))

    def patch_lines(self, pedido_id, cantidades):
        """PATCH: cambia solo las lineas enviadas; cantidad 0 quita la linea."""
        return self._http.patch(f"/pedidos/{pedido_id}/lineas", _lineas(cantidades))

    def cancel(self, pedido_id):
        return self._http.patch(f"/pedidos/{pedido_id}/cancelar", {})

    def set_state(self, pedido_id, estado):
        """Admin: ENVIADO o ENTREGADO."""
        return self._http.patch(f"/pedidos/{pedido_id}/estado", {"estado": estado})

    def delete(self, pedido_id):
        """Admin: borrado logico de un pedido CANCELADO o EXPIRADO."""
        return self._http.delete(f"/pedidos/{pedido_id}")

    # ------------------------------------------------------------ inventario
    @staticmethod
    def _isbn(isbn):
        return urllib.parse.quote(isbn, safe="")

    def inventory(self, per_page=500):
        """[{isbn, stock_disponible, stock_reservado, updated_at}] (publico)."""
        return self._http.get("/inventario", params={"per_page": per_page}, auth=False).get("items", [])

    def inventory_add(self, isbn, stock_disponible):
        return self._http.post("/inventario", {"isbn": isbn, "stock_disponible": stock_disponible})

    def inventory_set(self, isbn, stock_disponible):
        return self._http.put(f"/inventario/{self._isbn(isbn)}", {"stock_disponible": stock_disponible})

    def inventory_remove(self, isbn):
        return self._http.delete(f"/inventario/{self._isbn(isbn)}")
