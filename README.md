# Spark MD

Spark MD is an always-on, fully air-gapped lung cancer screening assistant for a radiology team, running on a single Dell Pro Max with GB10 (aarch64, CUDA 13). It watches an intake folder that acts as a mock PACS, organizes incoming chest CTs into a per-patient registry, detects and tracks lung nodules across yearly screens, computes Lung-RADS v2022 categories in deterministic tested code, and drafts a radiology-style report plus a primary-care letter for a radiologist to confirm and approve. Patient data never leaves the box: no remote LLM or API calls, no CDNs, no telemetry, no browser speech services. Built in one day (Oct 25, 2026) for the Dell x NVIDIA AI Hackathon, San Francisco.

## Human-in-the-loop flow

Principle: deterministic code does the medical math; the LLM orchestrates and writes. The agent never proposes or edits a diameter and never assigns or changes a Lung-RADS category. Every number in agent-written text comes from a tool result.

1. **Intake** — a watched folder receives new studies (mock PACS).
2. **Organize** (agent) — parse DICOM headers, group by patient/study/series, pick the thin-slice lung series, write the SQLite registry.
3. **Detect** (code) — MONAI nodule detection; a rule-based segmenter (A7) proposes a diameter and mask per nodule. Proposals only.
4. **Confirm** (human) — the radiologist confirms or edits each diameter in the UI. Growth and Lung-RADS are computed only after confirmation.
5. **Score** (code) — Lung-RADS v2022 from size, type and growth (growth = >1.5 mm per 12 months; 4X is a category; volume doubling time is evidence-only, never a category driver).
6. **Draft** (agent) — report and PCP letter, written from tool results.
7. **Approve** (human) — only a person's click approves. The agent has no approve tool, the OpenShell policy does not allow the approve route, and the worker rejects approve requests from the sandbox (verified: 403).
8. **Deliver** — the approved letter lands in a mock EHR inbox.

## Architecture (one box)

| Component | What it does | Where |
| --- | --- | --- |
| LLM | Qwen3.8-27B served by TensorFold, OpenAI-compatible, served name `qwen3.8-27b`, ~36 GiB | `127.0.0.1:8000` (binds `0.0.0.0` so the sandbox reaches it as `host.openshell.internal:8000`) |
| Agent harness | OpenClaw managed by NemoClaw, inside an OpenShell sandbox (restricted tier). Sandbox egress is limited to the imaging worker's agent routes in `enforce` mode; loopback egress is never authorized | in the sandbox; OpenClaw forward on `127.0.0.1:18789` |
| Imaging worker | MONAI `lung_nodule_ct_detection` v0.5.9 detection, A7 diameter proposals, Lung-RADS v2022 rules engine (tested code), meshes and key slices; REST + MCP + SSE | host, outside the sandbox, on `10.77.0.1:8100` (dummy interface `spark0`; also `127.0.0.1:8100`) |
| UI | Electron + React + three.js served by the worker: worklist, study viewer (2D slices, 3D), agent log, research risk card, Approve, mock EHR inbox; optional local voice (whisper.cpp ASR, Qwen3-TTS) with chips/mute fallback | worker serves `ui/dist` on `:8100` |

The sandbox can reach only the worker's agent routes — not the registry, cache, outbox or the approve route.

## Running it

```
bin/sparkmd-start    # idempotent start-all: preflight -> spark0 -> firewall -> LLM -> sandbox -> worker -> voice -> UI
bin/sparkmd-status   # read-only checks, same table; exit code = number of FAIL lines
bin/sparkmd-stop     # reverse order; leaves spark0, the registry, cache/ and outbox/ alone
```

Both `start` and `stop` take `--only llm,sandbox,worker,asr,tts,ui` and `--dry-run`. Logs go to `~/logs/`. Preflight requires Docker usable by the current user and `MemAvailable` ≥ 15 GiB. The scripts set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and `NEMOCLAW_DISABLE_TELEMETRY=1`, and never use `:latest` image tags.

**Not in this repo** (staged on the box / external drive; required to run): `models/` (VISTA-3D NV-Segment-CT, MONAI detection bundle, whisper.cpp and TTS models), `data/` (NLST and LIDC-IDRI DICOM and clinical tables), `wheelhouse/` and `nodehouse/` (offline Python/npm packages), the TensorFold serving directory (`~/qwen38-27b-tensorfold`), a Python venv (default `~/.venvs/spark-md`), and a `.env` with the agent hook token. Defaults, all overridable via environment: runtime home `~/spark-md-runtime-w`, models at `~/spark-md/models`, worker on `:8100`, LLM on `:8000`. Per-layer specs and commands: `docs/build/`.

