# Spark MD: demo walkthrough (recording, Oct 25)

Build `34ad051`. Ty runs the terminal; Joyce does every click. Times are from the 16:08 warm-up run (thinking off).

## 0. Setup (before the camera rolls)
1. Box terminal: `DEMO_BASELINE=1 ~/spark-md-app/bin/sparkmd-demo --wait`
   (restores the baseline: 100005 T0 already reviewed by Joyce; relaunches the app; waits for Enter).
2. Maximize/fullscreen the app. Voice: mute (speaker icon) unless the mic was tested.
3. **Pull the LAN cable; turn Wi-Fi off.** (Film this: the unplug shot.)
4. Start screen capture.

## 1. Opening (~10 s, no clicks)
- Worklist: patient rows (100005 with 1 reviewed screen, 100285, 100288, LIDC-IDRI-0052), all local.
- Footer: "Research demo, not for clinical use · Local only · Air-gapped". System page: network monitor ~0 bytes sent, links down.
- Optional: open 100005 to show a reviewed patient (pills T0 ✓ · T1 ● · T2 ●, Lung-RADS 3, letter in the inbox).

## 2. A new scan arrives (Ty presses Enter)
- Replay banner: "Time machine replay · 134503 · T0". The hero appears in the worklist.
- Agent log (keep visible): get_study → select_series → run_analysis.
- ~25-30 s later: banner "Waiting for radiologist". **Edit point: label "time skipped" or 2×.**

## 3. Radiologist review of T0 (Joyce)
1. Open **134503**. Header: "Patient 134503 · 1 screen".
2. **3D anatomy**: auto-orbit; toggle Vessels/Skeleton once; "Focus nodule".
3. **CT slices**: color by default; click a nodule marker above the slider; box on the nodule.
4. **Assessment**: 2 nodules marked Proposed (LLL ~6.5 mm, RUL ~5.0 mm) → **Confirm all**.
5. Instantly: **Lung-RADS 3**, "6-month LDCT" (computed by code, not the AI).
6. Agent log: "Confirmed: Lung-RADS 3. Drafting reports." → drafts in ~20 s.
7. **Review & approve** → radiology report → **Approve** → PCP letter → **Approve** → toast "Delivered to Primary care physician".

## 4. One year later: T1 arrives by itself (time machine)
- Banner switches to T1 (~3 s after the T0 approval). Agent triages; ~30 s to "Waiting for radiologist". **Edit point.**
1. Open T1 (pill **T1**; header "Patient 134503 · 2 screens"; T0 ✓).
2. **Compare** tab: prior 6.5 mm → current 10.4 mm, +3.9 mm over 357 days; both key slices boxed.
3. **Confirm** → **Lung-RADS 4B** + management (diagnostic CT / PET-CT / tissue sampling or referral).
4. The agent sets priority **elevated**: the hero jumps to the top of the worklist and appears under **Priority patients** in the sidebar.
5. Drafts in ~20 s.

## 5. Talk to the scan (after the T1 drafts)
- Chips, in order: **"Show me the nodule"** (camera flies) → **"Compare it to last year"** → **"Why did you flag this?"** (~5 s each; every number matches the Assessment panel).
- With voice (only if tested): hold Space and say the exact chip phrase.

## 6. Approve T1 and close
1. **Review & approve** → radiology → **Approve** → PCP letter → **Approve**.
2. **Inbox**: letters for the hero T0 + T1 (and 100005's from the baseline).
3. Banner "done". Close on the network monitor (~0 bytes sent) and the footer.
4. Optional: Sybil card, only if its NLST training-overlap caveat is readable.
5. Stop capture.

## Retake
Re-run `DEMO_BASELINE=1 ~/spark-md-app/bin/sparkmd-demo --wait` → Enter (~15 s to reset). Cable/Wi-Fi stay off.

## Don't
- Open 100288 (failed proposal) or 100285 (false-positive 27 mm candidate) on camera.
- Edit a diameter on camera unless it's a planned beat.
- Run any test/QA script during recording (they write to the on-screen agent log).
- Speed anything up without an on-screen "2×"/"time skipped" label in the edit.

## After recording
Wi-Fi on, cable in → upload video → final push/tag → wipe the box (12 §Recording procedure D) → return by 17:30.
