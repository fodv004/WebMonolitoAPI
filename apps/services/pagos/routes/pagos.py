"""
routes/pagos.py
Endpoints del microservicio pagos. Solo traducen HTTP <-> services/pagos_service.py.

  POST   /pagos                      JWT (dueño del pedido)   header Idempotency-Key obligatorio
  GET    /pagos                      JWT            cliente: los suyos; admin: todos (?estado=&metodo=&user_id=)
  GET    /pagos/<id>                 JWT            dueño o admin
  GET    /pagos/pedido/<pedido_id>   JWT            dueño o admin
  PATCH  /pagos/<id>                 JWT + admin    solo referencia y notas
  POST   /pagos/<id>/reembolso       JWT + admin    pago -> REEMBOLSADO, pedido -> CANCELADO
  DELETE /pagos/<id>                 JWT + admin    borrado logico, solo RECHAZADO

Body de POST /pagos:
  {"pedido_id": 7, "metodo": "TARJETA_SIMULADA", "tarjeta": "4111111111111111", "cvv": "123"}
  {"pedido_id": 7, "metodo": "TRANSFERENCIA"}        (o "EFECTIVO")
No lleva monto: sale del pedido. Responde 201 la primera vez y 200 (con "repetido": true)
cuando es el reenvio de una Idempotency-Key ya usada.

Errores: {"error": "<CODIGO>", "message": "<texto>"} (common/errors.py).
"""
from flask import Blueprint, g, jsonify, request

from common.auth import ADMIN_ROLE_ID, require_auth, require_role
from services import pagos_service
from services.pagos_service import Actor

bp = Blueprint("pagos", __name__)
solo_admin = require_role(ADMIN_ROLE_ID)

IDEMPOTENCY_HEADER = "Idempotency-Key"


def _actor():
    return Actor(g.jwt_payload)


def _json():
    return request.get_json(silent=True)


@bp.post("/pagos")
@require_auth
def pagar():
    pago, creado = pagos_service.pagar(_actor(), request.headers.get(IDEMPOTENCY_HEADER), _json())
    return jsonify({**pago, "repetido": not creado}), 201 if creado else 200


@bp.get("/pagos")
@require_auth
def listar():
    return jsonify(pagos_service.listar(_actor(), request.args))


@bp.get("/pagos/<int:pago_id>")
@require_auth
def obtener(pago_id):
    return jsonify(pagos_service.obtener(_actor(), pago_id))


@bp.get("/pagos/pedido/<int:pedido_id>")
@require_auth
def de_pedido(pedido_id):
    return jsonify(pagos_service.de_pedido(_actor(), pedido_id))


@bp.patch("/pagos/<int:pago_id>")
@solo_admin
def editar(pago_id):
    return jsonify(pagos_service.editar(pago_id, _json()))


@bp.post("/pagos/<int:pago_id>/reembolso")
@solo_admin
def reembolsar(pago_id):
    return jsonify(pagos_service.reembolsar(pago_id, _json()))


@bp.delete("/pagos/<int:pago_id>")
@solo_admin
def eliminar(pago_id):
    return jsonify(pagos_service.eliminar(pago_id))
