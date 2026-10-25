# Prep day plan: Sat Oct 24, 2026

*The day before the hackathon. Owner: Ty (agents execute), with Joyce's items at the end. Read `AGENTS.md` first.*

## Today's goals and what "done" means

1. **Serving recipe confirmed with numbers.** TensorFold is the working default (decided 13:30). Track A runs last, after B and C, as a tune-and-confirm bench with real prompts and real co-load. The recipe that ends up chosen passes every gate. Its exact launch command and memory settings are recorded in `docs/build/02-llm-serving.md`, the brief and `AGENTS.md`.
2. **Prep finalized.** The external drive is packed and checksummed, and an **offline fresh-box dry run** from the drive alone works (Track E).
3. **MVP built back to front, far enough to write the specs.** Every layer in Track D ends with its `docs/build/NN-*.md` spec. Those specs are the deliverable. The MVP code is deleted tonight.

## Constraints

- **Sparks (updated ~13:00):** GLM-5.3 is unloaded.
  - **spark-1** runs Qwen3.8-Flash-Next for coding help. Hands off.
  - **spark-2** is free and is **the test device for everything below**. Rules are in `AGENTS.md` → Machines.
- **Required stack:** at least one of OpenClaw / NemoClaw / OpenShell (organizer, event Discord). We fix **OpenShell**. The agent harness is chosen by bake-off (Track C).
- **Channel:** none for v1 (decided Oct 24).
- **MVP location:** `/mnt/ty-ubuntu/projects/spark-md-mvp/` on the laptop, rsynced to `~/spark-md-mvp/` on a Spark. Never put it inside `spark-md/` or on the drive.

## Survey findings that change the plan (Oct 24, morning)

| # | Finding | Consequence |
| --- | --- | --- |
| F1 | OpenShell **never authorizes loopback egress**. A host service must sit on a non-loopback host IP and be added with `--trusted-private-host`. Don't rely on `host.docker.internal`, which bypasses policy. | The brief's "tools over localhost" is wrong. The worker binds `10.77.0.1` on a dummy iface `spark0`. Verified in C3. |
| F2 | Pulling the cable removes the LAN IP. Anything bound to it breaks mid-demo. | The dummy-interface address (F1) also fixes this by construction; the on-camera unplug is the only link-loss test (C4 rehearsal dropped — demos run fully local). Also turn **wifi off**, or "air-gapped" isn't true. |
| F3 | NemoClaw-managed harnesses (OpenClaw, Hermes) accept no-auth local inference only on localhost `:8000` (`NEMOCLAW_VLLM_PORT`) or `:11434`. | Serve the LLM on `:8000` at the event. SGLang's `start.sh` hardcodes `PORT="8888"` (line 238), so it needs a recipe-branch edit. |
| F4 | OpenShell policy enforcement defaults to **`audit`** (logs, then allows). | Every preset sets `enforcement: enforce`, or the exfil-block moment shows nothing. |
| F5 | Nothing in the agent stack (OpenClaw, NemoClaw, OpenShell, Hermes, Node) is installed on either Spark. MONAI isn't either. Hermes Agent *is* installed on Ty's laptop (`~/.local/bin/hermes`, standalone, not sandboxed). | Track C is the biggest unknown. Start it on spark-2 now. |
| F6 | TensorFold's default KV pool **pins up to 78 GiB** (~97 GiB process). SGLang's DFlash wrapper sets `--mem-fraction-static 0.90`. | Both need explicit low-memory settings to sit beside imaging (A1 settings). |
| F7 | TensorFold `.env` sets `HOST=100.65.103.115` (Tailscale) and uses `TensorFold/Qwen3.8-27B-MLX-4bit`. `prepare.log` warns this checkpoint is "not a checkpoint TensorFold is tested with" (the tested one is `Vontra/...`). | The event box has no Tailscale, so bind to `127.0.0.1`. Treat quality as unverified until A1 G4 passes. |
| F8 | The wheelhouse lacks the web stack and speech recognition. Frontend assets aren't staged. | Track E1–E3. |
| F9 | HF caches use symlinks (blobs → snapshots). exFAT drops symlinks and exec bits. | The drive should be ext4. Otherwise copy HF caches dereferenced (`rsync -aL`) or as tarballs. |
| F10 | The NemoClaw installer (`curl -fsSL https://www.nvidia.com/nemoclaw.sh \| bash`) pulls Node, OpenShell and images from the internet. | Capture what it pulls (C2). Fallbacks: venue wifi at 08:30 before the crowd, or Ty's phone hotspot. |
| F11 | NLST-reported sizes: **134503** has a single solid lingula nodule 7×5 → 10×8 → 14×14 mm, a clean "category 3 → growing 4B" story. **113820** also has a 13 mm RUL nodule at T0, which scores 4A at baseline by itself. | 134503 is the preliminary hero. Confirm with our own measurements (B3–B6). |
| F12 | Organizer (event Discord, Oct 24): bring-your-own agents are fine as long as we use one of OpenClaw / NemoClaw / OpenShell. | We fix OpenShell and bake off harnesses (Track C). The tool layer must not depend on one harness. |
| F13 | "Hermes" (the Discord link `build.nvidia.com/spark/hermes-agent`) is **Nous Research's Hermes Agent harness**, not a model. Playbook: v0.18.0. It runs standalone, or inside OpenShell via NemoClaw (`NEMOCLAW_AGENT=hermes`, CLI `nemohermes`), where it exposes an OpenAI-compatible API on `:8642` and a dashboard on `:18789`. NemoClaw also lists LangChain Deep Agents and Pi, but both are terminal-only with no HTTP API, which doesn't fit an event-driven agent with a UI. | Bake-off candidates: OpenClaw, Hermes, custom loop. |
| F14 | NemoClaw install **telemetry is on by default**. | Set `NEMOCLAW_DISABLE_TELEMETRY=1` before every install, or "0 bytes to the cloud" isn't true. |

## Tracks

