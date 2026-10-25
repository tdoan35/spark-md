import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useState } from "react"
import { Inbox, CheckCheck, FileText } from "lucide-react"
import { useOutbox, useWorklist } from "@/api/hooks"
import { hm, relTime } from "@/lib/format"
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet"
import type { OutboxItem } from "@/api/types"

export function InboxPage() {
  const { data, isLoading } = useOutbox()
  const { data: worklist } = useWorklist()
  const [sel, setSel] = useState<OutboxItem | null>(null)

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
            Nothing delivered yet. Approve a PCP letter to send it here.
          </div>
        )}
        <ul>
          {data?.map((o) => (
            <li key={o.id}>
              <button onClick={() => setSel(o)} className="flex w-full items-center gap-3 border-b px-4 py-4 text-left last:border-b-0 hover:bg-muted/50">
                <span className="grid size-8 shrink-0 place-items-center rounded-md bg-ok-soft text-ok"><CheckCheck className="size-4" /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-medium">{o.subject ?? `${o.kind ?? "Report"} · ${o.patient_id ?? ""}`}</span>
                  <span className="mt-1 block truncate text-sm text-muted-foreground">To {o.recipient} · Patient {worklist?.find((r) => r.study_uid === o.study_uid)?.patient_id ?? o.patient_id ?? "—"} · delivered at {hm(o.ts)}</span>
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">{relTime(o.ts)}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <Sheet open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <SheetContent side="right" className="data-[side=right]:w-[600px]! data-[side=right]:sm:max-w-[600px]! gap-0 p-0 animate-none! transition-none! data-[side=right]:top-(--titlebar-h)! data-[side=right]:bottom-(--footer-h)! data-[side=right]:h-auto!" onOpenAutoFocus={(e) => e.preventDefault()}>
          <SheetTitle className="sr-only">Delivered PCP letter</SheetTitle>
          {sel && (
            <div className="flex h-full flex-col">
              <div className="shrink-0 border-b px-6 py-4">
                <div className="flex items-center gap-2 pr-8 text-sm font-medium text-ok"><CheckCheck className="size-4 shrink-0" /> Delivered to {sel.recipient}</div>
                <div className="mt-2 text-base font-medium">{sel.subject}</div>
                <SheetDescription className="mt-1 text-sm">Patient {worklist?.find((r) => r.study_uid === sel.study_uid)?.patient_id ?? sel.patient_id ?? "—"} · delivered at {hm(sel.ts)}</SheetDescription>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4 text-[15px] leading-relaxed">
                <div className="mb-3 flex items-center gap-2 text-xs text-muted-foreground"><FileText className="size-4" /> Approved PCP letter</div>
                {sel.payload?.markdown ? (
                  <article className="report-md [&_h1]:text-lg [&_h2]:text-sm [&_h3]:text-base [&_table]:text-sm">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{sel.payload.markdown}</ReactMarkdown>
                    <div className="mt-4 border-t pt-3 text-sm text-ok">Approved by {sel.payload.approved_by ?? "—"} at {hm(sel.payload.approved_at ?? sel.ts)}</div>
                  </article>
                ) : (
                  <p className="text-muted-foreground">
                    This {(sel.kind ?? sel.payload?.kind) === "pcp_letter" ? "PCP letter" : "radiology report"} was approved by a radiologist in the app and written to the mock EHR outbox. Open the study to read the full text.
                  </p>
                )}
              </div>
              <div className="shrink-0 border-t px-6 py-3">
                <p className="text-xs leading-relaxed text-muted-foreground">Research demo, not for clinical use. Delivered to the mock EHR inbox only.</p>
                <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{sel.report_id}</p>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
