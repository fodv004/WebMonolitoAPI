"""
routes/pedidos.py
Endpoints de pedidos. Solo traducen HTTP <-> services/.

  POST   /pedidos                        JWT            crea el pedido y reserva el stock
  GET    /pedidos                        JWT            cliente: los suyos; admin: todos (?estado=&user_id=)
  GET    /pedidos/<id>                   JWT            dueño o admin; con lineas e historial
  PUT    /pedidos/<id>                   JWT (dueño)    reemplaza las lineas (solo PENDIENTE_PAGO)
  PATCH  /pedidos/<id>/lineas            JWT (dueño)    cambia algunas lineas (cantidad 0 = quitar)
  PATCH  /pedidos/<id>/cancelar          JWT            dueño en PENDIENTE_PAGO; admin si es cancelable
  PATCH  /pedidos/<id>/estado            JWT + admin    ENVIADO | ENTREGADO
  DELETE /pedidos/<id>                   JWT + admin    borrado logico (solo CANCELADO o EXPIRADO)
  GET    /pedidos/internal/<id>          X-Internal-Key para el servicio pagos
  PATCH  /pedidos/internal/<id>/estado   X-Internal-Key PAGADO | CANCELADO

El stock es libros.stock: lo reserva y lo libera books (endpoints internos) y el admin lo
edita con PATCH /books/<isbn>.

Errores: {"error": "<CODIGO>", "message": "<texto>"} (common/errors.py).
"""
from flask import Blueprint, g, jsonify, request

from common.auth import ADMIN_ROLE_ID, require_auth, require_internal_key, require_role
from services import pedidos_service
from services.pedidos_service import Actor

bp = Blueprint("pedidos", __name__)
solo_admin = require_role(ADMIN_ROLE_ID)


def _actor():
    return Actor(g.jwt_payload)


def _json():
    return request.get_json(silent=True)


# ------------------------------------------------------------------ pedidos
@bp.post("/pedidos")
@require_auth
def crear():
    return jsonify(pedidos_service.crear(_actor(), _json())), 201


@bp.get("/pedidos")
@require_auth
def listar():
    return jsonify(pedidos_service.listar(_actor(), request.args))


@bp.get("/pedidos/<int:pedido_id>")
@require_auth
def obtener(pedido_id):
    return jsonify(pedidos_service.obtener(_actor(), pedido_id))


@bp.put("/pedidos/<int:pedido_id>")
@require_auth
def reemplazar_lineas(pedido_id):
    return jsonify(pedidos_service.editar_lineas(_actor(), pedido_id, _json(), reemplazar=True))


@bp.patch("/pedidos/<int:pedido_id>/lineas")
@require_auth
def modificar_lineas(pedido_id):
    return jsonify(pedidos_service.editar_lineas(_actor(), pedido_id, _json(), reemplazar=False))


@bp.patch("/pedidos/<int:pedido_id>/cancelar")
@require_auth
def cancelar(pedido_id):
    return jsonify(pedidos_service.cancelar(_actor(), pedido_id))


@bp.patch("/pedidos/<int:pedido_id>/estado")
@solo_admin
def cambiar_estado(pedido_id):
    return jsonify(pedidos_service.cambiar_estado_admin(_actor(), pedido_id, _json()))


@bp.delete("/pedidos/<int:pedido_id>")
@solo_admin
def eliminar(pedido_id):
    return jsonify(pedidos_service.eliminar(pedido_id))


# ------------------------------------------------------------------ internos (servicio pagos)
@bp.get("/pedidos/internal/<int:pedido_id>")
@require_internal_key
def obtener_interno(pedido_id):
    return jsonify(pedidos_service.obtener_interno(pedido_id))


@bp.patch("/pedidos/internal/<int:pedido_id>/estado")
@require_internal_key
def cambiar_estado_interno(pedido_id):
    return jsonify(pedidos_service.cambiar_estado_interno(pedido_id, _json()))
