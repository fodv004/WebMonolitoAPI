/**
 * main.js
 * Proceso principal de Electron. Crea la ventana y atiende la peticion
 * "fetch-xml" del renderer usando el modulo `net` de Electron.
 *
 * La peticion HTTP se hace aqui (no en el renderer) porque el
 * microservicio no envia cabeceras CORS y un fetch() hecho desde el
 * renderer seria bloqueado por Chromium. `net.request` del proceso
 * principal no esta sujeto a esa restriccion.
 */
const { app, BrowserWindow, ipcMain, net } = require("electron");
const path = require("path");

/**
 * URL base del API Gateway (nginx). Es el UNICO lugar donde se define el
 * servidor: todas las llamadas salen por aqui y el gateway enruta por
 * prefijo (/books -> books, /login -> login, ...).
 * Se puede sobrescribir con la variable de entorno EG4_GATEWAY_URL.
 */
const DEFAULT_GATEWAY_URL = "http://34.51.84.143:8080/catalogo/api";
const GATEWAY_URL = (process.env.EG4_GATEWAY_URL || DEFAULT_GATEWAY_URL).trim().replace(/\/+$/, "");

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 960,
    minHeight: 640,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // El preload (sandbox) lee la URL del gateway de process.argv.
      additionalArguments: [`--gateway-url=${GATEWAY_URL}`],
    },
  });

  win.loadFile("index.html");
}

app.whenReady().then(() => {
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

ipcMain.handle("fetch-xml", async (_event, rawUrl) => {
  let target;
  try {
    target = new URL(rawUrl);
  } catch (err) {
    return { ok: false, error: `URL invalida: ${err.message}` };
  }

  if (target.protocol !== "http:" && target.protocol !== "https:") {
    return { ok: false, error: "Solo se permiten URLs http:// o https://." };
  }

  return new Promise((resolve) => {
    const request = net.request({ method: "GET", url: target.toString() });
    const chunks = [];

    request.on("response", (response) => {
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf-8");
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve({ ok: true, status: response.statusCode, data: body });
        } else {
          resolve({
            ok: false,
            status: response.statusCode,
            error: `El servidor respondio con estado ${response.statusCode}.`,
          });
        }
      });
      response.on("error", (err) => resolve({ ok: false, error: err.message }));
    });

    request.on("error", (err) => resolve({ ok: false, error: err.message }));
    request.end();
  });
});