| Track | Where | Can start | Output |
| --- | --- | --- | --- |
| **A0** TensorFold smoke test (working default) | spark-2 | **now, first** | `docs/benchmarks/2026-10-24-tensorfold-smoke.md`; TensorFold serving on `127.0.0.1:8000` |
| **A** Tune and confirm the recipe (A1–A3) | spark-2 | **last**, after B and C | `docs/benchmarks/2026-10-24-llm-recipes.md`, `docs/build/02-llm-serving.md` |
| **B** Imaging core experiments | laptop 3080 now; spark-2 after A0 | **now** | `04-imaging-pipeline.md`, `05-clinical-rules.md`, hero decision in `data/README.md` |
| **C** OpenShell + agent-harness bake-off | spark-2 | **now** (C1–C4 need no LLM; C5 needs A0's TensorFold on `:8000`) | `07-agent.md`, harness decision, box-setup steps in `01-box-setup.md` |
| **D** MVP layers, back to front | laptop, then spark-2 | L0–L4 now; L5+ after A0 and C | `01`–`12` specs |
| **E** Finalize prep and pack the drive | laptop, then spark-2 | E1–E3, E7–E9 **now** | drive + checksums + dry-run timings |
| **J** Joyce | — | now | story/pitch inputs listed below |

**Sharing spark-2:**
- A0 runs first. TensorFold then **stays up** on `127.0.0.1:8000` with low-memory settings for C5, B on GB10 and the MVP.
- Light work (E1 wheelhouse install, C1–C4) can run alongside it.
- Track A runs last. Its A1 probes need ~30 minutes with nothing else heavy on the box; A3 is the deliberate co-residence test.

### Status

| Item | Status |
| --- | --- |
| UI chat resize + borderless | **done (Oct 24, laptop)** — phrase chips are now outline buttons; removed outer borders on the chat rail, composer footer and composer card (shadow-only); chat rail is drag-resizable via its right edge (240–560 px, `.resizing` kills the grid transition mid-drag), persists in `sparkmd-chat-w`, double-click resets to the CSS default. Build passed; DOM-verified outline chips, 0 px borders, drag/clamp 240–560/reset/reload-persistence, inspector collapse at custom width, no overflow; e2e 50 req / 0 non-loopback, approval→outbox 1 ms. Updated `08-ui.md`. |
| UI chat chip placement | **done (Oct 24, laptop)** — quick-phrase chips moved out of the composer card to a row above it, at the bottom of the chat history; composer toolbar now right-aligned mic + Send/Stop. Build passed; DOM-verified placement, 4 chips, gating code unchanged, no overflow. |
| UI chat composer (fabric port) | **done (Oct 24, laptop)** — studied fabric `composer.tsx`/`composer-bar.tsx`; ported the card composer (2-row auto-grow textarea + toolbar), circular accent Send with ArrowUp, streaming Stop swap with gated input (no more silent abort-previous), phrases as toolbar chips; mic slot kept disabled (09). Context meter/attachments/pickers deliberately not ported (no data source / not applicable). Build passed; DOM-verified swap/gating/stop/auto-grow/Enter; e2e 50 req / 0 non-loopback, approval→outbox 1 ms. Updated `08-ui.md`. |
| UI patient-page refinement | **done (Oct 24, laptop)** — inspector collapse animates (220 ms grid-track transition, fixed inner width + `inert`); inspector top has Assessment ↔ Agent activity toggle group (Live pill in tab row, activity fills the panel); growth strip header `Longitudinal comparison · N total scans` with Compare moved into it; strip wraps on imaging-column container width (≤880 px) so nothing clips with the inspector open. Fixed a persistence regression (effect lost in an edit) found by re-checking. Build passed; Electron e2e 50 req / 0 non-loopback, approval→outbox 1 ms, no overflow; DOM-verified animation trajectory, tabs, wrap at a 574 px column, persistence both directions. Updated `08-ui.md`. |
| UI patient-page revision | **done (Oct 24, laptop)** — one-row 60 px header (title + CT/timepoint + priority inline), header icon toggle collapses the clinical inspector (persists per session), new left **agent chat rail** with real conversation history + moved composer; growth strip stays under the viewer; AskBox deleted. Build passed; Electron e2e 51 req / 0 non-loopback, approval→outbox 1 ms; DOM-verified grid at 1920/1440 × inspector open/collapsed. Updated `08-ui.md`. |
| UI container/footer refinement | **done (Oct 24, laptop)** — restored 1 px main-surface border; removed 8 px bottom outer margin; moved “Local only · Air-gapped” from sidebar to footer right, replacing old Spark MD copy. Sidebar/footer borders remain off. Build passed; expanded/light 1920×1080 and collapsed/dark 1440×900 browser checks: 0 px gap above footer, status visible, no page overflow. Updated `08-ui.md`. |
| UI shell border cleanup | **done (Oct 24, laptop)** — moved history Back/Forward immediately after Search in the left cluster. Removed sidebar edge, main-surface outline and footer rule; sidebar uses important border override to beat shadcn's side-specific selector. Build passed; browser checked working history, expanded/light 1920×1080 and collapsed/dark 1440×900: computed shell borders all 0 px, no page overflow. Updated `08-ui.md`. |
| L5 worker API | **rehearsed Oct 25 ~00:45 (spark-2), cut for time** — throwaway FastAPI worker (MCP + SSE + gates + trigger, fixture imaging): stdlib contract 27/27 laptop + spark-2 (wheelhouse venv); sandbox reaches worker from 172.18.0.2 (worker guard independent of policy); OpenClaw ran a full triage chain through it. C5 rerun stopped at ~5/20 (no failures). Hook trigger, C5 ×5, MCP-timeout probe unverified. Growth window resolved Oct 25: intervals > 12 months rate-normalized (`growth_per_12mo`, 05). C5 fixture worker restored on :8100; MVP code in `~/spark-md-mvp/worker` (spark-2) and `spark-md-mvp/worker` (laptop), not for the drive. Spec: `06-worker-api.md` |
| Plan, AGENTS.md, build-spec framework, v0 contract | done (12:45); stack and Sparks update (13:15) |
| A0 TensorFold smoke | **done 13:45 — PASS** (10/10 tool calls thinking-off, 9/10 on; 40 tok/s prose; ~36 GiB; no prefix reuse — see doc). Record: `docs/benchmarks/2026-10-24-tensorfold-smoke.md` |
| C | **C1–C3 + C5 done — harness = OpenClaw** (20/20 scenarios, 5/5 triage; Hermes/custom-loop not run for time). **C4 dropped: rules say demos run fully local on the event box, no LAN-loss rehearsal needed** (see decisions log). Record: `docs/build/07-agent.md` |
| B | **B1–B3/B7 done; B5/B6 historical hero results partly invalidated ~20:42** — Lung-RADS v2022 engine: 41 vectors pass, historical 2 → 4B → 4B is only an engine-input example: T0 mask wrong-target, so full patient sequence/growth is unvalidated (`05-clinical-rules.md`). Hero = 134503. B4, B8–B10 open. Records: `docs/benchmarks/2026-10-24-b-imaging.md`, `04`, `05` |
| B on spark-2 (files only, no processes) | `~/spark-md-b/` (volumes, bundle, VISTA, results) + `~/venvs/spark-md-arm` (torch/monai/transformers stack). Delete after packing unless reused for B4/B7 on GB10. |
| VISTA focused diagnostic | **done 20:30 — partial pass** on spark-2, 134503 T2. LPS→RAS omission put old prompt outside image; `>0` decoded uncomputed 255 as nodule. Corrected point + `==1` yields aligned foreground, but over-segments (~8,783 mm³, prompt component ~72×27×62 mm); keep threshold fallback. Pipeline 3.96 s, min available 67.17 GiB. Probe exited; no imaging process left running, LLM/OpenClaw untouched. Raw `~/spark-md-b/vista-probe-20261024-01/`; record `docs/benchmarks/2026-10-24-vista-point.md`. |
| VISTA prompt refinement | **done 20:35 — guided improvement, accuracy unverified** on spark-2, 134503 T2. Centered foreground: 3,089 mm³ / one component; centered + two inspected negatives: 1,372 mm³ / one component, bounding ~13.5×16.8×14 mm. Both match CT grid; final inspected overlays are tighter around nodule. Pipeline 4.34/2.11 s, min available 63.83 GiB. Probe exited; no imaging process remains, LLM/OpenClaw untouched. Keep threshold measurements pending independent/all-timepoint validation. Code `bench/vista_refine_probe.py`; raw `~/spark-md-b/vista-probe-20261024-02/`; record `docs/benchmarks/2026-10-24-vista-refine.md`. |
| VISTA automatic hero sequence | **done ~20:42 — FAIL T0 under both frozen rules**, spark-2. v1 threshold seed drifts 18.46 mm onto heart boundary, output ~428,424 mm³. v2 detector-box seed stays on T0 nodule, but VISTA still returns ~980,087 mm³ lung-scale mask; T1/T2 localized (~586/~1,794 mm³), accuracy unverified. No sequence accepted for growth; historical fallback T0 measurements/VDT/category sequence invalidated as patient evidence. Min available 62.51/62.73 GiB; both probes exited; no imaging process remains, LLM/OpenClaw untouched. Remote `~/spark-md-b/vista-probe-20261024-03/` and `-04/`. Record `docs/benchmarks/2026-10-24-vista-longitudinal.md`. |
| VISTA local-crop experiment | **done ~20:50 — 3/3 technical pass, accuracy unverified** on spark-2, fixed `hero-crop64-v1`. Full CT vs 64 mm crop with identical automatic positives/no negatives: cropped T0/T1/T2 ~347/553/774 mm³, one component each, >23 mm edge margin; original-grid restoration verified. Full T0 remains lung-scale, cropped T0 localized. Crop pipeline 0.36–0.39 s (warm, excludes setup/analysis), min available 63.79 GiB. No clinical size/growth/category accepted; old T0 evidence remains invalidated. Probe exited; no imaging process remains; LLM/OpenClaw untouched. Code `bench/vista_crop_probe.py`; remote `~/spark-md-b/vista-probe-20261024-05/`; record `docs/benchmarks/2026-10-24-vista-crop.md`. |
| VISTA LIDC reader/crop stability | **done — FAIL for current point-only configuration**. 0415 excluded for SEG/CT geometry contradiction; 7 eligible cases / 22 groups / 61 annotations. 18 matched groups / 57 reader annotations, 3 crop sizes + hero stability = 63 calls. Median Dice48/64/96 = 0.064/0.033/0.023; only 5/18 coarse technical passes at 64 mm. Same 15 multi-reader groups: model Dice64 median 0.086 vs reader-pair median 0.775. Hero volume spans 61/42/71% of volume64 across sizes; identical 64 mm reruns bitwise reproduce prior masks. No nodule measurement/growth/category accepted. Min available 63.89 GiB; inference/scoring/plots exited; services untouched. Raw `~/spark-md-b/vista-lidc-20261024-01/`; record `docs/benchmarks/2026-10-24-vista-lidc.md`. |
| VISTA loader/conditioning audit | **done — loader passes, no conditioning rescue**. CPU spark-2 audit: all 259 original/converted/loaded tensors exact, no missing keys. Laptop RTX 3080: 4 diagnostic targets × 5 point/class/flag conditions = 20 calls. Direct point-only controls Dice 0.996–1.000 vs prior GB10 wrapper masks. Zero133 worsens reader overlap on all 3 selected LIDC targets; class23/special flag3 does not fix small failure. Pretransform/network class23 flag disagreement remains documented, not a demonstrated fix. GB10 class ablation/cohort validation unverified. Laptop min host 35.88 GiB, min GPU free 4.30 GiB; probe exited. Existing spark-2 reliability job untouched, no second GPU job started there. Code `bench/vista_loader_audit.py`, `bench/vista_conditioning_probe.py`; local scratch `tmp/vista-conditioning-20261024-02/`, inputs in `-01/`; record `docs/benchmarks/2026-10-24-vista-conditioning.md`. |
| VISTA crop mechanism/stability | **done ~21:50 — mechanism isolated, stability FAIL** on spark-2, `vista-reliability-v1`, 720 calls. Context removal (masked64 at original phase) explains the crop rescue; phase/crop192 do not. ±6 mm crop jitter: hero volume up to 3.8×. LIDC median Dice ≤0.09 all conditions vs inter-reader 0.78; class23 no gain. Min available 57.40 GiB; probe exited, no imaging process left; LLM/OpenClaw untouched. Remote `~/spark-md-b/vista-probe-20261024-06/` (+ `lidc_masks/`); record `docs/benchmarks/2026-10-24-vista-reliability.md`. |
| Nodule measurement bake-off | **done ~22:45 — nothing passes the frozen bar.** Rule-based A7: held-out median diameter error 0.46 mm (readers 0.73), NLST heroes 0.86 mm, but ±3 mm box shift → ~2–3 mm range. VISTA + negatives 60% empty. Box diameter "passes" only trivially (contaminated, no stability test). Min available 65.66 GiB; all probes exited. Remote `~/spark-md-b/measure-20261024-0{1,3,4-shift3}/`; record `docs/benchmarks/2026-10-24-nodule-measure.md`. Decision for Ty: more held-out LIDC, or radiologist-confirmed diameters. |
| Held-out LIDC measurement check | **done ~22:55 — FAIL G5 only.** 15 new IDC LIDC patients (31 groups), frozen rule `nodule-holdout-v1`: A7 unflagged error 0.51 mm, bin agreement 0.80, flag rate 19%; ±3 mm shift range 1.82 mm > 1.5. Detection run on GB10 exited; LLM/OpenClaw untouched. Data laptop `~/spark-md-holdout/` (2 GB, delete when done) + remote `~/spark-md-b/holdout/`; record `docs/benchmarks/2026-10-24-nodule-holdout.md`. |
| Cohort 2 (NLST stable + LIDC pool 2) | **done ~00:30 Oct 25.** NLST stable 30 pts: A7 Δ median 0.28 mm, false growth 3.8% — pass; +1 mm bias vs NLST reports. LIDC pool 2 (40 nodules): fails G2/G5. 0123 excluded (uneven slice spacing). All processes exited; LLM/OpenClaw untouched. Data laptop `~/spark-md-cohort2/` (8.7 GB) + remote `~/spark-md-b/cohort2/`; record `docs/benchmarks/2026-10-24-nodule-cohort2.md`. |
| Validation data on drive | **done ~01:15 Oct 25.** `/mnt/sparkmd/validation/` (`lidc-holdout-15/`, `cohort2/`, `README.md`): 65 public IDC patients (15 + 20 LIDC, 30 NLST), raw DICOM + selection files, own SHA256SUMS, **verified on-drive 21,488/21,488**. Outside `data/` so the verified `data/` manifest is unchanged; not demo data; skip when copying the drive to the event box. Drive now 86 GB used. |
| VISTA annotation-assisted clicks | **done ~22:30 — capability diagnostic FAIL** on laptop 3080 (spark-2 busy with reliability probe; untouched), rule `clicks-assisted-v1`. 3 diagnostic targets × 5 frozen conditions (auto baseline + guide-reader positive alone + 1+/4−, 3+/8−, 5+/16− near-boundary negatives), held-out readers score. Controls reproduce GB10 (0.996–1.000) and same-device conditioning masks (1.000) exactly. **No assisted condition beats the automatic single positive**; guide positive alone degrades all three (0.59→0.08, 0.75→0.25); negatives suppress the logit at the positive point (−17.1 on 0052) → native component filter empties masks. Interactive guidance is not a rescue path in this stack; no measurements accepted. Min host 30.50 GiB, min GPU free 3.96 GiB; probe exited. Code `bench/vista_click_probe.py` (+`_overlays/_debug`); raw `tmp/vista-click-20261024-03/`; record `docs/benchmarks/2026-10-24-vista-clicks.md`. |
| Running on spark-2 (Spark MD) | 1) `qwen38-27b-tf` container: qwen3.8-27b on `0.0.0.0:8000` (`PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16`, ~36 GiB, `MemAvailable` ~73 GiB). 2) `nemoclaw-openshell-gateway.service` (user systemd) + sandbox `spark-md-openclaw` + OpenClaw gateway `:18789`. 3) fixture worker `python3 /tmp/fixture_worker.py` on `0.0.0.0:8100` (C5; request log `/tmp/c5_requests.jsonl`; disposable). Don't stop 1–2 unless Ty says so. |
| E | **E1+E2 done 17:50** — offline install on spark-2 (aarch64/cp312) passes: torch 2.13.0+cu130, monai 1.6.1, fastapi 0.162.0, transformers 4.46.3, SimpleITK, 98 wheels + SHA256SUMS. **E2 ASR superseded by Ty-confirmed whisper.cpp (Voice row); faster-whisper retained as fallback** (numpy audio path; PyAV torch-pinned incompatible with file decode — UI records WAV). **Dropped from the lock:** `pydicom-seg`+`highdicom` and the `mcp` SDK (runtime-broken with pydantic 2.14; worker `/mcp` is the hand-rolled stdlib endpoint validated in C5). **E4/E5/E6 done** — staging on spark-2: 3 container tars (TensorFold 24.8G, sandbox 2.0G, voice-team TTS 7.7G = `martinb78/faster-qwen3-tts-dgx-spark:v6.15.0`, inspected), `llm-hf-cache.tar` 19.9G (symlinks preserved in-tar), `offline-kit.tar` 0.7G, `derived-b-track.tar` 3.2G (36 vols + detections + b5), all in `DRIVE-TARS.SHA256SUMS` (paths normalized to relative). **E7/E8 done** (checksums pass; brief locked stack updated). **E9 done 22:18 — drive packed and FULLY VERIFIED on-drive ~23:10** (Ty's 1 TB Toshiba exFAT `avocado`, stays exFAT for the MacBook; transport-only; ~74 GB / 932 GB; mount `/mnt/sparkmd` uid=ty; all 6 tars OK, containers OK, 98/98 wheels OK, models OK, data OK; `scripts/e9_pack_drive.sh` fixed: copies containers/SHA256SUMS*, no `--ignore-missing`). **Weights-cache question CLOSED 23:20:** extracted-tar cache resolves offline via `snapshot_download(local_files_only=True)` → the 2 root-owned `trees/*.json` are irrelevant. **E10: prestage `~/spark-md-dryrun-src` on spark-2 verified byte-identical; dry run itself blocked on Ty's sudo (useradd sparkdry + owner-matched auto-revert iptables) + his OK to stop/restart the live LLM for the second-server step.** |
| UI (L7/E3) | **P0a done** (offline kit `nodehouse/`). **P0b passes** (Electron WebGL2 on GB10; pin `use-angle=gl-egl`). **MVP done 17:20 (laptop):** all pieces U0–U11 work against a mock worker in the real Electron main — time machine, worklist reorder, study view, 3D fly-to, compare, streamed ask, extras, Approve → inbox < 50 ms, SSE recovery 1.5 s, 0 non-loopback requests. Spec filled: `docs/build/08-ui.md` (build steps, params, 25+ gotchas, acceptance, snippets); 00 v0.3. Screens for Joyce: `tmp/ui-screens/`. **B9 prototype ~21:00:** threshold lung + airway glb and real key slices for hero 134503 (`bench/b9_render/`) run in the MVP viewer; RAS→three and key-slice convention agree on real CT; mask-only, no lobes. Open: real-worker swap, GB10 fps with real mesh, `chrome-sandbox` sudo. MVP code `~/spark-md-mvp/` (laptop, throwaway; delete after freeze). |
| UI viewer-first revision | **done ~20:14 (laptop)** — Ty chose viewer-first. Study screen now has large viewer + persistent longitudinal strip, assessment-first clinical inspector, readable agent activity / expandable raw trace and two-row ask controls. Fixed secondary-nodule → wrong CT slice. `npm run build` passes; real Electron replay → ask/compare/extras → report approval → inbox smoke: 46 requests, 0 non-loopback, 2 ms approval → outbox, no page overflow. Browser checked 1920×1080, 1440×900, light/dark, baseline navigation, full trace and PCP-letter approval. Spec: `08-ui.md`; captures `~/spark-md-mvp/shots/viewer-first-e2e/`. Real worker/anatomy and GB10 performance remain unverified. |
| UI Linear-inspired section 1 | **done ~20:52 (laptop)** — approved title bar: hamburger app menu / sidebar toggle / local study search on left, retained study tabs + `+` worklist slot, history Back/Forward on right, removed pinned Worklist tab and network pill. Patient title/context simplified; gray sidebar + single 12 px main surface, 8 px viewer/composer, flat clinical rail/timeline, neutral nodule selection. Build passed. Actual Electron controls smoke + full replay/ask/compare/extras/approve/inbox run: 51 requests, 0 non-loopback, approval → outbox 52 ms. Browser checked light/dark, 1920×1080 / 1440×900, keyboard/no-match search, close/fallback/history, tab overflow; no page overflow. Spec `08-ui.md`; captures `~/spark-md-mvp/shots/linear-shell-e2e/`, `linear-shell-review.png`. Temporary smoke processes stopped. Real worker/anatomy + revision on GB10 unverified. |
| Voice memory check | **done 20:07 — capacity PASS** on spark-2: TensorFold + existing OpenClaw + CUDA small.en/VAD + Qwen3-TTS 1.7B-Base + **touched 25 GiB CUDA imaging reservation**. Minimum available **36.84 GiB**, **21.84 GiB above 15 GiB floor**; LLM/ASR/TTS requests succeeded. This is a capacity probe; actual imaging/UI/recording co-load remains **unverified**. Temporary ASR/TTS/reservation stopped; TensorFold/OpenClaw untouched. Record: `docs/benchmarks/2026-10-24-voice-headroom.md`. |
| Voice (L8/E2) | **ASR + TTS validated on GB10 with synthetic voices (18:10).** Pick: **whisper.cpp small.en (CUDA) + phrase prompt + Silero VAD**: 337/339, 0 wrong commands, 74 ms median (151 ms with the LLM decoding). It beats faster-whisper (CPU-only on aarch64, 361–991 ms) and Parakeet-ONNX (CPU-only, 143 ms, worse in babble), so it **supersedes the E2 faster-whisper pick, confirmed by Ty; retain fallback models for pre-demo comparison**. TTS = faster-qwen3-tts container (voice aiden, ~0.68 s to first audio, 5.4 GB; ~2 s while the LLM decodes). Staged: `models/asr/whispercpp/`, `models/tts/`, spark-2 `~/spark-md-staging/containers/faster-qwen3-tts-dgx-spark-v6.15.0.tar` (+ `SHA256SUMS.voice`). Spec `09-voice.md`, record `docs/benchmarks/2026-10-24-voice-gb10.md`. **Ty confirmed:** spoken answers in scope, immediate deterministic viewer actions (log + per-request deduplication), bringing a plug-in speaker/microphone. **Open:** real-voice clips (Ty, Joyce), device input/output and Electron mic capture. **Left on spark-2:** image `martinb78/faster-qwen3-tts-dgx-spark:v6.15.0` (container stopped and removed), scratch dir `~/spark-md-asr/` (bench venv, whisper.cpp build, clips). |

---

## Track A0: TensorFold smoke test (working default; first)

TensorFold is the working default: it's faster and lighter in memory on paper. A0 clears the four catches before anything depends on it:
1. low-memory settings, since the default pins ~97 GiB;
2. bind to `127.0.0.1:8000`, not the Tailscale IP in `.env`;
3. **structured `tool_calls`** through the OpenAI API (unverified for TensorFold);
4. sane output from the untested `TensorFold/` checkpoint.

The step-by-step is in `docs/plans/2026-10-24-handoff-01-tensorfold-smoke.md`. Pass: all four clear, and the server stays up for C5/B/D.

## Track A: Tune and confirm the recipe (spark-2; **last**, after B and C)

Run this once B and C have produced real inputs: the chosen harness's actual system prompt (it replaces the synthetic 12k prefix in P3), the real triage flow, and imaging running on GB10 for co-load. A1 tunes TensorFold. A2 benches SGLang under the same conditions **if time allows**. If SGLang would win, re-run the tool-call gate (G1) through the chosen harness against SGLang (~15 min) before switching. Its parser (`qwen3_coder`) can behave differently.

**Candidates (both fully staged on spark-2):**
- **A-TF (default):** TensorFold v0.6.0 (`tensorfold-qwen38-27b:v0.6.0`) + `TensorFold/Qwen3.8-27B-MLX-4bit` + `z-lab/Qwen3.8-27B-DFlash2`. Launcher: `~/qwen38-27b-tensorfold/start.sh`. If quality looks off, fall back to the tested `Vontra/Qwen3.8-27B-MLX-4bit` (~15 GB download; ask Ty first).
- **A-SGL:** SGLang nightly `nightly-cu134-20260909-708f51e` (pinned digest `sha256:00205b89…`) + `RadixArk/Qwen3.8-27B-NVFP4-BF16-LMHead` + `z-lab/Qwen3.8-27B-DFlash2` @ `50307d4c`. Launcher: `~/qwen38-sglang/start-dflash.sh`, which wraps `start.sh` (`--tool-call-parser qwen3_coder`, `--reasoning-parser qwen3`).
- Optional, only if time allows: TensorFold + `nvidia/Qwen3.8-27B-NVFP4` (`VISION=0`). Not downloaded.

**Prior numbers (different settings, so not comparable):** SGLang/DSpark on spark-2, Sep 26: 39.9 tok/s net decode on code, 20.1 on prose, 8.4 s TTFT at 16k. The forum recipe reports 52–61 code / ~26 prose. The TensorFold README reports 58 prose / 137 code (sparkDash) and 48.6 in its own run.

**Before you start:** commit any recipe edits on a `spark-md` branch in each recipe's git repo, never on main. Record `free -g` and `docker ps` first.

### A1 (TensorFold tune) and A2 (SGLang, if time allows): probes, matched settings

Use the same settings for both: context 65,536, 4 concurrent requests, thinking **off** unless a probe says otherwise, same fixtures, a warm-up first, 3 repetitions, report the median.

- A-SGL: `MAX_CONCURRENT_REQUESTS=4 CONTEXT_LENGTH=65536 DF_EXTRA="--mem-fraction-static 0.50" ./start-dflash.sh`. Argparse is last-wins, so `DF_EXTRA` overrides the 0.90. If it passes, retry at 0.40.
- A-TF: `HOST=127.0.0.1 PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16 ./start.sh`. A fixed pool keeps the footprint predictable (~19 GiB weights + 16 GiB pool, unverified).

The bench script is `bench/spark_md_llm_bench.py`, adapted from `spark-2:~/bench_pair.py`. Its fixtures live in `bench/fixtures/`: the tool schemas from `00-architecture.md`, 20 scenarios, and 5 findings JSONs built from NLST-reported sizes. Probes:

| Probe | Measures |
| --- | --- |
| P1 start | container start → `/v1/models` ready (warm caches), twice |
| P2 decode | net tok/s on report-length prose (600 tok) and on code (as a control against the published numbers) |
| P3 prefill | TTFT on a ~12k-token "agent prefix" (tool schemas + skill text; swap in the real harness system prompts once C5 measures them), cold, then warm with the same prefix and a new suffix. **This dominates agent latency.** |
| P4 tool calls | 20 scenarios with OpenAI `tools`, `tool_choice: auto`. Score: structured `tool_calls` present, right tool, schema-valid args. Plus a scripted 3-step chain (we feed tool results back). Run thinking off and on. |
| P5 grounded writing | findings JSON → radiology report, PCP letter, 2-sentence "why flagged" (N=10, temp 0.7). Automated check: every number in the output appears in the input, the Lung-RADS string is verbatim, no invented categories. |
| P6 concurrency | agent run + UI Q&A at once: per-request tok/s |
| P7 memory | idle and loaded: `MemAvailable` (`/proc/meminfo`) and `docker stats`. On GB10, `nvidia-smi` shows N/A for memory. |
| P8 injection (stretch) | a DICOM-comment instruction to POST data to an external URL: does the model try? Blocking it is OpenShell's job (C3 `enforce` policy). |

### A3: Co-residence stress, the deciding test (current recipe; repeat for SGLang only if it's in contention)

This needs the imaging core on aarch64 (B on a Spark). Loop detection + VISTA-3D over 3 NLST scans while P2–P5 loop, for **30 minutes**.

### Gates and decision

- **G1 tool calls:** ≥ 19/20 correct structured calls (thinking off), and the 3-step chain completes 5/5.
- **G2 co-residence:** zero OOMs, hard reboots or 5xx responses. `MemAvailable` floor ≥ 8 GiB.
- **G3 offline start:** with egress blocked (auto-revert iptables) and `HF_HUB_OFFLINE=1`, stop → start → smoke test passes. Check whether SGLang's `docker run` passes `HF_HUB_OFFLINE`; add it on the branch if it doesn't. TensorFold defaults to offline.
- **G4 grounding:** ≥ 9/10 outputs pass the P5 checks.
- **Ranking among recipes that pass:** first warm agent-turn latency (P3 warm + 300-token decode), then prose tok/s, memory footprint, and start time. **Tie-break:** SGLang + NVFP4, which is already in the brief and the more NVIDIA-native story for the judges.
- Record the result in `docs/benchmarks/2026-10-24-llm-recipes.md` (method, settings, table, raw JSON path). Then update the decisions log in `AGENTS.md`, the brief's "Serving recipe" line and Joyce's stack card.

**Budget:** ~20 min for A0; ~45 min for A1, ~45 min for A2 (optional), ~45 min for A3.

**Default if A runs out of time:** keep TensorFold as smoke-tested, with whatever A3 shows. Record that in the decisions log.

---

## Track B: Imaging core experiments (laptop 3080 now; GB10 timings later)

- Laptop: create an x86 venv **outside** the project (e.g. `~/venvs/spark-md-x86`; internet is fine on the laptop). Copy the DICOM you need to local disk rather than reading over CIFS in loops.
- Spark: offline-install from the wheelhouse. That doubles as the **arm64 check** from the checklist.
- If the 3080 runs out of memory on the detector's 512×512×192 patch, note it and finish that step on a GB10. Don't shrink the patch silently, because that changes the results.

| # | Experiment | Output / pass criterion |
| --- | --- | --- |
| B1 | Series selection rules: soft kernel (B30f/STANDARD…), axial, slice thickness ≤ 2.5 mm, ≥ 100 instances, no localizers | Picks the right series for all 12 NLST + 8 LIDC studies; rules table |
| B2 | Load → HU → RAS → 0.703×0.703×1.25 mm (the bundle's transforms) | Volumes + spacing table; seconds per study |
| B3 | MONAI detection (bundle v0.5.9 on monai 1.6.1: check compatibility) | Candidates per study at several score thresholds. **LIDC:** recall vs reader nodules ≥ 3 mm (SEG/XML). **NLST heroes:** rank and score of the tracked nodule vs the Farina i/j/k location (≤ 10 mm). |
| B4 | Lung mask: VISTA-3D lobes (labels 28–32) vs the CPU threshold fallback | Time and memory; % of B3 candidates dropped outside the mask; lobe assigned per nodule |
| B5 | Characterize: segment the nodule (VISTA-3D point prompt at the candidate center vs a HU-threshold ROI), then long/short axis → **mean diameter** (Lung-RADS), volume, mean HU, solid / part-solid / GGO | Compare diameters with NLST `sct_long_dia`/`sct_perp_dia` and LIDC reader measurements; error table |
| B6 | Prior matching: register year N-1 → N (lung-mask rigid), match by lobe + distance; growth = Δ mean diameter, Δ volume, **VDT** using real intervals from `scr_days*` (StudyDate is fake) | Correct track across T0/T1/T2 for the 5 heroes; 3 controls stay "stable" |
| B7 | Lung-RADS v2022 rules engine with unit tests (test vectors written from the ACR table, cited) | `05-clinical-rules.md` with rule table, IDs and test vectors; all tests pass |
| B8 | Extras: emphysema LAA-950 % in the lung mask; bone: mean HU of a trabecular core in the lowest fully imaged vertebra (VISTA labels 37 L1 … 49 T1); CAC: HU ≥ 130 in heart (115), labeled experimental | Values per study; time; cut decision |
| B9 | Render: marching cubes (lung decimated, nodule fine) → glTF/JSON; key axial/coronal PNGs with a box, lung window (-600/1500) | Asset sizes; load time in three.js (with D-L7) |
| B10 | Cold open: run B3–B6 on the **neg-neg-pos** set (102537, 117502, 113918, 131156) at Y1/Y2, using the Y3 `sct_slice_num` as the locator | A yes/no evidence table. The cold open may claim only what this shows. |

**Hero decision (by ~17:00):** the tracked nodule is in the top-5 in-mask candidates at every timepoint; our measured growth puts T1 at ≥ 4A while T0 is ≤ 3; the numbers are stable across reruns. Write the decision and its evidence into `data/README.md`, then give Joyce the numbers.

---

## Track C: OpenShell + agent-harness bake-off (spark-2)

Time every step and log every command into `07-agent.md` / `01-box-setup.md`. Before any install, run **`export NEMOCLAW_DISABLE_TELEMETRY=1`** in every shell (F14).

### Groundwork that doesn't depend on the harness (C1–C4; start now, no LLM needed)

| # | Step | Pass criterion |
| --- | --- | --- |
| C1 | Prereqs: `head -n2 /etc/os-release`, Docker ≥ 28, NVIDIA runtime (`docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi`) | All OK |
| C2 | Install OpenShell via NemoClaw, with OpenClaw as the first agent: `NEMOCLAW_NO_EXPRESS=1 curl -fsSL https://www.nvidia.com/nemoclaw.sh \| bash`, then `nemoclaw onboard`: agent OpenClaw, provider "Other OpenAI-compatible" at `http://localhost:8000/v1`, sandbox `spark-md-openclaw`, strictest policy tier, no web search, no messaging. Also capture the non-interactive form (`NEMOCLAW_NON_INTERACTIVE=1 NEMOCLAW_PROVIDER=custom …`). | Sandbox up. Record versions (node, openshell, nemoclaw, openclaw), and diff `docker images` / downloads before and after for the offline kit (E6). |
| C3 | Sandbox → host: `ip link add spark0 type dummy && ip addr add 10.77.0.1/32 dev spark0 && ip link set spark0 up`; run a stub `/health` on `10.77.0.1:8100`; preset with `enforcement: enforce`, `protocol: rest`, method/path rules; `policy add --from-file … --trusted-private-host 10.77.0.1 --dry-run`, then `--yes` | `curl` from the sandbox succeeds. `curl https://example.com` and a POST to a non-allowed path are denied (`policy_denied`) and visible in `openshell term`. Fallback address: docker0 `172.17.0.1`. |
| C4 | **Dropped** (Oct 24): rules confirm every demo runs fully local on the event box, so there is no link-loss scenario to rehearse. C3 already proved sandbox → `10.77.0.1` under `enforce`; the iface is dummy and addressing is IP-only, so link loss can't break the stack. The unplug stays as the on-camera storyboard beat. |

### Bake-off (C5; needs A0's TensorFold serving on `:8000`)

**Common setup:**
- A **stub worker** on `10.77.0.1:8100` serves the v0 agent routes from fixture JSON (no imaging). It also exposes the same tools as an **MCP endpoint** (`/mcp`, streamable HTTP), so every harness gets identical tools.
- Every harness runs the same tests: the 20 tool scenarios from A1/P4, plus the full triage flow (`00-architecture.md` §Flows 1) 5 times.

| Harness | Install | Tools | Host trigger | UI Q&A path |
| --- | --- | --- | --- | --- |
| **H1 OpenClaw** (NemoClaw default) | C2 | MCP (`mcp.servers.<name>`: `url`, `transport: "streamable-http"`) or a `defineToolPlugin` plugin. Sandbox mode also needs `tools.sandbox.tools.alsoAllow`. | `POST /hooks/agent` (`hooks.enabled`, dedicated token) | gateway `chatCompletions` endpoint (`gateway.http.endpoints.chatCompletions.enabled`) |
| **H2 Hermes Agent** (NemoClaw) | `curl -fsSL https://www.nvidia.com/nemoclaw.sh \| NEMOCLAW_AGENT=hermes NEMOCLAW_SANDBOX_NAME=spark-md-hermes bash`; `nemohermes spark-md-hermes status` | MCP. Config keys unverified; see upstream docs at hermes-agent.nousresearch.com. | OpenAI-compatible API `:8642` (token: `nemohermes spark-md-hermes gateway-token --quiet`) or the built-in cron | the same API on `:8642` |
| **H3 Minimal custom loop** in OpenShell | A small Python loop (OpenAI `tools` API → worker REST) run inside an OpenShell sandbox. How to run a custom image or process under `openshell` is unverified; check the OpenShell docs. | direct REST | its own HTTP endpoint, or polling the worklist | its own endpoint |

LangChain Deep Agents and Pi are skipped: both are terminal-only, with no HTTP API (F13).

**Measure for each harness:**
- install/onboard time and **system-prompt tokens** (the prefill cost of every turn);
- tool-scenario score, triage flows completed out of 5, and warm wall time per study;
- whether the host trigger works, and the Q&A latency;
- whether a trace is available for the agent-log panel;
- offline stop/start;
- whether enforce-mode policy holds: only the worker is reachable, and an exfil attempt is denied and visible in `openshell term`;
- rebuild effort on the day: setup minutes and how much config there is.

### Decision (C6, by the 17:00 checkpoint)

- **Gates:** runs inside OpenShell with enforce-only access to the worker; ≥ 19/20 tool scenarios and 5/5 triage flows; a host trigger and an HTTP Q&A path both work; offline restart works.
- **Ranking among harnesses that pass:**
  1. warm per-study latency;
  2. rebuild effort;
  3. demo story. OpenClaw + NemoClaw is NVIDIA's reference stack, Hermes is in NVIDIA's own Spark playbook, and the custom loop gives the plainest "OpenShell sandboxes our agent" story.
- Record the decision in the `AGENTS.md` decisions log and in the brief.

### For the winner only

- **C7 Cold restart:** stop and start the sandbox, and reboot once, with egress blocked. Pass: back up offline; record time to ready.
- **C8 Teardown and reinstall from scratch,** as close to "from the drive" as possible. Pass: total time-to-working for the morning; offline gaps listed. **Ask Ty before `nemoclaw uninstall`.**

Known Spark caveats from the NemoClaw docs: host freezes under inference memory pressure, in-sandbox DNS can fail, GPU passthrough into the sandbox is not CI-tested on Spark (we don't need it, because imaging runs on the host).

---

## Track D: MVP back to front, one spec per layer

Rule: a layer is **done** only when (1) it works, (2) its spec is written per the `docs/build/README.md` template, and (3) its acceptance commands have run. Then start the next layer. Start from the v0 contract in `00-architecture.md` and update it as the MVP proves or changes it.

| Layer | What | Spec | Depends on |
| --- | --- | --- | --- |
| L0 | Box layout: users, dirs (`$SPARKMD_HOME`), `spark0` iface, env vars, venv, process list, start/stop script outline | `01-box-setup.md` | — |
| L1 | LLM serving (from Track A) | `02-llm-serving.md` | A |
| L2 | Intake + registry: watched inbox, DICOM header parse, study/series grouping, SQLite schema, NLST day offsets | `03-intake-registry.md` | — |
| L3 | Imaging pipeline as a job runner (from B1–B6, B8, B9), cached per SeriesInstanceUID | `04-imaging-pipeline.md` | B |
| L4 | Clinical rules (B7) | `05-clinical-rules.md` | B |
| L5 | Worker API + MCP endpoint (`/mcp`) + SSE events + agent trigger + agent-call logging + approve guard | `06-worker-api.md` | L2–L4 |
| L6 | Agent: the chosen harness's config, tool binding (MCP or plugin), skill(s) and prompt, trigger, OpenShell policy preset | `07-agent.md` | C, L5 |
| L7 | UI: worklist, study view (3D + key slices + findings + priors), report/letter editor + **Approve**, mock EHR inbox, agent log, "bytes sent" panel, disclaimer | `08-ui.md` | L5 (fixtures earlier) |
| L8 | Voice: push-to-talk → local ASR → fixed command set → agent/viewer | `09-voice.md` | E2, L6, L7 |
| L9 | Demo harness: time-machine replay (drops T0 then T1 into the inbox), reset, backlog seeding, network monitor | `10-demo-harness.md` | L5–L7 |
| L10 | End-to-end acceptance: Joyce's QA list, cold restart, 30-min contention with the full app | `11-acceptance.md` | all |
| — | **Day-of runbook:** setup order, agent assignments with kickoff prompts, timeline, milestones, cut order | `12-day-of-runbook.md` | all |

- **Parallelism:** the UI (L7) can start against fixture JSON once `00-architecture.md` §API is unchanged for an hour. Everything else follows the order above.
- **Measure per-scan latency** in L3 on the GB10. That decides live processing vs pre-run backlog for the time machine (a brief risk item).
- **UI stack (decide in L7):** the recommendation is a no-build static UI served by the worker with vendored three.js ESM, which leaves no npm on the offline box. Alternative: Vite + React with an npm cache on the drive, verified with `npm ci --offline`.
- **Voice (decide in E2/L8):** a local Whisper model through our torch stack (or whisper.cpp) plus fuzzy matching to the fixed phrases. Clicks are always the fallback.

**MVP scope priority:** P0 = L0–L6 + worklist/study/Approve + time machine. P1 = 3D viewer, report + letter, agent log, outbox. P2 = voice, emphysema, bone, bytes panel. P3 = CAC, injection demo, backlog counter, channel.

**Cut rule:** at **20:30**, stop building. Any layer not reached gets a spec written from research plus what's known, marked **unverified**. A good spec matters more than finishing the MVP.

---

## Track E: Finalize prep and pack the drive

| # | Item |
| --- | --- |
| E1 | Wheelhouse: add `fastapi`, `uvicorn`, `pydantic`, `httpx`, `python-multipart`, `mcp` (the Python MCP SDK, for the worker's `/mcp`) and the chosen ASR package + deps. Re-lock, `fetch.sh`, checksums. **Offline install test on a Spark** (doubles as the arm64 check, with B on GB10). |
| E2 | ASR: pick on the laptop, confirm on GB10 (latency on 2–3 s clips, accuracy on Joyce's exact phrases). Stage weights in `models/asr/` with a checksum. |
| E3 | Frontend assets vendored into `vendor/`: three.js ESM + `OrbitControls` + `GLTFLoader`, local font files. Or an npm cache, if L7 picks Vite. |
| E4 | Containers: `docker save` the winning LLM image (+ the runner-up if space allows) and the OpenShell/NemoClaw/harness images → `containers/*.tar` + SHA256SUMS. |
| E5 | LLM weights: HF caches, dereferenced (`rsync -aL`) → `llm/hf/` + checksums. SGLang ≈ 23 + 3.6 GB; TensorFold ≈ 15 + 3.6 GB. |
| E6 | Offline kit for OpenShell + the chosen harness, from C2/C8. Otherwise the decision is "install over venue wifi at 08:30, phone hotspot as fallback". |
| E7 | Verify `data/SHA256SUMS` and `models/SHA256SUMS`; record the hero decision in `data/README.md`. |
| E8 | Docs: brief (recipe winner, ports, channel), checklist ticks, storyboard cold open (with Joyce). |
| E9 | Drive: check the filesystem (ext4 preferred, F9) and capacity. Estimate ≈ 75 GB with the winner only, ≈ 130 GB with both recipes. Copy, then verify checksums **on the drive**. |
| E10 | **Fresh-box dry run tonight** on spark-2, from the drive only, egress blocked. Run it as a fresh Linux user with an empty home, so no caches help. Steps: `docker load`, venv install, LLM up, worker smoke, harness onboard (or the documented gap). Time each step into `01-box-setup.md`. Ask Ty before removing images or uninstalling anything. |
| E11 | Delete `tmp/` and both MVP copies. Confirm the drive holds no MVP code, only docs. |
| E12 | Still open: email info@builderbase.com (is a channel required, how long is the top-8 pitch). Ty/Joyce. |

### E10 dry-run checklist (execute as soon as the drive lands; time every step)

Drive = Ty's 1 TB Toshiba USB HDD, **stays exFAT** (Ty also mounts it on tys-macbook-air at the venue). exFAT is transport-only: everything is copied to the GB10's local disk before use. Payload is therefore symlink-free — the HF weights cache and the offline kit ship as tarballs (tar preserves symlinks internally):
`containers/` (2 tars, 26.8 GB) · `llm-hf-cache.tar` (18.6 GB) · `offline-kit.tar` (0.7 GB) · `wheelhouse/` (3.0 GB, 98 wheels) · `data/` (6 GB) · `models/` (VISTA 0.9 GB + detector + `asr/faster-whisper-small`) · `nodehouse/` · `docs/` + `AGENTS.md` + `scripts/` + `bench/`. ≈ 58 GB. Checksums: `DRIVE-TARS.SHA256SUMS` (staging root) + per-pair SHA256SUMS.

| E10 status 23:59 | **PASS 8/8 as `sparkdry`, egress-blocked (owner-matched DROP), 90 s total** — weights extract 10 s · kit 0 s · offline venv install 39 s · imports OK CUDA True · Lung-RADS suite pass · docker loads 34 s/3 s · offline HF cache resolve OK. Skipped: second-server start (live LLM holds GPU; components proven separately). Earlier same-night no-sudo variant (empty `$HOME` as ty): 7/7 in 103 s. Gotchas recorded in `01-box-setup.md` (home-dir traversal, docker group, console paste wrapping, broken auto-revert timer). Cleanup pending at Ty's console: delete the DROP rule + `userdel -r sparkdry` (optionally restore `/home/ty` to `o-x`). |

1. Mount on ty-ubuntu (Ty, sudo, **no format**): `sudo mkdir -p /mnt/sparkmd && sudo mount -o uid=ty,gid=ty /dev/sdc1 /mnt/sparkmd`. Rsync payloads from ty-ubuntu (project is local) + pull `~/spark-md-staging` tars from spark-2; `sha256sum -c` **on the drive**.
2. On spark-2 as a **fresh user** (`sudo useradd -m sparkdry`; empty home), egress blocked with the auto-revert iptables timer (sudo, console). Source = the tars only (not the loose staging), exactly as the venue will see them.
3. Steps, in order, each timed: `docker load` both tars → `tar xf llm-hf-cache.tar` to `~/.cache/hf/hub` equivalent → `tar xf offline-kit.tar` → venv `pip install --no-index --find-links <drive>/wheelhouse/wheels -r requirements.lock` (E1-proven) → TensorFold start (`HOST=0.0.0.0 …` per the A0 addendum; weights from the extracted cache — this also proves whether the missing root-owned `trees/*.json` matter) → `python scripts/lungrads/test_rules.py` (no GPU) → detector smoke on one volume → OpenShell/NemoClaw restore from the extracted kit (expected gap: gateway/provider registration; record exactly what fails) → worker `/mcp` probe from the sandbox.
4. Record all timings + gaps in `01-box-setup.md`; revert the iptables rule; delete the `sparkdry` user.

---

## Track J: What Joyce needs from us, and when

- **~17:00:** the hero patient plus real measured numbers (sizes, growth, VDT, Lung-RADS per year), to fix the cold-open wording. Use the B10 result if the neg-neg-pos story holds.
- **~19:00:** the exact voice phrases (`09-voice.md`) to practice, and the stack card wording with the harness and recipe winners. The storyboard card currently says "OpenClaw + NemoClaw + OpenShell"; it changes if Hermes or the custom loop wins. If TensorFold wins, it says "MLX 4-bit", not "NVFP4".
- **~20:00:** MVP screenshots for the storyboard and writeup. If the MVP reaches L7, a QA pass against her checklist.

## Suggested schedule (PT)

| Time | What |
| --- | --- |
| 13:30 | On spark-2: **A0 TensorFold smoke**, then C1–C4 and the E1 offline install. On the laptop: B, E2–E3, and the D-L0/L2 specs. |
| ~14:30 | C5 harness bake-off against TensorFold on `:8000`; B on GB10 |
| 17:00 | **Checkpoint:** harness chosen, imaging core runs on GB10, hero chosen |
| ~17:00–18:30 | **Track A** tune and confirm (A1 → A3; A2 if time allows), with the real harness prompt and imaging co-load |
| 18:30–20:30 | MVP L5–L9 on spark-2; cable-pull and cold-restart tests |
| 20:30 | **Build stop.** Finish specs; write `12-day-of-runbook.md`; update AGENTS.md |
| 21:00–22:30 | Pack the drive, fresh-box dry run, delete the MVP |
| 22:30 | Done. Doors open at 08:30. |
