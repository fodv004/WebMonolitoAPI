# Catalogo de Libreria (Electron)

Aplicacion de escritorio para Windows 11 que muestra el catalogo de libros
en tarjetas (imagen, autor(es), ISBN, stock, ano de publicacion, genero y
precio), consumiendo **exclusivamente XML** desde el microservicio REST de
la libreria (`GET /books`).

La URL base y el endpoint son configurables desde la propia aplicacion y se
guardan en el equipo mediante `localStorage`, por lo que persisten entre
sesiones.

## Requisitos previos (Windows 11)

1. Instalar [Node.js LTS](https://nodejs.org/) (incluye `npm`). Verifica la
   instalacion abriendo PowerShell y ejecutando:

   ```powershell
   node -v
   npm -v
   ```

## Pasos para ejecutar la aplicacion

1. Abre PowerShell y entra a la carpeta del proyecto:

   ```powershell
   cd "EG4\apps\Electron_app"
   ```

2. Instala las dependencias (descarga Electron; puede tardar unos minutos
   la primera vez):

   ```powershell
   npm install
   ```

3. Ejecuta la aplicacion:

   ```powershell
   npm start
   ```

4. Se abrira la ventana del catalogo. Por defecto apunta a
   `http://34.51.96.249:5001/books`. Para cambiar el servidor:
   - Da clic en **Configuracion** (esquina superior derecha).
   - Ajusta **URL base** (ej. `http://localhost:5001`) y **Endpoint**
     (ej. `/books`).
   - Da clic en **Guardar y cargar catalogo**. La nueva configuracion queda
     guardada en `localStorage` para la proxima vez que abras la app.
   - **Restablecer valores por defecto** regresa a la URL original.

5. Navega el catalogo con **Anterior / Siguiente**; el tamano de pagina
   (6/12/24 libros) tambien se guarda en la configuracion.

## Empaquetar como ejecutable de Windows (opcional)

Si se necesita un instalador `.exe` para distribuir la app sin requerir
Node.js en la maquina destino:

```powershell
npm run dist
```

El instalador se genera en la carpeta `dist/` usando `electron-builder`.

## Notas tecnicas

- La peticion HTTP al microservicio se realiza desde el **proceso
  principal** de Electron (no desde el renderer) porque el servidor no
  envia cabeceras CORS; esto evita que el navegador (Chromium) bloquee la
  peticion.
- El renderer corre con `nodeIntegration: false` y `contextIsolation: true`;
  solo se expone `window.catalogAPI.fetchXml(url)` via `preload.js`.
- El catalogo completo se descarga en una sola peticion XML y la
  paginacion se aplica del lado del cliente (el microservicio actual no
  soporta parametros de pagina/tamano en `/books`).
