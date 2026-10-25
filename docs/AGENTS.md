# AGENTS.md — Spark MD

Read this first. Every agent working in this directory follows it. *Last updated: Sun Oct 25, 2026 ~09:55 (re-planned for the organizer schedule); prep on Sat Oct 24.*

## What this is

Spark MD is Ty and Joyce's entry for the **Dell x NVIDIA AI Hackathon, SF, Sun Oct 25, 2026**. It is an always-on, fully air-gapped lung CT screening agent that runs on one Dell Pro Max with GB10. It reads incoming chest CTs, tracks nodules across years, and drafts reports for a radiologist to approve. Patient data never leaves the box.

- **Ty** builds everything: infra, imaging, agent, UI. **Joyce** owns story, pitch, video and QA, and plays the radiologist in the demo. Tailor answers to whoever is asking.
- Be concise.

## Read order

1. This file.
2. `docs/spark-md-brief.md`: scope, stack, pipeline, demo, risks. The source of truth for *what* we're building.
3. **Event day:** `docs/build/12-day-of-runbook.md` (timeline, parallel lanes, gates, cuts). Prep history: `docs/plans/2026-10-24-prep-day-plan.md`.
4. `docs/build/README.md` and `docs/build/00-architecture.md`: the build-spec system and the v0 contract (ports, API, tools, schema).
5. The spec for the layer you're working on (`docs/build/NN-*.md`).
6. `docs/spark-md-storyboard.md` (demo) and `data/README.md` (data, pitfalls, citations) when relevant.

## Event day: speed first

On Oct 25 **implementation speed beats everything except the non-negotiables below** (those keep us safe and eligible). **Hard stop 17:30:** code locks, video (under 2:00) + repo are due and the GB10 goes back (organizers). Feature freeze 15:15. In practice:

- **Spine first.** Get G3 (confirm → Lung-RADS → agent drafts → Approve → outbox) working end to end before polishing anything. Ugly and working beats clean and half done.
- **Build from the spec, don't research.** The specs hold measured choices. Don't re-litigate decisions, survey alternatives, refactor, or add tests beyond the spec's acceptance tests.
- **15-minute rule.** Stuck for 15 minutes → take the spec's fallback or the next item on the cut order (12), and tell Ty in one line. Don't wait for an answer on reversible choices; pick the default and note it.
- **Parallelize.** Run independent work at the same time (12 §Parallel lanes). Never sit idle waiting on another layer; code against `00` and fixtures.
- **Docs minimal.** During the build, only update a spec's "Open / unverified" and the status line. No write-ups until after submission.
- **Commit small and often** to the event repo, so anything can be rolled back fast.
- **Report in one or two lines:** what passed, what's blocked.

## Non-negotiables

1. **Deterministic code does the medical math.** Measurements, growth, volume doubling time and the Lung-RADS category come from code with tests. The LLM orchestrates and writes. It never assigns or changes a Lung-RADS category. Every number in agent-written text must come from a tool result.
2. **Air-gapped at runtime.** No remote LLM or API calls, no CDNs, no web fonts, no telemetry, and no browser Web Speech API (Chrome sends that audio to Google). Vendor every asset. Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and `NEMOCLAW_DISABLE_TELEMETRY=1` (NemoClaw telemetry is on by default). Never use `:latest` image tags, which can trigger pulls.
3. **Stack.** The hackathon requires **at least one of OpenClaw, NemoClaw or OpenShell**. The organizer confirmed on the event Discord (Oct 24) that teams may bring their own agents as long as they use one of the three.
   - **Fixed:** the OpenShell sandbox (it does the security job in our story), Qwen3.8-27B on the GB10, and MONAI lung nodule detection + VISTA-3D. Don't re-litigate these.
   - **Open until today's checkpoint:**
     - the **agent harness** (Track C bake-off): OpenClaw via NemoClaw, Hermes Agent via NemoClaw, or a minimal custom loop in OpenShell;
     - the **serving recipe** (Track A): SGLang + DFlash2 vs TensorFold + DFlash2.
   - Record each winner in the decisions log below and in the brief.
   - Keep the tool layer harness-agnostic: the worker's REST API plus an MCP endpoint (`00-architecture.md`).
