# 00: Architecture and v0 contract

Status: **v0.8, the build contract for Oct 25** (Ty, ~10:15; first drafted Oct 24 before the MVP). The MVP validates or changes every item. Whoever changes it adds a line to the change log.
Change log:
- v0 (Oct 24): initial contract from the brief + the morning survey (`docs/plans/2026-10-24-prep-day-plan.md` F1–F11).
- v0.1 (Oct 24, 13:15): the harness is no longer fixed to OpenClaw (F12). Tools are exposed as MCP on the worker (`/mcp`) so any harness can use them. The trigger and Q&A endpoints depend on the harness.
- v0.2 (Oct 24, C-track): policy preset syntax replaced with the validated `openshell policy update` form (rules need `--binary`). LLM binds `0.0.0.0:8000` (sandbox reaches it as `host.openshell.internal` → bridge `172.18.0.1`; host clients keep `127.0.0.1`). Worker address may be `10.77.0.1` (spark0, needs sudo) or docker0 `172.17.0.1` (zero-sudo, also cable-pull-proof). Details: `07-agent.md`.
- v0.3 (Oct 24, UI MVP / L7): UI-facing shapes pinned in `08-ui.md` §Interfaces: SSE frame format + all 8 payloads, `/api/ask` stream format (our own `delta`/`tool`/`done`/`error` SSE frames, harness-agnostic), approve responses (200 / 409 already approved / 403 not loopback), job stage list, worklist row fields (`lung_rads`, `reports_awaiting`), `key_slices[]` as objects, `placeholder` flag on findings. New UI route `GET /api/agent-log?study_uid=&limit=` (history for the log panel). Mock-only: `POST /api/demo/replay`. Later (17:20): demo harness `GET /api/demo/state` + SSE `demo_state {replaying, patient_id, timepoint, speed}` (replay banner, "2×" honesty badge); optional `extras.vertebra.flag` (worker rule text; the UI never derives it). Suggested, not yet adopted: `nodule.prior.{nodule_id, timepoint, day_offset, key_slice}`, `AgentEvent.patient_id` (08 §Open).
- v0.4 (Oct 24, voice / L8): `POST /api/asr` takes `audio/wav` 16 kHz mono s16 (the box has no ffmpeg) and returns `{text, command, phrase, score}` with `command` ∈ `show_nodule|compare_prior|why_flag|reset_view|null`. New optional `POST /api/tts {text}` → streamed 24 kHz s16 PCM. New loopback-only ports: whisper.cpp `whisper-server` `127.0.0.1:8178`, TTS container `127.0.0.1:8020`. Memory: ASR ≈ 1.2 GB, TTS ≈ 5.4 GB GPU (optional). Proposed (Ty to decide): matched viewer commands also emit `viewer_command` directly, without waiting for the agent. Details: `09-voice.md`.

