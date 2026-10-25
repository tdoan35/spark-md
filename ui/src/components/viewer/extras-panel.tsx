import { useEffect, useState } from "react"
import type { Findings } from "@/api/types"
import { X, Wind, Bone, Heart } from "lucide-react"
import { hu } from "@/lib/format"
import { cn } from "@/lib/utils"

/** 4 extras rows slide in staggered on `show_extras` (agent-driven; numbers from the worker's extras). */
export function ExtrasPanel({ findings, uid, onClose }: { findings: Findings | undefined; uid: string; onClose: () => void }) {
  const [n, setN] = useState(0)
  useEffect(() => {
    setN(0)
    let i = 0
    const t = setInterval(() => setN(++i), 350)
    return () => clearInterval(t)
  }, [uid])
  const e = findings?.extras
  const rows = [
    { k: "nodules", icon: Wind, label: "Nodules", value: `${findings?.nodules.length ?? 0} tracked`, sub: "lung nodule detection" },
    { k: "emph", icon: Wind, label: "Emphysema", value: `${e?.emphysema_laa950_pct?.toFixed(1) ?? "—"} %`, sub: "LAA-950 volume" },
    { k: "bone", icon: Bone, label: `Bone · ${e?.vertebra?.label ?? "—"}`, value: hu(e?.vertebra?.mean_hu), sub: e?.vertebra?.flag ?? "vertebral HU" },
    { k: "cac", icon: Heart, label: "Coronary calcium", value: e?.cac?.agatston != null ? `${e.cac.agatston}` : "—", sub: "experimental · Agatston" },
  ]
  return (
    <div className="absolute bottom-3 right-3 w-56 rounded-lg border border-white/10 bg-black/70 p-2">
      <div className="mb-1 flex items-center justify-between px-1 text-[10px] text-white/60">
        <span>Screenings · agent-triggered</span>
        <button onClick={onClose} className="rounded p-0.5 hover:bg-white/10" aria-label="Hide extras">
          <X className="size-3" />
        </button>
      </div>
      <div className="space-y-1">
        {rows.map((r, i) => (
          <div key={r.k} className={cn("flex items-center gap-2 rounded bg-white/5 px-2 py-1.5 transition-all duration-300", i < n ? "translate-y-0 opacity-100" : "translate-y-1 opacity-0")}>
            <r.icon className="size-3.5 text-white/50" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[11px] text-white/80">{r.label}</div>
              <div className="truncate text-[9px] text-white/40">{r.sub}</div>
            </div>
            <span className="font-mono text-[12px] tabular-nums text-white/90">{r.value}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 px-1 text-[9px] text-white/30">Placeholder numbers · research demo</div>
    </div>
  )
}
