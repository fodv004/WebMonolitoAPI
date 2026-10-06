#!/usr/bin/env bash
# ============================================================
# scripts/run_tests.sh
# Ejecuta pytest del modulo comun, de cada microservicio y de la app Tk.
# No necesita PostgreSQL ni Redis (usa fakeredis). Cada suite corre en su
# propio proceso porque todos los servicios tienen un modulo llamado `app`.
#
# Uso:
#   bash scripts/run_tests.sh                 # prepara lo necesario y corre todo
#   PYTHON=/ruta/python bash scripts/run_tests.sh   # fuerza un interprete para todas las suites
#
# Sin PYTHON, cada servicio usa su propio .venv (instala ahi requirements-dev.txt
# si falta pytest); el modulo comun y la app Tk usan el .venv de users.
# ============================================================
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICES_DIR="$REPO_DIR/apps/services"
fallos=0

# Interprete del .venv de un servicio (Linux o Windows); vacio si no existe.
python_de() {
    local candidato
    for candidato in "$1/.venv/bin/python" "$1/.venv/Scripts/python.exe"; do
        [ -x "$candidato" ] && { printf '%s' "$candidato"; return; }
    done
}

# Interprete con el que se corre una suite, con pytest y fakeredis instalados.
preparar() {
    local dir="$1" py
    if [ -n "${PYTHON:-}" ]; then printf '%s' "$PYTHON"; return; fi
    py="$(python_de "$dir")"
    [ -z "$py" ] && { printf 'python'; return; }
    "$py" -c "import pytest, fakeredis" 2>/dev/null \
        || "$py" -m pip install --quiet -r "$dir/requirements-dev.txt" >&2
    printf '%s' "$py"
}

correr() {    # correr <nombre> <carpeta de la suite> <interprete>
    printf '\n==== %s ====\n' "$1"
    (cd "$2" && "$3" -m pytest -q tests) || fallos=$((fallos + 1))
}

py_users="$(preparar "$SERVICES_DIR/users")"
correr common "$SERVICES_DIR/common" "$py_users"
for suite in login library_soap_service users authors pedidos pagos; do
    correr "$suite" "$SERVICES_DIR/$suite" "$(preparar "$SERVICES_DIR/$suite")"
done
correr Python_app "$REPO_DIR/apps/Python_app" "$py_users"

printf '\n'
if [ "$fallos" -eq 0 ]; then
    echo "Todas las suites pasaron."
else
    echo "$fallos suite(s) con fallos."
    exit 1
fi
