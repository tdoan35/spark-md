# TensorFold + voice memory capacity check — Oct 24, 2026

**PASS for the planned memory budget.** On spark-2 (GB10, 128 GB marketed unified RAM; Linux reports 121.69 GiB), minimum host `MemAvailable` was **36.84 GiB**, leaving **21.84 GiB above the mandatory 15 GiB floor**. Spoken answers fit the TensorFold recipe with a 25 GiB imaging allowance. This is a capacity probe, **not a full imaging/UI co-residence acceptance run**.

## Method

- Oct 24, 20:06:15–20:07:18 PT, spark-2, DGX OS, NVIDIA driver 580.178.04. Script: `bench/voice/check_headroom.py`, copied to `~/spark-md-asr/src/` and run with system Python. Raw outputs remain in `~/spark-md-asr/results/headroom-20261024/`.
- Left existing TensorFold (`qwen38-27b-tf`, `PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16`), OpenShell/OpenClaw, GNOME/RDP desktop and unrelated services running. No change to the serving recipe or spark-1.
- Started CUDA whisper.cpp small.en + phrase prompt + Silero VAD on loopback 8178, and pinned Qwen3-TTS 1.7B-Base container (same image digest/config as `2026-10-24-voice-gb10.md`) on loopback 8020. Offline env flags enabled; no image pulls. Warmed ASR and TTS, including TTS CUDA graphs.
- Reserved **25 GiB of actual CUDA memory**, touched it with `fill_(1)` and synchronized, using the staged imaging torch venv. Held it throughout concurrent LLM (600-token completion), TTS (synthetic aiden) and ASR requests. This substitutes for the architecture's sequential imaging peak target; it does not measure actual detector/VISTA peak memory or latency.
- Sampled host `/proc/meminfo` every 200 ms, including startup/allocation/cleanup. Unified memory makes GPU memory/RSS insufficient for whole-box accounting. Sampling may miss shorter transients.
- Released the reservation and stopped only this check's whisper process and temporary TTS container. TensorFold and OpenClaw remain up. Post-cleanup available memory: 73.32 GiB (point-in-time read).

## Results

| Phase | Minimum available (GiB) |
| --- | ---: |
| Existing TensorFold + OpenClaw + desktop baseline | 69.19 |
| Voice service startup/warm-up | 60.93 |
| Both voice services warm | 61.56 |
| Adding/touching the 25 GiB imaging reservation | **36.84** |
| Concurrent LLM + ASR + TTS with reservation held | 38.40 |

All three requests succeeded: LLM returned 600 completion tokens; ASR returned “Compare it to last year”; TTS returned 188,160 PCM bytes (~3.92 s at 24 kHz mono s16). Swap stayed at or below its pre-existing 0.08516 GiB; the test did not increase it.

The warm voice stack reduced available memory by roughly **7.6 GiB** relative to baseline, including host overhead; plan **9 GiB** for voice rather than treating the 5.4 GB TTS GPU report as the entire voice footprint. These are sampled phase minima, not isolated per-process allocation measurements.

## Interpretation and remaining checks

- Capacity supports Ty's decision to include spoken answers with TensorFold's **16 GiB KV pool**, sequential imaging bounded by **25 GiB**, and the 15 GiB reserve. Do not use TensorFold's ~97 GiB default footprint.
- Allow a further **8 GiB** for the final Electron viewer, loaded assets, worker buffers and screen recorder beyond this desktop baseline (**planning allowance, unverified**). Applied to the measured 36.84 GiB minimum, that leaves ~28.84 GiB available, still ~13.84 GiB above the floor.
- The actual detector/VISTA/mesh/worker peak, full-context concurrent agent sessions, Electron scene and recording are **unverified together**. Their combined use must fit these allowances; final acceptance must monitor `MemAvailable` with the real pipeline. Keep imaging models sequential and release intermediate tensors.
- Enough memory does not remove compute contention. Prior voice benchmarks show TTS slower than real time during LLM decoding. Speak after the answer finishes and the shared LLM is idle; buffer complete audio if another study or imaging job competes. Actual TTS + imaging throughput remains **unverified**.

Raw evidence: `2026-10-24-voice-headroom-memory.jsonl`, `2026-10-24-voice-headroom-summary.json`, `2026-10-24-voice-headroom-requests.json` in this directory. No real-person recordings used.
