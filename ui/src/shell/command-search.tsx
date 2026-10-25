import { useEffect, useMemo, useRef, useState } from "react"
import { Search, Loader2, WifiOff, CornerDownLeft, ArrowUp, ArrowDown } from "lucide-react"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { useWorklist } from "@/api/hooks"
import { STATUS_LABEL, lungRadsClass } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { WorklistRow } from "@/api/types"

/** Local-only search over the cached worklist. Patient ID, UID, timepoint, category, review state. */
export function CommandSearch({ open, onOpenChange, onPick }: { open: boolean; onOpenChange: (b: boolean) => void; onPick: (uid: string) => void }) {
  const { data, isLoading, isError } = useWorklist()
  const [q, setQ] = useState("")
  const [sel, setSel] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) {
      setQ("")
      setSel(0)
      setTimeout(() => inputRef.current?.focus(), 10)
    }
  }, [open])

  const matches: WorklistRow[] = useMemo(() => {
    if (!data) return []
    const s = q.trim().toLowerCase()
    const base = s
      ? data.filter((r) =>
          [r.patient_id, r.study_uid, r.timepoint, r.lung_rads ?? "", STATUS_LABEL[r.status] ?? r.status, r.priority].some((f) => f.toLowerCase().includes(s)),
        )
      : data
    return base.slice(0, 12)
  }, [data, q])

  useEffect(() => setSel(0), [q])

  const pick = (r: WorklistRow) => {
    onOpenChange(false)
    onPick(r.study_uid)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[18%] translate-y-0 gap-0 p-0 sm:max-w-xl" showCloseButton={false} aria-describedby={undefined}>
        <DialogTitle className="sr-only">Search studies</DialogTitle>
        <div className="flex items-center gap-2 border-b px-3 py-2.5">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <Input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Patient ID, study UID, timepoint, Lung-RADS, review state…"
            className="h-7 border-0 bg-transparent px-0 text-sm shadow-none focus-visible:ring-0"
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault()
                setSel((s) => Math.min(s + 1, matches.length - 1))
              } else if (e.key === "ArrowUp") {
                e.preventDefault()
                setSel((s) => Math.max(s - 1, 0))
              } else if (e.key === "Enter" && matches[sel]) {
                e.preventDefault()
                pick(matches[sel])
              } else if (e.key === "Escape") {
                onOpenChange(false)
              }
            }}
          />
          <kbd className="rounded border px-1 text-[10px] text-muted-foreground">esc</kbd>
        </div>
        <div ref={listRef} className="max-h-[340px] overflow-y-auto p-1.5">
          {isLoading && (
            <div className="flex items-center gap-2 px-2 py-6 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading the worklist…</div>
          )}
          {isError && (
            <div className="flex items-center gap-2 px-2 py-6 text-sm text-muted-foreground"><WifiOff className="size-4" /> Worklist unavailable — is the worker running?</div>
          )}
          {!isLoading && !isError && !matches.length && (
            <div className="px-2 py-6 text-center text-sm text-muted-foreground">{data?.length ? `No studies match “${q}”` : "No studies yet"}</div>
          )}
          {matches.map((r, i) => (
            <button
              key={r.study_uid}
              onMouseEnter={() => setSel(i)}
              onClick={() => pick(r)}
              className={cn("flex w-full items-center gap-3 rounded-md px-2 py-2 text-left text-sm", i === sel ? "bg-muted" : "hover:bg-muted/60")}
            >
              <span className="font-mono text-[13px] tabular-nums">{r.patient_id}</span>
              <span className="text-xs text-muted-foreground">{r.timepoint}</span>
              <span className="ml-auto flex items-center gap-2 text-xs">
                {r.lung_rads ? <span className={cn("rounded px-1.5 py-0.5 font-mono tabular-nums", lungRadsClass(r.lung_rads))}>{r.lung_rads}</span> : <span className="text-muted-foreground">—</span>}
                <span className="text-muted-foreground">{STATUS_LABEL[r.status] ?? r.status}</span>
              </span>
              {i === sel && <CornerDownLeft className="size-3.5 text-muted-foreground" />}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 border-t px-3 py-1.5 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1"><ArrowUp className="size-3" /><ArrowDown className="size-3" /> navigate</span>
          <span className="flex items-center gap-1"><CornerDownLeft className="size-3" /> open</span>
          <span className="ml-auto">Local worklist only · no remote search</span>
        </div>
      </DialogContent>
    </Dialog>
  )
}
