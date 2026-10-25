# 12: Day-of runbook (Sun Oct 25, PT)

Status: **re-planned Oct 25 ~09:55 for the organizer announcement** (box handed out after 10:10, teams of 4–5 first; **17:30 code lock + video under 2:00 + repo + GB10 returned**; 19:00 pitch deck + top-8 live demos). First draft Oct 25 ~00:30, reviewed ~01:30. Every clock time below is a **proposed** plan, not a measurement. The one measured whole-stack number is the fresh-box rebuild (E10: 90 s, excluding USB copy and model start).
Audience: Ty (and any agent he hands a section). Joyce's sections are marked.

## Rules that decide everything (AGENTS.md + organizers)

1. **Build on the day.** Organizer rule: no prebuilt code (public open source allowed). Nothing in `spark-md-mvp/` or `bench/` goes into the event repo. Specs, scripts under `scripts/` (data prep), benchmarks and notes are allowed. Environment setup (containers, wheels, weights, OpenShell onboard, the box network) is not application code; **application code is written only after hacking begins at 10:10.**
2. **Derived imaging outputs are on the drive** (`derived-b-track.tar`: 36 volumes, detections, hero measurements). Default: **regenerate them on the day**, and use the tar only to diff your results. Using it as the product's data counts as pre-built unless an organizer says otherwise. Ty decides.
3. **Air-gapped at runtime.** Organizer rule: all inference runs locally on the GB10. Venue Wi-Fi is allowed for coding agents and syncing; the GB10 product runs with the cable out for the recording (10 §Network monitor).
4. **Human gates:** only a person confirms diameters and approves reports. No agent, harness or script does.
5. **Honesty:** "Research demo, not for clinical use" on screen, 2× labels, agent log visible, unmeasured = unverified.
6. **Secrets:** the venue Wi-Fi and GB10 passwords are in the organizer announcement. Never put them in the repo or the docs.

## Organizer schedule (announcement, Oct 25)

| Time | What |
| --- | --- |
| 09:50 | Opening ceremony |
| 10:10 | Computer distribution + hacking begins. Team lead claims the GB10 (team must be on BuilderBase); teams of 4–5 go first |
| 13:00 | Lunch |
| **17:30** | **Code locks. Round 1 submission due: video under 2 min + repo. Return the GB10.** |
| 18:00 | Project submission deadline (video, repo). **Unclear vs 17:30; plan for 17:30** |
| 19:00 | Pitch deck deadline. Round 2: top-8 live demos (3 min demo + 2 min Q&A) |
| 20:00 / 21:00 | Judges deliberate + awards / venue clears |

## Timeline (proposed)

| Time | What | Owner |
| --- | --- | --- |
| before 10:10 | Mac on the event LAN (10.78.0.2/24, no router). Drive checksums run from the Mac. Joyce: organizer questions (§Open) | Ty, Joyce |
| 10:10 | **Build start on the Mac** (§Mac-first start): create the event repo, 00 contract check (5 min), spawn W, I (rules), U. Ty gets in line for the box | Ty |
| box arrives (~10:30, **unverified**) | Box bring-up R1–R9 (~45–60 min). Mac agents keep building | Ty (+ infra agent on the box) |
| ~11:00 | **G1** worker skeleton + fixtures serve; UI shell on fixtures (on the Mac) | |
| ~11:30 | LLM + sandbox up. Push the repo, clone it on the box, move every agent to the box. **A** starts | Ty |
| 12:30 | **G2** hero T0 through intake + imaging → `awaiting_confirmation` on the GB10 | |
| 13:00 | Lunch. Nobody leaves a GPU job running; `free -g` first | |
| 14:00 | **G3** the spine: confirm → assessment → agent phase 2 → drafts → Approve → outbox | |
| 14:45 | **G4** time machine T0→T1 live; **time it**; decide live / cached / "2×" | |
| **15:15** | **G5 = feature freeze.** 3D/compare only if already working. Only fixes after this; quick acceptance pass (11); clean `tmp`, no secrets in repo | |
| 15:30 | **Video freeze.** Joyce records real runs (§Joyce); box is hers until 16:45 | Joyce |
| 16:45 | Joyce edits (under 2:00). Ty: final acceptance pass on the submitted commit, push the repo, tag it | Joyce, Ty |
| 17:00–17:15 | Upload video, submit repo link (+ writeup / NVIDIA form if still required) | Joyce, Ty |
| **17:30** | **Code lock, Round 1 due, GB10 returned** | Ty |
| 17:30–19:00 | Pitch deck (3 min demo + 2 min Q&A) | Joyce, Ty |
| 19:00 | Deck due; top-8 live demos (if selected) | Joyce, Ty |

