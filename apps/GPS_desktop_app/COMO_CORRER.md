# Mapa de la flota (Proyecto 3): cómo correr todo el sistema

> **En el monorepo EG4** las carpetas originales de OpenStreetMaps quedaron así: `microservicio/` → `apps/services/tracking/`, `gpsapp/` → `tools/gps_simulator/`, `mapa/` → `apps/GPS_desktop_app/` (solo referencia). Donde este texto diga `cd microservicio`, `cd gpsapp` o `cd mapa`, usa esas rutas. El puerto sigue siendo 5900.

El sistema son tres proyectos independientes, cada uno con su carpeta y su `requirements.txt`:

| Carpeta | Qué es |
|---|---|
| `microservicio/` | Servidor Flask + Flask-Sock en el puerto 5900 |
| `gpsapp/` | Un camión por ventana; manda su posición al microservicio |
| `mapa/` | Esta app: muestra a todos los camiones juntos en tiempo real |

## 1. Instalar (una sola vez por proyecto)

En **cada** carpeta (`microservicio`, `gpsapp` y `mapa`):

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Correr

Usa una terminal por programa, cada una con el venv de su carpeta activado.

**Terminal 1: microservicio** (primero; si tienes abierto `gpsapp\servidor_prueba.py`, ciérralo,
porque también usa el puerto 5900)

```powershell
cd microservicio
.venv\Scripts\activate
python app.py
```

**Terminal 2: mapa de la flota**

```powershell
cd mapa
.venv\Scripts\activate
python main.py
```

**Terminal 3, 4, ...: un camión por terminal**

```powershell
cd gpsapp
.venv\Scripts\activate
python main.py
```

En cada ventana de camión elige una ruta y pulsa **Iniciar**. Cada una toma un ID distinto
(V001, V002...). El orden no importa: el mapa y los camiones se reconectan solos si el
microservicio se abre después o se reinicia.

## 3. Uso del mapa

- **Indicador de conexión** arriba a la derecha: *Conectado* (verde) o *Reconectando...* (ámbar,
  con el número de intento). Se reconecta solo cada 1, 2, 4... hasta 10 s y, al reconectar,
  vuelve a mandar la configuración actual.
- **Conectados en total**: camiones activos según `/health` del microservicio.
  **Mostrando en el mapa**: cuántos se están dibujando.
- **Camiones a mostrar** y **Actualizar cada (s)**: al cambiarlos se manda
  `{"type":"config","max_vehicles":N,"interval":S}` al microservicio y se aplica al momento,
  sin reiniciar. Se muestran los primeros N camiones ordenados por ID.
- Cada camión tiene su color y gira según su rumbo; se pone **gris** si está inactivo
  (o mientras no hay conexión con el microservicio). Deja una estela de su recorrido reciente.
- Clic en un camión: popup con ID, velocidad, coordenadas y hora de la última actualización.
- Clic en la **lista lateral**: centra el mapa en ese camión y abre su popup.

## 4. Revisar el microservicio

```powershell
Invoke-RestMethod http://localhost:5900/health
```
