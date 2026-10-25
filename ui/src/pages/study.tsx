import { useRef, useState, useEffect } from "react"
import { useReports, useStudy, useFindings } from "@/api/hooks"
import { api } from "@/api/client"
import { useApp } from "@/lib/app-context"
import type { StudyDetail, Findings } from "@/api/types"
import { mm, mmNum, hu, signed, days, dayLabel, STATUS_LABEL, lungRadsClass } from "@/lib/format"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Skeleton } from "@/components/ui/skeleton"
import { AlertTriangle, Check, ChevronDown, ChevronRight, Loader2, Sparkles, Activity, PanelRight } from "lucide-react"
import { toast } from "sonner"
import { StudyActivity } from "@/components/agent-log"
import { ViewerPane } from "@/components/viewer/viewer-pane"
import { ReportSheet } from "@/components/report-sheet"

export type InspectorTab = "assessment" | "activity"

export function StudyPage({ uid }: { uid: string }) {
  const { data: study, isLoading, isError } = useStudy(uid)
  const { data: findings } = useFindings(uid)
  const [tab, setTab] = useState<InspectorTab>("assessment")
  const [open, setOpen] = useState(() => localStorage.getItem("sparkmd-inspector") !== "closed")
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    if (findings && !selected) setSelected(findings.nodules[0]?.nodule_id ?? null)
  }, [findings, selected])
  useEffect(() => localStorage.setItem("sparkmd-inspector", open ? "open" : "closed"), [open])

  const inspectorRef = useRef<HTMLDivElement>(null)

  if (isError) return <div className="grid h-full place-items-center text-sm text-muted-foreground">Study not found — it may have been reset.</div>
  if (isLoading || !study)
    return (
      <div className="flex h-full flex-col gap-3 p-5">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-[420px] w-full" />
      </div>
    )

  const awaiting = study.status === "awaiting_confirmation"

  return (
    <div className="flex h-full min-h-0 flex-col">
      <StudyHeader study={study} onToggleInspector={() => setOpen((o) => !o)} inspectorOpen={open} />
      <div
        className={cn("grid min-h-0 flex-1", open ? "inspector-open" : "inspector-closed")}
        style={{ gridTemplateColumns: open ? "minmax(0,1fr) var(--inspector-w)" : "minmax(0,1fr) 0px" }}
      >
        <div className="flex min-h-0 min-w-0 flex-col">
          <div className="min-h-0 flex-1 px-3 pb-1">
            <ViewerPane uid={uid} findings={findings} selected={selected} onSelect={setSelected} study={study} />
          </div>
          <Strip study={study} findings={findings} selected={selected} onSelect={setSelected} />
        </div>
        <div
          ref={inspectorRef}
          inert={!open}
          className={cn("min-h-0 min-w-0 overflow-hidden border-l", !open && "invisible")}
          style={{ width: "var(--inspector-w)" }}
        >
          <div className="flex h-full w-(--inspector-w) flex-col">
            {awaiting && !findings?.assessment && (
              <div className="mt-2 flex items-center gap-1.5 bg-warn-soft px-3 py-1.5 text-[11px] text-warn dark:bg-warn-soft/30">
                <AlertTriangle className="size-3" /> Needs confirmation — no category yet
              </div>
            )}
            <Inspector uid={uid} tab={tab} setTab={setTab} findings={findings} selected={selected} setSelected={setSelected} study={study} />
          </div>
        </div>
      </div>
    </div>
  )
}

function StudyHeader({ study, onToggleInspector, inspectorOpen }: { study: StudyDetail; onToggleInspector: () => void; inspectorOpen: boolean }) {
  const { data: reports } = useReports(study.study_uid)
  const [sheetOpen, setSheetOpen] = useState(false)
  // Any draft (either kind) is worth opening: the sheet has both tabs.
  const draft = reports?.find((r) => r.status === "draft")
  const lr = study.lung_rads
  return (
    <div className="flex h-[60px] shrink-0 items-center gap-4 px-5">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-[15px] font-semibold tracking-tight">Patient {study.patient_id}</span>
          <span className="text-xs text-muted-foreground">
            Chest CT · {study.timepoint} · {dayLabel(study.day_offset)}
          </span>
          <span className={cn("text-[11px]", study.priority === "urgent" ? "text-alert" : study.priority === "elevated" ? "text-warn" : "text-muted-foreground")}>
            {study.priority === "routine" ? "Routine" : study.priority === "elevated" ? "Elevated" : "Urgent"}
            {study.priority_reason && study.priority !== "routine" ? ` · ${study.priority_reason}` : ""}
          </span>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{STATUS_LABEL[study.status] ?? study.status}</span>
          {lr && <span className={cn("rounded px-1.5 py-0.5 font-mono text-[10px] tabular-nums", lungRadsClass(lr))}>Lung-RADS {lr}</span>}
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2" data-hdr-reports={reports ? `${reports.length}:${reports.map((r) => r.kind + r.status).join(",")}` : "none"}>
        {draft ? (
          <Button size="sm" className="h-8 gap-1 text-xs" onClick={() => setSheetOpen(true)}>
            Review &amp; approve <ChevronRight className="size-3.5" />
          </Button>
        ) : reports?.some((r) => r.status === "approved") ? (
          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => setSheetOpen(true)}>
            View approved reports
          </Button>
        ) : null}
        <Button variant="ghost" size="icon" className="size-8" aria-label="Toggle inspector" aria-pressed={inspectorOpen} onClick={onToggleInspector}>
          <PanelRight className="size-4" />
        </Button>
      </div>
      <ReportSheet open={sheetOpen} onOpenChange={setSheetOpen} uid={study.study_uid} />
    </div>
  )
}

