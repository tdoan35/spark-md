# Nodule measurement bake-off — 2026-10-24

Status: **no method passes the frozen bar honestly.** The rule-based segmenter (A7) is accurate at the detector centre but not position-stable; VISTA + ring negatives fails; the detector-box diameter (C) "passes" only because the stability test cannot perturb it and LIDC overlaps its training data. spark-2 GB10/CPU, rule `nodule-measure-v1`. Preparation diagnostic; no patient findings accepted.

## Method

- Code `bench/nodule_measure_probe.py` (`cache` → `classic` → `vista` → `score`; rule frozen at cache). Remote `~/spark-md-b/measure-20261024-01` (A/B/C/D, ±6 mm), `-03` (+ arm R, ±6 mm, B copied from -01), `-04-shift3` (±3 mm, post hoc). Local summaries in `2026-10-24-nodule-measure/`.
- Cases = `vista-reliability-v1` cases: 14 NLST hero scans (Farina-assisted boxes; 106000 T0 no seed) + 22 LIDC groups with ≥2 reader SEGs. 96 mm ROI cache (reader masks fully inside except one outlier reader on 0052 n2, 98.7%).
- **Metric:** Lung-RADS mean diameter, one function for every method and reader mask (axial slice with the longest in-plane diameter; long = max Feret over the pixel-corner hull; short = extent perpendicular to it). Reference = median reader diameter; reader ceiling = each reader vs median of the others. Bins 6/8/15 mm.
- **Arms:** A = rule-based: seed = max 1 mm-smoothed HU near the box centre; threshold halfway (f) between core HU and local parenchyma; sphere cap k×box radius; opening r mm; seed component (12-setting grid). B = VISTA crop64, 1 positive + 10 ring negatives at ≥6 mm. C = detector box (w+h)/2. D = old −400 HU box seed. R (**post hoc**, added after A's test results were seen) = A + re-centre on mask centroid, ≤3 passes.
- Split by LIDC case: tune 0052/0415/0447/0606, test 0080/0206/0473/0884. Settings chosen on tune only (A7 and R7: f=0.5, k=1.5, r=1 mm). Stability = box centre moved ±6 mm (±3 mm post hoc) along each array axis.
- Bar (test): median |err| ≤1.5 mm; bin agreement ≥ reader ceiling −0.10 (0.73); centre failure ≤10%; median shift range ≤1.5 mm on LIDC and heroes.

## Results (test split, 10 LIDC groups; heroes = 14 scans)

| Arm | Median abs err mm | Bin agree | Centre fail | Shift range ±6 / ±3 mm (LIDC) | Hero range ±6 / ±3 | Shift fail ±6 | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Readers (ceiling) | 0.73 | 0.83 | — | — | — | — | |
| **A7 rule-based** | **0.46** | 0.70 | 0% | 5.2 / 3.0 | 3.2 / 1.8 | 25% | fail (stability, bins by 0.03) |
| R7 re-centred (post hoc) | 2.21 | 0.60 | 0% | 0.15 / 0.10 | 1.4 / 0.0 | 25% | fail (drifts to wrong blobs) |
| B VISTA + negatives | 4.38 | 0.75 | **60%** | 32 | 9.0 | 62% | fail |
| C detector box | 0.59 | 1.00 | 0% | 0 (untestable) | 0 | 0% | "pass": not a real stability test; LIDC ⊂ LUNA16 training |
| D old −400 seed | 1.74 | 0.80 | 0% | 5.2 / 2.7 | 6.3 / 2.8 | 33% | fail |

Tune split: A7 1.11 mm / 0.83, C 0.96 / 0.75, R7 1.27 / 0.83.

**Independent hero check vs NLST radiologist-reported diameters** (12 scans matched unambiguously by slice number; slice direction is inconsistent, so this is a weak, integer-mm reference; NLST is not in LUNA16): median abs error A7 0.86 mm (11/12, 106000 fails closed), C 0.96 mm, R7 0.67 mm, D 1.45 mm, B 4.38 mm (3/12 non-empty). Hero 134503: A7 6.4 → 10.4 → 13.5, C 7.1 → 9.6 → 13.1, NLST 6 → 9 → 14 mm.

**Failure modes:**
- A7 merges attached structures on some small nodules (0473 n1/n2: 8–9 mm vs readers ~5 mm) and under-calls large irregular ones (0080). Its instability comes from the seed and threshold depending on where the box lands.
- R7 makes the answer stable but sometimes settles on the wrong blob (0415 n8 Dice 0.0; 0415 n5 13.7 vs 8.1 mm).
- B: negative clicks empty most small-nodule outputs, matching `2026-10-24-vista-clicks.md`.
- Detector offset on LIDC: median 2.75 mm, max 9.2 mm from the reader centroid, so ±6 mm is roughly the 90th percentile.

**Post-hoc observation (unvalidated):** flagging when A7 and C disagree by >2 mm catches 3 of the 4 large A7 LIDC errors (0473 n1, n2, 0080 n1; misses 0080 n2) and hero 106194 T0. It needs fresh cases before anyone relies on it.

## Interpretation

- A7 at the detector centre is about as accurate as readers on these 22 groups, but a 3 mm box offset moves it ~2–3 mm, which is above the 1.5 mm/12 mo growth threshold. Accept it only with a stability fix or a human check.
- C looks good on both LIDC and NLST, but it is a regression output with no mask, its LIDC numbers are contaminated, and its scan-to-scan noise is untested.
- VISTA point prompting stays out of measurement.
- Next (Ty's call): (1) download ~10–15 more LIDC cases with SEGs as a truly held-out set and freeze "A7 + C agreement ≤2 mm, else radiologist confirms" before scoring it; (2) or ship the demo with the radiologist confirming or entering diameters while code computes growth and category.

## Runtime

Cache 44 s (37 ROIs); classic A/C/D 84 s on 8 CPU workers (A+R+C+D ~4 min); VISTA 259 calls ~2.7 s each (one 128³ window per click), ~12 min. Min host MemAvailable 65.66 GiB (VISTA stage) with TensorFold/OpenClaw running. All probes exited; no process left. Torch 2.14.1+cu130 / MONAI 1.6.1. NLST CC BY 4.0, LIDC-IDRI CC BY 3.0 via IDC; SEG DOI `10.7937/tcia.2018.h7umfurq`.
