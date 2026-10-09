"""
app.py
Entrypoint del microservicio pagos (Flask, puerto 5005): registra pagos (simulados) y
actualiza el estado de los pedidos.

Usa el modulo compartido apps/services/common; ver docs/ARQUITECTURA.md.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
# apps/services en el path: ahi vive el modulo compartido `common`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.app_factory import create_service_app  # noqa: E402
from common.config import settings  # noqa: E402
from config.settings import DEFAULT_PORT, SERVICE_NAME, SINCRONIZACION_AUTOMATICA, VERSION  # noqa: E402
from db import connection  # noqa: E402
from routes import register_routes  # noqa: E402
from services import sincronizacion  # noqa: E402

app = create_service_app(SERVICE_NAME, VERSION, db_check=lambda: connection.ping())
register_routes(app)

# Tarea en segundo plano: cada minuto reintenta avisar a pedidos de los pagos sin sincronizar.
if SINCRONIZACION_AUTOMATICA:
    sincronizacion.iniciar()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.PORT or DEFAULT_PORT, debug=False)
