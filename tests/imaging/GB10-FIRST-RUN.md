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