## What is validated

Measured Oct 24–25 on the prep DGX Spark; method, machine and raw data for each number are in `docs/benchmarks/`.

- **Lung-RADS v2022 engine:** 41 test vectors from the ACR table pass.
- **Growth rule:** 8 test suites pass (>1.5 mm per 12 months; see the interpretation note below for intervals ≠ 12 months).
- **A7 diameter proposals, as proposals:** held-out LIDC (15 patients, 31 nodules, rule frozen before download): median diameter error 0.51 mm unflagged vs 0.59 mm for radiologist readers, flag rate 19%. NLST stable-nodule cohort (30 patients): year-to-year change median 0.28 mm, false growth in 2/53 intervals (3.8%). Known weakness: ±3 mm detector-box shifts swing A7 by up to 1.8 mm, and the A7-vs-box flag caught 10/13 large errors pooled — the reason diameters are human-confirmed.
- **Detector:** on 5 NLST hero patients, the tracked nodule ranked top at all screens and all 5 heroes passed 15/15 checks at the ≤10 mm bar against NLST-reported sizes.
- **Agent + LLM:** OpenClaw via NemoClaw passed 20/20 tool scenarios and 5/5 end-to-end triage flows (~74 s median per study). TensorFold smoke: tool calls 10/10 (thinking off) and 9/10 (thinking on), ~40 tok/s prose, ~36 GiB footprint.
- **Sandbox policy:** `enforce`-mode denials verified; sandbox → worker on `10.77.0.1` verified; an approve request from the sandbox is rejected with 403.

## What is not validated

- **VISTA-3D nodule segmentation failed validation** and is not used for any size, growth, VDT or Lung-RADS input. Full-CT segmentation fails at the hero's first screen; the fixed 64 mm-crop variant passes coarse geometry checks but fails LIDC boundary/stability evaluation (median Dice 0.033–0.086 across crop sizes vs 0.78 median inter-reader agreement; hero volume spans 42–71% across crop sizes); annotation-assisted click prompting also failed. The imaging pipeline uses VISTA-3D only for the lung/lobe mask, with a CPU threshold fallback.
- **Diameters are radiologist-confirmed.** A7 output is a proposal, not an accepted measurement; a human confirms or edits each diameter in the UI before growth, VDT or Lung-RADS are computed.
- **Growth normalized to 12 months is our interpretation.** Lung-RADS Note 6 defines growth as >1.5 mm "within a 12-month interval"; NLST annual screens run ~12–13 months. For longer intervals, Spark MD rate-normalizes the change to a per-12-month value (short intervals are never scaled up). This is not ACR wording; the UI rule text labels it as our interpretation.
- **The Sybil risk card is precomputed, and its scores are not validation.** The 1–6-year risk numbers shown next to the Lung-RADS badge were computed offline on the GB10 (`scripts/sybil_precompute.py`, `fixtures/sybil_risk.json`) and rendered read-only. Sybil was trained on NLST, and the demo patients may be in its training set, so the scores are optimistic. The card never feeds Lung-RADS and the agent does not see it.
- **Unverified (not measured):** real microphone capture and speaker playback on the event device; OpenShell policy persistence across reboot; the full stack (LLM + agent + imaging + voice) loaded together on one box — measured headroom used touched reservations only; the complete acceptance pass in `docs/build/11-acceptance.md` — that spec was a draft and its run results are not recorded in these docs.

## Honesty

"Research demo, not for clinical use" is shown on screen. No clinical outcome is claimed beyond what the data supports; anything not measured is marked **unverified**. The agent log stays visible during time-travel replay. Recordings are of real runs; sped-up footage is labeled (e.g. "2×").

## Credits

Verbatim from `docs/build/12-day-of-runbook.md` §Submission checklist: NLST (TCIA, CC BY 4.0, doi:10.7937/TCIA.HMQ8-J677), LIDC-IDRI (CC BY 3.0, doi:10.7937/K9/TCIA.2015.LO9QL9SX + Armato 2011), IDC (Fedorov 2023), Lung-RADS v2022 (ACR).
