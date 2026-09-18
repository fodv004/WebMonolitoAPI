"""
routes.py
Endpoints del microservicio de autenticacion:

  POST /register   registrar usuario (envia correo de confirmacion por Mailpit)
  POST /login      autenticar y abrir sesion Flask
  POST /logout     cerrar sesion
  GET  /session    consultar la sesion actual
  GET  /health     estado del servicio y de PostgreSQL
  GET  /confirm    confirmar la cuenta con el token del correo
  GET  /confirmed  pagina que confirma visualmente que la cuenta quedo activada

Los docstrings (YAML tras '---') alimentan Swagger UI en /apidocs/.
"""
import logging

import psycopg2
from psycopg2 import errors as pg_errors
from flask import Blueprint, redirect, render_template, request, session, url_for

from config import Config
from db import get_conn
from mailer import MailError, send_confirmation_email
from responses import ApiError, resolve_format, success
from security import burn_password_check, hash_password, new_token, token_digest, verify_password
from validators import validar_credenciales, validar_registro

log = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)

USER_COLS = "id_usuario, nombre, apellido_paterno, apellido_materno, correo, es_admin, activo, estado_cuenta"


def _user_data(row):
    return {
        "id_usuario": row[0],
        "nombre": row[1],
        "apellido_paterno": row[2],
        "apellido_materno": row[3],
        "email": row[4],
        "es_admin": row[5],
        "estado_cuenta": row[7],
    }


def _read_payload():
    """Cuerpo de la peticion: JSON o formulario (application/x-www-form-urlencoded)."""
    if request.is_json:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ApiError(400, "CUERPO_INVALIDO", "El cuerpo JSON no es un objeto valido.")
        return data
    if request.form:
        return request.form.to_dict()
    raise ApiError(
        400, "CUERPO_INVALIDO",
        "Envia el cuerpo como JSON (Content-Type: application/json) o como formulario.",
    )