4. **Human gate.** Only a human click approves a report. The agent has no approve tool, the OpenShell policy does not allow the approve route, and the worker rejects approve requests from the sandbox.
5. **Hackathon build rule.** Everything is built on the day; anything substantially pre-built is disqualified. Today's MVP is a **throwaway rehearsal**:
   - MVP code lives **outside** this directory, in `/mnt/ty-ubuntu/projects/spark-md-mvp/` (ty-omarchy) and `~/spark-md-mvp/` (Spark). It is deleted once the specs freeze.
   - Specs in `docs/build/` hold interfaces, parameters, commands, gotchas, acceptance tests, and short snippets (≤ ~30 lines) for the non-obvious parts. **Never paste whole source files into docs.**
   - Benchmarks, environment setup, data prep and notes are allowed prep.
6. **Honesty.** Show "Research demo, not for clinical use" on screen. Use real recorded runs, and mark any sped-up footage (e.g. "2×"). Keep the agent log visible during the time machine. Never claim a clinical outcome the data doesn't support. In docs, mark anything not yet measured as **unverified**.
7. **Shared hardware is Ty's call.** See Machines.

## Machines

| Name | What | Notes |
| --- | --- | --- |
| `tys-macbook-air` | Ty's MacBook Air M2, macOS arm64 | **Ty's dev machine at the event.** Editor + SSH client to the event box; the product builds and runs on the box, not here. Exception: from 10:10 until the box is set up, wave 1 (worker, rules, UI on fixtures) is written here and then moved to the box (12 §Mac-first start). `wheelhouse/` (linux aarch64) and `nodehouse/` (linux x64/arm64) do **not** cover macOS. Reaches the other machines over Tailscale only while venue internet works. |
| `ty-omarchy` | Ty's home desktop, x86_64, RTX 3080 10 GB + RTX 4060 8 GB, 60 GB RAM | Where most prep was done. **Not used at the event** (reachable over Tailscale only). Project mounted over CIFS at `/mnt/ty-ubuntu/projects/spark-md`. |
| `ty-ubuntu` | File server | Holds the project at `/mnt/data/projects/spark-md`. |
| `ty-dgx-spark` ("spark-1") | DGX Spark, GB10, 128 GB unified, aarch64, DGX OS | `ssh ty@ty-dgx-spark` (Tailscale). **Our coding-assistant model server. Not a test box.** |
| `ty-dgx-spark-2` ("spark-2") | Same hardware | `ssh ty@ty-dgx-spark-2.tail29ed60.ts.net`. **The test device: our stand-in for the event box.** Both LLM recipes are staged here: `~/qwen38-sglang` and `~/qwen38-27b-tensorfold`. |
| Event box | Dell Pro Max with GB10, borrowed at the venue | Starts fresh with no Tailscale. Set it up from the external drive (`docs/build/01-box-setup.md`). |

