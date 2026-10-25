// Sidebar section: top elevated/urgent patients, worklist order, max 3 unique patients.
// Live updates come from the worklist query cache (SSE worklist_changed invalidates it).
import { useState } from "react"
import { ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { useWorklist } from "@/api/hooks"
import { useApp } from "@/lib/app-context"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { LungRadsBadge } from "@/pages/worklist"

const MAX_ROWS = 3

export function PriorityPatients({ expanded }: { expanded: boolean }) {
  const app = useApp()
  const { data } = useWorklist()
  const [open, setOpen] = useState(true)
  const seen = new Set<string>()
  // First qualifying scan in worker order supplies each patient's badge and destination.
  const patients = (data ?? []).filter((r) => {
    if ((r.priority !== "elevated" && r.priority !== "urgent") || seen.has(r.patient_id)) return false
    seen.add(r.patient_id)
    return true
  })
  if (!expanded || patients.length === 0) return null

  return (
    <div className="mt-4 min-h-0 px-2">
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger className="flex h-7 w-full items-center gap-1.5 rounded-md px-2 text-[11px] font-medium text-muted-foreground/80 hover:bg-sidebar-accent hover:text-foreground">
          <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          Priority patients
          <span className="ml-auto rounded-full bg-muted px-1.5 text-[10px] tabular-nums text-muted-foreground">{patients.length}</span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ul className="mt-0.5 flex flex-col gap-0.5">
            {patients.slice(0, MAX_ROWS).map((r) => (
              <li key={r.patient_id}>
                <button
                  onClick={() => app.openStudy(r.study_uid)}
                  className="flex h-8 w-full items-center gap-1.5 rounded-md px-2 text-left text-[13px] transition-colors hover:bg-sidebar-accent"
                >
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-mono tabular-nums">{r.patient_id}</span>
                    <span className="ml-1.5 text-[11px] text-muted-foreground">{r.timepoint}</span>
                  </span>
                  <LungRadsBadge lr={r.lung_rads} />
                </button>
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
