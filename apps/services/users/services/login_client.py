"""
services/login_client.py
Llamadas al microservicio de login. Users no escribe en las tablas de
login (tokens_confirmacion): le pide por HTTP que envie el correo de
confirmacion, con timeout de 3 segundos y el header X-Internal-Key.
"""
import logging

import requests

from common.auth import INTERNAL_KEY_HEADER
from common.config import settings
from common.errors import ApiError

log = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 3


def enviar_confirmacion(user_id, email, nombre):
    """Pide a login el correo de confirmacion para `email`. Lanza ApiError 503 si no se pudo."""
    no_enviado = ApiError(503, "CORREO_NO_ENVIADO",
                          "No se pudo enviar el correo de confirmacion. El correo no se cambio; intenta mas tarde.")
    try:
        resp = requests.post(
            f"{settings.LOGIN_URL}/internal/confirmation",
            json={"user_id": user_id, "email": email, "nombre": nombre},
            headers={INTERNAL_KEY_HEADER: settings.INTERNAL_API_KEY, "Accept": "application/json"},
            params={"format": "json"},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as e:
        log.error("login no responde al pedir la confirmacion de correo: %s", type(e).__name__)
        raise no_enviado
    if resp.status_code >= 400:
        log.error("login rechazo la confirmacion de correo: HTTP %s", resp.status_code)
        raise no_enviado
