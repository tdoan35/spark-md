# First GB10 run — hero T0 / G2

Status: **event-box CLI G2 passed T0/T1/T2, Oct 25** on the locked Linux aarch64 stack, alongside the running LLM. First T0 failed because only the detector network was in eval mode; setting the `RetinaNetDetector` wrapper to eval fixed real inference. All sizes remain proposals, with null accepted sizes/assessments. Full timings, every candidate and failure reason: [`gb10-g2-results.json`](gb10-g2-results.json). Actual UI alignment remains unverified (no local Chromium/build); original-grid target CT/mask/box crops were inspected, not clinical boundaries.

## 1. Box preparation (once)

Assumes the event repo is `$HOME/spark-md-app`, and the verified NVMe kit copy is `$HOME/spark-md-kit` containing `data/`, `models/`, and `wheelhouse/wheels/`. Set `SPARKMD_KIT` to the actual kit root if bring-up used another directory. Do **not** transfer the Mac `.venv`; create the Linux Python 3.12 venv on the box.

```bash
cd "$HOME/spark-md-app"
export SPARKMD_KIT="$HOME/spark-md-kit"
export SPARKMD_HOME="$HOME/spark-md-runtime"
export SPARKMD_MODELS="$SPARKMD_KIT/models"
export SPARKMD_BIND=127.0.0.1 SPARKMD_PORT=8100
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NEMOCLAW_DISABLE_TELEMETRY=1
unset SPARKMD_DB SPARKMD_FAKE_IMAGING SPARKMD_FAKE_SEED SPARKMD_HOOK_URL SPARKMD_HOOK_TOKEN SPARKMD_UI_TOKEN
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links "$SPARKMD_KIT/wheelhouse/wheels" -r "$SPARKMD_KIT/wheelhouse/requirements.lock"
.venv/bin/python -m unittest discover -s tests/rules -v
.venv/bin/python -m unittest discover -s tests/imaging -v
free -g
.venv/bin/python -m uvicorn sparkmd.app:app --host "$SPARKMD_BIND" --port "$SPARKMD_PORT"
```

Require `MemAvailable >= 15 GiB` (the runner enforces it). Keep the hook unset for this first smoke so an agent cannot race the manual series selection. If W's real worker is already running with the same home/models/env, use it instead of starting a second worker. Event deployment can bind `0.0.0.0` only after external interfaces are firewalled; this smoke/UI always uses `127.0.0.1:8100`.

## 2. G2: one command (second terminal, same exported environment)

```bash
.venv/bin/python tests/imaging/gb10_hero.py --source "$SPARKMD_KIT/data/dicom/nlst/134503"
```

The runner checks Linux aarch64 GB10, free memory, offline flags, locked package versions and real-worker mode; copies **T0 only** into the inbox without changing the source; waits for organization; selects **B30f, 2 mm, 151 instances**, series `1.2.840.113654.2.55.191672868291879989699384719070844674759`; runs the worker's real analysis; checks pending human confirmation, null accepted sizes/assessment, A7 proposals and downloadable key slices. It never confirms or approves. Success prints `"G2": "PASS"` and the study UID. Open the running UI on `http://127.0.0.1:8100` and visually inspect the proposal/mask alignment; a CLI PASS is not visual proof.

If a run failed, inspect its job/error/cache before retrying. The runner never resets a study, cancels a job, overwrites confirmed evidence or mistakes an existing result for a fresh run. A 300 s timeout does not stop the worker's job.

Event-box run used `~/.venvs/spark-md/bin/python`, `SPARKMD_KIT=$HOME/spark-md`, `SPARKMD_MODELS=$SPARKMD_KIT/models`, and isolated `SPARKMD_HOME=$HOME/spark-md-runtime-g2`. The original failed attempt remains in `$HOME/spark-md-runtime`; neither registry was reset. Run the command above sequentially with `--timepoint T0`, then `--timepoint T1`, then `--timepoint T2`, supplying the complete patient source root. The runner refuses existing completed/failed evidence, rather than treating it as a fresh run. Both smoke homes lack `day_offsets.csv`, so intervals remain unknown.

Original pipeline 0.2 run: all 18 candidates stayed visible/pending; 4 T1 and 3 T2 A7 proposals failed closed with `core_below_minus600_hu`. The highest-score hero linked T0→T1; T2 stayed unlinked with `incomplete_prior_geometry` (some prior candidates have no approximate lung/lobe frame). No confirmation, approval, growth, VDT or category was produced. The temporary smoke worker is stopped after evidence capture; caches/registries remain available for inspection.

### Admission update — pipeline 0.3.0

