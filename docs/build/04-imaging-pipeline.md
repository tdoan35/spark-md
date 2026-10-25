# 04: Imaging pipeline (B-track, partial — Oct 24)

Status: **B1–B3 validated; B7 rules tested; historical T0 characterization invalidated by wrong-target seed.** T1/T2 segmentation is experimental. The previously reported 4.6→8.4→14.7 mm / VDT 140/186 d sequence is retained as historical raw data, **not validated nodule measurements**. Full-CT automatic VISTA prompt rules fail on the small T0 nodule; a fixed 64 mm crop passes hero coarse gates but fails subsequent LIDC reader-agreement/crop-stability evaluation; reader-assisted foreground/background clicks also fail (annotation-assisted capability diagnostic, `2026-10-24-vista-clicks.md`); see `docs/benchmarks/2026-10-24-vista-longitudinal.md`. B4/B8 remain open; B9 has a threshold-mask prototype (see B9 section).
Rebuild budget on the day: venv ~5 min (wheelhouse), B1+B2 over the demo set ~2 min, detection ~7 s/series on GB10 (44 studies ≈ 5 min).

## Purpose and scope

Series selection → HU/RAS volume → detector candidates → hero nodule characterization (threshold-ROI fallback) → hero growth/VDT. Rules engine (B7) tested separately in 05. Lobe masks (B4), general prior matching, extras and render (B8–B9) remain open.


## VISTA-3D (NV-Segment-CT) wiring — gotchas so far (event-box blockers)

**Oct 24 longitudinal-test correction:** the old hero T0 threshold-ROI mask is not validated nodule tissue. Its maximum-interior point is 18.46 mm from the detector center, on the heart boundary, outside the ~7 mm detection box. The automatic v1 rule inherits this wrong target and produces a ~428,424 mm³ T0 VISTA region. Historical T0 fallback size/volume, T0→T1 VDT and the category sequence must not be presented as validated measurements of the tracked nodule. Raw historical JSON is retained. A detector-box-bounded seed follow-up keeps the T0 point in the nodule, but VISTA still returns a ~980,087 mm³ lung-scale mask; T1/T2 remain localized but unvalidated. Neither sequence is accepted for growth; see `docs/benchmarks/2026-10-24-vista-longitudinal.md`.

