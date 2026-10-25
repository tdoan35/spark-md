# First GB10 run — hero T0 / G2

Status: Mac CPU tests/smokes pass; **this runner and real detector inference are unverified on the event box**. Never install torch/MONAI on the Mac. Run only one heavy GPU job; do not use either coding Spark.

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

## 3. Timing and audit checks

Baseline only, from build/04 (Oct 24; **not event-box acceptance deadlines**):

| Stage | Recorded baseline / uncertainty |
| --- | --- |
| Series headers/selection | ~4 s for 44 studies, laptop CPU |
| DICOM → original HU/RAS volume | 44 volumes in 85 s total, laptop CPU; event-box gzip/I/O unverified |
| MONAI detection | ~7 s per series on GB10; exact torch 2.13 event-stack recipe unverified |
| Threshold lung split | Prototype ~2.3–2.7 s/study, laptop CPU; rebuilt Mac split 3.3–3.8 s on hero T0/T1/T2, Oct 25 |
| A7, matching, key slices, cold imports | No per-stage GB10 measurement yet |

Printed job `stage`/`elapsed_s` are sampled through the API, not exact profiler stage durations. Cache: `$SPARKMD_HOME/cache/<SeriesUID>/{candidates,nodules,lung_geometry,findings}.json`, `lung_sides.nii.gz`, `N*_proposal_mask.nii.gz`, `key_axial_N*.png`.

All lobes say **approximate**: right superior/middle/inferior thirds; left superior/inferior halves, not fissures. Matching uses same-lobe lung-centered RAS positions, mutual nearest neighbors, ≤5 mm confident distance and ≥5 mm competitor margin; 5–10 mm or ambiguous/boundary/missing-frame cases are flagged and **not linked**. Every decision is in `nodules.json` and registry `agent_events` (`GET /api/agent-log?study_uid=<UID>&limit=100`); these direct registry audit writes do not themselves emit live SSE. Review low-confidence decisions before claiming longitudinal growth. Only confirmed diameters on a linked track feed growth/VDT/Lung-RADS.

The CLI smoke does not establish clinical boundary accuracy, true anatomical lobes, registration accuracy, real T0→T1 identity, or UI alignment. Keep the on-screen “Research demo, not for clinical use” disclaimer.
