// Spark MD Electron smoke test over CDP (dev tool, not part of the product).
// Static-serves dist and proxies /api to the worker; drives the REAL electron/main.cjs.
// Usage: node tools/smoke.mjs [port] [shots-dir]
import http from "node:http"
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const PORT = Number(process.argv[2] ?? 8099)
const SHOTS = process.argv[3] ?? "/tmp/sparkmd-shots"
const UI = path.resolve(import.meta.dirname, "..", "dist")
const WORKER = process.env.WORKER_URL ?? "http://127.0.0.1:8100"
const API = process.env.MOCK_URL ?? WORKER // mock at 8101 or the real worker at 8100
const SERVE_STATIC = process.env.SERVE_STATIC !== "0"

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2", ".json": "application/json", ".glb": "model/gltf-binary" }

const server = http.createServer((req, res) => {
  if (req.url.startsWith("/api/")) {
    const target = new URL(req.url, API)
    const up = http.request({ hostname: target.hostname, port: target.port, path: target.pathname + target.search, method: req.method, headers: { ...req.headers, host: target.host } }, (ur) => {
      res.writeHead(ur.statusCode, ur.headers)
      ur.pipe(res)
    })
    up.on("error", () => {
      res.writeHead(502)
      res.end("api down")
    })
    req.pipe(up)
    if (target.pathname === "/api/events") req.socket.setTimeout(0)
    return
  }
  if (!SERVE_STATIC) {
    res.writeHead(404)
    return res.end()
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
const CDP_PORT = Number(process.env.CDP_PORT ?? 9333)
const electron = process.env.ELECTRON_BIN ?? path.resolve(import.meta.dirname, "..", "node_modules", ".bin", "electron")
const proc = spawn(electron, [".", `--remote-debugging-port=${CDP_PORT}`, "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"], {
  cwd: path.resolve(import.meta.dirname, ".."),
  env: { ...process.env, SPARKMD_UI_URL: SERVE_STATIC ? `http://127.0.0.1:${PORT}/` : WORKER + "/" },
  stdio: ["ignore", "pipe", "pipe"],
})
const logLines = []
proc.stdout.on("data", (d) => logLines.push(String(d)))
proc.stderr.on("data", (d) => logLines.push(String(d)))

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
let seq = 0
const pending = new Map()
const netUrls = []
async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()
      const page = list.find((t) => t.type === "page" && t.url.startsWith("http"))
      if (page) return page.webSocketDebuggerUrl
    } catch {
      /* electron still starting */
    }
    await wait(250)
  }
  throw new Error("no CDP page; log:\n" + logLines.join(""))
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
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png", fromSurface: true })
  fs.writeFileSync(path.join(SHOTS, `${name}.png`), Buffer.from(r.data, "base64"))
}
async function click(x, y) {
  for (const type of ["mousePressed", "mouseReleased"]) await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 })
}
async function clickText(text, nth = 0) {
  const pos = await ev(`(() => { const els=[...document.querySelectorAll('button,[role=tab]')].filter(e=>e.innerText.trim().includes(${JSON.stringify(text)})); const el=els[${nth}]; if(!el) return null; const r=el.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2} })()`)
  if (pos) await click(pos.x, pos.y)
  return !!pos
}

const wsUrl = await connect()
const ws = new WebSocket(wsUrl)
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
await send("Log.enable")
const consoleErrors = []
ws.addEventListener("message", (m) => {
  const msg = JSON.parse(m.data)
  if (msg.method === "Runtime.exceptionThrown") consoleErrors.push(msg.params.exceptionDetails.text + " " + (msg.params.exceptionDetails.exception?.description ?? ""))
})
await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false })
await wait(4000)

const report = {}
await ev("document.documentElement.classList.remove('dark')")
report.bodyStart = await ev("document.body.innerText.slice(0,600)")
report.rowsHtml = await ev("document.querySelector('tbody')?.innerHTML.slice(0,400) ?? null")
report.rows = await ev("document.querySelectorAll('tbody tr').length")
report.disclaimer = await ev("document.body.innerText.includes('Research demo, not for clinical use')")
report.overflow = await ev("document.documentElement.scrollHeight > window.innerHeight")
await shot("01-worklist")

