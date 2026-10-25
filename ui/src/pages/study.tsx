import { useRef, useState, useEffect } from "react"
import { useQueries, useQueryClient } from "@tanstack/react-query"
import { useReports, useStudy, useFindings, useWorklist } from "@/api/hooks"
import { api } from "@/api/client"
import { qk } from "@/api/keys"
import { viewerBus } from "@/api/viewer-bus"
import { useApp } from "@/lib/app-context"
import type { StudyDetail, Findings, Nodule } from "@/api/types"
import { mm, mmNum, hu, signed, days, dayLabel, STATUS_LABEL, lungRadsClass } from "@/lib/format"
import { compareScreens, patientScreens } from "@/lib/patient-studies"
import { cn } from "@/lib/utils"
import { readApprover } from "@/lib/prefs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Skeleton } from "@/components/ui/skeleton"
import { AlertTriangle, Check, ChevronDown, ChevronRight, Loader2, Activity, PanelRight } from "lucide-react"
import { toast } from "sonner"
import { StudyActivity } from "@/components/agent-log"
import { ViewerPane } from "@/components/viewer/viewer-pane"
import { ReportSheet } from "@/components/report-sheet"
import { RiskCard } from "@/components/risk-card"

export type InspectorTab = "assessment" | "activity"

export function StudyPage({ uid }: { uid: string }) {
  const { openStudy } = useApp()
  const { data: study, isLoading, isError } = useStudy(uid)
  const { data: findings } = useFindings(uid)
  const [tab, setTab] = useState<InspectorTab>("assessment")
  const [open, setOpen] = useState(() => localStorage.getItem("sparkmd-inspector") !== "closed")
  const [selected, onSelectNodule] = useState<string | null>(null)

  useEffect(() => {
    if (findings && !selected) onSelectNodule(findings.nodules[0]?.nodule_id ?? null)
  }, [findings, selected])
  useEffect(() => localStorage.setItem("sparkmd-inspector", open ? "open" : "closed"), [open])
  const [sheetOpen, setSheetOpen] = useState(false)

  const inspectorRef = useRef<HTMLDivElement>(null)

  // Keep the page (and an open review sheet) through a transient worker restart; error only with no data.
  if (isError && !study) return <div className="grid h-full place-items-center text-sm text-muted-foreground">Study not found — it may have been reset.</div>
  if (isLoading || !study)
    return (
      <div className="flex h-full flex-col gap-3 p-5">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-[420px] w-full" />
      </div>
    )


  return (
    <div className="flex h-full min-h-0 flex-col">
      <StudyHeader study={study} onToggleInspector={() => setOpen((o) => !o)} inspectorOpen={open} sheetOpen={sheetOpen} setSheetOpen={setSheetOpen} />
      <PriorReviewGuide study={study} />
      <div
        className={cn("grid min-h-0 flex-1", open ? "inspector-open" : "inspector-closed")}
        style={{ gridTemplateColumns: open ? "minmax(0,1fr) var(--inspector-w)" : "minmax(0,1fr) 0px", transition: "grid-template-columns 220ms ease" }}
      >
        <div className="flex min-h-0 min-w-0 flex-col">
          <div className="min-h-0 flex-1 px-3 pb-1">
            <ViewerPane
              uid={uid}
              findings={findings}
              selected={selected}
              onSelect={onSelectNodule}
              study={study}
              paused={sheetOpen}
              bottom={
                <Strip
                  study={study}
                  findings={findings}
                  selected={selected}
                  onOpenStudy={openStudy}
                  onCompare={() => viewerBus.emit({ command: "compare_prior", study_uid: uid, ...(selected ? { nodule_id: selected } : {}) })}
                />
              }
            />
          </div>
        </div>
        <div
          ref={inspectorRef}
          inert={!open}
          className={cn("min-h-0 min-w-0 overflow-hidden", !open && "invisible")}
          style={{ width: "var(--inspector-w)" }}
        >
          <div className="flex h-full w-(--inspector-w) flex-col">
            <Inspector uid={uid} tab={tab} setTab={setTab} findings={findings} selected={selected} setSelected={onSelectNodule} />
          </div>
        </div>
      </div>
    </div>
  )
}

