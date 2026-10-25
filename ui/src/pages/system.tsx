import { useEffect, useState } from "react"
import { Server, ShieldCheck, Wifi, WifiOff } from "lucide-react"
import { useNetstats } from "@/api/hooks"
import { useApp } from "@/lib/app-context"
import { bytes } from "@/lib/format"

/** 120 s ring buffer of net_stats → hand-drawn SVG sparkline. */
export function Sparkline({ series }: { series: number[] }) {
  const max = Math.max(1, ...series)
  const pts = series.map((v, i) => `${(i / Math.max(1, series.length - 1)) * 400},${40 - (v / max) * 36}`).join(" ")
  return (
    <svg viewBox="0 0 400 44" className="h-11 w-full" preserveAspectRatio="none" aria-label="External bytes transmitted">
      <polyline points={pts} fill="none" stroke="var(--ok)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

export function SystemPage() {
  const { status } = useApp().sse
  const { data } = useNetstats()
  const [hist, setHist] = useState<number[]>([])
  useEffect(() => {
    if (!data) return
    const v = data.tx_bytes
    setHist((h) => [...(h.length ? h : [v, v, v]), v].slice(-120))
  }, [data])

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 px-6 pb-4 pt-5">
      <div>
        <h1 className="flex items-center gap-2 text-[15px] font-semibold"><Server className="size-4 text-muted-foreground" /> System</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">Air-gap monitor · bytes crossing physical interfaces since boot.</p>
      </div>

      <section className="rounded-lg border p-4">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-medium">
            <ShieldCheck className="size-3.5 text-ok" /> Network monitor
          </div>
          <span className={`flex items-center gap-1 text-[11px] ${data?.link_up ? "text-ok" : "text-muted-foreground"}`}>
            {data?.link_up ? <Wifi className="size-3" /> : <WifiOff className="size-3" />}
            {data?.link_up ? "Link up (internal)" : "No link"}
          </span>
        </div>
        <div className="flex items-baseline gap-3">
          <div className="font-mono text-4xl tabular-nums">{bytes(data?.tx_bytes ?? 0)}</div>
          <div className="text-xs text-muted-foreground">sent on external interfaces</div>
        </div>
        <div className="mt-1 font-mono text-[11px] text-muted-foreground">{bytes(data?.rx_bytes ?? 0)} received · since {data?.since ? new Date(data.since).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"}</div>
        <div className="mt-3"><Sparkline series={hist.length ? hist : [0, 0, 0]} /></div>
        <ul className="mt-2 space-y-0.5">
          {(data?.interfaces ?? []).map((i) => (
            <li key={i.name} className="flex items-center justify-between font-mono text-[11px] text-muted-foreground">
              <span>{i.name}</span>
              <span className="tabular-nums">↑ {bytes(i.tx_bytes)} ↓ {bytes(i.rx_bytes)}</span>
            </li>
          ))}
          {!data?.interfaces?.length && <li className="text-[11px] text-muted-foreground">No physical interfaces reported.</li>}
        </ul>
      </section>

      <section className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border p-3">
          <div className="text-xs font-medium">Event stream</div>
          <div className="mt-1 flex items-center gap-2 text-[12px]">
            <span className={`size-2 rounded-full ${status === "live" ? "bg-ok" : status === "connecting" ? "bg-warn" : "bg-alert"}`} />
            {status === "live" ? "Live (SSE on 127.0.0.1:8100)" : status === "connecting" ? "Connecting…" : "Reconnecting…"}
          </div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-xs font-medium">Model & stack</div>
          <ul className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
            <li>Qwen3.8-27B · on device</li>
            <li>OpenShell sandbox · human gates enforced</li>
            <li>Serving: TensorFold</li>
          </ul>
        </div>
      </section>
      <p className="mt-auto text-[11px] text-muted-foreground/70">
        Placeholder counters in mock mode. In the product, every byte here should be 0 — research demo, not for clinical use.
      </p>
    </div>
  )
}
