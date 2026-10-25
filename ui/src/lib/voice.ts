// 09 voice: hold-to-talk capture. One session at a time: start() on press, stop() on
// release (returns the encoded clip), abort() to discard. The AudioWorklet module is
// served same-origin from public/ — Electron refuses blob:-URL worklet modules.
import { toWav16k } from "@/voice/wav"

const WORKLET_SRC = "voice-capture-worklet.js" // public/, resolves against the page origin
const PROCESSOR = "sparkmd-capture"

export interface CapturedClip {
  wav: Blob
  seconds: number
}

export class PushToTalk {
  private ctx: AudioContext | null = null
  private stream: MediaStream | null = null
  private src: MediaStreamAudioSourceNode | null = null
  private node: AudioWorkletNode | null = null
  private chunks: Float32Array[] = []
  private t0 = 0
  private levelCb: ((v: number) => void) | null = null

  async start(onLevel?: (v: number) => void): Promise<void> {
    this.levelCb = onLevel ?? null
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    this.ctx = new AudioContext()
    await this.ctx.audioWorklet.addModule(WORKLET_SRC)
    this.src = this.ctx.createMediaStreamSource(this.stream)
    this.node = new AudioWorkletNode(this.ctx, PROCESSOR)
    this.node.port.onmessage = (e: MessageEvent<Float32Array>) => {
      const f = e.data
      this.chunks.push(new Float32Array(f))
      if (this.levelCb) {
        let s = 0
        for (let i = 0; i < f.length; i++) s += f[i] * f[i]
        this.levelCb(Math.min(1, Math.sqrt(s / f.length) * 4))
      }
    }
    this.src.connect(this.node)
    this.t0 = performance.now()
  }

  get active() {
    return !!this.ctx
  }

  get elapsedMs() {
    return this.t0 ? performance.now() - this.t0 : 0
  }

  /** Stops capture; null when under the 0.4 s minimum (09: ignore, don't transcribe). */
  async stop(): Promise<CapturedClip | null> {
    if (!this.ctx) return null
    const ms = this.elapsedMs
    const rate = this.ctx.sampleRate
    const chunks = this.chunks
    this.teardown()
    if (ms < 400 || !chunks.length) return null
    return { wav: toWav16k(chunks, rate), seconds: ms / 1000 }
  }

  abort(): void {
    this.teardown()
  }

  private teardown() {
    this.levelCb = null
    try {
      this.node?.port.close()
      this.node?.disconnect()
      this.src?.disconnect()
    } catch {
      /* already torn down */
    }
    this.stream?.getTracks().forEach((t) => t.stop())
    void this.ctx?.close().catch(() => undefined)
    this.node = null
    this.src = null
    this.stream = null
    this.ctx = null
    this.chunks = []
    this.t0 = 0
  }
}
