"""
services/users_service.py
Reglas de negocio del microservicio users (sin Flask).

  * Un usuario solo ve y edita su propia cuenta; el admin, todas.
  * Solo el admin cambia `activo` y `role_id`.
  * El ultimo administrador activo no puede perder el rol ni desactivarse.
  * Mientras la base conserve la regla del monolito "un solo administrador"
    (indice un_solo_admin), nombrar un segundo admin responde 409 UN_SOLO_ADMIN.
  * Al cambiar la contraseña, desactivar o cambiar el rol se cierran las
    sesiones del usuario en Redis ANTES del COMMIT: si Redis falla, la
    excepcion deshace la transaccion y la respuesta es 503.
  * password_hash nunca sale de aqui.
"""
from math import ceil

from common import session_store
from common.auth import ADMIN_ROLE_ID, CLIENTE_ROLE_ID, ROLES
from common.errors import ApiError
from db import repository
from services import login_client, passwords, validators

CONFIRMADO, PENDIENTE = "confirmado", "pendiente"

_CAMPOS_PERFIL = ("nombre", "apellido_paterno", "apellido_materno")
_CAMPOS_ADMIN = ("role_id", "activo")
# Campos que tienen su propio endpoint (con sus propias reglas).
_CAMPOS_CON_ENDPOINT = {
    "email": "PATCH /users/{id}/email", "correo": "PATCH /users/{id}/email",
    "password": "PATCH /users/{id}/password", "password_nueva": "PATCH /users/{id}/password",
}


class Actor:
    """Quien hace la peticion, segun su JWT."""

    def __init__(self, payload):
        self.user_id = payload["user_id"]
        self.role_id = payload["role_id"]

    @property
    def es_admin(self):
        return self.role_id == ADMIN_ROLE_ID


# ------------------------------------------------------------------ salida
def _fecha(valor):
    return valor.isoformat(timespec="seconds") if valor is not None else None


def publico(fila):
    """Representacion de un usuario en la API (sin password_hash)."""
    return {
        "id_usuario": fila["id_usuario"],
        "nombre": fila["nombre"],
        "apellido_paterno": fila["apellido_paterno"],
        "apellido_materno": fila["apellido_materno"],
        "email": fila["correo"],
        "role_id": fila["role_id"],
        "role": ROLES.get(fila["role_id"], "cliente"),
        "activo": fila["activo"],
        "email_verificado": fila["estado_cuenta"] == CONFIRMADO,
        "created_at": _fecha(fila["fecha_registro"]),
        "updated_at": _fecha(fila["updated_at"]),
    }


# ------------------------------------------------------------------ errores
def _no_encontrado():
    return ApiError(404, "USUARIO_NO_ENCONTRADO", "No existe el usuario indicado.")


def _prohibido(mensaje="No tienes permisos para esta operacion."):
    return ApiError(403, "ROL_INSUFICIENTE", mensaje)


def _exigir_propio_o_admin(actor, user_id):
    # Antes de consultar la base: un cliente no debe poder averiguar que ids existen.
    if not actor.es_admin and actor.user_id != user_id:
        raise _prohibido("Solo puedes consultar y modificar tu propia cuenta.")


def _un_solo_admin():
    return ApiError(409, "UN_SOLO_ADMIN",
                    "La base de datos solo admite un administrador (regla un_solo_admin del monolito). "
                    "Para permitir varios, ejecuta apps/services/users/sql/opcional_permitir_varios_admins.sql.")


def _cuerpo(datos):
    if not isinstance(datos, dict):
        raise validators.invalido("Envia el cuerpo como un objeto JSON (Content-Type: application/json).")
    return datos


def _role_id_valido(repo, valor):
    role_id = validators.entero("role_id", valor)
    if repo.role(role_id) is None:
        raise validators.invalido(f"No existe el rol {role_id}. Consulta GET /roles.")
    return role_id


# ------------------------------------------------------------------ consultas
def listar(args):
    filtros = validators.filtros_de_lista(args)
    page, per_page = filtros.pop("page"), filtros.pop("per_page")
    with repository.unit_of_work() as repo:
        filas, total = repo.list(limit=per_page, offset=(page - 1) * per_page, **filtros)
    return {
        "items": [publico(fila) for fila in filas],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": ceil(total / per_page) if total else 0,
    }