function Inspector({ uid, tab, setTab, findings, selected, setSelected, study }: { uid: string; tab: InspectorTab; setTab: (t: InspectorTab) => void; findings: Findings | undefined; selected: string | null; setSelected: (id: string) => void; study: StudyDetail }) {
  const { status } = useApp().sse
  return (
    <div className="flex h-full min-h-0 flex-col px-3 pt-2">
      <div className="mb-2 flex items-center gap-2">
        <ToggleGroup type="single" value={tab} onValueChange={(v) => v && setTab(v as InspectorTab)} className="h-7">
          <ToggleGroupItem value="assessment" className="h-7 px-2 text-[11px]">Assessment</ToggleGroupItem>
          <ToggleGroupItem value="activity" className="h-7 px-2 text-[11px]">Agent activity</ToggleGroupItem>
        </ToggleGroup>
        <span className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground">
          <span className={cn("size-1.5 rounded-full", status === "live" ? "bg-ok" : status === "down" ? "bg-alert" : "bg-warn")} />
          {status === "live" ? "Live" : status === "down" ? "Offline" : "Connecting"}
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pb-3">
        {tab === "assessment" ? (
          <Assessment findings={findings} selected={selected} setSelected={setSelected} study={study} />
        ) : (
          <StudyActivity studyUid={uid} />
        )}
      </div>
    </div>
  )
}

