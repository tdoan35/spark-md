# Spark MD — Project Brief

*Dell x NVIDIA AI Hackathon, San Francisco · Sun Oct 25, 2026 · Frontier Tower, 995 Market St* *Last updated: Oct 24, 2026*

## One-liner

Spark MD is an always-on, fully air-gapped lung cancer screening assistant for hospital radiology teams. It reads incoming chest CTs, finds and tracks nodules across years, and drafts reports for a radiologist to approve. It runs on one Dell Pro Max with GB10, and patient data never leaves the box.

## Team


| Person    | Owns                                                                                                                                                                                                        |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Ty**    | All engineering: infra (SGLang, NemoClaw/OpenShell), imaging worker (MONAI, VISTA-3D), agent tools, UI build. Brings the 2017 Kaggle Data Science Bowl lung-CT background and a DGX Spark cluster for prep. |
| **Joyce** | Story, pitch, and demo video (storyboard, voiceover, recording). QA, and she plays the user: the radiologist in the demo who talks to the scan and clicks Approve.                                          |


## The event (confirmed from the SF page)

- **Brief:** an always-on agent someone in ops, sales, support or engineering would want tomorrow. "It runs locally, it's useful, and a company would pay for it." 150 builders, teams of 2–5, one GB10 per team.
- **Required stack:** at least **one of** NemoClaw, OpenClaw or OpenShell. Bring-your-own agents are allowed (organizer Sean Chiu on the event Discord, Oct 24). All inference on the GB10; no remote LLM calls at runtime. A Mac-only demo can't place.
- **Channel:** Slack, Discord or Telegram (see Risks; this conflicts with the air-gap story).
- **Judged on:** technical execution, business value, local-first design, demo quality.
- **Rules that matter to us:** build on the day; scaffolds and libraries are fine, anything substantially pre-built is disqualified. Business workflow only (no toys or personal-assistant clones). Only use material we're cleared to use, and declare the stack.
- **Hardware:** we borrow a GB10, monitor, keyboard and mouse. Bring laptops. Bring models, datasets and packages on an external drive (the `spark-md/` project dir); wifi is shared by 150 people.
- **Prizes:** 1st: one Dell Pro Max with GB10 per team. 2nd/3rd: one Dell Pro Max Premium 14 per team. 5th–8th: swag.
- **Our prep rule:** this week we prep **environment, data, benchmarks and notes only**. No app code until the day.

### Schedule (Sun Oct 25, PT; organizer announcement on the day, supersedes the Oct 23 email)


| Time        | What                                                                 |
| ----------- | -------------------------------------------------------------------- |
| 09:50       | Opening ceremony                                                     |
| 10:10       | GB10 distribution + hacking begins (teams of 4–5 get boxes first)    |
| 13:00       | Lunch                                                                |
| **17:30**   | **Code locks. Round 1 due: video under 2 min + repo. GB10 returned** |
| 18:00       | Project submission deadline (video, repo); unclear vs 17:30, plan for 17:30 |
| 19:00       | Pitch deck due. Top-8 live demos: 3 min demo + 2 min Q&A            |
| 20:00       | Judges deliberate + awards                                           |


### Submission (due 17:30)

