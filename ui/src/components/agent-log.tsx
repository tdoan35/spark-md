import { useLayoutEffect, useRef, useState } from "react"
import { Activity, ChevronDown, Terminal, Sparkles, Info } from "lucide-react"
import { useAgentLog } from "@/api/hooks"
import { useApp } from "@/lib/app-context"
import type { AgentEvent } from "@/api/types"
import { hm, relTime } from "@/lib/format"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

export function LiveDot({ status }: { status: "connecting" | "live" | "down" }) {
  const cls = status === "live" ? "bg-ok" : status === "connecting" ? "bg-warn" : "bg-alert"
  const label = status === "live" ? "Live" : status === "connecting" ? "Connecting" : "Offline"
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
      <span className={cn("relative flex size-1.5", status === "live" && "")}>
        <span className={cn("absolute inline-flex size-full rounded-full opacity-60", cls, status === "live" && "animate-ping")} />
        <span className={cn("relative inline-flex size-1.5 rounded-full", cls)} />
      </span>
      {label}
    </span>
  )
}

function SourceIcon({ source }: { source: AgentEvent["source"] }) {
  if (source === "agent_note") return <Sparkles className="size-3.5 text-run" />
  if (source === "tool_call") return <Terminal className="size-3.5 text-muted-foreground" />
  return <Info className="size-3.5 text-muted-foreground/70" />
}

function parseJson(s?: string | null): unknown {
  if (!s) return null
  try { return JSON.parse(s) } catch { return s }
}

export function EventRow({ ev, compact }: { ev: AgentEvent; compact?: boolean }) {
  const [open, setOpen] = useState(false)
  const args = (ev as AgentEvent & { args?: unknown }).args
  const payload = ev.payload ?? parseJson(ev.payload_json)
  const hasDetail = !!payload || !!args || !!ev.tool
  return (
    <div className={cn("group rounded-md px-2.5 py-2 hover:bg-muted/60", ev.source === "agent_note" && "bg-run-soft/40 dark:bg-run-soft/30")}>
      <button
        className="flex w-full items-start gap-2 text-left"
        onClick={() => hasDetail && setOpen((o) => !o)}
        disabled={!hasDetail}
        aria-expanded={hasDetail ? open : undefined}
      >
        <span className="mt-0.5 shrink-0"><SourceIcon source={ev.source} /></span>
        <span className="min-w-0 flex-1">
          <span className={cn("block break-words font-mono text-[13px] leading-relaxed text-foreground", ev.source === "agent_note" && "font-sans text-[15px]")}>
            {ev.message}
          </span>
          {!compact && (
            <span className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
              <span className="tabular-nums">{hm(ev.ts)}</span>
              {ev.duration_ms != null && <span>{ev.duration_ms} ms</span>}
            </span>
          )}
          {ev.status != null && ev.status >= 400 && <span className="mt-1 block text-xs font-medium text-alert">Request failed · {ev.status}</span>}
        </span>
        {hasDetail && <ChevronDown className={cn("mt-0.5 size-3 shrink-0 text-muted-foreground/50 transition-transform", open && "rotate-180")} />}
      </button>
      {open && (
        <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted/60 p-2 font-mono text-xs leading-relaxed text-muted-foreground">
          {JSON.stringify({ tool: ev.tool, status: ev.status, args, payload }, null, 2)}
        </pre>
      )}
    </div>
  )
}

