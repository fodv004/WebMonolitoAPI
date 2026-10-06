#!/usr/bin/env bash
# ============================================================
# scripts/levantar_servicios.sh
# Deja corriendo en la VM los 6 microservicios (login, books, users,
# authors, pedidos, pagos) como unidades systemd con gunicorn:
#
#   1. Crea el .venv de cada servicio e instala sus dependencias.
#   2. Verifica que cada servicio tenga su .env (lo crea desde
#      .env.example y se detiene para que lo completes).
#   3. Ejecuta las migraciones apps/services/*/sql/NNN_*.sql.
#   4. Instala, activa y reinicia las 6 unidades systemd.
#
# Uso (en la VM, desde cualquier carpeta; pide sudo solo para systemd):
#   bash scripts/levantar_servicios.sh
#
# Variables opcionales:
#   PYTHON=python3.12              interprete con el que se crean los .venv
#   RUN_USER=usuario               usuario de las unidades (default: el actual)
#   MIGRATION_DATABASE_URL=...     conexion del DUEÑO de la BD para migrar
#                                  (default: DATABASE_URL de users/.env)
#   SKIP_MIGRATIONS=1              no ejecutar migraciones
#
# El administrador inicial NO se toca aqui: se prepara una sola vez con
#   (cd apps/services/users && .venv/bin/python scripts/crear_admin.py)
# ============================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICES_DIR="$REPO_DIR/apps/services"
PYTHON="${PYTHON:-python3}"
RUN_USER="${RUN_USER:-$(id -un)}"

SERVICIOS=(login books users authors pedidos pagos)
declare -A DIRECTORIO=([login]=login [books]=library_soap_service [users]=users
                       [authors]=authors [pedidos]=pedidos [pagos]=pagos)

titulo() { printf '\n==== %s ====\n' "$1"; }

# Valor de una variable en un archivo .env (ultima definicion; sin comillas).
valor_env() {
    local valor
    valor="$(grep -E "^$2=" "$1" 2>/dev/null | tail -n 1 | cut -d= -f2- || true)"
    valor="${valor%\"}"; valor="${valor#\"}"
    printf '%s' "$valor"
}

# ------------------------------------------------------------ 1. dependencias
titulo "1/4 Dependencias"
for servicio in "${SERVICIOS[@]}"; do
    dir="$SERVICES_DIR/${DIRECTORIO[$servicio]}"
    echo "-> $servicio ($dir)"
    [ -x "$dir/.venv/bin/python" ] || "$PYTHON" -m venv "$dir/.venv"
    "$dir/.venv/bin/python" -m pip install --quiet --upgrade pip
    "$dir/.venv/bin/python" -m pip install --quiet -r "$dir/requirements.txt"
done

# ------------------------------------------------------------ 2. archivos .env
titulo "2/4 Archivos .env"
pendientes=()
secreto_ref=""
for servicio in "${SERVICIOS[@]}"; do
    dir="$SERVICES_DIR/${DIRECTORIO[$servicio]}"
    if [ ! -f "$dir/.env" ]; then
        cp "$dir/.env.example" "$dir/.env"
        pendientes+=("$dir/.env  (recien creado desde .env.example)")
    fi
    chmod 600 "$dir/.env"

    secreto="$(valor_env "$dir/.env" JWT_SECRET_KEY)"
    redis_url="$(valor_env "$dir/.env" REDIS_URL)"
    if [ -z "$secreto" ]; then
        pendientes+=("$dir/.env  (falta JWT_SECRET_KEY)")
    elif [ -z "$secreto_ref" ]; then
        secreto_ref="$secreto"
    elif [ "$secreto" != "$secreto_ref" ]; then
        pendientes+=("$dir/.env  (JWT_SECRET_KEY distinto al de login: deben ser IGUALES)")
    fi
    if [ -z "$redis_url" ] || [ "$redis_url" = "redis://:password@127.0.0.1:6379/0" ]; then
        pendientes+=("$dir/.env  (REDIS_URL sin la contraseña real de Redis)")
    fi
done
if [ "${#pendientes[@]}" -gt 0 ]; then
    echo "Completa estos archivos y vuelve a ejecutar el script:"
    printf '  - %s\n' "${pendientes[@]}"
    exit 1
fi
echo "Los 6 .env existen, comparten JWT_SECRET_KEY y tienen REDIS_URL."

# ------------------------------------------------------------ 3. migraciones
titulo "3/4 Migraciones"
if [ "${SKIP_MIGRATIONS:-0}" = "1" ]; then
    echo "SKIP_MIGRATIONS=1: se omiten."
else
    db_url="${MIGRATION_DATABASE_URL:-$(valor_env "$SERVICES_DIR/users/.env" DATABASE_URL)}"
    if [ -z "$db_url" ]; then
        echo "ERROR: define DATABASE_URL en apps/services/users/.env (o MIGRATION_DATABASE_URL)."
        exit 1
    fi
    shopt -s nullglob
    for archivo in "$SERVICES_DIR"/*/sql/[0-9][0-9][0-9]_*.sql; do
        echo "-> ${archivo#"$REPO_DIR"/}"
        psql "$db_url" -v ON_ERROR_STOP=1 --quiet -f "$archivo"
    done
    shopt -u nullglob
fi

# ------------------------------------------------------------ 4. systemd
titulo "4/4 Unidades systemd (usuario: $RUN_USER)"
unidades=()
for servicio in "${SERVICIOS[@]}"; do
    dir="$SERVICES_DIR/${DIRECTORIO[$servicio]}"
    sed -e "s|__USER__|$RUN_USER|g" -e "s|__REPO_DIR__|$REPO_DIR|g" "$dir/deploy/$servicio.service" \
        | sudo tee "/etc/systemd/system/$servicio.service" > /dev/null
    unidades+=("$servicio.service")
done
sudo systemctl daemon-reload
sudo systemctl enable "${unidades[@]}"
sudo systemctl restart "${unidades[@]}"

sleep 3
bash "$REPO_DIR/scripts/estado_servicios.sh" || true