- Working demo on the GB10
- Repo (named in BuilderBase's Oct 23 email)
- Video walkthrough, **under 2 minutes**
- Short writeup and NVIDIA feedback form (in the Oct 23 email; not in the day-of announcement, so confirm)
- Pitch deck by 19:00 for the top-8 round

**Implication:** the video has to be recorded and edited before the GB10 goes back at 17:30. Feature freeze 15:15, Joyce records 15:30–16:45, upload by 17:15. Day-of timeline: `docs/build/12-day-of-runbook.md`.

## Why it wins

Judges are selling three things: local/private, always-on, and sandboxed safety. Spark MD answers "why not just call a cloud API?" in one sentence: HIPAA-grade patient scans can't leave the hospital. It acts on triggers (new scans arriving), not chat prompts, and OpenShell has a real job (blocking exfiltration).

## Locked stack

- **Sandbox:** OpenShell (fixed; satisfies the required-stack rule).
- **Agent harness (locked Oct 24):** **OpenClaw via NemoClaw** inside OpenShell — passed 20/20 tool scenarios and 5/5 full triage flows against the fixture worker (~74 s median per study). Hermes and the custom loop were not run (time); bake-off curtailed. See `docs/build/07-agent.md`.
- **LLM:** Qwen3.8-27B (MLX 4-bit quant) on **TensorFold** with the z-lab DFlash2 drafter. A0 smoke (Oct 24, spark-2): tool calls 10/10 thinking-off, 40 tok/s prose, ~36 GiB footprint.
- **Serving recipe (working default, Oct 24):** TensorFold, `tensorfold-qwen38-27b:v0.6.0`, `HOST=0.0.0.0 PORT=8000 SERVED_NAME=qwen3.8-27b PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16` (binds `0.0.0.0` so the sandbox bridge reaches it at `host.openshell.internal:8000`). Track A may still bench SGLang, but TensorFold is smoke-proven end to end. No prefix caching: ~60k-token harness prompt ⇒ ~30 s prefill per fresh session — keep sessions warm in the demo.
- **Ruled out:** Qwen3.8-Flash-Next (NVFP4 checkpoint too large for the pipeline's memory budget).
- **Imaging:** MONAI `lung_nodule_ct_detection` v0.5.9 (on monai 1.6.1 with documented shims — `04-imaging-pipeline.md`), VISTA-3D (`nvidia/NV-Segment-CT`) for point-prompt segmentation, threshold-ROI fallback, Lung-RADS v2022 rules engine with 41 test vectors (`05-clinical-rules.md`).
- **Imaging validation correction (Oct 24):** detection passed; full-CT VISTA segmentation failed at T0; a fixed 64 mm crop passes hero gross-failure checks but **fails the subsequent LIDC boundary/stability test** (18 matched groups, median Dice64 0.033; hero volume spans 42–71% across crop sizes). No reliable automatic nodule measurements/growth are established for this configuration. The historical T0 threshold mask selected heart-boundary tissue, so its size/volume and T0-dependent VDT/category sequence must not be presented as validated patient findings. See `docs/benchmarks/2026-10-24-vista-longitudinal.md`.
- **Data:** NLST (TCIA, CC BY 4.0) for multi-year patients; LIDC-IDRI for radiologist-annotated ground truth. Staged in `data/` (see `data/README.md`).
- **Staged weights (`models/`):** VISTA-3D `nvidia/NV-Segment-CT` `model.pt` (NVIDIA Open Model License) and MONAI `lung_nodule_ct_detection` bundle v0.5.9.

## Architecture

**Principle:** deterministic code does the medical math; the LLM orchestrates and writes. The LLM never assigns the Lung-RADS category.

- **Agent** (in the OpenShell sandbox) calls the imaging worker's tools over a stable host IP (`10.77.0.1`, a dummy interface that survives the cable pull). OpenShell never authorizes loopback egress (Oct 24 finding; see `docs/build/00-architecture.md`).
- **Imaging worker** (host GPU service, outside the sandbox): MONAI detector, VISTA-3D, Lung-RADS rules, marching-cubes meshes.
- **LLM server** on localhost `:8000` serving Qwen3.8-27B. NemoClaw-managed harnesses expect `:8000`.
- **UI:** worklist dashboard, three.js 3D viewer, voice commands, Approve button, mock EHR inbox.
- **Egress policy:** the sandbox may reach only the imaging worker's agent routes, in `enforce` mode (the default is audit, which allows). Nothing else. The approve route is human-only.

### Pipeline

1. **Intake:** watched folder acts as a mock PACS.
2. **Organize** *(agent):* parse DICOM headers, group by patient/study/series, pick the thin-slice lung series, write to a SQLite registry.
3. **Preprocess:** HU conversion and resampling with the MONAI bundle's transforms.
4. **Lung mask:** VISTA-3D lobes (CPU threshold fallback).
5. **Detect:** MONAI candidates; drop any outside the lung mask.
6. **Characterize:** size, volume, solid vs ground-glass from HU.
7. **Compare with priors:** match nodules to last year's scan by lobe and position; compute growth. *(Core to the demo.)*
8. **Score** *(rules):* Lung-RADS from size, type, growth.
9. **Render:** meshes to three.js, plus key 2D slices with the nodule boxed.
10. **Report** *(agent):* radiology-style report and PCP letter.
11. **Human gate:** radiologist approves; letter goes to the mock EHR inbox.

### Extra screenings (demo segment 4)

- **Emphysema** (easy): % of lung voxels below about −950 HU inside the lung mask.
- **Bone density** (moderate): mean HU in one vertebra from VISTA-3D's segmentation.
- **Coronary calcium** (hard): label "experimental"; first to cut.

### Voice

Local push-to-talk recognition uses whisper.cpp small.en on CUDA with phrase prompting + Silero VAD (Ty confirmed Oct 24); faster-whisper and base.en stay staged for pre-demo comparison and fallback. Four fixed commands: show nodule, compare last year, explain the flag, reset view. Viewer actions run immediately in deterministic code, are logged, and the agent explanation follows. Spoken answers use local Qwen3-TTS 1.7B-Base, synthetic voice aiden, after the answer finishes and the shared LLM is idle; label the voice on screen. Ty brings a plug-in speaker/microphone. Real voices and capture/playback on that device remain **unverified**. See `docs/build/09-voice.md`.

## Demo plan

3-minute arc; full shot list in [`spark-md-storyboard.md`](spark-md-storyboard.md).

1. Cold open: a real patient diagnosed in year 3.
2. Pull the network cable.
3. Time machine: replay the scans; the agent flags growth at year 2.
4. Talk to the scan: Joyce, as the radiologist, asks questions and approves.
5. One scan, four screenings.
6. Close: stack card, "0 bytes sent to the cloud," the 2017 callback.

Stretch moments if time allows: a DICOM-embedded prompt injection blocked live by OpenShell; a backlog counter showing scans processed since doors opened.

## Risks


| Risk                                      | Test / mitigation                                                                                                                                                                                                                                                                 |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Memory contention** (the deciding test) | SGLang at \~0.50 memory fraction; push full scans through detection + VISTA-3D while generating, dozens of times. Fallbacks in order: raise to \~0.60 and use the CPU lung mask; run imaging models sequentially and free memory between steps; cut SGLang context length.        |
| **Arm64**                                 | Confirm MONAI, SimpleITK, pydicom and TensorRT export all install and run on DGX OS.                                                                                                                                                                                              |
| **Patient selection**                     | Need an NLST patient with ≥2 prior screens, a visibly growing nodule, and a known later diagnosis. If TCIA's public clinical subset lacks diagnosis timing, reframe the open as "This nodule grew. Would anyone have caught it?" Never claim an outcome the data doesn't support. |
| **Sandbox + harness setup time**          | Rehearse OpenShell + the chosen harness install and policy config from scratch on spark-2.                                                                                                                                                                                                                       |
| **Sandbox → host reach**                  | Verified in C3 on spark-2: sandbox reaches the worker on `10.77.0.1` (loopback egress is never allowed by OpenShell), `enforce` denials visible. Cable-pull rehearsal (C4) dropped Oct 24 — rules say demos run fully local on the event box; the on-camera unplug is the only link-loss test.                                                      |
| **Per-scan latency**                      | Measure detection time per scan; decide live processing vs pre-run backlog.                                                                                                                                                                                                       |
| **Channel vs air gap**                    | The page lists Slack/Discord/Telegram as the channel, but those are cloud services and the cable pull would cut them. Decide this week (see Open questions).                                                                                                                      |
| **Video inside the build day**            | Feature freeze 15:15, video freeze 15:30; the GB10 goes back at 17:30. Joyce records whatever works then; the cut order in the storyboard applies.                                                                                                                                 |
| **Data licensing**                        | NLST (CC BY 4.0) and LIDC-IDRI (CC BY 3.0) both allow use with attribution. Credit TCIA in the writeup and the video end card.                                                                                                                                                    |


## Honesty rules

- "Research demo, not for clinical use" on screen.
- Real recorded runs. Any sped-up footage gets a visible "2×".
- Agent log stays on screen during the time machine.

## Open questions

- **Channel (decided Oct 24: none for v1; add later if time allows):** is Slack/Discord/Telegram required, or one option? Ask [info@builderbase.com](mailto:info@builderbase.com). If it's required, the leading option is a PHI-free alert ("1 priority study on the worklist") to the radiologist's channel, with images, findings and reports staying on the box. Keep the cable pull, and show alerts queuing offline and delivering on reconnect.
- ~~How long the top-8 live pitch is.~~ Answered Oct 25: 3 min demo + 2 min Q&A, deck due 19:00. Open: whether finalists get the GB10 back after returning it at 17:30.
- Whether TCIA's public NLST clinical subset includes diagnosis timing.
- Exactly which patients we'll use (pre-download 5–10).