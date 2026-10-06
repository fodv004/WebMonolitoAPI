"""
api/auth_jwt.py
Decorador @jwt_requerido para las rutas REST de escritura (POST, PUT,
PATCH y DELETE de /books). La validacion vive en el modulo compartido
common/auth.py: JWT HS256 del microservicio de login + rol admin.

  Sin "Authorization: Bearer <token>", token invalido, expirado,
  sin claims o revocado (jwt:revoked:<jti>)                  -> 401
  Redis caido (no se puede comprobar la revocacion)          -> 503
  Token valido pero el usuario no es admin (role_id != 1)    -> 403

Las rutas GET siguen siendo publicas: no usan este decorador.
"""
from common.auth import ADMIN_ROLE_ID, require_role

jwt_requerido = require_role(ADMIN_ROLE_ID)
