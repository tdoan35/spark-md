// Spark MD mock worker (spec 08 item M). stdlib only, deterministic, loopback.
// Implements the 00 v0.8 routes the UI consumes, an SSE stream, and a scripted time machine.
// Placeholder numbers: it exists to build the UI against, not to be a product.
import http from "node:http"
import zlib from "node:zlib"
import { studies } from "./fixtures.mjs"

const PORT = Number(process.env.MOCK_PORT ?? 8101)
const SPEED = Number(process.env.MOCK_SPEED ?? 1)
const HERO = "134503"

// ---------------------------------------------------------------- state
let seq = 1
let eventSeq = 0
const subscribers = new Set()
const events = []

const state = {
  studies: new Map(), // uid -> study record
  nods: new Map(), // nodule_id -> nodule row
  orders: new Map(), // patient -> [uid]
  reports: [],
  outbox: [],
  demo: { replaying: false, patient_id: null, timepoint: null, speed: SPEED, mode: "live", waiting_for: null, phase: null },
  net: { tx_bytes: 0, rx_bytes: 0, since: new Date().toISOString() },
}
let reportSeq = 1
let outboxSeq = 1
let jobSeq = 1

const now = () => new Date().toISOString()
function emit(event, payload) {
  eventSeq += 1
  const frame = `id: ${eventSeq}\nevent: ${event}\ndata: ${JSON.stringify(payload)}\n\n`
  events.push(frame)
  if (events.length > 2000) events.shift()
  for (const res of subscribers) res.write(frame)
}
function agentEvent(source, message, studyUid, extra = {}) {
  const ev = { id: seq++, ts: now(), study_uid: studyUid ?? null, source, message, ...extra }
  agentEvents.push(ev)
  if (agentEvents.length > 3000) agentEvents.shift()
  emit("agent_log", ev)
  return ev
}
const agentEvents = []

function row(s) {
  const a = s.assessment
  return {
    study_uid: s.study_uid,
    patient_id: s.patient_id,
    timepoint: s.timepoint,
    day_offset: s.day_offset,
    status: s.status,
    priority: s.priority,
    priority_reason: s.priority_reason,
    lung_rads: a ? a.lung_rads : null,
    received_at: s.received_at,
    reports_awaiting: state.reports.filter((r) => r.study_uid === s.study_uid && r.status === "draft").length,
  }
}

const PR = { "0": 0, "1": 1, "2": 2, "3": 3, "4A": 4, "4B": 5, "4X": 6 }
function worklist() {
  return [...state.studies.values()]
    .map(row)
    .sort((a, b) => {
      const pa = a.priority === "urgent" ? 0 : a.priority === "elevated" ? 1 : 2
      const pb = b.priority === "urgent" ? 0 : b.priority === "elevated" ? 1 : 2
      if (pa !== pb) return pa - pb
      const la = a.lung_rads ? PR[a.lung_rads] ?? -1 : -1
      const lb = b.lung_rads ? PR[b.lung_rads] ?? -1 : -1
      if (la !== lb) return lb - la
      const ra = a.received_at.localeCompare(b.received_at)
      if (ra !== 0) return ra
      return a.study_uid.localeCompare(b.study_uid)
    })
}

function seriesFor(s) {
  return [
    { series_uid: `${s.study_uid}.1`, series_number: 1, modality: "CT", kernel: "BONE", kernel_list: ["BONE", "BONE"], slice_thickness: 1.25, n_instances: 151, image_type: "ORIGINAL\\PRIMARY\\AXIAL", axial: true, path: `/tmp/spark/inbox/${s.study_uid}/CT1`, eligible: false, eligible_reason: "sharp kernel", fallback: false, selected: false, select_reason: null },
    { series_uid: `${s.study_uid}.2`, series_number: 2, modality: "CT", kernel: "STANDARD", kernel_list: ["STANDARD"], slice_thickness: 1.25, n_instances: s.stack_count || 151, image_type: "ORIGINAL\\PRIMARY\\AXIAL", axial: true, path: `/tmp/spark/inbox/${s.study_uid}/CT2`, eligible: true, eligible_reason: "soft-kernel thin axial", fallback: false, selected: s.job != null, select_reason: s.job ? "soft-kernel thin axial" : null },
    { series_uid: `${s.study_uid}.3`, series_number: 3, modality: "CT", kernel: null, kernel_list: [], slice_thickness: 5, n_instances: 1, image_type: "DERIVED\\SECONDARY\\LOCALIZER", axial: false, path: `/tmp/spark/inbox/${s.study_uid}/CT3`, eligible: false, eligible_reason: "localizer", fallback: false, selected: false, select_reason: null },
  ]
}

function growthFor(cur, prior) {
  // Placeholder rules output: the mock only formats numbers a real worker would compute.
  if (!prior) return null
  const delta = +((cur.mean_mm ?? 0) - (prior.mean_mm ?? 0)).toFixed(1)
  const days = cur.day_offset != null && prior.day_offset != null ? cur.day_offset - prior.day_offset : null
  const per12 = days ? +((days > 365.25 ? (delta * 365.25) / days : delta)).toFixed(1) : null
  const v1 = (Math.PI / 6) * Math.pow(prior.mean_mm ?? 0, 3)
  const v2 = (Math.PI / 6) * Math.pow(cur.mean_mm ?? 0, 3)
  const vdt = delta > 0 && v2 > v1 && days ? Math.round((days * Math.log(2)) / Math.log(v2 / v1)) : null
  return {
    study_uid: prior.study_uid,
    interval_days: days,
    mean_mm: prior.mean_mm,
    volume_mm3: +v1.toFixed(1),
    delta_mean_mm: delta,
    growth_per_12mo_mm: per12,
    growth_normalized: !!days && days > 365.25,
    vdt_days: vdt,
    growing: delta > 1.5,
  }
}

