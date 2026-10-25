import { Component, Suspense, lazy, useEffect, useState, type ReactNode } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { viewerBus } from "@/api/viewer-bus"
import type { Findings, StudyDetail, ViewerCommand } from "@/api/types"
import { cn } from "@/lib/utils"
import { Box, Images, Columns2, RotateCcw } from "lucide-react"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { SlicesView } from "./slices-view"
import { CompareView } from "./slices-view"
import { ExtrasPanel } from "./extras-panel"
import { ChatRail } from "./chat-rail"

const Lung3D = lazy(() => import("./lung-3d"))

type Mode = "3d" | "slices" | "compare"

class ViewError extends Component<{ children: ReactNode }, { msg: string | null }> {
  state = { msg: null as string | null }
  static getDerivedStateFromError(e: unknown) {
    return { msg: String(e) }
  }
  render() {
    if (this.state.msg)
      return <div className="grid h-full place-items-center p-6 text-center text-xs text-muted-foreground">3D scene unavailable: {this.state.msg}</div>
    return this.props.children
  }
}

export function ViewerPane({
  uid, findings, selected, onSelect, study, paused, bottom,
}: {
  uid: string
  findings: Findings | undefined
  selected: string | null
  onSelect: (id: string) => void
  study: StudyDetail
  /** Freeze the 3D canvas (report sheet open); GL-on-EGL renders are CPU-bound on GB10. */
  paused?: boolean
  /** Rendered under the imaging well only — the chat rail keeps full height beside it (08). */
  bottom?: ReactNode
}) {
  const [mode, setMode] = useState<Mode>(() => study.priors.length ? "compare" : "slices")
  const [extrasOpen, setExtrasOpen] = useState(false)
  const [cmdTick, setCmdTick] = useState<{ command: ViewerCommand["command"]; nodule_id?: string } | null>(null)
  const qc = useQueryClient()

  // A study that has not been organized/analyzed yet has nothing to show: start the job once
  // (the worker long-polls and returns `awaiting_confirmation`; SSE then refreshes findings).
  const needsAnalysis = study.status === "received" || study.status === "organized"
  useEffect(() => {
    if (!needsAnalysis) return
    let cancelled = false
    const series = study.series?.find((x) => x.eligible)
    const run = async () => {
      try {
        if (series) {
          await fetch(`/api/studies/${uid}/select-series`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ series_uid: series.series_uid, reason: series.eligible_reason ?? "eligible" }) })
        }
        await fetch(`/api/studies/${uid}/analyze`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ wait_s: 25 }) })
      } catch {
        /* SSE study_updated drives the refresh; a failed start shows in the log */
      }
      if (!cancelled) {
        void qc.invalidateQueries({ queryKey: ["study", uid] })
        void qc.invalidateQueries({ queryKey: ["findings", uid] })
      }
    }
    void run()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsAnalysis, uid, qc])

  useEffect(() => {
    const off = viewerBus.subscribe((cmd) => {
      if (cmd.study_uid !== uid) return
      setCmdTick({ command: cmd.command, nodule_id: "nodule_id" in cmd ? cmd.nodule_id : undefined })
      if (cmd.command === "show_nodule") {
        setMode("3d")
        if (cmd.nodule_id) onSelect(cmd.nodule_id)
      } else if (cmd.command === "compare_prior") {
        setMode("compare")
        if (cmd.nodule_id) onSelect(cmd.nodule_id)
      } else if (cmd.command === "reset_view") {
        setMode("3d")
      } else if (cmd.command === "show_extras") {
        setExtrasOpen(true)
      }
    })
    return off
  }, [uid, onSelect])

  const nodule = findings?.nodules.find((n) => n.nodule_id === selected)

  return (
    <div className="grid h-full min-h-0 grid-cols-[var(--chat-w)_minmax(0,1fr)] grid-rows-[minmax(0,1fr)_auto]" style={{ containerType: "inline-size" }}>
      <div className="row-span-2 flex min-h-0 min-w-0">
        <ChatRail uid={uid} />
      </div>
      <div className={cn("relative min-h-0 min-w-0 overflow-hidden rounded-lg bg-well", extrasOpen && "col-span-2")}>
        <div className="flex h-9 items-center gap-2 px-2.5 text-[11px] text-white/60">
          <ToggleGroup
            type="single"
            value={mode}
            onValueChange={(v) => v && setMode(v as Mode)}
            className="rounded-md bg-white/5"
          >
            <ToggleGroupItem value="slices" className="h-6 px-1.5 text-[11px] text-white/70 data-[state=on]:bg-white/15 data-[state=on]:text-white" aria-label="CT slices">
              <Images className="mr-1 size-3.5" /> CT slices
            </ToggleGroupItem>
            <ToggleGroupItem value="3d" className="h-6 px-1.5 text-[11px] text-white/70 data-[state=on]:bg-white/15 data-[state=on]:text-white" aria-label="3D anatomy">
              <Box className="mr-1 size-3.5" /> 3D anatomy
            </ToggleGroupItem>
            <ToggleGroupItem value="compare" className="h-6 px-1.5 text-[11px] text-white/70 data-[state=on]:bg-white/15 data-[state=on]:text-white" aria-label="Compare">
              <Columns2 className="mr-1 size-3.5" /> Compare
            </ToggleGroupItem>
          </ToggleGroup>
          <button
            onClick={() => {
              setMode("3d")
              viewerBus.emit({ command: "reset_view", study_uid: uid })
            }}
            className="ml-auto flex h-6 items-center gap-1 rounded px-1.5 text-[11px] text-white/60 hover:bg-white/10 hover:text-white"
            aria-label="Reset view"
          >
            <RotateCcw className="size-3.5" /> Reset
          </button>
          {findings?.placeholder && <span className="font-mono text-[10px] text-white/40">Synthetic preview · placeholder numbers</span>}
        </div>
        <div className="absolute inset-x-0 bottom-0 top-9">
          {mode === "3d" && (
            <ViewError>
              <Suspense fallback={<div className="grid h-full place-items-center text-[11px] text-white/50">Loading anatomy…</div>}>
                <Lung3D uid={uid} findings={findings} selected={selected} onSelect={onSelect} command={cmdTick} paused={paused} />
              </Suspense>
            </ViewError>
          )}
          {mode === "slices" && <SlicesView uid={uid} findings={findings} selected={selected} onSelect={onSelect} />}
          {mode === "compare" && <CompareView findings={findings} selected={selected} onSelect={onSelect} study={study} />}
          {mode === "3d" && (
          <div className="pointer-events-none absolute bottom-2 left-3 max-w-[40%] font-mono text-[10px] text-white/40">
            {study.timepoint} · {nodule ? `${nodule.lobe} · mean ${nodule.mean_mm ?? nodule.proposal?.mean_mm ?? "—"} mm` : "No nodule selected"}
          </div>
          )}
          {mode === "3d" && !!findings?.nodules.length && (
            <div role="group" aria-label="Nodule shortcuts" className="absolute bottom-3 right-3 flex max-h-[50%] max-w-[55%] flex-col gap-1.5 overflow-y-auto">
              {findings.nodules.map((n, i) => (
                <button
                  key={n.nodule_id}
                  type="button"
                  aria-label={`Focus nodule ${i + 1} · ${n.lobe}`}
                  aria-pressed={selected === n.nodule_id}
                  title={n.nodule_id}
                  onClick={() => viewerBus.emit({ command: "show_nodule", study_uid: uid, nodule_id: n.nodule_id })}
                  className={cn(
                    "min-h-8 shrink-0 rounded-md border px-3 py-1.5 text-left text-sm shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white",
                    selected === n.nodule_id ? "border-white/60 bg-white/20 text-white" : "border-white/20 bg-well/95 text-white/75 hover:border-white/40 hover:bg-white/10 hover:text-white",
                  )}
                >
                  Nodule {i + 1} · {n.lobe}
                </button>
              ))}
            </div>
          )}
        </div>
        {extrasOpen && <ExtrasPanel findings={findings} onClose={() => setExtrasOpen(false)} uid={uid} />}
      </div>
      {bottom && <div className="col-start-2 row-start-2 min-h-0 min-w-0">{bottom}</div>}
    </div>
  )
}
