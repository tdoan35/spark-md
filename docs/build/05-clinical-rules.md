# 05: Clinical rules — Lung-RADS v2022 engine

Status: **implemented and tested (Oct 24)** — engine `scripts/lungrads/rules.py` (stdlib-only; prep validation copy), vectors `scripts/lungrads/test_rules.py` (41 vectors, 6 suites, **all pass**). The day-of product copy lives in the event repo's L4 layer; recreate from this spec.
Rebuild budget on the day: ~10 min to retype/port + run tests.

## Purpose and scope

Deterministic Lung-RADS v2022 categorization and management strings from nodule measurements. **The LLM never computes or changes a category** (AGENTS.md non-negotiable 1). Also emits the `rule_id` shown in the UI. Out of scope: VDT (computed in the imaging layer, reported as evidence, not a category driver per the ACR table), categories 0/S (needs inputs we don't produce; hooks exist).

## Interfaces

Input: nodule dicts as produced by the findings pipeline —

```python
{"type": "solid" | "part_solid" | "ggo",   # required
 "mean_mm": 8.4,                            # mean diameter, 1 decimal
 "solid_mm": 5.0,                           # part_solid only
 "new": True, "growth_mm": 3.9,             # built with growth_per_12mo(delta, interval_days); see Growth definition
 "benign_features": False, "slow_growing": False,
 "suspicion_flags": []}                     # spiculation|lymphadenopathy|metastasis|ggn_doubling_1y
```

Output (`assess(nodules)`): `{lung_rads, rule_id, management, driver, nodules[]}` — the exam takes the most suspicious nodule's category (1 < 2 < 3 < 4A < 4B < 4X). Maps to the registry's `assessments` row (00 §Registry).

## Dependencies

None (stdlib only). Source of truth: **ACR Lung-RADS v2022** (acr.org/Lung-RADS, released Nov 2022), category table as reproduced in *ACR Lung-RADS v2022: Assessment Categories and Management Recommendations*, J Am Coll Radiol 2023, doi:10.1016/j.jacr.2023.10.012 (also CHEST 2024, doi:10.1016/j.chest.2023.12.025).

## Rule table (IDs as emitted; every threshold from the ACR v2022 table)

| Rule ID | Condition | Category |
| --- | --- | --- |
| S-BENIGN | solid, fat / popcorn-central calcification | 1 |
| S-BASE-<6 | solid <6 mm (<113 mm³) at baseline | 2 |
| S-NEW-<4 | new solid <4 mm (<34 mm³) | 2 |
| S-BASE-6-8 | solid ≥6 to <8 mm at baseline | 3 |
| S-NEW-4-6 | new solid 4 to <6 mm | 3 |
| S-BASE-8-15 | solid ≥8 to <15 mm at baseline | 4A |
| S-GROW-<8 | growing solid <8 mm | 4A |
| S-NEW-6-8 | new solid 6 to <8 mm | 4A |
| S-BASE-≥15 | solid ≥15 mm at baseline | 4B |
| S-GROW-≥8 | **new or growing solid ≥8 mm** | 4B |
| S-N8 | slow growth over multiple exams (Note 8) | 4B |
| PS-BASE-<6 | part-solid <6 mm total at baseline | 2 |
| PS-BASE-S<6 | part-solid ≥6 mm total, solid component <6 mm | 3 |
| PS-NEW-<6 | new part-solid <6 mm total | 3 |
| PS-BASE-S6-8 | part-solid, solid component ≥6 to <8 mm | 4A |
| PS-GROW-S<4 | new/growing part-solid, solid component <4 mm | 4A |
| PS-BASE-S≥8 | part-solid, solid component ≥8 mm | 4B |
| PS-GROW-S≥4 | new/growing part-solid, solid component ≥4 mm | 4B |
| G-<30 | GGN <30 mm (any behavior) | 2 |
| G-≥30 | GGN ≥30 mm baseline or new | 3 |
| G-N7 | GGN ≥30 mm stable or slowly growing (Note 7) | 2 |
| G-X / +X | GGN doubling in 1 y; or cat 3/4 + spiculation/lymphadenopathy/metastasis (Note 14; 4X is a distinct category, not a modifier) | 4X |
| NO-NODULES | no nodules | 1 |

**Growth definition (Note 6): >1.5 mm increase in mean diameter within a 12-month interval.** Callers build `growth_mm` with `growth_per_12mo(delta_mm, interval_days)`: intervals ≤ 365.25 d use the absolute change (Note 6 as written); longer intervals use the change scaled to a 12-month rate (`delta × 365.25 / days`). Short intervals are never scaled up. **This is Spark MD's interpretation (decided Oct 25, Ty), not ACR wording**, consistent with Note 8's per-12-month framing. Reason: NLST annual screens run ~12–13 months (hero T0→T1 = 371 d); a strict ≤12-month cut-off would drop growth for a late annual screen. Examples: +4.0 mm / 371 d → 3.9 mm/12 mo → growing; +2.0 mm / 730 d → 1.0 → not growth. Show the normalization in the UI rule text when it applies (e.g. "growth 3.9 mm/12 mo, normalized").

## Inputs come from confirmed diameters only (Oct 25, with 00 v0.6)

- `assess()` is called by the worker only when **every** nodule on the study (and on the prior study used for growth) has `confirmed = true`. Inputs: `mean_mm` = the confirmed diameter; `growth_mm` = `growth_per_12mo(confirmed current − confirmed prior, interval_days)` for every interval with a known `day_offset` (real `scr_days*` offsets, 03); intervals > 12 months are rate-normalized, never dropped (00 v0.8). A proposal (`proposed_*`, A7, detector box) is never an input.
- The worker returns no `assessment` for an unconfirmed study (null in findings; no row in `assessments`).
- Rule engine and its 41 vectors are **unchanged**. New worker-level tests (06/11): (a) `assess` is not called with an unconfirmed nodule; (b) editing a confirmed diameter and re-confirming recomputes growth and category; (c) the category equals what `assess()` returns for the confirmed inputs.
- Hero example caveat stands: the table below used pre-confirmation numbers. On the day the demo sequence comes from the diameters the radiologist (Joyce) confirms; do not quote 2 → 4B → 4B as a fixed result.

## Acceptance tests

`cd scripts/lungrads && python3 -m unittest test_rules -v` → **8 suites OK** (Oct 25: the 41 table vectors + `TestGrowthInterval`, 9 interval cases). Vectors cover every row above including boundaries (4.0/6.0/8.0/15.0/30.0 mm, growth 1.5 vs 2.0), the benign/Note-7/Note-8/4X specials, exam-level max-suspicion, and the hero series.

## Hero through the engine (measured numbers, `2026-10-24-b5-hero-measurements.json`)

**Oct 24 correction:** longitudinal inspection found the historical T0 threshold mask on heart-boundary tissue, not a validated mask of the detector target. The table below remains an engine-input example, not a validated patient category sequence. T0-dependent measurements/VDT/categories require remeasurement. See `docs/benchmarks/2026-10-24-vista-longitudinal.md`. Passing rule vectors do not validate the imaging inputs.

| Timepoint | Input | Category |
| --- | --- | --- |
| T0 | solid 4.6 mm, baseline | **2** (S-BASE-<6) |
| T1 | solid 8.4 mm, growth +3.9 mm | **4B** (S-GROW-≥8) |
| T2 | solid 14.7 mm, growth +6.2 mm | **4B** (S-GROW-≥8) |

With the NLST-reported T0 size (6 mm), T0 is 3 — the demo story "≤3 → growing 4B" holds either way; **the on-screen category always comes from this engine on our measured inputs** (T0 measured slightly under because the threshold ROI misses faint solid component — see 04).

## Gotchas

- v2022 moved **new solid <6 mm from 2 (2019) to 3** and **solid ≥8–<15 mm at baseline to 4A** (2019 had 8–<15 partly in 3) — do not mix editions; the rule IDs above are v2022-only.
- Part-solid categorization keys off the **solid component** once total ≥6 mm; total size alone never gives 4A/4B.
- 4X is a category, not a suffix (do not print "4A-X").
- Growth over intervals > 12 months is rate-normalized via `growth_per_12mo` (see above); do not pass the raw delta for long intervals, and do not drop growth just because the interval exceeds 365 d.

## Open / unverified

- Categories 0 (incomplete) and the S modifier need inputs (prior-lookup state, incidental-findings detector) we don't produce; hooks only.
- Juxtapleural/perifissural nodule rules (v2022) not implemented — our detector does not classify them.
