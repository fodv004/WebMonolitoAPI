"""
common/config.py
Configuracion compartida, leida de variables de entorno (.env del
servicio que arranca). Ningun secreto vive en el codigo.

Si falta JWT_SECRET_KEY el servicio NO arranca. Por compatibilidad con los
.env anteriores se aceptan, en este orden, JWT_SECRET (nombre viejo) y
SECRET_KEY (solo como respaldo), avisando en el log.
"""
import logging
import os
from urllib.parse import quote

from dotenv import find_dotenv, load_dotenv

# El .env es el del servicio que arranca (su directorio de trabajo), no el de common/.
# Cada app.py lo carga ademas de forma explicita antes de importar este modulo.
load_dotenv(find_dotenv(usecwd=True))

log = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"  # fijo: nunca se toma del token ni se negocia


def _env(name, default=""):
    return os.getenv(name, default).strip()


def _lista(valor):
    return [v.strip() for v in valor.split(",") if v.strip()]


def _database_url():
    """DATABASE_URL, o la equivalente armada con DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD."""
    url = _env("DATABASE_URL")
    if url or not _env("DB_NAME"):
        return url
    credenciales = quote(_env("DB_USER"), safe="")
    if _env("DB_PASSWORD"):
        credenciales += ":" + quote(_env("DB_PASSWORD"), safe="")
    return f"postgresql://{credenciales}@{_env('DB_HOST', 'localhost')}:{_env('DB_PORT', '5432')}/{_env('DB_NAME')}"


def _jwt_secret():
    secreto = _env("JWT_SECRET_KEY")
    if secreto:
        return secreto
    for respaldo in ("JWT_SECRET", "SECRET_KEY"):
        secreto = _env(respaldo)
        if secreto:
            log.warning("JWT_SECRET_KEY no definida: se usa %s como respaldo de compatibilidad. "
                        "Define JWT_SECRET_KEY en el .env.", respaldo)
            return secreto
    raise SystemExit(
        "ERROR: la variable de entorno JWT_SECRET_KEY no esta definida. "
        "El servicio no puede firmar ni validar tokens sin ella. "
        "Definela en el .env (con el MISMO valor en los 6 microservicios) y vuelve a arrancar."
    )


class Settings:
    def __init__(self):
        self.PORT = int(_env("PORT") or _env("FLASK_PORT") or "0")
        self.DATABASE_URL = _database_url()
        self.REDIS_URL = _env("REDIS_URL", "redis://127.0.0.1:6379/0")

        self.JWT_SECRET_KEY = _jwt_secret()
        self.JWT_ALGORITHM = JWT_ALGORITHM
        if _env("JWT_ALGORITHM", JWT_ALGORITHM) != JWT_ALGORITHM:
            raise SystemExit(f"ERROR: JWT_ALGORITHM debe ser {JWT_ALGORITHM}; no se admite otro algoritmo.")
        self.ACCESS_TOKEN_MINUTES = int(_env("ACCESS_TOKEN_MINUTES", "20"))

        # Nunca "*": si la lista queda vacia no se envia ningun header CORS.
        origenes = _lista(_env("CORS_ALLOWED_ORIGINS") or _env("CORS_ORIGINS"))
        self.CORS_ALLOWED_ORIGINS = [o for o in origenes if o != "*"]

        self.INTERNAL_API_KEY = _env("INTERNAL_API_KEY")

        self.LOGIN_URL = _env("LOGIN_URL", "http://127.0.0.1:5000").rstrip("/")
        self.BOOKS_URL = _env("BOOKS_URL", "http://127.0.0.1:5001").rstrip("/")
        self.USERS_URL = _env("USERS_URL", "http://127.0.0.1:5002").rstrip("/")
        self.AUTHORS_URL = _env("AUTHORS_URL", "http://127.0.0.1:5003").rstrip("/")
        self.PEDIDOS_URL = _env("PEDIDOS_URL", "http://127.0.0.1:5004").rstrip("/")
        self.PAGOS_URL = _env("PAGOS_URL", "http://127.0.0.1:5005").rstrip("/")

    @property
    def ACCESS_TOKEN_SECONDS(self):
        return self.ACCESS_TOKEN_MINUTES * 60


settings = Settings()