function assess(s) {
  const confirmed = [...state.nods.values()].filter((n) => n.study_uid === s.study_uid)
  if (!confirmed.length || confirmed.some((n) => n.mean_mm == null)) return null
  const driver = confirmed.reduce((m, n) => ((n.mean_mm ?? 0) > (m.mean_mm ?? 0) ? n : m))
  const m = driver.mean_mm
  const isNew = (n) => !n.prior
  let cat = "1"
  let rule = "lungrads-v2022"
  if (m < 6 && confirmed.every(isNew)) cat = "2"
  else if (m < 6) cat = "2"
  else if (m >= 6 && m < 8) cat = isNew(driver) ? "4A" : "3"
  else if (m >= 8 && m < 15) cat = "4A"
  else if (m >= 15) cat = "4B"
  if (driver.prior && driver.prior.growing && cat !== "4X") cat = "4B"
  return {
    lung_rads: cat,
    rule_id: `${cat}-${m >= 15 ? "S" : "S"}-${m.toFixed(1)}mm`,
    driver_nodule_id: driver.nodule_id,
    management: cat === "4B" ? "Diagnostic chest CT; consider PET/CT and tissue sampling" : cat === "4A" ? "May consider PET/CT or tissue sampling; 3-month follow-up" : cat === "3" ? "6-month LDCT" : "12-month LDCT screening",
    rules_version: "lungrads-v2022",
    growth: driver.prior,
  }
}

function findingsFor(s) {
  const list = [...state.nods.values()].filter((n) => n.study_uid === s.study_uid)
  const pending = list.filter((n) => n.mean_mm == null).map((n) => n.nodule_id)
  const assessment = pending.length ? null : assess(s)
  const stack = s.stack_count
    ? {
        count: s.stack_count,
        spacing_mm: 2,
        z_mm: Array.from({ length: s.stack_count }, (_, i) => +(-218.3 + i * 2).toFixed(1)),
        size: [512, 512],
        url_pattern: `/api/studies/${s.study_uid}/assets/stack_{i}.jpg`,
        index_digits: 3,
        nodule_slices: list.map((n, i) => ({
          nodule_id: n.nodule_id,
          index: Math.floor((s.stack_count * (i + 1)) / (list.length + 1)),
          box_px: [212, 196, 72, 72],
          half_range: 2,
        })),
      }
    : null
  return {
    study_uid: s.study_uid,
    patient_id: s.patient_id,
    timepoint: s.timepoint,
    day_offset: s.day_offset,
    series_uid: `${s.study_uid}.2`,
    pipeline_version: "mock-0.1.0",
    lung: { mask_source: "threshold", volume_ml: 4120.4 },
    nodules: list.map((n) => ({
      nodule_id: n.nodule_id,
      track_id: n.track_id,
      lobe: n.lobe,
      center_mm: n.center_mm,
      det_score: n.det_score,
      long_mm: n.long_mm,
      short_mm: n.short_mm,
      mean_mm: n.mean_mm,
      volume_mm3: n.volume_mm3,
      proposal: n.proposal_long != null ? { source: "A7", long_mm: n.proposal_long, short_mm: n.proposal_short, mean_mm: n.proposal_mean, box_mean_mm: n.box_mean } : null,
      confirmation: n.confirmed_at ? { confirmed: true, edited: n.edited, by: n.confirmed_by, at: n.confirmed_at } : { confirmed: false, edited: false, by: null, at: null },
      mean_hu: n.mean_hu,
      type: n.type,
      prior: n.prior,
    })),
    pending_confirmation: pending,
    assessment,
    extras: {
      emphysema_laa950_pct: 7.1,
      vertebra: { label: "T12", mean_hu: 165, flag: null },
      cac: { experimental: true, agatston: null },
    },
    assets: {
      lung_mesh: `/api/studies/${s.study_uid}/assets/lung.glb`,
      nodule_mesh: `/api/studies/${s.study_uid}/assets/nodules.glb`,
      key_slices: list.map((n, i) => ({ name: `key_axial_${n.nodule_id}.png`, url: `/api/studies/${s.study_uid}/assets/key_axial_${i + 1}.png`, plane: "axial", nodule_id: n.nodule_id, box_px: [212, 196, 72, 72] })),
      slice_stack: stack,
    },
    placeholder: true,
  }
}

// ---------------------------------------------------------------- seeding
function seedStudy(spec, status, receivedAt) {
  const s = {
    ...spec,
    status,
    priority: "routine",
    priority_reason: null,
    received_at: receivedAt ?? now(),
    selected: false,
    job: null,
    assessment: null,
  }
  state.studies.set(s.study_uid, s)
  if (!state.orders.has(s.patient_id)) state.orders.set(s.patient_id, [])
  state.orders.get(s.patient_id).push(s.study_uid)
  for (const n of s.nodules) {
    state.nods.set(n.nodule_id, {
      nodule_id: n.nodule_id,
      study_uid: s.study_uid,
      track_id: n.track_id,
      lobe: n.lobe,
      center_mm: n.center_mm,
      det_score: n.det_score,
      mean_hu: n.mean_hu,
      type: n.type,
      box_mean: n.box_mean,
      proposal_long: n.long,
      proposal_short: n.short,
      proposal_mean: n.long != null ? +((n.long + n.short) / 2).toFixed(1) : null,
      long_mm: null,
      short_mm: null,
      mean_mm: null,
      volume_mm3: null,
      confirmed_by: null,
      confirmed_at: null,
      edited: false,
      prior: null,
    })
  }
  return s
}