def obtener(actor, user_id):
    _exigir_propio_o_admin(actor, user_id)
    with repository.unit_of_work() as repo:
        fila = repo.get(user_id)
    if fila is None:
        raise _no_encontrado()
    return publico(fila)


def roles():
    with repository.unit_of_work() as repo:
        return repo.roles()


def interno(user_id):
    """Datos minimos para otros microservicios (pedidos, pagos)."""
    with repository.unit_of_work() as repo:
        fila = repo.get(user_id)
    if fila is None:
        raise _no_encontrado()
    return {
        "id_usuario": fila["id_usuario"],
        "nombre": " ".join(p for p in (fila["nombre"], fila["apellido_paterno"], fila["apellido_materno"]) if p),
        "email": fila["correo"],
        "role_id": fila["role_id"],
        "activo": fila["activo"],
        "email_verificado": fila["estado_cuenta"] == CONFIRMADO,
    }


# ------------------------------------------------------------------ alta
def crear(datos):
    """Alta hecha por un administrador: la cuenta nace confirmada (puede iniciar sesion de inmediato)."""
    datos = _cuerpo(datos)
    limpio = {campo: validators.nombre(campo, datos.get(campo)) for campo in _CAMPOS_PERFIL}
    correo = validators.email(datos.get("email", datos.get("correo")))
    error = passwords.error_de_password(datos.get("password"))
    if error:
        raise validators.invalido(error)
    activo = validators.booleano("activo", datos.get("activo", True))

    with repository.unit_of_work() as repo:
        role_id = _role_id_valido(repo, datos.get("role_id", CLIENTE_ROLE_ID))
        try:
            fila = repo.insert(correo=correo, password_hash=passwords.hash_password(datos["password"]),
                               role_id=role_id, activo=activo, estado_cuenta=CONFIRMADO, **limpio)
        except repository.EmailDuplicado:
            raise ApiError(409, "EMAIL_DUPLICADO", "Ya existe una cuenta registrada con ese email.")
        except repository.UnSoloAdmin:
            raise _un_solo_admin()
    return publico(fila)


# ------------------------------------------------------------------ cambios
def _aplicar(repo, usuario, cambios):
    """Aplica `cambios` (columnas) a `usuario` respetando la regla del ultimo admin y
    cerrando sus sesiones cuando cambia el rol o se desactiva. Devuelve la fila nueva."""
    cambios = {columna: valor for columna, valor in cambios.items() if usuario.get(columna) != valor}
    if not cambios:
        return usuario

    pierde_rol = "role_id" in cambios and usuario["role_id"] == ADMIN_ROLE_ID
    se_desactiva = cambios.get("activo") is False
    if usuario["role_id"] == ADMIN_ROLE_ID and usuario["activo"] and (pierde_rol or se_desactiva):
        if repo.otros_admins_activos(usuario["id_usuario"]) == 0:
            raise ApiError(409, "ULTIMO_ADMIN",
                           "Es el ultimo administrador activo: no puede cambiar de rol ni desactivarse.")

    try:
        fila = repo.update(usuario["id_usuario"], **cambios)
    except repository.UnSoloAdmin:
        raise _un_solo_admin()
    if "role_id" in cambios or se_desactiva or "password_hash" in cambios:
        # Si Redis falla aqui, la excepcion sale del unit_of_work y no hay COMMIT.
        session_store.revoke_user_sessions(usuario["id_usuario"])
    return fila


def _usuario_bloqueado(repo, user_id):
    usuario = repo.get(user_id, bloquear=True)
    if usuario is None:
        raise _no_encontrado()
    return usuario


