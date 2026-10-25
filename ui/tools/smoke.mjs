// Spark MD static serve + CDP smoke test (dev tool; not part of the product).
// Usage: node tools/smoke.mjs [port] [shots-dir]
import http from "node:http"
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const PORT = Number(process.argv[2] ?? 8099)
const SHOTS = process.argv[3] ?? "/tmp/sparkmd-shots"
const UI = path.resolve(import.meta.dirname, "..", "dist")
const MOCK = process.env.MOCK_URL ?? "http://127.0.0.1:8101"

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".json": "application/json", ".glb": "model/gltf-binary" }

// Static server for dist + a transparent proxy of /api to the mock worker.
const server = http.createServer(async (req, res) => {
  if (req.url.startsWith("/api/")) {
    const target = new URL(req.url, MOCK)
    const isSse = target.pathname === "/api/events"
    const up = http.request({ hostname: target.hostname, port: target.port, path: target.pathname + target.search, method: req.method, headers: { ...req.headers, host: target.host } }, (ur) => {
      res.writeHead(ur.statusCode, ur.headers)
      ur.pipe(res)
    })
    up.on("error", () => {
      res.writeHead(502)
      res.end("worker down")
    })
    req.pipe(up)
    if (isSse) req.socket.setTimeout(0)
    return
  }
  let p = req.url.split("?")[0]
  if (p === "/") p = "/index.html"
  const file = path.join(UI, p)
  if (!file.startsWith(UI) || !fs.existsSync(file)) {
    res.writeHead(404)
    return res.end("not found")
  }
  res.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "application/octet-stream" })
  fs.createReadStream(file).pipe(res)
})
await new Promise((r) => server.listen(PORT, "127.0.0.1", r))

fs.mkdirSync(SHOTS, { recursive: true })
const CDP_PORT = 9333
const electron = process.env.ELECTRON_BIN ?? path.resolve(import.meta.dirname, "..", "node_modules", ".bin", "electron")
const proc = spawn(electron, [".", `--remote-debugging-port=${CDP_PORT}`, "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"], {
  cwd: path.resolve(import.meta.dirname, ".."),
  env: { ...process.env, SPARKMD_UI_URL: `http://127.0.0.1:${PORT}/` },
  stdio: ["ignore", "pipe", "pipe"],
})
proc.stderr.on("data", (d) => {
  const s = String(d)
  if (/blocked non-local/.test(s)) console.log("[smoke] main log:", s.trim())
})

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
let ws
let seq = 0
const pending = new Map()
const netUrls = []
async function connect() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()
      const page = list.find((t) => t.type === "page")
      if (page) return page.webSocketDebuggerUrl
    } catch {
      /* electron still starting */
    }
    await wait(250)
  }
  throw new Error("no CDP page")
}
function send(method, params = {}) {
  const id = ++seq
  ws.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}
async function ev(expression) {
  const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + (r.exceptionDetails.exception?.description ?? ""))
  return r.result.value
}
async function shot(name, full = true) {
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false, fromSurface: true })
  fs.writeFileSync(path.join(SHOTS, `${name}.png`), Buffer.from(r.data, "base64"))
  return path.join(SHOTS, `${name}.png`)
}
const mouse = (type, x, y) => send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 })

const wsUrl = await connect()
const { WebSocket } = await import("node:worker_threads") // node has global WebSocket since 22
const WS = globalThis.WebSocket
ws = new WS(wsUrl)
await new Promise((r) => (ws.onopen = r))
ws.onmessage = (m) => {
  const msg = JSON.parse(m.data)
  if (msg.id && pending.has(msg.id)) {
    const p = pending.get(msg.id)
    pending.delete(msg.id)
    msg.error ? p.reject(new Error(msg.error.message)) : p.resolve(msg.result)
  } else if (msg.method === "Network.requestWillBeSent") netUrls.push(msg.params.request.url)
}
await send("Runtime.enable")
await send("Page.enable")
await send("Network.enable")
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false })
await wait(4000)

const report = {}
await ev("document.documentElement.classList.remove('dark')")
report.worklistRows = await ev("document.querySelectorAll('tbody tr').length")
report.disclaimer = await ev("document.body.innerText.includes('Research demo, not for clinical use')")
report.overflow = await ev("document.documentElement.scrollHeight > window.innerHeight")
report.tabs = await ev("document.querySelectorAll('[role=tab]').length")
await shot("01-worklist")

// Open the hero T0 study in the active empty slot.
const heroRow = await ev(`(() => { const rows=[...document.querySelectorAll('tbody tr')]; const r=rows.find(r=>r.innerText.includes('134503')); if(!r) return null; const b=r.getBoundingClientRect(); return {x:b.x+120,y:b.y+15} })()`)
report.heroRow = !!heroRow
if (heroRow) {
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: heroRow.x, y: heroRow.y, button: "left", clickCount: 1 })
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: heroRow.x, y: heroRow.y, button: "left", clickCount: 1 })
  await wait(2200)
}
report.url = await ev("location.hash")
report.hasCanvas = await ev("!!document.querySelector('canvas')")
report.canvasSize = await ev("(() => { const c=document.querySelector('canvas'); return c ? [c.width, c.height] : null })()")
report.overview = await ev("document.body.innerText.slice(0, 1400)")
await shot("02-study-3d")
await wait(1500)
await shot("03-study-3d-later")

report.nonLoopback = netUrls.filter((u) => !/^https?:\/\/(127\.0\.0\.1|localhost)(:|\/)/.test(u))
report.requests = netUrls.length

// Slices tab
const slicesBtn = await ev(`(() => { const b=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('CT slices')); if(!b) return null; const r=b.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2} })()`)
if (slicesBtn) {
  await mouse("mousePressed", slicesBtn.x, slicesBtn.y)
  await mouse("mouseReleased", slicesBtn.x, slicesBtn.y)
  await wait(900)
  report.sliceImgs = await ev("document.querySelectorAll('img[src*=stack_]').length")
  await shot("04-slices")
}
fs.writeFileSync(path.join(SHOTS, "report.json"), JSON.stringify(report, null, 1))
console.log(JSON.stringify(report, null, 1))
ws.close()
proc.kill()
await wait(300)
server.close()
process.exit(0)
