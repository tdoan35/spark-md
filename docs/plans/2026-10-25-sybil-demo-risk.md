# Sybil risk card: precomputed demo version (Oct 25)

Status: **plan + briefs (Oct 25, ~13:00).** Demo-only, read-only. Not part of the build contract (`docs/build/00-architecture.md` is untouched); if this is kept after the event, promote it per "After the event".

## What and why

Sybil (open-source deep-learning model, trained on NLST) predicts 1–6 year lung-cancer risk from a whole low-dose chest CT. A spike on the GB10 (Oct 25) scored 36 NLST scans (12 patients × 3 screens) at ~3 s/scan with no nodule box or clinical inputs. The demo shows those **precomputed** numbers as a small research card next to the Lung-RADS badge.

Hero 134503, 1-year risk: **2.8% → 26.9% → 40.2%** (T0 → T1 → T2). Controls stay at 0.1–2.2%.

## Hard rules

1. **Never feeds Lung-RADS.** The category, management text, rule id and driver nodule come only from `sparkmd/rules`. The card is visually separate from the badge.
2. **The agent does not see it today.** No field in `get_findings`, no MCP tool, no `AGENTS.md` change. The LLM never narrates this number in the demo.
3. **Label always visible on the card:** "Research model · not a diagnosis · not part of Lung-RADS · precomputed offline on this box".
4. **Do not claim it predicted anything.** Sybil was trained on NLST and these patients may be in its training set, so the scores are optimistic and are not validation. Say "the model's risk rises as the nodule grows", not "it caught it early". T0 is only 2.8% for the hero; this is not an early-detection claim.
5. **Time machine honesty:** at screen Tn the card shows only T0..Tn, never later screens.
6. **Fail closed:** no matching entry → render nothing (no placeholder number).

## Design (new files, two one-line hooks, no backend)

The study page already receives `study_uid`, `patient_id`, `timepoint` in the findings payload. So the card is **UI-only**: it reads a static JSON bundled with the UI. No new worker route, no `app.py` edit, no payload or contract change.

| Piece | Path | Owner | New or edit |
| --- | --- | --- | --- |
| Precomputed scores | `fixtures/sybil_risk.json` | W (fixtures) | new |
| Fixture schema test | `tests/worker/test_risk_fixture.py` | W | new |
| Precompute script (reproducibility, box is returned 17:30) | `scripts/sybil_precompute.py` | W | new |
| Card component | `ui/src/components/risk-card.tsx` | U | new |
| Mount | `ui/src/pages/study.tsx`, inside `Assessment()`, one import + one JSX line | U | one-line edit |

### Fixture schema (`fixtures/sybil_risk.json`)

```json
{
  "model": "sybil_ensemble", "sybil_commit": "d9fc81b", "generated": "2026-10-25",
  "host": "GB10", "notes": "NLST-trained model; demo patients may overlap its training set.",
  "patients": {
    "134503": {"group": "hero_cancer", "screens": [
      {"timepoint": "T0", "study_uid": "...", "series_uid": "...", "study_date": "19990102",
       "kernel": "B30f", "slices": 151, "risk_1_to_6yr": [0.0281, 0.0502, "…6 values, years 1–6"]}
    ]}
  }
}
```

Lookup order in the card: exact `study_uid`; else `patient_id` (strip a leading `fixture-`) + `timepoint`. The second path covers the UI mock (`fixtures/studies.json` uses `fixture-T0` ids).

### Collision map (checked against `git status`, Oct 25 ~13:00)

Files others are actively editing, which this plan **does not touch**: `ui/src/App.tsx`, `ui/src/api/types.ts`, `ui/mock/server.mjs`, `ui/src/index.css`, `ui/src/pages/system.tsx`, `ui/src/shell/*`, `ui/electron/main.cjs`, `sparkmd/imaging/pipeline.py`, `docs/build/08-ui-status.md`, and `sparkmd/app.py` (a new `sparkmd/netstats.py` is expected to hook into it). Re-run `git status` before the one-line edit to `study.tsx`; if someone is editing it, rebase the one line rather than rewriting the file. Define the card's own types inside `risk-card.tsx`; do not edit `types.ts`.

## Brief: U (UI)

Build `ui/src/components/risk-card.tsx` and mount it in `Assessment()`.
- Props: `studyUid`, `patientId`, `timepoint` (from `findings`). Import `fixtures/sybil_risk.json` (relative path; if Vite blocks files outside its root in dev, copy it to `ui/src/data/` and note it in the commit).
- Show: "1-yr" and "6-yr" as percentages (1 decimal), a small T0→current trend (only screens up to the current timepoint), and the exact label from rule 3. Muted styling; no red/green coding; must not look like a second Lung-RADS badge. Place it below the management block.
- Renders `null` when there is no match (rule 6). Reuse existing `card`/`badge` primitives; no new dependencies.
- Done when: hero T0/T1/T2 show the right numbers and trend length, a control shows ~0–2%, an unknown study shows nothing, `tsc` passes, and screenshots at T0 and T2 are archived like the other UI shots.

## Brief: W (worker / fixtures)

- Add `scripts/sybil_precompute.py` (copy of the spike runner; header documents the venv setup and `torch.load(weights_only=False)` patch) and `tests/worker/test_risk_fixture.py`: schema valid, 12 patients, 3 screens each for all but any missing, six probabilities in [0, 1] and non-decreasing across years, T-labels contiguous.
- Do **not** touch `sparkmd/app.py`, `get_findings`, or the contract. Confirm the box/Electron build ships `fixtures/` (or the copy U makes).
- Done when the test passes and `git status` shows only the new files.

## Brief: A (agent)

No change. Do not add the fixture to `get_findings` or any MCP tool. If the agent is asked about the card, the answer is that it is a separate research display it did not compute.

## Brief: Joyce (video)

Fallback if the card is not merged by **15:00**: overlay the hero numbers as a graphic in the edit (2.8% → 26.9% → 40.2% 1-year risk, with the rule 3 label). The recording window is 15:30–16:45 and code locks at 17:30; no one should merge UI changes after recording starts. Narration: "a research model's risk estimate rises as the nodule grows; it does not change the Lung-RADS category".

## Timeline and gates

| Time | Step |
| --- | --- |
| ~13:15 | Fixture committed (advisor). |
| 13:15–14:30 | U card + mount; W script + test. |
| 14:30 | Joint check on the box with the hero replay (T0, T1, T2). |
| **15:00** | Merge gate. Not working → cut to the overlay fallback. |
| 15:30 | Freeze: no changes while recording. |

## After the event (full integration, not for today)

1. Measure peak GPU/host memory beside the other models (imaging budget ≤25 GiB; floor 15 GiB `MemAvailable`) and run-time on the worker path.
2. Run Sybil in a sidecar subprocess (own venv, pinned commit, torch.load patch isolated), as a pipeline stage `risk` using the existing series selection in `sparkmd/imaging/series.py` rather than the spike's largest-series pick.
3. Registry table `risk_scores` and an additive nullable `risk` object in findings (change-log line in 00).
4. Validate on a non-NLST cohort with outcomes before any accuracy claim. Check the weights' license and the checkpoint sizes (~730 MB).
5. Brock (published logistic model) is a cheap complement but needs age, sex, family history, emphysema and spiculation, which the pipeline does not produce.