**At the event (Ty's plan, Oct 25):**
- Ty brings an unmanaged Ethernet switch + cables. MacBook (USB-C Ethernet adapter) and event box sit on a private LAN `10.78.0.0/24` with static IPs (`docs/build/01-box-setup.md`, Event LAN). Ty develops over Remote-SSH from the Mac to the box (SSH access to the box assumed, **unverified**; fallback is keyboard + monitor at the box).
- **spark-1 + spark-2 run as one dual-Spark cluster serving DeepSeek V4.1 Flash** (TP2 over their direct fabric link) for Ty's coding inference. The Mac reaches it over Tailscale (already set up, SSH config in place). It is a dev tool, not part of the product, and never runs Spark MD workloads. This supersedes the spark-1/spark-2 roles below; spark-2 is no longer a Spark MD test device.
- Venue internet may be unstable, so the build never depends on it or on Tailscale. Everything needed to build and run lives on the external drive, the box and the LAN. Internet-only items: cloud coding assistants, pushing the event repo, the video upload.

**Rules for the Sparks (prep, as of Oct 24, ~13:00; event-day roles above):**
- **spark-1:**
  - Runs container `qwen38-flash-next-tf` (TensorFold): **Qwen3.8-Flash-Next** at `http://100.114.195.121:8888/v1` (served name `Qwen3.8-Flash-Next`, 262k context, 5 parallel). It helps us write code; any coding agent may use it as an OpenAI-compatible endpoint.
  - It is **not** Spark MD's runtime model and not part of the product.
  - **Never stop, restart or reconfigure it. Don't run GPU or Spark MD workloads on spark-1** (~24 GB available).
- **spark-2:**
  - All Spark MD testing happens here: benches, imaging, sandbox/harness rehearsal, MVP, dry runs. You may start and stop **containers and processes that Spark MD work started**.
  - Leave everything else alone: `beszel-agent`, other projects' images, models and directories in `~` (`dsv41*`, `mimo26*`, `glm53*`, …). Ask Ty before deleting anything or uninstalling system software.
  - Run one heavy GPU job at a time, except in the deliberate co-residence test (A2). Note what you started in the plan's status table, and stop it when you're done.
- **Both:** unified-memory exhaustion can freeze the host. Before any GPU job, run `free -g`. Keep `MemAvailable` ≥ 15 GB.
- **Offline tests over SSH:** block egress with an iptables rule that has an **auto-revert timer** (`systemd-run --on-active=10m ...`) so you can't lock yourself out. Do real cable pulls only at the console.

## Ports and addresses (v0; details in `docs/build/00-architecture.md`)

| What | Where |
| --- | --- |
| LLM, OpenAI-compatible | `127.0.0.1:8000`, served name `qwen3.8-27b`. Port 8000 because NemoClaw treats only localhost `:8000`/`:11434` as no-auth local inference. Today's bench uses the recipes' default `:8888`. |
| Imaging worker (API + MCP + UI + SSE) | `10.77.0.1:8100`, a dummy interface `spark0`. The address must survive a cable pull and be reachable from the sandbox. |
| Agent harness (in sandbox) | Depends on the bake-off. OpenClaw: gateway `:18789` (hooks + chat endpoint). Hermes under NemoClaw: dashboard `:18789`, OpenAI-compatible API `:8642` (`nemohermes <sandbox> gateway-token`). |
| Sandbox → host | OpenShell **never** authorizes loopback egress. The sandbox reaches the worker only through an `enforce`-mode preset added with `--trusted-private-host 10.77.0.1`. The default enforcement is `audit` (log and allow), so always set `enforce`. |

## Directory layout

```
AGENTS.md            this file (CLAUDE.md imports it)
docs/                brief, storyboard, checklist, IDEA.md
docs/plans/          day plans (today: 2026-10-24-prep-day-plan.md)
docs/build/          build specs for recreating the product on the day, back to front
docs/benchmarks/     measured results with method + raw JSON pointers (create when first used)
bench/               benchmark scripts + fixtures (allowed prep; create when first used)
data/                DICOM (NLST, LIDC-IDRI), clinical tables, derived labels, SHA256SUMS. Read data/README.md.
models/              VISTA-3D (NV-Segment-CT) + MONAI lung_nodule_ct_detection v0.5.9, SHA256SUMS
wheelhouse/          aarch64 / cp312 / cu130 wheels + requirements.in/.lock + fetch.sh
nodehouse/           offline UI kit: npm cache (x64+arm64), Electron zips, shadcn registry snapshot, Node tarballs. Read nodehouse/README.md.
scripts/             data-selection scripts (prep only)
assets/brand/        Spark MD icon + lockups (SVG, light/dark) for the UI, pitch and video
tmp/                 scratch; delete before copying to the drive
```

This directory is **not** a git repo. The event repo is created on the day. Never commit `data/`, `models/`, `wheelhouse/` or container tarballs to it.

## Environment

- Target: aarch64, CPython 3.12, CUDA 13 driver, torch `2.13.0+cu130` (matches the SGLang image).
- Offline install on a GB10:
  `python3.12 -m venv ~/.venvs/spark-md && ~/.venvs/spark-md/bin/pip install --no-index --find-links wheelhouse/wheels -r wheelhouse/requirements.lock`
- To add a Python dependency: edit `requirements.in`, re-lock, run `fetch.sh`, then regenerate `wheelhouse/SHA256SUMS`. Same rule for `data/` and `models/`: any file you add gets a checksum.
- The wheelhouse does **not** yet include the web stack (FastAPI/uvicorn) or speech recognition. Today's plan adds them (Track E).

## Working conventions

- Write what you learn into the relevant `docs/build/` spec as you go, not at the end. Each spec follows the template in `docs/build/README.md`. (Event day: minimal docs, see "Event day: speed first".)
- Give every measured number its method, its machine, and the date.
- Update the status table in today's plan when you finish or block on something.
- Don't put secrets (HF tokens, hook tokens) in docs. Point to where they live instead.
- Cite data per `data/README.md` (TCIA: NLST CC BY 4.0, LIDC-IDRI CC BY 3.0; IDC as the source).
- Ask Ty before anything hard to reverse: stopping services, deleting data, installing system packages on the Sparks, or anything outward-facing.

## Decisions log

| Date | Decision |
| --- | --- |
| Oct 24 | Channel (Slack/Discord/Telegram): **none for v1**. Add a PHI-free alert later if time allows. |
| Oct 24 | Required stack = at least one of OpenClaw / NemoClaw / OpenShell (organizer, event Discord). We fix **OpenShell**. |
| Oct 24 | Agent harness: **TBD by Track C** (OpenClaw / Hermes Agent / custom loop, all inside OpenShell). |
| Oct 24 | Sparks: spark-1 = Qwen3.8-Flash-Next coding model (hands off); spark-2 = Spark MD test device. |
| Oct 24 | Serving recipe: **TensorFold is the working default** (13:30, Ty). It is smoke-tested in A0 and serves on `127.0.0.1:8000`. Track A runs last as tune-and-confirm, and SGLang is benched only if time allows. Record the final recipe, exact command and memory settings here. |
| Oct 24 | Hero patient: **TBD by Track B.** Preliminary pick from NLST-reported sizes is 134503. |
| Oct 24 | **A0 passed; TensorFold live on `127.0.0.1:8000`** (spark-2, container `qwen38-27b-tf`; `HOST=127.0.0.1 PORT=8000 SERVED_NAME=qwen3.8-27b PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16 ./start.sh`, ~36 GiB). Tool calls 10/10 thinking-off, 9/10 thinking-on; 40 tok/s prose; no prefix reuse (16k prompt = 8.7 s prefill every turn). Record: `docs/benchmarks/2026-10-24-tensorfold-smoke.md`. |
| Oct 24 | **OpenShell stack live on spark-2** (C1–C3 pass): nemoclaw v0.0.137 + openshell 0.0.116 + OpenClaw 2026.9.2, sandbox `spark-md-openclaw`, `restricted` tier. Inference via `NEMOCLAW_PROVIDER=vllm` (custom/local-endpoint path is broken; LLM now binds `0.0.0.0:8000`, sandbox hits `host.openshell.internal:8000`). Worker policy enforce-verified incl. approve→403. Record: `docs/build/07-agent.md`. |
| Oct 24 | **C4 (cable-pull rehearsal) dropped** (rules check: every demo runs fully local on the event box; laptop demos are out of the prize pool, so there is no network-loss scenario to rehearse on spark-2). Sandbox → worker on `10.77.0.1` stays C3-verified under `enforce`; the iface is dummy and addressing is IP-only, so link loss can't break the stack. The on-camera unplug stays in the storyboard; `spark0` creation on the event box stays in `01-box-setup.md`. |
| Oct 24 | **Agent harness: OpenClaw via NemoClaw** (C5 gate passed 20/20 tool scenarios + 5/5 triage flows, ~74 s median per study; bake-off curtailed for time — Hermes and custom loop not run, reopen only if OpenClaw blocks us). Note for the demo: ~60k-token OpenClaw system prompt × TensorFold's no-prefix-reuse = ~30 s prefill per fresh session; keep sessions warm. Record: `docs/build/07-agent.md`. |
| Oct 24 | **Hero patient: 134503 confirmed** (B3: tracked nodule top-ranked at T0/T1/T2, 2.1/4.0/5.6 mm from Farina coords, scores 0.999–1.000; all 5 heroes passed 15/15 ≤10 mm — `docs/benchmarks/2026-10-24-b-imaging.md`). Our own growth measurements pending B5/B6. Imaging stack: monai 1.6.1 + bundle shims (see `04-imaging-pipeline.md`); detection runs on GB10 only (3080 OOMs). |
| Oct 24 | **Lung-RADS v2022 engine done** (`docs/build/05-clinical-rules.md`; `scripts/lungrads/`): 41 test vectors from the ACR table pass; growth = >1.5 mm/12 mo (Note 6); 4X is a category not a modifier. Hero 134503 on our measured numbers = **2 → 4B → 4B** (with NLST-reported T0 6 mm: 3 → 4B → 4B). VDT stays evidence-only, never a category driver. |
| Oct 24 | **UI: Electron 44 + React 19 + Vite 8 + Tailwind v4 + shadcn (radix-nova) + R3F/three.js** (Ty). Design language from Ty's fabric app (shell, sidebar, sheets; no aurora or avatars), light first with a dark toggle, Geist / Geist Mono (Inter alternate), 1920×1080. Offline kit in `nodehouse/`. Spec: `docs/build/08-ui.md`. |
| Oct 24 | **Voice confirmed by Ty:** ASR = whisper.cpp `small.en` CUDA + phrase prompt + Silero VAD; retain faster-whisper/base.en for pre-demo comparison and fallback. **Spoken answers in scope:** Qwen3-TTS 1.7B-Base container, synthetic voice "aiden", speak after the answer finishes and LLM is idle. **Viewer actions run immediately**, deterministically before agent response, logged and deduplicated per request. Ty brings a plug-in speaker/microphone. Spec: `docs/build/09-voice.md`. |
| Oct 24 | **Voice memory capacity check passed** on spark-2 with TensorFold (`KV_POOL_GB=16`), OpenClaw, ASR/TTS and touched 25 GiB imaging reservation: minimum available **36.84 GiB**, **21.84 GiB above floor**. Reserve another 8 GiB for final UI/worker/recording (unverified allowance). Actual full pipeline co-load remains unverified. Record: `docs/benchmarks/2026-10-24-voice-headroom.md`. |
| Oct 24 | **Imaging correction from longitudinal VISTA test:** historical hero 134503 T0 threshold mask selected heart-boundary tissue (~18.46 mm from detector center), not a validated nodule mask. Historical T0 4.6 mm / 29.7 mm³, T0→T1 VDT 140 d and the derived category sequence are **unvalidated patient evidence**; rule tests still pass on their supplied inputs. Automatic prompt rule v1 fails T0; a detector-box seed follow-up also fails T0 with lung-scale output despite correct positive placement; both are recorded in `docs/benchmarks/2026-10-24-vista-longitudinal.md`. Do not reuse historical T0-dependent numbers as confirmed findings. |
| Oct 24 | **VISTA crop experiment:** fixed 64 mm detector-centered input, same automatic positive/no negatives, yields localized masks and passes coarse geometry/extent/edge gates at T0/T1/T2 (~347/553/774 mm³), >23 mm edge clearance. Full-CT T0 control still fails. **Boundary accuracy and clinical measurements remain unverified; historical T0 fallback/growth/category evidence is not reinstated.** Crop pipeline 0.36–0.39 s warm, min available 63.79 GiB on spark-2. Record `docs/benchmarks/2026-10-24-vista-crop.md`; next independent LIDC contour and crop-stability checks. |
| Oct 24 | **VISTA point-only crop configuration fails LIDC evaluation:** 7 geometry-valid cases, 18 matched nodules / 57 reader annotations, 63 calls including hero stability. Median Dice48/64/96 = 0.064/0.033/0.023. Same 15 multi-reader groups: model median Dice64 0.086 vs reader-pair median 0.775. Hero volume spans 61/42/71% across crop sizes despite bitwise-repeatable same-64 mm masks. **Do not use current VISTA masks for size/growth/VDT/categories.** 0415 SEG orientation metadata contradicts CT, excluded before scoring. Audit point/class conditioning and reference-runner compatibility next; stack remains fixed. Record `docs/benchmarks/2026-10-24-vista-lidc.md`. |
| Oct 24 | **VISTA loader/conditioning audit:** all 259 original, prefixed and HF-loaded tensors match exactly (CPU spark-2). Laptop RTX 3080 direct controls reproduce prior GB10 masks at Dice 0.996–1.000. Three selected LIDC targets + hero T0 × five conditions: explicit zero133 and class23/special click flags do not rescue the selected small failure. Preprocessor/network flag inconsistency exists but is not a demonstrated fix. No nodule measurements accepted; GB10/cohort class validation unverified. Record `docs/benchmarks/2026-10-24-vista-conditioning.md`; next diagnostic is explicitly annotation-assisted foreground/background guidance to test model capability, not automatic validation. |
| Oct 24 | **VISTA crop mechanism isolated:** the 64 mm crop rescue comes from **removing context** (air-masking outside 64 mm on the original grid rescues 7/7 lung-scale failures; resampling-phase shifts and a 192 mm crop do not). Not a fix: ±6 mm crop shifts change hero volumes up to 3.8×, LIDC median Dice ≤0.09 in all 20 conditions (inter-reader 0.78), class 23 no gain. VISTA point masks stay out of size/growth/categories. Record `docs/benchmarks/2026-10-24-vista-reliability.md`. |
| Oct 24 | **VISTA annotation-assisted click diagnostic fails:** reader-guided positives + near-boundary (2–4 mm) negatives on 3 diagnostic targets (rule `clicks-assisted-v1`, laptop 3080; controls reproduce GB10 and conditioning masks at Dice 0.996–1.000) never beat the automatic single positive. Guide positive alone degrades all targets; negatives collapse the logit at the positive point (−17.1 on 0052) and the native `keep_components_with_positive_points` filter empties the output. Interactive guidance is not a rescue path in this stack; if VISTA is pursued further, run NVIDIA's reference runner on the same frozen clicks. No measurements accepted. Record `docs/benchmarks/2026-10-24-vista-clicks.md`. |
| Oct 24 | **Measurement bake-off (no method accepted):** rule-based segmenter A7 is accurate at the detector centre (held-out LIDC median diameter error 0.46 mm vs readers 0.73; NLST-reported heroes 0.86 mm) but moves ~2–3 mm under ±3 mm box shifts; VISTA + negatives 60% empty; detector-box diameter looks good but is contaminated on LIDC and has no mask. Pending Ty: extra held-out LIDC validation of "A7 + box agreement ≤2 mm, else radiologist confirms", or radiologist-entered diameters. Record `docs/benchmarks/2026-10-24-nodule-measure.md`. |
| Oct 24 | **Demo measurement path = radiologist-confirmed diameters (Ty).** The worker shows the rule-based A7 diameter (and mask) as a *proposal*; the radiologist confirms or edits each diameter in the UI before growth/VDT/Lung-RADS are computed by code. The agent never proposes or edits a diameter. Held-out LIDC validation of "A7 + box agreement ≤2 mm" runs in parallel as evidence only. |
| Oct 24 | **Held-out LIDC check (15 new patients, 31 nodules, rule frozen before download): G1–G4 pass, G5 fails.** A7 median diameter error 0.51 mm unflagged (readers 0.59), 0.55 mm all; flag rate 19%; but ±3 mm box shifts swing A7 by 1.8 mm (bar 1.5), and the A7-vs-box flag caught only 2/4 errors >2 mm. Confirms the radiologist-confirmed path; A7 is a proposal, not an accepted measurement. Record `docs/benchmarks/2026-10-24-nodule-holdout.md`. |
| Oct 25 | **Cohort 2 (rule frozen before download):** 30 NLST stable-nodule patients — A7 year-to-year change median 0.28 mm, false growth 2/53 intervals (3.8%), **passes**; but A7 reads +1 mm vs NLST reports on 4–7 mm nodules. 20 more LIDC (40 nodules) fail G2/G5 again; A7-vs-box >2 mm flag caught 10/13 large errors pooled. Keeps the radiologist-confirmed path; A7 growth proposals look usable. Record `docs/benchmarks/2026-10-24-nodule-cohort2.md`. |
| Oct 25 | **Event-day machines (Ty):** dev on `tys-macbook-air` via Remote-SSH to the event box over Ty's own switch (LAN `10.78.0.0/24`); spark-1 + spark-2 serve DeepSeek V4.1 Flash as a dual-Spark coding cluster, reached from the Mac over Tailscale. `ty-omarchy` stays home. |
| Oct 25 | **Growth over intervals > 12 months is rate-normalized (Ty).** Lung-RADS Note 6 says >1.5 mm "within a 12-month interval"; NLST annual screens run ~12–13 months (hero T0→T1 = 371 d). `growth_per_12mo(delta, days)` in `scripts/lungrads/rules.py`: ≤ 365.25 d uses the absolute change, longer intervals use `delta × 365.25 / days`, short intervals are never scaled up. Our interpretation, not ACR wording; label it in the UI rule text. Tests pass (8 suites). Spec: `05-clinical-rules.md`. |
| Oct 25 | **Organizer schedule (announcement, ~09:50) replaces the brief's:** hacking + GB10 distribution 10:10 (teams of 4–5 first); **17:30 code lock, video under 2:00 + repo due, GB10 returned**; 18:00 project deadline (unclear vs 17:30, plan for 17:30); 19:00 pitch deck + top-8 live demos (3 + 2 min). Rules match ours: no prebuilt code (public open source allowed), all inference local on the GB10. Re-planned timeline: `12-day-of-runbook.md`. |
| Oct 25 | **Wave 1 starts on the Mac (Ty):** W, I's rules and U begin at 10:10 on `tys-macbook-air` in the event repo, then move to the box after bring-up. Coding agent on the box = Claude Code over venue Wi-Fi; fallback DeepSeek cluster through the Mac (`ssh -R 8091:100.114.195.121:8091`). Box bring-up: copy then verify locally, skip `validation/`, block `:8000` before starting the LLM when the box is on Wi-Fi. |
| Oct 25 | **Specs live in the event repo from ~11:20 (Ty):** `docs/` in `tdoan35/spark-md` is canonical (Mac `~/Desktop/spark-md-app/docs`, box `~/spark-md-app/docs`); the old paths `~/Desktop/spark-md/docs`, `~/spark-md/docs` and both `AGENTS.md` are symlinks to it (originals kept as `*.bak-prep`). Commit spec edits with `git add docs/<file>`. Git on the box: `~/spark-md-app` clones the LAN bare repo `~/spark-md-app.git`; the Mac pushes it to GitHub. Box copy landed at `~/spark-md/` (incl. `validation/`). |
