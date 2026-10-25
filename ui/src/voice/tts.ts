import { API_BASE } from "@/api/config"

/** /api/tts streams raw s16le PCM (audio/L16; rate=24000; channels=1); play it with Web Audio. */
const RATE = 24000

class TtsPlayer {
  private ctx: AudioContext | null = null
  private src: AudioBufferSourceNode | null = null
  private pending: AbortController | null = null
  private muted = false
  playing = false
  onPlaying: ((playing: boolean) => void) | null = null

  setMuted(muted: boolean) {
    this.muted = muted
    if (muted) this.stop()
  }

  /** Cancel pending synthesis and stop playback (push-to-talk, a new question, Escape or unmount). */
  stop() {
    this.pending?.abort()
    this.pending = null
    if (this.src) {
      try {
        this.src.stop()
      } catch {
        /* already ended */
      }
      this.src = null
    }
    if (this.playing) {
      this.playing = false
      this.onPlaying?.(false)
    }
  }

  /** Speak `text` (the worker normalises it: markdown, Lung-RADS, ≤ 2 sentences).
 *  Any failure — 502, network, empty clip — means text only; never a toast. */
  async speak(text: string): Promise<void> {
    this.stop()
    const t0 = performance.now()
    if (this.muted || !text.trim()) return
    const request = new AbortController()
    this.pending = request
    try {
      const res = await fetch(`${API_BASE}/api/tts`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
        signal: request.signal,
      })
      if (!res.ok) return // The text answer already on screen remains available.
      const raw = await res.arrayBuffer()
      if (request.signal.aborted || this.pending !== request || this.muted || raw.byteLength < 2) return
      if (!this.ctx) this.ctx = new AudioContext({ sampleRate: RATE })
      const ctx = this.ctx
      if (ctx.state === "suspended") await ctx.resume()
      // Stop/mute can happen while the response body or audio context is still pending.
      if (request.signal.aborted || this.pending !== request || this.muted) return
      const pcm = new Int16Array(raw)
      const buf = ctx.createBuffer(1, pcm.length, RATE)
      const f = buf.getChannelData(0)
      for (let i = 0; i < pcm.length; i++) f[i] = pcm[i] / 32768
      const src = ctx.createBufferSource()
      src.buffer = buf
      src.connect(ctx.destination)
      src.onended = () => {
        if (this.src === src) {
          this.src = null
          this.playing = false
          this.onPlaying?.(false)
        }
      }
      this.src = src
      this.playing = true
      this.onPlaying?.(true)
      src.start()
      console.info(
        `[voice] tts first audio +${Math.round(performance.now() - t0)}ms, clip ${(pcm.length / RATE).toFixed(1)}s`,
      )
    } catch {
      // Cancellation, unavailable synthesis or audio output leaves the answer text-only.
    } finally {
      if (this.pending === request) this.pending = null
    }
  }
}

/** One player for the app (24 kHz playback context, reused across answers). */
export const tts = new TtsPlayer()
