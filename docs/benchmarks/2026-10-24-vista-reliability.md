# VISTA crop mechanism, position stability, class prompt — 2026-10-24

Status: **mechanism isolated (context removal, not resampling phase); position stability FAILS; reader agreement FAILS in every condition.** spark-2 GB10, rule `vista-reliability-v1`. Preparation diagnostic only; no measurements, growth or categories accepted. Complements `2026-10-24-vista-lidc.md` (crop 48/64/96 vs readers) and `2026-10-24-vista-conditioning.md` (class/flag audit); it answers the "context vs padding vs phase not isolated" open question from `2026-10-24-vista-crop.md`.

## Method

- Code `bench/vista_reliability_probe.py` (prepare/infer, rule frozen before inference), `bench/vista_reliability_summary.py`, reader masks `bench/lidc_seg_masks.py`. Remote `~/spark-md-b/vista-probe-20261024-06/` (per-condition masks as bbox NPZ in `masks/`); local `2026-10-24-vista-reliability/` (rule, cases, results, memory log).
- **Cases:** 5 NLST heroes × T0/T1/T2 using the Farina-assisted tracked detector boxes (106000 T0: no seed → explicit failure; 14 scans run), plus 22 LIDC nodule groups with ≥2 reader SEGs (8 cases). Every LIDC group matched a detector box ≤10 mm from the reader-consensus centroid (any score; best score kept). Consensus = voxels in ≥⌈R/2⌉ of R reader masks.
- **Prompt:** the `hero-crop64-v1` automatic seed (deepest EDT voxel of the HU ≥−400 component nearest the box centre, inside the box), one positive, no negatives, identical physical point in every condition. Decode `==1` (`==23` for class conditions). No cleanup.
- **20 conditions per case** (720 VISTA calls):
  - *context:* `full`; `crop48/64/96/128/192`; `masked64` = original full grid with HU outside the crop64 block set to −1000 (removes context, keeps the original Spacingd phase).
  - *phase:* `full_trim111/220/001` and `crop64_trim111/220` = drop 1–2 low-index voxels per axis (shifts the internal 1.5 mm resampling grid; context unchanged).
  - *position:* crop64 centre ±6 mm along each array axis (6 crops).
  - *class:* `full_cls23`, `crop64_cls23` (`label_prompt` 23 "lung tumor" + same point).
- Gates: the crop64 technical gates (contains positive, extent ≤3× largest box axis, volume ≤4× box volume, crop-edge ≥5 mm). "Gross" below = >100,000 mm³.
- Why these conditions: the bundle resamples to 1.5 mm (Spacingd, phase set by the input's first voxel), crops HU>0 foreground + 10 voxels, then runs **one 128³ point-centred window (192 mm)**, zero-padding (≈−964 HU after scaling) when the input is smaller. So a 64 mm crop = the 192 mm window filled mostly with air padding, plus a phase change.

**0415 note:** its dcmqi SEGs declare IOP `[1,0,0,0,1,0]` while the CT is `[-1,0,0,0,-1,0]`. `lidc_seg_masks.py` maps each SEG frame through its *referenced CT SOP* (SEG pixel (r,c) = CT pixel (r,c), CT IPP/IOP), not SEG plane geometry; reader-mask mean HU is −16 to −334 (tissue) for all 0415 nodules. `2026-10-24-vista-lidc.md` excluded 0415 instead; headline LIDC numbers are given both ways. The pixel-aligned interpretation is **unverified** against the source XML.

## Results

Reproducibility: hero 134503 `full` = 681,125 / 586 / 3,022 mm³ and `crop64` = 347 / 553 / 774 mm³, the same as `2026-10-24-vista-crop.md`.

**Mechanism (NLST, 7 scans where `full` is gross):**

| Condition | Still gross (of 7) | Newly gross (of 7 full-OK) | Changes vs full |
| --- | ---: | ---: | --- |
| full_trim111 / 220 / 001 (phase only) | 6 / 6 / 6 | 1 / 0 / 1 | phase alone rarely rescues; occasionally breaks (113820 T1 11k → 942k mm³) |
| crop192 (≈ same window content) | 6 | 0 | removing out-of-window image does nothing |
| crop128 | — | — | 1/14 NLST gate pass; worst condition (partial air padding) |
| masked64 (context → air, original phase) | **0** | 0 | rescues all, like crop64 |
| crop64 | **0** | 0 | |

→ The T0-style lung-scale failure is driven by **what fills the 192 mm window** (surrounding anatomy vs air padding), not by resampling phase or the HF wrapper. A compact output comes from deleting context, which is not a segmentation fix: the model is not localising the nodule from the point.

**Position stability (crop64 ±6 mm, plus two phase trims):** volume max/min per scan 1.8–66.7× (134503: 3.8× / 1.8× / 2.0×); min Dice vs the centred crop64 0.11–0.80. A 6 mm crop shift is smaller than detector-centre error (hero eval median 3.3 mm, up to ~6 mm), so the crop64 output is **not stable enough for growth**.

**LIDC reader agreement (median Dice vs consensus):**

| Set | Inter-reader | full | masked64 | crop48 | crop64 | crop96 | crop64_cls23 | crop64 Dice ≥0.5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 22 groups, incl. 0415 | 0.78 | 0.00 | 0.04 | 0.05 | 0.05 | 0.02 | 0.05 | 3/22 |
| 15 groups, excl. 0415 | 0.78 | 0.00 | 0.04 | 0.08 | 0.09 | 0.04 | 0.09 | 3/15 |

The excl-0415 crop64 median (0.09) independently reproduces `2026-10-24-vista-lidc.md` (0.086, different matching and reference definition). Only larger solid nodules (≥~600 mm³ consensus: 0884 n2 0.76, 0206 n2 0.59, 0606 n1 0.45) give moderate overlap. Nodules <100 mm³ fail almost universally (often 40–900× volume). Per-nodule table: `python3 bench/vista_reliability_summary.py docs/benchmarks/2026-10-24-vista-reliability/results.json`.

**Class prompt 23:** no Dice gain (crop64 0.09 → 0.09); `crop64_cls23` passes 0/14 NLST gates (extent + crop-edge in 29/36 cases: the class head adds disconnected foreground at the crop faces). Consistent with the conditioning audit.

## Interpretation

- Cause of the crop "fix": context replacement by air padding (confirmed by `masked64` at the original phase). Phase and wrapper are ruled out as primary causes; phase still matters at the margin.
- No condition tested approaches inter-reader agreement on small nodules; outputs are position-sensitive. **Do not use VISTA point-prompt masks for size, growth, VDT or categories.** Nothing in this run reinstates the invalidated historical T0 evidence.
- Practical implication for the product (Ty's call): nodule measurement needs a different deterministic method (e.g. a reader-validated threshold/region-growing segmenter scored against these LIDC masks) or the analysis must fail closed. VISTA can stay for anatomy (lobes, B4), where it is in-distribution.

## Runtime

720 calls, no errors; model load 6.57 s; crop calls ~0.3–0.6 s, full-size ~2–3 s (warm, excluding I/O). Min host MemAvailable **57.40 GiB** (0.5 s sampling) with TensorFold/OpenClaw running; probe exited, no imaging process left. Torch 2.14.1+cu130 / MONAI 1.6.1 / transformers 4.46.3; wheelhouse torch 2.13 unverified. NLST (CC BY 4.0) and LIDC-IDRI (CC BY 3.0) via IDC; LIDC SEG DOI `10.7937/tcia.2018.h7umfurq`; citations in `data/README.md`.
