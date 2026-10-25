import { useEffect, useMemo, useRef, useState } from "react"
import { viewerBus } from "@/api/viewer-bus"
import { useFindings } from "@/api/hooks"
import type { Findings, KeySlice, StudyDetail } from "@/api/types"
import { cn } from "@/lib/utils"
import { days, mm, signed } from "@/lib/format"
import { ChevronLeft, ChevronRight, Columns2 } from "lucide-react"
import { usePref } from "@/lib/prefs"

/** Bracket overlay in PNG pixel space: pad = max(3, W/128) px outside the box, 2 px non-scaling stroke. */
function Bracket({ box, w, h, color }: { box: [number, number, number, number] | null; w: number; h: number; color: string }) {
  if (!box) return null
  const [x, y, bw, bh] = box
  const pad = Math.max(3, w / 128)
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
      <rect x={x - pad} y={y - pad} width={bw + pad * 2} height={bh + pad * 2} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function SlicesView({ uid, findings, selected, onSelect }: { uid: string; findings: Findings | undefined; selected: string | null; onSelect: (id: string) => void }) {
  const stack = findings?.assets.slice_stack ?? null
  const [color, setColor] = usePref("sparkmd-slice-color", false)
  const [index, setIndex] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const wheelAcc = useRef(0)
  const wrap = useRef<HTMLDivElement>(null)

  const nodeSlice = useMemo(() => stack?.nodule_slices.find((s) => s.nodule_id === selected) ?? null, [stack, selected])

  useEffect(() => {
    if (!stack) return
    setIndex((i) => (nodeSlice ? nodeSlice.index : (i ?? Math.floor(stack.count / 2))))
    // Only on study/nodule change; paging is free afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stack?.url_pattern, nodeSlice?.nodule_id])

  useEffect(() => {
    const off = viewerBus.subscribe((cmd) => {
      if (cmd.command === "show_nodule" && "nodule_id" in cmd && cmd.nodule_id) onSelect(cmd.nodule_id)
    })
    return off
  }, [onSelect])

  useEffect(() => {
    const el = wrap.current
    if (!el || !stack) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      wheelAcc.current += e.deltaY
      const step = Math.trunc(wheelAcc.current / 100)
      if (step !== 0) {
        wheelAcc.current -= step * 100
        setIndex((i) => Math.min(stack.count - 1, Math.max(0, (i ?? 0) + step)))
      }
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [stack])

  // The mock names stack_NNN.jpg; the worker names stack_<i>.jpg with a raw index (08's `index_digits`).
  const url = (i: number) => (stack ? stack.url_pattern.replace("{i}", String(i).padStart(stack.index_digits, "0")) : null)
  // The worker writes key slices named for the nodule id; the mock uses per-study names.
  const keySliceUrl = (ks: KeySlice) => (ks.nodule_id && !ks.name.includes(ks.nodule_id) ? `/api/studies/${uid}/assets/key_axial_${ks.nodule_id}.png` : ks.url)

  if (!findings) return <div className="grid h-full place-items-center text-[11px] text-white/50">Waiting for findings…</div>

  if (!stack) {
    const ks = findings.assets.key_slices ?? []

    const slice = ks.find((k) => k.nodule_id === selected) ?? ks[0]
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-2 px-3 pb-1 text-[10px] text-white/50">
          <span>Axial key slice</span>
          <span className="ml-auto font-mono">{slice ? slice.name : "no key slice"}</span>
        </div>
        <div className="relative grid min-h-0 flex-1 place-items-center overflow-hidden p-3">
          {slice && (
            <div ref={wrap} className="relative" style={{ containerType: "size" }}>
              <div className="relative" style={{ width: "min(100cqw, calc(100cqh * 1))" }}>
                <img src={keySliceUrl(slice)} alt={`Key slice for ${slice.nodule_id}`} className="block w-full" style={{ imageRendering: "pixelated", filter: color ? "none" : "grayscale(1)" }} onLoad={() => setLoading(false)} />
                <Bracket box={slice.box_px} w={512} h={512} color="var(--warn)" />
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  const cur = index ?? 0
  const onSlice = nodeSlice ? Math.abs(cur - nodeSlice.index) <= nodeSlice.half_range : false
  const offset = nodeSlice ? cur - nodeSlice.index : 0
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 px-3 pb-1 text-[10px] text-white/50">
        <span>Axial CT stack</span>
        <span className="ml-auto rounded bg-white/5 px-1.5 py-0.5">
          {nodeSlice && onSlice ? `nodule selected · on this slice` : nodeSlice ? `selected nodule ${Math.abs(offset)} slices ${offset > 0 ? "below" : "above"}` : "no nodule selected"}
        </span>
        <button onClick={() => setColor((c) => !c)} className={cn("rounded px-1.5 py-0.5", color ? "bg-white/15 text-white" : "text-white/50 hover:text-white")}>
          {color ? "Color" : "Gray"}
        </button>
      </div>
      <div ref={wrap} className="relative min-h-0 flex-1 overflow-hidden px-2 pb-7">
        <div className="flex h-full items-center justify-center gap-0">
          {[-2, -1, 0, 1, 2].map((o) => {
            const i = cur + o
            if (i < 0 || i >= stack.count) return <div key={o} className="shrink-0" style={{ width: Math.abs(o) === 1 ? "14%" : "8.5%" }} />
            return (
              <button
                key={i}
                onClick={() => o !== 0 && setIndex(i)}
                className="relative shrink-0 overflow-hidden rounded"
                style={{
                  width: Math.abs(o) === 0 ? "40%" : Math.abs(o) === 1 ? "14%" : "8.5%",
                  transform: `translateX(${o * (Math.abs(o) === 1 ? 18 : 30)}%) scaleX(${Math.abs(o) === 1 ? 1.15 : 1.3}) rotateY(${o === 0 ? 0 : -o * 34}deg)`,
                  filter: o === 0 ? "none" : `brightness(${1 - 0.13 * Math.abs(o)})`,
                  zIndex: o === 0 ? 3 : 2,
                }}
              >
                <img src={url(i)!} alt={`Slice ${i}`} className="block w-full" style={{ imageRendering: "pixelated", filter: color ? undefined : "grayscale(1)" }} />
                {o === 0 && <Bracket box={onSlice ? nodeSlice?.box_px ?? null : null} w={256} h={256} color="var(--warn)" />}
              </button>
            )
          })}
        </div>
        <div className="absolute bottom-1 left-3 font-mono text-[10px] text-white/50">Slice {cur + 1} / {stack.count}</div>
        <div className="absolute bottom-1 right-3 font-mono text-[10px] text-white/50">z {stack.z_mm[cur]?.toFixed(1) ?? "—"} mm</div>
        <input
          type="range"
          min={0}
          max={stack.count - 1}
          value={cur}
          onChange={(e) => setIndex(Number(e.target.value))}
          className="absolute bottom-2.5 left-1/2 w-[46%] -translate-x-1/2 accent-[var(--warn)]"
          aria-label={`Slice ${cur + 1} of ${stack.count}`}
        />
        <div className="absolute right-1 top-1 flex flex-col gap-0.5">
          {(findings.nodules ?? []).map((n, i) => (
            <button key={n.nodule_id} onClick={() => onSelect(n.nodule_id)} className={cn("rounded px-1 py-0.5 font-mono text-[10px]", n.nodule_id === selected ? "bg-white/20 text-white" : "text-white/40 hover:bg-white/10")} title={n.lobe ?? undefined}>
              {i + 1}
            </button>
          ))}
        </div>
        <div className="absolute bottom-1 left-1/2 hidden -translate-x-1/2 text-[9px] text-white/30">{loading ? "loading…" : ""}</div>
      </div>
    </div>
  )
}

function CompareSlice({ slice, label, diameter, pending }: { slice: KeySlice | undefined; label: string; diameter: number | null | undefined; pending?: boolean }) {
  const [image, setImage] = useState<{ url: string; w: number; h: number } | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const loaded = image?.url === slice?.url ? image : null
  return (
    <div className="flex min-h-0 min-w-0 flex-col rounded bg-white/5 p-2">
      <div className="mb-2 flex items-baseline justify-between gap-2 text-[11px] text-white/60">
        <span>{label}</span>
        <span className="font-mono text-lg text-white/90">{mm(diameter)}</span>
      </div>
      <div className="grid min-h-0 flex-1 place-items-center" style={{ containerType: "size" }}>
        {slice && failed !== slice.url ? (
          <div className="relative" style={{ width: "min(100cqw, 100cqh)" }}>
            <img
              src={slice.url}
              alt={`${label} axial key slice with nodule box`}
              className="block w-full"
              style={{ imageRendering: "pixelated" }}
              onLoad={(e) => setImage({ url: slice.url, w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
              onError={() => setFailed(slice.url)}
            />
            {loaded && <Bracket box={slice.box_px} w={loaded.w} h={loaded.h} color="var(--warn)" />}
          </div>
        ) : (
          <span className="text-center text-[11px] text-white/50">{pending ? "Loading matched prior…" : "Matched key slice unavailable"}</span>
        )}
      </div>
      <div className="mt-2 text-[10px] text-white/40">Axial key slice · worker-supplied box</div>
    </div>
  )
}

export function CompareView({ findings, selected, onSelect, study }: { findings: Findings | undefined; selected: string | null; onSelect: (id: string) => void; study: StudyDetail }) {
  const nodule = findings?.nodules.find((n) => n.nodule_id === selected) ?? findings?.nodules[0]
  const prior = nodule?.prior
  const pq = useFindings(prior?.study_uid ?? null)
  // Match the longitudinal track, never the first prior nodule (T0 can contain several).
  const priorNodule = pq.data?.nodules.find((n) => n.track_id === nodule?.track_id)
  const priorSlice = priorNodule ? pq.data?.assets.key_slices?.find((s) => s.nodule_id === priorNodule.nodule_id && s.plane === "axial") : undefined
  const currentSlice = findings?.assets.key_slices?.find((s) => s.nodule_id === nodule?.nodule_id && s.plane === "axial")
  const priorTimepoint = study.priors.find((p) => p.study_uid === prior?.study_uid)?.timepoint ?? "prior"
  return (
    <div className="flex h-full min-h-0 flex-col p-2">
      <div className="mb-2 flex items-center gap-2 px-1 text-[10px] text-white/50">
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
          <CompareSlice slice={priorSlice} label={`Prior · ${priorTimepoint}`} diameter={prior.mean_mm} pending={pq.isLoading} />
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
        <CompareSlice slice={currentSlice} label={`Current · ${study.timepoint}`} diameter={nodule?.mean_mm} />
      </div>
      <div className="mt-2 flex items-center gap-1 px-1 text-[10px] text-white/40">
        <ChevronLeft className="size-3" />
        <span>{nodule?.lobe ?? "No nodule selected"} · matched by longitudinal track</span>
        <ChevronRight className="size-3" />
      </div>
    </div>
  )
}
