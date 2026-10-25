# 11: Acceptance

Status: **draft (Oct 25). Nothing in this spec has been run.** It collates the per-layer acceptance tables (02–10, 00 invariants) into one ordered pass and adds the end-to-end, cold-restart, contention and air-gap tests. Layer tests keep their own IDs and live in their own specs; this file points to them instead of copying them.
Rebuild budget on the day: ~60 min to write the runner and invariant checker (QA agent Q), then the runs themselves: ~15 min quick pass, ~45 min full pass including the 30-minute contention test. Estimates, unmeasured.

## Purpose and scope

Answers one question before the recording and again before submission: does the whole product do what the video claims, on the event box, with the cable out. In: run order, pass bars, the end-to-end scenarios (E1–E9), the invariant checker, cold restart, contention, air gap, Joyce's QA list. Out: unit-level tests (each layer spec), performance tuning.
Cut first: the full 30-minute contention run (shorten to 10), the TTS and slice-carousel checks.

## Run order

| Pass | When | What | Time |
| --- | --- | --- | --- |
| Smoke | after every integration | layer tables for 02, 06 (contract test), 07 policy checks, 03 I1–I3 | ~5 min |
| Quick | G3 and G5 (12) | smoke + E1–E6 + invariants V1–V8 | ~15 min |
| Full | 15:15 freeze (12, Oct 25 re-plan), and again after any fix; shorten contention to 10 min if needed | quick + E7–E9 + cold restart + contention + air gap | ~45 min |
| Final | ≤ 17:00, after the last commit, before upload (GB10 returned 17:30) | quick, on the submitted commit | ~15 min |

Record every run (date, commit, who, pass/fail per ID, raw output path) in `docs/benchmarks/2026-10-25-acceptance.md` using the AGENTS.md rule: each number gets its method and machine. A failure is written down, not rerun silently.

## Layer tests pulled in (by reference)

| Spec | Tests | Notes |
| --- | --- | --- |
| 02 | Up, sandbox route, tools 10/10, grounding, memory, restart | `bench/tf_smoke.py` is a prep script; rewrite or reuse as the event repo's smoke |
| 03 | I1–I8 | I1 over the full 44-study demo set |
| 05 | 41 vectors + worker-level tests (a–c) | engine must pass before anything else |
| 06 | contract test checks 1–13 | 27/27 was a rehearsal; rerun against the real worker |
| 07 | sandbox checks, two-phase transcript tests, C5 rerun ×5 | confirm blocked from the sandbox |
| 08 | the table in 08 §Acceptance, run on the real worker | the MVP numbers were against a mock |
| 09 | tests 1–7 | tests 5 and 6 were unverified |
| 10 | D1–D10 | D9 needs sudo at the console |

## End-to-end scenarios

All on the event box, real worker, real agent, real LLM, hero 134503 unless stated. "Human" = Ty or Joyce clicking.

| # | Scenario | Pass |
| --- | --- | --- |
| E1 | Cold start of the worker with an empty registry, drop T0 | within the target time (to be measured) the study reaches `awaiting_confirmation`; agent log shows phase 1 with no sizes |
| E2 | Human confirms T0's diameter (accept, then re-run with an edit) | assessment appears from 05; `edited` set only when changed; agent drafts radiology report + PCP letter; category in text equals `assessments.lung_rads` |
| E3 | Drop T1 | T1 shows "prior T0 unconfirmed" if T0 is unconfirmed; after confirming, growth and VDT computed from confirmed values (`growth_per_12mo` applied for 371 d); priority moves; worklist reorders |
| E4 | Talk to the scan: the four fixed phrases by chip, then by voice | viewer action before agent text; the answer's numbers all in the findings; five consecutive first-try successes per phrase |
| E5 | Extras beat | four rows; any experimental item labelled; no number without a worker source |
| E6 | Approve the PCP letter | only by UI click; letter in the outbox < 1 s; approving the radiology report first or second changes nothing unexpected; approve before confirm → 409 |
| E7 | Failure paths: bad DICOM, study with no eligible series, LLM stopped mid-triage, worker restarted mid-SSE | readable `failed` state or recovery within 5 s; no half-written report shown as final |
| E8 | A second patient (LIDC single study) and a control (NLST stable) | no priors, no growth; no hero-specific code paths; sensible worklist ordering |
| E9 | Full replay for the recording: `demo/replay` T0→T1 with Joyce clicking | timed; phases advance only on human actions; log visible; final wall time feeds the live/cached/"2×" decision (10) |

## Invariants (V1–V8, automated)

The checker (QA agent writes it; ~100 lines, stdlib) runs after E2/E3/E9 and in the final pass. It reads `registry.sqlite`, `agent_events` and the REST API, never the UI.