def actualizar(actor, user_id, datos, parcial):
    """PUT (parcial=False: nombre obligatorio, apellidos se reemplazan) y PATCH (solo lo enviado)."""
    _exigir_propio_o_admin(actor, user_id)
    datos = _cuerpo(datos)

    for campo, endpoint in _CAMPOS_CON_ENDPOINT.items():
        if campo in datos:
            raise validators.invalido(f"'{campo}' no se cambia aqui: usa {endpoint}.")
    if not actor.es_admin and any(campo in datos for campo in _CAMPOS_ADMIN):
        raise _prohibido("Solo un administrador puede cambiar 'role_id' y 'activo'.")

    cambios = {}
    for campo in _CAMPOS_PERFIL:
        if campo in datos or not parcial:
            cambios[campo] = validators.nombre(campo, datos.get(campo))
    if "activo" in datos:
        cambios["activo"] = validators.booleano("activo", datos["activo"])
    if parcial and not cambios and "role_id" not in datos:
        raise validators.invalido("No enviaste ningun campo para modificar.")

    with repository.unit_of_work() as repo:
        if "role_id" in datos:
            cambios["role_id"] = _role_id_valido(repo, datos["role_id"])
        return publico(_aplicar(repo, _usuario_bloqueado(repo, user_id), cambios))


def desactivar(user_id):
    """Baja logica (activo = false). Idempotente."""
    with repository.unit_of_work() as repo:
        return publico(_aplicar(repo, _usuario_bloqueado(repo, user_id), {"activo": False}))


def cambiar_rol(user_id, datos):
    datos = _cuerpo(datos)
    if "role_id" not in datos:
        raise validators.invalido("'role_id' es obligatorio.")
    with repository.unit_of_work() as repo:
        role_id = _role_id_valido(repo, datos["role_id"])
        return publico(_aplicar(repo, _usuario_bloqueado(repo, user_id), {"role_id": role_id}))


def cambiar_password(actor, user_id, datos):
    """El usuario envia su contraseña actual; el admin restablece la de OTRO usuario sin ella."""
    _exigir_propio_o_admin(actor, user_id)
    datos = _cuerpo(datos)
    error = passwords.error_de_password(datos.get("password_nueva"), "La contraseña nueva")
    if error:
        raise validators.invalido(error)

    with repository.unit_of_work() as repo:
        usuario = _usuario_bloqueado(repo, user_id)
        if actor.user_id == user_id:
            actual = datos.get("password_actual")
            if not isinstance(actual, str) or not actual:
                raise validators.invalido("'password_actual' es obligatorio para cambiar tu propia contraseña.")
            if not passwords.verify_password(actual, repo.password_hash(user_id)):
                # 400 y no 401: el token es valido; lo incorrecto es el dato enviado.
                raise ApiError(400, "PASSWORD_ACTUAL_INCORRECTA", "La contraseña actual no es correcta.")
        # Siempre se guarda y se cierran las sesiones, aunque la nueva sea igual a la anterior.
        repo.update(user_id, password_hash=passwords.hash_password(datos["password_nueva"]))
        session_store.revoke_user_sessions(user_id)
        return publico(repo.get(user_id) or usuario)


def cambiar_email(actor, user_id, datos):
    """Cambia el correo, deja la cuenta pendiente de verificar y pide a login el correo de confirmacion."""
    _exigir_propio_o_admin(actor, user_id)
    datos = _cuerpo(datos)
    correo = validators.email(datos.get("email", datos.get("correo")))

    duplicado = ApiError(409, "EMAIL_DUPLICADO", "Ya existe una cuenta registrada con ese email.")
    with repository.unit_of_work() as repo:
        usuario = _usuario_bloqueado(repo, user_id)
        if usuario["correo"] == correo:
            raise validators.invalido("El email nuevo es igual al actual.")
        if repo.get_by_email(correo) is not None:
            raise duplicado
        # Orden obligado: login inserta su token (FK a esta fila) ANTES de que aqui se
        # actualice `correo`. Al reves, el UPDATE de una columna unica bloquearia ese
        # INSERT hasta el COMMIT y la llamada agotaria su timeout.
        # Si el correo no sale, la excepcion deshace todo y la cuenta no queda bloqueada.
        login_client.enviar_confirmacion(user_id, correo, usuario["nombre"])
        try:
            return publico(repo.update(user_id, correo=correo, estado_cuenta=PENDIENTE))
        except repository.EmailDuplicado:      # otra peticion lo tomo entre la comprobacion y el UPDATE
            raise duplicado
