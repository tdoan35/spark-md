# 09: Voice (push-to-talk ASR, fixed commands, spoken answers)
Status: ASR + TTS **validated on GB10 with synthetic voices (Oct 24)**. **Oct 25, on the box:** `/api/asr` + `/api/tts` live behind the worker; Electron push-to-talk (getUserMedia → AudioWorklet → 16 kHz WAV → `/api/asr` → transcript bubble → `submit`) and post-`done` TTS fetch verified end to end in a CDP-driven Electron run (fake tone device + a TTS-generated "Show me the nodule." clip fed through a patched `getUserMedia`): ASR 92–116 ms, keyup → transcript bubble ~0.5 s, miss-clip toast verified; `/api/tts` clip 0.9 s idle / ~12 s with concurrent GPU benches; playback (`onended`) verified on a null sink. **Unverified:** real human voices and audible output on the event mic/speaker (no capture device on the box at 13:20; `arecord -l` empty). Bench record: `docs/benchmarks/2026-10-24-voice-gb10.md`.
Rebuild budget on the day: 45 min ASR (whisper.cpp build + `/api/asr` + PTT in the UI), +20 min TTS. Worker agent does the routes; UI agent does capture/playback. **Oct 25:** `/api/ask` (text path, incl. the immediate viewer action below) moved to agent A (`sparkmd/ask.py`) so the ask chips work without voice; V adds only `/api/asr`, `/api/tts` and push-to-talk on top.

