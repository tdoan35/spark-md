import type {
  AgentEvent,
  ApproveResult,
  AskEvent,
  ConfirmResult,
  Findings,
  JobProgress,
  NetStats,
  OutboxItem,
  Report,
  ReportKind,
  StudyDetail,
  WorklistRow,
} from "./types"

export { API_BASE } from "./config"
import { API_BASE } from "./config"

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `HTTP ${status}`)
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  })
  lastStatus.set(path, res.status)
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!res.ok) throw new ApiError(res.status, body, (body as { error?: string } | null)?.error)
  return body as T
}

// Diagnostic breadcrumb: the last response status per path, so a smoke run can tell "worker 502"
// apart from "empty payload". Costs one Map write per request; never sent anywhere.
export const lastStatus: Map<string, number> = new Map()
;(globalThis as unknown as { __sparkmdLast: Map<string, number> }).__sparkmdLast = lastStatus

export const api = {
  worklist: () => request<WorklistRow[]>("/api/worklist"),
  study: (uid: string) => request<StudyDetail>(`/api/studies/${encodeURIComponent(uid)}`),
  findings: (uid: string) => request<Findings>(`/api/studies/${encodeURIComponent(uid)}/findings`),
  reports: (uid: string) => request<Report[]>(`/api/studies/${encodeURIComponent(uid)}/reports`),
  agentLog: (studyUid?: string | null, limit = 200) =>
    request<AgentEvent[]>(
      `/api/agent-log?limit=${limit}${studyUid ? `&study_uid=${encodeURIComponent(studyUid)}` : ""}`,
    ),
  outbox: () => request<OutboxItem[]>("/api/outbox"),
  netstats: () => request<NetStats>("/api/netstats"),
  job: (jobId: string) => request<JobProgress>(`/api/jobs/${encodeURIComponent(jobId)}`),
  health: () => request<{ status: string }>("/api/health"),
  /** 09: canonical phrase recognition on the box. Returns {text, command, phrase, score}. */
  asr: async (wav: Blob) => {
    const res = await fetch(`${API_BASE}/api/asr`, { method: "POST", headers: { "content-type": "audio/wav" }, body: wav })
    return (await res.json()) as { text: string; command: string | null; phrase: string | null; score: number }
  },
  /** 09: spoken answer (24 kHz s16 PCM stream); optional, muted by default in the UI. */
  tts: async (text: string) => {
    const res = await fetch(`${API_BASE}/api/tts`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text }) })
    return res.ok
  },
  saveReport: (uid: string, kind: ReportKind, markdown: string) =>
    request<Report>(`/api/studies/${encodeURIComponent(uid)}/reports`, {
      method: "POST",
      body: JSON.stringify({ kind, markdown }),
    }),
  confirm: (noduleId: string, longMm: number, shortMm: number, by: string) =>
    request<ConfirmResult>(`/api/nodules/${encodeURIComponent(noduleId)}/confirm`, {
      method: "POST",
      body: JSON.stringify({ long_mm: longMm, short_mm: shortMm, by }),
    }),
  /**
   * 409 means two things (00 v0.8): already approved (body.already_approved === true → success
   * with the original approver) or nodules unconfirmed (body.error === "confirm_all_first" → error).
   */
  async approve(reportId: string, approver: string): Promise<ApproveResult> {
    try {
      return await request<ApproveResult>(`/api/reports/${encodeURIComponent(reportId)}/approve`, {
        method: "POST",
        body: JSON.stringify({ approver }),
      })
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const b = e.body as Partial<ApproveResult> & { error?: string } | null
        if (b && b.already_approved === true && b.report) {
          return { report: b.report, outbox_id: b.outbox_id ?? null, already_approved: true }
        }
        throw Object.assign(e, { userMessage: "Confirm all nodules before approving." })
      }
      throw e
    }
  },
  viewerCommand: (command: string, studyUid: string, noduleId?: string) =>
    request<unknown>("/api/viewer/command", {
      method: "POST",
      body: JSON.stringify({ command, study_uid: studyUid, ...(noduleId ? { nodule_id: noduleId } : {}) }),
    }),
  demoReset: (empty = false) =>
    request<unknown>("/api/demo/reset", { method: "POST", body: JSON.stringify({ empty }) }),
  demoDrop: (patientId: string, timepoint: string) =>
    request<unknown>("/api/demo/drop", {
      method: "POST",
      body: JSON.stringify({ patient_id: patientId, timepoint }),
    }),
  demoReplay: (patientId: string, timepoints?: string[], mode?: string, speed?: number) =>
    request<unknown>("/api/demo/replay", {
      method: "POST",
      body: JSON.stringify({ patient_id: patientId, timepoints, mode, speed }),
    }),
  demoStop: () => request<unknown>("/api/demo/stop", { method: "POST", body: "{}" }),
}

/** Parses our own `deltas|tool|done|error` SSE frames over a POST (EventSource cannot POST). */
export async function* ask(studyUid: string, text: string, signal?: AbortSignal): AsyncGenerator<AskEvent> {
  const res = await fetch(`${API_BASE}/api/ask`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ study_uid: studyUid, text }),
    signal,
  })
  if (!res.ok || !res.body) throw new ApiError(res.status, null, `ask failed (${res.status})`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ""
  while (true) {
    const { value, done } = await reader.read()
    if (done) return
    buf += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      let event = "message"
      let data = ""
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim()
        else if (line.startsWith("data:")) data += line.slice(5).trim()
      }
      if (event === "message" || !data) continue
      let parsed: unknown = {}
      try {
        parsed = JSON.parse(data)
      } catch {
        parsed = { text: data }
      }
      yield { event: event as AskEvent["event"], data: parsed as AskEvent["data"] }
    }
  }
}