function priorsOf(s) {
  const order = state.orders.get(s.patient_id) ?? []
  const idx = order.indexOf(s.study_uid)
  return order
    .slice(0, Math.max(0, idx))
    .map((u) => state.studies.get(u))
    .filter(Boolean)
    .map((p) => ({ study_uid: p.study_uid, timepoint: p.timepoint, day_offset: p.day_offset, status: p.status, lung_rads: p.assessment?.lung_rads ?? null }))
}

function linkPrior(s) {
  // Growth uses only confirmed priors (00 v0.8 / 06).
  const order = state.orders.get(s.patient_id) ?? []
  const idx = order.indexOf(s.study_uid)
  const priorUid = order[idx - 1]
  const priorS = priorUid ? state.studies.get(priorUid) : null
  for (const n of [...state.nods.values()].filter((x) => x.study_uid === s.study_uid)) {
    n.prior = null
    if (priorS && priorS.status !== "received" && priorS.status !== "organized") {
      const pn = [...state.nods.values()].find((x) => x.study_uid === priorUid && x.track_id === n.track_id && x.mean_mm != null)
      if (pn) n.prior = growthFor({ mean_mm: n.mean_mm, day_offset: s.day_offset }, { study_uid: priorUid, mean_mm: pn.mean_mm, day_offset: priorS.day_offset })
    }
  }
}

function reset() {
  for (const s of state.studies.values()) {
    if (s.job?.timer) clearTimeout(s.job.timer)
  }
  state.studies.clear()
  state.nods.clear()
  state.orders.clear()
  state.reports = []
  state.outbox = []
  agentEvents.length = 0
  state.demo = { replaying: false, patient_id: null, timepoint: null, speed: SPEED, mode: "live", waiting_for: null, phase: null }
  // All fixtures exist from the start so every timepoint is reachable for UI work;
  // the mock time machine still drops T1/T2 on top of them.
  for (const spec of studies) seedStudy(spec, "received", new Date(Date.now() - 7200e3).toISOString())
  const s = state.studies.get(studies.find((x) => x.patient_id === "900102").study_uid)
  s.status = "awaiting_confirmation"
  s.job = { job_id: `job-${jobSeq++}`, study_uid: s.study_uid, state: "running", stage: "detect", stage_index: 3, elapsed_s: 6, study_status: "analyzing" }
  agentEvent("system", "Worker started · mock mode · placeholder numbers", null)
  agentEvent("agent_note", "Worklist scanned: 5 studies waiting.", null)
}

// ---------------------------------------------------------------- jobs
const STAGES = ["organize", "select", "volume", "detect", "segment", "characterize", "match", "rules", "render"]
const JOB_STEP = 320 / SPEED

function runJob(uid) {
  const s = state.studies.get(uid)
  if (!s) return
  if (s.job && s.job.state === "running") return
  const job = { job_id: `job-${jobSeq++}`, study_uid: uid, state: "running", stage: STAGES[0], stage_index: 0, elapsed_s: 0 }
  s.job = job
  s.status = "analyzing"
  emit("study_updated", { study_uid: uid, status: s.status })
  emit("worklist_changed", { reason: "status", study_uid: uid })
  agentEvent("tool_call", `run_analysis(${uid}) -> 200`, uid, { tool: "run_analysis", status: 200 })
  let i = 0
  const tick = () => {
    if (s.job !== job) return
    i += 1
    job.elapsed_s += JOB_STEP / 1000
    if (i < STAGES.length) {
      job.stage = STAGES[i]
      job.stage_index = i
      emit("job_progress", { ...job })
      job.timer = setTimeout(tick, JOB_STEP)
    } else {
      job.state = "done"
      job.stage = "render"
      job.stage_index = STAGES.length - 1
      s.status = "awaiting_confirmation"
      emit("job_progress", { ...job })
      emit("study_updated", { study_uid: uid, status: s.status })
      emit("worklist_changed", { reason: "status", study_uid: uid })
      const pending = [...state.nods.values()].filter((n) => n.study_uid === uid)
      agentEvent("agent_note", `${s.timepoint}: ${pending.length} candidate nodule${pending.length === 1 ? "" : "s"} proposed. Holding at the confirmation gate — no sizes, growth or category reported until the radiologist confirms.`, uid)
      if (state.demo.replaying) { state.demo.waiting_for = "confirm"; emit("demo_state", state.demo) }
    }
  }
  job.timer = setTimeout(tick, JOB_STEP)
}

