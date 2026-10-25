import { useEffect, useRef, useState } from "react"
import { ask, api } from "@/api/client"
import { viewerBus } from "@/api/viewer-bus"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { ArrowUp, Square, Mic, Sparkles, MicOff } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { usePref } from "@/lib/prefs"

interface Turn {
  id: number
  q: string
  text: string
  tools: string[]
  status: "streaming" | "done" | "error" | "stopped"
  error?: string
}

const PHRASES = ["Show me the nodule", "Compare it to last year", "Why did you flag this?", "Reset the view"]

/** Canonical phrase → viewer command. The demo runs these deterministically before the agent answers. */
const PHRASE_COMMANDS: { match: RegExp; command: "show_nodule" | "compare_prior" | "reset_view"; nodule: boolean }[] = [
  { match: /show .*nodule/i, command: "show_nodule", nodule: true },
  { match: /compare/i, command: "compare_prior", nodule: true },
  { match: /why .*flag/i, command: "show_nodule", nodule: true },
  { match: /reset/i, command: "reset_view", nodule: false },
]

export function ChatRail({ uid }: { uid: string }) {
  const [width, setWidth] = usePref("sparkmd-chat-w", 300)
  const [resizing, setResizing] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState("")
  const ctl = useRef<AbortController | null>(null)
  const seq = useRef(0)
  const [busy, setBusy] = useState(false)
  const [recording, setRecording] = useState(false)
  const scroller = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const [unseen, setUnseen] = useState(0)
  const prevLen = useRef(0)

  useEffect(() => {
    document.documentElement.style.setProperty("--chat-w", `${width}px`)
  }, [width])

  const totalLen = turns.reduce((a, t) => a + t.text.length + 1, 0)
  useEffect(() => {
    const el = scroller.current
    if (!el) return
    if (stick.current) el.scrollTop = el.scrollHeight
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalLen, turns.length])

  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const added = Math.max(0, totalLen - prevLen.current)
    prevLen.current = totalLen
    if (stick.current) el.scrollTop = el.scrollHeight
    else setUnseen((n) => (added ? n + added : n))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalLen])

  const onScroll = () => {
    const el = scroller.current
    if (!el) return
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    if (stick.current) setUnseen(0)
  }

  /** Deterministic viewer action for a canonical phrase: the camera moves before the agent replies. */
  const fireViewer = async (text: string) => {
    const hit = PHRASE_COMMANDS.find((p) => p.match.test(text))
    if (!hit) return
    try {
      await api.viewerCommand(hit.command, uid)
    } catch {
      // Offline/mock: fall back to the local bus so the view still moves during the demo.
      viewerBus.emit({ command: hit.command, study_uid: uid })
    }
  }

  const submit = async (text: string) => {
    const question = text.trim()
    if (!question || busy) return
    ctl.current?.abort()
    const c = new AbortController()
    ctl.current = c
    const id = ++seq.current
    setBusy(true)
    setQ("")
    stick.current = true
    setTurns((t) => [...t, { id, q: question, text: "", tools: [], status: "streaming" }])
    const upd = (f: (t: Turn) => Turn) => setTurns((all) => all.map((t) => (t.id === id ? f(t) : t)))
    void fireViewer(question)
    try {
      for await (const ev of ask(uid, question, c.signal)) {
        if (ev.event === "delta") upd((t) => ({ ...t, text: t.text + (ev.data.text ?? "") }))
        else if (ev.event === "tool") upd((t) => ({ ...t, tools: [...t.tools, String(ev.data.tool ?? "tool")] }))
        else if (ev.event === "error") upd((t) => ({ ...t, status: "error", error: ev.data.message ?? "error" }))
      }
      upd((t) => (t.status === "streaming" ? { ...t, status: "done" } : t))
    } catch (e) {
      upd((t) => (c.signal.aborted ? { ...t, status: "stopped" } : { ...t, status: "error", error: String((e as Error).message) }))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && busy) ctl.current?.abort()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [busy])

  useEffect(() => {
    if (!resizing) return
    const railLeft = () => window.innerWidth - width - 380 - 12
    const start = railLeft()
    const move = (e: PointerEvent) => setWidth(Math.min(560, Math.max(240, e.clientX - start + width)))
    const up = () => setResizing(false)
    window.addEventListener("pointermove", move)
    window.addEventListener("pointerup", up, { once: true })
    return () => {
      window.removeEventListener("pointermove", move)
      window.removeEventListener("pointerup", up)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resizing])

  return (
    <div className="relative flex min-h-0 flex-col" style={{ width }}>
      <div
        data-grip="1"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the chat rail"
        onPointerDown={(e) => {
          e.preventDefault()
          setResizing(true)
        }}
        onDoubleClick={() => setWidth(300)}
        className={cn("absolute -right-1 top-0 z-10 h-full w-2 cursor-col-resize hover:bg-border/70", resizing && "bg-border")}
      />
      <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 space-y-2 overflow-y-auto px-2 pb-2">
        {!turns.length && (
          <div className="px-1 pt-1 text-[12px] text-muted-foreground">
            <div className="mb-1 flex items-center gap-1.5 text-[11px] font-medium">
              <Sparkles className="size-3.5 text-run" /> Talk to the scan
            </div>
            Ask about the findings, or use a phrase. Numbers in answers come from the worker&apos;s findings payload.
          </div>
        )}
        {turns.map((t) => (
          <div key={t.id} className="space-y-1.5">
            <div className="ml-3 rounded-lg rounded-tr-sm bg-muted px-2.5 py-1.5 text-[12.5px]">{t.q}</div>
            <div className="text-[13px] leading-snug">
              {t.tools.length > 0 && (
                <div className="mb-1 flex flex-wrap gap-1">
                  {t.tools.map((tool, i) => (
                    <span key={i} className="rounded bg-muted/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                      {tool}
                    </span>
                  ))}
                </div>
              )}
              {t.text ? (
                <div className="report-md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{t.text}</ReactMarkdown>
                  {t.status === "streaming" && <span className="ml-0.5 inline-block animate-pulse text-run">▍</span>}
                </div>
              ) : t.status === "streaming" ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                  Thinking<span className="animate-pulse">…</span>
                  <span className="text-run">▍</span>
                </span>
              ) : null}
              {t.status === "stopped" && <div className="mt-1 text-[10px] text-muted-foreground">Stopped</div>}
              {t.status === "error" && <div className="mt-1 text-[11px] text-alert">{t.error}</div>}
            </div>
          </div>
        ))}
        {unseen > 0 && (
          <button
            onClick={() => {
              stick.current = true
              setUnseen(0)
              if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight
            }}
            className="sticky bottom-1 mx-auto block rounded-full bg-secondary px-2 py-1 text-[10px] shadow"
          >
            new content ↓
          </button>
        )}
      </div>

      <div className="border-t border-transparent px-2 pb-2">
        <div className="mb-1 flex flex-wrap gap-1">
          {PHRASES.map((p) => (
            <button
              key={p}
              disabled={busy}
              onClick={() => void submit(p)}
              className="rounded-full border px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
            >
              {p}
            </button>
          ))}
        </div>
        <div className="rounded-xl border bg-card shadow-sm">
          <Textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                void submit(q)
              }
            }}
            placeholder="Ask the scan…"
            rows={1}
            className="max-h-[132px] min-h-[52px] resize-none border-0 bg-transparent px-2.5 py-2 text-[13px] shadow-none focus-visible:ring-0"
          />
          <div className="flex items-center gap-1 px-2 pb-1.5">
            <Tooltip>
              <TooltipTrigger asChild>
                <span tabIndex={0}>
                  <Button
                    size="icon"
                    variant={recording ? "secondary" : "ghost"}
                    className="size-6"
                    aria-label={recording ? "Listening (push-to-talk via the worker)" : "Push to talk"}
                    aria-pressed={recording}
                    onClick={() => {
                      setRecording((r) => !r)
                      if (!recording) void api.health().catch(() => undefined)
                    }}
                  >
                    {recording ? <Mic className="size-3.5" /> : <MicOff className="size-3.5" />}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>{recording ? "Voice capture arrives with 09 (whisper.cpp on the box)" : "Push-to-talk is wired to /api/asr in 09; mic capture unverified"}</TooltipContent>
            </Tooltip>
            <span className="text-[9px] text-muted-foreground/60">Synthetic voice (Qwen3-TTS) · on device</span>
            <div className="ml-auto flex items-center gap-1">
              {busy ? (
                <Button size="icon" variant="secondary" className="size-7 rounded-full" aria-label="Stop" onClick={() => ctl.current?.abort()}>
                  <Square className="size-3" />
                </Button>
              ) : (
                <Button size="icon" className="size-7 rounded-full" aria-label="Send" disabled={!q.trim()} onClick={() => void submit(q)}>
                  <ArrowUp className="size-3.5" />
                </Button>
              )}
            </div>
          </div>
        </div>
        <div className="mt-1 px-0.5 text-[9px] text-muted-foreground/50">Answers may quote confirmed findings only · research demo</div>
      </div>
    </div>
  )
}
