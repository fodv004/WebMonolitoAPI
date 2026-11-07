"""
routes/envios.py
Endpoints REST de envios. Solo traducen HTTP <-> services/envios_service.py.
  POST /envios                    JWT            body {"pedido_id": 7}; 201 nuevo, 200 si ya existia
  GET  /envios                    JWT            cliente: los suyos; admin: todos (?estado=&user_id=&page=&per_page=)
  GET  /envios/<codigo>           JWT            dueño o admin; con ruta completa y ruta recorrida
  GET  /envios/internal/activos   X-Internal-Key envios ENVIADO / EN_RUTA con los puntos de su ruta (simulador)
Errores: {"error": "<CODIGO>", "message": "<texto>"} (common/errors.py).
"""
from flask import Blueprint, g, jsonify, request

from common.auth import require_auth, require_internal_key
from services import envios_service
from services.envios_service import Actor

bp = Blueprint("envios", __name__)


def _actor():
    return Actor(g.jwt_payload)


@bp.post("/envios")
@require_auth
def crear():
    envio, creado = envios_service.crear(_actor(), request.headers.get("Authorization"),
                                         request.get_json(silent=True))
    return jsonify(envio), 201 if creado else 200


@bp.get("/envios")
@require_auth
def listar():
    return jsonify(envios_service.listar(_actor(), request.args))


@bp.get("/envios/internal/activos")
@require_internal_key
def activos():
    return jsonify(envios_service.activos())


@bp.get("/envios/<codigo>")
@require_auth
def obtener(codigo):
    return jsonify(envios_service.obtener(_actor(), codigo))