function confirmNodule(id, body) {
  const n = state.nods.get(id)
  if (!n) return { status: 404, body: { error: "nodule_not_found" } }
  const s = state.studies.get(n.study_uid)
  let long = Number(body.long_mm)
  let short = body.short_mm == null || body.short_mm === "" ? long : Number(body.short_mm)
  if (n.proposal_long == null && (body.short_mm == null || body.short_mm === "")) short = long
  const by = String(body.by ?? "").trim()
  if (!by) return { status: 422, body: { error: "approver_required" } }
  if (!Number.isFinite(long) || !Number.isFinite(short) || !(short > 0) || short > long || long > 100) {
    return { status: 422, body: { error: "invalid_diameter", detail: "require 0 < short <= long <= 100" } }
  }
  long = Math.round(long * 10) / 10
  short = Math.round(short * 10) / 10
  n.long_mm = long
  n.short_mm = short
  n.mean_mm = Math.round(((long + short) / 2) * 10) / 10
  n.volume_mm3 = +((Math.PI / 6) * Math.pow(n.mean_mm, 3)).toFixed(1)
  n.confirmed_by = by
  n.confirmed_at = now()
  n.edited = n.proposal_long != null && (long !== n.proposal_long || short !== n.proposal_short)
  linkPrior(s)
  const remaining = [...state.nods.values()].filter((x) => x.study_uid === s.study_uid && x.mean_mm == null)
  agentEvent("system", `Confirmed ${id}: ${long.toFixed(1)} × ${short.toFixed(1)} mm → mean ${n.mean_mm.toFixed(1)} mm by ${by}`, s.study_uid)
  if (!remaining.length) {
    s.assessment = assess(s)
    s.status = "analyzed"
    emit("study_updated", { study_uid: s.study_uid, status: s.status })
    emit("worklist_changed", { reason: "status", study_uid: s.study_uid })
    agentEvent("agent_note", `Confirmed by ${by}; drafting reports. Category ${s.assessment.lung_rads} from the rules engine (${s.assessment.rules_version}).`, s.study_uid)
    setTimeout(() => draftReports(s.study_uid), 600 / SPEED)
    if (state.demo.replaying) { state.demo.waiting_for = "agent"; emit("demo_state", state.demo) }
  }
  return {
    status: 200,
    body: {
      nodule_id: id,
      long_mm: long,
      short_mm: short,
      mean_mm: n.mean_mm,
      volume_mm3: n.volume_mm3,
      edited: n.edited,
      confirmed_by: by,
      confirmed_at: n.confirmed_at,
      all_confirmed: !remaining.length,
      assessment: s.assessment,
    },
  }
}

const RADIOLOGY = (s) => `## Chest CT — Lung cancer screening

**Patient ${s.patient_id} · ${s.timepoint} · Day ${s.day_offset ?? "—"}**

### Findings

${[...state.nods.values()]
  .filter((n) => n.study_uid === s.study_uid)
  .map((n) => `- **${n.nodule_id.replace(/^.*-/, "")}** (${n.lobe}): ${n.mean_mm?.toFixed(1)} mm mean diameter (${n.long_mm?.toFixed(1)} × ${n.short_mm?.toFixed(1)} mm), ${n.type.replace("_", "-")}, ${n.mean_hu} HU.${n.prior ? ` Prior ${n.prior.mean_mm?.toFixed(1)} mm, Δ ${n.prior.delta_mean_mm > 0 ? "+" : ""}${n.prior.delta_mean_mm?.toFixed(1)} mm over ${n.prior.interval_days} days${n.prior.growth_normalized ? " (normalized to 12 mo)" : ""}, VDT ${n.prior.vdt_days ?? "n/a"} days.` : " Baseline — no prior comparison."}`)
  .join("\n")}

### Assessment

Lung-RADS **${s.assessment?.lung_rads}** — ${s.assessment?.management}.

> Rule ${s.assessment?.rule_id} · ${s.assessment?.rules_version}. Diameters were confirmed by a radiologist; category computed by code.

*Research demo, not for clinical use.*`

const LETTER = (s) => `Dear clinician,

Re: ${s.patient_id}, screening CT ${s.timepoint} (day ${s.day_offset ?? "—"}).

Lung-RADS category **${s.assessment?.lung_rads}** on this exam. ${s.assessment?.management}.

The report is available in the EHR inbox for review.

— Spark MD (draft)
*Research demo, not for clinical use.*`

function draftReports(uid) {
  const s = state.studies.get(uid)
  if (!s) return
  for (const [kind, md] of [["radiology", RADIOLOGY(s)], ["pcp_letter", LETTER(s)]]) {
    const r = { report_id: `R${reportSeq++}`, study_uid: uid, kind, markdown: md, version: 1, status: "draft", approved_by: null, approved_at: null }
    state.reports.push(r)
    emit("report_saved", { study_uid: uid, report_id: r.report_id, kind, version: 1, status: "draft" })
    agentEvent("tool_call", `save_report(${uid}, ${kind}) -> 200`, uid, { tool: "save_report", status: 200 })
  }
  if (s.assessment?.lung_rads === "4B") {
    s.priority = "elevated"
    s.priority_reason = `Lung-RADS ${s.assessment.lung_rads} · growing nodule`
    emit("worklist_changed", { reason: "priority", study_uid: uid })
  }
  s.status = "reported"
  emit("study_updated", { study_uid: uid, status: s.status })
  emit("worklist_changed", { reason: "status", study_uid: uid })
  agentEvent("agent_note", "Drafts ready for review: radiology report and PCP letter. Approval is a human click — no tool can approve.", uid)
  if (state.demo.replaying) { state.demo.waiting_for = "approve"; emit("demo_state", state.demo) }
}

function dropTimepoint(patientId, timepoint) {
  const spec = studies.find((x) => x.patient_id === patientId && x.timepoint === timepoint)
  if (!spec) return { status: 404, body: { error: "no_such_timepoint" } }
  if (state.studies.has(spec.study_uid)) return { status: 409, body: { error: "already_dropped" } }
  seedStudy(spec, "organized")
  emit("worklist_changed", { reason: "received", study_uid: spec.study_uid })
  state.demo.timepoint = timepoint
  emit("demo_state", state.demo)
  agentEvent("system", `New study ${patientId} ${timepoint} landed in the inbox`, spec.study_uid)
  setTimeout(() => {
    agentEvent("agent_note", `Triage ${patientId} ${timepoint}: selecting the thin soft-kernel axial series.`, spec.study_uid)
    agentEvent("tool_call", `select_series(${spec.study_uid}) -> 200`, spec.study_uid, { tool: "select_series", status: 200 })
    setTimeout(() => runJob(spec.study_uid), 500 / SPEED)
  }, 400 / SPEED)
  return { status: 200, body: { ok: true, study_uid: spec.study_uid } }
}