Why these gates: against the prep plan we lose ~2 h of box time at the start (box after 10:10 instead of 08:30) and ~45 min at the end (freeze 15:15 instead of 16:00). W, I's rules and U need no GPU, so they start on the Mac and the late box only hits G2 onward. 06 (60–90 min) and 03 (45 min) are still the longest serial pieces and block G2/G3; 08 needs 1.5–2 h against fixtures; 07's install is 15 + 4 min and runs during bring-up. If G2 slips past 13:00, take the cut list below.

**Voice (V: ASR + TTS) is kept for now; Ty decides by 13:00** (Oct 25 ~10:00). Bring-up still loads whisper.cpp and the TTS image. Proposed (Ty to confirm): cut the extras (calcium, bone density, emphysema) up front; there is no G5 slot left for them and a sub-2:00 video has no room to show them.

## Parallel lanes

Ty's attention is the real bottleneck: keep **at most 3–4 agents running at once** and give each one a lane. `→` = must wait for; `∥` = can run at the same time.

**Bring-up (when the box arrives)**

| Lane | Steps | Waits for |
| --- | --- | --- |
| Box chain | R1 copy → R2 → R3 sudo → R4 docker load → R7 block :8000 → R6 LLM → R8 NemoClaw onboard | serial (R8 needs R6) |
| Box side jobs | R5 venv ∥ R9 npm (+ whisper.cpp/TTS image only if voice is kept) | R1 copy only; run while R4/R6 load |
| Network + coding agent | box on the switch (10.78.0.10) and on venue Wi-Fi ∥ Mac SSH config for the box ∥ Claude Code on the box | nothing; do during R1's copy |
| Joyce | organizer questions, storyboard recut to under 2:00, tripod/B-roll setup, deck + writeup skeletons with credits | nothing |

**Build (10:10 →)**

| Wave | Starts | Agents in parallel | Unblocks |
| --- | --- | --- | --- |
| 1 | 10:10, **on the Mac** | **W** worker + registry ∥ **I** rules (10 min), then B1/B2 imaging code (runs on the box later) ∥ **U** UI on fixtures | G1, G2 |
| — | box bring-up done (~11:30) | move the repo and all agents to the box (§Mac-first start) | |
| 2 | when R8 is done and W serves `/mcp` | **A** agent joins W, I, U | G3 |
| 3 | after G2 | **H** harness/replay (as U or I frees up) | G4 |
| 4 | after G3 | **Q** QA; U on 3D/compare; (V voice and I on extras only if Ty keeps them) | freeze |
| Joyce, all day | 10:10 | radiologist QA on each gate, storyboard recut, writeup, end card, shot list, deck skeleton | video at 15:30 |

Serial points nobody can parallelize: the 00 contract check at 10:10 (5 min, before any agent starts), W's `registry.py` (I and A import it), the Mac → box move, and the GPU (one heavy job at a time: detection runs, LLM already resident).

## Mac-first start (10:10 until the box is up)

The box arrives after 10:10 and needs ~45–60 min of bring-up; W, I's rules and U don't need the GPU, so they start on `tys-macbook-air`.

