import { useEffect } from "react"
import { viewerBus } from "@/api/viewer-bus"
import { useFindings } from "@/api/hooks"
import type { Findings, KeySlice, StudyDetail } from "@/api/types"
import { cn } from "@/lib/utils"
import { days, mm, signed } from "@/lib/format"
import { ChevronLeft, ChevronRight, Columns2 } from "lucide-react"
import { usePref } from "@/lib/prefs"
import { SliceImage, sliceSizeLabel } from "./slices/slice-image"
import { SliceColorToggle } from "./slices/slice-color-toggle"
import { SliceCarousel } from "./slices/slice-carousel"

export function SlicesView({ uid, findings, selected, onSelect }: { uid: string; findings: Findings | undefined; selected: string | null; onSelect: (id: string) => void }) {
  const [color, setColor] = usePref("sparkmd-slice-color", true)
  useEffect(() => viewerBus.subscribe((cmd) => {
    if (cmd.study_uid !== uid) return
    if (cmd.command === "show_nodule" && cmd.nodule_id) onSelect(cmd.nodule_id)
  }), [uid, onSelect])
  if (!findings) return <div className="grid h-full place-items-center text-[11px] text-white/50">Waiting for findings…</div>
  const stack = findings.assets.slice_stack
  const slice = findings.assets.key_slices?.find((s) => s.nodule_id === selected) ?? findings.assets.key_slices?.[0]
  const sliceNodule = findings.nodules.find((n) => n.nodule_id === slice?.nodule_id)
  const imageUrl = slice ? (slice.nodule_id && !slice.name.includes(slice.nodule_id) ? `/api/studies/${uid}/assets/key_axial_${slice.nodule_id}.png` : slice.url) : null
  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <SliceColorToggle color={color} onChange={setColor} />
      <div className="flex h-10 shrink-0 items-center gap-2 px-3 pr-28 text-[10px] text-white/50">
        <span>{stack ? "Axial CT stack" : "Axial key slice"}</span>
        <span>· {color ? "Jet colour" : "Grayscale"} · lung window</span>
      </div>
      {stack ? (
        <SliceCarousel key={`${uid}:${stack.url_pattern}`} stack={stack} nodules={findings.nodules} selected={selected} driver={findings.assessment?.driver_nodule_id ?? null} color={color} onSelect={onSelect} />
      ) : (
        <div className="min-h-0 flex-1 p-3">
          {slice && imageUrl ? <SliceImage src={imageUrl} alt={`Key slice for ${slice.nodule_id}`} color={color} box={slice.box_px} sizeLabel={sliceSizeLabel(sliceNodule?.mean_mm, sliceNodule?.proposal?.mean_mm)} fit /> : <div className="grid h-full place-items-center text-[11px] text-white/50">No key slice available</div>}
        </div>
      )}
    </div>
  )
}

function CompareSlice({ slice, label, diameter, proposed, pending, color }: { slice: KeySlice | undefined; label: string; diameter: number | null | undefined; proposed?: number | null; pending?: boolean; color: boolean }) {
  return (
    <div className="flex min-h-0 min-w-0 flex-col rounded bg-white/5 p-2">
      <div className="mb-2 flex items-baseline justify-between gap-2 text-[11px] text-white/60">
        <span>{label}</span>
        <span className="font-mono text-lg text-white/90">{mm(diameter)}</span>
      </div>
      <div className="min-h-0 flex-1">
        {slice ? <SliceImage src={slice.url} alt={`${label} axial key slice with nodule box`} color={color} box={slice.box_px} sizeLabel={sliceSizeLabel(diameter, proposed)} fit /> : <div className="grid h-full place-items-center text-[11px] text-white/50">{pending ? "Loading matched prior…" : "Matched key slice unavailable"}</div>}
      </div>
      <div className="mt-2 text-[10px] text-white/40">Axial key slice · worker-supplied box</div>
    </div>
  )
}

export function CompareView({ findings, selected, onSelect, study }: { findings: Findings | undefined; selected: string | null; onSelect: (id: string) => void; study: StudyDetail }) {
  const [color, setColor] = usePref("sparkmd-slice-color", true)
  const nodule = findings?.nodules.find((n) => n.nodule_id === selected) ?? findings?.nodules[0]
  const prior = nodule?.prior
  const pq = useFindings(prior?.study_uid ?? null)
  // Match the longitudinal track, never the first prior nodule (T0 can contain several).
  const priorNodule = pq.data?.nodules.find((n) => n.track_id === nodule?.track_id)
  const priorSlice = priorNodule ? pq.data?.assets.key_slices?.find((s) => s.nodule_id === priorNodule.nodule_id && s.plane === "axial") : undefined
  const currentSlice = findings?.assets.key_slices?.find((s) => s.nodule_id === nodule?.nodule_id && s.plane === "axial")
  const priorTimepoint = study.priors.find((p) => p.study_uid === prior?.study_uid)?.timepoint ?? "prior"
  return (
    <div className="relative flex h-full min-h-0 flex-col p-2">
      <SliceColorToggle color={color} onChange={setColor} />
      <div className="mb-2 flex min-h-9 items-center gap-2 px-1 pr-28 text-[10px] text-white/50">
        <Columns2 className="size-3.5" /> Longitudinal comparison · confirmed measurements
        <div className="ml-auto flex items-center gap-1">
          {findings?.nodules.map((n, i) => (
            <button key={n.nodule_id} onClick={() => onSelect(n.nodule_id)} className={cn("rounded px-1.5 font-mono text-[10px]", n.nodule_id === selected ? "bg-white/20 text-white" : "text-white/40 hover:bg-white/10")}>
              #{i + 1}
            </button>
          ))}
        </div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_136px_minmax(0,1fr)] gap-2">
        {prior ? (
          <CompareSlice slice={priorSlice} label={`Prior · ${priorTimepoint}`} diameter={prior.mean_mm} pending={pq.isLoading} color={color} />
        ) : (
          <div className="grid place-items-center text-[11px] text-white/50">Baseline — no prior</div>
        )}
        <div className="flex flex-col items-center justify-center gap-1 text-center">
          {prior ? (
            <>
              <div className="font-mono text-xl text-white/90">{signed(prior.delta_mean_mm)}</div>
              <div className="text-[11px] text-white/60">over {prior.interval_days ?? "—"} days</div>
              {prior.growing != null && <div className={cn("mt-2 rounded px-2 py-1 text-[11px]", prior.growing ? "bg-warn-soft text-warn" : "bg-white/5 text-white/60")}>{prior.growing ? "Growth confirmed" : "No growth flagged"}</div>}
              <div className="mt-2 font-mono text-[10px] text-white/60">{mm(prior.growth_per_12mo_mm)} / 12 mo</div>
              {prior.growth_normalized && <div className="text-[10px] text-white/40">normalized to 12 mo</div>}
              <div className="text-[10px] text-white/50">VDT {days(prior.vdt_days)}</div>
            </>
          ) : (
            <span className="text-[11px] text-white/40">No comparison</span>
          )}
        </div>
        <CompareSlice slice={currentSlice} label={`Current · ${study.timepoint}`} diameter={nodule?.mean_mm} proposed={nodule?.proposal?.mean_mm} color={color} />
      </div>
      <div className="mt-2 flex items-center gap-1 px-1 text-[10px] text-white/40">
        <ChevronLeft className="size-3" />
        <span>{nodule?.lobe ?? "No nodule selected"} · matched by longitudinal track</span>
        <ChevronRight className="size-3" />
      </div>
    </div>
  )
}
