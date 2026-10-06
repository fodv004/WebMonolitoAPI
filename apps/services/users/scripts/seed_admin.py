"""
scripts/seed_admin.py
Crea o actualiza el usuario administrador inicial (role_id = 1) con los
datos de las variables de entorno del .env de users:

    ADMIN_EMAIL, ADMIN_PASSWORD            (obligatorias)
    ADMIN_NOMBRE, ADMIN_APELLIDO_PATERNO, ADMIN_APELLIDO_MATERNO

Es idempotente: si el correo ya existe se actualizan su contraseña, su
rol y su estado (activo y confirmado). La contraseña solo se guarda como
hash bcrypt (mismo formato que login) y nunca se imprime.

Requiere la migracion sql/001_roles.sql. Ejecutar desde apps/services/users:

    .venv/bin/python scripts/seed_admin.py
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]          # apps/services/users
load_dotenv(RAIZ / ".env")
sys.path.insert(0, str(RAIZ.parent))                # apps/services (modulo `common`)

import bcrypt  # noqa: E402

from common.auth import ADMIN_ROLE_ID  # noqa: E402
from common.db import get_conn  # noqa: E402

BCRYPT_ROUNDS = 12
BCRYPT_MAX_BYTES = 72
PASSWORD_MIN = 8


def main():
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or not password:
        raise SystemExit("ERROR: define ADMIN_EMAIL y ADMIN_PASSWORD en apps/services/users/.env.")
    if len(password) < PASSWORD_MIN or len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise SystemExit(f"ERROR: ADMIN_PASSWORD debe tener entre {PASSWORD_MIN} caracteres y {BCRYPT_MAX_BYTES} bytes.")

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")
    with get_conn() as conn:
        fila = conn.execute(
            """
            INSERT INTO usuarios (nombre, apellido_paterno, apellido_materno, correo, password_hash,
                                  es_admin, activo, estado_cuenta, role_id)
            VALUES (%s, %s, %s, %s, %s, TRUE, TRUE, 'confirmado', %s)
            ON CONFLICT (correo) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    es_admin = TRUE,
                    activo = TRUE,
                    estado_cuenta = 'confirmado',
                    role_id = EXCLUDED.role_id
            RETURNING id_usuario, (xmax = 0) AS creado
            """,
            (
                os.getenv("ADMIN_NOMBRE", "").strip() or "Administrador",
                os.getenv("ADMIN_APELLIDO_PATERNO", "").strip() or None,
                os.getenv("ADMIN_APELLIDO_MATERNO", "").strip() or None,
                email,
                password_hash,
                ADMIN_ROLE_ID,
            ),
        ).fetchone()

    print(f"Admin {'creado' if fila[1] else 'actualizado'}: id_usuario={fila[0]} correo={email} role_id={ADMIN_ROLE_ID}")


if __name__ == "__main__":
    main()