- **Mac toolchain (checked Oct 25 09:50):** Python 3.12.2, Node 26.8.1 / npm 11.19, uv 0.8.15, git 2.51, Docker 29.4. The box uses Node 22.23.4 from `nodehouse/`; the UI kit was verified with both (nodehouse README).
- **Same versions as the box:** copies of `wheelhouse/requirements.{in,lock}` and `nodehouse/ui/package{,-lock}.json` are in the Mac's project dir. Python: `uv venv -p 3.12` and install only the packages the layer needs, at the lock's versions (no torch/MONAI on the Mac). UI: copy both `nodehouse/ui` files into the repo's `ui/` and `npm ci` (online on the Mac; Electron fetches its macOS binary). **No new dependency outside the lockfiles without Ty's OK**: the box installs offline from the drive.
- **Write Linux-clean code:** no macOS paths, no `/Volumes`, config from env (00 §Env). Imaging code (B1/B2, detector) can be written on the Mac but only runs on the box.
- **Event repo:** create it on the Mac (name per BuilderBase); push to GitHub over venue Wi-Fi (needed for submission anyway) and `git clone` on the box. Fallback without GitHub: `ssh box 'git init --bare ~/<repo>.git'`, push over the LAN, clone on the box.
- **Specs and git (Oct 25 ~11:20):** specs now live in the repo's `docs/` (old paths are symlinks), so git carries them; no docs rsync. The box clone `~/spark-md-app` pulls from the LAN bare repo `~/spark-md-app.git` (Mac remote `box`); the Mac pushes to GitHub.
- **The move (~11:30):** stop the Mac agents at a commit, push, clone on the box, restart each agent on the box with the same prompt plus "continue from the last commit". From then on the Mac is editor + SSH only.

