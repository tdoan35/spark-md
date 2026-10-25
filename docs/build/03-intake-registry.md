# 03: Intake and registry

Status: **draft from measured prep scripts; the watcher and registry code do not exist yet.** The header rules (B1) and the conversion step (B2) ran over all 44 staged studies on Oct 24 (`docs/benchmarks/2026-10-24-b-imaging.md`). Everything about the watcher, the SQLite writes, stability detection, timepoint assignment and demo reset is **unverified** design. Nothing here has run on a GB10.
Rebuild budget on the day: ~45 min, by the infra/worker agent. (Estimate, unmeasured.)

## Purpose and scope

Turns "a study directory appears in `inbox/`" into registry rows ready for analysis: parse headers, group patient → study → series, decide which series are eligible, assign a timepoint and a real day offset, and emit the event that triggers the agent.

In: the watcher, header parsing, series eligibility rules, the timepoint/day-offset rule, the SQLite schema (`patients`, `studies`, `series`), idempotency, demo reset and backlog seeding.
Out: HU conversion and everything after it (04), the rest of the tables (`nodules`, `assessments`, `reports`, … in 00), HTTP routes (06), the agent's `select_series` call (07).
Cut first: the `patients` demographics, sidecar validation warnings, a second-timepoint re-ranking on late arrival.

## Interfaces

**Inbox contract** (00): `$SPARKMD_HOME/inbox/<anything>/…`, one directory per study, containing one subdirectory per series or flat files. A study is complete when no file in it has changed (size + mtime) for **5 s** (00). The study directory name is not trusted; identity comes from the DICOM headers.

**Organized layout** (00): `studies/<StudyInstanceUID>/<SeriesInstanceUID>/<SOPInstanceUID>.dcm`. Files are **moved** from the inbox, not copied, so a disk doesn't hold two copies. The moved path is stored on the `series` row.

**Day-offset sidecar** (new, proposed): `$SPARKMD_HOME/day_offsets.csv`

```
patient_id,rank,day_offset
134503,0,23
134503,1,380
134503,2,800
```

Generated once from `data/nlst/nlst_picked_prsn.csv` (columns `pid`, `scr_days0`, `scr_days1`, `scr_days2`; **covers only the 8 hero + control patients**) plus `data/nlst/nlst_neg_neg_pos.csv` for the 4 negative-then-cancer patients (column `days`, a `/`-joined string such as `7/355/722`; verified for 102537). It's a lookup, not an invention: NLST's header `StudyDate` is de-identified to Jan 2 of 1999/2000/2001, so real intervals only exist in the clinical table (`data/README.md`). Where no row exists, `day_offset` is null and `day_offset_source = 'none'`; the worker must then show intervals as unknown and VDT as not computable.

**Registry columns** (extends 00; keep names exactly):