function replay(patientId, timepoints, speed, mode) {
  state.demo = { replaying: true, patient_id: patientId, timepoint: null, speed: speed ?? SPEED, mode: mode === "cached" ? "cached" : "live", waiting_for: null, phase: "dropping" }
  emit("demo_state", state.demo)
  const tps = timepoints?.length ? timepoints : ["T0", "T1", "T2"]
  let i = 0
  const step = () => {
    if (!state.demo.replaying || state.demo.patient_id !== patientId) return
    if (i >= tps.length) {
      state.demo.replaying = false
      state.demo.waiting_for = null
      state.demo.phase = "done"
      emit("demo_state", state.demo)
      return
    }
    const tp = tps[i++]
    state.demo.phase = `drop ${tp}`
    state.demo.timepoint = tp
    dropTimepoint(patientId, tp)
    state.demo.waiting_for = "confirm"
    emit("demo_state", state.demo)
    // The harness waits for the human; the demo script only advances if the timepoint was already done.
    const uid = studies.find((x) => x.patient_id === patientId && x.timepoint === tp)?.study_uid
    const wait = () => {
      const s = uid ? state.studies.get(uid) : null
      if (!state.demo.replaying) return
      if (s && ["awaiting_confirmation", "analyzed", "reported", "approved"].includes(s.status) && state.demo.waiting_for !== "confirm") {
        setTimeout(step, 500 / SPEED)
      } else setTimeout(wait, 700 / SPEED)
    }
    setTimeout(wait, 700 / SPEED)
  }
  step()
  return { status: 200, body: { ok: true } }
}

// ---------------------------------------------------------------- assets
function crc32(buf) {
  let c
  const table = crc32.table ?? (crc32.table = Array.from({ length: 256 }, (_, n) => {
    c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    return c >>> 0
  }))
  let crc = 0xffffffff
  for (let i = 0; i < buf.length; i++) crc = table[(crc ^ buf[i]) & 0xff] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}
function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const t = Buffer.from(type, "ascii")
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(Buffer.concat([t, data])))
  return Buffer.concat([len, t, data, crc])
}
function png(width, height, gray) {
  const raw = Buffer.alloc((width * 3 + 1) * height)
  for (let y = 0; y < height; y++) {
    raw[y * (width * 3 + 1)] = 0
    for (let x = 0; x < width; x++) {
      const v = gray(x, y)
      const o = y * (width * 3 + 1) + 1 + x * 3
      raw[o] = v
      raw[o + 1] = v
      raw[o + 2] = v
    }
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8
  ihdr[9] = 2
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))])
}
// Lung-window-ish synthetic axial: two dark lungs in a body, a bright nodule disc.
function slice(variant, index) {
  return png(512, 512, (x, y) => {
    const dx = (x - 256) / 180
    const dy = (y - 236) / 210
    const inBody = dx * dx + dy * dy < 1
    if (!inBody) return 0
    const lx = (x - (256 - 88)) / 68
    const ly = (y - 240) / 150
    const rx = (x - (256 + 88)) / 66
    const ry = (y - 242) / 148
    const inLung = lx * lx + ly * ly < 1 || rx * rx + ry * ry < 1
    const ndx = x - 212 - 36
    const ndy = y - 196 - 36 + (variant - 1) * 12 + Math.sin(index / 6) * 2
    if (inLung) {
      const nod = ndx * ndx + ndy * ndy < 30 * 30 ? 150 : 0
      return 18 + nod + ((x * 7 + y * 3 + index) % 9)
    }
    return 90 + ((x * 5 + y * 11 + variant) % 14)
  })
}

