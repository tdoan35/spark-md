# 02: LLM serving

Status: **TensorFold validated on spark-2 (Oct 24, A0 + C-track + voice headroom).** Track A's tune-and-confirm bench (`docs/benchmarks/2026-10-24-llm-recipes.md`) never ran, so SGLang is an **unverified** fallback. Decision (Ty, Oct 24/25): build on TensorFold; keep backups.
Rebuild budget on the day: ~2 min cold-start check if the image is loaded and the kernel cache is warm (31 s measured warm restart); first start with an empty kernel cache compiles two CUDA extensions (70 s measured). Image load and checkpoint copy from the drive are extra (**unmeasured**). Agent: infra.

## Purpose and scope

Serve Qwen3.8-27B as an OpenAI-compatible endpoint on `:8000`, served name `qwen3.8-27b`, for the OpenClaw agent (inside the sandbox) and the worker's Q&A proxy. In: the launch command, memory settings, smoke test, fallbacks. Out: agent prompts (07), the coding-assistant model on spark-1 (not part of the product).

## Interfaces

| What | Value |
| --- | --- |
| Host clients | `http://127.0.0.1:8000/v1` |
| Sandbox | `http://host.openshell.internal:8000/v1` (→ bridge `172.18.0.1`) |
| Served name | `qwen3.8-27b` (the NemoClaw onboard pins it; `SPARKMD_LLM_URL` in 00) |
| Auth | none (keyless) |
| Thinking | **off by default for the product**: send `chat_template_kwargs: {"enable_thinking": false}`. The server starts with `--thinking` (default on). |
| Container | `qwen38-27b-tf`, image `tensorfold-qwen38-27b:v0.6.0` |

## Dependencies

