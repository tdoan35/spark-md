// Spark MD desktop shell. Frameless (opaque; rounded corners come from CSS on #root), loads
// the worker-served UI, refuses any request that is not loopback / the sandbox worker
// address (air-gap belt-and-braces).
const { app, BrowserWindow, ipcMain, Menu, session } = require("electron")
const path = require("node:path")

const START_URL = process.env.SPARKMD_UI_URL || "http://127.0.0.1:8100/"
const ALLOWED_HOSTS = new Set(["127.0.0.1", "::1", "10.77.0.1"])

// Mac dev: metal. GB10 (linux arm64, X11): ANGLE's default GL backend. Do NOT pin gl-egl there:
// on the X11 desktop its WebGL frames never reach the window (canvas stuck on its first frame
// while the page keeps rendering), and it costs ~2× the GPU-process CPU of the default.
if (process.platform === "darwin") app.commandLine.appendSwitch("use-angle", "metal")

function hostAllowed(url) {
  try {
    const u = new URL(url)
    if (u.protocol === "file:" || u.protocol === "data:" || u.protocol === "blob:") return true
    return (u.protocol === "http:" || u.protocol === "ws:") && ALLOWED_HOSTS.has(u.hostname)
  } catch {
    return false
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1920,
    height: 1080,
    minWidth: 1280,
    minHeight: 800,
    frame: false,
    backgroundColor: "#fafafa", // opaque: a transparent window costs compositor work on X11
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
      backgroundThrottling: false,
      preload: path.join(__dirname, "preload.cjs"),
    },
  })
  win.once("ready-to-show", () => win.show())
  win.loadURL(START_URL)
  const send = (s) => !win.isDestroyed() && win.webContents.send("window-state", s)
  for (const ev of ["maximize", "unmaximize", "enter-full-screen", "leave-full-screen"]) {
    win.on(ev, () => send({ maximized: win.isMaximized(), fullscreen: win.isFullScreen() }))
  }
  return win
}

app.whenReady().then(() => {
  if (!process.env.SPARKMD_DEVMENU) Menu.setApplicationMenu(null)
  // No remote frames, no popups, no device permissions: the product is one local page.
  app.on("web-contents-created", (_e, contents) => {
    contents.setWindowOpenHandler(() => ({ action: "deny" }))
    contents.on("will-navigate", (event, url) => {
      if (!hostAllowed(url)) event.preventDefault()
    })
  })
  // 09 push-to-talk needs the mic: allow only `media` for the app origin; everything else stays denied.
  session.defaultSession.setPermissionRequestHandler((wc, permission, callback) => callback(permission === "media" && hostAllowed(wc.getURL())))
  session.defaultSession.webRequest.onBeforeRequest((details, cb) => {
    if (hostAllowed(details.url)) return cb({})
    console.warn("[sparkmd] blocked non-local request:", details.url)
    cb({ cancel: true })
  })
  const win = createWindow()
  ipcMain.handle("win:minimize", () => win.minimize())
  ipcMain.handle("win:maximize", () => (win.isMaximized() ? win.unmaximize() : win.maximize()))
  ipcMain.handle("win:close", () => win.close())
  ipcMain.handle("win:state", () => ({ maximized: win.isMaximized(), fullscreen: win.isFullScreen() }))
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on("window-all-closed", () => app.quit())
