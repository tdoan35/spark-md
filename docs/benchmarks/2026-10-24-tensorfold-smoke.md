# A0: TensorFold smoke test (Qwen3.8-27B) — 2026-10-24, spark-2

Status: **PASS** (all gates). Server left running for C5 / B / MVP.
Method: `bench/tf_smoke.py` (stdlib only), run on spark-2 against the live server. Raw JSON: `docs/benchmarks/2026-10-24-tensorfold-smoke.raw.json`.

## Setup

- **Machine:** spark-2 (`ty-dgx-spark-2`), DGX Spark GB10, 128 GB unified, DGX OS. Idle before the test (`MemAvailable` 111 GiB, load 0.13).
- **Exact command:**

  ```bash
  cd ~/qwen38-27b-tensorfold
  HOST=127.0.0.1 PORT=8000 SERVED_NAME=qwen3.8-27b PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16 ./start.sh
  ```

- **Image:** `tensorfold-qwen38-27b:v0.6.0` (id `034aaf3d1c64`, container `qwen38-27b-tf`).
- **Checkpoint:** `TensorFold/Qwen3.8-27B-MLX-4bit`, snapshot `22d8d538154e0e5b6f8dcb1fcc74a60a0798104c`, drafter `z-lab/Qwen3.8-27B-DFlash2`. Effective serve args: `--parallel 4 --context 65536 --temperature 1.0 --top-p 0.95 --top-k 20 --prefill-fp8 --vision --thinking`.
- **Time to ready:** 70 s from launch (`loaded in 67.6s`). This start **compiled two CUDA extensions** (`tensorfold_qmm_v3`, `tensorfold_gdn_v2`) despite the kernel cache dir existing — the "first start skips compiling" hope was wrong for this config; a restart should now reuse them (**unverified**).
- **Server banner:** 4 streams × 65,536 tokens, fp8 KV, pinned 16.0 GiB cache pool (524,288 tokens), 3 prompt states kept; startup estimate 41.57 GiB.

## Results

| Check | Result | Pass |
| --- | --- | --- |
| S1 `GET /v1/models` | `["qwen3.8-27b"]` | ✅ |
| S2 plain chat "Reply exactly OK" | `OK` | ✅ |
| S3 tool calls, thinking **off** | **10/10** structured `message.tool_calls`, right tool, schema-valid args | ✅ (gate ≥9) |
| S3 tool calls, thinking **on** | **9/10** (one wrong-tool miss, see below) | ✅ (gate ≥9) |
| S4 tool round trip → "why flagged" | Coherent 2-sentence answer; every number (10 mm, 14 mm, 371 d, 47 d, 4B) present in the fake result; zero invented numbers | ✅ |
| S5 decode, ~517-token prose, thinking off, 3 runs | 40.1 / 40.0 / 40.0 → **median 40.0 tok/s net**; TTFT ≈ 0.1 s. Not a gate; README's 48–58 is other settings | ✅ recorded |
| S6 16,061-token prompt, cold then same-prefix/new-question | TTFT **8.69 s cold vs 8.71 s warm** → **no prefix reuse**; prefill ≈ 1,850 tok/s; `MemAvailable` 75.1 GiB after | ✅ recorded |

All 20 S3 responses returned structured `tool_calls` (JSON args, correct types, enum-valid commands); none emitted tool-call text in `content`. `chat_template_kwargs: {"enable_thinking": false}` is honored.

## Memory

| When | `MemAvailable` |
| --- | --- |
| Before start (idle) | 111 GiB |
| After load, idle-serving | 75 GiB |
| After full S1–S6 suite (incl. two 16k prompts) | 75.1 GiB |

Server footprint ≈ **36 GiB** (111 − 75), under the ≲40 GiB target and consistent with the 41.57 GiB startup estimate. `docker stats` RSS reads 2.82 GiB — misleading on GB10 unified memory; use the `MemAvailable` delta. Floor ≥ 15 GiB: satisfied (75 GiB free with the server up).

## Failures / notes (raw)

- **S3 thinking on, prompt 2** ("Show me the nodule in study 1.2.3.4.5.") → called `get_study {"study_uid":"1.2.3.4.5"}` instead of `viewer_command(show_nodule)`. The only wrong-tool miss in 20 calls. Thinking on also burns tokens before the call; **product default stays thinking off**.
- First run artifact (fixed in the script, kept for the record): when a UID ended a sentence ("for study 4.4.4.4.4."), both modes echoed the trailing period into `study_uid` (`"4.4.4.4.4."`) — schema-valid but wrong. In the product, UIDs come from tool results, not free text; real prompts should still quote or delimit them.
- S6 first pass with a 34,142-token prompt (oversized builder): TTFT 19.88 s cold / 19.96 s warm — confirms no prefix reuse at longer prompts too, and prefill scales ≈ linearly with prompt length.
- No tool-parser option exists in `tensorfold serve --help` — tool calling is native only; nothing to tune server-side.
- The container logs the untested-checkpoint warning (`TensorFold/…` is not a checkpoint TensorFold is tested with) — expected (F7); S2–S4 output quality looked sane, but G4 in Track A is the real grounding gate.
- The server keeps "3 prompt states", yet identical 16k prefixes saw no TTFT benefit across requests. Treat warm agent-turn latency as ≈ full re-prefill (~5–7 s at a 12k-token harness prefix) when ranking recipes and harnesses (A1 P3, C5).

## Verdict

A0's four catches all clear: low-memory settings hold (~36 GiB), loopback `:8000` bind works, structured tool calls work (10/10 off, 9/10 on), output quality sane on the untested checkpoint. **TensorFold stays serving on `127.0.0.1:8000` for C5, B-on-GB10 and the MVP.**

## Addendum (14:00, C2 dependency)

Sandboxed agents reach the LLM via the OpenShell bridge (`host.openshell.internal` → `172.18.0.1:8000`), so the server was restarted with `HOST=0.0.0.0` (same other settings). Warm restart: **31 s** to ready (CUDA extensions reused — kernel cache works after first compile). Host clients keep using `127.0.0.1:8000`. Note for the event box: `0.0.0.0` exposes the keyless API on every interface; block `:8000` externally (unverified how).

After the rebind, the sandboxed agent consumes the same server through `host.openshell.internal:8000`; everything else in this record is unchanged.
