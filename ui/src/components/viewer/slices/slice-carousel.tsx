import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import type { Findings, SliceStack } from "@/api/types"
import { mm } from "@/lib/format"
import { SliceImage, preloadSlice } from "./slice-image"

type Props = {
  stack: SliceStack
  nodules: Findings["nodules"]
  selected: string | null
  driver: string | null
  color: boolean
  onSelect: (id: string) => void
}

const clamp = (index: number, count: number) => Math.max(0, Math.min(Math.max(0, count - 1), Math.round(index)))
const sliceUrl = (stack: SliceStack, index: number) => stack.url_pattern.replace("{i}", String(index).padStart(stack.index_digits, "0"))

function noduleIndex(stack: SliceStack, nodules: Findings["nodules"], id: string | null): number | null {
  if (!id) return null
  const metadata = stack.nodule_slices.find((slice) => slice.nodule_id === id)
  if (metadata) return clamp(metadata.index, stack.count)
  const z = nodules.find((nodule) => nodule.nodule_id === id)?.center_mm?.[2]
  if (z == null || !Number.isFinite(z)) return null
  let nearest: number | null = null
  let distance = Infinity
  stack.z_mm.slice(0, stack.count).forEach((value, index) => {
    if (Number.isFinite(value) && Math.abs(value - z) < distance) {
      nearest = index
      distance = Math.abs(value - z)
    }
  })
  return nearest
}

/** A study change remounts the well, cancelling its animation and interaction state. */
export function SliceCarousel(props: Props) {
  return <CarouselWell key={`${props.stack.url_pattern}:${props.stack.count}`} {...props} />
}

