import { useEffect, useState } from "react"
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

  const approved: Report | null = result?.report.status === "approved" ? result.report : active?.status === "approved" ? active : null

  const approve = async () => {
    if (!active) return
    const name = approver.trim()
    if (!name) return
    setPending(true)
    setError(null)
    try {
      const r = await api.approve(active.report_id, name)
      setResult(r)
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
      setPending(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-[480px] gap-0 p-0 data-[side=right]:top-(--titlebar-h)! data-[side=right]:bottom-(--footer-h)! data-[side=right]:h-auto!"
        onOpenAutoFocus={(e) => {
          e.preventDefault()
          requestAnimationFrame(() => (document.getElementById("approver-input") as HTMLInputElement | null)?.focus())
        }}
      >
        <div className="flex h-full flex-col">
          <div className="border-b px-5 py-3">
            <SheetTitle className="text-sm">Report review · patient {patient ?? "—"}</SheetTitle>
            <SheetDescription className="mt-0.5 text-[11px]">Read the text, then approve. Only a human click approves — no tool, no shortcut.</SheetDescription>
            <div className="mt-2 flex gap-1">
              {(["radiology", "pcp_letter"] as Tab[]).map((k) => {
                const latest = reports?.filter((r) => r.kind === k).sort((a, b) => b.version - a.version)[0]
                return (
                  <button
                    key={k}
                    onClick={() => {
                      setTab(k)
                      setResult(null)
                      setError(null)
                    }}
                    className={cn("flex h-6 items-center gap-1.5 rounded px-2 text-[11px]", tab === k ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/60")}
                  >
                    {k === "radiology" ? "Radiology report" : "PCP letter"}
                    {latest?.status === "approved" && <CheckCheck className="size-3 text-ok" />}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {isLoading && <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3 animate-spin" /> Loading…</div>}
            {!isLoading && !active && <div className="text-sm text-muted-foreground">No {tab === "radiology" ? "report" : "letter"} yet — the agent drafts after the last diameter is confirmed.</div>}
            {active && (
              <article className="report-md text-[13px] leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{active.markdown}</ReactMarkdown>
                <div className="mt-3 border-t pt-2 font-mono text-[10px] text-muted-foreground">
                  {active.report_id} · v{active.version} · {active.status}
                  {approved && <> · approved by {approved.approved_by} on {hm(approved.approved_at)}</>}
                </div>
              </article>
            )}
          </div>

          <div className="border-t px-5 py-3">
            {approved ? (
              <div className="flex items-center gap-2 rounded-md bg-ok-soft px-2.5 py-2 text-[12px] text-ok">
                <CheckCheck className="size-4" /> Approved by {approved.approved_by} on {hm(approved.approved_at)}{approved.kind === "pcp_letter" ? " — delivered to the EHR inbox." : "."}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <label htmlFor="approver-input" className="text-[11px] text-muted-foreground">Approver</label>
                <Input id="approver-input" value={approver} onChange={(e) => setApprover(e.target.value)} className="h-8 flex-1 text-[12px]" />
                <Button
                  disabled={!active || pending || !approver.trim()}
                  onClick={(e) => {
                    // Mouse only: ignore keyboard-synthesised clicks (e.detail === 0).
                    if (e.detail === 0) return
                    void approve()
                  }}
                >
                  {pending ? <Loader2 className="size-4 animate-spin" /> : <Lock className="size-3.5" />} Approve
                </Button>
              </div>
            )}
            {error && (
              <div role="alert" className="mt-2 flex items-start gap-1.5 rounded-md bg-alert-soft px-2 py-1.5 text-[11px] text-alert">
                <X className="mt-0.5 size-3 shrink-0" /> {error}
              </div>
            )}
            <p className="mt-2 text-[10px] text-muted-foreground/70">Research demo, not for clinical use. Approval is logged and written to the mock outbox only.</p>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