1. `vista3d_pretrained_model/model.pt` is an unprefixed MONAI state dict; transformers `from_pretrained` needs `network.`-prefixed keys in `pytorch_model.bin` (one-time conversion, kept beside the bundle) **and** `transformers==4.46.3` (the config's own pin; 5.x breaks the custom class).
2. monai 1.6.1 shim in `vista3d_pipeline.py`: `torch.from_numpy(points)` → `torch.as_tensor(points)` (transform_points now returns a Tensor). Deps beyond requirements.lock: `transformers`, `einops`, `scikit-image`.
3. Output lands nested: `<out_dir>/<image>/<image>_seg.nii.gz` — glob recursively.
4. **Focused diagnostic completed (Oct 24, 134503 T2 on spark-2):** the old VISTA caller omitted LPS→RAS before applying the inverse NIfTI affine. Old point `[822.15,185.22,67.50]` is outside the `[512,512,152]` image; corrected point `[216.37,381.63,67.50]` visibly lies in the target nodule. The old saved segmentation has only 0 and 255, **zero label-1 foreground voxels**. `255` encodes NaN/uncomputed regions in the bundled saver; `mask > 0` incorrectly treats them as nodule. Point-only foreground must be decoded as `mask == 1`. VISTA internally maps original-image voxels into processed voxels using `inverse(processed_affine) @ original_affine`; supply original-image voxel coordinates. Fresh corrected output matches the input grid and contains the target, **but over-segments**: 8,783 mm³ foreground, prompt-containing component 8,749 mm³ with ~72×27×62 mm bounding extent. Do not use it for nodule measurements. Follow-up completed: a centered point reduces T2 foreground to 3,089 mm³; adding two inspected negative points yields one 1,372 mm³ region (~13.5×16.8×14 mm bounding extent), more tightly aligned visually. Prompts were fallback-guided and manually inspected, so this is not automatic accuracy validation; keep fallback measurements. Record: `docs/benchmarks/2026-10-24-vista-refine.md`, code `bench/vista_refine_probe.py`. Full record: `docs/benchmarks/2026-10-24-vista-point.md`; probe `bench/vista_point_probe.py`; remote outputs `~/spark-md-b/vista-probe-20261024-01/`. B5 measurements still use the threshold-ROI fallback.
5. **Detection boxes come out in DICOM/LPS convention** even though the input NIfTI affine is RAS — negate x/y when mapping box centers back to voxels (cost an hour to find; hero-eval distances were consistent only because both sides were LPS).

## Local-crop follow-up (Oct 24)

`bench/vista_crop_probe.py`, rule `hero-crop64-v1`: same detector-box positive, full CT control vs 64 mm local crop, no negatives. All three cropped outputs are localized and pass predeclared gross-failure checks; volumes ~347/553/774 mm³. Foreground edge clearance >23 mm rules out simple crop truncation. Correct crop affine `original_affine @ translation(crop_start)` and local point `original_point - crop_start`; restore by exact index placement, outside-crop labels 255 (uncomputed). Cropping alters context/padding/internal resampling phase; root cause is not isolated. No clinical measurement/growth/category accepted; old T0 fallback evidence remains invalidated. Full method, frozen checks, timing and overlays: `docs/benchmarks/2026-10-24-vista-crop.md`.

## LIDC reader and crop-size evaluation (Oct 24)

**Current point-only crop configuration is rejected for nodule measurement.** Seven cases pass exact DICOM SEG→CT geometry plus sampled CT/NIfTI HU checks; 0415 is excluded because its SEG IOP contradicts source CT orientation at unchanged origin. Among 18 matched high-confidence detections / 57 separate reader annotations, median per-group reader Dice at 48/64/96 mm crops is 0.064/0.033/0.023; only 5/18 pass coarse gates at 64 mm. In the same 15 multi-reader groups, model Dice64 median 0.086 vs reader-pair median 0.775. Four unmatched groups remain reported separately. No annotation used to choose seed voxels.

Hero volume spans across crop sizes are 61/42/71% of volume64 for T0/T1/T2. Repeating the identical 64 mm input produces bitwise-identical hero masks, so these differences are crop sensitivity, not random rerun noise. Root cause is not isolated: audit vendor point/class conditioning and reference-runner/weights compatibility before further crop tuning. Do not generalize this result to every VISTA implementation. Record: `docs/benchmarks/2026-10-24-vista-lidc.md`; code `bench/lidc_references.py`, `bench/vista_lidc_probe.py`, `bench/lidc_score.py`, `bench/lidc_overlays.py`.

## Checkpoint/conditioning audit (Oct 24)

CPU audit on spark-2: all 259 original→prefixed→HF-loaded tensors exact, no missing/unexpected keys. Laptop RTX 3080 direct-MONAI controls reproduce prior GB10 HF point-only masks at Dice 0.996–1.000 on four diagnostic inputs. Explicit zero-shot class133 worsens reader overlap on all three selected LIDC targets; class23 and special positive flag3 do not rescue the selected small failure. MONAI preprocessing class23→flag1 disagrees with network converter→flag3, but the disagreement is not a demonstrated fix. Do not alter defaults or treat this selected laptop sample as cohort/GB10 validation. Existing LIDC rejection stands; no sizes/growth/categories accepted. Method, native class decoding, hooks, limits and overlays: `docs/benchmarks/2026-10-24-vista-conditioning.md`.

## Crop mechanism / position / class isolation (Oct 24)

`bench/vista_reliability_probe.py`, rule `vista-reliability-v1`, 14 NLST hero scans + 22 LIDC groups × 20 conditions. The bundle runs one 192 mm (128³ @1.5 mm) point-centred window, zero-padded (air) when the input is smaller. **The crop "fix" is context removal:** HU outside a 64 mm block set to −1000 on the *original* grid rescues 7/7 lung-scale failures; resampling-phase shifts (1–2 voxel trims) rescue ~1/7; a 192 mm crop (same window content) rescues 1/7. **±6 mm crop shifts change hero volumes up to 3.8× (66.7× worst NLST scan)**, i.e. within detector-centre error. Class prompt 23 adds edge foreground, no Dice gain. LIDC median Dice vs consensus ≤0.09 in every condition (inter-reader 0.78). Record: `docs/benchmarks/2026-10-24-vista-reliability.md`. Nodule measurement needs a different, reader-validated method or must fail closed.

## Annotation-assisted click diagnostic (Oct 24)

Reader-guided clicks **do not rescue segmentation**; frozen rule `clicks-assisted-v1`, laptop 3080. One guide reader's contour generated deterministic positives (FPS from deepest EDT voxel) and near-boundary negatives (2–4 mm shell, outside all annotated groups); held-out readers scored. Five conditions per target (auto baseline preserved + 1+/0−, 1+/4−, 3+/8−, 5+/16−) on the exact same 64 mm crops; `auto1` controls reproduce GB10 (0.996–1.000) and same-device conditioning masks (1.000). Result: no assisted condition beats the automatic single positive; a guide positive alone degrades all three targets; near-boundary negatives suppress the logit **at the positive point** (−17.1 on 0052), so the native `keep_components_with_positive_points` filter empties the mask. With N clicks the point-window inferer makes N window calls carrying the full set (hook-verified, no dropped points). Conclusion: the documented interactive-guidance route itself fails in this MONAI 1.6.1/torch 2.14 stack — not a seed/crop/weight/loader problem. Next step if pursued: NVIDIA reference runner on the same clicks. Full method, mechanism trace and overlays: `docs/benchmarks/2026-10-24-vista-clicks.md`.

## Measurement bake-off (Oct 24)

`bench/nodule_measure_probe.py`, rule `nodule-measure-v1`, Lung-RADS mean diameter vs LIDC reader medians (tune/test split by case). **Rule-based segmenter A7** (seed = max 1 mm-smoothed HU near box centre; threshold = parenchyma + 0.5×(core − parenchyma); sphere cap 1.5× box radius; 1 mm opening; seed component; fails closed if core < −600 HU): held-out median error 0.46 mm (readers 0.73), NLST-reported heroes 0.86 mm, **but ±3 mm box shifts move it ~2–3 mm**, so it is not yet usable for growth on its own. VISTA + ring negatives: 60% empty. Detector-box diameter: 0.59 mm on LIDC (contaminated: LUNA16 ⊂ LIDC), 0.96 mm vs NLST, no mask. Record: `docs/benchmarks/2026-10-24-nodule-measure.md`.

**Held-out (15 new LIDC patients, 31 nodules):** A7 0.51 mm median error unflagged, but ±3 mm box shift → 1.8 mm swing; frozen rule fails stability only. **Decision (Ty): A7 diameter + mask are a proposal; the radiologist confirms/edits before growth/category.** Gotchas: skip non-reader SEGs (QIN challenge algorithm SEGs live in some LIDC studies, e.g. 0766); `b3_detect.py` raises `_ConfigProxy` TypeError *after* writing results (harmless). Record: `docs/benchmarks/2026-10-24-nodule-holdout.md`.

**NLST stable nodules (30 pts):** A7 year-to-year change median 0.28 mm, false growth 3.8% (real detector boxes land consistently); absolute A7 ~+1 mm vs NLST reports on small nodules. Gotchas: exclude LIDC cases whose CT slice positions are off a uniform grid (0123: 0.4 voxel); some NLST series have non-integer HU after rescale. Record: `docs/benchmarks/2026-10-24-nodule-cohort2.md`.

## Confirm-flow update (Oct 25, proposed with 00 v0.6): the pipeline emits proposals, not measurements

Per the Oct 24 decision (Ty), nothing this layer measures is accepted until a radiologist confirms it. Changes for the day-of build:

- **Output stage:** after detection and the A7 segmenter, the job ends in `awaiting_confirmation`, not `analyzed`. For each detected nodule, store `proposed_long_mm`, `proposed_short_mm`, `proposed_mean_mm`, `proposal_source = 'A7'`, `box_mean_mm` (detector-box diameter, shown as a cross-check), and the A7 mask (for the overlay). `long_mm`, `short_mm`, `mean_mm`, `volume_mm3` stay null.
- **A7 fail-closed cases** (core < −600 HU, empty mask) produce a nodule with `proposed_*` null and a reason. The radiologist then types a diameter from the CT; the UI does not hide the candidate.
- **After confirmation** (`POST /api/nodules/{id}/confirm`), code derives the accepted values: `mean_mm` = the confirmed value; `volume_mm3` = sphere-equivalent `4/3·π·(mean_mm/2)³` (**proposed rule; the mask volume would disagree with an edited diameter**); `growth_mm`, `vdt_days` and the category use confirmed values only, on both timepoints. Mask volumes remain audit data, never shown as measurements.
- **Priors must be confirmed first.** If T1 arrives while T0 still has an unconfirmed nodule, T1 stays `awaiting_confirmation` with the reason "prior T0 unconfirmed"; do not compare against a proposal.
- **Matching across timepoints stays code-only** (lobe + position); the radiologist confirms diameters, not track identity. Whether the UI should also let them correct a wrong track match is **open**.
- **Nodule `type`** (solid / part-solid / ggo, from HU) is not part of the confirm step yet; it still feeds the category. **Open**: confirm it too, or show it as a proposal.
- Held-out evidence behind this decision: `docs/benchmarks/2026-10-24-nodule-holdout.md` (A7 0.51 mm median error, ±3 mm box shift swings it 1.8 mm).

## Interfaces

- Input: DICOM as staged in `data/dicom/<collection>/<PatientID>/<StudyUID>/<Modality>_<SeriesUID>/*.dcm`.
- Selection output: `b1_series.json` (per study: series rows + `selected` + `reason`).
- Volume output: `<patient>_<study8>.nii.gz`, HU-calibrated, RAS affine, original spacing (the bundle resamples). Volumes land in `~/spark-md-b/vols` + `volumes.json` (spacing/shape/timing).
- Detection output: `detect/result_luna16_fold0.json` — per image, world-coord boxes (**LPS mm**, negate x/y for the RAS affine) + `label_scores`.

## Dependencies (laptop venv `~/venvs/spark-md-x86`, x86; spark-2 `~/venvs/spark-md-arm`, aarch64)

| Package | Version (both) | Note |
| --- | --- | --- |
| python | 3.14.8 (laptop) / 3.12.3 (spark-2) | 3.12 matches the event box |
| torch | 2.14.1+cu130 | wheelhouse pins 2.13.0 — detector worked on 2.14; event box uses the wheelhouse pin (unverified there) |
| monai | 1.6.1 | **the wheelhouse lock version — the bundle needs the shims below** |
| pydicom / nibabel / itk / torchvision / pytorch-ignite | latest | torchvision + itk + ignite are REQUIRED (bundle imports); install them explicitly |

## Build steps

```bash
# laptop (or event box from wheelhouse): the imaging extras beyond requirements.lock
pip install torchvision itk pytorch-ignite
# B1: rules table (44 studies, ~4 s)
python scripts/b1_series_select.py ~/spark-md-b/dicom --json ~/spark-md-b/b1_series.json
# B2: volumes (44 studies, 85 s total)
python scripts/b2_convert.py
# B3: detection (GB10; on the 3080 it OOMs — don't retry there)
python scripts/b3_detect.py
```

Scripts live in the project `scripts/` (prep). The patched bundle config is generated in place as `configs/inference_monai16.json` (see Gotchas).

## Parameters (B1 rules, in order)

1. CT modality; 2. not a localizer (`≥100` instances; `ImageType` LOCALIZER hint); 3. axial (IOP axis-aligned, **sign-insensitive** — LIDC-IDRI-0415 is `[-1,0,0,0,-1,0]`); 4. `SliceThickness ≤ 2.5 mm`; 5. soft kernel (`B30f/B31f/B20f/STANDARD/FC01/FC02/FC51/FC52`); if several soft, thinnest wins.
6. Fallback: if no soft series exists and exactly one axial thin non-localizer CT remains, select it flagged `sharp-kernel fallback` (4 LIDC GE `BONE`-only cases; NLST 100005/100288/109965 single studies missing the thin soft recon).

## Gotchas (found today, all cost cycles)

1. **`ConvolutionKernel` can be a plain string OR MultiValue** (`['B30f','3']` on Siemens). Take the first element of the list form; never iterate a bare string.
2. **monai 1.6.1 vs the 2023 bundle (built for monai 1.2 / torch 1.13)** — three shims, all applied in `configs/inference_monai16.json` + bundle `scripts/*.py` (keep them when copying the bundle to the event box):
   - `EnsureChannelFirstd`: drop `meta_key_postfix` (kwarg removed).
   - `scripts/*.py`: `from monai.config import IgniteInfo` → `from monai.utils import IgniteInfo`.
   - `DetectionSaver` handler `batch_transform`: old `x['image_meta_dict']` key no longer exists; use `{'filename_or_obj': [t.meta['filename_or_obj'] for t in (x['image'] if isinstance(x['image'], list) else [x['image']])]}`. In the ignite batch, `x['image']` is a LIST of MetaTensors.
   - monai 1.2 **cannot** run on CPython ≥3.12 (`FileFinder.find_module` removed), so pinning down is not an option; the wheelhouse's 1.6.1 is correct.
3. `ConfigParser`: `read_config` FIRST, overrides AFTER — overrides set before the read get clobbered by the config file's own values.
4. The bundle's `scripts/` package must be on `sys.path` (`sys.path.insert(0, BUNDLE)`) or `scripts.detection_inferer` fails to import.
5. Datalist needs a `label` key per item (`is_segmentation=True`), even for inference.
6. **RTX 3080 10 GB OOMs** on the 512×512×192 sliding-window patch (amp on, ~8.7 GB needed + fragmentation). Do not shrink the patch silently — run detection on GB10 (MemAvailable 73 GB with TensorFold up, i.e. co-residence works: detector ran beside the LLM within the memory budget).

## Measured performance (Oct 24)

- B1: 44 studies (12 NLST × ~3.7 + 8 LIDC) in ~4 s; **44/44 exactly one selected series** (37 soft, 7 flagged fallback).
- B2: 44 volumes in 85 s total (0.1–0.6 s/study, laptop CPU).
- B3: 44 studies in ~5 min on GB10 (MemAvailable 73 GB with TensorFold up). RTX 3080 OOMs — detection is GB10-only. Hero eval (`b3_eval_heroes.py`, run it where the DICOM tree lives): 15/15 within 10 mm, median 3.3 mm, rank 0–1, no i/j swap.
- **Hero decision: 134503** (top-ranked all timepoints, scores ≈1.000; recorded in `data/README.md`).
## B9 render prototype (Oct 24, ~21:00, laptop CPU)

Lung + airway surface glb and key axial PNGs from the HU volume, no GPU, no VISTA. Code: `bench/b9_render/lung_mesh.py` (mask → mesh → glb), `bench/b9_render/qa_overlay.py` (axial + coronal outline check). Tried on hero 134503 T0/T1/T2 and run in the UI MVP via the mock (`~/spark-md-mvp/mock/real_hero.py`, throwaway).

Build steps (verify each):
1. `python -I bench/b9_render/lung_mesh.py <vol.nii.gz> <out> --boxes boxes.json` → `lung.glb` (nodes `lung_right`, `lung_left`, `airways`), `nodules.glb` (one node per id, ellipsoid = detector box), `b9_stats.json`. Verify: R/L ml plausible (hero 2.4/2.2 L), airway ≈ 40 ml (a leak shows as > 400 ml and is dropped).
2. `python -I bench/b9_render/qa_overlay.py <vol> qa.png --lps cx cy cz` → prints which mask holds the detector centre; look at the PNG (blue = R on image-left, orange = L, green = airway). Hero: centre in **left** mask at all three years, 0.0 mm from mask.
3. Key slice: axial slice through the centre on the **original** grid (`as_closest_canonical`), W1500/L−600, `np.flipud(sl.T)[:, ::-1]` = anterior up, patient-right on image-left; `box_px` in those PNG pixels. Visually matched to the nodule on T0/T1/T2.

Parameters: `as_closest_canonical`, then resample to 1.5 mm iso (order 1). Body = per-slice largest `HU > −400` component, holes filled. Lung = `HU < −400` inside body, 3D components > 300 ml. Airway = `binary_propagation` from the trachea seed (top 10 slices, midline component 30–800 mm², `HU < −950`), dilated 1 voxel, kept only if < 400 ml. R/L split = erode until two pieces (second ≥ 15 % of the first), then watershed on −EDT; per lung the largest component, axial holes filled (vessels → lung). Vessels = `HU > −600` inside the lungs eroded 2 voxels (skips the pleura), components > 0.3 ml, surface σ 0.6 voxel, step 1 (σ 1 erases branches < ~3 mm; −500 HU reached only the hilar trunks, −650 is 128k triangles). Skeleton = `HU > 250` inside the body mask eroded 1 voxel (drops the CT table and skin streaks), closing 1 voxel (bridges low-dose cancellous marrow), components > 2 ml, step 2: ribs, spine, sternum, clavicles, scapulae, proximal humeri; hero T1 ≈ 728 ml, ~98k triangles. (Same idea as the 2017 Kaggle DSB preprocessing tutorial: marching cubes at ~400 HU on the resampled HU volume.) The nodule itself is also bright and joins the vessel mask; the viewer draws the nodule mesh over it. Lung/airway surface = Gaussian σ 1 voxel → marching cubes 0.5 (`step_size` 2 for the lungs, 1 for the airway) → Taubin 10 iterations (λ 0.5, μ −0.53) → affine → glTF `(−R, S, A)`, uint32 indices.

Measured (laptop ty-omarchy CPU, Oct 24): ~2.3–2.7 s per study (load + resample 0.6 s, masks 1.1–1.4 s). Hero T0/T1/T2: R 2398/2448/2336 ml, L 2177/2186/2019 ml, airway 40/40/39 ml; ~100k triangles, **2.3–2.4 MB glb** (step 1 = 330k triangles, 8.4 MB). With vessels (−600 HU, ~80 ml, ~97k triangles): ~195k triangles, **~4.8 MB**, ~3 s per study. With skeleton too: ~295k triangles, **~7.0 MB**, ~3.9 s per study. In Electron (RTX 3080, offscreen 1258×596 well), idle and focused frames hold the 240 fps cap (p50 4.2 ms). GB10 fps with this mesh is **unverified**.

Gotchas:
- `(−R, S, A)` has determinant +1, so marching-cubes winding survives the axis map. Only a mirrored affine flips it, and the viewer's fresnel uses `|n·v|` anyway.
- A small midline air blob behind the heart on coronal is the right lung's azygo-oesophageal recess. It is lung, not gut gas.
- Scanner coordinates differ between years (the hero's detector centre moves 27 mm in x between T0 and T1). Meshes are per study, never shared, and the viewer must not assume a common frame across timepoints.

Open: VISTA-3D lobe masks (B4) to replace the threshold split; coronal key slices; check the threshold mask on emphysematous or diseased lungs (only the hero has been tried); nodule mesh from a validated segmentation (now it is the detector box, **not a measurement**).

## Open / unverified

- Acceptance gate: a seed outside its detector box or a lung-scale nodule output must produce an explicit analysis failure and no derived growth/category. Geometry and connected-component count alone do not establish target validity; T0 v2 passed both and still failed. No current VISTA sequence is approved for measurement.

- B3 detection and Farina hero checks passed; LIDC XML recall remains unverified. Conditional DICOM SEG reader evaluation is complete and fails for the tested point-only crop configuration; it is not a full detector sensitivity study.
- B4 lobe masks, general B5 characterization and B6 automatic matching/control validation, B8 extras and B9 render remain open. B5/B6 hero measurements use the threshold fallback; B7 rules are tested in 05.
- Full-CT VISTA automatic prompts tested unchanged on T0/T1/T2 under two frozen rules. Both fail T0 (lung-scale output). A subsequent fixed 64 mm crop with the same automatic positives passes gross-failure checks on 3/3 timepoints, but a subsequent independent LIDC reader-contour and 48/64/96 mm size test shows poor agreement and large volume changes; this configuration is not accepted for measurement. No sequence accepted for growth. Historical T0 fallback measurements are invalidated as tracked-nodule evidence; nodule measurements are not switched to VISTA. Legacy `b5_characterize.py` still needs coordinate correction, explicit label-1 decoding, fresh-cache handling and geometry-safe measurement (column norms / determinant, not affine diagonal).
- Annotation-assisted click diagnostic (Oct 24): reader-guided positives and near-boundary negatives do **not** recover boundaries in this stack; negatives collapse the logit at the positive point and the native point-only component filter empties the output. Interactive guidance is not a rescue path here; a reader-validated measurement method or fail-closed behavior is required. Record: `docs/benchmarks/2026-10-24-vista-clicks.md`.
- torch 2.13 (wheelhouse pin) vs 2.14 (tested): unverified on the exact event-box stack.