Rule announced to Ty before commit: register a confirmation nodule **iff `det_score >= 0.90`**, inclusive; no size cutoff, no top-k, no requirement that A7 succeed. This is a demo operating point, **not validated clinical sensitivity**; it can exclude true low-score lesions. Build/04 had no separate nodule-admission cutoff. Every raw detector candidate stays in `candidates.json` with stable ID, score, admission decision/reason and A7 result/failure reason; excluded candidates are also summarized in registry `agent_events`. Only admitted candidates get nodule rows, matching, key slices and confirmation requirements. An admitted A7 failure still requires manual measurement.

CPU replay of the real G2 cached volumes/detector outputs through the updated pipeline registers **T0/T1/T2 = 2/1/1**, versus original **3/7/8**; all 7 failed secondary proposals remain audit-only. The hero shares one track across all three studies; T1→T2 links at **3.737 mm**. Its original blocker came from excluded low-score priors with missing geometry. The matcher itself is unchanged: missing geometry on an admitted prior still blocks confidence, as do the distance, ambiguity and lobe-boundary gates.

Evidence: [`admission-replay-results.json`](admission-replay-results.json); imaging **30 passed + 1 Mac-only skip**, rules **10 passed**. No new GPU run, no live-worker restart and no existing registry/cache edits: W must load pipeline **0.3.0** before fresh analysis. Replaying cached detections is CPU integration proof, not fresh GPU/HTTP acceptance. Existing 0.2 studies retain their original confirmation counts and tracks.

### B9 render update — pipeline 0.4.0

Ty approved the first full **CPU-only cached render**; no detector/GPU calls, live-data resets, G3 edits or original G2 cache writes. The real worker HTTP analysis/assets routes passed using cached real volumes/detector outputs. Threshold surfaces use Gaussian sigma 1, marching cubes step 2 and Taubin smoothing; `lung.glb` has `lung_right`/`lung_left`. `nodules.glb` has one node/mesh per admitted `nodule_id`, with exact `(-R,S,A)` mm translation and detector-box ellipsoid geometry: **display markers, not measurements**. No recentering; extras remain null.

`findings.json.assets` retains `lung_mesh`, `nodule_mesh`, `key_slices`; optional `slice_stack` is the existing 08 addition, not a renamed 00 field. Cache-root files are `lung.glb`, `nodules.glb`, `mesh_stats.json`, `key_axial_<nodule_id>.png`, `stack_NNN.jpg`, `stack.json`. `key_slices[]` has `name,url,plane,nodule_id,box_px`. `slice_stack` has `count,spacing_mm,z_mm,size,url_pattern,index_digits,nodule_slices`; each nodule entry has `nodule_id,index,box_px,half_range`. Index 0 is most superior; `{i}` is zero-padded; `size=[width,height]`. Half-range uses detector depth, not an unconfirmed diameter. PNG/JPEG orientations and boxes share the original canonical grid. The asset route must retain `.jpg` support.

| Cached hero | Render stage seconds | Lung triangles | Admitted nodule mesh nodes | Axial JPEG count |
| --- | ---: | ---: | ---: | ---: |
| T0 | 0.245498 | 83076 | 2 | 151 |
| T1 | 0.218727 | 84132 | 1 | 158 |
| T2 | 0.214262 | 82256 | 1 | 152 |

All admitted A7 proposals succeeded; T1→T2 remains linked at 3.737 mm, with one hero track across all scans. Evidence: [`render-results.json`](render-results.json). Imaging **39 passed + 1 Mac-only skip**, rules **10 passed**. CPU replay sampled minimum MemAvailable **73.037 GiB**. Actual Electron 44.5.1/SwiftShader UI loaded both T0 GLBs and the CT stack; nodule world centers matched the prescribed map. **UI blocker reported to Ty/U:** `Controls` currently frames only meshes with parent type `Scene`, but GLTFLoader's actual parents are `Group`; default camera misses the unrecentered CT. QA-only manual camera capture showed the lung surfaces/marker; no product/UI workaround was applied. Hardware-GPU fps remains unverified.

Staged cache-only outputs for W: `$HOME/spark-md-render-cache/cache/<sid>/`. The staging registry is an isolated CPU-smoke fixture (no real day offsets), **not a replacement live registry**. `run_analysis` has no restore/reuse path and still calls detection: W owns detector-free restoration of cached `nodules.json` and `findings.json`, not `candidates.json`. Preserve `nodule_id`, `track_id`, RAS `center_mm`, proposal fields and the `matching` audit (`prior_nodule_id,prior_study_uid,status,confidence,distance_mm,rule,flags,candidates`). Restore chronologically and retain the earliest origin per track. Cached proposal files do not store subsequent human confirmations; never infer/overwrite accepted evidence from them. G4 replay must use admitted v0.3+ caches rather than original v0.2 G2 counts. Isolated preview worker/browser are stopped; W/G2 runtimes were not changed.

