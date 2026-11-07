# JavaDesktop_app

App de escritorio JavaFX, cliente de los microservicios de Library.

## Requisitos

- JDK 25 o superior (probado con JDK 26). No hace falta instalar Maven: `mvnw` lo descarga.
- Internet para los tiles del mapa (OpenStreetMap).

## JAVA_HOME

El wrapper necesita `JAVA_HOME`. En PowerShell, una sola vez para tu usuario:

```powershell
[Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Java\jdk-26", "User")
```

Cierra y vuelve a abrir la terminal para que tome el valor.

## Cambiar la IP del servidor

Edita `src/main/resources/config.properties`:

```properties
host=34.51.14.51
```

Ahí también están los puertos de cada servicio (`port.login`, `port.books`, ...).

## Ejecutar

Desde `apps/JavaDesktop_app`:

```powershell
.\mvnw.cmd javafx:run
```

(En Linux/macOS: `./mvnw javafx:run`.)