## Purpose and scope
- **In:** hold-to-talk (hold **Space** or the mic button in the ask box) → 16 kHz WAV → `POST /api/asr` → local whisper.cpp → fuzzy match to **4 fixed commands** → the same `submit()` the ask-box chips use (08 U9). **Spoken answers are in scope (Ty confirmed Oct 24):** use local Qwen3-TTS, synthetic voice aiden, after the answer finishes. ASR default is whisper.cpp small.en + phrase prompt + Silero VAD; retain faster-whisper and base.en for pre-demo comparison/fallback.
- **Out:** free-form dictation, wake word, always-listening, voice approval. **Approve is click only**; "Approve the report" is a tested negative and must map to nothing.
- **Cut order:** TTS first → then voice entirely (chips + clicks stay; they're the fallback on camera anyway).
- **Air gap:** no browser Web Speech API (Chrome sends audio to Google). Both servers bind `127.0.0.1` only.

## Commands (final phrases for Joyce)

| id | Say exactly | Also accepted (tested) | Canonical text sent to `/api/ask` | Viewer effect |
| --- | --- | --- | --- | --- |
| `show_nodule` | "Show me the nodule." | "Show me that nodule", "Show the nodule", "…please" | `Show me the nodule.` | `viewer_command show_nodule` |
| `compare_prior` | "Compare it to last year." | "Compare to last year", "Compare this to last year's scan" | `Compare it to last year.` | `viewer_command compare_prior` |
| `why_flag` | "Why did you flag this?" | "Why'd you flag this one?", "Why was this flagged?" | `Why did you flag this?` | none (answer only) |
| `reset_view` | "Reset the view." | "Reset view" | `Reset the view.` | `viewer_command reset_view` |

Leading "okay / so / hey / um / please" are ignored. Rehearsal tips for Joyce: hold the key, **start speaking ~0.3 s after pressing**, release **after** the last word, normal volume, mic 20–40 cm away.

## Interfaces

**UI → worker:** `POST /api/asr`, body `audio/wav` (RIFF PCM s16le, **16 000 Hz, mono**, ≤ 6 s, ≤ 256 kB) →
`200 {text, command, phrase, score}`: `command` ∈ `show_nodule|compare_prior|why_flag|reset_view|null`; `phrase` = canonical text (or `null`); `score` = best match ratio 0–1. `422` if the body isn't 16 kHz mono s16 WAV. On `command:null` the UI shows a toast with `text` ("Didn't catch that: …") and does nothing else. On a command, the UI shows the transcript as the user's question bubble, then calls its existing `submit(phrase)` (→ `/api/ask`, 08).

**Worker → ASR:** `whisper-server` on `127.0.0.1:8178`, `POST /inference` multipart: `file` (the WAV as received), `response_format=json`, `prompt=<PROMPT>` (per request; tested). Response `{"text": "..."}`. Empty input returns `[BLANK_AUDIO]` or a bracketed tag, which the matcher rejects.

**UI → worker (TTS):** `POST /api/tts {text}` → worker normalises the text (Parameters) → `POST 127.0.0.1:8020/v1/audio/speech {"model":"tts-1","voice":"aiden","input":…,"response_format":"pcm"}` → streams back `audio/L16; rate=24000; channels=1` (raw s16le). The UI plays it with Web Audio. **Call it only after `/api/ask` sends `done`** and while the shared LLM is idle (another background study may still be generating). Buffer the clip if competing GPU work cannot be avoided. Show "Synthetic voice (Qwen3-TTS, on device)" and a mute control. Stop playback when push-to-talk starts so the speaker does not feed the mic.

**Ports (add to 00):** ASR `127.0.0.1:8178`, TTS `127.0.0.1:8020`. Neither is reachable from the sandbox (loopback), and the agent has no ASR/TTS tool.

**Immediate viewer action (Ty approved Oct 24; implementation unverified):** preserve `/api/asr` as recognition-only. When its canonical phrase reaches `/api/ask {study_uid, text}`, the worker deterministically maps the three viewer phrases to `show_nodule` / `compare_prior` / `reset_view` and immediately emits `viewer_command` SSE for that study, before calling the agent. The same path serves typed chips. Log `command → show_nodule` as a `system` agent-log entry; `why_flag` only requests an answer. Pass the completed action into the agent context and suppress duplicate same-action viewer tool calls within that ask request; return the existing action result. Keep deduplication scoped to the request and study so later intentional commands still run. No camera move waits for LLM prefill.

## Dependencies
| What | Where (drive) | Pin |
| --- | --- | --- |
| whisper.cpp source | `models/asr/whispercpp/whisper.cpp-231638a.tar.gz` | commit `231638a0717b7822784297e5980965ffcec05810` (Oct 19, 2026), libwhisper 1.9.5 |
| ASR model | `models/asr/whispercpp/ggml-small.en.bin` (488 MB) | `ggerganov/whisper.cpp`; SHA256 in `models/SHA256SUMS` |
| ASR fallback model | `models/asr/whispercpp/ggml-base.en.bin` (148 MB) | same |
| VAD model | `models/asr/whispercpp/ggml-silero-v5.1.2.bin` (0.9 MB) | `ggml-org/whisper-vad` |
| Build tools | DGX OS: `/usr/local/cuda/bin/nvcc` (CUDA 13.0), `cmake`, `gcc` (present on spark-2; `nvcc` is **not on PATH** by default) | – |
| TTS image | spark-2 `~/spark-md-staging/containers/faster-qwen3-tts-dgx-spark-v6.15.0.tar` (7.7 GB), SHA256 in `SHA256SUMS.voice` next to it | `martinb78/faster-qwen3-tts-dgx-spark@sha256:ee83531abd5df4aa11f165110703bfd7d581d7d59c42e58a429c919b35d5f072` (tag `v6.15.0`; **never `:latest`**) |
| TTS model | `models/tts/Qwen3-TTS-12Hz-1.7B-Base/` (4.3 GB, Apache-2.0) | SHA256 in `models/SHA256SUMS` |
| TTS voice | `models/tts/voices/{aiden_ref.wav, ref.txt, voices.json}` | aiden_ref = synthetic (Qwen3-TTS CustomVoice speaker "aiden"), not a real person |
| Python | none new. The worker calls both servers with `httpx` (already in the wheelhouse). The matcher is stdlib `difflib`. | – |

Not used, and why: faster-whisper and Parakeet-ONNX run **CPU-only on aarch64** (PyPI `ctranslate2`/`onnxruntime` have no CUDA there), at 5–13× the latency and lower accuracy (bench record). `faster-whisper` is in the wheelhouse lock from E1 and `models/asr/faster-whisper-small/` exists; it's harmless and is the CPU fallback if the whisper.cpp build fails (decode WAV to a numpy array yourself, since PyAV file decode is broken with the pinned `av`).

## Build steps
1. **Build whisper.cpp (CUDA, sm_121).**
   ```bash
   M=$DRIVE/models/asr/whispercpp; mkdir -p ~/sparkmd-voice && cd ~/sparkmd-voice
   tar xzf $M/whisper.cpp-231638a.tar.gz && cd whisper.cpp
   PATH=/usr/local/cuda/bin:$PATH cmake -B build -DGGML_CUDA=1 -DCMAKE_CUDA_ARCHITECTURES=121 -DCMAKE_BUILD_TYPE=Release
   cmake --build build -j 12 --target whisper-cli whisper-server
   ```
   Verify: `build/bin/whisper-cli -m $M/ggml-small.en.bin -f samples/jfk.wav -nt 2>&1 | grep -E "GB10|fellow"` → `Device 0: NVIDIA GB10, compute capability 12.1` and "And so, my fellow Americans, ask not what your country can do for you…" (checked on spark-2, Oct 24).
2. **Run the ASR server.**
   `build/bin/whisper-server -m $M/ggml-small.en.bin --host 127.0.0.1 --port 8178 -l en -t 8 -nt --vad -vm $M/ggml-silero-v5.1.2.bin`
   Verify: `curl -s 127.0.0.1:8178/inference -F file=@samples/jfk.wav -F response_format=json` → `{"text":" And so, my fellow Americans, …"}` (checked on spark-2, Oct 24). Expect ~0.9 GB GPU in `nvidia-smi`.
3. **Worker `/api/asr`** (06): check the WAV header (16 kHz, mono, 16-bit) → forward to `:8178` with `prompt` → `match()` (Snippets) → JSON. Verify with a recorded clip: `curl -s -XPOST 127.0.0.1:8100/api/asr --data-binary @show.wav -H 'Content-Type: audio/wav'` → `{"command":"show_nodule",…}`; a 1.5 s silence WAV → `{"command":null,…}`.
4. **UI push-to-talk** (08 U9 mic slot): Electron main allows only `media` permission for the app origin (`session.defaultSession.setPermissionRequestHandler((wc, p, cb) => cb(p === "media"))`). Renderer: `getUserMedia({audio:{channelCount:1, echoCancellation:true, noiseSuppression:true, autoGainControl:true}})` → `AudioContext` + `AudioWorklet` collecting Float32 frames while Space is held → resample to 16 kHz → s16 WAV (Snippets) → `/api/asr`. Show a live level meter while recording and "Transcribing…" after release. Verify: hold Space, say "Show me the nodule" → camera flies to the nodule.
5. **TTS.**
   ```bash
   docker load -i faster-qwen3-tts-dgx-spark-v6.15.0.tar
   mkdir -p ~/sparkmd-voice/tts-config/speakers && cp $DRIVE/models/tts/voices/aiden_ref.wav ~/sparkmd-voice/tts-config/speakers/ && cp $DRIVE/models/tts/voices/voices.json ~/sparkmd-voice/tts-config/
   docker run -d --name sparkmd-tts --gpus all -p 127.0.0.1:8020:8000 -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
     -v $DRIVE/models/tts/Qwen3-TTS-12Hz-1.7B-Base:/models/Qwen3-TTS:ro -v ~/sparkmd-voice/tts-config:/config \
     martinb78/faster-qwen3-tts-dgx-spark@sha256:ee83531abd5df4aa11f165110703bfd7d581d7d59c42e58a429c919b35d5f072
   ```
   (The config dir must be writable: the server caches the speaker embedding as `/config/speakers/aiden.pt` on first use.) Verify: `curl -s 127.0.0.1:8020/health` → `{"status":"ok","model_loaded":true}` within ~60 s; then `curl -s 127.0.0.1:8020/v1/audio/speech -H 'Content-Type: application/json' -d '{"model":"tts-1","input":"View reset.","voice":"aiden","response_format":"wav"}' -o t.wav` → ~1.5 s WAV. Send one warm-up request at startup (the first one captures CUDA graphs).
6. **Worker `/api/tts`** + UI playback after `done`. Verify: ask "Why did you flag this?" → text streams, then the answer is spoken in the aiden voice.

## Parameters
| Name | Value | Source |
| --- | --- | --- |
| ASR prompt | `Show me the nodule. Compare it to last year. Why did you flag this? Reset the view.` | bench: +4–10 clips/variant |
| VAD | `--vad`, Silero v5.1.2, defaults (threshold 0.50, min speech 250 ms, pad 30 ms) | bench: removes prompt hallucination on noise (7 → 0 wrong commands) |
| Match accept | best ≥ **0.80** and best − second ≥ **0.08** (difflib ratio on normalised text) | bench sweep: 0.70–0.80 equal for small.en+VAD; 0.70 lets turbo misfire |
| Filler words dropped | okay ok um uh so hey please spark alright now | – |
| Clip limits | 16 kHz mono s16, max 6 s (auto-stop), min 0.4 s (else ignore) | – |
| whisper-server threads | `-t 8` | as benched |
| TTS voice | `aiden` (Base 1.7B voice clone; seeded per voice → same voice every call) | serena mispronounces *nodule* / *Lung-RADS* |
| TTS text normalisation | strip markdown; `Lung-RADS` → `Lung RADS`; `mm` → `millimeters`; speak the first ≤ 2 sentences / ≤ 300 chars of the answer | round-trip test |
| TTS output | `pcm`, 24 000 Hz s16le mono | server |

## Gotchas
- **Prompt biasing makes whisper invent the prompt on noise** ("Why did you flag this?" from brown noise) → an accidental press fires a command. Fix: always run with `--vad`. Don't drop VAD to save 30 ms.
- **No ffmpeg on DGX OS** (spark-2) → don't use `MediaRecorder` (webm/opus) or `whisper-server --convert`. The UI sends 16 kHz WAV it encodes itself.
- `nvcc` isn't on `PATH` on DGX OS: prefix `PATH=/usr/local/cuda/bin:$PATH` for the cmake step.
- faster-whisper: `transcribe(path)` fails with the pinned PyAV (`open() got an unexpected keyword argument 'metadata_errors'`); pass a float32 numpy array. On aarch64 it is CPU-only.
- The TTS image's server (`examples/openai_server.py`) supports **voice clone only**. A CustomVoice/VoiceDesign model there raises `Loaded model does not support…`. Use the Base model + a reference WAV.
- TTS `response_format: "zip"` lazily downloads `Qwen/Qwen3-ForcedAligner-0.6B` (network) → never use `zip`.
- faster-qwen3-tts (pip, 0.5.4) breaks on transformers ≥ 5.20 (`MimiConfig has no attribute rope_theta`); 5.15.1 works. It also conflicts with the wheelhouse's transformers 4.46.3 → **TTS lives only in its container**, never in the worker venv.
- `pkill -f <pattern>` over SSH can match the SSH shell itself and kill the session; kill by PID.

## Acceptance tests (feed 11)
1. ASR server up, warm: 20 recorded clips per speaker (Ty, Joyce; 4 phrases × 5) on the event mic → **20/20 correct, 0 wrong commands**, each < 300 ms server time.
2. 10 presses with nobody talking (room noise) + "Approve the report" ×3 + "Next patient" ×3 → **all `command:null`**.
3. Storyboard check: "Do all three voice commands work on the first try, five times in a row?" → yes, end to end (camera moves / compare opens / answer streams).
4. TTS: "Why did you flag this?" answer spoken with *nodule* and *Lung RADS* pronounced right; first audio < 1 s after `done`.
5. Immediate viewer action: delay the agent response by 10 s; all three viewer commands emit one SSE action before agent work, with a visible system log. A later duplicate tool call must not move the camera again; a new user request must still work. **Unverified.**
6. Speaker/mic: start playback, then hold Space → playback stops before capture; no self-triggered command. **Unverified.**
7. Air gap: with egress blocked, both servers start and answer (no HF/network calls; `HF_HUB_OFFLINE=1`).

## Measured performance (GB10, spark-2, Oct 24; method in the bench record)
| Thing | Result |
| --- | --- |
| whisper.cpp small.en + prompt + VAD, 2–3 s clip, LLM idle | 74 ms median / 125 ms p95; 337/339 right, 0 wrong commands (synthetic voices) |
| same, LLM decoding in parallel | 151 / 254 ms, same accuracy |
| whisper.cpp base.en + prompt (+ VAD) | 21 / 31 ms (52 / 84 ms); 335/339 (334/339) |
| ASR memory | ~0.9 GB GPU + 0.3 GB RSS |
| TTS first audio / gen÷audio, LLM idle | ~680 ms / 0.67–0.70 |
| TTS while LLM decodes | ~1.9–2.1 s / 1.4–1.9 (slower than real time: **don't stream it while the LLM is busy**; buffer the whole clip or skip TTS) |
| TTS memory | ~5.4 GB GPU; combined warm ASR + TTS host/GPU delta ~7.6 GiB; budget 9 GiB |
| Whole-box capacity probe (TensorFold + OpenClaw + voice + touched 25 GiB imaging allowance) | minimum 36.84 GiB available; 21.84 GiB above floor. See `docs/benchmarks/2026-10-24-voice-headroom.md`. Actual imaging/UI co-load unverified. |

## Snippets
Matcher (worker; stdlib only, as benched):
```python
import re
from difflib import SequenceMatcher
COMMANDS = {
    "show_nodule":   ["show me the nodule", "show the nodule", "show me that nodule"],
    "compare_prior": ["compare it to last year", "compare to last year", "compare this to last years scan"],
    "why_flag":      ["why did you flag this", "why was this flagged", "why did you flag this one"],
    "reset_view":    ["reset the view", "reset view"],
}
FILLER = {"okay", "ok", "um", "uh", "so", "hey", "please", "spark", "alright", "now"}
def norm(t):
    t = re.sub(r"\bwhy'd\b", "why did", t.lower().replace("’", "'"))
    t = re.sub(r"[^a-z' ]+", " ", t).replace("'", "")
    return " ".join(w for w in t.split() if w not in FILLER)
def match(text, threshold=0.80, margin=0.08):
    n = norm(text)
    s = sorted(((max(SequenceMatcher(None, n, p).ratio() for p in ps), c) for c, ps in COMMANDS.items()), reverse=True)
    (s1, c1), (s2, _) = s[0], s[1]
    return (c1 if s1 >= threshold and s1 - s2 >= margin else None), round(s1, 3)
```
16 kHz WAV from captured Float32 frames (renderer; **unverified** in Electron):
```ts
function toWav16k(chunks: Float32Array[], inRate: number): Blob {
  const n = chunks.reduce((a, c) => a + c.length, 0), x = new Float32Array(n);
  let o = 0; for (const c of chunks) { x.set(c, o); o += c.length; }
  const r = inRate / 16000, m = Math.floor(n / r), pcm = new Int16Array(m);
  for (let i = 0; i < m; i++) {                       // box-average downsample
    let s = 0, a = Math.floor(i * r), b = Math.min(n, Math.floor((i + 1) * r));
    for (let j = a; j < b; j++) s += x[j];
    pcm[i] = Math.max(-1, Math.min(1, s / Math.max(1, b - a))) * 0x7fff;
  }
  const h = new DataView(new ArrayBuffer(44)), w = (p: number, s: string) => [...s].forEach((ch, k) => h.setUint8(p + k, ch.charCodeAt(0)));
  w(0, "RIFF"); h.setUint32(4, 36 + m * 2, true); w(8, "WAVEfmt "); h.setUint32(16, 16, true);
  h.setUint16(20, 1, true); h.setUint16(22, 1, true); h.setUint32(24, 16000, true); h.setUint32(28, 32000, true);
  h.setUint16(32, 2, true); h.setUint16(34, 16, true); w(36, "data"); h.setUint32(40, m * 2, true);
  return new Blob([h.buffer, pcm.buffer], { type: "audio/wav" });
}
```

## Open / unverified
- ~~Electron `getUserMedia` + AudioWorklet on the box's desktop~~ verified headless Oct 25 (see Status); real mic input still pending. Worklet must be a same-origin `public/` file — the page CSP (`script-src 'self'`) rejects blob:-URL worklet modules.
- **Speaker/microphone:** Ty confirmed he will bring a plug-in speaker/microphone. Test input and output on the event box at 08:30 together with the WebGL probe (`arecord -l` lists capture devices; select the PipeWire/Pulse input/output). Repeat the real-voice and room-noise tests on that device, with playback interrupted by push-to-talk.
- Immediate viewer action and duplicate suppression: approved; end-to-end implementation unverified (see Interfaces).
- TTS is in scope (Ty confirmed Oct 24); show "Synthetic voice (Qwen3-TTS, on device)" in the UI. The image is a third-party community build (MIT, `mARTin-B78/dgx-spark-faster-qwen3-tts`); it's pinned by digest and runs on loopback only.
- TTS while a real imaging job runs: throughput/latency not measured. Capacity check with a touched 25 GiB imaging reservation passed (36.84 GiB minimum available); real imaging peak and complete UI/recording co-load remain unverified.