function Assessment({ findings, selected, setSelected, study }: { findings: Findings | undefined; selected: string | null; setSelected: (id: string) => void; study: StudyDetail }) {
  const a = findings?.assessment
  const [openRules, setOpenRules] = useState(false)
  if (!findings) return <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3 animate-spin" /> Waiting for findings…</div>
  return (
    <div className="space-y-3">
      {a ? (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Management</div>
          <div className="mt-1 flex items-center gap-2">
            <span className={cn("rounded px-2 py-1 font-mono text-sm font-semibold tabular-nums", lungRadsClass(a.lung_rads))}>Lung-RADS {a.lung_rads}</span>
            {study.priority_reason && <span className="text-[11px] text-warn">{study.priority_reason}</span>}
          </div>
          <p className="mt-1.5 text-[13px] leading-snug">{a.management}</p>
          <button onClick={() => setOpenRules((o) => !o)} className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground">
            {openRules ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />} Rule {a.rule_id} · {a.rules_version}
          </button>
          {openRules && (
            <div className="mt-1 rounded-md bg-muted/60 p-2 text-[10.5px] leading-relaxed text-muted-foreground">
              Category assigned by the deterministic Lung-RADS v2022 rules engine from confirmed diameters. Growth = &gt; 1.5 mm per 12 months, rate-normalized for intervals &gt; 12 mo. VDT is evidence only and never drives the category. The agent cannot propose, edit or assign a category.
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-md bg-warn-soft/70 px-2.5 py-2 text-[12px] leading-snug text-warn dark:bg-warn-soft/30">
          <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide"><AlertTriangle className="size-3" /> Needs confirmation</div>
          Confirm each diameter below. Growth, VDT and Lung-RADS are computed by code after the last confirm.
        </div>
      )}

      <div>
        <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wide text-muted-foreground">
          <span>Nodules · {findings.nodules.length}</span>
          {findings.placeholder && <span className="rounded bg-replay-soft px-1.5 py-0.5 text-[9px] normal-case text-replay">placeholder numbers</span>}
        </div>
        <div className="space-y-1.5">
          {findings.nodules.map((n, i) => (
            <NoduleBlock key={n.nodule_id} n={n} idx={i} selected={selected === n.nodule_id} onSelect={() => setSelected(n.nodule_id)} />
          ))}
          {!findings.nodules.length && <div className="text-xs text-muted-foreground">No nodules detected.</div>}
        </div>
      </div>

      {findings.extras && (
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">Screenings</div>
          <div className="grid grid-cols-2 gap-1.5 text-[11px]">
            <div className="rounded-md border px-2 py-1.5">
              <div className="text-[10px] text-muted-foreground">Emphysema (LAA-950)</div>
              <div className="font-mono text-[13px] tabular-nums">{findings.extras.emphysema_laa950_pct?.toFixed(1) ?? "—"} %</div>
            </div>
            <div className="rounded-md border px-2 py-1.5">
              <div className="text-[10px] text-muted-foreground">Bone · {findings.extras.vertebra?.label ?? "—"}</div>
              <div className="font-mono text-[13px] tabular-nums">{hu(findings.extras.vertebra?.mean_hu)}</div>
              {findings.extras.vertebra?.flag && <div className="text-[10px] text-warn">{findings.extras.vertebra.flag}</div>}
            </div>
            <div className="col-span-2 rounded-md border px-2 py-1.5">
              <div className="text-[10px] text-muted-foreground">Coronary calcium · experimental</div>
              <div className="font-mono text-[13px] tabular-nums">{findings.extras.cac?.agatston ?? "—"} Agatston</div>
            </div>
          </div>
        </div>
      )}
      <div className="flex items-center gap-1.5 pt-1 text-[10px] text-muted-foreground/70">
        <Sparkles className="size-3" /> Every number comes from the worker · research demo, not for clinical use
      </div>
    </div>
  )
}

function NoduleBlock({ n, idx, selected, onSelect }: { n: import("@/api/types").Nodule; idx: number; selected: boolean; onSelect: () => void }) {
  const [long, setLong] = useState(n.proposal?.long_mm != null ? String(n.proposal.long_mm) : n.long_mm != null ? String(n.long_mm) : "")
  const [short, setShort] = useState(n.proposal?.short_mm != null ? String(n.proposal.short_mm) : n.short_mm != null ? String(n.short_mm) : "")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const confirmed = n.confirmation.confirmed
  const approver = () => localStorage.getItem("sparkmd-approver") ?? "Dr. Joyce (demo)"
  const L = Number(long)
  const S = Number(short)
  const valid = Number.isFinite(L) && Number.isFinite(S) && S > 0 && S <= L && L <= 100

  const submit = async () => {
    setBusy(true)
    setErr(null)
    try {
      await api.confirm(n.nodule_id, L, S, approver())
      toast.success(`Confirmed ${n.lobe ?? "nodule"}`, { description: `${L.toFixed(1)} × ${S.toFixed(1)} mm · mean computed by the worker` })
    } catch (e) {
      const ae = e as { status?: number; message?: string }
      setErr(ae.status === 403 ? "Confirm only works from this device (loopback)." : ae.message ?? "Confirm failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={cn("rounded-md p-1.5 transition-colors", selected ? "bg-muted/70 ring-1 ring-border" : "hover:bg-muted/40")} onClick={onSelect}>
      <div className="flex items-start gap-2">
        <span className="mt-0.5 w-4 shrink-0 font-mono text-[10px] text-muted-foreground">{idx + 1}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5">
            <span className="truncate text-[12.5px] font-medium">{n.lobe ?? "Lobe —"}</span>
            <span className="font-mono text-[10px] text-muted-foreground">
              {n.type?.replace("_", "-")} · {hu(n.mean_hu)}
            </span>
            {confirmed && n.confirmation.edited && <span className="rounded bg-replay-soft px-1 text-[9px] text-replay">Edited</span>}
          </div>
          <div className="mt-1 flex items-end gap-2">
            <div>
              <div className="font-mono text-xl leading-none tabular-nums">
                {confirmed ? mmNum(n.mean_mm) : mmNum(n.proposal?.mean_mm)}
                <span className="text-[11px] text-muted-foreground"> mm</span>
              </div>
              <div className="mt-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">{confirmed ? "confirmed mean" : n.proposal ? "proposed (A7)" : "no proposal"}</div>
            </div>
            <div className="ml-auto text-right text-[10px] leading-snug text-muted-foreground">
              <div>detector box {mm(n.proposal?.box_mean_mm)}</div>
              {n.prior ? (
                <>
                  <div className={n.prior.growing ? "text-warn" : ""}>Δ {signed(n.prior.delta_mean_mm)} · {days(n.prior.interval_days)}</div>
                  <div>
                    {signed(n.prior.growth_per_12mo_mm)}/12 mo{n.prior.growth_normalized ? " · normalized" : ""} · VDT {days(n.prior.vdt_days)}
                  </div>
                </>
              ) : (
                <div>baseline · no prior comparison</div>
              )}
            </div>
          </div>
          {!confirmed && (
            <div className="mt-1.5 flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
              <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                long
                <Input value={long} onChange={(e) => setLong(e.target.value)} inputMode="decimal" aria-label={`Long diameter mm, nodule ${idx + 1}`} className="h-6 w-14 px-1.5 font-mono text-[11px]" />
              </label>
              <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                short
                <Input value={short} onChange={(e) => setShort(e.target.value)} inputMode="decimal" aria-label={`Short diameter mm, nodule ${idx + 1}`} className="h-6 w-14 px-1.5 font-mono text-[11px]" />
              </label>
              <Button size="sm" disabled={!valid || busy} onClick={() => void submit()} className="ml-auto h-6 gap-1 px-2 text-[10px]">
                {busy ? <Loader2 className="size-3 animate-spin" /> : <Check className="size-3" />} Confirm
              </Button>
            </div>
          )}
          {!confirmed && n.proposal == null && <div className="mt-1 text-[10px] text-warn">No proposal — enter a diameter</div>}
          {!confirmed && !valid && (long !== "" || short !== "") && <div className="mt-1 text-[10px] text-alert">Require 0 &lt; short ≤ long ≤ 100</div>}
          {err && <div className="mt-1 text-[10px] text-alert">{err}</div>}
          {confirmed && (
            <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
              <span>
                {mm(n.long_mm)} × {mm(n.short_mm)} · vol {mmNum(n.volume_mm3)} mm³
              </span>
              <button
                className="rounded px-1 text-muted-foreground hover:text-foreground"
                onClick={(e) => {
                  e.stopPropagation()
                  void api.confirm(n.nodule_id, Number(n.long_mm), Number(n.short_mm), approver()).catch((er) => toast.error(String((er as Error).message)))
                }}
                title={`Confirmed by ${n.confirmation.by ?? "—"} · re-confirm to recompute`}
              >
                by {n.confirmation.by} · re-confirm
              </button>
            </div>
          )}
          {n.confirmation.confirmed && (
            <div className="mt-1 flex items-center gap-1 text-[10px] text-run">
              <Activity className="size-3" /> Confirmed by {n.confirmation.by}; drafting reports
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Strip({ study, findings, selected, onSelect }: { study: StudyDetail; findings: Findings | undefined; selected: string | null; onSelect: (id: string) => void }) {
  const all = [...study.priors, { study_uid: study.study_uid, timepoint: study.timepoint, day_offset: study.day_offset, status: study.status, lung_rads: study.lung_rads }]
  const n = findings?.nodules.find((x) => x.nodule_id === selected)
  return (
    <div className="shrink-0 border-t px-4 pb-2 pt-2" style={{ containerType: "inline-size" }}>
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-medium text-muted-foreground">Longitudinal comparison · {all.length} total scans</span>
        <div className="ml-auto flex items-center gap-1.5">
          {n?.prior ? (
            <span className="font-mono text-[11px] text-muted-foreground">
              {signed(n.prior.delta_mean_mm)} · {days(n.prior.interval_days)} · VDT {days(n.prior.vdt_days)}
            </span>
          ) : (
            <span className="text-[11px] text-muted-foreground/70">baseline · no growth comparison</span>
          )}
        </div>
      </div>
      <div className="mt-1.5 flex gap-1.5 overflow-x-auto">
        {all.map((s) => {
          const mine = s.study_uid === study.study_uid
          return (
            <button
              key={s.study_uid}
              onClick={() => (mine ? undefined : onSelect(s.study_uid))}
              className={cn("flex h-9 min-w-0 flex-1 items-center gap-2 rounded-md border px-2 text-left text-[11px]", mine ? "border-foreground/30 bg-muted/60" : "hover:bg-muted/40")}
            >
              <span className="font-medium">{s.timepoint}</span>
              <span className="font-mono text-[10px] tabular-nums text-muted-foreground">{dayLabel(s.day_offset)}</span>
              <span className="ml-auto font-mono text-[10px] tabular-nums">
                {myPriorSize(findings, s.study_uid, n) !== "—" ? myPriorSize(findings, s.study_uid, n) : s.lung_rads ? `LR ${s.lung_rads}` : "—"}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function myPriorSize(findings: Findings | undefined, uid: string, n: import("@/api/types").Nodule | undefined) {
  if (n?.prior?.study_uid === uid) return mm(n.prior.mean_mm)
  if (findings?.study_uid === uid && n && findings.nodules.some((x) => x.nodule_id === n.nodule_id)) return mm(n.mean_mm)
  return "—"
}
