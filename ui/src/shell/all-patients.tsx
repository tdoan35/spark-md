// Sidebar section: every patient on the worklist, ordered by their most urgent study
// (worklist order). Click opens that patient's top worklist study. Live like the worklist.
import { useState } from "react"
import { ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { useWorklist } from "@/api/hooks"
import { useApp } from "@/lib/app-context"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import type { WorklistRow } from "@/api/types"

export function AllPatients({ expanded }: { expanded: boolean }) {
  const app = useApp()
  const { data } = useWorklist()
  const [open, setOpen] = useState(true)

  // First occurrence in worklist order = the patient's most urgent study.
  const patients: { patient_id: string; rows: WorklistRow[] }[] = []
  for (const r of data ?? []) {
    const p = patients.find((x) => x.patient_id === r.patient_id)
    if (p) p.rows.push(r)
    else patients.push({ patient_id: r.patient_id, rows: [r] })
  }
  if (!expanded || patients.length === 0) return null

  return (
    <div className="mt-4 min-h-0 px-2">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger className="flex h-7 w-full items-center gap-1.5 rounded-md px-2 text-[11px] font-medium text-muted-foreground/80 hover:bg-sidebar-accent hover:text-foreground">
          <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          All patients
          <span className="ml-auto rounded-full bg-muted px-1.5 text-[10px] tabular-nums text-muted-foreground">{patients.length}</span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ul className="mt-0.5 flex max-h-[40vh] flex-col gap-0.5 overflow-y-auto">
            {patients.map(({ patient_id, rows }) => (
              <li key={patient_id}>
                <button
                  onClick={() => app.openStudy(rows[0].study_uid)}
                  className="flex h-8 w-full items-center gap-1.5 rounded-md px-2 text-left text-[13px] transition-colors hover:bg-sidebar-accent"
                >
                  <span className="min-w-0 flex-1 truncate font-mono tabular-nums">{patient_id}</span>
                  <span className="text-[11px] text-muted-foreground">{rows.length} {rows.length === 1 ? "scan" : "scans"}</span>
                </button>
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
