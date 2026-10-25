# 06: Worker API (FastAPI + MCP + SSE + trigger + human gates)

Status: **rehearsed Oct 24–25** (throwaway MVP worker, fixture imaging): stdlib contract test **27/27 on the laptop and on spark-2 (aarch64, wheelhouse venv)**; OpenClaw drove a full triage chain through it on spark-2. Unverified: the `/hooks/agent` trigger (config read, never fired), the full C5 rerun score (cut at ~5/20 for time, no failures seen), job past the MCP timeout, and the 00 v0.6 `awaiting_confirmation` status (the rehearsal used a close variant; see Gotchas).
Rebuild budget on the day: ~60–90 min for one agent (worker + contract test), after 03/04/05 expose their functions.

## Purpose and scope

One process, `uvicorn` on `10.77.0.1:8100` (bind `0.0.0.0` on spark-2 for testing; see 07 for addresses). It owns the SQLite registry, serves the REST API in `00-architecture.md` ("Worker API, v0"), the same tools as MCP at `/mcp`, the SSE stream for the UI, triggers the agent, logs every agent call, and enforces the two human gates (diameter confirm, report approve).

- In: everything in the 00 Worker API table except `/api/ask` (text path → agent A, `sparkmd/ask.py`, mounted by W with one include line; Oct 25), `/api/asr`, `/api/tts` (→ 09) and `/api/netstats` (→ 10).
- Out: imaging (04 functions called from the job thread), Lung-RADS math (agent I's `sparkmd/rules/`, recreated from 05 on the day; never copy `scripts/lungrads/`), UI.
- Cut first: `/api/jobs/{id}` (long-poll already returns progress). **Not cut:** `GET /api/agent-log?study_uid=&limit=` history (the UI log panel needs it; 00 v0.8).

## Interfaces

Contract = **00 v0.8** (routes, tables, findings shape, tools; v0.8 addendum wins where this spec differs). This spec adds only what the rehearsal pinned down:

| Item | Value |
| --- | --- |
| Caller classification | `agent` if `X-SparkMD-Caller: agent` **or** client IP not in `{127.0.0.1, ::1}`; else `ui`. Sandbox traffic arrives from **`172.18.0.2`** (OpenShell bridge), measured spark-2 Oct 25, so it is never loopback. |
| Human gates | `POST /api/nodules/{id}/confirm` and `POST /api/reports/{id}/approve`: refuse (403) any `agent` caller. Optional `SPARKMD_UI_TOKEN` → also require header `X-SparkMD-UI-Token` (defense in depth; Electron holds it). Policy also denies both routes (07). |
| Approve precondition | 409 `{error:"confirm_all_first", already_approved:false}` (no `report`) while any nodule on the study is unconfirmed; already approved → 409 `{report, outbox_id, already_approved:true}` (00 v0.8). Approving a `pcp_letter` writes `outbox` and emits `outbox_delivered`. |
| Findings split | The **agent never sees proposals**: MCP `get_findings` and agent-classified REST `GET …/findings` omit `proposal` (and all sizes) until confirmed; UI-classified callers get `proposal` for the confirm panel. Stronger than 00's "proposal stays for audit": keep audit in the UI view only. |
| Confirm math | `mean_mm = round((long_mm + short_mm)/2, 1)` (Lung-RADS mean diameter); the UI sends both `long_mm` and `short_mm` (prefilled from the proposal); `short = long` when there is no proposal and no short; reject unless `0 < short ≤ long ≤ 100`. `edited` = differs from proposal. After the **last** nodule: run the rules engine `assess()` (map `driver` → `driver_nodule_id`, add `rules_version`), write `assessments`, status → `analyzed`, SSE `study_updated` + `worklist_changed {reason:"status"}`, trigger phase 2 (07). |
| `new` flag for 05 | `new = (patient has an earlier study) and (no confirmed prior on the same track)`. On a baseline exam every nodule is baseline, never "new" (rehearsal bug: T0 10 mm scored 4B S-NEW instead of 4A). |
| Growth input | `growth_mm = rules.growth_per_12mo(delta_mean_mm, interval_days)` (05, decided Oct 25). The rehearsal used a strict 366 d cut-off, now superseded. |
| VDT | from confirmed diameters as spheres (`π/6·d³`), `interval·ln2/ln(V2/V1)`, null if not growing; evidence only (05). |
| `run_analysis` long-poll | REST `wait_s ≤ 300`; MCP waits `SPARKMD_MCP_WAIT_S` (set **≤ 50**, under OpenClaw's 60 s `requestTimeoutMs`); concurrent calls for one study **join one job** (same `job_id`). Returns `{job_id, state, stage, elapsed_s, study_status}` (`state` = job state `queued|running|done|failed`; `study_status` = `awaiting_confirmation` once proposals are ready, 00 v0.8); if still running, tool text says to call again. |
| MCP | streamable HTTP, **JSON responses (no SSE upgrade)**: `initialize` (echo client `protocolVersion`, return `Mcp-Session-Id`), notifications → 202 empty, `ping`, `tools/list`, `tools/call` (result = one text item with the REST JSON, `isError` = status ≥ 400). `GET /mcp` → 405 `Allow: DELETE, POST`; `DELETE /mcp` → 204. All three methods need policy allow rules (07). |
| Agent-call log | Middleware writes every `agent` REST request to `agent_events` (`source=tool_call`, `"METHOD path -> status"`); `/mcp tools/call` logs `"<tool> -> <status> (<s>)"` with args. Each insert also emits SSE `agent_log`. `log_event` → `source=agent_note`. Gate denials → `source=system`. |
| SSE `GET /api/events` | `text/event-stream`, headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`; first line `: connected`, `: ping` every 15 s; one `asyncio.Queue` per client; threads post via `loop.call_soon_threadsafe`. Event names as in 00. |
| Trigger | `POST http://127.0.0.1:18789/hooks/agent` (host side; OpenShell forwards the gateway), headers `Authorization: Bearer $SPARKMD_HOOK_TOKEN`, `Idempotency-Key: study-<uid>` (phase 2: `study-<uid>-confirmed`), body `{"message", "name":"spark-md", "agentId":"main", "deliver":false}`. Fire-and-forget thread; log result as `system` event. |
| Demo routes | `POST /api/demo/reset {empty?}`, `POST /api/demo/drop {patient_id, timepoint}` (loopback only; drop → `intake.ingest_study` from `backlog/<patient_id>/<timepoint>/` → `received` → `organized` → SSE + trigger; 409 if already dropped). Intake contract, backlog layout and status ownership: `03-intake-registry.md` §Worker integration. |

Env vars: `SPARKMD_DB`, `SPARKMD_REQLOG` (JSONL of every request incl. MCP bodies — C5's runner scores from it with `C5_REQLOG`), `SPARKMD_MCP_WAIT_S`, `SPARKMD_UI_TOKEN`, `SPARKMD_HOOK_URL`, `SPARKMD_HOOK_TOKEN`. Rehearsal-only: `SPARKMD_FAKE_ANALYZE_S`, `SPARKMD_AUTOCONFIRM=1` (proposals auto-confirmed, for the old-flow C5 regression).

## Dependencies

Wheelhouse (E1): `fastapi 0.162.0`, `starlette 1.10.0`, `uvicorn 0.54.0`, `pydantic 2.14.1`; verified importable from a fresh wheelhouse venv on spark-2 (`~/venvs/spark-md-offlinetest`). **No `mcp` SDK, `httpx` or `pytest` in the wheelhouse** — hand-roll MCP (≈60 lines, snippet below) and write tests with `urllib` + stdlib `unittest` (works anywhere). 05: import agent I's `sparkmd/rules/` (recreated from 05 on the day; never copy `scripts/lungrads/`, hackathon no-prebuilt-code rule).

## Build steps

1. Registry: 00 v0.6 tables in SQLite (`check_same_thread=False` + one `RLock` around execute/commit). Verify: `sqlite3 $SPARKMD_DB .tables`.
2. Tool layer: one `async call_tool(name, args) -> (obj, status)` used by **both** REST handlers and MCP, so the two can't drift. Verify: contract test MCP + REST checks.
3. Middleware (caller classification + agent-call log), gates, confirm/approve, SSE, job thread, trigger, demo routes.
4. Run: bind address from env (00 v0.8). Mac dev: `--host 127.0.0.1 --port 8100`. Event box: `--host 0.0.0.0 --port 8100` with external interfaces firewalled, so the UI uses `127.0.0.1` and the sandbox `10.77.0.1` (a second `--host` is not supported). **Never run the UI against `10.77.0.1`**: it is classified as the agent and gets 403 on confirm/approve. Verify: `curl 127.0.0.1:8100/api/health` → `{"status":"ok",...}` (box: also `curl 10.77.0.1:8100/api/health`).
5. Contract test (below), then from the sandbox: health 200, approve/confirm 403.
6. OpenClaw hooks (once, in the sandbox `openclaw.json`; then `nemoclaw <name> gateway restart`):
   `hooks: {enabled: true, token: "<new random>", path: "/hooks", allowedAgentIds: ["main"], allowRequestSessionKey: false}`. Token distinct from `gateway.auth.token`; keep it out of docs (store beside the worker env file). Verify: curl the hook → `200 {"ok":true,"runId":…}`; `openclaw logs --follow` shows `hook agent run completed`. **Unverified.**

## Parameters

| Name | Value | Source |
| --- | --- | --- |
| Worker port | 8100 | 00 |
| MCP long-poll | ≤ 50 s | OpenClaw `mcp.servers.spark-md-worker.requestTimeoutMs = 60000` (set in C5) |
| Real job time | ~10–20 s/study (detection ~7 s GB10 + meshes ~3 s) | 04, so fits the long-poll |
| Hook admission | answers ≤ 15 s (admission, not completion); 503 if not admitted | OpenClaw docs `automation/cron-jobs.md` |
| Hook body limit | 256 KiB | OpenClaw `gateway/configuration-reference.md#hooks` |
| SSE keepalive | 15 s | rehearsal |
| Growth | `growth_per_12mo` (absolute ≤ 12 mo, 12-month rate beyond) | 05, Ty Oct 25 |

## Gotchas

- **Intake (03):** the real watcher and `studies`/`series` columns (`rank`, `day_offset_source`, `failure_reason`, `fallback`) are not in the rehearsal; the trigger fires on `organized`, not on `received`. A null `day_offset` means no interval, growth or VDT.
- **Fixtures with a pre-set `status`** (e.g. `analyzed`) but no nodules make `analyze` return "done" with empty findings. Seed every study as `received`.
- **Baseline "new" bug** (above): fixed by checking for an earlier exam.
- **Hook `sessionKey`**: a request `sessionKey` returns 400 unless `hooks.allowRequestSessionKey: true` + `allowedSessionKeyPrefixes`, and only reuses context with `sessionMode: "persistent"` (docs). Default is isolated (fresh `hook:<uuid>` session ⇒ ~30 s cold prefill per run, 07). Answers part of 07's "warm session" question on paper; still unverified in practice.
- **Eager skill**: in the C5 rerun, "Look up study X" made OpenClaw run the entire triage chain. With two-phase triage, the phase-1 skill must stop after `log_event` (07).
- **CIFS**: `uv venv` on the project mount fails (no symlinks). Keep venvs in `~`.
- **nohup + Python stdout**: runner logs stay empty until exit; use `python3 -u` for live progress.
- Rehearsal deviations from 00 v0.6 (build to 00, not to these): confirm route was study-scoped `/api/studies/{uid}/nodules/{nid}/confirm`; no `awaiting_confirmation` status (used `analyzed` + `measurement_status: pending_confirmation|confirmed|not_analyzed` in findings — worth keeping as a field alongside 00's status).

## Acceptance tests

Rehearsal contract test (stdlib, against a live worker, loopback, fake 2 s jobs) — **27/27 pass on laptop and spark-2, Oct 25**. Recreate these checks:

| # | Check | Expected |
| --- | --- | --- |
| 1 | `/api/health`; `POST /api/demo/reset` | 200 |
| 2 | MCP `initialize` / notification / `tools/list` / `GET` / `DELETE` | 200 + `Mcp-Session-Id` / 202 / 9 tools, none named `*approv*` or `*confirm*` / 405 / 204 |
| 3 | `run_analysis` before `select_series`; ineligible series; eligible series | error "select a series first" / 422 "ineligible: sharp kernel" / 200 |
| 4 | REST analyze + MCP `run_analysis` concurrently | same `job_id`, both return `state: done`, `study_status: awaiting_confirmation` after ~2 s (00 v0.8) |
| 5 | agent `get_findings` before confirm | `pending_confirmation`, no `proposal`, no sizes, `assessment: null` |
| 6 | UI `GET …/findings`; same with `X-SparkMD-Caller: agent` | has `proposal` / no `proposal` |
| 7 | approve before confirm | 409 |
| 8 | confirm / approve with `X-SparkMD-Caller: agent` | 403 / 403 |
| 9 | confirm T0 `{11.0, 9.0}` | mean 10.0, `edited: true`, assessment from 05 (4A S-BASE-8-15) |
| 10 | confirm T1 (proposal 14×14) | prior = confirmed T0 (10.0), Δ 4.0, interval 371 d; assessment `rules_version: lungrads-v2022` |
| 11 | SSE subscriber, then approve letter from UI | 200; `outbox_delivered` < 1 s; outbox has 1 row |
| 12 | `agent_events` | MCP tool calls and agent REST calls auto-logged |
| 13 | `demo/drop` twice | 200 + trigger event / 409 |

From the sandbox (spark-2, Oct 25): `GET /api/health` via `10.77.0.1` → 200, worker logs client `172.18.0.2`; `POST …/approve` → 403 at the policy (never reaches the worker). Still to run: phase-1/phase-2 triage (07), C5 triage ×5 against this worker, hook trigger, 90 s fake job vs 60 s MCP timeout.

## Measured performance

- Contract test end to end: a few seconds (dominated by two 2 s fake jobs); SSE latency < 1 s (laptop and spark-2, Oct 25).
- OpenClaw via this worker (spark-2, Oct 25): ~20 s from MCP `initialize` to first tool call (fresh-session prefill); full 9-call triage chain 43 s after the first call; ~2 min per C5 scenario including session reset.

## Snippets

MCP `tools/call` over the shared tool layer (the rest of the handler is in 00/07: initialize, 202 for notifications, ping, tools/list):

```python
if method == "tools/call":
    p = msg.get("params", {})
    name, args = p.get("name"), dict(p.get("arguments") or {})
    try:
        obj, code = await call_tool(name, args)        # same function REST uses
    except Exception as e:
        obj, code = {"error": f"{type(e).__name__}: {e}"}, 500
    agent_event("tool_call", f"{name} -> {code}", args.get("study_uid"), {"args": args})
    return 200, {"jsonrpc": "2.0", "id": rid, "result": {
        "content": [{"type": "text", "text": json.dumps(obj)}], "isError": code >= 400}}
```

SSE fan-out from worker threads:

```python
def emit(event, data):
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    for qu in list(SUBSCRIBERS):            # one asyncio.Queue per /api/events client
        LOOP.call_soon_threadsafe(qu.put_nowait, msg)
```

## Open / unverified

- ~~Growth window~~ **decided Oct 25:** rate-normalize intervals > 12 months (05 `growth_per_12mo`). Fixture T1 (+4.0 mm / 371 d) → 3.9 mm/12 mo → 4B. Test 10 in the table above expected 4A under the old strict rule; on rebuild it should give 4B.
- **Pre-confirmation drafting:** 07/00 v0.6 say phase 1 writes no report. The rehearsal let the agent draft "pending confirmation"; follow 00 unless Ty changes it.
- Hook trigger end to end; C5 ×5 triage score on this worker; job longer than the MCP timeout; event-box bind (`10.77.0.1` + UI loopback).