// Only transport health checks and audit-log writes are routine. Clinical tools,
// agent notes, and unsuccessful health checks always remain in the main trace.
function isRoutine(ev: AgentEvent) {
  return ev.source === "tool_call" && (
    ev.tool === "log_event" || /^log_event(?:\s|\(|$)/.test(ev.message) ||
    (ev.status === 200 && /^GET \/api\/health\b/.test(ev.message))
  )
}

function eventGroups(events: AgentEvent[]) {
  const groups: { routine: boolean; events: AgentEvent[] }[] = []
  for (const ev of events) {
    const routine = isRoutine(ev)
    const last = groups[groups.length - 1]
    if (routine && last?.routine) last.events.push(ev)
    else groups.push({ routine, events: [ev] })
  }
  return groups
}

function RoutineEvents({ events, compact }: { events: AgentEvent[]; compact?: boolean }) {
  const failed = events.filter((ev) => ev.status != null && ev.status >= 400)
  return (
    <details className="rounded-md px-2.5 py-2 text-xs text-muted-foreground">
      <summary className="cursor-pointer leading-relaxed">
        {events.length} routine health / audit event{events.length === 1 ? "" : "s"}
        {failed.length > 0 && <span className="ml-1 text-alert"> · {failed.length} failed ({[...new Set(failed.map((ev) => ev.status))].join(", ")})</span>}
      </summary>
      <div className="mt-1 space-y-1">{events.map((ev) => <EventRow key={ev.id} ev={ev} compact={compact} />)}</div>
    </details>
  )
}

/**
 * Stick-to-bottom agent log: instant scroll (smooth breaks stickiness mid-burst);
 * a "N new events ↓" pill when the reader has scrolled up.
 */
export function AgentLog({ studyUid, className, compact }: { studyUid?: string | null; className?: string; compact?: boolean }) {
  const { status } = useApp().sse
  const { data, isLoading } = useAgentLog(studyUid ?? null, compact ? 80 : 300)
  const ref = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const previous = useRef<{ studyUid: typeof studyUid; id: number | null }>({ studyUid, id: null })
  const [unseen, setUnseen] = useState(0)
  const [fullTrace, setFullTrace] = useState(false)
  const lastId = data?.at(-1)?.id ?? null

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const changedStudy = previous.current.studyUid !== studyUid
    const previousId = previous.current.id
    const added = previousId == null ? 0 : (data ?? []).filter((ev) => ev.id > previousId).length
    previous.current = { studyUid, id: lastId }
    if (changedStudy) {
      stick.current = true
      setUnseen(0)
    }
    if (stick.current) el.scrollTop = el.scrollHeight
    else if (added > 0) setUnseen((n) => n + added)
  }, [data, lastId, studyUid, fullTrace])

  const onScroll = () => {
    const el = ref.current
    if (!el) return
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32
    if (stick.current) setUnseen(0)
  }

  return (
    <div className={cn("relative flex min-h-0 flex-col", className)}>
      <div className="mb-1.5 flex items-center gap-2">
        <Activity className="size-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{studyUid ? "Agent activity" : "Global activity"}</span>
        <button className="ml-auto text-xs text-muted-foreground hover:text-foreground" aria-pressed={fullTrace} onClick={() => setFullTrace((v) => !v)}>{fullTrace ? "Collapse routine" : "Full trace"}</button>
        <LiveDot status={status} />
      </div>
      <div ref={ref} onScroll={onScroll} aria-label="Agent event log" className="min-h-0 flex-1 space-y-1 overflow-y-auto rounded-md border bg-background/40 p-1.5">
        {isLoading && <div className="px-2 py-3 text-xs text-muted-foreground">Loading the log…</div>}
        {!isLoading && !data?.length && <div className="px-2 py-3 text-xs text-muted-foreground">No activity yet.</div>}
        {eventGroups(data ?? []).map((group) => group.routine && !fullTrace
          ? <RoutineEvents key={group.events[0].id} events={group.events} compact={compact} />
          : group.events.map((ev) => <EventRow key={ev.id} ev={ev} compact={compact} />))}
        {data?.length ? (
          <div className="px-2 pb-1 pt-1 text-xs text-muted-foreground">{data.length} events · live from the worker</div>
        ) : null}
      </div>
      {unseen > 0 && (
        <Button
          size="sm"
          variant="secondary"
          className="absolute bottom-3 left-1/2 h-8 -translate-x-1/2 gap-1 text-xs shadow-md"
          onClick={() => {
            stick.current = true
            setUnseen(0)
            const el = ref.current
            if (el) el.scrollTop = el.scrollHeight
          }}
        >
          {unseen} new event{unseen === 1 ? "" : "s"} ↓
        </Button>
      )}
    </div>
  )
}

export function ActivityPage() {
  return (
    <div className="flex h-full min-h-0 flex-col px-6 pb-4 pt-5">
      <div className="mb-3">
        <h1 className="flex items-center gap-2 text-[15px] font-semibold"><Activity className="size-4 text-muted-foreground" /> Agent activity</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">Every agent request is logged by the worker middleware — not narrated after the fact.</p>
      </div>
      <div className="min-h-0 flex-1">
        <AgentLog className="h-full" />
      </div>
    </div>
  )
}

export function StudyActivity({ studyUid }: { studyUid: string }) {
  const { data } = useAgentLog(studyUid, 200)
  let latest: AgentEvent | undefined
  for (let i = (data?.length ?? 0) - 1; i >= 0; i--) {
    if (data![i].source === "agent_note") {
      latest = data![i]
      break
    }
  }
  return (
    <div className="flex h-full min-h-0 flex-col gap-2 pt-3">
      {latest && (
        <div className="rounded-md bg-run-soft/50 px-2.5 py-2 dark:bg-run-soft/30">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-run"><Sparkles className="size-3.5" /> Latest note · {relTime(latest.ts)}</div>
          <div className="max-h-40 overflow-y-auto text-[15px] leading-relaxed">{latest.message}</div>
        </div>
      )}
      <AgentLog studyUid={studyUid} className="min-h-0 flex-1" compact />
    </div>
  )
}
