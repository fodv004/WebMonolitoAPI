"""
db/repository.py
Acceso a datos del microservicio users (psycopg 3, consultas parametrizadas).
Tablas: `usuarios` (la misma de login y del monolito) y `roles`.

Nombres reales de las columnas -> nombre en la API:
  correo -> email · fecha_registro -> created_at ·
  estado_cuenta ('confirmado'/'pendiente') -> email_verificado (true/false)

password_hash NUNCA sale en las filas de usuario: solo se lee con
password_hash() para verificar la contraseña actual.
"""
from contextlib import contextmanager

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from common.auth import ADMIN_ROLE_ID
from common.db import get_conn

COLUMNAS = ("id_usuario, nombre, apellido_paterno, apellido_materno, correo, role_id, activo, "
            "estado_cuenta, fecha_registro, updated_at")
_EDITABLES = {"nombre", "apellido_paterno", "apellido_materno", "correo", "password_hash",
              "role_id", "activo", "estado_cuenta"}


class EmailDuplicado(Exception):
    pass


class UnSoloAdmin(Exception):
    """El esquema del monolito admite un unico administrador (indice unico `un_solo_admin`
    sobre es_admin). Se respeta mientras exista; ver sql/opcional_permitir_varios_admins.sql."""


def _conflicto(error):
    """Excepcion de dominio que corresponde a una violacion de unicidad en `usuarios`."""
    return UnSoloAdmin() if error.diag.constraint_name == "un_solo_admin" else EmailDuplicado()


def _like(texto):
    """Patron ILIKE que busca `texto` literal (escapa % y _)."""
    return "%" + texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class UserRepository:
    def __init__(self, conn):
        self.conn = conn

    def _cur(self):
        return self.conn.cursor(row_factory=dict_row)

    # ------------------------------------------------------------ lectura
    def get(self, user_id, bloquear=False):
        # FOR NO KEY UPDATE (y no FOR UPDATE): bloquea la fila contra otros cambios pero
        # deja que login inserte su token de confirmacion (FK a esta fila) mientras tanto.
        sql = f"SELECT {COLUMNAS} FROM usuarios WHERE id_usuario = %s" + (" FOR NO KEY UPDATE" if bloquear else "")
        return self._cur().execute(sql, (user_id,)).fetchone()

    def get_by_email(self, correo):
        return self._cur().execute(f"SELECT {COLUMNAS} FROM usuarios WHERE correo = %s", (correo,)).fetchone()

    def password_hash(self, user_id):
        fila = self.conn.execute("SELECT password_hash FROM usuarios WHERE id_usuario = %s", (user_id,)).fetchone()
        return fila[0] if fila else None

    def list(self, q=None, role_id=None, activo=None, limit=20, offset=0):
        """(filas, total) con los filtros aplicados, ordenadas por id."""
        condiciones, valores = [], []
        if q:
            condiciones.append("(nombre ILIKE %s OR apellido_paterno ILIKE %s OR apellido_materno ILIKE %s "
                               "OR correo ILIKE %s)")
            valores += [_like(q)] * 4
        if role_id is not None:
            condiciones.append("role_id = %s")
            valores.append(role_id)
        if activo is not None:
            condiciones.append("activo = %s")
            valores.append(activo)
        where = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""

        total = self.conn.execute(f"SELECT COUNT(*) FROM usuarios{where}", valores).fetchone()[0]
        filas = self._cur().execute(
            f"SELECT {COLUMNAS} FROM usuarios{where} ORDER BY id_usuario LIMIT %s OFFSET %s",
            valores + [limit, offset],
        ).fetchall()
        return filas, total

    def otros_admins_activos(self, user_id):
        """Cuantos administradores activos hay ademas de `user_id` (bloquea esas filas
        para que dos peticiones simultaneas no dejen el sistema sin administradores)."""
        filas = self.conn.execute(
            "SELECT id_usuario FROM usuarios WHERE role_id = %s AND activo AND id_usuario <> %s FOR NO KEY UPDATE",
            (ADMIN_ROLE_ID, user_id),
        ).fetchall()
        return len(filas)

    # ------------------------------------------------------------ roles
    def roles(self):
        return self._cur().execute("SELECT role_id, nombre, descripcion FROM roles ORDER BY role_id").fetchall()

    def role(self, role_id):
        return self._cur().execute(
            "SELECT role_id, nombre, descripcion FROM roles WHERE role_id = %s", (role_id,)).fetchone()

    # ------------------------------------------------------------ escritura
    def insert(self, nombre, apellido_paterno, apellido_materno, correo, password_hash, role_id, activo,
               estado_cuenta):
        try:
            return self._cur().execute(
                f"""
                INSERT INTO usuarios (nombre, apellido_paterno, apellido_materno, correo, password_hash,
                                      es_admin, role_id, activo, estado_cuenta)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {COLUMNAS}
                """,
                (nombre, apellido_paterno, apellido_materno, correo, password_hash,
                 role_id == ADMIN_ROLE_ID, role_id, activo, estado_cuenta),
            ).fetchone()
        except pg_errors.UniqueViolation as e:
            raise _conflicto(e)

    def update(self, user_id, **campos):
        """Actualiza solo las columnas indicadas y devuelve la fila resultante.
        Al cambiar role_id tambien se actualiza es_admin (columna que usa el monolito)."""
        desconocidas = set(campos) - _EDITABLES
        if desconocidas:
            raise ValueError(f"Columnas no editables: {sorted(desconocidas)}")
        if "role_id" in campos:
            campos["es_admin"] = campos["role_id"] == ADMIN_ROLE_ID
        asignaciones = ", ".join(f"{columna} = %s" for columna in campos)
        try:
            return self._cur().execute(
                f"UPDATE usuarios SET {asignaciones}, updated_at = NOW() WHERE id_usuario = %s RETURNING {COLUMNAS}",
                list(campos.values()) + [user_id],
            ).fetchone()
        except pg_errors.UniqueViolation as e:
            raise _conflicto(e)


@contextmanager
def unit_of_work():
    """Una transaccion: COMMIT si el bloque termina bien, ROLLBACK si lanza.
    Las revocaciones en Redis se hacen DENTRO del bloque: si Redis falla, no hay COMMIT."""
    with get_conn() as conn:
        yield UserRepository(conn)
