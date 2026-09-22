"""
mailer.py
Envio del correo de confirmacion por SMTP. El modo se elige con
MAIL_MODE en el .env:

  - mailpit (por defecto): servidor SMTP local de pruebas, sin TLS ni
    login (localhost:1025). El mensaje se ve en http://localhost:8025.
  - gmail: SMTP real de Gmail (smtp.gmail.com:587) con STARTTLS y
    autenticacion (usuario + contraseña de aplicacion de Gmail).

En ambos casos host/puerto/usuario/contraseña salen de Config (.env),
nunca hardcodeados en este archivo.
"""
import logging
import smtplib
from email.message import EmailMessage
from html import escape
from urllib.parse import quote

from config import Config

log = logging.getLogger(__name__)


class MailError(Exception):
    """No se pudo entregar el correo al servidor SMTP."""


def confirmation_link(token):
    return f"{Config.PUBLIC_BASE_URL}/confirm?token={quote(token, safe='')}"


def _build_message(destinatario, nombre, token):
    enlace = confirmation_link(token)
    horas = Config.CONFIRM_TOKEN_HOURS

    msg = EmailMessage()
    msg["Subject"] = "Confirma tu cuenta en la Librería"
    msg["From"] = Config.MAIL_FROM
    msg["To"] = destinatario
    msg.set_content(
        f"Hola {nombre},\n\n"
        "Gracias por registrarte en la Librería. Para activar tu cuenta abre este enlace:\n\n"
        f"{enlace}\n\n"
        f"El enlace es de un solo uso y vence en {horas} horas.\n"
        "Si no creaste esta cuenta, ignora este mensaje.\n"
    )
    msg.add_alternative(
        f"""<!doctype html>
<html lang="es"><body style="font-family:Arial,Helvetica,sans-serif;color:#1f2937">
  <h2>Hola {escape(nombre)},</h2>
  <p>Gracias por registrarte en la Librería. Para activar tu cuenta confirma tu correo:</p>
  <p><a href="{escape(enlace, quote=True)}"
        style="display:inline-block;background:#1d4ed8;color:#fff;padding:12px 20px;border-radius:6px;text-decoration:none">
        Confirmar mi cuenta</a></p>
  <p style="font-size:13px;color:#6b7280">Si el botón no funciona, copia este enlace en tu navegador:<br>{escape(enlace)}</p>
  <p style="font-size:13px;color:#6b7280">El enlace es de un solo uso y vence en {horas} horas.
     Si no creaste esta cuenta, ignora este mensaje.</p>
</body></html>""",
        subtype="html",
    )
    return msg


def _send_mailpit(msg):
    """Modo de pruebas: sin TLS ni login, tal como esperaba Mailpit."""
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10) as smtp:
        smtp.send_message(msg)


def _send_gmail(msg):
    """Modo real: STARTTLS + login con contraseña de aplicación de Gmail."""
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        smtp.send_message(msg)


def send_confirmation_email(destinatario, nombre, token):
    msg = _build_message(destinatario, nombre, token)
    try:
        if Config.MAIL_MODE == "gmail":
            _send_gmail(msg)
        else:
            _send_mailpit(msg)
    except (OSError, smtplib.SMTPException) as e:
        log.error("No se pudo enviar el correo de confirmacion a %s (MAIL_MODE=%s): %s",
                   destinatario, Config.MAIL_MODE, e)
        raise MailError(str(e)) from e
