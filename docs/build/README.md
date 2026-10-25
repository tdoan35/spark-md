# Build specs

These specs let follow-up agents **recreate Spark MD from scratch on Oct 25**, back to front. Each one is written by the agent that built that layer of today's throwaway MVP, as soon as the layer works.

**Rule (hackathon):** specs carry interfaces, parameters, commands, gotchas, acceptance tests and short snippets (≤ ~30 lines) for the non-obvious parts. **No whole source files.** The MVP code is deleted tonight and never goes on the drive.

## Index (build order)

| # | Spec | Layer | Status |
| --- | --- | --- | --- |
| 00 | [architecture](00-architecture.md) | v0 contract: processes, ports, dirs, schema, API, tools, flows | draft v0.7 (confirm flow v0.6, intake and demo harness v0.7 proposed) |
| 01 | [box-setup](01-box-setup.md) | prereqs + iface (partial, C-track) | prereqs + E10 rebuild validated Oct 24; start/stop outline added Oct 25 (unverified); users, dirs, venv layout unwritten |
| 02 | [llm-serving](02-llm-serving.md) | winning recipe, exact command, memory settings, smoke tests, fallbacks | TensorFold validated Oct 24; SGLang fallback unbenched; event-box image load unverified |
| 03 | [intake-registry](03-intake-registry.md) | watched inbox, DICOM parsing, series selection, SQLite | draft; B1/B2 rules measured on 44 studies, watcher/registry code unwritten and unverified |
| 04 | [imaging-pipeline](04-imaging-pipeline.md) | transforms, detector, VISTA-3D, characterization, matching, extras, render | B1–B3 done; T0 wrong-target fallback invalidated, full-CT VISTA fails T0; cropped point-only VISTA fails LIDC reader/crop-stability test; no accepted measurements; B4/B8–B9 open; outputs are proposals pending radiologist confirmation (Oct 25) |
| 05 | [clinical-rules](05-clinical-rules.md) | Lung-RADS v2022 table, growth/VDT, extras thresholds, test vectors | **done Oct 24** — 41 vectors pass; inputs = confirmed diameters only (Oct 25) |
| 06 | [worker-api](06-worker-api.md) | FastAPI endpoints, MCP endpoint, SSE, agent trigger, agent-call log, approve guard | rehearsed Oct 25 — contract 27/27 laptop + spark-2; OpenClaw triage chain via it; hook trigger + C5 ×5 unverified |
| 07 | [agent](07-agent.md) | OpenShell + chosen harness install, tool binding (MCP/plugin), skill + prompt, trigger, policy | C1–C3 + C5 done (harness = OpenClaw); C4 dropped (demos fully local); two-phase confirm flow added Oct 25, unverified |
| 08 | [ui](08-ui.md) | Electron + React desktop app: shell, screens, three.js viewer, API usage, states | MVP done Oct 24; confirm-diameter panel specified Oct 25, not built |
| 09 | [voice](09-voice.md) | ASR model, push-to-talk, fixed phrases, matching, fallbacks, spoken answers | ASR + TTS validated on GB10 with synthetic voices (Oct 24); real voices + mic unverified |
| 10 | [demo-harness](10-demo-harness.md) | time-machine replay, reset, backlog seeding, network monitor | draft Oct 25; only the interface-counter source checked on spark-2; replay/state/seeding unverified |
| 11 | [acceptance](11-acceptance.md) | end-to-end QA, cold restart, contention | draft Oct 25; nothing run; runner and invariant checker unwritten |
| 12 | [day-of-runbook](12-day-of-runbook.md) | setup order, agent assignments + kickoff prompts, timeline, cut order | draft Oct 25; times are proposals |

## Spec template

Copy these headings into every `NN-*.md`:

```
# NN: <layer>
Status: draft | validated on GB10 (date) | unverified parts listed below
Rebuild budget on the day: <minutes>, by <which agent>

## Purpose and scope       what's in, what's out, what's cut first
## Interfaces              exact endpoints / JSON schemas / tables / files / env vars (consistent with 00)
## Dependencies            exact versions (wheelhouse lock, image digests, model files + SHA256)
## Build steps             ordered; each step ends with a verification command and its expected output
## Parameters              every threshold, label ID, window and constant, with its source
## Gotchas                 symptom → cause → fix, found in the MVP
## Acceptance tests        commands → expected results (these feed 11-acceptance)
## Measured performance    on GB10: time, memory, with method and date
## Snippets                only the non-obvious bits, ≤ ~30 lines each
## Open / unverified
```

## Writing rules

- Write for an agent with no context except `AGENTS.md`, `00-architecture.md` and this spec. Use exact names, paths and versions. Don't write "configure X appropriately".
- If you change the contract in 00, update 00 in the same edit and note the change at the top of 00.
- Mark anything not run on a GB10 as **unverified**.