### Full B9 context layers — pipeline 0.5.0

`lung.glb` now contains **lung_right, lung_left, airways, vessels, skeleton**. Airway propagation reuses the lung splitter's trachea-seed rule, dilation and <400 ml leak gate. Vessels use HU >−600 inside lungs eroded 2, strict components >0.3 ml, sigma 0.6 and step 1. Skeleton uses HU >250 inside body eroded 1, closing 1, strict components >2 ml and step 2; its otherwise unspecified smoothing uses the common sigma-1 default, explicitly recorded in `mesh_stats.json`. All surfaces retain Taubin smoothing and unrecentered `(-R,S,A)` mm coordinates; these are display anatomy, not clinical measurements.

CPU-only real hero render and standalone GLTFLoader/SwiftShader visual checks passed for all three timepoints. Per-node triangles and exact file sizes: [`b9-layer-results.json`](b9-layer-results.json). Totals T0/T1/T2: **296016 / 295044 / 293874 triangles**, **7115116 / 7090584 / 7062884 bytes**; CPU rendering **1.026 / 1.187 / 1.271 s**. Imaging **54 passed + 1 Mac-only skip**, rules **10 passed**.

After coordination through Ty/W, promoted only **`lung.glb` and `mesh_stats.json`** by same-filesystem atomic replacement under `$HOME/spark-md-runtime-w/cache/<sid>/`. Read-only SQL before/after snapshots confirmed registry nodule rows unchanged; hashes confirmed `nodules.json`, `findings.json`, `nodules.glb`, stack metadata and candidates unchanged. Original G2 data is untouched. T2 lacks raw volume/mask in W's cache, so its render used original G2 raw files after checking live candidate IDs, RAS centers, detector sizes, proposals and lung bounds. T0/T1 worker asset responses are 200 with byte-matching GLBs; T2's cache is ready but the API is 404 until W registers/restores T2. Reload the viewer's in-memory GLTF cache to see new layers; no live-worker restart or detector call was performed. Staging and previous asset backups: `$HOME/sparkmd-b9-kdpcx8ph/<sid>/`. `render_meshes` now requires `volume=Volume(...)`; all repository callers were migrated.

## 3. Timing and audit checks

Baseline only, from build/04 (Oct 24; **not event-box acceptance deadlines**):

| Stage | Recorded baseline / uncertainty |
| --- | --- |
| Series headers/selection | ~4 s for 44 studies, laptop CPU |
| DICOM → original HU/RAS volume | 44 volumes in 85 s total, laptop CPU; event-box gzip/I/O unverified |
| MONAI detection | ~7 s per series on GB10; exact torch 2.13 event-stack recipe unverified |
| Threshold lung split | Prototype ~2.3–2.7 s/study, laptop CPU; rebuilt Mac split 3.3–3.8 s on hero T0/T1/T2, Oct 25 |
| A7, matching, key slices, cold imports | No per-stage GB10 measurement yet |

Printed job `stage`/`elapsed_s` are sampled through the API, not exact profiler stage durations. `stage_timings.json` now records `perf_counter` wall time between pipeline stage callbacks: `segment` includes A7 + threshold lung split; `render` includes PNG, registry and cache writes. Intake and cold imports before the first stage are outside those stage timings; rules are intentionally not run before confirmation. Cache: `$SPARKMD_HOME/cache/<SeriesUID>/{candidates,nodules,lung_geometry,findings,stage_timings}.json`, `lung_sides.nii.gz`, `N*_proposal_mask.nii.gz`, `key_axial_N*.png`.

All lobes say **approximate**: right superior/middle/inferior thirds; left superior/inferior halves, not fissures. Matching uses same-lobe lung-centered RAS positions, mutual nearest neighbors, ≤5 mm confident distance and ≥5 mm competitor margin; 5–10 mm or ambiguous/boundary/missing-frame cases are flagged and **not linked**. Every decision is in `nodules.json` and registry `agent_events` (`GET /api/agent-log?study_uid=<UID>&limit=100`); these direct registry audit writes do not themselves emit live SSE. Review low-confidence decisions before claiming longitudinal growth. Only confirmed diameters on a linked track feed growth/VDT/Lung-RADS.

The CLI smoke does not establish clinical boundary accuracy, true anatomical lobes, registration accuracy, real T0→T1 identity, or UI alignment. Keep the on-screen “Research demo, not for clinical use” disclaimer.
