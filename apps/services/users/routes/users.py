"""
routes/users.py
Endpoints del microservicio users. Solo traducen HTTP <-> services/users_service.py.

  GET    /users                    JWT + admin   lista paginada (?q=&role_id=&activo=&page=&per_page=)
  GET    /users/me                 JWT           la cuenta del token
  GET    /users/<id>               JWT           admin o el mismo usuario
  POST   /users                    JWT + admin   alta
  PUT    /users/<id>               JWT           admin o el mismo usuario (solo admin: activo, role_id)
  PATCH  /users/<id>               JWT           idem, solo los campos enviados
  DELETE /users/<id>               JWT + admin   baja logica (activo = false)
  PATCH  /users/<id>/password      JWT           propia (con la actual) o restablecida por el admin
  PATCH  /users/<id>/email         JWT           admin o el mismo usuario; pide confirmacion a login
  PATCH  /users/<id>/role          JWT + admin
  GET    /roles                    JWT
  GET    /users/internal/<id>      X-Internal-Key   datos minimos para pedidos y pagos

Errores: {"error": "<CODIGO>", "message": "<texto>"} (common/errors.py).
"""
from flask import Blueprint, g, jsonify, request

from common.auth import ADMIN_ROLE_ID, require_auth, require_internal_key, require_role
from services import users_service
from services.users_service import Actor

bp = Blueprint("users", __name__)
solo_admin = require_role(ADMIN_ROLE_ID)


def _actor():
    return Actor(g.jwt_payload)


def _json():
    return request.get_json(silent=True)


@bp.get("/users")
@solo_admin
def listar():
    return jsonify(users_service.listar(request.args))


@bp.get("/users/me")
@require_auth
def yo():
    actor = _actor()
    return jsonify(users_service.obtener(actor, actor.user_id))


@bp.get("/users/<int:user_id>")
@require_auth
def obtener(user_id):
    return jsonify(users_service.obtener(_actor(), user_id))


@bp.post("/users")
@solo_admin
def crear():
    return jsonify(users_service.crear(_json())), 201


@bp.put("/users/<int:user_id>")
@require_auth
def reemplazar(user_id):
    return jsonify(users_service.actualizar(_actor(), user_id, _json(), parcial=False))


@bp.patch("/users/<int:user_id>")
@require_auth
def modificar(user_id):
    return jsonify(users_service.actualizar(_actor(), user_id, _json(), parcial=True))


@bp.delete("/users/<int:user_id>")
@solo_admin
def desactivar(user_id):
    return jsonify(users_service.desactivar(user_id))


@bp.patch("/users/<int:user_id>/password")
@require_auth
def cambiar_password(user_id):
    users_service.cambiar_password(_actor(), user_id, _json())
    return jsonify({"status": "ok", "message": "Contraseña actualizada. Las sesiones del usuario se cerraron."})


@bp.patch("/users/<int:user_id>/email")
@require_auth
def cambiar_email(user_id):
    usuario = users_service.cambiar_email(_actor(), user_id, _json())
    return jsonify({"status": "ok", "user": usuario,
                    "message": "Correo actualizado. Se envio un enlace de confirmacion al correo nuevo."})


@bp.patch("/users/<int:user_id>/role")
@solo_admin
def cambiar_rol(user_id):
    return jsonify(users_service.cambiar_rol(user_id, _json()))


@bp.get("/roles")
@require_auth
def roles():
    return jsonify(users_service.roles())


@bp.get("/users/internal/<int:user_id>")
@require_internal_key
def interno(user_id):
    return jsonify(users_service.interno(user_id))