function StudyHeader({ study, onToggleInspector, inspectorOpen, sheetOpen, setSheetOpen }: { study: StudyDetail; onToggleInspector: () => void; inspectorOpen: boolean; sheetOpen: boolean; setSheetOpen: (v: boolean) => void }) {
  const { data: reports } = useReports(study.study_uid)
  const { data: worklist } = useWorklist()
  const { openStudy } = useApp()
  const screens = patientScreens(study, worklist)
  // Any draft (either kind) is worth opening: the sheet has both tabs.
  const draft = reports?.find((r) => r.status === "draft")
  const lr = study.lung_rads
  return (
    <div className="flex min-h-[84px] shrink-0 items-center gap-4 px-5 py-2">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-[15px] font-semibold tracking-tight">Patient {study.patient_id} · {screens.length} {screens.length === 1 ? "screen" : "screens"}</span>
          <span className="text-xs text-muted-foreground">
            Chest CT · Time point {study.timepoint} · {dayLabel(study.day_offset)}
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
        <nav aria-label="Patient timepoints" className="mt-1.5 flex gap-1.5 overflow-x-auto pb-0.5">
          {screens.map((screen) => {
            const label = screen.status === "reported" ? "Drafts waiting" : STATUS_LABEL[screen.status] ?? screen.status
            return <button key={screen.study_uid} data-timepoint={screen.timepoint}
              aria-current={screen.study_uid === study.study_uid ? "page" : undefined}
              aria-label={`${screen.timepoint} ${dayLabel(screen.day_offset)} · ${label}`}
              title={label} onClick={() => { if (screen.study_uid !== study.study_uid) openStudy(screen.study_uid) }}
              className={cn("flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", screen.study_uid === study.study_uid ? "border-foreground/30 bg-muted font-medium" : "text-muted-foreground hover:bg-muted/50")}>
              <span className={screen.status === "approved" ? "text-ok" : "text-warn"} aria-hidden="true">{screen.status === "approved" ? "✓" : screen.status === "reported" ? "≡" : screen.status === "awaiting_confirmation" ? "●" : "○"}</span>
              {screen.timepoint} {dayLabel(screen.day_offset)}
              {screen.status === "reported" && <span className="text-warn">· drafts waiting</span>}
            </button>
          })}
        </nav>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2" data-hdr-reports={reports ? `${reports.length}:${reports.map((r) => r.kind + r.status).join(",")}` : "none"}>
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

function PriorReviewGuide({ study }: { study: StudyDetail }) {
  const { openStudy } = useApp()
  const { data: worklist } = useWorklist()
  const earlier = patientScreens(study, worklist).filter((s) => compareScreens(s, study) < 0)
  const queries = useQueries({ queries: earlier.map((s) => ({
    queryKey: qk.findings(s.study_uid), queryFn: () => api.findings(s.study_uid), staleTime: 5_000, retry: false,
  })) })
  const pending = earlier.find((s, i) => {
    const f = queries[i].isError ? undefined : queries[i].data
    return f ? f.pending_confirmation.length > 0 || f.nodules.some((n) => !n.confirmation.confirmed)
      : ["received", "organized", "analyzing", "awaiting_confirmation", "failed"].includes(s.status)
  })
  if (!pending) return null
  return <div role="status" className="mx-5 mb-2 flex shrink-0 items-center gap-2 rounded-md bg-warn-soft px-3 py-2 text-xs text-warn">
    <AlertTriangle className="size-3.5" />
    <span>Review {pending.timepoint} first: growth needs a confirmed prior</span>
    <Button variant="outline" size="sm" className="ml-auto h-6 text-[11px]" onClick={() => openStudy(pending.study_uid)}>Review {pending.timepoint}</Button>
  </div>
}

function ConfirmedPriorSize({ n, studyUid }: { n: Nodule; studyUid: string }) {
  const { data: study } = useStudy(studyUid)
  const priorUid = n.prior?.study_uid ?? [...(study?.priors ?? [])].sort(compareScreens).at(-1)?.study_uid ?? null
  const { data: prior, isError } = useFindings(priorUid)
  const matched = prior?.nodules.find((p) => p.track_id === n.track_id)
  if (!study?.priors.length) return null
  return <div className="mt-1 text-[10px] text-muted-foreground" data-confirmed-prior={n.nodule_id}>
    {matched?.confirmation.confirmed && matched.mean_mm != null
      ? `prior ${mm(matched.mean_mm)} · ${prior?.timepoint} confirmed`
      : prior ? "No confirmed matched prior" : isError ? "Confirmed prior unavailable" : "Loading confirmed prior…"}
  </div>
}

function Inspector({ uid, tab, setTab, findings, selected, setSelected }: { uid: string; tab: InspectorTab; setTab: (t: InspectorTab) => void; findings: Findings | undefined; selected: string | null; setSelected: (id: string) => void }) {
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
      <div className={cn("min-h-0 flex-1 overflow-y-auto", tab !== "assessment" && "pb-3")}>
        {tab === "assessment" ? (
          <Assessment findings={findings} selected={selected} setSelected={setSelected} />
        ) : (
          <StudyActivity studyUid={uid} />
        )}
      </div>
    </div>
  )
}

function Assessment({ findings, selected, setSelected }: { findings: Findings | undefined; selected: string | null; setSelected: (id: string) => void }) {
  const a = findings?.assessment
  const [openRules, setOpenRules] = useState(false)
  const { data: study } = useStudy(findings?.study_uid ?? null)
  if (!findings) return <div className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="size-3 animate-spin" /> Waiting for findings…</div>
  // Full-height column so the Sybil card sits at the panel bottom, and stays pinned there when the list scrolls.
  return (
    <div className="flex min-h-full flex-col gap-3">
      {a ? (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Management</div>
          <div className="mt-1 flex items-center gap-2">
            <span className={cn("rounded px-2 py-1 font-mono text-sm font-semibold tabular-nums", lungRadsClass(a.lung_rads))}>Lung-RADS {a.lung_rads}</span>
            {a.driver_nodule_id && <span className="text-[11px] text-muted-foreground">{findings.nodules.find((n) => n.nodule_id === a.driver_nodule_id)?.lobe ?? "—"} · driver nodule</span>}
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
          <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide"><AlertTriangle className="size-3" /> {STATUS_LABEL.awaiting_confirmation}</div>
          Confirm each diameter below. Growth, VDT and Lung-RADS are computed by code after the last confirm.
        </div>
      )}
      <NoduleList findings={findings} drafting={study?.status === "analyzed"} selected={selected} onSelectNodule={setSelected} />

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
      <div className="sticky bottom-0 mt-auto bg-background pb-3 pt-1">
        <RiskCard studyUid={findings.study_uid} patientId={findings.patient_id} timepoint={findings.timepoint} />
      </div>
    </div>
  )
}

type DiameterDraft = { long: string; short: string }

function initialDiameters(n: Nodule): DiameterDraft {
  return {
    long: String((n.confirmation.confirmed ? n.long_mm : n.proposal?.long_mm) ?? ""),
    short: String((n.confirmation.confirmed ? n.short_mm : n.proposal?.short_mm) ?? ""),
  }
}

function validDiameters({ long, short }: DiameterDraft) {
  const L = Number(long)
  const S = Number(short)
  return Number.isFinite(L) && Number.isFinite(S) && S > 0 && S <= L && L <= 100
}

function NoduleList({ findings, drafting, selected, onSelectNodule }: { findings: Findings; drafting: boolean; selected: string | null; onSelectNodule: (id: string) => void }) {
  const qc = useQueryClient()
  const [drafts, setDrafts] = useState<Record<string, DiameterDraft>>({})
  const [errors, setErrors] = useState<Record<string, string | undefined>>({})
  const [busy, setBusy] = useState(false)
  const draftFor = (n: Nodule) => drafts[n.nodule_id] ?? initialDiameters(n)
  const pending = findings.nodules.filter((n) => !n.confirmation.confirmed || drafts[n.nodule_id])
  const cancel = (id: string) => {
    setDrafts((old) => {
      const next = { ...old }
      delete next[id]
      return next
    })
    setErrors((old) => ({ ...old, [id]: undefined }))
  }

  // Bulk confirmation uses the same endpoint as a single row; all derived values stay in the worker.
  const confirm = async (nodes: Nodule[]) => {
    if (busy || !nodes.length || !nodes.every((n) => validDiameters(draftFor(n)))) return
    const values = nodes.map((n) => ({ id: n.nodule_id, ...draftFor(n) }))
    const by = readApprover()
    const succeeded: string[] = []
    setBusy(true)
    setErrors((old) => {
      const next = { ...old }
      for (const { id } of values) delete next[id]
      return next
    })
    try {
      for (const { id, long, short } of values) {
        try {
          await api.confirm(id, Number(long), Number(short), by)
          succeeded.push(id)
        } catch (e) {
          const ae = e as { status?: number; message?: string }
          setErrors((old) => ({ ...old, [id]: ae.status === 403 ? "Confirm only works from this device (loopback)." : ae.message ?? "Confirm failed" }))
        }
      }
      // A partially successful batch still refreshes each confirmed row and retains failed edits.
      await Promise.all([
        qc.invalidateQueries({ queryKey: qk.findings(findings.study_uid) }),
        qc.invalidateQueries({ queryKey: qk.study(findings.study_uid) }),
        qc.invalidateQueries({ queryKey: qk.worklist }),
      ])
      setDrafts((old) => {
        const next = { ...old }
        for (const id of succeeded) delete next[id]
        return next
      })
      if (succeeded.length) toast.success(`Confirmed ${succeeded.length} nodule${succeeded.length === 1 ? "" : "s"}`, { description: "Mean, growth and category are computed by the worker." })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>Nodules · {findings.nodules.length}</span>
        {findings.placeholder && <span className="rounded bg-replay-soft px-1.5 py-0.5 text-[9px] normal-case text-replay">placeholder numbers</span>}
        <Button size="sm" variant="outline" className="h-6 px-2 text-[10px] normal-case" disabled={busy || !pending.length || !pending.every((n) => validDiameters(draftFor(n)))} onClick={() => void confirm(pending)}>Confirm all</Button>
      </div>
      <div className="space-y-2">
        {findings.nodules.map((n, i) => (
          <NoduleBlock key={n.nodule_id} studyUid={findings.study_uid} n={n} idx={i} drafting={drafting} selected={selected === n.nodule_id} onSelect={() => onSelectNodule(n.nodule_id)}
            draft={draftFor(n)} editing={!n.confirmation.confirmed || !!drafts[n.nodule_id]} busy={busy} error={errors[n.nodule_id]}
            onDraft={(draft) => setDrafts((old) => ({ ...old, [n.nodule_id]: draft }))}
            onEdit={() => setDrafts((old) => ({ ...old, [n.nodule_id]: initialDiameters(n) }))}
            onCancel={() => cancel(n.nodule_id)} onConfirm={() => void confirm([n])} />
        ))}
        {!findings.nodules.length && <div className="text-xs text-muted-foreground">No nodules detected.</div>}
      </div>
    </div>
  )
}

function NoduleBlock({ studyUid, n, idx, drafting, selected, onSelect, draft, editing, busy, error, onDraft, onEdit, onCancel, onConfirm }: {
  studyUid: string; n: Nodule; idx: number; drafting: boolean; selected: boolean; onSelect: () => void
  draft: DiameterDraft; editing: boolean; busy: boolean; error: string | undefined
  onDraft: (draft: DiameterDraft) => void; onEdit: () => void; onCancel: () => void; onConfirm: () => void
}) {
  const confirmed = n.confirmation.confirmed
  const valid = validDiameters(draft)

  return (
    <div className={cn("rounded-lg border p-2 transition-colors", selected ? "border-foreground/25 bg-muted/70" : "hover:bg-muted/40")} onClick={onSelect}>
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
              <ConfirmedPriorSize n={n} studyUid={studyUid} />
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
          {editing && (
            <div className="mt-1.5 flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
              <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                long
                <Input value={draft.long} disabled={busy} onChange={(e) => onDraft({ ...draft, long: e.target.value })} inputMode="decimal" aria-label={`Long diameter mm, nodule ${idx + 1}`} className="h-6 w-14 px-1.5 font-mono text-[11px]" />
              </label>
              <label className="flex items-center gap-1 text-[10px] text-muted-foreground">
                short
                <Input value={draft.short} disabled={busy} onChange={(e) => onDraft({ ...draft, short: e.target.value })} inputMode="decimal" aria-label={`Short diameter mm, nodule ${idx + 1}`} className="h-6 w-14 px-1.5 font-mono text-[11px]" />
              </label>
              <Button size="sm" disabled={!valid || busy} onClick={onConfirm} className="ml-auto h-6 gap-1 px-2 text-[10px]">
                {busy ? <Loader2 className="size-3 animate-spin" /> : <Check className="size-3" />} {confirmed ? "Re-confirm" : "Confirm"}
              </Button>
              {confirmed && <Button size="sm" variant="ghost" disabled={busy} onClick={onCancel} className="h-6 px-1 text-[10px]">Cancel</Button>}
            </div>
          )}
          {!confirmed && n.proposal == null && <div className="mt-1 text-[10px] text-warn">No proposal — enter a diameter</div>}
          {editing && !valid && (draft.long !== "" || draft.short !== "") && <div className="mt-1 text-[10px] text-alert">Require 0 &lt; short ≤ long ≤ 100</div>}
          {error && <div role="alert" className="mt-1 text-[10px] text-alert">{error}</div>}
          {confirmed && (
            <div className="mt-1 flex items-center justify-between text-[10px] text-muted-foreground">
              <span>
                {mm(n.long_mm)} × {mm(n.short_mm)} · vol {mmNum(n.volume_mm3)} mm³
              </span>
              {!editing && <button
                disabled={busy}
                className="rounded px-1 text-muted-foreground hover:text-foreground disabled:opacity-40"
                onClick={(e) => {
                  e.stopPropagation()
                  onEdit()
                }}
                aria-label={`Edit diameters, nodule ${idx + 1}`}
                title={`Confirmed by ${n.confirmation.by ?? "—"}`}
              >
                Edit / re-confirm
              </button>}
            </div>
          )}
          {n.confirmation.confirmed && (
            <div className="mt-1 flex items-center gap-1 text-[10px] text-run">
              <Activity className="size-3" /> Confirmed by {n.confirmation.by}{drafting && "; drafting reports"}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Strip({ study, findings, selected, onOpenStudy, onCompare }: { study: StudyDetail; findings: Findings | undefined; selected: string | null; onOpenStudy: (studyUid: string) => void; onCompare: () => void }) {
  const all = [...study.priors, { study_uid: study.study_uid, timepoint: study.timepoint, day_offset: study.day_offset, status: study.status, lung_rads: study.lung_rads }]
  const n = findings?.nodules.find((x) => x.nodule_id === selected)
  return (
    <div className="shrink-0 px-4 pb-2 pt-2" style={{ containerType: "inline-size" }}>
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
          <Button size="sm" variant="outline" className="h-6 px-2 text-[10px]" disabled={!n?.prior} onClick={onCompare}>Compare</Button>
        </div>
      </div>
      <div className="mt-1.5 flex gap-1.5 overflow-x-auto">
        {all.map((s) => {
          const mine = s.study_uid === study.study_uid
          return (
            <button
              key={s.study_uid}
              onClick={() => { if (!mine) onOpenStudy(s.study_uid) }}
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
