"""
config.py
Configuracion del microservicio de autenticacion, leida de variables de
entorno (.env). Ningun secreto vive en el codigo.
"""
import logging
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


def _bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "si")


class Config:
    HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    PORT = int(os.getenv("FLASK_PORT", "5000"))

    # Sesion del lado de Flask (cookie firmada). Nombre propio para no chocar con
    # las cookies de otros servicios que comparten host (p. ej. connect.sid del monolito).
    SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
    SESSION_COOKIE_NAME = "auth_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = int(os.getenv("SESSION_LIFETIME_HOURS", "8")) * 3600

    # Los cuerpos de estas peticiones son minusculos: se corta cualquier abuso.
    MAX_CONTENT_LENGTH = 16 * 1024

    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "library")
    DB_USER = os.getenv("DB_USER", "auth_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
    MAIL_FROM = os.getenv("MAIL_FROM", "Libreria <no-reply@libreria.local>")

    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5000").rstrip("/")
    CONFIRM_TOKEN_HOURS = int(os.getenv("CONFIRM_TOKEN_HOURS", "24"))


if not Config.SECRET_KEY:
    Config.SECRET_KEY = secrets.token_hex(32)
    log.warning("SECRET_KEY no definida: se genero una aleatoria para este proceso "
                "(las sesiones se invalidan al reiniciar). Defínela en .env.")
