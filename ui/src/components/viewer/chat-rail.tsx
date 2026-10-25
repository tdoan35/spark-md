import { useEffect, useRef, useState } from "react"
import { ask } from "@/api/client"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { ArrowUp, Square, Mic, Sparkles, Loader2, Volume2, VolumeX } from "lucide-react"
import { usePref } from "@/lib/prefs"
import { PushToTalk } from "@/lib/voice"
import { postAsr } from "@/voice/asr"
import { tts } from "@/voice/tts"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { toast } from "sonner"

interface Turn {
  id: number
  q: string
  text: string
  tools: string[]
  status: "streaming" | "done" | "error" | "stopped"
  error?: string
}

const PHRASES = ["Show me the nodule", "Compare it to last year", "Why did you flag this?", "Reset the view"]

export function ChatRail({ uid }: { uid: string }) {
  const [width, setWidth] = usePref("sparkmd-chat-w", 300)
  const [resizing, setResizing] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState("")
  const ctl = useRef<AbortController | null>(null)
  const seq = useRef(0)
  const [busy, setBusy] = useState(false)
  const [pttState, setPttState] = useState<"idle" | "recording" | "transcribing">("idle")
  const [level, setLevel] = useState(0)
  const [voiceOn, setVoiceOn] = usePref("sparkmd-voice", true)
  const pttRef = useRef<PushToTalk | null>(null)
  const maxHold = useRef<number | undefined>(undefined)
  const pttHandlers = useRef<{ start: () => void; finish: () => void }>({ start: () => {}, finish: () => {} })
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

  const submit = async (text: string, display?: string) => {
    const question = text.trim()
    if (!question || busy) return
    ctl.current?.abort()
    tts.stop()
    const c = new AbortController()
    ctl.current = c
    const id = ++seq.current
    setBusy(true)
    setQ("")
    stick.current = true
    setTurns((t) => [...t, { id, q: display ?? question, text: "", tools: [], status: "streaming" }])
    const upd = (f: (t: Turn) => Turn) => setTurns((all) => all.map((t) => (t.id === id ? f(t) : t)))
    // /api/ask owns deterministic viewer actions for both typed and spoken requests (09).
    let acc = ""
    let completed = false
    try {
      for await (const ev of ask(uid, question, c.signal)) {
        if (ev.event === "delta") {
          acc += ev.data.text ?? ""
          upd((t) => ({ ...t, text: t.text + (ev.data.text ?? "") }))
        } else if (ev.event === "tool") upd((t) => ({ ...t, tools: [...t.tools, String(ev.data.tool ?? "tool")] }))
        else if (ev.event === "error") throw new Error(ev.data.message ?? "Answer failed")
        else if (ev.event === "done") {
          if (ev.data.ok !== true) throw new Error("Answer did not complete successfully.")
          completed = true
        }
      }
      if (!completed) throw new Error("Answer stream ended before completion.")
      upd((t) => (t.status === "streaming" ? { ...t, status: "done" } : t))
      // 09: speak the answer only after `done` and only when not muted; failures stay silent.
      if (!c.signal.aborted && voiceOn && acc.trim()) void tts.speak(acc)
    } catch (e) {
      upd((t) => (c.signal.aborted ? { ...t, status: "stopped" } : { ...t, status: "error", error: String((e as Error).message) }))
    } finally {
      setBusy(false)
    }
  }

  const finishPtt = async () => {
    const p = pttRef.current
    if (!p) return
    pttRef.current = null
    window.clearTimeout(maxHold.current)
    setLevel(0)
    const clip = await p.stop()
    if (!clip) {
      setPttState("idle")
      return
    }
    setPttState("transcribing")
    try {
      const r = await postAsr(clip.wav)
      if (r.command && r.phrase) submit(r.phrase, r.text.trim() || r.phrase)
      else
        toast.info("Didn't catch that", {
          description: r.text?.trim() ? `Heard: “${r.text.trim()}”` : "No speech detected",
        })
    } catch (e) {
      toast.error("Voice recognition unavailable", { description: String((e as Error)?.message ?? e) })
    } finally {
      setPttState("idle")
    }
  }

  const startPtt = () => {
    if (pttRef.current || pttState === "transcribing") return
    tts.stop() // 09: stop playback before capture so the speaker cannot feed the mic
    setPttState("recording")
    const p = new PushToTalk()
    pttRef.current = p
    p.start(setLevel).catch((e) => {
      if (pttRef.current === p) pttRef.current = null
      setPttState("idle")
      toast.error("Microphone unavailable", { description: String((e as Error)?.message ?? e) })
    })
    maxHold.current = window.setTimeout(() => void finishPtt(), 6000) // 09: auto-stop at 6 s
  }
  pttHandlers.current = { start: startPtt, finish: () => void finishPtt() }

  useEffect(() => {
    const inField = (t: EventTarget | null) => t instanceof Element && !!t.closest("input, textarea, [contenteditable], button, [role=button]")
    const down = (e: KeyboardEvent) => {
      if (e.code === "Space" && !e.repeat && !e.altKey && !e.ctrlKey && !e.metaKey && !inField(e.target)) {
        e.preventDefault()
        pttHandlers.current.start()
      }
      if (e.key === "Escape") {
        ctl.current?.abort()
        tts.stop()
      }
    }
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") pttHandlers.current.finish()
    }
    const blur = () => {
      if (pttRef.current) pttHandlers.current.finish()
    }
    window.addEventListener("keydown", down)
    window.addEventListener("keyup", up)
    window.addEventListener("blur", blur)
    return () => {
      window.removeEventListener("keydown", down)
      window.removeEventListener("keyup", up)
      window.removeEventListener("blur", blur)
      ctl.current?.abort()
      pttRef.current?.abort()
      tts.stop()
    }
    // Busy transitions must not cancel the speech requested by a completed answer.
  }, [])

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
                    variant={pttState !== "idle" ? "secondary" : "ghost"}
                    className="size-6"
                    aria-label={pttState === "recording" ? "Listening — release to transcribe" : "Push to talk (hold, or hold Space)"}
                    aria-pressed={pttState !== "idle"}
                    disabled={pttState === "transcribing"}
                    onPointerDown={(e) => {
                      e.preventDefault()
                      startPtt()
                    }}
                    onPointerUp={() => void finishPtt()}
                    onPointerLeave={() => void finishPtt()}
                  >
                    {pttState === "transcribing" ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Mic className={cn("size-3.5", pttState === "recording" && "animate-pulse text-primary")} />
                    )}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>Hold to talk — or hold Space; whisper.cpp runs on the box</TooltipContent>
            </Tooltip>
            {pttState === "recording" && (
              <span className="h-1 w-8 overflow-hidden rounded-full bg-muted" aria-hidden>
                <span className="block h-full bg-primary transition-[width] duration-75" style={{ width: `${Math.round(level * 100)}%` }} />
              </span>
            )}
            {pttState === "transcribing" && <span className="text-[9px] text-muted-foreground/70">Transcribing…</span>}
            <span className="text-[9px] text-muted-foreground/60">Synthetic voice (Qwen3-TTS) · on device</span>
            <Button
              size="icon"
              variant="ghost"
              className="size-5"
              aria-label={voiceOn ? "Mute spoken answers" : "Unmute spoken answers"}
              aria-pressed={voiceOn}
              onClick={() => {
                tts.setMuted(voiceOn) // muting also cancels pending synthesis
                setVoiceOn(!voiceOn)
              }}
            >
              {voiceOn ? <Volume2 className="size-3" /> : <VolumeX className="size-3" />}
            </Button>
            <div className="ml-auto flex items-center gap-1">
              {busy ? (
                <Button size="icon" variant="secondary" className="size-7 rounded-full" aria-label="Stop" onClick={() => { ctl.current?.abort(); tts.stop() }}>
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