function CarouselWell({ stack, nodules, selected, driver, color, onSelect }: Props) {
  const [initial] = useState(() => noduleIndex(stack, nodules, selected) ?? Math.floor(stack.count / 2))
  const [target, setTarget] = useState(initial)
  const [position, setPosition] = useState(initial)
  const targetRef = useRef(initial)
  const positionRef = useRef(initial)
  const transition = useRef({ target: initial, from: initial })
  if (transition.current.target !== target) {
    transition.current = { target, from: positionRef.current }
  }
  const frame = useRef<number | null>(null)
  const well = useRef<HTMLDivElement>(null)
  const previousSelected = useRef(selected)
  const markerSelection = useRef<string | null>(null)
  const wheelRemainder = useRef(0)
  const drag = useRef<{ id: number; x: number; index: number; moved: boolean } | null>(null)
  const suppressClick = useRef(false)

  const navigate = useCallback((index: number) => {
    const next = clamp(index, stack.count)
    targetRef.current = next
    setTarget(next)
  }, [stack.count])

  useEffect(() => {
    if (previousSelected.current === selected) return
    previousSelected.current = selected
    if (markerSelection.current === selected) {
      markerSelection.current = null
      return
    }
    markerSelection.current = null
    const next = noduleIndex(stack, nodules, selected)
    if (next != null) navigate(next)
  }, [selected, stack, nodules, navigate])

  useEffect(() => {
    const from = transition.current.from
    if (from === target) return
    const start = performance.now()
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / 240)
      const next = progress === 1 ? target : from + (target - from) * (1 - (1 - progress) ** 3)
      positionRef.current = next
      setPosition(next)
      frame.current = progress < 1 ? requestAnimationFrame(tick) : null
    }
    frame.current = requestAnimationFrame(tick)
    return () => {
      if (frame.current != null) cancelAnimationFrame(frame.current)
      frame.current = null
    }
  }, [target])

  useEffect(() => {
    for (let index = Math.max(0, target - 3); index <= Math.min(stack.count - 1, target + 3); index++) {
      preloadSlice(sliceUrl(stack, index))
    }
  }, [target, stack.url_pattern, stack.index_digits, stack.count])

  useEffect(() => {
    const element = well.current
    if (!element) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY
      const pixels = delta * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element.clientHeight : 1)
      if (Math.sign(pixels) !== Math.sign(wheelRemainder.current)) wheelRemainder.current = 0
      wheelRemainder.current += pixels
      const steps = Math.trunc(wheelRemainder.current / 55)
      if (steps) {
        wheelRemainder.current -= steps * 55
        navigate(targetRef.current + steps)
      }
    }
    element.addEventListener("wheel", onWheel, { passive: false })
    return () => element.removeEventListener("wheel", onWheel)
  }, [navigate])

  const markers = useMemo(() => nodules.flatMap((nodule, row) => {
    const metadata = stack.nodule_slices.find((slice) => slice.nodule_id === nodule.nodule_id)
    const center = metadata?.index ?? noduleIndex(stack, nodules, nodule.nodule_id)
    if (center == null) return []
    const range = metadata ? Math.max(0, Math.floor(metadata.half_range)) : 0
    const start = Math.max(0, Math.ceil(center - range))
    const end = Math.min(stack.count - 1, Math.floor(center + range))
    return Array.from({ length: Math.max(0, end - start + 1) }, (_, offset) => ({
      index: start + offset,
      id: nodule.nodule_id,
      row: row % 3,
      title: `${nodule.lobe ?? "Lobe unavailable"} · ${nodule.mean_mm == null ? "proposed mean" : "mean"} ${mm(nodule.mean_mm ?? nodule.proposal?.mean_mm)}`,
    }))
  }), [stack, nodules])

  // Large slider jumps crossfade the old centre into the destination's neighbours;
  // never decode every intervening slice just to animate a 158-slice jump.
  const from = transition.current.from
  const jumping = Math.abs(target - from) > 5 && position !== target
  const blend = jumping ? Math.min(1, Math.abs((position - from) / (target - from))) : 1
  const nearest = jumping ? target : clamp(position, stack.count)
  const visible = Array.from({ length: jumping ? 5 : 7 }, (_, offset) => nearest + offset - (jumping ? 2 : 3))
    .filter((index) => index >= 0 && index < stack.count && (jumping || Math.abs(index - position) <= 2.75))
  if (jumping) visible.push(clamp(from, stack.count))
  const boxMetadata = stack.nodule_slices.find((slice) => slice.nodule_id === selected)
    ?? stack.nodule_slices.find((slice) => slice.nodule_id === driver)
  const currentZ = stack.z_mm[target]
  const stopDrag = () => { drag.current = null }

  return (
    <div
      ref={well}
      tabIndex={0}
      role="region"
      aria-label="Axial CT slice carousel. Use arrow keys to navigate slices."
      className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl bg-black/35 outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-white/60"
      style={{ touchAction: "pan-y" }}
      onKeyDown={(event) => {
        if ((event.target as HTMLElement).closest("[data-carousel-control]")) return
        const next = event.key === "ArrowRight" || event.key === "ArrowDown" ? targetRef.current + 1
          : event.key === "ArrowLeft" || event.key === "ArrowUp" ? targetRef.current - 1
          : event.key === "Home" ? 0 : event.key === "End" ? stack.count - 1 : null
        if (next != null) { event.preventDefault(); navigate(next) }
      }}
      onPointerDown={(event) => {
        if (event.button !== 0 || (event.target as HTMLElement).closest("[data-carousel-control]")) return
        well.current?.focus({ preventScroll: true })
        suppressClick.current = false
        drag.current = { id: event.pointerId, x: event.clientX, index: targetRef.current, moved: false }
      }}
      onPointerMove={(event) => {
        const active = drag.current
        if (!active || active.id !== event.pointerId) return
        const delta = active.x - event.clientX
        if (Math.abs(delta) > 6 && !active.moved) {
          active.moved = true
          event.currentTarget.setPointerCapture(event.pointerId)
        }
        if (active.moved) {
          suppressClick.current = true
          navigate(active.index + delta / 65)
        }
      }}
      onPointerUp={(event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
        stopDrag()
      }}
      onDragStart={(event) => event.preventDefault()}
      onPointerCancel={stopDrag}
      onLostPointerCapture={stopDrag}
      onClickCapture={(event) => {
        if (!suppressClick.current) return
        event.preventDefault()
        event.stopPropagation()
        suppressClick.current = false
      }}
    >
      <div className="relative min-h-0 flex-1 overflow-hidden" style={{ perspective: "1100px", containerType: "size" }}>
        {visible.map((index) => {
          const outgoing = jumping && index === clamp(from, stack.count)
          const offset = outgoing ? 0 : jumping ? index - target + Math.sign(target - from) * (1 - blend) * 0.3 : index - position
          const distance = Math.abs(offset)
          const box = boxMetadata && Math.abs(index - boxMetadata.index) <= boxMetadata.half_range ? boxMetadata.box_px : null
          return (
            <button
              key={index}
              data-slice-index={index}
              type="button"
              tabIndex={index === target ? 0 : -1}
              aria-label={`Go to slice ${index + 1}`}
              aria-current={index === target ? "true" : undefined}
              onClick={() => navigate(index)}
              className="absolute left-1/2 top-1/2 overflow-hidden rounded-lg border border-white/15 bg-black shadow-2xl outline-none focus-visible:ring-2 focus-visible:ring-white/80"
              style={{
                width: `min(58cqw, calc(88cqh * ${stack.size[0] / stack.size[1]}))`,
                transform: `translate(-50%, -50%) translateX(${offset * 67}%) translateZ(${-distance * 115}px) rotateY(${Math.max(-48, Math.min(48, -offset * 33))}deg) scale(${1 - Math.min(distance, 3) * 0.09})`,
                zIndex: outgoing ? 20 : 10 - Math.round(distance * 2),
                opacity: (outgoing ? 1 - blend : jumping ? blend : 1) * Math.max(0, Math.min(1, 3 - distance)),
                filter: `brightness(${1 - Math.min(distance, 3) * 0.18})`,
                willChange: position !== target ? "transform, opacity" : undefined,
              }}
            >
              <SliceImage src={sliceUrl(stack, index)} alt={`Axial CT slice ${index + 1}`} color={color} size={stack.size} box={box} className="block w-full select-none" />
            </button>
          )
        })}
        <div className="pointer-events-none absolute inset-x-0 top-3 flex justify-between px-4 text-[9px] uppercase tracking-[0.2em] text-white/45"><span>Axial</span><span>Scroll · drag · arrow keys</span></div>
      </div>
      <div data-carousel-control className="relative z-20 shrink-0 space-y-2 px-4 pb-3 pt-2" onPointerDown={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-between font-mono text-[11px] text-white/75">
          <span>Slice <span className="text-white">{target + 1}</span> / {stack.count}</span>
          <span>z {currentZ != null && Number.isFinite(currentZ) ? currentZ.toFixed(1) : "—"} mm</span>
        </div>
        <div className="relative mx-10 h-6" aria-label="Nodule-containing slice markers">
          <div className="absolute inset-x-0 top-3 h-px bg-white/20" />
          {markers.map((marker) => (
            <button
              key={`${marker.id}:${marker.index}`}
              type="button"
              title={marker.title}
              aria-label={`${marker.id}, ${marker.title}, slice ${marker.index + 1}`}
              onClick={() => {
                markerSelection.current = marker.id !== selected ? marker.id : null
                navigate(marker.index)
                onSelect(marker.id)
              }}
              className="absolute h-3 min-w-[7px] -translate-x-1/2 rounded-sm border border-black/60 outline-none hover:scale-150 focus-visible:z-30 focus-visible:ring-2 focus-visible:ring-white"
              style={{ left: `${stack.count > 1 ? marker.index / (stack.count - 1) * 100 : 50}%`, top: marker.row * 5 + 2, backgroundColor: marker.id === driver ? "var(--warn)" : marker.id === selected ? "#e2e8f0" : "#94a3b8", zIndex: marker.id === selected ? 3 : marker.id === driver ? 2 : 1 }}
            />
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button type="button" aria-label="Previous slice" disabled={target === 0} onClick={() => navigate(targetRef.current - 1)} className="grid h-7 w-7 shrink-0 place-items-center rounded border border-white/15 text-lg text-white/80 hover:bg-white/10 disabled:opacity-25">‹</button>
          <input type="range" min={0} max={Math.max(0, stack.count - 1)} step={1} value={target} onChange={(event) => navigate(Number(event.target.value))} onPointerDown={(event) => event.stopPropagation()} aria-label={`Slice ${target + 1} of ${stack.count}`} className="h-5 min-w-0 flex-1 cursor-pointer accent-[var(--warn)]" />
          <button type="button" aria-label="Next slice" disabled={target >= stack.count - 1} onClick={() => navigate(targetRef.current + 1)} className="grid h-7 w-7 shrink-0 place-items-center rounded border border-white/15 text-lg text-white/80 hover:bg-white/10 disabled:opacity-25">›</button>
        </div>
      </div>
    </div>
  )
}
