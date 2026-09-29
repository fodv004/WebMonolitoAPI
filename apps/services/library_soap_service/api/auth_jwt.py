"""
api/auth_jwt.py
Decorador @jwt_requerido para las rutas REST de escritura (POST, PUT,
PATCH y DELETE de /books). Valida el JWT HS256 emitido por el
microservicio de login (POST /login) con el MISMO JWT_SECRET.

  Sin header Authorization o sin el formato "Bearer <token>" -> 401
  Firma invalida, token mal formado o expirado               -> 403

Las rutas GET siguen siendo publicas: no usan este decorador.
"""
import os
from functools import wraps

import jwt
from dotenv import load_dotenv
from flask import g, jsonify, request

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
JWT_ALGORITHM = "HS256"

if not JWT_SECRET:
    raise SystemExit(
        "ERROR: la variable de entorno JWT_SECRET no esta definida. "
        "El microservicio de libros no puede validar tokens sin ella. "
        "Definela en el .env o en la terminal (con el MISMO valor que en el servicio de login) "
        "y vuelve a arrancar."
    )


def _no_autorizado(mensaje):
    respuesta = jsonify({"error": "NO_AUTORIZADO", "mensaje": mensaje})
    respuesta.status_code = 401
    respuesta.headers["WWW-Authenticate"] = 'Bearer realm="books"'
    return respuesta


def _prohibido(codigo, mensaje):
    return jsonify({"error": codigo, "mensaje": mensaje}), 403


def jwt_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        encabezado = request.headers.get("Authorization", "").strip()
        if not encabezado:
            return _no_autorizado("Falta el header Authorization. Envia 'Authorization: Bearer <token>'.")

        partes = encabezado.split()
        if len(partes) != 2 or partes[0].lower() != "bearer":
            return _no_autorizado("Formato de Authorization invalido. Se espera 'Bearer <token>'.")

        try:
            payload = jwt.decode(
                partes[1],
                JWT_SECRET,
                algorithms=[JWT_ALGORITHM],
                options={"require": ["exp", "iat"]},
            )
        except jwt.ExpiredSignatureError:
            return _prohibido("TOKEN_EXPIRADO", "El token expiro. Inicia sesion de nuevo.")
        except jwt.InvalidSignatureError:
            return _prohibido("TOKEN_INVALIDO", "La firma del token no es valida.")
        except jwt.InvalidTokenError:
            return _prohibido("TOKEN_INVALIDO", "El token no es valido.")

        g.jwt_payload = payload
        return vista(*args, **kwargs)

    return envoltura
