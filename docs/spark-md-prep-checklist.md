# Spark MD — Prep Checklist (Oct 19–25)

*Rule: environment, data, benchmarks and notes only. No app code until the day.*

*Oct 24: today's execution plan (tracks, gates, schedule) is in [`plans/2026-10-24-prep-day-plan.md`](plans/2026-10-24-prep-day-plan.md). The throwaway MVP lives outside this directory and is deleted tonight; see `AGENTS.md`.*

## Ty — infra and data

- [ ] **Memory-fraction stress test** on one Spark: SGLang at ~0.50 + full scans through MONAI detection and VISTA-3D while generating, dozens of runs. Record the fraction that never OOMs or hard-reboots.
- [ ] **Arm64 check** on DGX OS: MONAI, SimpleITK, pydicom, TensorRT export install and run.
- [ ] **Sandbox + harness rehearsal:** OpenShell install + policy config, plus the harness bake-off (OpenClaw / Hermes / custom), timed. Write down every command. (Plan Track C.)
- [x] **Sandbox → host:** confirm the sandbox can call a host service on `10.77.0.1` (dummy interface). Loopback can't be allowed by OpenShell policy — done in C3 (enforce-verified); the C4 cable-pull rehearsal was dropped (demos run fully local).
- [ ] **Per-scan timing:** detection and VISTA-3D seconds per scan on one GB10.
- [ ] **SGLang + DFlash2 launch command** saved and verified, with the context length you'll use.
- [x] **Data:** pick and download 5–10 patients (NLST with ≥2 prior screens and a growing nodule; LIDC-IDRI with annotations for ground truth). Put everything on a portable drive.
- [x] **Check TCIA's public NLST clinical subset** for diagnosis timing. (Done: the clinical tables give `candx_days`; see `data/README.md`.)
- [ ] **Local speech recognition** model chosen and tested on the Spark.
- [ ] **Email [info@builderbase.com](mailto:info@builderbase.com):** is a Slack/Discord/Telegram channel required? How long is the top-8 live pitch?
- [ ] If a channel is required: confirm OpenClaw's channel setup (Telegram is likely the quickest) and that alerts queue while offline.
- [ ] **External drive:** copy `spark-md/` (delete `tmp/` first). model weights, SGLang/DFlash2 setup, MONAI bundle, VISTA-3D weights, wheels/pip cache for arm64, speech model, patient data. Don't count on venue wifi.

## Joyce — story, pitch, QA

- [ ] Rehearse the voiceover against the storyboard with a timer; trim to fit 3:00.
- [ ] Decide the cold-open wording once the patient is chosen.
- [ ] Plan recording: screen capture tool, mic, and a phone or camera for the cable-pull shot.
- [ ] Draft the stack card and the "not for clinical use" overlay.
- [ ] Write the exact voice command phrases and practice them.
- [ ] **Writeup skeleton** (prose only): problem, who pays, why local, what it does, stack, data credits (TCIA: NLST, LIDC-IDRI), "not for clinical use." Fill in the numbers on the day.
- [ ] **Recording plan for 16:30–17:45 on the day:** tool, mic, export settings, upload test. Do a dry run of record → edit → export in under an hour.
- [ ] **Live pitch** (top 8, 18:30): a short version of the storyboard script, assuming a live demo on the GB10.

## Day-of time anchors

> **Superseded Oct 25** by the organizer announcement: hacking 10:10, freeze 15:15, video under 2:00 + repo due **17:30** with the GB10 returned, deck 19:00. See `docs/build/12-day-of-runbook.md`. Original anchors below for history.

- 08:30 arrive (doors; the Oct 23 email also says 9:00, so plan for 8:30), set up the GB10 from the external drive
- 10:00 build starts
- ~16:30 video freeze: Joyce records what works
- 17:45 upload video, writeup and feedback form
- 18:00 hard deadline

## Bring on the day

- [ ] Both laptops + chargers (Ty: MacBook Air M2)
- [ ] USB-C → Ethernet adapter for the MacBook
- [ ] Ethernet switch + power, 2+ cables (Mac, event box)
- [ ] Power strip or extension cord (outlets are limited)
- [ ] External drive: the `spark-md/` project dir (`data/`, `models/`, `docs/`, wheelhouse, container tarballs, notes)
- [ ] Ethernet cable (for the cable-pull shot)
- [ ] USB mic or headset for voice commands
- [ ] Phone tripod / camera for B-roll