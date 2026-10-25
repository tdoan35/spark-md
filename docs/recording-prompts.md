# Spark MD: computer-use recording prompts (GNOME screen-recorder clips for HyperFrames)

Ty's plan (Oct 25, ~16:20): record several short screen clips of real runs (GNOME's built-in recorder; OBS was dropped after it cut a take); HyperFrames assembles them with a TTS script.
Clips are cut together, so each one only needs its own beat. Everything shown is a real run on the GB10.

## Ty: one-time setup before the agent starts
1. Recorder: GNOME 46's built-in screen recorder (X11 session, 1920x1200). **Ctrl+Shift+Alt+R** opens the recording UI; choose **Screen**, turn **Show Pointer** on, press the round record button. **Ctrl+Shift+Alt+R** again (or the red stop button in the top bar) stops. Files land in `~/Videos/Screencasts/` as `.webm` (no length limit in this UI). It records the **whole screen**, so the Spark MD window must be maximized and on top, with nothing else open over it.
2. Close the recorder app you used before. The agent runs the launcher from its own shell on the box, not a desktop terminal.
3. Theme light; voice muted unless the mic was tested. The agent (re)starts the app itself with the launcher command.
4. For this submission video the computer-use agent operates the UI, including Confirm and Approve, standing in for the radiologist (Ty's decision, Oct 25). The product's gate is unchanged: only the loopback UI can confirm/approve; the AI agent in the sandbox cannot. In the live demo Joyce clicks.
5. The computer-use agent needs internet, so these clips are recorded **online**. Don't show the network monitor in them. The unplug / "0 bytes sent" shot is a separate clip Ty and Joyce film by hand at the end (Clip 6).

## Master prompt (paste first)
```
You are operating the Spark MD demo on a Dell GB10 (Ubuntu desktop) to record short screen clips with GNOME's built-in screen recorder
for a hackathon video. Spark MD is a lung CT screening research demo: the AI detects and proposes, code computes
Lung-RADS, and the radiologist (you, operating the UI for this video) confirms measurements and approves reports.

HARD RULES
1. You operate the UI as the radiologist would, including "Confirm all", "Confirm" and "Approve" when a clip says
   so. Before each of those clicks, pause ~1.5 s with the pointer on the button so the viewer sees it. Never edit
   a diameter (keep the proposed values) unless a clip says so.
2. You are running ON the GB10 itself (user dell). Use your own shell/command tool directly; don't open or type
   into a desktop terminal. You may run exactly two commands, nothing else (no sudo, kill, reset, stop, rm):
   a) Launcher (kills any running Spark MD app, restores the demo baseline in ~15 s, opens a fresh app window on
      the box display, then exits):
        DEMO_BASELINE=1 ~/spark-md-app/bin/sparkmd-demo --no-replay
   b) Start the hero replay (the new scan arrives):
        curl -s -X POST http://127.0.0.1:8100/api/demo/replay -H 'Content-Type: application/json' -d '{"patient_id":"134503","timepoints":["T0","T1"]}'
      It must return "replaying":true. Never close the Spark MD window by hand.
3. Recording uses GNOME's built-in screen recorder, which records the WHOLE screen. Before each start: the Spark
   MD window is maximized and frontmost, nothing else on top (no terminal, no other app, no notifications).
   START: press Ctrl+Shift+Alt+R; in the panel select "Screen" (not Selection/Window), make sure "Show Pointer" is
   on, then click the round record button. Wait ~1 s for the red recording indicator in the top bar.
   STOP: press Ctrl+Shift+Alt+R again (or click the red stop button in the top bar).
   One clip per recording. After stopping, run `ls -t ~/Videos/Screencasts | head -1` and report the clip name,
   that file name and the approximate length.
4. Mouse: slow and deliberate. Move to an element, pause ~1.5 s so a viewer can read it, then click. No frantic
   scrolling, no hovering over unrelated UI. Keep the agent log panel visible where the clip says so.
5. Waits are normal: the agent triages a new scan in ~30 s and drafts reports in ~20 s. During a wait longer than
   5 s, stop recording and resume with a new recording when the next beat is ready (unless the clip says keep rolling).
6. If anything looks wrong (error toast, blank 3D, missing data), stop recording and tell Ty. Don't improvise.
Acknowledge, then wait for "Clip 1".
```

## Clip 1: a new scan arrives (~20 s)  → script 0:00-0:20
```
Clip 1.
0. From your shell, run command (a), the launcher. Wait until it prints "done (no replay)". Bring the new Spark MD
   window to the front and maximize it; close anything on top of it.
1. START recording (rule 3). Hold on the worklist 3 s (patient rows; footer "Research demo,
   not for clinical use").
2. From your shell, run command (b) (the replay starts; no window switch needed). Keep recording.
3. When the replay banner "Time machine replay · 134503 · T0" appears and the hero row shows in the worklist,
   open the Agent activity panel (or the agent log on the study) and hold 5 s on the tool calls
   (get_study, select_series, run_analysis).
4. STOP recording (rule 3). Report "Clip 1 done, ~N s" + the file name.
5. Wait until the banner says "Waiting for radiologist" (~30 s). Then say "Ready for Clip 2".
```

## Clip 2: nodule + confirmation + Lung-RADS (~35 s)  → script 0:20-1:00
```
Clip 2.
1. START recording (rule 3). Open patient 134503 (worklist row). Hold 2 s on the header ("Patient 134503 · 1 screen").
2. 3D anatomy tab: let it orbit 4 s. Click the Vessels toggle on, hold 2 s, off. Click "Focus nodule", hold 3 s.
3. CT slices tab: hold on the color slice 2 s; click a nodule marker above the slider; hold 3 s on the boxed nodule.
4. Assessment panel: move the pointer over each proposed nodule row (lobe, proposed diameter), 2 s each.
5. Pause 1.5 s on "Confirm all", then click it. Wait for the category to appear.
6. Hold 4 s on "Lung-RADS 3" and the management text "6-month LDCT".
7. STOP recording (rule 3). Report.
```

## Clip 3: chat + risk estimate (~25 s)  → script 1:00-1:20
```
Clip 3. Wait until the agent log shows "Drafts ready" (~20 s after the confirm) so the model is idle.
1. START recording (rule 3). In the chat rail, click the chip "Show me the nodule". Hold until the answer finishes (~5-13 s);
   the camera flies to the nodule by itself. Do not type.
2. Click the chip "Why did you flag this?". Hold until the answer finishes; hold 2 s more on the text.
3. Scroll the Assessment panel to the Sybil risk card below the management text. Hold 4 s so the card's
   caveat text ("research model, precomputed, not validated…", NLST training overlap) is readable.
4. STOP recording (rule 3). Report.
```

## Clip 4: summary report + human approval (~25 s)  → script 1:20-1:35
```
Clip 4.
1. START recording (rule 3). Click "Review & approve" in the header. The report sheet opens on the radiology report.
2. Slowly scroll the report so the Findings and "Lung-RADS 3" lines are visible; hold 3 s.
3. Pause 1.5 s on "Approve", then click it. Wait for the "Approved by …" state.
4. Switch to the PCP letter tab; hold 3 s on the first paragraph.
5. Pause 1.5 s on "Approve", then click it. Wait for the toast "Delivered to Primary care physician".
6. Open the Inbox (sidebar). Hold 3 s on the delivered letter.
7. STOP recording (rule 3). Report.
```

## Clip 5: one year later: comparison + growth (~35 s)  → script 1:35-1:55
```
Clip 5. After the T0 approvals the replay drops T1 by itself; wait until its banner says "Waiting for radiologist"
(~30 s). Do not record the wait.
1. START recording (rule 3). Open patient 134503. Hold 2 s on the header pills (T0 ✓ · T1).
2. Click the Compare tab. Hold 5 s: prior 6.5 mm vs current 10.4 mm, +3.9 mm over 357 days, both key slices boxed.
3. Pause 1.5 s on "Confirm", then click it. Wait for "Lung-RADS 4B" and the management text; hold 4 s.
4. Click Worklist in the sidebar: the hero is now at the top, marked elevated, and listed under Priority
   patients. Hold 3 s.
5. Reopen 134503; click the chip "Compare it to last year". Hold until the answer finishes.
6. STOP recording (rule 3). Report.
7. (Off camera, not recorded) Open "Review & approve" and approve both T1 reports so the run completes.
```

## Clip 6: air-gapped (Ty + Joyce by hand, no agent, at the end)
1. Close the computer-use agent. Ty: `DEMO_BASELINE=1 ~/spark-md-app/bin/sparkmd-demo --no-replay`.
2. Film (phone): pulling the LAN cable and turning Wi-Fi off.
3. GNOME recorder (Ctrl+Shift+Alt+R → Screen): the System page / network monitor reading ~0 bytes sent with links down, and the footer "Local only · Air-gapped". 10 s.
4. Wi-Fi back on, cable back in.

## Retakes
Any clip can be redone: tell the agent "Retake from Clip 1". It re-runs command (a) (kills the app, restores the
baseline in ~15 s, starts a fresh app) and command (b) at Clip 1 step 2, then replays from Clip 1, recording only the clip(s) being redone
(for later clips it performs the earlier steps unrecorded, including the Confirm/Approve clicks they need).

## Script accuracy notes for Joyce (match the product's real behavior)
- 0:10 "load scans": the scan arrives in the intake; the agent triages it on its own (real, not an upload UI).
- 0:20-0:45 "documented … location and measurement": the AI **proposes** a diameter; the radiologist confirms or edits it.
- 0:45-1:00 Lung-RADS: say it is **computed by deterministic code from the radiologist-confirmed diameters**; the AI never assigns it.
- 1:00-1:20 risk estimate: the Sybil card is a **patient-level 1-6 year risk from a research model (Sybil), precomputed, not validated for clinical use; Sybil was trained on NLST, which this patient comes from**. Not "for the nodule", not a diagnosis.
- 1:20-1:35 report: the agent **drafts** a radiology report and a letter to the primary care physician; **nothing is sent until the radiologist approves**.
- 1:35-1:55: say growth (+3.9 mm in a year) moves it to **Lung-RADS 4B** and the agent raises its priority.
- Any sped-up or cut wait gets an on-screen label ("time skipped" / "2×"). Keep "Research demo, not for clinical use" visible (it's in the footer).
