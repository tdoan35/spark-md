# Spark MD — 3-Minute Demo Storyboard

*Owner: Joyce (story, voiceover, recording). Joyce also plays the radiologist on screen.*

> **Oct 25 (organizers): the video must be under 2:00**, due 17:30 with the repo. This 3:00 cut needs a recut by Joyce: keep the cold open, the box/unplug, the time machine with the agent log, Confirm and Approve; drop or shorten the extras and voice beats. Recording 15:30–16:45 (`docs/build/12-day-of-runbook.md`).

## 0:00–0:20 — Cold open

**Visual:** black screen, white text: "Patient 1. Three annual lung screenings. Diagnosed with lung cancer after the third." Their three scans fade in side by side. **VO:** "This patient's cancer was diagnosed in year three. What if their scans had been read by an agent that never sleeps?"

## 0:20–0:35 — The box

**Visual:** the Dell Pro Max on a desk. The network cable gets unplugged; a network monitor drops to zero. **VO:** "Everything you're about to see runs on this one box. Offline. Patient data never leaves."

## 0:35–1:20 — The time machine

**Visual:** split screen. Left: the agent's live activity log ("new study detected → selecting thin-slice series → segmenting lungs → 1 candidate found"). Right: a rotating 3D lung with a small nodule glowing.

- **Year 1 arrives:** small nodule found; agent recommends routine follow-up and logs the patient for tracking.
- **Year 2 arrives:** agent matches the same nodule, flags significant growth, raises the Lung-RADS category, moves the patient to the top of the worklist, drafts the PCP letter.

**On-screen text:** "Diagnosed: year 3. Flagged by the agent: year 2."

## 1:20–2:05 — Talk to the scan

**Visual:** the radiologist's view. Joyce speaks:

- "Show me the nodule." The 3D view rotates and zooms in.
- "Compare it to last year." Side-by-side slices with the growth measurement.
- "Why did you flag this?" The agent answers in two sentences, citing size, growth and density.

She clicks **Approve**; the PCP letter lands in a mock EHR inbox.

## 2:05–2:40 — One scan, several screenings

**Visual:** same scan; panels slide in one by one:

- Lung nodules ✓
- Emphysema: % of lung tissue below the density threshold
- Bone density: measured from a vertebra, flagging possible osteoporosis
- Coronary calcium (labeled "experimental")

**VO:** "The hospital paid for one scan. The agent screened for four conditions."

## 2:40–3:00 — Close

**Visual:** stack card: OpenClaw + NemoClaw + OpenShell · Qwen3.8-27B · MONAI + VISTA-3D · one Dell Pro Max with GB10 · 0 bytes sent to the cloud. **VO:** "In 2017 I spent weeks just preprocessing these scans for a Kaggle competition. Today, an agent reads them, end to end, on one box." **Small text:** "Research demo, not for clinical use."

## Production notes

- **Patient selection decides the opening.** If no patient has a confirmed later diagnosis in the public data, change the cold open to "This nodule grew. Would anyone have caught it?"
- **Record real runs.** Any sped-up footage gets "2×" in the corner.
- **Keep the agent log visible** through the time machine; it's what shows this is an agent, not a pipeline.
- **Voice commands are a fixed set**, so rehearse the exact phrasing.
- **Cut order if behind:** coronary calcium → bone density → voice (fall back to clicks) → emphysema.

## QA checklist (Joyce, as the user)

- Can a first-time viewer follow the time machine without narration?
- Do all three voice commands work on the first try, five times in a row?
- Does the "why" answer cite real numbers from the findings, not invented ones?
- Does Approve reliably land the letter in the inbox?
- Does the whole flow survive a cold restart of the app?