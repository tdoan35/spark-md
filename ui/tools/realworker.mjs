// Spark MD read-only probe against the REAL worker (dev tool, not part of the product).
// Never clicks Confirm / Approve / Review & approve — safe for real studies.
// Usage: node tools/realworker.mjs [port] [shots-dir]   (env: WORKER_URL, CDP_PORT)
import http from "node:http"
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const PORT = Number(process.argv[2] ?? 8098)
const SHOTS = process.argv[3] ?? "/tmp/sparkmd-realworker"
const UI = path.resolve(import.meta.dirname, "..", "dist")
const WORKER = process.env.WORKER_URL ?? "http://127.0.0.1:8100"

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2", ".json": "application/json", ".glb": "model/gltf-binary" }

const server = http.createServer((req, res) => {
  if (req.url.startsWith("/api/")) {
    const target = new URL(req.url, WORKER)
    const up = http.request({ hostname: target.hostname, port: target.port, path: target.pathname + target.search, method: req.method, headers: { ...req.headers, host: target.host } }, (ur) => {
      res.writeHead(ur.statusCode, ur.headers)
      ur.pipe(res)
    })
    up.on("error", () => { res.writeHead(502); res.end("api down") })
    req.pipe(up)
    if (target.pathname === "/api/events") req.socket.setTimeout(0)
    return
  }
  const raw = req.url.split("?")[0]
  const p = raw === "/" ? "/index.html" : raw
  const file = path.join(UI, p)
  if (!file.startsWith(UI) || !fs.existsSync(file)) { res.writeHead(404); return res.end("not found") }
  res.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "application/octet-stream" })
  fs.createReadStream(file).pipe(res)
})
await new Promise((r) => server.listen(PORT, "127.0.0.1", r))

