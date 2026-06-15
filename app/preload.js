// Bridge the native folder picker into the web UI. The page checks
// `window.ninexf?.pickFolder` — present in Electron, absent in a plain
// browser (which falls back to the server-side folder browser).

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('ninexf', {
  pickFolder: () => ipcRenderer.invoke('pick-folder'),
  openExternal: url => ipcRenderer.invoke('open-external', url),
});