# ============================================================
# POST /register
# ============================================================
@bp.post("/register")
def register():
    """Registrar un nuevo usuario
    Valida los datos, crea la cuenta en estado `pendiente` (solo se guarda el
    hash bcrypt de la contraseña, nunca el texto plano) y envía por SMTP a
    Mailpit un correo con el link de confirmación `/confirm?token=...`.
    El email se normaliza a minúsculas y debe ser único.
    ---
    tags:
      - Autenticación
    consumes:
      - application/json
      - application/x-www-form-urlencoded
    produces:
      - application/xml
      - application/json
    parameters:
      - $ref: '#/parameters/formatParam'
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/RegistroRequest'
    responses:
      201:
        description: Usuario creado en estado `pendiente`; correo de confirmación enviado.
        schema:
          $ref: '#/definitions/Respuesta'
        examples:
          application/json:
            status: ok
            code: USUARIO_REGISTRADO
            message: Usuario registrado. Revisa tu correo para confirmar la cuenta.
            data:
              id_usuario: 31
              nombre: Ana
              apellido_paterno: Pérez
              apellido_materno: Ruiz
              email: ana@correo.com
              estado_cuenta: pendiente
              correo_confirmacion_enviado: true
          application/xml: |
            <?xml version="1.0" encoding="UTF-8"?>
            <response>
              <status>ok</status>
              <code>USUARIO_REGISTRADO</code>
              <message>Usuario registrado. Revisa tu correo para confirmar la cuenta.</message>
              <data>
                <id_usuario>31</id_usuario>
                <nombre>Ana</nombre>
                <apellido_paterno>Pérez</apellido_paterno>
                <apellido_materno>Ruiz</apellido_materno>
                <email>ana@correo.com</email>
                <estado_cuenta>pendiente</estado_cuenta>
                <correo_confirmacion_enviado>true</correo_confirmacion_enviado>
              </data>
            </response>
      400:
        description: Datos inválidos (campo faltante, email mal formado, password corto, `format` inválido).
        schema:
          $ref: '#/definitions/Respuesta'
      409:
        description: El email ya está registrado.
        schema:
          $ref: '#/definitions/Respuesta'
      503:
        description: No se pudo enviar el correo (Mailpit caído). No se crea la cuenta; se puede reintentar.
        schema:
          $ref: '#/definitions/Respuesta'
    """
    formato = resolve_format()
    limpio, errores = validar_registro(_read_payload())
    if errores:
        raise ApiError(400, "VALIDACION", "Los datos enviados no son validos.", errors=errores)

    password_hash = hash_password(limpio["password"])
    token = new_token()

    try:
        # Usuario + token + correo en una sola transaccion: si el correo no sale,
        # todo se revierte y el usuario puede reintentar con el mismo email.
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO usuarios (nombre, apellido_paterno, apellido_materno, correo,
                                          password_hash, es_admin, estado_cuenta)
                    VALUES (%s, %s, %s, %s, %s, FALSE, 'pendiente')
                    RETURNING id_usuario
                    """,
                    (limpio["nombre"], limpio["apellido_paterno"], limpio["apellido_materno"],
                     limpio["email"], password_hash),
                )
                id_usuario = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO tokens_confirmacion (id_usuario, token_hash, expira_en)
                    VALUES (%s, %s, NOW() + %s * INTERVAL '1 hour')
                    """,
                    (id_usuario, token_digest(token), Config.CONFIRM_TOKEN_HOURS),
                )
            send_confirmation_email(limpio["email"], limpio["nombre"], token)
    except pg_errors.UniqueViolation:
        raise ApiError(409, "EMAIL_DUPLICADO", "Ya existe una cuenta registrada con ese email.")
    except MailError:
        log.exception("No se pudo enviar el correo de confirmacion")
        raise ApiError(503, "CORREO_NO_ENVIADO",
                       "No se pudo enviar el correo de confirmacion. Intenta de nuevo en unos minutos.")

    return success(formato, 201, "USUARIO_REGISTRADO",
                   "Usuario registrado. Revisa tu correo para confirmar la cuenta.", {
                       "id_usuario": id_usuario,
                       "nombre": limpio["nombre"],
                       "apellido_paterno": limpio["apellido_paterno"],
                       "apellido_materno": limpio["apellido_materno"],
                       "email": limpio["email"],
                       "estado_cuenta": "pendiente",
                       "correo_confirmacion_enviado": True,
                   })


# ============================================================
# GET /confirm  y  GET /confirmed
# ============================================================
_CONFIRM_RESULTADOS = {
    # estado -> (http, codigo, mensaje)
    "ok": (200, "CUENTA_CONFIRMADA", "Tu cuenta quedó activada."),
    "already": (200, "CUENTA_YA_CONFIRMADA", "Tu cuenta ya estaba activada."),
    "expired": (410, "TOKEN_EXPIRADO", "El enlace de confirmación expiró."),
    "invalid": (400, "TOKEN_INVALIDO", "El enlace de confirmación no es válido."),
}


