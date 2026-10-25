# Held-out LIDC check: A7 + box-agreement flag — 2026-10-24

Status: **FAIL on the frozen rule (G5 stability), G1–G4 pass.** Accuracy of the rule-based A7 measurement holds on 15 unseen patients; box-shift stability does not. Supports Ty's decision: A7 is shown as a *proposal* and the radiologist confirms each diameter. No patient findings accepted.

## Method

- Rule `nodule-holdout-v1` (`2026-10-24-nodule-holdout/rule.json`), frozen **before** sampling or downloading. 15 PatientIDs drawn with `default_rng(20261024)` from 788 eligible IDC `lidc_idri` studies (one CT, ≥1 nodule group with ≥2 reader SEGs, excluding our 8 earlier cases). Downloaded via `idc-index` 0.13.4 from the public IDC bucket: 142 series, 2.1 GB, 142/142 instance counts verified. Laptop copy `~/spark-md-holdout/`; remote `~/spark-md-b/holdout/`. Not added to `data/` (validation-only).
- Pipeline: `bench/nodule_holdout.py convert` (B2 conversion) → `scripts/b3_detect.py` unchanged on GB10 → `bench/lidc_seg_masks.py` → `nodule_holdout.py cases` (same matching as `vista-reliability-v1`) → `bench/nodule_measure_probe.py cache/classic --shift-mm 3` (unchanged A7 code; its rule label reads `-shift3-posthoc` because of the CLI flag, but the holdout rule governs) → `nodule_holdout.py score`, run once.
- Method: A7 (f=0.5, k=1.5, 1 mm opening) at the detector box. Flag = A7 fails or |A7 − box (w+h)/2| > 2 mm. Gates: G1 unflagged median |err| ≤1.5 mm; G2 unflagged size-bin agreement ≥ reader leave-one-out −0.10; G3 ≤10% of unflagged with |err| >2 mm; G4 flag rate ≤40%; G5 median range across ±3 mm box shifts ≤1.5 mm (unflagged groups, unflagged shifts).
- Data gotchas found: (1) LIDC-IDRI-0766's study also holds 9 **QIN CT challenge algorithm SEGs** with `SegmentLabel` "Segmentation"; they are not reader contours, so the mask script now skips and logs them. (2) `b3_detect.py` ends with `TypeError: '_ConfigProxy' object is not callable` *after* `result_luna16_fold0.json` is written (same in the original B3 log); harmless, but don't mistake it for a failed run.

## Results

31 multi-reader groups, all matched by a detector box (median offset ~2.5 mm, max 9.4 mm); reader masks verified on tissue (mean HU −647 to +1201; 0766/0791 calcified).

| Gate | Value | Bar | |
| --- | ---: | ---: | --- |
| G1 unflagged median abs error | **0.51 mm** | ≤1.5 | pass (readers vs each other: 0.59 mm) |
| G2 unflagged bin agreement | 0.80 | ≥0.70 (reader 0.80 − 0.10) | pass |
| G3 unflagged with error >2 mm | 8% (2/25) | ≤10% | pass |
| G4 flag rate | 19% (6/31) | ≤40% | pass |
| G5 shift range, median | **1.82 mm** | ≤1.5 | **fail** |

All 31: A7 median error 0.55 mm, box diameter 0.69 mm. 18% of shifted runs on unflagged groups trip the flag. The flag catches 2 of the 4 A7 errors >2 mm (0303 n1, 0791 n1). It misses 0047 n1 (15.0 → 11.7 mm) and calcified 0766 n1 (14.5 → 9.6 mm), where the box is also low. 4 of the 6 flags are large nodules where A7 is close and the box under-calls (e.g. 0207 n1: ref 22.8, A7 22.9, box 15.2).

## Interpretation

- At the detector-given box, A7 is about as accurate as a second reader on unseen LIDC nodules (n=31). The open problem is position sensitivity: ~1.8 mm swing for ±3 mm box offsets, comparable to the 1.5 mm/12 mo growth threshold. Detector-placement noise between years can therefore create or hide growth.
- The A7-vs-box flag is a weak safety net (2/4 large errors) and often fires when A7 is right. Don't present it as a validated safety check.
- This supports the decided demo path: show A7 diameter + mask as a proposal; radiologist confirms or edits; code computes growth/VDT/category from the confirmed numbers. Label A7 as "research measurement, radiologist-confirmed".
- Limits: 31 nodules, 15 patients, LIDC only (LUNA16 overlap affects the box diameter, not A7), single-timepoint scans (no true longitudinal noise measurement), readers' contours as reference.

## Runtime

Download 27 s; conversion 48 s; detection ~4 min on GB10 (15 series, TensorFold/OpenClaw running, MemAvailable 72 GiB at start, process exited); masks/cache/A7 a few minutes on CPU. Torch 2.14.1+cu130 / MONAI 1.6.1. LIDC-IDRI CC BY 3.0 via IDC; SEG DOI `10.7937/tcia.2018.h7umfurq`; citations in `data/README.md`.
