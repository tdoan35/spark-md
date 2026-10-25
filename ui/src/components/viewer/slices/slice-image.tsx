import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { mm } from "@/lib/format"

/** Format worker diameters only; never present an unconfirmed proposal as a measurement. */
export function sliceSizeLabel(mean: number | null | undefined, proposed?: number | null): string {
  if (mean != null) return mm(mean)
  if (proposed != null) return `Proposed ${mm(proposed)}`
  return "Size unavailable"
}

// Matplotlib's piecewise-linear jet channels, sampled once at all 256 grayscale values.
const CHANNELS = [
  [[0, 0], [0.35, 0], [0.66, 1], [0.89, 1], [1, 0.5]],
  [[0, 0], [0.125, 0], [0.375, 1], [0.64, 1], [0.91, 0], [1, 0]],
  [[0, 0.5], [0.11, 1], [0.34, 1], [0.65, 0], [1, 0]],
] as const
const JET = new Uint8ClampedArray(256 * 3)
for (let g = 0; g < 256; g++) {
  const x = g / 255
  for (let c = 0; c < 3; c++) {
    const stops = CHANNELS[c]
    for (let s = 1; s < stops.length; s++) {
      const [left, a] = stops[s - 1]
      const [right, b] = stops[s]
      if (x <= right) {
        JET[g * 3 + c] = Math.round((a + (b - a) * (x - left) / (right - left)) * 255)
        break
      }
    }
  }
}

interface DecodedSlice {
  src: string
  image: HTMLImageElement
  w: number
  h: number
  jet: HTMLCanvasElement | null
}
// At most 32 decoded images + colour canvases, not all 158 stack slices. Shared by Compare/carousel.
const cache = new Map<string, Promise<DecodedSlice>>()
function loadSlice(src: string): Promise<DecodedSlice> {
  const found = cache.get(src)
  if (found) {
    cache.delete(src)
    cache.set(src, found)
    return found
  }
  const pending = new Promise<DecodedSlice>((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve({ src, image, w: image.naturalWidth, h: image.naturalHeight, jet: null })
    image.onerror = () => reject(new Error("CT slice unavailable"))
    image.src = src
  })
  cache.set(src, pending)
  if (cache.size > 32) cache.delete(cache.keys().next().value!)
  return pending
}
function jetCanvas(slice: DecodedSlice): HTMLCanvasElement {
  if (slice.jet) return slice.jet
  const canvas = document.createElement("canvas")
  canvas.width = slice.w
  canvas.height = slice.h
  const ctx = canvas.getContext("2d", { willReadFrequently: true })
  if (!ctx) throw new Error("CT colour canvas unavailable")
  ctx.drawImage(slice.image, 0, 0)
  const pixels = ctx.getImageData(0, 0, slice.w, slice.h)
  const rgba = pixels.data
  for (let i = 0; i < rgba.length; i += 4) {
    const j = rgba[i] * 3 // source PNG/JPEG is the worker's grayscale lung window
    rgba[i] = JET[j]
    rgba[i + 1] = JET[j + 1]
    rgba[i + 2] = JET[j + 2]
  }
  ctx.putImageData(pixels, 0, 0)
  slice.jet = canvas
  return canvas
}

/** Decode and colour-cache visible neighbours before navigation reaches them. */
export function preloadSlice(src: string): void {
  void loadSlice(src).then(jetCanvas).catch(() => { /* visible slice reports its own load error */ })
}

export function SliceImage({ src, alt, color, box, size, sizeLabel, className, fit = false }: {
  src: string
  alt: string
  color: boolean
  box?: [number, number, number, number] | null
  size?: [number, number]
  sizeLabel?: string
  className?: string
  fit?: boolean
}) {
  const [decoded, setDecoded] = useState<DecodedSlice | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const slice = decoded?.src === src ? decoded : null
  useEffect(() => {
    let live = true
    void loadSlice(src).then((image) => { if (live) setDecoded(image) }).catch(() => { if (live) setFailed(src) })
    return () => { live = false }
  }, [src])
  useLayoutEffect(() => {
    if (!slice || !canvas.current) return
    try {
      const ctx = canvas.current.getContext("2d")
      if (!ctx) throw new Error("CT canvas unavailable")
      ctx.drawImage(color ? jetCanvas(slice) : slice.image, 0, 0)
    } catch {
      setFailed(src)
    }
  }, [slice, color, src])
  const w = slice?.w ?? size?.[0] ?? 1
  const h = slice?.h ?? size?.[1] ?? 1
  const boxW = size?.[0] ?? w
  const boxH = size?.[1] ?? h
  const pad = Math.max(3, boxW / 128)
  return (
    <div className={cn(fit ? "grid h-full w-full place-items-center" : "relative w-full", className)} style={fit ? { containerType: "size" } : undefined}>
      <div className="relative" style={{ width: fit ? `min(100cqw, calc(100cqh * ${w / h}))` : "100%" }} data-slice-src={src}>
        <canvas ref={canvas} width={w} height={h} role="img" aria-label={alt} data-color={color ? "jet" : "gray"} data-loaded={!!slice && failed !== src} className="block w-full" style={{ imageRendering: "pixelated" }} />
        {slice && box && failed !== src && (
          <svg viewBox={`0 0 ${boxW} ${boxH}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
            <rect x={box[0] - pad} y={box[1] - pad} width={box[2] + pad * 2} height={box[3] + pad * 2} fill="none" stroke="black" strokeWidth={5} vectorEffect="non-scaling-stroke" />
            <rect x={box[0] - pad} y={box[1] - pad} width={box[2] + pad * 2} height={box[3] + pad * 2} fill="none" stroke="#39ff14" strokeWidth={2} vectorEffect="non-scaling-stroke" />
          </svg>
        )}
        {slice && box && sizeLabel && failed !== src && (
          <span
            data-nodule-size-label
            className="pointer-events-none absolute z-10 whitespace-nowrap rounded border px-1.5 py-0.5 font-mono text-[11px] font-semibold leading-tight shadow-sm"
            style={{
              color: "#39ff14",
              borderColor: "#39ff14",
              backgroundColor: "rgba(0,0,0,0.88)",
              ...(box[0] > boxW / 2
                ? { right: `${Math.max(1, (boxW - box[0] - box[2] - pad) / boxW * 100)}%` }
                : { left: `${Math.max(1, (box[0] - pad) / boxW * 100)}%` }),
              top: `${(box[1] - pad < boxH * 0.1 ? box[1] + box[3] + pad : box[1] - pad) / boxH * 100}%`,
              transform: box[1] - pad < boxH * 0.1 ? "translateY(4px)" : "translateY(calc(-100% - 4px))",
            }}
          >{sizeLabel}</span>
        )}
        {!slice && failed !== src && <span className="absolute inset-0 grid place-items-center text-[10px] text-white/50">Loading CT slice…</span>}
        {failed === src && <span role="status" className="absolute inset-0 grid place-items-center text-[11px] text-white/60">CT slice unavailable</span>}
      </div>
    </div>
  )
}
