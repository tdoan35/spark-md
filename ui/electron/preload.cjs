const { contextBridge, ipcRenderer } = require("electron")
contextBridge.exposeInMainWorld("sparkmd", {
  minimize: () => ipcRenderer.invoke("win:minimize"),
  maximize: () => ipcRenderer.invoke("win:maximize"),
  close: () => ipcRenderer.invoke("win:close"),
  state: () => ipcRenderer.invoke("win:state"),
  onState: (fn) => {
    const handler = (_e, s) => fn(s)
    ipcRenderer.on("window-state", handler)
    return () => ipcRenderer.removeListener("window-state", handler)
  },
})
