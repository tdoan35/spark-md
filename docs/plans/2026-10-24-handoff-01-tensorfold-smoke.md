# Handoff 01: TensorFold smoke test (A0), then keep it serving

*From: planning agent · To: the next agent helping Ty execute today's plan · Sat Oct 24, 2026, ~13:30 PT*

## Read first (in this order, ~10 min)

1. `AGENTS.md`: rules, machines, ports. Read **Machines → Rules for the Sparks** in particular.
2. `docs/plans/2026-10-24-prep-day-plan.md`: Constraints, F1–F14, Track A0, and the start of Track C.
3. `docs/build/00-architecture.md`: the Agent tools section only (you'll use those schemas).

## Context in three lines

- Spark MD is our hackathon entry (event: tomorrow, Oct 25). Today we prep and build a throwaway MVP to write the build specs.
- Ty chose **TensorFold** as the working default LLM serving recipe. It's faster and lighter on paper. A full bench comes last (Track A).
- Your job: prove TensorFold is safe to build on (A0), leave it running for the next tracks, then help Ty with whatever track he picks next.

## Where things are

- **Box: spark-2 only.** `ssh ty@ty-dgx-spark-2.tail29ed60.ts.net`. It's our test device, and it was idle at 13:15 (`MemAvailable` 111 GB).
- **Don't touch spark-1.** It serves Ty's coding model.
- **Recipe:**
  - Directory: `~/qwen38-27b-tensorfold` (a git repo, on `main`, with untracked `hf/` and `prepare.*`).
  - Image: `tensorfold-qwen38-27b:v0.6.0`. Container name: `qwen38-27b-tf`.
  - Weights: `hf/hub/` holds `TensorFold/Qwen3.8-27B-MLX-4bit` (15 GB) + `z-lab/Qwen3.8-27B-DFlash2` (3.6 GB).
  - The kernel cache dir `~/.cache/tensorfold-qwen38-27b` exists, so the first start may skip compiling. Unverified.
- **Settings:** all of them are in `scripts/config.sh`. **Environment variables override `.env`.** `.env` currently has `HOST=100.65.103.115` (Tailscale) and `TENSORFOLD_MEMORY_RESERVE_GIB=4`. Don't edit `.env`; pass env vars instead. If you must change a file, make a `spark-md` branch first.
- **Status:** the plan's Status table, rows "A0" and "Running on spark-2". Update both.

## Steps

### 0. Pre-flight

`free -g; docker ps; ss -ltn 'sport = :8000'`. Confirm nothing else of ours is running and port 8000 is free. Record the baseline `MemAvailable`.

### 1. Start with low-memory settings on `127.0.0.1:8000`

```bash
cd ~/qwen38-27b-tensorfold
HOST=127.0.0.1 PORT=8000 SERVED_NAME=qwen3.8-27b PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16 ./start.sh
```

- Record the time to ready (the script runs its own smoke test at the end).
- Then record `MemAvailable` and `docker stats --no-stream qwen38-27b-tf`.
- **Pass:** ready, and the process uses ≲ 40 GiB. The estimate is ~19 GiB of weights and buffers plus the 16 GiB pool; it's unverified.
- If it refuses to start, the message names a size that fits. Adjust `KV_POOL_GB` and `CONTEXT`, and note what you changed.

### 2. Write `bench/tf_smoke.py` in the project

Stdlib only (`urllib`), so it runs on spark-2 with plain `python3`. Copy it to spark-2 and run it there, because the server listens only on 127.0.0.1. You may reuse ideas from `spark-2:~/bench_pair.py`.

The tools are 3 from `00-architecture.md` as OpenAI function schemas: `get_study`, `get_findings`, `viewer_command`. Send `"chat_template_kwargs": {"enable_thinking": false}` unless a check says thinking on.

| Check | Pass criterion |
| --- | --- |
| S1 `GET /v1/models` | lists `qwen3.8-27b` |
| S2 plain chat ("Reply exactly OK") | `OK` |
| S3 tool call, 10 prompts, e.g. "New CT study 1.2.3 arrived. Look it up." and "Show me the nodule in study 1.2.3." | **≥ 9/10** return structured `message.tool_calls` (not tool-call text in `content`), with the right tool name and JSON args that parse and match the schema. Run once with thinking off and once with thinking on; report both. |
| S4 round trip: feed a fake `get_findings` tool result back (`role: tool`), ask for a 2-sentence "why flagged" | Coherent answer that uses only numbers present in the fake result |
| S5 decode speed: ~400-token report-style prose, thinking off, 3 runs | Record median tok/s. For context: the README says 48–58. It is not a gate. |
| S6 longer prompt: ~16k-token prompt, then the same prefix with a new question | Record TTFT cold vs warm (does prefix reuse help?). Record `MemAvailable` after. |

**If S3 fails** (tool calls arrive as text):
1. Check `docker exec qwen38-27b-tf tensorfold serve --help` for a tool-parser option.
2. Check the TensorFold README/RUNBOOK.
3. Report to Ty with the raw response. Don't switch recipes on your own.

**If output quality looks broken** (garbled text, wrong language, loops): report to Ty. The fallback is the tested `Vontra/Qwen3.8-27B-MLX-4bit` (~15 GB download), and it needs his OK.

### 3. Record

Write `docs/benchmarks/2026-10-24-tensorfold-smoke.md` with:
- the exact command;
- image tag and checkpoint revision (`hf/hub/models--TensorFold--Qwen3.8-27B-MLX-4bit/snapshots/<rev>`);
- the S1–S6 table with numbers;
- memory before and after;
- any failures with their raw output.

Then:
- Update the plan's Status rows: A0 result, and "Running on spark-2: `qwen38-27b-tf` on 127.0.0.1:8000, started by A0".
- If S3 passes, add a line to the `AGENTS.md` decisions log: "A0 passed; TensorFold live on :8000 (settings…)".

### 4. Leave it running

Track C5 (harness bake-off), B on GB10 and the MVP all use it. Don't stop it unless Ty says so.

## Then: ask Ty which to pick up next

Suggested order, all in the plan:
- **C1–C4** on spark-2: OpenShell install and sandbox → host networking. Export `NEMOCLAW_DISABLE_TELEMETRY=1` first, and ask Ty before running the NemoClaw installer, because it installs system software.
- **E1:** add the web, `mcp` and ASR wheels to the wheelhouse, then run the offline install on spark-2 (also the arm64 check).
- **B1–B3:** imaging on the laptop's RTX 3080.

## Guardrails

- spark-2 only. Start and stop only what you started.
- Keep `MemAvailable` ≥ 15 GB.
- No pushes, uploads or remote LLM calls with project data.
- Use the scratchpad for temp files. Put durable results in `docs/`, and scripts in `bench/` (allowed prep).
- Inside `spark-md/`, only benchmark scripts are allowed (in `bench/`). Product or MVP code goes in the MVP folder outside the project (`AGENTS.md` non-negotiable 5).
