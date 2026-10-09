"""
api/pagos_client.py
Cliente del microservicio pagos (apps/services/pagos, puerto 5005): pagos
SIMULADOS de los pedidos. Todo exige JWT; corregir, reembolsar y eliminar
son del admin.

El numero de tarjeta y el CVV solo viajan en el cuerpo de POST /pagos
(el log de consola los oculta) y esta app no los guarda en ningun lado.
"""
from api.http_base import ServiceClient

METODOS = ("TARJETA_SIMULADA", "TRANSFERENCIA", "EFECTIVO")
ESTADOS = ("APROBADO", "RECHAZADO", "REEMBOLSADO")


class PagosClient(ServiceClient):
    SERVICIO = "pagos"

    def pay(self, pedido_id, metodo, idempotency_key, tarjeta=None, cvv=None):
        """Paga un pedido. `idempotency_key` identifica el intento: reenviarla devuelve el MISMO
        pago (con "repetido": true) sin cobrar otra vez. El monto lo pone el servidor."""
        cuerpo = {"pedido_id": pedido_id, "metodo": metodo}
        if metodo == "TARJETA_SIMULADA":
            cuerpo.update(tarjeta=tarjeta, cvv=cvv)
        return self._http.post("/pagos", cuerpo, headers={"Idempotency-Key": idempotency_key})

    def list(self, estado=None, metodo=None, user_id=None, page=1, per_page=50):
        """Cliente: sus pagos. Admin: todos, con filtros. {"items", "page", "per_page", "total", "pages"}."""
        return self._http.get("/pagos", params={"estado": estado, "metodo": metodo, "user_id": user_id,
                                                "page": page, "per_page": per_page})

    def get(self, pago_id):
        return self._http.get(f"/pagos/{pago_id}")

    def of_order(self, pedido_id):
        """{"pedido_id", "items": [...]} con los pagos de un pedido."""
        return self._http.get(f"/pagos/pedido/{pedido_id}")

    # ------------------------------------------------------------ admin
    def update(self, pago_id, referencia=None, notas=None):
        """Corrige la referencia y/o las notas (nunca el monto). Solo se envia lo que no sea None."""
        cuerpo = {campo: valor for campo, valor in (("referencia", referencia), ("notas", notas))
                  if valor is not None}
        return self._http.patch(f"/pagos/{pago_id}", cuerpo)

    def refund(self, pago_id, notas=None):
        """Pago a REEMBOLSADO y pedido a CANCELADO (pedidos libera el stock)."""
        return self._http.post(f"/pagos/{pago_id}/reembolso", {"notas": notas} if notas else {})

    def delete(self, pago_id):
        """Borrado logico; solo pagos RECHAZADO."""
        return self._http.delete(f"/pagos/{pago_id}")