| Table | Added or pinned here |
| --- | --- |
| `studies` | `patient_id`, `study_uid` PK, `study_date` (raw header string, **not used for intervals**), `rank` (0-based order among the patient's studies by `study_date`, then by arrival), `timepoint` = `T<rank>`, `day_offset` (int or null), `day_offset_source` (`sidecar` \| `none`), `status`, `received_at`, `inbox_path`, `failure_reason` |
| `series` | `series_uid` PK, `study_uid`, `modality`, `series_number`, `kernel` (first `ConvolutionKernel` value), `kernel_list` (JSON), `slice_thickness`, `n_instances`, `image_type`, `axial` (0/1), `path`, `eligible` (0/1), `eligible_reason`, `fallback` (0/1), `selected` (0/1), `select_reason` |
| `patients` | `patient_id` PK, `cohort`, `sex`, `birth_year` (nullable). `cohort` comes from `data/nlst/picks.json` keys (`nlst_hero`, `nlst_ctrl`, `lidc`; the neg-neg-pos set is `nlst_negnegpos`), via a second sidecar line or env; unknown = `unknown`. |

**Order of events** (reconciled with 06, Oct 25): stable → parse → insert patient/study/series rows with `status = 'received'` (+ SSE `worklist_changed {reason:'received'}`) → move files → `status = 'organized'` (+ SSE `study_updated`) → **agent trigger fires on `organized`**, never earlier: the agent's `select_series` needs the files in place. On any failure → `failed` with `failure_reason`, no trigger. The worker owns the trigger (06); intake only calls it. See §Worker integration.

## Worker integration (reconciled with 06, Oct 25)

06 owns the process, routes, trigger and the other tables; 03 owns `patients`, `studies`, `series` and the intake module. One `registry.py` creates all tables (06 step 1), including the 03 columns above, and the same `RLock` guards every write.

| Function (intake module) | Called by | Behaviour |
| --- | --- | --- |
| `ingest_study(path) -> study_uid` | the watcher thread **and** `POST /api/demo/drop` | parse → rows (`received`) → move → `organized`; then calls `on_organized(study_uid)`. Synchronous; raises on failure after setting `failed`. Idempotent per step 7. |
| `reset(patient_ids=None, empty=False)` | `POST /api/demo/reset` | step 8; `empty=True` also clears `cache/` for those patients (so a reset can force a cold rerun). |
| `on_organized(study_uid)` (06 supplies) | intake | SSE + agent trigger (`Idempotency-Key: study-<uid>`) + a `system` agent-log line. |

- **`demo/drop {patient_id, timepoint}`:** looks up `backlog/<patient_id>/<timepoint>/`, calls `ingest_study` directly. It skips the 5 s stability wait (the backlog is local and already complete), so the drop-to-trigger latency is parse + move only. A study already in the registry → 409 (06 test 13). Warn in the log if the computed `timepoint` differs from the requested one.
- **Backlog layout** (proposed): `backlog/<patient_id>/T0|T1|T2/<series dirs>`, built from `data/dicom` by a prep script on the day. The watched `inbox/` stays for the "real PACS" path and for any manual drop.
- **Fixtures vs real studies:** 06's rehearsal fixtures bypass intake. Once 03 exists, studies come only from `ingest_study`; keep fixtures behind `SPARKMD_FAKE_*` for tests. Seed every study as `received` (06 gotcha).
- **Null `day_offset`:** 06's interval, growth and VDT must treat a null offset on either study as "interval unknown" → no growth, no VDT, no category driver from growth. This applies to LIDC and to any NLST patient missing from the sidecar.
- **`priors[]` for `GET /api/studies/{uid}`:** all other studies of the same patient with a lower `rank`, newest first.
- **Status sets:** 03 writes `received`, `organized`, `failed`; 06 writes the rest (`analyzing` → `awaiting_confirmation` → `analyzed` → `reported` → `approved`).
- **Open for the 06 owner:** `demo/reset {empty?}` as rehearsed has no defined meaning for intake. Treat `empty=True` as "drop all registry rows, restore the full backlog" and `empty=False` as "reset the demo patients only". Confirm.

## Dependencies

- Python 3.12 wheelhouse venv (`~/.venvs/spark-md`): `pydicom` (in the lock, B1/B2 used it), stdlib `sqlite3`, `pathlib`. No `watchdog`: poll (below).
- Source data for tests: `data/dicom/{nlst,lidc_idri}/…`, `data/nlst/nlst_picked_prsn.csv`, `data/nlst/picks.json`.

## Build steps

1. **Poll loop.** Every 2 s list `inbox/` one level deep. For each unseen study directory, record `(total_bytes, newest_mtime, n_files)`. Mark complete when the triple has not changed for 5 s. *Verify:* `cp -r` a 150-slice series into `inbox/` and confirm no registry row appears until the copy ends, then one row appears.
2. **Parse headers.** For every file, `pydicom.dcmread(path, stop_before_pixels=True, force=False)`. Skip (and count) files that aren't DICOM. Group by `StudyInstanceUID` → `SeriesInstanceUID`. Read one file per series for series-level fields; count the files. *Verify:* 134503's three studies each produce 3 series (localizer, B30f, B50f), 151–158 instances on the axial ones.
3. **Skip non-image series, but record them.** Keep `modality != 'CT'` (LIDC `SEG`, `SR`) as series rows with `eligible = 0`, reason `not CT`, and move them too. Never try to build a volume from them. *Verify:* LIDC-IDRI-0052 gives 1 CT + 8 SEG + 8 SR; exactly the CT is eligible.
4. **Eligibility per series** (the B1 rules, precedence in this order; first match wins):
   1. `Modality != CT` → no.
   2. `ImageType` contains `LOCALIZER`, or `n_instances < 100` → no.
   3. Not axial (|IOP| within 0.05 of `1,0,0,0,1,0`; sign-insensitive) → no.
   4. `SliceThickness` not in (0, 2.5] mm → no.
   5. Kernel in the soft set → yes. Sharp set or prefix `b5/b6/b7/b8`, `bone`, `lung` → no. Otherwise → no, reason `unknown kernel`.

   Soft: `b30f b31f b20f standard fc01 fc02 fc51 fc52`. Sharp: `b70f b80s b60f bone lung`. (`B50f` is neither list → rejected as sharp by prefix `b5`.)
5. **One default per study.** If several are eligible, prefer thinner slices, then more instances; the rest get `superseded (multiple soft candidates)`. If none are eligible but exactly one CT series is axial, thin, non-localizer and ≥ 100 instances, take it as `only eligible series (sharp-kernel fallback)`: set `eligible = 1`, `selected = 1`, `fallback = 1` (new `series` column) so `select_series` accepts it, and 04 can warn. Fallback series are the only eligible sharp-kernel ones. The default is a **proposal**: the agent still calls `select_series` (00), which rejects ineligible series. *Verify:* B1's 44/44 exactly-one-selected, 37 soft + 7 fallback.
6. **Timepoint and day offset.** After inserting a study, recompute `rank` for all of that patient's studies (sort by `study_date`, tie-break `received_at`) and set `timepoint = T<rank>`. Look up `day_offset` in the sidecar by `(patient_id, rank)`. *Verify:* 134503 → `1999-01-02 → T0 → 23`, `2000-01-02 → T1 → 380`, `2001-01-02 → T2 → 800`.
7. **Idempotency.** Re-dropping a study whose `study_uid` exists is a no-op unless its file count grew; if it grew, re-parse and set status back to `received`. *Verify:* drop the same dir twice → one row, one agent trigger (the `Idempotency-Key` also guards).
8. **Reset and seeding** (used by 10): `reset` deletes `studies`, `series` and downstream rows for the demo patients, moves their DICOM back to a `backlog/` source, and leaves `cache/<SeriesUID>/` in place so reruns reuse results. *Verify:* reset, drop T0 → analysis reuses the cache and completes in seconds.

## Parameters

| Parameter | Value | Source |
| --- | --- | --- |
| Poll interval | 2 s | proposed, unmeasured |
| Stability window | 5 s | 00 |
| Min instances (non-localizer) | 100 | `scripts/b1_series_select.py` |
| Max slice thickness | 2.5 mm | same |
| Axial tolerance | 0.05 on \|IOP\| | same |
| Soft / sharp kernel lists | above | same, from `data/README.md` pitfalls |
| Timepoint key | `StudyDate` order within patient | NLST dates are 1999/2000/2001 Jan 2, verified on 134503 |
| Day offsets | `scr_days0/1/2`; neg-neg-pos: `days` split on `/` | `nlst_picked_prsn.csv` (8 patients), `nlst_neg_neg_pos.csv` (4) |

## Gotchas

- **`StudyDate` is not time.** NLST dates are fake (Jan 2 of 1999/2000/2001); LIDC's are `20000101`. Use them for *order* only. Intervals and VDT must come from the sidecar. Never subtract two `StudyDate`s.
- **Every NLST study has 2–3 look-alike series:** a 1–2-image localizer (`T20s`), a soft `B30f` and a sharp `B50f`, both ~150 slices at 2 mm. Without the kernel rule you'd pick whichever sorts first.
- **`ConvolutionKernel` can be multi-valued.** Read it as a list (B1 does) and join for display.
- **LIDC studies carry SEG and SR series** (8 each for 0052) plus, in some cases, non-reader QIN challenge SEGs (e.g. 0766). Intake records them; nothing downstream should treat a SEG as ground truth for the product.
- **LIDC has one study per patient.** It gets `T0` with no priors, so compare/growth views are empty by design. Its calendar values are placeholders too (`day_offset` null unless a sidecar row exists).
- **Sharp-only studies exist** (4 LIDC GE BONE-only; NLST 100005, 100288, 109965 single studies). They pass only through the flagged fallback; surface the flag in the agent log rather than hiding it.
- **Slice positions can be off-grid** (LIDC 0123 at 0.4 voxel; some NLST series have non-integer HU after rescale; from 04). Record a `geometry_warning` on the series if slice spacing varies by > 0.1 mm; 04 decides what to do. (Check is **unverified**.)
- **Copies in progress.** A slow `cp`/`rsync` from the drive can pause longer than 5 s on a large series. If a study is later extended, step 7 handles it; log it so a half-ingested study isn't silently analyzed.
- **Don't parse pixel data here.** `stop_before_pixels=True` is why 44 studies took ~4 s in B1.
- **Moved files need the same filesystem** for an atomic `rename`. If `inbox/` and `studies/` are on different mounts, copy-then-delete and verify counts first.
- **PHI.** Store only IDs, dates, kernel and geometry. Don't copy patient name, birth date or institution into the registry or the agent log. (The NLST/LIDC test data is de-identified; the rule is for the habit.)

## Acceptance tests

| # | Test | Expect |
| --- | --- | --- |
| I1 | Drop all 44 staged studies into `inbox/` (any order) | 44 `studies` rows, 44/44 with exactly one `selected` candidate (37 soft + 7 flagged fallback); total header time ≤ ~10 s (B1: ~4 s) |
| I2 | 134503: drop T1, then T0, then T2 | after each drop the `rank`/`timepoint` are correct; final `T0/T1/T2` = 23/380/800 days; the selected series are the `B30f` ones |
| I3 | LIDC-IDRI-0052 | 1 eligible CT; SEG/SR recorded as `not CT`; `timepoint = T0`; no priors |
| I4 | Copy a study in slowly (pause 8 s mid-copy) | no `received` row until the copy has been quiet 5 s; if the copy resumes later, the file count is updated and the status resets |
| I5 | Drop the same study twice | one row, one agent trigger |
| I6 | A directory of non-DICOM files, and a truncated `.dcm` | `failed` with a readable `failure_reason`; the worker keeps polling |
| I7 | Reset + redrop T0 | no extra analysis time: results come from `cache/` |
| I8 | Restart the worker mid-poll | the registry survives; an incomplete inbox study is re-evaluated, not duplicated |

I2 and I3 feed 11-acceptance. No test here has been run.

## Measured performance

Only the prep scripts have numbers (Oct 24, laptop 3080 and spark-2): header selection of 44 studies ≈ 4 s total (B1); NIfTI conversion 0.1–0.6 s per study, 85 s total (B2). **No watcher, stability or SQLite timing exists.**

## Snippets

Eligibility core (the B1 rule order; trimmed):

```python
def eligible(s):                              # s = series dict from the header
    if s["modality"] != "CT":                   return False, "not CT"
    if s["localizer"] or s["n"] < 100:          return False, f"localizer/few ({s['n']})"
    if not s["axial"]:                          return False, "not axial"
    if not (0 < s["thickness"] <= 2.5):         return False, f"thick ({s['thickness']} mm)"
    ks = {k.lower() for k in s["kernels"]}
    if ks & SOFT:                               return True,  f"soft {s['kernels']}"
    return False, f"sharp/unknown {s['kernels']!r}"
```

Timepoint rank (idempotent, run after every insert):

```python
rows = db.execute("select study_uid from studies where patient_id=? "
                  "order by study_date, received_at", (pid,)).fetchall()
for rank, (uid,) in enumerate(rows):
    off = offsets.get((pid, rank))               # day_offsets.csv
    db.execute("update studies set rank=?, timepoint=?, day_offset=?, day_offset_source=? "
               "where study_uid=?", (rank, f"T{rank}", off, "sidecar" if off is not None else "none", uid))
```

## Open / unverified

- The entire watcher, stability rule, SQLite writes and reset (steps 1, 7, 8).
- The sidecar file: not generated yet; `patients.cohort` source; demographics fields.
- Whether `rank` re-assignment on late arrival can relabel a study that already has a report (it can; decide whether to block re-ranking once a study is `reported`).
- A `geometry_warning` check, and whether the neg-neg-pos patients (`102537`, `117502`, `113918`, `131156`) need their Y1/Y2 scans flagged as "no reader measurements" (data README).
- Whether the demo drops from the drive in place (cross-mount move) or from a local backlog.
- Where the sidecar and its generator live in the build order (a prep script in `scripts/` is allowed; the file itself must be regenerated on the day).