**Kickoff prompts for the Mac (10:10; paste, don't summarize; `<repo>` = the event repo path on the Mac):**

```
You are agent W (worker + registry) on Spark MD (Dell x NVIDIA hackathon; code locks 17:30).
You run on Ty's Mac (macOS arm64) until the GB10 is up; the code must run on the box later
(Linux aarch64, Python 3.12, versions from ~/Desktop/spark-md/wheelhouse/requirements.lock).
Read, in order, under ~/Desktop/spark-md: AGENTS.md, docs/build/README.md,
docs/build/00-architecture.md, docs/build/03-intake-registry.md, docs/build/06-worker-api.md.
Build only your layer, from the spec, in <repo>. Do not read or copy any MVP code.
Contract: 00 (v0.6+). If you must change it, edit 00 in the same change and note it at the top.
You own registry.py (I and A import it): land it first and commit.
Hard rules: Lung-RADS and all medical math in tested code, never the LLM; air-gapped at runtime;
no approve/confirm tool for the agent; only a human confirms diameters or approves reports.
No new dependencies outside the lockfile without asking. No macOS-only paths.
Target: G1 by ~11:00 (curl :8100/api/health, fixtures serve, contract test passes).
Done = your spec's acceptance tests pass. Report: what passed, commands run, what is unverified.
Commit small and often. Be concise.
```

```
You are agent I (imaging + rules) on Spark MD (Dell x NVIDIA hackathon; code locks 17:30).
You run on Ty's Mac (macOS arm64) until the GB10 is up; the code must run on the box later
(Linux aarch64, Python 3.12, CUDA, versions from ~/Desktop/spark-md/wheelhouse/requirements.lock).
Read, in order, under ~/Desktop/spark-md: AGENTS.md, docs/build/README.md,
docs/build/00-architecture.md, docs/build/05-clinical-rules.md, docs/build/04-imaging-pipeline.md.
Build only your layer, from the spec, in <repo>. Do not read or copy any MVP code or scripts/lungrads/.
Order: (1) the Lung-RADS engine from 05, its test vectors first (they are the contract), ~10 min;
(2) series -> volume code from 04 (B1/B2), runnable on the Mac only with pure-Python deps;
(3) detector + A7 proposals: write against 04, run only on the box (GPU) after the move.
Contract: 00 (v0.6+). Import registry.py from W; don't write your own.
Hard rules: Lung-RADS and all medical math in tested code, never the LLM; the agent never
proposes or edits a diameter; only a human confirms diameters or approves reports.
No new dependencies outside the lockfile without asking. No macOS-only paths.
Done = your spec's acceptance tests pass. Report: what passed, commands run, what is unverified.
Commit small and often. Be concise.
```

```
You are agent U (UI) on Spark MD (Dell x NVIDIA hackathon; code locks 17:30).
You run on Ty's Mac (macOS arm64) until the GB10 is up; the app must run on the box later
(Linux aarch64, Electron 44, Node 22, offline npm cache from nodehouse/).
Read, in order, under ~/Desktop/spark-md: AGENTS.md, docs/build/README.md,
docs/build/00-architecture.md, docs/build/08-ui.md.
Build only the UI, from the spec, in <repo>/ui, against 00 and fixtures (W's worker comes later).
Start from ~/Desktop/spark-md/nodehouse/ui/package.json + package-lock.json (exact versions).
Do not read or copy any MVP code. Contract: 00 (v0.6+).
Hard rules: no CDNs, no web fonts from the network, no Web Speech API, no telemetry; show
"Research demo, not for clinical use"; Confirm and Approve are human clicks only.
No new npm packages outside the lockfile without asking (the box installs offline).
Target: G1 by ~11:00 (UI shell renders fixtures).
Done = your spec's acceptance tests pass. Report: what passed, commands run, what is unverified.
Commit small and often. Be concise.
```

## Box bring-up (when the box arrives)

Each step names its spec and measured time. Do them in this order; verify before moving on.

| # | Step | Spec | Measured |
| --- | --- | --- | --- |
| R1 | Mount the drive (exFAT, transport-only). **Copy to local NVMe first, skipping `validation/`** (13 GB of benchmark evidence the build doesn't need), **then `sha256sum -c` the local copies** (one drive read instead of two). Delete macOS `._*` files from the copy (`find ~/spark-md -name '._*' -delete`): a `._*.whl` breaks `pip --find-links` | 01 | copy ~10–15 min for ~73 GB (**estimate**). Drive checksums: see §Open |
| R2 | OS/Docker/GPU checks; `free -g` baseline | 01 | seconds |
| R3 | `sudo` console: `spark0` (10.77.0.1/32), add user to `docker` group if needed | 01 | **spark0 on GB10 unverified at the venue** (exists on spark-2) |
| R4 | `docker load` TensorFold + sandbox tars (+ TTS only if voice is kept); extract the HF cache tar | 02, E10 | 34 s + 3 s load; 10 s extract |
| R5 | wheelhouse venv: `pip install --no-index --find-links … -r requirements.lock` | AGENTS.md | 39 s |
| R7 | **Before R6 when the box is on venue Wi-Fi** (the LLM binds `0.0.0.0:8000`): block `:8000` on every non-loopback interface except what the sandbox needs (console, iptables) | 02, 01 | **method unverified** |
| R6 | Start the LLM: `HOST=0.0.0.0 PORT=8000 SERVED_NAME=qwen3.8-27b PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16 PREPARE=0 ./start.sh`; verify `/v1/models` | 02 | 31–70 s |
| R8 | NemoClaw installer + onboard (`NEMOCLAW_DISABLE_TELEMETRY=1`, provider `vllm`, `restricted`); remove cloud presets; verify the sandbox reaches `host.openshell.internal:8000` | 07 | 75 s + 42 s–2 min |
| R9 | `npm ci --offline` from `nodehouse/`; whisper.cpp build and TTS image only if voice is kept | 08, 09 | 4 s npm; others see spec |

**First prompt (when the box arrives, agent on the box; paste as is):**

```
You are the infra agent for Spark MD on the event GB10 (Dell x NVIDIA hackathon, today; code locks 17:30).
The external drive (exFAT, label "avocado") is plugged in. Find it with lsblk/findmnt.
1. Copy the drive's AGENTS.md, CLAUDE.md and docs/ to ~/spark-md first, then read in order:
   AGENTS.md, docs/build/12-day-of-runbook.md (§Box bring-up, §Parallel lanes), docs/build/01-box-setup.md,
   02-llm-serving.md, 07-agent.md.
2. Do bring-up R1-R9 from 12 in the order listed (R7 before R6). SPARKMD_HOME=~/spark-md.
   Copy the rest of the drive EXCEPT validation/ to local NVMe, then verify the local copies with
   sha256sum -c (DRIVE-TARS.SHA256SUMS, models/, wheelhouse/, nodehouse/, data/); delete ._* files.
   Never run from the drive. Run R5 (venv) and R9 (npm) while R4/R6 load. R8 only after R6 answers
   /v1/models. Voice is kept for now (Ty decides by 13:00): do R9 fully, incl. whisper.cpp + TTS image.
3. Rules: environment setup only; application code is being written by other agents. Export
   HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NEMOCLAW_DISABLE_TELEMETRY=1 in every shell. No :latest
   tags, no pulls. The box is on venue Wi-Fi only for coding agents: port 8000 must not be reachable
   from it. free -g before GPU jobs, MemAvailable >= 15 GiB. Anything needing sudo (spark0, docker
   group, iptables, nmcli): print the exact command for Ty to run at the console and wait.
   Speed first: stuck 15 min -> take the spec's fallback and tell me in one line.
4. Keep a one-line-per-step log (step, time taken, pass/fail) and report after each step.
Target: LLM on 127.0.0.1:8000, sandbox reaching it, venv + npm ready ~45-60 min after the box arrives.
```

Set `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NEMOCLAW_DISABLE_TELEMETRY=1` in every shell; never `:latest` tags. If R6 fails: 02 §Fallbacks. If R8 fails: reopen the harness decision only now (custom loop in OpenShell), and tell Ty before spending more than 20 minutes.

## Agents (10:10 onward)

Ty builds everything; "agent" = a coding-agent session he starts and supervises. **Code starts on the Mac at 10:10 (§Mac-first start) and moves to the box once bring-up is done; from then on every agent runs on the box** (in tmux, opened from the Mac over SSH): the Mac can't run the stack (no macOS in `wheelhouse/`/`nodehouse/`). Coding agent on the box: **Claude Code over venue Wi-Fi**; fallback: the dual-Spark DeepSeek V4.1 Flash cluster through the Mac (`ssh -R 8091:100.114.195.121:8091 <box>` → `http://127.0.0.1:8091/v1` on the box, model `DeepSeek-V4.1-Flash-1017`; close the tunnel before recording). spark-1 + spark-2 are never a Spark MD runtime; the box is the only GB10 running Spark MD and shares GPU memory with the product, so **one heavy GPU job at a time** and `MemAvailable ≥ 15 GiB`.

| Agent | Builds | Spec(s) | Starts when | Machine |
| --- | --- | --- | --- | --- |
| W: worker + registry | intake, registry, routes, SSE, MCP, trigger, gates | 03, 06 | 10:10 | Mac → box |
| I: imaging + rules | Lung-RADS port + tests; series → volume → detector → A7 proposals | 05, 04 | 10:10 (rules first, 10 min) | Mac → box (detection on the box only) |
| A: agent | skill text (triage + Q&A), MCP binding, hook trigger, policy preset, two-phase triage, **`/api/ask` text path** (`sparkmd/ask.py`; moved from V Oct 25 so the ask chips don't depend on voice) | 07, 08 §ask stream, 09 §Immediate viewer action | prep on the Mac from ~10:30; on the box after R8 and W's `/mcp` | Mac → box |
| U: UI | Electron app on fixtures, then the real worker | 08 | 10:10 (fixtures); switch at G2 | Mac → box (Electron on the box display) |
| V: voice | whisper.cpp, `/api/asr`, push-to-talk, TTS (not `/api/ask`: A owns it) | 09 | after G3, **only if Ty keeps voice** | box |
| H: harness | backlog script, replay, netstats | 10 | after G2 | box |
| Q: QA | acceptance script, cold restart, contention | 11 | continuous from G3 | box |

**Order inside I:** recreate the Lung-RADS engine from 05 first (its vector tables are the contract; never copy `scripts/lungrads/`), then series selection + DICOM → volume from 04, then detection on the hero.

**Kickoff prompt template for agents started on the box** (A, H, Q, V; give each agent its row; paste, don't summarize):

```
You are agent <W|I|A|U|V|H|Q> on Spark MD (Dell x NVIDIA hackathon; code locks 17:30).
Read, in order: AGENTS.md, docs/build/README.md, docs/build/00-architecture.md, then <your specs>.
Build only your layer, from the spec, in the event repo at <path>. Do not read or copy any MVP code.
Contract: 00 (v0.6+). If you must change it, edit 00 in the same change and note it at the top.
Hard rules: Lung-RADS and all medical math in tested code, never the LLM; air-gapped at runtime;
no approve/confirm tool for the agent; only a human confirms diameters or approves reports.
GPU: one heavy job at a time, free -g before it, MemAvailable >= 15 GiB.
Done = your spec's acceptance tests pass. Report: what passed, commands run, what is unverified.
Update the spec's "Open / unverified" and the status file as you go. Be concise.
```

**Interfaces that must agree before anyone builds:** 00 tables and routes, the 03 `studies/series` columns and status ownership, the `confirm` route and `awaiting_confirmation` state, the findings shape with null-until-confirmed fields. W owns the shared `registry.py`; U and I code against 00 and fixtures.

## Gates and what to do when one slips

| Gate | Pass condition | If late by > 45 min |
| --- | --- | --- |
| G1 (~11:00) | `curl :8100/api/health`, fixtures render in the UI, contract test passes | W trims to the 06 "cut first" list |
| G2 (12:30) | hero T0 (134503) ingested, detected, A7 proposals visible in the UI | drop VISTA/lobes (not needed); keep detector-box + A7 only |
| G3 (14:00) | confirm → Lung-RADS from 05 → agent drafts → Approve → letter in inbox, all on the box | cut voice, extras, 3D polish until this passes |
| G4 (14:45) | replay T0→T1 with Joyce clicking, wall time recorded | switch the recording to cached runs, labelled (10) |
| G5 (15:15, freeze) | 11 quick pass passes; no non-loopback requests from the UI | ship what passes; mark the rest unverified in the writeup |

## Cut order

Highest value first to keep: the spine (G3) → time machine → talk to the scan (clicks) → 3D viewer → extras → voice. Cut from the bottom (**Oct 25 re-plan: items 1–2 proposed cut up front, Ty decides**):
1. Coronary calcium, then bone density (storyboard cut order).
2. Spoken answers (TTS), then voice input (clicks remain; the ask chips already exist).
3. Background seeding, T2, the slice carousel.
4. Emphysema.
5. 3D lobes; keep the threshold lung mesh.
6. **Never cut:** the human gates, the disclaimer, the agent log, the network monitor.

## Fallback ladder

- **LLM:** restart → lower memory → other checkpoint → SGLang (unbenched) → no-LLM template mode (02).
- **Harness:** OpenClaw (chosen) → a minimal custom loop inside OpenShell (not run; reopen only if OpenClaw blocks).
- **Measurement:** A7 proposals + radiologist-confirmed diameters (decided). VISTA masks are not used for sizes.
- **Imaging speed:** live → cached results labelled as such (10).
- **UI on the box:** Electron with the default ANGLE backend + `--ozone-platform=x11` (never `use-angle=gl-egl`: frames never reach the GB10 X11 screen, 84a9f17); last resort the same app in a browser at `http://127.0.0.1:8100/`.
- **Coding agent:** Claude Code on the box → DeepSeek cluster through the Mac's SSH tunnel → agents on the Mac pushing to the box.
- **Time:** if the box is unstable after 14:45, freeze what runs and record it.

## Joyce (15:30–17:15)

- **Video under 2:00** (organizers, Oct 25; was ≤ 3:00). Recut the storyboard this morning; the time machine and the human gates are the core.
- Record at the console: **no remote desktop**; network cable out for the opening shot, capture the monitor going to its unplugged state (10). The box goes back at 17:30, so recording ends by 16:45; no re-shoots after that.
- Real runs only. Sped-up footage gets "2×"; cached runs get their label. Keep the agent log on screen through the time machine.
- Joyce clicks Confirm and Approve on camera. Use the ask chips (or her exact voice phrases (09) if voice is kept).
- Cold open wording depends on the patient story: the hero is a cancer diagnosed after T2; never claim an outcome the data doesn't support. The category shown is whatever the engine returns for the diameters she confirms.
- End card: stack (OpenClaw + NemoClaw + OpenShell, Qwen3.8-27B MLX 4-bit on TensorFold, MONAI, one Dell Pro Max with GB10), the disclaimer, and the data credits (below).
- Writeup (if still required): problem, who pays, why local, what it does, stack, credits, limits. State what is unvalidated (measurements need radiologist confirmation; VISTA masks failed validation; growth normalized to 12 months is our interpretation).
- **Pitch deck (due 19:00)** for the top-8 round: 3 min demo + 2 min Q&A. Start the skeleton in the morning; finish 17:30–19:00. If the GB10 is not available again for the live demo, the demo is the video + deck.

## Recording procedure (offline; console only) — written Oct 25 ~13:55

Everything below runs with the box **offline**: Wi-Fi off and LAN cable out also cut every Claude Code session (incl. Ty's advisor), Orca and the Mac's SSH. So the dry run happens online first; the recording itself needs nobody but Ty + Joyce at the console.

**A. Before 15:15 freeze (online)**
1. Every agent: commit, report, stop. `git status` clean; push to GitHub (`git push github main`) and the box mirror (`git push origin main`).
2. Rebuild the UI once from the committed tree: `cd ~/spark-md-app/ui && npm run build` (never `npm ci`; it undoes the Electron sandbox fix).
3. `bin/sparkmd-status`: LLM, worker, sandbox/gateway, whisper, TTS, fw, dups all OK. **Do not** run Q's runner with sandbox probes or off-loopback 403 probes during recording (they write rows into the on-screen agent log).
4. Clear the hero's OpenClaw ask sessions (A, needs Ty's approval) so old long answers can't bias the takes.

**B. Dry run (online, ~10 min, Joyce clicking)**
1. Relaunch Electron on the box display (then fullscreen it):
   `tmux kill-session -t sparkmd-ui; pkill -x electron; tmux new-session -d -s sparkmd-ui -c ~/spark-md-app/ui "DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority SPARKMD_UI_URL=http://127.0.0.1:8100/ ./node_modules/electron/dist/electron --ozone-platform=x11 --remote-debugging-address=127.0.0.1 --remote-debugging-port=9350 --user-data-dir=$HOME/.config/spark-md-ui-desktop ."`
2. `POST /api/demo/reset` → worklist empty; then `POST /api/demo/replay {"patient_id":"134503","timepoints":["T0","T1"]}`.
3. Joyce: T0 confirm → category 3 → wait for drafts → Approve both → T1 confirm → 4B → drafts → Approve both → inbox shows 2 letters. Ask one warm-up chip per study (first ask per study costs ~13 s; warm ~5 s), then the on-camera chips: "Show me the nodule", "Compare it to last year", "Why did you flag this?". Voice only with the real mic tested.
4. Time each wait (drop→awaiting ~39 s; confirm→drafts ~97 s at G4 with thinking on; re-measure with thinking off). These waits become labelled cuts ("time skipped" / "N× speed") in the edit.

**C. Recording (offline)**
1. At the console: stop Orca/SSH sessions you don't need; **pull the LAN cable, turn Wi-Fi off** (capture this for the unplug shot).
2. `POST /api/demo/reset` (zeroes the network counters) from a box terminal: `curl -s -X POST 127.0.0.1:8100/api/demo/reset -H 'Content-Type: application/json' -d '{}'`. Monitor should read ~0 bytes sent and link down.
3. Start screen capture; replay T0,T1 as in B; Joyce does every Confirm/Approve; agent log visible during the time machine; disclaimer visible throughout.
4. Stop capture. Keep the raw file; note wall-clock times of each cut for the labels.

**D. After recording**
1. Wi-Fi on, cable in; copy the video off the box; upload (Joyce).
2. Final QA quick pass on the submitted commit (online, sandbox probes OK now), tag, push by 17:00.
3. **Before returning the box (17:15):** wipe Ty's credentials: `gh auth logout`; `rm -rf ~/.omp ~/.claude ~/.config/gh`; remove Ty's key from `~/.ssh/authorized_keys`; delete `~/spark-md-app*`, `~/spark-md`, `~/spark-md-runtime-w`, `~/spark-md-render-cache`, `~/qwen38-27b-tensorfold`, `~/sparkmd-voice`, `~/logs`; stop containers (`docker stop qwen38-27b-tf sparkmd-tts`) and the OpenShell sandbox/gateway; `docker image rm` the loaded images. Ask the organizers if they wipe boxes anyway.

## Submission checklist (due 17:30: video + repo; GB10 returned)

- [ ] Working demo on the GB10, cold restart tested
- [ ] Repo (name from BuilderBase's Oct 23 email); contains no `data/`, `models/`, wheelhouse, container tars, MVP code, secrets, tokens, venue passwords
- [ ] Video **under 2:00**, disclaimer visible, honest labels
- [ ] Writeup with credits (if still required): NLST (TCIA, CC BY 4.0, doi:10.7937/TCIA.HMQ8-J677), LIDC-IDRI (CC BY 3.0, doi:10.7937/K9/TCIA.2015.LO9QL9SX + Armato 2011), IDC (Fedorov 2023), Lung-RADS v2022 (ACR)
- [ ] NVIDIA feedback form (if still required)
- [ ] Final `git status` clean; tag the submitted commit
- [ ] GB10 returned at 17:30
- [ ] Pitch deck by 19:00

## Before leaving tonight (prep, Ty at the console)

- ~~Remove the E10 leftovers~~ **done Oct 25 ~01:45:** `sparkdry` user + home gone, no owner DROP rule in OUTPUT, `/home/ty` back to `drwxr-x---`.
- Run `scripts/e9_pack_drive.sh` check again if anything under `docs/` changed after the drive was packed; the drive holds docs, not code.
- Delete `tmp/` and both MVP copies **after** the specs freeze (AGENTS.md rule 5). Confirm no MVP code is on the drive.
- Bring: see `docs/spark-md-prep-checklist.md` → Bring on the day (now includes the switch, cables and USB-C Ethernet adapter).

## Open / unverified

- **Ask the organizers (Joyce):** (1) is the hard deadline for video + repo 17:30 or 18:00; (2) do top-8 teams get their GB10 back for the 19:00 live demo; (3) the GB10 username, whether SSH is allowed and whether we can plug our switch into it; (4) repo: public GitHub? naming? is a channel required (E12; decided for v1: no channel)? Is the writeup / NVIDIA form still required?
- E12: top-8 format answered by the announcement: 3 min demo + 2 min Q&A, deck due 19:00.
- ~~How code gets from the laptops to the box~~ → **re-decided Oct 25 ~09:55:** code starts on the Mac at 10:10 and moves to the box after bring-up (§Mac-first start); push the repo from the box when internet is up.
- ~~Which coding agent drives the sessions~~ → **decided Oct 25 ~09:55:** Claude Code on the box over venue Wi-Fi; fallback DeepSeek cluster via the Mac's SSH reverse tunnel (the box has no Tailscale). Cluster checked from the Mac 09:45: `http://100.114.195.121:8091/v1`, model `DeepSeek-V4.1-Flash-1017`, 524k context.
- When the box arrives (teams of 4–5 first) and how long bring-up takes on it: USB copy time and the first-time TensorFold CUDA compile on the real box are estimates.
- `spark0` creation, the `:8000` block (now also against venue Wi-Fi) and the cold sandbox build on the event box.
- Whether the box has wired Ethernet free for our switch while it is on Wi-Fi (affects the cable-pull shot).
- Voice: kept for now, Ty decides by 13:00. Extras: proposed cut up front, Ty to confirm.
- Event repo (Oct 25 ~10:00): `~/Desktop/spark-md-app` on the Mac, GitHub `spark-md` (private until the organizers say public); no repo name in the BuilderBase email ("Dell x Nvidia Hackathon via BuilderBase @ Frontier Tower").
- All timeline clock times and per-agent start dependencies.
- Whether the storyboard (confirm click, T0→T1 pacing) fits under 2:00; Joyce recuts it.
