# WebMonolitoAPI

## Rastreo GPS (tracking) y apps relacionadas

Integrado desde el proyecto "Monterrey GPS Tracker" (copiado sin cambios de lógica).

| Carpeta | Qué es | Puerto |
|---|---|---|
| `apps/services/tracking/` | Microservicio Flask + Flask-Sock: `GET /health` y WebSocket `/ws?role=gps\|map`. Estado en memoria (sin BD, sin JWT). | 5900 |
| `tools/gps_simulator/` | Simulador de camiones (pywebview + Leaflet); manda posiciones a `ws://localhost:5900/ws?role=gps`. Incluye `servidor_prueba.py`. | — |
| `apps/GPS_desktop_app/` | Mapa de la flota (pywebview + Leaflet), solo como referencia para el cliente Java. | — |
| `apps/JavaDesktop_app/` | Pendiente: app de escritorio JavaFX cliente de Library. | — |

Puertos de los microservicios: login 5000, books (`library_soap_service`) 5001, users 5002, authors 5003,
pedidos 5004, pagos 5005, tracking 5900. tracking **no** está en `scripts/levantar_servicios.sh`;
para la VM ver `VMComandos.md`, sección 23. Inventario de endpoints: `docs/INVENTARIO_SERVICIOS.md`.
