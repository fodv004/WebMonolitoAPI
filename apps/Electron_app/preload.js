/**
 * preload.js
 * Puente seguro entre el renderer (sin nodeIntegration) y el proceso
 * principal. Solo expone lo estrictamente necesario: pedir XML por URL.
 */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("catalogAPI", {
  fetchXml: (url) => ipcRenderer.invoke("fetch-xml", url),
});