// glTF 2.0 binary: a lung volume stand-in (two ellipsoids) and one sphere per nodule.
function glb(kind, s) {
  const parts = []
  const json = { asset: { version: "2.0" }, scenes: [{ nodes: [] }], scene: 0, nodes: [], meshes: [], accessors: [], bufferViews: [], buffers: [], materials: [] }
  const bin = []
  let binLen = 0
  let accessor = 0
  const addMesh = (name, positions, indices) => {
    const posBuf = Buffer.from(new Float32Array(positions).buffer)
    const idxBuf = Buffer.from(new Uint32Array(indices).buffer)
    const posView = json.bufferViews.length
    json.bufferViews.push({ buffer: 0, byteOffset: binLen, byteLength: posBuf.length, target: 34962 })
    bin.push(posBuf)
    binLen += posBuf.length
    binLen += (4 - (binLen % 4)) % 4
    const idxView = json.bufferViews.length
    json.bufferViews.push({ buffer: 0, byteOffset: binLen, byteLength: idxBuf.length, target: 34963 })
    bin.push(idxBuf)
    binLen += idxBuf.length
    binLen += (4 - (binLen % 4)) % 4
    const a = accessor++
    json.accessors.push({ bufferView: posView, componentType: 5126, count: positions.length / 3, type: "VEC3", min: [Math.min(...positions.filter((_, i) => i % 3 === 0)), Math.min(...positions.filter((_, i) => i % 3 === 1)), Math.min(...positions.filter((_, i) => i % 3 === 2))], max: [Math.max(...positions.filter((_, i) => i % 3 === 0)), Math.max(...positions.filter((_, i) => i % 3 === 1)), Math.max(...positions.filter((_, i) => i % 3 === 2))] })
    const ia = accessor++
    json.accessors.push({ bufferView: idxView, componentType: 5125, count: indices.length, type: "SCALAR" })
    json.meshes.push({ name, primitives: [{ attributes: { POSITION: a }, indices: ia }] })
  }
  // RAS -> three inside the mock too: x = -r, y = s, z = a
  if (kind === "lung") {
    for (const side of [-1, 1]) {
      const [nx, ny, nz] = [0, 0, 0, 0, 0, 0]
      void nx, ny, nz
      const pts = ellipsoid([-side * 78, 30, 0], [58, 130, 72])
      const idx = []
      const rings = 14, segs = 22
      const n = (rings + 1) * (segs + 1)
      const pos = []
      for (let r = 0; r <= rings; r++) {
        const th = (r / rings) * Math.PI
        for (let sg = 0; sg <= segs; sg++) {
          const ph = (sg / segs) * Math.PI * 2
          pos.push(
            pts.c[0] + Math.sin(th) * Math.cos(ph) * pts.r[0],
            pts.c[1] + Math.cos(th) * pts.r[1],
            pts.c[2] + Math.sin(th) * Math.sin(ph) * pts.r[2],
          )
        }
      }
      for (let r = 0; r < rings; r++)
        for (let sg = 0; sg < segs; sg++) {
          const a = r * (segs + 1) + sg
          idx.push(a, a + segs + 1, a + 1, a + 1, a + segs + 1, a + segs + 2)
        }
      addMesh(side < 0 ? "lung_R" : "lung_L", pos, idx)
      void n
    }
  } else {
    for (const nb of s.nodules) {
      const c = nb.center_mm ?? [0, 0, 0]
      const radius = (nb.long ?? 5) / 2
      const pts = ellipsoid([-c[0], c[1], c[2]], [radius, radius, radius])
      void pts
      const rings = 10, segs = 14
      const pos = []
      const idx = []
      for (let r = 0; r <= rings; r++) {
        const th = (r / rings) * Math.PI
        for (let sg = 0; sg <= segs; sg++) {
          const ph = (sg / segs) * Math.PI * 2
          pos.push((-c[0]) + Math.sin(th) * Math.cos(ph) * radius, c[1] + Math.cos(th) * radius, c[2] + Math.sin(th) * Math.sin(ph) * radius)
        }
      }
      for (let r = 0; r < rings; r++)
        for (let sg = 0; sg < segs; sg++) {
          const a = r * (segs + 1) + sg
          idx.push(a, a + segs + 1, a + 1, a + 1, a + segs + 1, a + segs + 2)
        }
      addMesh(nb.nodule_id, pos, idx)
    }
  }
  json.nodes = json.meshes.map((m, i) => ({ name: m.name, mesh: i }))
  json.scenes[0].nodes = json.nodes.map((_, i) => i)
  const binBuf = Buffer.concat(bin)
  json.buffers = [{ byteLength: binBuf.length }]
  let jsonBuf = Buffer.from(JSON.stringify(json), "utf8")
  while (jsonBuf.length % 4) jsonBuf = Buffer.concat([jsonBuf, Buffer.from(" ")])
  const total = 12 + 8 + jsonBuf.length + 8 + binBuf.length
  const out = Buffer.alloc(12)
  out.writeUInt32LE(0x46546c67, 0)
  out.writeUInt32LE(2, 4)
  out.writeUInt32LE(total, 8)
  const hdr = Buffer.alloc(8)
  hdr.writeUInt32LE(jsonBuf.length, 0)
  hdr.writeUInt32LE(0x4e4f534a, 4)
  const bhd = Buffer.alloc(8)
  bhd.writeUInt32LE(binBuf.length, 0)
  bhd.writeUInt32LE(0x004e4942, 4)
  return Buffer.concat([out, hdr, jsonBuf, bhd, binBuf])
}
function ellipsoid(c, r) {
  return { c, r }
}

