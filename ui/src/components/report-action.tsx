import { AlertTriangle, ChevronRight, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useAgentLog, useInterval, useReports } from "@/api/hooks"
import type { AgentEvent, Report, ReportKind, StudyDetail } from "@/api/types"

/** No agent event for this long after the confirm → the drafting run is treated as stalled. */
const STALL_MS = 120_000
const KINDS: ReportKind[] = ["radiology", "pcp_letter"]

type Drafting = { t0: number | null; last: number | null; step: string; failed: boolean }

/**
 * The drafting run since the latest "Confirmed by …" event, read from the agent's own log
 * (no timers pretending progress): hook accepted → get_findings → agent note → save_report.
 */
function draftingRun(log: AgentEvent[] | undefined): Drafting {
  const events = log ?? []
  let start = -1
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].message.startsWith("Confirmed by")) {
      start = i
      break
    }
  }
  const since = start >= 0 ? events.slice(start) : []
  let step = "Starting agent"
  let failed = false
  for (const e of since) {
    if (/^Agent hook (failed|not configured)/.test(e.message)) failed = true
    if (e.message.startsWith("Agent hook accepted")) step = "Agent started"
    if (e.tool === "get_findings") step = "Reading findings"
    if (e.source === "agent_note" || e.tool === "log_event") step = "Writing report & PCP letter"
    if (e.tool === "save_report") step = "Saving drafts"
  }
  const ts = (e: AgentEvent | undefined) => (e ? Date.parse(e.ts) : null)
  return { t0: ts(since[0]), last: ts(since[since.length - 1]), step, failed }
}

const clock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

function DraftingButton({ run }: { run: Drafting }) {
  // Ticks only while this state is mounted.
  const now = useInterval(() => Date.now(), 1000) ?? Date.now()
  const stalled = run.failed || (run.last != null && now - run.last > STALL_MS)
  if (stalled)
    return (
      <Button size="sm" variant="outline" disabled className="h-8 gap-1.5 border-warn/50 text-xs text-warn disabled:opacity-100" title={run.failed ? "The agent hook failed after the diameters were confirmed. See Agent activity." : "No agent activity for 2 minutes since the diameters were confirmed. See Agent activity."}>
        <AlertTriangle className="size-3.5" /> Agent not responding
      </Button>
    )
  return (
    <div className="flex items-center gap-2" role="status" aria-live="polite">
      <span className="text-[11px] tabular-nums text-muted-foreground">
        {run.step}
        {run.t0 != null && ` · ${clock(now - run.t0)}`}
      </span>
      <Button size="sm" disabled className="h-8 gap-1.5 text-xs disabled:opacity-100">
        <Loader2 className="size-3.5 animate-spin" /> Drafting Reports
      </Button>
    </div>
  )
}

/** Header action: always present, its state follows what the radiologist has to do next. */
export function ReportAction({ study, onOpen }: { study: StudyDetail; onOpen: () => void }) {
  const { data: reports } = useReports(study.study_uid)
  const { data: log } = useAgentLog(study.study_uid, 200)
  const latest = KINDS.map((k) => reports?.filter((r) => r.kind === k).sort((a, b) => b.version - a.version)[0]).filter((r): r is Report => !!r)
  const drafts = latest.filter((r) => r.status === "draft").length

  if (drafts)
    return (
      <Button size="sm" className="h-8 gap-1 text-xs" onClick={onOpen}>
        Review Reports{latest.length - drafts > 0 && ` · ${drafts} left`} <ChevronRight className="size-3.5" />
      </Button>
    )
  if (latest.length)
    return (
      <Button size="sm" variant="outline" className="h-8 text-xs" onClick={onOpen}>
        View approved reports
      </Button>
    )
  // Diameters confirmed and the deterministic assessment is in: the agent is drafting.
  if (study.status === "analyzed") return <DraftingButton run={draftingRun(log)} />
  return (
    <Button size="sm" variant="ghost" disabled className="h-8 text-xs">
      Approve Nodules
    </Button>
  )
}
