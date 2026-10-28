# AGENTS.md — Spark MD

Read this first. Every agent working in this repo follows it. *Last updated: Wed Oct 28, 2026 (post-event).*

## What this is

Spark MD is Ty and Joyce's entry for the **Dell x NVIDIA AI Hackathon, SF, Sun Oct 25, 2026**, and it **won 1st place**. It is an always-on, fully air-gapped lung CT screening agent that runs on one Dell Pro Max with GB10. It reads incoming chest CTs, tracks nodules across years, and drafts reports for a radiologist to approve. Patient data never leaves the box.

- **Ty** builds everything: infra, imaging, agent, UI. **Joyce** owns story, pitch, video and QA, and plays the radiologist in the demo.
- The event is over. This repo is the record of what was built on the day. There is no active build; ask Ty before starting new feature work.
- Be concise.

## Read order

1. This file, then `README.md` (features, flow, architecture, how to run).
2. `docs/spark-md-brief.md`: scope, stack, pipeline, demo, risks.
3. `docs/build/README.md` and `docs/build/00-architecture.md`: the build-spec system and the v0 contract (ports, API, tools, schema). Then the spec for the layer you're touching (`docs/build/NN-*.md`).
4. History: `docs/build/12-day-of-runbook.md` (event day), `docs/plans/` (prep), `docs/benchmarks/` (measured results).

## Product rules (still apply to any change)

1. **Deterministic code does the medical math.** Measurements, growth, volume doubling time and the Lung-RADS category come from code with tests. The LLM orchestrates and writes. It never assigns or changes a Lung-RADS category, and never proposes or edits a diameter. Every number in agent-written text must come from a tool result.
2. **Air-gapped at runtime.** No remote LLM or API calls, no CDNs, no web fonts, no telemetry, and no browser Web Speech API. Vendor every asset. Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and `NEMOCLAW_DISABLE_TELEMETRY=1`. Never use `:latest` image tags.
3. **Stack (as shipped):** OpenShell sandbox + OpenClaw via NemoClaw, Qwen3.8-27B on TensorFold, MONAI lung nodule detection, A7 rule-based diameter proposals confirmed by the radiologist. Keep the tool layer harness-agnostic (worker REST API + MCP).
4. **Human gate.** Only a human click approves a report. The agent has no approve tool, the OpenShell policy does not allow the approve route, and the worker rejects approve requests from the sandbox.
5. **Honesty.** Show "Research demo, not for clinical use" on screen. Use real recorded runs and mark sped-up footage. Never claim a clinical outcome the data doesn't support. Mark anything not measured as **unverified**.
6. **Build-on-the-day record.** Don't add pre-event prep code to this repo; it stays in the local, gitignored `archive/`.

## Machines (post-event)

| Name | Notes |
| --- | --- |
| `ty-omarchy` | Ty's home desktop. Repo cloned at `/mnt/ty-ubuntu/projects/spark-md` (CIFS from `ty-ubuntu:/mnt/data/projects/spark-md`), with local-only `data/`, `models/` and `archive/`. |
| `ty-dgx-spark`, `ty-dgx-spark-2` | Run as one cluster serving GLM-5.3-Flash for unrelated coding work. **Never touch the model or its service, and don't run Spark MD workloads there** without Ty's go-ahead. spark-2 keeps the Qwen3.8-27B recipes (`~/qwen38-27b-tensorfold`, `~/qwen38-sglang`) and the stopped `qwen38-27b-tf` container for later use. |
| Event box | Borrowed Dell Pro Max with GB10; returned after the event. |

Unified-memory exhaustion can freeze a GB10. Before any GPU job, run `free -g` and keep `MemAvailable` ≥ 15 GB.

## Ports and addresses (details in `docs/build/00-architecture.md`)

| What | Where |
| --- | --- |
| LLM, OpenAI-compatible | `127.0.0.1:8000`, served name `qwen3.8-27b` (binds `0.0.0.0` so the sandbox reaches `host.openshell.internal:8000`). |
| Imaging worker (API + MCP + UI + SSE) | `10.77.0.1:8100` on dummy interface `spark0` (also `127.0.0.1:8100`). |
| Agent harness (in sandbox) | OpenClaw gateway `:18789`. |
| Sandbox → host | Only through an `enforce`-mode preset with `--trusted-private-host 10.77.0.1`; OpenShell never authorizes loopback egress. |

## Local-only directories (gitignored)

```
data/      DICOM (NLST, LIDC-IDRI), clinical tables, derived labels. Read data/README.md. Re-downloadable from IDC.
models/    detection, VISTA-3D, ASR and TTS weights. Re-fetchable.
archive/   spark-md-prep-2026-10-24.tar.gz: pre-event bench/, scripts/ and assets/brand/.
```

Never commit these or container tarballs.

## Working conventions

- Give every measured number its method, its machine, and the date.
- Don't put secrets (HF tokens, hook tokens) in docs. Point to where they live instead.
- Cite data per `data/README.md` (TCIA: NLST CC BY 4.0, LIDC-IDRI CC BY 3.0; IDC as the source).
- Ask Ty before anything hard to reverse: stopping services, deleting data, installing system packages, or anything outward-facing.

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
| Oct 25 | **Result: 1st place**, Dell x NVIDIA AI Hackathon SF. Built on the day from the `docs/build/` specs. |
| Oct 28 | **Post-event cleanup (Ty):** prep MVP code deleted on all machines; OpenShell sandbox `spark-md-openclaw` destroyed on spark-2; the Sparks now serve GLM-5.3-Flash for unrelated coding work. Prep scripts (`bench/`, `scripts/`, incl. `scripts/lungrads/` referenced above) archived locally in gitignored `archive/`, not published. |