// ---------------------------------------------------------------- http
function json(res, code, obj) {
  const body = JSON.stringify(obj)
  res.writeHead(code, { "content-type": "application/json", "cache-control": "no-store" })
  res.end(body)
}
function readBody(req) {
  return new Promise((resolve) => {
    let b = ""
    req.on("data", (c) => (b += c))
    req.on("end", () => {
      try {
        resolve(b ? JSON.parse(b) : {})
      } catch {
        resolve({})
      }
    })
  })
}
const loopback = (req) => ["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(req.socket.remoteAddress)
const caller = (req) => (req.headers["x-sparkmd-caller"] === "agent" || !loopback(req) ? "agent" : "ui")

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, "http://127.0.0.1")
  const p = u.pathname
  const m = req.method
  const asAgent = caller(req) === "agent"
  try {
    if (p === "/api/events") {
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache", "x-accel-buffering": "no", connection: "keep-alive" })
      res.write(": connected\nretry: 3000\n\n")
      const last = Number(req.headers["last-event-id"] ?? 0)
      for (const f of events) {
        const id = Number(f.match(/^id: (\d+)/m)?.[1] ?? 0)
        if (id > last) res.write(f)
      }
      subscribers.add(res)
      req.on("close", () => subscribers.delete(res))
      return
    }
    if (p === "/api/health") return json(res, 200, { status: "ok", mock: true, version: "mock-0.1.0" })
    if (p === "/api/worklist") return json(res, 200, worklist())
    if (p === "/api/outbox") return json(res, 200, [...state.outbox].sort((a, b) => b.ts.localeCompare(a.ts)))
    if (p === "/api/netstats") {
      const stats = { tx_bytes: 0, rx_bytes: 0, since: state.net.since, interfaces: [{ name: "enp1s0f0", tx_bytes: 0, rx_bytes: 0 }, { name: "wlp1s0", tx_bytes: 0, rx_bytes: 0 }], link_up: true }
      res.writeHead(200, { "content-type": "application/json" })
      return res.end(JSON.stringify(stats))
    }
    if (p === "/api/agent-log") {
      const uid = u.searchParams.get("study_uid")
      const limit = Number(u.searchParams.get("limit") ?? 200)
      const list = agentEvents.filter((e) => !uid || e.study_uid === uid).slice(-limit)
      return json(res, 200, list)
    }
    if (p === "/api/demo/state") return json(res, 200, state.demo)
    if (p === "/api/demo/reset" && m === "POST") {
      if (asAgent) return json(res, 403, { error: "loopback_only" })
      reset()
      emit("worklist_changed", { reason: "reset", study_uid: null })
      emit("demo_state", state.demo)
      return json(res, 200, { ok: true })
    }
    if (p === "/api/demo/drop" && m === "POST") {
      if (asAgent) return json(res, 403, { error: "loopback_only" })
      const b = await readBody(req)
      const r = dropTimepoint(b.patient_id, b.timepoint)
      return json(res, r.status, r.body)
    }
    if (p === "/api/demo/replay" && m === "POST") {
      if (asAgent) return json(res, 403, { error: "loopback_only" })
      const b = await readBody(req)
      const r = replay(b.patient_id, b.timepoints, b.speed, b.mode)
      return json(res, r.status, r.body)
    }
    if (p === "/api/demo/stop" && m === "POST") {
      state.demo.replaying = false
      state.demo.waiting_for = null
      emit("demo_state", state.demo)
      return json(res, 200, { ok: true })
    }
    if (p === "/api/ask" && m === "POST") {
      const b = await readBody(req)
      const s = state.studies.get(b.study_uid)
      const f = s ? findingsFor(s) : null
      res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" })
      const q = String(b.text ?? "").toLowerCase()
      let answer
      const n = f?.nodules?.[0]
      if (!f) answer = "No findings for this study yet."
      else if (q.includes("compare") || q.includes("last year"))
        answer = n?.prior
          ? `Nodule ${n.nodule_id.split("-").pop()} measured **${n.mean_mm?.toFixed(1)} mm** today; the prior (${n.prior.study_uid.slice(-2)}, day ${n.prior.interval_days} interval) was ${n.prior.mean_mm?.toFixed(1)} mm. ${n.prior.delta_mean_mm > 0 ? "+" : ""}${n.prior.delta_mean_mm?.toFixed(1)} mm over ${n.prior.interval_days} days${n.prior.growth_normalized ? ", normalized to 12 mo" : ""}; VDT ${n.prior.vdt_days ?? "n/a"} days.`
          : "This is a baseline exam — no prior comparison exists."
      else if (q.includes("why") || q.includes("flag"))
        answer = n
          ? `Flagged at Lung-RADS **${f.assessment?.lung_rads ?? "pending"}**: ${n.mean_mm?.toFixed(1)} mm ${n.type?.replace("_", "-")} in the ${n.lobe}, ${n.mean_hu} HU${n.prior ? `, ${n.prior.delta_mean_mm > 0 ? "+" : ""}${n.prior.delta_mean_mm?.toFixed(1)} mm over ${n.prior.interval_days} days` : ""}. Rule ${f.assessment?.rule_id ?? "pending"}.`
          : "No flagged nodule here."
      else if (q.includes("reset")) answer = "View reset to the anterior home position."
      else answer = n ? `Nodule ${n.nodule_id.split("-").pop()} sits in the ${n.lobe}: **${n.mean_mm?.toFixed(1)} mm** mean diameter, ${n.mean_hu} HU.` : "Nothing to show for this study."
      const parts = answer.split(" ")
      let i = 0
      const tick = () => {
        if (i >= parts.length) {
          res.write(`event: done\ndata: {"ok":true}\n\n`)
          return res.end()
        }
        res.write(`event: delta\ndata: ${JSON.stringify({ text: (i ? " " : "") + parts[i++] })}\n\n`)
        setTimeout(tick, 45 / SPEED)
      }
      if (q.includes("show")) res.write(`event: tool\ndata: ${JSON.stringify({ tool: "viewer_command", args: { command: "show_nodule" } })}\n\n`)
      tick()
      return
    }
    const studyMatch = p.match(/^\/api\/studies\/([^/]+)(\/.*)?$/)
    if (studyMatch) {
      const uid = decodeURIComponent(studyMatch[1])
      const rest = studyMatch[2] ?? ""
      const s = state.studies.get(uid)
      if (!s && rest !== "") return json(res, 404, { error: "study_not_found" })
      if (!rest) {
        if (!s) return json(res, 404, { error: "study_not_found" })
        return json(res, 200, { ...row(s), series: seriesFor(s), priors: priorsOf(s), job: s.job })
      }
      if (rest === "/findings") {
        if (!s) return json(res, 404, { error: "study_not_found" })
        const f = findingsFor(s)
        if (asAgent) return json(res, 200, { ...f, nodules: f.nodules.map((n) => ({ ...n, proposal: undefined })) })
        return json(res, 200, f)
      }
      if (rest === "/reports") return json(res, 200, state.reports.filter((r) => r.study_uid === uid))
      if (rest === "/analyze" && m === "POST") {
        if (!s) return json(res, 404, { error: "study_not_found" })
        runJob(uid)
        await new Promise((r) => setTimeout(r, 60))
        return json(res, 200, { job_id: s.job.job_id, state: s.job.state, stage: s.job.stage, elapsed_s: s.job.elapsed_s, study_status: s.status })
      }
      if (rest === "/assets/lung.glb") {
        const b = glb("lung", s ?? { nodules: [] })
        res.writeHead(200, { "content-type": "model/gltf-binary", "content-length": b.length })
        return res.end(b)
      }
      if (rest === "/assets/nodules.glb") {
        const b = glb("nodules", s ?? { nodules: [] })
        res.writeHead(200, { "content-type": "model/gltf-binary", "content-length": b.length })
        return res.end(b)
      }
      const key = rest.match(/^\/assets\/key_axial_(\d+)\.png$/)
      if (key) {
        const b = slice(Number(key[1]), 10)
        res.writeHead(200, { "content-type": "image/png", "cache-control": "max-age=60" })
        return res.end(b)
      }
      const st = rest.match(/^\/assets\/stack_(\d+)\.jpg$/)
      if (st) {
        const idx = Number(st[1])
        const b = png(256, 256, (x, y) => {
          const dx = (x - 128) / 92
          const dy = (y - 120) / 104
          if (dx * dx + dy * dy >= 1) return 0
          const lx = (x - (128 - 44)) / 34
          const ly = (y - 122) / 74
          const rx = (x - (128 + 44)) / 33
          const ry = (y - 123) / 73
          const inLung = lx * lx + ly * ly < 1 || rx * rx + ry * ry < 1
          return inLung ? 18 + ((x + y + idx) % 8) : 92 + ((x * 3 + idx) % 12)
        })
        res.writeHead(200, { "content-type": "image/png", "cache-control": "max-age=60" })
        return res.end(b)
      }
      return json(res, 404, { error: "not_found" })
    }
    const confirm = p.match(/^\/api\/nodules\/([^/]+)\/confirm$/)
    if (confirm && m === "POST") {
      if (asAgent) return json(res, 403, { error: "confirm_loopback_only" })
      const b = await readBody(req)
      const r = confirmNodule(decodeURIComponent(confirm[1]), b)
      return json(res, r.status, r.body)
    }
    const approve = p.match(/^\/api\/reports\/([^/]+)\/approve$/)
    if (approve && m === "POST") {
      if (asAgent) return json(res, 403, { error: "approve_loopback_only" })
      const r = state.reports.find((x) => x.report_id === decodeURIComponent(approve[1]))
      if (!r) return json(res, 404, { error: "report_not_found" })
      const b = await readBody(req)
      const s = state.studies.get(r.study_uid)
      const unconfirmed = [...state.nods.values()].some((x) => x.study_uid === r.study_uid && x.mean_mm == null)
      if (unconfirmed) return json(res, 409, { error: "confirm_all_first", already_approved: false })
      if (r.status === "approved")
        return json(res, 409, { report: r, outbox_id: state.outbox.find((o) => o.report_id === r.report_id)?.id ?? null, already_approved: true })
      r.status = "approved"
      r.approved_by = String(b.approver ?? "").trim() || "Dr. Joyce (demo)"
      r.approved_at = now()
      // Like the worker: only a pcp_letter is delivered (outbox row + outbox_delivered); payload = the approved report.
      let o = null
      if (r.kind === "pcp_letter") {
        o = { id: outboxSeq++, ts: now(), report_id: r.report_id, study_uid: r.study_uid, patient_id: s?.patient_id ?? null, recipient: "Primary care physician", subject: "Lung CT screening follow-up", payload: { ...r } }
        state.outbox.push(o)
        emit("outbox_delivered", { outbox_id: o.id, report_id: r.report_id, study_uid: r.study_uid, patient_id: o.patient_id, recipient: o.recipient, subject: o.subject })
      }
      agentEvent("system", `Approved ${r.kind.replace("_", " ")} by ${r.approved_by}${o ? ` — delivered to ${o.recipient}` : ""}`, r.study_uid)
      emit("report_saved", { study_uid: r.study_uid, report_id: r.report_id, kind: r.kind, version: r.version, status: "approved" })
      if (s && state.reports.filter((x) => x.study_uid === s.study_uid).every((x) => x.status === "approved")) {
        s.status = "approved"
        emit("study_updated", { study_uid: s.study_uid, status: s.status })
        emit("worklist_changed", { reason: "status", study_uid: s.study_uid })
      }
      return json(res, 200, { report: r, outbox_id: o?.id ?? null, already_approved: false })
    }
    const rep = p.match(/^\/api\/studies\/([^/]+)\/reports$/)
    if (rep && m === "POST") {
      const b = await readBody(req)
      const r = { report_id: `R${reportSeq++}`, study_uid: decodeURIComponent(rep[1]), kind: b.kind, markdown: b.markdown, version: 1, status: "draft", approved_by: null, approved_at: null }
      state.reports.push(r)
      return json(res, 200, r)
    }
    const job = p.match(/^\/api\/jobs\/([^/]+)$/)
    if (job) {
      const s = [...state.studies.values()].find((x) => x.job?.job_id === decodeURIComponent(job[1]))
      if (!s) return json(res, 404, { error: "job_not_found" })
      return json(res, 200, s.job)
    }
    return json(res, 404, { error: "not_found", path: p })
  } catch (e) {
    console.error(e)
    return json(res, 500, { error: String(e) })
  }
})

const ping = setInterval(() => {
  for (const res of subscribers) res.write(": ping\n\n")
}, 15000)
server.on("close", () => clearInterval(ping))
reset()
server.listen(PORT, "127.0.0.1", () => console.log(`[mock] spark-md mock worker on http://127.0.0.1:${PORT} (speed ${SPEED})`))
