# GPSapp (Proyecto 1): cómo correrla

> **En el monorepo EG4** las carpetas originales de OpenStreetMaps quedaron así: `microservicio/` → `apps/services/tracking/`, `gpsapp/` → `tools/gps_simulator/`, `mapa/` → `apps/GPS_desktop_app/` (solo referencia). Donde este texto diga `cd microservicio`, `cd gpsapp` o `cd mapa`, usa esas rutas. El puerto sigue siendo 5900.

Cada camión se conecta a `ws://localhost:5900/ws?role=gps` y manda solo
`vehicle_id, latitude, longitude, speed, heading`. El servidor responde `ack` o `error`.

## 1. Instalar (una sola vez)

En la carpeta `gpsapp`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Levantar el servidor de prueba (mientras no exista el microservicio real)

```powershell
python servidor_prueba.py
```

Escucha en `0.0.0.0:5900`, imprime cada mensaje y responde `ack` (o `error` si no cumple el contrato).

## 3. Abrir un camión

```powershell
python main.py
```

En la ventana, de arriba abajo:

1. **ID del camión**: se llena solo (`V001`, `V002`...). Puedes cambiarlo.
2. **Ruta**: elige una ruta guardada o **Nueva ruta**.
3. **Velocidad**: Lenta (30 km/h), Normal (50) o Rápida (70). Se puede cambiar en marcha.
4. **Iniciar**: el camión se conecta al servidor y empieza a mandar su posición cada segundo.
   **Detener** lo para y lo desconecta.
5. **Estado**: Conectado/Desconectado, velocidad actual y última respuesta del servidor.

Si el servidor se cae mientras el camión anda, el camión sigue avanzando y reintenta la
conexión solo (cada 1, 2, 4... hasta 10 s). Cerrar la ventana detiene y desconecta el camión.

Mientras el camión anda, la vista lo sigue. Si mueves el mapa deja de seguirlo; el botón
**Seguir camión** (abajo a la izquierda del mapa) lo vuelve a activar.

## 4. Crear una ruta

1. En **Ruta** elige **Nueva ruta**.
2. Haz clic en el mapa en el inicio y luego en el destino. Se calcula el camino por calles
   con OSRM (requiere internet). Si OSRM no responde, se unen los puntos en línea recta y se avisa.
3. Escribe un nombre y pulsa **Guardar ruta**. Queda en `rutas.json` y en la lista.
   **Limpiar** borra los puntos para empezar de nuevo.

La ruta no se puede cambiar mientras el camión anda; primero pulsa **Detener**.

## 5. Varios camiones

Abre `python main.py` una vez por camión (en terminales distintas). Cada ventana es un camión
independiente con su propio ID y solo muestra su camión.

## 6. Cómo se mueve el camión

Avanza por la ruta a la velocidad elegida con una pequeña variación aleatoria, frena un poco
en las vueltas cerradas y, al llegar al destino, regresa por la misma ruta, una y otra vez
hasta que pulses Detener. `speed` y `heading` salen de ese movimiento.

## Archivos

| Archivo | Para qué |
|---|---|
| `main.py` | La aplicación (ventana, conexión con el servidor) |
| `mapa.html` | La página de la ventana (mapa y panel) |
| `simulacion.py` | Movimiento del camión |
| `rutas.py` | Lectura/guardado de `rutas.json` y cálculo con OSRM |
| `rutas.json` | Rutas guardadas (incluye 5 de ejemplo de Monterrey) |
| `assets/camion.svg` | Icono del camión |
| `servidor_prueba.py` | Servidor WebSocket de prueba |
