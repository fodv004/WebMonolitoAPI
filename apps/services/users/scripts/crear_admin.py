"""
scripts/crear_admin.py
Deja lista la cuenta del administrador inicial. Se ejecuta UNA vez en la
VM, despues de las migraciones (sql/001_roles.sql y sql/002_users.sql):

    cd apps/services/users
    .venv/bin/python scripts/crear_admin.py

Lee del .env de users:
    ADMIN_EMAIL      (por ejemplo admin@libreria.com)
    ADMIN_PASSWORD   (solo se usa si hay que poner una contraseña)

Que hace con la cuenta ADMIN_EMAIL:
  * Le asigna role_id = 1 (y es_admin, la columna del monolito) y activo = true.
  * Si su password_hash sigue siendo un valor de ejemplo de los seeds del
    monolito ('hash_de_ejemplo' o 'CAMBIAR_POR_HASH_BCRYPT_REAL') lo reemplaza
    por el hash bcrypt de ADMIN_PASSWORD (mismo algoritmo que login).
    Si ya tiene un hash real NO lo toca.
  * Si la cuenta no existe, la crea ya confirmada con ADMIN_PASSWORD.

Es idempotente: ejecutarlo otra vez no cambia nada. Nunca imprime la
contraseña ni su hash.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]          # apps/services/users
load_dotenv(RAIZ / ".env")
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ.parent))                # apps/services (modulo `common`)

from common.auth import ADMIN_ROLE_ID  # noqa: E402
from db import repository  # noqa: E402
from services import passwords  # noqa: E402


def _hash_de_admin_password(password):
    error = passwords.error_de_password(password, "ADMIN_PASSWORD")
    if error:
        raise SystemExit(f"ERROR: {error} Definela en apps/services/users/.env.")
    return passwords.hash_password(password)


def asegurar_admin(repo, email, password):
    """Aplica los cambios necesarios y devuelve la lista de lo que hizo (vacia = ya estaba listo)."""
    acciones = []
    usuario = repo.get_by_email(email)

    if usuario is None:
        usuario = repo.insert(nombre="Admin", apellido_paterno="Principal", apellido_materno=None, correo=email,
                              password_hash=_hash_de_admin_password(password), role_id=ADMIN_ROLE_ID,
                              activo=True, estado_cuenta="confirmado")
        return usuario, ["cuenta creada (no existia) con role_id = 1, activa y confirmada"]

    cambios = {}
    if usuario["role_id"] != ADMIN_ROLE_ID:
        cambios["role_id"] = ADMIN_ROLE_ID
        acciones.append("role_id = 1 (admin)")
    if not usuario["activo"]:
        cambios["activo"] = True
        acciones.append("activo = true")
    if repo.password_hash(usuario["id_usuario"]) in passwords.HASHES_DE_EJEMPLO:
        cambios["password_hash"] = _hash_de_admin_password(password)
        acciones.append("password_hash de ejemplo reemplazado por el hash bcrypt de ADMIN_PASSWORD")
    if cambios:
        usuario = repo.update(usuario["id_usuario"], **cambios)
    return usuario, acciones


def main():
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    if not email:
        raise SystemExit("ERROR: define ADMIN_EMAIL en apps/services/users/.env.")

    try:
        with repository.unit_of_work() as repo:
            usuario, acciones = asegurar_admin(repo, email, os.getenv("ADMIN_PASSWORD", ""))
            hash_actual = repo.password_hash(usuario["id_usuario"])
    except repository.UnSoloAdmin:
        raise SystemExit(
            f"ERROR: ya hay OTRO administrador y la base solo admite uno (indice un_solo_admin del monolito), "
            f"asi que {email} no puede serlo tambien. Revisa ADMIN_EMAIL o ejecuta "
            "sql/opcional_permitir_varios_admins.sql si quieres permitir varios administradores.")

    print(f"Admin: id_usuario={usuario['id_usuario']} correo={usuario['correo']} "
          f"role_id={usuario['role_id']} activo={usuario['activo']} estado_cuenta={usuario['estado_cuenta']}")
    for accion in acciones:
        print(f"  - {accion}")
    if not acciones:
        print("  - sin cambios: la cuenta ya estaba lista")

    if not passwords.es_hash_bcrypt(hash_actual):
        print("AVISO: su password_hash no es un hash bcrypt ni un valor de ejemplo conocido, asi que no se toco. "
              "Con ese valor no podra iniciar sesion en login.")
    if usuario["estado_cuenta"] != "confirmado":
        print("AVISO: la cuenta esta 'pendiente' de confirmar su correo; login no la dejara entrar hasta confirmarla.")


if __name__ == "__main__":
    main()
