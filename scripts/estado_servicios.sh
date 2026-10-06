#!/usr/bin/env bash
# ============================================================
# scripts/estado_servicios.sh
# Muestra el systemctl status de los 6 microservicios y hace curl a
# cada GET /health. Termina con codigo 1 si alguno no responde 200.
#
# Uso:
#   bash scripts/estado_servicios.sh            # resumen
#   bash scripts/estado_servicios.sh -v         # con systemctl status completo
#   HOST=34.x.x.x bash scripts/estado_servicios.sh   # contra otra maquina
# ============================================================
set -uo pipefail

HOST="${HOST:-127.0.0.1}"
VERBOSO="${1:-}"
SERVICIOS=(login:5000 books:5001 users:5002 authors:5003 pedidos:5004 pagos:5005)
fallos=0

for entrada in "${SERVICIOS[@]}"; do
    servicio="${entrada%%:*}"
    puerto="${entrada##*:}"
    printf '\n==== %s (puerto %s) ====\n' "$servicio" "$puerto"

    if command -v systemctl > /dev/null; then
        if [ "$VERBOSO" = "-v" ]; then
            systemctl status "$servicio.service" --no-pager --lines 5 || true
        else
            printf 'systemd: %s / %s\n' "$(systemctl is-active "$servicio.service" 2>&1)" \
                                         "$(systemctl is-enabled "$servicio.service" 2>&1)"
        fi
    fi

    respuesta="$(curl --silent --max-time 5 --write-out '\n%{http_code}' "http://$HOST:$puerto/health" 2>&1)"
    codigo="${respuesta##*$'\n'}"
    cuerpo="${respuesta%$'\n'*}"
    if [ "$codigo" = "200" ]; then
        printf 'health : 200 OK   %s\n' "$cuerpo"
    else
        printf 'health : %s FALLA   %s\n' "${codigo:-sin respuesta}" "$cuerpo"
        fallos=$((fallos + 1))
    fi
done

printf '\n'
if [ "$fallos" -eq 0 ]; then
    echo "Los 6 servicios responden 200 en /health."
else
    echo "$fallos servicio(s) NO responden 200. Revisa: journalctl -u <servicio> -n 50 --no-pager"
    exit 1
fi
