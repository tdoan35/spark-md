import { API_BASE } from "./client"
import { qk } from "./keys"
import { viewerBus } from "./viewer-bus"
import { toast } from "sonner"
import type { AgentEvent, NetStats, SseEventType, SseEvents } from "./types"
import type { QueryClient } from "@tanstack/react-query"

/** Append one agent event to a log cache (dedupe by id, cap 2000). */
export function appendLog(qc: QueryClient, studyUid: string | null, ev: AgentEvent) {
  const key = qk.agentLog(studyUid)
  qc.setQueryData<AgentEvent[]>(key, (old) => {
    const base = old ?? []
    if (base.some((e) => e.id === ev.id)) return base
    const next = [...base, ev].sort((a, b) => a.id - b.id)
    return next.length > 2000 ? next.slice(next.length - 2000) : next
  })
}

function mergeLog(qc: QueryClient, studyUid: string | null, ev: AgentEvent) {
  // A study-scoped event also belongs in the global list.
  appendLog(qc, studyUid, ev)
  if (studyUid) appendLog(qc, null, ev)
}

export const handlers: { [K in SseEventType]: (qc: QueryClient, d: SseEvents[K]) => void } = {
  agent_log: (qc, d) => mergeLog(qc, d.study_uid, d),
  worklist_changed: (qc, d) => {
    qc.invalidateQueries({ queryKey: qk.worklist })
    if (d.study_uid) qc.invalidateQueries({ queryKey: qk.study(d.study_uid) })
    if (d.reason === "reset") qc.invalidateQueries()
  },
  study_updated: (qc, d) => {
    qc.invalidateQueries({ queryKey: qk.study(d.study_uid) })
    qc.invalidateQueries({ queryKey: qk.findings(d.study_uid) })
    qc.invalidateQueries({ queryKey: qk.worklist })
  },
  job_progress: (qc, d) => {
    qc.setQueryData(qk.study(d.study_uid), (s: unknown) =>
      s && typeof s === "object" ? { ...(s as object), job: d } : s,
    )
    qc.invalidateQueries({ queryKey: qk.study(d.study_uid) })
  },
  viewer_command: (_qc, d) => viewerBus.emit(d),
  report_saved: (qc, d) => {
    qc.invalidateQueries({ queryKey: qk.reports(d.study_uid) })
    qc.invalidateQueries({ queryKey: qk.worklist })
    qc.invalidateQueries({ queryKey: qk.study(d.study_uid) })
  },
  outbox_delivered: (qc, d) => {
    qc.invalidateQueries({ queryKey: qk.outbox })
    qc.invalidateQueries({ queryKey: qk.worklist })
    toast.success(`Delivered to ${d.recipient}`, { description: d.subject ?? d.patient_id })
  },
  net_stats: (qc, d) => qc.setQueryData<NetStats>(qk.netstats, d),
  demo_state: (qc, d) => qc.setQueryData(["demo_state"], d),
}

export type SseStatus = "connecting" | "live" | "down"

/**
 * One EventSource for the app, mounted above the router. `onEvent` lets
 * components subscribe to transient events without the query cache.
 */
export function connectSse(
  qc: QueryClient,
  onEvent: (type: SseEventType, data: unknown) => void,
  onStatus: (s: SseStatus) => void,
): () => void {
  let es: EventSource | null = null
  let retry = 0
  let retryTimer: number | undefined
  let lastId = 0
  let wasDown = false
  let closed = false

  const open = () => {
    if (closed) return
    onStatus(retry > 0 ? "connecting" : "connecting")
    es = new EventSource(`${API_BASE}/api/events`)
    es.onopen = () => {
      retry = 0
      onStatus("live")
      if (wasDown) {
        wasDown = false
        qc.invalidateQueries()
      }
    }
    const types: SseEventType[] = [
      "agent_log",
      "worklist_changed",
      "study_updated",
      "job_progress",
      "viewer_command",
      "report_saved",
      "outbox_delivered",
      "net_stats",
      "demo_state",
    ]
    for (const t of types) {
      es.addEventListener(t, (e) => {
        const msg = e as MessageEvent
        const id = Number(msg.lastEventId)
        if (Number.isFinite(id) && id > 0) lastId = id
        let data: unknown
        try {
          data = JSON.parse(msg.data)
        } catch {
          return
        }
        ;(handlers as Record<string, (qc: QueryClient, d: unknown) => void>)[t](qc, data)
        onEvent(t, data)
      })
    }
    es.onerror = () => {
      wasDown = true
      onStatus("down")
      if (es && es.readyState === EventSource.CLOSED) {
        es.close()
        es = null
        retry = Math.min(retry + 1, 5)
        retryTimer = window.setTimeout(open, 2000)
      }
    }
  }
  open()

  return () => {
    closed = true
    clearTimeout(retryTimer)
    es?.close()
    void lastId
  }
}
