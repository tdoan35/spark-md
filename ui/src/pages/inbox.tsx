import { useState } from "react"
import { Inbox, CheckCheck, FileText } from "lucide-react"
import { useOutbox, useWorklist } from "@/api/hooks"
import { hm, relTime } from "@/lib/format"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import type { OutboxItem } from "@/api/types"

export function InboxPage() {
  const { data, isLoading } = useOutbox()
  const { data: worklist } = useWorklist()
  const [sel, setSel] = useState<OutboxItem | null>(null)
  const patient = worklist?.find((r) => r.study_uid === sel?.study_uid)?.patient_id ?? sel?.patient_id

  return (
    <div className="flex h-full min-h-0 flex-col px-6 pb-4 pt-5">
      <div className="mb-3">
        <h1 className="flex items-center gap-2 text-[15px] font-semibold"><Inbox className="size-4 text-muted-foreground" /> EHR inbox</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">Mock EHR · approved letters land here the moment a human clicks Approve.</p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border">
        {isLoading && <div className="p-6 text-xs text-muted-foreground">Loading…</div>}
        {!isLoading && !data?.length && (
          <div className="flex flex-col items-center justify-center gap-2 p-12 text-xs text-muted-foreground">
            <Inbox className="size-5" />
            Nothing delivered yet. Approve a report to send it here.
          </div>
        )}
        <ul>
          {data?.map((o) => (
            <li key={o.id}>
              <button onClick={() => setSel(o)} className="flex w-full items-center gap-3 border-b px-3 py-2.5 text-left last:border-b-0 hover:bg-muted/50">
                <span className="grid size-7 shrink-0 place-items-center rounded-md bg-ok-soft text-ok"><CheckCheck className="size-4" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{o.subject ?? `${o.kind ?? "Report"} · ${o.patient_id ?? ""}`}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">To {o.recipient} · {patient ?? o.patient_id ?? "—"} · approved {hm(o.ts)}</span>
                </span>
                <span className="shrink-0 text-[11px] text-muted-foreground">{relTime(o.ts)}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <Sheet open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <SheetContent side="right" className="w-[460px] p-0 data-[side=right]:top-(--titlebar-h)! data-[side=right]:bottom-(--footer-h)! data-[side=right]:h-auto!" onOpenAutoFocus={(e) => e.preventDefault()}>
          <SheetTitle className="sr-only">Delivered report</SheetTitle>
          {sel && (
            <div className="flex h-full flex-col">
              <div className="border-b px-5 py-3">
                <div className="flex items-center gap-2 text-xs text-ok"><CheckCheck className="size-3.5" /> Delivered to {sel.recipient}</div>
                <div className="mt-1 text-sm font-medium">{sel.subject}</div>
                <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{sel.report_id} · {hm(sel.ts)}</div>
              </div>
              <div className="flex-1 overflow-y-auto px-5 py-4 text-[13px] leading-relaxed">
                <div className="mb-2 flex items-center gap-1.5 text-[11px] text-muted-foreground"><FileText className="size-3.5" /> Letter body (stored in outbox payload)</div>
                <p className="text-muted-foreground">
                  This {sel.kind === "pcp_letter" ? "PCP letter" : "radiology report"} was approved by a radiologist in the app and written to the mock EHR outbox. Open the study to read the full text.
                </p>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
