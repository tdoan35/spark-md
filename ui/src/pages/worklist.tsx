import { compareScreens } from "@/lib/patient-studies"
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

type PatientRow = {
  primary: WorklistRow
  scans: WorklistRow[]
  reportsAwaiting: number
  allApproved: boolean
}

export function WorklistPage() {
  const app = useApp()
  const { data, isLoading, isError } = useWorklist()
  const [busy, setBusy] = useState<string | null>(null)
  const patients = useMemo(() => {
    const grouped = new Map<string, PatientRow>()
    // Preserve worker ordering: the first scan for each patient has the highest priority.
    for (const scan of data ?? []) {
      let patient = grouped.get(scan.patient_id)
      if (!patient) {
        patient = { primary: scan, scans: [], reportsAwaiting: 0, allApproved: true }
        grouped.set(scan.patient_id, patient)
      }
      patient.scans.push(scan)
      patient.reportsAwaiting += scan.reports_awaiting
      patient.allApproved = patient.allApproved && scan.status === "approved"
    }
    for (const patient of grouped.values()) {
      patient.scans.sort(compareScreens)
      patient.primary = [...patient.scans].reverse().find((s) => s.status !== "approved") ?? patient.scans[patient.scans.length - 1]
    }
    return [...grouped.values()]
  }, [data])
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
            {data ? `${patients.length} patient${patients.length === 1 ? "" : "s"} · ${data.length} scan${data.length === 1 ? "" : "s"} · sorted by highest-priority scan` : "Loading…"}
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
                <th className="border-b px-3 py-2 font-medium">Scans</th>
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
                {patients.map(({ primary: r, scans, reportsAwaiting, allApproved }) => (
                  <motion.tr
                    key={r.patient_id}
                    data-patient-id={r.patient_id}
                    layout="position"
                    initial={{ opacity: 0, y: -6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ layout: { type: "spring", stiffness: 380, damping: 34 } }}
                    onClick={() => app.openStudy(r.study_uid)}
                    className="cursor-pointer bg-background hover:bg-muted/50"
                  >
                    <td className="border-b px-3 py-2.5 font-mono text-[13px] tabular-nums">
                      <button
                        className="rounded text-left hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label={`Open patient ${r.patient_id}, current scan ${r.timepoint}`}
                        onClick={(e) => { e.stopPropagation(); app.openStudy(r.study_uid) }}
                      >
                        {r.patient_id}
                      </button>
                    </td>
                    <td className="border-b px-3 py-2.5 text-xs text-muted-foreground">
                      <div>Chest CT · {scans.length} {scans.length === 1 ? "scan" : "scans"} · current scan {r.timepoint}</div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {scans.map((scan) => (
                          <button
                            key={scan.study_uid}
                            data-scan-uid={scan.study_uid}
                            aria-label={`Open ${scan.timepoint} scan for patient ${r.patient_id}`}
                            title={`${scan.timepoint}${scan.day_offset != null ? ` · Day ${scan.day_offset}` : ""} · ${STATUS_LABEL[scan.status] ?? scan.status}${scan.lung_rads ? ` · Lung-RADS ${scan.lung_rads}` : ""}${scan.study_uid === r.study_uid ? " · current scan" : ""}`}
                            onClick={(e) => { e.stopPropagation(); app.openStudy(scan.study_uid) }}
                            className={cn("h-6 rounded border px-2 text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", scan.study_uid === r.study_uid ? "border-foreground/30 bg-muted text-foreground" : "border-border hover:bg-muted hover:text-foreground")}
                          >
                            {scan.timepoint}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td className="border-b px-3 py-2.5 text-xs text-muted-foreground">{relTime(r.received_at)}</td>
                    <td className="border-b px-3 py-2.5"><Priority p={r.priority} /></td>
                    <td className="border-b px-3 py-2.5"><LungRadsBadge lr={r.lung_rads} /></td>
                    <td className="border-b px-3 py-2.5"><StatusPill status={r.status} /></td>
                    <td className="border-b px-3 py-2.5 text-xs text-muted-foreground">
                      {reportsAwaiting > 0 ? (
                        <span className="inline-flex items-center gap-1 text-warn"><FileText className="size-3.5" />{reportsAwaiting} await approval</span>
                      ) : allApproved ? (
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
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px]">
        <span className="text-muted-foreground/70">
          Hero patient 134503: {hero ? `${STATUS_LABEL[hero.status] ?? hero.status}${heroReports.data?.length ? ` · ${heroReports.data.length} report${heroReports.data.length === 1 ? "" : "s"}` : ""}` : "not dropped yet"}. All numbers are placeholders.
        </span>
        <span className="text-muted-foreground/50">Clinical values reflect the current scan · reports cover all scans</span>
      </div>
    </div>
  )
}
