import { useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { CheckCheck, Loader2, Lock, X } from "lucide-react"
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { usePatientOf, useReports } from "@/api/hooks"
import { qk } from "@/api/keys"
import { api, ApiError } from "@/api/client"
import { hm } from "@/lib/format"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { ApproveResult, Report, ReportKind } from "@/api/types"

type Tab = ReportKind

export function ReportSheet({ open, onOpenChange, uid }: { open: boolean; onOpenChange: (v: boolean) => void; uid: string }) {
  const { data: reports, isLoading } = useReports(uid)
  const patient = usePatientOf(uid)
  const [tab, setTab] = useState<Tab>("radiology")
  const [approver, setApprover] = useState(() => localStorage.getItem("sparkmd-approver") ?? "Dr. Joyce (demo)")
  const [result, setResult] = useState<ApproveResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const inFlight = useRef(false)
  const qc = useQueryClient()

  const active = reports?.filter((r) => r.kind === tab).sort((a, b) => b.version - a.version)[0]

  useEffect(() => {
    if (!open) {
      setResult(null)
      setError(null)
    }
  }, [open])

  useEffect(() => {
    localStorage.setItem("sparkmd-approver", approver)
  }, [approver])

  const approved: Report | null = result?.report.report_id === active?.report_id && result?.report.status === "approved" ? result.report : active?.status === "approved" ? active : null

  const approve = async () => {
    if (!active || inFlight.current) return
    const name = approver.trim()
    if (!name) return
    inFlight.current = true
    setPending(true)
    setError(null)
    try {
      const r = await api.approve(active.report_id, name)
      setResult(r)
      qc.setQueryData<Report[]>(qk.reports(uid), (current) => current?.map((report) => report.report_id === r.report.report_id ? r.report : report))
      void qc.invalidateQueries({ queryKey: qk.reports(uid) })
      void qc.invalidateQueries({ queryKey: qk.outbox })
      void qc.invalidateQueries({ queryKey: qk.worklist })
      toast.success(r.already_approved ? "Already approved" : `Approved by ${name}`, {
        description: r.already_approved ? `Approved earlier by ${r.report.approved_by ?? "a radiologist"}` : r.outbox_id != null ? "Delivered to the EHR inbox" : "Signed and filed",
      })
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const code = (e.body as { error?: string } | null)?.error
        setError(code === "confirm_all_first" ? "Confirm all nodules before approving this study." : code === "superseded report" ? "A newer draft exists. Reopen the report to approve the latest version." : `Not approved: ${code ?? "conflict"}`)
      }
      else if (e instanceof ApiError && e.status === 403) setError("Approval only works from this device (loopback only).")
      else setError((e as Error).message ?? "Approve failed")
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="data-[side=right]:w-[560px]! data-[side=right]:sm:max-w-[560px]! animate-none! transition-none! gap-0 p-0 data-[side=right]:top-(--titlebar-h)! data-[side=right]:bottom-(--footer-h)! data-[side=right]:h-auto!"
        // Close only via the X / Escape, so a stray click beside the sheet never drops the review.
        onInteractOutside={(e) => e.preventDefault()}
        onOpenAutoFocus={(e) => {
          e.preventDefault()
          requestAnimationFrame(() => (document.getElementById("approver-input") as HTMLInputElement | null)?.focus())
        }}
      >
        <div className="flex h-full flex-col">
          <div className="shrink-0 border-b px-6 py-4">
            <SheetTitle className="pr-8 text-base">Report review · patient {patient ?? "—"}</SheetTitle>
            <SheetDescription className="mt-1 pr-5 text-xs leading-relaxed">Read the text, then approve. Only a human click approves — no tool, no shortcut.</SheetDescription>
            <div className="mt-3 flex gap-1">
              {(["radiology", "pcp_letter"] as Tab[]).map((k) => {
                const latest = reports?.filter((r) => r.kind === k).sort((a, b) => b.version - a.version)[0]
                return (
                  <button
                    key={k}
                    disabled={pending}
                    onClick={() => {
                      setTab(k)
                      setResult(null)
                      setError(null)
                    }}
                    className={cn("flex h-8 items-center gap-2 rounded px-3 text-sm disabled:opacity-60", tab === k ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/60")}
                  >
                    {k === "radiology" ? "Radiology report" : "PCP letter"}
                    {latest?.status === "approved" && <CheckCheck className="size-3 text-ok" />}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            {isLoading && <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3 animate-spin" /> Loading…</div>}
            {!isLoading && !active && <div className="text-sm text-muted-foreground">No {tab === "radiology" ? "report" : "letter"} yet — the agent drafts after the last diameter is confirmed.</div>}
            {active && (
              <article className="report-md text-[15px] leading-relaxed [&_h1]:text-lg [&_h2]:text-sm [&_h3]:text-base [&_table]:text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{active.markdown}</ReactMarkdown>
                <div className="mt-4 break-all border-t pt-3 font-mono text-xs text-muted-foreground">
                  {active.report_id} · v{active.version} · {approved ? "approved" : active.status}
                </div>
              </article>
            )}
          </div>

          <div className="shrink-0 border-t px-6 py-4">
            {approved ? (
              <div role="status" className="flex items-start gap-2 rounded-md bg-ok-soft px-3 py-3 text-sm font-medium text-ok">
                <CheckCheck className="mt-0.5 size-4 shrink-0" />
                <div>Approved by {approved.approved_by} at {hm(approved.approved_at)}
                  {approved.kind === "pcp_letter" && <div className="mt-1 text-xs font-normal">Delivered to the EHR inbox.</div>}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <label htmlFor="approver-input" className="text-xs text-muted-foreground">Approver</label>
                <Input id="approver-input" value={approver} disabled={pending} onChange={(e) => setApprover(e.target.value)} className="h-9 min-w-0 flex-1 text-sm" />
                <Button
                  disabled={!active || pending || !approver.trim()}
                  onClick={(e) => {
                    // Mouse only: ignore keyboard-synthesised clicks (e.detail === 0), but say so.
                    console.info(`[sparkmd] approve click detail=${e.detail} report=${active?.report_id ?? "none"}`)
                    if (e.detail === 0) {
                      toast.info("Approve needs a mouse click", { description: "Keyboard activation is ignored by design." })
                      return
                    }
                    void approve()
                  }}
                >
                  {pending ? <Loader2 className="size-4 animate-spin" /> : <Lock className="size-3.5" />} Approve
                </Button>
              </div>
            )}
            {error && (
              <div role="alert" className="mt-2 flex items-start gap-2 rounded-md bg-alert-soft px-3 py-2 text-sm text-alert">
                <X className="mt-0.5 size-4 shrink-0" /> {error}
              </div>
            )}
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">Research demo, not for clinical use. Approval is logged and written to the mock EHR outbox only.</p>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
