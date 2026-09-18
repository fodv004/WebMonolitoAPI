"""
mailer.py
Envio del correo de confirmacion por SMTP a Mailpit (localhost:1025), el
servidor de correo propio de la instancia. No se usa Gmail ni ningun servicio
de terceros. El mensaje se puede ver en la interfaz web de Mailpit
(http://localhost:8025).
"""
import smtplib
from email.message import EmailMessage
from html import escape
from urllib.parse import quote

from config import Config


class MailError(Exception):
    """No se pudo entregar el correo al servidor SMTP."""


def confirmation_link(token):
    return f"{Config.PUBLIC_BASE_URL}/confirm?token={quote(token, safe='')}"


def send_confirmation_email(destinatario, nombre, token):
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

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10) as smtp:
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        raise MailError(str(e)) from e