const hero = await ev(`(() => { const r=[...document.querySelectorAll('tbody tr')].find(r=>r.innerText.includes(${JSON.stringify(process.env.HERO ?? "134503")})); if(!r) return null; const b=r.getBoundingClientRect(); return {x:b.x+120,y:b.y+15} })()`)
report.heroRow = !!hero
if (hero) {
  await click(hero.x, hero.y)
  await wait(2500)
}
report.url = await ev("location.hash")
report.canvas = await ev("(() => { const c=document.querySelector('canvas'); return c ? [c.width,c.height] : null })()")
report.studyBody = await ev("document.body.innerText.slice(600,2200)")
await shot("02-study")

report.slicesClicked = await clickText("CT slices")
await wait(900)
report.sliceImgs = await ev("document.querySelectorAll('img[src*=stack_]').length")
await shot("03-slices")

report.compareClicked = await clickText("Compare")
await wait(600)
await shot("04-compare")

report.slicesBack = await clickText("CT slices")
await wait(600)
report.toolbarBack = await clickText("3D anatomy")
await wait(1200)

// Chat: click a fixed phrase and wait for a streamed answer.
report.chatClicked = await clickText("Show me the nodule")
await wait(2500)
report.chatText = await ev("document.body.innerText.includes('Talk to the scan')")
report.chatBody = await ev("document.body.innerText.slice(0,600)")
await shot("05-chat")

// Confirm flow (real worker fixtures): press Confirm if present.
const confirmBtn = await ev(`(() => { const b=[...document.querySelectorAll('button')].find(b=>b.innerText.trim()==='Confirm' && !b.disabled); if(!b) return null; const r=b.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2} })()`)
report.confirmBtn = !!confirmBtn
if (confirmBtn) {
  await click(confirmBtn.x, confirmBtn.y)
  await wait(2500)
  await shot("06-confirmed")
  report.assessmentText = await ev("document.body.innerText.match(/Lung-RADS [0-9ABX]+/)?.[0] ?? null")
  report.afterConfirm = await ev("document.body.innerText.slice(700,1800)")
}

// Report sheet + Approve via a real mouse click.
report.sheetBtn = await clickText("Review & approve")
if (!report.sheetBtn) report.sheetBtn = await clickText("View approved reports")
await wait(900)
await shot("07-sheet")
const approveBtn = await ev(`(() => { const b=[...document.querySelectorAll('button')].find(b=>/^Approve$/.test(b.innerText.trim())); if(!b) return null; const r=b.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2,disabled:b.disabled} })()`)
report.approveBtn = approveBtn ? { ...approveBtn, disabled: !!approveBtn.disabled } : null
if (approveBtn && !approveBtn.disabled) {
  await click(approveBtn.x, approveBtn.y)
  await wait(1500)
  await shot("08-approved")
}
await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 })
await wait(500)

report.inboxClicked = await ev(`(() => { const a=[...document.querySelectorAll('a[href="#/inbox"]')][0]; if(!a) return false; const r=a.getBoundingClientRect(); window.__inboxPos={x:r.x+r.width/2,y:r.y+r.height/2}; return true })()`)
if (report.inboxClicked) { const p = await ev("window.__inboxPos"); await click(p.x, p.y) }
await wait(1200)
await shot("09-inbox")
report.inboxRows = await ev("document.querySelectorAll('li button').length")

report.nonLoopback = netUrls.filter((u) => !/^(https?|ws):\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/)/.test(u))
report.requests = netUrls.length
report.exceptions = consoleErrors.slice(0, 5)
report.log = logLines.filter((l) => /blocked|Error|error/.test(l)).slice(0, 8)
fs.writeFileSync(path.join(SHOTS, "report.json"), JSON.stringify(report, null, 1))
console.log(JSON.stringify(report, null, 1))
ws.close()
proc.kill()
await wait(300)
server.close()
process.exit(0)
