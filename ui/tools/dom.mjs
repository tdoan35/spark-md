// Layout probe over CDP: real electron/main.cjs, DOM rects for key regions.
import http from "node:http"
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"
const UI = path.resolve(import.meta.dirname, "..", "dist")
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".json": "application/json" }
const server = http.createServer((req, res) => {
  if (req.url.startsWith("/api/")) {
    const t = new URL(req.url, process.env.WORKER_URL ?? "http://127.0.0.1:8100")
    const up = http.request({ hostname: t.hostname, port: t.port, path: t.pathname + t.search, method: req.method, headers: { ...req.headers, host: t.host } }, (ur) => { res.writeHead(ur.statusCode, ur.headers); ur.pipe(res) })
    up.on("error", () => { res.writeHead(502); res.end() })
    req.pipe(up)
    if (t.pathname === "/api/events") req.socket.setTimeout(0)
    return
  }
  let p = req.url.split("?")[0]
  if (p === "/") p = "/index.html"
  const f = path.join(UI, p)
  if (!fs.statSync(f, { throwIfNoEntry: false })?.isFile()) { res.writeHead(404); return res.end() }
  res.writeHead(200, { "content-type": MIME[path.extname(f)] ?? "application/octet-stream" })
  fs.createReadStream(f).pipe(res)
})
const PORT = 8098
await new Promise((r) => server.listen(PORT, "127.0.0.1", r))
console.log("server up")
const route = process.argv[2] ?? "#!/study/fixture-T0" // hash goes after the served path; no leading slash here
const width = Number(process.argv[3] ?? 1920), height = Number(process.argv[4] ?? 1080)
console.log("route:", route)
const e = spawn(path.resolve(import.meta.dirname, "..", "node_modules", ".bin", "electron"), [".", "--remote-debugging-port=9334"], { cwd: path.resolve(import.meta.dirname, ".."), env: { ...process.env, SPARKMD_UI_URL: `http://127.0.0.1:${PORT}/${route}` }, stdio: ["ignore", "pipe", "pipe"] })
e.stdout.on("data", (d) => console.log("[main]", String(d).trim()))
e.stderr.on("data", (d) => console.log("[main-err]", String(d).trim()))
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
let page
for (let i = 0; i < 40 && !page; i++) {
  await wait(300)
  try { page = (await (await fetch("http://127.0.0.1:9334/json/list")).json()).find((t) => t.url.startsWith("http")) } catch { /* starting */ }
}
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((r) => (ws.onopen = r))
let id = 0
const pend = new Map()
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id) } }
const send = (method, params = {}) => { const i = ++id; ws.send(JSON.stringify({ id: i, method, params })); return new Promise((r) => pend.set(i, r)) }
await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false })
await wait(3500)
for (const m of ["Page.enable", "Runtime.enable"]) await send(m)
const nav = await send("Runtime.evaluate", { expression: "({url: location.href, title: document.title, html: document.documentElement.outerHTML.slice(0,300)})", returnByValue: true })
console.log("nav:", JSON.stringify(nav.result.result.value))
const r = await send("Runtime.evaluate", {
  expression: `(() => {
 const rect = s => { const e=document.querySelector(s); if(!e) return null; const b=e.getBoundingClientRect(); return [Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height)] };
 return { main: rect('main'), surface: rect('main > div'), header: rect('header'), sidebar: rect('aside'), footer: rect('footer'),
   chat: rect('[role=separator]'), canvas: rect('canvas'),
   grids: [...document.querySelectorAll('main div')].filter(d=>getComputedStyle(d).display==='grid').slice(0,3).map(d=>getComputedStyle(d).gridTemplateColumns),
   chatW: getComputedStyle(document.documentElement).getPropertyValue('--chat-w').trim(),
   vScroll: document.documentElement.scrollHeight - window.innerHeight, hScroll: document.documentElement.scrollWidth - window.innerWidth,
   text: document.body.innerText.slice(0, 300) }})()`,
  returnByValue: true,
})
console.log(JSON.stringify(r.result.result.value, null, 1))
ws.close()
e.kill()
server.close()
process.exit(0)
