# Cohort 2: NLST stable-nodule false growth + LIDC pool 2 — 2026-10-24/25

Status: **NLST stable set PASSES the frozen gates (real year-to-year noise is low); LIDC pool 2 FAILS G2/G5.** A7 reads ~1 mm larger than NLST-reported diameters. No patient findings accepted. Rule `nodule-cohort2-v1` (`2026-10-24-nodule-cohort2/rule.json`), frozen before selection and download.

## Data

- **NLST:** 30 patients drawn (seed 20261024) from 40 eligible: Farina single nodule at T0/T1/T2, no cancer, NLST reports exactly one nodule per year with long/perp change ≤1 mm. 90 exact Farina series (soft kernel), 6.7 GB. Mostly 4–7 mm nodules (two ~13–15 mm).
- **LIDC pool 2:** 20 patients (seed 20261025) from the 773 eligible not yet used; 171 series, 2.0 GB. LIDC-IDRI-0123 **excluded before scoring**: CT slice positions sit 0.4 voxel off a uniform grid (uneven spacing), so reader masks can't be placed exactly. `lidc_seg_masks.py` now checks this per case and excludes instead of force-fitting.
- 261/261 series verified. Laptop `~/spark-md-cohort2/`, remote `~/spark-md-b/cohort2/`; not in `data/`, not on the drive.
- Pipeline: `bench/nodule_holdout.py convert`, `scripts/b3_detect.py` (GB10), `bench/lidc_seg_masks.py`, `bench/nodule_stable.py` / `nodule_holdout.py cases + score`, `bench/nodule_measure_probe.py cache/classic` (frozen A7). Runner `tmp/measure/cohort2_run.sh`. Fix during the run: the cache now keeps float32 when a series' HU isn't int16-exact (non-integer rescale in some NLST series). Storage only; the method is unchanged.

## NLST stable nodules (the real-world stability test)

Identity = Farina point → best detector box within 10 mm: 5/90 scans missed. Intervals with both years measured: A7 53, box 55. NLST-reported change: median 0.0 mm.

| | A7 | Box (w+h)/2 | Gate (A7) |
| --- | ---: | ---: | --- |
| Median abs year-to-year change | **0.28 mm** | 0.20 mm | ≤1.0 ✓ |
| False growth (>1.5 mm increase) | **2/53 (3.8%)** | 2/55 (3.6%) | ≤10% ✓ |
| Detection/measure failures | 8.9% | 5.6% | ≤15% ✓ |
| Median abs error vs NLST report | 0.98 mm | 0.85 mm | — |
| Signed median vs NLST report | **+0.97 mm** (23% > +1.5 mm) | +0.84 mm (14%) | — |

False growth: 102511 T0→T1 (11.0 → 12.6, reported 9 → 8) and 102669 T1→T2 (6.5 → 8.6, reported 5.5 throughout). Gross over-reads: 101857 (A7 9.0 vs reported 3.5, likely an adjacent structure; box 4.3) and 102154 (6.8 vs 4.0). Real detector boxes land consistently between years, so year-to-year noise is far smaller than the synthetic ±3 mm shift test implied (1.8 mm).

**Bias caveat:** A7 runs ~1 mm above NLST radiologist reports on 4–7 mm nodules. NLST reports are integer-mm caliper reads, so some of this is the reference. On LIDC contours A7 was close to unbiased. But near the 6 mm Lung-RADS cut point, +1 mm moves category 2 → 3. Another reason the radiologist confirms each diameter.

## LIDC pool 2 (descriptive under the holdout gates)

41 groups, 1 detection miss, 40 evaluated. A7 median error 1.07 mm (all), box 0.77 mm; reader leave-one-out 0.71 mm. Unflagged: 0.94 mm (G1 ✓), bin agreement 0.67 vs 0.69 needed (G2 ✗), >2 mm errors 3% (G3 ✓), flag rate 25% (G4 ✓), ±3 mm shift range 1.68 mm (G5 ✗). The A7-vs-box flag caught **8/9** errors >2 mm here (2/4 on the first holdout; 10/13 pooled).

## Interpretation

- Pooled LIDC (holdout + pool 2, 71 nodules): A7 is close to reader agreement but slightly worse than the box diameter, and the synthetic stability gate fails twice.
- On real longitudinal data, though, year-to-year A7 noise is small (0.28 mm median, 3.8% false growth). So **growth calls from A7 on consistently detected nodules look usable as a proposal**; absolute size has a ~+1 mm bias vs NLST reports.
- Supports the decided path: A7 diameter + mask as a proposal, radiologist confirms/edits, code computes growth/category. The A7-vs-box disagreement (>2 mm) is a reasonable "look carefully" cue (10/13 large errors pooled), not a safety guarantee.

## Runtime

Download ~2 min (8.7 GB); conversion ~3 min; detection 110 series ~13 min on GB10 (TensorFold/OpenClaw running, 72 GiB available at start and end); masks/cache/A7 a few minutes CPU. All processes exited. NLST CC BY 4.0, LIDC-IDRI CC BY 3.0 via IDC; Farina et al. 2025 for nodule locations; citations in `data/README.md`.
