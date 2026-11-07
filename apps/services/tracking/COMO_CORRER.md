# Microservicio (Proyecto 2): cómo correrlo

> **En el monorepo EG4** las carpetas originales de OpenStreetMaps quedaron así: `microservicio/` → `apps/services/tracking/`, `gpsapp/` → `tools/gps_simulator/`, `mapa/` → `apps/GPS_desktop_app/` (solo referencia). Donde este texto diga `cd microservicio`, `cd gpsapp` o `cd mapa`, usa esas rutas. El puerto sigue siendo 5900.

Recibe las posiciones de los camiones (GPSapp) y se las empuja a los mapas por WebSocket.
No sirve páginas web; solo expone `/ws` y `/health` en el puerto **5900**.

## 1. Instalar (una sola vez)

En la carpeta `microservicio`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Correr todo el sistema

Usa terminales separadas, cada una con el venv de su proyecto activado.

**Terminal 1: microservicio**

```powershell
cd microservicio
.venv\Scripts\activate
python app.py
```

Si ya tenías corriendo `gpsapp\servidor_prueba.py`, ciérralo antes: los dos usan el puerto 5900.

**Terminal 2, 3, ...: un camión por terminal**

```powershell
cd gpsapp
.venv\Scripts\activate
python main.py
```

En cada ventana elige una ruta y pulsa **Iniciar**. Cada ventana toma un ID distinto
(V001, V002...). En la consola del microservicio verás algo como:

```
[18:17:21] [gps] Conectado 127.0.0.1:63455
[18:17:21] [gps] 127.0.0.1:63455 es el vehículo V001
[18:17:21] [gps] Vehículo nuevo: V001
[18:17:26] [gps] Desconectado V001
[18:17:26] [gps] V001 inactivo (desconectado o sin datos en 15 s)
```

**Mapa (Proyecto 3)**: se conecta a `ws://localhost:5900/ws?role=map`.

## 3. Probar /health

Con el navegador: <http://localhost:5900/health>

Con PowerShell:

```powershell
Invoke-RestMethod http://localhost:5900/health
```

o con `curl.exe http://localhost:5900/health`. Respuesta:

```json
{"status": "ok", "vehicles": 3, "active_vehicles": 2, "map_clients": 1}
```

- `vehicles`: vehículos en memoria (activos e inactivos).
- `active_vehicles`: conectados y con datos en los últimos 15 s.
- `map_clients`: mapas conectados.

## 4. Qué hace

- **Camiones (`/ws?role=gps`)**: cada mensaje debe traer exactamente
  `vehicle_id, latitude, longitude, speed, heading`, con tipos y rangos válidos
  (latitud -90..90, longitud -180..180, speed >= 0, heading 0..360). Si es válido se guarda y se
  responde `{"type":"ack"}`; si no, `{"type":"error","detail":"..."}` y no se guarda.
  A un camión nunca se le mandan posiciones de otros camiones.
- **Una conexión = un vehículo**: la conexión queda ligada al `vehicle_id` de su primer mensaje.
  Si otra GPSapp se conecta con un ID que ya está conectado, se le responde error y se cierra.
  Si un camión manda un `vehicle_id` distinto al suyo, ese mensaje se rechaza.
- **Inactivos**: un vehículo pasa a `active: false` si se desconecta o lleva 15 s sin mandar
  datos. Se queda en memoria (con sus últimas 50 posiciones) y se borra tras 10 minutos inactivo.
- **Mapas (`/ws?role=map`)**: al conectar reciben `{"type":"snapshot","vehicles":[...]}`. Luego,
  cada `interval` segundos, si algo cambió, reciben `{"type":"update","vehicles":[...]}` con el
  estado actual de los primeros `max_vehicles` vehículos (ordenados por `vehicle_id`). El mapa
  puede cambiarlo en cualquier momento con:

  ```json
  {"type": "config", "max_vehicles": 5, "interval": 2}
  ```

  Por defecto: todos los vehículos, cada 1 s. `max_vehicles: null` vuelve a "todos";
  `interval` acepta de 0.1 a 3600 s. Una config inválida se responde con `error`.
- Cada vehículo que se manda al mapa lleva los 5 campos más `received_at` (hora UTC en que lo
  recibió el servidor, ISO-8601) y `active`.