fs.mkdirSync(SHOTS, { recursive: true })
const CDP_PORT = Number(process.env.CDP_PORT ?? 9341)
const electron = path.resolve(import.meta.dirname, "..", "node_modules", ".bin", "electron")
const proc = spawn(electron, [".", `--remote-debugging-port=${CDP_PORT}`, "--ozone-platform=headless", "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"], {
  cwd: path.resolve(import.meta.dirname, ".."),
  env: { ...process.env, SPARKMD_UI_URL: `http://127.0.0.1:${PORT}/`, DISPLAY: "" },
  stdio: ["ignore", "pipe", "pipe"],
})
const logLines = []
proc.stdout.on("data", (d) => logLines.push(String(d)))
proc.stderr.on("data", (d) => logLines.push(String(d)))
const cleanup = () => { try { proc.kill("SIGKILL") } catch {} ; server.close() }
process.on("exit", cleanup)
process.on("SIGINT", () => { cleanup(); process.exit(130) })

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
let seq = 0
const pending = new Map()
const netUrls = []
const consoleMsgs = []
let ws
async function connect() {
  for (let i = 0; i < 60; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()
      const page = list.find((t) => t.type === "page" && t.url.startsWith("http"))
      if (page) return page.webSocketDebuggerUrl
    } catch { /* electron still starting */ }
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
async function clickText(text) {
  const pos = await ev(`(() => { const els=[...document.querySelectorAll('button,[role=tab],a')]; const e=els.find(e=>e.innerText.trim()===${JSON.stringify(text)}); if(!e) return null; const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2} })()`)
  if (pos) await click(pos.x, pos.y)
  return !!pos
}

const report = {}
try {
  const wsUrl = await connect()
  ws = new WebSocket(wsUrl)
  await new Promise((r) => (ws.onopen = r))
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data)
    if (d.id && pending.has(d.id)) {
      const p = pending.get(d.id)
      pending.delete(d.id)
      d.error ? p.reject(new Error(d.error.message)) : p.resolve(d.result ?? d)
    }
    if (d.method === "Network.requestWillBeSent") netUrls.push(d.params.request.url)
    if (d.method === "Runtime.consoleAPICalled") consoleMsgs.push(`[${d.params.type}] ${d.params.args?.map((a) => a.value ?? a.description ?? "").join(" ")}`)
    if (d.method === "Log.entryAdded") consoleMsgs.push(`[log:${d.params.entry.level}] ${d.params.entry.text}`)
    if (d.method === "Runtime.exceptionThrown") consoleMsgs.push(`[exception] ${d.params.exceptionDetails.text} ${d.params.exceptionDetails.exception?.description ?? ""}`)
  }
  await send("Runtime.enable")
  await send("Page.enable")
  await send("Network.enable")
  await send("Log.enable")
  await send("Emulation.setDeviceMetricsOverride", { width: Number(process.env.WIDTH ?? 1920), height: Number(process.env.HEIGHT ?? 1080), deviceScaleFactor: 1, mobile: false })
  await wait(3000)

  await ev("document.documentElement.classList.remove('dark')")
  report.rows = await ev("document.querySelectorAll('tbody tr').length")
  report.disclaimer = await ev("document.body.innerText.includes('Research demo, not for clinical use')")
  await shot("01-worklist")

  // Open the hero study row — read-only navigation.
  const hero = await ev(`(() => { const r=[...document.querySelectorAll('tbody tr')].find(r=>/T0|T1|T2/.test(r.innerText)); if(!r) return null; const b=r.getBoundingClientRect(); return {x:b.x+120,y:b.y+15,text:r.innerText.slice(0,90)} })()`)
  report.heroRow = hero?.text ?? null
  if (hero) { await click(hero.x, hero.y); await wait(6000) }
  await shot("02-study-3d")

  report.studyHeader = await ev("document.body.innerText.slice(0, 300)")
  report.canvas = await ev(`(() => { const c=document.querySelector('canvas'); if(!c) return null; const gl=c.getContext('webgl2'); return {w:c.width,h:c.height,webgl2:!!gl} })()`)
  report.fps3d = await ev("new Promise(r=>{let n=0;const t0=performance.now();const f=()=>{n++;performance.now()-t0<1000?requestAnimationFrame(f):r(n)};requestAnimationFrame(f)})")

  // Select the first nodule row (flies the camera client-side; no /api/ask, no writes).
  const nod = await ev(`(() => { const els=[...document.querySelectorAll('button,[role=button]')].filter(e=>/mm/.test(e.innerText)); const e=els.find(e=>e.getBoundingClientRect().width>0); if(!e) return null; const r=e.getBoundingClientRect(); return {x:r.x+Math.min(70,r.width/2),y:r.y+r.height/2,label:e.innerText.slice(0,60)} })()`)
  report.noduleRow = nod?.label ?? null
  if (nod) { await click(nod.x, nod.y); await wait(2000); await shot("03-nodule") }

  report.slicesClick = await clickText("CT slices")
  await wait(3500)
  await shot("04-slices")
  report.slices = await ev(`(() => { const imgs=[...document.querySelectorAll('img')]; const loaded=imgs.filter(i=>i.complete&&i.naturalWidth>0); return {imgs:imgs.length,loaded:loaded.length,srcs:loaded.slice(0,3).map(i=>i.src.split('/').pop())} })()`)

  report.compareClick = await clickText("Compare")
  await wait(2000)
  await shot("05-compare")

  report.systemClick = await clickText("System")
  await wait(1500)
  await shot("06-system")
  report.netText = await ev(`(() => { const t=document.body.innerText; const i=t.indexOf('bytes'); return i<0?null:t.slice(Math.max(0,i-120),i+120) })()`)

  report.nonLoopback = netUrls.filter((u) => !/^http:\/\/(127\.0\.0\.1|localhost)/.test(u))
  report.consoleInteresting = consoleMsgs.filter((m) => /warn|error|align|mismatch|\[sparkmd/i.test(m)).slice(0, 20)
  console.log(JSON.stringify(report, null, 1))
} finally {
  cleanup()
}
