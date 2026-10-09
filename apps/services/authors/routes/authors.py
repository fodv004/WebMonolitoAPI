"""
routes/authors.py
Endpoints del microservicio authors. Solo traducen HTTP <-> services/authors_service.py.

  GET    /authors                      publico      lista paginada (?q=&nacionalidad=&page=&per_page=)
  GET    /authors/<id>                 publico
  GET    /authors/<id>/books           publico      libros del autor, con titulo si books responde
  GET    /authors/by-book/<isbn>       publico      autores de un libro
  POST   /authors                      JWT + admin
  PUT    /authors/<id>                 JWT + admin
  PATCH  /authors/<id>                 JWT + admin
  DELETE /authors/<id>                 JWT + admin  409 si tiene libros, salvo ?force=true
  POST   /authors/<id>/books           JWT + admin  body {"isbn"}; valida el ISBN en books
  DELETE /authors/<id>/books/<isbn>    JWT + admin

Tablas: autores (id_autor, nombre, nacionalidad) y libro_autor (isbn, id_autor).
Errores: {"error": "<CODIGO>", "message": "<texto>"} (common/errors.py).
"""
from flask import Blueprint, jsonify, request

from common.auth import ADMIN_ROLE_ID, require_role
from services import authors_service

bp = Blueprint("authors", __name__)
solo_admin = require_role(ADMIN_ROLE_ID)


def _json():
    return request.get_json(silent=True)


@bp.get("/authors")
def listar():
    return jsonify(authors_service.listar(request.args))


@bp.get("/authors/<int:author_id>")
def obtener(author_id):
    return jsonify(authors_service.obtener(author_id))


@bp.get("/authors/<int:author_id>/books")
def libros_de(author_id):
    return jsonify(authors_service.libros_de(author_id))


@bp.get("/authors/by-book/<isbn>")
def por_libro(isbn):
    return jsonify(authors_service.por_libro(isbn))


@bp.post("/authors")
@solo_admin
def crear():
    return jsonify(authors_service.crear(_json())), 201


@bp.put("/authors/<int:author_id>")
@solo_admin
def reemplazar(author_id):
    return jsonify(authors_service.actualizar(author_id, _json(), parcial=False))


@bp.patch("/authors/<int:author_id>")
@solo_admin
def modificar(author_id):
    return jsonify(authors_service.actualizar(author_id, _json(), parcial=True))


@bp.delete("/authors/<int:author_id>")
@solo_admin
def eliminar(author_id):
    forzar = request.args.get("force", "").lower() in ("true", "1")
    return jsonify(authors_service.eliminar(author_id, forzar))


@bp.post("/authors/<int:author_id>/books")
@solo_admin
def relacionar(author_id):
    return jsonify(authors_service.relacionar(author_id, _json())), 201


@bp.delete("/authors/<int:author_id>/books/<isbn>")
@solo_admin
def quitar_relacion(author_id, isbn):
    return jsonify(authors_service.quitar_relacion(author_id, isbn))
