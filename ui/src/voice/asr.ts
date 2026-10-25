import { API_BASE } from "@/api/config"

/** POST /api/asr response (09): command null = no match, phrase = canonical text. */
export interface AsrResult {
  text: string
  command: string | null
  phrase: string | null
  score: number
}

/** Raw 16 kHz mono s16 WAV bytes → worker → whisper.cpp + phrase match.
 *  Errors come back as `{error}` JSON (422 bad wav / 502 upstream down / 403 not loopback). */
export async function postAsr(wav: Blob, signal?: AbortSignal): Promise<AsrResult> {
  const res = await fetch(`${API_BASE}/api/asr`, {
    method: "POST",
    headers: { "content-type": "audio/wav" },
    body: wav,
    signal,
  })
  const body = (await res.json().catch(() => null)) as (AsrResult & { error?: string }) | null
  if (!res.ok || !body) throw new Error(body?.error ?? `asr ${res.status}`)
  return body
}
