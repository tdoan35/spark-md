// Spark MD read-only probe against the REAL worker (dev tool, not part of the product).
// Never clicks Confirm / Approve / Review & approve — safe for real studies.
// Usage: node tools/patient-readonly.mjs [Vite port=5180] [shots-dir] (env: CDP_PORT)
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const PORT = Number(process.argv[2] ?? 5180)
const SHOTS = process.argv[3] ?? "/tmp/sparkmd-patient-page"
fs.mkdirSync(SHOTS, { recursive: true })
const CDP_PORT = Number(process.env.CDP_PORT ?? 9381)
const electron = path.resolve(import.meta.dirname, "..", "node_modules", ".bin", "electron")
const proc = spawn(electron, [".", `--remote-debugging-port=${CDP_PORT}`, "--ozone-platform=headless", "--use-angle=gl-egl", "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"], {
  cwd: path.resolve(import.meta.dirname, ".."),
  env: { ...process.env, SPARKMD_UI_URL: `http://127.0.0.1:${PORT}/`, DISPLAY: "" },
  stdio: ["ignore", "pipe", "pipe"],
})
const logLines = []
proc.stdout.on("data", (d) => logLines.push(String(d)))
proc.stderr.on("data", (d) => logLines.push(String(d)))
const cleanup = () => { try { proc.kill("SIGKILL") } catch {} }
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
  // Deny all API writes during this read-only navigation probe.
  const blockedWrites = []
  const fixtureResponses = new Map()
  const handler = ws.onmessage
  ws.onmessage = (m) => {
    handler(m)
    const d = JSON.parse(m.data)
    if (d.method === "Fetch.requestPaused") {
      const { requestId, request } = d.params
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
        blockedWrites.push(request.url)
        void send("Fetch.failRequest", { requestId, errorReason: "BlockedByClient" })
      } else if (fixtureResponses.has(new URL(request.url).pathname)) {
        void send("Fetch.fulfillRequest", { requestId, responseCode: 200,
          responseHeaders: [{ name: "Content-Type", value: "application/json" }],
          body: Buffer.from(JSON.stringify(fixtureResponses.get(new URL(request.url).pathname))).toString("base64"),
        })
      } else void send("Fetch.continueRequest", { requestId })
    }
  }
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/api/*" }] })
  const assert = (ok, message) => { if (!ok) throw new Error(message) }
  const until = async (expr) => {
    for (let i = 0; i < 100; i++) { if (await ev(`Boolean(${expr})`)) return; await wait(100) }
    throw new Error("Timed out: " + expr)
  }
  const pick = async (selector) => {
    assert(await ev(`(() => { const e=document.querySelector(${JSON.stringify(selector)}); if(!e) return false; e.click(); return true })()`), "Missing " + selector)
    await wait(400)
  }
  const screen = (tp) => until(`document.querySelector('[data-timepoint=${tp}][aria-current=page]')`)
  const tabs = () => ev("document.querySelectorAll('[data-tab]').length")
  const compare = () => ev("document.querySelector('button[aria-label=Compare]')?.getAttribute('data-state')")
  await until(`document.querySelector('[data-patient-id="100005"]')`)
  await pick('[data-patient-id="100005"]')
  await screen("T2")
  assert(await tabs() === 1, "Expected one patient tab")
  assert(await compare() === "on", "T2 should open Compare")
  report.currentStudy = "T2"
  await pick('[data-timepoint=T1]')
  await screen("T1")
  assert(await tabs() === 1, "Pill opened another tab")
  assert(await compare() === "on", "T1 should open Compare")
  assert(await ev("document.querySelectorAll('[data-timepoint]').length") === 3, "Missing screens")
  await wait(1200)
  await shot("100005-t1-compare")
  await pick('[data-timepoint=T0]')
  await screen("T0")
  assert(await ev(`document.querySelector('button[aria-label="CT slices"]')?.getAttribute('data-state')`) === "on", "Baseline changed")
  await ev("history.back()")
  await screen("T1")
  await ev("history.forward()")
  await screen("T0")
  assert(await tabs() === 1, "History duplicated tab")
  report.history = "passed"
  await pick('[aria-label="Open worklist in a new tab"]')
  await until(`document.querySelector('[data-patient-id="100005"]')`)
  await pick('[data-patient-id="100005"]')
  await screen("T2")
  assert(await ev("[...document.querySelectorAll('[data-tab]')].filter(e=>e.textContent.includes('100005')).length") === 1, "Worklist duplicated patient tab")
  report.tabReuse = "passed"
  await ev("location.hash='/'")
  await until(`document.querySelector('[data-patient-id="100285"]')`)
  await pick('[data-patient-id="100285"] [aria-label="Open T2 scan for patient 100285"]')
  await screen("T2")
  await until("document.body.innerText.includes('Review T1 first: growth needs a confirmed prior')")
  await shot("100285-prior-review-guide")
  await clickText("Review T1")
  await screen("T1")
  report.priorGuide = "passed"
  // Synthetic GET responses only: prove a matched prior reads the confirmed mean,
  // not its deliberately different proposal, and hides an unconfirmed measurement.
  const rows = await (await fetch(`http://127.0.0.1:${PORT}/api/worklist`)).json()
  const t0 = rows.find(r => r.patient_id === "100005" && r.timepoint === "T0")
  const t1 = rows.find(r => r.patient_id === "100005" && r.timepoint === "T1")
  const priorPath = `/api/studies/${t0.study_uid}/findings`
  const currentPath = `/api/studies/${t1.study_uid}/findings`
  const prior = await (await fetch(`http://127.0.0.1:${PORT}${priorPath}`)).json()
  const current = await (await fetch(`http://127.0.0.1:${PORT}${currentPath}`)).json()
  prior.nodules[0].mean_mm = 6.5
  prior.nodules[0].proposal.mean_mm = 99
  prior.nodules[0].confirmation.confirmed = true
  current.nodules[0].track_id = prior.nodules[0].track_id
  fixtureResponses.set(priorPath, prior)
  fixtureResponses.set(currentPath, current)
  await ev(`location.hash=${JSON.stringify(`/study/${t1.study_uid}`)}`)
  await send("Page.reload")
  await until("document.body.innerText.includes('prior 6.5 mm · T0 confirmed')")
  prior.nodules[0].confirmation.confirmed = false
  await send("Page.reload")
  await until("document.body.innerText.includes('No confirmed matched prior')")
  assert(!await ev("document.body.innerText.includes('prior 6.5 mm · T0 confirmed')"), "Unconfirmed prior leaked as confirmed")
  report.confirmedPriorFixture = "passed: confirmed mean, not proposal; unconfirmed hidden"
  report.blockedWrites = blockedWrites
  report.consoleErrors = consoleMsgs.filter(m => /\[exception\]|\[error\]/i.test(m))
  assert(!blockedWrites.length, "Unexpected write attempted")
  assert(!report.consoleErrors.length, "Console errors: " + report.consoleErrors.join("\n"))
  fs.writeFileSync(path.join(SHOTS, "report.json"), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))

} finally {
  ws?.close()
  cleanup()
}
