/**
 * preload.js
 * Puente seguro entre el renderer (sin nodeIntegration) y el proceso
 * principal. Solo expone lo estrictamente necesario: pedir XML por URL
 * y la URL base del API Gateway definida en main.js (o en EG4_GATEWAY_URL).
 */
const { contextBridge, ipcRenderer } = require("electron");

const GATEWAY_ARG = "--gateway-url=";
const gatewayArg = process.argv.find((arg) => arg.startsWith(GATEWAY_ARG));

contextBridge.exposeInMainWorld("catalogAPI", {
  gatewayUrl: gatewayArg ? gatewayArg.slice(GATEWAY_ARG.length) : "",
  fetchXml: (url) => ipcRenderer.invoke("fetch-xml", url),
});
