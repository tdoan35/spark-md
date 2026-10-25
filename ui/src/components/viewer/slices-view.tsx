import { useEffect, useMemo, useRef, useState } from "react"
import { viewerBus } from "@/api/viewer-bus"
import type { Findings, KeySlice, StudyDetail } from "@/api/types"
import { cn } from "@/lib/utils"
import { mm } from "@/lib/format"
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

export function CompareView({ findings, selected, onSelect, study }: { findings: Findings | undefined; selected: string | null; onSelect: (id: string) => void; study: StudyDetail }) {
  const nodule = findings?.nodules.find((n) => n.nodule_id === selected) ?? findings?.nodules[0]
  return (
    <div className="flex h-full flex-col p-2">
      <div className="mb-1 flex items-center gap-2 px-1 text-[10px] text-white/50">
        <Columns2 className="size-3.5" /> Prior | change | current · all values from `nodule.prior`
        <div className="ml-auto flex items-center gap-1">
          {findings?.nodules.map((n, i) => (
            <button key={n.nodule_id} onClick={() => onSelect(n.nodule_id)} className={cn("rounded px-1.5 font-mono text-[10px]", n.nodule_id === selected ? "bg-white/20 text-white" : "text-white/40 hover:bg-white/10")}>
              #{i + 1}
            </button>
          ))}
        </div>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[1fr_168px_1fr] gap-2">
        <div className="grid place-items-center rounded bg-white/5 p-2 text-[11px] text-white/60">
          {nodule?.prior ? (
            <div className="text-center">
              <div className="font-mono text-2xl text-white/90">{mm(nodule.prior.mean_mm)}</div>
              <div className="mt-1">prior {study.priors.find((p) => p.study_uid === nodule.prior?.study_uid)?.timepoint ?? "—"}</div>
              <div className="text-[10px] text-white/40">{nodule.prior.interval_days} d</div>
            </div>
          ) : (
            <span>baseline — no prior</span>
          )}
        </div>
        <div className="grid place-items-center text-center">
          {nodule?.prior ? (
            <>
              <div className="font-mono text-lg text-white/90">{nodule.prior.delta_mean_mm! > 0 ? "+" : ""}{nodule.prior.delta_mean_mm?.toFixed(1)} mm</div>
              <div className="text-[10px] text-white/50">over {nodule.prior.interval_days} d</div>
              <div className="mt-1 font-mono text-[11px] text-white/70">{nodule.prior.growth_per_12mo_mm?.toFixed(1)} mm / 12 mo{nodule.prior.growth_normalized ? " · normalized" : ""}</div>
              <div className="text-[10px] text-white/40">VDT {nodule.prior.vdt_days ?? "n/a"} d</div>
            </>
          ) : (
            <span className="text-[11px] text-white/40">no comparison</span>
          )}
        </div>
        <div className="grid place-items-center rounded bg-white/5 p-2 text-[11px] text-white/60">
          <div className="text-center">
            <div className="font-mono text-2xl text-white/90">{mm(nodule?.mean_mm ?? nodule?.proposal?.mean_mm)}</div>
            <div className="mt-1">current {study.timepoint}</div>
            <div className="text-[10px] text-white/40">{nodule?.lobe ?? "—"}</div>
          </div>
        </div>
      </div>
      <div className="mt-1 flex items-center gap-1 px-1 text-[10px] text-white/40">
        <ChevronLeft className="size-3" />
        {nodule ? `${nodule.nodule_id}` : "—"}
        <ChevronRight className="size-3" />
      </div>
    </div>
  )
}