- v0.5 (Oct 24, Ty confirmed voice): whisper.cpp default; faster-whisper/base.en retained for comparison/fallback. Spoken answers included (aiden, synthetic voice label). `/api/ask` immediately emits deterministic viewer actions for the three canonical viewer phrases before forwarding to the agent; log and suppress duplicate tool actions within the same request. `/api/asr` remains recognition-only. Ty brings a plug-in speaker/microphone. Details: `09-voice.md`.
- v0.6 (Oct 25, **adopted** — Ty, ~10:15; 04/05/07/08 updated Oct 25, 06 rehearsed against it): radiologist-confirmed diameters (AGENTS.md decision, Oct 24 22:55). A7 gives a *proposal* (diameter + mask); the radiologist confirms or edits each nodule's diameter in the UI; only then does code compute growth, VDT and the Lung-RADS category. Changes: new study status `awaiting_confirmation`; `nodules` gets proposal + confirmation columns, and `long_mm`/`short_mm`/`mean_mm`/`volume_mm3` hold **confirmed values only** (null until confirmed); new `POST /api/nodules/{id}/confirm` (**UI only**, loopback, not in the sandbox allow-list); `assessment` is null until every nodule on the study is confirmed; the worker re-triggers the agent when the study reaches `analyzed`. Refinements from the 06 rehearsal (build to these): the agent's `get_findings` omits `proposal` and all sizes until confirmed (UI callers see them); `mean_mm = round((long_mm+short_mm)/2, 1)`; approve returns 409 while any nodule is unconfirmed; the `new` flag for 05 is false on a baseline exam. Follow-ups still open: 11 (invariants), storyboard.
- v0.7 (Oct 25, **build to it** — Ty, ~10:15; written by the 03/10/11/12 pass): (1) intake columns from `03-intake-registry.md`: `studies` gains `study_date`, `rank`, `day_offset_source`, `inbox_path`, `failure_reason`; `series` gains `modality`, `series_number`, `kernel_list`, `axial`, `path`, `eligible_reason`, `fallback`; agent trigger fires on `organized`, not `received`; null `day_offset` = no interval, growth or VDT. (2) New dirs `backlog/` and file `day_offsets.csv`. (3) Growth over intervals > 12 months is rate-normalized (`growth_per_12mo`, AGENTS.md Oct 25 decision, `05`). (4) Demo harness (`10-demo-harness.md`): new `POST /api/demo/replay`, `POST /api/demo/stop`, `GET /api/demo/state`; SSE `demo_state` gains `mode` (`live`\|`cached`), `waiting_for` (`null`\|`confirm`\|`agent`\|`approve`) and `phase`; `net_stats` counts physical interfaces only (`/sys/class/net/<if>/device`). The harness never confirms or approves; auto-confirm is a dry-run aid, refused when `SPARKMD_RECORDING=1`. Build to 06/03/10 where they are more specific.
- **v0.8 (Oct 25, ~10:15, Ty; contract addendum from the pre-build consistency check of 00 vs 03/05/06/08). Where specs disagree, this wins:** (1) **Approve 409 has two meanings:** already approved → 409 `{report, outbox_id, already_approved:true}` (UI success state); unconfirmed nodules → 409 `{error:"confirm_all_first", already_approved:false}`, no `report` (UI shows the error). The UI treats 409 as success **only** when `already_approved === true`. (2) **Confirm:** the UI edits `long_mm` **and** `short_mm` (both prefilled from `proposal`), shows the worker's computed mean, and sends `{long_mm, short_mm, by}`; the worker computes `mean_mm = round((long+short)/2, 1)`, requires `0 < short ≤ long ≤ 100`, and uses `short = long` when there is no proposal and no short. (3) **Bind from env:** Mac dev `127.0.0.1`; event box `0.0.0.0` with external interfaces firewalled (one uvicorn can't take two `--host`s). The UI always uses `127.0.0.1:8100`, never `10.77.0.1` (that address is the agent's and gets 403 on confirm/approve). (4) **Analyze:** `state` stays the job state `queued|running|done|failed` (08); the analyze / `run_analysis` response adds `study_status`, which is `awaiting_confirmation` once proposals are ready. (5) **`GET /api/agent-log?study_uid=&limit=`** is the history route (not `/api/agent-events`) and is not cut; the UI needs it. (6) Every study status change emits `study_updated` **and** `worklist_changed {reason:"status"}`. (7) The agent trigger fires on `organized` (confirms v0.7). (8) **Growth always uses `growth_per_12mo`** (05 §Growth); findings carry `prior.growth_per_12mo_mm` and `prior.growth_normalized` (bool) for the UI label. Minor: the worker maps 05's `assess()` `driver` → `driver_nodule_id` and adds `rules_version`; trigger env vars are `SPARKMD_HOOK_URL` / `SPARKMD_HOOK_TOKEN` (06); `SPARKMD_UI_TOKEN` stays unset. Specs 05/06/08 fixed to match.
- **v0.8 additive clarification (Oct 25, W, requested by Ty):** UI findings include nullable `nodules[].proposal.reason`, mapped from imaging's per-nodule `proposal_reason` audit field. Failed proposals keep null proposed diameters plus the failure reason so the radiologist can enter a diameter; if no reason was supplied, the worker says `proposal_reason_unavailable`. Successful proposals use `reason: null`. Like the rest of `proposal`, this field is UI-only and omitted from agent REST/MCP findings. Mac synthetic A7 failure → UI reason → manual-diameter confirmation smoke passed Oct 25; GB10 validation remains unverified.

## Processes (one box, offline)

```
 inbox/ (mock PACS drop)
    │ poll
    ▼
 ┌─ imaging-worker (host, Python, FastAPI) ── binds 127.0.0.1:8100 + 10.77.0.1:8100 ──────────┐
 │  intake watcher → registry.sqlite → job runner (MONAI detector, VISTA-3D, rules, meshes)   │
 │  serves UI static + /api + SSE /api/events                                                 │
 └──────▲──────────────────────────┬──────────────────────────────▲───────────────────────────┘
        │ tool calls: MCP /mcp      │ agent trigger (new study)      │ browser on the box (UI, push-to-talk)
        │ or REST (OpenShell        │ Q&A proxy (/api/ask)           │ via 127.0.0.1:8100
        │ enforce preset)           │                                │
 ┌──────┴───────────────────────────▼─────────┐
 │ OpenShell sandbox:                          │
 │ agent harness (bake-off: OpenClaw / Hermes  │
 │ via NemoClaw, or a custom loop) + skill(s)  │
 └──────┬──────────────────────────────────────┘
        │ inference (NemoClaw route for OpenClaw/Hermes; mechanism: verify in Track C)
        ▼
 LLM server 127.0.0.1:8000 (Qwen3.8-27B, recipe from Track A)
```

| Process | Runs | Binds | Started by |
| --- | --- | --- | --- |
| LLM server | Docker on host (recipe image) | `0.0.0.0:8000` (host clients use `127.0.0.1:8000`; the sandbox uses `host.openshell.internal:8000` → bridge `172.18.0.1`) | recipe start script (02) |
| imaging-worker | host venv `~/.venvs/spark-md` | `0.0.0.0:8100` with external interfaces firewalled, so it answers on `127.0.0.1` (UI) and `10.77.0.1` (sandbox); bind address from env (v0.8) | `uvicorn` (06) |
| OpenShell gateway + sandbox + harness | Docker (OpenShell; NemoClaw for OpenClaw/Hermes) | OpenClaw gateway `:18789`; Hermes API `:8642` + dashboard `:18789`; forwarded to the host | `nemoclaw` / `nemohermes` / `openshell` (07) |
| Browser | host desktop | — | UI at `http://127.0.0.1:8100/` |

**Why two worker addresses:** the sandbox can't reach loopback (OpenShell never authorizes it), so it uses `10.77.0.1`, a dummy interface `spark0` that also survives the cable pull. The browser uses `127.0.0.1`. **Approve is accepted only on `127.0.0.1`**, so the sandbox can never approve.

## Memory budget (TensorFold default; capacity checked Oct 24 on spark-2)

GB10 is marketed as 128 GB unified; Linux on spark-2 reports 121.69 GiB. Use host `MemAvailable` for whole-box headroom, not process RSS or a sum of GPU reports.

| Consumer | Budget / evidence |
| --- | --- |
| TensorFold | ~36 GiB measured A0; **`KV_POOL_GB=16`**, `PARALLEL=4 CONTEXT=65536`. Default ~97 GiB footprint is unsuitable. |
| OS, desktop, OpenShell/OpenClaw, existing services | Included in measured baseline: 69.19 GiB available with TensorFold running. |
| Imaging | **≤25 GiB** target, models sequential with intermediates released; a touched 25 GiB CUDA allocation stood in for imaging in the capacity probe. Actual full-pipeline peak remains **unverified**. |
| ASR + TTS, host + GPU combined | **9 GiB allowance**; warm stack reduced available memory by ~7.6 GiB (small.en + VAD, Qwen3-TTS 1.7B-Base). TTS included in scope. |
| Final Electron UI, worker buffers, recording beyond baseline | **8 GiB additional allowance, unverified**. |
| **Floor** | `MemAvailable` ≥ **15 GiB** at all times. |

Measured minimum: **36.84 GiB available** with voice warm-up, 25 GiB CUDA reservation and concurrent LLM/ASR/TTS requests; **21.84 GiB above the floor**. After subtracting the additional unverified 8 GiB app/recording allowance: ~28.84 GiB available. Capacity fits; the full imaging/UI/recording workload still needs final acceptance. Method/raw evidence: `docs/benchmarks/2026-10-24-voice-headroom.md`. This result applies to TensorFold, not the alternative SGLang recipe. Memory capacity does not remove TTS compute contention: speak while the shared LLM is idle (09).

## Directories and env

`$SPARKMD_HOME` (default `/srv/spark-md`):

```
inbox/                          drop zone (one dir per study; stable for 5 s = complete)
backlog/<patient>/T0|T1|T2/     demo source studies for replay (10); `demo/drop` ingests from here
day_offsets.csv                 patient_id,rank,day_offset (NLST scr_days; 03)
studies/<StudyUID>/<SeriesUID>/ organized DICOM (moved from inbox)
cache/<SeriesUID>/              volume.nii.gz, lung/lobe masks, candidates.json, nodules.json,
                                meshes/*.glb, slices/*.png   (keyed by SeriesUID; reruns reuse it)
registry.sqlite
outbox/                         approved letters (JSON + HTML) = the mock EHR inbox
logs/
```

Env: `SPARKMD_HOME`, `SPARKMD_PORT=8100`, `SPARKMD_SANDBOX_ADDR=10.77.0.1`, `SPARKMD_LLM_URL=http://127.0.0.1:8000/v1`, `SPARKMD_MODELS=<path to models/>`, `SPARKMD_HOOK_URL` (the harness trigger endpoint), `SPARKMD_HOOK_TOKEN` (secret; lives in `$SPARKMD_HOME/.env`, never in docs; names per 06, v0.8), `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `NEMOCLAW_DISABLE_TELEMETRY=1`.

## Registry (SQLite), v0

| Table | Key columns |
| --- | --- |
| `patients` | `patient_id` PK, `cohort` (nlst_hero / nlst_ctrl / nlst_negnegpos / lidc), `sex`, `birth_year` |
| `studies` | `study_uid` PK, `patient_id`, `study_date` (raw, order only), `rank`, `timepoint` (T0/T1/T2 = rank), `day_offset` (NLST `scr_days*` via `day_offsets.csv`; StudyDate is fake; null = unknown), `day_offset_source` (sidecar / none), `inbox_path`, `failure_reason`, `status` (received → organized → analyzing → awaiting_confirmation → analyzed → reported → approved; or failed), `priority` (routine / elevated / urgent), `priority_reason`, `received_at` |
| `series` | `series_uid` PK, `study_uid`, `modality`, `series_number`, `kernel`, `kernel_list`, `slice_thickness`, `n_instances`, `image_type`, `axial`, `path`, `eligible` (0/1), `eligible_reason`, `fallback` (sharp-kernel only-eligible series), `selected` (0/1), `select_reason` |
| `nodules` | `nodule_id` PK, `study_uid`, `series_uid`, `track_id`, `lobe`, `center_mm` (RAS, JSON), `long_mm`, `short_mm`, `mean_mm`, `volume_mm3` (**confirmed values; null until confirmed**), `proposed_long_mm`, `proposed_short_mm`, `proposed_mean_mm`, `proposal_source` (e.g. `A7`), `box_mean_mm` (detector-box diameter, evidence for the reviewer), `confirmed_by`, `confirmed_at`, `edited` (0/1: radiologist changed the proposal), `mean_hu`, `type` (solid / part_solid / ggo), `det_score` |
| `tracks` | `track_id` PK, `patient_id`, `first_study_uid` |
| `assessments` | `study_uid` PK, `lung_rads`, `rule_id`, `driver_nodule_id`, `management`, `growth_json`, `rules_version` |
| `extras` | `study_uid` PK, `emphysema_pct`, `vertebra_label`, `vertebra_hu`, `cac_json` (experimental) |
| `reports` | `report_id` PK, `study_uid`, `kind` (radiology / pcp_letter), `markdown`, `version`, `status` (draft / approved), `approved_by`, `approved_at` |
| `agent_events` | `id`, `ts`, `study_uid`, `source` (tool_call / agent_note / system), `message`, `payload_json` |
| `outbox` | `id`, `ts`, `report_id`, `recipient`, `payload_json` |

## Findings payload (`GET /api/studies/{uid}/findings`), shape only

**The values below are placeholders, not measurements.** Before confirmation: measured fields and `prior.*` deltas are null and `assessment` is null. After every nodule is confirmed, the worker computes them and `assessment` takes the shape shown under `_assessment_after_confirmation` (that key is shape-only; the real key is `assessment`). `proposal.*` stays for audit.

```json
{
  "study_uid": "…", "patient_id": "134503", "timepoint": "T1", "day_offset": 380,
  "series_uid": "…", "pipeline_version": "0.1.0",
  "lung": {"mask_source": "vista3d|threshold", "volume_ml": 0},
  "nodules": [{
    "nodule_id": "…", "track_id": "T1", "lobe": "LUL (lingula)", "center_mm": [0, 0, 0],
    "det_score": 0.0, "long_mm": null, "short_mm": null, "mean_mm": null, "volume_mm3": null,
    "proposal": {"source": "A7", "long_mm": 0.0, "short_mm": 0.0, "mean_mm": 0.0, "box_mean_mm": 0.0, "reason": null},
    "confirmation": {"confirmed": false, "edited": false, "by": null, "at": null},
    "mean_hu": 0, "type": "solid",
    "prior": {"study_uid": "…", "interval_days": 0, "mean_mm": 0.0, "volume_mm3": 0,
              "delta_mean_mm": 0.0, "growth_per_12mo_mm": 0.0, "growth_normalized": false,
              "vdt_days": 0, "growing": true}
  }],
  "pending_confirmation": ["<nodule_id>"],
  "assessment": null,
  "_assessment_after_confirmation": {"lung_rads": "4B", "rule_id": "…", "driver_nodule_id": "…",
                 "management": "…", "rules_version": "lungrads-v2022"},
  "extras": {"emphysema_laa950_pct": 0.0, "vertebra": {"label": "T12", "mean_hu": 0},
             "cac": {"experimental": true}},
  "assets": {"lung_mesh": "/api/studies/…/assets/lung.glb", "nodule_mesh": "…", "key_slices": ["…"]}
}
```

## Worker API, v0

| Method + path | Caller | Purpose |
| --- | --- | --- |
| `GET /api/health` | all | liveness + versions |
| `GET /api/worklist` | agent, UI | studies sorted by priority, then Lung-RADS, then received time |
| `GET /api/studies/{uid}` | agent, UI | study + series header summary + eligibility + prior studies |
| `POST /api/studies/{uid}/select-series` `{series_uid, reason}` | agent | rejects ineligible series (localizer, sharp kernel, thick slices) |
| `POST /api/studies/{uid}/analyze` `{wait_s≤300}` | agent | starts or joins the job; long-polls; returns `{job_id, state, stage, elapsed_s, study_status}` (`state` = job state; `study_status` = `awaiting_confirmation` once proposals are ready, v0.8) |
| `GET /api/jobs/{job_id}` | agent, UI | job progress (stages from 04) |
| `GET /api/studies/{uid}/findings` | agent, UI | the payload above (nodules + priors + assessment + extras + assets) |
| `GET /api/studies/{uid}/assets/{name}` | UI | `.glb` meshes, `.png` key slices |
| `POST /api/studies/{uid}/reports` `{kind, markdown}` | agent | saves a draft (new version) |
| `GET /api/studies/{uid}/reports` | UI | drafts + approved |
| `POST /api/nodules/{id}/confirm` `{long_mm, short_mm, by}` | **UI only** | accepted only from `127.0.0.1`; the UI sends both diameters (prefilled from the proposal); `mean_mm = round((long+short)/2, 1)`, requires `0 < short ≤ long ≤ 100`, `short = long` when there is no proposal and no short (v0.8). Stores the confirmed diameter (`edited` = differs from proposal), recomputes volume/growth/VDT/assessment by code once all nodules on the study are confirmed, moves the study to `analyzed`, emits SSE `study_updated` + `worklist_changed`, re-triggers the agent for the report drafts. Not in the sandbox allow-list; no agent tool |
| `POST /api/reports/{id}/approve` `{approver}` | **UI only** | accepted only from `127.0.0.1`; writes the outbox; denied by policy for the sandbox. 200 `{report, outbox_id, already_approved:false}`; 409 `{…, already_approved:true}` = already approved (success); 409 `{error:"confirm_all_first", already_approved:false}` = nodules unconfirmed; 403 not loopback (v0.8) |
| `GET /api/agent-log?study_uid=&limit=` | UI | agent-log history for the log panel (not cut, v0.8) |
| `POST /api/studies/{uid}/priority` `{priority, reason}` | agent | worklist move |
| `POST /api/viewer/command` `{command, study_uid, nodule_id?}` | agent | `show_nodule`, `compare_prior`, `reset_view`, `show_extras` → SSE |
| `POST /api/agent-log` `{study_uid?, message}` | agent | narrative lines for the visible log |
| `GET /api/events` (SSE) | UI | `agent_log`, `worklist_changed`, `study_updated`, `job_progress`, `viewer_command`, `report_saved`, `outbox_delivered`, `net_stats`, `demo_state` |
| `POST /mcp` (streamable HTTP) | agent | the agent tools below as MCP tools; each is a thin wrapper over its REST route |
| `POST /api/ask` `{study_uid, text}` | UI | proxies to the harness's chat/API endpoint (one session per study) and streams the answer |
| `POST /api/asr` (audio) | UI | `{text, command, score}` |
| `GET /api/outbox` | UI | the mock EHR inbox |
| `GET /api/netstats` | UI | bytes TX on external interfaces since reset ("0 bytes sent") |
| `POST /api/demo/reset`, `POST /api/demo/drop` `{patient_id, timepoint}` | demo harness (loopback only) | time machine; drop ingests `backlog/<patient>/<timepoint>/` (03, 06) |
| `POST /api/demo/replay` `{patient_id, timepoints?, mode?, speed?, gap_s?}`, `POST /api/demo/stop`, `GET /api/demo/state` | demo harness (loopback only) | orchestrator that drops each timepoint and waits for human confirm/approve (10) |

**Agent-call logging:** the plugin sends `X-SparkMD-Caller: agent` and a run id. The worker writes **every** agent request to `agent_events` automatically, so the on-screen log is real and not narrated after the fact.

## Agent tools, v0 (harness-agnostic)

The worker serves these as **MCP tools at `/mcp`**, so OpenClaw (`mcp.servers`) and Hermes (MCP) bind the same set without code changes. Alternatives: OpenClaw can use a `defineToolPlugin` plugin, and a custom loop maps them to OpenAI `tools` → REST. Each tool is a thin wrapper with no logic:

| Tool | → API |
| --- | --- |
| `list_studies(status?)` | `GET /api/worklist` |
| `get_study(study_uid)` | `GET /api/studies/{uid}` |
| `select_series(study_uid, series_uid, reason)` | `POST …/select-series` |
| `run_analysis(study_uid)` | `POST …/analyze` (long-poll; `study_status` = `awaiting_confirmation` when proposals are ready) |
| `get_findings(study_uid)` | `GET …/findings` |
| `save_report(study_uid, kind, markdown)` | `POST …/reports` |
| `set_priority(study_uid, priority, reason)` | `POST …/priority` |
| `viewer_command(command, study_uid, nodule_id?)` | `POST /api/viewer/command` |
| `log_event(study_uid, message)` | `POST /api/agent-log` |

There is no approve tool and no confirm tool: the agent never proposes, edits or confirms a diameter. Disable the harness's own file, shell, web and messaging tools, using its most restrictive tool profile (OpenClaw: `tools.profile` + `tools.allow`; Hermes: `hermes tools`).

## Flows

1. **New study (trigger):** a study lands in the inbox. The watcher waits until it's stable, parses headers, writes the registry (`received`), organizes it (`organized`), emits SSE, and triggers the agent once the study is `organized` (v0.7/v0.8). OpenClaw: `POST /hooks/agent` (`deliver:false`, `Idempotency-Key: study-<uid>`). Hermes: its API on `:8642`. Custom loop: its own endpoint. The agent then runs the triage skill: `get_study` → `select_series` → `run_analysis` → (stops at `awaiting_confirmation`; narrates in the log; the radiologist confirms diameters in the UI; the worker re-triggers with `Idempotency-Key: study-<uid>-confirmed`) → `get_findings` → `log_event`… → `save_report(radiology)` → `save_report(pcp_letter)` → `set_priority` (if elevated) → `log_event` (summary).
2. **Talk to the scan:** push-to-talk → `/api/asr` → canonical phrase → `/api/ask {study_uid, text}` → worker immediately emits/logs the matched viewer action, then forwards to the agent with the action already completed. Suppress duplicate viewer calls within this request (09). The agent calls `get_findings` for explanations; every number comes from findings. Text streams to the UI; after `done` and while the LLM is idle, `/api/tts` speaks the answer in aiden's synthetic voice. Push-to-talk stops current playback.
3. **Approve:** the radiologist clicks Approve → `POST /api/reports/{id}/approve` on `127.0.0.1` → status `approved` → `outbox/` → SSE `outbox_delivered` → the letter appears in the mock EHR inbox.
4. **Time machine:** the replay orchestrator drops T0, waits for the radiologist to confirm its diameters (and the agent's drafts), then drops T1 (and T2); it never confirms or approves (`10-demo-harness.md`). The agent log stays on screen throughout.

Draft voice phrases (Joyce finalizes them in 09): "Show me the nodule" · "Compare it to last year" · "Why did you flag this?" · "Reset the view". Approval is **click only**.

## Sandbox policy preset (validated on spark-2, Oct 24; full detail in `07-agent.md`)

```bash
# NEMOCLAW_DISABLE_TELEMETRY=1 in every shell. Applied after onboard:
openshell policy update spark-md-openclaw \
  --add-endpoint 10.77.0.1:8100:read-write:rest:enforce \
  --binary /usr/bin/curl --binary /usr/local/bin/node --binary /usr/local/bin/openclaw \
  --add-allow '10.77.0.1:8100:GET:/api/**' \
  --add-allow '10.77.0.1:8100:POST:/api/studies/*/select-series' \
  --add-allow '10.77.0.1:8100:POST:/api/studies/*/analyze' \
  --add-allow '10.77.0.1:8100:POST:/api/studies/*/reports' \
  --add-allow '10.77.0.1:8100:POST:/api/studies/*/priority' \
  --add-allow '10.77.0.1:8100:POST:/api/viewer/command' \
  --add-allow '10.77.0.1:8100:POST:/api/agent-log' \
  --add-allow '10.77.0.1:8100:POST:/mcp' --wait
```

- Rules without `--binary` match nothing (even allowed routes 403). Bind curl (tests), node + openclaw (agent).
- An access preset (`read-write`) alone expands to broad `METHOD /**` rules; a later explicit update replaces them — verify the final rules with `policy get --full -o json`.
- Also remove OpenShell's cloud presets: `--remove-rule clawhub`, `npm_registry`, `nvidia`, `openclaw_api`, `openclaw_docs` (keep `_provider_*` and `managed_inference`: they are the LLM route).
- Inference does NOT go through this preset: the native vLLM provider preset allows only `host.openshell.internal:8000` for openclaw/node.
- Verified denials: POST approve → 403 `policy_denied`; internet and npm → blocked; denials visible via `openshell logs` (`denied_action_count` activity summaries).

## Invariants (tests in 11)

- The Lung-RADS category in any report equals `assessments.lung_rads` exactly, and `assessments` has no row for a study with unconfirmed nodules.
- No size, growth or category appears in agent text before confirmation; after it, every number is a confirmed value or a code-derived value from findings.
- The sandbox can't confirm: `POST /api/nodules/{id}/confirm` from inside the sandbox → 403 (policy) and from a non-loopback address → 403 (worker).
- Every number in agent-written text appears in that study's findings payload.
- The sandbox can't reach anything except the worker routes above. A test exfil (`curl https://example.com`, a POST to approve) is denied and visible in `openshell term`.
- The whole app works with the LAN interface down and wifi off.
- A cold restart (reboot → start script) returns to a working worklist with prior results intact.
