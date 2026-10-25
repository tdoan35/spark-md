import { useMemo, useState } from "react"
import { motion, AnimatePresence } from "motion/react"
import { ListChecks, Play, RotateCcw, Loader2, WifiOff, FileText } from "lucide-react"
import { useWorklist, useReports } from "@/api/hooks"
import { useApp } from "@/lib/app-context"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { STATUS_LABEL, PRIORITY_LABEL, lungRadsClass, relTime } from "@/lib/format"
import { api } from "@/api/client"
import { toast } from "sonner"
import type { WorklistRow } from "@/api/types"

export function LungRadsBadge({ lr }: { lr: string | null }) {
  if (!lr) return <span className="font-mono text-xs text-muted-foreground/70">—</span>
  return (
    <span className={cn("inline-flex h-5 min-w-8 items-center justify-center rounded px-1.5 font-mono text-xs tabular-nums", lungRadsClass(lr), lr === "4X" && "ring-1 ring-alert/50")}>
      {lr}
    </span>
  )
}

export function StatusPill({ status }: { status: WorklistRow["status"] }) {
  const label = STATUS_LABEL[status] ?? status
  const cls =
    status === "approved"
      ? "bg-ok-soft text-ok"
      : status === "failed"
        ? "bg-alert-soft text-alert"
        : status === "awaiting_confirmation" || status === "reported"
          ? "bg-warn-soft text-warn"
          : status === "analyzing"
            ? "bg-run-soft text-run"
            : "bg-muted text-muted-foreground"
  return <span className={cn("inline-flex h-5 items-center gap-1 rounded px-1.5 text-[11px] font-medium", cls)}>{status === "analyzing" && <Loader2 className="size-3 animate-spin" />}{label}</span>
}

function Priority({ p }: { p: WorklistRow["priority"] }) {
  return <span className={cn("text-[11px]", p === "urgent" ? "font-medium text-alert" : p === "elevated" ? "text-warn" : "text-muted-foreground")}>{PRIORITY_LABEL[p]}</span>
}

export function WorklistPage() {
  const app = useApp()
  const { data, isLoading, isError } = useWorklist()
  const [busy, setBusy] = useState<string | null>(null)
  const hero = useMemo(() => data?.find((r) => r.patient_id === "134503" || r.patient_id === "fixture-134503"), [data])
  const heroReports = useReports(hero?.study_uid ?? null)

  const drop = async (tp: string) => {
    setBusy(tp)
    try {
      await api.demoDrop(hero?.patient_id ?? "134503", tp)
      toast.success(`Dropped 134503 ${tp}`, { description: "The worker will analyze it; you confirm diameters." })
    } catch (e) {
      toast.error(String((e as Error).message))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col px-6 pb-4 pt-5">
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-[15px] font-semibold">
            <ListChecks className="size-4 text-muted-foreground" /> Worklist
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {data ? `${data.length} studies · sorted by priority, Lung-RADS, then arrival` : "Loading…"}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <Button variant="outline" size="sm" className="h-7 gap-1.5 text-xs" onClick={() => void drop("T1")} disabled={!!busy || !hero}>
            {busy === "T1" ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />} Drop next scan
          </Button>
          <Button
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={() => {
              void api.demoReset().catch((e) => toast.error(String(e.message)))
              toast("Replay reset", { description: "Back to the seeded worklist." })
            }}
          >
            <RotateCcw className="size-3" /> Reset
          </Button>
        </div>
      </div>

      {isError && (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
          <WifiOff className="size-5" />
          Worker unreachable at 127.0.0.1:8100
        </div>
      )}

      {!isError && (
        <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border">
          <table className="w-full border-separate border-spacing-0 text-sm">
            <thead className="sticky top-0 z-10 bg-background">
              <tr className="text-left text-[11px] font-medium text-muted-foreground">
                <th className="border-b px-3 py-2 font-medium">Patient</th>
                <th className="border-b px-3 py-2 font-medium">Scan</th>
                <th className="border-b px-3 py-2 font-medium">Received</th>
                <th className="border-b px-3 py-2 font-medium">Priority</th>
                <th className="border-b px-3 py-2 font-medium">Lung-RADS</th>
                <th className="border-b px-3 py-2 font-medium">State</th>
                <th className="border-b px-3 py-2 font-medium">Reports</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={7} className="px-3 py-10 text-center text-xs text-muted-foreground"><Loader2 className="mr-2 inline size-3 animate-spin" />Loading the worklist…</td>
                </tr>
              )}
              {!isLoading && !data?.length && (
                <tr>
                  <td colSpan={7} className="px-3 py-10 text-center text-xs text-muted-foreground">No studies yet. Drop a scan from the backlog.</td>
                </tr>
              )}
              <AnimatePresence initial={false}>
                {data?.map((r) => (
                  <motion.tr
                    key={r.study_uid}
                    layout="position"
                    initial={{ opacity: 0, y: -6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ layout: { type: "spring", stiffness: 380, damping: 34 } }}
                    onClick={() => app.openStudy(r.study_uid)}
                    className="cursor-pointer bg-background hover:bg-muted/50"
                  >
                    <td className="border-b px-3 py-2.5 font-mono text-[13px] tabular-nums">{r.patient_id}</td>
                    <td className="border-b px-3 py-2.5 text-xs text-muted-foreground">
                      Chest CT · {r.timepoint}
                      {r.day_offset != null && <span className="text-muted-foreground/60"> · Day {r.day_offset}</span>}
                    </td>
                    <td className="border-b px-3 py-2.5 text-xs text-muted-foreground">{relTime(r.received_at)}</td>
                    <td className="border-b px-3 py-2.5"><Priority p={r.priority} /></td>
                    <td className="border-b px-3 py-2.5"><LungRadsBadge lr={r.lung_rads} /></td>
                    <td className="border-b px-3 py-2.5"><StatusPill status={r.status} /></td>
                    <td className="border-b px-3 py-2.5 text-xs text-muted-foreground">
                      {r.reports_awaiting > 0 ? (
                        <span className="inline-flex items-center gap-1 text-warn"><FileText className="size-3.5" />{r.reports_awaiting} await approval</span>
                      ) : r.status === "approved" ? (
                        <span className="text-ok">Approved</span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </motion.tr>
                ))}
              </AnimatePresence>
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-2 flex items-center justify-between text-[11px]">
        <span className="text-muted-foreground/70">
          Hero patient 134503: {hero ? `${STATUS_LABEL[hero.status] ?? hero.status}${heroReports.data?.length ? ` · ${heroReports.data.length} report${heroReports.data.length === 1 ? "" : "s"}` : ""}` : "not dropped yet"}. All numbers are placeholders.
        </span>
        <span className="text-muted-foreground/50">Priority, then Lung-RADS, then arrival · tie-break study UID</span>
      </div>
    </div>
  )
}
