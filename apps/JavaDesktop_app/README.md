# JavaDesktop_app

App de escritorio JavaFX, cliente de los microservicios de Library.

## Requisitos

- JDK 25 o superior (probado con JDK 26). JavaFX 27.0.1 lo descarga Maven. No hace falta instalar Maven: `mvnw` lo descarga.
- Internet para los tiles del mapa (OpenStreetMap).
- Si Windows (Smart App Control / Control de aplicaciones) bloquea la DLL nativa del WebView (`jfxwebkit.dll`),
  la app no se cierra: en Rastreo aparece "Mapa no disponible en este equipo" y una tabla con las posiciones
  que llegan por el WebSocket (código, estado, latitud, longitud, hora).

## JAVA_HOME

El wrapper necesita `JAVA_HOME`. En PowerShell, una sola vez para tu usuario:

```powershell
[Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Java\jdk-26", "User")
```

Cierra y vuelve a abrir la terminal para que tome el valor.

## Cambiar la IP del servidor (API Gateway)

Todas las peticiones (HTTP y el WebSocket de tracking) pasan por el API Gateway
(nginx). Solo hay una URL base, en `src/main/resources/config.properties`:

```properties
gateway.url=http://34.51.84.143:8080/catalogo/api
```

También se puede sobrescribir sin recompilar con la variable de entorno
`EG4_GATEWAY_URL` o con `-Dgateway.url=...`. El WebSocket se deriva de la misma URL:
`ws://IP_EXTERNA:8080/catalogo/api/ws`.

## Ejecutar

Desde `apps/JavaDesktop_app`:

```powershell
.\mvnw.cmd javafx:run
```

(En Linux/macOS: `./mvnw javafx:run`.)
