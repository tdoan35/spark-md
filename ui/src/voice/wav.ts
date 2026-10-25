/** 09-voice.md Snippets: captured Float32 frames → RIFF PCM s16le, 16 kHz mono WAV blob. */

export function toWav16k(chunks: Float32Array[], inRate: number): Blob {
  const n = chunks.reduce((a, c) => a + c.length, 0)
  const x = new Float32Array(n)
  let o = 0
  for (const c of chunks) {
    x.set(c, o)
    o += c.length
  }
  const r = inRate / 16000
  const m = Math.floor(n / r)
  const pcm = new Int16Array(m)
  for (let i = 0; i < m; i++) {
    // box-average downsample
    let s = 0
    const a = Math.floor(i * r)
    const b = Math.min(n, Math.floor((i + 1) * r))
    for (let j = a; j < b; j++) s += x[j]
    pcm[i] = Math.max(-1, Math.min(1, s / Math.max(1, b - a))) * 0x7fff
  }
  const h = new DataView(new ArrayBuffer(44))
  const w = (p: number, s: string) => [...s].forEach((ch, k) => h.setUint8(p + k, ch.charCodeAt(0)))
  w(0, "RIFF")
  h.setUint32(4, 36 + m * 2, true)
  w(8, "WAVEfmt ")
  h.setUint32(16, 16, true)
  h.setUint16(20, 1, true)
  h.setUint16(22, 1, true)
  h.setUint32(24, 16000, true)
  h.setUint32(28, 32000, true)
  h.setUint16(32, 2, true)
  h.setUint16(34, 16, true)
  w(36, "data")
  h.setUint32(40, m * 2, true)
  return new Blob([h.buffer, pcm.buffer], { type: "audio/wav" })
}