- Recipe dir: `~/qwen38-27b-tensorfold` (spark-2) = TensorFold `v0.6.0` + `patches/` + `scripts/config.sh`. Env vars override `.env`; don't edit `.env`.
- Image `tensorfold-qwen38-27b:v0.6.0` (id `034aaf3d1c64`, 24.6 GB; base `nvcr.io/nvidia/pytorch:26.07-py3`). A prebuilt twin exists as `ghcr.io/miaai-lab/qwen3.8-27b-dgx-spark-tensorfold:v0.6.0-fb91a0019fdc`.
- Checkpoint `TensorFold/Qwen3.8-27B-MLX-4bit` (snapshot `22d8d538…`, ~15 GB) + drafter `z-lab/Qwen3.8-27B-DFlash2` (~3.6 GB), under `hf/hub/`. Served offline (`HF_HUB_OFFLINE=1` is start.sh's default).
- **On the event box nothing can be pulled or built**: `scripts/prepare.sh` downloads ~19 GB and builds on first run. The image tarball and `hf/` must come from the drive and be verified with `PREPARE=0` (below). **Whether `docker load` of the current image + copied `hf/` + empty kernel cache starts cleanly is unverified.**

## Build steps

1. Baseline: `free -g; docker ps; ss -ltn 'sport = :8000'`. Expect port 8000 free and `MemAvailable` ≥ 60 GiB.
2. Start (the exact command validated in A0, with the bind changed to `0.0.0.0` in C2):
   ```bash
   cd ~/qwen38-27b-tensorfold
   HOST=0.0.0.0 PORT=8000 SERVED_NAME=qwen3.8-27b PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16 ./start.sh
   ```
   Expect the banner "4 streams × 65,536 tokens, fp8 KV, pinned 16.0 GiB cache pool", ready in ~31 s (warm) / ~70 s (first compile). On the event box add `PREPARE=0` so a hash mismatch can't trigger a download.
3. Verify: `curl -s http://127.0.0.1:8000/v1/models` → `{"data":[{"id":"qwen3.8-27b",…}]}`.
4. Verify from the sandbox: `openshell sandbox exec -n spark-md-openclaw -- curl -s http://host.openshell.internal:8000/v1/models` → same.
5. Memory: `free -g` → `MemAvailable` ≈ 75 GiB on an otherwise idle box (server ≈ 36 GiB).
6. Smoke (stdlib script, not in the specs): one plain chat "Reply exactly OK", one tool call with `enable_thinking:false`. Pass = `OK` and a structured `tool_calls` entry. The full A0 suite is `bench/tf_smoke.py`.

Stop: `./stop.sh` (cuts running requests; it warns). Restart with new settings: `./start.sh restart …`.

## Parameters

| Setting | Value | Why / source |
| --- | --- | --- |
| `PARALLEL` | 4 | Agent + Q&A + a spare; 5.4 GB TTS and imaging share the box. A0 |
| `CONTEXT` | 65536 | OpenClaw's system prompt is ~60k tokens (07). Do not lower it without re-checking 07. |
| `KV_POOL_GB` | 16 | Default pool gives a ~97 GiB footprint; 16 GiB gives ~36 GiB. A0 |
| Sampling | temp 1.0, top-p 0.95, top-k 20 | Qwen thinking-mode defaults baked into start.sh; a request's own values win. |
| `PREFILL_FP8` | 1 (default) | Faster prefill; slightly less prompt precision. Unchanged since A0. |
| `VISION` | 1 (default) | Not used by the product. Switching it off may save memory (**unmeasured**). |
| Memory floor | `MemAvailable` ≥ 15 GiB | AGENTS.md; full budget in 00 |

## Gotchas

- **Keyless on every interface.** `HOST=0.0.0.0` exposes `:8000` to LAN/wifi. The sandbox needs the bridge address, so loopback alone fails (07 §C2). Block `:8000` on external interfaces at the console. **How is unverified** (iptables, or bind `127.0.0.1` + `172.18.0.1`).
- **No prefix reuse.** A 16k prompt costs 8.7 s prefill on every turn; OpenClaw's ~60k prompt costs ~30 s on a fresh session. Keep sessions warm; never make a demo step depend on a cold session.
- **Tool calls are native only.** There's no tool-parser flag. With thinking on, 1/10 calls picked the wrong tool in A0. Keep thinking off.
- **UIDs ending a sentence** get their trailing period echoed into tool args. Quote or delimit UIDs in prompts; in the product they come from tool results.
- **Untested-checkpoint warning** (`TensorFold/…` isn't a checkpoint TensorFold is tested with) is expected. Output quality was sane in S2–S4.
- **First start compiles** `tensorfold_qmm_v3` and `tensorfold_gdn_v2` even with a cache dir (`~/.cache/tensorfold-qwen38-27b`). Copying a warm cache to the event box helps; **unverified**.
- `docker stats` RSS (2.8 GiB) is misleading on unified memory. Use the `MemAvailable` delta.
- TTS and the LLM contend for compute even when memory fits. Speak only when the LLM is idle (09).

## Acceptance tests

| Test | Command | Expect |
| --- | --- | --- |
| Up | `curl -s 127.0.0.1:8000/v1/models` | id `qwen3.8-27b` |
| Sandbox route | `openshell sandbox exec … curl host.openshell.internal:8000/v1/models` | same |
| Tools | `bench/tf_smoke.py` S3, thinking off | 10/10 structured `tool_calls` (gate ≥ 9) |
| Grounding | S4 | every number in the answer is in the fake tool result |
| Memory | `free -g` after smoke | `MemAvailable` ≥ 60 GiB with only the LLM + sandbox up |
| Restart | `./start.sh restart` | ready ≤ 60 s, models list unchanged |

## Measured performance (spark-2, Oct 24, TensorFold)

| Metric | Value | Source |
| --- | --- | --- |
| Decode, prose, thinking off | 40.0 tok/s median (3 runs), TTFT ≈ 0.1 s | `2026-10-24-tensorfold-smoke.md` S5 |
| Prefill | ≈ 1,850 tok/s (16k prompt: 8.7 s cold = warm) | S6 |
| Footprint | ~36 GiB (111 → 75 GiB available) | A0 |
| Cold start | 70 s with CUDA compile; 31 s warm restart | A0 + addendum |
| Whole-box minimum with ASR, TTS, OpenClaw, 25 GiB imaging reservation | 36.84 GiB available | `2026-10-24-voice-headroom.md` |

## Fallbacks (cheapest first)

1. **Restart TensorFold** (`./start.sh restart`). A hung or OOM-killed container is the likeliest failure. If `MemAvailable` is low, stop optional consumers (TTS first), then restart.
2. **Lower memory:** `KV_POOL_GB=12 PARALLEL=3`, or `VISION=0`. Both **unverified**; run the smoke test after any change.
3. **Other checkpoint:** `MODEL_ID=Vontra/Qwen3.8-27B-MLX-4bit` is the one TensorFold lists as tested (~15 GB). It is not on the drive unless staged; **needs Ty's OK and a download, so it isn't available air-gapped.**
4. **SGLang + DFlash2** (`~/qwen38-sglang`, image `lmsysorg/sglang:qwen38-27b`, staged on spark-2): **never benched.**
   - `start.sh` hard-codes `PORT=8888`, `HOST=0.0.0.0`, `SERVED_MODEL_NAME=qwen3.8-27b-sglang` (lines ~231–238) and `--mem-fraction-static 0.95`.
   - To replace TensorFold you'd edit those to `8000` / `qwen3.8-27b`. The 0.95 fraction almost certainly breaks co-residence with imaging and voice. Lower it and re-measure.
   - Its tool calling and reasoning parser (`--reasoning-parser qwen3`) are untested with OpenClaw.
   - Treat it as a last resort with **no** evidence behind it.
5. **Degrade the product, not the rules:** if no LLM works, the worker, viewer, Lung-RADS engine and the human gate all still run. Reports can be filled from the deterministic findings by a template, with the agent log showing "agent unavailable". Say so on screen (honesty rule).

## Open / unverified

- Track A bench (real prompts, real co-load, SGLang numbers) not run.
- Event-box image load + checkpoint copy + kernel-cache reuse.
- Blocking `:8000` externally.
- Memory with the full imaging + UI + recording load (00 budget has an 8 GiB unverified allowance).