| # | Invariant | How |
| --- | --- | --- |
| V1 | Category in any report = `assessments.lung_rads` | regex the report text for `Lung-RADS\s*(\w+)`; compare |
| V2 | No `assessments` row, size, growth or category for a study with unconfirmed nodules; no such numbers in phase-1 agent text | query + scan `agent_events` before the confirm timestamp for `\d+(\.\d+)?\s*mm` and category tokens |
| V3 | Every number in agent-written text appears in that study's findings | extract numeric tokens from reports and agent notes; allowed set = numbers in the findings JSON at 0/1/2 decimals, mm↔cm conversions, dates/IDs from the study, plus a short whitelist (category digits, "12 months", years). Unlisted numbers fail and are printed for review |
| V4 | The sandbox cannot confirm or approve | `openshell sandbox exec … curl -XPOST …/confirm` and `…/approve` → 403 `policy_denied`; same from a non-loopback host → 403 from the worker |
| V5 | The sandbox reaches only the allowed worker routes and the LLM | exfil attempts (`https://example.com`, npm, an unlisted path) denied; denials visible in `openshell logs` |
| V6 | The UI makes no non-loopback request over a full flow | Electron CDP `Network.requestWillBeSent` log, as in the 08 MVP run (36–51 requests, 0 external); the main-process filter also counts blocked requests |
| V7 | Confirmed/approved rows carry a human `by` (not `demo-harness` when recording) | query `nodules.confirmed_by`, `reports.approved_by` |
| V8 | Cached results are labelled | any study run with `mode=cached` has the log line and the banner state (10) |

V3 is the weakest check (false positives on derived numbers). Treat a V3 failure as "review" until a person has looked; never loosen it silently.

## Cold restart

Start-all order (L0 `start` script, to be written in 01 on the day): `spark0` → LLM container → sandbox gateway (restart if needed) → worker → UI. Test: reboot, run the script, open the app.

| # | Check | Pass |
| --- | --- | --- |
| C1 | After reboot, ordered start with no manual fixes | worklist loads; time recorded (target ≤ 5 min, proposed) |
| C2 | Registry, cache and outbox survive | prior studies present; confirmed diameters and approved letters intact; `cache/` reused |
| C3 | Agent sessions are fresh | no stale session context; phase 1 still works (cold prefill ~30 s, 07) |
| C4 | SSE and UI reconnect | UI recovers < 5 s after a worker restart (08 measured 1.5 s on the mock) |
| C5 | Voice and TTS servers return | ASR answers on `:8178`, TTS on `:8020` or the UI shows the mute fallback |

Record which step needed a manual fix; those become `start` script lines.

## Contention (30 minutes, full app)

Goal: prove the memory budget holds with everything on. Method:
1. Baseline `free -g`, `nvidia-smi`, container list.
2. Loop for 30 min: replay hero T0→T1 (cached mode), one `ask` every 60 s, one ASR clip every 30 s, one TTS answer every 5 min, imaging job running continuously on a second study every ~5 min.
3. Sample `MemAvailable` every 5 s into JSONL; watchdog aborts the test and stops the imaging job if `MemAvailable < 15 GiB`.

Pass: min `MemAvailable ≥ 15 GiB` (budget in 00: 28.84 GiB expected after the 8 GiB unverified allowance), no OOM kill (`dmesg`), no container restart, 0 failed worker requests, LLM p95 TTFT noted. Fail: any freeze of the host; if that happens, power-cycle and reduce `KV_POOL_GB` or `PARALLEL` per 02.
Run only when no other GPU job is active. Do not run this at the same time as the recording.

## Air gap

| # | Check | Pass |
| --- | --- | --- |
| A1 | With the LAN cable out and wifi off, run E1–E6 | all pass |
| A2 | `netstats` over a full flow with the cable out | `link_up:false`; bytes since unplug reported as measured; a nonzero value is explained, not hidden |
| A3 | No outbound sockets from Spark MD processes | `ss -tnp` filtered to the worker, LLM, harness and UI PIDs shows loopback, bridge and `10.77.0.1` only (**method unverified**) |
| A4 | Offline env set | `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `NEMOCLAW_DISABLE_TELEMETRY` present in every service's environment; no `:latest` tags in `docker ps` |
| A5 | Fresh-user dry run still passes | E10's 8/8 (`scripts/e10_dry_run.sh`), 90 s, repeat only if the container or wheelhouse changed |

## Joyce's QA list (maps to the storyboard)

| Question | Test |
| --- | --- |
| Can a first-time viewer follow the time machine without narration? | watch one unnarrated replay with someone who hasn't seen it; list where they hesitate |
| Do all voice commands work first try, five in a row? | E4 and 09 test 1/3 |
| Does the "why" answer cite real numbers? | V3 on that answer |
| Does Approve reliably land the letter? | E6, five times (reset between) |
| Does the flow survive a cold restart? | Cold restart C1–C5 |
| New: is the confirm step understandable on camera? | E2/E3 with Joyce clicking |

## Pass bars for submission

Must pass: engine vectors, V1, V2, V4, V5, V6, V7, E1–E3, E6, cold restart C1–C2, A1. Should pass: V3 (reviewed), E4, E5, E9, contention. Anything failing is either fixed, cut from the video and writeup, or written down as a limitation. Nothing is claimed that a test did not pass.

## Gotchas (expected)

- Cached runs make E1/E9 look fast; always state the mode in the record.
- A warm agent session can hide a cold-start bug; run C3 from a fresh session.
- V3 must read the same findings payload the agent saw (agent view omits proposals before confirmation).
- A replay left running during the contention test inflates memory; stop it first.
- The UI e2e (CDP) runner from the MVP is throwaway; rebuild it from 08's description.

## Open / unverified

- The runner, invariant checker and start-all script do not exist.
- Target times (E1, C1) are placeholders until the first live runs.
- A3's `ss` method and the V3 whitelist need a first pass to tune.
- Whether the 30-minute contention test is affordable on the day; the cut is 10 minutes with the same pass bar.
- Test IDs from other specs may be renamed by their owners; this file lists them by spec, not by number, where possible.
