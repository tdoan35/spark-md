import { MonitorPlay, X } from "lucide-react"
import type { DemoState } from "@/api/types"
import { api } from "@/api/client"

/** Replay line + pill over the patient header; honesty badge when speed ≠ 1. No layout shift. */
export function ReplayBanner({ demo, uid }: { demo: DemoState | null; uid: string | null }) {
  if (!demo?.replaying) return null
  const waiting = demo.waiting_for ? `waiting for ${demo.waiting_for === "confirm" ? "radiologist confirmation" : demo.waiting_for}` : demo.phase ?? ""
  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-0 z-20 h-0.5 bg-replay" />
      <div className="absolute left-1/2 top-1.5 z-20 -translate-x-1/2">
        <div className="pointer-events-auto flex h-7 items-center gap-2 rounded-full bg-replay-soft px-2.5 text-[11px] text-replay shadow-sm dark:bg-replay-soft/60">
          <MonitorPlay className="size-3.5" />
          <span className="font-medium">Time machine replay</span>
          <span className="text-replay/70">{demo.patient_id} · {demo.timepoint ?? "—"} · {waiting}</span>
          {demo.speed !== 1 && <span className="rounded bg-replay px-1 py-0.5 font-mono text-[10px] text-white">{demo.speed}×</span>}
          <button aria-label="Stop replay" className="rounded p-0.5 hover:bg-replay/10" onClick={() => void api.demoStop()}>
            <X className="size-3" />
          </button>
        </div>
      </div>
      <span className="sr-only">{uid ?? ""}</span>
    </>
  )
}
