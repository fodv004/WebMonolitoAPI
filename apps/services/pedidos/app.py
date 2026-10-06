"""
app.py
Entrypoint del microservicio pedidos (Flask, puerto 5004): crea y gestiona pedidos, líneas de pedido, stock y estados.

Parte 1 del proyecto: solo el ambiente base. Ya expone GET /health y
GET /metrics con el modulo compartido apps/services/common; los endpoints
de negocio se agregan en routes/ (ver docs/ARQUITECTURA.md).
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
# apps/services en el path: ahi vive el modulo compartido `common`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.app_factory import create_service_app  # noqa: E402
from common.config import settings  # noqa: E402
from config.settings import DEFAULT_PORT, SERVICE_NAME, VERSION  # noqa: E402
from db import connection  # noqa: E402
from routes import register_routes  # noqa: E402

app = create_service_app(SERVICE_NAME, VERSION, db_check=lambda: connection.ping())
register_routes(app)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.PORT or DEFAULT_PORT, debug=False)