def _confirmar(token):
    """Valida el token y activa la cuenta. Devuelve 'ok' | 'already' | 'expired' | 'invalid'."""
    if not token or len(token) > 200:
        return "invalid"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id_token, t.id_usuario, t.expira_en < NOW(), t.usado_en IS NOT NULL, u.estado_cuenta
                FROM tokens_confirmacion t
                JOIN usuarios u ON u.id_usuario = t.id_usuario
                WHERE t.token_hash = %s
                FOR UPDATE OF t
                """,
                (token_digest(token),),
            )
            fila = cur.fetchone()
            if fila is None:
                return "invalid"
            id_token, id_usuario, expirado, usado, estado = fila
            if usado:
                # Segundo clic (o un escáner de enlaces que abrió el correo antes): no es un error.
                return "already" if estado == "confirmado" else "invalid"
            if expirado:
                return "expired"
            cur.execute("UPDATE usuarios SET estado_cuenta = 'confirmado' WHERE id_usuario = %s", (id_usuario,))
            cur.execute("UPDATE tokens_confirmacion SET usado_en = NOW() WHERE id_token = %s", (id_token,))
            return "ok"


@bp.get("/confirm")
def confirm():
    """Confirmar la cuenta con el token del correo
    Valida el token, cambia el estado del usuario de `pendiente` a `confirmado`
    y **redirige** a la página `/confirmed` que muestra el resultado. El token es
    de un solo uso y vence según `CONFIRM_TOKEN_HOURS`.
    Si se envía `format` de forma explícita (xml o json) no hay redirección:
    se responde el resultado en ese formato (útil para pruebas).
    ---
    tags:
      - Autenticación
    produces:
      - application/xml
      - application/json
      - text/html
    parameters:
      - name: token
        in: query
        type: string
        required: true
        description: Token recibido en el correo de confirmación.
      - $ref: '#/parameters/formatParam'
    responses:
      302:
        description: Sin `format`. Redirige a `/confirmed?status=ok|already|expired|invalid`.
      200:
        description: Con `format` explícito. Cuenta confirmada (o ya lo estaba).
        schema:
          $ref: '#/definitions/Respuesta'
        examples:
          application/json:
            status: ok
            code: CUENTA_CONFIRMADA
            message: Tu cuenta quedó activada.
          application/xml: |
            <?xml version="1.0" encoding="UTF-8"?>
            <response>
              <status>ok</status>
              <code>CUENTA_CONFIRMADA</code>
              <message>Tu cuenta quedó activada.</message>
            </response>
      400:
        description: Con `format` explícito. Token inválido.
        schema:
          $ref: '#/definitions/Respuesta'
      410:
        description: Con `format` explícito. Token expirado.
        schema:
          $ref: '#/definitions/Respuesta'
    """
    resultado = _confirmar(request.args.get("token", ""))
    if "format" not in request.args:
        return redirect(url_for("auth.confirmed", status=resultado))

    formato = resolve_format()
    http_status, codigo, mensaje = _CONFIRM_RESULTADOS[resultado]
    if http_status >= 400:
        raise ApiError(http_status, codigo, mensaje)
    return success(formato, http_status, codigo, mensaje)


@bp.get("/confirmed")
def confirmed():
    estado = request.args.get("status", "invalid")
    if estado not in _CONFIRM_RESULTADOS:
        estado = "invalid"
    return render_template("confirmed.html", estado=estado), (200 if estado in ("ok", "already") else 400)


# ============================================================
# POST /login
# ============================================================
@bp.post("/login")
def login():
    """Autenticar al usuario e iniciar sesión
    Verifica email y contraseña contra PostgreSQL (hash bcrypt). Si son
    correctos y la cuenta está `confirmado`, crea la sesión de Flask
    (cookie firmada `auth_session`) que identifica al usuario en las
    peticiones siguientes (`/session`, `/logout`).
    ---
    tags:
      - Autenticación
    consumes:
      - application/json
      - application/x-www-form-urlencoded
    produces:
      - application/xml
      - application/json
    parameters:
      - $ref: '#/parameters/formatParam'
      - name: body
        in: body
        required: true
        schema:
          $ref: '#/definitions/LoginRequest'
    responses:
      200:
        description: Sesión iniciada (se entrega la cookie `auth_session`).
        schema:
          $ref: '#/definitions/Respuesta'
        examples:
          application/json:
            status: ok
            code: LOGIN_EXITOSO
            message: Sesión iniciada.
            data:
              authenticated: true
              user:
                id_usuario: 31
                nombre: Ana
                apellido_paterno: Pérez
                apellido_materno: Ruiz
                email: ana@correo.com
                es_admin: false
                estado_cuenta: confirmado
          application/xml: |
            <?xml version="1.0" encoding="UTF-8"?>
            <response>
              <status>ok</status>
              <code>LOGIN_EXITOSO</code>
              <message>Sesión iniciada.</message>
              <data>
                <authenticated>true</authenticated>
                <user>
                  <id_usuario>31</id_usuario>
                  <nombre>Ana</nombre>
                  <apellido_paterno>Pérez</apellido_paterno>
                  <apellido_materno>Ruiz</apellido_materno>
                  <email>ana@correo.com</email>
                  <es_admin>false</es_admin>
                  <estado_cuenta>confirmado</estado_cuenta>
                </user>
              </data>
            </response>
      400:
        description: Falta email o password (o `format` inválido).
        schema:
          $ref: '#/definitions/Respuesta'
      401:
        description: Credenciales incorrectas (mismo mensaje para email desconocido y password incorrecto).
        schema:
          $ref: '#/definitions/Respuesta'
      403:
        description: Credenciales correctas pero la cuenta está pendiente de confirmar o inactiva.
        schema:
          $ref: '#/definitions/Respuesta'
    """
    formato = resolve_format()
    cred, errores = validar_credenciales(_read_payload())
    if errores:
        raise ApiError(400, "VALIDACION", "Los datos enviados no son validos.", errors=errores)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {USER_COLS}, password_hash FROM usuarios WHERE correo = %s", (cred["email"],))
            fila = cur.fetchone()

    if fila is None:
        burn_password_check(cred["password"])
        raise ApiError(401, "CREDENCIALES_INVALIDAS", "Email o contraseña incorrectos.")
    if not verify_password(cred["password"], fila[-1]):
        raise ApiError(401, "CREDENCIALES_INVALIDAS", "Email o contraseña incorrectos.")

    # La contraseña es correcta: ahora sí se informa el estado de la cuenta.
    if not fila[6]:
        raise ApiError(403, "CUENTA_INACTIVA", "La cuenta está desactivada. Contacta al administrador.")
    if fila[7] != "confirmado":
        raise ApiError(403, "CUENTA_NO_CONFIRMADA",
                       "La cuenta aun no esta confirmada. Abre el enlace que se envio a tu correo.")

    session.clear()                      # sesion nueva: evita fijacion de sesion
    session["id_usuario"] = fila[0]
    session.permanent = True
    return success(formato, 200, "LOGIN_EXITOSO", "Sesión iniciada.",
                   {"authenticated": True, "user": _user_data(fila)})


# ============================================================
# POST /logout
# ============================================================
@bp.post("/logout")
def logout():
    """Cerrar la sesión
    Destruye la sesión de Flask asociada a la cookie. Es idempotente: si no
    había sesión también responde 200.
    ---
    tags:
      - Autenticación
    produces:
      - application/xml
      - application/json
    parameters:
      - $ref: '#/parameters/formatParam'
    responses:
      200:
        description: Sesión cerrada (o no existía).
        schema:
          $ref: '#/definitions/Respuesta'
        examples:
          application/json:
            status: ok
            code: LOGOUT_EXITOSO
            message: Sesión cerrada.
            data:
              authenticated: false
          application/xml: |
            <?xml version="1.0" encoding="UTF-8"?>
            <response>
              <status>ok</status>
              <code>LOGOUT_EXITOSO</code>
              <message>Sesión cerrada.</message>
              <data><authenticated>false</authenticated></data>
            </response>
    """
    formato = resolve_format()
    habia_sesion = "id_usuario" in session
    session.clear()
    return success(formato, 200, "LOGOUT_EXITOSO",
                   "Sesión cerrada." if habia_sesion else "No había una sesión activa.",
                   {"authenticated": False})


# ============================================================
# GET /session
# ============================================================
@bp.get("/session")
def current_session():
    """Consultar si existe una sesión autenticada
    Lee la sesión de Flask (cookie `auth_session`) y la revalida contra
    PostgreSQL (la cuenta debe seguir activa y confirmada). Responde 200 en
    ambos casos; el campo `authenticated` indica si hay sesión.
    ---
    tags:
      - Autenticación
    produces:
      - application/xml
      - application/json
    parameters:
      - $ref: '#/parameters/formatParam'
    responses:
      200:
        description: Estado de la sesión.
        schema:
          $ref: '#/definitions/Respuesta'
        examples:
          application/json:
            status: ok
            code: SESION_ACTIVA
            message: Hay una sesión autenticada.
            data:
              authenticated: true
              user:
                id_usuario: 31
                nombre: Ana
                apellido_paterno: Pérez
                apellido_materno: Ruiz
                email: ana@correo.com
                es_admin: false
                estado_cuenta: confirmado
          application/xml: |
            <?xml version="1.0" encoding="UTF-8"?>
            <response>
              <status>ok</status>
              <code>SESION_ACTIVA</code>
              <message>Hay una sesión autenticada.</message>
              <data>
                <authenticated>true</authenticated>
                <user>
                  <id_usuario>31</id_usuario>
                  <nombre>Ana</nombre>
                  <apellido_paterno>Pérez</apellido_paterno>
                  <apellido_materno>Ruiz</apellido_materno>
                  <email>ana@correo.com</email>
                  <es_admin>false</es_admin>
                  <estado_cuenta>confirmado</estado_cuenta>
                </user>
              </data>
            </response>
    """
    formato = resolve_format()
    id_usuario = session.get("id_usuario")
    fila = None
    if id_usuario is not None:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {USER_COLS} FROM usuarios WHERE id_usuario = %s AND activo AND estado_cuenta = 'confirmado'",
                    (id_usuario,),
                )
                fila = cur.fetchone()
        if fila is None:
            session.clear()            # la cuenta ya no existe / se desactivo

    if fila is None:
        return success(formato, 200, "SIN_SESION", "No hay una sesión autenticada.", {"authenticated": False})
    return success(formato, 200, "SESION_ACTIVA", "Hay una sesión autenticada.",
                   {"authenticated": True, "user": _user_data(fila)})


# ============================================================
# GET /health
# ============================================================
@bp.get("/health")
def health():
    """Verificar el estado del microservicio y de PostgreSQL
    Ejecuta una consulta real (`SELECT 1`) contra la base `library`.
    Responde 200 si todo funciona y 503 si PostgreSQL no responde.
    ---
    tags:
      - Salud
    produces:
      - application/xml
      - application/json
    parameters:
      - $ref: '#/parameters/formatParam'
    responses:
      200:
        description: Servicio y PostgreSQL operativos.
        schema:
          $ref: '#/definitions/Respuesta'
        examples:
          application/json:
            status: ok
            code: SERVICIO_SALUDABLE
            message: El servicio y PostgreSQL están operativos.
            data:
              service: auth
              database:
                status: up
                name: library
                version: "16.4"
          application/xml: |
            <?xml version="1.0" encoding="UTF-8"?>
            <response>
              <status>ok</status>
              <code>SERVICIO_SALUDABLE</code>
              <message>El servicio y PostgreSQL están operativos.</message>
              <data>
                <service>auth</service>
                <database><status>up</status><name>library</name><version>16.4</version></database>
              </data>
            </response>
      503:
        description: PostgreSQL no responde.
        schema:
          $ref: '#/definitions/Respuesta'
    """
    formato = resolve_format()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.execute("SHOW server_version")
                version = cur.fetchone()[0].split(" ")[0]
    except psycopg2.Error:
        log.exception("Health check: PostgreSQL no responde")
        raise ApiError(503, "BASE_DE_DATOS_NO_DISPONIBLE", "PostgreSQL no responde.")

    return success(formato, 200, "SERVICIO_SALUDABLE", "El servicio y PostgreSQL están operativos.", {
        "service": "auth",
        "database": {"status": "up", "name": Config.DB_NAME, "version": version},
    })
