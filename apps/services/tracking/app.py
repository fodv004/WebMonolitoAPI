"""
app.py
Entrypoint del microservicio tracking (Flask + Flask-Sock, puerto 5900): codigo de
rastreo por pedido pagado, estados del envio y posiciones en tiempo real por WebSocket.

Usa el modulo compartido apps/services/common (JWT, BD, /health, /metrics, errores).
  REST       POST/GET /envios, GET /envios/<codigo>, GET /envios/internal/activos  (routes/envios.py)
  WebSocket  /ws?role=gps | cliente | map                                          (routes/ws.py)

En produccion: gunicorn con 1 worker y hilos (deploy/tracking.service). Los
WebSocket y la difusion de eventos viven en la memoria del proceso.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
# apps/services en el path: ahi vive el modulo compartido `common`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.app_factory import create_service_app  # noqa: E402
from common.config import settings  # noqa: E402
from config.settings import DEFAULT_PORT, SERVICE_NAME, TAREAS_AUTOMATICAS, VERSION  # noqa: E402
from db import connection  # noqa: E402
from routes import register_routes  # noqa: E402
from services import tareas  # noqa: E402

app = create_service_app(SERVICE_NAME, VERSION, db_check=lambda: connection.ping())
register_routes(app)

# Hilo en segundo plano: estados por tiempo y reintentos de aviso a pedidos.
if TAREAS_AUTOMATICAS:
    tareas.iniciar()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.PORT or DEFAULT_PORT, debug=False, threaded=True)
